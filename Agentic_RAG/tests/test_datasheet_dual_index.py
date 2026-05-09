"""
Phase 2 full dual-index tests for datasheet retrieval.

The earlier Phase 2/3/6 slice created row chunks but still used one collection.
This file locks the next behavior: datasheet block and row indexes must be
physically separated and query APIs must expose block/row/datasheet merge paths.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_loader import chunk_markdown
from retriever import DatasheetIndexConfig, Retriever, build_datasheet_row_chunks

ROOT = Path(__file__).resolve().parent.parent
STRUCTURE_PATH = ROOT / "knowledge_base" / ".structure" / "dlpc3436.structure.json"


def _sample_block_chunks():
    return chunk_markdown(
        """
## 5.6 Peripheral Interface

| IIC0_SCL | N10 | I/O | Type 7 | I2C secondary port 0 SCL |
| IIC0_SDA | P10 | I/O | Type 7 | I2C secondary port 0 SDA |

## 7.3.4 I 2 C Interface

Both I2C interface ports support 100-kHz baud rate.
""",
        "dlpc3436_clean.md",
        max_size=600,
    )


def test_retriever_builds_physical_block_and_row_collections():
    blocks = _sample_block_chunks()
    row_chunks = build_datasheet_row_chunks(STRUCTURE_PATH)
    retriever = Retriever(blocks, datasheet_index=DatasheetIndexConfig(row_chunks=row_chunks))

    retriever.build_index()

    assert retriever._block_collection is not None
    assert retriever._row_collection is not None
    assert retriever._block_collection.name.endswith("_block")
    assert retriever._row_collection.name.endswith("_row")
    assert retriever._collection is retriever._block_collection
    assert retriever._row_chunks is row_chunks


def test_search_block_and_search_row_are_physically_separated():
    blocks = _sample_block_chunks()
    row_chunks = build_datasheet_row_chunks(STRUCTURE_PATH)
    retriever = Retriever(blocks, datasheet_index=DatasheetIndexConfig(row_chunks=row_chunks))
    retriever.build_index()

    block_results = retriever.search_block("I2C interface baud rate", top_k=3)
    row_results = retriever.search_row("IIC0_SCL pin row", top_k=5)

    assert block_results
    assert all(r["index_kind"] == "block" for r in block_results)
    assert row_results
    assert all(r["index_kind"] == "row" for r in row_results)
    assert any("IIC0_SCL" in r["text"] for r in row_results)


def test_search_datasheet_index_merges_row_hits_before_block_context():
    blocks = _sample_block_chunks()
    row_chunks = build_datasheet_row_chunks(STRUCTURE_PATH)
    retriever = Retriever(blocks, datasheet_index=DatasheetIndexConfig(row_chunks=row_chunks))
    retriever.build_index()

    results = retriever.search_datasheet_index("DLP3436支持的I2C有哪些？", top_k=8)

    assert results
    assert any(r["index_kind"] == "row" and "IIC0_SCL" in r["text"] for r in results)
    assert any(r["index_kind"] == "block" and "100-kHz baud rate" in r["text"] for r in results)
    kinds = [r["index_kind"] for r in results]
    assert kinds.index("row") < kinds.index("block")
