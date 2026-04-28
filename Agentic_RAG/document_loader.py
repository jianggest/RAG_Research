"""
文档加载与分块模块

职责：
  1. 扫描 knowledge_base/，将 PDF 通过 Docling 转换为同名 .md（已存在则跳过）
  2. 对 .md 文件调用清洗器，生成 _clean.md（已存在则跳过）
  3. 读取 .md 文件（优先加载 _clean.md，不存在时回退原文件），使用表格感知分块
  4. 读取 .txt 文件，使用滑动窗口分块
  5. 返回统一格式的 chunk 列表

对外接口：
  load_documents(kb_dir) -> list[Chunk]
  chunk_markdown(content, source, max_size) -> list[Chunk]   # 供测试直接调用
  chunk_text(content, source, max_size) -> list[Chunk]       # 供测试直接调用
"""

import re
from pathlib import Path
from typing import TypedDict

from config import CHUNK_SIZE


class Chunk(TypedDict):
    source: str
    chunk_index: int
    text: str
    is_table: bool


# ── PDF 转换 ──────────────────────────────────────────────────────────────────

def convert_pdfs(kb_dir: Path) -> None:
    """
    扫描目录，将未转换的 PDF 用 Docling 转为同名 .md。
    同名 .md 已存在时跳过，原始 PDF 始终保留。
    """
    for pdf_path in sorted(kb_dir.glob("*.pdf")):
        md_path = pdf_path.with_suffix(".md")
        if md_path.exists():
            print(f"[Loader] 跳过已转换: {pdf_path.name}")
            continue
        _convert_single_pdf(pdf_path, md_path)


def _convert_single_pdf(pdf_path: Path, md_path: Path) -> None:
    print(f"[Loader] 转换 PDF: {pdf_path.name} → {md_path.name}")
    try:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        md_path.write_text(result.document.export_to_markdown(), encoding="utf-8")
        print(f"[Loader] 转换完成: {md_path.name}")
    except ImportError:
        print("[Loader] ❌ 未安装 Docling，跳过 PDF 转换。运行：pip install docling")
    except Exception as e:
        print(f"[Loader] ❌ 转换失败 {pdf_path.name}: {e}")


# ── 表格感知分块（Markdown）────────────────────────────────────────────────────

def _extract_blocks(content: str) -> list[str]:
    """
    将 Markdown 文本拆成语义块（表格块 / 文本块）。

    核心规则：表格内的空行不作为分块边界，保证表格连续性。
    """
    blocks: list[str] = []
    current_lines: list[str] = []
    in_table = False

    for line in content.split("\n"):
        is_table_line = line.strip().startswith("|")

        if is_table_line:
            # 从文本切换到表格：先保存当前文本块
            if not in_table and current_lines:
                blocks.append("\n".join(current_lines))
                current_lines = []
            in_table = True
            current_lines.append(line)
        else:
            if in_table:
                # 表格内空行：跳过，不中断表格
                if not line.strip():
                    continue
                # 非空非表格行：表格结束，保存表格块
                blocks.append("\n".join(current_lines))
                current_lines = []
                in_table = False
            # 普通文本：空行作为块分隔符
            if not line.strip() and current_lines:
                blocks.append("\n".join(current_lines))
                current_lines = []
            elif line.strip():
                current_lines.append(line)

    if current_lines:
        blocks.append("\n".join(current_lines))

    return [b.strip() for b in blocks if b.strip()]


def _extract_heading(section: str) -> str:
    """提取节的首行标题（以 # 开头），找不到则返回空字符串。"""
    for line in section.splitlines():
        if line.strip().startswith("#"):
            return line.strip()
    return ""


def _with_heading(heading: str, block: str) -> str:
    """若 block 不以标题开头，则将节标题前置，保留检索上下文。"""
    if not heading or block.strip().startswith("#"):
        return block
    return f"{heading}\n\n{block}"


def _build_chunk(text: str, source: str, index: int) -> Chunk:
    return Chunk(
        source=source,
        chunk_index=index,
        text=text.strip(),
        is_table=text.strip().startswith("|"),
    )


