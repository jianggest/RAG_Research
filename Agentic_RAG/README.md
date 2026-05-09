# Agentic RAG

基于 **Skill / Tool Use** 架构的检索增强生成系统。相比基础 RAG，核心差异在于引入了 LLM 驱动的规划层——系统会先"思考应该检索什么、用什么方式检索"，再执行多步骤的检索链，最终综合所有结果生成回答。

## 两类知识库

工程当前同时支持两类形态完全不同的知识：

| 类别 | 文档形态 | 用户问法 | 关键挑战 | 代表 Skill |
|------|----------|---------|----------|-----------|
| **企业内部知识库** | 中文流程文档：报销、考勤、IT、行政、资产 | 语义化（"怎么申请笔记本"） | 跨域污染、伞形概念、地区分类 | `search_attendance` / `search_admin_guide` / `search_it_guide` / `search_asset_management` / `search_expense_reimbursement` |
| **英文规格书 / 协议规格书** | DLPC3436 datasheet、HDMI 1.4/2.0/2.1b、DVI 1.0、EIA-CEA-861-D | 精确术语（"VDD_18 电压范围"、"MOSC timing"） | 中英混合、数值忠实度、跨章节合成、表格 + 脚注 + 定义跳转 | `search_datasheet` |

两类场景共用同一套 Planner / Executor / Generator 编排，但在 chunk schema、归一化、索引、generator prompt、retrieval planner 上做了**子系统级**的分化（详见后文「Datasheet RAG 子系统」一节）。

> v3.1：知识库已拆成 `knowledge_base/enterprise` 与 `knowledge_base/datasheet` 两个 profile。运行时通过 `RAG_PROFILE=enterprise|datasheet|all` 选择加载范围；持久化 Chroma、collection name、增强问题缓存、页面图片缓存均随 profile 隔离，避免企业制度与规格书互相污染。

---

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动前端（Ollama 需提前运行）
streamlit run app.py
#后台启动
nohup streamlit run app.py --server.address 0.0.0.0 --server.port 8501 > demo.log 2>&1 &

# v3.1：按 profile 离线构建/更新持久化索引，再启动前端
# 可选：enterprise / datasheet / all；默认见 config.py 的 RAG_PROFILE
RAG_PROFILE=datasheet .venv/bin/python tasks/run_persistent_index.py >> demo.log 2>&1
RAG_PROFILE=datasheet streamlit run app.py --server.port 8501

# 运行单元测试
pytest tests/ -v --ignore=tests/integration

# 运行集成测试（需要真实 LLM，耗时较长）
pytest tests/integration/ -v -m integration
```

> 修改 `config.py` 可切换模型、调整分块大小、检索 Top-K 等参数，无需改代码逻辑。

---

## 模型配置

系统使用两类模型，均通过 `config.py` 配置：

### Embedding 模型（向量化）

| 配置值 | 模型 | 说明 |
|--------|------|------|
| `"BAAI/bge-m3"` | BGE-M3 ✅ 推荐 | 多语言模型，中文语义理解强，表格内容向量质量显著优于默认模型 |
| `"default"` | all-MiniLM-L6-v2 | ChromaDB 内置，无需额外安装，英文为主，中文效果较差 |

切换 `config.py` 中的 `EMBEDDING_MODEL` 即可。首次使用 BGE-M3 会自动下载模型（约 570MB），需提前安装：

```bash
pip install sentence-transformers
```

### LLM 模型（推理与生成）

通过 `LLM_BACKEND` 选择后端：

| `LLM_BACKEND` | 说明 |
|---------------|------|
| `"ollama"` | 本地推理，无外部依赖，适合内网部署。模型名通过 `OLLAMA_MODEL` 配置 |
| `"openai"` | 调用 OpenAI 兼容协议网关（含自建反向代理）。通过 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` 配置 |
| `"none"` | 跳过 LLM 调用，仅用于检索调试 |

**Ollama 可选模型：**

| `OLLAMA_MODEL` | 说明 |
|----------------|------|
| `"qwen3.6:35b-a3b-q4_K_M"` | ✅ 推荐，支持视觉理解，对中文提示词理解更准确，分类推断误判率显著降低 |
| `"gemma4"` | 备选，需设置 `think=False` |

> ⚠️ `OPENAI_API_KEY` 当前以明文形式存放在 `config.py`，**不要将含密钥的 `config.py` 提交到公共仓库**。建议改为 `os.getenv("OPENAI_API_KEY")` 读取（已记录为待办 R-5）。

---

## 架构概览

系统由两个独立阶段组成：**文档预处理**（离线，一次性）和**查询响应**（在线，每次提问触发）。

### 阶段一：文档预处理（离线）

```
knowledge_base/
│
├── 普通文档（.pdf / .md / .txt）
│       │
│       ▼
│  ┌─────────────────────────────────────────────────────────────────┐
│  │ Step 1: PDF 转 Markdown                                          │
│  │ document_loader.convert_pdfs()                                   │
│  │ Docling 将 PDF 转为结构化 .md，保留表格；同名 .md 已存在则跳过       │
│  │ v3.1：只扫描当前 RAG_PROFILE 对应的 knowledge_base/<profile>/ 目录 │
│  └──────────────────────────────┬──────────────────────────────────┘
│                                 │
│                                 ▼
│  ┌─────────────────────────────────────────────────────────────────┐
│  │ Step 2: 文档清洗                                                  │
│  │ doc_cleaner.clean_documents()                                    │
│  │ 去除页眉/页脚/版本号等污染内容，输出 _clean.md；已存在则跳过          │
│  └──────────────────────────────┬──────────────────────────────────┘
│                                 │
│                                 ▼
│  ┌─────────────────────────────────────────────────────────────────┐
│  │ Step 3: 表格感知分块                                              │
│  │ document_loader.chunk_markdown()                                 │
│  │ 按 Markdown 标题分节，表格块保持完整，每个 chunk 携带节标题作为上下文  │
│  └──────────────────────────────┬──────────────────────────────────┘
│                                 │
└─────────────────────────────────┤
                                  │
├── 图片型文档（PPT 转 PDF）
│       │
│       ▼
│  ┌─────────────────────────────────────────────────────────────────┐
│  │ Step 1: 视觉提取（手动运行一次）                                   │
│  │ python run_vision_extract.py                                     │
│  │ 逐页截图 → Ollama 视觉模型提取文字 → 每页嵌入 __PAGE_IMG__ 标记     │
│  │ 输出覆盖 _clean.md，后续流程与普通文档相同                           │
│  └──────────────────────────────┬──────────────────────────────────┘
│                                 │
└─────────────────────────────────┤
                                  │
                                  ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ Step 4: 向量化 + BM25 索引                                       │
     │ retriever.build_index()                                          │
     │ BGE-M3 Embedding → ChromaDB（含 original_text 存入 metadata）    │
     │ BM25 基于原始文本构建本地倒排索引                                   │
     │ v3.1：Chroma 持久化到 knowledge_base/<profile>/chroma_db，按 hash 增量跳过 │
     └──────────────────────────────┬──────────────────────────────────┘
                                    │
                                    ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ Step 5: 增强索引                                                  │
     │ index_augmenter.generate_augmented_entries()                     │
     │ LLM 为每个 chunk 生成 8-10 个用户视角问题                          │
     │ 问题文本向量化存入 ChromaDB，original_text 存入对应 metadata        │
     │ 命中增强条目时，从 metadata 取回原始 chunk 返回                     │
     │                                                                  │
     │ 缓存：.question_cache.json 存储 chunk_MD5 → 问题列表               │
     │       避免重复调用 LLM；文档内容变更时 MD5 失效自动重新生成           │
     └──────────────────────────────────────────────────────────────────┘
```

