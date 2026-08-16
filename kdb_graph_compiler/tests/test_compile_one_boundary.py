"""#119 boundary behavior end-to-end inside compile_one (mocked model)."""
import json
from unittest.mock import patch

import pytest

from common.types import CompileJob, ContextSnapshot
from kdb_graph_compiler.compiler import compile_one


class _Resp:
    def __init__(self, text):
        self.text = text
        self.provider = "test"
        self.model = "test-model"
        self.input_tokens = 1
        self.output_tokens = 1
        self.latency_ms = 1
        self.stop_reason = "stop"
        self.stop_reason_normalized = "complete"  # mirrors the #124 boundary
        self.attempts = 1


def _job(source_id):
    return CompileJob(source_id=source_id, abs_path="",
                      context_snapshot=ContextSnapshot(source_id=source_id),
                      source_text="body", frontmatter=None)


def _ctx(tmp_path):
    from common.run_context import RunContext
    return RunContext.new(dry_run=True, vault_root=tmp_path)


def _compile_with_payload(tmp_path, source_id, payload, captured):
    """One compile_one call with a mocked model + a resp-stats sink."""
    calls = {"n": 0}

    def fake_call(req):
        calls["n"] += 1
        return _Resp(payload)

    with patch("kdb_graph_compiler.compiler.call_model_with_retry", side_effect=fake_call):
        cs, notes, err = compile_one(
            _job(source_id), vault_root=tmp_path, state_root=tmp_path,
            ctx=_ctx(tmp_path), provider="test", model="test-model", max_tokens=1000,
            stats_record_sink=lambda rec, path: captured.setdefault("rec", rec))
    return cs, err, calls["n"]


def test_punctuation_deviant_summary_never_retries_never_quarantines(
        tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_RESP_STATS_CAPTURE_FULL", "1")  # parsed_json is capture-full-gated (llm_telemetry.py:196)
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/GraphRAG for Adaptive KB - Gemini3.1.md",
        json.dumps({"pages": [
            {"page_type": "summary",
             "slug": "summary-graphrag-for-adaptive-kb-gemini31",
             "title": "T", "body": "See [[graphrag]]."},
            {"page_type": "concept", "slug": "graphrag", "title": "G",
             "body": "G."},
        ]}), captured)
    assert err is None and n == 1  # NO retry
    assert "summary-graphrag-for-adaptive-kb-gemini3-1" in [p.slug for p in cs.pages]
    rec = captured["rec"]  # §3.5 truth table — sink-captured record
    assert rec.final_status == "clean"            # stamping is NOT a recovery
    assert rec.slug_coerced is False              # stamping/ignoring never set it
    assert rec.summary_identity_derived is True
    assert any(d["rule"] == "summary_slug_ignored"
               for d in rec.normalization_decisions)
    assert "gemini31" in json.dumps(rec.parsed_json)  # raw proposal preserved


def test_concept_coercion_sets_slug_coerced_and_repaired(tmp_path):
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "summary", "title": "T", "body": "See [[Foo--Bar]]."},
            {"page_type": "concept", "slug": "Foo--Bar", "title": "FB",
             "body": "FB."},
        ]}), captured)
    assert err is None and n == 1
    rec = captured["rec"]
    assert rec.slug_coerced is True and rec.final_status == "repaired"
    assert rec.summary_identity_derived is True


def test_zero_summaries_retries_once_then_typed_quarantine(tmp_path):
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "concept", "slug": "a", "title": "T", "body": "B."}]}),
        captured)
    assert err is not None and n == 2  # retriable once, then terminal
    rec = captured["rec"]
    assert rec.final_status == "quarantined"
    assert rec.failure_stage == "validate"
    assert rec.failure_exception_type == "ProposalReject:no_summary"


def test_partial_decisions_persist_on_terminal_reject(tmp_path):
    """Coercion decision recorded, THEN a derived-slug collision rejects —
    the terminal record must carry the partial decision list (F5)."""
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "summary", "title": "T", "body": "B."},
            {"page_type": "concept", "slug": "Summary--X", "title": "SX",
             "body": "SX."},  # coerces to "summary-x" → collides with derived
        ]}), captured)
    assert err is not None and n == 2
    rec = captured["rec"]
    assert rec.failure_exception_type == "ProposalReject:slug_collision"
    assert any(d["rule"] == "slug_form_coercion"
               for d in rec.normalization_decisions)


def test_uncoercible_slug_retries_once_then_typed_quarantine(tmp_path):
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md",
        json.dumps({"pages": [
            {"page_type": "summary", "title": "T", "body": "B."},
            {"page_type": "concept", "slug": "Foo Bar", "title": "FB",
             "body": "FB."},
        ]}), captured)
    assert err is not None and n == 2
    rec = captured["rec"]
    assert rec.failure_exception_type == "ProposalReject:uncoercible_slug"


def test_canonical_invariant_failure_captured(tmp_path, monkeypatch):
    captured = {}
    payload = json.dumps({"pages": [{"page_type": "summary", "title": "T",
                                     "body": "B."}]})
    import kdb_graph_compiler.proposal_bridge as pb
    monkeypatch.setattr(pb, "normalize_proposal",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            pb.CanonicalInvariantError("boom")))
    cs, err, n = _compile_with_payload(
        tmp_path, "KDB/raw/x.md", payload, captured)
    assert err is not None and n == 1  # NON-retriable — no retry
    rec = captured["rec"]
    assert rec.final_status == "quarantined"
    assert rec.failure_exception_type == "CanonicalInvariantError"
    # failed-response raw capture fires even without capture-full
    # (raw_response_text kept when failed_after_response, llm_telemetry.py:199-201)
    assert rec.raw_response_text == payload


