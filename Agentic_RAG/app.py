"""
Agentic RAG — Streamlit 前端

职责：UI 展示，不包含任何业务逻辑。
启动：streamlit run app.py
"""

import streamlit as st

import inspect
import re
from pathlib import Path

from agentic_rag import run
from app_figure_assets import collect_figure_images_from_steps
from config import SHOW_HOME_DEBUG_PANELS, get_knowledge_base_dir, get_rag_profile
from doc_cleaner import clean_documents
from document_loader import convert_pdfs, load_documents
from evaluator import get_stats, record_satisfied, record_unsatisfied
from pdf_figure_extractor import extract_pdf_figures
from retriever import Retriever
from structured_refs import (
    format_reference_label,
    markdown_tables_to_html,
    resolve_structured_reference_detail,
    split_structured_references,
)


# ── 页面配置 ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Agentic RAG", layout="wide")
st.title("🤖 Agentic RAG")

st.markdown(
    """
    <style>
    div[data-testid="stDialog"] {
        width: min(92vw, 1120px);
    }

    div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] {
        max-width: 100%;
        overflow-x: auto;
    }

    div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] table {
        display: block;
        max-width: 100%;
        overflow-x: auto;
        white-space: nowrap;
    }

    div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] th,
    div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] td {
        min-width: max-content;
        vertical-align: top;
    }

    .structured-ref-content {
        max-width: 100%;
        overflow-x: auto;
        padding-bottom: 0.5rem;
    }

    .structured-ref-content p {
        margin: 0 0 0.85rem 0;
        line-height: 1.7;
    }

    .structured-ref-table-wrap {
        width: 100%;
        overflow-x: auto;
        margin: 1rem 0;
        border: 1px solid rgba(49, 51, 63, 0.18);
        border-radius: 0.5rem;
    }

    .structured-ref-table {
        width: max-content;
        min-width: 100%;
        border-collapse: collapse;
        table-layout: auto;
        white-space: nowrap;
    }

    .structured-ref-table th,
    .structured-ref-table td {
        padding: 0.65rem 0.85rem;
        border: 1px solid rgba(49, 51, 63, 0.14);
        text-align: left;
        vertical-align: top;
    }

    .structured-ref-table th {
        background: rgba(49, 51, 63, 0.05);
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 知识库初始化（仅首次加载）────────────────────────────────────────────────

@st.cache_resource(show_spinner="正在加载知识库并建立索引...")
def init_retriever() -> tuple[Retriever, list]:
    kb_dir = get_knowledge_base_dir()
    print(f"[App] RAG_PROFILE={get_rag_profile()} KB={kb_dir}", flush=True)
    chunks = load_documents(kb_dir)
    retriever = Retriever(chunks)
    retriever.build_index()
    return retriever, chunks


retriever, all_chunks = init_retriever()


# ── 知识库文档管理 ─────────────────────────────────────────────────────────────

def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _safe_pdf_upload_target(kb_dir: Path, filename: str) -> tuple[Path | None, str | None]:
    if not filename or not filename.strip():
        return None, "上传失败：文件名不能为空。"

    name = Path(filename).name
    if name != filename or name in {".", ".."}:
        return None, "上传失败：文件名不合法。"
    if Path(name).suffix.lower() != ".pdf":
        return None, "上传失败：仅支持 PDF 文件。"

    kb_root = Path(kb_dir).resolve()
    target = (kb_root / name).resolve()
    try:
        target.relative_to(kb_root)
    except ValueError:
        return None, "上传失败：目标路径不在当前知识库目录内。"
    if target.exists():
        return None, f"上传失败：{name} 已存在，请更换文件名后再上传。"
    return target, None


def process_uploaded_pdf(kb_dir: Path, pdf_path: Path, st_api=st) -> None:
    with st_api.status("正在处理上传文档...", expanded=True) as status:
        status.write("1/4 提取图片")
        extract_pdf_figures(kb_dir, only_pdf_stem=pdf_path.stem)

        status.write("2/4 转换 Markdown")
        convert_pdfs(kb_dir)

        status.write("3/4 清洗文档")
        clean_documents(kb_dir)

        status.write("4/4 建立索引")
        chunks = load_documents(kb_dir)
        refreshed_retriever = Retriever(chunks)
        refreshed_retriever.build_index()

        status.update(label="文档处理完成", state="complete", expanded=False)


def render_knowledge_base_documents_sidebar(
    st_api=st,
    kb_dir: Path | None = None,
    profile: str | None = None,
    process_uploaded_pdf=process_uploaded_pdf,
    clear_retriever_cache=None,
) -> None:
    kb_dir = Path(kb_dir) if kb_dir is not None else get_knowledge_base_dir()
    profile = profile or get_rag_profile()
    clear_retriever_cache = clear_retriever_cache or init_retriever.clear
    uploaded_file = None
    uploader_key = f"kb_pdf_upload_{profile}_{st_api.session_state.get('kb_upload_reset_nonce', 0)}"
    upload_feedback = st_api.session_state.pop("kb_upload_feedback", None)
    pdf_files = sorted([p for p in kb_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"], key=lambda p: p.name.lower())

    with st_api.expander("我的文档库", expanded=False):
        st_api.markdown(
            """
            <style>
            .kb-header-actions {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: 0.18rem;
                min-height: 1.75rem;
            }
            .kb-control-trigger {
                width: 1.45rem;
                height: 1.45rem;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 0.35rem;
                color: #4e5969;
                font-size: 1.05rem;
                line-height: 1;
                user-select: none;
            }
            .kb-control-trigger:hover {
                background: #f2f3f5 !important;
            }
            .kb-upload-toolbar {
                display: flex;
                justify-content: flex-end;
                margin: -0.2rem 0 0.15rem 0;
            }
            div[data-testid="stPopover"] button {
                border: 0 !important;
                border-radius: 0.36rem !important;
                width: 1.45rem !important;
                min-width: 1.45rem !important;
                height: 1.45rem !important;
                min-height: 1.45rem !important;
                padding: 0 !important;
                background: transparent !important;
                color: #4e5969 !important;
                box-shadow: none !important;
                font-size: 1.05rem !important;
                line-height: 1 !important;
            }
            div[data-testid="stPopover"] button:hover {
                background: #f2f3f5 !important;
            }
            .kb-native-doc-list {
                margin-top: 0.35rem;
            }
            .kb-native-doc-list + div[data-testid="stDownloadButton"],
            div[data-testid="stDownloadButton"] {
                margin: 0 0 0.12rem 0 !important;
            }
            div[data-testid="stDownloadButton"] button {
                border: 0 !important;
                border-radius: 0.36rem !important;
                min-height: 1.7rem !important;
                height: 1.7rem !important;
                padding: 0.22rem 0.34rem !important;
                background: transparent !important;
                color: #1f2329 !important;
                box-shadow: none !important;
                width: 100% !important;
                justify-content: flex-start !important;
                text-align: left !important;
                font-size: 0.82rem !important;
                font-weight: 400 !important;
                line-height: 1.2 !important;
            }
            div[data-testid="stDownloadButton"] button:hover {
                background: #f2f3f5 !important;
            }
            div[data-testid="stDownloadButton"] button p,
            div[data-testid="stDownloadButton"] button span {
                color: #1f2329 !important;
                font-size: 0.82rem !important;
                font-weight: 400 !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                white-space: nowrap !important;
                text-align: left !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        info_col, action_col = st_api.columns([0.84, 0.16], vertical_alignment="center")
        with info_col:
            st_api.caption(f"当前知识库：{profile}")
            st_api.caption(f"PDF 文档：{len(pdf_files)} 个")
        with action_col:
            st_api.markdown(
                """
                <div class="kb-header-actions">
                    <span class="kb-control-trigger" title="更多">☷</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st_api.button("+", key=f"kb_open_upload_{profile}", help="点击上传", type="tertiary"):
                st_api.session_state["kb_upload_open"] = True

        if upload_feedback:
            feedback_type, feedback_text = upload_feedback
            if feedback_type == "error":
                st_api.error(feedback_text)
            elif feedback_type == "success":
                st_api.success(feedback_text)
            else:
                st_api.warning(feedback_text)

        if st_api.session_state.get("kb_upload_open", False):
            st_api.markdown('<div class="kb-upload-toolbar"></div>', unsafe_allow_html=True)
            if st_api.button("×", key=f"kb_close_upload_{profile}", help="关闭上传", type="tertiary"):
                st_api.session_state["kb_upload_open"] = False
            if st_api.session_state.get("kb_upload_open", False):
                uploaded_file = st_api.file_uploader(
                    "选择PDF",
                    type=["pdf"],
                    label_visibility="visible",
                    key=uploader_key,
                    help="选择要加入当前知识库的 PDF",
                    width="stretch",
                )

        if not pdf_files:
            st_api.caption("暂无 PDF 文档")
        else:
            st_api.markdown('<div class="kb-native-doc-list"></div>', unsafe_allow_html=True)
            for pdf_path in pdf_files:
                size_label = _format_file_size(pdf_path.stat().st_size)
                st_api.download_button(
                    f"📄 {pdf_path.name}    {size_label}",
                    data=pdf_path.read_bytes(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                    key=f"download_pdf_{profile}_{pdf_path.name}",
                    help="点击下载 PDF",
                )

    if uploaded_file is None:
        return

    target_path, error = _safe_pdf_upload_target(kb_dir, uploaded_file.name)
    if error:
        st_api.session_state["kb_upload_reset_nonce"] = st_api.session_state.get("kb_upload_reset_nonce", 0) + 1
        st_api.session_state["kb_upload_open"] = False
        st_api.session_state["kb_upload_feedback"] = ("error", error)
        st_api.rerun()
        return
    assert target_path is not None

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(bytes(uploaded_file.getbuffer()))
    except Exception as exc:
        st_api.session_state["kb_upload_reset_nonce"] = st_api.session_state.get("kb_upload_reset_nonce", 0) + 1
        st_api.session_state["kb_upload_open"] = False
        st_api.session_state["kb_upload_feedback"] = ("error", f"上传失败：PDF 保存失败：{exc}")
        st_api.rerun()
        return

    try:
        process_uploaded_pdf(kb_dir, target_path, st_api)
    except Exception as exc:
        st_api.session_state["kb_upload_reset_nonce"] = st_api.session_state.get("kb_upload_reset_nonce", 0) + 1
        st_api.session_state["kb_upload_open"] = False
        st_api.session_state["kb_upload_feedback"] = ("error", f"上传失败：文档处理失败：{exc}")
        st_api.rerun()
        return

    clear_retriever_cache()
    st_api.session_state["kb_upload_reset_nonce"] = st_api.session_state.get("kb_upload_reset_nonce", 0) + 1
    st_api.session_state["kb_upload_open"] = False
    st_api.success(f"上传完成：{target_path.name}")
    st_api.rerun()


# ── session_state 初始化 ──────────────────────────────────────────────────────

if "result" not in st.session_state:
    st.session_state.result = None
if "history" not in st.session_state:
    st.session_state.history = []
if "eval_rated" not in st.session_state:
    # 当前结果是否已评价；False 表示待评价，提交新问题时自动记为满意
    st.session_state.eval_rated = True
if "selected_structured_ref" not in st.session_state:
    st.session_state.selected_structured_ref = None


# ── 侧边栏 ────────────────────────────────────────────────────────────────────

with st.sidebar:
    render_knowledge_base_documents_sidebar()
    st.divider()

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
                    st.session_state.selected_structured_ref = None
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

    if SHOW_HOME_DEBUG_PANELS:
        st.divider()

        # ── Chunk 调试区 ──────────────────────────────────────────────────────
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
    return _resolve_page_img_path(m.group(1).strip())


def _resolve_page_img_path(raw_path: str) -> Path | None:
    """
    将 __PAGE_IMG__ 标记解析为当前机器可访问的图片路径。

    兼容两类历史/新格式：
    - 旧格式：生成机器上的绝对路径，如 /home/.../knowledge_base/.page_cache/资产管理流程/page_01.png
    - 新格式：相对知识库路径，如 .page_cache/资产管理流程/page_01.png
    """
    if not raw_path:
        return None

    raw = Path(raw_path)
    candidates = []

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(get_knowledge_base_dir() / raw)
        candidates.append(Path(__file__).parent / raw)

    parts = raw_path.replace("\\", "/").split("/")
    if ".page_cache" in parts:
        cache_idx = parts.index(".page_cache")
        candidates.append(get_knowledge_base_dir() / Path(*parts[cache_idx:]))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


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


def _open_structured_reference_dialog(detail) -> None:
    """展示结构化引用原文；Streamlit 低版本没有 dialog 时自动降级。"""
    dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog:
        dialog_kwargs = {}
        try:
            if "width" in inspect.signature(dialog).parameters:
                dialog_kwargs["width"] = "large"
        except (TypeError, ValueError):
            pass

        @dialog(detail.title, **dialog_kwargs)
        def _show_dialog():
            if detail.source:
                st.caption(f"来源：{detail.source}")
            if detail.found:
                st.markdown(
                    f'<div class="structured-ref-content">{markdown_tables_to_html(detail.content)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning(detail.message)

        _show_dialog()
        return

    with st.expander(f"📖 {detail.title}", expanded=True):
        if detail.source:
            st.caption(f"来源：{detail.source}")
        if detail.found:
            st.markdown(
                f'<div class="structured-ref-content">{markdown_tables_to_html(detail.content)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.warning(detail.message)


def _render_structured_references(refs: list, executed_steps: list) -> None:
    """将结构化引用渲染成可点击按钮。"""
    if not refs:
        st.session_state.selected_structured_ref = None
        return

    st.markdown("#### 结构化引用")
    cols = st.columns(min(len(refs), 4))
    for i, ref in enumerate(refs):
        label = format_reference_label(ref)
        if cols[i % 4].button(label, key=f"structured_ref_{i}_{ref.raw}"):
            st.session_state.selected_structured_ref = i

    selected = st.session_state.get("selected_structured_ref")
    if selected is not None and 0 <= selected < len(refs):
        detail = resolve_structured_reference_detail(
            refs[selected],
            executed_steps,
            get_knowledge_base_dir(),
        )
        _open_structured_reference_dialog(detail)


def _render_result(result: dict) -> None:
    """将 RunResult 的各部分渲染到页面上。"""

    if SHOW_HOME_DEBUG_PANELS:
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
    display_answer, structured_refs = split_structured_references(display_answer)
    st.markdown("### 💡 回答")
    if result.get("needs_clarification"):
        st.info(display_answer)
    else:
        st.markdown(display_answer)
    _render_structured_references(structured_refs, result.get("executed_steps", []))

    # Figure 展示：根据检索结果 metadata.figure_refs 解析 figures.json 并显示对应 PNG。
    figure_images = collect_figure_images_from_steps(
        get_knowledge_base_dir(),
        result.get("executed_steps", []),
    )
    if figure_images:
        st.markdown("#### 🖼️ 相关 Figure")
        cols = st.columns(min(len(figure_images), 3))
        for i, fig in enumerate(figure_images):
            caption = fig.figure_id
            if fig.caption:
                caption += f" — {fig.caption}"
            cols[i % 3].image(str(fig.path), caption=caption, width="stretch")

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
    with st.status("处理中...", expanded=False) as status:
        def _update_progress(msg: str):
            status.update(label=msg)
        result = run(question.strip(), retriever, on_progress=_update_progress)
        status.update(label="完成", state="complete")
        st.session_state.result = result
        st.session_state.eval_rated = False  # 新结果等待评价
        st.session_state.selected_structured_ref = None
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