def chunk_markdown(content: str, source: str, max_size: int = CHUNK_SIZE) -> list[Chunk]:
    """
    表格感知分块：
    - 表格块无论多大，保持完整（不受 max_size 限制）
    - 普通文本块超过 max_size 时才按字符拆分
    - 按 Markdown 标题（#/##/###）优先分节
    """
    chunks: list[Chunk] = []
    chunk_index = 0

    def save_chunk(text: str) -> None:
        nonlocal chunk_index
        text = text.strip()
        if text:  # 过滤空白内容
            chunks.append(_build_chunk(text, source, chunk_index))
            chunk_index += 1

    # 按标题分节，每节内部再细分
    sections = re.split(r"(?=\n#{1,3} )", "\n" + content)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= max_size:
            save_chunk(section)
            continue

        # 节内容过大，按语义块进一步拆分
        blocks = _extract_blocks(section)
        accumulated = ""

        # 提取节标题（首行以 # 开头），拆分后的子 chunk 都携带标题作为上下文
        # 避免"标题在 chunk1，表格在 chunk2"导致表格 chunk 缺失分类信息
        section_heading = _extract_heading(section)

        for block in blocks:
            is_table = block.strip().startswith("|")

            if len(block) > max_size:
                # 先保存已积累的内容
                if accumulated:
                    save_chunk(accumulated)
                    accumulated = ""
                if is_table:
                    # 表格始终保持完整，但携带节标题作为上下文
                    save_chunk(_with_heading(section_heading, block))
                else:
                    for i in range(0, len(block), max_size):
                        save_chunk(block[i : i + max_size])
            elif len(accumulated) + len(block) + 2 <= max_size:
                accumulated = (accumulated + "\n\n" + block).strip() if accumulated else block
            else:
                if accumulated:
                    save_chunk(accumulated)
                # 若新积累块是表格，携带节标题作为上下文
                # 避免"标题在 chunk N，表格在 chunk N+1"导致表格 chunk 丢失分类信息
                accumulated = _with_heading(section_heading, block) if is_table else block

        if accumulated:
            save_chunk(accumulated)

    return chunks


# ── 普通文本分块 ──────────────────────────────────────────────────────────────

def chunk_text(content: str, source: str, max_size: int = CHUNK_SIZE, overlap: int = 50) -> list[Chunk]:
    """滑动窗口分块，用于 .txt 文件（无表格感知）。"""
    chunks: list[Chunk] = []
    start = 0
    index = 0

    while start < len(content):
        text = content[start : start + max_size].strip()
        if text:
            chunks.append(_build_chunk(text, source, index))
            index += 1
        start += max_size - overlap

    return chunks


# ── 主入口 ────────────────────────────────────────────────────────────────────

def load_documents(kb_dir: Path) -> list[Chunk]:
    """
    加载 kb_dir 下所有文档，返回 chunk 列表。
    执行顺序：PDF 转换 → 文档清洗 → .md 分块 → .txt 分块
    """
    from doc_cleaner import clean_documents

    convert_pdfs(kb_dir)
    clean_documents(kb_dir)

    all_chunks: list[Chunk] = []

    for md_file in sorted(kb_dir.glob("*.md")):
        if md_file.stem.endswith("_clean"):
            # _clean.md 的处理：
            # - 若存在同名原始文件（去掉 _clean 后缀），则由原始文件路径统一处理，此处跳过
            # - 若无原始文件（用户直接提供 _clean.md），则作为独立文件直接加载
            original = md_file.with_name(md_file.stem[: -len("_clean")] + ".md")
            if original.exists():
                continue
            target = md_file
        else:
            # 优先加载 _clean.md，不存在时回退到原文件
            clean_file = md_file.with_name(f"{md_file.stem}_clean.md")
            target = clean_file if clean_file.exists() else md_file

        label = target.name
        content = target.read_text(encoding="utf-8")
        file_chunks = chunk_markdown(content, label)
        all_chunks.extend(file_chunks)
        print(f"[Loader] {label} → {len(file_chunks)} chunks")

    for txt_file in sorted(kb_dir.glob("*.txt")):
        content = txt_file.read_text(encoding="utf-8")
        file_chunks = chunk_text(content, txt_file.name)
        all_chunks.extend(file_chunks)
        print(f"[Loader] {txt_file.name} → {len(file_chunks)} chunks")

    print(f"[Loader] 共加载 {len(all_chunks)} 个 chunks")
    return all_chunks
