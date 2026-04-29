# Codex 工程理解笔记

生成时间：2026-04-29

本文档是我结合 `README.md`、核心代码、`skills/`、`tests/`、`tasks/` 和知识库目录后，对当前 `Agentic_RAG` 工程的理解记录。它不是用户使用手册，而是偏工程维护视角的地图，方便后续协作时快速进入上下文。

## 1. 项目定位

这是一个企业内部知识库问答系统，核心思路不是单次检索后直接生成答案，而是引入 Agentic RAG 流程：

1. 先用 LLM 做查询语义解析，识别用户问题中的 Who / Where / What、约束条件、意图颗粒度、是否需要追问。
2. 再由 Planner 根据可用 Skill 列表生成结构化检索计划。
3. Executor 串行执行 Skill，并处理前后步骤依赖和 `<step_N_result>` 占位符。
4. Generator 汇总检索结果，基于内部文档生成最终回答。

系统面向的是公司内部制度、流程、报销、考勤、IT、行政和资产管理等场景。当前实现更像一个带业务策略层的 RAG 应用，而不只是通用向量搜索壳子。

## 2. 两条主链路

### 2.1 离线/启动时入库链路

```text
knowledge_base/
  -> convert_pdfs()
  -> clean_documents()
  -> chunk_markdown() / chunk_text()
  -> Retriever.build_index()
  -> 可选 index_augmenter.generate_augmented_entries()
```

关键点：

- `document_loader.py` 扫描 `knowledge_base/`，PDF 会先尝试用 Docling 转 Markdown。
- Markdown 会经过 `doc_cleaner.py` 清理页眉、页脚、版本号、文件编号等污染内容。
- `chunk_markdown()` 是表格感知分块：表格尽量保持完整，并把标题带入表格 chunk，避免检索时丢上下文。
- `retriever.py` 用 ChromaDB 建内存向量索引，同时支持 BM25 和 hybrid 检索。
- `index_augmenter.py` 会为 chunk 生成 8-10 个用户视角问题，把“用户问法”和“文档术语”之间的语义差距提前补上。

### 2.2 在线问答链路

```text
app.py
  -> agentic_rag.run()
    -> query_understanding.parse_query()
    -> planner.plan()
    -> executor.execute_plan()
    -> generator.generate()
```

关键点：

- `app.py` 是 Streamlit 前端，负责初始化知识库、展示调试信息、历史记录、满意度评价、页面图片引用。
- `agentic_rag.py` 只负责编排，不承载业务规则。它支持 `on_progress` 回调，供 UI 展示“语义分析中 / 制定检索计划 / 检索执行中 / 生成回答中”。
- `query_understanding.py` 目前只保留 `where.value`，已经移除了早期的 `where.scope`。
- `planner.py` 根据 Skill 描述和 QueryStructure 生成 JSON steps。
- `executor.py` 会把每个 Skill 执行结果中的关键实体提取出来，供后续 step 替换占位符。
- `generator.py` 把所有检索结果拼成上下文，并根据意图颗粒度、推断维度、冲突检测和分类结论补充 prompt 约束。

## 3. 核心模块职责

| 模块 | 职责 | 我读到的重点 |
| --- | --- | --- |
| `app.py` | Streamlit UI | 展示 Step 0/Planner/Executor/Answer；支持历史、满意度、图片页展示 |
| `agentic_rag.py` | 主流程编排 | 不含业务逻辑，支持进度回调 |
| `query_understanding.py` | 查询结构化 | Who/Where/What、constraints、granularity、conflicts、clarification |
| `planner.py` | 检索计划生成 | 解析 LLM JSON，容错返回 `error` |
| `executor.py` | Skill 执行 | 串行执行、占位符替换、异常不中断 |
| `generator.py` | 最终回答生成 | 拼上下文、控制回答风格、注入单/多城市分类结论、处理页码引用 |
| `retriever.py` | 检索基础设施 | ChromaDB vector、BM25、hybrid/RRF、增强索引命中回原文 |
| `document_loader.py` | 文档加载和分块 | PDF 转 MD、clean 优先、表格完整分块 |
| `doc_cleaner.py` | 文档清洗 | 固定规则 + LLM 判断重复污染段落 |
| `index_augmenter.py` | 增强问题索引 | chunk MD5 缓存，减少重复 LLM 调用 |
| `utils.py` | 通用工具 | 关键实体提取、表格清洗、地区分类结果解析 |
| `evaluator.py` | 满意度记录 | 满意计数，不满意保存完整上下文 top3 |
| `pdf_vision_loader.py` | 图片型 PDF 文字提取 | 每页截图后用 Ollama 视觉模型提取文字 |
| `pdf_vision_qa.py` | PDF 页面图片缓存/直答 | 构建页面 PNG 缓存，供前端展示原始页 |

## 4. Skill 体系

`skills/__init__.py` 会动态扫描 `search_*.py` 文件并注册 Skill，`search_example.py` 作为模板不加载。

当前实际加载的 Skill：

