# Datasheet RAG 演进计划

> 当前执行状态已标注：`tasks/datasheet_rag_status.md`
>
> 结论（2026-05-07）：DLPC3436 查询问题尚未全部解决。已完成表格 chunk 识别、clean md hash 锁定、generator prompt 雏形、search_datasheet 初版、technical_datasheet query 分支；未完成 Phase 0 baseline 闭环（15-20 cases、retrieval/full baseline、baseline report、config 白名单、chunk is_datasheet metadata、datasheet 跳过 augmenter）。

> 范围：针对 `knowledge_base/dlpc3436.pdf` / `dlpc3437.pdf` 这类**英文芯片 datasheet** 的 RAG 能力建设。
>
> 与项目主路线（`tasks/phase1_core.md` / `phase2_retrieval.md` / `phase3_*`）并列。
> 文档内 Phase 编号（Phase 0~6）为 datasheet 子方向内部使用，不与项目主路线 Phase 编号冲突。

---

## 1. 背景与动机

### 1.1 文档差异

`dlpc343x` 系列是 TI DLP Pico 投影芯片 datasheet，与项目内现有中文 HR/IT/资产指引在多个维度上根本不同：

| 维度 | 现有中文流程文档 | dlpc343x Datasheet |
|---|---|---|
| 语言 | 中文流程描述 | 英文技术规格 |
| 内容形态 | 章节段落 + 流程表 | 引脚表、寄存器表、电气特性表、时序图 |
| 用户问法 | "怎么申请笔记本"（语义） | "VDD_18 电压范围"、"I2C 地址"（精确术语） |
| 关键陷阱 | 跨域污染 | 中英混合查询 + 数值精度不能改写 + 跨章节合成 |

### 1.2 NotebookLM 验证查询作为标杆

通过 NotebookLM 验证查询 "DLPC3436 系统振荡器时序要求"，得到 6 行参数 timing 表 + 5 条关键技术补充要求（±200 PPM、不支持展频、外部驱动适用条件、过渡时间定义、晶振接线）。逐行核对 `dlpc3436.md` 后发现：

- **6 行 timing 表**集中在 `## 6.10 System Oscillator Timing Requirements`（line 690-699）
- **5 条补充要求分布跨度极大**：表注 (2) 在 line 701（紧邻），±200 PPM 在 line 1410（10.1 章），PLL_REFCLK 接线在 line 383-384 + line 1460（pin 表 + 10.1.2）

NotebookLM 的回答是**跨章节合成**的，不是单一 chunk 召回。这是当前架构最大的能力缺口。

### 1.3 当前架构对照

**已具备能力（验证过）：**

- Docling PDF→Markdown 还原：`6.10 System Oscillator Timing Requirements` 表格 6 行参数、所有数值/单位/范围（含 40%/50%、2%、10 ns）一字不差，表头 MIN/NOM/MAX/UNIT 完整保留
- Heading 前置切块：`document_loader._with_heading()` 把章节标题前置到 chunk，BM25 命中"System Oscillator"无压力
- Hybrid 检索：`retriever.search(method="hybrid")` 已支持
- 表格优先重排：现有 Skill 模板里的 `_boost_table_chunks` 可复用
- 域过滤：`where={"source": {"$in": [...]}}` 防止跨域污染

**已识别缺口：**

1. **跨章节多片段整合**：邻接 chunk（chunk_index ±1）够不到跨 700+ 行的相关信息
2. **结构信息损失**：当前 chunk 只是文本块，不知道自己属于哪节、哪表、哪行
3. **实体/别名缺失**：`I 2 C` / `I²C` / `IIC` / `f clk` / `f_clk` 等同义形态没有规整
4. **数值忠实度无约束**：generator prompt 是为流程类问答写的，不约束 datasheet 数值改写
5. **AUGMENT_QUESTIONS 副作用**：对参数表生成的"增强问题"质量差，污染索引
6. **doc_cleaner 不适配 datasheet**：通用清洗规则可能误删 NOTE / 脚注 / 表注

---

## 2. 设计原则

### 2.1 不要模仿 NotebookLM 的"回答风格"，要模仿它的"文档理解路径"

