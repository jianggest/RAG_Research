from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def collect_figure_images_from_steps(kb_dir: Path, executed_steps: list[dict]) -> list[FigureImage]:
    """Resolve SearchResult figure_refs into local PNG paths for UI rendering."""
    figures: list[FigureImage] = []
    seen_paths: set[Path] = set()
    index_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}
    root = Path(kb_dir)

    for step in executed_steps or []:
        for result in step.get("results", []) or []:
            source = result.get("source", "")
            refs = _normalize_figure_refs(result.get("figure_refs"))
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
    return figures
