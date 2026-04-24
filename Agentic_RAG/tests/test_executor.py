"""
TDD：executor 的执行逻辑测试
运行：pytest tests/test_executor.py -v
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from executor import execute_plan


# ── 测试用 Mock ───────────────────────────────────────────────────────────────

def make_retriever(results: list) -> MagicMock:
    """创建返回固定结果的 Mock Retriever"""
    retriever = MagicMock()
    retriever.vector_search.return_value = results
    return retriever


def make_skill_registry(skill_name: str, results: list) -> dict:
    """创建包含单个 Mock Skill 的注册表"""
    return {
        skill_name: {
            "meta": {"name": skill_name},
            "execute": MagicMock(return_value=results),
        }
    }


SAMPLE_RESULTS = [{"text": "A类城市：深圳、广州", "source": "doc.md", "score": 0.9}]


# ── 基本执行 ──────────────────────────────────────────────────────────────────

class TestBasicExecution:

    def test_single_step_executed(self):
        """单步计划应正常执行并返回结果"""
        plan = {
            "steps": [
                {"step_id": 1, "skill": "search_classification", "query": "深圳分类", "depends_on": None}
            ]
        }
        registry = make_skill_registry("search_classification", SAMPLE_RESULTS)
        retriever = make_retriever(SAMPLE_RESULTS)

        steps = execute_plan(plan, retriever, skill_registry=registry)

        assert len(steps) == 1
        assert steps[0]["skill"] == "search_classification"
        assert steps[0]["results"] == SAMPLE_RESULTS

    def test_multi_step_all_executed(self):
        """多步计划的每个 step 都应被执行"""
        plan = {
            "steps": [
                {"step_id": 1, "skill": "search_classification", "query": "深圳分类", "depends_on": None},
                {"step_id": 2, "skill": "search_standards", "query": "A类住宿费", "depends_on": None},
            ]
        }
        registry = {
            "search_classification": {"meta": {}, "execute": MagicMock(return_value=SAMPLE_RESULTS)},
            "search_standards": {"meta": {}, "execute": MagicMock(return_value=SAMPLE_RESULTS)},
        }
        retriever = make_retriever(SAMPLE_RESULTS)

        steps = execute_plan(plan, retriever, skill_registry=registry)

        assert len(steps) == 2


# ── depends_on 与占位符 ───────────────────────────────────────────────────────

class TestDependsOnAndPlaceholder:

    def test_placeholder_replaced_with_step1_result(self):
        """{{step_1_result}} 应被第1步检索结果的摘要替换"""
        plan = {
            "steps": [
                {"step_id": 1, "skill": "search_classification", "query": "深圳分类", "depends_on": None},
                {"step_id": 2, "skill": "search_standards", "query": "<step_1_result> 住宿费", "depends_on": 1},
            ]
        }
        step2_execute = MagicMock(return_value=[])
        registry = {
            "search_classification": {"meta": {}, "execute": MagicMock(return_value=SAMPLE_RESULTS)},
            "search_standards": {"meta": {}, "execute": step2_execute},
        }
        retriever = make_retriever(SAMPLE_RESULTS)

        execute_plan(plan, retriever, skill_registry=registry)

        # 验证 step2 的 query 中占位符已被替换（不含原始占位符字符串）
        actual_query = step2_execute.call_args[0][0]
        assert "<step_1_result>" not in actual_query
        # 替换内容来自 SAMPLE_RESULTS[0]["text"] 的清洗结果（去除表格符号）
        assert "A类城市" in actual_query or "深圳" in actual_query


# ── 异常容错 ──────────────────────────────────────────────────────────────────

class TestErrorHandling:

    def test_missing_skill_returns_empty_results(self):
        """Skill 不存在时，该步骤返回空结果，不崩溃"""
        plan = {
            "steps": [
                {"step_id": 1, "skill": "nonexistent_skill", "query": "test", "depends_on": None}
            ]
        }
        retriever = make_retriever([])

        steps = execute_plan(plan, retriever, skill_registry={})

        assert len(steps) == 1
        assert steps[0]["results"] == []

    def test_skill_exception_returns_empty_results(self):
        """Skill 执行抛出异常时，返回空结果，不崩溃，后续 step 继续执行"""
        plan = {
            "steps": [
                {"step_id": 1, "skill": "bad_skill", "query": "test", "depends_on": None},
                {"step_id": 2, "skill": "good_skill", "query": "test2", "depends_on": None},
            ]
        }
        registry = {
            "bad_skill": {"meta": {}, "execute": MagicMock(side_effect=RuntimeError("崩了"))},
            "good_skill": {"meta": {}, "execute": MagicMock(return_value=SAMPLE_RESULTS)},
        }
        retriever = make_retriever([])

        steps = execute_plan(plan, retriever, skill_registry=registry)

        assert steps[0]["results"] == []
        assert steps[1]["results"] == SAMPLE_RESULTS

    def test_empty_steps_returns_empty_list(self):
        """空 steps 计划应返回空列表"""
        plan = {"steps": []}
        steps = execute_plan(plan, make_retriever([]), skill_registry={})
        assert steps == []
