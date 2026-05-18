"""
结构锚字段在 retriever 层的端到端测试：
  - Chroma metadata 序列化 / 反序列化对称
  - _metadata_for_chunk 在主索引和增强索引上都带三个字段，且为标量字符串
  - SearchResult 经 _rrf_merge 透传 anchors_used / anchors_defined / refs_outbound

不依赖 ChromaDB / 真实 embedding / rank-bm25，全部为纯函数级单元测试。

运行：pytest tests/test_anchor_metadata.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from retriever import (
    SearchResult,
    _deserialize_anchor_list,
    _follow_cross_refs,
    _metadata_for_chunk,
    _rrf_merge,
    _serialize_anchor_list,
    _with_cross_refs,
)


# ── 序列化对称 ────────────────────────────────────────────────────────────────

class TestAnchorListSerialization:

    def test_empty_round_trip(self):
        assert _serialize_anchor_list([]) == ""
        assert _serialize_anchor_list(None) == ""
        assert _deserialize_anchor_list("") == []
        assert _deserialize_anchor_list(None) == []

    def test_single_item_round_trip(self):
        s = _serialize_anchor_list(["(1)"])
        assert isinstance(s, str)
        assert _deserialize_anchor_list(s) == ["(1)"]

    def test_multi_item_round_trip(self):
        items = ["(1)", "(2)", "(3)"]
        s = _serialize_anchor_list(items)
        assert s == "(1)|(2)|(3)"
        assert _deserialize_anchor_list(s) == items

    def test_refs_round_trip(self):
        items = ["Figure 6-5", "Section 7.5"]
        s = _serialize_anchor_list(items)
        assert _deserialize_anchor_list(s) == items

    def test_no_empty_components(self):
        """解析时丢弃空字符串组件，避免 "|" 误产生空元素。"""
        assert _deserialize_anchor_list("|(1)||(2)|") == ["(1)", "(2)"]


# ── _metadata_for_chunk 产物 ──────────────────────────────────────────────────

class TestMetadataForChunk:

    def test_metadata_contains_three_anchor_fields(self):
        chunk = {
            "source": "x.md",
            "chunk_index": 0,
            "text": "...",
            "is_table": True,
            "is_datasheet": True,
            "index_kind": "block",
            "anchors_used": ["(1)", "(2)"],
            "anchors_defined": ["(1)"],
            "refs_outbound": ["Figure 6-5"],
        }
        m = _metadata_for_chunk(chunk)
        assert m["anchors_used"] == "(1)|(2)"
        assert m["anchors_defined"] == "(1)"
        assert m["refs_outbound"] == "Figure 6-5"

    def test_metadata_field_types_are_chroma_safe(self):
        """ChromaDB metadata 只接受标量类型，三字段必须是 str。"""
        chunk = {
            "source": "x.md", "chunk_index": 0, "text": "t",
            "anchors_used": ["(1)"], "anchors_defined": [], "refs_outbound": [],
        }
        m = _metadata_for_chunk(chunk)
        for key in ("anchors_used", "anchors_defined", "refs_outbound"):
            assert isinstance(m[key], str), f"{key} 应为 str 以兼容 ChromaDB"

    def test_metadata_handles_missing_anchor_fields(self):
        """缺字段的 chunk（如旧版本数据）应回落为空字符串，不抛异常。"""
        chunk = {"source": "x.md", "chunk_index": 0, "text": "t"}
        m = _metadata_for_chunk(chunk)
        assert m["anchors_used"] == ""
        assert m["anchors_defined"] == ""
        assert m["refs_outbound"] == ""


# ── _rrf_merge 透传新字段 ─────────────────────────────────────────────────────

def _mk_result(text: str, score: float, **extra) -> SearchResult:
    base = {
        "text": text,
        "source": "x.md",
        "score": score,
        "is_table": False,
        "is_datasheet": False,
        "index_kind": "block",
        "anchors_used": [],
        "anchors_defined": [],
        "refs_outbound": [],
    }
    base.update(extra)
    return SearchResult(**base)


class TestRrfMergePreservesAnchors:

    def test_anchors_passed_through(self):
        a = [_mk_result("alpha", 0.9, anchors_used=["(1)"], anchors_defined=["(1)"], refs_outbound=["Figure 1"])]
        b = [_mk_result("beta", 0.8, anchors_used=["(2)"])]
        merged = _rrf_merge(a, b, top_k=2)
        by_text = {r["text"]: r for r in merged}
        assert by_text["alpha"]["anchors_used"] == ["(1)"]
        assert by_text["alpha"]["anchors_defined"] == ["(1)"]
        assert by_text["alpha"]["refs_outbound"] == ["Figure 1"]
        assert by_text["beta"]["anchors_used"] == ["(2)"]


# ── cross-reference following ────────────────────────────────────────────────

class TestCrossRefFollowing:

    def test_follows_section_ref_in_same_source(self):
        top = [
            _mk_result(
                "See Section 7.5 for timing.",
                0.8,
                source="chip.md",
                refs_outbound=["Section 7.5"],
            )
        ]
        chunks = [
            {
                "source": "chip.md",
                "chunk_index": 1,
                "text": "## 7.5 Timing Requirements\n\nTarget section body.",
                "is_table": False,
                "is_datasheet": True,
                "index_kind": "block",
                "anchors_used": [],
                "anchors_defined": [],
                "refs_outbound": [],
            }
        ]

        followed = _follow_cross_refs(top, chunks)

        assert len(followed) == 1
        assert followed[0]["facet"] == "cross_ref_followed"
        assert followed[0]["followed_ref"] == "Section 7.5"
        assert followed[0]["score"] == 0.56
        assert "Target section body" in followed[0]["text"]

    def test_does_not_follow_across_sources(self):
        top = [_mk_result("See Figure 6-5.", 1.0, source="a.md", refs_outbound=["Figure 6-5"])]
        chunks = [
            {
                "source": "b.md",
                "chunk_index": 1,
                "text": "Figure 6-5. Other document figure.",
                "is_table": False,
                "is_datasheet": True,
                "index_kind": "block",
                "anchors_used": [],
                "anchors_defined": [],
                "refs_outbound": [],
            }
        ]

        assert _follow_cross_refs(top, chunks) == []

    def test_respects_max_refs(self):
        top = [
            _mk_result(
                f"See Section {i}.",
                1.0,
                source="chip.md",
                refs_outbound=[f"Section {i}"],
            )
            for i in range(10)
        ]
        chunks = [
            {
                "source": "chip.md",
                "chunk_index": i,
                "text": f"## {i} Section {i}\n\nBody {i}",
                "is_table": False,
                "is_datasheet": True,
                "index_kind": "block",
                "anchors_used": [],
                "anchors_defined": [],
                "refs_outbound": [],
            }
            for i in range(10)
        ]

        followed = _follow_cross_refs(top, chunks, max_refs=5)

        assert len(followed) == 5
        assert all(r["facet"] == "cross_ref_followed" for r in followed)

    def test_with_cross_refs_can_include_followed_when_top_k_full(self):
        """base 已满 top_k 时, cross-ref 候选仍参与最终按分裁剪。"""
        base = [
            _mk_result("See Section 7.5.", 0.9, source="chip.md", refs_outbound=["Section 7.5"]),
            _mk_result("low score base", 0.1, source="chip.md"),
        ]
        chunks = [
            {
                "source": "chip.md",
                "chunk_index": 7,
                "text": "## 7.5 Target\n\nFollowed body.",
                "is_table": False,
                "is_datasheet": True,
                "index_kind": "block",
                "anchors_used": [],
                "anchors_defined": [],
                "refs_outbound": [],
            }
        ]

        out = _with_cross_refs(base, chunks, top_k=2)

        assert [r["text"] for r in out] == ["See Section 7.5.", "## 7.5 Target\n\nFollowed body."]
        assert out[1]["facet"] == "cross_ref_followed"
