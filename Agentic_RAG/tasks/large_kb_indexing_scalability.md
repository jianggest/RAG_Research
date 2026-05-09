# Large KB Indexing Scalability 处理记录

## 背景

新增多个大文档后，Streamlit 页面长时间停留在“加载知识库/建立索引”，`demo.log` 长时间没有继续推进。

已确认小文件正常，因此问题不是基础加载链路失效，而是知识库规模变大后触发的索引构建/增强生成瓶颈。

## 根因分析

1. `Retriever.build_index()` 原实现一次性将全部 chunk 写入 Chroma：
   - 大文档场景下约数千 chunk。
   - 一次性 embedding + Chroma add 会导致长时间无日志、内存峰值高、页面看起来卡死。

2. 仅改分批仍不足以解决“后续文件更多”：
   - 实测 `INDEX_BATCH_SIZE=16` 约 18 分钟只到 `977-992/6270`，RSS 到约 `15.4GB`。
   - 说明瓶颈是每次启动都重新 embedding 全量文档，而不是单纯缺少日志。

3. `index_augmenter.generate_augmented_entries()` 可能对大量 chunk 串行调用 LLM 生成增强问题：
   - 文件更多时，首次启动会出现大量 LLM 调用。
   - 当前首要目标是让页面能稳定完成原始索引，因此已临时关闭增强。

4. 长期方向必须是：
   - Chroma 持久化
   - chunk hash 稳定 ID
   - 已索引 chunk 跳过
   - 新增/修改文件才增量 embedding

## 已完成改动

### 1. 分批索引配置

文件：`config.py`

当前：

```python
AUGMENT_QUESTIONS = False
INDEX_BATCH_SIZE = 16
PERSIST_CHROMA_INDEX = True
CHROMA_PERSIST_DIR = Path(__file__).parent / ".chroma_index"
AUGMENT_MAX_CHUNKS: int | None = None
```

用途：
- `INDEX_BATCH_SIZE` 控制 Chroma add 批大小。
- 起初尝试 `64`，实测本地 CPU embedding 下仍出现单批耗时/内存峰值偏高，已降为 `16`。
- `AUGMENT_QUESTIONS` 已临时关闭，避免增强问题生成阻塞启动。
- `PERSIST_CHROMA_INDEX` 启用 Chroma 持久化，避免后续每次启动全量重建。

### 2. Retriever 分批 add + flush 进度日志

文件：`retriever.py`

新增/调整：
- `_add_chunks_in_batches(...)` 分批写入。
- 每批 `print(..., flush=True)`。
- 日志改为范围式进度。

日志形态：

```text
[Retriever] 原始索引进度：1-16/6270（总 6270）
```

### 3. Chroma 持久化 + 增量索引

文件：`retriever.py`

新增：
- `chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))`
- `client.get_or_create_collection(...)`
- `_chunk_content_id(prefix, chunk)` 基于 source + chunk_index + text/normalized_text 生成稳定 hash ID。
- `_existing_ids(collection, ids)` 查询已存在 ID。
- `_add_chunks_in_batches()` 跳过已存在 ID，只 add 新 chunk。

增量日志：

```text
[Retriever] 原始跳过已存在索引：N/TOTAL
[Retriever] 原始新增索引建立完成，共 N 条；总 chunks TOTAL 条
```

### 4. 增强生成上限入口

文件：`index_augmenter.py`

新增读取：

```python
from config import AUGMENT_MAX_CHUNKS
```

并在生成问题循环中加入上限判断，避免未来大 KB 首次启动无限串行生成。

### 5. 离线索引脚本

文件：`tasks/run_persistent_index.py`

用途：先在 Streamlit 外完成持久化索引构建，避免页面进程热重载/事件循环干扰。

命令：

```bash
.venv/bin/python tasks/run_persistent_index.py >> demo.log 2>&1
```

## 已执行验证

### 单测：增量跳过已存在 chunk

```bash
.venv/bin/python -m pytest tests/test_retriever.py::test_build_index_skips_already_indexed_chunk_hashes -q
```

结果：

```text
1 passed in 0.02s
```

### Retriever 测试回归

```bash
.venv/bin/python -m pytest tests/test_retriever.py -q
```

结果：

```text
24 passed in 0.05s
```

## 真实运行记录

### 分批但未持久化阶段

后台 session：

