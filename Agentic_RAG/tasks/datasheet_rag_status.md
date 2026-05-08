# Datasheet RAG 任务状态（2026-05-07）

对照 `tasks/datasheet_rag_plan.md` 的 Phase 0~6 执行状态。

结论：本轮继续推进后，Phase 5 真实 generator answer 层严格指标已闭环。`generator.py` 现在把 `required_terms/must_have_terms` 注入 context，并在技术 datasheet prompt 中强制“必须覆盖的期望术语/数值”逐项原样输出，避免同一参数 continuation rows / 多档位只摘要第一行。真实 generator sample 复跑产物 `evaluation/.datasheet_real_generator_sample_metrics.json`：`sample_count=3`、`llm_judge_pass_count=3`、`effective_pass_count=3`、`parse_error_count=0`、`failed_cases=[]`、`deterministic_failed_cases=[]`。当前 15 个 retrieval baseline case 全部通过，`recall@10=1.0`、`recall@20=1.0`、`failed_cases_at_20=[]`；大范围 datasheet pytest 通过：`58 passed in 78.78s`。

## 最新验证结论

- 已修复早前后台大范围测试失败：`spi_flash_voltage_condition` anchor 为空，现指向 `dlpc3436_clean.md` line 918。
- 已修复剩余 3 个 retrieval baseline case：
  - `ds_param_003`：DMD parking timing 聚合 timing table + GPIO_08 normal park + PARKZ fast park note。
  - `ds_enum_001`：I2C/IIC 端口枚举聚合 IIC0/IIC1 pin rows + 100-kHz baud-rate interface paragraph。
  - `ds_state_001`：I2C command readiness 聚合 HOST_IRQ startup / auto-initialization sequence。
- Phase 2/3/6 基础设施：
  - `document_loader.chunk_markdown()` 生成 block chunk 时补 `index_kind="block"`、`normalized_text`、`entity_tokens`、`is_datasheet`。
  - `retriever.build_datasheet_row_chunks()` 可从 `knowledge_base/.structure/dlpc3436.structure.json` 生成 row-level chunks，保留 `row_id/table_id/section_id/source_line`。
  - `retriever.normalize_datasheet_text()` 统一 `I 2 C/I²C/IIC -> I2C`、`GPIO08 -> GPIO_08`、`PLL REFCLK I -> PLL_REFCLK_I`、`+/-200 PPM -> ±200 ppm`、`f clk -> f_clk`。
  - `Retriever` 索引与 BM25 查询优先使用 `normalized_text`，返回结果保留原文用于 generator。
  - `index_augmenter._should_augment()` 对 `is_datasheet=True` chunk 返回 `False`，避免 datasheet 被 LLM 自然语言问题增强污染。
- Phase 2 完整化切片：
  - `DatasheetIndexConfig(row_chunks=...)` 注入 row index 数据。
  - `Retriever.build_index()` 在有 row chunks 时创建两个物理 collection：`agentic_rag_block` / `agentic_rag_row`；旧 `_collection` 保持指向 block collection 以兼容现有调用。
  - API：`search_block()`、`search_row()`、`search_datasheet_index()`；datasheet 合并路径按 row-first，再补 block context。
  - 回归：`tests/test_datasheet_dual_index.py`，验证 collection 名称、物理分离、row/block 查询和 I2C row+context 合并。
- 本轮新增 Phase 4 structure-driven bundle 切片：
  - `DatasheetIndexConfig.structure_path` 保存 structure digest 路径。
  - 新增 `plan_datasheet_evidence_bundle(query, retriever, top_k)`：推断 query_type，使用 row hits + block context，补 `section_id/section_title/table_id/row_id/source_line`。
  - `Retriever.search_datasheet_index(..., return_bundle=True)` 返回结构化 evidence bundle。
  - 新增 `tests/test_datasheet_structure_planner.py`，覆盖 I2C interface_ports 的 row evidence + 100-kHz block context + section metadata。
- 最终复跑命令：

```bash
cd /home/jjh/works/RAG_Projects/Agentic_RAG
.venv/bin/python -m pytest \
  tests/test_datasheet_structure_digest.py \
  tests/test_datasheet_source_metadata.py \
  tests/test_datasheet_retrieval_baseline.py \
  tests/test_datasheet_full_baseline.py \
  tests/test_datasheet_staged_retrieval.py \
  tests/test_datasheet_remaining_staged_retrieval.py \
  tests/test_datasheet_phase2_phase3_phase6.py \
  tests/test_datasheet_dual_index.py \
  tests/test_datasheet_structure_planner.py \
  tests/test_search_datasheet.py \
  tests/test_dlpc_datasheet_retrieval.py \
  tests/test_datasheet_pdf_pipeline.py \
  tests/test_dlpc3436_document_evidence.py -q
```

