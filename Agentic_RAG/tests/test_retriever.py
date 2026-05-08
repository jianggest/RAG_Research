"""
Retriever 模块测试

覆盖范围：
  - bm25_search：精确关键词匹配行为（不依赖 ChromaDB）
  - _rrf_merge：RRF 融合算法的正确性（纯函数）
  - hybrid_search：降级逻辑（Mock 两路子方法）
  - search：策略路由正确性（Mock 子方法）

不覆盖：
  - vector_search 的真实向量相似度（依赖 ChromaDB + embedding，属于集成测试范畴）
  - build_index 的索引建立过程
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
import pytest
import types
import hashlib

from retriever import Retriever, _rrf_merge


# ── 测试用 chunk 数据 ──────────────────────────────────────────────────────────

def make_chunk(text: str, source: str = "test.md", index: int = 0) -> dict:
    return {"text": text, "source": source, "chunk_index": index, "is_table": False}


CITY_CHUNKS = [
    make_chunk("A 类地区：北京、上海、广州、深圳", index=0),
    make_chunk("B 类地区：珠海、汕头、厦门、大连", index=1),
    make_chunk("C 类地区：其他", index=2),
    make_chunk("住宿费报销标准：A类420元/天，B类350元/天，C类250元/天", index=3),
    make_chunk("出差补贴按实际天数计算", index=4),
]


# ── bm25_search 测试 ──────────────────────────────────────────────────────────

class TestBm25Search:

    def setup_method(self):
        self.retriever = Retriever(CITY_CHUNKS)

    def test_finds_chunk_containing_keyword(self):
        """BM25 应能精确命中包含"深圳"的 chunk"""
        results = self.retriever.bm25_search("深圳", top_k=3)
        assert len(results) > 0
        assert any("深圳" in r["text"] for r in results), "Top 结果应包含'深圳'"

    def test_top1_is_most_relevant(self):
        """搜索"深圳"时，Top-1 应是 A 类城市 chunk 而非其他"""
        results = self.retriever.bm25_search("深圳", top_k=5)
        assert "深圳" in results[0]["text"]

    def test_returns_empty_for_entity_not_in_corpus(self):
        """揭阳不在任何 chunk 中，BM25 应返回空列表（体现 Phase 3 需要处理此边界）"""
        results = self.retriever.bm25_search("揭阳", top_k=5)
        assert results == [], f"揭阳不在语料中，预期空列表，实际返回: {results}"

    def test_returns_empty_for_empty_query(self):
        results = self.retriever.bm25_search("", top_k=5)
        assert results == []

    def test_returns_empty_for_blank_query(self):
        results = self.retriever.bm25_search("   ", top_k=5)
        assert results == []

    def test_returns_empty_when_no_chunks(self):
        retriever = Retriever([])
        results = retriever.bm25_search("深圳", top_k=5)
        assert results == []

    def test_respects_top_k(self):
        results = self.retriever.bm25_search("类", top_k=2)
        assert len(results) <= 2

    def test_result_has_required_fields(self):
        results = self.retriever.bm25_search("深圳", top_k=1)
        assert len(results) > 0
        r = results[0]
        assert "text" in r
        assert "source" in r
        assert "score" in r

    def test_score_is_positive_for_match(self):
        results = self.retriever.bm25_search("深圳", top_k=1)
        assert results[0]["score"] > 0

    def test_gracefully_handles_missing_rank_bm25(self):
        """rank-bm25 未安装时应返回空列表而非崩溃"""
        with patch.dict("sys.modules", {"rank_bm25": None}):
            # 重新触发 ImportError 路径
            import importlib
            import retriever as retriever_module
            # 直接测试 ImportError 容错：mock BM25Okapi 导入失败
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                results = self.retriever.bm25_search("深圳", top_k=3)
                # 只要不崩溃即可（实际返回取决于是否已缓存）
                assert isinstance(results, list)


# ── _rrf_merge 测试 ───────────────────────────────────────────────────────────

def make_result(text: str, source: str = "test.md", score: float = 0.5) -> dict:
    return {"text": text, "source": source, "score": score}


class TestRrfMerge:

    def test_item_in_both_lists_gets_higher_score(self):
        """同时出现在两路结果中的 chunk，RRF 得分应高于只出现一次的"""
        shared = make_result("共同结果")
        only_a = make_result("仅A路结果")
        only_b = make_result("仅B路结果")

        results_a = [shared, only_a]
        results_b = [shared, only_b]

        merged = _rrf_merge(results_a, results_b, top_k=3)
        texts = [r["text"] for r in merged]

        assert "共同结果" in texts
        shared_score = next(r["score"] for r in merged if r["text"] == "共同结果")
        only_a_score = next(r["score"] for r in merged if r["text"] == "仅A路结果")
        assert shared_score > only_a_score, "两路都出现的结果应得分更高"

    def test_respects_top_k(self):
        results_a = [make_result(f"A{i}") for i in range(5)]
        results_b = [make_result(f"B{i}") for i in range(5)]
        merged = _rrf_merge(results_a, results_b, top_k=3)
        assert len(merged) <= 3

    def test_deduplicates_by_text(self):
        """相同文本内容只保留一条"""
        dup = make_result("重复内容")
        results_a = [dup, make_result("唯一A")]
        results_b = [dup, make_result("唯一B")]
        merged = _rrf_merge(results_a, results_b, top_k=10)
        texts = [r["text"] for r in merged]
        assert texts.count("重复内容") == 1

    def test_returns_empty_for_empty_inputs(self):
        merged = _rrf_merge([], [], top_k=5)
        assert merged == []

    def test_higher_rank_gives_higher_score(self):
        """排名靠前（rank 小）的结果 RRF 得分应更高"""
        results_a = [make_result("第一名"), make_result("第二名"), make_result("第三名")]
        results_b = []
        merged = _rrf_merge(results_a, results_b, top_k=3)
        scores = [r["score"] for r in merged]
        assert scores == sorted(scores, reverse=True), "RRF 得分应按排名降序"


# ── hybrid_search 降级逻辑测试 ────────────────────────────────────────────────

class TestHybridSearch:

    def setup_method(self):
        self.retriever = Retriever(CITY_CHUNKS)

    def test_falls_back_to_vector_when_bm25_empty(self):
        """BM25 无结果时，hybrid 应降级为向量检索结果"""
        fake_vector = [make_result("向量结果")]
        with patch.object(self.retriever, "bm25_search", return_value=[]):
            with patch.object(self.retriever, "vector_search", return_value=fake_vector):
                results = self.retriever.hybrid_search("任意查询", top_k=5)
        assert results == fake_vector

    def test_falls_back_to_bm25_when_vector_empty(self):
        """向量无结果时，hybrid 应降级为 BM25 结果"""
        fake_bm25 = [make_result("BM25结果")]
        with patch.object(self.retriever, "bm25_search", return_value=fake_bm25):
            with patch.object(self.retriever, "vector_search", return_value=[]):
                results = self.retriever.hybrid_search("任意查询", top_k=5)
        assert results == fake_bm25

    def test_merges_when_both_have_results(self):
        """两路都有结果时，返回合并后的列表（非单路结果）"""
        fake_vector = [make_result("向量结果A"), make_result("向量结果B")]
        fake_bm25 = [make_result("BM25结果X"), make_result("共同结果")]
        with patch.object(self.retriever, "bm25_search", return_value=fake_bm25):
            with patch.object(self.retriever, "vector_search", return_value=fake_vector):
                results = self.retriever.hybrid_search("查询", top_k=5)
        result_texts = {r["text"] for r in results}
        # 合并结果应包含两路内容
        assert "向量结果A" in result_texts or "BM25结果X" in result_texts


# ── search 路由测试 ───────────────────────────────────────────────────────────

class TestSearchRouting:

    def setup_method(self):
        self.retriever = Retriever(CITY_CHUNKS)

    def test_routes_to_bm25(self):
        with patch.object(self.retriever, "bm25_search", return_value=[]) as mock:
            self.retriever.search("query", method="bm25", top_k=3)
            mock.assert_called_once_with("query", 3)

    def test_routes_to_vector(self):
        with patch.object(self.retriever, "vector_search", return_value=[]) as mock:
            self.retriever.search("query", method="vector", top_k=3)
            mock.assert_called_once_with("query", 3, where=None)

    def test_routes_to_hybrid(self):
        with patch.object(self.retriever, "hybrid_search", return_value=[]) as mock:
            self.retriever.search("query", method="hybrid", top_k=3)
            mock.assert_called_once_with("query", 3, where=None)

    def test_defaults_to_vector_for_unknown_method(self):
        with patch.object(self.retriever, "vector_search", return_value=[]) as mock:
            self.retriever.search("query", method="unknown", top_k=3)
            mock.assert_called_once()


class _FakeCollection:
    def __init__(self, existing_ids=None):
        self.add_calls = []
        self._ids = set(existing_ids or [])

    def add(self, documents, ids, metadatas):
        self.add_calls.append({
            "documents": documents,
            "ids": ids,
            "metadatas": metadatas,
        })
        self._ids.update(ids)

    def get(self, ids=None, include=None):
        matched = [i for i in (ids or []) if i in self._ids]
        return {"ids": matched}

    def count(self):
        return len(self._ids)


class _FakeClient:
    def __init__(self, existing_ids=None):
        self.collection = _FakeCollection(existing_ids=existing_ids)
        self.deleted = []
        self.created = []

    def delete_collection(self, name):
        self.deleted.append(name)

    def create_collection(self, **kwargs):
        self.created.append(kwargs)
        return self.collection

    def get_or_create_collection(self, **kwargs):
        self.created.append(kwargs)
        return self.collection


def test_build_index_adds_chunks_in_batches_and_logs_progress(monkeypatch, capsys):
    """大知识库索引应分批 add，并输出 flush 进度，避免页面黑盒卡住。"""
    fake_client = _FakeClient()
    fake_chromadb = types.SimpleNamespace(EphemeralClient=lambda: fake_client)
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setattr("retriever._build_embedding_fn", lambda: None)
    monkeypatch.setattr("retriever.INDEX_BATCH_SIZE", 2)
    monkeypatch.setattr("retriever.PERSIST_CHROMA_INDEX", False)

    chunks = [make_chunk(f"chunk {i}", index=i) for i in range(5)]
    retriever = Retriever(chunks)

    retriever.build_index()

    assert [len(call["ids"]) for call in fake_client.collection.add_calls] == [2, 2, 1]
    out = capsys.readouterr().out
    assert "原始索引进度：1-2/5" in out
    assert "原始索引进度：3-4/5" in out
    assert "原始索引建立完成，共 5 条" in out


def test_build_index_skips_already_indexed_chunk_hashes(monkeypatch, capsys):
    """持久化索引已存在的 chunk hash 不应重复 embedding/add。"""
    existing_text = "chunk 0"
    existing_chunk = make_chunk(existing_text, index=0)
    existing_id = "chunk_" + hashlib.md5(
        f"{existing_chunk['source']}\n{existing_chunk['chunk_index']}\n{existing_chunk['text']}".encode()
    ).hexdigest()
    fake_client = _FakeClient(existing_ids=[existing_id])
    fake_chromadb = types.SimpleNamespace(
        EphemeralClient=lambda: fake_client,
        PersistentClient=lambda path: fake_client,
    )
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setattr("retriever._build_embedding_fn", lambda: None)
    monkeypatch.setattr("retriever.INDEX_BATCH_SIZE", 2)
    monkeypatch.setattr("retriever.PERSIST_CHROMA_INDEX", True)

    retriever = Retriever([make_chunk("chunk 0", index=0), make_chunk("chunk 1", index=1)])

    retriever.build_index()

    assert fake_client.deleted == []
    assert len(fake_client.collection.add_calls) == 1
    assert fake_client.collection.add_calls[0]["documents"] == ["chunk 1"]
    assert fake_client.collection.add_calls[0]["ids"] == [
        "chunk_" + hashlib.md5("test.md\n1\nchunk 1".encode()).hexdigest()
    ]
    out = capsys.readouterr().out
    assert "跳过已存在索引：1/2" in out
    assert "新增索引建立完成，共 1 条" in out
