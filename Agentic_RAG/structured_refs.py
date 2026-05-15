"""
Structured reference helpers for clickable datasheet citations.

The generator appends references such as:
    结构化引用：
    - [Section: 7.5]
    - [Section: 6.10 System Oscillator Timing Requirements; line: 632]

This module keeps parsing and source-section lookup independent from Streamlit,
so the UI can render those references as buttons/dialogs.
"""

from __future__ import annotations

import re
from html import escape
from dataclasses import dataclass
from pathlib import Path


_STRUCTURED_REF_BLOCK_RE = re.compile(
    r"(?P<body>.*?)(?:\n\s*)?(?:#{1,6}\s*)?结构化引用[:：]\s*"
    r"(?P<refs>(?:\n\s*(?:[-*]\s*)?\[[^\]]+\]\s*)+)\s*$",
    re.DOTALL,
)
_REFERENCE_ITEM_RE = re.compile(r"\[([^\]]+)\]")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\d+(?:\.\d+)*)\b(.*)$")
_SECTION_TAG_RE = re.compile(r"\[section:\s*([^\]]+)\]", re.IGNORECASE)


@dataclass
class StructuredReference:
    """A parsed citation like ``[Section: 7.5; line: 1204]``."""

    raw: str
    fields: dict[str, str]

    @property
    def section(self) -> str:
        return self.fields.get("section", "")

    @property
    def source(self) -> str:
        return self.fields.get("source", "")

    @property
    def line(self) -> int | None:
        value = self.fields.get("line", "")
        match = re.search(r"\d+", value)
        return int(match.group()) if match else None


@dataclass
class ReferenceDetail:
    """Resolved source content for one structured reference."""

    title: str
    content: str
    source: str = ""
    found: bool = True
    message: str = ""


def split_structured_references(answer: str) -> tuple[str, list[StructuredReference]]:
    """
    Split a trailing ``结构化引用`` block from an answer.

    Returns the display body and parsed references. If no trailing structured
    reference block exists, the original answer is returned unchanged.
    """
    match = _STRUCTURED_REF_BLOCK_RE.match(answer.strip())
    if not match:
        return answer.strip(), []
    body = match.group("body").strip()
    refs = parse_structured_references(match.group("refs"))
    return body, refs


def parse_structured_references(text: str) -> list[StructuredReference]:
    """Parse all bracketed structured references from text."""
    refs: list[StructuredReference] = []
    for match in _REFERENCE_ITEM_RE.finditer(text):
        inner = match.group(1).strip()
        fields: dict[str, str] = {}
        for part in inner.split(";"):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            normalized_key = key.strip().lower()
            normalized_value = value.strip()
            if normalized_key and normalized_value:
                fields[normalized_key] = normalized_value
        if fields:
            refs.append(StructuredReference(raw=f"[{inner}]", fields=fields))
    return refs


def format_reference_label(ref: StructuredReference) -> str:
    """Return a compact UI label for a structured reference button."""
    section = ref.section
    if section:
        section_no = extract_section_number(section)
        if section_no and section.strip() == section_no:
            label = f"Section: {section_no}"
        else:
            label = f"Section: {section}"
    elif ref.line:
        label = f"line: {ref.line}"
    else:
        label = ref.raw.strip("[]")

    extras = []
    if ref.fields.get("table"):
        extras.append(f"Table: {ref.fields['table']}")
    if ref.fields.get("row"):
        extras.append(f"Row: {ref.fields['row']}")
    if ref.line and "line" not in label:
        extras.append(f"line: {ref.line}")

    suffix = " | " + " | ".join(extras) if extras else ""
    return (label + suffix)[:120]


def extract_section_number(value: str) -> str:
    """Extract a numeric section id from values like ``7.5`` or ``section_6_10``."""
    value = (value or "").strip()
    if not value:
        return ""

    internal = re.match(r"^section[_\s-]*(\d+(?:[_.]\d+)*)$", value, re.IGNORECASE)
    if internal:
        return internal.group(1).replace("_", ".")

    match = re.search(r"\b(\d+(?:\.\d+)*)\b", value)
    return match.group(1) if match else ""


def extract_section_from_markdown(path: Path, section_no: str) -> str:
    """Return a markdown section, including child subsections, from a source file."""
    if not path.exists() or not path.is_file() or not section_no:
        return ""

    lines = path.read_text(encoding="utf-8").splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line.strip())
        if match and match.group(2) == section_no:
            start_idx = idx
            break
    if start_idx is None:
        return ""

    end_idx = len(lines)
    child_prefix = f"{section_no}."
    for idx in range(start_idx + 1, len(lines)):
        match = _HEADING_RE.match(lines[idx].strip())
        if not match:
            continue
        next_section = match.group(2)
        if next_section != section_no and not next_section.startswith(child_prefix):
            end_idx = idx
            break

    return "\n".join(lines[start_idx:end_idx]).strip()


