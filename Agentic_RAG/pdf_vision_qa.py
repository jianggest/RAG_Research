"""
PDF 视觉直答模块

原理：将 PDF 所有页面预渲染为图片缓存到本地，回答问题时把全部图片 + 问题
直接传给 Ollama 视觉模型，由模型看图作答，同时返回图片路径供前端展示。

对外接口：
  build_cache(pdf_path)               → 预渲染 PDF 页面到本地缓存
  answer(question, pdf_path) -> dict  → 看图回答，返回 {text, image_paths}
"""

from __future__ import annotations

from pathlib import Path

import ollama

from config import OLLAMA_MODEL, OLLAMA_OPTIONS

_DPI_SCALE = 2.0

_QA_PROMPT_TEMPLATE = (
    "以下是公司内部文档《{title}》的全部页面图片（共 {n} 页）。\n"
    "请根据图片内容回答以下问题，要求：\n"
    "1. 只根据图片中的实际内容作答，不要臆测；\n"
    "2. 如果答案涉及流程步骤，请按顺序列出；\n"
    "3. 如果图片中没有相关信息，明确告知。\n\n"
    "问题：{question}"
)


def build_cache(pdf_path: str | Path, force: bool = False) -> list[Path]:
    """
    将 PDF 各页渲染为 PNG 缓存到 knowledge_base/.page_cache/<pdf名>/ 目录。

    Args:
        pdf_path: PDF 文件路径
        force:    True 时强制重新渲染

    Returns:
        按页序排列的图片 Path 列表
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("请先安装 pymupdf：pip install pymupdf")

    pdf_path  = Path(pdf_path)
    cache_dir = pdf_path.parent / ".page_cache" / pdf_path.stem
    cache_dir.mkdir(parents=True, exist_ok=True)

    doc   = fitz.open(str(pdf_path))
    mat   = fitz.Matrix(_DPI_SCALE, _DPI_SCALE)
    paths: list[Path] = []

    for i, page in enumerate(doc):
        out = cache_dir / f"page_{i+1:02d}.png"
        if not out.exists() or force:
            pix = page.get_pixmap(matrix=mat)
            pix.save(str(out))
            print(f"[pdf_vision_qa] 渲染 第{i+1}/{len(doc)}页 → {out.name}")
        paths.append(out)

    doc.close()
    print(f"[pdf_vision_qa] 缓存就绪：{cache_dir}  共 {len(paths)} 张")
    return paths


def _load_cache(pdf_path: Path) -> list[Path]:
    """读取已有缓存，不存在时自动构建。"""
    cache_dir = pdf_path.parent / ".page_cache" / pdf_path.stem
    pages = sorted(cache_dir.glob("page_*.png")) if cache_dir.exists() else []
    return pages if pages else build_cache(pdf_path)


def answer(question: str, pdf_path: str | Path) -> dict:
    """
    将 PDF 全部页面图片 + 问题传给视觉模型，返回回答和图片路径。

    Returns:
        {
          "text":        str,          # 模型回答
          "image_paths": list[Path],   # 全部页面图片路径，供前端展示
        }
    """
    pdf_path   = Path(pdf_path)
    img_paths  = _load_cache(pdf_path)

    if not img_paths:
        return {"text": "❌ 无法加载文档图片，请检查 PDF 路径。", "image_paths": []}

    images = [p.read_bytes() for p in img_paths]
    print(f"[pdf_vision_qa] 传入 {len(images)} 张图片，模型：{OLLAMA_MODEL}")

    prompt = _QA_PROMPT_TEMPLATE.format(
        title=pdf_path.stem,
        n=len(images),
        question=question,
    )

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": images,
            }],
            options=OLLAMA_OPTIONS,
            think=False,
        )
        text = response["message"]["content"].strip()
    except Exception as e:
        text = f"❌ 视觉模型调用失败：{e}"

    return {"text": text, "image_paths": img_paths}
