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

from config import CHUNK_SIZE, DATASHEET_SOURCES
from document_catalog import write_document_catalog
from retriever import extract_datasheet_entity_tokens, normalize_datasheet_text


class Chunk(TypedDict):
    source: str
    chunk_index: int
    text: str
    is_table: bool
    is_datasheet: bool
    index_kind: str
    normalized_text: str
    entity_tokens: list[str]
    # 结构锚字段：用于 V2 检索的"文档结构感知"，替代主题专属硬编码规则。
    # anchors_used: chunk 文本里出现的脚注引用（如表格单元格内的 "(1)"）
    # anchors_defined: chunk 内行首定义的脚注（如 "(1) ±200 PPM ..."）
    # refs_outbound: 跨章节引用（如 "Figure 6-5"、"Section 7.5"）
    anchors_used: list[str]
    anchors_defined: list[str]
    refs_outbound: list[str]


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

# 表格脚注锚定行模式：表格紧随其后的此类行应吸附进表格块，避免限制条件
# （如 "(1) ±200 PPM"、"Note 1: 不支持展频"）与表格主体被切散导致召回不全。
# 同时支持 docling/MinerU 清洗后常见的"- (1) ..."列表项形式。
_FOOTNOTE_ANCHOR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\(\d+\)\s+"),                          # (1) ...
    re.compile(r"^\[\d+\]\s+"),                          # [1] ...
    re.compile(r"^Note\s+\d+[:.]?\s+", re.IGNORECASE),   # Note 1: ... / Note 1. ...
    re.compile(r"^\*\s+"),                               # * ...
    re.compile(r"^†\s+"),                                # † ...
    re.compile(r"^\[\^\d+\]:\s+"),                       # [^1]: ...
    re.compile(r"^-\s+\(\d+\)\s+"),                      # - (1) ...
    re.compile(r"^-\s+\[\d+\]\s+"),                      # - [1] ...
    re.compile(r"^-\s+Note\s+\d+[:.]?\s+", re.IGNORECASE),  # - Note 1 ...
]


def _is_footnote_anchor(line: str) -> bool:
    """判断一行是否为表格脚注锚定行（(1)/[1]/Note N/* /†/[^N]:）。"""
    stripped = line.lstrip()
    return any(pat.match(stripped) for pat in _FOOTNOTE_ANCHOR_PATTERNS)


# 列表项前缀：在 ABSORBING 状态下被视为脚注续行（例如公式变量定义的 "- VAR = ..."）。
# 注意：`* ...` 同时被 _FOOTNOTE_ANCHOR_PATTERNS 命中，行为一致。
_LIST_BULLET_PATTERN: re.Pattern[str] = re.compile(r"^[-*+]\s+")


def _is_list_continuation(line: str) -> bool:
    """ABSORBING 状态下的"列表续行"判定：行首为 `-` / `*` / `+` 列表标记。"""
    return bool(_LIST_BULLET_PATTERN.match(line.lstrip()))


# ── 结构锚提取（V2 检索用）────────────────────────────────────────────────────
#
# anchors_used: chunk 文本里出现的脚注引用（表格单元格内的 (1)、<sup>(2)</sup>、[3]）
# anchors_defined: chunk 内行首定义的脚注（"(1) ±200 PPM" / "Note 1:" / "[1]" / "- (1)"）
# refs_outbound: 跨章节引用 "See Figure 6-5" / "Refer to Section 7.5"
#
# 所有锚点统一规范化为 "(N)" 格式，便于 V2 在不同写法间配对（used 与 defined 同号匹配）。
# 跨引用统一规范化为 "Kind Number"（首字母大写），如 "Figure 6-5"、"Section 7.5"。

# 行内 used 锚点：在一行的非定义部分扫描
_ANCHOR_USED_INLINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<sup>\s*\(?(\d+)\)?\s*</sup>"),  # <sup>(1)</sup> / <sup>1</sup>
    re.compile(r"\((\d+)\)"),                     # (1), (2)
    re.compile(r"\[(\d+)\]"),                     # [1], [2]
]

