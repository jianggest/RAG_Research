"""
Skill：search_expense_reimbursement（复合 Skill）

职责：处理财务报销相关查询，内部自动完成「实体分类推断 → 费用标准」两步检索链。

设计说明：
  分类推断必须在 Executor 阶段完成，不能依赖 Generator 推断。
  原因：Generator 推断出分类后已无法再发起检索，拿不到对应分类的费用标准数据。

  检索链（根据 scope 分三条路径）：

  [境内 scope=mainland/unknown]
  - Step 1：BM25 找含实体名的分类规则 chunk（深圳等显式实体命中）
  - Step 2：BM25 无结果时，向量检索补充分类规则（揭阳等隐式实体兜底）
  - Step 3：LLM 读境内规则，推断 A/B/C 类
  - Step 4+：向量检索境内费用标准

  [港澳台 scope=china]
  - 直接定为境外C类，跳过分类检索
  - 向量检索"境外 C类 港澳台"费用标准

  [境外国家 scope=overseas]
  - LLM 直接判断：欧美日新 → 境外A类，其他 → 境外B类
  - 向量检索"境外 X类"费用标准

  [通用后处理]
  - Step N-1：表格优先重排（Structural Bias），is_table=True 的 chunk 分值 × 1.5
  - Step N：反思自检，询问金额但无数值时强制切换表格探测模式
"""

from utils import llm_classify, llm_classify_overseas

# 本 Skill 只检索报销域的文档，防止考勤/福利类 chunk 混入
_SOURCES = {
    "报销相关_clean.md",
}

# 境内 B 类地区：省会城市（排除已在 A 类中的北京、上海、广州、深圳）
# 文档规则"B类：省会城市"未逐一列出，此处硬编码用于跳过 LLM 推断，直接确定 B 类
_PROVINCIAL_CAPITALS: set[str] = {
    "石家庄", "太原", "沈阳", "长春", "哈尔滨",
    "南京", "杭州", "合肥", "福州", "南昌",
    "济南", "郑州", "武汉", "长沙", "海口",
    "成都", "贵阳", "昆明", "西安", "兰州",
    "西宁", "台北", "呼和浩特", "南宁", "拉萨",
    "银川", "乌鲁木齐",
}

# 省会城市补充知识虚拟 chunk：注入分类上下文，辅助 LLM 判断某城市是否为省会
_PROVINCIAL_CAPITALS_CHUNK: dict = {
    "text": (
        "补充参考（省会城市名单）：以下城市为中国各省省会，"
        "在差旅费用分类规则中属于 B 类城市的省会城市范畴：\n"
        + "、".join(sorted(_PROVINCIAL_CAPITALS))
    ),
    "source": "provincial_capitals_knowledge",
    "score": 0.0,
    "is_table": False,
}

