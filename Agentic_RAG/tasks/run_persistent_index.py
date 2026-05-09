import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import get_knowledge_base_dir, get_rag_profile
from document_loader import load_documents
from retriever import Retriever

kb_dir = get_knowledge_base_dir()
print(f'[IndexRunner] start large KB persistent indexing profile={get_rag_profile()} kb={kb_dir}', flush=True)
chunks = load_documents(kb_dir)
print(f'[IndexRunner] loaded chunks={len(chunks)}', flush=True)
retriever = Retriever(chunks)
retriever.build_index()
print('[IndexRunner] done large KB persistent indexing', flush=True)
