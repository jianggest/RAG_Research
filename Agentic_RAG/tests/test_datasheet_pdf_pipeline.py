"""
PDF 转换/清洗链路测试：新增 DLPC PDF 后应自动保留 datasheet 关键脚注，
不能依赖手工修改某个 *_clean.md。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from doc_cleaner import _clean_content, _post_process
from document_loader import chunk_markdown


def test_generic_dlpc_datasheet_footnotes_survive_cleaning_and_chunking():
    raw = """
# DLPC3470 Controller Datasheet

## 6.10 System Oscillator Timing Requirements

| PARAMETER | SYMBOL | MIN | TYP | MAX | UNIT |
|-----------|--------|-----|-----|-----|------|
| Clock frequency, MOSC | f clk | 23.998 | 24.000 | 24.002 | MHz |
| Cycle time | t c | 41.663 | 41.667 | 41.670 | ns |

(1) The frequency accuracy for MOSC is ±200 PPM including aging, temperature, and trim sensitivity.
The MOSC input does not support spread spectrum clock spreading.
(2) Pulse duration and jitter specifications apply only when driven by an external digital oscillator.

## Footer
<!-- image -->
"""

    cleaned = _post_process(_clean_content(raw, to_delete=set()))
    chunks = chunk_markdown(cleaned, "dlpc3470_clean.md", max_size=260)
    joined = "\n".join(c["text"] for c in chunks)

    assert "DLPC3470" in joined
    assert "System Oscillator Timing Requirements" in joined
    assert "±200 PPM" in joined
    assert "spread spectrum clock spreading" in joined
    assert any(c["is_table"] for c in chunks)