_MATRIX = [
    # (case_id, source_id, payload, expected_calls, expected_failure_type | None,
    #  expected_final_status, expected_decision_rules)
    ("proposal-schema-violation", "KDB/raw/x.md",
     {"pages": [{"page_type": "concept", "title": "T", "body": "B."}]},  # missing required slug
     2, "StructuralInsufficiency", "quarantined", []),
    ("zero-summaries", "KDB/raw/x.md",
     {"pages": [{"page_type": "concept", "slug": "a", "title": "T", "body": "B."}]},
     2, "ProposalReject:no_summary", "quarantined", []),
    ("two-summaries", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "A", "body": "B."},
                {"page_type": "summary", "title": "C", "body": "B."}]},
     2, "ProposalReject:multiple_summaries", "quarantined", []),
    ("derived-slug-collision", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "T", "body": "B."},
                {"page_type": "concept", "slug": "summary-x", "title": "SX", "body": "B."}]},
     2, "ProposalReject:slug_collision", "quarantined", []),
    ("uncoercible-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "T", "body": "B."},
                {"page_type": "concept", "slug": "Foo Bar", "title": "FB", "body": "B."}]},
     2, "ProposalReject:uncoercible_slug", "quarantined", []),
    ("absent-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_identity_stamp"]),
    ("deviating-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "slug": "summary-x-deviant", "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_slug_ignored", "summary_identity_stamp"]),
    ("malformed-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "slug": "SUMMARY--X", "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_slug_ignored", "summary_identity_stamp"]),
    ("nonstring-summary-slug", "KDB/raw/x.md",
     {"pages": [{"page_type": "summary", "slug": {"x": 1}, "title": "T", "body": "B."}]},
     1, None, "clean", ["summary_slug_ignored", "summary_identity_stamp"]),
]


@pytest.mark.parametrize(
    "case_id, source_id, payload, calls, failure, final_status, rules",
    _MATRIX, ids=[m[0] for m in _MATRIX])
def test_retry_and_tolerance_matrix(tmp_path, case_id, source_id, payload,
                                    calls, failure, final_status, rules):
    """Codex PR3 F3: the full retry/tolerance matrix through compile_one —
    call count, terminal type, decisions, final_status, all asserted."""
    captured = {}
    cs, err, n = _compile_with_payload(
        tmp_path, source_id, json.dumps(payload), captured)
    rec = captured["rec"]
    assert n == calls, case_id
    assert rec.final_status == final_status, case_id
    if failure is None:
        assert err is None and cs is not None, case_id
        from kdb_graph_compiler.summary_slug import expected_summary_slug
        assert expected_summary_slug(source_id) in [p.slug for p in cs.pages], case_id
    else:
        assert err is not None, case_id
        assert rec.failure_exception_type == failure, case_id
    got_rules = [d["rule"] for d in (rec.normalization_decisions or [])]
    for rule in rules:
        assert rule in got_rules, (case_id, rule)


# --- decision-cap telemetry (Task 4.2 Step 2 injection, Codex PR5 F3): ---
# >50 decisions on BOTH the success path and the terminal-reject path —
# ≤50 located samples, TRUE total count, stable overflow digest.

_HEX = set("0123456789abcdef")


def test_decision_cap_success_path_samples_count_and_stable_digest(tmp_path):
    """62 decisions (1 coercion + 60 body rewrites + 1 stamp) → 50 samples,
    count 62, and an identical payload yields an identical overflow digest."""
    body = " ".join(["[[Foo--Bar]]"] * 60)
    payload = json.dumps({"pages": [
        {"page_type": "summary", "title": "T", "body": body},
        {"page_type": "concept", "slug": "Foo--Bar", "title": "FB",
         "body": "FB."},
    ]})
    cap1, cap2 = {}, {}
    cs, err, n = _compile_with_payload(tmp_path, "KDB/raw/x.md", payload, cap1)
    assert err is None and n == 1
    _compile_with_payload(tmp_path, "KDB/raw/x.md", payload, cap2)
    rec = cap1["rec"]
    assert len(rec.normalization_decisions) == 50
    assert rec.normalization_decision_count == 62
    sha = rec.normalization_decisions_overflow_sha256
    assert sha is not None and len(sha) == 64 and set(sha) <= _HEX
    assert sha == cap2["rec"].normalization_decisions_overflow_sha256


def test_decision_cap_terminal_reject_persists_capped_partials(tmp_path):
    """55 coercion decisions recorded BEFORE a slug-collision reject → the
    terminal record carries 50 samples, the true total 55, stable digest."""
    pages = [{"page_type": "summary", "title": "T", "body": "B."}]
    pages += [{"page_type": "concept", "slug": f"Coercible--Slug-{i}",
               "title": f"C{i}", "body": "B."} for i in range(55)]
    pages.append({"page_type": "concept", "slug": "coercible-slug-0",
                  "title": "C55", "body": "B."})  # collides post-coercion
    payload = json.dumps({"pages": pages})
    cap1, cap2 = {}, {}
    cs, err, n = _compile_with_payload(tmp_path, "KDB/raw/x.md", payload, cap1)
    assert err is not None and n == 2  # retriable once, then terminal
    _compile_with_payload(tmp_path, "KDB/raw/x.md", payload, cap2)
    rec = cap1["rec"]
    assert rec.failure_exception_type == "ProposalReject:slug_collision"
    assert len(rec.normalization_decisions) == 50
    assert rec.normalization_decision_count == 55
    sha = rec.normalization_decisions_overflow_sha256
    assert sha is not None and len(sha) == 64 and set(sha) <= _HEX
    assert sha == cap2["rec"].normalization_decisions_overflow_sha256
