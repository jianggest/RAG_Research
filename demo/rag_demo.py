#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║           RAG（检索增强生成）原理演示 Demo                      ║
║                                                              ║
║  场景：模拟企业内部知识库智能问答系统                             ║
║  目的：通过实际运行，感受 RAG 为什么能让 LLM 回答私有数据问题       ║
║                                                              ║
║  运行：python rag_demo.py                                    ║
║  依赖（轻量）：pip install chromadb                           ║
║  依赖（完整）：我    ║
╚══════════════════════════════════════════════════════════════╝

【核心问题】
  普通 LLM（如 GPT-4）的知识来自公开训练数据，它有两个天然缺陷：
  1. 知识截止日期 → 不知道最新信息
  2. 不知道你的私有数据 → 不了解公司内部文档、规章、产品定价

【RAG 的解法】
  Retrieval-Augmented Generation = 先检索，再生成

  用户提问
     ↓
  ① 把问题转成向量，去知识库里"找相关原文"  ← Retrieval（检索）
     ↓
  ② 把原文片段塞进 Prompt，让 LLM 参考作答  ← Augmented Generation（增强生成）
     ↓
  有依据的回答（可追溯到原文出处）

【本 Demo 包含 4 个步骤】
  步骤 1：加载文档（从 knowledge_base/ 目录读取）
  步骤 2：文本切块（Chunking）
  步骤 3：向量化 + 建立索引（Embedding + ChromaDB）
  步骤 4：交互式问答（检索 + 可选 LLM 生成）
