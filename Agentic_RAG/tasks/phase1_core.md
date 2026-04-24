# Phase 1 — 核心骨架

> 目标：跑通完整的"提问 → Planner → Executor → Generator → 回答"主流程
> 验收方式：统一通过 `streamlit run app.py` 启动页面，在页面上操作和观察结果
> 编码要求：遵守 PLAN.md 第八章编码规范（高内聚低耦合、可读性、设计模式、TDD）

---

## T1-1 搭建目录结构与知识库

**任务：** 创建工程所需的目录和文件骨架，提示手动复制知识库文档

**支持的文档格式：**
- `.md` — 直接进入表格感知分块
- `.txt` — 直接进入普通分块（无表格结构）
- `.pdf` — 先通过 Docling 转换为同名 `.md`，再进入表格感知分块；原始 PDF 始终保留

**PDF 转换策略：跳过已转换的文件**
- 扫描 `knowledge_base/` 时，若发现 `foo.pdf`，先检查同目录下是否已存在 `foo.md`
- 若 `foo.md` 已存在，跳过转换，直接使用已有的 `.md` 文件
- 若 `foo.md` 不存在，调用 Docling 转换并生成 `foo.md`

**完成标准：**
- [ ] `Agentic_RAG/` 下存在 `agentic_rag.py`、`app.py`、`skills/`、`knowledge_base/`、`tests/`
- [ ] `knowledge_base/` 下有出差报销相关的知识库文档（含城市分类规则和费用标准）
- [ ] 放入新 PDF 时，系统启动自动转换并生成同名 `.md`，终端打印 `[Loader] 转换 PDF: foo.pdf → foo.md`
- [ ] 同名 `.md` 已存在时，跳过转换，终端打印 `[Loader] 跳过已转换: foo.pdf`
- [ ] `streamlit run app.py` 能启动，浏览器页面正常打开（内容为空或占位提示均可）

---

## T1-2 实现 Retriever 基础类

**任务：** 实现 `Retriever` 类，提供 `vector_search` 方法，供 Skill 调用

**分块要求（重点）：** 必须使用表格感知分块策略
- Markdown 表格无论大小，必须保持为一个完整的 chunk，不得在表格中间截断
- 表格内的空行不能作为分块边界
- 普通文本超过 `CHUNK_SIZE` 时才按字符拆分，表格不受此限制

**完成标准：**
- [ ] `Retriever` 能读取 `knowledge_base/` 下所有文档并建立向量索引
- [ ] 返回格式：每条包含 `text`、`source`、`score` 三个字段
- [ ] **Streamlit 验收（分块正确性）：** 页面调试区展示所有 chunk 列表，人工确认城市分类表格和费用标准表格各自完整地在一个 chunk 内，没有被截断
- [ ] **Streamlit 验收（检索正确性）：** 页面上输入"A类城市"，检索返回的 chunk 包含完整的分类规则表格，不是半截内容

---

## T1-3 实现第一个 Skill：search_classification

**任务：** 按模板编写 `skills/search_classification.py`

**完成标准：**
- [ ] 文件存在且符合模板格式（含 `SKILL_META` 和 `execute`）
- [ ] 启动时终端输出 `[SkillLoader] 已加载 Skill: search_classification`
- [ ] **Streamlit 验收：** 页面提问"深圳属于哪类城市"，页面展示 Skill 调用过程，可见 `search_classification` 被调用，返回结果包含分类规则

---

## T1-4 实现第二个 Skill：search_standards

**任务：** 按模板编写 `skills/search_standards.py`

**完成标准：**
- [ ] 文件存在且符合模板格式
- [ ] 启动时终端输出 `[SkillLoader] 已加载 Skill: search_standards`
- [ ] **Streamlit 验收：** 页面提问"A类城市住宿费标准"，可见 `search_standards` 被调用，返回结果包含具体金额

---

## T1-5 实现 Planner

**任务：** 调用 LLM，将用户问题转化为结构化 Skill 调用计划（JSON）

**说明：** step 数量由 Planner 根据问题复杂度动态决定，不固定。简单问题可能只有1个 step，多层依赖问题可能有3个或更多。

**完成标准：**
- [ ] Planner 输出合法 JSON，step 数量和内容由 LLM 自行分析决定
- [ ] **Streamlit 验收（简单问题）：** 输入"A类城市住宿费是多少"，Planner 应识别为单步直接检索，页面可见1个 step
- [ ] **Streamlit 验收（多步依赖问题）：** 输入"深圳出差住宿费是多少"，Planner 应识别出需要先查分类再查标准的依赖关系，页面可见多个 step 且 `depends_on` 关系正确
- [ ] LLM 输出非法 JSON 时，页面显示友好错误提示，不白屏崩溃

---

## T1-6 实现 Executor

**任务：** 按 Planner 输出的计划串行执行 Skill，处理 `depends_on` 和占位符替换

**完成标准：**
- [ ] 按 `step_id` 顺序执行，有 `depends_on` 的 step 在依赖完成后才执行
- [ ] `{{step_1_result}}` 在执行前被替换为第1步检索结果的文本摘要
- [ ] **Streamlit 验收：** 页面展示每个 Step 的执行状态（执行中 / 完成 / 返回 N 条结果），人工确认执行顺序正确

---

## T1-7 实现 Generator

**任务：** 将所有 Skill 检索结果拼接后，调用 LLM 生成最终回答

**完成标准：**
- [ ] 最终回答包含具体金额数字
- [ ] 回答中注明信息来源文档名
- [ ] **Streamlit 验收：** 页面底部展示最终回答，内容符合上述要求

---

## T1-8 实现 Streamlit 页面布局

**任务：** 完善 `app.py` 页面结构，使验收所需信息清晰可见

**页面需展示的内容：**
- 用户输入框
- 提交后展示用户提问的问题原文
- Planner 输出的调用计划（可折叠）
- 每个 Step 的执行过程与检索结果（可折叠）
- 最终回答（突出显示）

**完成标准：**
- [ ] 以上五块内容均在页面上有对应区域
- [ ] 提问原文在回答流程开始前清晰展示
- [ ] 可折叠区域默认折叠，避免页面过长

---

## T1-9 端到端验收

**任务：** 在 Streamlit 页面上用两个验收问题跑完整流程，人工核对

**验收问题 1：** "深圳出差住宿费是多少？"

期望页面展示：
- 调用计划：Step 1 `search_classification`，Step 2 `search_standards`（depends_on: 1）
- Step 1 结果：包含城市分类规则的文本
- Step 2 结果：包含A类城市住宿费金额的文本
- 最终回答：深圳属于A类城市，住宿费标准为 xxx 元/天

**验收问题 2：** "揭阳出差住宿费是多少？"

期望页面展示：
- 调用计划与深圳相同（同一路径）
- 最终回答：揭阳未在A/B类中列出，按C类标准，住宿费为 xxx 元/天，回答中体现推断过程