# 行首 defined 锚点：返回匹配对象 + 编号字符串
_ANCHOR_DEFINED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\((\d+)\)\s+"),                          # (1) ...
    re.compile(r"^\[(\d+)\]\s+"),                          # [1] ...
    re.compile(r"^Note\s+(\d+)[:.]?\s+", re.IGNORECASE),   # Note 1: ... / Note 1. ...
    re.compile(r"^\[\^(\d+)\]:\s+"),                       # [^1]: ...
    re.compile(r"^-\s+\((\d+)\)\s+"),                      # - (1) ...
    re.compile(r"^-\s+\[(\d+)\]\s+"),                      # - [1] ...
    re.compile(r"^-\s+Note\s+(\d+)[:.]?\s+", re.IGNORECASE),  # - Note 1 ...
]

# 跨章节引用：统一捕获 Figure/Table/Section/Chapter + 编号
_REF_OUTBOUND_PATTERN: re.Pattern[str] = re.compile(
    r"(?:See|Refer\s+to)\s+(Figure|Table|Section|Chapter)\s+([\w.\-]+?\d[\w.\-]*)",
    re.IGNORECASE,
)


def _anchor_sort_key(anchor: str) -> tuple[int, str]:
    """按编号数值排序（解析失败的排在末尾）。"""
    inner = anchor.strip("()")
    try:
        return (int(inner), anchor)
    except ValueError:
        return (10**9, anchor)


def _extract_anchors(text: str) -> tuple[list[str], list[str]]:
    """提取 (anchors_used, anchors_defined)，编号规范化为 "(N)"。

    扫描策略：
      - defined 行（行首匹配 `(1)` / `[1]` / `Note 1:` 等）：编号进 defined。
        定义之后的部分继续扫 used（脚注内常跨引用其他脚注，如 "(1) 见 (2)"）。
      - 其他行：只在以下情形扫 used，避免普通文本里的"步骤(1)"等噪声：
          a) 表格行（行首 `|`）—— 表格单元格里的 (1) / [1] 是脚注引用
          b) 行内含 `<sup>` 标签 —— 明确的脚注上标语义
    """
    used: set[str] = set()
    defined: set[str] = set()

    for line in text.splitlines():
        stripped = line.lstrip()
        matched_end = 0
        for pat in _ANCHOR_DEFINED_PATTERNS:
            m = pat.match(stripped)
            if m:
                defined.add(f"({m.group(1)})")
                matched_end = m.end()
                break

        # 是否应扫该行 used：表格行 / <sup> 标签行 / defined 行剩余部分
        is_defined_line = matched_end > 0
        is_table_line = stripped.startswith("|")
        has_sup_tag = "<sup>" in stripped.lower()
        if not (is_defined_line or is_table_line or has_sup_tag):
            continue

        scan = stripped[matched_end:] if matched_end else stripped
        for pat in _ANCHOR_USED_INLINE_PATTERNS:
            for m in pat.finditer(scan):
                used.add(f"({m.group(1)})")

    return sorted(used, key=_anchor_sort_key), sorted(defined, key=_anchor_sort_key)


def _extract_refs_outbound(text: str) -> list[str]:
    """提取跨章节引用，规范化为 "Kind Number" 形式。"""
    refs: set[str] = set()
    for m in _REF_OUTBOUND_PATTERN.finditer(text):
        kind = m.group(1).capitalize()
        number = m.group(2).rstrip(".,;:")
        refs.add(f"{kind} {number}")
    return sorted(refs)