- ❌ 不要：每来一个新名词就往 `_CONCEPT_MAP` 里补一组关键词——这是人工规则补丁，长期一定崩
- ✅ 要：先把文档结构吃透（section / table / row / entity / alias），围绕实体做多跳检索

### 2.2 先量化 baseline，再按收益逐层加结构

- 不直接上"三层大架构"
- 每加一层架构必须能回答："它让哪类 datasheet query 的 recall / precision / answer fidelity 提升了多少？"
- 回答不了就不进主线

### 2.3 LLM 不进在线 query 主路径

- LLM 用于离线索引精修（entity merge / alias inference / type classification）
- 在线检索靠规则 + 索引结构
- 例外：在线 evidence selection 的最后一步可考虑 LLM，需实验验证

### 2.4 目标是可量化、可解释、可迭代

不是复现 NotebookLM 100%。如果某些类型问题用更轻的方法能到 80% NotebookLM 效果，就不必追求完全仿真。

---

## 3. 总体路线

| Phase | 内容 | 关键产物 | 开发顺序 |
|---|---|---|---|
| **Phase 0** | 裸 baseline 量化 | baseline cases JSON + report | 第一优先 |
| **Phase 0.5** | datasheet generator prompt 雏形 | prompt 分支 in `generator.py` | 与 Phase 0 并行 |
| **Phase 1** | 文档结构 digest | `dlpc3436.structure.json` | Phase 0 出报告后 |
| **Phase 2** | 双层索引（block + row） | 双 ChromaDB collection | 依赖 Phase 1 |
| **Phase 3** | 索引 + 查询双向 normalization | normalized_text 字段 | 可并行 Phase 2 |
| **Phase 4** | 轻量 query planner | rule-based query type 分类 | 依赖 Phase 1 |
| **Phase 5** | datasheet generator 结构化引用 | section/table/row 引用模板 | 依赖 Phase 1 + 0.5 |
| **Phase 6** | datasheet 关闭 AUGMENT_QUESTIONS | `is_datasheet=True` 跳过 augmenter | 任意时刻可做 |
| **Phase 7** | 规格书 reading path reconstruction | `reading_closure`：anchor + followed cues + relation + quote/line | 依赖 Phase 1/2/4，替代 TE/footnote 特判 |

---

## 4. Phase 0：裸 baseline（最小执行集）

### 4.1 目标

先知道当前系统到底差在哪，不猜。不写新 Skill / 不改 chunk / 不抽实体 / 不改 retriever，只用现有 hybrid_search + datasheet 域过滤跑评估。

### 4.2 0.1 固定"实际入索引文本版本"（最高优先级）

**问题**：`document_loader.py:236-238` 优先加载 `*_clean.md`。也就是说 baseline / golden evidence 必须基于 `dlpc3436_clean.md`，而不是 raw `dlpc3436.md`。

**doc_cleaner 在 datasheet 上的合规性**：

| 必须保留 | 可以删除 |
|---|---|
| NOTE / `(1)(2)(3)` 脚注 | 页眉页脚 |
| section / table heading | 重复水印（"TI Confidential" 等） |
| table row / symbol / unit | OCR 垃圾 |
| `www.ti.com` 附近的有用上下文 | 明显页码 |

**实现方案**：在 `config.py` 维护 datasheet source 白名单（决策 #1）：

```python
DATASHEET_SOURCES: set[str] = {
    "dlpc3436.pdf",
    # Phase 1 之后追加 dlpc3437.pdf 等
}
```

- `document_loader` 加载时根据白名单为 chunk 打 `is_datasheet=True` 标记（决策 #5）
- `doc_cleaner` 检查 source 是否在白名单，若是则跳过通用清洗，只做轻量 normalization（不做段落合并 / 删行 / 改写）
- 必须保留：NOTE / `(1)(2)(3)` 脚注 / heading / table row / symbol / unit
- 可以删除：页眉页脚 / 重复水印（"TI Confidential"）/ OCR 垃圾 / 明显页码

**严格执行顺序（不能乱）**：

```
1. 改 doc_cleaner（加 datasheet 白名单 / 跳过逻辑）
2. 删掉旧的 dlpc3436_clean.md（如果已生成过）
3. 跑 load_documents() 重新生成 dlpc3436_clean.md
4. 锁定这个 _clean.md 的 git hash
5. 在这个版本上做所有 golden evidence 标注
```