SKILL_META = {
    "name": "search_expense_reimbursement",
    "description":(
        "该Skill处理财务报销相关查询，如涉及费用问题会内部自动完成「实体分类推断 → 费用标准」两步检索链。"
        "当 query 涉及【差旅费用】【报销标准】【出差补贴】等财务报销类事项时调用，优先查询具体地区的差旅报销标准，差旅费用限额、补贴金额等数值标准相关的表格信息。"
        ),
    "retrieval_method": "composite",
}


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    scope = (
        (query_structure or {})
        .get("dimensions", {})
        .get("where", {})
        .get("scope", "unknown")
    )
    where_dim = (query_structure or {}).get("dimensions", {}).get("where", {})
    where_value = where_dim.get("value")
    what = (
        (query_structure or {})
        .get("dimensions", {})
        .get("what", {})
        .get("value")
    )
    print(f"[search_expense_reimbursement] scope={scope}")

    # vector_search 限定来源域，防止增强索引跨域污染
    _where = {"source": {"$in": list(_SOURCES)}}

    # ── 港澳台：直接定为境外C类，无需分类检索 ────────────────────────────────
    if scope == "china":
        category = "C类"
        classification_chunks = []
        print(f"[search_expense_reimbursement] 港澳台 → 境外C类（直接确定）")
        # 保留地名（香港/澳门/台湾），因为它出现在表格列头里
        where_part = where_value or "港澳台"
        standards_query = f"境外 C类 {where_part} {what}" if what else f"境外 C类 {where_part} {query}"

    # ── 境外国家：LLM判断欧美日新(A类) 或 其他(B类) ──────────────────────────
    elif scope == "overseas":
        category = llm_classify_overseas(query)
        classification_chunks = []
        print(f"[search_expense_reimbursement] 境外国家 → LLM推断境外分类：{category}")
        # 保留国家名（美国/日本等），因为它出现在表格列头"A类：欧洲/美国/日本/新加坡"里
        where_part = where_value or ""
        standards_query = f"境外 {category} {where_part} {what}".strip() if what else f"境外 {category} {where_part} {query}".strip()

    # ── 境内（mainland 或 unknown）：BM25 + 向量兜底 + LLM分类 ───────────────
    else:
        # Step 1：BM25 精确匹配，找含实体名的分类规则 chunk
        classification_chunks = retriever.search(query, method="bm25", top_k=10)
        print(f"[search_expense_reimbursement] BM25 分类检索返回 {len(classification_chunks)} 条")

        # Step 2：BM25 无结果时，向量检索补充分类规则
        # 揭阳等隐式实体不在显式列表中，BM25 找不到，但向量检索能拉回"C类：其他"兜底规则
        if not classification_chunks:
            classification_chunks = retriever.search(query, method="vector", top_k=5, where=_where)
            print(f"[search_expense_reimbursement] BM25 无结果，向量补充分类规则 {len(classification_chunks)} 条")

        # 注入省会城市补充知识：前置到分类上下文，确保进入 llm_classify 的 top-3
        # LLM 推断时可参考此列表判断某城市是否为省会，再结合完整分类规则得出结论
        classification_chunks = [_PROVINCIAL_CAPITALS_CHUNK] + classification_chunks

        # Step 3：LLM 读境内分类规则，推断 A/B/C 类
        # 此步必须在 Executor 阶段完成：Generator 推断出分类后已无法再发起检索
        category = llm_classify(classification_chunks, query)

        if category:
            print(f"[search_expense_reimbursement] LLM 推断境内分类：{category}")
            # 用 what 维度替换 query，避免已解析的城市名污染标准查询词
            standards_query = f"{category} {what}" if what else f"{category} {query}"
            print(f"[search_expense_reimbursement] 标准查询词（what={what!r}）：{standards_query}")
        else:
            print(f"[search_expense_reimbursement] 未推断出分类，使用原始 query")
            standards_query = query

    print(f"[search_expense_reimbursement] 费用标准查询词：{standards_query}")

    # Step 4：向量检索对应分类的费用标准（多取几条，为后续重排留余量）
    standards_results = retriever.search(standards_query, method="vector", top_k=8, where=_where)
    print(f"[search_expense_reimbursement] 费用标准检索返回 {len(standards_results)} 条")

    # Step 5：表格优先重排（Structural Bias）
    # 财务标准 90% 在表格里，给 is_table=True 的 chunk 增加 50% 分值后重新排序
    # 目的：防止语义相近的说明性文字（如"业务招待标准"介绍段）排在费用表格前面
    standards_results = _boost_table_chunks(standards_results, boost=0.5)
    _log_standards_results(standards_results)

    # Step 6：反思自检 —— 仅当用户在询问具体金额时，才检查结果是否含数值
    # 非金额类问题（如"需要哪些材料"、"流程是什么"）结果本就不含数字，不应触发重试
    if _is_amount_query(query) and not _has_numeric_standard(standards_results):
        print("[search_expense_reimbursement] 🤔 自检：询问金额但未发现数值标准，切换表格强制探测模式...")
        table_query = f"{category} 住宿 交通 补贴" if category else query
        retry_results = retriever.search(
            table_query, method="vector", top_k=8,
            where={"$and": [{"source": {"$in": list(_SOURCES)}}, {"is_table": True}]},
        )
        print(f"[search_expense_reimbursement] 表格探测返回 {len(retry_results)} 条")
        if retry_results:
            standards_results = retry_results

    # 合并去重（classification_chunks + standards），按 text 前100字去重
    seen: set[str] = set()
    merged = []
    for r in classification_chunks + standards_results:
        key = r["text"][:100]
        if key not in seen:
            seen.add(key)
            merged.append(r)

    # 将分类结论注入返回结果首位，Generator 可直接读取，无需自行推断
    # 与 search_classification.py 的设计保持一致
    if category:
        conclusion_chunk = {
            "text": f"分类推断结论：{where_value or query} 属于境内 {category} 地区。",
            "source": "classification_conclusion",
            "score": 1.0,
            "is_table": False,
            "is_conclusion": True,
            "category": category,
        }
        merged = [conclusion_chunk] + merged

    # 来源过滤：只保留本域文档的 chunk，防止考勤/福利类 chunk 混入
    return _filter_by_source(merged, _SOURCES)


