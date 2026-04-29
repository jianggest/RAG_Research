"""
search_expense_reimbursement Skill 测试

覆盖当前实现：
  - config/region_classification.json 确定性分类优先，LLM 兜底
  - 单城市境内/境外标准查询词构造
  - 多城市拆分为逐城市检索并合并结果
  - 分类失败时回退原始 query
  - 金额类问题未命中数值时切换表格探测
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.search_expense_reimbursement import _classify_region_by_rules, _split_cities, execute


SOURCE = "报销相关_clean.md"

STANDARD_A = {
    "text": "A类住宿费标准：500元/天",
    "source": SOURCE,
    "score": 0.80,
    "is_table": True,
}
STANDARD_A_EXTRA = {
    "text": "A类差旅补贴标准：100元/天",
    "source": SOURCE,
    "score": 0.70,
    "is_table": True,
}
STANDARD_OVERSEA_A = {
    "text": "境外A类住宿费标准：欧洲、美国、日本、新加坡按实际标准执行，含德国。",
    "source": SOURCE,
    "score": 0.78,
    "is_table": True,
}
STANDARD_OVERSEA_A_EXTRA = {
    "text": "境外A类补贴标准：欧美日新为$50/天。",
    "source": SOURCE,
    "score": 0.74,
    "is_table": True,
}
UNKNOWN_STANDARD = {
    "text": "按原始问题检索得到的备用费用标准：300元/天",
    "source": SOURCE,
    "score": 0.60,
    "is_table": False,
}


def make_query_structure(where: str | None, what: str | None = "住宿费") -> dict:
    return {
        "dimensions": {
            "who": {"value": "其他员工", "inferred": True},
            "where": {"value": where, "inferred": False},
            "what": {"value": what, "inferred": False},
        }
    }


def make_retriever(results_by_keyword: dict[str, list[dict]] | None = None, default: list[dict] | None = None):
    """按查询词关键片段返回结果的 Mock Retriever。"""
    retriever = MagicMock()
    results_by_keyword = results_by_keyword or {}
    default = default or []

    def mock_search(query: str, method: str, top_k: int = 5, where: dict | None = None):
        for keyword in sorted(results_by_keyword, key=len, reverse=True):
            if keyword in query:
                return results_by_keyword[keyword]
        return default

    retriever.search.side_effect = mock_search
    return retriever


class TestSplitCities:

    def test_splits_comma_chinese_comma_and_he(self):
        assert _split_cities("深圳,德国，香港和揭阳") == ["深圳", "德国", "香港", "揭阳"]

    def test_strips_empty_parts(self):
        assert _split_cities(" 深圳 ，  德国 ,, ") == ["深圳", "德国"]


class TestRegionClassificationRules:

    def test_mainland_rules_cover_a_b_and_c_examples(self):
        assert _classify_region_by_rules("深圳") == {"scope_label": "境内", "category": "A类"}
        assert _classify_region_by_rules("南昌") == {"scope_label": "境内", "category": "B类"}
        assert _classify_region_by_rules("揭阳") == {"scope_label": "境内", "category": "C类"}

    def test_overseas_rules_cover_a_b_and_c_examples(self):
        assert _classify_region_by_rules("德国") == {"scope_label": "境外", "category": "A类"}
        assert _classify_region_by_rules("越南") == {"scope_label": "境外", "category": "B类"}
        assert _classify_region_by_rules("香港") == {"scope_label": "境外", "category": "C类"}

    def test_normalizes_common_suffixes(self):
        assert _classify_region_by_rules("深圳市") == {"scope_label": "境内", "category": "A类"}
        assert _classify_region_by_rules("香港特别行政区") == {"scope_label": "境外", "category": "C类"}


class TestSingleCityClassification:

    def test_mainland_city_uses_category_and_what_for_standards_query(self):
        retriever = make_retriever({
            "A类 住宿费": [STANDARD_A, STANDARD_A_EXTRA],
        })

        with patch(
            "skills.search_expense_reimbursement.llm_classify_region",
            return_value={},
        ) as mock_classify:
            results = execute(
                "深圳出差住宿费",
                retriever,
                query_structure=make_query_structure("深圳", "住宿费"),
            )

        mock_classify.assert_not_called()

        vector_calls = [
            c for c in retriever.search.call_args_list
            if c.kwargs.get("method") == "vector"
        ]
        assert vector_calls[0].args[0] == "A类 住宿费"

        assert results[0]["is_conclusion"] is True
        assert "深圳 属于境内A类地区" in results[0]["text"]
        assert any("A类住宿费标准" in r["text"] for r in results)

    def test_overseas_city_keeps_scope_city_and_what_in_standards_query(self):
        retriever = make_retriever({
            "境外 A类 德国 住宿费": [STANDARD_OVERSEA_A, STANDARD_OVERSEA_A_EXTRA],
        })

        with patch(
            "skills.search_expense_reimbursement.llm_classify_region",
            return_value={},
        ) as mock_classify:
            results = execute(
                "德国出差住宿费",
                retriever,
                query_structure=make_query_structure("德国", "住宿费"),
            )

        mock_classify.assert_not_called()

        vector_calls = [
            c for c in retriever.search.call_args_list
            if c.kwargs.get("method") == "vector"
        ]
        assert vector_calls[0].args[0] == "境外 A类 德国 住宿费"
        assert results[0]["is_conclusion"] is True
        assert "德国 属于境外A类地区" in results[0]["text"]

    def test_unknown_category_uses_llm_fallback_then_original_query_when_still_unknown(self):
        retriever = make_retriever({
            "某城市出差住宿费": [UNKNOWN_STANDARD],
        })

        with patch(
            "skills.search_expense_reimbursement.llm_classify_region",
            return_value={},
        ) as mock_classify:
            results = execute(
                "某城市出差住宿费",
                retriever,
                query_structure=make_query_structure("某城市", "住宿费"),
            )

        mock_classify.assert_called_once()
        assert mock_classify.call_args.args[1] == "某城市"

        vector_calls = [
            c for c in retriever.search.call_args_list
            if c.kwargs.get("method") == "vector"
        ]
        assert vector_calls[0].args[0] == "某城市出差住宿费"
        assert not any(r.get("is_conclusion") for r in results)
        assert any(r["text"] == UNKNOWN_STANDARD["text"] for r in results)

    def test_unknown_city_uses_llm_fallback_when_config_has_no_match(self):
        retriever = make_retriever({
            "境外 B类 火星 住宿费": [UNKNOWN_STANDARD],
        })

        with patch(
            "skills.search_expense_reimbursement.llm_classify_region",
            return_value={"scope_label": "境外", "category": "B类"},
        ) as mock_classify:
            results = execute(
                "火星出差住宿费",
                retriever,
                query_structure=make_query_structure("火星", "住宿费"),
            )

        mock_classify.assert_called_once()
        vector_calls = [
            c for c in retriever.search.call_args_list
            if c.kwargs.get("method") == "vector"
        ]
        assert vector_calls[0].args[0] == "境外 B类 火星 住宿费"
        assert results[0]["is_conclusion"] is True
        assert "火星 属于境外B类地区" in results[0]["text"]


class TestMultiCity:

    def test_multi_city_query_runs_each_city_and_merges_results(self):
        retriever = make_retriever({
            "境外 A类 德国 住宿费": [STANDARD_OVERSEA_A, STANDARD_OVERSEA_A_EXTRA],
            "A类 住宿费": [STANDARD_A, STANDARD_A_EXTRA],
        })

        with patch(
            "skills.search_expense_reimbursement.llm_classify_region",
            return_value={},
        ) as mock_classify:
            results = execute(
                "深圳和德国出差住宿费",
                retriever,
                query_structure=make_query_structure("深圳，德国", "住宿费"),
            )

        mock_classify.assert_not_called()

        vector_queries = [
            c.args[0] for c in retriever.search.call_args_list
            if c.kwargs.get("method") == "vector"
        ]
        assert vector_queries == ["A类 住宿费", "境外 A类 德国 住宿费"]

        conclusion_texts = [r["text"] for r in results if r.get("is_conclusion")]
        assert any("深圳 属于境内A类地区" in t for t in conclusion_texts)
        assert any("德国 属于境外A类地区" in t for t in conclusion_texts)
        conclusion_maps = [
            (r.get("entity"), r.get("scope_label"), r.get("category"), r.get("full_category"))
            for r in results
            if r.get("is_conclusion")
        ]
        assert ("深圳", "境内", "A类", "境内A类") in conclusion_maps
        assert ("德国", "境外", "A类", "境外A类") in conclusion_maps
        assert any("A类住宿费标准" in r["text"] for r in results)
        assert any("境外A类住宿费标准" in r["text"] for r in results)


class TestAmountRetry:

    def test_amount_query_retries_table_search_when_no_numeric_standard(self):
        non_numeric = {
            "text": "住宿费报销需符合公司差旅制度。",
            "source": SOURCE,
            "score": 0.66,
            "is_table": False,
        }
        retry_table = {
            "text": "A类住宿费表格标准：500元/天",
            "source": SOURCE,
            "score": 0.90,
            "is_table": True,
        }

        retriever = MagicMock()
        retriever.search.side_effect = [
            [non_numeric],
            [retry_table],
        ]

        with patch(
            "skills.search_expense_reimbursement.llm_classify_region",
            return_value={},
        ) as mock_classify:
            results = execute(
                "深圳出差住宿费多少",
                retriever,
                query_structure=make_query_structure("深圳", "住宿费"),
            )

        mock_classify.assert_not_called()

        assert len(retriever.search.call_args_list) == 2
        retry_call = retriever.search.call_args_list[1]
        assert retry_call.args[0] == "A类 住宿 交通 补贴"
        assert retry_call.kwargs["where"] == {
            "$and": [{"source": {"$in": [SOURCE]}}, {"is_table": True}]
        }
        assert any("500元/天" in r["text"] for r in results)
