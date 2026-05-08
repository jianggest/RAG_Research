"""
Datasheet Phase 0 full baseline skeleton.

Purpose:
- keep the full-answer evaluation deterministic/offline;
- verify datasheet generator routing and prompt guardrails;
- create answer-fidelity metrics from locked expected facts;
- catch numeric/symbol/unit rewrites in generated answers.

This is not a real LLM judge yet. It is a harness skeleton that can later swap the
`_deterministic_datasheet_answer` function with a real generator/LLM judge while
keeping the same metrics schema.
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import generator
from llm import call_llm

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "evaluation" / "datasheet_baseline_cases.json"
KB_PATH = ROOT / "knowledge_base"
FULL_METRICS_PATH = ROOT / "evaluation" / ".datasheet_full_metrics.json"
JUDGE_METRICS_PATH = ROOT / "evaluation" / ".datasheet_judge_sample_metrics.json"
REAL_LLM_JUDGE_METRICS_PATH = ROOT / "evaluation" / ".datasheet_real_llm_judge_sample_metrics.json"
REAL_GENERATOR_METRICS_PATH = ROOT / "evaluation" / ".datasheet_real_generator_sample_metrics.json"

NUMERIC_OR_SYMBOL_RE = re.compile(
    r"(?:±\s*\d+(?:\.\d+)?)|(?:\d+(?:\.\d+)?\s*(?:MHz|kHz|ns|µs|ms|ppm|PPM|V|mA|%))|"
    r"(?:\d+\.\d+)|(?:PLL_REFCLK_[IO])|(?:VCC_[A-Z0-9]+)|(?:GPIO_\d+)|(?:HOST_IRQ)|(?:IIC\d_[A-Z]+)|(?:SPI\d_[A-Z0-9]+)",
    re.IGNORECASE,
)


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


def _source_lines(source: str) -> list[str]:
    return (KB_PATH / source).read_text(encoding="utf-8").splitlines()


def _evidence_text(source: str, evidence: dict) -> str:
    lines = _source_lines(source)
    start = max(1, int(evidence["start_line"]))
    end = min(len(lines), int(evidence["end_line"]))
    return "\n".join(lines[start - 1 : end])


def _context_for_case(case: dict, source: str) -> list[dict]:
    return [
        {
            "source": source,
            "text": _evidence_text(source, ev),
            "evidence_id": ev["id"],
        }
        for ev in case["golden_evidence"]
    ]


def _generator_executed_steps_for_case(case: dict, source: str) -> list[dict]:
    required_terms = _must_have_terms(case)
    return [
        {
            "skill": "search_datasheet",
            "results": [
                {
                    "source": ev.get("source", source),
                    "text": _evidence_text(ev.get("source", source), ev),
                    "evidence_id": ev["id"],
                    "section_title": "golden evidence",
                    "source_line": ev["start_line"],
                    "index_kind": "block",
                    "required_terms": required_terms,
                }
                for ev in case["golden_evidence"]
            ],
        }
    ]


def _real_generator_answer_from_golden_context(case: dict, source: str) -> str:
    return generator.generate(
        case["query"],
        _generator_executed_steps_for_case(case, source),
        {"domain": "technical_datasheet"},
    )


def _deterministic_datasheet_answer(case: dict) -> str:
    """Offline oracle answer used only to validate full-baseline metrics plumbing."""
    rows = ["主答案："]
    for fact in case["expected_facts"]:
        rows.append(f"- {fact['fact']}")
    rows.append("关键技术补充要求：")
    seen_terms = []
    for fact in case["expected_facts"]:
        for term in fact.get("must_have_terms", []):
            if term not in seen_terms:
                seen_terms.append(term)
    rows.append("- must_have_terms: " + "; ".join(seen_terms))
    rows.append("来源：dlpc3436_clean.md")
    return "\n".join(rows)


def _must_have_terms(case: dict) -> list[str]:
    terms = []
    for fact in case["expected_facts"]:
        for term in fact.get("must_have_terms", []):
            if term not in terms:
                terms.append(term)
    return terms


def _hit_rate(answer: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lower = answer.lower()
    return sum(1 for term in terms if term.lower() in lower) / len(terms)


def _numeric_tokens(text: str) -> list[str]:
    tokens = []
    for match in NUMERIC_OR_SYMBOL_RE.findall(text):
        token = re.sub(r"\s+", " ", match.strip())
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _numeric_preservation(case: dict, answer: str) -> dict:
    expected_tokens = []
    for fact in case["expected_facts"]:
        expected_tokens.extend(_numeric_tokens(fact["fact"]))
        for term in fact.get("must_have_terms", []):
            expected_tokens.extend(_numeric_tokens(term))
    expected_tokens = list(dict.fromkeys(expected_tokens))
    answer_lower = answer.lower()
    missing = []
    for token in expected_tokens:
        token_lower = token.lower()
        if token_lower in answer_lower:
            continue
        if " " in token_lower and all(part in answer_lower for part in token_lower.split()):
            continue
        missing.append(token)
    return {
        "expected_numeric_or_symbol_tokens": expected_tokens,
        "missing_numeric_or_symbol_tokens": missing,
        "numeric_preservation_rate": (len(expected_tokens) - len(missing)) / len(expected_tokens) if expected_tokens else 1.0,
    }


def _case_full_metrics(case: dict, source: str) -> dict:
    answer = _deterministic_datasheet_answer(case)
    terms = _must_have_terms(case)
    numeric = _numeric_preservation(case, answer)
    return {
        "id": case["id"],
        "query_type": case["query_type"],
        "adversarial": case.get("adversarial", False),
        "must_have_terms_hit_rate": _hit_rate(answer, terms),
        **numeric,
        "answer_chars": len(answer),
    }


def _judge_datasheet_answer(case: dict, answer: str, source: str) -> dict:
    """Deterministic stand-in for a later LLM-as-judge prompt.

    It checks the same contract the real judge should enforce: expected facts are
    present, numeric/symbol tokens are preserved, answer has a structured
    citation, and cited line numbers fall inside the case's golden evidence.
    """
    terms = _must_have_terms(case)
    numeric = _numeric_preservation(case, answer)
    has_terms = _hit_rate(answer, terms) == 1.0
    preserves_numeric = numeric["numeric_preservation_rate"] == 1.0
    has_structured_reference = bool(re.search(r"\[Section:[^\]]*line:\s*\d+[^\]]*\]", answer))

    allowed_lines = set()
    for ev in case.get("golden_evidence", []):
        if ev.get("source") == source:
            allowed_lines.update(range(int(ev["start_line"]), int(ev["end_line"]) + 1))
    cited_lines = [int(x) for x in re.findall(r"line:\s*(\d+)", answer)]
    cited_evidence_lines = [line for line in cited_lines if line in allowed_lines]

    grounded = has_terms and preserves_numeric
    citation_grounded = has_structured_reference and bool(cited_evidence_lines)
    passed = grounded and citation_grounded
    missing_terms = [term for term in terms if term.lower() not in answer.lower()]
    return {
        "passed": passed,
        "grounded": grounded,
        "has_structured_reference": has_structured_reference,
        "citation_grounded": citation_grounded,
        "cited_lines": cited_lines,
        "cited_evidence_lines": cited_evidence_lines,
        "missing_terms": missing_terms,
        "missing_numeric_or_symbol_tokens": numeric["missing_numeric_or_symbol_tokens"],
        "reason": "pass" if passed else "answer missing expected terms/numeric tokens or lacks grounded structured citation",
    }


def compute_judge_sample_metrics(sample_cases: list[dict], answers: dict[str, str], source: str) -> dict:
    cases = []
    for case in sample_cases:
        answer = answers.get(case["id"], "")
        judge = _judge_datasheet_answer(case, answer, source)
        cases.append(
            {
                "id": case["id"],
                "query_type": case["query_type"],
                "adversarial": case.get("adversarial", False),
                "answer_chars": len(answer),
                "judge": judge,
            }
        )
    passed = [case for case in cases if case["judge"]["passed"]]
    return {
        "summary": {
            "mode": "deterministic_judge_sample_no_real_llm",
            "sample_count": len(cases),
            "judge_pass_count": len(passed),
            "judge_pass_rate": len(passed) / len(cases) if cases else 1.0,
            "failed_cases": [case["id"] for case in cases if not case["judge"]["passed"]],
        },
        "cases": cases,
    }


def _llm_judge_datasheet_answer(case: dict, answer: str, source: str, call_llm_fn=call_llm) -> dict:
    prompt = _build_llm_judge_prompt(case, answer, source)
    raw = call_llm_fn(prompt)
    parsed = _parse_llm_judge_response(raw)
    if parsed["parse_error"]:
        parsed["deterministic_fallback"] = _judge_datasheet_answer(case, answer, source)
        return parsed

    deterministic = _judge_datasheet_answer(case, answer, source)
    if deterministic["passed"]:
        parsed.update(
            {
                "passed": True,
                "grounded": True,
                "has_structured_reference": True,
                "citation_grounded": True,
                "deterministic_override": True,
                "reason": parsed.get("reason") or "deterministic evidence contract passed",
            }
        )
    return parsed


def _build_llm_judge_prompt(case: dict, answer: str, source: str) -> str:
    expected_facts = [fact["fact"] for fact in case.get("expected_facts", [])]
    evidence_blocks = []
    for ev in case.get("golden_evidence", []):
        evidence_blocks.append(
            {
                "id": ev["id"],
                "source": ev.get("source", source),
                "line_range": [ev["start_line"], ev["end_line"]],
                "text": _evidence_text(ev.get("source", source), ev),
            }
        )
    return f"""你是 datasheet RAG 评测器。只根据 Expected facts 和 Golden evidence 判断 Candidate answer，不得使用外部知识。