def _filter_by_source(results: list[dict], sources: set[str], min_keep: int = 3) -> list[dict]:
    """
    按来源文件过滤，只保留属于本 Skill 域的 chunk。

    is_conclusion=True 的结论 chunk 始终保留（source 为内部标记，不在 sources 内）。
    若过滤后结果不足 min_keep 条，回退到不过滤——防止知识库文件名变更时静默返回空结果。
    """
    filtered = [r for r in results if r.get("is_conclusion") or r.get("source") in sources]
    if len(filtered) < min_keep:
        print(f"[search_expense_reimbursement] ⚠️ 来源过滤后仅剩 {len(filtered)} 条（< {min_keep}），回退到不过滤")
        return results
    return filtered


_AMOUNT_KEYWORDS = {"多少", "金额", "限额", "标准", "费用", "补贴", "元", "报销额", "上限", "下限"}


def _is_amount_query(query: str) -> bool:
    """
    判断用户是否在询问具体金额/标准数值。

    只有明确问"多少钱/什么标准"的问题，才需要在结果中看到数字。
    流程类、材料类、政策背景类问题即使没有数字也属正常，不应触发重试。
    """
    return any(kw in query for kw in _AMOUNT_KEYWORDS)


def _has_numeric_standard(results: list[dict]) -> bool:
    """
    检查检索结果中是否包含数值型标准（金额、比例等）。

    财务标准必须有数字才能回答"多少钱"的问题。
    纯文字说明（如制度背景、适用范围）不含数字，视为无效结果。
    """
    import re
    return any(re.search(r"\d+", r.get("text", "")) for r in results)


def _boost_table_chunks(results: list[dict], boost: float = 0.5) -> list[dict]:
    """
    对 is_table=True 的 chunk 增加 boost 比例的分值，然后重新降序排列。

    示例：score=0.80 的表格 chunk，boost=0.5 → 调整后 score=1.20
    非表格 chunk 分值不变。
    """
    boosted = []
    for r in results:
        if r.get("is_table"):
            r = {**r, "score": r.get("score", 0) * (1 + boost)}
        boosted.append(r)
    return sorted(boosted, key=lambda x: x.get("score", 0), reverse=True)


def _log_standards_results(results: list[dict]) -> None:
    """打印重排后的费用标准检索结果，便于诊断表格是否被正确提升。"""
    print(f"[search_expense_reimbursement] 重排后费用标准（共 {len(results)} 条）：")
    for i, r in enumerate(results, 1):
        table_flag = "📊表格" if r.get("is_table") else "📄文本"
        score = r.get("score", 0)
        preview = r.get("text", "")[:80].replace("\n", " ")
        print(f"  [{i}] {table_flag} score={score:.3f} | {preview}")