v3.1 profile 隔离路径：

```text
RAG_PROFILE=enterprise → knowledge_base/enterprise → knowledge_base/enterprise/chroma_db → agentic_rag_enterprise / *_enterprise_block / *_enterprise_row
RAG_PROFILE=datasheet  → knowledge_base/datasheet  → knowledge_base/datasheet/chroma_db  → agentic_rag_datasheet / *_datasheet_block / *_datasheet_row
RAG_PROFILE=all        → knowledge_base            → knowledge_base/chroma_db            → agentic_rag / agentic_rag_block / agentic_rag_row（仅调试/兼容）
```

> 普通文档预处理在 `app.py` 启动时自动执行（已有缓存则跳过）。
> 图片型 PDF 需提前手动运行 `python run_vision_extract.py`，完成后重启 app 重建索引。

---

### 阶段二：查询响应（在线）

```
用户提问
    │
    ▼
┌─────────────────────────────┐
│  Step 0: QueryUnderstanding  │  语义解析：维度补全 / 约束识别 / 意图判断 / 冲突检测
└──────────────┬──────────────┘
               │ QueryStructure（含 Who / Where / What、约束、意图、冲突）
               ▼
┌─────────────────────────────┐
│     Step 1: Planner          │  LLM 读取 Skill 列表，生成结构化 JSON 检索计划
└──────────────┬──────────────┘
               │ PlanResult（steps[]）
               ▼
┌─────────────────────────────┐
│     Step 2: Executor         │  按依赖顺序执行每个 Skill，处理 <step_N_result> 占位符
└──────────────┬──────────────┘
               │ ExecutedStep[]（含检索结果）
               ▼
┌─────────────────────────────┐
│     Step 3: Generator        │  LLM 整合所有检索结果，生成最终回答
└──────────────┬──────────────┘
               │
               ▼
            最终回答
```

---

## 目录结构

```
Agentic_RAG/
├── app.py                      # Streamlit 前端（历史查询、满意度评价、图片展示）
├── agentic_rag.py              # 主流程编排（RunResult）
├── query_understanding.py      # 查询语义解析（QueryStructure，含 domain 字段：enterprise_policy / technical_datasheet）
├── planner.py                  # 检索计划生成（含 datasheet 路由消歧规则）
├── executor.py                 # Skill 执行引擎
├── generator.py                # 回答生成（含 _ANSWER_PROMPT_TEMPLATE / _TECHNICAL_DATASHEET_PROMPT_TEMPLATE 两套 prompt + reading_closure / 结构化引用注入）
├── retriever.py                # 检索器（向量 / BM25 / 混合 + datasheet 双层索引 + bundle planner + reading_closure 构建）
├── index_augmenter.py          # 增强索引生成（datasheet chunk 自动跳过，避免参数表生成低质量增强问题）
├── document_loader.py          # 文档加载、清洗与表格感知分块（chunk 含 is_datasheet/index_kind/normalized_text/entity_tokens）
├── doc_cleaner.py              # 文档清洗：流程文档去除页眉/页脚；datasheet 走保守清洗，保留 NOTE / 脚注 / 表注
├── evaluator.py                # 满意度评价（本地持久化，统计满意/不满意记录）
├── pdf_vision_loader.py        # 图片型 PDF 视觉解析（逐页截图 → Ollama 视觉模型提取文字）
├── pdf_vision_qa.py            # PDF 视觉直答（图片缓存 + 看图回答，供前端展示原始页面）
├── run_vision_extract.py       # 一次性脚本：视觉提取结果写入 _clean.md（图片型 PDF 预处理）
├── test_pdf_render.py          # 调试脚本：PDF 页面渲染为图片，验证截图清晰度
├── llm.py                      # LLM 调用封装
├── utils.py                    # 工具函数（实体抽取、表格清洗、LLM 分类）
├── config.py                   # 全局配置项（RAG_PROFILE、profile 路径、collection 名、DATASHEET_SOURCES 白名单）
│
├── skills/                     # 可插拔检索技能
│   ├── __init__.py             # 动态加载器（扫描 search_*.py）
│   ├── search_attendance.py              # 考勤/休假/福利查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_expense_reimbursement.py   # 报销复合技能（配置规则分类 → LLM兜底 → 费用标准 + 结论 chunk + 域隔离）
│   ├── search_admin_guide.py             # 行政指引查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_it_guide.py                # IT 指引查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_asset_management.py        # 资产管理流程查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_datasheet.py               # 芯片/协议规格书查询（structure-driven bundle planner + staged retrieval fallback）
│   └── search_example.py                 # Skill 编写模板（不被加载）
│
├── scripts/
│   └── regen_datasheet_structure.py      # 离线生成 datasheet structure digest（section_tree / table_catalog / row_index / entity_inventory / alias_graph）
│
├── config/
│   └── region_classification.json        # 报销地区分类规则（A/B/C 类城市清单）
│
├── knowledge_base/             # v3.1 profile 化知识库文档
│   ├── enterprise/             # 企业内部制度 profile
│   │   ├── 报销相关.md / 报销相关_clean.md
│   │   ├── 考勤&休假&福利指引20251023_clean.md
│   │   ├── OA新员工-行政指引2025.7.7 .md / _clean.md
│   │   ├── 【光峰】新员工IT指引.md / _clean.md
│   │   ├── 资产管理流程.pdf / 资产管理流程.md / 资产管理流程_clean.md
│   │   ├── .page_cache/        # 当前 profile 的 PDF 页面图片缓存
│   │   ├── .question_cache.json# 当前 profile 的增强索引问题缓存
│   │   └── chroma_db/          # 当前 profile 的 Chroma 持久化索引
│   ├── datasheet/              # 英文规格书 / 协议规格书 profile
│   │   ├── dlpc3436.pdf / dlpc3436.md / dlpc3436_clean.md
│   │   ├── DVI_1.0.pdf / DVI_1.0.md / DVI_1.0_clean.md
│   │   ├── .structure/         # Phase 1 结构化 digest（datasheet 专用）
│   │   │   └── dlpc3436.structure.json
│   │   └── chroma_db/          # datasheet profile 的 Chroma 持久化索引
│
├── evaluation/                 # Datasheet baseline 评估资产（详见「Datasheet RAG 子系统」一节）
│   ├── datasheet_baseline_cases.json          # 15 个回归 case（parameter / enumeration / connection / support / state / adversarial）
│   ├── datasheet_baseline_report.md
│   └── .datasheet_*_metrics.json              # retrieval baseline / full baseline / judge sample / real generator sample 指标
│
├── tests/                      # 测试
│   ├── 流程类回归
│   │   ├── test_chunking.py / test_executor.py / test_planner.py / test_retriever.py / test_knowledge_base_profile.py
│   │   ├── test_query_understanding.py / test_utils.py / test_generator.py
│   │   ├── test_search_expense_reimbursement.py
│   │   └── integration/test_llm_classify_reasoning.py
│   └── datasheet 回归（17 个）
│       ├── test_dlpc3436_document_evidence.py / test_datasheet_pdf_pipeline.py
│       ├── test_datasheet_baseline.py / test_datasheet_full_baseline.py
│       ├── test_datasheet_retrieval_baseline.py / test_datasheet_staged_retrieval.py
│       ├── test_datasheet_remaining_staged_retrieval.py
│       ├── test_datasheet_source_metadata.py / test_datasheet_phase2_phase3_phase6.py
│       ├── test_datasheet_dual_index.py / test_datasheet_structure_digest.py
│       ├── test_datasheet_structure_planner.py
│       ├── test_search_datasheet.py / test_dlpc_datasheet_retrieval.py / test_dlpc_agentic_run.py
│       └── test_specification_reading_path.py
│
├── tasks/
│   ├── run_persistent_index.py             # v3.1：按 RAG_PROFILE 离线构建/增量更新 Chroma 持久化索引
│   ├── datasheet_rag_plan.md               # Datasheet RAG Phase 0~7 演进计划
│   ├── datasheet_rag_status.md             # Datasheet RAG 当前完成状态
│   ├── large_kb_indexing_scalability.md    # v3.0 大知识库索引可扩展性记录
│   ├── known_risks.md                      # 已识别风险与待办（R-1 ~ R-8）
│   └── phase{1_core,2_retrieval,3_robustness,3_entity_understanding}.md
│
├── DLPC3436_CHANGELOG.md       # DLPC3436 datasheet 修改记录（每次改动追加）
├── DLPC3436_DELIVERY_REPORT.md # DLPC3436 RAG 闭环交付验证报告
├── docs_dlpc3436_datasheet_rag_plan.md     # DLPC3436 详细技术方案
├── CODEX_PROJECT_UNDERSTANDING.md          # 工程整体理解笔记
├── PLAN.md                     # v1.0 → v2.0 架构演进
├── pytest.ini
└── requirements.txt
```

