# RAG 原理演示 Demo

通过一个"企业内部知识库问答"场景，直观理解 RAG 的工作原理。

## 目录结构

```
demo/
├── rag_demo.py          # 主程序（含详细注释）
├── requirements.txt     # 依赖列表
├── knowledge_base/      # 模拟的企业内部文档（LLM 不知道的私有数据）
│   ├── 01_产品手册.txt
│   ├── 02_员工手册.txt
│   └── 03_系统架构说明.txt
└── chroma_db/           # 运行后自动生成，向量库的持久化文件
```

## 快速开始

### 第一步：安装依赖

```bash
cd demo
pip install -r requirements.txt
```

> 首次运行会自动下载 Embedding 模型（约 400MB），需要网络连接。

### 第二步：运行 Demo

```bash
python rag_demo.py
```

### 第三步：试试这些问题

这些问题的答案**不在任何 LLM 的训练数据中**，但 RAG 能从知识库里找到：

| 问题 | 答案藏在哪份文档 |
|------|-----------------|
| 智云助手Pro的年费是多少？ | 01_产品手册.txt |
| 员工生日当天有什么福利？ | 02_员工手册.txt |
| 系统用的是什么向量数据库？ | 03_系统架构说明.txt |
| 试用期薪资是正式薪资的多少？ | 02_员工手册.txt |
| 文档解析支持哪些 OCR 工具？ | 03_系统架构说明.txt |

---

## 开启 LLM 生成（可选）

默认模式只展示检索结果，不调用 LLM。如果想看完整的"检索 + 生成"效果：

### 方式一：Ollama（本地，免费，推荐）

```bash
# 1. 安装 Ollama（从官网下载安装包）
# 2. 拉取中文模型（约 4.7GB）
ollama pull qwen2:7b

# 3. 安装 Python 库
pip install ollama

# 4. 修改 rag_demo.py 顶部配置
LLM_BACKEND = "ollama"
```

### 方式二：OpenAI API

```bash
# 1. 安装库
pip install openai

# 2. 设置 API Key（Windows）
set OPENAI_API_KEY=sk-...

# 3. 修改 rag_demo.py 顶部配置
LLM_BACKEND = "openai"
```

---

## 理解运行过程

程序运行时会经历 3 个阶段，对应 RAG 的核心流程：

```
步骤 1：加载文档
  knowledge_base/*.txt → 读取文本内容

步骤 2：文本切块（Chunking）
  长文档 → 切成 300 字的小块，相邻块重叠 50 字

步骤 3：向量化 + 建立索引
  每个小块 → Embedding 模型 → 向量 → ChromaDB

问答阶段（交互式）：
  用户问题 → 向量化 → 相似度搜索 → Top-3 片段
           → 拼入 Prompt → LLM 生成答案（如已配置）
```

---

## 常见问题

**Q：下载模型太慢怎么办？**
可以设置 HuggingFace 镜像：
```bash
set HF_ENDPOINT=https://hf-mirror.com
```

**Q：提示 `No module named 'chromadb'`？**
```bash
pip install chromadb sentence-transformers
```

**Q：向量库数据在哪里？**
在 `demo/chroma_db/` 目录，重新索引时会自动覆盖。
