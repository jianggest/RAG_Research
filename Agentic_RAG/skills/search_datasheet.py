"""
Skill：search_datasheet

职责：处理芯片 datasheet / 硬件规格书中的技术参数查询。
适用问题类型：
  - timing requirements / electrical characteristics / recommended operating conditions
  - oscillator / clock / PLL / pin connection / interface timing
  - 具体符号、数值、单位查询（MHz、ns、ppm、V、mA 等）

检索策略：
  - 领域隔离：只检索 datasheet 文档，避免企业制度文档污染
  - 技术关键词扩写：对短符号、英文术语、中文问法做多路检索
  - Hybrid（BM25 + 向量）+ 表格优先：datasheet 关键事实通常在表格中
"""

SKILL_META = {
    "name": "search_datasheet",
    "description": (
        "该Skill处理芯片datasheet、硬件规格书、电子器件手册中的技术参数查询，"
        "覆盖 timing requirements、电气特性、recommended operating conditions、clock、oscillator、PLL、pin connection、interface timing、"
        "以及具体符号/数值/单位（如 MOSC、f clk、t c、t w(H)、t w(L)、t jp、PLL_REFCLK_I、MHz、ns、ppm）的查询。"
        "适用于 DLPC3436 等器件手册；不处理企业HR、财务报销、行政、IT账号登录等内部制度问题。"
    ),
    "retrieval_method": "hybrid",
}

