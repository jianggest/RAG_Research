"""
Skill：search_it_guide

职责：处理新员工 IT 指引相关查询。
适用问题类型：
  - 设备类：办公电脑配备标准、笔记本申请、研发/测试电脑申请
  - 网络类：有线/无线网络权限、WiFi 名称与密码、IP 查询方式
  - 账号类：邮箱/OA/HR/EPROS/PLM/JIRA/ERP/FIS/CRM 账号初始密码、权限申请、联系人
  - 信息安全类：电脑使用规范、受控区行为规范、数据安全要求
  - OA 使用类：OA 流程发起方式、IT 办公指引区
  - IT 支持类：IT 服务目录、各系统联系人与联系方式

检索策略：
  - 概念词典扩写：将用户的上位概念展开为文档中实际存在的具体术语
  - Hybrid（BM25 + 向量）+ 域隔离：vector_search 限定本域文档，防止跨域污染
  - 表格优先重排：系统账号表、网络权限表、IT 服务目录表等关键信息在表格中
"""

SKILL_META = {
    "name": "search_it_guide",
    "description": (
        "该Skill处理新员工IT指引相关查询，"
        "当 query 涉及【电脑配备】【笔记本】【台式电脑】【网络】【WiFi】【密码】"
        "【账号】【权限】【邮箱】【OA】【ERP】【PLM】【JIRA】【CRM】【FIS】【HR系统】"
        "【信息安全】【受控区】【数据安全】【IT支持】【IT联系】【系统申请】等IT相关事务时调用，"
        "不适用于考勤打卡、休假福利、行政办公等非IT类问题"
    ),
    "retrieval_method": "hybrid",
}

# 本 Skill 只检索 IT 指引域的文档
_SOURCES = {
    "【光峰】新员工IT指引_clean.md",
}

# 伞形概念 → 文档中实际存在的具体术语
# 维护原则：当用户使用上位概念、但文档将其拆分到多个独立章节时添加映射。
_CONCEPT_MAP: dict[str, list[str]] = {
    "系统账号":   ["邮箱", "OA", "HR", "ERP", "PLM", "JIRA", "CRM", "FIS", "EPROS"],
    "账号申请":   ["邮箱", "OA账号", "PLM", "JIRA", "ERP", "CRM", "系统权限"],
    "IT联系方式": ["IT服务目录", "IT服务工程师", "联系人"],
    "网络权限":   ["有线网络", "无线网络", "WiFi", "网络类别"],
    "信息安全规范": ["办公电脑使用规范", "受控区", "数据安全"],
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
    print(f"[search_it_guide] 检索词：{search_query!r}（原始 query：{query!r}）")

    # 概念扩写：词典命中时展开为多个具体检索词
    expanded = _expand_query(search_query)
    if len(expanded) > 1:
        print(f"[search_it_guide] 概念扩写：{search_query!r} → {expanded}")

    # vector_search 限定来源域，防止增强索引跨域污染
    _where = {"source": {"$in": list(_SOURCES)}}

    # 对每个检索词分别 hybrid 检索，合并去重
    all_results: list[dict] = []
    for eq in expanded:
        sub = retriever.search(eq, method="hybrid", top_k=8, where=_where)
        print(f"[search_it_guide] hybrid 检索 {eq!r} 返回 {len(sub)} 条")
        print(f"[search_it_guide] hybrid top3: {[(r['score'], r.get('is_table'), r['text'][:30]) for r in sub[:3]]}")
        all_results = _merge_deduplicate(all_results, sub)

    # 表格优先重排（系统账号表、网络权限表、IT 服务目录表关键信息在表格中）
    all_results = _boost_table_chunks(all_results, boost=0.5)
    print(f"[search_it_guide] 表格重排后 top3: {[(r['score'], r.get('is_table'), r['text'][:30]) for r in all_results[:3]]}")

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
        print(f"[search_it_guide] ⚠️ 来源过滤后仅剩 {len(filtered)} 条（< {min_keep}），回退到不过滤")
        return results
    return filtered


def _expand_query(query: str) -> list[str]:
    """
    领域词典扩写：将伞形概念展开为文档中实际存在的具体术语列表。

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
