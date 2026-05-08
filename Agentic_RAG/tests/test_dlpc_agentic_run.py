"""
DLPC/datasheet Agentic RAG 编排级集成测试。
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentic_rag import run
from document_loader import load_documents


class KeywordRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, query, method="hybrid", top_k=10, where=None):
        allowed = set((where or {}).get("source", {}).get("$in", []))
        tokens = [t.lower() for t in query.replace("_", " ").replace("/", " ").split() if len(t) >= 2]
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
                    score += 50
            if "spread spectrum clock spreading" in tl:
                score += 10
            if "pll_refclk_i" in tl or "pll_refclk_o" in tl:
                score += 6
            if score > 0:
                out.append({**chunk, "score": float(score)})
        return sorted(out, key=lambda r: r["score"], reverse=True)[:top_k]


def test_agentic_run_routes_dlpc_datasheet_to_search_datasheet_and_generator():
    chunks = load_documents(Path(__file__).parent.parent / "knowledge_base")
    retriever = KeywordRetriever([c for c in chunks if "dlpc" in c["source"].lower()])

    planner_response = '{"reasoning":"技术datasheet参数查询","steps":[{"step_id":1,"skill":"search_datasheet","query":"系统 Oscillator Timing 要求？","depends_on":null}]}'
    final_answer = "DLPC 系统振荡器要求：f clk 23.998/24.000/24.002 MHz；t c 41.663/41.667/41.670 ns；MOSC input does not support spread spectrum clock spreading；PLL_REFCLK_I，PLL_REFCLK_O unconnected。"

    with patch("planner.call_llm", return_value=planner_response), patch("generator.call_llm", return_value=final_answer):
        result = run("系统 Oscillator Timing 要求？", retriever)

    assert result["needs_clarification"] is False
    assert result["query_structure"]["domain"] == "technical_datasheet"
    assert result["plan"]["steps"][0]["skill"] == "search_datasheet"
    assert result["executed_steps"][0]["results"]
    context_text = "\n".join(r["text"] for r in result["executed_steps"][0]["results"])
    assert "System Oscillator Timing Requirements" in context_text
    assert "spread spectrum clock spreading" in context_text
    assert "PLL_REFCLK_I" in context_text
    assert "24.002" in result["answer"]
    assert "does not support spread spectrum" in result["answer"]