---

## 核心模块说明

## 知识库文档说明

```
PDF → Docling 转 .md（同名 .md 已存在则跳过）
    ↓
  .md → doc_cleaner 清洗为 _clean.md（已存在则跳过）
    ↓
  加载时优先读 _clean.md，不存在时回退原文件

图片型 PDF（PPT转换）→ run_vision_extract.py 视觉提取 → _clean.md（含 __PAGE_IMG__ 标记）
```

### 图片型 PDF 处理（视觉 RAG）

针对 PPT 转 PDF 等图片型文档，Docling 文字提取丢失严重，采用视觉提取方案：

```
资产管理流程.pdf
    ↓ run_vision_extract.py（一次性运行）
    ↓ pdf_vision_loader：逐页截图 → Ollama 视觉模型提取文字
    ↓ 每页插入图片路径标记 __PAGE_IMG__:/path/page_XX.png
    ↓
资产管理流程_clean.md（含文字内容 + 图片标记）
    ↓ 正常建索引（文字用于 BM25/向量检索）

查询命中时：
    Generator 在回答末尾标注 [引用页面: 第N页]
    app.py 解析页码 → st.image() 展示对应原始页面图片
    显示答案时自动剔除 [引用页面: ...] 标记
```

PDF 页面图片缓存到 `knowledge_base/.page_cache/<pdf名>/`，首次调用自动生成，后续复用。

### QueryUnderstanding

将自然语言问题结构化为机器可读的 `QueryStructure`，提取：

| 字段 | 说明 | 示例 |
|------|------|------|
| `dimensions` | Who / Where / What 三维度 | `where: 深圳, what: 住宿费` |
| `constraints` | 时间/场景约束 | `{type: 时间约束, value: 2023年后}` |
| `intent_granularity` | 精确事实 / 总结性 | 影响 Generator 回答风格 |
| `needs_clarification` | 是否需要追问 | `True` 时短路，直接返回追问文案 |

### Planner

接收 Skill 描述列表和 QueryStructure，通过 LLM 生成 JSON 格式的检索计划：

```json
{
  "steps": [
    {"step_id": 1, "skill": "search_expense_reimbursement", "query": "深圳出差住宿费标准", "depends_on": []}
  ]
}
```

`<step_N_result>` 占位符由 Executor 在执行前替换为前置步骤的关键实体摘要。

> 注：报销类查询不再需要拆分为"先分类、再查标准"两步，`search_expense_reimbursement` 内部已一条龙完成分类推断 → 费用标准检索。

#### Planner 路由消歧规则

`_PLAN_PROMPT_TEMPLATE` 内嵌了多条防止 Skill 误选的规则：

- **规则 8 — 系统名 vs 业务动作**：query 同时含『系统名』（OA / HR / ERP / PLM / JIRA）和『业务动作』（出差申请 / 报销审批 / 请假）时，按业务动作选 Skill，不被系统名锚定。反例 TE25：『OA系统出差申请流程』应选 `search_expense_reimbursement` 而非 `search_it_guide`。
- **规则 9 — datasheet / 芯片手册**：含 DLPC、datasheet、芯片型号、oscillator、clock、PLL、timing、electrical characteristics、MHz/ns/ppm/V/mA 等硬件规格词时，优先选 `search_datasheet`，不要把 DLPC 文档误按企业制度 Skill 处理。

#### QueryUnderstanding domain 字段

`QueryStructure` 在 `dimensions / entities / constraints / intent_granularity` 之外，还携带 `domain` 字段（`enterprise_policy` / `technical_datasheet`）。`_looks_technical_datasheet_query()` 在解析阶段命中规格书关键词时把 domain 设为 `technical_datasheet`，让技术 query 跳过企业政策的 Where 澄清逻辑（避免追问"您要查询的是哪个城市"），并在 Generator 阶段切换到技术 datasheet prompt。

### Skills（可插拔检索技能）

每个 Skill 是一个独立的 `search_*.py` 文件：

```python
SKILL_META = {
    "name": "search_xxx",
    "description": "Planner 用于选择 Skill 的描述文字",
    "retrieval_method": "vector" | "bm25" | "hybrid" | "composite",
}

def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    ...
```

新增 Skill 只需在 `skills/` 目录下创建文件，系统自动加载，无需修改主程序。

#### 当前内置 Skill

| Skill | 触发场景 | 内部检索链 |
|-------|---------|-----------|
| `search_admin_guide` | 行政办公指引（着装/会议室/快递/班车/差旅票务/印章/档案等） | 伞形扩写 → hybrid（域隔离）→ 表格重排 |
| `search_it_guide` | IT 指引（电脑配备/网络/系统账号/信息安全/IT 联系方式等） | 伞形扩写 → hybrid（域隔离）→ 表格重排 |
| `search_attendance` | 考勤/休假/福利政策 | 伞形扩写 → hybrid（域隔离）→ 表格重排 |
| `search_asset_management` | 资产管理流程（固定资产/非固资/盘点/调拨/报废等） | 伞形扩写 → hybrid（域隔离）→ 表格重排 |
| `search_expense_reimbursement` | 报销费用查询（复合） | 配置规则分类 → LLM 兜底分类 → 向量检索费用标准 → 表格优先重排 → 反思自检（域隔离） |
| `search_datasheet` | 芯片 datasheet / 协议规格书（DLPC、HDMI、DVI、CEA-861-D），覆盖 timing/electrical characteristics/oscillator/PLL/pin connection/具体符号数值 | structure-driven bundle planner（row evidence + block context + section/table/row/source_line）→ fallback：技术关键词扩写 + hybrid（域自动发现+隔离）+ staged retrieval 规则 + 表格/实体加权重排 |

