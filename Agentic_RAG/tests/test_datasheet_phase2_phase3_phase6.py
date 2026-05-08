"""
Phase 2/3/6 datasheet infrastructure tests.

These tests cover the next engineering slice after targeted staged retrieval:
- Phase 2: expose row-level datasheet chunks from the structure digest and keep
  row/block metadata distinct.
- Phase 3: normalize both indexed text and query aliases for exact sparse match.
- Phase 6: prevent datasheet chunks from entering natural-language question
  augmentation.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_loader import chunk_markdown
from index_augmenter import _should_augment
from retriever import normalize_datasheet_text

ROOT = Path(__file__).resolve().parent.parent
STRUCTURE_PATH = ROOT / "knowledge_base" / ".structure" / "dlpc3436.structure.json"


def test_datasheet_chunks_include_normalized_text_and_entity_tokens():
    chunks = chunk_markdown(
        "## 5.6 Peripheral Interface\n\n| IIC0_SCL | N10 | I/O | Type 7 | I 2 C secondary port 0 SCL |\n",
        "dlpc3436_clean.md",
        max_size=600,
    )
    assert chunks
    chunk = chunks[0]
    assert chunk["is_datasheet"] is True
    assert chunk["index_kind"] == "block"
    assert "normalized_text" in chunk
    assert "I2C" in chunk["normalized_text"]
    assert "IIC0_SCL" in chunk["entity_tokens"]


def test_normalize_datasheet_text_unifies_common_aliases():
    normalized = normalize_datasheet_text(
        "I 2 C / I²C via GPIO08 and PLL REFCLK I, +/-200 PPM, f clk"
    )
    assert "I2C" in normalized
    assert "GPIO_08" in normalized
    assert "PLL_REFCLK_I" in normalized
    assert "±200 ppm" in normalized
    assert "f_clk" in normalized


def test_retriever_builds_datasheet_row_chunks_from_structure_digest():
    from retriever import build_datasheet_row_chunks

    rows = build_datasheet_row_chunks(STRUCTURE_PATH)
    assert rows
    iic_row = next(row for row in rows if "IIC0_SCL" in row["text"])
    assert iic_row["index_kind"] == "row"
    assert iic_row["is_datasheet"] is True
    assert iic_row["source"] == "dlpc3436_clean.md"
    assert iic_row["row_id"]
    assert iic_row["table_id"]
    assert "[row:" in iic_row["text"]
    assert "I2C" in iic_row["normalized_text"]
    assert "IIC0_SCL" in iic_row["entity_tokens"]


def test_datasheet_chunks_are_not_augmented_even_when_table_like():
    chunks = chunk_markdown(
        "## 6.10 System Oscillator Timing Requirements\n\n| f clk | 23.998 | MHz |",
        "dlpc3436_clean.md",
        max_size=600,
    )
    assert chunks[0]["is_table"] is True
    assert chunks[0]["is_datasheet"] is True
    assert _should_augment(chunks[0]) is False
