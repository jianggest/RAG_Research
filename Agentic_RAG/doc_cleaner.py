"""
文档清洗模块

职责：去除 PDF 转 Markdown 后产生的页眉/页脚/文件元信息等污染内容，
      输出干净文档供 RAG 检索使用。

命名约定（与 PDF 转换保持一致）：
  报销相关.md  →  报销相关_clean.md
  _clean.md 已存在时跳过，不重复处理。

清洗流程：
  Step 1: 频率统计 — 将文档按段落拆分，找出重复出现 ≥2 次的段落作为"污染候选"
  Step 2: LLM 确认 — 判断候选段落是"页眉/文件标识（删除）"还是"正文（保留）"
  Step 3: 规则清洗 — 删除固定模式 + LLM 确认的污染段落
  Step 4: 后处理  — 合并多余空行，写入 _clean.md

对外接口：clean_documents(kb_dir: Path) -> None
"""

import re
from collections import Counter
from pathlib import Path

from llm import call_llm


# ── 固定规则：无需 LLM 确认，直接删除 ────────────────────────────────────────

# 页码行，如"第 3 页 共 28 页"（含 ## 前缀变体）
_PAGE_RE = re.compile(r"^(?:##\s*)?第\s*\d+\s*页\s*共\s*\d+\s*页\s*$")

# 图片占位符
_IMAGE_LINE = "<!-- image -->"

# 孤立的文件编号（如 M-APPO-FM-02-02-02）
_FILE_NO_RE = re.compile(r"^[A-Z]+-[A-Z]+-[A-Z]+-\d+-\d+-\d+$")

# 孤立的版本号（如 V1.2、V1.3）
_VERSION_RE = re.compile(r"^V\d+\.\d+$")

# "文件编号" 独立行（PDF 表格被切断产生的碎片）
_FILE_NO_LABEL_RE = re.compile(r"^(?:文\s*件\s*编\s*号|版\s*本)$")


def _is_fixed_pollution(line: str) -> bool:
    """判断单行是否属于固定规则污染。"""
    s = line.strip()
    return (
        s == _IMAGE_LINE
        or bool(_PAGE_RE.match(s))
        or bool(_FILE_NO_RE.match(s))
        or bool(_VERSION_RE.match(s))
        or bool(_FILE_NO_LABEL_RE.match(s))
    )


def _is_file_meta_table_start(lines: list[str], i: int) -> bool:
    """
    检测从第 i 行开始是否是2列文件元信息表（文件编号/版本）。

    匹配形态：
      | 文件编号   | M-APPO-...  |
      |------------|-------------|
      | 版本       | V1.x        |
    或合并形态：
      | 费用报销及付款规定 | 文件编号 版本 | M-... V1.x |
    """
    if i >= len(lines):
        return False
    s = lines[i].strip()
    if not s.startswith("|"):
        return False
    # 匹配含"文件编号"的表格行（文件头行）
    if "文件编号" in s or ("文件" in s and "编号" in s):
        return True
    # 匹配合并形态（文件编号与版本在同一行）
    if "文件编号" in s and "版本" in s:
        return True
    return False


# ── Step 1：频率统计，发现重复段落 ───────────────────────────────────────────

def _split_blocks(content: str) -> list[str]:
    """按空行将文档拆分为段落块列表。"""
    blocks: list[str] = []
    current: list[str] = []

    for line in content.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []

    if current:
        blocks.append("\n".join(current))
    return blocks


def _find_candidates(content: str, min_count: int = 2) -> list[str]:
    """返回在文档中重复出现 ≥ min_count 次的段落（标准化后比较）。"""
    blocks = _split_blocks(content)
    # 标准化：压缩空白，便于跨版本差异块合并计数
    normalized = [re.sub(r"\s+", " ", b.strip()) for b in blocks]
    counts = Counter(normalized)
    repeated = {norm for norm, cnt in counts.items() if cnt >= min_count}
    # 返回原始块（去重）
    seen: set[str] = set()
    result: list[str] = []
    for orig, norm in zip(blocks, normalized):
        if norm in repeated and norm not in seen:
            seen.add(norm)
            result.append(orig)
    return result


# ── Step 2：LLM 确认污染候选 ──────────────────────────────────────────────────