#### 地区分类推断机制

`search_expense_reimbursement` 内部采用**配置规则优先 + LLM 兜底**方案，不再依赖 BM25 检索分类规则，也避免把关键地区归类完全交给 LLM 常识判断：

```
config/region_classification.json
    ↓ 先做确定性地区分类
    ↓ 命中则直接输出分类结论
    ↓ 未命中时，将配置规则转换为上下文 chunk
    ↓
LLM 兜底判断（llm_classify_region）
    ↓ 补充处理配置未覆盖的地名
    ↓
输出分类结论（如"境内A类"、"境外C类"）
    ↓
构造费用标准查询词 → 向量检索
```

示例：
- 深圳 → 境内A类（规则中明确列出）
- 南昌 → 境内B类（规则中列为省会城市）
- 揭阳 → 境内C类（排除法，不在 A/B 类列表中）
- 德国 → 境外A类（规则中列为欧洲）
- 香港 → 境外C类（规则中列为港澳台）

> 分类推断在 Executor 阶段完成，结论以 `is_conclusion=True` 的 chunk 形式返回，Generator 直接读取结论，无需重新推断。

### 增强索引（index_augmenter）

对每个 chunk 调用 LLM 生成 8-10 个用户视角的问题，问题向量作为检索入口，原始 chunk 作为返回内容。解决用户提问用语与文档术语不一致的语义鸿沟。

生成结果持久化到当前 profile 的 `knowledge_base/<profile>/.question_cache.json`，缓存键为 chunk MD5，重启直接复用。`config.py` 中 `AUGMENT_QUESTIONS = True` 开启。

> v3.1 备注：`AUGMENT_QUESTIONS` 当前可开启；datasheet chunk 会被 `_should_augment()` 强制跳过，企业 profile 可继续使用增强问题。大 KB 恢复全量增强时建议先通过 `AUGMENT_MAX_CHUNKS` 限流，或改为离线/后台增量任务。

这一步很关键，能够让Chunk更容易的和自然语言对接上。

### v3.0 大知识库索引持久化与增量构建

v3.0 解决新增大规格书后页面长时间停留在“加载知识库”的问题。核心变化：

1. **分批写入 Chroma**：`INDEX_BATCH_SIZE = 64`，每批打印范围式进度，避免一次性 add 数千 chunks 时长时间无日志。
2. **Chroma 持久化**：`PERSIST_CHROMA_INDEX = True`，索引写入当前 profile 的 `knowledge_base/<profile>/chroma_db/`，重启不再清空 collection。
3. **chunk hash 增量跳过**：基于 `source + chunk_index + normalized_text/text` 生成稳定 ID，已存在 chunk 不再重复 embedding。
4. **离线构建入口**：首次大规模索引建议先运行 `tasks/run_persistent_index.py`，再启动 Streamlit。
5. **启动期增强可控**：`AUGMENT_QUESTIONS` / `AUGMENT_MAX_CHUNKS` 控制增强问题生成；datasheet chunk 仍强制跳过自然语言增强，避免污染精确技术索引。
6. **v3.1 profile 隔离**：`RAG_PROFILE` 决定 source dir、Chroma persist dir、collection names、question cache、page cache，企业制度与规格书不再共享运行时路径。

首次/增量构建命令：

```bash
RAG_PROFILE=datasheet .venv/bin/python tasks/run_persistent_index.py >> demo.log 2>&1
# 或：RAG_PROFILE=enterprise .venv/bin/python tasks/run_persistent_index.py >> demo.log 2>&1
```

验证命令：

```bash
.venv/bin/python -m pytest tests/test_retriever.py -q
curl -sS -D - -o /tmp/agentic_rag_8501.html http://127.0.0.1:8501/
grep -Ei 'traceback|exception|error|failed|runtimeerror|module' demo.log
```

本次验证结果：

```text
24 passed in 0.05s
[IndexRunner] start large KB persistent indexing profile=datasheet kb=.../knowledge_base/datasheet
[IndexRunner] loaded chunks=6270
[Retriever] 原始新增索引建立完成，共 6270 条；总 chunks 6270 条
knowledge_base/datasheet/chroma_db = 已生成持久化索引
HTTP/1.1 200 OK
[Retriever] 原始跳过已存在索引：6270/6270
[Retriever] 原始索引无新增，共 6270 条
[Retriever] 原始新增索引建立完成，共 0 条；总 chunks 6270 条
```

v3.1 profile 隔离新增回归：`tests/test_knowledge_base_profile.py` 覆盖 profile 子目录选择、collection name 加 profile 后缀、question cache 与 `chroma_db` 指向当前 profile。

处理过程记录见：`tasks/large_kb_indexing_scalability.md`。

注意：持久化模式下已有 collection 不要再次传入新的 `embedding_function`，否则 Chroma 会报 embedding function conflict；当前 `retriever.py` 已按持久化/非持久化模式区分处理。

### Datasheet RAG 子系统

针对 `dlpc3436.pdf` / HDMI / DVI / CEA-861-D 这类**英文规格书**，工程内嵌了一套独立子系统。设计原则：**不模仿 NotebookLM 的回答风格，要模仿它的文档理解路径**——围绕 section / table / row / entity 做多跳检索，避免每来一个新名词就往 `_CONCEPT_MAP` 加补丁。

#### 与流程文档的关键差异

| 维度 | 中文流程文档 | datasheet / 协议规格书 |
|---|---|---|
| 用户问法 | 语义化 | 精确符号、单位 |
| 关键事实位置 | 段落 | 表格行 + 表注 + 跨章节定义 |
| 关键陷阱 | 跨域污染 | 数值改写、跨章节合成、`I 2 C / IIC / I²C` 同义形态、TI internal use 误读 |
| 召回失败模式 | 用语术语错位 | 单 chunk 信息不全（NotebookLM 标杆查询揭示需要跨 700+ 行合成） |

#### Phase 0~7 演进路线

详见 `tasks/datasheet_rag_plan.md` / `tasks/datasheet_rag_status.md`。当前 datasheet 大范围回归 `64 passed`：

| Phase | 内容 | 关键产物 |
|---|---|---|
| **Phase 0** | 裸 baseline 量化 | `evaluation/datasheet_baseline_cases.json`（15 cases）+ baseline report |
| **Phase 0.5** | datasheet 专用 generator prompt 雏形 | `_TECHNICAL_DATASHEET_PROMPT_TEMPLATE` |
| **Phase 1** | 文档结构化 digest（离线规则） | `knowledge_base/datasheet/.structure/dlpc3436.structure.json`（section_tree / table_catalog / row_index / entity_inventory / alias_graph） |
| **Phase 2** | 双层物理索引（block + row） | `agentic_rag_<profile>_block` / `agentic_rag_<profile>_row` 两个 collection |
| **Phase 3** | 索引 + 查询双向 normalization | `normalize_datasheet_text()` |
| **Phase 4** | structure-driven bundle planner | `plan_datasheet_evidence_bundle()` 输出结构化 evidence bundle |
| **Phase 5** | datasheet generator 结构化引用 | 回答末尾 `[Section: ...; Table: ...; Row: ...; line: ...]` |
| **Phase 6** | datasheet 跳过 AUGMENT_QUESTIONS | `index_augmenter._should_augment()` 对 `is_datasheet=True` 返回 False |
| **Phase 7** | 规格书 reading path 闭环（核心） | `build_specification_reading_closure()` |

