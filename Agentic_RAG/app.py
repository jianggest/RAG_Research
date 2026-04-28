"""
Agentic RAG — Streamlit 前端

职责：UI 展示，不包含任何业务逻辑。
启动：streamlit run app.py
"""

import streamlit as st

import re
from pathlib import Path

from agentic_rag import run
from config import KNOWLEDGE_BASE_DIR
from document_loader import load_documents
from evaluator import get_stats, record_satisfied, record_unsatisfied
from retriever import Retriever


# ── 页面配置 ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Agentic RAG", layout="wide")
st.title("🤖 Agentic RAG")


# ── 知识库初始化（仅首次加载）────────────────────────────────────────────────

@st.cache_resource(show_spinner="正在加载知识库并建立索引...")
def init_retriever() -> tuple[Retriever, list]:
    chunks = load_documents(KNOWLEDGE_BASE_DIR)
    retriever = Retriever(chunks)
    retriever.build_index()
    return retriever, chunks


retriever, all_chunks = init_retriever()


# ── session_state 初始化 ──────────────────────────────────────────────────────

if "result" not in st.session_state:
    st.session_state.result = None
if "history" not in st.session_state:
    st.session_state.history = []
if "eval_rated" not in st.session_state:
    # 当前结果是否已评价；False 表示待评价，提交新问题时自动记为满意
    st.session_state.eval_rated = True


# ── 侧边栏 ────────────────────────────────────────────────────────────────────

with st.sidebar:
    # ── 历史查询记录 ──────────────────────────────────────────────────────────
    st.subheader("🕘 历史查询")

    if not st.session_state.history:
        st.caption("暂无历史记录")
    else:
        st.caption(f"共 {len(st.session_state.history)} 条")
        for i, item in enumerate(st.session_state.history):
            # 截断过长问题作为标题
            label = item["question"] if len(item["question"]) <= 24 else item["question"][:24] + "…"
            with st.expander(label, expanded=(i == 0)):
                st.markdown(item["answer"])
                if st.button("重新查看详情", key=f"history_load_{i}"):
                    st.session_state.result = item["result"]
                    st.rerun()

        if st.button("清空历史", type="secondary"):
            st.session_state.history = []
            st.rerun()

    st.divider()

    # ── 满意度统计 ────────────────────────────────────────────────────────────
    st.subheader("📊 满意度统计")
    stats = get_stats()
    if stats["total"] == 0:
        st.caption("暂无评价记录")
    else:
        rate = stats["satisfaction_rate"]
        st.metric("满意率", f"{rate * 100:.1f}%" if rate is not None else "—")
        col1, col2 = st.columns(2)
        col1.metric("👍 满意", stats["satisfied_count"])
        col2.metric("👎 不满意", stats["unsatisfied_count"])
        if stats["unsatisfied_count"] > 0:
            with st.expander(f"查看 {stats['unsatisfied_count']} 条不满意记录"):
                for rec in reversed(stats["unsatisfied_records"]):
                    st.markdown(f"**{rec['timestamp']}**")
                    st.markdown(f"问题：{rec['question']}")
                    st.markdown(f"回答：{rec['answer'][:100]}…")
                    st.divider()

    st.divider()

    # ── Chunk 调试区 ──────────────────────────────────────────────────────────
    st.subheader("📦 知识库 Chunks")
    st.caption(f"共 {len(all_chunks)} 个 chunk")

    if st.checkbox("展开查看所有 chunks"):
        for chunk in all_chunks:
            label = f"[{chunk['source']}] #{chunk['chunk_index']} {'📊 表格' if chunk['is_table'] else '📝 文本'}"
            with st.expander(label):
                st.text(chunk["text"])


# ── 主区域：问答 ──────────────────────────────────────────────────────────────

question = st.text_input("请输入问题", placeholder="例如：深圳出差住宿费是多少？")
submitted = st.button("提问", type="primary")


_PAGE_IMG_RE   = re.compile(r"__PAGE_IMG__:(\S+)")
_CITED_PAGE_RE = re.compile(r"\[引用页面:([^\]]+)\]")


def _extract_page_img(text: str) -> Path | None:
    """从 chunk 文字中提取 __PAGE_IMG__ 标记的图片路径，不存在则返回 None。"""
    m = _PAGE_IMG_RE.search(text)
    if not m:
        return None
    p = Path(m.group(1).strip())
    return p if p.exists() else None


def _extract_cited_images(answer: str, executed_steps: list) -> list[Path]:
    """
    从 Generator 回答中解析 [引用页面: 第N页, 第M页] 标记，
    返回对应的图片路径列表。
    """
    m = _CITED_PAGE_RE.search(answer)
    if not m:
        return []

    # 提取页码数字，如 "第16页, 第17页" → {16, 17}
    cited_nums: set[int] = set()
    for part in m.group(1).split(","):
        digits = re.search(r"\d+", part)
        if digits:
            cited_nums.add(int(digits.group()))

    # 遍历所有 chunk，找页码匹配的图片路径
    page_imgs: list[Path] = []
    for step in executed_steps:
        for r in step.get("results", []):
            page_m = re.search(r"##\s*第(\d+)页", r["text"])
            if page_m and int(page_m.group(1)) in cited_nums:
                img = _extract_page_img(r["text"])
                if img and img not in page_imgs:
                    page_imgs.append(img)
    return page_imgs


