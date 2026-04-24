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

**BGE-M3 带来的提升：**
- 中文语义匹配精度大幅提升，费用标准表格能被准确检索
- 原本"说明文字排名高于费用表格"的问题得到根本性改善
- 揭阳、广水等隐式实体的分类规则检索更准确

### LLM 模型（推理与生成）

| 配置值 | 说明 |
|--------|------|
| `"qwen3.6:35b-a3b-q4_K_M"` | ✅ 推荐，对中文提示词理解更准确，分类推断误判率显著降低 |
| `"gemma4"` | 备选，需设置 `think=False` |

**模型升级带来的提升：**
- 分类推断更严格遵守"排除法"（未列出的城市归C类，不再被地理位置带偏）
- QueryUnderstanding 对 Who/Where/What 维度的识别更精准
- Generator 生成的回答更贴合提示词中的格式要求

---

## 架构概览

```
用户提问
    │
    ▼
┌─────────────────────────────┐
│  Step 0: QueryUnderstanding  │  语义解析：维度补全 / 约束识别 / 意图判断 / 冲突检测
└──────────────┬──────────────┘
               │ QueryStructure（含 where.scope 境内/境外/港澳台）
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
├── app.py                      # Streamlit 前端页面（含历史查询记录）
├── agentic_rag.py              # 主流程编排（RunResult）
├── query_understanding.py      # 查询语义解析（QueryStructure）
├── planner.py                  # 检索计划生成
├── executor.py                 # Skill 执行引擎
├── generator.py                # 回答生成
├── retriever.py                # 检索器（向量 / BM25 / 混合，支持 BGE-M3）
├── document_loader.py          # 文档加载、清洗与表格感知分块
├── doc_cleaner.py              # 文档清洗（去除 PDF 转换产生的页眉/页脚污染）
├── llm.py                      # LLM 调用封装
├── utils.py                    # 工具函数（实体抽取、表格清洗、LLM 分类）
├── config.py                   # 全局配置项
│
├── skills/                     # 可插拔检索技能
│   ├── __init__.py             # 动态加载器（扫描 search_*.py）
│   ├── search_classification.py          # 实体分类查询（支持境内/境外/港澳台）
│   ├── search_standards.py               # 费用标准查询
│   ├── search_expense_reimbursement.py   # 报销复合技能（分类→标准两步链）
│   └── search_example.py                 # Skill 编写模板（不被加载）
│
├── knowledge_base/             # 知识库文档
│   ├── 报销相关.md              # 企业费用报销规定（含城市分类、境内外标准）
│   ├── 报销相关_clean.md        # 清洗后版本（自动生成，RAG 实际使用此文件）
│   └── *.pdf                   # PDF 文档（自动转 Markdown 后使用）
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
│       └── test_llm_classify_reasoning.py  # LLM 推理能力集成测试
│
├── tasks/                      # 阶段任务文档
├── PLAN.md                     # 架构设计与演进记录
├── pytest.ini                  # 测试配置（marker 注册）
└── requirements.txt
```

---

## 核心模块说明

### QueryUnderstanding

将自然语言问题结构化为机器可读的 `QueryStructure`，提取：

| 字段 | 说明 | 示例 |
|------|------|------|
| `dimensions.where.scope` | 地点类型 | `mainland`/`china`（港澳台）/`overseas` |
| `dimensions` | Who / Where / What 三维度 | `where: 深圳, what: 住宿费` |
| `constraints` | 时间/场景约束 | `{type: 时间约束, value: 2023年后}` |
| `intent_granularity` | 精确事实 / 总结性 | 影响 Generator 回答风格 |
| `needs_clarification` | 是否需要追问 | `True` 时短路，直接返回追问文案 |

### Planner

接收 Skill 描述列表和 QueryStructure，通过 LLM 生成 JSON 格式的检索计划：

```json
{
  "steps": [
    {
      "step_id": 1,
      "skill": "search_classification",
      "query": "深圳 地区分类",
      "depends_on": []
    },
    {
      "step_id": 2,
      "skill": "search_standards",
      "query": "<step_1_result> 住宿费标准",
      "depends_on": [1]
    }
  ]
}
```

`<step_N_result>` 占位符由 Executor 在执行前替换为前置步骤的关键实体摘要。

### Skills（可插拔检索技能）

每个 Skill 是一个独立的 `search_*.py` 文件，包含两个必要属性：

```python
SKILL_META = {
    "name": "search_xxx",
    "description": "Planner 用于选择 Skill 的描述文字",
    "retrieval_method": "vector" | "bm25" | "composite",
}

def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    ...
```

新增 Skill 只需在 `skills/` 目录下创建文件，系统自动加载，无需修改主程序。

