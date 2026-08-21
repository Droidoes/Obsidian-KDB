"""extract: prompt build + pure parse/salvage (no LLM, no DB)."""
from __future__ import annotations

import json

import pytest

from kdb_fts import extract


def _payload(**over):
    base = {
        "ideas": [{
            "company": "Alibaba", "stance": "long", "thesis": "Cloud re-acceleration",
            "evidence": {"paragraph_id": "p0001", "head_anchor": "Cloud revenue", "tail_anchor": "grew"},
        }],
        "lessons": [],
        "downgraded": False,
    }
    base.update(over)
    return json.dumps(base)


def test_political_fixture_zero_mentions():
    r = extract.parse_extraction(json.dumps({"ideas": [], "lessons": [], "downgraded": True}))
    assert r.mentions == [] and r.cards == [] and r.downgraded is True


def test_thesis_fixture_one_mention_with_span():
    r = extract.parse_extraction(_payload())
    assert len(r.mentions) == 1
    m = r.mentions[0]
    assert m.company == "Alibaba" and m.stance == "long"
    assert m.evidence["head_anchor"] == "Cloud revenue"


def test_unknown_stance_drops_mention():
    r = extract.parse_extraction(_payload(ideas=[{
        "company": "X", "stance": "yolo", "thesis": "t",
        "evidence": {"paragraph_id": "p0001", "head_anchor": "a", "tail_anchor": "b"}}]))
    assert r.mentions == []


def test_invalid_json_raises():
    with pytest.raises(extract.ExtractParseError):
        extract.parse_extraction("not json {")


def test_build_prompt_numbers_paragraphs_and_no_truncation():
    paras = [(f"p{i:04d}", "word " * 100) for i in range(1, 10)]  # 900 words total
    p = extract.build_prompt(title="T", author="A", published_date="d", paragraphs=paras)
    assert "[p0001]" in p and "[p0009]" in p and "word" in p


def test_prompt_version_matches_filename():
    from pathlib import Path
    prompts = Path(__file__).parents[1] / "prompts"
    assert (prompts / f"{extract.EXTRACT_PROMPT_VERSION}.j2").exists()


# --- runner tests (Task 5) ---------------------------------------------------

from common.call_model import ModelResponse

from kdb_fts import ledger


def _fake_call_factory(payloads):
    """payloads: {title_suffix: response_text}. call_fn(req) picks by the Title line."""
    calls = []

    def _call(req):
        calls.append(req)
        for key, text in payloads.items():
            if f"Title: {key}" in req.prompt:
                return ModelResponse(text=text, input_tokens=100, output_tokens=20,
                                     latency_ms=5, model=req.model, provider=req.provider)
        raise AssertionError(f"no payload for prompt: {req.prompt[:200]}")

    _call.calls = calls
    return _call


def _seed_direct(conn, gid="a1", title="A1"):
    conn.execute(
        "INSERT INTO articles (article_id, path, content_sha256, title, raw_author,"
        " published_date, source_url, content_kind, word_count, cleanliness,"
        " first_seen_run, last_seen_run) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (gid, "p", "h", title, "x", None, None, "article", 100, "ok", "r1", "r1"))
    conn.execute(
        "INSERT INTO paragraphs (article_id, paragraph_id, body) VALUES (?,?,?)",
        (gid, "p0001", "body text here"))
    conn.commit()


def test_chunk_paragraphs_paragraph_atomic_and_long_own_chunk():
    paras = [(f"p{i:04d}", "word " * 2000) for i in range(1, 5)]   # 2000 words each
    chunks = extract.chunk_paragraphs(paras)
    assert [len(c) for c in chunks] == [3, 1]  # 3×2000=6000 then the 4th
    big = [("p0001", "word " * 9000)]  # > CHUNK_TARGET → its own chunk, never split
    assert [len(c) for c in extract.chunk_paragraphs(big)] == [1]


def test_run_extract_dry_run_commits_nothing(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_direct(conn)
    ledger.insert_gate_verdict(conn, article_id="a1", run_id="r1", topic="investment",
                               signal=0.5, extract_ideas=True, extract_lessons=False,
                               exploration=False, confidence=None, rationale="",
                               model="m", prompt_version="gate_v1",
                               input_tokens=0, output_tokens=0)
    fake = _fake_call_factory({"A1": json.dumps({"ideas": [], "lessons": [], "downgraded": True})})
    stats = extract.run_extract(conn, state_root=tmp_path, run_id="r2", dry_run=True, call_fn=fake)
    assert stats["extracted"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 0


def test_run_extract_resume_skips_extracted_article(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_direct(conn)
    ledger.insert_gate_verdict(conn, article_id="a1", run_id="r1", topic="investment",
                               signal=0.5, extract_ideas=True, extract_lessons=False,
                               exploration=False, confidence=None, rationale="",
                               model="m", prompt_version="gate_v1", input_tokens=0, output_tokens=0)
    payload = json.dumps({"ideas": [{"company": "X", "stance": "long", "thesis": "buy",
        "evidence": {"paragraph_id": "p0001", "head_anchor": "body", "tail_anchor": "here"}}],
        "lessons": [], "downgraded": False})
    fake = _fake_call_factory({"A1": payload})
    s1 = extract.run_extract(conn, state_root=tmp_path, run_id="r2", call_fn=fake)
    assert s1["mentions"] == 1
    s2 = extract.run_extract(conn, state_root=tmp_path, run_id="r3", call_fn=fake)
    assert s2["skipped"] == 1 and s2["mentions"] == 0
    # the span was source-sliced (head..tail) and proven at insert
    assert conn.execute("SELECT exact_quote FROM evidence_spans").fetchone()[0] == "body text here"
