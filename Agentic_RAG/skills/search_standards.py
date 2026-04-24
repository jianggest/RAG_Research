"""
Skill：search_standards
查询某个分类/等级下的具体标准、金额、限额或配额。
"""

SKILL_META = {
    "name": "search_standards",
    "description": "当已知实体所属【分类/等级/类别】后，查询该类别对应的具体数值标准、金额或限额",
    "retrieval_method": "vector",  # 费用描述语义多样，向量检索覆盖更广
}


def execute(query: str, retriever) -> list[dict]:
    return retriever.search(query, method="vector", top_k=5)