**强约束**：case JSON 里记录 `source_md_sha256`，标注时校验 hash 一致；hash 变了自动 fail，强制 review。否则会反复出现"标注完成 → 改 cleaner → _clean.md 重生成 → 行号错位 → 标注作废"。

### 4.3 0.2 datasheet generator prompt 雏形（前移到 Phase 0.5）

**为什么前移**：成本低、独立收益高，还能避免 baseline 把 generator 错误误判成 retrieval 错误。

**最小规则**：

- 数值、符号、单位逐字保留，不四舍五入
- 不改写 `±` / `%` / `MHz` / `ns` / `kHz` / `V`
- 表格 evidence 尽量还原为 markdown 表格
- 不把 absolute maximum 当 recommended operating condition
- 不把 internal use 改写成用户可用
- 多来源 evidence 分成：主答案 / 补充约束 / 注意事项
- 没 evidence 就明确说"当前检索证据不足"，不要猜

**挂接位置**：`generator.py` 的 `_build_style_instruction()` 或 `_build_domain_instruction()`。

**触发条件**：
- `executed_steps` 中 skill/source 属于 datasheet
- 或 retrieved chunks metadata `is_datasheet=True`
- 或 `query_structure.domain == "datasheet"` / `"hardware"`

> 后续 Phase 5 在此基础上扩展结构化引用格式（section_id / table_id / row_id / line range）。

### 4.4 0.3 Golden evidence 标注流程

**不纯手工**。LLM 辅助 + 人工 review，效率最高。

**两步法工作流**：

```
Step 1: 用现有 retriever.search(query, top_k=30) 跑一遍每个 query
Step 2: 把 top_30 chunks + 期望事实点喂给 LLM
        → LLM 输出"哪些 chunk 是 evidence、对应哪些 fact、line range 范围"
Step 3: 人工 review LLM 输出 → 写入 case JSON
```

**注意**：这意味着 baseline 数据本身受限于"现有 retriever 能找到的范围"。如果某个 fact 现有 retriever top_30 都找不到——这恰好是"重大召回失败"，应该直接进 baseline report 的 critical issues 章节，**不要靠人工补标注掩盖**。

**产物路径**：

```
evaluation/datasheet_baseline_cases.json
```

**Case schema**（强约束：每条 `expected_fact` 必须能映射到至少一条 `golden_evidence`）：

```json
{
  "id": "ds_i2c_001",
  "query": "DLP3436支持的I2C有哪些？",
  "query_type": "enumeration",
  "adversarial": false,
  "source_md_sha256": "<dlpc3436_clean.md 的 sha256>",
  "expected_facts": [
    {
      "fact": "Both I2C interface ports support 100-kHz baud rate",
      "evidence_refs": ["ev_003"],
      "must_have_terms": ["100-kHz", "baud rate"]
    },
    {
      "fact": "IIC0_SCL/IIC0_SDA 是 secondary I2C port 0",
      "evidence_refs": ["ev_001"],
      "must_have_terms": ["IIC0_SCL", "IIC0_SDA"]
    }
  ],
  "golden_evidence": [
    {
      "id": "ev_001",
      "source": "dlpc3436_clean.md",
      "start_line": 296,
      "end_line": 299,
      "required_terms": ["IIC0_SCL", "IIC0_SDA", "IIC1_SCL", "IIC1_SDA"]
    },
    {
      "id": "ev_003",
      "source": "dlpc3436_clean.md",
      "start_line": 925,
      "end_line": 927,
      "required_terms": ["100-kHz baud rate"]
    }
  ]
}
```

**评估口径**（两个独立指标，不重叠）：
- `retrieval recall` = 命中了多少 evidence chunk
- `answer fidelity` = 回答里包含多少 fact 的 must_have_terms

### 4.5 0.4 测试集分布

**总数 15-20 个**。每类 ≥ 3 个。对抗 case ≥ 3-5 个。

**A. 参数型（≥ 3）**
- System Oscillator Timing 要求？
- VCC_INTF 推荐工作电压范围？
- DMD parking timing 是多少？

**B. 枚举型（≥ 3）**
- DLP3436 支持的 I2C 有哪些？
- 支持哪些 DMD/PMIC？
- SPI flash 兼容设备有哪些？

