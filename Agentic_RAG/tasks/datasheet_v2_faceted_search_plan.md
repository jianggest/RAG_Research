# Datasheet 检索 V2 — 任务记录

记录日期: 2026-05-15
状态: 设计阶段, 尚未编码

## 背景

V1 (`skills/search_datasheet.py`) 用硬编码 if/elif (staged rules + concept_map) 锚定特定问题(oscillator timing / spi flash / i2c ports / parking)。这种方式:
- 加一个新接口/新主题就要写一组规则
- 对未覆盖问题退化为普通 hybrid 检索
- 维护成本高、可扩展性差

要做一个 V2, 用"工程视角通用切面" + "文档结构感知"两条路, 长期替代 V1。

## 触发问题示例

- "DLPC3436 的 I2C 接口或 I2C 信号有哪些"
- "DLPC3436 系统 Oscillator Timing 要求"
- "DLPC3436 的 ESD 设计要求是什么"(未来扩展)

## 设计决策(已确认)

### 1. 检索切面用"工程视角"通用模板, 不绑定接口

6 个切面:

| key | 中文名 | 用途 |
|---|---|---|
| physical_scope | 物理形态/范围 | pin/ball/signal/instance |
| functional_role | 功能定位 | master/slave/control/data/protection |
| parameters_and_ratings | 参数与等级 | voltage/current/HBM/CDM/temperature |
| performance_timing | 性能与时序 | rate/frequency/setup/hold |
| system_conditions | 系统级条件 | reset/init/sequence/layout |
| configuration_control | 配置与控制 | register/command/firmware |

每个切面 keywords 用 `{topic}` 占位, 运行时替换。

### 2. 不做主题专属 overlay

明确拒绝 `_TOPIC_OVERLAYS = {"I2C": {...}, "ESD": {...}}` 这种结构。补强能力靠通用机制, 不靠为每个主题手工写关键词。

### 3. 通用补强方向: 文档结构感知, 不用语言学正则

- 拒绝方案: 关键词正则匹配("must"/"shall"/"±"/"not supported"/"tolerance" 等)
- 采用方案: 利用文档自身已有的结构锚(脚注 `(1)(2)` / `See Figure X` / `Refer to Section Y`)

### 4. V1 与 V2 关系

V2 上线并验证 oscillator timing / i2c 等回归用例后, V1 整体退役删除。
不留长期共存, 不做按主题路由分工。

### 5. Top-K 总额 20, 切面权重初版全 1

后续根据实际召回结果再调权。

### 6. 默认串行执行 + 打印每切面耗时

```
[search_datasheet_v2] facet=parameters_and_ratings q=... hits=N took=Mms
```

跑几个真实问题后再决定要不要上并行。

## 实施任务列表

### Task 1: 改 chunker, 让表格和它的脚注绑成一个 chunk

文件: `document_loader.py`

当前 bug:
- `_extract_blocks` 在第 88-95 行, 遇到非 `|` 开头的行就结束表格块
- 表格后面的 `(1) The frequency accuracy for MOSC is ±200 PPM...` 被切成独立 chunk
- 这是 oscillator 问题召回不到限制条件的根因

改造点:
- 在 `_extract_blocks` 里加"表格脚注吸附"规则
- 表格结束后, 如果下一行匹配以下任一模式, 仍归入表格 chunk:
  - `^\(\d+\)\s+` → `(1) ...`
  - `^\[\d+\]\s+` → `[1] ...`
  - `^Note\s+\d+[:.]?\s+` → `Note 1: ...`
  - `^\*\s+` 或 `^†\s+` → 星号/匕首脚注
  - `^\[\^\d+\]:\s+` → Markdown footnote 语法
- 终止条件: 空行后接非锚定行 / 任何 markdown 标题 / 下一个表格开始

### Task 2: chunk metadata 加结构锚字段

文件: `document_loader.py` 的 `_build_chunk`

新增字段:
- `anchors_used`: 该 chunk 文本里出现的脚注引用, 如 `["(1)", "(2)"]`
- `anchors_defined`: 该 chunk 内定义的脚注, 如 `["(1)", "(2)"]`
- `refs_outbound`: 跨章节引用, 如 `["Figure 6-5", "Section 7.5"]`

