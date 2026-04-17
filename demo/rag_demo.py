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
║  依赖：pip install chromadb sentence-transformers            ║
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

# Embedding 模型
# paraphrase-multilingual-MiniLM-L12-v2：支持中英文，约 400MB，首次运行自动下载
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 文本切块参数
CHUNK_SIZE = 300    # 每个 chunk 的最大字符数
CHUNK_OVERLAP = 50  # 相邻 chunk 的重叠字符数（避免边界信息丢失）

# 检索返回的 Top-K 片段数
TOP_K = 3

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

OLLAMA_MODEL = "gemma4"       # Ollama 使用的模型名称
OPENAI_MODEL = "gpt-4o-mini"    # OpenAI 使用的模型名称
OPENAI_BASE_URL = None          # None = 使用官方地址；填写则使用自定义地址


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 1：加载文档
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_documents(docs_dir: Path) -> list:
    """
    从目录读取所有 .txt 文档。

    真实项目中，这里会替换为更强大的文档解析器，
    支持 PDF、Word、Excel、网页等格式（如 Unstructured.io）。
    """
    docs = []

    if not docs_dir.exists():
        print(f"  ❌ 知识库目录不存在：{docs_dir}")
        sys.exit(1)

    for file_path in sorted(docs_dir.glob("*.txt")):
        content = file_path.read_text(encoding="utf-8")
        docs.append({
            "filename": file_path.name,
            "content": content,
        })
        print(f"  📄 {file_path.name:<30} {len(content):>6} 字")

    if not docs:
        print(f"  ❌ knowledge_base/ 目录中没有找到 .txt 文件")
        sys.exit(1)

    return docs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 2：文本切块（Chunking）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def chunk_documents(docs: list, chunk_size: int, overlap: int) -> list:
    """
    将长文档切成小块（Chunks）。

    【为什么要切块？】
    原因 1：Embedding 模型有输入长度上限（通常 512 tokens），长文档必须切块。
    原因 2：切块后每块语义更集中，检索时能精确定位到相关段落，而不是返回整篇文章。
    原因 3：LLM 的上下文窗口有限，只能把最相关的 3-5 个片段塞进 Prompt。

    【重叠的意义】
    如果不重叠，关键信息可能恰好落在两个 chunk 的边界，被切断。
    重叠 50 字确保边界附近的内容在两个 chunk 中都出现。
    """
    chunks = []

    for doc in docs:
        content = doc["content"]
        start = 0
        chunk_index = 0

        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunk_text = content[start:end].strip()

            if len(chunk_text) > 20:  # 过滤掉太短的碎片
                chunks.append({
                    "id": f"{doc['filename']}__chunk_{chunk_index:03d}",
                    "text": chunk_text,
                    "source": doc["filename"],
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

            # 滑动窗口：下一个 chunk 从 (start + chunk_size - overlap) 开始
            start += chunk_size - overlap

    return chunks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  步骤 3：向量化 + 建立索引
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_index(chunks: list, chroma_dir: str, model_name: str):
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
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"\n  ❌ 缺少依赖库：{e}")
        print("  请运行：pip install chromadb sentence-transformers")
        sys.exit(1)

    print(f"\n  正在加载 Embedding 模型：{model_name}")
    print("  （首次运行需从网络下载模型，约 400MB，请耐心等待）")
    print("  （下载完成后会缓存到本地，后续运行无需重新下载）")

    embed_model = SentenceTransformer(model_name)

    # ChromaDB 持久化客户端（数据保存到本地目录）
    client = chromadb.PersistentClient(path=chroma_dir)

    # 删除已存在的同名集合（方便重新索引）
    try:
        client.delete_collection("rag_demo")
        print("  ℹ️  已清除旧索引，重新构建中...")
    except Exception:
        pass

    collection = client.create_collection(
        name="rag_demo",
        metadata={"hnsw:space": "cosine"},  # 使用余弦相似度
    )

    texts = [c["text"] for c in chunks]
    ids = [c["id"] for c in chunks]
    metadatas = [{"source": c["source"], "chunk_index": c["chunk_index"]} for c in chunks]

    print(f"\n  正在向量化 {len(chunks)} 个文本块...")
    # show_progress_bar=True 会显示进度条
    embeddings = embed_model.encode(texts, show_progress_bar=True, batch_size=32)

    collection.add(
        ids=ids,
        documents=texts,
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
    )

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
    query_vec = embed_model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_vec,
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
                options={"num_ctx": 4096},   # 加这一行
                think = False,
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
    print(f"\n  共加载 {len(docs)} 份文档。")
    print("""
  💡 理解要点：
     这些文档是 LLM 原本"不知道"的私有数据。
     它们不在任何 LLM 的训练集里，直接问 LLM 是不会回答的。
    """)

    # ── 步骤 2：文本切块 ───────────────────────────────────────────
    print_banner("步骤 2 / 3：文本切块（Chunking）")
    chunks = chunk_documents(docs, CHUNK_SIZE, CHUNK_OVERLAP)
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
    embed_model, collection = build_index(chunks, CHROMA_DIR, EMBEDDING_MODEL)
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