**C. 连接/设计约束型（≥ 3）**
- 外部 oscillator 怎么接？
- IIC0_SDA/SCL 上拉怎么接？
- SPI flash 应该接哪个 chip select？

**D. 兼容/支持型（≥ 3，含对抗）**
- 支持 3.3V SPI flash 吗？
- DLP3436 支持 USB 吗？（adversarial：错误前提）
- 能不能用 variable frequency reference clock？（adversarial：负面）

**E. 流程/状态型（≥ 3）**
- 什么时候可以通过 I2C 发送命令？
- HOST_IRQ 表示什么？
- GPIO_08 上电时有什么要求？

**对抗 case 类型**：
- 模糊问法：`DLP3436 时钟` / `DLP3436 用什么晶振`
- 错误前提：`DLP3436 支持 USB 吗？` / `IIC1 是用户控制端口吗？`
- 中英术语错位：`DLP3436 用什么晶振？` / `PLL_REFCLK 怎么接？`
- 跨表合成：`System Oscillator Timing 要求？` / `I2C 支持情况？`

### 4.6 0.5 评估脚本（双档）

**快速回归**：

```
tests/test_datasheet_retrieval_baseline.py
pytest tests/test_datasheet_retrieval_baseline.py -v
```

特点：
- retrieval-only，不调 generator
- 不调 LLM judge
- 指标：`recall@10` / `recall@20` / `required_terms hit` / `golden line range hit` / `by query_type breakdown`
- 秒级完成，零 LLM 成本，每次代码改动可跑

**完整回归**：

```
tests/test_datasheet_full_baseline.py
pytest tests/test_datasheet_full_baseline.py -v --full
```

特点：
- retrieve + generate 全链路
- 指标：`answer fidelity` / `must_have_terms 字符串命中（hard）` / 抽样 LLM-as-judge 最多 5 个 case
- 每个 Phase 收尾 / merge 前跑

> **CI 集成不在 Phase 0 范围**。第一阶段只做人工 `pytest` 习惯或 pre-push hook，CI 是后期事。

### 4.7 0.6 baseline report

**产物路径**：

```
evaluation/datasheet_baseline_report.md
```

**必须包含**：

- case 总数 / query_type 分布
- `recall@10` / `recall@20`（整体 + 按 query_type）
- `required_terms` hit rate
- 失败归因分布：
  - 哪些 case golden evidence 没召回
  - 哪些 case top20 有但 top6 丢了
  - 哪些 case retrieval OK 但 generator 错
- 对抗 case 表现
- **下一阶段优先级建议**（基于此决定 Phase 1~6 顺序）

---

## 5. Phase 1~6 修正版

### 5.1 Phase 1：structure digest JSON

**产物**：

```
knowledge_base/.structure/dlpc3436.structure.json
```

**包含**：

1. **section_tree**
   ```json
   {
     "section_id": "7.3.4",
     "title": "I 2 C Interface",
     "level": 3,
     "start_line": 925,
     "end_line": 927,
     "parent": "7.3"
   }
   ```

2. **table_catalog**：`table_id` / `section_id` / `table_title` / `start_line` / `end_line` / `columns` / `row_count` / `detected_units` / `detected_symbols` / `row_entities`

3. **row_index**：每个表格行单独记录 `row_id` / `table_id` / `section_id` / `original_text` / `normalized_text` / `entities` / `symbols` / `units` / `source_line`

4. **entity_inventory**：`entity_id` / `canonical_name` / `entity_type` / `aliases` / `mentions` / `source_mappings`
   - 类型：`pin` / `signal` / `interface` / `power_rail` / `timing_symbol` / `electrical_symbol` / `section_concept` / `device_model` / `command/protocol` / `unit/value`

5. **alias_graph**

**实体抽取策略**：
- 规则做粗筛（高召回低精度）：全大写信号名、pin 命名风格、table row 第一列、单位列
- LLM 做精修（高精度）：entity merge / alias inference / type classification
- LLM 调用只在离线 indexing，不进在线 query 主路径

**版本管理**：JSON 入库 commit。提供幂等的 `regen_structure.py` 脚本，文档更新后重新生成 + diff review，类似 schema migration 思路。

