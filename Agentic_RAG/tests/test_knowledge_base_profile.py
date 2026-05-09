"""
Knowledge-base profile isolation tests.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import get_knowledge_base_dir, get_chroma_collection_names, get_chroma_persist_dir
from document_loader import load_documents
from retriever import Retriever
from index_augmenter import get_question_cache_file


def test_get_knowledge_base_dir_selects_profile_subdirectory(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "datasheet")

    kb_dir = get_knowledge_base_dir()

    assert kb_dir.name == "datasheet"
    assert kb_dir.parent.name == "knowledge_base"


def test_load_documents_only_scans_selected_profile_directory(tmp_path):
    kb_root = tmp_path / "knowledge_base"
    enterprise = kb_root / "enterprise"
    datasheet = kb_root / "datasheet"
    enterprise.mkdir(parents=True)
    datasheet.mkdir(parents=True)
    (enterprise / "expense.md").write_text("# 报销制度\n\n住宿标准", encoding="utf-8")
    (datasheet / "dlpc3436.md").write_text("# DLPC3436\n\n| f clk | 23.998 MHz |", encoding="utf-8")

    chunks = load_documents(enterprise)

    assert chunks
    assert {c["source"] for c in chunks} == {"expense_clean.md"}
    assert all(not c["is_datasheet"] for c in chunks)


def test_chroma_collection_names_are_profile_scoped(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "enterprise")

    names = get_chroma_collection_names()

    assert names["block"] == "agentic_rag_enterprise"
    assert names["datasheet_block"] == "agentic_rag_enterprise_block"
    assert names["datasheet_row"] == "agentic_rag_enterprise_row"


def test_retriever_uses_profile_scoped_collection_name(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "enterprise")

    retriever = Retriever([])

    assert retriever._datasheet_index.block_collection_name == "agentic_rag_enterprise_block"
    assert retriever._datasheet_index.row_collection_name == "agentic_rag_enterprise_row"


def test_profile_runtime_paths_point_inside_selected_kb(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "enterprise")

    kb_dir = get_knowledge_base_dir()

    assert get_question_cache_file() == kb_dir / ".question_cache.json"
    assert get_chroma_persist_dir() == kb_dir / "chroma_db"
