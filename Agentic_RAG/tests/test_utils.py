"""
utils 模块测试

覆盖范围：
  - extract_key_entities：结论优先 > 表格清洗 > 纯文本截取
  - clean_table_text：Markdown 表格转纯文本
  - llm_classify_region：LLM 统一推断地理范围 + 费用分类（Mock LLM）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from utils import clean_table_text, extract_key_entities, llm_classify_region


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def make_result(text: str, score: float = 0.5, is_conclusion: bool = False, category: str = "") -> dict:
    r = {"text": text, "source": "test.md", "score": score}
    if is_conclusion:
        r["is_conclusion"] = True
        r["category"] = category
    return r


# ── extract_key_entities 测试 ─────────────────────────────────────────────────

class TestExtractKeyEntities:

    def test_returns_placeholder_for_empty(self):
        assert extract_key_entities([]) == "（未找到相关内容）"

    def test_conclusion_chunk_takes_priority(self):
        """is_conclusion=True 的结论 chunk 应优先于其他所有结果"""
        conclusion = make_result("分类结论：A类", is_conclusion=True, category="A类")
        other = make_result("A 类地区：北京、上海、广州、深圳")
        result = extract_key_entities([conclusion, other])
        assert result == "A类"

    def test_conclusion_priority_even_if_not_first(self):
        """结论 chunk 不在第一位时仍应被优先取用"""
        other = make_result("A 类地区：北京、上海、广州、深圳")
        conclusion = make_result("分类结论：B类", is_conclusion=True, category="B类")
        result = extract_key_entities([other, conclusion])
        assert result == "B类"

    def test_table_cleaned_when_no_conclusion(self):
        """无结论 chunk 时，含表格的文本应被清洗"""
        table_result = make_result("| A类 | 北京 |\n|---|---|\n| B类 | 珠海 |")
        result = extract_key_entities([table_result])
        assert "|" not in result
        assert "A类" in result

    def test_plain_text_truncated_when_no_conclusion(self):
        """无结论且无表格时，截取前200字"""
        long_text = "这是普通文本" * 50  # 300 字
        result = extract_key_entities([make_result(long_text)])
        assert len(result) <= 200

    def test_conclusion_without_category_falls_through(self):
        """is_conclusion=True 但 category 为空时，不使用该结论，降级到下一规则"""
        bad_conclusion = {"text": "分类结论", "source": "test.md", "score": 1.0,
                          "is_conclusion": True, "category": ""}
        plain = make_result("普通文本内容")
        result = extract_key_entities([bad_conclusion, plain])
        assert result == "普通文本内容"


# ── clean_table_text 测试 ─────────────────────────────────────────────────────

class TestCleanTableText:

    def test_extracts_cell_content(self):
        table = "| 城市类别 | 包含城市 |\n|---------|---------|\n| A类城市 | 北京、上海、广州、深圳 |"
        result = clean_table_text(table)
        assert "A类城市" in result
        assert "深圳" in result
        assert "|" not in result

    def test_skips_separator_rows(self):
        table = "| 列1 | 列2 |\n|---|---|\n| 值1 | 值2 |"
        result = clean_table_text(table)
        assert "---" not in result
        assert "值1" in result

    def test_empty_input(self):
        assert clean_table_text("") == ""

    def test_truncates_at_300(self):
        long_row = "| " + "很长的内容" * 20 + " |"
        table = "\n".join([long_row] * 10)
        result = clean_table_text(table)
        assert len(result) <= 300


# ── llm_classify_region 测试 ─────────────────────────────────────────────────

class TestLlmClassifyRegion:

    def test_returns_scope_and_category_from_llm(self):
        """LLM 返回有效分类时应解析出地理范围和类别"""
        chunks = [{"text": "A 类地区：北京、上海、广州、深圳", "source": "test.md", "score": 0.9}]
        with patch("llm.call_llm", return_value="境内A类"):
            result = llm_classify_region(chunks, "深圳")
        assert result == {"scope_label": "境内", "category": "A类"}

    def test_accepts_space_between_scope_and_category(self):
        """支持 '境外 B类' 这类带空格输出"""
        chunks = [{"text": "境外 A类：欧洲、美国、日本；境外 B类：其他国家", "source": "test.md", "score": 0.9}]
        with patch("llm.call_llm", return_value="境外 B类"):
            result = llm_classify_region(chunks, "德国")
        assert result == {"scope_label": "境外", "category": "B类"}

    def test_returns_empty_for_unknown(self):
        """LLM 返回'未知'时应返回空 dict"""
        chunks = [{"text": "A 类：北京；B类：珠海", "source": "test.md", "score": 0.9}]
        with patch("llm.call_llm", return_value="未知"):
            result = llm_classify_region(chunks, "揭阳")
        assert result == {}

    def test_returns_empty_when_no_chunks_or_city(self):
        """无规则 chunk 或无地名时不调用 LLM，直接返回空 dict"""
        with patch("llm.call_llm") as mock_llm:
            assert llm_classify_region([], "揭阳") == {}
            assert llm_classify_region([{"text": "规则"}], "") == {}
        mock_llm.assert_not_called()

    def test_returns_empty_for_too_long_response(self):
        """LLM 返回过长内容（非标准分类结果）时过滤掉"""
        chunks = [{"text": "分类规则", "source": "test.md", "score": 0.9}]
        with patch("llm.call_llm", return_value="这是一段很长的解释文字，不是分类名称，应该被过滤掉"):
            result = llm_classify_region(chunks, "某城市")
        assert result == {}

    def test_returns_empty_on_llm_failure(self):
        """LLM 调用失败时返回空 dict，不崩溃"""
        chunks = [{"text": "分类规则", "source": "test.md", "score": 0.9}]
        with patch("llm.call_llm", return_value=""):
            result = llm_classify_region(chunks, "某城市")
        assert result == {}

    def test_only_uses_top3_chunks(self):
        """只使用 top-3 chunk，不把所有结果都塞进 prompt"""
        chunks = [{"text": f"chunk{i}", "source": "test.md", "score": 0.9} for i in range(10)]
        captured_prompt = []
        def fake_llm(prompt):
            captured_prompt.append(prompt)
            return "境内A类"
        with patch("llm.call_llm", side_effect=fake_llm):
            llm_classify_region(chunks, "查询")
        assert "chunk3" not in captured_prompt[0]
        assert "chunk0" in captured_prompt[0]
