from pathlib import Path

from retriever import build_specification_reading_closure


SOURCE = Path(__file__).resolve().parents[1] / "knowledge_base" / "dlpc3436_clean.md"


def _quotes(closure):
    items = closure["anchors"] + closure["followed_cues"]
    return "\n".join(item["quote"] for item in items)


def _relations(closure):
    return {item["relation"] for item in closure["followed_cues"]}


def test_te53_reading_closure_follows_annotations_and_external_oscillator_pin_definitions():
    closure = build_specification_reading_closure(
        "DLPC3436 系统 Oscillator Timing 要求？",
        source_path=SOURCE,
    )

    assert closure["subject"]
    assert closure["closure_complete"] is True
    text = _quotes(closure)

    # Anchor: 6.10 timing table rows, values, units.
    for term in [
        "Clock frequency, MOSC",
        "23.998",
        "24.000",
        "24.002",
        "Cycle time, MOSC",
        "41.663",
        "41.667",
        "41.670",
        "Pulse duration",
        "40%",
        "50%",
        "Transition time",
        "10",
        "Long-term, peak-to-peak, period jitter",
        "2%",
    ]:
        assert term in text

    # Followed cue: annotation (1) adds accuracy and prohibition/constraint.
    assert "±200 PPM" in text
    assert "does not support spread spectrum clock spreading" in text

    # Followed cue: annotation (2) adds applicability condition.
    assert "Applies only when driven by an external digital oscillator" in text

    # Followed cue: external oscillator definition/pin dependency.
    assert "PLL_REFCLK_I" in text
    assert "use this pin as the oscillator input" in text
    assert "PLL_REFCLK_O" in text
    assert "leave this pin unconnected" in text
    assert "floating with no added capacitive load" in text

    relations = _relations(closure)
    assert "constraint" in relations
    assert "condition" in relations
    assert "dependency" in relations

    assert not closure["unresolved_cues"]
    assert all(item.get("line") for item in closure["anchors"] + closure["followed_cues"])


def test_reading_closure_follows_inline_note_and_split_section_reference():
    closure = build_specification_reading_closure(
        "TSTPT_5 外部 pullup 正常使用有什么限制？",
        source_path=SOURCE,
    )

    text = _quotes(closure)
    assert "TSTPT_5" in text
    assert "Note: An external pullup may put the DLPC3436 in a test mode" in text
    assert "7.3.8 for more information" in text
    assert "Test Point Support" in text
    assert "external pullups must be used to modify the default test configuration" in text
    assert "For normal use TSTPT\\_(7:3) should be left unconnected" in text

    cue_types = {item["cue_type"] for item in closure["followed_cues"]}
    relations = _relations(closure)
    assert "note" in cue_types
    assert "cross_reference" in cue_types
    assert "constraint" in relations
    assert "dependency" in relations
    assert not closure["unresolved_cues"]


def test_reading_closure_attaches_nearby_note_and_figure_caption_context():
    closure = build_specification_reading_closure(
        "Normal Park power down 后 SYSPWR 要保持多久？",
        source_path=SOURCE,
    )

    text = _quotes(closure)
    assert "System Power-Up and Power-Down Sequence" in text
    assert "Note  that  when  V DD  core  power  is  applied" in text
    assert "Figure 9-2. DLPC3436 Normal Power-Down" in text
    assert "It is recommended that SYSPWR not be turned off for 50 ms after PROJ\\_ON is deasserted" in text

    cue_types = {item["cue_type"] for item in closure["followed_cues"]}
    relations = _relations(closure)
    assert "note" in cue_types
    assert "figure" in cue_types
    assert "condition" in relations or "constraint" in relations
    assert not closure["unresolved_cues"]


def test_reading_closure_is_structured_not_plain_topk_chunks():
    closure = build_specification_reading_closure(
        "DLPC3436 系统 Oscillator Timing 要求？",
        source_path=SOURCE,
    )

    assert set(closure) >= {"subject", "anchors", "followed_cues", "unresolved_cues", "closure_complete"}
    assert closure["anchors"]
    assert closure["followed_cues"]
    for cue in closure["followed_cues"]:
        assert set(cue) >= {"cue_type", "relation", "quote", "line", "source", "confidence"}
        assert cue["quote"].strip()
        assert isinstance(cue["line"], int)