def resolve_structured_reference_detail(
    ref: StructuredReference,
    executed_steps: list,
    kb_dir: Path,
) -> ReferenceDetail:
    """Resolve a structured reference to source markdown content."""
    section_no = extract_section_number(ref.section)
    source_names = _candidate_source_names(ref, executed_steps)
    candidate_paths = _candidate_markdown_paths(kb_dir, source_names)

    if section_no:
        for path in candidate_paths:
            content = extract_section_from_markdown(path, section_no)
            if content:
                title = _first_heading_title(content) or f"Section {section_no}"
                return ReferenceDetail(title=title, content=content, source=path.name)

    if ref.line:
        for path in candidate_paths:
            content = _extract_line_context(path, ref.line)
            if content:
                return ReferenceDetail(
                    title=f"{path.name} line {ref.line}",
                    content=content,
                    source=path.name,
                )

    matched_result = _find_matching_result(ref, executed_steps)
    if matched_result and matched_result.get("text"):
        source = matched_result.get("source", "")
        title = format_reference_label(ref)
        return ReferenceDetail(title=title, content=matched_result["text"], source=source)

    message = f"未在当前知识库中找到 {format_reference_label(ref)} 对应的原文。"
    return ReferenceDetail(
        title=format_reference_label(ref),
        content="",
        source="",
        found=False,
        message=message,
    )


def markdown_tables_to_html(markdown: str) -> str:
    """Convert pipe markdown tables to HTML tables for overflow-safe display."""
    lines = markdown.splitlines()
    rendered: list[str] = []
    i = 0
    while i < len(lines):
        if _is_table_start(lines, i):
            table_lines = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and _is_table_row(lines[i]):
                table_lines.append(lines[i])
                i += 1
            rendered.append(_render_markdown_table(table_lines))
            continue

        rendered.append(_render_non_table_line(lines[i]))
        i += 1

    return "\n".join(rendered)


def _first_heading_title(markdown: str) -> str:
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            return line.lstrip("#").strip()
    return ""


def _is_table_start(lines: list[str], idx: int) -> bool:
    return (
        idx + 1 < len(lines)
        and _is_table_row(lines[idx])
        and bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[idx + 1]))
    )


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _render_markdown_table(lines: list[str]) -> str:
    header = _split_table_row(lines[0])
    rows = [_split_table_row(line) for line in lines[2:]]
    html = ['<div class="structured-ref-table-wrap"><table class="structured-ref-table">']
    html.append("<thead><tr>")
    for cell in header:
        html.append(f"<th>{escape(cell)}</th>")
    html.append("</tr></thead><tbody>")
    for row in rows:
        html.append("<tr>")
        for cell in row:
            html.append(f"<td>{escape(cell)}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


def _render_non_table_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
    if heading:
        level = min(len(heading.group(1)) + 1, 6)
        return f"<h{level}>{escape(heading.group(2))}</h{level}>"
    return f"<p>{escape(stripped)}</p>"


def _candidate_source_names(ref: StructuredReference, executed_steps: list) -> list[str]:
    names: list[str] = []
    if ref.source:
        names.append(ref.source)

    matched = _find_matching_result(ref, executed_steps)
    if matched and matched.get("source"):
        names.append(matched["source"])

    all_sources = [
        result.get("source", "")
        for step in executed_steps or []
        for result in step.get("results", [])
        if result.get("source")
    ]
    unique_sources = _dedupe(all_sources)
    if len(unique_sources) == 1:
        names.append(unique_sources[0])
    elif not names:
        names.extend(unique_sources)

    return _dedupe(names)


def _candidate_markdown_paths(kb_dir: Path, source_names: list[str]) -> list[Path]:
    paths: list[Path] = []
    for source in source_names:
        raw = Path(source)
        candidates = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.extend([Path.cwd() / raw, kb_dir / raw, kb_dir / raw.name])

        for candidate in candidates:
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".md":
                paths.append(candidate)

        if not any(p.name == raw.name for p in paths) and raw.name:
            paths.extend(kb_dir.rglob(raw.name))

    if not paths:
        paths.extend(kb_dir.rglob("*.md"))

    return _dedupe_paths(paths)


def _find_matching_result(ref: StructuredReference, executed_steps: list) -> dict | None:
    for step in executed_steps or []:
        for result in step.get("results", []):
            if _result_matches_reference(result, ref):
                return result
    return None


def _result_matches_reference(result: dict, ref: StructuredReference) -> bool:
    if ref.fields.get("table") and result.get("table_id") == ref.fields["table"]:
        return True
    if ref.fields.get("row") and result.get("row_id") == ref.fields["row"]:
        return True
    if ref.line and str(result.get("source_line", "")) == str(ref.line):
        return True

    ref_section = extract_section_number(ref.section)
    if not ref_section:
        return False

    candidates = [
        result.get("section_id", ""),
        result.get("section_title", ""),
        _extract_section_id_from_text(result.get("text", "")),
    ]
    return any(extract_section_number(candidate) == ref_section for candidate in candidates if candidate)


def _extract_section_id_from_text(text: str) -> str:
    tag = _SECTION_TAG_RE.search(text or "")
    if tag:
        return tag.group(1).strip()
    for line in (text or "").splitlines():
        heading = _HEADING_RE.match(line.strip())
        if heading:
            return heading.group(2)
    return ""


def _extract_line_context(path: Path, line_no: int, radius: int = 20) -> str:
    if not path.exists() or not path.is_file() or line_no <= 0:
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start - 1:end]).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    deduped = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped
