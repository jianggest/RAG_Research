"""
Executor 模块

职责：按 Planner 输出的计划串行执行 Skill，处理依赖关系和占位符替换。
对外接口：execute_plan(plan_result, retriever, skill_registry=None) -> list[ExecutedStep]

设计说明：
  - skill_registry 支持依赖注入，便于测试时传入 Mock 注册表
  - 占位符 <step_N_result> 在执行前被替换为对应步骤的关键实体摘要
  - 替换时遍历所有已完成步骤，支持 query 中同时引用多个前置步骤
  - Skill 不存在或执行异常时，返回空结果并继续执行后续步骤（不中断）
"""

from typing import Optional, TypedDict

from utils import extract_key_entities


class ExecutedStep(TypedDict):
    step_id: int
    skill: str
    query: str          # 替换占位符后的实际查询词
    results: list       # list[SearchResult]


def execute_plan(
    plan_result: dict,
    retriever,
    skill_registry: Optional[dict] = None,
    query_structure: Optional[dict] = None,
) -> list[ExecutedStep]:
    """
    按计划顺序执行每个 Skill，收集检索结果。

    Args:
        plan_result:     Planner 输出的计划 dict（含 steps 列表）
        retriever:       Retriever 实例，注入到每个 Skill 的 execute() 中
        skill_registry:  Skill 注册表；为 None 时从 skills 模块动态加载
        query_structure: QueryUnderstanding 输出的结构化信息，透传给 Skill
                         Skill 可从中读取 what 维度，避免已解析的 where 实体污染查询词

    Returns:
        每个执行步骤的结果列表，顺序与 steps 一致。
    """
    if skill_registry is None:
        from skills import get_registry
        skill_registry = get_registry()

    step_summaries: dict = {}   # step_id → 关键实体摘要，用于占位符替换
    executed_steps = []

    for step in plan_result.get("steps", []):
        step_id = step["step_id"]
        skill_name = step["skill"]

        # 替换 query 中所有已完成步骤的占位符（支持多个前置依赖）
        query = _resolve_all_placeholders(step["query"], step_summaries)
        results = _run_skill(skill_name, query, retriever, skill_registry, query_structure)

        # 提炼关键实体摘要，用于后续步骤的占位符替换
        # 使用实体提取而非原始截断，避免 Markdown 表格格式符号污染查询词
        step_summaries[step_id] = extract_key_entities(results)

        executed_steps.append(
            ExecutedStep(step_id=step_id, skill=skill_name, query=query, results=results)
        )

    return executed_steps


def _resolve_all_placeholders(query: str, step_summaries: dict) -> str:
    """
    替换 query 中所有 <step_N_result> 占位符。

    遍历全部已完成步骤，支持 query 中同时引用多个前置步骤，
    例如："<step_1_result> 在 <step_2_result> 下的标准"
    """
    for step_id, summary in step_summaries.items():
        query = query.replace(f"<step_{step_id}_result>", summary)
    return query


def _run_skill(
    skill_name: str,
    query: str,
    retriever,
    registry: dict,
    query_structure: Optional[dict] = None,
) -> list:
    """执行单个 Skill，异常时返回空列表并打印日志。"""
    if skill_name not in registry:
        print(f"[Executor] ⚠️ Skill '{skill_name}' 未注册，跳过")
        return []

    print(f"[Executor] Step → {skill_name} | query: {query}")
    try:
        results = registry[skill_name]["execute"](query, retriever, query_structure=query_structure)
        print(f"[Executor]   └─ 返回 {len(results)} 条结果")
        for i, r in enumerate(results, 1):
            preview = r.get("text", "")[:150].replace("\n", " ")
            score = r.get("score", 0)
            source = r.get("source", "")
            is_conclusion = " [结论]" if r.get("is_conclusion") else ""
            print(f"[Executor]   [{i}]{is_conclusion} {source} score={score:.3f} | {preview}")
        return results
    except Exception as e:
        print(f"[Executor] ❌ Skill '{skill_name}' 执行异常: {e}")
        return []
