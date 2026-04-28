"""
Skill：search_asset_management

职责：处理公司资产管理流程相关查询。
适用问题类型：
  - 资产分类类：固定资产、非固资、无形资产、耗用品的定义与分类标准
  - 固定资产类：资产申请、采购、到货验收、调拨、借用、盘点、处置流程
  - 非固资类：非固资申请、领用、台账管理、转移、报废流程
  - 角色职责类：总资产管理员、一级资产管理员、二级资产管理员职责
  - OA流程类：各类资产相关的OA申请单、审批流程
  - 报废/处置类：资产无使用价值时的废处置申请、存货转资产申请

检索策略：
  - Hybrid（BM25 + 向量）+ 域隔离：vector_search 限定本域文档，防止跨域污染
  - 表格优先重排：固定资产管理流程表等关键信息在表格中
  - 图片展示：chunk 文字用于检索，命中后前端解析 __PAGE_IMG__ 标记展示原始页面图片
"""

SKILL_META = {
    "name": "search_asset_management",
    "description": (
        "该Skill处理公司资产管理流程相关查询，"
        "当 query 涉及【固定资产】【非固资】【无形资产】【耗用品】【资产申请】【资产采购】"
        "【资产调拨】【资产借用】【资产盘点】【资产处置】【资产报废】【存货转资产】"
        "【资产管理员】【资产台账】【非固资领用】【非固资转移】【一物一码】等资产管理事务时调用，"
        "不适用于办公用品日常申领、IT设备账号申请、行政办公等非资产管理类问题"
    ),
    "retrieval_method": "hybrid",
}

_SOURCES = {
    "资产管理流程_clean.md",
}

_CONCEPT_MAP: dict[str, list[str]] = {
    "资产申请":     ["固定资产申请", "非固资申请", "存货转资产申请"],
    "资产处置":     ["资产报废", "非固资报废", "资产废处置申请", "资产转存货申请"],
    "资产盘点":     ["固定资产盘点", "盘点单", "非固资台账"],
    "资产调拨":     ["调拨申请单", "跨组织调拨", "非固资转移"],
    "资产分类":     ["固定资产", "非固资", "耗用品", "无形资产"],
    "资产管理流程": ["资产申请", "资产采购", "资产到货验收", "资产调拨", "资产盘点", "资产处置"],
}


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    what = (
        (query_structure or {})
        .get("dimensions", {})
        .get("what", {})
        .get("value")
    )
    search_query = what if what else query
    print(f"[search_asset_management] 检索词：{search_query!r}（原始 query：{query!r}）")

    expanded = _expand_query(search_query)
    if len(expanded) > 1:
        print(f"[search_asset_management] 概念扩写：{search_query!r} → {expanded}")

    _where = {"source": {"$in": list(_SOURCES)}}

    all_results: list[dict] = []
    for eq in expanded:
        sub = retriever.search(eq, method="hybrid", top_k=8, where=_where)
        print(f"[search_asset_management] hybrid 检索 {eq!r} 返回 {len(sub)} 条")
        all_results = _merge_deduplicate(all_results, sub)

    all_results = _boost_table_chunks(all_results, boost=0.5)
    all_results = _filter_by_source(all_results, _SOURCES)

    return all_results[:5]


def _filter_by_source(results: list[dict], sources: set[str], min_keep: int = 3) -> list[dict]:
    filtered = [r for r in results if r.get("source") in sources]
    if len(filtered) < min_keep:
        print(f"[search_asset_management] ⚠️ 来源过滤后仅剩 {len(filtered)} 条（< {min_keep}），回退到不过滤")
        return results
    return filtered


def _expand_query(query: str) -> list[str]:
    for key, expansions in _CONCEPT_MAP.items():
        if key in query:
            return expansions
    return [query]


def _merge_deduplicate(primary: list[dict], secondary: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged = []
    for r in primary + secondary:
        key = r["text"][:100]
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return merged


def _boost_table_chunks(results: list[dict], boost: float = 0.5) -> list[dict]:
    boosted = []
    for r in results:
        if r.get("is_table"):
            r = {**r, "score": r.get("score", 0) * (1 + boost)}
        boosted.append(r)
    return sorted(boosted, key=lambda x: x.get("score", 0), reverse=True)
