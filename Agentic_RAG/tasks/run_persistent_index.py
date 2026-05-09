import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import KNOWLEDGE_BASE_DIR
from document_loader import load_documents
from retriever import Retriever

print('[IndexRunner] start large KB persistent indexing', flush=True)
chunks = load_documents(KNOWLEDGE_BASE_DIR)
print(f'[IndexRunner] loaded chunks={len(chunks)}', flush=True)
retriever = Retriever(chunks)
retriever.build_index()
print('[IndexRunner] done large KB persistent indexing', flush=True)