"""

import os
import sys
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  配置区（可根据需要修改）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 知识库文档目录（相对于本脚本的路径）
DOCS_DIR = Path(__file__).parent / "knowledge_base"

# 向量库持久化目录
CHROMA_DIR = str(Path(__file__).parent / "chroma_db")

# Embedding 后端选择：
#   "chroma"  → 使用 ChromaDB 内置模型（仅需 pip install chromadb，约 50MB）【推荐先用这个】
#               模型：all-MiniLM-L6-v2，英文效果好，中文可用
#   "sentence" → 使用 sentence-transformers（需额外安装 PyTorch，约 200MB+）
#               模型：paraphrase-multilingual-MiniLM-L12-v2，中英文效果更好
EMBEDDING_BACKEND = "sentence"

# sentence-transformers 模式下使用的模型名称（EMBEDDING_BACKEND="sentence" 时生效）
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 文本切块参数
CHUNK_SIZE = 300    # 每个 chunk 的最大字符数
CHUNK_OVERLAP = 50  # 相邻 chunk 的重叠字符数（避免边界信息丢失）

# 检索返回的 Top-K 片段数
TOP_K = 5

# ── LLM 后端配置 ────────────────────────────────────────────────
#
#  "none"   → 只展示检索到的文档片段，不调用 LLM【推荐初学者】
#             这个模式已足够理解 RAG 的核心：检索阶段。
#
#  "ollama" → 使用本地 Ollama 模型（免费，数据不出境）
#             前提：
#               1. 安装 Ollama：https://ollama.com/download
#               2. 拉取模型：ollama pull qwen2:7b
#               3. pip install ollama
#
#  "openai" → 使用 OpenAI 或兼容 API（需要 API Key）
#             前提：
#               1. pip install openai
#               2. 设置环境变量：set OPENAI_API_KEY=你的key
#               3. 如使用国内中转，修改下方 OPENAI_BASE_URL
#
LLM_BACKEND = "ollama"

OLLAMA_MODEL = "qwen3.6:35b-a3b-q4_K_M"#"gemma4"       # Ollama 使用的模型名称
OPENAI_MODEL = "gpt-4o-mini"    # OpenAI 使用的模型名称
OPENAI_BASE_URL = None          # None = 使用官方地址；填写则使用自定义地址


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 1：加载文档
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_documents(docs_dir: Path) -> list:
    """
    从目录读取所有 .txt 和 .pdf 文档。
    - .txt 直接读取文本
    - .pdf 使用 Docling 解析，表格会转为 Markdown 格式保留结构
    """
    docs = []

    if not docs_dir.exists():
        print(f"  ❌ 知识库目录不存在：{docs_dir}")
        sys.exit(1)

    # 读取 .txt 文件
    for file_path in sorted(docs_dir.glob("*.txt")):
        content = file_path.read_text(encoding="utf-8")
        docs.append({
            "filename": file_path.name,
            "content": content,
        })
        print(f"  📄 {file_path.name:<35} {len(content):>6} 字  [txt]")

    # 读取 .pdf 文件（使用 Docling 解析）
    pdf_files = sorted(docs_dir.glob("*.pdf"))
    if pdf_files:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            print("  ❌ 缺少 Docling 库，无法解析 PDF。请运行：pip install docling")
            sys.exit(1)

        converter = DocumentConverter()
        for file_path in pdf_files:
            print(f"  📑 {file_path.name:<35}  解析中...", end="", flush=True)
            result = converter.convert(str(file_path))
            content = result.document.export_to_markdown()
            content = filter_watermarks(content)
            docs.append({
                "filename": file_path.name,
                "content": content,
            })
            print(f"\r  📑 {file_path.name:<35} {len(content):>6} 字  [pdf]")

    if not docs:
        print(f"  ❌ knowledge_base/ 目录中没有找到 .txt 或 .pdf 文件")
        sys.exit(1)

    return docs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PDF 后处理：水印过滤
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def filter_watermarks(content: str, freq_threshold: int = 5) -> str:
    """
    过滤 Docling 解析 PDF 后产生的噪音：
    1. 删除高频重复行（文字水印）—— 同一行出现次数 >= freq_threshold 视为水印
    2. 删除图片占位符 <!-- image -->
    3. 删除纯表格分隔线（仅含 | - : 空格 的行，无实际内容）
    4. 合并连续空行
    """
    import re
    from collections import Counter

    lines = content.split('\n')

    # 统计每行出现频率
    line_counts = Counter(line.strip() for line in lines if line.strip())
    watermark_lines = {line for line, cnt in line_counts.items() if cnt >= freq_threshold}

    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            filtered.append('')
            continue
        if stripped in watermark_lines:
            continue
        if stripped == '<!-- image -->':
            continue
        # 纯表格分隔线：只含 | - : 空格
        if re.fullmatch(r'[\|\-\s:]+', stripped):
            continue
        filtered.append(line)

    # 合并连续空行为单个空行
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(filtered))
    return result.strip()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 2：文本切块（Chunking）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def chunk_documents(docs: list, chunk_size: int, overlap: int) -> list:
    """
    将长文档切成小块（Chunks）。

    【策略】
    - .txt 文档：滑动窗口固定切块（原有方式）
    - .pdf 文档：Markdown 感知切块
        ① 按标题（#/##/###）分节，节作为基本单位
        ② 节内识别表格块，保证表格不被切断
        ③ 非表格内容按空行分段
        ④ 超过 chunk_size 的块再做降级拆分

    【为什么 PDF 要特殊处理？】
    Docling 输出的是 Markdown，表格是 | col | col | 格式。
    固定窗口会把表头和数据行切到不同 chunk，导致语义完全丢失。
    """
    chunks = []
    for doc in docs:
        if doc["filename"].endswith(".pdf"):
            chunks.extend(_chunk_markdown(doc["content"], doc["filename"], chunk_size))
        else:
            chunks.extend(_chunk_text(doc["content"], doc["filename"], chunk_size, overlap))
    return chunks


def _chunk_text(content: str, source: str, chunk_size: int, overlap: int) -> list:
    """原有滑动窗口切块，用于 .txt 文档。"""
    chunks = []
    start = 0
    chunk_index = 0
    while start < len(content):
        end = min(start + chunk_size, len(content))
        chunk_text = content[start:end].strip()
        if len(chunk_text) > 20:
            chunks.append({
                "id": f"{source}__chunk_{chunk_index:03d}",
                "text": chunk_text,
                "source": source,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        start += chunk_size - overlap
    return chunks


def _extract_blocks(content: str) -> list:
    """
    将 Markdown 内容拆成语义块：
    - 连续的 | 开头行合并为一个表格块
    - 其余内容按空行分段
    """
    blocks = []
    current_lines = []
    in_table = False

    for line in content.split('\n'):
        is_table_line = line.strip().startswith('|')

        if is_table_line:
            if not in_table and current_lines:
                blocks.append('\n'.join(current_lines))
                current_lines = []
            in_table = True
            current_lines.append(line)
        else:
            if in_table:
                blocks.append('\n'.join(current_lines))
                current_lines = []
                in_table = False
            if not line.strip() and current_lines:
                blocks.append('\n'.join(current_lines))
                current_lines = []
            elif line.strip():
                current_lines.append(line)

    if current_lines:
        blocks.append('\n'.join(current_lines))

    return [b.strip() for b in blocks if b.strip()]


def _chunk_markdown(content: str, source: str, max_size: int) -> list:
    """
    Markdown 感知切块：按标题分节 → 节内按表格/段落分块 → 超大块降级拆分。
    """
    import re

    chunks = []
    chunk_index = 0

    def append_chunk(text: str):
        nonlocal chunk_index
        text = text.strip()
        if len(text) > 20:
            chunks.append({
                "id": f"{source}__chunk_{chunk_index:03d}",
                "text": text,
                "source": source,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    # 按标题行分节（保留标题本身在节内）
    sections = re.split(r'(?=\n#{1,3} )', '\n' + content)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= max_size:
            append_chunk(section)
        else:
            # 节太大，按表格块 + 段落拆分，然后贪心合并
            blocks = _extract_blocks(section)
            current = ""
            for block in blocks:
                if len(block) > max_size:
                    # 超大单块（超长表格或段落）：强制按字符拆分
                    if current:
                        append_chunk(current)
                        current = ""
                    for i in range(0, len(block), max_size):
                        append_chunk(block[i:i + max_size])
                elif len(current) + len(block) + 2 <= max_size:
                    current = (current + "\n\n" + block).strip() if current else block
                else:
                    if current:
                        append_chunk(current)
                    current = block
            if current:
                append_chunk(current)

    return chunks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 3：向量化 + 建立索引
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_index(chunks: list, chroma_dir: str):
    """
    将每个文本块转换为向量，存入 ChromaDB。

    【Embedding 是什么？】
    把文字转换成一串数字（高维向量），例如：
      "员工生日福利" → [0.12, -0.34, 0.78, ..., 0.05]  （384个数字）
      "生日当天的假期" → [0.11, -0.31, 0.80, ..., 0.06]  （384个数字）

    语义相近的文字，对应的向量在数学空间中距离更近。
    这样就能用"计算两个向量的余弦相似度"来找到语义最相关的内容。

    【为什么用向量数据库而不是普通数据库？】
    普通数据库（MySQL）做的是精确匹配，比如 WHERE content LIKE '%生日%'
    向量数据库做的是语义相似搜索，能找到"表达意思相近"的内容，
    即使用词完全不同也能匹配到（如"生日" 和 "出生纪念日"）。
    """
    try:
        import chromadb
    except ImportError:
        print("\n  ❌ 缺少依赖库：chromadb")
        print("  请运行：pip install chromadb")
        sys.exit(1)

    # ── 根据配置选择 Embedding 后端 ─────────────────────────────
    embed_model = None  # sentence-transformers 模式下使用

    if EMBEDDING_BACKEND == "sentence":
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("\n  ❌ EMBEDDING_BACKEND='sentence' 需要安装额外依赖。")
            print("  方案一（推荐，无需 GPU 库）：")
            print("    pip install torch --index-url https://download.pytorch.org/whl/cpu")
            print("    pip install sentence-transformers")
            print("\n  方案二（改用轻量模式，无需 PyTorch）：")
            print("    修改脚本配置：EMBEDDING_BACKEND = 'chroma'")
            sys.exit(1)

        print(f"\n  正在加载 Embedding 模型：{EMBEDDING_MODEL}")
        print("  （首次运行需下载模型，约 400MB）")
        embed_model = SentenceTransformer(EMBEDDING_MODEL)
        ef = None  # 使用手动 encode，不用 ChromaDB 的 embedding_function
    else:
        # chroma 模式：使用 ChromaDB 内置的 all-MiniLM-L6-v2（基于 onnxruntime）
        from chromadb.utils import embedding_functions
        print("\n  使用 ChromaDB 内置 Embedding 模型（all-MiniLM-L6-v2）")
        print("  （首次运行需下载模型，约 50MB，比 PyTorch 方案轻量很多）")
        ef = embedding_functions.DefaultEmbeddingFunction()

    # ── 初始化向量库 ─────────────────────────────────────────────
    client = chromadb.PersistentClient(path=chroma_dir)

    try:
        client.delete_collection("rag_demo")
        print("  ℹ️  已清除旧索引，重新构建中...")
    except Exception:
        pass

    if ef is not None:
        # chroma 模式：让 ChromaDB 自动处理 embedding
        collection = client.create_collection(
            name="rag_demo",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    else:
        collection = client.create_collection(
            name="rag_demo",
            metadata={"hnsw:space": "cosine"},
        )

    texts = [c["text"] for c in chunks]
    ids = [c["id"] for c in chunks]
    metadatas = [{"source": c["source"], "chunk_index": c["chunk_index"]} for c in chunks]

    print(f"\n  正在向量化 {len(chunks)} 个文本块...")

    if embed_model is not None:
        # sentence-transformers 模式：手动 encode 后存入
        embeddings = embed_model.encode(texts, show_progress_bar=True, batch_size=32)
        collection.add(ids=ids, documents=texts, embeddings=embeddings.tolist(), metadatas=metadatas)
    else:
        # chroma 模式：直接存 documents，ChromaDB 自动调用 ef 生成向量
        collection.add(ids=ids, documents=texts, metadatas=metadatas)

    print(f"\n  ✅ 索引构建完成！向量库位置：{chroma_dir}")
    return embed_model, collection


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 4a：检索（Retrieval）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def retrieve(query: str, embed_model, collection, top_k: int) -> list:
    """
    将用户问题向量化，在向量库中搜索最相似的文本块。

    【相似度的含义】
    相似度范围 0~1，越高越相关：
      > 0.85：高度相关，几乎可以直接作为答案
      0.70~0.85：相关，但可能需要结合其他片段
      < 0.60：相关性较低，可能是噪音
    """
    if embed_model is not None:
        # sentence-transformers 模式：手动向量化问题
        query_vec = embed_model.encode([query]).tolist()
        results = collection.query(
            query_embeddings=query_vec,
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    else:
        # chroma 模式：直接传文本，ChromaDB 内部自动向量化
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

    retrieved = []
    for i in range(len(results["documents"][0])):
        # ChromaDB 返回的是"距离"，余弦距离转换为相似度：similarity = 1 - distance
        similarity = 1 - results["distances"][0][i]
        retrieved.append({
            "text": results["documents"][0][i],
            "source": results["metadatas"][0][i]["source"],
            "chunk_index": results["metadatas"][0][i]["chunk_index"],
            "similarity": similarity,
        })

    return retrieved


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 4b：构建 Prompt + 调用 LLM 生成答案
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_rag_prompt(query: str, contexts: list) -> str:
    """
    构建 RAG Prompt：把检索到的原文片段 + 用户问题组合成发给 LLM 的完整指令。

    【这是 RAG 的核心 "Augmented" 部分】
    我们把检索到的文档内容直接"喂"给 LLM，相当于在开会前把相关文件递给顾问，
    让他有依据地回答，而不是凭空猜测。

    【关键指令："不要编造"】
    Prompt 中明确要求：如果检索内容中没有答案，就说"不知道"。
    这是控制幻觉（Hallucination）的基本手段。
    """
    context_parts = []
    for i, ctx in enumerate(contexts, 1):
        context_parts.append(
            f"【片段{i} | 来源：{ctx['source']} | 相似度：{ctx['similarity']:.2f}】\n{ctx['text']}"
        )
    context_text = "\n\n".join(context_parts)

    return f"""你是一个企业内部知识库助手。请严格根据下方"检索到的知识库内容"来回答用户问题。