#### 核心机制 1：文本归一化

`retriever.normalize_datasheet_text()` 在索引和查询时双向使用，统一同义形态：

```
I 2 C / I²C / IIC          →  I2C
GPIO08 / GPIO 08 / GPIO_08 →  GPIO_08
TSTPT5 / TSTPT_5           →  TSTPT_5
PLL REFCLK I               →  PLL_REFCLK_I
+/- 200 PPM / ± 200 PPM    →  ±200 ppm
f clk / fclk               →  f_clk
```

`extract_datasheet_entity_tokens()` 同时抽出高信号实体 token（`MOSC` / `PLL_REFCLK_I` / `GPIO_08` / `IIC0_SCL` / `HOST_IRQ` / `VCC_FLSH` 等）作为 BM25 精确匹配入口。

#### 核心机制 2：双层物理索引（block + row）

```
DatasheetIndexConfig(row_chunks=...)
    ↓
build_index() 创建两个物理 collection：
    agentic_rag_block ── 段落/表格 chunk（含 normalized_text）
    agentic_rag_row   ── 表格行级 chunk（带 row_id / table_id / section_id / source_line）
    ↓
search_block() / search_row() / search_datasheet_index() 三个新 API
search_datasheet_index() 默认 row-first，再补 block context
```

row chunk 由 `build_datasheet_row_chunks()` 从 Phase 1 structure digest 离线生成，每行格式：

```
[doc: dlpc3436_clean.md]
[section: 6.10]
[table: System Oscillator Timing Requirements]
[row: f_clk | MOSC primary oscillator clock | 23.998 | 24.000 | 24.002 | MHz]
```

#### 核心机制 3：structure-driven bundle planner

`plan_datasheet_evidence_bundle(query, retriever)` 是 Phase 4 关键能力：

```
query → 规则推断 query_type（parameter / enumeration / connection / support / state / spec_reading）
      → row hits（精确事实）
      → block context（表注 / 章节背景）
      → 结构化元数据（section_id / section_title / table_id / row_id / source_line）
      → reading_closure（Phase 7 跨章节合成）
      ↓
Retriever.search_datasheet_index(query, return_bundle=True)
      ↓
search_datasheet Skill 优先消费此 bundle，旧 staged retrieval 规则保留为 fallback
```

#### 核心机制 4：规格书阅读路径闭环（reading_closure，Phase 7）

NotebookLM 验证查询 "DLPC3436 系统振荡器时序要求" 揭示了跨 700+ 行合成的能力缺口：6 行 timing 表在 line 690-699，但 ±200 PPM 在 line 1410（10.1 章），PLL_REFCLK 接线在 line 383-384 + line 1460。这是规格书 RAG 的核心场景。

`retriever.build_specification_reading_closure(query, source_path)` 输出：

```python
{
  "subject": "6.10 System Oscillator Timing Requirements",
  "anchors": [
    {"quote": "| f_clk | ... | 23.998 | 24.000 | 24.002 | MHz |", "line": 695, "relation": "value"},
    ...
  ],
  "followed_cues": [
    {"cue_type": "annotation", "relation": "constraint",
     "quote": "(1) The MOSC input does not support spread spectrum clock spreading.",
     "line": 701, "confidence": 0.9},
    {"cue_type": "cross_reference", "relation": "dependency",
     "quote": "If an external oscillator is used, the oscillator output must drive PLL_REFCLK_I",
     "line": 1460, "confidence": 0.8},
    ...
  ],
  "unresolved_cues": [],
  "closure_complete": true
}
```

实现路径：anchor 定位（章节标题 + 实体 token 加权）→ 邻接 cue 收集（NOTE / 脚注 / `(n)` 标注 / Figure caption）→ cross-reference 跟踪（`See Section X.Y.Z` / phrase definition）→ entity 定义跳转（`PLL_REFCLK_I` 的 pin 表定义）。**通用规则驱动，不允许 TE53 / Spread Spectrum 专用补漏**。

#### 核心机制 5：Datasheet 专用 Generator prompt

`generator._TECHNICAL_DATASHEET_PROMPT_TEMPLATE` 是与流程文档完全独立的一套 12 条规则，关键约束：

- **数值/符号/单位逐字保留**：不得四舍五入，不得改写 ± / % / MHz / ns / ppm（`23.998` 不得写成 `23.99`）
- **保留必要英文符号**：`f clk` / `t c` / `t w(H)` / `PLL_REFCLK_I` / `MOSC` 等参数符号必须保留，只翻译参数说明
- **结构化输出**：按"主答案 / 关键技术补充要求 / 注意事项"组织，不同表格的约束不混在一行
- **表格优先**：检索到参数表时按 Markdown 表格输出
- **必须覆盖期望术语/数值**：context 注入 `required_terms / must_have_terms` 时，回答必须逐项原样包含；多电压档位 / continuation rows 必须全部枚举，不得只摘要第一行
- **结构化引用**：回答末尾保留 `[Section: ...; Table: ...; Row: ...; line: ...]`
- **reading_closure 消费**：context 含闭环时，回答必须覆盖 anchors 的 value/spec + followed_cues 的 condition/constraint/prohibition/definition/dependency；`closure_complete=False` 或存在 `unresolved_cues` 时必须在注意事项中说明

触发条件：`query_structure.domain == "technical_datasheet"` 或 executed_steps 中包含 `search_datasheet`。

#### chunk schema 与文档清洗的 datasheet 适配

- `document_loader.chunk_markdown()` 生成的 chunk 含 `is_datasheet / index_kind / normalized_text / entity_tokens` 字段（流程文档默认空）
- `doc_cleaner._is_datasheet_document()` 命中 `DATASHEET_SOURCES` 白名单时走 `_clean_datasheet_content()` 保守清洗：保留 NOTE / 脚注 / 表注 / `(1)(2)(3)` 标记，只去页眉页脚和水印
- `index_augmenter._should_augment()` 对 `is_datasheet=True` 直接返回 False，避免对参数表生成低质量增强问题污染索引

#### 评估资产

`evaluation/` 目录维护 datasheet baseline 评估闭环：

- `datasheet_baseline_cases.json` — 15 个 case 覆盖 parameter / enumeration / connection / support / state / adversarial
- `.datasheet_retrieval_metrics.json` — recall@10 / recall@20 / required_terms_hit_rate
- `.datasheet_full_metrics.json` — oracle hit / numeric preservation
- `.datasheet_judge_sample_metrics.json` — 确定性 judge 抽样
- `.datasheet_real_llm_judge_sample_metrics.json` — 真实 Ollama judge 抽样
- `.datasheet_real_generator_sample_metrics.json` — 真实 generator 端到端抽样

当前 15-case retrieval baseline `recall@10=1.0`、`recall@20=1.0`，3-case real generator sample `effective_pass=3 / 3`。

#### 离线脚本

```bash
# 重新生成 DLPC3436 structure digest（dlpc3436_clean.md hash 锁定）
python scripts/regen_datasheet_structure.py
```

### 伞形概念扩写（_CONCEPT_MAP）

在 Skill 层维护领域词典，将上位概念（如"结婚福利"）映射为文档中实际存在的具体术语，每个术语独立 hybrid 检索后合并去重，解决用户心智模型与文档信息架构之间的语义鸿沟。

