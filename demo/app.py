import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from rag_demo import (
    DOCS_DIR, CHROMA_DIR, TOP_K, RERANKER_ENABLED, HYBRID_SEARCH_ENABLED, LLM_BACKEND,
    load_documents, chunk_documents, build_index,
    retrieve, rerank, hybrid_retrieve, build_rag_prompt, call_llm,
    retrieve_rag_with_reflection, run_rag_with_reflection,
)
from rag_eval import evaluate_all

st.set_page_config(page_title="RAG 知识库问答", layout="wide")
st.title("📚 RAG 知识库问答演示")

@st.cache_resource(show_spinner="正在构建知识库索引，请稍候...")
def init_index():
    docs = load_documents(DOCS_DIR)

    for doc in docs:
        if doc["filename"].endswith(".pdf"):
            print("\n===== Docling 解析内容预览 =====")
            print(doc["content"][:1000])
            break

    chunks = chunk_documents(docs, 300, 50)

    pdf_chunks = [c for c in chunks if c["source"].endswith(".pdf")][:5]
    for c in pdf_chunks:
        print(f"\n--- chunk {c['chunk_index']} ---")
        print(c["text"])

    embed_model, collection, bm25, chunks = build_index(chunks, CHROMA_DIR)
    return embed_model, collection, bm25, chunks

embed_model, collection, bm25, chunks = init_index()

# ── 历史记录初始化 ────────────────────────────────────────────────
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
                if item.get("eval"):
                    st.caption("评估总分")
                    st.write(f"{item['eval']['overall']:.2f}")

# ── 问答界面 ──────────────────────────────────────────────────────
query = st.chat_input("请输入你的问题...")

if query:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("🔍 检索到的片段")
        results = retrieve_rag_with_reflection(query, embed_model, collection, bm25, chunks)

        for i, r in enumerate(results):
            parts = []
            if RERANKER_ENABLED and "rerank_score" in r:
                parts.append(f"Rerank: {r['rerank_score']:.3f}")
            if HYBRID_SEARCH_ENABLED and "rrf_score" in r:
                parts.append(f"RRF: {r['rrf_score']:.4f}")
            parts.append(f"Embedding: {r['similarity']:.3f}")
            score_label = "  ".join(parts)
            with st.expander(f"片段 {i+1}（{score_label}）"):
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

        # ── 自动评估（仅在有答案时运行）────────────────────────────
        eval_result = {}
        if answer and LLM_BACKEND != "none":
            with st.spinner("评估中..."):
                eval_result = evaluate_all(query, results, answer, call_llm)

            st.divider()
            st.subheader("📊 RAG 评估")

            metrics = [
                ("Context Relevance", "检索片段与问题的相关性",  eval_result.get("context_relevance", {})),
                ("Faithfulness",      "答案忠实于检索内容的程度", eval_result.get("faithfulness", {})),
                ("Answer Relevance",  "答案对问题的回答质量",     eval_result.get("answer_relevance", {})),
            ]

            for name, desc, data in metrics:
                score = data.get("score", 0.0)
                # 根据分数选颜色
                if score >= 0.75:
                    color = "normal"
                elif score >= 0.5:
                    color = "off"
                else:
                    color = "inverse"

                col_name, col_bar, col_score = st.columns([3, 5, 1])
                with col_name:
                    st.caption(desc)
                    st.write(f"**{name}**")
                with col_bar:
                    st.progress(score)
                with col_score:
                    st.metric(label="", value=f"{score:.2f}")

                with st.expander("评估理由"):
                    reason = data.get("reason", "")
                    # 对 Faithfulness 额外显示陈述统计
                    if name == "Faithfulness" and "supported" in data:
                        st.caption(f"有依据的陈述：{data['supported']} / {data['total']}")
                    if name == "Context Relevance" and "useful_count" in data:
                        st.caption(f"有用片段：{data['useful_count']} / {data['total']}")
                    st.write(reason)

            # 总分
            overall = eval_result.get("overall", 0.0)
            st.divider()
            st.metric(label="综合评分（三项均值）", value=f"{overall:.2f}", delta=None)

    # 本次问答存入历史
    st.session_state.history.append({
        "query":   query,
        "results": results,
        "answer":  answer,
        "eval":    eval_result,
    })
