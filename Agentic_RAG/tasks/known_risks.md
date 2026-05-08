# 已知风险与待办（R-x）

> 由近期失败用例（TE8 / TE20 / TE25 / TE31）和 OpenAI 通道接入引出的待办清单。
> 命名规则：`R-x` 为风险/待办编号，被 README "设计问题记录"反向引用。
> 每条含：**根因引用** / **当前状态** / **完成标准** / **优先级**。

---

## R-1 表格合并单元格在 PDF→Markdown 转换时丢失（治本）

**根因引用**：README 问题八 / TE8

**当前状态**：仅识别根因，**临时缓解未实施**（用户未同意手工修改 `报销相关_clean.md`）。Docling `export_to_markdown()` 对合并单元格做错位填充，导致销售人员 A 类金额完全丢失。

**完成标准**：
- [ ] 在 `document_loader._convert_single_pdf` 中绕过 `export_to_markdown()`，自定义渲染器读取 `DoclingDocument.tables[*]` 的 `col_span / row_span` 信息
- [ ] 渲染策略：合并单元格的值复制填充到所有展开后的格子（保证语义不丢失）
- [ ] 子分类标签行（如"销售人员/非销售人员"独占一行）合并到下一行作为子分类前缀
- [ ] `tests/test_chunking.py` 增加 fixture：含合并单元格的 mock DoclingDocument，断言展开后所有数值列正确
- [ ] 全量重跑 ingest，对照 `报销相关.md` 与 `报销相关_clean.md`，确认所有金额单元格不再缺失

**优先级**：🔴 高（直接影响财务类查询正确性）

---

## R-2 Markdown 标题层级误用导致父语境丢失（治本）

**根因引用**：README 问题九 / TE20

**当前状态**：仅识别根因，**临时与治本均未实施**。`document_loader.chunk_markdown` 按 H1-H3 同等切节，节内若不超 `CHUNK_SIZE` 就不会触发 `_with_heading` 父标题注入，导致孤儿 chunk 完全失去父语境。

**完成标准**：
- [ ] `chunk_markdown` 引入"标题栈注入"：维护 H1/H2/H3 三层栈，每个 chunk 入库前前置当前所有活跃高级标题
- [ ] 进入更高级标题时清空更深层栈（避免跨节标题污染）
- [ ] 兼容性：旧的 `_with_heading` 仅在"超 CHUNK_SIZE 拆分子块"路径生效，新逻辑覆盖"整节直接入库"路径
- [ ] `tests/test_chunking.py` 增加用例：父标题 + 同级误用子标题（即 TE20 复刻），断言子 chunk 文本含父标题字符串
- [ ] 修复 `OA新员工-行政指引2025.7.7 _clean.md:131-141` 班车段的 H2 误用为 H3（兜底）

**优先级**：🔴 高（影响所有 markdown 文档的层级误用场景）

---

## R-3 表格"形状审计"检测脚本（兜底）

**根因引用**：README 问题八延伸 / 上一轮讨论的方案 D

**当前状态**：未实施。即使 R-1 治本，仍需检测"VLM 重提取后的输出""人工编辑后的 markdown"是否还有错位。

**完成标准**：
- [ ] 新增 `tools/audit_tables.py`，扫描所有 `_clean.md`，对每张 markdown 表格执行三类启发式检测：
  - 列内类型混杂（数值列混入分类标签）
  - 行宽不一致（某行列数与表头不符）
  - 标签 + 重复数值模式（如 `[..., "销售人员", "50元/天", "50元/天"]` 暗示 colspan 拆错）
- [ ] 命中告警写入 `<file>.audit.txt`，**不阻断**入库（避免误杀合法表格）
- [ ] `document_loader.convert_pdfs` 完成后自动调用一次审计

**优先级**：🟡 中（R-1 治本前先上这条防回归）

---

## R-4 PDF 视觉块检索路径（长期方向）

**根因引用**：README 问题七延伸 / 上一轮讨论的"模式 1"

**当前状态**：仅讨论未实施。R-1/R-2 是逐点修补 PDF→MD 管道的脆弱性，但该管道还会在列表层级、跨页内容、脚注、双栏版面等场景继续踩坑。视觉检索从根上消除中间层。

**完成标准**：
- [ ] 在 `pdf_vision_qa.py` 基础上增加"按召回页推送"模式：检索召回 top-k 页 → 仅把这几页的图片塞给 VLM 回答
- [ ] 路由策略：query 含数值/精确事实类关键词（如"多少/标准/金额/限额"）走视觉路径，文字类继续走 MD 文本检索
- [ ] 评估对比：选 10 条"金额/标准类"失败用例，对比 MD 路径 vs 视觉路径的准确率与延迟
- [ ] 与现有 MD 链路并存（不替换，混合路由）

