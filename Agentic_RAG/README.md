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
├── retriever.py                # 检索器（向量 / BM25 / 混合，支持 where 域过滤）
├── index_augmenter.py          # 增强索引生成（LLM 为每个 chunk 生成多角度问题，带缓存）
├── document_loader.py          # 文档加载、清洗与表格感知分块
├── doc_cleaner.py              # 文档清洗（去除 PDF 转换产生的页眉/页脚污染）
├── llm.py                      # LLM 调用封装
├── utils.py                    # 工具函数（实体抽取、表格清洗、LLM 分类）
├── config.py                   # 全局配置项
│
├── skills/                     # 可插拔检索技能
│   ├── __init__.py             # 动态加载器（扫描 search_*.py）
│   ├── search_attendance.py              # 考勤/休假/福利查询（hybrid + 伞形扩写 + 域隔离）
│   ├── search_classification.py          # 实体分类查询（支持境内/境外/港澳台）
│   ├── search_standards.py               # 费用标准查询
│   ├── search_expense_reimbursement.py   # 报销复合技能（分类→标准两步链 + 域隔离）
│   └── search_example.py                 # Skill 编写模板（不被加载）
│
├── knowledge_base/             # 知识库文档
│   ├── 报销相关.md              # 企业费用报销规定（含城市分类、境内外标准）
│   ├── 报销相关_clean.md        # 清洗后版本（自动生成，RAG 实际使用此文件）
│   ├── 考勤&休假&福利指引20251023_clean.md  # 考勤/休假/福利政策文档
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

**where 缺失判断原则**：判断依据是"该问题的答案是否会因城市/地区不同而不同"，而不是枚举关键词白名单。考勤/福利类问题全公司统一适用，不因城市不同而变化，因此不需要补全 where 维度。

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
    "retrieval_method": "vector" | "bm25" | "hybrid" | "composite",
}

def execute(query: str, retriever, query_structure: dict = None) -> list[dict]:
    ...
```

新增 Skill 只需在 `skills/` 目录下创建文件，系统自动加载，无需修改主程序。

#### 当前内置 Skill

| Skill | 触发场景 | 内部检索链 |
|-------|---------|-----------|
| `search_attendance` | 考勤/休假/福利政策查询 | 伞形扩写 → hybrid（域隔离）→ 表格重排 |
| `search_classification` | 查询实体所属分类 | scope 路由 → BM25/LLM 境内分类 或 LLM 境外分类 |
| `search_standards` | 查询某分类下的费用标准 | 向量检索 |
| `search_expense_reimbursement` | 报销费用查询（复合） | scope 路由 → 分类推断 → 表格优先重排 → 反思自检（域隔离）|

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

### 增强索引（index_augmenter）

**解决问题**：用户提问用语与文档术语不一致的语义鸿沟。例如用户说"生日福利"，文档是一张多主题"关爱福利大表"——表的整体 embedding 被多主题稀释，向量检索无法精确命中。

**工作原理**：
- 对每个 chunk，调用 LLM 从用户视角生成 8-10 个不同问法的问题
- 将问题文本作为 ChromaDB 的 document（用于向量匹配），原始 chunk 文本存入 metadata
- 检索命中增强条目时，返回 metadata 中的原始 chunk，而非问题文本本身

**缓存机制**：
- 生成结果持久化到 `knowledge_base/.question_cache.json`
- 缓存键为 chunk 文本的 MD5，文档内容变更时自动失效
- 重启时直接复用，不重复调用 LLM

**配置**：`config.py` 中 `AUGMENT_QUESTIONS = True` 开启，`False` 跳过（适合快速调试）。

### 伞形概念扩写（_CONCEPT_MAP）

**解决问题**：用户使用上位概念提问（如"结婚福利"），而文档将其拆分为多个独立章节（"结婚礼金"在关爱福利表、"婚假"在休假章节）。单次检索无法同时覆盖所有相关内容。

**工作原理**：在 Skill 层维护领域词典，将伞形概念映射为文档中实际存在的具体术语，每个术语独立做 hybrid 检索后合并去重：

```python
_CONCEPT_MAP = {
    "结婚福利": ["结婚礼金", "婚假", "结婚福利"],
    "生育福利": ["生育津贴", "产假", "陪产假", "生育礼金"],
    ...
}
```

**维护原则**：仅当用户心智模型与文档信息架构存在明确鸿沟时才添加映射，避免过度维护。

### 检索域隔离（where 过滤）

**问题**：向量索引是全域共享的，包含增强索引的问题向量。搜索某个业务域的 query 时，其他域的语义相近内容会占用 top_k 名额，挤出本域正确 chunk。例如搜索"结婚礼金"时，报销文档中"礼品赠送"的增强问题向量语义相近，混入结果。事后过滤（`_filter_by_source`）只能删掉跨域结果，无法补回被挤走的正确 chunk。

**设计决策**：本系统采用 Skill 路由架构，每个 Skill 已明确划定业务域，因此**检索区域在 Skill 层就做收窄**，通过 `where={"source": {"$in": list(_SOURCES)}}` 将 vector_search 限定在本域文档内。

```python
# 每个 Skill 定义本域文档集合
_SOURCES = {"考勤&休假&福利指引20251023_clean.md"}

