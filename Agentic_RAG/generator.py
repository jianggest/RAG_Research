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
7. 若检索内容中包含"## 第N页"格式的页码标记，在回答最后单独一行用以下格式注明实际引用的页码：\
[引用页面: 第N页, 第M页]（仅列出真正用于回答的页码，未用到的页不列）
{style_instruction}{assumption_note}{entity_note}
检索到的内容：
{context}

用户问题：{question}\
"""


_TECHNICAL_DATASHEET_PROMPT_TEMPLATE = """\
你是一个技术 datasheet 问答助手。请只根据下方检索到的内容回答用户问题。

规则：
1. 答案必须以检索内容为依据，不得捏造，不得用常识补齐。
2. 必须用中文回答；英文技术术语需要翻译为中文说明，但保留必要的英文参数符号和单位，例如 f clk、t c、t w(H)、t w(L)、t t、t jp、PLL_REFCLK_I、PLL_REFCLK_O、MHz、ns、ppm。
3. 数值、符号、单位必须逐字保留：不得四舍五入，不得改写 ±、%、MHz、ns、kHz、V、mA，不得把 23.998 写成 23.99。
4. 若检索内容包含参数表，优先按 Markdown 表格输出；表格中的数值/单位/符号按原文保留，只翻译参数说明。
5. Notes、脚注、补充条件、规格书阅读路径闭环中的 condition/constraint/dependency 单独列为“关键技术补充要求”；补充说明可翻译成中文，但原始符号、引脚名、单位、限制词（如 internal use、leave unconnected）必须保留。
6. 不得把 Absolute Maximum Ratings 当作 Recommended Operating Conditions；不得把 TI internal use 解释为用户可用接口。
7. 对 spread spectrum、jitter、transition time、external oscillator、pullup、HOST_IRQ、ready/initialization 等条件性事实，必须有检索证据才可回答；如果没检索到证据，明确说“未在检索内容中找到”。
8. 如果检索内容来自多个章节，请按“主答案 / 关键技术补充要求 / 注意事项”组织，避免把不同表格的约束混在一行。
9. 回答时注明信息来源的文档名。
10. 检索内容如包含“必须覆盖的期望术语/数值”，最终回答必须逐项原样包含这些术语/数值；不要只摘要第一行，同一参数的 continuation rows / 多个电压档位必须全部枚举。
11. 检索内容如包含“结构化引用”，回答末尾必须保留这些引用，格式为 [Section: ...; Table: ...; Row: ...; line: ...]。
12. 检索内容如包含“规格书阅读路径闭环”，最终回答必须从该闭环生成：覆盖 anchors 的 value/spec，并逐项覆盖 followed_cues 中的 condition、constraint、prohibition、definition、dependency；若 closure_complete=False 或存在 unresolved_cues，必须在注意事项中说明未闭合线索。

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

    if _is_technical_datasheet_answer(executed_steps, query_structure):
        prompt = _TECHNICAL_DATASHEET_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
        )
        print(f"[Generator] 开始调用技术 datasheet LLM，prompt 长度：{len(prompt)} 字符")
        answer = call_llm(prompt)
        print(f"[Generator] LLM 返回，回答长度：{len(answer)} 字符")
        answer = answer or "（LLM 未返回回答，请检查 Ollama 是否已启动）"
        return _append_structured_references(answer, executed_steps)

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