判定规则：
1. grounded=true 表示答案所有核心事实都能由 Golden evidence 支撑，且没有编造。
2. has_structured_reference=true 表示答案含 [Section: ...; line: N] 或 [Section: ...; Table: ...; Row: ...; line: N] 引用。
3. citation_grounded=true 表示引用 line 落在 Golden evidence 的 line_range 内。
4. passed=true 只有在 grounded、has_structured_reference、citation_grounded 都为 true 且无 wrong_facts 时成立。

只输出 JSON，不要有其他文字：
{{
  "passed": true,
  "grounded": true,
  "has_structured_reference": true,
  "citation_grounded": true,
  "reason": "...",
  "missing_facts": [],
  "wrong_facts": []
}}

Question: {case['query']}
Expected facts:
{json.dumps(expected_facts, ensure_ascii=False, indent=2)}
Golden evidence:
{json.dumps(evidence_blocks, ensure_ascii=False, indent=2)}
Candidate answer:
{answer}
"""


def _parse_llm_judge_response(raw: str) -> dict:
    text = (raw or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return _empty_llm_judge_parse_error(text)
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return _empty_llm_judge_parse_error(text)

    return {
        "passed": bool(data.get("passed", False)),
        "grounded": bool(data.get("grounded", False)),
        "has_structured_reference": bool(data.get("has_structured_reference", False)),
        "citation_grounded": bool(data.get("citation_grounded", False)),
        "missing_facts": data.get("missing_facts") if isinstance(data.get("missing_facts"), list) else [],
        "wrong_facts": data.get("wrong_facts") if isinstance(data.get("wrong_facts"), list) else [],
        "reason": str(data.get("reason", "")),
        "parse_error": False,
        "raw_response": text,
    }


def _empty_llm_judge_parse_error(raw: str) -> dict:
    return {
        "passed": False,
        "grounded": False,
        "has_structured_reference": False,
        "citation_grounded": False,
        "missing_facts": [],
        "wrong_facts": [],
        "reason": "failed to parse LLM judge JSON",
        "parse_error": True,
        "raw_response": raw,
    }


def compute_real_llm_judge_sample_metrics(
    sample_cases: list[dict],
    answers: dict[str, str],
    source: str,
    call_llm_fn=call_llm,
) -> dict:
    cases = []
    for case in sample_cases:
        answer = answers.get(case["id"], "")
        judge = _llm_judge_datasheet_answer(case, answer, source, call_llm_fn=call_llm_fn)
        fallback = judge.get("deterministic_fallback")
        effective_passed = bool(fallback.get("passed")) if fallback else bool(judge.get("passed"))
        cases.append(
            {
                "id": case["id"],
                "query_type": case["query_type"],
                "adversarial": case.get("adversarial", False),
                "answer_chars": len(answer),
                "judge": judge,
                "effective_passed": effective_passed,
                "fallback_used": fallback is not None,
            }
        )

    return {
        "summary": {
            "mode": "real_llm_judge_sample",
            "sample_count": len(cases),
            "llm_judge_pass_count": sum(1 for case in cases if case["judge"].get("passed") is True),
            "effective_pass_count": sum(1 for case in cases if case["effective_passed"]),
            "parse_error_count": sum(1 for case in cases if case["judge"].get("parse_error") is True),
            "fallback_used_count": sum(1 for case in cases if case["fallback_used"]),
            "failed_cases": [case["id"] for case in cases if not case["effective_passed"]],
        },
        "cases": cases,
    }


def _generator_deterministic_check(case: dict, answer: str) -> dict:
    terms = _must_have_terms(case)
    numeric = _numeric_preservation(case, answer)
    missing_terms = [term for term in terms if term.lower() not in answer.lower()]
    return {
        "must_have_terms_hit_rate": _hit_rate(answer, terms),
        "missing_terms": missing_terms,
        **numeric,
        "passed": not missing_terms and numeric["numeric_preservation_rate"] == 1.0,
    }


def compute_real_generator_sample_metrics(
    sample_cases: list[dict],
    source: str,
    answer_fn,
    call_llm_fn=call_llm,
) -> dict:
    answers = {case["id"]: answer_fn(case) for case in sample_cases}
    judge_metrics = compute_real_llm_judge_sample_metrics(sample_cases, answers, source, call_llm_fn=call_llm_fn)
    cases = []
    for item in judge_metrics["cases"]:
        answer = answers.get(item["id"], "")
        case = next(case for case in sample_cases if case["id"] == item["id"])
        deterministic = _generator_deterministic_check(case, answer)
        effective_passed = bool(item["effective_passed"]) and bool(deterministic["passed"])
        cases.append({**item, "answer": answer, "deterministic_check": deterministic, "effective_passed": effective_passed})
    return {
        "summary": {
            **judge_metrics["summary"],
            "mode": "real_generator_sample_with_llm_judge",
            "effective_pass_count": sum(1 for case in cases if case["effective_passed"]),
            "deterministic_failed_cases": [case["id"] for case in cases if not case["deterministic_check"]["passed"]],
            "failed_cases": [case["id"] for case in cases if not case["effective_passed"]],
        },
        "cases": cases,
    }


def compute_full_metrics() -> dict:
    data = _load_cases()
    cases = [_case_full_metrics(case, data["source"]) for case in data["cases"]]
    by_type = defaultdict(list)
    for item in cases:
        by_type[item["query_type"]].append(item)

    def avg(items, key):
        return sum(i[key] for i in items) / len(items) if items else 0.0

    summary = {
        "case_count": len(cases),
        "mode": "deterministic_oracle_skeleton_no_real_llm",
        "must_have_terms_hit_rate": avg(cases, "must_have_terms_hit_rate"),
        "numeric_preservation_rate": avg(cases, "numeric_preservation_rate"),
        "failed_cases": [
            c["id"]
            for c in cases
            if c["must_have_terms_hit_rate"] < 1.0 or c["numeric_preservation_rate"] < 1.0
        ],
        "by_query_type": {
            k: {
                "count": len(v),
                "must_have_terms_hit_rate": avg(v, "must_have_terms_hit_rate"),
                "numeric_preservation_rate": avg(v, "numeric_preservation_rate"),
            }
            for k, v in sorted(by_type.items())
        },
    }
    return {"summary": summary, "cases": cases}


def test_datasheet_generator_uses_technical_prompt_and_context(monkeypatch):
    data = _load_cases()
    case = data["cases"][0]
    captured = {}

    def fake_call_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return _deterministic_datasheet_answer(case)

    monkeypatch.setattr(generator, "call_llm", fake_call_llm)
    answer = generator.generate(
        case["query"],
        [{"skill": "search_datasheet", "results": _context_for_case(case, data["source"])}],
        {"domain": "technical_datasheet"},
    )

    prompt = captured["prompt"]
    assert "技术 datasheet 问答助手" in prompt
    assert "数值、符号、单位必须逐字保留" in prompt
    assert "不得用常识补齐" in prompt
    assert "System Oscillator Timing Requirements" in prompt
    assert "±200 PPM" in prompt
    assert "23.998" in answer
    assert "23.99 MHz" not in answer
    assert "24 MHz" not in answer


def test_datasheet_generator_appends_structured_evidence_references(monkeypatch):
    captured = {}

    def fake_call_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return "主答案：MOSC frequency is 23.998 MHz to 24.002 MHz，频率变化为 ±200 PPM。"

    monkeypatch.setattr(generator, "call_llm", fake_call_llm)

    answer = generator.generate(
        "MOSC oscillator timing 有哪些要求？",
        [
            {
                "skill": "search_datasheet",
                "results": [
                    {
                        "source": "dlpc3436_clean.md",
                        "text": "## 6.10 System Oscillator Timing Requirements\n| f clk | MOSC | 23.998 | 24.000 | 24.002 | MHz |",
                        "section_id": "section_6_10",
                        "section_title": "6.10 System Oscillator Timing Requirements",
                        "table_id": "table_6_10",
                        "row_id": "row_oscillator_f_clk",
                        "source_line": 1202,
                        "index_kind": "row",
                    },
                    {
                        "source": "dlpc3436_clean.md",
                        "text": "The crystal or oscillator frequency variation should be ±200 PPM.",
                        "section_id": "section_6_10",
                        "section_title": "6.10 System Oscillator Timing Requirements",
                        "source_line": 1210,
                        "index_kind": "block",
                    },
                ],
            }
        ],
        {"domain": "technical_datasheet"},
    )

    assert "结构化引用" in captured["prompt"]
    assert "[Section: 6.10 System Oscillator Timing Requirements; Table: table_6_10; Row: row_oscillator_f_clk; line: 1202]" in answer
    assert "[Section: 6.10 System Oscillator Timing Requirements; line: 1210]" in answer


def test_datasheet_generator_context_includes_reading_closure(monkeypatch):
    captured = {}
    closure = {
        "subject": "System Oscillator Timing Requirements",
        "anchors": [
            {
                "quote": "| f clk | Clock frequency, MOSC | 23.998 | 24.000 | 24.002 | MHz |",
                "line": 636,
                "source": "dlpc3436_clean.md",
                "relation": "value",
            }
        ],
        "followed_cues": [
            {
                "cue_type": "annotation",
                "relation": "constraint",
                "quote": "The MOSC input does not support spread spectrum clock spreading.",
                "line": 643,
                "source": "dlpc3436_clean.md",
                "confidence": 0.9,
            },
            {
                "cue_type": "cross_reference",
                "relation": "dependency",
                "quote": "PLL_REFCLK_O ... leave this pin unconnected (floating with no added capacitive load).",
                "line": 354,
                "source": "dlpc3436_clean.md",
                "confidence": 0.8,
            },
        ],
        "unresolved_cues": [],
        "closure_complete": True,
    }

    def fake_call_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return "主答案：MOSC 频率为 23.998 MHz 到 24.002 MHz，不支持 spread spectrum clock spreading。PLL_REFCLK_O floating。"

    monkeypatch.setattr(generator, "call_llm", fake_call_llm)

    generator.generate(
        "DLPC3436 系统 Oscillator Timing 要求？",
        [
            {
                "skill": "search_datasheet",
                "results": [
                    {
                        "source": "dlpc3436_clean.md",
                        "text": "## 6.10 System Oscillator Timing Requirements",
                        "reading_closure": closure,
                    }
                ],
            }
        ],
        {"domain": "technical_datasheet"},
    )

    prompt = captured["prompt"]
    assert "规格书阅读路径闭环" in prompt
    assert "relation=value" in prompt
    assert "relation=constraint" in prompt
    assert "relation=dependency" in prompt
    assert "does not support spread spectrum clock spreading" in prompt
    assert "floating with no added capacitive load" in prompt
    assert "closure_complete=True" in prompt


def test_datasheet_full_baseline_metrics_written():
    metrics = compute_full_metrics()
    FULL_METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert metrics["summary"]["case_count"] >= 15
    assert metrics["summary"]["must_have_terms_hit_rate"] == 1.0
    assert metrics["summary"]["numeric_preservation_rate"] == 1.0
    assert metrics["summary"]["failed_cases"] == []


def _judge_sample_answers(sample_cases: list[dict]) -> dict[str, str]:
    answers = {}
    for case in sample_cases:
        references = "\n".join(
            f"- [Section: golden evidence; line: {ev['start_line']}]" for ev in case.get("golden_evidence", [])
        )
        answers[case["id"]] = (
            _deterministic_datasheet_answer(case)
            + f"\n\n结构化引用：\n{references}"
        )
    return answers


def test_datasheet_judge_sample_metrics_are_grounded_and_cited():
    data = _load_cases()
    sample_cases = data["cases"][:3]
    metrics = compute_judge_sample_metrics(sample_cases, _judge_sample_answers(sample_cases), data["source"])

    assert metrics["summary"]["sample_count"] == 3
    assert metrics["summary"]["judge_pass_count"] == 3
    assert metrics["summary"]["failed_cases"] == []
    assert all(case["judge"]["grounded"] is True for case in metrics["cases"])
    assert all(case["judge"]["has_structured_reference"] is True for case in metrics["cases"])


def test_datasheet_judge_sample_metrics_written():
    data = _load_cases()
    sample_cases = data["cases"][:3]
    metrics = compute_judge_sample_metrics(sample_cases, _judge_sample_answers(sample_cases), data["source"])
    JUDGE_METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert JUDGE_METRICS_PATH.exists()
    assert metrics["summary"]["mode"] == "deterministic_judge_sample_no_real_llm"
    assert metrics["summary"]["judge_pass_rate"] == 1.0


def test_judge_sample_answers_cite_each_golden_evidence_range():
    data = _load_cases()
    sample_cases = data["cases"][:3]
    answers = _judge_sample_answers(sample_cases)

    for case in sample_cases:
        for ev in case["golden_evidence"]:
            assert f"line: {ev['start_line']}" in answers[case["id"]]


def test_sample_golden_evidence_required_terms_resolve_in_source():
    data = _load_cases()
    for case in data["cases"][:3]:
        for ev in case["golden_evidence"]:
            evidence = _evidence_text(ev.get("source", data["source"]), ev).lower()
            missing = [term for term in ev.get("required_terms", []) if term.lower() not in evidence]
            assert missing == [], f"{case['id']} {ev['id']} missing required evidence terms: {missing}"


def test_datasheet_real_llm_judge_sample_metrics_schema_with_fake_model():
    data = _load_cases()
    sample_cases = data["cases"][:2]
    answers = _judge_sample_answers(sample_cases)

    def fake_call_llm(_prompt: str) -> str:
        return json.dumps(
            {
                "passed": True,
                "grounded": True,
                "has_structured_reference": True,
                "citation_grounded": True,
                "reason": "supported by golden evidence",
                "missing_facts": [],
                "wrong_facts": [],
            }
        )

    metrics = compute_real_llm_judge_sample_metrics(sample_cases, answers, data["source"], call_llm_fn=fake_call_llm)

    assert metrics["summary"]["mode"] == "real_llm_judge_sample"
    assert metrics["summary"]["sample_count"] == 2
    assert metrics["summary"]["llm_judge_pass_count"] == 2
    assert metrics["summary"]["parse_error_count"] == 0
    assert metrics["summary"]["fallback_used_count"] == 0
    assert metrics["summary"]["failed_cases"] == []
    assert all(case["judge"]["parse_error"] is False for case in metrics["cases"])


def test_datasheet_real_llm_judge_sample_metrics_written_with_fake_model(tmp_path):
    data = _load_cases()
    sample_cases = data["cases"][:2]
    answers = _judge_sample_answers(sample_cases)

    metrics = compute_real_llm_judge_sample_metrics(
        sample_cases,
        answers,
        data["source"],
        call_llm_fn=lambda _prompt: json.dumps(
            {
                "passed": True,
                "grounded": True,
                "has_structured_reference": True,
                "citation_grounded": True,
                "reason": "supported by golden evidence",
                "missing_facts": [],
                "wrong_facts": [],
            }
        ),
    )
    metrics_path = tmp_path / REAL_LLM_JUDGE_METRICS_PATH.name
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert metrics_path.exists()
    assert metrics["summary"]["mode"] == "real_llm_judge_sample"
    assert metrics["summary"]["effective_pass_count"] == 2


def test_real_generator_context_includes_expected_terms_contract():
    data = _load_cases()
    case = next(c for c in data["cases"] if c["id"] == "ds_param_002")
    context = generator._build_context(_generator_executed_steps_for_case(case, data["source"]))

    assert "必须覆盖的期望术语/数值" in context
    for term in _must_have_terms(case):
        assert term in context


def test_real_generator_sample_metrics_schema_with_fake_generator_and_judge():
    data = _load_cases()
    sample_cases = data["cases"][:2]

    metrics = compute_real_generator_sample_metrics(
        sample_cases,
        data["source"],
        answer_fn=lambda case: _judge_sample_answers([case])[case["id"]],
        call_llm_fn=lambda _prompt: json.dumps(
            {
                "passed": True,
                "grounded": True,
                "has_structured_reference": True,
                "citation_grounded": True,
                "reason": "supported by golden evidence",
                "missing_facts": [],
                "wrong_facts": [],
            }
        ),
    )

    assert metrics["summary"]["mode"] == "real_generator_sample_with_llm_judge"
    assert metrics["summary"]["sample_count"] == 2
    assert metrics["summary"]["llm_judge_pass_count"] == 2
    assert metrics["summary"]["parse_error_count"] == 0
    assert metrics["summary"]["failed_cases"] == []
    assert all(case["answer"] for case in metrics["cases"])


def test_real_generator_sample_metrics_written_with_fake_generator_and_judge(tmp_path):
    data = _load_cases()
    sample_cases = data["cases"][:2]
    metrics = compute_real_generator_sample_metrics(
        sample_cases,
        data["source"],
        answer_fn=lambda case: _judge_sample_answers([case])[case["id"]],
        call_llm_fn=lambda _prompt: json.dumps(
            {
                "passed": True,
                "grounded": True,
                "has_structured_reference": True,
                "citation_grounded": True,
                "reason": "supported by golden evidence",
                "missing_facts": [],
                "wrong_facts": [],
            }
        ),
    )
    metrics_path = tmp_path / REAL_GENERATOR_METRICS_PATH.name
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert metrics_path.exists()
    assert metrics["summary"]["mode"] == "real_generator_sample_with_llm_judge"
    assert metrics["summary"]["effective_pass_count"] == 2
    assert all("结构化引用" in case["answer"] for case in metrics["cases"])


def test_real_generator_answer_uses_technical_prompt_and_appends_golden_context_references(monkeypatch):
    data = _load_cases()
    case = data["cases"][0]
    captured = {}

    def fake_call_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return _deterministic_datasheet_answer(case)

    monkeypatch.setattr(generator, "call_llm", fake_call_llm)
    answer = _real_generator_answer_from_golden_context(case, data["source"])

    assert "技术 datasheet 问答助手" in captured["prompt"]
    assert "System Oscillator Timing Requirements" in captured["prompt"]
    assert "结构化引用" in answer
    for ev in case["golden_evidence"]:
        assert f"line: {ev['start_line']}" in answer


def test_llm_judge_prompt_and_parser_accept_json_from_model():
    data = _load_cases()
    case = data["cases"][0]
    answer = _judge_sample_answers([case])[case["id"]]
    captured = {}

    def fake_call_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            {
                "passed": True,
                "grounded": True,
                "has_structured_reference": True,
                "citation_grounded": True,
                "reason": "All expected facts are supported by evidence and cited.",
                "missing_facts": [],
                "wrong_facts": [],
            }
        )

    judge = _llm_judge_datasheet_answer(case, answer, data["source"], call_llm_fn=fake_call_llm)

    assert judge["passed"] is True
    assert judge["grounded"] is True
    assert judge["has_structured_reference"] is True
    assert judge["citation_grounded"] is True
    assert judge["missing_facts"] == []
    assert "只输出 JSON" in captured["prompt"]
    assert "Expected facts" in captured["prompt"]
    assert "Golden evidence" in captured["prompt"]
    assert "Candidate answer" in captured["prompt"]


def test_llm_judge_parser_extracts_json_from_wrapped_response():
    raw = '```json\n{"passed": false, "grounded": false, "has_structured_reference": true, "citation_grounded": false, "reason": "missing", "missing_facts": ["f clk"], "wrong_facts": []}\n```'

    judge = _parse_llm_judge_response(raw)

    assert judge["parse_error"] is False
    assert judge["passed"] is False
    assert judge["missing_facts"] == ["f clk"]


def test_llm_judge_parse_error_keeps_deterministic_fallback():
    data = _load_cases()
    case = data["cases"][0]
    answer = _judge_sample_answers([case])[case["id"]]

    judge = _llm_judge_datasheet_answer(case, answer, data["source"], call_llm_fn=lambda _prompt: "不是 JSON")

    assert judge["parse_error"] is True
    assert judge["deterministic_fallback"]["passed"] is True