# 检索时限定来源
_where = {"source": {"$in": list(_SOURCES)}}
retriever.search(query, method="hybrid", top_k=8, where=_where)
```

BM25 本地运算无法传 `where`，保留 `_filter_by_source` 作为兜底过滤。

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
| `OLLAMA_OPTIONS` | `{"num_ctx": 4096, "temperature": 0}` | `temperature=0` 消除 LLM 随机性，确保同一问题每次结果一致 |
| `AUGMENT_QUESTIONS` | `True` | 是否生成增强索引问题；`False` 跳过，适合快速调试 |

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

## 设计问题记录

记录开发过程中遇到的核心问题、讨论过程与解决方案，供后续参考。

---

### 问题一：BM25 补漏机制的设计与取舍

**初衷**：hybrid 检索（BM25 + 向量 RRF 融合）存在一个结构性缺陷——当某个 chunk 的向量 embedding 因多主题内容被稀释时，它只能获得 BM25 单路 RRF 贡献（≈0.016），低于双路命中结果（≈0.032），容易被 top_k 截断。典型场景："生日福利"只出现在一张多主题关爱福利大表中，表的 embedding 被稀释，向量无法命中，hybrid 截断后大表消失。BM25 补漏的设计是：检查 top5 结果是否包含目标词，未命中则用 BM25 扩大 top_k 再捞一遍。

**遇到的问题**：
- BM25 原始分（~13.8）与 hybrid RRF 分（~0.032）量纲完全不同，合并后 BM25 结果异常高分压制正确的 hybrid 结果
- 自检条件（字面匹配）在同义词场景误触发：用户问"年假"，文档写"年休假"，top5 里有正确结果但字面不含"年假"，补漏被反复触发
- 即便将 BM25 分数转为 RRF 等效分（rank → 1/(60+rank+1)），单路 BM25 chunk 的最高分（0.016）仍低于任何双路命中结果（0.032+），补漏结果始终排在正确结果后面，无法真正"救出"目标 chunk

**为何最终移除**：增强索引上线后，原本向量无法命中的大表，通过"生日福利有哪些"等问题向量变成双路命中，分数从 0.016 升到 0.032，自然进入 top_k，补漏的使用场景被从根本上消除。

**何时仍有价值**：若未部署增强索引，或知识库中存在大量精确实体（型号编码、人名、数字串等增强索引无法覆盖的内容），BM25 补漏仍是有效的兜底手段，但需要解决量纲统一问题（将 BM25 分数按排名转为 RRF 等效分）。

---

### 问题二：多域知识库下的检索区域划分

**问题本质**：当知识库包含多个业务域（如差旅报销、考勤福利）时，向量索引是全域共享的。搜索某域 query 时，其他域的语义相近 chunk（包括增强索引的问题向量）会被召回，占用 top_k 名额，挤出本域正确结果。这不仅是增强索引的问题，普通 chunk 的向量检索同样面临跨域干扰。

**设计决策**：本系统采用 Skill 路由架构，每个 Skill 已明确划定业务域，因此检索区域应该在 Skill 层就做收窄，而不是依赖事后过滤。事后的 `_filter_by_source` 只能删掉结果，无法补回被跨域 chunk 挤走的正确 chunk。在每个 Skill 的 vector_search 调用中传入 `where={"source": {"$in": list(_SOURCES)}}` 实现前置过滤，从源头隔离跨域干扰。

---

### 问题三：BM25 在 hybrid 中的角色定位

**结论**：BM25 在 hybrid 中的核心价值是**确认信号**——与向量双路命中的 chunk 分数叠加（0.016 × 2 = 0.032），提升可靠性排名。其次是**精确实体匹配**（型号、编码等 embedding 不敏感的内容）。增强索引上线后，BM25 通过"独家发现"弥补语义鸿沟的场景被覆盖，角色从"补漏主力"退为"确认信号 + 精确实体兜底"，这是合理的分工而非 BM25 价值下降。

**RRF 核心逻辑**：`score = 1/(k+rank+1)`，k=60。单路命中 rank=0 约 0.016，双路命中约 0.032。调权重无法从根本上解决单路 vs 双路的结构性差距（需要权重 > 30 倍才能反超），正确解法是通过增强索引让目标 chunk 进入向量侧，成为双路命中。

---

### 问题四：伞形概念与文档信息架构的语义鸿沟

**问题**：用户使用上位概念提问（如"结婚福利"），而文档将其拆分为多个独立章节。单次向量检索倾向于语义最相近的某一个子项，无法同时覆盖全部相关内容。直接依赖 LLM 在 Generator 阶段推断关联关系也不可行，因为 Generator 阶段已无法再发起检索。

**解决方案**：在 Skill 层维护 `_CONCEPT_MAP` 领域词典，将伞形概念展开为多个具体检索词，每个词独立 hybrid 检索后合并去重。这样每个子项都能以最精确的关键词独立命中，避免单次检索的覆盖盲区。相比依赖 LLM 自动扩写，词典方案确定性更强，不引入额外 LLM 调用延迟。

---

## 架构演进记录

详见 [PLAN.md](./PLAN.md)，记录了从 v1.0 到 v2.0 的设计决策、方案对比和关键取舍。