def _is_technical_datasheet_answer(executed_steps: list, query_structure: Optional[dict]) -> bool:
    """根据 domain 或执行 Skill 判断是否使用技术 datasheet 回答 prompt。"""
    if query_structure and query_structure.get("domain") == "technical_datasheet":
        return True
    return any(step.get("skill") == "search_datasheet" for step in executed_steps)


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
    # 只注明地区推断，身份推断对用户意义不大且容易造成干扰
    inferred = [
        f"{label}={dims[key]['value']}"
        for key, label in [("where", "地区")]
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
    - 优先使用 executed_steps 中 is_conclusion=True 的结构化字段 entity/category/full_category
    - 兼容旧数据：无 entity 时回退 query_structure.dimensions.where / who 的 value
    """
    if not query_structure:
        return ""

    dims = query_structure.get("dimensions", {})
    fallback_entity = (
        dims.get("where", {}).get("value")
        or dims.get("who", {}).get("value")
    )
    entity_categories = []
    seen: set[tuple[str, str]] = set()
    for step in executed_steps:
        for r in step.get("results", []):
            if r.get("is_conclusion") and r.get("category"):
                entity = r.get("entity") or fallback_entity
                category = r.get("full_category") or r.get("category")
                if not entity or not category:
                    continue
                key = (entity, category)
                if key not in seen:
                    seen.add(key)
                    entity_categories.append(key)

    if not entity_categories:
        return ""

    if len(entity_categories) == 1:
        entity, category = entity_categories[0]
        return f'7. 已知"{entity}"被识别为"{category}"，回答中必须明确说明"{entity}属于{category}"，再给出对应标准\n'

    mapping = "；".join(f"{entity}属于{category}" for entity, category in entity_categories)
    return f"7. 已知多个地区分类结论：{mapping}。回答中必须逐一对应地区说明分类和标准，不得只使用第一个地区的分类\n"


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
            reading_closure = _format_reading_closure(result.get("reading_closure"))
            if reading_closure:
                parts.append(reading_closure)
            required_terms = result.get("required_terms") or result.get("must_have_terms") or []
            if required_terms:
                parts.append("必须覆盖的期望术语/数值：" + "；".join(str(term) for term in required_terms))
            ref = _format_structured_reference(result)
            if ref:
                parts.append(f"结构化引用：{ref}")
            parts.append("---")

    return "\n".join(parts)


def _format_reading_closure(closure: Optional[dict]) -> str:
    """把 specification-RAG reading_closure 注入上下文，供最终回答覆盖完整阅读路径。"""
    if not isinstance(closure, dict):
        return ""

    lines = ["规格书阅读路径闭环："]
    subject = closure.get("subject")
    if subject:
        lines.append(f"- subject: {subject}")
    lines.append(f"- closure_complete={bool(closure.get('closure_complete'))}")

    for label, items in (
        ("anchors", closure.get("anchors") or []),
        ("followed_cues", closure.get("followed_cues") or []),
        ("unresolved_cues", closure.get("unresolved_cues") or []),
    ):
        if not isinstance(items, list) or not items:
            continue
        lines.append(f"- {label}:")
        for item in items:
            if not isinstance(item, dict):
                continue
            relation = item.get("relation") or "unspecified"
            cue_type = item.get("cue_type")
            quote = item.get("quote") or item.get("text") or ""
            source = item.get("source") or ""
            line = item.get("line") or item.get("source_line") or ""
            confidence = item.get("confidence")
            meta = [f"relation={relation}"]
            if cue_type:
                meta.append(f"cue_type={cue_type}")
            if source:
                meta.append(f"source={source}")
            if line:
                meta.append(f"line={line}")
            if confidence is not None:
                meta.append(f"confidence={confidence}")
            lines.append(f"  - {'; '.join(meta)} | quote: {quote}")
    return "\n".join(lines)


def _append_structured_references(answer: str, executed_steps: list) -> str:
    """在技术 datasheet 回答末尾追加去重后的结构化引用。"""
    refs = []
    seen = set()
    for step in executed_steps:
        for result in step.get("results", []):
            ref = _format_structured_reference(result)
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
    if not refs:
        return answer
    missing = [ref for ref in refs if ref not in answer]
    if not missing:
        return answer
    return answer.rstrip() + "\n\n结构化引用：\n" + "\n".join(f"- {ref}" for ref in missing)


def _format_structured_reference(result: dict) -> str:
    """把 evidence metadata 格式化为 [Section/Table/Row/line] 引用。"""
    section = result.get("section_title") or result.get("section_id")
    line = result.get("source_line")
    if not section and not line:
        return ""

    parts = []
    if section:
        parts.append(f"Section: {section}")
    if result.get("table_id"):
        parts.append(f"Table: {result['table_id']}")
    if result.get("row_id"):
        parts.append(f"Row: {result['row_id']}")
    if line:
        parts.append(f"line: {line}")
    return "[" + "; ".join(parts) + "]"
