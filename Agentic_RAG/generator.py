"""
Generator 模块

职责：将所有 Skill 检索结果整合，调用 LLM 生成最终回答。
对外接口：generate(question, executed_steps, query_structure=None) -> str
"""

from typing import Optional

from llm import call_llm


_ANSWER_PROMPT_TEMPLATE = """\
你是一个企业内部知识库助手。请根据下方检索到的内容回答用户问题。

规则：
1. 答案必须以检索内容为依据，不得捏造
2. 如果检索内容中有地区分类规则，必须主动判断目标地区属于哪一类，再对应查找该类的费用标准
3. 允许基于检索到的规则进行逻辑推理（例如：城市不在A类、B类列表中，则按C类：其他处理）
4. 仅当检索内容确实无法支撑推理时，才回复"根据现有知识库，我暂时无法回答这个问题"
5. 回答时注明信息来源的文档名
6. 回答中出现分类标签（如"A类地区"）时，必须同时说明用户询问的具体实体（如城市名）属于该类，\
例如："深圳属于A类地区，其住宿费标准为..."，不得只说类别而不提原始实体
{style_instruction}{assumption_note}{entity_note}
检索到的内容：
{context}

用户问题：{question}\
"""


def generate(question: str, executed_steps: list, query_structure: Optional[dict] = None) -> str:
    """
    整合所有步骤的检索结果，调用 LLM 生成最终回答。

    Args:
        question:         原始用户问题
        executed_steps:   Executor 返回的执行步骤列表
        query_structure:  QueryUnderstanding 输出的结构化语义（可选）

    Returns:
        LLM 生成的回答文本；无检索结果时返回固定提示。
    """
    context = _build_context(executed_steps)

    if not context:
        return "根据现有知识库，未找到与该问题相关的内容，无法回答。"

    style_instruction = _build_style_instruction(query_structure)
    assumption_note = _build_assumption_note(query_structure)

    entity_note = _build_entity_note(query_structure, executed_steps)

    prompt = _ANSWER_PROMPT_TEMPLATE.format(
        context=context,
        question=question,
        style_instruction=style_instruction,
        assumption_note=assumption_note,
        entity_note=entity_note,
    )
    print(f"[Generator] 开始调用 LLM，prompt 长度：{len(prompt)} 字符")
    answer = call_llm(prompt)
    print(f"[Generator] LLM 返回，回答长度：{len(answer)} 字符")

    if not answer:
        return "（LLM 未返回回答，请检查 Ollama 是否已启动）"

    # 冲突预警追加到回答末尾
    conflict_warning = _build_conflict_warning(query_structure)
    if conflict_warning:
        answer = answer + "\n\n" + conflict_warning

    return answer


def _build_style_instruction(query_structure: Optional[dict]) -> str:
    """根据意图颗粒度生成回答风格指引。"""
    if not query_structure:
        return ""
    granularity = query_structure.get("intent_granularity", "精确事实")
    if granularity == "总结性":
        return "6. 本问题期望概括性回答：合并多个检索结果的要点，给出结构化摘要，不必逐行引用原文\n"
    return "6. 本问题期望精确回答：直接给出具体数字或明确规定，不必展开背景信息\n"


def _build_assumption_note(query_structure: Optional[dict]) -> str:
    """当存在推断维度时，生成假设说明，提示 LLM 在回答中注明。"""
    if not query_structure:
        return ""
    dims = query_structure.get("dimensions", {})
    inferred = [
        f"{label}={dims[key]['value']}"
        for key, label in [("who", "身份"), ("where", "地区")]
        if dims.get(key, {}).get("inferred") and dims[key].get("value")
    ]
    if not inferred:
        return ""
    return f"7. 以下维度为系统推断默认值，请在回答开头注明：{', '.join(inferred)}\n"


def _build_conflict_warning(query_structure: Optional[dict]) -> str:
    """当存在冲突时，生成预警文案追加到回答末尾。"""
    if not query_structure:
        return ""
    conflicts = query_structure.get("conflicts", [])
    if not conflicts:
        return ""
    conflict_desc = "；".join(conflicts) if isinstance(conflicts, list) else str(conflicts)
    return f"⚠️ **注意**：检测到问题中存在逻辑冲突，请核实后再使用以上信息：{conflict_desc}"


def _build_entity_note(
    query_structure: Optional[dict],
    executed_steps: list,
) -> str:
    """
    提取"原始实体 → 分类"映射，注入 prompt，确保 LLM 回答时提及原始实体而非只说类别。

    映射来源：
    - 原始实体：query_structure.dimensions.where / who 的 value
    - 分类结论：executed_steps 中 is_conclusion=True 的 chunk 的 category 字段
    """
    if not query_structure:
        return ""

    dims = query_structure.get("dimensions", {})
    entity = (
        dims.get("where", {}).get("value")
        or dims.get("who", {}).get("value")
    )
    if not entity:
        return ""

    # 从执行结果中找分类结论 chunk
    category = None
    for step in executed_steps:
        for r in step.get("results", []):
            if r.get("is_conclusion") and r.get("category"):
                category = r["category"]
                break
        if category:
            break

    if not category:
        return ""

    return f'7. 已知"{entity}"被识别为"{category}"，回答中必须明确说明"{entity}属于{category}"，再给出对应标准\n'


def _build_context(executed_steps: list) -> str:
    """将各步骤的检索结果整合为上下文字符串，每步最多取 top-3 结果。"""
    parts = []

    for step in executed_steps:
        results = step.get("results", [])
        if not results:
            continue
        parts.append(f"【{step['skill']} 检索结果】")
        for result in results:
            parts.append(f"来源：{result['source']}\n{result['text']}")
            parts.append("---")

    return "\n".join(parts)
