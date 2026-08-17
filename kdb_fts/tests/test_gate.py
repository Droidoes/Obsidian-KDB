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


from common.call_model import ModelResponse

from kdb_fts import ledger


def _seed_articles(conn, tmp_path, n=6):
    """n ok-cleanliness articles a0..a(n-1), authored round-robin by a{i}%2."""
    from kdb_fts import intake

    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    for i in range(n):
        (raw / f"a{i}.md").write_text(
            f"---\ntitle: T{i}\nauthor: Au{i % 2}\ngmail_message_id: gid{i}\n---\n\n"
            + f"topic {i} " * 60, encoding="utf-8")
    intake.run_intake(conn, raw, "seed-run", state_root=tmp_path)


def _fake_call_factory(payloads):
    """payloads: dict article-title-suffix → response text. Returns a
    call_fn(req) that picks the payload by the title line in the prompt."""
    calls = []

    def _call(req):
        calls.append(req)
        for key, text in payloads.items():
            if f"Title: {key}" in req.prompt:
                return ModelResponse(text=text, input_tokens=100,
                                     output_tokens=20, latency_ms=5,
                                     model=req.model, provider=req.provider)
        raise AssertionError(f"no payload for prompt: {req.prompt[:200]}")

    _call.calls = calls
    return _call


def test_run_gate_happy_path_and_resume(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    payloads = {f"T{i}": json.dumps({
        "topic": "investment", "signal": 0.5 + i / 10,
        "extract_ideas": True, "extract_lessons": False,
        "confidence": 0.9, "rationale": f"r{i}"}) for i in range(4)}
    fake = _fake_call_factory(payloads)
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-1",
                          model_id="deepseek-v4-flash", call_fn=fake)
    assert stats["gated"] == 4 and stats["failed"] == 0
    assert stats["input_tokens"] == 400 and stats["output_tokens"] == 80
    assert stats["cost_usd"] > 0
    assert stats["by_topic"] == {"investment": 4}
    # 4 eligible (extract_ideas=true) → no ineligible → no exploration marks.
    assert stats["exploration_marked"] == 0
    rows = ledger.latest_verdicts(conn)
    assert len(rows) == 4 and rows[0]["model"] == "deepseek-v4-flash"
    assert rows[0]["prompt_version"] == gate.GATE_PROMPT_VERSION
    # journal written under runs/
    journal = (tmp_path / "runs" / "run-1" / "journal.jsonl")
    assert journal.exists() and "gated" in journal.read_text()
    # resume: second run with same model+prompt version gates nothing.
    stats2 = gate.run_gate(conn, state_root=tmp_path, run_id="run-2",
                           model_id="deepseek-v4-flash", call_fn=fake)
    assert stats2["gated"] == 0 and stats2["skipped"] == 4


def test_run_gate_retry_then_fail_closed(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    payloads = {"T0": "garbage{",  # invalid JSON both attempts
                "T1": json.dumps({"topic": "sports", "signal": 0.9,
                                  "extract_ideas": True, "extract_lessons": True,
                                  "confidence": 1.0, "rationale": "x"})}
    fake = _fake_call_factory(payloads)
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-1",
                          model_id="deepseek-v4-flash", call_fn=fake)
    assert stats["failed"] == 1 and stats["gated"] == 1
    rows = {r["article_id"]: r for r in ledger.latest_verdicts(conn)}
    assert len(rows) == 1  # the failed one left NO verdict row
    v = next(iter(rows.values()))
    assert v["topic"] == "other" and v["extract_ideas"] == 0  # fail-closed


def test_exploration_sample_marks_five_percent_min_ten(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=6)
    payloads = {f"T{i}": json.dumps({
        "topic": "geopolitics", "signal": 0.1,
        "extract_ideas": False, "extract_lessons": False,
        "confidence": 0.5, "rationale": "politics"}) for i in range(6)}
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-1",
                          model_id="deepseek-v4-flash",
                          call_fn=_fake_call_factory(payloads))
    # 6 ineligible → min-10 rule caps at population: all 6 marked.
    assert stats["exploration_marked"] == 6
    rows = ledger.latest_verdicts(conn)
    assert all(r["exploration"] == 1 for r in rows)


def test_dry_run_commits_nothing(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    payloads = {f"T{i}": json.dumps({
        "topic": "other", "signal": 0.2, "extract_ideas": False,
        "extract_lessons": False, "confidence": 0.5,
        "rationale": "x"}) for i in range(2)}
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-dry",
                          model_id="deepseek-v4-flash", dry_run=True,
                          call_fn=_fake_call_factory(payloads))
    assert stats["gated"] == 2  # calls happened
    assert ledger.latest_verdicts(conn) == []
    assert not (tmp_path / "runs" / "run-dry").exists()


def test_cli_gate_dry_run(tmp_path, monkeypatch, capsys):
    from kdb_fts import cli

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=1)
    conn.close()
    fake = _fake_call_factory({"T0": json.dumps({
        "topic": "other", "signal": 0.1, "extract_ideas": False,
        "extract_lessons": False, "confidence": 0.5, "rationale": "x"})})
    monkeypatch.setattr(gate, "call_model", fake)
    rc = cli.main(["gate", "--state", str(tmp_path), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "gated=1" in out