提取规则:
- `anchors_used`: 扫描单元格内 `\(\d+\)` / `<sup>(\d+)</sup>` / `\[\d+\]`
- `anchors_defined`: 行首匹配 `^\(\d+\)\s` 等
- `refs_outbound`: `(?:See|Refer to)\s+(Figure|Table|Section|Chapter)\s+([\d.\-]+)`

### Task 3: 重建索引

Task 1+2 改完后必须 rebuild, 因为现有 ChromaDB 里的 chunk 是旧切法。

### Task 4: 加单元测试验证脚注吸附

文件: `tests/test_chunking.py` 加用例

输入: 模拟 DLPC3436 第 6.10 节(System Oscillator Timing Requirements 表 + (1)(2) 脚注)
断言:
- 表格和两条脚注在同一个 chunk
- 该 chunk 的 `anchors_defined` 含 `"(1)"` 和 `"(2)"`
- 该 chunk 文本同时包含 `"23.998"` 和 `"±200 PPM"`

### Task 5: 写 search_datasheet_v2.py

文件: `skills/search_datasheet_v2.py` (新建)

骨架:
- `SKILL_META` 描述: 多切面检索, 面向枚举/总览/设计要求型问题
- `_FACETS`: 6 个切面定义(intent + keywords_template, 不含主题专属内容)
- `_detect_topic(query)`: 抽取主题词(接口名/ESD/Power/Clock 等), 抽不出返回 None
- `_run_faceted_retrieval`: 对每个切面跑一次 hybrid 检索, 打日志记录耗时
- `_facet_round_robin_topk`: 按切面轮询合并到 top-20, 保证每切面至少 2~3 条

不写主题特例。不写关键词正则。不写 staged rules。

### Task 6 (可选): cross-reference 跟随

文件: `retriever.py` 加 `_follow_cross_refs(top_k_results)`

机制:
- 对 top-K 中每个 chunk, 读 `refs_outbound`
- 用 source + ref 反查同文档的其他 chunk(查 metadata, 不是字面文本)
- 命中的 chunk 以 0.7× 分数加入候选, facet 标 `cross_ref_followed`
- 最多跟随 5 个跨引用

先观察 Task 1+2 后召回是否够好, 如果脚注绑定已经解决 90% 问题就不做这个。

### Task 7: 注册 V2 + 改 Planner 路由

- `skills/__init__.py`: 注册 search_datasheet_v2
- `planner.py` 规则 9: 改成路由到 V2, V1 暂时保留做兜底

### Task 8: 回归测试

- 跑现有 `tests/test_dlpc_*` 全套用例, V2 召回不能差于 V1
- 重点验证两个问题:
  - "DLPC3436 系统 Oscillator Timing 要求" → 必须召回 ±200 ppm 注释和"不支持展频"
  - "DLPC3436 的 I2C 接口或 I2C 信号有哪些" → 必须召回 IIC0_SCL/SDA 和 100-kHz baud rate
- 通过后删除 V1 (`skills/search_datasheet.py` + 注册条目)

## 已经否决的方案(避免回退)

| 方案 | 否决原因 |
|---|---|
| 改 Generator prompt | 用户验证过, 现有 prompt 没问题, 问题在召回不全 |
| Planner 拆 6 个 step | LLM 输出不稳定, 6× 调用慢 |
| V2 加 `_TOPIC_OVERLAYS["I2C/ESD/..."]` | 本质还是硬编码主题知识, 跟 V1 同样的病 |
| 关键词正则补强(must/shall/±/tolerance/不支持) | 拟合数据, 跨语种要分别维护, 误召率高 |
| 数值锚二跳(numeric anchor expansion) | 复杂, 与结构锚方案功能重叠, 结构锚更优雅 |
| V1/V2 长期共存按问题类型路由 | 维护两套, 无法收敛 |

## 待确认问题

1. Task 6 (cross-ref following) 要不要做? 默认先不做, 等 Task 1+2 上线后看效果。
2. Task 7 里 Planner 路由阶段是否真的需要保留 V1 兜底? 还是 V2 跑通就直接删?

## 实施顺序

Task 1 → Task 2 → Task 4 (测试) → Task 3 (重建索引) → Task 5 → Task 7 → Task 8 → (可选 Task 6)
