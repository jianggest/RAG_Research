"""
Skill：search_admin_guide

职责：处理总部行政办公指引相关查询。
适用问题类型：
  - 着装类：正式/非正式场合着装要求
  - 办公类：办公用品申领、饮用水、会议室预订、名片申请
  - 快递类：快递收发流程、月结快递公司
  - 交通类：上下班班车、坪山/总部/桥头摆渡车时刻、停车收费、外出公干用车
  - 差旅类：火车票/机票/签证/酒店预订流程与差标
  - 安全类：门禁管理、用电安全、消防安全、紧急疏散
  - 规范类：5S管理要求
  - 行政审批类：印章申请、合同盖章、档案借阅

检索策略：
  - 概念词典扩写：将用户的上位概念展开为文档中实际存在的具体术语
  - Hybrid（BM25 + 向量）+ 域隔离：vector_search 限定本域文档，防止跨域污染
  - 表格优先重排：差旅服务流程表、摆渡车时刻表等高价值信息在表格中
"""

SKILL_META = {
    "name": "search_admin_guide",
    "description": (
        "该Skill处理总部行政办公指引相关查询，"
        "当 query 涉及【着装】【办公用品】【会议室】【名片】【快递】【班车】【摆渡车】"
        "【停车】【交通】【出差票务】【签证】【机票】【火车票】【酒店预订】"
        "【门禁】【用电安全】【消防】【5S】【印章】【盖章】【合同审批】【档案】等行政事务时调用，"
        "不适用于考勤打卡、休假天数、薪酬福利等人事政策类问题"
    ),
    "retrieval_method": "hybrid",
}

# 本 Skill 只检索行政指引域的文档
_SOURCES = {
    "OA新员工-行政指引2025.7.7 _clean.md",
}

# 伞形概念 → 文档中实际存在的具体术语
# 维护原则：当用户使用上位概念、但文档将其拆分到多个独立章节时添加映射。
_CONCEPT_MAP: dict[str, list[str]] = {
    "差旅安排":   ["火车票", "机票", "签证", "酒店", "差旅服务"],
    "出差预订":   ["火车票", "机票", "签证", "酒店", "差旅服务"],
    "公司交通":   ["班车", "摆渡车", "停车", "外出公干交通"],
    "盖章申请":   ["印章管理", "盖章申请", "合同盖章"],
    "办公安全":   ["门禁管理", "用电安全", "消防安全", "紧急疏散"],
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
    print(f"[search_admin_guide] 检索词：{search_query!r}（原始 query：{query!r}）")

    # 概念扩写：词典命中时展开为多个具体检索词
    expanded = _expand_query(search_query)
    if len(expanded) > 1:
        print(f"[search_admin_guide] 概念扩写：{search_query!r} → {expanded}")

    # vector_search 限定来源域，防止增强索引跨域污染
    _where = {"source": {"$in": list(_SOURCES)}}

    # 对每个检索词分别 hybrid 检索，合并去重
    all_results: list[dict] = []
    for eq in expanded:
        sub = retriever.search(eq, method="hybrid", top_k=8, where=_where)
        print(f"[search_admin_guide] hybrid 检索 {eq!r} 返回 {len(sub)} 条")
        print(f"[search_admin_guide] hybrid top3: {[(r['score'], r.get('is_table'), r['text'][:30]) for r in sub[:3]]}")
        all_results = _merge_deduplicate(all_results, sub)

    # 表格优先重排（差旅流程表、摆渡车时刻表等关键信息在表格中）
    all_results = _boost_table_chunks(all_results, boost=0.5)
    print(f"[search_admin_guide] 表格重排后 top3: {[(r['score'], r.get('is_table'), r['text'][:30]) for r in all_results[:3]]}")

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
        print(f"[search_admin_guide] ⚠️ 来源过滤后仅剩 {len(filtered)} 条（< {min_keep}），回退到不过滤")
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
    """
    boosted = []
    for r in results:
        if r.get("is_table"):
            r = {**r, "score": r.get("score", 0) * (1 + boost)}
        boosted.append(r)
    return sorted(boosted, key=lambda x: x.get("score", 0), reverse=True)
