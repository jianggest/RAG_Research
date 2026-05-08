"""
Phase 1 datasheet structure digest tests.

The digest is a lightweight, offline structure map for DLPC3436. It is not a
semantic KG; it preserves section/table/note anchors so later staged retrieval can
pull the right evidence bundle instead of relying on ad-hoc concept expansion.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRUCTURE_PATH = ROOT / "knowledge_base" / "dlpc3436.structure.json"
SOURCE_PATH = ROOT / "knowledge_base" / "dlpc3436_clean.md"


def _load_structure() -> dict:
    return json.loads(STRUCTURE_PATH.read_text(encoding="utf-8"))


def test_dlpc3436_structure_digest_schema_and_hash():
    data = _load_structure()
    assert data["schema_version"] == "0.1"
    assert data["source"] == "dlpc3436_clean.md"
    assert data["source_sha256"] == hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    assert data["line_count"] == len(SOURCE_PATH.read_text(encoding="utf-8").splitlines())
    assert data["section_count"] >= 100
    assert len(data["sections"]) == data["section_count"]
    assert len(data["anchors"]) >= 10


def test_dlpc3436_structure_digest_required_anchors():
    data = _load_structure()
    anchors = {item["id"]: item for item in data["anchors"]}
    required = {
        "oscillator_timing_table",
        "oscillator_mosc_notes",
        "reference_clock_layout",
        "pll_refclk_pins",
        "spi_flash_options",
        "spi_flash_voltage_condition",
        "vcc_intf_recommended",
        "iic0_control_port",
        "host_irq_initialization",
        "gpio08_parking",
    }
    assert required.issubset(anchors)
    assert 632 in anchors["oscillator_timing_table"]["lines"]
    assert 643 in anchors["oscillator_mosc_notes"]["lines"]
    assert 1237 in anchors["reference_clock_layout"]["lines"]
    assert 353 in anchors["pll_refclk_pins"]["lines"]
    assert 920 in anchors["spi_flash_options"]["lines"]
    assert anchors["spi_flash_voltage_condition"]["lines"], "VCC_FLSH condition anchor must resolve"


def test_dlpc3436_structure_digest_query_stage_hints():
    data = _load_structure()
    hints = data["query_stage_hints"]
    assert hints["oscillator_timing"] == [
        "oscillator_timing_table",
        "oscillator_mosc_notes",
        "reference_clock_layout",
        "pll_refclk_pins",
    ]
    assert hints["spi_flash_support"] == ["spi_flash_voltage_condition", "spi_flash_options"]
