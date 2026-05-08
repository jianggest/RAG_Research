"""
Skill：search_expense_reimbursement（复合 Skill）

职责：处理财务报销相关查询，内部自动完成「实体分类推断 → 费用标准」两步检索链。

设计说明：
  分类推断必须在 Executor 阶段完成，不能依赖 Generator 推断。
  原因：Generator 推断出分类后已无法再发起检索，拿不到对应分类的费用标准数据。

  检索链（确定性配置优先 + LLM 兜底）：
  - Step 1：读取 config/region_classification.json 做确定性地区分类
  - Step 2：配置未覆盖时，注入配置规则文本给 LLM 兜底判断
  - Step 3：向量检索对应分类的费用标准
  - Step 4：表格优先重排（Structural Bias），is_table=True 的 chunk 分值 × 1.5
  - Step 5：反思自检，询问金额但无数值时强制切换表格探测模式

  多城市支持：
  - where_value 含多个城市时（如"深圳, 德国"），逐个执行分类链后合并结果
"""

import json
import re
from pathlib import Path

from utils import llm_classify_region

# 本 Skill 只检索报销域的文档，防止考勤/福利类 chunk 混入
_SOURCES = {
    "报销相关_clean.md",
}

_REGION_RULE_PATH = Path(__file__).resolve().parent.parent / "config" / "region_classification.json"
_REGION_RULES_CACHE: dict | None = None



SKILL_META = {
    "name": "search_expense_reimbursement",
    "description":(
        "该Skill处理财务报销与出差业务流程相关查询，覆盖两类问题："
        "（1）数值/标准类：【差旅费用】【报销标准】【出差补贴】【住宿费/交通费限额】等，"
        "内部自动完成「实体分类推断 → 费用标准」两步检索链；"
        "（2）流程类：【出差申请单】【出差审批流程】【报销审批流程】【报销时限/材料要求】等。"
        "⚠️只要问题涉及『出差/报销』这类业务动作，即使 query 里出现【OA系统】【HR系统】等系统名，"
        "也应走本 Skill——系统名只表示『在哪里操作』，业务知识不在 IT 指引里。"
        ),
    "retrieval_method": "composite",
}


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    """
    入口函数：检测多城市时逐个执行分类链，单城市直接执行。
    """
    where_value = (
        (query_structure or {})
        .get("dimensions", {})
        .get("where", {})
        .get("value")
    )

    # 拆分多城市（支持"A, B"、"A，B"、"A和B"格式）
    cities = _split_cities(where_value) if where_value else []

    if len(cities) <= 1:
        # 单城市或无城市，直接走原有流程
        return _execute_for_city(query, retriever, query_structure, where_value)

    # 多城市：逐个执行分类链，合并结果
    print(f"[search_expense_reimbursement] 检测到多城市：{cities}")
    all_results: list[dict] = []
    for city in cities:
        print(f"[search_expense_reimbursement] ── 处理城市：{city} ──")
        city_results = _execute_for_city(query, retriever, query_structure, city)
        all_results = _merge_deduplicate(all_results, city_results)

    return all_results


def _split_cities(where_value: str) -> list[str]:
    """拆分多城市字符串。

    分隔符兼容不同 LLM 的输出习惯：
    - 半角/全角逗号、顿号、分号、斜杠：`, ， 、 ; ； /`
    - 连接词：`和`、`与`、`及`

    背景：QueryUnderstanding 的 where.value 是 LLM 自由文本，不同模型对
    "A 和 B" 的归一化形式不同（Ollama 多保留 `和`，gpt-5.4 改写为 `、`），
    切分规则需同时覆盖这些形式。
    """
    parts = [c.strip() for c in re.split(r"[,，、;；/]|和|与|及", where_value) if c.strip()]
    return parts


