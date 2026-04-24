"""
Skill：search_classification

职责：查询某个实体属于哪个分类/等级/分组，并通过 LLM 推断出明确结论。

设计说明：
  分类推断必须在 Executor 阶段完成，不能依赖后续步骤或 Generator。
  - Step 1：BM25 精确匹配检索分类规则（找含实体名的 chunk）
  - Step 2：BM25 无结果时，向量检索补充分类规则（揭阳等隐式实体兜底）
  - Step 3：LLM 读分类规则，推断实体所属类别
    - 深圳：BM25 命中 → LLM 得出"A类"
    - 揭阳：BM25 未命中 → 向量拉回完整规则 → LLM 推断"C类"
  - 返回值在列表首位加入结论 chunk（is_conclusion=True），
    Executor 的 extract_key_entities 优先读取结论，
    使得下一步 query 变为"A类 ..."而非一堆 Markdown 原文
"""

from utils import llm_classify, llm_classify_overseas

SKILL_META = {
    "name": "search_classification",
    "description": "当 query 中包含【地区名】【职级名】【部门名】等需要确认所属规则类别的实体时调用，返回该实体的分类信息",
    "retrieval_method": "bm25",
}


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    scope = (
        (query_structure or {})
        .get("dimensions", {})
        .get("where", {})
        .get("scope", "unknown")
    )

    # ── 港澳台：境外C类，直接确定，无需检索 ──────────────────────────────────
    if scope == "china":
        category = "C类"
        chunks = retriever.search(query, method="bm25", top_k=10)
        print(f"[search_classification] 港澳台 → 境外C类（直接确定）")

    # ── 境外国家：靠LLM地理常识判断，无需检索分类规则 ─────────────────────────
    elif scope == "overseas":
        category = llm_classify_overseas(query)
        chunks = retriever.search(query, method="bm25", top_k=10)
        print(f"[search_classification] 境外国家 → LLM推断境外分类：{category}")

    # ── 境内（mainland 或 unknown）：BM25 + 向量兜底 + LLM境内分类 ─────────────
    else:
        # Step 1：BM25 精确匹配，找含实体名的分类规则 chunk
        chunks = retriever.search(query, method="bm25", top_k=10)
        print(f"[search_classification] BM25 返回 {len(chunks)} 条")

        # Step 2：BM25 无结果时，向量检索补充分类规则
        # 揭阳等隐式实体不在显式列表中，但向量检索能拉回"C类：其他"兜底规则
        if not chunks:
            chunks = retriever.search(query, method="vector", top_k=5)
            print(f"[search_classification] BM25 无结果，向量补充分类规则 {len(chunks)} 条")

        # Step 3：LLM 读境内规则推断 A/B/C 类
        category = llm_classify(chunks, query)
        print(f"[search_classification] LLM 推断境内分类：{category}")

    if category:
        conclusion = {
            "text": f"分类结论：查询中的实体属于{category}",
            "source": chunks[0]["source"] if chunks else "推断",
            "score": 1.0,
            "is_conclusion": True,
            "category": category,
        }
        return [conclusion] + chunks

    print(f"[search_classification] 未能推断明确分类")
    return chunks
