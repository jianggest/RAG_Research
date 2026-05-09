"""
文档增强索引模块

职责：为每个 chunk 生成多角度问题，扩充向量索引的召回覆盖面。

解决的核心问题：用户提问用语与文档术语不一致的语义鸿沟。
  示例："年假" ↔ "年休假"，"婚礼福利" ↔ "婚假"，"结婚福利" ↔ "结婚礼金+婚假"

工作原理：
  - 对每个 chunk，让 LLM 从用户视角生成 8-10 个不同问法
  - 将问题文本作为 ChromaDB 的 document（用于向量匹配），原始 chunk 文本存入 metadata
  - 检索命中增强条目时，返回 metadata 中的原始文本，而非问题文本本身

缓存机制：
  - 生成结果持久化到当前 profile 的 knowledge_base/<profile>/.question_cache.json
  - 缓存键：chunk text 的 MD5（文档内容变更时自动失效）
  - 重启时直接复用，不重复调用 LLM
"""

import hashlib
import json
from pathlib import Path

from llm import call_llm
from config import AUGMENT_MAX_CHUNKS, get_knowledge_base_dir

def get_question_cache_file() -> Path:
    return get_knowledge_base_dir() / ".question_cache.json"

_AUGMENT_PROMPT = """\
给定以下文档片段，请从用户提问的角度，生成8-10个不同的自然语言问题，这些问题的答案都能在这段内容中找到。

要求：
- 覆盖不同的提问方式（直接问、间接问、用近义词）
- 包含该内容相关的上位概念（例如婚假内容，也要生成"婚礼福利有哪些"这类问题）
- 同一事项用不同词汇提问（例如"年休假"对应"年假"、"带薪假期"）
- 每行一个问题，不要编号或其他格式，不要输出任何解释

文档片段：
{text}"""


# ── 缓存 ──────────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    """加载本地问题缓存，文件不存在时返回空字典。"""
    cache_file = get_question_cache_file()
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    """持久化问题缓存到本地文件。"""
    cache_file = get_question_cache_file()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _chunk_hash(text: str) -> str:
    """MD5 作为缓存键，内容变更时自动失效。"""
    return hashlib.md5(text.encode()).hexdigest()


# ── 问题生成 ──────────────────────────────────────────────────────────────────

def _should_augment(chunk: dict) -> bool:
    """
    判断 chunk 是否值得生成增强问题。

    规则：
    - datasheet chunk：跳过自然语言增强，避免 LLM 生成问题污染精确技术索引。
    - 表格 chunk：无论长短都增强（年假表、报销标准表是用户最常查的内容）
    - 文本 chunk：内容足够长才有增强价值（纯标题、过渡句跳过）
    """
    if chunk.get("is_datasheet"):
        return False
    if chunk.get("is_table"):
        return True
    return len(chunk["text"]) >= 80


def _generate_questions(text: str) -> list[str]:
    """调用 LLM 为单个 chunk 生成问题列表，失败时返回空列表。"""
    prompt = _AUGMENT_PROMPT.format(text=text[:800])
    raw = call_llm(prompt)
    if not raw:
        return []
    questions = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith(("#", "-", "*"))
    ]
    return questions[:10]


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def generate_augmented_entries(chunks: list[dict]) -> list[dict]:
    """
    为 chunk 列表生成增强索引条目，带缓存。

    返回值格式（每条对应一个问题）：
      {
        "document":      问题文本（ChromaDB document，用于向量匹配）,
        "source":        来源文件名,
        "chunk_index":   原始 chunk 编号,
        "is_table":      是否为表格 chunk,
        "original_text": 原始 chunk 文本（检索命中后返回给用户）,
        "chunk_hash":    chunk MD5（唯一标识，用于生成 ChromaDB ID）,
      }
    """
    cache = load_cache()
    cache_updated = False
    augmented: list[dict] = []

    for chunk in chunks:
        text = chunk["text"]
        if not _should_augment(chunk):
            continue
        if AUGMENT_MAX_CHUNKS is not None and len(cache) >= AUGMENT_MAX_CHUNKS:
            print(f"[Augmenter] 达到增强上限 {AUGMENT_MAX_CHUNKS}，跳过剩余 chunk", flush=True)
            break

        key = _chunk_hash(text)

        if key in cache:
            questions = cache[key]
        else:
            print(f"[Augmenter] 生成问题：{chunk['source']} chunk_{chunk['chunk_index']}")
            questions = _generate_questions(text)
            cache[key] = questions  # 即使为空也缓存，避免重复调用失败的 chunk
            cache_updated = True

        for q in questions:
            augmented.append({
                "document":      q,
                "source":        chunk["source"],
                "chunk_index":   chunk["chunk_index"],
                "is_table":      chunk["is_table"],
                "is_datasheet":  bool(chunk.get("is_datasheet", False)),
                "index_kind":    chunk.get("index_kind", "block"),
                "original_text": text,
                "chunk_hash":    key,
            })

    if cache_updated:
        save_cache(cache)
        print(f"[Augmenter] 缓存已保存：{get_question_cache_file()}（共 {len(cache)} 个 chunk）")

    return augmented
