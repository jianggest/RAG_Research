"""
Skill：search_expense_reimbursement（复合 Skill）

职责：处理财务报销相关查询，内部自动完成「实体分类推断 → 费用标准」两步检索链。

设计说明：
  分类推断必须在 Executor 阶段完成，不能依赖 Generator 推断。
  原因：Generator 推断出分类后已无法再发起检索，拿不到对应分类的费用标准数据。

  检索链：
  - Step 1：BM25 找含实体名的分类规则 chunk（深圳等显式实体命中）
  - Step 2：BM25 无结果时，向量检索补充分类规则（揭阳等隐式实体兜底）
  - Step 3：LLM 读分类规则，推断实体所属类别（如"C类"）
    - 深圳：BM25 命中 → LLM 得出"A类"
    - 揭阳：BM25 未命中 → 向量拉回完整规则 → LLM 推断"C类"
  - Step 4：以"分类 + 原始 query"为查询词，向量检索对应费用标准（多取 top_k=8）
  - Step 5：表格优先重排（Structural Bias）
    - is_table=True 的 chunk 分值 × 1.5，重新排序
    - 财务标准 90% 在表格里，防止语义相近的说明段（如"业务招待标准"）排在费用表前面
"""

from utils import llm_classify

SKILL_META = {
    "name": "search_expense_reimbursement",
    "description": "当 query 涉及【差旅费用】【报销标准】【出差补贴】等财务报销类事项时调用，优先查询具体地区的出差费用限额、补贴金额等数值标准",
    "retrieval_method": "composite",
}


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    # Step 1：BM25 精确匹配，找含实体名的分类规则 chunk
    classification_chunks = retriever.search(query, method="bm25", top_k=10)
    print(f"[search_expense_reimbursement] BM25 分类检索返回 {len(classification_chunks)} 条")

    # Step 2：BM25 无结果时，向量检索补充分类规则
    # 揭阳等隐式实体不在显式列表中，BM25 找不到，但向量检索能拉回"C类：其他"兜底规则
    if not classification_chunks:
        classification_chunks = retriever.search(query, method="vector", top_k=5)
        print(f"[search_expense_reimbursement] BM25 无结果，向量补充分类规则 {len(classification_chunks)} 条")

    # Step 3：LLM 读分类规则，推断实体所属类别
    # 此步必须在 Executor 阶段完成：Generator 推断出分类后已无法再发起检索
    category = llm_classify(classification_chunks, query)

    if category:
        print(f"[search_expense_reimbursement] LLM 推断分类：{category}")
        # 用 what 维度替换 query，避免已解析的城市名污染标准查询词
        # 逻辑：where（深圳）→ 已解析为 category（A类），query 里的城市名不再需要
        # 优先用 query_structure.what，回退到原始 query
        what = (
            (query_structure or {})
            .get("dimensions", {})
            .get("what", {})
            .get("value")
        )
        standards_query = f"{category} {what}" if what else f"{category} {query}"
        print(f"[search_expense_reimbursement] 标准查询词（what={what!r}）：{standards_query}")
    else:
        print(f"[search_expense_reimbursement] 未推断出分类，使用原始 query")
        standards_query = query

    print(f"[search_expense_reimbursement] 费用标准查询词：{standards_query}")

    # Step 4：向量检索对应分类的费用标准（多取几条，为后续重排留余量）
    standards_results = retriever.search(standards_query, method="vector", top_k=8)
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
            table_query, method="vector", top_k=8, where={"is_table": True}
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

    return merged


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
