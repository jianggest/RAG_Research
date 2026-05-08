"""
Datasheet source whitelist / metadata tests.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import DATASHEET_SOURCES
from doc_cleaner import _is_datasheet_document
from document_loader import chunk_markdown


def test_datasheet_sources_whitelist_contains_dlpc3436_variants():
    assert "dlpc3436.pdf" in DATASHEET_SOURCES
    assert "dlpc3436.md" in DATASHEET_SOURCES
    assert "dlpc3436_clean.md" in DATASHEET_SOURCES


def test_doc_cleaner_uses_datasheet_whitelist_before_hint_matching():
    assert _is_datasheet_document(
        Path("dlpc3436.md"),
        "content without automatic datasheet hints",
    ) is True
    assert _is_datasheet_document(
        Path("employee_policy.md"),
        "差旅费报销制度",
    ) is False


def test_chunk_markdown_marks_datasheet_chunks_from_whitelisted_source():
    chunks = chunk_markdown(
        "## 6.10 System Oscillator Timing Requirements\n\n| f clk | 23.998 | MHz |",
        "dlpc3436_clean.md",
        max_size=600,
    )
    assert chunks
    assert chunks[0]["is_datasheet"] is True
    assert chunks[0]["is_table"] is True


def test_chunk_markdown_does_not_mark_non_datasheet_source():
    chunks = chunk_markdown("## 出差制度\n\n正文", "travel_policy_clean.md", max_size=600)
    assert chunks
    assert chunks[0]["is_datasheet"] is False
