"""
search_expense_reimbursement Skill 测试

覆盖范围：
  - Step 1：BM25 命中显式实体（深圳、广州）→ 直接推断分类，不走向量兜底
  - Step 2：BM25 无结果（揭阳、广水）→ 向量兜底补充分类规则
  - Step 3：llm_classify 结合分类规则推断出正确类别
    - 深圳 → A类
    - 广州 → B类
    - 揭阳 → C类（隐式，须通过向量兜底 + LLM 推断）
    - 广水 → C类（隐式，同揭阳路径）
  - standards_query 构造：有分类时拼接 "{category} {query}"，无分类时用原始 query
  - 向量检索以 standards_query 发起，而非固定的"差旅报销标准"

不覆盖：
  - 真实 LLM 调用（使用 Mock 隔离）
  - 真实向量/BM25 检索（使用 Mock Retriever 隔离）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, call
import pytest

# ── 测试数据 ───────────────────────────────────────────────────────────────────

# 模拟分类规则 chunk（与实际文档规则对齐）
# A类：北京、上海、广州、深圳（显式列出）
# B类：珠海、汕头、厦门、大连等 + 除A类外其他省会城市（含隐式推理）
# C类：其他
CLASSIFICATION_RULE = {
    "text": (
        "A 类地区：北京、上海、广州、深圳；\n"
        "B 类地区：珠海、汕头、厦门、大连、秦皇岛、天津、烟台、青岛、连云港、南通、"
        "宁波、温州、福州、湛江、北海和除A类地区外其他省会城市；\n"
        "C 类地区：其他。"
    ),
    "source": "差旅管理制度.md",
    "score": 0.9,
}

# 模拟费用标准 chunk
STANDARD_A = {"text": "A类城市住宿费标准：500元/天", "source": "差旅管理制度.md", "score": 0.85}
STANDARD_B = {"text": "B类城市住宿费标准：400元/天", "source": "差旅管理制度.md", "score": 0.85}
STANDARD_C = {"text": "C类城市住宿费标准：300元/天", "source": "差旅管理制度.md", "score": 0.85}


def make_mock_retriever(bm25_results: list, vector_results_map: dict = None) -> MagicMock:
    """
    构造 Mock Retriever。

    Args:
        bm25_results:      BM25 检索返回结果
        vector_results_map: 按查询词返回不同向量结果，格式 {query_keyword: [chunks]}
                           未匹配时返回空列表
    """
    retriever = MagicMock()
    vector_results_map = vector_results_map or {}

    def mock_search(query: str, method: str, top_k: int = 5):
        if method == "bm25":
            return bm25_results
        if method == "vector":
            # 最长 key 优先，避免短 key（如"B类"）误命中含城市名的长查询词
            for keyword in sorted(vector_results_map, key=len, reverse=True):
                if keyword in query:
                    return vector_results_map[keyword]
            return []

    retriever.search.side_effect = mock_search
    return retriever


# ── Step 1：BM25 命中显式实体 ──────────────────────────────────────────────────

class TestStep1BM25HitsExplicitEntity:

    def test_shenzhen_bm25_hits_no_vector_fallback(self):
        """深圳：BM25 命中分类规则，不应触发向量兜底"""
        retriever = make_mock_retriever(
            bm25_results=[CLASSIFICATION_RULE],
            vector_results_map={"A类": [STANDARD_A]},
        )
        with patch("llm.call_llm", return_value="A类"):
            from skills.search_expense_reimbursement import execute
            execute("深圳出差住宿费", retriever)

        calls = retriever.search.call_args_list
        # 第一次调用必须是 BM25
        assert calls[0] == call("深圳出差住宿费", method="bm25", top_k=10)
        # BM25 有结果，第二次调用不应再是向量补充分类规则
        # （第二次向量调用是查费用标准，query 应含 "A类"）
        vector_calls = [c for c in calls if c.kwargs.get("method") == "vector"]
        assert len(vector_calls) == 1
        assert "A类" in vector_calls[0].args[0]

    def test_guangzhou_bm25_hits_returns_a_category(self):
        """广州：在 A类 显式列表中，BM25 命中 → LLM 推断 A类"""
        retriever = make_mock_retriever(
            bm25_results=[CLASSIFICATION_RULE],
            vector_results_map={"A类": [STANDARD_A]},
        )
        with patch("llm.call_llm", return_value="A类"):
            from skills.search_expense_reimbursement import execute
            execute("广州出差住宿费", retriever)

        # 费用标准查询词应含 "A类"
        vector_calls = [c for c in retriever.search.call_args_list
                        if c.kwargs.get("method") == "vector"]
        assert "A类" in vector_calls[0].args[0]


# ── Step 2：BM25 无结果时向量兜底 ─────────────────────────────────────────────

class TestStep2VectorFallbackForImplicitEntity:

    def test_jieyang_bm25_empty_triggers_vector_fallback(self):
        """揭阳：BM25 返回空 → 应触发向量检索补充分类规则"""
        retriever = make_mock_retriever(
            bm25_results=[],  # 揭阳不在显式列表
            vector_results_map={
                "揭阳": [CLASSIFICATION_RULE],  # 向量补充分类规则
                "C类": [STANDARD_C],            # 费用标准
            },
        )
        with patch("llm.call_llm", return_value="C类"):
            from skills.search_expense_reimbursement import execute
            execute("揭阳出差住宿费", retriever)

        calls = retriever.search.call_args_list
        # 第一次：BM25 分类检索
        assert calls[0] == call("揭阳出差住宿费", method="bm25", top_k=10)
        # 第二次：向量兜底补充分类规则（BM25 无结果触发）
        assert calls[1] == call("揭阳出差住宿费", method="vector", top_k=5)

    def test_guangshui_bm25_empty_triggers_vector_fallback(self):
        """广水：同揭阳，BM25 空 → 向量兜底"""
        retriever = make_mock_retriever(
            bm25_results=[],
            vector_results_map={
                "广水": [CLASSIFICATION_RULE],
                "C类": [STANDARD_C],
            },
        )
        with patch("llm.call_llm", return_value="C类"):
            from skills.search_expense_reimbursement import execute
            execute("广水出差住宿费", retriever)

        calls = retriever.search.call_args_list
        assert calls[1] == call("广水出差住宿费", method="vector", top_k=5)


# ── Step 3：LLM 推断分类结论 ───────────────────────────────────────────────────

class TestStep3CategoryInference:

    # 按规则划分：
    #   A类（显式）：北京、上海、广州、深圳 → BM25 能命中
    #   B类（显式列表）：珠海、天津、厦门等 → BM25 能命中
    #   B类（省会推理）：成都、杭州、武汉等 → BM25 未命中，须 LLM 推理省会身份
    #   C类（其他）：揭阳、广水等 → BM25 未命中，LLM 推断不是省会 → C类
    @pytest.mark.parametrize("city,bm25_hits,expected_category,standard_chunk", [
        ("深圳", True,  "A类", STANDARD_A),  # A类，显式命中
        ("广州", True,  "A类", STANDARD_A),  # A类，显式命中
        ("天津", True,  "B类", STANDARD_B),  # B类，显式列表命中
        ("成都", False, "B类", STANDARD_B),  # B类，省会推理（BM25 未命中）
        ("揭阳", False, "C类", STANDARD_C),  # C类，非省会非显式列表
        ("广水", False, "C类", STANDARD_C),  # C类，非省会非显式列表
    ])
    def test_category_inferred_correctly(self, city, bm25_hits, expected_category, standard_chunk):
        """各城市应推断出正确分类（含省会推理路径）"""
        # BM25 命中时不触发向量分类兜底，vector_results_map 只需费用标准 key
        # BM25 未命中时，向量兜底用城市名查分类规则，city key 才需要加入
        vector_map = {expected_category: [standard_chunk]}
        if not bm25_hits:
            vector_map[city] = [CLASSIFICATION_RULE]
        retriever = make_mock_retriever(
            bm25_results=[CLASSIFICATION_RULE] if bm25_hits else [],
            vector_results_map=vector_map,
        )
        with patch("llm.call_llm", return_value=expected_category):
            from skills.search_expense_reimbursement import execute
            results = execute(f"{city}出差住宿费", retriever)

        # 结果中应包含费用标准 chunk
        texts = [r["text"] for r in results]
        assert any(expected_category in t for t in texts)

    def test_chengdu_provincial_capital_inferred_as_b(self):
        """成都：BM25 未命中 → 向量拉回规则 → LLM 推理省会城市 → B类
        此测试验证 prompt 引导 LLM 使用地理知识进行省会推理，而非直接输出'未知'"""
        # 用调用顺序区分两次向量调用：
        #   第1次 vector（BM25空触发）→ 分类规则
        #   第2次 vector（费用标准查询）→ B类费用标准
        vector_call_count = {"n": 0}

        def mock_search(query, method, top_k=5):
            if method == "bm25":
                return []
            if method == "vector":
                vector_call_count["n"] += 1
                if vector_call_count["n"] == 1:
                    return [CLASSIFICATION_RULE]   # 分类兜底
                return [STANDARD_B]                # 费用标准

        retriever = MagicMock()
        retriever.search.side_effect = mock_search

        captured_prompts = []
        def fake_llm(prompt):
            captured_prompts.append(prompt)
            return "B类"

        with patch("llm.call_llm", side_effect=fake_llm):
            from skills.search_expense_reimbursement import execute
            results = execute("成都出差住宿费", retriever)

        # prompt 应包含省会推理引导
        assert len(captured_prompts) > 0
        assert "省会" in captured_prompts[0]
        # 最终结果应含 B类 费用标准
        texts = [r["text"] for r in results]
        assert any("B类" in t for t in texts)

    def test_standards_query_uses_category_plus_original(self):
        """费用标准查询词应为 '{category} {原始query}'，而非固定的'差旅报销标准'"""
        retriever = make_mock_retriever(
            bm25_results=[CLASSIFICATION_RULE],
            vector_results_map={"A类": [STANDARD_A]},
        )
        with patch("llm.call_llm", return_value="A类"):
            from skills.search_expense_reimbursement import execute
            execute("深圳出差交通费", retriever)

        vector_calls = [c for c in retriever.search.call_args_list
                        if c.kwargs.get("method") == "vector"]
        standards_query = vector_calls[0].args[0]
        assert "A类" in standards_query
        assert "交通费" in standards_query          # 原始意图保留
        assert standards_query != "A类 差旅报销标准"  # 不能替换为固定词

    def test_no_category_uses_original_query(self):
        """LLM 无法推断分类时，直接用原始 query 查费用标准"""
        retriever = make_mock_retriever(
            bm25_results=[],
            vector_results_map={},  # 向量也没有分类规则
        )
        with patch("llm.call_llm", return_value="未知"):
            from skills.search_expense_reimbursement import execute
            execute("某城市出差住宿费", retriever)

        vector_calls = [c for c in retriever.search.call_args_list
                        if c.kwargs.get("method") == "vector"]
        # 唯一的向量调用（Step2兜底）或费用标准调用，query 应是原始内容
        assert any("某城市" in c.args[0] for c in vector_calls)

    def test_c_class_implicit_city_gets_standard_chunk(self):
        """揭阳推断出 C类 后，最终结果应包含 C类 费用标准 chunk"""
        vector_call_count = {"n": 0}

        def mock_search(query, method, top_k=5):
            if method == "bm25":
                return []
            if method == "vector":
                vector_call_count["n"] += 1
                if vector_call_count["n"] == 1:
                    return [CLASSIFICATION_RULE]   # 分类兜底
                return [STANDARD_C]                # 费用标准

        retriever = MagicMock()
        retriever.search.side_effect = mock_search

        with patch("llm.call_llm", return_value="C类"):
            from skills.search_expense_reimbursement import execute
            results = execute("揭阳出差住宿费", retriever)

        texts = [r["text"] for r in results]
        assert any("C类城市住宿费标准" in t for t in texts)
