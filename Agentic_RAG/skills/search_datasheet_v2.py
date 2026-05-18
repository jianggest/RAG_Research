"""
Skill：search_datasheet_v2 — 多切面（faceted）检索 V2

定位:
  V1 (`search_datasheet.py`) 用 staged rules + topic concept_map 对 oscillator
  timing / spi flash / i2c ports 等问题逐一硬编码规则, 加一个新主题就要写一组。
  V2 改为「工程视角通用切面」+「文档结构感知」, 长期替代 V1。

设计原则:
  - 6 个通用切面 (physical_scope / functional_role / parameters_and_ratings /
    performance_timing / system_conditions / configuration_control)
  - facet query = device_token(s) + (topic 或 原始 query) + 切面 keywords
    设备型号必须保留, 避免多 datasheet 入库后跨型号串台
  - 切面 keywords 不绑接口/主题, 只装「工程通用属性词」
  - 不写主题专属 overlay, 不写关键词正则补强, 不写 staged rules
  - 切面权重初版全 1（round-robin 一轮一条）
  - 串行执行, 打印每切面耗时与命中数, 便于后续调权 / 上并行

适用问题类型:
  - 枚举/总览型: "X 有哪些"、"X 的接口/信号都包含什么"
  - 设计要求型: "X 的设计要求"、"X 的时序约束"、"X 的 ESD 要求"

返回值:
  list[SearchResult], 每条带 `facet` 字段标识来源切面, 便于上层 evidence 归类。
"""

from __future__ import annotations

import re
import time

from retriever import extract_datasheet_entity_tokens, normalize_datasheet_text


SKILL_META = {
    "name": "search_datasheet_v2",
    "description": (
        "该Skill处理 datasheet / 芯片手册的【多切面】查询, 面向【枚举/总览/设计要求】型问题, "
        "如 'I2C 接口或信号有哪些'、'Oscillator Timing 要求'、'ESD 设计要求'。"
        "采用工程视角的 6 个通用切面（物理形态/功能定位/参数等级/性能时序/系统条件/配置控制）, "
        "切面 keywords 与设备型号 + 主题词拼接成 facet query, 无需为每个接口/主题写专属规则。"
        "不处理企业 HR、财务报销、行政、IT 账号登录等内部制度问题。"
    ),
    "retrieval_method": "hybrid",
}


# ── 6 个通用切面 ──────────────────────────────────────────────────────────────
# 字段:
#   intent    — 切面意图说明（仅供调试 / 文档, 不进入检索）
#   keywords  — 切面 keywords 常量串; 与 device + topic 一起拼成 facet query
#
# 维护原则:
#   只往里加「工程通用属性词」, 不能写「I2C」「ESD」「MOSC」这类主题专属词。
#   如果某个切面需要 boost 某主题, 答案在 query 拼装环节加入主题, 而非改这里。

_FACETS: dict[str, dict] = {
    "physical_scope": {
        "intent": "物理形态/范围: pin / ball / signal / instance",
        "keywords": "pin ball signal instance interface port pinout",
    },
    "functional_role": {
        "intent": "功能定位: master / slave / control / data / protection",
        "keywords": "master slave primary secondary control data role function",
    },
    "parameters_and_ratings": {
        "intent": "参数与等级: voltage / current / temperature / HBM / CDM / tolerance",
        "keywords": "voltage current temperature HBM CDM tolerance rating limit",
    },
    "performance_timing": {
        "intent": "性能与时序: rate / frequency / setup / hold / cycle / jitter",
        "keywords": "rate frequency setup hold cycle period jitter timing",
    },
    "system_conditions": {
        "intent": "系统级条件: reset / init / sequence / layout / power-on",
        "keywords": "reset initialization sequence layout power-on supply",
    },
    "configuration_control": {
        "intent": "配置与控制: register / command / firmware / config",
        "keywords": "register command firmware configuration mode control",
    },
}


# ── 调参常量 ─────────────────────────────────────────────────────────────────
TOP_K_TOTAL = 20            # 最终返回总数（按 plan 约定）
PER_FACET_FETCH = 6         # 每切面拉这么多候选, 给去重和保底留余量
MIN_PER_FACET = 2           # round-robin 保底: 每切面至少保留 N 条（若候选足够）


# ── Topic 归一别名 ────────────────────────────────────────────────────────────
# 这里只做「query 表达 → 规范主题名」的归一化, 不携带主题专属知识。
# value 端的主题名只是被拼到 facet query 里的字符串, facet 模板对它毫不知情。
#
# 匹配卫生:
#   - 英文别名加 `\b` 边界, 避免 "esdfasdf" 误判为 ESD、"asparking" 误判为 parking
#   - 中文别名不加边界（中文无单词边界, substring 即可）
#   - "SPI flash" 等多词别名排在 "SPI" 前面, 优先匹配更具体形式

