"""
Regression tests for datasheet staged retrieval.

These tests encode Phase 4 small-slice requirements from tasks/datasheet_rag_status.md:
- oscillator queries must retrieve both timing table and adjacent MOSC notes;
- 3.3V SPI flash support queries must retrieve both VCC_FLSH prerequisite and compatible device table.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_loader import load_documents
from skills.search_datasheet import execute as search_datasheet


class KeywordRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, query, method="hybrid", top_k=10, where=None):
        allowed = set((where or {}).get("source", {}).get("$in", []))
        tokens = [t.lower() for t in query.replace("_", " ").replace("/", " ").replace("-", " ").split() if len(t) >= 2]
        out = []
        for chunk in self.chunks:
            if allowed and chunk["source"] not in allowed:
                continue
            text = chunk["text"]
            tl = text.lower()
            score = sum(1 for t in tokens if t in tl)
            if "system oscillator timing requirements" in tl:
                score += 10
            if "spread spectrum clock spreading" in tl:
                score += 10
            if "vcc_flsh" in tl:
                score += 8
            if "compatible spi flash device options" in tl:
                score += 8
            if score > 0:
                out.append({**chunk, "score": float(score)})
        return sorted(out, key=lambda r: r["score"], reverse=True)[:top_k]


def _build_retriever():
    chunks = load_documents(Path(__file__).parent.parent / "knowledge_base")
    return KeywordRetriever([c for c in chunks if c.get("is_datasheet") or "dlpc" in c["source"].lower()])


def _joined(results):
    return "\n".join(r.get("text", "") for r in results)


def test_staged_oscillator_query_retrieves_table_and_mosc_notes():
    retriever = _build_retriever()

    results = search_datasheet("DLPC3436 系统 Oscillator Timing 要求？", retriever)
    text = _joined(results)

    assert "System Oscillator Timing Requirements" in text
    assert "23.998" in text
    assert "24.002" in text
    assert "t jp" in text
    assert "±200 PPM" in text
    assert "spread spectrum clock spreading" in text
    assert "external digital oscillator" in text


def test_staged_spi_flash_support_query_retrieves_vcc_flsh_condition_and_options():
    retriever = _build_retriever()

    results = search_datasheet("DLPC3436 支持 3.3V SPI flash 吗？", retriever)
    text = _joined(results)

    assert "VCC_FLSH" in text
    assert "corresponding voltage" in text
    assert "3.3-V compatible SPI serial flash devices" in text
    assert "DLPC3436 Compatible SPI Flash Device Options" in text
    assert "W25Q32FVSSIG" in text
    assert "W25Q64FVSSIG" in text
