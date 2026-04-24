"""
Agentic RAG 流程编排模块

职责：串联 QueryUnderstanding → Planner → Executor → Generator，对外提供统一的 run() 入口。
      本模块只做编排，不包含任何业务逻辑。

对外接口：
  run(question, retriever) -> RunResult

流程（v2.0）：
  Step 0: QueryUnderstanding — 语义解析，识别维度/约束/意图/冲突
  Step 1: Planner            — 结合语义结构制定检索计划
  Step 2: Executor           — 串行执行 Skill
  Step 3: Generator          — 综合推理生成回答
"""

from typing import TypedDict

from executor import execute_plan
from generator import generate
from planner import plan
from query_understanding import QueryStructure, build_clarification_question, parse_query
from skills import get_skill_descriptions


class RunResult(TypedDict):
    question: str
    query_structure: QueryStructure  # Step 0 输出
    plan: dict                       # Planner 输出（含 reasoning 和 steps）
    executed_steps: list             # Executor 输出（含每步 skill、query、results）
    answer: str                      # Generator 输出
    needs_clarification: bool        # True 时 answer 为追问文案


def run(question: str, retriever) -> RunResult:
    """
    执行完整的 Agentic RAG 流程（v2.0）。

    Args:
        question:  用户提问
        retriever: 已建立索引的 Retriever 实例

    Returns:
        RunResult，包含中间过程和最终回答，供 app.py 展示。
    """
    # ── Step 0: 查询语义解析 ─────────────────────────────────────────────────
    query_structure = parse_query(question)

    # 关键维度缺失时，直接追问用户，不进入检索流程
    if query_structure["needs_clarification"]:
        clarification = build_clarification_question(query_structure)
        return RunResult(
            question=question,
            query_structure=query_structure,
            plan={},
            executed_steps=[],
            answer=clarification,
            needs_clarification=True,
        )

    # ── Step 1: Planner ──────────────────────────────────────────────────────
    skill_descriptions = get_skill_descriptions()
    plan_result = plan(question, skill_descriptions, query_structure)

    if "error" in plan_result:
        return RunResult(
            question=question,
            query_structure=query_structure,
            plan=plan_result,
            executed_steps=[],
            answer=f"规划失败，请重新提问。（原因：{plan_result['error']}）",
            needs_clarification=False,
        )

    # ── Step 2: Executor ─────────────────────────────────────────────────────
    executed_steps = execute_plan(plan_result, retriever, query_structure=query_structure)

    # ── Step 3: Generator ────────────────────────────────────────────────────
    answer = generate(question, executed_steps, query_structure)

    return RunResult(
        question=question,
        query_structure=query_structure,
        plan=plan_result,
        executed_steps=executed_steps,
        answer=answer,
        needs_clarification=False,
    )
