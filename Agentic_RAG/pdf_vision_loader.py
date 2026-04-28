"""
PDF 视觉解析加载器

职责：将图片型 PDF（如 PPT 转 PDF）逐页截图，调用本地 Ollama 视觉模型提取文字内容，
返回与现有 indexer pipeline 兼容的 chunk 列表。

适用场景：
  - PPT 转 PDF 后文字大量以图片形式存在，纯文本提取丢失内容严重
  - 含有大量流程图、截图的文档

依赖：
  - pymupdf：pip install pymupdf
  - ollama：项目已有，无需额外安装

使用示例：
  from pdf_vision_loader import load_pdf_via_vision
  chunks = load_pdf_via_vision("knowledge_base/资产管理流程.pdf")
"""

from __future__ import annotations

from pathlib import Path

import ollama

from config import OLLAMA_MODEL, OLLAMA_OPTIONS

# source_name 与 search_asset_management.py 中 _SOURCES 保持一致
_DEFAULT_SOURCE = "资产管理流程_clean.md"

_VISION_PROMPT = (
    "这是公司内部文档的某一页（由 PPT 转换而来）。\n"
    "请提取页面中所有可见的文字内容，要求：\n"
    "1. 保留原有结构，如列表、流程步骤、表格；\n"
    "2. 表格用 Markdown 格式输出；\n"
    "3. 去掉纯装饰性元素（背景、logo、色块）；\n"
    "4. 直接输出提取结果，不要加任何前缀说明。\n"
    "如果页面内容为空或只有装饰，输出：[空页]"
)


def load_pdf_via_vision(
    pdf_path: str | Path,
    source_name: str = _DEFAULT_SOURCE,
    dpi_scale: float = 2.0,
) -> list[dict]:
    """
    逐页将 PDF 渲染为图片，用 Ollama 视觉模型提取内容，返回 chunk 列表。

    Args:
        pdf_path:    PDF 文件路径
        source_name: chunk 的 source 字段，须与对应 Skill 的 _SOURCES 保持一致
        dpi_scale:   渲染分辨率倍数，2.0 = 144dpi

    Returns:
        list[dict]，每个 dict 包含 text / source / page / is_table 字段
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("请先安装 pymupdf：pip install pymupdf")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    print(f"[pdf_vision_loader] {pdf_path.name}  共 {total} 页  模型：{OLLAMA_MODEL}")

    chunks: list[dict] = []
    mat = fitz.Matrix(dpi_scale, dpi_scale)

    for page_num, page in enumerate(doc):
        print(f"  第 {page_num + 1}/{total} 页 ...", end=" ", flush=True)

        img_bytes = page.get_pixmap(matrix=mat).tobytes("png")
        text = _vision_extract(img_bytes)

        if not text or text.strip() == "[空页]":
            print("跳过（空页）")
            continue

        is_table = "|" in text and text.count("|") >= 4
        chunks.append({
            "text": text.strip(),
            "source": source_name,
            "page": page_num + 1,
            "is_table": is_table,
        })
        print(f"{len(text)} 字{'  [表格]' if is_table else ''}")

    doc.close()
    print(f"[pdf_vision_loader] 完成，共 {len(chunks)} 个 chunk")
    return chunks


def _vision_extract(img_bytes: bytes) -> str:
    """调用 Ollama 视觉模型从图片中提取文字。"""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{
                "role": "user",
                "content": _VISION_PROMPT,
                "images": [img_bytes],
            }],
            options=OLLAMA_OPTIONS,
            think=False,
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"\n[pdf_vision_loader] ❌ 视觉提取失败: {e}")
        return ""
