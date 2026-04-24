"""
TDD：planner 的 JSON 解析与容错测试
运行：pytest tests/test_planner.py -v
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from planner import plan, parse_plan_json


# ── parse_plan_json 单元测试（纯函数，无需 Mock LLM）────────────────────────

class TestParsePlanJson:

    def test_valid_json_parsed_correctly(self):
        """合法 JSON 应正确解析"""
        raw = '''{"reasoning": "需要两步", "steps": [{"step_id": 1, "skill": "search_classification", "query": "深圳", "depends_on": null}]}'''
        result = parse_plan_json(raw)
        assert "error" not in result
        assert len(result["steps"]) == 1

    def test_json_embedded_in_text_is_extracted(self):
        """LLM 在 JSON 前后附加文字时，应自动提取 JSON 部分"""
        raw = '好的，我来规划：\n{"reasoning": "test", "steps": []}\n以上是计划。'
        result = parse_plan_json(raw)
        assert "error" not in result

    def test_invalid_json_returns_error(self):
        """非法 JSON 应返回含 error 字段的 dict"""
        result = parse_plan_json("这不是JSON内容")
        assert "error" in result

    def test_missing_steps_field_returns_error(self):
        """缺少 steps 字段应返回 error"""
        result = parse_plan_json('{"reasoning": "test"}')
        assert "error" in result

    def test_steps_not_list_returns_error(self):
        """steps 不是列表时应返回 error"""
        result = parse_plan_json('{"reasoning": "test", "steps": "invalid"}')
        assert "error" in result

    def test_empty_steps_is_valid(self):
        """steps 为空列表是合法的"""
        result = parse_plan_json('{"reasoning": "无需检索", "steps": []}')
        assert "error" not in result
        assert result["steps"] == []


# ── plan() 集成测试（Mock LLM）───────────────────────────────────────────────

class TestPlanFunction:

    def test_plan_returns_parsed_dict_on_success(self):
        """LLM 返回合法 JSON 时，plan() 应返回解析后的 dict"""
        mock_response = '{"reasoning": "先查分类", "steps": [{"step_id": 1, "skill": "search_classification", "query": "深圳", "depends_on": null}]}'

        with patch("planner.call_llm", return_value=mock_response):
            result = plan("深圳住宿费", skill_descriptions="- search_classification: 查分类")

        assert "error" not in result
        assert result["steps"][0]["skill"] == "search_classification"

    def test_plan_returns_error_on_llm_failure(self):
        """LLM 返回空字符串时，plan() 应返回含 error 的 dict"""
        with patch("planner.call_llm", return_value=""):
            result = plan("深圳住宿费", skill_descriptions="")

        assert "error" in result

    def test_plan_returns_error_on_invalid_json(self):
        """LLM 返回非法 JSON 时，plan() 应返回含 error 的 dict"""
        with patch("planner.call_llm", return_value="我不知道怎么回答"):
            result = plan("深圳住宿费", skill_descriptions="")

        assert "error" in result
