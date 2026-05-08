"""
Targeted staged retrieval regressions for remaining datasheet baseline gaps.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_datasheet_retrieval_baseline import _build_retriever
from skills.search_datasheet import execute as search_datasheet


def _texts_for(query: str) -> str:
    retriever = _build_retriever()
    results = search_datasheet(query, retriever, {"domain": "technical_datasheet"})[:20]
    return "\n".join(r.get("text", "") for r in results)


def test_parking_timing_stages_table_gpio_and_parkz_note():
    text = _texts_for("DMD parking timing 有哪些要求？")

    assert "DMD Parking Switching Characteristics" in text
    assert "t park" in text and "20" in text and "ms" in text
    assert "t fast park" in text and "32" in text and "µs" in text
    assert "GPIO\\_08" in text and "Normal mirror parking request" in text
    assert "fast park request" in text and "PARKZ goes low" in text


def test_i2c_iic_enumeration_stages_pin_rows_and_interface_rate():
    text = _texts_for("DLP3436 支持的 I2C/IIC 端口有哪些？")

    assert "IIC0_SCL" in text and "IIC0_SDA" in text
    assert "IIC1_SCL" in text and "IIC1_SDA" in text
    assert "internal use" in text
    assert "Both" in text and "I 2 C" in text and "100-kHz" in text and "baud rate" in text


def test_i2c_command_state_stages_host_irq_startup_sequence():
    text = _texts_for("什么时候可以通过 I2C 发送命令？")

    assert "HOST\\_IRQ" in text
    assert "ready to receive commands" in text
    assert "I 2 C" in text
    assert "auto-initialization" in text
    assert "falling edge" in text