### 5.2 Phase 2：双层索引（block + row）

**两个独立 collection，物理分离**：

```
agentic_rag_block   # 块级 chunk：表 / 段落 / 图注
agentic_rag_row     # 行级 chunk：每张表的每一行
```

**为什么必须分离**：
- 防止 BM25 IDF 污染（"MHz" 在 50+ row 里出现，词频权重失真）
- 防止 row 或 block chunk 互相挤占 top_k
- 方便按 query_type 加权合并

**Row-level chunk 格式**（前置上下文，独立召回也不丢语义）：

```
[doc: DLPC3436]
[section: 5.6 Peripheral Interface]
[table: Peripheral Interface]
[row: IIC0_SCL | N10 | I/O | Type 7 | I2C secondary port 0 SCL...]
```

**接口扩展**（`retriever.py`）：

```python
retriever.search_block(q, top_k=5)
retriever.search_row(q, top_k=10)
retriever.search_datasheet(q, query_type=...)
```

**合并策略**：
- row 命中后回溯 parent block / table / section
- block 命中后展开其中高相关 rows
- 按 query_type 加权
- 去重，保留 line/table/row metadata

### 5.3 Phase 3：索引 + 查询双向 normalization

**不是只 query expansion**。索引时同样规整，BM25 才能精确命中。

Chunk metadata 三个文本字段：

| 字段 | 用途 |
|---|---|
| `original_text` | 给 generator 引用，避免改写错数字 |
| `normalized_text` | 给 BM25 / sparse retrieval 用 |
| `entity_tokens` | 给 exact match / rerank 用 |

**典型 normalization 映射**：

```
I 2 C / I²C / IIC                  → I2C
f clk / fclk / f_clk               → f_clk
t w(H) / tw(H) / t_w_H             → t_w_H
V IH / VIH / V_IH                  → V_IH
GPIO08 / GPIO_08                   → GPIO_08
PLL REFCLK I / PLL_REFCLK_I        → PLL_REFCLK_I
±200 PPM / +/-200 ppm              → ±200 ppm
```

### 5.4 Phase 4：轻量 query planner

**query_type 分类用规则，不上 LLM**：

```
参数型：     要求 / 规格 / timing / requirements / characteristics / parameter / max/min/typ
枚举型：     有哪些 / 支持哪些 / list / options / compatible devices
连接/设计型：怎么接 / 如何连接 / connection / layout / external oscillator / pullup
兼容/支持型：支持吗 / compatible / support / can use
流程/状态型：什么时候 / ready / startup / initialization / HOST_IRQ / reset / power up
```

**按问题类型做 staged retrieval**：

| query_type | retrieval plan |
|---|---|
| 参数型 | exact section title search → table search → notes search → related pin/clock layout |
| 枚举型 | entity search → pin table rows → feature description → electrical/voltage rows → startup constraints |
| 连接型 | pin rows → clock and PLL section → layout recommendations → notes/warnings |
| 兼容型 | compatible device table → flash requirement table → timing table → constraint notes |

LLM 不做 query 分类。LLM 可能用于：离线实体精修 / 少量 evidence selection 实验。

### 5.5 Phase 5：datasheet generator 结构化引用

**Phase 0.5 prompt 雏形之上扩展**：

- 引用格式：`[Section 6.10 / Table System Oscillator Timing Requirements / Row f_clk / line 694]`
- 多 evidence 合成模板：主答案 → 补充约束 → 注意事项 → 引用清单
- negative evidence 处理模板：明确说"文档未提及" / "需要进一步查证 datasheet 第 X 章"

### 5.6 Phase 6：datasheet 关闭 AUGMENT_QUESTIONS

**修改 `index_augmenter.py`**：

- `is_datasheet=True` 的 chunk 不进 augmenter
- 或者 datasheet 只生成结构化 entity/query，不生成自然语言增强问题

datasheet 召回靠：
- `normalized_text`
- row index / block index
- entity inventory
- structure metadata
- alias graph

不是靠"LLM 想象这个 chunk 可能回答什么问题"。

---

## 6. 关键约束（写入设计文档和代码注释）

### 6.1 alias 和 related_entities 严格分离

**严格分工**：