| Skill | 对应知识域 | 检索策略 |
| --- | --- | --- |
| `search_expense_reimbursement` | 报销、差旅费、补贴、费用标准 | 复合链路：配置规则分类 + LLM 兜底 + vector 标准检索 + 表格提升 |
| `search_attendance` | 考勤、休假、福利 | what 降噪 + 概念扩写 + hybrid + 来源过滤 + 表格提升 |
| `search_admin_guide` | 行政办公、会议室、快递、班车、印章、档案等 | what 降噪 + 概念扩写 + hybrid + 来源过滤 + 表格提升 |
| `search_it_guide` | IT 设备、账号、网络、权限、信息安全 | what 降噪 + 概念扩写 + hybrid + 来源过滤 + 表格提升 |
| `search_asset_management` | 固定资产、非固资、资产申请/调拨/盘点/处置 | what 降噪 + 概念扩写 + hybrid + 来源过滤 + 表格提升 |

通用 Skill 模式基本一致：

```text
query_structure.dimensions.what
  -> _expand_query()
  -> retriever.search(method="hybrid", where=source_filter)
  -> _merge_deduplicate()
  -> _boost_table_chunks()
  -> _filter_by_source()
```

报销 Skill 是当前最特殊的一条链：

```text
where.value
  -> _split_cities()
  -> 每个 city 调 _execute_for_city()
  -> config/region_classification.json 确定性分类
  -> 未命中时使用 llm_classify_region() 兜底
  -> 构造 standards_query
  -> vector 检索报销标准
  -> 表格提升和金额自检
  -> 注入 classification_conclusion chunk
  -> 多城市结果合并去重
```

## 5. 多城市支持

实现位置：`skills/search_expense_reimbursement.py`

当前行为：

- 从 `query_structure.dimensions.where.value` 取地点字符串。
- `_split_cities()` 支持 `,`、`，` 和 `和` 分隔，例如 `深圳, 德国`、`深圳，德国`、`深圳和德国`。
- 多个城市时，每个城市独立走分类和标准检索链路。
- `_merge_deduplicate()` 合并多城市检索结果，按 text 前 100 字去重。
- 分类结论 chunk 会携带 `entity`、`scope_label`、`category`、`full_category`。
- Generator 会收集所有分类结论并注入 prompt，例如“深圳属于境内A类；德国属于境外A类”，避免只读取第一个结论。

需要留意：

- 当前切分规则是 `re.split(r"[,，和]", where_value)`，它会把所有“和”字都当分隔符。对“共和县”“和田”这类地名可能有误切风险。

## 6. 知识库内容

当前 `knowledge_base/` 包含以下主要知识域：

| 文件 | 内容 |
| --- | --- |
| `报销相关_clean.md` | 费用报销及付款规定、差旅费、出差地区分类、境内/境外标准、招待费等 |
| `考勤&休假&福利指引20251023_clean.md` | 考勤、打卡、加班、年假、病假、产假、婚假、福利等 |
| `OA新员工-行政指引2025.7.7 _clean.md` | 着装、办公用品、会议室、快递、交通、差旅服务、办公室安全、印章、档案等 |
| `【光峰】新员工IT指引_clean.md` | 办公电脑、网络、邮箱/OA/HR/ERP/PLM/JIRA/CRM 等账号、信息安全、IT 支持 |
| `资产管理流程_clean.md` | 由图片型 PDF 视觉提取得来，按页组织，并包含 `__PAGE_IMG__` 页面图片标记 |

资产管理流程的 `_clean.md` 使用相对知识库路径记录页面图片，例如 `__PAGE_IMG__:.page_cache/资产管理流程/page_01.png`。`app.py` 的 `_resolve_page_img_path()` 同时兼容旧的 Linux 绝对路径和新的相对路径，因此跨 Windows/Linux 或项目目录迁移时更稳。

## 7. 测试现状

测试目录覆盖了以下层次：

- `test_chunking.py`：Markdown 表格完整性和普通文本分块。
- `test_retriever.py`：BM25、RRF、hybrid 降级和 search 路由。
- `test_planner.py`：Planner JSON 解析和 LLM 失败容错。
- `test_executor.py`：Skill 执行、占位符替换、异常容错。
- `test_query_understanding.py`：QueryStructure 解析、fallback、追问、约束、冲突。
- `test_utils.py`：关键实体提取、表格清洗、`llm_classify_region` 解析行为。
- `test_search_expense_reimbursement.py`：配置规则分类、多城市拆分、LLM 兜底、金额表格重试。
- `test_generator.py`：单城市/多城市分类结论注入 Generator prompt。
- `tests/integration/test_llm_classify_reasoning.py`：真实 LLM fallback 分类能力，使用生产配置生成的规则上下文。

当前本地环境没有完整运行依赖，测试由用户在本地手动验证。

## 8. 当前状态与注意事项

README 已同步当前代码结构，早期 `where.scope` 残留已移除。报销分类已从“LLM 判断为主”改为 `config/region_classification.json` 配置规则优先，配置未覆盖时才调用 `llm_classify_region()` 兜底。视觉 PDF 图片标记也已改为跨平台相对路径。

仍需注意：

1. `config/region_classification.json` 是报销地区分类的受控规则源，欧洲国家、境外 B 类示例、境内 C 类示例需要由业务/财务持续确认维护。
2. `_split_cities()` 目前会按“和”切分，对“共和县”“和田”等地名有潜在误切风险；后续更稳的方向是让 QueryUnderstanding 输出结构化地点数组。
3. 仓库根目录还有用户未提交的 `knowledge_base` PDF 改动、`pdf_pages/` 图片和其它相邻目录变更，提交时要继续小心区分本次工程改动与用户本地文件。
