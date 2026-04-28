"""
视觉提取执行脚本（一次性运行）

将 资产管理流程.pdf 逐页截图，用 Ollama 视觉模型提取内容，
结果写入 knowledge_base/资产管理流程_clean.md，覆盖 Docling 生成的残缺版本。

完成后重启 app.py 即可自动重建索引。

运行：
    cd Agentic_RAG
    python run_vision_extract.py
"""

from pathlib import Path
from pdf_vision_loader import load_pdf_via_vision

KB_DIR   = Path(__file__).parent / "knowledge_base"
PDF_PATH = KB_DIR / "资产管理流程.pdf"
OUT_PATH = KB_DIR / "资产管理流程_clean.md"


def main():
    print(f"PDF 路径：{PDF_PATH}")
    print(f"输出路径：{OUT_PATH}\n")

    chunks = load_pdf_via_vision(pdf_path=PDF_PATH)

    if not chunks:
        print("❌ 未提取到任何内容，请检查 PDF 路径或 Ollama 是否正常运行。")
        return

    # 预先构建图片缓存（渲染 PDF 页面为 PNG）
    from pdf_vision_qa import build_cache
    img_paths = build_cache(PDF_PATH)
    # 建立页码 → 图片路径映射（页码从 1 开始）
    img_map = {p: img_paths[p - 1] for p in range(1, len(img_paths) + 1) if p - 1 < len(img_paths)}

    # 将各页内容拼接为 Markdown
    # 每页头部嵌入图片路径标记 __PAGE_IMG__:/abs/path/page_XX.png
    # 该标记供前端检测后渲染原始图片，同时不影响文字检索
    lines = []
    for c in chunks:
        img_path = img_map.get(c["page"])
        lines.append(f"## 第{c['page']}页\n")
        if img_path:
            lines.append(f"__PAGE_IMG__:{img_path.as_posix()}\n")
        lines.append(c["text"])
        lines.append("\n")

    md_content = "\n".join(lines)
    OUT_PATH.write_text(md_content, encoding="utf-8")
    print(f"\n✅ 已写入 {OUT_PATH.name}，共 {len(chunks)} 页，{len(md_content)} 字")
    print("重启 app.py 将自动重建索引。")


if __name__ == "__main__":
    main()