def _extract_blocks(content: str) -> list[str]:
    """
    将 Markdown 文本拆成语义块（表格块 / 文本块）。

    采用三态状态机：
      TEXT       — 普通文本流；空行作为块分隔符。
      TABLE_BODY — 表格主体（| 行流）。空行跳过；
                   anchor 行 → 转 ABSORBING；其他非 | 非空行 → 关表回到 TEXT。
      ABSORBING  — 表格脚注吸附段（已吸附 ≥1 行 anchor）。空行跳过；
                   anchor 行 或 列表续行（`- ...` / `* ...` / `+ ...`）→ 继续吸附；
                   新 | 行 → 关旧块、以本行为新表格起点；
                   其他普通行 → 关旧块、回到 TEXT。

    设计取舍：
      - ABSORBING 下任何列表项视为续行（覆盖 datasheet 中"公式变量逐行定义"等真实形态）。
      - 不拆分"| 行 + 空行 + | 行"形式的相邻表格，保留原有合并行为
        （该问题与脚注吸附正交，留给后续任务处理）。
    """
    TEXT, TABLE_BODY, ABSORBING = "text", "table_body", "absorbing"

    blocks: list[str] = []
    current_lines: list[str] = []
    state = TEXT

    def flush() -> None:
        if current_lines:
            blocks.append("\n".join(current_lines))
            current_lines.clear()

    for line in content.split("\n"):
        stripped = line.strip()
        is_table_line = stripped.startswith("|")
        is_blank = not stripped

        if state == TABLE_BODY:
            if is_table_line:
                current_lines.append(line)
            elif is_blank:
                # 表格内空行：跳过，等待后续 | 行或脚注
                continue
            elif _is_footnote_anchor(line):
                current_lines.append(line)
                state = ABSORBING
            else:
                # 普通文本 / 标题 / 图片说明 → 表格结束
                flush()
                current_lines.append(line)
                state = TEXT
        elif state == ABSORBING:
            if is_table_line:
                # 脚注吸附完毕又遇到新表格 → 关旧块，以本行为新表格起点
                flush()
                current_lines.append(line)
                state = TABLE_BODY
            elif is_blank:
                continue
            elif _is_footnote_anchor(line) or _is_list_continuation(line):
                # anchor 行或列表续行：继续吸附（state 保持 ABSORBING）
                current_lines.append(line)
            else:
                # 普通文本段 / 图片说明 → 关旧块，回到 TEXT 累积
                flush()
                current_lines.append(line)
                state = TEXT
        else:  # TEXT
            if is_table_line:
                flush()
                current_lines.append(line)
                state = TABLE_BODY
            elif is_blank:
                if current_lines:
                    flush()
            else:
                current_lines.append(line)

    flush()
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
    stripped = text.strip()
    is_datasheet = source in DATASHEET_SOURCES
    normalized_text = normalize_datasheet_text(stripped) if is_datasheet else re.sub(r"\s+", " ", stripped)
    anchors_used, anchors_defined = _extract_anchors(stripped)
    refs_outbound = _extract_refs_outbound(stripped)
    return Chunk(
        source=source,
        chunk_index=index,
        text=stripped,
        # 表格 chunk 可能带有前置标题（例如 datasheet 的 "## 6.10 ..."），
        # 不能只判断首字符，否则表格 boost 会失效。
        is_table=any(line.strip().startswith("|") for line in stripped.splitlines()),
        is_datasheet=is_datasheet,
        index_kind="block",
        normalized_text=normalized_text,
        entity_tokens=extract_datasheet_entity_tokens(stripped) if is_datasheet else [],
        anchors_used=anchors_used,
        anchors_defined=anchors_defined,
        refs_outbound=refs_outbound,
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
    loaded_documents: list[dict] = []

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
        loaded_documents.append({"source": label, "content": content})
        file_chunks = chunk_markdown(content, label)
        all_chunks.extend(file_chunks)
        print(f"[Loader] {label} → {len(file_chunks)} chunks")

    for txt_file in sorted(kb_dir.glob("*.txt")):
        content = txt_file.read_text(encoding="utf-8")
        loaded_documents.append({"source": txt_file.name, "content": content})
        file_chunks = chunk_text(content, txt_file.name)
        all_chunks.extend(file_chunks)
        print(f"[Loader] {txt_file.name} → {len(file_chunks)} chunks")

    write_document_catalog(kb_dir, loaded_documents)
    print(f"[Loader] 共加载 {len(all_chunks)} 个 chunks")
    return all_chunks
