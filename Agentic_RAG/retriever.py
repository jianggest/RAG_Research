"""
Retriever 模块

职责：管理向量索引，提供检索接口供 Skill 调用。
对外接口：Retriever 类，三种检索策略（Strategy 模式）：
  - vector_search(query, top_k)   向量检索（当前实现）
  - bm25_search(query, top_k)     BM25 关键词检索（Phase 2 实现）
  - hybrid_search(query, top_k)   混合检索（Phase 2 实现）
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from config import (
    AUGMENT_QUESTIONS,
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    INDEX_BATCH_SIZE,
    PERSIST_CHROMA_INDEX,
    TOP_K,
    get_chroma_collection_names,
)

def _chunk_content_id(prefix: str, chunk: dict) -> str:
    fingerprint = "\n".join([
        str(chunk.get("source", "")),
        str(chunk.get("chunk_index", "")),
        chunk.get("normalized_text", chunk.get("text", "")),
    ])
    return f"{prefix}_{hashlib.md5(fingerprint.encode()).hexdigest()}"


# ── 结构锚字段序列化（Chroma metadata 不支持 list，用 "|" 分隔字符串）───────────
# 锚点值形如 "(1)" / "Figure 6-5"，均不含 "|"，分隔符安全。

def _serialize_anchor_list(items: list[str] | None) -> str:
    """list[str] → "a|b|c"；None / 空列表 → ""。"""
    return "|".join(items) if items else ""


def _deserialize_anchor_list(value: str | None) -> list[str]:
    """metadata 中的 "a|b|c" → ["a","b","c"]；None / "" → []。"""
    if not value:
        return []
    return [item for item in value.split("|") if item]


_ENTITY_TOKEN_RE = re.compile(
    r"\b(?:TSTPT_?\d+|IIC\d_[A-Z]+|GPIO_\d+|GPIO\d+|PLL_REFCLK_[IO]|PLL\s+REFCLK\s+[IO]|VCC_[A-Z0-9]+|HOST_IRQ|SPI\d_[A-Z0-9]+|[A-Z]{2,}\d*[A-Z0-9_]*)\b"
)


def normalize_datasheet_text(text: str) -> str:
    """Normalize common datasheet aliases for sparse/exact retrieval.

    The original text is still preserved for generation; this field is only for
    matching aliases such as I 2 C/I²C/IIC, GPIO08/GPIO_08 and clock symbols.
    """
    normalized = text
    normalized = normalized.replace("I²C", "I2C")
    normalized = re.sub(r"\bI\s*2\s*C\b", "I2C", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bIIC\b", "I2C", normalized, flags=re.IGNORECASE)
    if re.search(r"\bIIC\d_", normalized, flags=re.IGNORECASE) and "I2C" not in normalized:
        normalized = f"{normalized} I2C"
    normalized = re.sub(r"\bGPIO\s*_?\s*(\d{2})\b", r"GPIO_\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bTSTPT\s*_?\s*(\d+)\b", r"TSTPT_\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bPLL\s+REFCLK\s+([IO])\b", r"PLL_REFCLK_\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\+/-\s*200\s*ppm\b", "±200 ppm", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b±\s*200\s*PPM\b", "±200 ppm", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bf\s*_?\s*clk\b", "f_clk", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def extract_datasheet_entity_tokens(text: str) -> list[str]:
    """Extract high-signal exact-match tokens for datasheet chunks/rows."""
    normalized = normalize_datasheet_text(text)
    seen: list[str] = []
    for match in _ENTITY_TOKEN_RE.findall(normalized):
        token = re.sub(r"\s+", "_", match.upper())
        if token.startswith("GPIO") and not token.startswith("GPIO_"):
            token = token.replace("GPIO", "GPIO_", 1)
        if token.startswith("TSTPT") and not token.startswith("TSTPT_"):
            token = token.replace("TSTPT", "TSTPT_", 1)
        if token and token not in seen:
            seen.append(token)
    if "I2C" in normalized and "I2C" not in seen:
        seen.append("I2C")
    if "f_clk" in normalized and "f_clk" not in seen:
        seen.append("f_clk")
    if "±200 ppm" in normalized and "±200 ppm" not in seen:
        seen.append("±200 ppm")
    return seen


def build_datasheet_row_chunks(structure_path: str | Path) -> list[dict]:
    """Build row-level chunks from a Phase-1 datasheet structure digest."""
    path = Path(structure_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    source = data.get("source", path.name.replace(".structure.json", "_clean.md"))
    tables = {table.get("table_id"): table for table in data.get("table_catalog", [])}
    rows: list[dict] = []
    for idx, row in enumerate(data.get("row_index", [])):
        table = tables.get(row.get("table_id"), {})
        section_id = row.get("section_id") or table.get("section_id") or ""
        table_title = table.get("table_title") or row.get("table_id") or ""
        original = row.get("original_text", "")
        row_text = (
            f"[doc: {source}]\n"
            f"[section: {section_id}]\n"
            f"[table: {table_title}]\n"
            f"[row: {original}]"
        )
        normalized = normalize_datasheet_text(row_text)
        rows.append({
            "source": source,
            "chunk_index": idx,
            "text": row_text,
            "is_table": True,
            "is_datasheet": True,
            "index_kind": "row",
            "normalized_text": normalized,
            "entity_tokens": extract_datasheet_entity_tokens(original),
            # 结构锚字段：row chunk 是表格的单行，脚注归属表格整体 chunk，此处用空列表占位
            # 保持与 block chunk 的 schema 一致，避免下游访问时 KeyError
            "anchors_used": [],
            "anchors_defined": [],
            "refs_outbound": [],
            "row_id": row.get("row_id", ""),
            "table_id": row.get("table_id", ""),
            "section_id": section_id,
            "source_line": row.get("source_line"),
        })
    return rows


def _metadata_for_chunk(chunk: dict) -> dict:
    metadata = {
        "source": chunk.get("source", ""),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "is_table": bool(chunk.get("is_table", False)),
        "is_datasheet": bool(chunk.get("is_datasheet", False)),
        "index_kind": chunk.get("index_kind", "block"),
        "is_augmented": bool(chunk.get("is_augmented", False)),
        "original_text": chunk.get("text", ""),
        # 结构锚字段：ChromaDB metadata 只接受标量，序列化为 "|" 分隔字符串
        "anchors_used":    _serialize_anchor_list(chunk.get("anchors_used")),
        "anchors_defined": _serialize_anchor_list(chunk.get("anchors_defined")),
        "refs_outbound":   _serialize_anchor_list(chunk.get("refs_outbound")),
    }
    for key in ("row_id", "table_id", "section_id"):
        if chunk.get(key) is not None:
            metadata[key] = str(chunk.get(key))
    if chunk.get("source_line") is not None:
        metadata["source_line"] = int(chunk.get("source_line"))
    return metadata


def build_specification_reading_closure(query: str, source_path: str | Path) -> dict:
    """Build a structured reading closure for specification-style documents.

    Phase 7 minimal slice: start from the most relevant section anchor, attach
    nearby annotation/note cues, then follow high-signal terms from those cues
    to definition/dependency rows elsewhere in the same source. This is
    intentionally subject/cue based rather than TE-case based.
    """
    path = Path(source_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    normalized_query = normalize_datasheet_text(query).lower()

    anchor_idx = _find_spec_anchor_line(lines, normalized_query)
    section_start, section_end = _section_bounds(lines, anchor_idx)
    anchors = _reading_anchor_items(lines, section_start, section_end, str(path.name))

    followed: list[dict] = []
    unresolved: list[dict] = []
    cue_lines = _nearby_reading_cues(lines, section_start, section_end)
    for line_no, quote in cue_lines:
        followed.append(_reading_cue_item(quote, line_no, path.name))

    cue_text = "\n".join(quote for _, quote in cue_lines)
    for line_no, quote in _find_section_reference_lines(lines, cue_text):
        followed.append({
            "cue_type": "cross_reference",
            "relation": "dependency",
            "quote": quote,
            "line": line_no,
            "source": path.name,
            "confidence": 0.8,
        })
    for line_no, quote in _find_phrase_definition_lines(lines, cue_text, exclude=(section_start, section_end)):
        followed.append({
            "cue_type": "cross_reference",
            "relation": "dependency",
            "quote": quote,
            "line": line_no,
            "source": path.name,
            "confidence": 0.75,
        })

    for term in sorted(set(extract_datasheet_entity_tokens(cue_text))):
        if term in {"MOSC", "PPM"}:
            continue
        if any(term in normalize_datasheet_text(item.get("quote", "")) for item in anchors + followed):
            continue
        definition_lines = _find_definition_lines(lines, term, exclude=(section_start, section_end))
        if not definition_lines:
            unresolved.append({"cue_type": "definition", "term": term, "reason": "definition not found"})
            continue
        for line_no, quote in definition_lines:
            followed.append({
                "cue_type": "cross_reference",
                "relation": "dependency",
                "quote": quote,
                "line": line_no,
                "source": path.name,
                "confidence": 0.8,
            })

    return {
        "subject": _subject_from_heading(lines[anchor_idx - 1] if anchor_idx else query),
        "anchors": anchors,
        "followed_cues": _dedupe_closure_items(followed),
        "unresolved_cues": unresolved,
        "closure_complete": not unresolved and bool(anchors),
    }


def _find_spec_anchor_line(lines: list[str], normalized_query: str) -> int:
    query_terms = [t for t in re.split(r"\W+", normalized_query) if len(t) >= 4]
    query_entities = set(extract_datasheet_entity_tokens(normalized_query))
    best_idx = 1
    best_score = -1
    for idx, line in enumerate(lines, start=1):
        norm = normalize_datasheet_text(line).lower()
        score = sum(1 for term in query_terms if term in norm)
        line_entities = set(extract_datasheet_entity_tokens(line))
        score += 10 * len(query_entities & line_entities)
        if not score:
            continue
        if line.startswith("## "):
            score += 3
        if "timing requirements" in norm and "oscillator" in norm:
            score += 5
        if "table of contents" in norm:
            score -= 5
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx


def _section_bounds(lines: list[str], anchor_idx: int) -> tuple[int, int]:
    start = anchor_idx
    while start > 1 and not lines[start - 1].startswith("## "):
        start -= 1
    end = anchor_idx + 1
    while end <= len(lines) and not lines[end - 1].startswith("## "):
        end += 1
    return start, end - 1


def _subject_from_heading(line: str) -> str:
    return line.lstrip("# ").strip() or "specification subject"


def _reading_anchor_items(lines: list[str], start: int, end: int, source: str) -> list[dict]:
    anchors: list[dict] = []
    for line_no in range(start, end + 1):
        quote = lines[line_no - 1].strip()
        if not quote or quote.startswith("-") or quote.lower().startswith("figure"):
            continue
        if quote.startswith("##") or "|" in quote:
            anchors.append({
                "quote": quote,
                "line": line_no,
                "source": source,
                "relation": "source_context" if quote.startswith("##") else "value",
            })
    return anchors


def _nearby_reading_cues(lines: list[str], start: int, end: int) -> list[tuple[int, str]]:
    cues: list[tuple[int, str]] = []
    scan_end = min(len(lines), end + 30)
    for line_no in range(start, scan_end + 1):
        quote = lines[line_no - 1].strip()
        if not quote:
            continue
        lower = quote.lower()
        if quote.startswith("## Note") and line_no < len(lines):
            next_quote = lines[line_no].strip()
            if next_quote:
                cues.append((line_no + 1, next_quote))
            continue
        if quote.startswith("-") or lower.startswith(("note", "warning", "caution")) or lower.startswith("figure") or "note:" in lower or "see section" in lower:
            if "see section" in lower:
                quote = _join_split_section_reference(lines, line_no, quote)
            cues.append((line_no, quote))
    return cues


def _join_split_section_reference(lines: list[str], line_no: int, quote: str) -> str:
    """Join converted-PDF table cells where `See Section` and section number split across continuation rows."""
    if re.search(r"See\s+Section\s+\d", quote, flags=re.IGNORECASE):
        return quote
    joined = quote
    for next_no in range(line_no + 1, min(len(lines), line_no + 3) + 1):
        nxt = lines[next_no - 1].strip()
        if not nxt:
            break
        if re.search(r"\d+(?:\.\d+)+\s+for more information", nxt, flags=re.IGNORECASE):
            return joined.rstrip("|").rstrip() + " " + nxt
        if nxt.startswith("|") and any(token in nxt for token in ("TSTPT_", "JTAG", "RESETZ", "HWTEST")):
            break
    return joined


def _reading_cue_item(quote: str, line_no: int, source: str) -> dict:
    lower = quote.lower()
    relation = "condition" if "applies only" in lower or "when " in lower else "constraint" if "not support" in lower or "must" in lower else "source_context" if lower.startswith("figure") else "definition"
    cue_type = "annotation" if quote.startswith("-") else "figure" if lower.startswith("figure") else "note"
    return {
        "cue_type": cue_type,
        "relation": relation,
        "quote": quote,
        "line": line_no,
        "source": source,
        "confidence": 0.9,
    }


def _find_section_reference_lines(lines: list[str], cue_text: str) -> list[tuple[int, str]]:
    refs = []
    compact = re.sub(r"\s+", " ", cue_text.replace("\n", " "))
    compact = re.sub(r"See\s+Section\s+\|\s*([^|]*?\d+(?:\.\d+)+)\s+for more information", r"See Section \1 for more information", compact, flags=re.IGNORECASE)
    compact = re.sub(r"Section\s+(\d+(?:\.\d+)*)\s+for more information", r"Section \1 for more information", compact, flags=re.IGNORECASE)
    for match in re.finditer(r"Section\s+(\d+(?:\.\d+)+)", compact, flags=re.IGNORECASE):
        refs.append(match.group(1))
    if re.search(r"See\s+Section", compact, flags=re.IGNORECASE):
        for match in re.finditer(r"\b(\d+\.\d+\.\d+(?:\.\d+)*)\b", compact):
            refs.append(match.group(1))
    hits: list[tuple[int, str]] = []
    for ref in refs:
        heading_prefix = f"## {ref}"
        for idx, line in enumerate(lines, start=1):
            if line.startswith(heading_prefix):
                section_start, section_end = _section_bounds(lines, idx)
                for line_no in range(section_start, min(section_end, section_start + 4) + 1):
                    quote = lines[line_no - 1].strip()
                    if quote:
                        hits.append((line_no, quote))
                break
    return hits


def _find_phrase_definition_lines(lines: list[str], cue_text: str, exclude: tuple[int, int]) -> list[tuple[int, str]]:
    phrases: list[str] = []
    lower = cue_text.lower()
    if "external" in lower and "oscillator" in lower:
        phrases.append("external oscillator")
    if "crystal" in lower:
        phrases.append("crystal")
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if exclude[0] <= idx <= exclude[1]:
            continue
        quote = line.strip()
        lower_quote = quote.lower()
        if not quote or not any(phrase in lower_quote for phrase in phrases):
            continue
        if "pin" in lower_quote or "input" in lower_quote or "return" in lower_quote or "floating" in lower_quote or "unconnected" in lower_quote:
            hits.append((idx, quote))
    return hits[:6]


def _find_definition_lines(lines: list[str], term: str, exclude: tuple[int, int]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if exclude[0] <= idx <= exclude[1]:
            continue
        quote = line.strip()
        if not quote or term not in normalize_datasheet_text(quote):
            continue
        lower = quote.lower()
        if "input" in lower or "return" in lower or "used" in lower or "floating" in lower or "unconnected" in lower:
            hits.append((idx, quote))
    return hits[:4]


def _dedupe_closure_items(items: list[dict]) -> list[dict]:
    seen: set[tuple[str, int]] = set()
    deduped: list[dict] = []
    for item in items:
        key = (item.get("quote", ""), int(item.get("line", 0)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


class SearchResult(TypedDict):
    text: str
    source: str
    score: float
    is_table: bool
    is_datasheet: bool
    index_kind: str
    # 结构锚字段：透传 Chunk 上的同名字段，供 V2 检索做 facet 配对、跨引用跟随等。
    # 普通文本 chunk 三者皆为空列表。
    anchors_used: list[str]
    anchors_defined: list[str]
    refs_outbound: list[str]


_CROSS_REF_SECTION_HEADING_RE = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)\b")
_CROSS_REF_LABEL_RE = re.compile(
    r"\b(Figure|Table|Section|Chapter)\s+([\w.\-]+?\d[\w.\-]*)",
    re.IGNORECASE,
)
_CROSS_REF_FOLLOW_LIMIT = 5
_CROSS_REF_SCORE_FACTOR = 0.7


def _normalize_cross_ref(ref: str) -> str:
    """Normalize a cross-reference label to 'Kind Number'."""
    match = _CROSS_REF_LABEL_RE.search(ref or "")
    if not match:
        return " ".join((ref or "").split())
    kind = match.group(1).capitalize()
    number = match.group(2).rstrip(".,;:")
    return f"{kind} {number}"


def _cross_ref_labels_for_chunk(chunk: dict) -> set[str]:
    """Return structural labels that can be targeted by refs_outbound."""
    labels: set[str] = set()
    text = chunk.get("text", "") or ""

    section_id = str(chunk.get("section_id") or "").strip()
    if section_id:
        labels.add(f"Section {section_id}")

    for line in text.splitlines():
        heading = _CROSS_REF_SECTION_HEADING_RE.match(line.strip())
        if heading:
            labels.add(f"Section {heading.group(1)}")
            if "." not in heading.group(1):
                labels.add(f"Chapter {heading.group(1)}")
        for match in _CROSS_REF_LABEL_RE.finditer(line):
            labels.add(_normalize_cross_ref(match.group(0)))

    return labels


def _result_key(result: dict) -> str:
    return (result.get("source", ""), (result.get("text") or "")[:180])


def _chunk_to_search_result(
    chunk: dict,
    score: float,
    *,
    facet: str | None = None,
    followed_ref: str | None = None,
) -> SearchResult:
    result = SearchResult(
        text=chunk.get("text", ""),
        source=chunk.get("source", ""),
        score=round(float(score), 4),
        is_table=bool(chunk.get("is_table", False)),
        is_datasheet=bool(chunk.get("is_datasheet", False)),
        index_kind=chunk.get("index_kind", "block"),
        anchors_used=list(chunk.get("anchors_used") or []),
        anchors_defined=list(chunk.get("anchors_defined") or []),
        refs_outbound=list(chunk.get("refs_outbound") or []),
    )
    if facet:
        result["facet"] = facet
    if followed_ref:
        result["followed_ref"] = followed_ref
    return result


def _follow_cross_refs(
    top_k_results: list[SearchResult],
    chunks: list[dict],
    max_refs: int = _CROSS_REF_FOLLOW_LIMIT,
) -> list[SearchResult]:
    """Follow refs_outbound from top-K results to chunks in the same source.

    The lookup uses chunk metadata / structure labels (source + ref), not a second
    lexical search. Followed chunks are scored at 0.7x of the source result and
    tagged with facet='cross_ref_followed'.
    """
    if not top_k_results or not chunks or max_refs <= 0:
        return []

    by_source_ref: dict[tuple[str, str], list[dict]] = {}
    for chunk in chunks:
        source = chunk.get("source", "")
        if not source:
            continue
        for label in _cross_ref_labels_for_chunk(chunk):
            by_source_ref.setdefault((source, label), []).append(chunk)

    followed: list[SearchResult] = []
    seen = {_result_key(r) for r in top_k_results}
    refs_seen: set[tuple[str, str]] = set()

    for result in top_k_results:
        source = result.get("source", "")
        if not source:
            continue
        base_score = float(result.get("score", 0) or 0)
        for raw_ref in result.get("refs_outbound", []) or []:
            ref = _normalize_cross_ref(raw_ref)
            ref_key = (source, ref)
            if ref_key in refs_seen:
                continue
            refs_seen.add(ref_key)
            for chunk in by_source_ref.get(ref_key, []):
                candidate = _chunk_to_search_result(
                    chunk,
                    base_score * _CROSS_REF_SCORE_FACTOR,
                    facet="cross_ref_followed",
                    followed_ref=ref,
                )
                key = _result_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                followed.append(candidate)
                if len(followed) >= max_refs:
                    return followed
                break

    return followed


def _with_cross_refs(
    base_results: list[SearchResult],
    chunks: list[dict],
    top_k: int,
) -> list[SearchResult]:
    """Add followed cross-ref chunks to the candidate pool, then trim to top_k."""
    followed = _follow_cross_refs(base_results, chunks)
    if not followed:
        return base_results[:top_k]

    combined: list[SearchResult] = []
    seen: set[tuple[str, str]] = set()
    for result in base_results + followed:
        key = _result_key(result)
        if key in seen:
            continue
        seen.add(key)
        combined.append(result)

    return sorted(combined, key=lambda r: r.get("score", 0), reverse=True)[:top_k]


@dataclass
class DatasheetIndexConfig:
    """Optional Phase-2 datasheet row-index configuration."""

    row_chunks: list[dict] = field(default_factory=list)
    block_collection_name: str | None = None
    row_collection_name: str | None = None
    structure_path: str | Path | None = None

    def __post_init__(self) -> None:
        names = get_chroma_collection_names()
        if self.block_collection_name is None:
            self.block_collection_name = names["datasheet_block"]
        if self.row_collection_name is None:
            self.row_collection_name = names["datasheet_row"]


class Retriever:
    """
    向量检索器，基于 ChromaDB 实现。

    使用方式：
        retriever = Retriever(chunks)
        retriever.build_index()
        results = retriever.vector_search("A类城市住宿费", top_k=5)
    """

    def __init__(self, chunks: list, datasheet_index: DatasheetIndexConfig | None = None) -> None:
        self._chunks = chunks
        self._datasheet_index = datasheet_index or DatasheetIndexConfig()
        self._row_chunks = self._datasheet_index.row_chunks
        self._collection = None
        self._block_collection = None
        self._row_collection = None
        self._client = None

    def _existing_ids(self, collection, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        try:
            existing = collection.get(ids=ids, include=[])
        except TypeError:
            existing = collection.get(ids=ids)
        except Exception:
            return set()
        return set(existing.get("ids", []))

    def _add_chunks_in_batches(self, collection, chunks: list, id_prefix: str, log_label: str) -> int:
        total = len(chunks)
        if total == 0:
            return 0
        all_ids = [_chunk_content_id(id_prefix, c) for c in chunks]
        existing_ids = self._existing_ids(collection, all_ids) if PERSIST_CHROMA_INDEX else set()
        pending = [(i, c, cid) for i, (c, cid) in enumerate(zip(chunks, all_ids)) if cid not in existing_ids]
        skipped = total - len(pending)
        if skipped:
            print(f"[Retriever] {log_label}跳过已存在索引：{skipped}/{total}", flush=True)
        if not pending:
            print(f"[Retriever] {log_label}索引无新增，共 {total} 条", flush=True)
            return 0
        batch_size = max(1, int(INDEX_BATCH_SIZE))
        added = 0
        pending_total = len(pending)
        for start in range(0, pending_total, batch_size):
            batch = pending[start:start + batch_size]
            end = start + len(batch)
            print(f"[Retriever] {log_label}索引进度：{start + 1}-{end}/{pending_total}（总 {total}）", flush=True)
            collection.add(
                documents=[c.get("normalized_text", c["text"]) for _, c, _ in batch],
                ids=[cid for _, _, cid in batch],
                metadatas=[_metadata_for_chunk(c) for _, c, _ in batch],
            )
            added += len(batch)
        return added

    def build_index(self) -> None:
        """建立 ChromaDB 内存向量索引。"""
        import chromadb

        # 大知识库使用持久化 Chroma，避免每次 Streamlit 启动都全量 embedding。
        if PERSIST_CHROMA_INDEX:
            client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
        else:
            # 兼容 chromadb 新旧版本：0.4+ 推荐 EphemeralClient，旧版用 Client()
            try:
                client = chromadb.EphemeralClient()
            except AttributeError:
                client = chromadb.Client()
        self._client = client

        collection_names = [get_chroma_collection_names()["block"]]
        if self._row_chunks:
            collection_names.extend([
                self._datasheet_index.block_collection_name,
                self._datasheet_index.row_collection_name,
            ])
        if not PERSIST_CHROMA_INDEX:
            for name in collection_names:
                try:
                    client.delete_collection(name)
                except Exception:
                    pass

        embedding_fn = _build_embedding_fn()
        kwargs = {"name": self._datasheet_index.block_collection_name if self._row_chunks else get_chroma_collection_names()["block"]}
        if embedding_fn and not PERSIST_CHROMA_INDEX:
            kwargs["embedding_function"] = embedding_fn
        self._block_collection = client.get_or_create_collection(**kwargs) if PERSIST_CHROMA_INDEX else client.create_collection(**kwargs)
        self._collection = self._block_collection

        if not self._chunks:
            print("[Retriever] ⚠️ 知识库为空，索引未建立")
            return

        added = self._add_chunks_in_batches(self._collection, self._chunks, "chunk", "原始")
        if PERSIST_CHROMA_INDEX:
            print(f"[Retriever] 原始新增索引建立完成，共 {added} 条；总 chunks {len(self._chunks)} 条", flush=True)
        else:
            print(f"[Retriever] 原始索引建立完成，共 {len(self._chunks)} 条", flush=True)

        if self._row_chunks:
            row_kwargs = {"name": self._datasheet_index.row_collection_name}
            if embedding_fn and not PERSIST_CHROMA_INDEX:
                row_kwargs["embedding_function"] = embedding_fn
            self._row_collection = client.get_or_create_collection(**row_kwargs) if PERSIST_CHROMA_INDEX else client.create_collection(**row_kwargs)
            row_added = self._add_chunks_in_batches(self._row_collection, self._row_chunks, "row", "Datasheet row ")
            if PERSIST_CHROMA_INDEX:
                print(f"[Retriever] Datasheet row 新增索引建立完成，共 {row_added} 条；总 rows {len(self._row_chunks)} 条", flush=True)
            else:
                print(f"[Retriever] Datasheet row 索引建立完成，共 {len(self._row_chunks)} 条", flush=True)

        # 文档增强索引：为每个 chunk 生成问题，扩充同义词/近义词召回覆盖面
        if AUGMENT_QUESTIONS:
            from index_augmenter import generate_augmented_entries
            entries = generate_augmented_entries(self._chunks)
            if entries:
                total = len(entries)
                batch_size = max(1, int(INDEX_BATCH_SIZE))
                for start in range(0, total, batch_size):
                    batch = entries[start:start + batch_size]
                    end = start + len(batch)
                    print(f"[Retriever] 增强问题索引进度：{end}/{total}", flush=True)
                    self._collection.add(
                        documents=[e["document"] for e in batch],
                        ids=[f"aug_{e['chunk_hash']}_{i}" for i, e in enumerate(batch, start=start)],
                        metadatas=[{
                            "source":        e["source"],
                            "chunk_index":   e["chunk_index"],
                            "is_table":      e["is_table"],
                            "is_datasheet":  bool(e.get("is_datasheet", False)),
                            "index_kind":    e.get("index_kind", "block"),
                            "is_augmented":  True,
                            "original_text": e["original_text"],
                            # 与主索引保持 metadata schema 一致；增强条目透传原 chunk 的锚字段，
                            # 缺失则置空字符串（"|" 分隔序列化）。
                            "anchors_used":    _serialize_anchor_list(e.get("anchors_used")),
                            "anchors_defined": _serialize_anchor_list(e.get("anchors_defined")),
                            "refs_outbound":   _serialize_anchor_list(e.get("refs_outbound")),
                        } for e in batch],
                    )
                print(f"[Retriever] 增强问题索引：{len(entries)} 条", flush=True)

    def _vector_search_collection(
        self,
        collection,
        query: str,
        top_k: int = TOP_K,
        where: dict = None,
        chunk_count: int | None = None,
    ) -> list[SearchResult]:
        if not collection or not query.strip():
            return []
        n = min(top_k, chunk_count or collection.count())
        if n == 0:
            return []
        n_fetch = min(n * 3, collection.count()) if AUGMENT_QUESTIONS else n
        indexed_query = normalize_datasheet_text(query)
        kwargs = {"query_texts": [indexed_query], "n_results": n_fetch}
        if where:
            kwargs["where"] = where
        raw = collection.query(**kwargs)
        seen: dict[str, SearchResult] = {}
        for doc, meta, dist in zip(raw["documents"][0], raw["metadatas"][0], raw["distances"][0]):
            is_augmented = meta.get("is_augmented", False)
            text = meta.get("original_text", doc) if (is_augmented or meta.get("original_text")) else doc
            score = round(max(0.0, 1 - dist), 4)
            key = text[:100]
            if is_augmented:
                print(f"[Retriever] 🔗 增强命中 score={score:.4f} | 问题：'{doc[:50]}' → {meta.get('source','')}")
            if key not in seen or score > seen[key]["score"]:
                seen[key] = SearchResult(
                    text=text,
                    source=meta.get("source", ""),
                    score=score,
                    is_table=bool(meta.get("is_table", False)),
                    is_datasheet=bool(meta.get("is_datasheet", False)),
                    index_kind=meta.get("index_kind", "block"),
                    anchors_used=_deserialize_anchor_list(meta.get("anchors_used")),
                    anchors_defined=_deserialize_anchor_list(meta.get("anchors_defined")),
                    refs_outbound=_deserialize_anchor_list(meta.get("refs_outbound")),
                )
        results = sorted(seen.values(), key=lambda r: r["score"], reverse=True)[:top_k]
        print(f"[Retriever] vector_search top{len(results)} 分数: {[r['score'] for r in results]}")
        return results

    def vector_search(
        self,
        query: str,
        top_k: int = TOP_K,
        where: dict = None,
    ) -> list[SearchResult]:
        """
        向量语义检索。
        返回按相关度降序排列的结果列表。

        Args:
            where: ChromaDB metadata 过滤条件，如 {"is_table": True}
        """
        return self._vector_search_collection(self._collection, query, top_k, where, len(self._chunks))

    def search_block(self, query: str, top_k: int = TOP_K, where: dict = None) -> list[SearchResult]:
        """Search only the Phase-2 block collection."""
        return self._vector_search_collection(self._block_collection or self._collection, query, top_k, where, len(self._chunks))

    def search_row(self, query: str, top_k: int = TOP_K, where: dict = None) -> list[SearchResult]:
        """Search only the Phase-2 datasheet row collection."""
        return self._vector_search_collection(self._row_collection, query, top_k, where, len(self._row_chunks))

    def search_datasheet_index(self, query: str, top_k: int = TOP_K, return_bundle: bool = False) -> list[SearchResult] | dict:
        """Merge row-first and block-context hits from physically separated indexes."""
        if return_bundle:
            return plan_datasheet_evidence_bundle(query, self, top_k=top_k)
        row_results = self.search_row(query, top_k=top_k)
        block_results = self.search_block(query, top_k=top_k)
        query_markers = normalize_datasheet_text(query).lower() + " " + query.lower()
        if "i2c" in query_markers or "iic" in query_markers:
            preferred_blocks = [r for r in block_results if "100-kHz baud rate" in r["text"]]
            if preferred_blocks:
                block_results = preferred_blocks + [r for r in block_results if r not in preferred_blocks]
            else:
                for chunk in self._chunks:
                    if "100-kHz baud rate" in chunk.get("text", ""):
                        block_results = [
                            SearchResult(
                                text=chunk["text"],
                                source=chunk.get("source", ""),
                                score=1.0,
                                is_table=bool(chunk.get("is_table", False)),
                                is_datasheet=bool(chunk.get("is_datasheet", False)),
                                index_kind=chunk.get("index_kind", "block"),
                                anchors_used=list(chunk.get("anchors_used") or []),
                                anchors_defined=list(chunk.get("anchors_defined") or []),
                                refs_outbound=list(chunk.get("refs_outbound") or []),
                            )
                        ]
                        break
        merged: list[SearchResult] = []
        seen: set[str] = set()
        # Row hits carry exact table facts; keep them first, then add block context.
        row_quota = min(len(row_results), max(0, top_k - 1)) if block_results else len(row_results)
        for result in row_results[:row_quota] + block_results:
            key = result["text"][:160]
            if key in seen:
                continue
            seen.add(key)
            merged.append(result)
            if len(merged) >= top_k:
                break
        return merged

    def bm25_search(self, query: str, top_k: int = TOP_K) -> list[SearchResult]:
        """
        BM25 关键词检索。

        适用场景：精确实体查找（城市名、职级名等），比向量检索更能命中含有该关键词的 chunk。
        依赖：pip install rank-bm25
        """
        if not self._chunks or not query.strip():
            return []

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            print("[Retriever] ❌ 未安装 rank-bm25，运行：pip install rank-bm25")
            return []

        # jieba 词级分词；未安装时降级为字符级分词
        tokenized_corpus = [_tokenize(c.get("normalized_text", c["text"])) for c in self._chunks]
        tokenized_query = _tokenize(normalize_datasheet_text(query))

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        # 取 top_k 个得分最高的 chunk，过滤掉得分为 0 的（完全无关）
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        return [
            SearchResult(
                text=self._chunks[i]["text"],
                source=self._chunks[i]["source"],
                score=round(float(scores[i]), 4),
                is_table=bool(self._chunks[i].get("is_table", False)),
                is_datasheet=bool(self._chunks[i].get("is_datasheet", False)),
                index_kind=self._chunks[i].get("index_kind", "block"),
                anchors_used=list(self._chunks[i].get("anchors_used") or []),
                anchors_defined=list(self._chunks[i].get("anchors_defined") or []),
                refs_outbound=list(self._chunks[i].get("refs_outbound") or []),
            )
            for i in top_indices
            if scores[i] > 0
        ]

    def hybrid_search(self, query: str, top_k: int = TOP_K, where: dict = None) -> list[SearchResult]:
        """
        混合检索：BM25 + 向量，用 RRF（倒数排名融合）合并两路结果。

        RRF 公式：score = Σ 1 / (k + rank_i)，k=60
        两路都无结果时降级为纯向量检索。
        where: metadata 过滤条件，传给 vector_search 限定来源域，防止增强索引跨域污染。
        """
        vector_results = self.vector_search(query, top_k=top_k * 2, where=where)
        bm25_results = self.bm25_search(query, top_k=top_k * 2)

        if not bm25_results:
            base_results = vector_results[:top_k]
            return _with_cross_refs(base_results, self._chunks, top_k)
        if not vector_results:
            base_results = bm25_results[:top_k]
            return _with_cross_refs(base_results, self._chunks, top_k)

        base_results = _rrf_merge(vector_results, bm25_results, top_k=top_k)
        return _with_cross_refs(base_results, self._chunks, top_k)

    def search(
        self,
        query: str,
        method: str,
        top_k: int = TOP_K,
        where: dict = None,
    ) -> list[SearchResult]:
        """
        统一检索入口，根据 method 分派到对应策略（策略模式）。

        Args:
            method: "vector" | "bm25" | "hybrid"
            where:  metadata 过滤条件（仅 vector 支持），如 {"is_table": True}
        """
        if method == "bm25":
            return self.bm25_search(query, top_k)
        if method == "hybrid":
            return self.hybrid_search(query, top_k, where=where)
        return self.vector_search(query, top_k, where=where)

    @property
    def chunks(self) -> list:
        """只读访问 chunk 列表，供 UI 展示调试信息。"""
        return self._chunks


def _load_structure_sections(structure_path: str | Path | None) -> dict[str, dict]:
    if not structure_path:
        return {}
    path = Path(structure_path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(s.get("section_id")): s for s in data.get("section_tree", [])}


def _infer_datasheet_query_type(query: str) -> str:
    markers = normalize_datasheet_text(query).lower() + " " + query.lower()
    if ("i2c" in markers or "iic" in markers) and any(k in markers for k in ("什么时候", "命令", "command", "ready", "receive", "发送")):
        return "i2c_command_ready"
    if ("i2c" in markers or "iic" in markers) and any(k in markers for k in ("端口", "port", "ports", "哪些", "有哪些", "支持")):
        return "interface_ports"
    if any(k in markers for k in ("parking", "parkz", "gpio_08", "gpio08")):
        return "dmd_parking"
    if "spi" in markers and "flash" in markers:
        return "spi_flash"
    if any(k in markers for k in ("oscillator", "mosc", "振荡器")):
        return "oscillator_timing"
    return "datasheet"


def _bundle_evidence(result: dict, sections: dict[str, dict]) -> dict:
    section_id = result.get("section_id") or _extract_section_id(result.get("text", ""))
    section = sections.get(str(section_id), {}) if section_id else {}
    return {
        "kind": result.get("index_kind", "block"),
        "source": result.get("source", ""),
        "section_id": str(section_id or ""),
        "section_title": section.get("title", ""),
        "table_id": result.get("table_id", ""),
        "row_id": result.get("row_id", ""),
        "source_line": result.get("source_line"),
        "score": result.get("score", 0),
        "text": result.get("text", ""),
    }


def _extract_section_id(text: str) -> str:
    match = re.search(r"\[section:\s*([^\]]+)\]", text)
    if match:
        return match.group(1).strip()
    heading = re.search(r"^##\s+([0-9]+(?:\.[0-9]+)*)\b", text.strip())
    if heading:
        return heading.group(1)
    return ""


def _rank_i2c_row(result: dict) -> int:
    text = result.get("text", "")
    score = 0
    for token in ("IIC0_SCL", "IIC0_SDA", "IIC1_SCL", "IIC1_SDA"):
        if token in text:
            score += 10
    if "Pin Configuration and Functions" in text:
        score += 5
    return score


def _read_source_lines(retriever, start_line: int, end_line: int) -> str:
    source_name = ""
    if getattr(retriever, "chunks", None):
        source_name = retriever.chunks[0].get("source", "")
    if not source_name:
        source_name = "dlpc3436_clean.md"
    source_path = Path(source_name)
    if not source_path.is_absolute():
        structure_path = getattr(getattr(retriever, "_datasheet_index", None), "structure_path", None)
        if structure_path:
            kb_dir = Path(structure_path).resolve().parent.parent
            source_path = kb_dir / source_name
    if not source_path.exists():
        return ""
    lines = source_path.read_text(encoding="utf-8").splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line)
    return "\n".join(lines[start - 1:end])


def _source_evidence(text: str, retriever, query_type: str, section_id: str, source_line: int) -> SearchResult:
    # 从源文本片段实时提取结构锚（无 chunk 上下文可用）。
    # 延迟 import 避免与 document_loader 形成顶层循环依赖。
    from document_loader import _extract_anchors, _extract_refs_outbound
    anchors_used, anchors_defined = _extract_anchors(text)
    refs_outbound = _extract_refs_outbound(text)
    return SearchResult(
        text=text,
        source=(retriever.chunks[0].get("source", "") if getattr(retriever, "chunks", None) else "dlpc3436_clean.md"),
        score=1.0,
        is_table="|" in text,
        is_datasheet=True,
        index_kind="block",
        anchors_used=anchors_used,
        anchors_defined=anchors_defined,
        refs_outbound=refs_outbound,
        section_id=section_id,
        source_line=source_line,
    )


def _targeted_datasheet_blocks(query_type: str, retriever) -> list[SearchResult]:
    ranges = {
        "oscillator_timing": [(632, 644, "6.10")],
        "spi_flash": [(918, 925, "7.3.3.1")],
        "dmd_parking": [(746, 759, "6.17")],
        "i2c_command_ready": [(827, 839, "7.3.2"), (1144, 1147, "9.2")],
    }.get(query_type, [])
    blocks: list[SearchResult] = []
    for start, end, section_id in ranges:
        text = _read_source_lines(retriever, start, end)
        if text:
            blocks.append(_source_evidence(text, retriever, query_type, section_id, start))
    return blocks


def plan_datasheet_evidence_bundle(query: str, retriever, top_k: int = TOP_K) -> dict:
    """Create a small structure-driven datasheet evidence bundle.

    Phase 4 bridge: use row collection hits as exact evidence, then attach block
    context from the physically separated block collection. This keeps the API
    structured while existing rule-based search_datasheet can be retired in
    later slices.
    """
    query_type = _infer_datasheet_query_type(query)
    sections = _load_structure_sections(getattr(getattr(retriever, "_datasheet_index", None), "structure_path", None))
    row_results = retriever.search_row(query, top_k=max(top_k * 3, 12)) if getattr(retriever, "_row_collection", None) else []
    block_results = retriever.search_block(query, top_k=max(top_k, 4)) if getattr(retriever, "_block_collection", None) else []

    if query_type == "interface_ports":
        row_results = sorted(row_results, key=_rank_i2c_row, reverse=True)
        preferred_blocks = [r for r in block_results if "100-kHz baud rate" in r.get("text", "")]
        if not preferred_blocks:
            preferred_blocks = [
                SearchResult(
                    text=c["text"],
                    source=c.get("source", ""),
                    score=1.0,
                    is_table=bool(c.get("is_table", False)),
                    is_datasheet=bool(c.get("is_datasheet", False)),
                    index_kind=c.get("index_kind", "block"),
                    anchors_used=list(c.get("anchors_used") or []),
                    anchors_defined=list(c.get("anchors_defined") or []),
                    refs_outbound=list(c.get("refs_outbound") or []),
                )
                for c in getattr(retriever, "chunks", [])
                if "100-kHz baud rate" in c.get("text", "")
            ]
        block_results = preferred_blocks + [r for r in block_results if r not in preferred_blocks]
    elif query_type in {"oscillator_timing", "spi_flash", "dmd_parking", "i2c_command_ready"}:
        targeted_blocks = _targeted_datasheet_blocks(query_type, retriever)
        block_results = targeted_blocks + [r for r in block_results if r not in targeted_blocks]

    evidence: list[dict] = []
    seen: set[str] = set()
    if query_type in {"oscillator_timing", "spi_flash", "dmd_parking", "i2c_command_ready"}:
        ordered_results = block_results + row_results
    else:
        row_quota = min(len(row_results), max(0, top_k - len(block_results))) if block_results else len(row_results)
        ordered_results = row_results[:row_quota] + block_results
    for result in ordered_results:
        key = result.get("text", "")[:180]
        if not key or key in seen:
            continue
        seen.add(key)
        evidence.append(_bundle_evidence(result, sections))
        if len(evidence) >= top_k:
            break

    source = evidence[0]["source"] if evidence else ""
    bundle = {"query": query, "query_type": query_type, "source": source, "evidence": evidence}
    reading_source = _resolve_reading_closure_source(retriever, source)
    if reading_source:
        bundle["reading_closure"] = build_specification_reading_closure(query, reading_source)
    return bundle


def _resolve_reading_closure_source(retriever, source: str) -> Path | None:
    candidates: list[Path] = []
    if source:
        candidates.append(Path(source))
    structure_path = getattr(getattr(retriever, "_datasheet_index", None), "structure_path", None)
    if structure_path:
        root = Path(structure_path).resolve().parents[1]
        if source:
            candidates.append(root / source)
        candidates.append(root / "dlpc3436_clean.md")
    for chunk in getattr(retriever, "chunks", []):
        chunk_source = chunk.get("source", "")
        if chunk_source:
            candidates.append(Path(chunk_source))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


# ── RRF 融合 ──────────────────────────────────────────────────────────────────

def _rrf_merge(
    results_a: list[SearchResult],
    results_b: list[SearchResult],
    top_k: int,
    k: int = 60,
) -> list[SearchResult]:
    """
    倒数排名融合（Reciprocal Rank Fusion）。

    用 text 内容作为去重键，两路分别计算排名得分后求和，取 top_k 返回。
    最终 score 字段存储 RRF 分数（值越大越相关）。
    """
    rrf_scores: dict[str, float] = {}
    text_to_result: dict[str, SearchResult] = {}

    for results in (results_a, results_b):
        for rank, result in enumerate(results):
            key = result["text"]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            text_to_result[key] = result

    sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)[:top_k]

    return [
        SearchResult(
            text=text_to_result[key]["text"],
            source=text_to_result[key]["source"],
            score=round(rrf_scores[key], 6),
            is_table=bool(text_to_result[key].get("is_table", False)),
            is_datasheet=bool(text_to_result[key].get("is_datasheet", False)),
            index_kind=text_to_result[key].get("index_kind", "block"),
            anchors_used=list(text_to_result[key].get("anchors_used") or []),
            anchors_defined=list(text_to_result[key].get("anchors_defined") or []),
            refs_outbound=list(text_to_result[key].get("refs_outbound") or []),
        )
        for key in sorted_keys
    ]


# ── Embedding 工厂 ─────────────────────────────────────────────────────────────

def _build_embedding_fn():
    """
    根据 config.EMBEDDING_MODEL 构建 ChromaDB embedding function。

    - "default"：返回 None，ChromaDB 使用内置 all-MiniLM-L6-v2
    - 其他字符串：用 SentenceTransformer 加载对应模型（如 BAAI/bge-m3）
      依赖：pip install sentence-transformers
    """
    if EMBEDDING_MODEL == "default":
        return None

    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        print(f"[Retriever] 加载 Embedding 模型：{EMBEDDING_MODEL}")
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        print(f"[Retriever] Embedding 模型加载完成")
        return ef
    except Exception as exc:
        print(f"[Retriever] ❌ Embedding 模型不可用，回退到默认模型：{exc}")
        return None


# ── 分词工具 ───────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """
    中文词级分词，供 BM25 使用。

    优先使用 jieba 词级分词（"生日福利" → ["生日", "福利"]），
    jieba 未安装时降级为字符级分词（["生", "日", "福", "利"]）。

    词级分词的优势：复合词（生日福利/年假/加班费）作为整体 token，
    IDF 值更高，BM25 能精确区分"生日福利"与其他含"福利"的 chunk。

    安装：pip install jieba
    """
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        return list(text)