规则：
1. 只能使用知识库内容中提到的信息作答，不得使用知识库以外的知识
2. 如果知识库内容无法回答该问题，请明确回复"根据现有知识库，我暂时无法回答这个问题"
3. 回答时注明信息来自哪份文档

===== 检索到的知识库内容 =====
{context_text}

===== 用户问题 =====
{query}

请根据以上知识库内容作答："""


def call_llm(prompt: str) -> str:
    """调用 LLM 生成答案，根据 LLM_BACKEND 配置选择不同后端。"""

    if LLM_BACKEND == "ollama":
        try:
            import ollama
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                think=False,           # 关闭 Thinking 模式，RAG 场景不需要深度推理
                options={"num_ctx": 4096},  # 限制 context 长度，避免不必要的性能开销
            )
            return response["message"]["content"]
        except ImportError:
            return "❌ 请先安装：pip install ollama"
        except Exception as e:
            return (
                f"❌ Ollama 调用失败：{e}\n"
                f"   请确认：\n"
                f"   1. Ollama 已启动（任务栏有图标）\n"
                f"   2. 模型已下载：ollama pull {OLLAMA_MODEL}"
            )

    elif LLM_BACKEND == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=OPENAI_BASE_URL,
            )
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            return response.choices[0].message.content
        except ImportError:
            return "❌ 请先安装：pip install openai"
        except Exception as e:
            return f"❌ OpenAI API 调用失败：{e}"

    return None  # LLM_BACKEND == "none"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  新增步骤：自我反思与查询重写
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def self_reflect_and_rewrite(query: str, contexts: list, threshold: float = 0.65) -> str:
    """
    反思逻辑：
    1. 检查最高相似度是否低于阈值。
    2. 如果太低，调用 LLM 重新生成一个更有利于检索的关键词。
    """
    max_sim = max([c['similarity'] for c in contexts]) if contexts else 0
    
    if max_sim >= threshold:
        return None  # 足够相关，无需反思
    
    print(f"  ⚠️  反思中：最高相似度仅为 {max_sim:.2f}，低于阈值 {threshold}。")
    print("  🔄  正在重写查询关键词以尝试优化检索...")

    # 构建重写 Prompt
    rewrite_prompt = f"""你是一个搜索优化助手。用户提出了一个问题，但在知识库中没搜到相关内容。