| 字段 | 用途 | 进入查询扩展？ |
|---|---|---|
| `aliases` | 同一概念的不同写法（I2C / I 2 C / IIC） | ✅ 用于 normalization 和 query expansion |
| `related_entities` | 实体族的相关项（I2C → IIC0_SCL/SDA 等 pin） | ❌ 只用于 generator 答案组织和上下文扩展 |

**反例**：把 `related_entities` 用于查询扩展 → 问 "I2C timing" 会被 4 个 IIC pin row 淹没，真正的 timing section 反而丢掉。

**代码层强约束**（不靠注释提醒）：

```python
@dataclass
class EntityNode:
    aliases: list[str]          # 只能进 query expansion
    related_entities: list[str] # 只能进 generator context

def expand_query(node: EntityNode) -> list[str]:
    return [node.canonical] + node.aliases  # 函数签名禁止 related

def build_generator_context(node: EntityNode) -> dict:
    return {"related": node.related_entities, ...}
```

**回归测试 case**：query=`I2C timing requirements`，断言 top_5 里**不出现** pin row chunks。

### 6.2 双层索引必须物理分离

不可混入同一 ChromaDB collection。理由见 Phase 2。

### 6.3 LLM 不进在线 query 主路径

- 离线 indexing：LLM 用于实体精修、alias 推断、entity type 分类
- 在线 retrieval：规则 + 索引结构
- 例外：在线 evidence selection 的最后一步可考虑 LLM，需实验验证

### 6.4 每层架构必须可量化收益

每加一层架构必须能回答：
> "它让哪类 datasheet query 的 recall / precision / answer fidelity 提升了多少？"

回答不了就不进主线。

---

## 7. 评估指标定义

### 7.1 Retrieval 层（快速回归）

| 指标 | 定义 |
|---|---|
| `recall@10` | top_10 检索结果中，命中的 golden_evidence chunk 数 / 总 evidence 数 |
| `recall@20` | 同上，top_20 |
| `required_terms hit` | golden_evidence 中 `required_terms` 在召回 chunk 文本里的命中率 |
| `golden line range hit` | 召回 chunk 的 line range 与 evidence line range 重叠率 |
| `by query_type breakdown` | 上述指标按 5 类 query_type 分组 |

### 7.2 Answer 层（完整回归）

| 指标 | 定义 |
|---|---|
| `answer fidelity` | 回答里包含的 `expected_facts.must_have_terms` 命中率（hard 字符串匹配） |
| `LLM-as-judge 抽样` | 最多 5 个 case，用另一个 LLM 对照 fact 列表打分（0/1） |
| `数值改写检查` | 抽样回答的关键数值（含小数点 / 单位 / `±` / `%`），与 evidence 逐字对照 |

### 7.3 失败归因维度

| 失败模式 | 检测方法 | 修复方向 |
|---|---|---|
| retrieval 根本找不到 | top_30 都没有 evidence chunk | Phase 1 / Phase 3（结构 + normalization） |
| top_20 有但 top_6 丢 | 重排问题 | Phase 2 / Phase 4（双层索引 + staged retrieval） |
| evidence 有但 generator 错 | 召回 OK，回答里 fact 缺失或被改写 | Phase 0.5 / Phase 5（generator prompt） |
| 单类型 query 特别差 | by query_type breakdown 异常 | Phase 4 staged retrieval 针对该类型设计 |
| 跨表/跨章节合成失败 | 多 evidence case 命中数 < 总 evidence 数的 50% | Phase 4 multi-hop / Phase 1 alias graph |

### 7.4 Phase 7：规格书 Reading Path Reconstruction 指标

Phase 7 不是继续扩 TE53 特判，也不是 table footnote 规则库；它度量 RAG 是否能重建规格书阅读路径。

| 指标 | 定义 |
|---|---|
| `reading_closure.anchor_hit` | 是否找到 subject 主证据，例如参数行/段落/图/引脚定义 |
| `reading_closure.followed_cue_hit` | 是否沿注解、小字、NOTE/WARNING、caption/callout、括注、see also、cross-reference 找到补充证据 |
| `reading_closure.relation_hit` | followed cue 是否被分类为 definition/value/condition/constraint/exception/dependency 等关系 |
| `reading_closure.quote_line_hit` | closure 中每条 evidence 是否保留原文 quote + line/source |
| `reading_closure.answer_coverage` | generator 最终回答是否覆盖 closure 中的 value/condition/constraint/dependency 等必需 evidence category |