### 检索域隔离（where 过滤）

向量索引全域共享，跨域语义相近的 chunk 会占用 top_k 名额。每个 Skill 通过 `where={"source": {"$in": list(_SOURCES)}}` 将 vector_search 限定在本域文档内，从源头隔离跨域干扰。事后 `_filter_by_source` 保留为兜底过滤。

### 满意度评价（evaluator）

用户可对每条回答进行 👍/👎 评价：
- **满意**：仅累计计数
- **不满意**：记录完整查询上下文（问题、回答、检索结果 top-3）到 `eval_records.json`
- **未评价直接提交下一问**：默认记为满意
- 侧边栏实时展示满意率统计与不满意记录

---

## 配置项

| 配置项 | 当前值 | 说明 |
|--------|--------|------|
| `RAG_PROFILE` | `"datasheet"`（可被环境变量覆盖） | v3.1 profile 选择：`enterprise` / `datasheet` / `all` |
| `KNOWLEDGE_BASE_ROOT` | `./knowledge_base` | profile 根目录 |
| `KNOWLEDGE_BASE_DIR` | `get_knowledge_base_dir()` | 当前 profile 的知识库目录，如 `knowledge_base/datasheet` |
| `CHUNK_SIZE` | `600` | chunk 最大字符数 |
| `TOP_K` | `5` | 检索返回条数 |
| `EMBEDDING_MODEL` | `"BAAI/bge-m3"` | Embedding 模型 |
| `LLM_BACKEND` | `"openai"` | `"ollama"` / `"openai"` / `"none"` |
| `OLLAMA_MODEL` | `"qwen3.6:35b-a3b-q4_K_M"` | Ollama 模型名（支持视觉理解） |
| `OLLAMA_OPTIONS` | `{"num_ctx": 4096, "temperature": 0}` | `temperature=0` 消除随机性 |
| `OPENAI_BASE_URL` | `"https://aicode.wewell.net/v1"` | OpenAI 兼容协议网关地址 |
| `OPENAI_API_KEY` | （明文，部署前替换） | API 密钥；建议改为环境变量读取（待办 R-5）|
| `OPENAI_MODEL` | `"gpt-5.4"` | 网关侧的模型路由名 |
| `OPENAI_OPTIONS` | `{"temperature": 0}` | OpenAI Chat Completions 参数 |
| `AUGMENT_QUESTIONS` | `True` | 企业 profile 可生成增强问题；datasheet chunk 仍由 `_should_augment()` 强制跳过 |
| `AUGMENT_MAX_CHUNKS` | `None` | 增强问题生成上限；大 KB 恢复增强时可先限流 |
| `INDEX_BATCH_SIZE` | `64` | Chroma 分批写入大小；范围式日志便于观察进度 |
| `PERSIST_CHROMA_INDEX` | `True` | 启用 Chroma 持久化，避免每次启动全量 embedding |
| `CHROMA_PERSIST_DIR` | `get_chroma_persist_dir()`，即 `knowledge_base/<profile>/chroma_db` | v3.1 profile 级 Chroma 持久化索引目录 |
| `get_chroma_collection_names()` | `agentic_rag_<profile>` / `agentic_rag_<profile>_block` / `agentic_rag_<profile>_row` | v3.1 profile 级 collection 命名，避免不同知识库共用 collection |
| `DATASHEET_SOURCES` | DLPC3436 + HDMI 1.4/2.0/2.1b + DVI 1.0 + EIA-CEA-861-D 三种文件名变体（`.pdf` / `.md` / `_clean.md`） | datasheet 白名单。命中后：① doc_cleaner 走保守清洗；② chunk 标记 `is_datasheet=True`；③ index_augmenter 跳过该 chunk；④ retriever 走 normalize + entity_tokens 抽取 |

---

## 测试策略

| 层次 | 位置 | LLM | 验证内容 |
|------|------|-----|---------|
| 单元测试 | `tests/` | Mock | 流程正确性、prompt 构造、结果处理 |
| 集成测试 | `tests/integration/` | 真实调用 | LLM 推理能力（省会识别、排除法推断）|
| Profile 隔离 | `tests/test_knowledge_base_profile.py` | 无 | `RAG_PROFILE` 子目录、Chroma collection、persist dir、question cache 隔离 |
| Datasheet 单点 | `tests/test_dlpc3436_document_evidence.py` / `test_search_datasheet.py` / `test_dlpc_datasheet_retrieval.py` | Mock | DLPC 单点 evidence + retrieval 回归 |
| Datasheet PDF / chunk | `tests/test_datasheet_pdf_pipeline.py` / `test_datasheet_phase2_phase3_phase6.py` / `test_datasheet_source_metadata.py` | 无 | PDF→md→chunk schema、is_datasheet 元数据、normalize 双向一致 |
| Datasheet 索引 | `tests/test_datasheet_dual_index.py` / `test_datasheet_structure_digest.py` / `test_datasheet_structure_planner.py` | 无 | block/row 双 collection 物理分离、structure digest 必须锚点、bundle planner |
| Datasheet baseline | `tests/test_datasheet_retrieval_baseline.py` / `test_datasheet_full_baseline.py` / `test_datasheet_baseline.py` | 部分真实 | 15 cases retrieval recall@10/@20、oracle hit、numeric preservation、real generator/judge 抽样 |
| Datasheet staged | `tests/test_datasheet_staged_retrieval.py` / `test_datasheet_remaining_staged_retrieval.py` | 无 | oscillator / SPI flash / DMD parking / I2C ports / I2C command readiness staged 兜底 |
| Datasheet reading path | `tests/test_specification_reading_path.py` | 无 | reading_closure：anchor + followed cues + cross_reference + definition |
| Datasheet 端到端 | `tests/test_dlpc_agentic_run.py` / `test_generator.py` | Mock | domain 路由、TECHNICAL_DATASHEET prompt、reading_closure 注入 context |

---

## 设计问题记录

---

### 问题一：BM25 补漏机制的设计与取舍

**初衷**：hybrid 检索存在结构性缺陷——当某 chunk 向量 embedding 因多主题内容被稀释时，只能获得 BM25 单路 RRF 贡献（≈0.016），低于双路命中结果（≈0.032），容易被 top_k 截断。

**遇到的问题**：BM25 原始分（~13.8）与 hybrid RRF 分（~0.032）量纲不同，合并后 BM25 结果异常高分压制正确结果；自检条件在同义词场景误触发；即便转为 RRF 等效分，单路 BM25 最高分仍低于任何双路命中结果。

**为何最终移除**：增强索引上线后，大表通过问题向量变成双路命中，自然进入 top_k，补漏使用场景被从根本上消除。

---

### 问题二：多域知识库下的检索区域划分

**问题本质**：向量索引全域共享，跨域语义相近 chunk（含增强索引问题向量）会混入结果，占用 top_k 名额。事后过滤只能删掉结果，无法补回被挤走的正确 chunk。

**设计决策**：检索区域在 Skill 层前置收窄，通过 `where={"source": {"$in": list(_SOURCES)}}` 实现预过滤，从源头隔离跨域干扰。

---

### 问题三：BM25 在 hybrid 中的角色定位

