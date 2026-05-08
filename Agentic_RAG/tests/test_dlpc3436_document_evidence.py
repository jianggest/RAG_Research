"""
DLPC3436 datasheet 文档证据测试。

这些测试只验证“知识库转换结果是否包含可支撑答案的原文证据”，不验证生成格式。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_loader import chunk_markdown

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
DLPC3436_CLEAN = KB_DIR / "dlpc3436_clean.md"


def _text() -> str:
    return DLPC3436_CLEAN.read_text(encoding="utf-8")


def test_dlpc3436_clean_contains_system_oscillator_timing_evidence():
    text = _text()

    required = [
        "## 6.10 System Oscillator Timing Requirements",
        "23.998",
        "24.000",
        "24.002",
        "41.663",
        "41.667",
        "41.670",
        "t w(H)",
        "t w(L)",
        "t t",
        "t jp",
        "2%",
        "Applies only when driven by an external digital oscillator",
    ]
    for item in required:
        assert item in text, f"missing evidence: {item}"


def test_dlpc3436_clean_contains_mosc_accuracy_and_spread_spectrum_evidence():
    text = _text()

    assert "frequency accuracy for MOSC is ±200 PPM" in text
    assert "aging, temperature, and trim sensitivity" in text
    assert "MOSC input does not support spread spectrum clock spreading" in text


def test_dlpc3436_clean_contains_external_oscillator_pin_evidence():
    text = _text()

    assert "PLL_REFCLK_I" in text
    assert "PLL_REFCLK_O" in text
    assert "oscillator output must drive the PLL\\_REFCLK\\_I" in text
    assert "PLL\\_REFCLK\\_O pin must be left unconnected" in text


def test_system_oscillator_chunk_is_table_and_adjacent_notes_are_available():
    chunks = chunk_markdown(_text(), "dlpc3436_clean.md", max_size=600)
    table_idx = next(
        i for i, c in enumerate(chunks)
        if "System Oscillator Timing Requirements" in c["text"] and "23.998" in c["text"]
    )
    target = chunks[table_idx]
    nearby_text = "\n".join(c["text"] for c in chunks[table_idx: table_idx + 2])

    assert target["is_table"] is True
    assert "t jp" in target["text"]
    assert "2%" in target["text"]
    assert "frequency accuracy for MOSC is ±200 PPM" in nearby_text
    assert "spread spectrum clock spreading" in nearby_text
    assert "external digital oscillator" in nearby_text
