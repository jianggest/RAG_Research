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

# LLM
LLM_BACKEND = "ollama"   # "ollama" | "none"
OLLAMA_MODEL =  "qwen3.6:35b-a3b-q4_K_M" #"gemma4"  #
OLLAMA_OPTIONS = {"num_ctx": 4096}
