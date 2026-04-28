"""
Skill：search_attendance

职责：处理考勤、休假、福利相关政策查询。
适用问题类型：
  - 考勤类：打卡规定、迟到早退处理、旷工处分、加班调休申请
  - 休假类：年假/病假/产假/婚假/丧假天数及申请流程
  - 福利类：节日福利、生日福利、健康检查等

检索策略：
  - 概念词典扩写：伞形概念（如"结婚福利"）展开为文档中实际存在的具体术语，
    每个术语独立检索后合并，解决用户心智模型与文档信息架构的语义鸿沟
  - Hybrid（BM25 + 向量）：BM25 精确匹配关键词（年假/迟到/打卡），
    向量补充语义相似结果（"旷工有什么后果"等表述多样的问题）
  - 表格优先重排：考勤处分表、假期天数表等高价值信息在表格中
  - 增强索引覆盖语义鸿沟（如"生日福利"↔"关爱福利大表"），BM25 补漏已不再需要
"""

SKILL_META = {
    "name": "search_attendance",
    "description": (
        "该Skill处理考勤、休假、福利相关政策查询，"
        "当 query 涉及【考勤】【打卡】【迟到】【早退】【旷工】【加班】【调休】"
        "【年假】【病假】【产假】【婚假】【丧假】【休假】【福利】【工龄】【司龄】等人事政策类事项时调用，"
        "不适用于差旅费用、报销金额等财务类问题"
    ),
    "retrieval_method": "hybrid",
}

# 本 Skill 只检索考勤/休假/福利域的文档，防止跨域噪声
_SOURCES = {
    "考勤&休假&福利指引20251023_clean.md",
}

# 伞形概念 → 文档中实际存在的具体术语
# 维护原则：当用户使用一个上位概念、但文档将其拆分到多个独立章节时，在此添加映射。
# 例："结婚福利"在文档中分散为"结婚礼金"（关爱福利表）和"婚假"（休假章节）。
_CONCEPT_MAP: dict[str, list[str]] = {
    "结婚福利": ["结婚礼金", "婚假", "结婚福利"],
    "生育福利": ["生育津贴", "产假", "陪产假", "生育礼金"],
    "丧亲福利": ["丧假", "慰问金", "丧亲福利"],
    "节日福利": ["节日慰问", "节日礼金", "节日福利"],
}


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    # 优先使用 QueryUnderstanding 提取的 what 维度，减少噪声词干扰
    what = (
        (query_structure or {})
        .get("dimensions", {})
        .get("what", {})
        .get("value")
    )
    search_query = what if what else query
    print(f"[search_attendance] 检索词：{search_query!r}（原始 query：{query!r}）")

    # 概念扩写：词典命中时展开为多个具体检索词
    expanded = _expand_query(search_query)
    if len(expanded) > 1:
        print(f"[search_attendance] 概念扩写：{search_query!r} → {expanded}")

    # vector_search 限定来源域，防止增强索引跨域污染（"结婚礼金"命中报销文档"礼品"问题向量）
    _where = {"source": {"$in": list(_SOURCES)}}

    # 对每个检索词分别 hybrid 检索，合并去重
    all_results: list[dict] = []
    for eq in expanded:
        sub = retriever.search(eq, method="hybrid", top_k=8, where=_where)
        print(f"[search_attendance] hybrid 检索 {eq!r} 返回 {len(sub)} 条")
        print(f"[search_attendance] hybrid top3: {[(r['score'], r.get('is_table'), r['text'][:30]) for r in sub[:3]]}")
        all_results = _merge_deduplicate(all_results, sub)

    # 表格优先重排
    all_results = _boost_table_chunks(all_results, boost=0.5)
    print(f"[search_attendance] 表格重排后 top3: {[(r['score'], r.get('is_table'), r['text'][:30]) for r in all_results[:3]]}")

    # 来源过滤
    all_results = _filter_by_source(all_results, _SOURCES)

    return all_results[:5]


def _filter_by_source(results: list[dict], sources: set[str], min_keep: int = 3) -> list[dict]:
    """
    按来源文件过滤，只保留属于本 Skill 域的 chunk。

    若过滤后结果不足 min_keep 条，回退到不过滤——防止知识库文件名变更时静默返回空结果。
    """
    filtered = [r for r in results if r.get("source") in sources]
    if len(filtered) < min_keep:
        print(f"[search_attendance] ⚠️ 来源过滤后仅剩 {len(filtered)} 条（< {min_keep}），回退到不过滤")
        return results
    return filtered


def _expand_query(query: str) -> list[str]:
    """
    领域词典扩写：将伞形概念展开为文档中实际存在的具体术语列表。

    匹配规则：query 中包含词典 key（子串匹配），返回对应扩写列表。
    未命中时返回原 query 的单元素列表，保持原有检索流程不变。
    """
    for key, expansions in _CONCEPT_MAP.items():
        if key in query:
            return expansions
    return [query]


def _merge_deduplicate(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """合并两路结果，按 text 前 100 字去重，primary 结果优先保留。"""
    seen: set[str] = set()
    merged = []
    for r in primary + secondary:
        key = r["text"][:100]
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return merged


def _boost_table_chunks(results: list[dict], boost: float = 0.5) -> list[dict]:
    """
    对 is_table=True 的 chunk 增加 boost 比例的分值，然后重新降序排列。
    与 search_expense_reimbursement 中的同名函数逻辑一致。
    """
    boosted = []
    for r in results:
        if r.get("is_table"):
            r = {**r, "score": r.get("score", 0) * (1 + boost)}
        boosted.append(r)
    return sorted(boosted, key=lambda x: x.get("score", 0), reverse=True)
