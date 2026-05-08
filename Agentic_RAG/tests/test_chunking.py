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
