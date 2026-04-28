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
LLM_BACKEND = "ollama"   # "ollama" | "none"
OLLAMA_MODEL =  "qwen3.6:35b-a3b-q4_K_M" #"gemma4"  #
OLLAMA_OPTIONS = {"num_ctx": 4096, "temperature": 0}

# 文档增强索引：为每个 chunk 生成多角度问题，显著提升同义词/近义词召回
# True  → 首次启动时调用 LLM 生成，结果缓存到 knowledge_base/.question_cache.json
# False → 跳过增强，适合快速调试
AUGMENT_QUESTIONS = True