def _render_result(result: dict) -> None:
    """将 RunResult 的各部分渲染到页面上。"""

    # Step 0：查询语义解析
    qs = result.get("query_structure", {})
    if qs:
        with st.expander("🔎 查询语义解析（Step 0）", expanded=False):
            dims = qs.get("dimensions", {})
            cols = st.columns(3)
            for col, (key, label) in zip(cols, [("who", "Who 主体"), ("where", "Where 地点"), ("what", "What 事项")]):
                dim = dims.get(key, {})
                val = (dim.get("value") or "—") + (" *(推断)*" if dim.get("inferred") else "")
                col.metric(label, val)
            if qs.get("expanded") and qs["expanded"] != qs.get("original"):
                st.caption(f"**补全语义：** {qs['expanded']}")
            if qs.get("constraints"):
                st.caption("**约束条件：** " + "、".join(f"{c['type']}:{c['value']}" for c in qs["constraints"]))
            if qs.get("conflicts"):
                st.warning("⚠️ 冲突检测：" + "；".join(qs["conflicts"]))
            st.caption(f"**意图颗粒度：** {qs.get('intent_granularity', '—')}")

    # 调用计划
    with st.expander("📋 调用计划（Planner 输出）", expanded=False):
        plan_data = result.get("plan", {})
        if not plan_data:
            st.info("本次问题触发追问，未生成检索计划。")
        elif "error" in plan_data:
            st.error(f"规划失败：{plan_data['error']}")
        else:
            st.markdown(f"**推理过程：** {plan_data.get('reasoning', '—')}")
            for step in plan_data.get("steps", []):
                dep_note = f" ← 依赖 Step {step['depends_on']}" if step.get("depends_on") else ""
                st.markdown(f"- **Step {step['step_id']}** `{step['skill']}` | 查询：`{step['query']}`{dep_note}")

    # 执行过程
    with st.expander("🔍 执行过程（Executor 输出）", expanded=False):
        if not result.get("executed_steps"):
            st.info("本次问题触发追问，未执行检索。")
        else:
            for step in result["executed_steps"]:
                st.markdown(f"**Step {step['step_id']} — `{step['skill']}`**")
                st.caption(f"实际查询词：{step['query']}")
                if step["results"]:
                    for i, r in enumerate(step["results"][:3], 1):
                        st.text(f"[{i}] 来源: {r['source']} | 相关度: {r['score']}")
                        img_path = _extract_page_img(r["text"])
                        if img_path:
                            st.image(img_path, caption=f"原始页面：{img_path.name}", width="stretch")
                        else:
                            st.code(r["text"], language=None)
                else:
                    st.warning("本步骤未检索到相关内容")
                st.divider()

    # 最终回答（剔除内部页码标记，不暴露给用户）
    display_answer = _CITED_PAGE_RE.sub("", result["answer"]).strip()
    st.markdown("### 💡 回答")
    if result.get("needs_clarification"):
        st.info(display_answer)
    else:
        st.markdown(display_answer)

    # 图片来源页展示：根据 Generator 在回答中标注的 [引用页面: 第N页] 来确定显示哪些图片
    page_images = _extract_cited_images(result["answer"], result.get("executed_steps", []))
    if page_images:
        st.markdown("#### 📄 原始页面")
        cols = st.columns(min(len(page_images), 3))
        for i, img in enumerate(page_images):
            cols[i % 3].image(str(img), caption=img.name, width="stretch")


# ── 问答触发 ──────────────────────────────────────────────────────────────────

if submitted and question.strip():
    # 上一条结果未显式评价时，默认记为满意
    if not st.session_state.eval_rated and st.session_state.result:
        record_satisfied()
    with st.spinner("思考中..."):
        result = run(question.strip(), retriever)
        st.session_state.result = result
        st.session_state.eval_rated = False  # 新结果等待评价
        # 追加到历史记录（最新在前）
        st.session_state.history.insert(0, {
            "question": result["question"],
            "answer": result["answer"],
            "result": result,
        })

# 从 session_state 渲染结果，重跑时（如点击侧边栏）依然保持显示
if st.session_state.result:
    result = st.session_state.result
    st.markdown(f"**❓ 你的问题：** {result['question']}")
    st.divider()
    _render_result(result)

    # ── 满意度评价 ────────────────────────────────────────────────────────────
    st.divider()
    if st.session_state.eval_rated:
        st.caption("✅ 已评价，感谢反馈")
    else:
        st.markdown("**这个回答对你有帮助吗？**")
        col_good, col_bad, _ = st.columns([1, 1, 6])
        if col_good.button("👍 满意", key="btn_satisfied"):
            record_satisfied()
            st.session_state.eval_rated = True
            st.rerun()
        if col_bad.button("👎 不满意", key="btn_unsatisfied"):
            record_unsatisfied(result)
            st.session_state.eval_rated = True
            st.rerun()