_TOPIC_ALIAS_PATTERNS: list[tuple[list[str], str]] = [
    ([r"\bi\s*2\s*c\b", r"\biic\b", r"i²c"], "I2C"),
    ([r"\bspi\s+flash\b", r"\bserial\s+flash\b"], "SPI flash"),
    ([r"\bspi\b"], "SPI"),
    ([r"\buart\b"], "UART"),
    ([r"\bjtag\b"], "JTAG"),
    ([r"\busb\b"], "USB"),
    ([r"\boscillator\b", r"振荡器"], "oscillator"),
    ([r"\bmosc\b"], "MOSC"),
    ([r"\bpll\b"], "PLL"),
    ([r"\bclock\b", r"时钟"], "clock"),
    ([r"\breset\b", r"复位"], "reset"),
    ([r"\besd\b", r"静电"], "ESD"),
    ([r"\bpower\b", r"电源", r"\bsupply\b"], "power"),
    ([r"\bparkz\b", r"\bparking\b", r"\bpark\b"], "parking"),
    ([r"\bgpio\b"], "GPIO"),
]

_TOPIC_ALIASES: list[tuple[list[re.Pattern[str]], str]] = [
    ([re.compile(p, re.IGNORECASE) for p in patterns], normalized)
    for patterns, normalized in _TOPIC_ALIAS_PATTERNS
]


# 设备型号识别: 这些是「指代某颗芯片」的标识, 不是「主题」, 应从 topic 候选剔除,
# 同时被收集为 device_tokens, 用于约束 source 与拼接 facet query。
# 用前缀匹配避免每加一颗型号都要登记。
_DEVICE_MODEL_PREFIXES = ("DLPC", "DLP", "DLPA", "MSP", "TPS", "LM", "TLC")


_FALLBACK_TOPIC_REJECTS = {
    "I2C",
    "SPI",
    "UART",
    "USB",
    "JTAG",
    "ESD",
    "GPIO",
}


_DATASHEET_SOURCE_HINTS = (
    "dlpc",
    "datasheet",
    "data sheet",
    "controller",
    "electrical characteristics",
    "timing requirements",
    "recommended operating conditions",
)


# ── 入口 ──────────────────────────────────────────────────────────────────────

def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    search_query = _extract_search_query(query, query_structure)
    topic = _detect_topic(search_query)
    device_tokens = _detect_device_tokens(search_query)
    device_prefix = " ".join(device_tokens)
    topic_or_query = topic if topic else search_query
    print(
        f"[search_datasheet_v2] query={search_query!r} "
        f"topic={topic!r} devices={device_tokens}"
    )

    chunks = getattr(retriever, "chunks", [])
    target_sources, device_aliases = _discover_relevant_datasheet_sources(chunks, device_tokens)
    if not target_sources:
        print("[search_datasheet_v2] ⚠️ 未识别到任何 datasheet 来源, 退化为全库检索")
    elif device_tokens:
        print(f"[search_datasheet_v2] 来源收窄: {sorted(target_sources)}")
    if device_aliases:
        print(f"[search_datasheet_v2] ℹ️ 设备型号模糊命中: {device_aliases}")

    where = {"source": {"$in": list(target_sources)}} if target_sources else None
    facet_results = _run_faceted_retrieval(retriever, device_prefix, topic_or_query, where)

    # bm25 不吃 where, 这里按 target_sources 做最终来源兜底过滤
    if target_sources:
        facet_results = {
            facet: [r for r in hits if r.get("source") in target_sources]
            for facet, hits in facet_results.items()
        }

    merged = _facet_round_robin_topk(facet_results, total=TOP_K_TOTAL, min_per_facet=MIN_PER_FACET)
    # 将设备 alias 信息盖到每条结果上, 供下游 generator 在回答里向用户说明模糊命中
    if device_aliases and merged:
        for r in merged:
            r["_device_alias_map"] = device_aliases
    print(f"[search_datasheet_v2] 合并后返回 {len(merged)} 条")
    if merged:
        print(
            "[search_datasheet_v2] top5: "
            + str([
                (round(r.get("score", 0) or 0, 4), r.get("facet"), r.get("source"), (r.get("text", "") or "")[:40])
                for r in merged[:5]
            ])
        )
    return merged


# ── Topic / Device 检测 ──────────────────────────────────────────────────────