**结论**：BM25 在 hybrid 中的核心价值是**确认信号**（与向量双路命中分数叠加提升可靠性）和**精确实体匹配**（型号、编码等 embedding 不敏感内容）。增强索引上线后，BM25 的"独家发现"场景被覆盖，角色从"补漏主力"退为"确认信号 + 精确实体兜底"。

---

### 问题四：伞形概念与文档信息架构的语义鸿沟

**问题**：用户使用上位概念提问，文档将其拆分为多个独立章节，单次向量检索无法同时覆盖所有相关内容。

**解决方案**：Skill 层维护 `_CONCEPT_MAP`，将伞形概念展开为多个具体检索词，每个词独立 hybrid 检索后合并去重，确定性强，不引入额外 LLM 调用。

---

### 问题五：Generator 分类结论丢失

**问题**：`search_expense_reimbursement` 在 Executor 阶段已通过 LLM 推断出城市分类（如"揭阳 = C类"），但该结论仅用于内部拼装查询词，未注入返回结果。Generator 拿到原始 chunk 后需自行重推，因缺少完整城市名单而无法判断，回答变为"无法确定"。

**解决方案**：在 `search_expense_reimbursement` 的 `merged` 首位插入 `is_conclusion=True` 的结论 chunk，`_filter_by_source` 对结论 chunk 豁免过滤（通过 `is_conclusion` 字段识别）。Generator 的 `_build_entity_note` 优先读取结论 chunk，直接得知城市分类，无需重推。

---

### 问题六：省会城市分类误判

**问题**：文档规则"B类：省会城市及计划单列市"未逐一列出省会城市名，LLM 需自行判断目标城市是否为省会。qwen3.6 对部分省会城市（如南昌）存在误判，将其归入 C 类。

**解决方案**：改为配置规则优先方案——在 `config/region_classification.json` 中维护 A/B 类城市清单（含省会城市和计划单列市），程序先按配置确定性分类；配置未覆盖时再调用 LLM 兜底。原先的 `_PROVINCIAL_CAPITALS` 硬编码名单和虚拟 chunk 已移除。

---

### 问题七：图片型 PDF 文字提取丢失

**问题**：PPT 转 PDF 的文档（如资产管理流程），大量内容以图片形式存在，Docling 文字提取丢失严重，索引后几乎无法回答相关问题。

**解决方案**：采用视觉 RAG 方案——逐页截图后调用 Ollama 视觉模型（`qwen3.6:35b-a3b-q4_K_M`）提取文字，同时在每页内容中嵌入 `__PAGE_IMG__` 图片路径标记。检索时文字用于 BM25/向量匹配，命中后前端解析标记展示原始页面图片。Generator 在回答中标注 `[引用页面: 第N页]`，app.py 据此精确定位并展示对应图片，显示时自动剔除内部标记。

---

### 问题八：表格合并单元格在 PDF→Markdown 转换时丢失（TE8）

**问题**：报销标准表中"销售人员/非销售人员 出差补贴"原本是合并单元格（A/B/C 类地区共用同一金额），Docling 输出 Markdown 时拆成两份分配到 B/C 列，A 列被分类标签"销售人员"占用，导致**深圳（A 类）销售人员的金额数据完全丢失**。LLM 看到残缺数据，给出"未明确金额"的错误回答。

**根因**：Markdown 表格语法不支持 `colspan/rowspan`，Docling `export_to_markdown()` 必须做信息降维，对合并行的处理是错位填充。

**当前缓解**：识别根因，已记录到 `tasks/known_risks.md`。**临时方案**是手工修复 `报销相关_clean.md` 该段表格；**治本方案**是绕过 `export_to_markdown()`，自定义渲染器读取 `DoclingDocument` 的 `col_span/row_span` 信息后展开复制（待办 R-1）。

---

### 问题九：Markdown 标题层级误用导致父语境丢失（TE20）

**问题**：用户问"总部到坪山往返班车的发车时间"，模型答出错误时间（来自另一段"坪山到总部摆渡车"表格）。GT 答案在 `OA新员工-行政指引2025.7.7 _clean.md` 的"早班车 07:30 / 晚班车 20:00"片段，但该 chunk 始终未被召回。

**根因**：原文档把"早班车："、"晚班车："和父标题"总部到坪山往返班车"**误用为同级 H2 标题**。`document_loader.chunk_markdown` 按 `re.split(r"(?=\n#{1,3} )", ...)` 切节后，"早班车 07:30" 被切成独立 chunk，**自身不含"总部"、"坪山"任何字样**，向量与 BM25 都无法召回。同时段 B "## 8、坪山到总部摆渡车 + 表格" 完整命中关键词且被 `_boost_table_chunks` ×1.5 提分，最终覆盖正确答案。

**当前缓解**：识别根因，已记录到 `tasks/known_risks.md`。**临时方案**是把误用的 H2 子标题改为粗体行内或 H3；**治本方案**是 chunker 引入"标题栈注入"，每个 chunk 入库前前置当前所有活跃高级标题，使父语境永远跟随（待办 R-2）。

---

### 问题十：系统名 vs 业务动作的路由消歧（TE25）

**问题**：用户问"OA 系统出差申请和审批流程是什么？"，Planner 路由到 `search_it_guide`（IT 指引），但该域只覆盖 OA 账号/密码/登录，没有出差业务流程。正确答案在 `报销相关_clean.md` 的"5.4.5. 差旅费报销制度及审批流程"，应路由到 `search_expense_reimbursement`。

**根因**：`search_it_guide` 的 description 把【OA】列为关键词，但 IT 指引文档**只覆盖 OA 接入层**（账号/登录/密码），不覆盖 OA 上承载的业务流程。Planner LLM 看到 query 含"OA"就直接命中 IT 指引，是 **Skill 描述与文档实际覆盖范围错位**。

**解决方案**：
1. **Skill 描述精修**：`search_it_guide.SKILL_META.description` 限定到"接入层"，并显式排除"业务流程"；`search_expense_reimbursement.SKILL_META.description` 拆成"数值/标准类"+"流程类"两路，明确"OA/HR 等系统名出现也走本 Skill"。
2. **Planner Prompt 增加路由消歧规则**：`planner._PLAN_PROMPT_TEMPLATE` 新增规则 8——"系统名 vs 业务动作"，附 TE25 反例，要求 Planner 按业务动作选 Skill，不被系统名锚定。

---

### 问题十一：Where 缺失判断过粗导致过度澄清（TE31）

**问题**：用户问"普通员工同性别 2 人出差同一地点，住宿标准如何调整？"，模型反问"您要查询的是哪个城市/地区的标准？"——但调整规则（+100 元/天）全国统一，与具体地区无关。

**根因**：`query_understanding._PARSE_PROMPT` 中 Where 缺失判断只有一条规则——"该问题的答案是否会因城市/地区不同而不同？" 过于粗糙。LLM 看到"住宿"关键词就关联到"差旅标准因地区而异"，触发 `needs_clarification=true`。该判断没区分"绝对金额（按地区分级）"与"相对调整/流程/共享规则（全国统一）"。

**解决方案**：
1. **Prompt 决策树细化**：Where 缺失判断改为 5 步顺序判断，先排除"相对调整/流程/共享规则/统一适用"四类区域无关问题，最后才触发追问。
2. **关键词兜底**：`parse_query` 末尾增加 `_looks_region_independent` 检测——命中"调整/流程/同性别/同地点/发票/丢失"等区域无关关键词时，强制撤回 `needs_clarification`。
3. **回归测试**：`tests/test_query_understanding.py::TestRegionIndependentFallback` 新增 4 条用例覆盖 TE31 同款、流程类、who+where 同缺允许兜底、纯金额 query 不被误伤。