**优先级**：🟢 低（探索性，等 R-1/R-2 落地后启动）

---

## R-5 OPENAI_API_KEY 改为环境变量读取（安全）

**根因引用**：README 模型配置注意事项 / OpenAI 通道接入

**当前状态**：`config.py` 中 `OPENAI_API_KEY` 以明文形式硬编码（`sk-5c83...`）。当前 `config.py` 已被 git 跟踪，**有提交泄露风险**。

**完成标准**：
- [ ] `config.py` 改为 `OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")`
- [ ] 提供 `.env.example` 模板（不含真实密钥）和 `.env`（在 `.gitignore` 中排除）的使用说明
- [ ] `llm._call_openai` 在 key 为空时给出清晰错误提示（"未配置 OPENAI_API_KEY 环境变量"）
- [ ] 检查 git 历史，必要时 `git filter-repo` 清理已提交的明文密钥
- [ ] 撤销当前已暴露的 key，签发新 key

**优先级**：🔴 高（安全合规问题）

---

## R-6 模型名 `gpt-5.4` 网关侧验证

**根因引用**：OpenAI 通道接入

**当前状态**：未验证。`OPENAI_MODEL = "gpt-5.4"` 是网关 `aicode.wewell.net` 自定义路由名，**OpenAI 官方无此模型**。若网关识别不了会导致首次调用就失败。

**完成标准**：
- [ ] 联系网关运维确认 `gpt-5.4` 是否为有效路由名
- [ ] 若否，替换为网关支持的模型 ID（如 `gpt-4o-mini` 等），并更新 README 配置项表
- [ ] `llm._call_openai` 增加首次调用的健康检查日志（model / base_url / 响应耗时）

**优先级**：🟡 中（不修复则 OpenAI 通道不可用）

---

## R-7 Skill 描述边界的回归覆盖（防 TE25 同型再发）

**根因引用**：README 问题十 / TE25

**当前状态**：本次只修了 OA 系统名 vs 出差业务的路由消歧，但同型潜在地雷仍在：
- "HR 系统怎么请假" → 应走 `search_attendance` 而非 `search_it_guide`
- "ERP 里怎么提物料申请" → 应走 `search_asset_management` 而非 `search_it_guide`
- "OA 审批权限怎么调整" → 边界模糊（IT 还是治理？）

**完成标准**：
- [ ] `tests/test_planner.py` 增加 `TestSystemVsBusinessRouting` 类：
  - "HR 系统请假流程" → 期望 `search_attendance`
  - "ERP 物料申请" → 期望 `search_asset_management`
  - "OA 出差申请" → 期望 `search_expense_reimbursement`（TE25 同款，回归用例）
- [ ] 测试以 mock LLM 形式跑（不依赖真实 LLM），mock 返回值需先用真实 LLM 验证一次合理性

**优先级**：🟡 中（TE25 已修，但缺少回归保护）

---

## R-8 区域无关关键词集合的误伤监测

**根因引用**：README 问题十一 / TE31

**当前状态**：`query_understanding._REGION_INDEPENDENT_KEYWORDS` 是手工维护的关键词列表，可能误伤本应追问的 query。如"调整深圳住宿费"——含"调整"会被兜底，但用户实际想知道某城市绝对金额。

**完成标准**：
- [ ] 监控线上日志：记录所有被 `_looks_region_independent` 兜底纠正的 query 与原始 needs_clarification 决策的差异
- [ ] 累计 ≥20 条误伤样本时，将关键词从纯字符串匹配改为"关键词 + 排除规则"（如"调整"出现且 query 含明确城市名时不兜底）
- [ ] 长期：改为小型分类器（基于规则或轻量 LLM），替代关键词匹配

**优先级**：🟢 低（当前关键词已足够保守，等真实数据再调）

---

## 优先级顺序建议

执行顺序按"风险高 + 改动小"优先：

1. **R-5（高/小）** —— 半小时改完，密钥安全立刻闭环
2. **R-6（中/小）** —— 一封消息验证，OpenAI 通道是否可用
3. **R-2（高/中）** —— chunker 标题栈注入，受益面广（覆盖所有 markdown 文档）
4. **R-3（中/中）** —— 表格审计脚本，作为 R-1 前置防护
5. **R-1（高/大）** —— Docling 自定义渲染器，最复杂但最彻底
6. **R-7（中/小）** —— Planner 路由回归测试，配合 R-1/R-2 一起跑
7. **R-4（低/大）** —— 视觉检索路径，长期方向
8. **R-8（低/小）** —— 关键词误伤监测，等线上数据