def _detect_topic(query: str) -> str | None:
    """从 query 抽取主题词; 抽不出返回 None。

    优先级:
      1. 主题别名词典（带 token 边界的正则, 覆盖中英/同义/大小写）
      2. datasheet 实体 token（如 PLL_REFCLK_I / GPIO_08）, 去掉设备型号
      3. 仍无 → None, 调用方退化为「device + 原始 query + facet keywords」检索

    顺序解释: 别名优先是因为 entity_tokens 会同时抽到 "DLPC3436" 和 "I2C", 取首项时
    可能误用设备型号当主题; 别名命中可直接锚定语义主题。
    """
    q_lower = (normalize_datasheet_text(query) + " " + query).lower()
    for patterns, normalized in _TOPIC_ALIASES:
        if any(p.search(q_lower) for p in patterns):
            return normalized

    for token in extract_datasheet_entity_tokens(query):
        if not _is_fallback_topic_token(token):
            continue
        return token

    return None


def _detect_device_tokens(query: str) -> list[str]:
    """从 query 抽取设备型号 token（如 DLPC3436）, 保留原顺序与大小写。

    用途:
      - 拼到 facet query 头部, 让检索保留设备约束
      - 用于 _discover_relevant_datasheet_sources 收窄 source 文件名
    """
    return [t for t in extract_datasheet_entity_tokens(query) if _is_device_model(t)]


def _is_device_model(token: str) -> bool:
    """判断一个 entity token 是不是设备型号（应排除出 topic 候选）。

    判定: 以 _DEVICE_MODEL_PREFIXES 中任一前缀开头, 且 token 内含至少一位数字。
    """
    upper = token.upper()
    return any(
        upper.startswith(prefix) and any(ch.isdigit() for ch in upper)
        for prefix in _DEVICE_MODEL_PREFIXES
    )


def _is_fallback_topic_token(token: str) -> bool:
    """判断 entity token 是否足够具体, 可作为 alias 未命中时的 topic。

    别名型主题（I2C/SPI/GPIO 等）必须由 _TOPIC_ALIASES 的边界正则命中,
    避免 "I2Channel" 这类词被 entity 归一化后误判成 I2C。
    """
    upper = token.upper()
    if _is_device_model(upper):
        return False
    if upper in _FALLBACK_TOPIC_REJECTS:
        return False
    return "_" in upper or any(ch.isdigit() for ch in upper)


# ── Source 发现与收窄 ────────────────────────────────────────────────────────

def _discover_datasheet_sources(chunks: list[dict]) -> set[str]:
    """从已加载 chunks 自动识别所有 datasheet 来源。

    判定优先级: chunk.is_datasheet=True 直接采纳; 否则用文件名 + 内容关键词兜底。
    """
    sources: set[str] = set()
    pending: dict[str, list[str]] = {}
    for chunk in chunks or []:
        source = chunk.get("source", "")
        if not source:
            continue
        if chunk.get("is_datasheet"):
            sources.add(source)
            continue
        pending.setdefault(source, []).append((chunk.get("text", "") or "")[:1000])

    for source, texts in pending.items():
        if source in sources:
            continue
        haystack = (source + "\n" + "\n".join(texts)).lower()
        if any(hint in haystack for hint in _DATASHEET_SOURCE_HINTS):
            sources.add(source)
    return sources


_LETTER_PREFIX_NUM_RE = re.compile(r"^([a-z]+)(\d.*)$")


def _device_token_matches_source(token: str, source_lower: str) -> bool:
    """device_token 与 source 文件名匹配, 字母前缀通用容错。

    匹配规则:
      - 直接 substring 命中即为匹配
      - 若 token 形如「字母前缀 + 数字尾」(如 'DLP6540'、'TPS5430'), 允许 source 在
        字母前缀与数字之间插入 1+ 字母（'DLP6540' 命中 'dlpc6540' / 'dlpa6540';
        'TPS5430' 命中 'tpsm5430'）, 应对用户口语化型号。
      - 已写明更长前缀的 token（如 'DLPC6540' / 'DLPA6540'）仅走 substring, 不再扩展,
        避免 DLPC ↔ DLPA 等同根不同子族被误串台。
    """
    t = token.lower()
    if t in source_lower:
        return True
    m = _LETTER_PREFIX_NUM_RE.match(t)
    if not m:
        return False
    prefix, rest = m.group(1), m.group(2)
    return re.search(rf"{prefix}[a-z]+{re.escape(rest)}", source_lower) is not None


def _discover_relevant_datasheet_sources(
    chunks: list[dict],
    device_tokens: list[str],
) -> tuple[set[str], dict[str, list[str]]]:
    """按 device_tokens 收窄 datasheet 来源; 没设备 / 没命中时退回全部 datasheet。

    返回:
      (sources, aliases)
      sources: 收窄后的 source 文件名集合
      aliases: {user_token: [matched_source, ...]}, 仅含「模糊命中」的条目, 即用户写的
               token 未在 source 中直接 substring 命中, 而是经字母前缀容错命中。供生成
               器在回答里向用户说明（如「未直接命中 DLP6540, 已用 DLPC6540 资料作答」）。

    例:
      device_tokens=["DLPC3436"] → sources={"dlpc3436_clean.md"}, aliases={}
      device_tokens=["DLP6540"]  → sources={"dlpc6540_..."}, aliases={"DLP6540": ["dlpc6540_..."]}
    """
    all_ds = _discover_datasheet_sources(chunks)
    if not device_tokens or not all_ds:
        return all_ds, {}
    narrowed: set[str] = set()
    aliases: dict[str, list[str]] = {}
    for src in all_ds:
        src_lower = src.lower()
        for token in device_tokens:
            if not _device_token_matches_source(token, src_lower):
                continue
            narrowed.add(src)
            if token.lower() not in src_lower:
                aliases.setdefault(token, []).append(src)
            break  # 该 source 已被某个 token 命中, 不必再试其他 token
    if not narrowed:
        return all_ds, {}
    return narrowed, aliases


