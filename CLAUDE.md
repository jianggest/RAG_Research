# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

RAG（Retrieval-Augmented Generation）学习与实践项目，包含：
- **demo/**：可本地运行的 RAG 原理演示程序
- **RAG学习路线.md**：持续更新的结构化学习笔记
- **RAG_需求收集表.md**：RAG 项目需求调研表单（v1.1，含 15 个章节）

## 运行 Demo

```bash
cd demo
pip install chromadb                  # 轻量模式（推荐先用）
python rag_demo.py
```

如需更好的中文 Embedding 效果：
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers
# 然后修改 rag_demo.py：EMBEDDING_BACKEND = "sentence"
```

如需下载模型加速（HuggingFace 镜像）：
```bash
set HF_ENDPOINT=https://hf-mirror.com
```

## Demo 架构（demo/rag_demo.py）

程序顶部的配置区控制所有行为，修改这里即可切换模式，无需改代码逻辑：

| 配置项 | 可选值 | 说明 |
|--------|--------|------|
| `EMBEDDING_BACKEND` | `"chroma"` / `"sentence"` | `chroma` 无需 PyTorch，`sentence` 中文效果更好 |
| `LLM_BACKEND` | `"none"` / `"ollama"` / `"openai"` | `none` 只展示检索结果，适合初学 |
| `OLLAMA_MODEL` | 模型名如 `"qwen2:7b"` | Ollama 使用的模型，gemma4 需加 `think=False` |
| `CHUNK_SIZE` | 默认 300 | 每个文本块的最大字符数 |
| `CHUNK_OVERLAP` | 默认 50 | 相邻 chunk 的重叠字符数 |
| `TOP_K` | 默认 3 | 检索返回的最相似片段数 |

**核心流程（4步）：**
1. `load_documents()` — 从 `knowledge_base/*.txt` 读取文档
2. `chunk_documents()` — 滑动窗口切块
3. `build_index()` — 向量化并存入 ChromaDB（`chroma_db/` 目录持久化）
4. 交互式问答：`retrieve()` → `build_rag_prompt()` → `call_llm()`

**注意**：当前每次启动都会删除并重建索引（`delete_collection`），向量库虽然持久化到磁盘，但未实现"跳过已有索引"的优化。

## Ollama 集成注意事项

- Ollama **客户端程序**需单独安装（任务栏驻留），`ollama` Python 库是调用接口
- 对于 gemma4 等支持 Thinking 模式的模型，务必设置 `think=False` + `options={"num_ctx": 4096}` 否则响应极慢
- 调用失败时检查：Ollama 是否已启动、模型是否已 `ollama pull`

## 知识库文档

`demo/knowledge_base/` 下的三份虚构文档用于演示：
- `01_产品手册.txt` — 智云助手 Pro 定价（专业版 2999元/年）、技术规格
- `02_员工手册.txt` — HR 政策（生日假 1天+500元购物卡、年假、绩效等级）
- `03_系统架构说明.txt` — 技术架构（Milvus/ChromaDB、bge-m3、GPTCache）

这些文档不在任何 LLM 训练集中，用于验证"有 RAG vs 无 RAG"的差异。
