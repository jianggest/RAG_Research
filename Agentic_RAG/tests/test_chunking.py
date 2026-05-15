"""
TDD：document_loader 的分块逻辑测试
运行：pytest tests/test_chunking.py -v
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from document_loader import chunk_markdown, chunk_text


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def find_chunks_with_keyword(chunks: list, keyword: str) -> list:
    return [c for c in chunks if keyword in c["text"]]


# ── 表格完整性 ────────────────────────────────────────────────────────────────

class TestTableIntegrity:

    def test_small_table_is_single_chunk(self):
        """节内容（标题+表格）不超过 max_size 时，应保存为一个完整 chunk"""
        content = "## 城市分类\n\n| 类别 | 城市 |\n|------|------|\n| A类 | 深圳 |\n| B类 | 杭州 |"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        # 整节内容在一个 chunk 里，A类和B类不被拆开
        assert len(chunks) == 1
        assert "A类" in chunks[0]["text"]
        assert "B类" in chunks[0]["text"]

    def test_large_table_stays_complete(self):
        """超过 max_size 的表格仍应保持完整，不被截断"""
        rows = "\n".join([f"| 城市{i} | {i*100} |" for i in range(20)])
        content = f"| 城市 | 金额 |\n|------|------|\n{rows}"
        chunks = chunk_markdown(content, "test.md", max_size=100)  # 故意设小
        table_chunks = [c for c in chunks if c["is_table"]]
        assert len(table_chunks) == 1, "大表格不应被拆成多个 chunk"
        # 验证所有行都在
        assert "城市19" in table_chunks[0]["text"]

    def test_empty_line_inside_table_does_not_split(self):
        """表格中间的空行不应中断表格，应保持为一个 chunk"""
        content = "| 类别 | 城市 |\n|------|------|\n| A类 | 深圳 |\n\n| B类 | 杭州 |"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        table_chunks = [c for c in chunks if c["is_table"]]
        assert len(table_chunks) == 1
        assert "A类" in table_chunks[0]["text"]
        assert "B类" in table_chunks[0]["text"]

    def test_table_chunk_is_flagged(self):
        """表格 chunk 的 is_table 字段应为 True"""
        content = "| 列1 | 列2 |\n|-----|-----|\n| a | b |"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert all(c["is_table"] for c in chunks)

    def test_table_with_heading_is_flagged(self):
        """带前置标题的表格 chunk 也应标记为 is_table=True（datasheet 表格常见形态）"""
        content = "## 6.10 System Oscillator Timing Requirements\n\n| 参数 | MIN | MAX |\n|------|-----|-----|\n| f clk | 23.998 | 24.002 |"
        chunks = chunk_markdown(content, "dlpc3436.md", max_size=600)
        assert len(chunks) == 1
        assert chunks[0]["is_table"] is True

    def test_dlpc3436_oscillator_table_absorbs_footnotes(self):
        """Task4: 6.10 oscillator timing 表格和 (1)(2) 脚注应保持在同一 chunk。"""
        content = (
            "## 6.10 System Oscillator Timing Requirements\n\n"
            "| PARAMETER | TEST CONDITIONS | MIN | TYP | MAX | UNIT |\n"
            "|-----------|-----------------|-----|-----|-----|------|\n"
            "| Crystal oscillator frequency, f_xtal (1) | MOSC input | 23.998 | 24 | 24.002 | MHz |\n"
            "| External oscillator frequency, f_ext (2) | MOSC input | 23.998 | 24 | 24.002 | MHz |\n"
            "\n"
            "(1) The frequency accuracy for MOSC is ±200 PPM over all conditions.\n"
            "(2) Spread spectrum clocking is not supported on the MOSC input.\n"
        )
        chunks = chunk_markdown(content, "dlpc3436.md", max_size=160)
        table_chunks = [c for c in chunks if c["is_table"] and "System Oscillator Timing" in c["text"]]

        assert len(table_chunks) == 1
        chunk = table_chunks[0]
        assert "(1) The frequency accuracy" in chunk["text"]
        assert "(2) Spread spectrum" in chunk["text"]
        assert {"(1)", "(2)"}.issubset(set(chunk["anchors_defined"]))
        assert "23.998" in chunk["text"]
        assert "±200 PPM" in chunk["text"]

    def test_non_table_chunk_is_not_flagged(self):
        """普通文本 chunk 的 is_table 字段应为 False"""
        content = "这是一段普通文本，没有表格。"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert all(not c["is_table"] for c in chunks)


# ── 普通文本分块 ──────────────────────────────────────────────────────────────

class TestTextChunking:

    def test_text_within_limit_is_single_chunk(self):
        """不超过 max_size 的文本应作为一个 chunk"""
        content = "短文本内容"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert len(chunks) == 1

    def test_long_text_is_split(self):
        """超过 max_size 的普通文本应被拆分"""
        content = "字" * 1000
        chunks = chunk_markdown(content, "test.md", max_size=200)
        assert len(chunks) > 1

    def test_chunk_source_is_preserved(self):
        """每个 chunk 应保留 source 字段"""
        chunks = chunk_markdown("内容", "my_doc.md", max_size=600)
        assert all(c["source"] == "my_doc.md" for c in chunks)

    def test_chunk_index_is_sequential(self):
        """chunk_index 应从 0 开始连续递增"""
        content = "\n\n".join([f"段落{i}" for i in range(5)])
        chunks = chunk_markdown(content, "test.md", max_size=600)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_content_returns_no_chunks(self):
        """空内容不应生成任何 chunk"""
        chunks = chunk_markdown("", "test.md", max_size=600)
        assert chunks == []

    def test_whitespace_only_content_returns_no_chunks(self):
        """纯空白内容不应生成任何 chunk"""
        chunks = chunk_markdown("   \n\n   ", "test.md", max_size=600)
        assert chunks == []


# ── 纯文本分块 ────────────────────────────────────────────────────────────────

class TestChunkText:

    def test_text_file_basic(self):
        """txt 文件能正常分块"""
        chunks = chunk_text("hello world", "test.txt", max_size=600)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "hello world"
        assert chunks[0]["is_table"] is False


# ── 结构锚字段（V2 检索用）────────────────────────────────────────────────────

class TestStructureAnchors:
    """验证 _build_chunk 在 anchors_used / anchors_defined / refs_outbound 上的提取行为。"""

    def test_plain_text_has_empty_anchor_fields(self):
        """无脚注无跨引用的普通文本：三个字段都为空列表"""
        chunks = chunk_markdown("这是一段普通文本，没有脚注也没有跨引用。", "test.md", max_size=600)
        assert chunks
        assert chunks[0]["anchors_used"] == []
        assert chunks[0]["anchors_defined"] == []
        assert chunks[0]["refs_outbound"] == []

    def test_table_cell_anchors_are_used(self):
        """表格单元格内的 (1) (2) 应进入 anchors_used"""
        content = (
            "| 参数 | 值 |\n"
            "|------|-----|\n"
            "| Voltage (1) | 3.3V |\n"
            "| Current (2) | 100mA |"
        )
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert len(chunks) == 1
        assert chunks[0]["anchors_used"] == ["(1)", "(2)"]
        assert chunks[0]["anchors_defined"] == []

    def test_footnote_line_defines_anchor(self):
        """行首形如 "(1) ..." 的脚注行进入 anchors_defined"""
        content = (
            "| 参数 | 值 |\n"
            "|------|-----|\n"
            "| f_clk (1) | 24 MHz |\n"
            "\n"
            "(1) The frequency accuracy for MOSC is ±200 PPM. Spread spectrum not supported."
        )
        chunks = chunk_markdown(content, "test.md", max_size=600)
        # 脚注吸附后表格与脚注同属一个 chunk
        assert len(chunks) == 1
        chunk = chunks[0]
        assert "(1)" in chunk["anchors_used"]
        assert "(1)" in chunk["anchors_defined"]
        assert "±200 PPM" in chunk["text"]

    def test_bracket_and_note_defined_forms(self):
        """[1] ... / Note 1: ... / [^1]: ... / - (1) ... 都应被识别为 defined"""
        content = (
            "## 脚注示例\n\n"
            "[1] 方括号定义形式\n"
            "Note 2: Note 形式\n"
            "[^3]: Markdown footnote 语法\n"
            "- (4) 列表项形式"
        )
        chunks = chunk_markdown(content, "test.md", max_size=600)
        defined = set()
        for c in chunks:
            defined.update(c["anchors_defined"])
        assert {"(1)", "(2)", "(3)", "(4)"}.issubset(defined)

    def test_sup_inline_anchor_used(self):
        """<sup>(1)</sup> / <sup>2</sup> 写法计入 anchors_used"""
        content = "参数 A <sup>(1)</sup> 和 参数 B <sup>2</sup> 都需要校准。"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert "(1)" in chunks[0]["anchors_used"]
        assert "(2)" in chunks[0]["anchors_used"]

    def test_refs_outbound_figure_and_section(self):
        """See Figure X-Y / Refer to Section X.Y 应提取到 refs_outbound"""
        content = "详细布局参考 See Figure 6-5 与 Refer to Section 7.5 的描述。"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        refs = chunks[0]["refs_outbound"]
        assert "Figure 6-5" in refs
        assert "Section 7.5" in refs

    def test_refs_outbound_dedup_and_case(self):
        """同一引用多次出现去重；kind 首字母统一大写"""
        content = "see figure 6-5; SEE FIGURE 6-5 again; refer to section 7.5."
        chunks = chunk_markdown(content, "test.md", max_size=600)
        refs = chunks[0]["refs_outbound"]
        assert refs.count("Figure 6-5") == 1
        assert "Section 7.5" in refs

    def test_defined_anchor_does_not_double_count_as_used(self):
        """行首的 "(1) ..." 中的 (1) 只算 defined，不应同时计入 used"""
        content = "(1) 这是脚注定义。"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert chunks[0]["anchors_defined"] == ["(1)"]
        assert chunks[0]["anchors_used"] == []

    def test_mixed_defined_and_used_on_same_line(self):
        """同行混合：行首 (1) 是 defined，行内出现的 (2) 是 used"""
        content = "(1) 定义部分，详见 (2) 的说明。"
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert chunks[0]["anchors_defined"] == ["(1)"]
        assert chunks[0]["anchors_used"] == ["(2)"]

    def test_plain_text_parentheses_not_treated_as_used(self):
        """普通正文里的 "(1)" "(2)" 等括号编号（非表格行、无 <sup>、非脚注定义）不应进 anchors_used。

        避免将"步骤(1)/参数(2)"等正文修辞误判为脚注引用。
        """
        content = (
            "## 安装步骤\n\n"
            "请按顺序执行：先确认环境(1)，再安装依赖(2)，最后启动服务(3)。\n"
            "本节描述的是一般流程，与表格脚注无关。"
        )
        chunks = chunk_markdown(content, "test.md", max_size=600)
        for c in chunks:
            assert c["anchors_used"] == [], (
                f"普通正文不应提取 anchors_used，但得到 {c['anchors_used']}"
            )
            assert c["anchors_defined"] == []

    def test_table_anchors_extracted_even_when_no_definition(self):
        """表格里出现 (1)/(2) 但本 chunk 没有脚注定义行：仍应提取 anchors_used。

        典型场景：表格在一个 chunk，脚注因吸附失败被切到下一个 chunk。
        used 字段保留信息，便于后续做跨 chunk 关联（Task 6）。
        """
        content = (
            "| 参数 | 值 |\n"
            "|------|-----|\n"
            "| A (1) | 100 |\n"
            "| B (2) | 200 |"
        )
        chunks = chunk_markdown(content, "test.md", max_size=600)
        assert chunks[0]["anchors_used"] == ["(1)", "(2)"]
        assert chunks[0]["anchors_defined"] == []
