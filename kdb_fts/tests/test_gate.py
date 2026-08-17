import json

import pytest

from kdb_fts import gate


def _payload(**over):
    base = {
        "topic": "investment",
        "signal": 0.8,
        "extract_ideas": True,
        "extract_lessons": False,
        "confidence": 0.9,
        "rationale": "specific thesis with valuation anchor",
    }
    base.update(over)
    return json.dumps(base)


@pytest.mark.parametrize("topic", list(gate.TOPICS))
def test_every_topic_label_roundtrips(topic):
    v = gate.parse_verdict(_payload(topic=topic))
    assert v.topic == topic
    assert v.raw_topic == topic


@pytest.mark.parametrize("topic", list(gate.TOPICS))
@pytest.mark.parametrize("ideas,lessons", [(True, True), (True, False),
                                           (False, True), (False, False)])
def test_all_topic_x_eligibility_combinations(topic, ideas, lessons):
    """§9 Phase-1 fixture matrix: 6 topics × 4 eligibility combos, all parsed."""
    v = gate.parse_verdict(_payload(topic=topic, extract_ideas=ideas,
                                    extract_lessons=lessons))
    assert v.topic == topic
    assert v.extract_ideas is ideas and v.extract_lessons is lessons


def test_unknown_label_fails_closed():
    v = gate.parse_verdict(_payload(topic="sports", extract_ideas=True,
                                    extract_lessons=True))
    assert v.topic == "other"
    assert v.extract_ideas is False and v.extract_lessons is False
    assert v.raw_topic == "sports"  # raw preserved for the journal


def test_invalid_json_raises():
    with pytest.raises(gate.GateParseError):
        gate.parse_verdict("not json {")
    with pytest.raises(gate.GateParseError):
        gate.parse_verdict(json.dumps([1, 2, 3]))  # not an object


def test_salvage_coercion():
    # string booleans fail closed to False; out-of-range signal clamps;
    # missing confidence → None; missing rationale → "".
    v = gate.parse_verdict(_payload(extract_ideas="true", signal=1.7,
                                    confidence=None, rationale=None))
    assert v.extract_ideas is False
    assert v.signal == 1.0
    assert v.confidence is None
    assert v.rationale == ""
    v2 = gate.parse_verdict(_payload(signal=-0.5))
    assert v2.signal == 0.0


def test_unparseable_signal_defaults_zero():
    v = gate.parse_verdict(_payload(signal="high"))
    assert v.signal == 0.0


def test_build_prompt_truncates_body_at_word_cap():
    body = " ".join(f"w{i}" for i in range(gate.MAX_BODY_WORDS + 500))
    p = gate.build_prompt(title="T", author="A", published_date="2026-01-01",
                          body=body)
    assert f"w{gate.MAX_BODY_WORDS - 1}" in p
    assert f"w{gate.MAX_BODY_WORDS}" not in p
    assert "T" in p and "A" in p and "2026-01-01" in p


def test_prompt_version_matches_filename():
    from pathlib import Path

    prompts = Path(__file__).parents[1] / "prompts"
    assert (prompts / f"{gate.GATE_PROMPT_VERSION}.md").exists()
