"""
PDF 渲染测试

用途：将 PDF 逐页渲染为图片保存到 /tmp/pdf_pages/，方便人工确认截图清晰度。
确认效果满意后再接入视觉模型做内容提取。

运行：
    python test_pdf_render.py
"""

from pathlib import Path
import fitz  # pymupdf: pip install pymupdf

PDF_PATH = Path(__file__).parent / "knowledge_base" / "资产管理流程.pdf"
OUT_DIR  = Path(__file__).parent / "tmp" / "pdf_pages"
DPI_SCALE = 2.0   # 2.0 = 144dpi，调高更清晰但文件更大


def main():
    if not PDF_PATH.exists():
        print(f"❌ 找不到文件：{PDF_PATH}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(PDF_PATH))
    total = len(doc)
    print(f"共 {total} 页，输出目录：{OUT_DIR}")

    mat = fitz.Matrix(DPI_SCALE, DPI_SCALE)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat)
        out_path = OUT_DIR / f"page_{i+1:02d}.png"
        pix.save(str(out_path))
        print(f"  第{i+1}页 → {out_path.name}  ({pix.width}x{pix.height})")

    doc.close()
    print(f"\n完成，请打开 {OUT_DIR} 查看图片效果。")


if __name__ == "__main__":
    main()