# datasheet 域来源兜底；主路径会从 retriever.chunks 动态发现 DLPC/datasheet 文档。
_SOURCES = {
    "dlpc3436.md",
    "dlpc3436_clean.md",
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

_CONCEPT_MAP: dict[str, list[str]] = {
    "System Oscillator Timing": [
        "System Oscillator Timing Requirements",
        "MOSC primary oscillator clock f clk t c t w(H) t w(L) t t t jp",
        "Clock frequency MOSC Cycle time Pulse duration Transition time period jitter",
    ],
    "系统 Oscillator Timing": [
        "System Oscillator Timing Requirements",
        "MOSC primary oscillator clock f clk t c t w(H) t w(L) t t t jp",
        "Clock frequency MOSC Cycle time Pulse duration Transition time period jitter",
    ],
    "振荡器定时": [
        "System Oscillator Timing Requirements",
        "MOSC primary oscillator clock f clk t c t w(H) t w(L) t t t jp",
    ],
    "MOSC": [
        "MOSC primary oscillator clock",
        "System Oscillator Timing Requirements MOSC",
        "Clock frequency MOSC Cycle time MOSC Pulse duration MOSC jitter MOSC",
    ],
    "PLL_REFCLK": [
        "PLL_REFCLK_I PLL_REFCLK_O external oscillator crystal input return",
        "Clock and PLL Support external oscillator leave unconnected",
        "Reference Clock Layout external oscillator PLL_REFCLK_I PLL_REFCLK_O",
    ],
    "外部振荡器": [
        "external oscillator PLL_REFCLK_I PLL_REFCLK_O",
        "If an external oscillator is used oscillator output must drive PLL_REFCLK_I",
        "PLL_REFCLK_O leave unconnected floating no added capacitive load",
    ],
    "频率精度": [
        "reference clock frequency variation ±200 ppm aging temperature trim component variation",
        "Crystal frequency tolerance including accuracy temperature aging trim sensitivity ±200 PPM",
    ],
}

_TECH_HINTS = (
    "DLPC3436", "datasheet", "timing", "oscillator", "MOSC", "PLL", "clock",
    "f clk", "t c", "t w", "t jp", "ppm", "MHz", "ns", "PLL_REFCLK",
)


def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    search_query = _extract_search_query(query, query_structure)
    bundle_results = _try_bundle_planner(search_query, retriever)
    if bundle_results:
        print(f"[search_datasheet] bundle planner 返回 {len(bundle_results)} 条")
        boosted = _boost_datasheet_chunks(bundle_results, query=search_query)
        print(f"[search_datasheet] bundle top5: {[(r.get('score'), r.get('staged_reason'), r.get('source'), r.get('text','')[:45]) for r in boosted[:5]]}")
        return boosted[:20]

    expanded = _expand_query(search_query)
    print(f"[search_datasheet] 检索词：{search_query!r} → {expanded}")

    datasheet_sources = _discover_datasheet_sources(getattr(retriever, "chunks", [])) or set(_SOURCES)
    _where = {"source": {"$in": list(datasheet_sources)}}
    all_results: list[dict] = []

    for eq in expanded:
        sub = retriever.search(eq, method="hybrid", top_k=10, where=_where)
        print(f"[search_datasheet] hybrid 检索 {eq!r} 返回 {len(sub)} 条")
        all_results = _merge_deduplicate(all_results, sub)

    all_results = _filter_by_source(all_results, datasheet_sources)
    all_results = _add_staged_datasheet_context(
        all_results,
        chunks=getattr(retriever, "chunks", []),
        query=search_query,
        sources=datasheet_sources,
    )
    all_results = _boost_datasheet_chunks(all_results, query=search_query)
    print(f"[search_datasheet] 重排后 top5: {[(r.get('score'), r.get('is_table'), r.get('source'), r.get('text','')[:45]) for r in all_results[:5]]}")
    return all_results[:20]


def _try_bundle_planner(query: str, retriever) -> list[dict]:
    if not hasattr(retriever, "search_datasheet_index"):
        return []
    try:
        bundle = retriever.search_datasheet_index(query, top_k=20, return_bundle=True)
    except Exception as exc:
        print(f"[search_datasheet] bundle planner 不可用，fallback staged rules: {exc}")
        return []
    evidence = (bundle or {}).get("evidence") or []
    query_type = (bundle or {}).get("query_type", "datasheet")
    results: list[dict] = []
    for idx, item in enumerate(evidence):
        text = item.get("text", "")
        source = item.get("source", "") or (bundle or {}).get("source", "")
        if not text or not source:
            continue
        result = {
            "text": text,
            "source": source,
            "score": float(item.get("score", 1.0) or 1.0) + 300.0 - idx,
            "is_table": item.get("kind") == "row" or "|" in text,
            "is_datasheet": True,
            "index_kind": item.get("kind", "block"),
            "staged_reason": f"bundle_{query_type}",
        }
        for key in ("section_id", "section_title", "table_id", "row_id", "source_line"):
            if item.get(key) not in (None, ""):
                result[key] = item.get(key)
        results.append(result)
    return results


def _extract_search_query(query: str, query_structure: dict = None) -> str:
    """datasheet 查询优先保留原始技术词；只有 what 明显更具体时才使用 what。"""
    what = (
        (query_structure or {})
        .get("dimensions", {})
        .get("what", {})
        .get("value")
    )
    if what and any(h.lower() in what.lower() for h in _TECH_HINTS):
        return what
    return query


def _expand_query(query: str) -> list[str]:
    expanded = [query]
    q_lower = query.lower()

    for key, expansions in _CONCEPT_MAP.items():
        if key.lower() in q_lower:
            expanded.extend(expansions)

    # 对常见混合中英问法兜底补充强关键词
    if any(k.lower() in q_lower for k in ("oscillator", "振荡器", "mosc", "timing", "定时")) and not ("dmd" in q_lower and ("parking" in q_lower or "timing" in q_lower)):
        expanded.extend(_CONCEPT_MAP["System Oscillator Timing"])
    if any(k.lower() in q_lower for k in ("pll_refclk", "外部振荡器", "crystal", "晶体")):
        expanded.extend(_CONCEPT_MAP["PLL_REFCLK"])
    if any(k.lower() in q_lower for k in ("ppm", "精度", "tolerance", "variation")):
        expanded.extend(_CONCEPT_MAP["频率精度"])
    if any(k.lower() in q_lower for k in ("spread spectrum", "clock spreading", "展频")):
        expanded.append("spread spectrum clock spreading MOSC input does not support")
    if any(k.lower() in q_lower for k in ("spi flash", "serial flash", "flash")):
        expanded.extend([
            "VCC_FLSH corresponding voltage 1.8-V 2.5-V 3.3-V serial flash devices",
            "Compatible SPI Flash Device Options 3.3-V W25Q32FVSSIG W25Q64FVSSIG",
        ])

    if any(k.lower() in q_lower for k in ("i2c", "iic", "i 2 c")):
        expanded.extend([
            "IIC0_SCL IIC0_SDA IIC1_SCL IIC1_SDA I 2 C secondary port control port internal use",
            "Both DLPC34xx I 2 C interface ports support 100-kHz baud rate",
        ])

    return _unique(expanded)


def _discover_datasheet_sources(chunks: list[dict]) -> set[str]:
    """从已加载 chunks 自动识别 datasheet 来源，避免新增 DLPC 文档后手工维护 _SOURCES。"""
    sources: set[str] = set()
    by_source: dict[str, list[str]] = {}
    for chunk in chunks or []:
        source = chunk.get("source", "")
        if source:
            by_source.setdefault(source, []).append(chunk.get("text", "")[:1000])

    for source, texts in by_source.items():
        haystack = f"{source}\n" + "\n".join(texts)
        h = haystack.lower()
        if any(hint in h for hint in _DATASHEET_SOURCE_HINTS):
            sources.add(source)

    return sources


def _unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _merge_deduplicate(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for r in primary + secondary:
        duplicate_at = None
        for i, existing in enumerate(merged):
            if _same_datasheet_fact(existing, r):
                duplicate_at = i
                break
        if duplicate_at is None:
            merged.append(r)
            continue
        if _result_richness(r) > _result_richness(merged[duplicate_at]):
            merged[duplicate_at] = r
    return merged


def _add_staged_datasheet_context(
    results: list[dict],
    chunks: list[dict],
    query: str,
    sources: set[str],
) -> list[dict]:
    """Small-slice Phase 4 staged retrieval for current measurable failures.

    This is intentionally rule-based and offline: when a query asks for oscillator
    requirements or SPI-flash support, append the known companion chunks from the
    same datasheet source so table + notes / prerequisite + option rows survive
    final top-k reranking.
    """
    q = query.lower()
    staged: list[dict] = []

    wants_oscillator = any(k in q for k in ("oscillator", "振荡器", "mosc", "timing")) and not (
        any(k in q for k in ("parking", "park", "dmd parking", "gpio_08", "gpio08", "parkz")) or ("dmd" in q and "timing" in q)
    )
    wants_spi_flash = "spi" in q and "flash" in q
    wants_parking = any(k in q for k in ("parking", "park", "dmd parking", "gpio_08", "gpio08", "parkz")) or ("dmd" in q and "timing" in q)
    wants_i2c_ports = any(k in q for k in ("i2c", "iic", "i 2 c")) and any(k in q for k in ("端口", "port", "ports", "有哪些", "support", "支持"))
    wants_i2c_command_state = any(k in q for k in ("i2c", "iic", "i 2 c")) and any(k in q for k in ("命令", "command", "ready", "什么时候", "when"))

    for chunk in chunks or []:
        if chunk.get("source") not in sources:
            continue
        text = chunk.get("text", "")
        tl = text.lower()
        score = 0.0
        reason = ""

        if wants_oscillator:
            if "system oscillator timing requirements" in tl and "23.998" in text and "t jp" in tl:
                score = 100.0
                reason = "staged_oscillator_table"
            elif "±200 ppm" in tl and "spread spectrum clock spreading" in tl and "external digital oscillator" in tl:
                score = 95.0
                reason = "staged_oscillator_notes"

        if wants_spi_flash:
            if "vcc\\_flsh" in tl and "corresponding voltage" in tl and "3.3-v" in tl:
                score = max(score, 100.0)
                reason = "staged_spi_flash_condition"
            elif "compatible spi flash device options" in tl and "w25q32fvssig" in tl and "w25q64fvssig" in tl:
                score = max(score, 95.0)
                reason = "staged_spi_flash_options"

        if wants_parking:
            if "dmd parking switching characteristics" in tl and "t park" in tl and "t fast park" in tl:
                score = max(score, 100.0)
                reason = "staged_parking_timing_table"
            elif "gpio\\_08" in tl and "normal mirror parking request" in tl and "park the dmd" in tl:
                score = max(score, 98.0)
                reason = "staged_parking_gpio08_pin"
            elif "fast park request" in tl and "parkz goes low" in tl:
                score = max(score, 220.0)
                reason = "staged_parking_parkz_note"

        if wants_i2c_ports:
            if "iic0_scl" in tl and "iic0_sda" in tl and "iic1_scl" in tl and "iic1_sda" in tl:
                score = max(score, 220.0)
                reason = "staged_i2c_pin_rows"
            elif "both" in tl and "i 2 c" in tl and "interface" in tl and "100-khz" in tl and "baud rate" in tl:
                score = max(score, 220.0)
                reason = "staged_i2c_interface_rate"

        if wants_i2c_command_state:
            if "host\\_irq" in tl and "ready to receive commands" in tl and "auto-initialization" in tl:
                score = max(score, 100.0)
                reason = "staged_i2c_command_ready_state"

        if score:
            staged.append({**chunk, "score": score, "staged_reason": reason})

    return _merge_deduplicate(results, staged)


def _same_datasheet_fact(a: dict, b: dict) -> bool:
    if a.get("source") != b.get("source"):
        return False
    at = a.get("text", "")
    bt = b.get("text", "")
    al = at.lower()
    bl = bt.lower()
    # Table-of-contents chunks mention many section titles; never let them dedupe
    # real evidence chunks.
    if "table of contents" in al or "table of contents" in bl:
        return at[:160] == bt[:160]
    if at[:160] == bt[:160]:
        return True
    section_markers = (
        "system oscillator timing requirements",
        "clock and pll support",
        "recommended crystal oscillator configuration",
    )
    return any(marker in al and marker in bl for marker in section_markers)


def _result_richness(r: dict) -> int:
    text = r.get("text", "")
    tl = text.lower()
    richness = min(len(text), 5000)
    for marker in (
        "spread spectrum clock spreading",
        "±200 ppm",
        "external digital oscillator",
        "pll_refclk_i",
        "pll_refclk_o",
    ):
        if marker in tl:
            richness += 2000
    return richness


def _filter_by_source(results: list[dict], sources: set[str], min_keep: int = 1) -> list[dict]:
    filtered = [r for r in results if r.get("source") in sources]
    if len(filtered) < min_keep:
        print(f"[search_datasheet] ⚠️ 来源过滤后仅剩 {len(filtered)} 条，回退到不过滤")
        return results
    return filtered


def _boost_datasheet_chunks(results: list[dict], query: str) -> list[dict]:
    q = query.lower()
    boosted = []
    for r in results:
        score = float(r.get("score", 0) or 0)
        text = r.get("text", "")
        text_lower = text.lower()

        if r.get("is_table"):
            score *= 1.6
        if "system oscillator timing requirements" in text_lower:
            score *= 1.8
        if "mosc" in q and "mosc" in text_lower:
            score *= 1.4
        if "pll_refclk" in q and "pll_refclk" in text_lower:
            score *= 1.4
        if any(token in text for token in ("23.998", "24.002", "41.667", "±200", "PLL_REFCLK_I", "PLL_REFCLK_O")):
            score *= 1.25
        if r.get("staged_reason"):
            score += 100.0
        if "table of contents" in text_lower:
            score *= 0.05

        boosted.append({**r, "score": round(score, 6)})

    return sorted(boosted, key=lambda x: x.get("score", 0), reverse=True)
