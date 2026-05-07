"""
全局配置项，所有模块从此处读取，修改行为只需改这里。
"""
from pathlib import Path

# 目录
KNOWLEDGE_BASE_DIR = Path(__file__).parent / "knowledge_base"

# 分块
CHUNK_SIZE = 600

# 检索
TOP_K = 5

# Embedding 模型（供 Retriever 使用）
# "default" → ChromaDB 内置 all-MiniLM-L6-v2（无需额外安装）
# "BAAI/bge-m3" → 多语言模型，中文效果显著更好（需 pip install sentence-transformers）
EMBEDDING_MODEL = "BAAI/bge-m3"

# LLM
# 默认 AI 模型后端：决定 call_llm() 走哪条分支
LLM_BACKEND = "openai"   # "ollama" | "openai" | "none"

# Ollama 配置
OLLAMA_MODEL =  "qwen3.6:35b-a3b-q4_K_M" #"gemma4"  #
OLLAMA_OPTIONS = {"num_ctx": 4096, "temperature": 0}

# OpenAI（兼容 OpenAI 协议的网关）配置
OPENAI_BASE_URL = "https://aicode.wewell.net/v1"
OPENAI_API_KEY = "sk-5c8387ac5581157a0d07cc997bb5e83c9d7e489cd78509e1c8cc8571462941f7"
OPENAI_MODEL = "gpt-5.4"
OPENAI_OPTIONS = {"temperature": 0}

# 文档增强索引：为每个 chunk 生成多角度问题，显著提升同义词/近义词召回
# True  → 首次启动时调用 LLM 生成，结果缓存到 knowledge_base/.question_cache.json
# False → 跳过增强，适合快速调试
AUGMENT_QUESTIONS = True