结果：`58 passed in 78.78s`。

## 已完成 / 部分完成 / 未完成

| 状态 | 计划项 | 当前证据 | 缺口 / 下一步 |
|---|---|---|---|
| ✅ 已完成 | `document_loader` 表格 chunk 识别修复 | `document_loader.py:_build_chunk()` 已使用 `any(line.strip().startswith("|") ...)`，可识别“heading + table” chunk | 继续保留测试覆盖 |
| ✅ 已完成 | `dlpc3436_clean.md` 已存在且 hash 已锁定 | `knowledge_base/dlpc3436_clean.md` sha256 = `a71748f822b2907416d19f841222f6137f676620e54432cbc9c2c98e3407c250` | 后续若重生成 clean md，必须重新 review golden evidence |
| ✅ 已完成 | datasheet generator prompt + 结构化引用 | `generator.py` 已有 `_TECHNICAL_DATASHEET_PROMPT_TEMPLATE`，按 `query_structure.domain == "technical_datasheet"` 或 `search_datasheet` 触发；prompt 注入结构化引用要求，回答末尾追加 `[Section: ...; Table: ...; Row: ...; line: ...]` | 后续接真实 LLM judge 抽样验证引用使用质量 |
| ✅ 已完成 | search_datasheet staged retrieval 小切片 | `skills/search_datasheet.py` 已优先调用 `search_datasheet_index(return_bundle=True)` / bundle planner；旧 oscillator / SPI flash / DMD parking / I2C ports / I2C command readiness staged context、query expansion、staged boost、去重保护、top20 返回保留为 fallback | 下一步可继续删减旧规则或保留兜底 |
| ✅ 已完成 | DLPC 技术 query 不走企业政策 clarification | `query_understanding.py` 已有 `technical_datasheet` 分支；相关测试保护 | 无新增动作 |
| ✅ 已完成 | spread-spectrum / MOSC 证据链复核 | `tests/test_dlpc3436_document_evidence.py` 在大范围测试通过 | 继续保留 evidence regression |
| ✅ 已完成 | doc_cleaner datasheet 保守清洗 | `doc_cleaner.py` 有 `_is_datasheet_document()` + `_clean_datasheet_content()`；`config.py` 已有 `DATASHEET_SOURCES` 白名单 | 后续扩 product-family 时补更多 datasheet source |
| ✅ 已完成 | baseline cases JSON | `evaluation/datasheet_baseline_cases.json` 15 cases，覆盖 parameter / enumeration / connection / support / state；含 adversarial case；source hash 已更新 | 后续可继续扩充真实用户 query |
| ✅ 已完成 | retrieval-only baseline 脚本 | `tests/test_datasheet_retrieval_baseline.py` 输出 `evaluation/.datasheet_retrieval_metrics.json`；当前 15 cases：recall@10=1.0、recall@20=1.0、required_terms_hit_rate=1.0、failed_cases_at_20=[] | 当前 baseline 已全过；后续扩数据集 |
| ✅ 已完成 | DLPC 单点 evidence/retrieval 测试 | `tests/test_dlpc3436_document_evidence.py`、`tests/test_dlpc_datasheet_retrieval.py`、`tests/test_search_datasheet.py` 均在大范围测试通过 | 单点测试继续作为回归保护 |
| ✅ 已完成 | `config.py` datasheet source 白名单 | `DATASHEET_SOURCES={"dlpc3436.pdf", "dlpc3436.md", "dlpc3436_clean.md"}` | 后续加入 `dlpc3437` 等 |
| ✅ 已完成 | chunk 级 `is_datasheet=True` metadata | `document_loader.py` chunk schema 已包含 `is_datasheet/index_kind/normalized_text/entity_tokens`；`tests/test_datasheet_phase2_phase3_phase6.py` 覆盖 | 后续扩 entity type 与 alias graph |
| ✅ 已完成 | full baseline 脚本骨架 + judge 抽样 | `tests/test_datasheet_full_baseline.py` 输出 `evaluation/.datasheet_full_metrics.json`、`evaluation/.datasheet_judge_sample_metrics.json`、`evaluation/.datasheet_real_llm_judge_sample_metrics.json`、`evaluation/.datasheet_real_generator_sample_metrics.json`；15 cases oracle hit=1.0、numeric_preservation=1.0；3-case deterministic judge sample pass_rate=1.0；真实 Ollama judge oracle sample：pass=3、parse_error=0、fallback=0；真实 generator sample：LLM judge pass=3、effective_pass=3、parse_error=0、failed_cases=[]、deterministic_failed_cases=[] | 后续扩 dataset/产品族覆盖 |
| ✅ 已完成 | baseline report | `evaluation/datasheet_baseline_report.md` 已更新到当前 15-case retrieval baseline 全通过状态 | 可在 Phase 5 后再追加 answer 层指标 |
| ✅ 已完成 | Phase 1 structure digest | `knowledge_base/.structure/dlpc3436.structure.json` 已存在，含 `section_tree/table_catalog/row_index/entity_inventory/alias_graph`；required anchors 测试通过 | 后续可补 LLM entity merge |
| ✅ 已完成 | Phase 2 block + row 双索引 | `Retriever.build_index()` 创建 `agentic_rag_block` / `agentic_rag_row`；`tests/test_datasheet_dual_index.py` 覆盖物理分离、row/block 查询和 row-first 合并 | 后续加强 parent block/table/section 回溯质量 |
| ✅ 已完成 | Phase 4 structure-driven planner | `plan_datasheet_evidence_bundle()` + `search_datasheet_index(return_bundle=True)` 已可输出 I2C interface_ports、oscillator、SPI flash、DMD parking、HOST_IRQ command-ready 的结构化证据包；`tests/test_datasheet_structure_planner.py` 覆盖 | 还需替换 `search_datasheet.py` staged rules，并继续加强 parent block/table/section 回溯质量 |
| ✅ 最小完成 | Phase 3 normalization | 已实现 `normalize_datasheet_text()`，索引/query 双向使用；覆盖 `I2C/IIC/I 2 C`、`GPIO_08/GPIO08`、`PLL_REFCLK_I`、`±200 ppm`、`f_clk` | 后续扩 alias graph、entity type 与更多符号 |
| ✅ 最小完成 | Phase 6 datasheet 关闭 AUGMENT_QUESTIONS | `_should_augment()` 对 `is_datasheet=True` 返回 False；测试覆盖 table-like datasheet chunk | 后续可改为 datasheet 专用结构化 entity/query augmentation |

