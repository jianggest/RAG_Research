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
你是一个技术资料阅读助手。你的任务不是复述检索片段，也不是展示内部检索过程，而是像一个认真读完资料的人一样，用自然、清晰、可信的方式回答用户问题。

回答原则：
1. 只能依据提供的资料回答，不得引入资料外的常识补全。
2. 如果资料已经能够回答问题的主要部分，第一句应先直接概括已知结论，再说明这是否为完整列表；不要以资料缺口或完整性不足作为回答开头。
3. 回答应像技术说明或研究摘要，而不是审计报告、检索日志或系统提示。
4. 当资料不足以支持“完整清单”时，不要直接拒答。要明确区分：
   - 已经能够明确确认的内容
   - 可以据资料归纳出的范围、条件或边界
   - 资料中暂时无法确认的部分
5. 如果问题是“支持哪些”“最高多少”“是否支持”“有什么区别”这类问题，优先按“结论 → 分类说明 → 条件或限制 → 未确认部分”来组织。
6. 如果多个文档共同支撑答案，要分清主文档和补充文档各自提供了什么，不要混成同一层级，也不要让补充文档压过主文档。
7. 不要输出任何内部系统术语或中间字段，例如：证据单元、reading task、routed documents、closure_complete、primary_source、matching_rows、table_header、evidence path 等。
8. 不要出现“未从当前证据单元中抽取到可回答内容”这类面向系统而不是面向用户的话。
9. 技术术语可以保留英文原文，但整体说明必须是自然中文；必要时可中英并列。
10. 数值、单位、频率、版本号、接口名、模式名必须与资料一致，不得改写、模糊化或四舍五入。
11. 若资料中包含参数规格表（如电气特性、时序参数），且用户问题本身是在询问具体参数、范围、时序或电气指标，优先用 Markdown 表格呈现关键字段（如参数名/符号/最小值/典型值/最大值/单位）；表中数值按原文保留，参数说明可翻译为中文。若整表过长，可仅保留与问题直接相关的行。
12. 如果资料里存在脚注、注释、限制条件、版本边界、兼容性说明、例外情况，必须写进正文，不能只给孤立结论。
13. 不得将 Absolute Maximum Ratings 与 Recommended Operating Conditions 混淆；引用参数时必须注明其所属的规格表类别。
14. 不要机械地逐条复述检索片段，要把相近信息合并整理后再回答。
15. 如果资料中存在明确的表格、模式列表、分辨率列表或条件矩阵，可以整理成简洁列表或表格；如果直接抄表会影响阅读，就改写成条目式总结。但参数规格表（电气特性、时序等）应优先保留表格形式（见规则 11）。
16. 若资料只能支持部分确认，正文主体仍应聚焦已确认事实；完整性不足、资料缺口或未确认部分只在后文用一小段说明一次，不要反复强调。
17. 避免反复使用“根据当前资料”“当前片段里”“能明确确认”“不能据此断言”这类免责声明；如确需说明证据边界，集中在一处简洁表达即可。
18. 若问题涉及多个知识点，默认使用 1. 2. 3. 编号展开；只有问题非常简单时才使用纯自然段。每个编号项直接写技术结论，不要使用“当前资料”“当前片段”“资料表明”作为标题或主语。
19. 除非用户明确要求，不要展示大段原文摘录。
20. 如果上下文中带有结构化引用，可将其保留在答案末尾作为附录；不要让引用列表打断正文叙述，也不要让正文变成引用清单。

输出格式要求：
1. 第一段先用 2 到 4 句话直接回答用户问题。
2. 如问题涉及多个方面，使用 1. 2. 3. 编号的知识点展开；每个编号项就是一个主要部分，不必再额外添加同层级小节标题。若问题本身较简单，可以只用自然段回答，不必强行编号。
3. 如果问题本身是在问“完整支持列表”，但资料没有给出完整总表，应明确说明“当前资料未见完整总表”，同时继续给出已经可以确认的内容；这类边界提醒只需说明一次。
4. 结尾单独一行写：
信息来源：文档名1；文档名2；……
5. 如果上下文中已经带有结构化引用，可保留在答案末尾，单独作为“结构化引用”附录，不要让它打断正文。

请直接给出最终回答，不要解释你的推理过程。

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
