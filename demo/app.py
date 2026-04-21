import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from rag_demo import (
    DOCS_DIR, CHROMA_DIR, TOP_K,
    load_documents, chunk_documents, build_index,
    retrieve, build_rag_prompt, call_llm, retrieve_rag_with_reflection, run_rag_with_reflection,
)

st.set_page_config(page_title="RAG 知识库问答", layout="wide")
st.title("📚 RAG 知识库问答演示")

@st.cache_resource(show_spinner="正在构建知识库索引，请稍候...")
def init_index():
    docs = load_documents(DOCS_DIR)

    # ── 调试：打印第一个 PDF 的 Docling 解析内容预览 ──────────────
    for doc in docs:
        if doc["filename"].endswith(".pdf"):
            print("\n===== Docling 解析内容预览 =====")
            print(doc["content"][:1000])
            break

    chunks = chunk_documents(docs, 300, 50)

    # ── 调试：打印前 5 个来自 PDF 的 chunk ────────────────────────
    pdf_chunks = [c for c in chunks if c["source"].endswith(".pdf")][:5]
    for c in pdf_chunks:
        print(f"\n--- chunk {c['chunk_index']} ---")
        print(c["text"])

    embed_model, collection = build_index(chunks, CHROMA_DIR)
    return embed_model, collection

embed_model, collection = init_index()

# ── 历史记录初始化 ────────────────────────────────────────────────
# 每条记录格式：{"query": str, "results": list, "answer": str}
if "history" not in st.session_state:
    st.session_state.history = []

# ── 侧边栏：历史记录列表 ──────────────────────────────────────────
with st.sidebar:
    st.subheader("🕘 历史问答记录")
    if not st.session_state.history:
        st.caption("暂无记录")
    else:
        if st.button("🗑️ 清空历史", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        for i, item in enumerate(reversed(st.session_state.history)):
            idx = len(st.session_state.history) - i
            with st.expander(f"Q{idx}：{item['query'][:30]}{'...' if len(item['query']) > 30 else ''}"):
                st.caption("问题")
                st.write(item["query"])
                st.caption("回答")
                st.write(item["answer"] or "（无 LLM 回答）")

# ── 问答界面 ──────────────────────────────────────────────────────
query = st.chat_input("请输入你的问题...")

if query:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("🔍 检索到的片段")
        # results = retrieve(query, embed_model, collection, TOP_K)
        results = retrieve_rag_with_reflection(query, embed_model,collection)
       
        for i, r in enumerate(results):
            with st.expander(f"片段 {i+1}（相似度: {r['similarity']:.3f}）"):
                st.write(r["text"])
                st.caption(f"来源：{r['source']}")

    with col2:
        st.subheader("💬 回答")
        prompt = build_rag_prompt(query, results)
        with st.spinner("生成中..."):
            answer = call_llm(prompt)
        if answer:
            st.markdown(answer)
        else:
            st.info('当前 LLM_BACKEND = "none"，请修改 rag_demo.py 顶部配置以启用 LLM。')

    # 本次问答存入历史
    st.session_state.history.append({
        "query": query,
        "results": results,
        "answer": answer,
    })
