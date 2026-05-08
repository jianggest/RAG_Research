"""
search_datasheet skill 单元测试。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.search_datasheet import (
    _boost_datasheet_chunks,
    _discover_datasheet_sources,
    _expand_query,
    _filter_by_source,
    _merge_deduplicate,
    execute,
)


def test_expand_system_oscillator_query_adds_datasheet_terms():
    expanded = _expand_query("系统 Oscillator Timing 要求？")
    joined = "\n".join(expanded)

    assert "System Oscillator Timing Requirements" in joined
    assert "MOSC primary oscillator clock" in joined
    assert "t w(H)" in joined
    assert "t jp" in joined


def test_expand_frequency_accuracy_query_adds_ppm_terms():
    expanded = _expand_query("MOSC 频率精度是多少？")
    joined = "\n".join(expanded)

    assert "±200 ppm" in joined or "±200 PPM" in joined
    assert "aging temperature trim" in joined or "aging, temperature" in joined


def test_expand_spread_spectrum_query_adds_clock_spreading_terms():
    expanded = _expand_query("MOSC 是否支持 spread spectrum？")
    joined = "\n".join(expanded).lower()

    assert "spread spectrum" in joined
    assert "clock spreading" in joined


def test_boost_prefers_system_oscillator_table_over_unrelated_result():
    results = [
        {
            "text": "普通 timing 文本",
            "source": "dlpc3436_clean.md",
            "score": 1.5,
            "is_table": False,
        },
        {
            "text": "## 6.10 System Oscillator Timing Requirements\n| f clk | MOSC | 23.998 | 24.000 | 24.002 | MHz |",
            "source": "dlpc3436_clean.md",
            "score": 1.0,
            "is_table": True,
        },
    ]

    boosted = _boost_datasheet_chunks(results, query="MOSC oscillator timing")

    assert boosted[0]["text"].startswith("## 6.10")


def test_merge_deduplicate_prefers_richer_system_oscillator_chunk():
    short = {"source": "dlpc3436_clean.md", "text": "## 6.10 System Oscillator Timing Requirements\n| f clk |", "score": 9.0}
    rich = {"source": "dlpc3436_clean.md", "text": "## 6.10 System Oscillator Timing Requirements\n| f clk |\nThe MOSC input does not support spread spectrum clock spreading.", "score": 8.0}

    merged = _merge_deduplicate([short], [rich])

    assert len(merged) == 1
    assert "spread spectrum clock spreading" in merged[0]["text"]


def test_discover_datasheet_sources_includes_future_dlpc_documents():
    chunks = [
        {"source": "dlpc3436_clean.md", "text": "DLPC3436 controller datasheet System Oscillator", "score": 1.0},
        {"source": "dlpc3470_clean.md", "text": "DLPC3470 controller datasheet electrical characteristics", "score": 1.0},
        {"source": "报销相关_clean.md", "text": "差旅费报销制度", "score": 1.0},
    ]

    sources = _discover_datasheet_sources(chunks)

    assert "dlpc3436_clean.md" in sources
    assert "dlpc3470_clean.md" in sources
    assert "报销相关_clean.md" not in sources


def test_filter_by_source_keeps_datasheet_sources_only():
    results = [
        {"text": "datasheet", "source": "dlpc3436_clean.md", "score": 1.0},
        {"text": "expense", "source": "报销相关_clean.md", "score": 9.0},
    ]

    filtered = _filter_by_source(results, {"dlpc3436_clean.md"})

    assert len(filtered) == 1
    assert filtered[0]["source"] == "dlpc3436_clean.md"


class _BundleFirstRetriever:
    chunks = [{"source": "dlpc3436_clean.md", "text": "DLPC3436 controller datasheet"}]

    def __init__(self):
        self.search_calls = 0

    def search_datasheet_index(self, query, top_k=8, return_bundle=False):
        assert return_bundle is True
        return {
            "query": query,
            "query_type": "spi_flash",
            "source": "dlpc3436_clean.md",
            "evidence": [
                {
                    "kind": "block",
                    "source": "dlpc3436_clean.md",
                    "section_id": "7.3.3.1",
                    "section_title": "SPI Flash Interface",
                    "table_id": "",
                    "row_id": "",
                    "source_line": 918,
                    "score": 1.0,
                    "text": "VCC\\_FLSH pin must be supplied with the corresponding voltage.",
                },
                {
                    "kind": "block",
                    "source": "dlpc3436_clean.md",
                    "section_id": "7.3.3.1",
                    "section_title": "SPI Flash Interface",
                    "table_id": "Table 7-5",
                    "row_id": "",
                    "source_line": 920,
                    "score": 1.0,
                    "text": "Compatible SPI Flash Device Options W25Q32FVSSIG W25Q64FVSSIG",
                },
            ],
        }

    def search(self, *args, **kwargs):
        self.search_calls += 1
        return []


def test_execute_prefers_structured_bundle_planner_when_available():
    retriever = _BundleFirstRetriever()

    results = execute("支持哪些 3.3-V SPI flash？", retriever, {"domain": "technical_datasheet"})
    text = "\n".join(r["text"] for r in results)

    assert retriever.search_calls == 0
    assert results[0]["staged_reason"] == "bundle_spi_flash"
    assert results[0]["section_id"] == "7.3.3.1"
    assert "VCC\\_FLSH" in text and "corresponding voltage" in text
    assert "W25Q32FVSSIG" in text and "W25Q64FVSSIG" in text