## 本轮新增/修改文件

- 修改：`tests/test_datasheet_full_baseline.py`
- 新增/更新：`evaluation/.datasheet_judge_sample_metrics.json`
- 新增/更新：`evaluation/.datasheet_real_llm_judge_sample_metrics.json`
- 新增/更新：`evaluation/.datasheet_real_generator_sample_metrics.json`
- 更新：`tasks/datasheet_rag_status.md`
- 继承上一轮新增/修改：`retriever.py`、`tests/test_datasheet_structure_planner.py`、`tests/test_datasheet_dual_index.py`、`document_loader.py`、`index_augmenter.py`、`skills/search_datasheet.py`、`tests/test_datasheet_retrieval_baseline.py`、`tests/test_datasheet_staged_retrieval.py`、`tests/test_datasheet_remaining_staged_retrieval.py`、`tests/test_datasheet_structure_digest.py`、`tests/test_datasheet_phase2_phase3_phase6.py`、`scripts/regen_datasheet_structure.py`、`knowledge_base/.structure/dlpc3436.structure.json`

## 下一步执行顺序

1. 扩充 baseline dataset 后再宣称更广泛 product-family 覆盖。
2. 后续可继续减少旧 staged rules 依赖，扩大 structure bundle planner 覆盖。
3. 新增 Phase 7：按 `specification-reading-path` skill 落地规格书 Reading Path Reconstruction。先用 TE53 预演路径做 RED 测试，但实现必须是通用 `reading_closure`：anchor + followed cues + relation + quote/line，不允许 TE53 / Spread Spectrum / PLL_REFCLK 专用补漏。

## Phase 7 进展反馈（2026-05-07）

