# Agentic RAG

基于 **Skill / Tool Use** 架构的检索增强生成系统。相比基础 RAG，核心差异在于引入了 LLM 驱动的规划层——系统会先"思考应该检索什么、用什么方式检索"，再执行多步骤的检索链，最终综合所有结果生成回答。

---

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动前端（Ollama 需提前运行）
streamlit run app.py

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

| 配置值 | 说明 |
|--------|------|
| `"qwen3.6:35b-a3b-q4_K_M"` | ✅ 推荐，支持视觉理解，对中文提示词理解更准确，分类推断误判率显著降低 |
| `"gemma4"` | 备选，需设置 `think=False` |

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
├── query_understanding.py      # 查询语义解析（QueryStructure）
├── planner.py                  # 检索计划生成
├── executor.py                 # Skill 执行引擎
├── generator.py                # 回答生成（含页码引用标记解析）
├── retriever.py                # 检索器（向量 / BM25 / 混合，支持 where 域过滤）
├── index_augmenter.py          # 增强索引生成（LLM 为每个 chunk 生成多角度问题，带缓存）
├── document_loader.py          # 文档加载、清洗与表格感知分块
├── doc_cleaner.py              # 文档清洗（去除 PDF 转换产生的页眉/页脚污染）
├── evaluator.py                # 满意度评价（本地持久化，统计满意/不满意记录）
├── pdf_vision_loader.py        # 图片型 PDF 视觉解析（逐页截图 → Ollama 视觉模型提取文字）
├── pdf_vision_qa.py            # PDF 视觉直答（图片缓存 + 看图回答，供前端展示原始页面）
├── run_vision_extract.py       # 一次性脚本：视觉提取结果写入 _clean.md（图片型 PDF 预处理）
├── test_pdf_render.py          # 调试脚本：PDF 页面渲染为图片，验证截图清晰度
├── llm.py                      # LLM 调用封装
├── utils.py                    # 工具函数（实体抽取、表格清洗、LLM 分类）
├── config.py                   # 全局配置项
│
├── skills/                     # 可插拔检索技能
│   ├── __init__.py             # 动态加载器（扫描 search_*.py）
│   ├── search_attendance.py              # 考勤/休假/福利查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_expense_reimbursement.py   # 报销复合技能（配置规则分类 → LLM兜底 → 费用标准 + 结论 chunk + 域隔离）
│   ├── search_admin_guide.py             # 行政指引查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_it_guide.py                # IT 指引查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_asset_management.py        # 资产管理流程查询（hybrid + 伞形扩写 + 域隔离）
│   └── search_example.py                 # Skill 编写模板（不被加载）
│
├── knowledge_base/             # 知识库文档
│   ├── 报销相关_clean.md
│   ├── 考勤&休假&福利指引20251023_clean.md
│   ├── OA新员工-行政指引2025.7.7 _clean.md
│   ├── 【光峰】新员工IT指引_clean.md
│   ├── 资产管理流程.pdf         # 原始 PPT 转 PDF，图片型文档
│   ├── 资产管理流程_clean.md    # 视觉提取生成（run_vision_extract.py），含 __PAGE_IMG__ 标记
│   ├── .page_cache/            # PDF 页面图片缓存（pdf_vision_qa.py 自动生成）
│   └── .question_cache.json    # 增强索引问题缓存（自动生成，按 chunk MD5 索引）
│
├── tests/                      # 测试
│   ├── test_chunking.py
│   ├── test_executor.py
│   ├── test_planner.py
│   ├── test_query_understanding.py
│   ├── test_retriever.py
│   ├── test_utils.py
│   ├── test_search_expense_reimbursement.py
│   └── integration/
│       └── test_llm_classify_reasoning.py
│
├── tasks/
├── PLAN.md
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

生成结果持久化到 `knowledge_base/.question_cache.json`，缓存键为 chunk MD5，重启直接复用。`config.py` 中 `AUGMENT_QUESTIONS = True` 开启。

这一步很关键，能够让Chunk更容易的和自然语言对接上。

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
| `KNOWLEDGE_BASE_DIR` | `./knowledge_base` | 知识库目录 |
| `CHUNK_SIZE` | `600` | chunk 最大字符数 |
| `TOP_K` | `5` | 检索返回条数 |
| `EMBEDDING_MODEL` | `"BAAI/bge-m3"` | Embedding 模型 |
| `LLM_BACKEND` | `"ollama"` | `"ollama"` 或 `"none"` |
| `OLLAMA_MODEL` | `"qwen3.6:35b-a3b-q4_K_M"` | Ollama 模型名（支持视觉理解） |
| `OLLAMA_OPTIONS` | `{"num_ctx": 4096, "temperature": 0}` | `temperature=0` 消除随机性 |
| `AUGMENT_QUESTIONS` | `True` | 是否生成增强索引；`False` 跳过，适合快速调试 |

---

## 测试策略

| 层次 | 位置 | LLM | 验证内容 |
|------|------|-----|---------|
| 单元测试 | `tests/` | Mock | 流程正确性、prompt 构造、结果处理 |
| 集成测试 | `tests/integration/` | 真实调用 | LLM 推理能力（省会识别、排除法推断）|

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

## 架构演进记录

详见 [PLAN.md](./PLAN.md)，记录了从 v1.0 到 v2.0 的设计决策、方案对比和关键取舍。
