"""
query_understanding 模块测试

覆盖范围：
  - _parse_llm_response：JSON 提取与字段校验
  - _normalize：字段补全与类型保证
  - _fallback_structure：降级结构的正确性
  - parse_query：完整流程（Mock LLM）
  - build_clarification_question：追问文案生成
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import patch

from query_understanding import (
    QueryStructure,
    _fallback_structure,
    _normalize,
    _parse_llm_response,
    build_clarification_question,
    parse_query,
)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def make_llm_response(
    who=None, where="深圳", what="住宿费标准",
    who_inferred=True, where_inferred=False,
    constraints=None, granularity="精确事实",
    missing=None, conflicts=None, needs_clarification=False,
    expanded="其他员工到深圳出差，住宿标准金额是多少",
):
    """构造标准 LLM JSON 响应字符串。"""
    data = {
        "original": "深圳出差住宿的标准",
        "expanded": expanded,
        "dimensions": {
            "who":   {"value": who or "其他员工", "inferred": who_inferred},
            "where": {"value": where,             "inferred": where_inferred},
            "what":  {"value": what,              "inferred": False},
        },
        "entities": [
            {"text": where, "type": "地区名", "role": "查询对象"},
            {"text": what,  "type": "费用项", "role": "目标属性"},
        ],
        "constraints": constraints or [],
        "intent_granularity": granularity,
        "missing": missing or ["who"],
        "conflicts": conflicts or [],
        "needs_clarification": needs_clarification,
    }
    return json.dumps(data, ensure_ascii=False)


# ── _parse_llm_response 测试 ──────────────────────────────────────────────────

class TestParseLlmResponse:

    def test_parses_valid_json(self):
        raw = make_llm_response()
        result = _parse_llm_response(raw, "深圳出差住宿的标准")
        assert result["dimensions"]["where"]["value"] == "深圳"
        assert result["intent_granularity"] == "精确事实"

    def test_extracts_json_from_surrounding_text(self):
        """LLM 在 JSON 前后添加说明文字时应仍能提取"""
        raw = "以下是分析结果：\n" + make_llm_response() + "\n以上。"
        result = _parse_llm_response(raw, "深圳出差住宿的标准")
        assert result["dimensions"]["where"]["value"] == "深圳"

    def test_falls_back_on_empty_response(self):
        result = _parse_llm_response("", "原始问题")
        assert result["original"] == "原始问题"
        assert result["needs_clarification"] is False

    def test_falls_back_on_invalid_json(self):
        result = _parse_llm_response("这不是JSON内容", "原始问题")
        assert result["original"] == "原始问题"
        assert result["entities"] == []

    def test_falls_back_on_missing_braces(self):
        result = _parse_llm_response("没有花括号的文本", "原始问题")
        assert result["expanded"] == "原始问题"


# ── _normalize 测试 ───────────────────────────────────────────────────────────

class TestNormalize:

    def test_fills_missing_dimensions(self):
        """缺少 dimensions 时应补全默认结构"""
        data = {"intent_granularity": "总结性"}
        result = _normalize(data, "原始问题")
        assert result["dimensions"]["who"]["value"] is None
        assert result["dimensions"]["where"]["value"] is None

    def test_preserves_existing_fields(self):
        data = json.loads(make_llm_response(where="揭阳"))
        result = _normalize(data, "揭阳出差住宿的标准")
        assert result["dimensions"]["where"]["value"] == "揭阳"

    def test_defaults_granularity_to_precise(self):
        result = _normalize({}, "问题")
        assert result["intent_granularity"] == "精确事实"

    def test_needs_clarification_defaults_false(self):
        result = _normalize({}, "问题")
        assert result["needs_clarification"] is False

    def test_constraints_defaults_empty_list(self):
        result = _normalize({}, "问题")
        assert result["constraints"] == []

    def test_conflicts_defaults_empty_list(self):
        result = _normalize({}, "问题")
        assert result["conflicts"] == []


# ── _fallback_structure 测试 ──────────────────────────────────────────────────

class TestFallbackStructure:

    def test_preserves_original_question(self):
        result = _fallback_structure("揭阳出差住宿费")
        assert result["original"] == "揭阳出差住宿费"
        assert result["expanded"] == "揭阳出差住宿费"

    def test_does_not_trigger_clarification(self):
        """降级结构不应阻断主流程"""
        result = _fallback_structure("任意问题")
        assert result["needs_clarification"] is False

    def test_all_dimensions_are_none(self):
        result = _fallback_structure("问题")
        for key in ("who", "where", "what"):
            assert result["dimensions"][key]["value"] is None


# ── parse_query 完整流程测试（Mock LLM）──────────────────────────────────────

class TestParseQuery:

    def test_shenzhen_identifies_where_and_what(self):
        """深圳出差住宿费：Where=深圳，What=住宿费，Who 为推断值"""
        mock_response = make_llm_response(
            who="其他员工", who_inferred=True,
            where="深圳", what="住宿费标准",
            missing=["who"],
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("深圳出差住宿的标准")
        assert result["dimensions"]["where"]["value"] == "深圳"
        assert result["dimensions"]["who"]["inferred"] is True
        assert "who" in result["missing"]
        assert result["needs_clarification"] is False

    def test_jieyang_has_same_structure_as_shenzhen(self):
        """揭阳与深圳应产生相同维度结构（Where 类型相同，值不同）"""
        mock_response = make_llm_response(
            where="揭阳", expanded="其他员工到揭阳出差，住宿标准金额是多少",
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("揭阳出差住宿的标准")
        assert result["dimensions"]["where"]["value"] == "揭阳"
        entity_types = [e["type"] for e in result["entities"]]
        assert "地区名" in entity_types

    def test_needs_clarification_when_where_missing(self):
        """只问'住宿费是多少'（无地点）应触发追问"""
        mock_response = make_llm_response(
            where=None, missing=["who", "where"], needs_clarification=True,
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("住宿费是多少")
        assert result["needs_clarification"] is True
        assert "where" in result["missing"]

    def test_constraint_detected(self):
        """含时间/场景约束的问题应提取 constraints"""
        mock_response = json.dumps({
            "original": "2023年后入职员工非工作日出差补贴",
            "expanded": "2023年后入职的其他员工，在非工作日出差的补贴标准是多少",
            "dimensions": {
                "who":   {"value": "其他员工", "inferred": True},
                "where": {"value": None,       "inferred": False},
                "what":  {"value": "出差补贴", "inferred": False},
            },
            "entities": [],
            "constraints": [
                {"type": "时间约束", "value": "2023年后入职", "source": "显式"},
                {"type": "场景约束", "value": "非工作日",     "source": "显式"},
            ],
            "intent_granularity": "精确事实",
            "missing": ["who"],
            "conflicts": [],
            "needs_clarification": False,
        }, ensure_ascii=False)
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("2023年后入职员工非工作日出差补贴")
        constraint_types = [c["type"] for c in result["constraints"]]
        assert "时间约束" in constraint_types
        assert "场景约束" in constraint_types

    def test_conflict_detected(self):
        """P10职级+实习生 应触发冲突检测"""
        mock_response = json.dumps({
            "original": "P10职级实习生出差补贴",
            "expanded": "P10职级的实习生出差补贴标准",
            "dimensions": {
                "who":   {"value": "P10实习生", "inferred": False},
                "where": {"value": None,         "inferred": False},
                "what":  {"value": "出差补贴",   "inferred": False},
            },
            "entities": [],
            "constraints": [],
            "intent_granularity": "精确事实",
            "missing": [],
            "conflicts": ["P10通常为高管职级，与实习生身份存在矛盾"],
            "needs_clarification": False,
        }, ensure_ascii=False)
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("P10职级实习生出差补贴")
        assert len(result["conflicts"]) > 0

    def test_summary_intent_detected(self):
        """'简单说说出差流程' 应识别为总结性意图"""
        mock_response = json.dumps({
            "original": "简单说说出差流程",
            "expanded": "简单说说出差流程",
            "dimensions": {
                "who":   {"value": None, "inferred": False},
                "where": {"value": None, "inferred": False},
                "what":  {"value": "出差流程", "inferred": False},
            },
            "entities": [],
            "constraints": [],
            "intent_granularity": "总结性",
            "missing": [],
            "conflicts": [],
            "needs_clarification": False,
        }, ensure_ascii=False)
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("简单说说出差流程")
        assert result["intent_granularity"] == "总结性"

    def test_falls_back_gracefully_on_llm_failure(self):
        """LLM 调用失败时应降级，不崩溃，needs_clarification=False"""
        with patch("query_understanding.call_llm", return_value=""):
            result = parse_query("深圳出差住宿费")
        assert result["original"] == "深圳出差住宿费"
        assert result["needs_clarification"] is False


# ── 区域无关问题的兜底纠正测试 ────────────────────────────────────────────────

class TestRegionIndependentFallback:
    """相对调整/流程/共享规则类 query：即使 LLM 误判 needs_clarification=True，兜底也应撤销追问。"""

    def test_relative_adjustment_query_overrides_clarification(self):
        """TE31 复现：'同性别2人住宿如何调整'，命中关键词应被兜底纠正"""
        mock_response = make_llm_response(
            who="其他员工", who_inferred=True,
            where=None, where_inferred=False,
            what="住宿标准调整规则",
            missing=["where"], needs_clarification=True,
            expanded="普通员工同性别2人出差同一地点的住宿标准如何调整",
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("普通员工同性别2人出差同一地点，住宿标准如何调整？")
        assert result["needs_clarification"] is False
        assert "where" not in result["missing"]

    def test_process_query_overrides_clarification(self):
        """流程/凭证类：'住宿发票丢了怎么办' 命中关键词应被兜底纠正"""
        mock_response = make_llm_response(
            who="其他员工", who_inferred=True,
            where=None, where_inferred=False,
            what="住宿发票处理流程",
            missing=["where"], needs_clarification=True,
            expanded="住宿发票丢失如何处理",
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("住宿发票丢了怎么办？")
        assert result["needs_clarification"] is False
        assert "where" not in result["missing"]

    def test_only_missing_who_and_where_still_overrides(self):
        """兜底允许同时缺 who（who 有默认值），不影响纠正"""
        mock_response = make_llm_response(
            who=None, who_inferred=False,
            where=None, where_inferred=False,
            what="出差申请审批流程",
            missing=["who", "where"], needs_clarification=True,
            expanded="出差申请审批流程",
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("出差申请审批流程是怎样的？")
        assert result["needs_clarification"] is False
        assert "where" not in result["missing"]

    def test_pure_amount_query_still_asks_clarification(self):
        """反向用例：'住宿费标准是多少' 不含区域无关关键词，仍然追问 Where"""
        mock_response = make_llm_response(
            who="其他员工", who_inferred=True,
            where=None, where_inferred=False,
            what="住宿费标准",
            missing=["where"], needs_clarification=True,
            expanded="出差住宿费标准是多少",
        )
        with patch("query_understanding.call_llm", return_value=mock_response):
            result = parse_query("住宿费标准是多少？")
        assert result["needs_clarification"] is True
        assert "where" in result["missing"]


# ── build_clarification_question 测试 ────────────────────────────────────────

class TestBuildClarificationQuestion:

    def test_asks_about_location_when_where_missing(self):
        qs = _fallback_structure("住宿费是多少")
        qs["missing"] = ["where"]
        question = build_clarification_question(qs)
        assert "城市" in question or "地区" in question

    def test_asks_about_role_when_who_missing(self):
        qs = _fallback_structure("出差补贴是多少")
        qs["missing"] = ["who"]
        question = build_clarification_question(qs)
        assert "职级" in question or "身份" in question

    def test_handles_multiple_missing_dimensions(self):
        qs = _fallback_structure("住宿费是多少")
        qs["missing"] = ["who", "where"]
        question = build_clarification_question(qs)
        assert len(question) > 10

    def test_returns_default_when_missing_is_empty(self):
        qs = _fallback_structure("问题")
        qs["missing"] = []
        question = build_clarification_question(qs)
        assert isinstance(question, str)
        assert len(question) > 0