```text
proc_e0cb1fafe404
PID 1142155 shell
PID 1142168 streamlit
```

观察：

```text
last 977-992/6270 pct 15.82
ELAPSED 17:56
RSS 15419404 KB
```

结论：分批可观察，但全量重建仍不可接受，停止该进程，进入持久化/增量改造。

### 持久化索引离线构建阶段

第一次脚本尝试因 `tasks/` 路径下导入不到 `config` 失败，已修复 `sys.path`。

当前后台 session：

```text
proc_57d4c29cc72e
PID 1155582 shell
PID 1155595 python tasks/run_persistent_index.py
```

当前进度：

```text
[Retriever] 原始索引进度：1729-1744/6270（总 6270）
```

进程状态样例：

```text
PID 1155595
ELAPSED 00:50
CPU 905%
RSS 210016 KB
```

说明：当前在离线构建持久化索引。首次仍需 embedding 全量新增 chunk；完成后后续启动应跳过已存在 chunk。

## 未完成/下一步

1. 等待 `proc_57d4c29cc72e` 完成首次持久化索引。
2. 完成后再启动 Streamlit，验证是否快速出现：

```text
[Retriever] 原始跳过已存在索引：6270/6270
[Retriever] 原始新增索引建立完成，共 0 条；总 chunks 6270 条
```

3. 页面验证：确认 `8501` 打开且不再长时间卡“加载知识库”。
4. 后续再考虑增强问题生成的离线/增量化恢复。

## 当前风险

- 首次持久化构建仍需要时间，但只应发生一次。
- `AUGMENT_QUESTIONS = False` 会牺牲部分同义问法召回；当前是为了先保证大 KB 页面可启动。
- chunk hash 目前包含 `source + chunk_index + text`；如果 loader chunk 切分规则变化，会触发重新索引，这是合理行为。


## 2026-05-08 验证更新

### 首次持久化离线索引完成

后台 session：

```text
proc_57d4c29cc72e
```

结果：

```text
exit_code: 0
[IndexRunner] loaded chunks=6270
[Retriever] 原始新增索引建立完成，共 6270 条；总 chunks 6270 条
[IndexRunner] done large KB persistent indexing
```

持久化目录：

```text
.chroma_index = 56M
```

### Streamlit 重启验证

后台 session：

```text
proc_ea1159857f39
shell PID 1189756
streamlit PID 1189769
```

端口与 HTTP 验证：

```text
8501 open
GET http://127.0.0.1:8501 -> HTTP 200
```

说明：Streamlit 服务已启动，页面可访问。当前仅做 HTTP 可达验证；本机 browser 工具缺 Chrome，无法直接做 Playwright/浏览器交互验证。


## 2026-05-08 curl 报错检查与修复

### curl 初查

命令：

```bash
curl -sS -D /tmp/agentic_rag_8501.headers -o /tmp/agentic_rag_8501.html http://127.0.0.1:8501/
grep -Ei 'traceback|exception|error|failed|runtimeerror|module' demo.log
```

HTTP 返回：

```text
HTTP/1.1 200 OK
Content-Length: 4876
```

但日志发现页面实际初始化报错：

```text
ValueError: An embedding function already exists in the collection configuration, and a new one is provided.
Embedding function conflict: new: sentence_transformer vs persisted: default
```

### 根因

首次持久化索引创建 collection 后，Chroma 记录了 persisted embedding function 配置；Streamlit 重新 `get_or_create_collection(..., embedding_function=SentenceTransformerEmbeddingFunction(...))` 时触发 Chroma 的 embedding function conflict 校验。

### 修复

文件：`retriever.py`

在 `PERSIST_CHROMA_INDEX=True` 时，`get_or_create_collection()` 不再传入 `embedding_function`，避免与已持久化 collection 配置冲突；非持久化模式仍保留原行为。

### 验证

测试：

```text
24 passed in 0.05s
```

重启 Streamlit：

```text
proc_cb8a4f94e00a
shell PID 1193324
streamlit PID 1193337
```

curl：

```text
HTTP/1.1 200 OK
Content-Length: 4876
```

日志无 traceback/error，并确认增量跳过生效：

```text
[Retriever] 原始跳过已存在索引：6270/6270
[Retriever] 原始索引无新增，共 6270 条
[Retriever] 原始新增索引建立完成，共 0 条；总 chunks 6270 条
```