_CONFIRM_PROMPT = """\
以下段落在文档中重复出现，请判断每项属于「页眉/页脚/文件标识」还是「正文内容」。

判断规则：
- 文件编号、版本号 → DELETE
- 文档标题作为页眉反复出现（而非正文章节标题）→ DELETE
- 图片占位符 → DELETE
- 页码信息 → DELETE
- 正文章节标题、条款内容、说明文字 → KEEP

只输出编号和判断，格式（每行一条，不要其他解释）：
[1] DELETE
[2] KEEP
...

段落列表：
{items}
"""


def _llm_confirm_pollution(candidates: list[str]) -> set[str]:
    """
    让 LLM 确认哪些候选段落是污染（应删除）。
    返回应删除段落的标准化文本集合。
    """
    if not candidates:
        return set()

    items = "\n---\n".join(f"[{i + 1}]\n{c}" for i, c in enumerate(candidates))
    prompt = _CONFIRM_PROMPT.format(items=items)

    print(f"[Cleaner] 请 LLM 确认 {len(candidates)} 个污染候选...")
    response = call_llm(prompt)
    print(f"[Cleaner] LLM 确认完成")

    to_delete: set[str] = set()
    for i, candidate in enumerate(candidates):
        if f"[{i + 1}] DELETE" in response:
            to_delete.add(re.sub(r"\s+", " ", candidate.strip()))

    return to_delete


# ── Step 3：规则清洗 ──────────────────────────────────────────────────────────

def _clean_content(content: str, to_delete: set[str]) -> str:
    """
    逐行/逐块清洗文档内容：
    1. 跳过固定规则命中的行
    2. 跳过文件元信息表格（多行）
    3. 跳过 LLM 确认的污染段落
    """
    lines = content.splitlines()
    cleaned: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 固定规则：单行污染
        if _is_fixed_pollution(line):
            i += 1
            continue

        # 文件元信息表格（跳过直到表格结束）
        if _is_file_meta_table_start(lines, i):
            # 跳过连续的表格行（以 | 开头）
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue

        cleaned.append(line)
        i += 1

    result = "\n".join(cleaned)

    # 删除 LLM 确认的污染段落
    if to_delete:
        blocks = _split_blocks(result)
        kept: list[str] = []
        for block in blocks:
            norm = re.sub(r"\s+", " ", block.strip())
            if norm not in to_delete:
                kept.append(block)
        result = "\n\n".join(kept)

    return result


# ── Step 4：后处理 ────────────────────────────────────────────────────────────

def _post_process(content: str) -> str:
    """合并连续多个空行为单个空行，去除首尾空白。"""
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip() + "\n"


# ── 主流程 ────────────────────────────────────────────────────────────────────

def _clean_single_document(md_path: Path, clean_path: Path) -> None:
    """清洗单个文档，输出到 clean_path。"""
    print(f"[Cleaner] 清洗: {md_path.name} → {clean_path.name}")

    content = md_path.read_text(encoding="utf-8")

    # Step 1：找出重复段落
    candidates = _find_candidates(content)
    print(f"[Cleaner]   频率统计发现 {len(candidates)} 个污染候选")

    # Step 2：LLM 确认（跳过已属于固定规则的候选，减少 LLM 调用量）
    llm_candidates = [
        c for c in candidates
        if not all(_is_fixed_pollution(line) for line in c.splitlines() if line.strip())
    ]
    to_delete = _llm_confirm_pollution(llm_candidates)
    print(f"[Cleaner]   LLM 确认删除 {len(to_delete)} 个段落")

    # Step 3：规则清洗
    cleaned = _clean_content(content, to_delete)

    # Step 4：后处理
    cleaned = _post_process(cleaned)

    clean_path.write_text(cleaned, encoding="utf-8")
    original_lines = len(content.splitlines())
    cleaned_lines = len(cleaned.splitlines())
    print(f"[Cleaner] 完成: {original_lines} 行 → {cleaned_lines} 行（减少 {original_lines - cleaned_lines} 行）")


def clean_documents(kb_dir: Path) -> None:
    """
    扫描目录，对未清洗的 .md 文件生成 _clean.md 版本。

    与 convert_pdfs 保持一致的幂等设计：
    - _clean.md 已存在 → 跳过（不重复处理）
    - 已是 _clean.md 的文件 → 跳过（避免递归处理）
    """
    for md_path in sorted(kb_dir.glob("*.md")):
        if md_path.stem.endswith("_clean"):
            continue  # 跳过已是 clean 的文件

        clean_path = md_path.with_name(f"{md_path.stem}_clean.md")
        if clean_path.exists():
            print(f"[Cleaner] 跳过已清洗: {md_path.name}")
            continue

        _clean_single_document(md_path, clean_path)