#### 当前内置 Skill

| Skill | 触发场景 | 内部检索链 |
|-------|---------|-----------|
| `search_classification` | 查询实体所属分类 | scope 路由 → BM25/LLM 境内分类 或 LLM 境外分类 |
| `search_standards` | 查询某分类下的费用标准 | 向量检索 |
| `search_expense_reimbursement` | 报销费用查询（复合） | scope 路由 → 分类推断 → 表格优先重排 → 反思自检 |

#### 境内/境外路由机制

`where.scope` 字段由 QueryUnderstanding 判断，Skill 据此选择不同检索路径：

```
scope=mainland  → BM25 精确匹配 → LLM 读境内规则推断 A/B/C 类
scope=china     → 直接确定境外C类（港澳台），无需分类检索
scope=overseas  → LLM 依地理常识判断境外 A类（欧美日新）或 B类（其他）
```

#### 境内分类推断路径

```
深圳（A类显式）→ BM25 命中规则 → LLM 读列表 → "A类"
天津（B类显式）→ BM25 命中规则 → LLM 读列表 → "B类"
成都（B类省会）→ BM25 未命中 → 向量拉回完整规则 → LLM 推理"省会城市" → "B类"
揭阳（C类其他）→ BM25 未命中 → 向量拉回完整规则 → LLM 排除法推断 → "C类"
```

> 分类推断在 Executor 阶段完成，不依赖 Generator。原因：Generator 推断出分类后已无法再发起检索，无法获取对应分类的费用数据。

### 文档清洗（doc_cleaner）

PDF 转 Markdown 后会产生重复的页眉、文件编号、版本号等"污染内容"，影响检索质量。`doc_cleaner` 在首次加载时自动清洗：

```
原始文档 报销相关.md
    │
    ├─ 频率统计：重复出现 ≥2 次的段落列为污染候选
    ├─ LLM 确认：判断候选段落是"页眉/文件标识"还是"正文"
    ├─ 规则清洗：删除 <!-- image -->、页码行、文件元信息表格
    └─ 输出 报销相关_clean.md（再次启动时直接复用，不重复清洗）
```

### 表格感知分块

Markdown 表格无论大小，始终保持为一个完整 chunk，不会被字符限制截断。每个表格 chunk 自动携带所属节标题，防止表格脱离上下文后丢失分类信息。

结合 BGE-M3 向量模型，费用标准表格能被准确检索和排名。

---

## 配置项

`config.py` 控制所有可变行为：

| 配置项 | 当前值 | 说明 |
|--------|--------|------|
| `KNOWLEDGE_BASE_DIR` | `./knowledge_base` | 知识库目录 |
| `CHUNK_SIZE` | `600` | chunk 最大字符数 |
| `TOP_K` | `5` | 检索返回条数 |
| `EMBEDDING_MODEL` | `"BAAI/bge-m3"` | Embedding 模型，`"default"` 回退内置模型 |
| `LLM_BACKEND` | `"ollama"` | `"ollama"` 或 `"none"` |
| `OLLAMA_MODEL` | `"qwen3.6:35b-a3b-q4_K_M"` | Ollama 模型名 |
| `OLLAMA_OPTIONS` | `{"num_ctx": 4096}` | 模型参数 |

---

## 测试策略

采用两层测试体系：

| 层次 | 位置 | LLM | 验证内容 |
|------|------|-----|---------|
| 单元测试 | `tests/` | Mock | 流程正确性、prompt 构造、结果处理 |
| 集成测试 | `tests/integration/` | 真实调用 | LLM 推理能力（省会识别、排除法推断）|

集成测试覆盖场景：

- A类城市直接识别（北京、上海、广州、深圳）
- B类显式城市识别（天津、厦门、珠海、青岛）
- **B类省会推理**（成都、杭州、武汉、西安、南京）—— 核心验证点
- C类其他城市推断（揭阳、广水、汕尾、韶关）
- 边界：北京不因"省会逻辑"被误判为 B类

---

## 知识库文档说明

支持三种格式，加载时按以下顺序处理：

```
PDF → Docling 转 .md（同名 .md 已存在则跳过）
 .md → doc_cleaner 清洗为 _clean.md（已存在则跳过）
 加载时优先读 _clean.md，不存在时回退原文件
```

| 格式 | 处理方式 |
|------|---------|
| `.pdf` | Docling 转 Markdown，保留表格结构 |
| `.md` | 自动清洗生成 `_clean.md`，表格感知分块 |
| `.txt` | 滑动窗口分块 |

---

## 架构演进记录

详见 [PLAN.md](./PLAN.md)，记录了从 v1.0 到 v2.0 的设计决策、方案对比和关键取舍。
