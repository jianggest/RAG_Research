"""Generate a deterministic structure digest for DLPC datasheet markdown.

This is Phase 1 of tasks/datasheet_rag_plan.md. It is intentionally rule-based:
LLM entity merge can be added later, but online query path must not depend on LLM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "knowledge_base" / "dlpc3436_clean.md"
DEFAULT_OUTPUT = ROOT / "knowledge_base" / ".structure" / "dlpc3436.structure.json"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SECTION_TITLE_RE = re.compile(r"^(?P<section>\d+(?:\.\d+)*)\s+(?P<title>.+)$")
TABLE_TITLE_RE = re.compile(r"^Table\s+(?P<table_id>\d+(?:-\d+)*)\.\s*(?P<title>.+)$", re.IGNORECASE)
SYMBOL_RE = re.compile(r"(?:\bt\s+jp\b|\bt\s+fast\s+park\b|\bt\s+park\b|\b[ftv]\s*[A-Za-z]?(?:\([HL]\))?\b|\bVCC_[A-Z0-9]+\b|\bPLL_REFCLK_[IO]\b|\bGPIO_\d+\b|\bHOST_IRQ\b|\bIIC\d_[A-Z]+\b|\bSPI\d_[A-Z0-9]+\b)", re.IGNORECASE)
UNIT_RE = re.compile(r"\b(?:MHz|kHz|ns|µs|ms|ppm|PPM|V|mA|%|Mb)\b")
ENTITY_RE = re.compile(r"\b(?:DLPC\d+|DLPA\d+|DMD|PMIC|MOSC|VCC_[A-Z0-9]+|PLL_REFCLK_[IO]|GPIO_\d+|HOST_IRQ|IIC\d_[A-Z]+|SPI\d_[A-Z0-9]+|W25Q\w+)\b", re.IGNORECASE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean_heading_title(raw: str) -> str:
    title = re.sub(r"\s+", " ", raw).strip()
    title = re.sub(r"\s+\(continued\)$", "", title, flags=re.IGNORECASE)
    return title


def _parse_heading(line: str):
    match = HEADING_RE.match(line)
    if not match:
        return None
    level = len(match.group(1))
    title = _clean_heading_title(match.group(2))
    section_id = None
    section_match = SECTION_TITLE_RE.match(title)
    if section_match:
        section_id = section_match.group("section")
        title = section_match.group("title").strip()
    table_id = None
    table_match = TABLE_TITLE_RE.match(title)
    if table_match:
        table_id = table_match.group("table_id")
    return {"level": level, "section_id": section_id, "table_id": table_id, "title": title}


def _split_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells)


def _norm_symbol(symbol: str) -> str:
    return re.sub(r"\s+", " ", symbol.strip())


def _detect_symbols(text: str) -> list[str]:
    seen = []
    for match in SYMBOL_RE.findall(text):
        token = _norm_symbol(match)
        if token and token not in seen:
            seen.append(token)
    return seen


def _detect_units(text: str) -> list[str]:
    seen = []
    for match in UNIT_RE.findall(text):
        token = match.strip()
        if token and token not in seen:
            seen.append(token)
    return seen


def _detect_entities(text: str) -> list[str]:
    seen = []
    for match in ENTITY_RE.findall(text):
        token = match.upper() if match.lower().startswith(("dlpc", "dlpa", "w25q")) else match
        if token and token not in seen:
            seen.append(token)
    return seen


def _parent_section(section_id: str | None) -> str | None:
    if not section_id or "." not in section_id:
        return None
    return section_id.rsplit(".", 1)[0]


def build_structure_digest(source_path: Path = DEFAULT_SOURCE) -> dict:
    lines = source_path.read_text(encoding="utf-8").splitlines()

    headings = []
    for idx, line in enumerate(lines, start=1):
        parsed = _parse_heading(line)
        if parsed:
            headings.append({**parsed, "line": idx})

    section_tree = []
    section_headings = [h for h in headings if h.get("section_id")]
    for i, h in enumerate(section_headings):
        end_line = (section_headings[i + 1]["line"] - 1) if i + 1 < len(section_headings) else len(lines)
        section_tree.append({
            "section_id": h["section_id"],
            "title": h["title"],
            "level": h["level"],
            "start_line": h["line"],
            "end_line": end_line,
            "parent": _parent_section(h["section_id"]),
        })

    def section_for_line(line_no: int) -> dict | None:
        current = None
        for section in section_tree:
            if section["start_line"] <= line_no <= section["end_line"]:
                if current is None or len(section["section_id"].split(".")) >= len(current["section_id"].split(".")):
                    current = section
        return current

    table_catalog = []
    row_index = []
    note_anchors = []
    table_counter = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|"):
            start = i + 1
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            end = i
            section = section_for_line(start) or {}
            prev_heading = None
            for h in reversed(headings):
                if h["line"] < start:
                    prev_heading = h
                    break
            table_counter += 1
            table_id = (prev_heading or {}).get("table_id") or f"table_{table_counter:03d}"
            table_title = (prev_heading or {}).get("title") or (section or {}).get("title") or "Untitled table"
            parsed_rows = [_split_table_cells(row) for row in table_lines]
            data_rows = [r for r in parsed_rows if not _is_separator_row(r)]
            columns = data_rows[0] if data_rows else []
            row_count = max(0, len(data_rows) - 1)
            text_blob = "\n".join(table_lines)
            table_catalog.append({
                "table_id": table_id,
                "section_id": section.get("section_id"),
                "table_title": table_title,
                "start_line": start,
                "end_line": end,
                "columns": columns,
                "row_count": row_count,
                "detected_units": _detect_units(text_blob),
                "detected_symbols": _detect_symbols(text_blob),
                "row_entities": sorted({e for row in data_rows for e in _detect_entities(" | ".join(row))}),
            })
            for offset, raw_row in enumerate(table_lines, start=start):
                cells = _split_table_cells(raw_row)
                if _is_separator_row(cells) or not any(cells):
                    continue
                original = " | ".join(cells)
                row_index.append({
                    "row_id": f"{table_id}_r{offset - start + 1:03d}",
                    "table_id": table_id,
                    "section_id": section.get("section_id"),
                    "original_text": original,
                    "normalized_text": re.sub(r"\s+", " ", original.lower()),
                    "entities": _detect_entities(original),
                    "symbols": _detect_symbols(original),
                    "detected_symbols": _detect_symbols(original),
                    "units": _detect_units(original),
                    "source_line": offset,
                })
            continue

        stripped = line.strip()
        if stripped.startswith("- (") or stripped.lower().startswith("note"):
            section = section_for_line(i + 1) or {}
            note_anchors.append({
                "note_id": f"note_{len(note_anchors)+1:03d}",
                "section_id": section.get("section_id"),
                "line": i + 1,
                "text": stripped,
                "entities": _detect_entities(stripped),
                "symbols": _detect_symbols(stripped),
                "units": _detect_units(stripped),
            })
        i += 1

    entity_mentions: dict[str, list[dict]] = defaultdict(list)
    for section in section_tree:
        for entity in _detect_entities(section["title"]):
            entity_mentions[entity].append({"kind": "section", "line": section["start_line"], "section_id": section["section_id"]})
    for table in table_catalog:
        for entity in table["row_entities"]:
            entity_mentions[entity].append({"kind": "table", "line": table["start_line"], "section_id": table["section_id"], "table_id": table["table_id"]})
    for row in row_index:
        for entity in row["entities"]:
            entity_mentions[entity].append({"kind": "row", "line": row["source_line"], "section_id": row["section_id"], "table_id": row["table_id"]})
    for note in note_anchors:
        for entity in note["entities"]:
            entity_mentions[entity].append({"kind": "note", "line": note["line"], "section_id": note["section_id"]})

    entity_inventory = []
    for idx, (entity, mentions) in enumerate(sorted(entity_mentions.items()), start=1):
        entity_type = "device_model" if entity.startswith(("DLPC", "DLPA")) else "signal"
        if entity.startswith("VCC_"):
            entity_type = "power_rail"
        elif entity.startswith(("SPI", "IIC")):
            entity_type = "interface"
        elif entity.startswith("W25Q"):
            entity_type = "device_model"
        entity_inventory.append({
            "entity_id": f"ent_{idx:04d}",
            "canonical_name": entity,
            "entity_type": entity_type,
            "aliases": [entity.replace("_", " ")] if "_" in entity else [],
            "mentions": mentions[:20],
            "source_mappings": sorted({m.get("section_id") for m in mentions if m.get("section_id")}),
        })

    alias_graph = {
        "I2C": ["I 2 C", "I²C", "IIC"],
        "f_clk": ["f clk", "fclk", "f_clk"],
        "PLL_REFCLK_I": ["PLL REFCLK I", "PLL_REFCLK_I"],
        "PLL_REFCLK_O": ["PLL REFCLK O", "PLL_REFCLK_O"],
        "±200 ppm": ["±200 PPM", "+/-200 ppm"],
    }

    return {
        "schema_version": "0.1",
        "source": source_path.name,
        "source_md_sha256": _sha256(source_path),
        "section_tree": section_tree,
        "table_catalog": table_catalog,
        "row_index": row_index,
        "note_anchors": note_anchors,
        "entity_inventory": entity_inventory,
        "alias_graph": alias_graph,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    digest = build_structure_digest(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"sections={len(digest['section_tree'])} tables={len(digest['table_catalog'])} rows={len(digest['row_index'])} entities={len(digest['entity_inventory'])} notes={len(digest['note_anchors'])}")


if __name__ == "__main__":
    main()
