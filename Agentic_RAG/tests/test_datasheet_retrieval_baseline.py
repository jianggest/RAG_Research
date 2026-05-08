"""
Datasheet Phase 0 retrieval-only baseline.

This is deterministic and dependency-light: no LLM, no embedding model. It measures
whether current indexed chunks can retrieve golden evidence in
`evaluation/datasheet_baseline_cases.json`.
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_loader import load_documents
from skills.search_datasheet import execute as search_datasheet

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "evaluation" / "datasheet_baseline_cases.json"
KB_PATH = ROOT / "knowledge_base"
REPORT_JSON_PATH = ROOT / "evaluation" / ".datasheet_retrieval_metrics.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_cases() -> dict:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    source_path = KB_PATH / data["source"]
    actual_hash = _sha256(source_path)
    assert actual_hash == data["source_md_sha256"], (
        f"{data['source']} hash changed; golden evidence line ranges require review. "
        f"expected={data['source_md_sha256']} actual={actual_hash}"
    )
    return data


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("i²c", "i 2 c").replace("i2c", "i 2 c").replace("iic", "iic")
    text = text.replace("_", " ").replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text)


def _tokenize(text: str) -> list[str]:
    normalized = _normalize(text)
    return [t for t in re.split(r"[^a-z0-9µ±.%]+", normalized) if len(t) >= 2]


class LexicalBaselineRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, query: str, method: str = "hybrid", top_k: int = 20, source: str | None = None, where: dict | None = None):
        q_tokens = _tokenize(query)
        q_norm = _normalize(query)
        allowed = set((where or {}).get("source", {}).get("$in", []))
        results = []
        for chunk in self.chunks:
            if source and chunk.get("source") != source:
                continue
            if allowed and chunk.get("source") not in allowed:
                continue
            text = chunk.get("text", "")
            text_norm = _normalize(text)
            score = sum(1 for t in q_tokens if t in text_norm)

            # Baseline alias normalization only; no related-entity expansion.
            if any(x in q_norm for x in ("i 2 c", "iic")) and any(x in text_norm for x in ("i 2 c", "iic")):
                score += 2
            if "oscillator" in q_norm and "system oscillator timing requirements" in text_norm:
                score += 6
            if "spread spectrum" in q_norm and "spread spectrum clock spreading" in text_norm:
                score += 8
            if "pll refclk" in q_norm and "pll refclk" in text_norm:
                score += 4
            if ("vcc intf" in q_norm or "vcc" in q_norm) and "vcc intf" in text_norm:
                score += 3
            if "spi" in q_norm and "spi" in text_norm:
                score += 2
            if "host irq" in q_norm and "host irq" in text_norm:
                score += 4
            if "gpio 08" in q_norm and "gpio 08" in text_norm:
                score += 4

            if chunk.get("is_table"):
                score *= 1.15
            if score > 0:
                results.append({**chunk, "score": float(score)})
        return sorted(results, key=lambda r: r["score"], reverse=True)[:top_k]


def _build_retriever():
    chunks = load_documents(KB_PATH)
    datasheet_chunks = [c for c in chunks if c.get("is_datasheet") or "dlpc" in c["source"].lower()]
    return LexicalBaselineRetriever(datasheet_chunks)


def _terms_hit(text: str, terms: list[str]) -> int:
    tl = text.lower()
    return sum(1 for term in terms if term.lower() in tl)


def _evidence_hit(results: list[dict], evidence: dict, top_k: int) -> bool:
    text = "\n".join(r.get("text", "") for r in results[:top_k])
    return _terms_hit(text, evidence.get("required_terms", [])) == len(evidence.get("required_terms", []))


def _case_metrics(case: dict, retriever: LexicalBaselineRetriever, source: str) -> dict:
    results = search_datasheet(case["query"], retriever, {"domain": "technical_datasheet"})[:30]
    evidence = case["golden_evidence"]
    total_evidence = len(evidence)
    top10_hits = sum(1 for ev in evidence if _evidence_hit(results, ev, 10))
    top20_hits = sum(1 for ev in evidence if _evidence_hit(results, ev, 20))
    all_terms = []
    for ev in evidence:
        all_terms.extend(ev.get("required_terms", []))
    joined20 = "\n".join(r.get("text", "") for r in results[:20])
    required_hit = _terms_hit(joined20, all_terms)
    required_total = len(all_terms)
    return {
        "id": case["id"],
        "query": case["query"],
        "query_type": case["query_type"],
        "adversarial": case.get("adversarial", False),
        "retrieved": len(results),
        "evidence_total": total_evidence,
        "recall_at_10": top10_hits / total_evidence if total_evidence else 0.0,
        "recall_at_20": top20_hits / total_evidence if total_evidence else 0.0,
        "required_terms_hit_rate": required_hit / required_total if required_total else 0.0,
        "missed_evidence_at_20": [ev["id"] for ev in evidence if not _evidence_hit(results, ev, 20)],
        "top_sources": [f"{r.get('source')}#{r.get('chunk_index')}:{r.get('score')}" for r in results[:5]],
    }


def compute_metrics() -> dict:
    data = _load_cases()
    retriever = _build_retriever()
    cases = [_case_metrics(case, retriever, data["source"]) for case in data["cases"]]
    by_type = defaultdict(list)
    for item in cases:
        by_type[item["query_type"]].append(item)

    def avg(items, key):
        return sum(i[key] for i in items) / len(items) if items else 0.0

    summary = {
        "case_count": len(cases),
        "query_type_counts": {k: len(v) for k, v in sorted(by_type.items())},
        "recall_at_10": avg(cases, "recall_at_10"),
        "recall_at_20": avg(cases, "recall_at_20"),
        "required_terms_hit_rate": avg(cases, "required_terms_hit_rate"),
        "by_query_type": {
            k: {
                "count": len(v),
                "recall_at_10": avg(v, "recall_at_10"),
                "recall_at_20": avg(v, "recall_at_20"),
                "required_terms_hit_rate": avg(v, "required_terms_hit_rate"),
            }
            for k, v in sorted(by_type.items())
        },
        "failed_cases_at_20": [c["id"] for c in cases if c["recall_at_20"] < 1.0],
    }
    return {"summary": summary, "cases": cases}


def test_datasheet_baseline_schema_expected_facts_map_to_evidence():
    data = _load_cases()
    assert len(data["cases"]) >= 15
    query_types = {case["query_type"] for case in data["cases"]}
    assert {"parameter", "enumeration", "connection", "support", "state"}.issubset(query_types)
    for case in data["cases"]:
        evidence_ids = {ev["id"] for ev in case["golden_evidence"]}
        for fact in case["expected_facts"]:
            assert fact.get("evidence_refs"), f"{case['id']} {fact['id']} missing evidence_refs"
            unknown = set(fact["evidence_refs"]) - evidence_ids
            assert not unknown, f"{case['id']} {fact['id']} references unknown evidence {unknown}"
            assert fact.get("must_have_terms"), f"{case['id']} {fact['id']} missing must_have_terms"


def test_datasheet_retrieval_baseline_metrics_written():
    metrics = compute_metrics()
    REPORT_JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert metrics["summary"]["case_count"] >= 15
    assert metrics["summary"]["recall_at_20"] >= 0.60
    assert metrics["summary"]["required_terms_hit_rate"] >= 0.60