请根据原始问题，提取或生成 2-3 个核心关键词，用空格分隔，以便更好地进行向量搜索。

原始问题：{query}
优化后的关键词："""

    # 调用 LLM（复用之前的 call_llm）
    new_query = call_llm(rewrite_prompt)
    # 简单的清理逻辑
    new_query = new_query.replace('"', '').replace("'", "").strip()
    return new_query

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  修改后的主循环逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def retrieve_rag_with_reflection(query: str, embed_model, collection):
    current_query = query
    max_retries = 1  # 允许重试 1 次
    attempt = 0
    
    while attempt <= max_retries:
        print(f"\n  🔍 检索阶段 (尝试 {attempt + 1})：使用查询 '{current_query}'")
        contexts = retrieve(current_query, embed_model, collection, TOP_K)
        
        # 展示检索结果（同你之前的代码）
        for i, ctx in enumerate(contexts, 1):
            print(f"  片段 {i} | 相似度: {ctx['similarity']:.3f} | 来源: {ctx['source']}")

        # --- 自动反思触发 ---
        # 如果是第一次尝试，且相似度不高，则重写
        if attempt < max_retries:
            rewritten_query = self_reflect_and_rewrite(query, contexts, threshold=0.68)
            if rewritten_query:
                current_query = rewritten_query
                attempt += 1
                continue # 进入下一次循环，重新检索
        
        # 如果相似度达标，或者已经重试过了，直接进入生成阶段
        break

    # 正常的生成流程
    
    return contexts



def run_rag_with_reflection(query: str, embed_model, collection):
    current_query = query
    max_retries = 1  # 允许重试 1 次
    attempt = 0
    
    while attempt <= max_retries:
        print(f"\n  🔍 检索阶段 (尝试 {attempt + 1})：使用查询 '{current_query}'")
        contexts = retrieve(current_query, embed_model, collection, TOP_K)
        
        # 展示检索结果（同你之前的代码）
        for i, ctx in enumerate(contexts, 1):
            print(f"  片段 {i} | 相似度: {ctx['similarity']:.3f} | 来源: {ctx['source']}")

        # --- 自动反思触发 ---
        # 如果是第一次尝试，且相似度不高，则重写
        if attempt < max_retries:
            rewritten_query = self_reflect_and_rewrite(query, contexts, threshold=0.68)
            if rewritten_query:
                current_query = rewritten_query
                attempt += 1
                continue # 进入下一次循环，重新检索
        
        # 如果相似度达标，或者已经重试过了，直接进入生成阶段
        break

    # 正常的生成流程
    prompt = build_rag_prompt(query, contexts)
    print(f"\n  💬 生成阶段...")
    answer = call_llm(prompt)
    return answer


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  主流程
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_banner(text: str, char="━", width=62):
    inner = f"  {text}  "
    pad = max(0, width - len(inner))
    print(f"\n{char * (pad // 2)}{inner}{char * (pad - pad // 2)}")


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          RAG（检索增强生成）原理演示                             ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # ── 步骤 1：加载文档 ───────────────────────────────────────────
    print_banner("步骤 1 / 3：加载知识库文档")
    print(f"\n  从目录加载文档：{DOCS_DIR}\n")
    docs = load_documents(DOCS_DIR)
    for doc in docs:
      if doc["filename"].endswith(".pdf"):
          print("\n===== Docling 解析内容预览 =====")
          print(doc["content"][:1000])
          break
      
    print(f"\n  共加载 {len(docs)} 份文档。")
    print("""
  💡 理解要点：
     这些文档是 LLM 原本"不知道"的私有数据。
     它们不在任何 LLM 的训练集里，直接问 LLM 是不会回答的。
    """)

    # ── 步骤 2：文本切块 ───────────────────────────────────────────
    print_banner("步骤 2 / 3：文本切块（Chunking）")
    chunks = chunk_documents(docs, CHUNK_SIZE, CHUNK_OVERLAP)

    pdf_chunks = [c for c in chunks if c["source"].endswith(".pdf")][:5]
    for c in pdf_chunks:
        print(f"\n--- chunk {c['chunk_index']} ---")
        print(c["text"])

    print(f"""
  参数：chunk_size={CHUNK_SIZE} 字，overlap={CHUNK_OVERLAP} 字
  结果：{len(docs)} 份文档 → {len(chunks)} 个文本块

  示例（第 3 个 chunk）：
  {'─' * 56}
  来源：{chunks[2]['source']}
  内容：{chunks[2]['text'][:120].replace(chr(10), ' ')}...
  {'─' * 56}

  💡 理解要点：
     切块是为了精准定位。检索时返回相关的小片段，
     而不是把整个 500KB 的 PDF 都塞进 Prompt。
    """)

    # ── 步骤 3：向量化 + 建立索引 ─────────────────────────────────
    print_banner("步骤 3 / 3：向量化 + 建立索引（Embedding + ChromaDB）")
    embed_model, collection = build_index(chunks, CHROMA_DIR)
    print("""
  💡 理解要点：
     每个文本块都被转成了一个"数字坐标"（高维向量）。
     语义相似的内容在这个坐标空间中距离更近。
     检索时，把问题也转成坐标，找"最近的邻居"即可。
    """)

    # ── 交互式问答 ─────────────────────────────────────────────────
    mode_desc = {
        "none": "仅展示检索结果（无 LLM 生成）",
        "ollama": f"Ollama 本地模型（{OLLAMA_MODEL}）",
        "openai": f"OpenAI API（{OPENAI_MODEL}）",
    }.get(LLM_BACKEND, LLM_BACKEND)

    print(f"""
{'═' * 62}
  索引构建完成！开始交互式问答
  LLM 模式：{mode_desc}
  输入 quit 退出
{'═' * 62}

  📌 推荐先试试这些问题（LLM 肯定不知道，但 RAG 能回答）：
     • 智云助手Pro的年费是多少？
     • 员工生日当天有什么福利？
     • 系统用的是什么向量数据库？
     • 试用期薪资是正式薪资的多少？
     • 文档解析支持哪些 OCR 工具？
    """)

    while True:
        try:
            query = input("🙋 你的问题：").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  已退出。")
            break

        if query.lower() in ("quit", "exit", "q", "退出", ""):
            print("\n  ✅ 演示结束。")
            break

        # ── 检索阶段 ────────────────────────────────────────────────
        print(f"\n  {'─' * 58}")
        print("  🔍 检索阶段（Retrieval）")
        print(f"  {'─' * 58}")
        print(f"  将问题转成向量，在 {collection.count()} 个文本块中搜索最相似的 {TOP_K} 个...\n")

        contexts = retrieve(query, embed_model, collection, TOP_K)

        for i, ctx in enumerate(contexts, 1):
            bar_len = int(ctx["similarity"] * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"  片段 {i}  相似度 [{bar}] {ctx['similarity']:.3f}")
            print(f"  来源：{ctx['source']}")
            preview = ctx["text"][:180].replace("\n", " ")
            print(f"  内容：{preview}{'...' if len(ctx['text']) > 180 else ''}")
            print()

        # ── 生成阶段 ────────────────────────────────────────────────
        print(f"  {'─' * 58}")
        print("  💬 生成阶段（Generation）")
        print(f"  {'─' * 58}")

        prompt = build_rag_prompt(query, contexts)

        if LLM_BACKEND == "none":
            print(f"""
  当前模式：仅检索（LLM_BACKEND = "none"）

  ✅ 检索阶段已完成，上方的片段就是 RAG 找到的"依据"。
     在真实系统中，这些片段会被拼入下面的 Prompt 发给 LLM：

  ┌──── Prompt 预览（前 600 字符）────────────────────────────
""")
            prompt_preview = prompt[:600].replace("\n", "\n  │  ")
            print(f"  │  {prompt_preview}")
            if len(prompt) > 600:
                print(f"  │  ... （共 {len(prompt)} 字符）")
            print("  └───────────────────────────────────────────────────────")
            print("""
  想看完整生成效果？修改脚本顶部配置：
    LLM_BACKEND = "ollama"   # 需安装 Ollama + 拉取模型
    LLM_BACKEND = "openai"   # 需设置 OPENAI_API_KEY
            """)
        else:
            print(f"\n  正在调用 {LLM_BACKEND} 生成答案...\n")
            answer = call_llm(prompt)
            print("  ┌──── LLM 答案 ──────────────────────────────────────────")
            for line in answer.split("\n"):
                print(f"  │  {line}")
            print("  └───────────────────────────────────────────────────────")

        print()


if __name__ == "__main__":
    main()
