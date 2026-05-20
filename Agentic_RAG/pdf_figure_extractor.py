"""PDF Figure caption parsing, screenshot extraction and figure index helpers.

First version targets datasheet PDFs where captions are explicit and usually sit
below the figure body. The module is safe to import without PyMuPDF; only the
real extraction path imports ``fitz`` lazily.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


FIGURE_CAPTION_RE = re.compile(
    r"^(?:Figure|Fig\.)\s+(\d+(?:[-.]\d+)+)\.?\s+(.+)$",
    re.IGNORECASE,
)
FIGURE_REF_RE = re.compile(r"\b(?:Figure|Fig\.)\s+(\d+(?:[-.]\d+)+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class FigureCaption:
    figure_id: str
    caption: str
    raw_text: str


@dataclass(frozen=True)
class _PageObject:
    kind: str
    bbox: tuple[float, float, float, float]
    text: str = ""


@dataclass(frozen=True)
class _CaptionOnPage:
    caption: FigureCaption
    bbox: tuple[float, float, float, float]
    text: str
    line_index: int = -1


def _normalize_figure_id(number: str) -> str:
    number = number.strip().replace(".", "-")
    return f"Figure {number}"


def _clean_caption_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    title = re.sub(r"\s+(?:www\.|Copyright|DLPS\d+|SL[A-Z0-9]+).*$", "", title, flags=re.IGNORECASE)
    return title.strip(" .;:")


def _is_bold_span(span: dict[str, Any]) -> bool:
    font = str(span.get("font", "")).lower()
    return "bold" in font or bool(int(span.get("flags", 0)) & 16)


def _line_is_caption_style(spans: list[dict[str, Any]]) -> bool:
    non_empty = [s for s in spans if str(s.get("text", "")).strip()]
    if not non_empty:
        return False
    return all(_is_bold_span(s) for s in non_empty)


def _is_page_header_or_footer(obj: _PageObject, page_rect: Any) -> bool:
    text = (obj.text or "").strip()
    y0, y1 = obj.bbox[1], obj.bbox[3]
    if obj.kind == "text" and re.match(r"^\d+(?:\.\d+)*\s+\S+", text):
        return True
    if y1 <= float(page_rect.y0) + 70:
        if re.search(r"\b(DLPC\d+|DLPS\d+|www\.ti\.com|REVISED|JANUARY|OCTOBER)\b", text, re.IGNORECASE):
            return True
        if obj.kind == "drawing":
            return True
    if y0 >= float(page_rect.y1) - 70:
        if re.search(r"\b(Copyright|Submit Document Feedback|Product Folder Links)\b", text, re.IGNORECASE):
            return True
        if obj.kind == "drawing":
            return True
    return False


def _parse_figure_caption(text: str) -> FigureCaption | None:
    match = FIGURE_CAPTION_RE.search(" ".join((text or "").split()))
    if not match:
        return None
    title = _clean_caption_title(match.group(2))
    if not title:
        return None
    return FigureCaption(
        figure_id=_normalize_figure_id(match.group(1)),
        caption=title,
        raw_text=text.strip(),
    )


def _extract_figure_refs(text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in FIGURE_REF_RE.finditer(text or ""):
        ref = _normalize_figure_id(match.group(1))
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _safe_figure_filename(figure_id: str, caption: str) -> str:
    stem = f"{figure_id}_{caption}"
    stem = stem.replace(" ", "_")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("._-")
    return f"{stem[:140]}.png"


def _pdf_signature(pdf_path: Path) -> dict[str, Any]:
    stat = pdf_path.stat()
    head = pdf_path.read_bytes()[:1024 * 1024]
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256_head": hashlib.sha256(head).hexdigest(),
    }


def _index_is_fresh(index_path: Path, pdf_path: Path) -> bool:
    if not index_path.exists():
        return False
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if isinstance(data, dict):
        return data.get("pdf_signature") == _pdf_signature(pdf_path)
    # Backward compatibility for the initially suggested list-only format.
    return False


def _index_entries(index_data: Any) -> list[dict[str, Any]]:
    if isinstance(index_data, dict):
        return list(index_data.get("figures", []))
    if isinstance(index_data, list):
        return index_data
    return []


def load_figure_index(kb_dir: Path, source: str) -> dict[str, list[dict[str, Any]]]:
    """Load figure_id -> entries for a markdown source such as dlpc3436_clean.md."""
    source_name = Path(source).name
    stem = source_name
    for suffix in ("_clean.md", ".md", ".pdf"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    index_path = Path(kb_dir) / stem / "figures.json"
    if not index_path.exists():
        return {}
    data = json.loads(index_path.read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, Any]]] = {}
    for item in _index_entries(data):
        figure_id = item.get("figure_id")
        if figure_id:
            out.setdefault(figure_id, []).append(item)
    return out


def _union_bbox(boxes: Iterable[tuple[float, float, float, float]]) -> tuple[float, float, float, float] | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _overlap_ratio_x(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    width = max(1.0, min(a[2] - a[0], b[2] - b[0]))
    return overlap / width


def _clip_bbox(
    bbox: tuple[float, float, float, float],
    page_rect: Any,
    padding: float = 8.0,
) -> tuple[float, float, float, float]:
    return (
        max(float(page_rect.x0), bbox[0] - padding),
        max(float(page_rect.y0), bbox[1] - padding),
        min(float(page_rect.x1), bbox[2] + padding),
        min(float(page_rect.y1), bbox[3] + padding),
    )


def _extract_text_objects(page: Any) -> tuple[list[_PageObject], list[_CaptionOnPage]]:
    raw = page.get_text("dict")
    objects: list[_PageObject] = []
    captions: list[_CaptionOnPage] = []
    line_index = 0
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = " ".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            bbox = tuple(float(v) for v in line.get("bbox", block.get("bbox")))  # type: ignore[arg-type]
            objects.append(_PageObject("text", bbox, text))
            current_line_index = line_index
            line_index += 1
            if not _line_is_caption_style(spans):
                continue
            parsed = _parse_figure_caption(text)
            if parsed:
                captions.append(_CaptionOnPage(parsed, bbox, text, current_line_index))
    return objects, captions


def _extract_drawing_objects(page: Any) -> list[_PageObject]:
    out: list[_PageObject] = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect:
            out.append(_PageObject("drawing", (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))))
    return out


def _extract_image_objects(page: Any) -> list[_PageObject]:
    out: list[_PageObject] = []
    for image in page.get_images(full=True):
        xref = image[0]
        try:
            for rect in page.get_image_rects(xref):
                out.append(_PageObject("image", (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))))
        except Exception:
            continue
    return out


def _caption_x_regions(captions: list[_CaptionOnPage], page_rect: Any) -> dict[_CaptionOnPage, tuple[float, float]]:
    page_width = float(page_rect.x1) - float(page_rect.x0)
    sorted_caps = sorted(captions, key=lambda c: ((c.bbox[0] + c.bbox[2]) / 2.0, c.bbox[1]))
    regions: dict[_CaptionOnPage, tuple[float, float]] = {}
    for cap in sorted_caps:
        cap_center = (cap.bbox[0] + cap.bbox[2]) / 2.0
        same_row = [c for c in sorted_caps if c is not cap and abs(c.bbox[1] - cap.bbox[1]) <= 45]
        if not same_row:
            regions[cap] = (float(page_rect.x0), float(page_rect.x1))
            continue
        left_neighbors = [((c.bbox[0] + c.bbox[2]) / 2.0, c) for c in same_row if (c.bbox[0] + c.bbox[2]) / 2.0 < cap_center]
        right_neighbors = [((c.bbox[0] + c.bbox[2]) / 2.0, c) for c in same_row if (c.bbox[0] + c.bbox[2]) / 2.0 > cap_center]
        if left_neighbors:
            left_cap = max(left_neighbors, key=lambda item: item[0])[1]
            left = (left_cap.bbox[2] + cap.bbox[0]) / 2.0
        else:
            left = float(page_rect.x0)
        if right_neighbors:
            right_cap = min(right_neighbors, key=lambda item: item[0])[1]
            right = (cap.bbox[2] + right_cap.bbox[0]) / 2.0
        else:
            right = float(page_rect.x1)
        # Give each same-row panel enough room for axis labels and waveform tails.
        gutter = min(28.0, page_width * 0.05)
        regions[cap] = (max(float(page_rect.x0), left - gutter), min(float(page_rect.x1), right + gutter))
    return regions


def _object_area(obj: _PageObject) -> float:
    w = max(0.0, obj.bbox[2] - obj.bbox[0])
    h = max(0.0, obj.bbox[3] - obj.bbox[1])
    return w * h


def _object_height(obj: _PageObject) -> float:
    return max(0.0, obj.bbox[3] - obj.bbox[1])


def _figure_like_seed_objects(objects: list[_PageObject], cap_top: float) -> list[_PageObject]:
    seeds: list[_PageObject] = []
    for obj in objects:
        if obj.bbox[3] > cap_top + 4:
            continue
        width = max(0.0, obj.bbox[2] - obj.bbox[0])
        height = max(0.0, obj.bbox[3] - obj.bbox[1])
        if obj.kind in {"drawing", "image"} and (width >= 12 or height >= 12):
            seeds.append(obj)
    return seeds


def _nearest_figure_top(candidate_objects: list[_PageObject], cap_top: float) -> float | None:
    seeds = _figure_like_seed_objects(candidate_objects, cap_top)
    if not seeds:
        return None
    # Start with the nearest substantial drawn/image object above the caption, then
    # grow upward only through visually connected/nearby objects. This prevents
    # earlier parameter tables or intro paragraphs from being swept into the crop.
    nearest = max(seeds, key=lambda obj: obj.bbox[3])
    top = nearest.bbox[1]
    bottom = nearest.bbox[3]
    changed = True
    while changed:
        changed = False
        for obj in seeds:
            if obj.bbox[1] >= top:
                continue
            gap = top - obj.bbox[3]
            if gap <= 22:
                top = obj.bbox[1]
                bottom = max(bottom, obj.bbox[3])
                changed = True
    return top


def _is_body_text_after_caption(
    obj: _PageObject,
    caption: _CaptionOnPage,
    horizontal_window: tuple[float, float, float, float],
) -> bool:
    if obj.kind != "text" or obj.bbox == caption.bbox:
        return False
    if obj.bbox[1] < caption.bbox[3] - 1:
        return False
    if _overlap_ratio_x(obj.bbox, horizontal_window) < 0.15:
        return False
    text = obj.text.strip()
    if re.match(r"^\d+(?:\.\d+)+\s+\S", text):
        return True
    if re.match(r"^(?:Table|Figure|Fig\.)\s+\d+(?:[-.]\d+)+\b", text, re.IGNORECASE):
        return True
    return False


def _expand_caption_continuation(
    caption: _CaptionOnPage,
    boxes: list[tuple[float, float, float, float]],
    objects: list[_PageObject],
    horizontal_window: tuple[float, float, float, float],
) -> None:
    cap_bottom = caption.bbox[3]
    cap_height = max(1.0, caption.bbox[3] - caption.bbox[1])
    for obj in objects:
        if obj.kind != "text" or obj.bbox == caption.bbox:
            continue
        if obj.bbox[1] < cap_bottom - 1:
            continue
        if obj.bbox[1] > cap_bottom + cap_height * 1.6:
            continue
        if _overlap_ratio_x(obj.bbox, horizontal_window) < 0.15:
            continue
        text = obj.text.strip()
        # Long captions in TI datasheets can wrap onto the next line, e.g.
        # "Figure 7-6. Pixels ... After CAIC" + "Processing". Include the
        # immediate continuation line but avoid pulling following paragraphs.
        if len(text) <= 80 and not re.match(r"^(?:Above|The|This|When|For|In|If|Note\b|\(\d+\))\b", text):
            boxes.append(obj.bbox)


def _figure_bbox_for_caption(
    caption: _CaptionOnPage,
    captions: list[_CaptionOnPage],
    objects: list[_PageObject],
    page_rect: Any,
) -> tuple[float, float, float, float]:
    x_regions = _caption_x_regions(captions, page_rect)
    x0, x1 = x_regions[caption]
    horizontal_window = (x0, float(page_rect.y0), x1, float(page_rect.y1))
    cap_top = caption.bbox[1]
    max_scan = float(page_rect.height) * 0.60
    above_captions = [c.bbox[3] for c in captions if c.bbox[3] < cap_top - 4 and _overlap_ratio_x(c.bbox, caption.bbox) > 0.1]
    y0_limit = max(above_captions) if above_captions else max(float(page_rect.y0), cap_top - max_scan)
    boxes = [caption.bbox]
    candidate_objects: list[_PageObject] = []
    for obj in objects:
        if obj.bbox == caption.bbox:
            continue
        if _is_page_header_or_footer(obj, page_rect):
            continue
        if obj.bbox[3] > cap_top + 4:
            continue
        if obj.bbox[1] < y0_limit:
            continue
        if _overlap_ratio_x(obj.bbox, horizontal_window) < 0.15:
            continue
        candidate_objects.append(obj)

    figure_top = _nearest_figure_top(candidate_objects, cap_top)
    for obj in candidate_objects:
        if figure_top is not None and obj.bbox[3] < figure_top - 6:
            continue
        boxes.append(obj.bbox)
    _expand_caption_continuation(caption, boxes, objects, horizontal_window)
    next_body_tops = [
        obj.bbox[1]
        for obj in objects
        if _is_body_text_after_caption(obj, caption, horizontal_window)
    ]
    if next_body_tops:
        body_top = min(next_body_tops)
        boxes = [box for box in boxes if box[1] < body_top - 1]
    merged = _union_bbox(boxes) or caption.bbox
    # Keep split figures inside their caption-defined half/column, but allow small padding.
    merged = (max(merged[0], x0 - 10), merged[1], min(merged[2], x1 + 10), merged[3])
    return _clip_bbox(merged, page_rect)


def extract_pdf_figures_for_file(pdf_path: Path, force: bool = False, dpi_scale: float = 2.0) -> list[dict[str, Any]]:
    try:
        import fitz  # type: ignore
    except ImportError:
        print("[FigureExtractor] 未安装 PyMuPDF，跳过 PDF Figure 提取。运行：pip install pymupdf")
        return []

    pdf_path = Path(pdf_path)
    out_dir = pdf_path.with_suffix("")
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "figures.json"
    if not force and _index_is_fresh(index_path, pdf_path):
        data = json.loads(index_path.read_text(encoding="utf-8"))
        figures = _index_entries(data)
        print(f"[FigureExtractor] 跳过未变化: {pdf_path.name} figures={len(figures)}")
        return figures

    figures: list[dict[str, Any]] = []
    used_names: set[str] = set()
    doc = fitz.open(str(pdf_path))
    try:
        for page_index, page in enumerate(doc):
            text_objects, captions = _extract_text_objects(page)
            if not captions:
                continue
            objects = text_objects + _extract_drawing_objects(page) + _extract_image_objects(page)
            for cap in captions:
                bbox = _figure_bbox_for_caption(cap, captions, objects, page.rect)
                filename = _safe_figure_filename(cap.caption.figure_id, cap.caption.caption)
                if filename in used_names:
                    stem = filename[:-4]
                    n = 2
                    while f"{stem}_{n}.png" in used_names:
                        n += 1
                    filename = f"{stem}_{n}.png"
                used_names.add(filename)
                out_path = out_dir / filename
                clip_rect = fitz.Rect(*bbox)
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale), clip=clip_rect, alpha=False)
                pix.save(str(out_path))
                figures.append(
                    {
                        "figure_id": cap.caption.figure_id,
                        "caption": cap.caption.caption,
                        "raw_caption": cap.caption.raw_text,
                        "source_pdf": pdf_path.name,
                        "source_markdown": f"{pdf_path.stem}_clean.md",
                        "page": page_index + 1,
                        "image_path": f"{pdf_path.stem}/{filename}",
                        "bbox": [round(v, 2) for v in bbox],
                    }
                )
    finally:
        doc.close()

    index_data = {
        "source_pdf": pdf_path.name,
        "pdf_signature": _pdf_signature(pdf_path),
        "figures": figures,
    }
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[FigureExtractor] {pdf_path.name} figures={len(figures)} out={out_dir}")
    return figures


def extract_pdf_figures(kb_dir: Path, force: bool = False, only_pdf_stem: str | None = None) -> None:
    try:
        import fitz  # noqa: F401  # type: ignore
    except ImportError:
        print("[FigureExtractor] 未安装 PyMuPDF，跳过 PDF Figure 提取。运行：pip install pymupdf")
        return

    for pdf_path in sorted(Path(kb_dir).glob("*.pdf")):
        if only_pdf_stem and pdf_path.stem != only_pdf_stem:
            continue
        try:
            extract_pdf_figures_for_file(pdf_path, force=force)
        except Exception as exc:
            print(f"[FigureExtractor] 提取失败 {pdf_path.name}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract datasheet PDF figures into PNG files and figures.json")
    parser.add_argument("pdf", type=Path, help="PDF path, e.g. knowledge_base/datasheet/dlpc3436.pdf")
    parser.add_argument("--force", action="store_true", help="rebuild even if figures.json signature is fresh")
    parser.add_argument("--dpi-scale", type=float, default=2.0)
    args = parser.parse_args()
    figures = extract_pdf_figures_for_file(args.pdf, force=args.force, dpi_scale=args.dpi_scale)
    print(json.dumps({"figures": len(figures), "pdf": str(args.pdf)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