TE53 只作为 Phase 7 的一个验证样例：`System Oscillator Timing` 表格行 → `(1)` 小字约束 → `(2)` external oscillator 条件 → `5.8 Clock and PLL Support` 中 `PLL_REFCLK_I/O` pin 定义。该路径必须由通用 reading closure 机制产生，不能写 TE53 专用补漏。

---

## 8. 第一天执行清单（Phase 0 + Phase 0.5）

### 8.1 前置环境

复用项目内已有的 demo venv（无需新建）：

```bash
source ../demo/.venv/bin/activate
```

已确认包含的依赖（与本计划相关的部分）：

| 依赖 | 版本 | 用途 |
|---|---|---|
| `chromadb` | 1.5.8 | 向量索引（block / row 双 collection） |
| `sentence_transformers` | 5.4.1 | embedding（中英混合 query） |
| `pytest` | 9.0.3 | baseline 评估脚本运行 |
| `BAAI/bge-m3` | 本地 cache 已存在，单独加载验证通过 | 默认 embedding 模型 |

如后续 Phase 引入新依赖（如 LLM SDK），按 `requirements.txt` 增量补装，不另建 venv。

### 8.2 执行步骤

按顺序执行：

1. **改 `doc_cleaner.py`**：加 datasheet 白名单 / 跳过逻辑
2. **重新生成 `dlpc3436_clean.md`**：删旧 → 跑 `load_documents()` → 锁定 git hash
3. **写 datasheet generator prompt 雏形**：约 30 行，挂在 `generator.py:_build_style_instruction()`，触发条件 `is_datasheet=True`
4. **标注 15-20 个 baseline case**：LLM 抽候选 → 人工 review → 写入 `evaluation/datasheet_baseline_cases.json`
5. **写 retrieval-only baseline 脚本**：`tests/test_datasheet_retrieval_baseline.py`
6. **写 full baseline 脚本骨架**：`tests/test_datasheet_full_baseline.py`
7. **跑出 `evaluation/datasheet_baseline_report.md`**

完成后基于报告决定 Phase 1~6 的优先级：
- 先做 normalization？
- 先做 row-level index？
- 先做 section/table catalog？
- 还是先改 rerank/top_k？

---

## 9. 设计决策

> 已于 2026-05-07 确认。

| # | 决策点 | 结论 | 理由 |
|---|---|---|---|
| 1 | doc_cleaner datasheet 判定方式 | **手工配置 source 白名单**（在 `config.py` 维护 `DATASHEET_SOURCES` set） | 当前 datasheet 数量少，自动判定易误伤；后续规模化再升级为 heading 匹配 |
| 2 | baseline case LLM 抽候选 | **Claude（Sonnet/Opus）** | 标注质量是 baseline 数据地基；一次性离线使用，成本 < $5 |
| 3 | dlpc3437 是否同步纳入 | **Phase 0 只做 dlpc3436，Phase 1 之后再扩 dlpc3437** | 同系列（DLPC343x）结构高度相似，3436 跑通的方案大概率直接适用 |
| 4 | structure JSON schema 版本号 | **加顶层 `schema_version: "0.1"` 字段**，但不做迁移机制 | 零成本买未来；真正不兼容时再写迁移脚本 |
| 5 | `is_datasheet` 字段挂在哪一层 | **chunk 级 metadata** | 与现有 `is_table` / `is_augmented` 一致；判定来源在 source 级（loader 根据决策 #1 白名单打标），存储在 chunk 级；retriever 可直接用 `where={"is_datasheet": True}` 过滤 |

---

## 10. 一句话总结

> 不要模仿 NotebookLM 的"回答风格"，要模仿它的"文档理解路径"。
>
> 不要靠 `_CONCEPT_MAP` 补丁，也不要一口气上知识图谱。
>
> 路径：**baseline 量化 → 文档结构 digest → 行级 + 块级双索引 → 索引/查询双向 normalization → 类型驱动 staged retrieval → datasheet-safe generator**。
>
> 每一层都必须能回答："它让哪类 query 的 recall / precision / fidelity 提升了多少？" 否则不进主线。