# ── 切面检索 ─────────────────────────────────────────────────────────────────

def _run_faceted_retrieval(
    retriever,
    device_prefix: str,
    topic_or_query: str,
    where: dict | None,
) -> dict[str, list[dict]]:
    """对每个切面跑一次 hybrid 检索, 串行执行, 打印每切面耗时。

    返回 {facet_key: [SearchResult, ...]}, 每个 SearchResult 带 `facet` 字段。
    """
    results: dict[str, list[dict]] = {}
    for facet_key, facet_def in _FACETS.items():
        facet_query = _build_facet_query(facet_def["keywords"], device_prefix, topic_or_query)
        start = time.perf_counter()
        hits = retriever.search(facet_query, method="hybrid", top_k=PER_FACET_FETCH, where=where)
        took_ms = int((time.perf_counter() - start) * 1000)
        tagged = [dict(hit, facet=facet_key, facet_query=facet_query) for hit in hits]
        results[facet_key] = tagged
        print(
            f"[search_datasheet_v2] facet={facet_key} q={facet_query!r} "
            f"hits={len(hits)} took={took_ms}ms"
        )
    return results


def _build_facet_query(facet_keywords: str, device_prefix: str, topic_or_query: str) -> str:
    """构造 facet query: {device_prefix} {topic_or_query} {facet_keywords}。

    任一段为空时跳过, 多余空白会被折叠。
    """
    parts: list[str] = []
    if device_prefix and device_prefix.strip():
        parts.append(device_prefix.strip())
    if topic_or_query and topic_or_query.strip():
        parts.append(topic_or_query.strip())
    if facet_keywords and facet_keywords.strip():
        parts.append(facet_keywords.strip())
    return " ".join(" ".join(parts).split())


# ── Round-robin 合并 ─────────────────────────────────────────────────────────

def _facet_round_robin_topk(
    facet_results: dict[str, list[dict]],
    total: int,
    min_per_facet: int,
) -> list[dict]:
    """按切面轮询合并到 top-N, 保证每切面至少保留 min_per_facet 条（若候选足够）。

    两阶段策略:
      阶段 1 — 保底: 依次给每个切面收满 min_per_facet 条（跨切面去重, 首次出现获胜）
      阶段 2 — 轮询: 剩余名额按切面顺序逐条轮转填充, 直到达到 total 或全部耗尽

    去重 key: 文本前 160 字。同一段文本即使被多切面召回, 只保留首次出现的 facet 标签。
    """
    if not facet_results:
        return []

    merged: list[dict] = []
    seen: set[str] = set()
    cursors: dict[str, int] = {facet: 0 for facet in facet_results}

    def dedupe_key(result: dict) -> str:
        return (result.get("text") or "")[:160]

    # 阶段 1: 保底
    for facet, hits in facet_results.items():
        taken = 0
        while taken < min_per_facet and cursors[facet] < len(hits):
            candidate = hits[cursors[facet]]
            cursors[facet] += 1
            key = dedupe_key(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
            taken += 1
            if len(merged) >= total:
                return merged

    # 阶段 2: 轮询填充剩余名额
    while len(merged) < total:
        advanced = False
        for facet, hits in facet_results.items():
            while cursors[facet] < len(hits):
                candidate = hits[cursors[facet]]
                cursors[facet] += 1
                key = dedupe_key(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(candidate)
                advanced = True
                break  # 本切面在本轮取一条就交给下一切面
            if len(merged) >= total:
                return merged
        if not advanced:
            break  # 所有切面候选耗尽

    return merged


# ── 辅助 ─────────────────────────────────────────────────────────────────────

def _extract_search_query(query: str, query_structure: dict | None) -> str:
    """datasheet 查询优先保留原始 query; what 含具体技术词时才采用 what。

    与 V1 行为对齐, 但判定改用 entity_tokens 而非硬编码关键词列表。
    """
    what = (
        (query_structure or {})
        .get("dimensions", {})
        .get("what", {})
        .get("value")
    )
    if not what:
        return query
    if extract_datasheet_entity_tokens(what):
        return what
    return query