---

### 问题十二：英文规格书跨章节合成（NotebookLM 标杆）

**问题本质**：DLPC3436 / HDMI / DVI 这类英文规格书，关键事实**分布在跨章节多片段**。NotebookLM 验证查询 "DLPC3436 系统振荡器时序要求" 揭示标杆答案需要：
- 6 行 timing 表（line 690-699）
- 表注 `(1)(2)` 的 ±200 PPM、no spread spectrum、过渡时间定义（line 701 邻接 + line 1410，跨 700+ 行）
- 外部 oscillator 接线要求 PLL_REFCLK_I/O（line 383-384 pin 表 + line 1460 章节 10.1.2）

旧 hybrid 检索单 chunk 召回够不到这种跨章节合成；伞形扩写 `_CONCEPT_MAP` 是人工补丁，每加一个新名词就要补一组关键词，长期一定崩。

**设计原则**：不模仿 NotebookLM 的回答风格，要模仿它的文档理解路径——**围绕 section / table / row / entity 做多跳检索**。

**解决方案（Phase 1 + 2 + 4 + 7）**：

1. **离线 structure digest**（Phase 1）：`scripts/regen_datasheet_structure.py` 从 `dlpc3436_clean.md` 生成 `section_tree / table_catalog / row_index / entity_inventory / alias_graph`，hash 锁定到文档内容。
2. **双层物理索引**（Phase 2）：block + row 两个 collection 物理分离，row chunk 携带 `section_id / table_id / row_id / source_line`。
3. **structure-driven bundle planner**（Phase 4）：`plan_datasheet_evidence_bundle()` 推断 query_type，row-first 检索 + block context 补全 + 结构化元数据。
4. **reading_closure**（Phase 7 核心）：`build_specification_reading_closure()` 通用规则驱动地构建阅读路径——anchor 定位（章节 + 实体 token 加权）→ 邻接 cue（NOTE / 脚注 / annotation `(n)` / Figure caption / inline `Note:` / `## Note` block）→ cross-reference 跟踪（`See Section X.Y.Z`，含 PDF 转换断行修复）→ entity 定义跳转（pin 表定义）。
5. **Generator prompt 强约束**：context 注入 reading_closure 时，回答必须覆盖 anchors 的 value/spec + followed_cues 的 condition/constraint/prohibition/definition/dependency；`closure_complete=False` 必须在注意事项中说明 unresolved cues。

**通用性约束**：实现必须是通用 `reading_closure`，不允许 TE53 / Spread Spectrum / PLL_REFCLK 专用补漏。Phase 7 单测在 RED 阶段先用 TE53 验证路径，但 GREEN 实现是 anchor + followed cues + relation + quote/line 通用规则。

**当前覆盖**：6.10 timing table → annotation `(1)/(2)` → external oscillator pin 定义；TSTPT_5 inline note + PDF 表格断行的 `See Section 7.3.8`；section-level NOTE + Figure caption + Figure 9-2 normal power-down `(c)` SYSPWR 50 ms 约束。Phase 7 单测 4 passed；datasheet 大范围回归 64 passed。

---

### v3.0：大知识库索引持久化与增量构建

**问题**：新增 DVI / CEA / HDMI 多个大规格书后，知识库规模达到 6270 chunks。旧实现每次启动都一次性向 Chroma add 全量 chunks，Streamlit 页面长时间停留在“加载知识库”，日志无推进；仅改为分批后仍会重复全量 embedding，扩展性不足。

**解决方案**：
1. `retriever.py` 改为分批写入 Chroma，`INDEX_BATCH_SIZE = 64`，每批输出范围式进度。
2. 启用 `chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))`，v3.1 后持久化索引目录为当前 profile 的 `knowledge_base/<profile>/chroma_db/`。
3. 基于 `source + chunk_index + normalized_text/text` 生成 chunk hash ID，已存在 ID 直接跳过，只对新增/变化 chunk 做 embedding。
4. 新增 `tasks/run_persistent_index.py`，支持在 Streamlit 外按 `RAG_PROFILE` 离线构建/更新大索引。
5. `AUGMENT_QUESTIONS` 与 `AUGMENT_MAX_CHUNKS` 控制增强问题生成；datasheet chunk 继续跳过增强，避免精确规格书查询被自然语言问题污染。
6. 修复 Chroma 持久化 collection 的 `embedding_function` 冲突：持久化模式下 `get_or_create_collection()` 不再传新的 embedding function。
7. v3.1 新增 profile 隔离：`get_knowledge_base_dir()` / `get_chroma_persist_dir()` / `get_chroma_collection_names()` 将 source、缓存、collection 全部绑定到 `enterprise` 或 `datasheet`。

**验证**：
```text
.venv/bin/python -m pytest tests/test_retriever.py -q -> 24 passed in 0.05s
首次离线索引：6270 chunks 完成，.chroma_index = 56M
重启后日志：原始跳过已存在索引：6270/6270；新增 0 条
curl http://127.0.0.1:8501/ -> HTTP/1.1 200 OK
```

详细过程记录：`tasks/large_kb_indexing_scalability.md`。

---

### v3.1：Knowledge Base Profile 隔离

**问题**：企业制度文档和英文规格书混放在同一运行时路径时，会出现三类污染：
1. source 级污染：企业 policy query 可能召回 datasheet chunk，datasheet query 也可能被企业制度 chunk 占据 top_k。
2. 索引级污染：Chroma collection / persist dir 共用后，不同知识库切换时容易复用旧 collection。
3. 缓存级污染：`.question_cache.json`、`.page_cache`、离线索引脚本若仍指向根目录，会导致拆目录后仍读旧缓存或重新生成增强问题。

**解决方案**：
1. `config.py` 新增 `RAG_PROFILE=enterprise|datasheet|all`，默认可被环境变量覆盖。
2. `get_knowledge_base_dir()` 将加载范围限定到 `knowledge_base/<profile>`。
3. `get_chroma_persist_dir()` 将持久化索引放到 `knowledge_base/<profile>/chroma_db`。
4. `get_chroma_collection_names()` 为 collection 添加 profile 后缀，例如 `agentic_rag_datasheet_block` / `agentic_rag_datasheet_row`。
5. `index_augmenter.get_question_cache_file()` 将增强问题缓存写入当前 profile 目录。
6. `app.py` 启动日志打印当前 `RAG_PROFILE` 与 KB 路径，页面图片缓存解析也基于当前 profile。
7. `tasks/run_persistent_index.py` 按当前 profile 离线构建索引，并打印 profile/kb 路径。

**验证**：
```text
tests/test_knowledge_base_profile.py：覆盖 profile 子目录选择、profile-scoped collection names、Retriever collection 名、question cache 与 chroma_db 路径。
```

---

## 架构演进记录

详见 [PLAN.md](./PLAN.md)，记录了从 v1.0 到 v2.0 的设计决策、方案对比和关键取舍。

## 已知风险与待办

详见 [tasks/known_risks.md](./tasks/known_risks.md)，记录由近期失败用例（TE8 / TE20 / TE25 / TE31）和 OpenAI 通道接入引出的待治本风险（R-1 ~ R-8）。已按"风险高 + 改动小"优先级排序。
