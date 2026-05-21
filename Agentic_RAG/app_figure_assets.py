from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

from pdf_figure_extractor import load_figure_index


@dataclass(frozen=True)
class FigureImage:
    figure_id: str
    caption: str
    source: str
    path: Path


def _normalize_figure_refs(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        refs = raw.split("|") if "|" in raw else [raw]
    else:
        refs = list(raw)
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        value = str(ref).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _answer_cited_refs(answer: str | None) -> list[str]:
    if not answer:
        return []
    from pdf_figure_extractor import _extract_figure_refs

    return _extract_figure_refs(answer)


def _result_score(result: dict) -> float:
    try:
        return float(result.get("score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


_FIGURE_CAPTION_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:Figure|Fig\.)\s+\d+(?:-\d+)+\.?\s+\S", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_QUERY_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "does", "into",
    "requirements", "requirement", "timing", "system", "technical", "tech", "如下",
}


def _looks_like_figure_caption(text: str) -> bool:
    return bool(_FIGURE_CAPTION_RE.search(text or ""))


def _query_terms(query: str | None) -> set[str]:
    if not query:
        return set()
    terms: set[str] = set()
    for token in _TOKEN_RE.findall(query):
        norm = token.casefold()
        # Device/model tokens scope the datasource; they are too broad for deciding
        # whether an uncited figure caption is semantically relevant. Otherwise a
        # caption like "Figure 9-1. DLPC3436 Power-Up Timing" matches any
        # DLPC3436 query and leaks into unrelated answers.
        if re.match(r"^(?:dlpc|dlpa|dlp|tps|msp|lm|tlc)\d", norm):
            continue
        if norm in _QUERY_STOPWORDS:
            continue
        terms.add(norm)
    return terms


def _caption_relevance(result: dict, query_terms: set[str], rank: int) -> tuple[int, float, int] | None:
    text = result.get("text") or ""
    if not _looks_like_figure_caption(text):
        return None
    if query_terms:
        text_norm = text.casefold()
        overlap = sum(1 for term in query_terms if term in text_norm)
        if overlap <= 0:
            return None
    else:
        overlap = 1
    return (-overlap, -_result_score(result), rank)


def _resolve_figures(
    root: Path,
    candidate_results: list[dict],
    *,
    cited_refs: list[str] | None = None,
    max_images: int = 3,
) -> list[FigureImage]:
    figures: list[FigureImage] = []
    seen_paths: set[Path] = set()
    index_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}
    cited_set = set(cited_refs or [])

    for result in candidate_results:
        source = result.get("source", "")
        refs = _normalize_figure_refs(result.get("figure_refs"))
        if cited_set:
            refs = [ref for ref in refs if ref in cited_set]
            refs.sort(key=lambda ref: cited_refs.index(ref) if cited_refs and ref in cited_refs else len(cited_refs or []))
        if not source or not refs:
            continue
        if source not in index_cache:
            index_cache[source] = load_figure_index(root, source)
        figure_index = index_cache[source]
        for ref in refs:
            for entry in figure_index.get(ref, []):
                image_path = entry.get("image_path")
                if not image_path:
                    continue
                path = root / image_path
                if not path.exists() or path in seen_paths:
                    continue
                seen_paths.add(path)
                figures.append(FigureImage(
                    figure_id=entry.get("figure_id", ref),
                    caption=entry.get("caption", ""),
                    source=source,
                    path=path,
                ))
                if len(figures) >= max_images:
                    return figures
    return figures


def collect_figure_images_from_steps(
    kb_dir: Path,
    executed_steps: list[dict],
    *,
    answer: str | None = None,
    query: str | None = None,
    min_score: float = 0.0,
    max_images: int = 3,
) -> list[FigureImage]:
    """Resolve high-confidence SearchResult figure_refs into local PNG paths for UI rendering."""
    root = Path(kb_dir)
    cited_refs = _answer_cited_refs(answer)
    cited_set = set(cited_refs)

    candidate_results: list[dict] = []
    for step in executed_steps or []:
        candidate_results.extend(step.get("results", []) or [])

    if cited_set:
        cited_results = [
            result for result in candidate_results
            if cited_set.intersection(_normalize_figure_refs(result.get("figure_refs")))
        ]
        return _resolve_figures(root, cited_results, cited_refs=cited_refs, max_images=max_images)

    terms = _query_terms(query)
    caption_ranked: list[tuple[tuple[int, float, int], dict]] = []
    for rank, result in enumerate(candidate_results):
        if not _normalize_figure_refs(result.get("figure_refs")):
            continue
        relevance = _caption_relevance(result, terms, rank)
        if relevance is not None:
            caption_ranked.append((relevance, result))
    if caption_ranked:
        caption_results = [result for _, result in sorted(caption_ranked, key=lambda item: item[0])]
        return _resolve_figures(root, caption_results, max_images=min(max_images, 2))

    high_score_results = [result for result in candidate_results if _result_score(result) >= min_score]
    high_score_results.sort(key=_result_score, reverse=True)
    return _resolve_figures(root, high_score_results, max_images=max_images)