def _load_region_rules() -> dict:
    """读取受控地区分类配置。配置缺失时返回空 dict，让 LLM 兜底。"""
    global _REGION_RULES_CACHE
    if _REGION_RULES_CACHE is not None:
        return _REGION_RULES_CACHE

    try:
        _REGION_RULES_CACHE = json.loads(_REGION_RULE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[search_expense_reimbursement] 地区分类配置读取失败：{e}")
        _REGION_RULES_CACHE = {}
    return _REGION_RULES_CACHE


def _normalize_place_name(place: str | None) -> str:
    """标准化地名，降低 '深圳市'、'香港特别行政区' 这类表述差异。"""
    if not place:
        return ""
    normalized = re.sub(r"\s+", "", str(place))
    changed = True
    while changed:
        changed = False
        for suffix in ("特别行政区", "地区", "省", "市"):
            if normalized.endswith(suffix) and len(normalized) > len(suffix):
                normalized = normalized[: -len(suffix)]
                changed = True
                break
    return normalized


def _matches_place(place: str, candidates: list[str]) -> bool:
    normalized = _normalize_place_name(place)
    return any(normalized == _normalize_place_name(candidate) for candidate in candidates)


def _classify_region_by_rules(city: str | None) -> dict:
    """
    使用 config/region_classification.json 做确定性地区分类。

    返回格式与 llm_classify_region 保持一致：
      {"scope_label": "境内"|"境外", "category": "A类"|"B类"|"C类"}
    未覆盖时返回空 dict，由 LLM 兜底。
    """
    if not city:
        return {}

    rules = _load_region_rules()
    if not rules:
        return {}

    mainland = rules.get("mainland", {})
    mainland_scope = mainland.get("scope_label", "境内")
    mainland_categories = mainland.get("categories", {})

    for category in ("A类", "B类"):
        if _matches_place(city, mainland_categories.get(category, [])):
            return {"scope_label": mainland_scope, "category": category}

    if _matches_place(city, mainland.get("c_class_examples", [])):
        return {"scope_label": mainland_scope, "category": "C类"}

    overseas = rules.get("overseas", {})
    overseas_scope = overseas.get("scope_label", "境外")
    overseas_categories = overseas.get("categories", {})

    if _matches_place(city, overseas_categories.get("C类", [])):
        return {"scope_label": overseas_scope, "category": "C类"}

    overseas_a = overseas_categories.get("A类", {})
    overseas_a_places = list(overseas_a.get("places", []))
    for group_name, members in overseas_a.get("region_groups", {}).items():
        overseas_a_places.append(group_name)
        overseas_a_places.extend(members)
    if _matches_place(city, overseas_a_places):
        return {"scope_label": overseas_scope, "category": "A类"}

    if _matches_place(city, overseas.get("b_class_examples", [])):
        return {"scope_label": overseas_scope, "category": "B类"}

    return {}


def _build_static_rule_chunks() -> list[dict]:
    """将配置转换为 LLM 兜底分类可读的规则 chunk。"""
    rules = _load_region_rules()
    if not rules:
        return []

    mainland = rules.get("mainland", {})
    mainland_categories = mainland.get("categories", {})
    china_text = (
        "A 类地区：" + "、".join(mainland_categories.get("A类", [])) + "；"
        "B 类地区：" + "、".join(mainland_categories.get("B类", [])) + "；"
        "C 类地区：其他。"
    )

    overseas = rules.get("overseas", {})
    overseas_categories = overseas.get("categories", {})
    overseas_a = overseas_categories.get("A类", {})
    a_parts = list(overseas_a.get("places", []))
    for group_name, members in overseas_a.get("region_groups", {}).items():
        a_parts.append(f"{group_name}（包括{'、'.join(members)}）")
    overseas_text = (
        "境外 A 类地区：" + "、".join(a_parts) + "；"
        "境外 B 类地区：其他国家；"
        "境外 C 类地区：" + "、".join(overseas_categories.get("C类", [])) + "。"
    )

    return [
        {"text": china_text, "source": "internal_rule_china", "score": 1.0, "is_table": False},
        {"text": overseas_text, "source": "internal_rule_oversea", "score": 1.0, "is_table": False},
    ]


def _execute_for_city(
    query: str,
    retriever,
    query_structure: dict,
    city: str | None,
) -> list[dict]:
    """
    对单个城市执行完整的分类 → 费用标准检索链（单路径，无 scope 分支）。
    """
    what = (
        (query_structure or {})
        .get("dimensions", {})
        .get("what", {})
        .get("value")
    )
    print(f"[search_expense_reimbursement] city={city}")

    # vector_search 限定来源域，防止增强索引跨域污染
    _where = {"source": {"$in": list(_SOURCES)}}

    # 注入配置规则，供 LLM 兜底时参考，也作为分类依据进入上下文。
    classification_chunks = _build_static_rule_chunks()

    # Step 3：配置确定性分类优先；配置未覆盖时再交给 LLM 兜底。
    region = _classify_region_by_rules(city)
    if region:
        print(
            f"[search_expense_reimbursement] 配置规则分类："
            f"{city} → {region.get('scope_label', '')}{region.get('category', '')}"
        )
    else:
        region = llm_classify_region(classification_chunks, city)

    scope_label = region.get("scope_label", "")
    category = region.get("category", "")

    if category:
        print(f"[search_expense_reimbursement] 分类结果：{city} → {scope_label}{category}")
        # 构造费用标准查询词
        if scope_label == "境外":
            standards_query = f"境外 {category} {city} {what}" if what else f"境外 {category} {city}"
        else:
            standards_query = f"{category} {what}" if what else f"{category} {query}"
        print(f"[search_expense_reimbursement] 标准查询词：{standards_query}")
    else:
        print(f"[search_expense_reimbursement] 未推断出分类，使用原始 query")
        scope_label = ""
        standards_query = query

    print(f"[search_expense_reimbursement] 费用标准查询词：{standards_query}")

    # Step 4：向量检索对应分类的费用标准
    standards_results = retriever.search(standards_query, method="vector", top_k=8, where=_where)
    print(f"[search_expense_reimbursement] 费用标准检索返回 {len(standards_results)} 条")

    # Step 5：表格优先重排
    standards_results = _boost_table_chunks(standards_results, boost=0.5)
    _log_standards_results(standards_results)

    # Step 6：反思自检
    if _is_amount_query(query) and not _has_numeric_standard(standards_results):
        print("[search_expense_reimbursement] 自检：询问金额但未发现数值标准，切换表格强制探测模式...")
        table_query = f"{category} 住宿 交通 补贴" if category else query
        retry_results = retriever.search(
            table_query, method="vector", top_k=8,
            where={"$and": [{"source": {"$in": list(_SOURCES)}}, {"is_table": True}]},
        )
        print(f"[search_expense_reimbursement] 表格探测返回 {len(retry_results)} 条")
        if retry_results:
            standards_results = retry_results

    # 合并去重
    seen: set[str] = set()
    merged = []
    for r in classification_chunks + standards_results:
        key = r["text"][:100]
        if key not in seen:
            seen.add(key)
            merged.append(r)

    # 注入分类结论
    if category:
        full_category = f"{scope_label}{category}"
        conclusion_chunk = {
            "text": f"分类推断结论：{city or query} 属于{full_category}地区。",
            "source": "classification_conclusion",
            "score": 1.0,
            "is_table": False,
            "is_conclusion": True,
            "entity": city or query,
            "scope_label": scope_label,
            "category": category,
            "full_category": full_category,
        }
        merged = [conclusion_chunk] + merged

    # 来源过滤
    return _filter_by_source(merged, _SOURCES)


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
        table_flag = "表格" if r.get("is_table") else "文本"
        score = r.get("score", 0)
        preview = r.get("text", "")[:80].replace("\n", " ")
        print(f"  [{i}] {table_flag} score={score:.3f} | {preview}")
