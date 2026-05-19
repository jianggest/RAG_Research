"""
Document catalog and query decomposition helpers.

The catalog maps loaded document sources to high-confidence names derived from
the document itself. Query decomposition uses that catalog to treat document
mentions as source filters, leaving the remaining text as the semantic query.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import TypedDict


CATALOG_FILENAME = "document_catalog.json"


class CatalogEntry(TypedDict, total=False):
    source: str
    canonical: str
    aliases: list[str]
    title: str
    content_hash: str


class DocumentScope(TypedDict):
    source: str
    canonical: str
    matched_text: str


class DecomposedQuery(TypedDict):
    original_query: str
    semantic_query: str
    document_scopes: list[DocumentScope]
    ambiguous_matches: list[dict]


_DESCRIPTOR_WORDS = {
    "clean",
    "datasheet",
    "data",
    "sheet",
    "spec",
    "specification",
    "document",
    "manual",
    "规格书",
    "说明书",
    "数据手册",
    "产品手册",
    "用户手册",
    "手册",
}

_LEADING_SCOPE_MARKERS = ("的", "在", "于", "：", ":", "-", "—")
_TRAILING_SCOPE_MARKERS = ("的", "在", "于", "：", ":", "-", "—")


def catalog_path(kb_dir: str | Path) -> Path:
    return Path(kb_dir) / CATALOG_FILENAME


def write_document_catalog(kb_dir: str | Path, documents: list[dict]) -> Path:
    """Write `{kb_dir}/document_catalog.json` for the documents just loaded."""
    path = catalog_path(kb_dir)
    entries = build_document_catalog(documents)
    rendered = json.dumps(entries, ensure_ascii=False, indent=2)
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        print(f"[DocumentCatalog] {path.name} 无变化: {len(entries)} documents")
        return path
    path.write_text(rendered, encoding="utf-8")
    print(f"[DocumentCatalog] 写入 {path.name}: {len(entries)} documents")
    return path


def load_document_catalog(kb_dir: str | Path) -> list[CatalogEntry]:
    path = catalog_path(kb_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("documents", [])
    if not isinstance(data, list):
        return []
    return [
        entry for entry in data
        if isinstance(entry, dict) and entry.get("source") and entry.get("aliases")
    ]


def build_document_catalog(documents: list[dict]) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    seen_sources: set[str] = set()
    for doc in documents:
        source = str(doc.get("source", "")).strip()
        if not source or source in seen_sources:
            continue
        seen_sources.add(source)
        content = str(doc.get("content", "") or "")
        title = _extract_title(content)
        canonical = _derive_canonical(source, title)
        aliases = _derive_aliases(source, title, canonical)
        if not aliases:
            continue
        entries.append(CatalogEntry(
            source=source,
            canonical=canonical,
            aliases=aliases,
            title=title,
            content_hash=_content_hash(content),
        ))
    return sorted(entries, key=lambda e: e["source"].lower())


def decompose_query_with_catalog(
    query: str,
    *,
    kb_dir: str | Path | None = None,
    catalog: list[CatalogEntry] | None = None,
    log: bool = True,
) -> DecomposedQuery:
    entries = catalog if catalog is not None else (load_document_catalog(kb_dir) if kb_dir else [])
    matches, ambiguous = _find_document_matches(query, entries)
    semantic_query = _remove_document_mentions(query, matches)
    result = DecomposedQuery(
        original_query=query,
        semantic_query=semantic_query or query,
        document_scopes=[
            DocumentScope(
                source=m["entry"]["source"],
                canonical=m["entry"].get("canonical") or m["entry"]["source"],
                matched_text=m["matched_text"],
            )
            for m in matches
        ],
        ambiguous_matches=ambiguous,
    )
    if log:
        log_decomposition(result)
    return result


def log_decomposition(result: DecomposedQuery) -> None:
    print(f"[QueryDecomposer] original={result['original_query']!r}")
    scopes = result.get("document_scopes", [])
    if scopes:
        for scope in scopes:
            print(
                "[QueryDecomposer] document_scope "
                f"source={scope['source']} canonical={scope['canonical']} "
                f"matched={scope['matched_text']!r}"
            )
    elif result.get("ambiguous_matches"):
        print(f"[QueryDecomposer] document_scope=<ambiguous> candidates={result['ambiguous_matches']}")
    else:
        print("[QueryDecomposer] document_scope=<none>")
    print(f"[QueryDecomposer] semantic_query={result['semantic_query']!r}")


def _extract_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith("<!--"):
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if stripped:
            return stripped[:160]
    return ""


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _derive_canonical(source: str, title: str) -> str:
    stem = _source_stem(source)
    source_name = _format_canonical(
        _remove_descriptors(_space_separators(_remove_numeric_parenthetical(stem)))
    )
    if source_name:
        return source_name
    title_name = _format_canonical(
        _remove_descriptors(_space_separators(_remove_numeric_parenthetical(title or "")))
    )
    return title_name or stem


def _derive_aliases(source: str, title: str, canonical: str) -> list[str]:
    seeds = {
        _source_stem(source),
        _remove_numeric_parenthetical(_source_stem(source)),
        canonical,
    }
    if title:
        seeds.add(title.strip())
        seeds.add(_remove_numeric_parenthetical(title.strip()))

    aliases: list[str] = []
    seen: set[str] = set()
    for seed in seeds:
        for variant in _alias_variants(seed):
            cleaned = variant.strip()
            if not _is_high_confidence_alias(cleaned):
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(cleaned)
    return sorted(aliases, key=lambda item: (-len(item), item.casefold()))


def _source_stem(source: str) -> str:
    stem = Path(source).stem
    if stem.lower().endswith("_clean"):
        return stem[:-len("_clean")]
    return stem


def _alias_variants(seed: str) -> set[str]:
    variants: set[str] = set()
    spaced = _space_separators(seed)
    no_copy = _remove_numeric_parenthetical(spaced)
    for item in {seed, spaced, no_copy, _remove_descriptors(spaced), _remove_descriptors(no_copy)}:
        item = item.strip()
        if not item:
            continue
        variants.add(item)
        variants.add(_compact(item))
    return {v for v in variants if v}


def _space_separators(text: str) -> str:
    translated = []
    for ch in text:
        translated.append(" " if ch in "_-" else ch)
    return " ".join("".join(translated).split())


def _format_canonical(text: str) -> str:
    text = " ".join(text.split()).strip()
    if not text:
        return ""
    if " " not in text and text.replace(".", "").replace("(", "").replace(")", "").isalnum():
        return text.upper()
    return " ".join(part.upper() if any(ch.isdigit() for ch in part) else part for part in text.split())


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch not in " _-\t\r\n")


def _remove_numeric_parenthetical(text: str) -> str:
    result = text
    while True:
        start = result.find("(")
        if start < 0:
            return " ".join(result.split())
        end = result.find(")", start + 1)
        if end < 0:
            return " ".join(result.split())
        inside = result[start + 1:end].strip()
        if inside.isdigit():
            result = result[:start] + result[end + 1:]
            continue
        start = end + 1
        return " ".join(result.split())


def _remove_descriptors(text: str) -> str:
    tokens = text.split()
    kept: list[str] = []
    skipping_descriptor_tail = False
    for token in tokens:
        normalized = token.strip("()[]{}.,;:").casefold()
        if normalized in _DESCRIPTOR_WORDS:
            skipping_descriptor_tail = True
            continue
        if skipping_descriptor_tail and normalized.isdigit():
            continue
        kept.append(token)
    return " ".join(kept).strip()


def _is_high_confidence_alias(alias: str) -> bool:
    if len(alias) < 3:
        return False
    lowered = alias.casefold()
    if lowered in _DESCRIPTOR_WORDS:
        return False
    if any(ch.isdigit() for ch in alias):
        return True
    if len(alias) >= 6:
        return True
    if any("\u4e00" <= ch <= "\u9fff" for ch in alias) and len(alias) >= 4:
        return True
    return False


def _find_document_matches(query: str, entries: list[CatalogEntry]) -> tuple[list[dict], list[dict]]:
    alias_rows: list[tuple[str, CatalogEntry]] = []
    for entry in entries:
        for alias in entry.get("aliases", []):
            if alias:
                alias_rows.append((alias, entry))
    alias_rows.sort(key=lambda row: len(row[0]), reverse=True)

    candidates: list[dict] = []
    ambiguous: list[dict] = []
    query_fold = query.casefold()
    for alias, entry in alias_rows:
        alias_fold = alias.casefold()
        start = 0
        while True:
            idx = query_fold.find(alias_fold, start)
            if idx < 0:
                break
            end = idx + len(alias)
            start = idx + 1
            if not _has_ascii_boundaries(query, idx, end):
                continue
            candidates.append({
                "start": idx,
                "end": end,
                "matched_text": query[idx:end],
                "entry": entry,
            })

    selected: list[dict] = []
    occupied: list[tuple[int, int]] = []
    for candidate in sorted(candidates, key=lambda m: (-(m["end"] - m["start"]), m["start"])):
        if any(not (candidate["end"] <= s or candidate["start"] >= e) for s, e in occupied):
            continue
        same_span = [
            m for m in candidates
            if m["start"] == candidate["start"] and m["end"] == candidate["end"]
        ]
        sources = sorted({m["entry"]["source"] for m in same_span})
        if len(sources) > 1:
            ambiguous.append({
                "matched_text": candidate["matched_text"],
                "sources": sources,
            })
            occupied.append((candidate["start"], candidate["end"]))
            continue
        selected.append(candidate)
        occupied.append((candidate["start"], candidate["end"]))

    selected.sort(key=lambda m: m["start"])
    return selected, ambiguous


def _has_ascii_boundaries(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not _is_ascii_word(before) and not _is_ascii_word(after)


def _is_ascii_word(ch: str) -> bool:
    return bool(ch) and (ch.isascii() and (ch.isalnum() or ch == "_"))


def _remove_document_mentions(query: str, matches: list[dict]) -> str:
    if not matches:
        return " ".join(query.split()).strip()
    ranges = [_expand_scope_span(query, m["start"], m["end"]) for m in matches]
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    parts: list[str] = []
    cursor = 0
    for start, end in merged:
        parts.append(query[cursor:start])
        cursor = end
    parts.append(query[cursor:])
    return _clean_remaining_query("".join(parts))


def _expand_scope_span(text: str, start: int, end: int) -> tuple[int, int]:
    new_start = start
    new_end = end

    before = text[:start]
    stripped_before = before.rstrip()
    if stripped_before.endswith("在"):
        new_start = len(stripped_before) - 1
    else:
        lowered = stripped_before.casefold()
        for marker in (" in", " of", " for"):
            if lowered.endswith(marker):
                new_start = len(stripped_before) - len(marker)
                break

    after_index = end
    while after_index < len(text) and text[after_index].isspace():
        after_index += 1
    if after_index < len(text) and text[after_index] == "的":
        new_end = after_index + 1
    elif after_index < len(text) and text[after_index] in ("中", "里"):
        marker_end = after_index + 1
        following = text[marker_end] if marker_end < len(text) else ""
        if not following or following.isspace() or following in "，,。.;；:：?？!！":
            new_end = marker_end
    return new_start, new_end


def _clean_remaining_query(text: str) -> str:
    cleaned = " ".join(text.split()).strip()
    changed = True
    while changed and cleaned:
        changed = False
        for marker in _LEADING_SCOPE_MARKERS:
            if cleaned.startswith(marker):
                cleaned = cleaned[len(marker):].strip()
                changed = True
        for marker in _TRAILING_SCOPE_MARKERS:
            if cleaned.endswith(marker):
                cleaned = cleaned[:-len(marker)].strip()
                changed = True
    return cleaned