- 文档：`tasks/datasheet_rag_plan.md` 已新增 Phase 7 与 `reading_closure` 指标，明确这是规格书 RAG 核心能力，不是 TE53/footnote 补漏。
- 测试：新增 `tests/test_specification_reading_path.py`，先 RED 验证 TE53 reading path：6.10 timing table rows → annotation `(1)` → annotation `(2)` → external oscillator pin definitions。
- 实现：`retriever.py` 新增 `build_specification_reading_closure(query, source_path)`，输出 `subject/anchors/followed_cues/unresolved_cues/closure_complete`，每条 cue 保留 `quote/line/source/relation/confidence`。
- 单测：`tests/test_specification_reading_path.py` 当前 `2 passed in 0.11s`。
- 组合回归：`tests/test_specification_reading_path.py tests/test_datasheet_structure_planner.py tests/test_search_datasheet.py` 当前 `16 passed in 51.51s`。
- datasheet 大范围回归加入 Phase 7 测试后：`60 passed in 79.96s (0:01:19)`。
- Bundle 接入：`plan_datasheet_evidence_bundle()` / `search_datasheet_index(return_bundle=True)` 已返回 `reading_closure`；新增回归验证 TE53 bundle 中 closure 覆盖 timing table、annotation `(1)/(2)`、external oscillator 的 `PLL_REFCLK_I/O` 定义。
- 组合回归更新：`tests/test_specification_reading_path.py tests/test_datasheet_structure_planner.py tests/test_search_datasheet.py` 当前 `17 passed in 59.28s`。
- datasheet 大范围回归更新：`61 passed in 87.40s (0:01:27)`。
- Generator 接入：`generator.py` 已把 result-level `reading_closure` 格式化进 context 的“规格书阅读路径闭环”，并在技术 datasheet prompt 中新增 answer contract：最终回答必须覆盖 anchors 的 value/spec，以及 followed_cues 中的 condition/constraint/prohibition/definition/dependency；closure 未闭合时需说明 unresolved cues。
- Generator RED/GREEN：新增 `tests/test_datasheet_full_baseline.py::test_datasheet_generator_context_includes_reading_closure`，RED 失败于 prompt 未包含“规格书阅读路径闭环”，GREEN 后单测 `1 passed in 0.01s`。
- 组合回归更新：`tests/test_specification_reading_path.py tests/test_datasheet_structure_planner.py tests/test_datasheet_full_baseline.py tests/test_search_datasheet.py` 当前 `34 passed in 58.81s`。
- datasheet 大范围回归更新：`62 passed in 88.22s (0:01:28)`。
- 当前边界：Phase 7 backend 已完成 closure 构建 → bundle 输出 → generator context/prompt 消费；下一步只剩 TE53 UI 单例验证，以及后续扩 paragraph/caption/callout/NOTE-WARNING fixture。
- Phase 7 增强（paragraph / cross-reference / NOTE / figure caption）已完成：
  - 新增 `tests/test_specification_reading_path.py::test_reading_closure_follows_inline_note_and_split_section_reference`，覆盖 TSTPT_5 inline note、PDF 表格断行的 `See Section 7.3.8`、目标 section `Test Point Support` 与正常使用约束。
  - 新增 `tests/test_specification_reading_path.py::test_reading_closure_attaches_nearby_note_and_figure_caption_context`，覆盖 section-level NOTE、figure source context、Figure 9-2 caption 以及 normal power-down `(c)` 的 SYSPWR 50 ms 约束。
  - `retriever.py` 增强：entity token 支持 `TSTPT_n`，query/line normalization 支持 `TSTPT5 -> TSTPT_5`；`_nearby_reading_cues()` 支持 inline `Note:`、section `## Note` block、figure captions、较长 figure/list proximity window；`_join_split_section_reference()` 与 `_find_section_reference_lines()` 支持 PDF 转换导致的 split section reference；definition following 对已由 cross-reference 覆盖的 term 去重。
  - Phase 7 单测：`tests/test_specification_reading_path.py` 当前 `4 passed in 0.46s`。
  - Phase 7 + planner/generator/search 组合回归：`36 passed in 60.24s (0:01:00)`。
  - datasheet 大范围回归：`64 passed in 88.53s (0:01:28)`。


## 风险点

- 当前仓库状态显示整个 `Agentic_RAG/` 在父仓库视角是 untracked（此前 `git status --short` 输出 `?? ./`），因此“git diff”无法作为可靠完成证据。
- `config.py` 中存在明文 OpenAI key；后续报告/总结不要复制该值。
- 当前 15-case retrieval baseline 已全过，但 `search_datasheet.py` 仍有规则化/硬编码 staged retrieval；下一步应逐步迁移到结构化 bundle planner。
