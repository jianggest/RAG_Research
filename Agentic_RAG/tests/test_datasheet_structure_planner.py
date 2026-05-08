"""
Phase 4 structure-driven evidence bundle tests.

This is the next step after the physical block/row collections: row hits should
be turned into structured evidence bundles using the structure digest, not only
hard-coded staged text matching in search_datasheet.py.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_loader import chunk_markdown
from retriever import (
    DatasheetIndexConfig,
    Retriever,
    build_datasheet_row_chunks,
    plan_datasheet_evidence_bundle,
)

ROOT = Path(__file__).resolve().parent.parent
STRUCTURE_PATH = ROOT / "knowledge_base" / ".structure" / "dlpc3436.structure.json"


def _sample_blocks():
    return chunk_markdown(
        """
## 5.6 Peripheral Interface

| IIC0_SCL | N10 | I/O | Type 7 | I2C secondary port 0 SCL |
| IIC0_SDA | P10 | I/O | Type 7 | I2C secondary port 0 SDA |
| IIC1_SCL | R13 | I/O | Type 7 | I2C secondary port 1 SCL |
| IIC1_SDA | R12 | I/O | Type 7 | I2C secondary port 1 SDA |

## 7.3.4 I 2 C Interface

Both I2C interface ports support 100-kHz baud rate.
""",
        "dlpc3436_clean.md",
        max_size=900,
    )


def _build_retriever():
    row_chunks = build_datasheet_row_chunks(STRUCTURE_PATH)
    retriever = Retriever(
        _sample_blocks(),
        datasheet_index=DatasheetIndexConfig(row_chunks=row_chunks, structure_path=STRUCTURE_PATH),
    )
    retriever.build_index()
    return retriever


def test_plan_datasheet_evidence_bundle_maps_i2c_query_to_row_and_section_context():
    retriever = _build_retriever()

    bundle = plan_datasheet_evidence_bundle("DLP3436支持哪些I2C端口？", retriever, top_k=8)

    assert bundle["query_type"] == "interface_ports"
    assert bundle["source"] == "dlpc3436_clean.md"
    assert any(e["kind"] == "row" and "IIC0_SCL" in e["text"] for e in bundle["evidence"])
    assert any(e["kind"] == "row" and "IIC1_SCL" in e["text"] for e in bundle["evidence"])
    assert any(e["kind"] == "block" and "100-kHz baud rate" in e["text"] for e in bundle["evidence"])
    assert all("section_id" in e and "source" in e for e in bundle["evidence"])


def test_search_datasheet_index_can_return_structured_bundle_when_requested():
    retriever = _build_retriever()

    bundle = retriever.search_datasheet_index("DLP3436支持哪些I2C端口？", top_k=8, return_bundle=True)

    assert bundle["query_type"] == "interface_ports"
    assert len(bundle["evidence"]) >= 3
    assert any(e["kind"] == "row" for e in bundle["evidence"])
    assert any(e["kind"] == "block" for e in bundle["evidence"])


def _texts(bundle: dict) -> str:
    return "\n".join(e["text"] for e in bundle["evidence"])


def test_bundle_planner_covers_oscillator_table_and_notes():
    retriever = _build_retriever()

    bundle = plan_datasheet_evidence_bundle("MOSC oscillator timing 有哪些要求？", retriever, top_k=8)
    text = _texts(bundle)

    assert bundle["query_type"] == "oscillator_timing"
    assert "System Oscillator Timing Requirements" in text
    assert "23.998" in text and "24.002" in text
    assert "±200 PPM" in text
    assert "spread spectrum clock spreading" in text


def test_bundle_planner_covers_oscillator_reading_closure():
    retriever = _build_retriever()

    bundle = retriever.search_datasheet_index("DLPC3436 系统 Oscillator Timing 要求？", top_k=8, return_bundle=True)
    closure = bundle["reading_closure"]
    text = "\n".join(
        item["quote"] for item in closure["anchors"] + closure["followed_cues"]
    )

    assert closure["closure_complete"] is True
    assert "Clock frequency, MOSC" in text
    assert "23.998" in text and "24.002" in text
    assert "does not support spread spectrum clock spreading" in text
    assert "Applies only when driven by an external digital oscillator" in text
    assert "PLL_REFCLK_I" in text and "oscillator input" in text
    assert "PLL_REFCLK_O" in text and "floating with no added capacitive load" in text


def test_bundle_planner_covers_spi_flash_condition_and_options():
    retriever = _build_retriever()

    bundle = plan_datasheet_evidence_bundle("支持哪些 3.3-V SPI flash？", retriever, top_k=8)
    text = _texts(bundle)

    assert bundle["query_type"] == "spi_flash"
    assert "VCC\\_FLSH" in text and "corresponding voltage" in text
    assert "Compatible SPI Flash Device Options" in text
    assert "W25Q32FVSSIG" in text and "W25Q64FVSSIG" in text


def test_bundle_planner_covers_dmd_parking_table_gpio_and_parkz_note():
    retriever = _build_retriever()

    bundle = plan_datasheet_evidence_bundle("DMD parking timing 有哪些要求？", retriever, top_k=8)
    text = _texts(bundle)

    assert bundle["query_type"] == "dmd_parking"
    assert "DMD Parking Switching Characteristics" in text
    assert "t park" in text and "t fast park" in text
    assert "GPIO\\_08 goes low" in text
    assert "fast park request" in text and "PARKZ goes low" in text


def test_bundle_planner_covers_i2c_command_ready_sequence():
    retriever = _build_retriever()

    bundle = plan_datasheet_evidence_bundle("什么时候可以通过 I2C 发送命令？", retriever, top_k=8)
    text = _texts(bundle)

    assert bundle["query_type"] == "i2c_command_ready"
    assert "HOST\\_IRQ" in text
    assert "ready to receive commands" in text
    assert "auto-initialization" in text
    assert "falling edge" in text
