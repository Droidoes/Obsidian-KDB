"""Tests for the #114 recovery-first parse stage in compile_one.

Contract under test (spec §3.3):
  * Recovery runs FIRST on every model response (unwrap + strict-eval +
    5-step selection ladder in compiler.response_recovery). Callers branch
    on ``result.recovered``, never on ``parsed is None`` (JSON null is a
    recovered value).
  * stop_reason in ("max_tokens", "length") is terminal ONLY after recovery
    fails — a truncated-flagged response may still carry a complete
    document (stop_reason is carrier metadata, not proof of absence).
  * extract_ok is non-gating telemetry; failure_stage="extract" is never
    emitted.
  * Winning-attempt semantics: boundary_recovered + discard counts reset
    per attempt and are assigned directly from the attempt's RecoveryResult.
  * Coercion guarded: coerce_slugs_and_propagate only runs on dict payloads.

Harness mirrors compiler/tests/test_compiler.py (imported helpers + the
same monkeypatched ``compiler.compiler.call_model_with_retry`` seam).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from common.call_model import ModelResponse

from compiler.tests.test_compiler import (
    _ctx,
    _failure_fields,
    _good_response,
    _job,
    _resp_stats_files,
    _write_raw,
    _write_vault,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'pass2_recovery'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_text())
RECOVERABLE = [e for e in MANIFEST if e['recoverable']]
INCOMPLETE = [e for e in MANIFEST if not e['recoverable']]

SOURCE_A = "KDB/raw/alpha.md"


@pytest.fixture(autouse=True)
def _clear_prompt_caches() -> None:
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _model_response(text: str, **kwargs) -> ModelResponse:
    return ModelResponse(
        text=text,
        input_tokens=100,
        output_tokens=50,
        latency_ms=10,
        model="claude-opus-4-7",
        provider="anthropic",
        attempts=1,
        **kwargs,
    )


def _compile(vault, state_root, ctx, source_id=SOURCE_A):
    return compiler.compile_one(
        _job(vault, source_id),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )


def _single_record(state_root: Path, run_id: str) -> dict:
    files = _resp_stats_files(state_root, run_id)
    assert len(files) == 1, files
    return json.loads(files[0].read_text(encoding="utf-8"))


# ---------- fixture manifest shape ----------

def test_manifest_shape():
    assert len(MANIFEST) == 20
    assert len(RECOVERABLE) == 19
    assert len(INCOMPLETE) == 1
    assert 'Negative cash-conversion' in INCOMPLETE[0]['source_id']
    assert sum(1 for e in MANIFEST if not e['extract_ok']) == 2
    # T1.7: exactly one retained legacy-shape negative (schema rejection)
    assert [e["file"] for e in MANIFEST if e.get("legacy_negative")] == ["19.txt"]


# 1. All 19 positives: 18 migrated new-shape fixtures decode schema+semantic
#    clean; the one retained legacy-shape negative decodes to schema REJECTION.
def test_all_19_fixtures_decode_schema_and_semantic_clean():
    from compiler import validate_source_response
    from compiler.response_recovery import recover_json_response
    from compiler.summary_slug import expected_summary_slug
    for e in RECOVERABLE:
        r = recover_json_response((FIXTURES / e['file']).read_text())
        assert r.recovered, e['source_id']
        errs = validate_source_response.validate(r.parsed)
        if e.get("legacy_negative"):
            # T1.7 retained legacy response: carrier recovers, the new
            # schema rejects the old shape (removed fields present).
            assert errs != [], f'{e["source_id"]}: legacy negative must fail schema'
            continue
        assert errs == [], f'{e["source_id"]}: {errs[:1]}'
        sem = validate_source_response.semantic_check(
            r.parsed,
            expected_summary_slug=expected_summary_slug(e["source_id"]))
        assert sem == [], f'{e["source_id"]}: {sem[:1]}'
        assert r.boundary_recovered, e['source_id']
        assert r.tail_discarded_chars == e['tail_discarded_chars']
        assert r.extract_ok == e['extract_ok']


# 2. The incomplete fixture fails recovery.
def test_incomplete_fixture_unrecoverable():
    from compiler.response_recovery import recover_json_response
    e = INCOMPLETE[0]
    r = recover_json_response((FIXTURES / e['file']).read_text())
    assert not r.recovered and r.error


# 3. compile_one e2e over the 18 migrated positives (spec §5 acceptance criterion).
@pytest.mark.parametrize("entry",
                         [e for e in RECOVERABLE if not e.get("legacy_negative")],
                         ids=[e["file"] for e in RECOVERABLE
                              if not e.get("legacy_negative")])
def test_compile_one_e2e_recovers_every_positive_fixture(
    entry: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each recoverable fixture compiles end-to-end: the source is fabricated
    at the manifest source_id (basename == payload source_name, required by
    the semantic echo check), the fake model returns the fixture text, and
    the persisted record carries the recovery telemetry of the winning
    (only) attempt: final_status="repaired", boundary_recovered=True, and
    prefix/tail counts + extract_ok matching the manifest."""
    source_id = entry["source_id"]
    vault = _write_vault(tmp_path)
    _write_raw(vault, source_id, f"source body for fixture {entry['file']}")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)
    text = (FIXTURES / entry["file"]).read_text(encoding="utf-8")

    def fake(req):
        return _model_response(text)

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, _, err = _compile(vault, state_root, ctx, source_id)

    assert err is None
    assert cs is not None
    assert cs.source_id == source_id

    rec = _single_record(state_root, ctx.run_id)
    assert rec["final_status"] == "repaired"
    assert rec["compile_attempts"] == 1
    assert rec["boundary_recovered"] is True
    assert rec["prefix_discarded_chars"] == entry["prefix_discarded_chars"]
    assert rec["tail_discarded_chars"] == entry["tail_discarded_chars"]
    assert rec["extract_ok"] == entry["extract_ok"]


def test_compile_one_e2e_legacy_negative_quarantines_at_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retained legacy-shape fixture recovers at the carrier level but
    fails the new schema (removed fields) → quarantine, no retry waste."""
    entry = [e for e in RECOVERABLE if e.get("legacy_negative")][0]
    source_id = entry["source_id"]
    vault = _write_vault(tmp_path)
    _write_raw(vault, source_id, "source body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)
    text = (FIXTURES / entry["file"]).read_text(encoding="utf-8")

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda req: _model_response(text),
    )

    cs, _, err = _compile(vault, state_root, ctx, source_id)

    assert cs is None
    assert "schema validation failed" in (err or "")
    rec = _single_record(state_root, ctx.run_id)
    assert rec["parse_ok"] is True          # carrier recovery worked
    assert rec["schema_ok"] is False        # new schema rejects the old shape
    assert rec["final_status"] == "quarantined"


# 4. Truncation composition: complete doc + stop_reason "length" → compiles.
def test_truncation_flagged_complete_document_compiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop_reason is carrier metadata, not proof of absence: a complete,
    valid document flagged 'length' recovers and compiles; the stop_reason
    is persisted on the record (token_overrun derived from it)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda req: _model_response(
            json.dumps(_good_response(SOURCE_A)), stop_reason="length"
        ),
    )

    cs, _, err = _compile(vault, state_root, ctx)

    assert err is None
    assert cs is not None
    rec = _single_record(state_root, ctx.run_id)
    assert rec["stop_reason"] == "length"
    assert rec["token_overrun"] is True
    assert rec["parse_ok"] is True
    assert rec["final_status"] == "clean"


# 5. Truncation terminal: truncated doc + "length" → failure_stage
#    "truncation", NO retry.
def test_truncated_unrecoverable_document_is_terminal_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery fails on a genuinely truncated document; only THEN does the
    stop_reason guard fire — terminal, no re-call (a re-call won't fit a
    bigger output)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    calls = {"n": 0}

    def fake(req):
        calls["n"] += 1
        return _model_response(
            '{"source_name": "alpha.md", "pages": [{"slug": "summary-f',
            stop_reason="length",
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, _, err = _compile(vault, state_root, ctx)

    assert cs is None
    assert err is not None
    assert "truncated at max_tokens=4096" in err
    assert "stop_reason='length'" in err
    assert calls["n"] == 1  # terminal — no retry

    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "truncation"
    assert etype == "TokenOverrun"
    rec = _single_record(state_root, ctx.run_id)
    assert rec["call_count"] == 1
    assert rec["parse_ok"] is False
    assert rec["final_status"] == "quarantined"


# 6. Two-attempt reset regression (Codex round-1 F1): attempt 1 boundary-
#    recovered but schema-invalid → retry; attempt 2 fully clean → success.
#    Modeled on test_compiler.py's
#    test_final_status_retried_when_attempt1_repaired_but_attempt2_is_clean.
def test_winning_attempt_resets_boundary_recovery_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Winning-attempt semantics: boundary_recovered + discard counts are
    per-attempt state, assigned directly (=) from the attempt's
    RecoveryResult. Attempt 1 carries tail junk (boundary-recovered) but its
    payload is missing the required summary_slug → schema gate rejects →
    retry. Attempt 2 is fully clean. The record must reflect attempt 2:
    boundary_recovered False, counts 0, final_status "retried" (NOT
    "retried-and-repaired")."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    bad = _good_response(SOURCE_A)
    del bad["pages"]  # schema-invalid (required field)
    attempt1_text = json.dumps(bad) + "\n} trailing-carrier-junk"
    attempt2_text = json.dumps(_good_response(SOURCE_A))
    seq = [attempt1_text, attempt2_text]

    def fake(req):
        return _model_response(seq.pop(0))

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, _, err = _compile(vault, state_root, ctx)

    assert cs is not None and err is None  # recovered on attempt 2

    rec = _single_record(state_root, ctx.run_id)
    assert rec["compile_attempts"] == 2
    # Attempt-1 boundary recovery must NOT stick to the winning attempt.
    assert rec["boundary_recovered"] is False
    assert rec["prefix_discarded_chars"] == 0
    assert rec["tail_discarded_chars"] == 0
    assert rec["syntax_repaired"] is False
    assert rec["slug_coerced"] is False
    assert rec["final_status"] == "retried"


# 7. Negative: a schema-wrong decodable prefix does not bypass content gates.
def test_decodable_wrong_prefix_still_hits_schema_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selection-first recovery accepts the FIRST complete document in the
    carrier — even when the real payload follows it. The schema gate is the
    content arbiter: the wrong (small) object fails schema, retries, and
    quarantines. Recovery selection never bypasses content gates."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    text = json.dumps({"source_name": "x"}) + "\n" + json.dumps(
        _good_response(SOURCE_A)
    )
    calls = {"n": 0}

    def fake(req):
        calls["n"] += 1
        return _model_response(text)

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, _, err = _compile(vault, state_root, ctx)

    assert cs is None
    assert err is not None
    assert "schema validation failed" in err
    assert calls["n"] == 2  # schema failure retries, then quarantines

    rec = _single_record(state_root, ctx.run_id)
    assert rec["parse_ok"] is True
    assert rec["boundary_recovered"] is True  # the prefix WAS selected
    assert rec["schema_ok"] is False
    assert rec["final_status"] == "quarantined"


# 8. Non-object payloads never crash (Codex round-2 F1+F3): top-level list,
#    scalar string, JSON null. Each recovers, fails the schema gate,
#    coercion is SKIPPED (no AttributeError), retries → quarantines.
@pytest.mark.parametrize(
    "payload_text",
    [
        '[{"slug": "summary-foo", "page_type": "summary"}]',
        '"just a string, no document here"',
        "null",
    ],
    ids=["top-level-list", "scalar-string", "json-null"],
)
def test_non_object_payloads_quarantine_without_crash(
    payload_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def fake(req):
        return _model_response(payload_text)

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, _, err = _compile(vault, state_root, ctx)

    assert cs is None
    assert err is not None
    assert "schema validation failed" in err  # schema-class, no crash

    rec = _single_record(state_root, ctx.run_id)
    # recovered=True (branch on .recovered — 'null' parses to None, which is
    # still a recovered value) → parse_ok True, then the schema gate rejects.
    assert rec["parse_ok"] is True
    assert rec["schema_ok"] is False
    assert rec["slug_coerced"] is False  # coercion skipped for non-dicts
    assert rec["final_status"] == "quarantined"


# 9. Incomplete fixture through compile_one (Codex round-3 F3): unrecoverable
#    on both attempts → 2 model calls, quarantined with parse-stage failure.
def test_incomplete_fixture_quarantines_after_exhausting_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    source_id = INCOMPLETE[0]["source_id"]
    _write_raw(vault, source_id, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    text = (FIXTURES / INCOMPLETE[0]["file"]).read_text(encoding="utf-8")
    calls = {"n": 0}

    def fake(req):
        calls["n"] += 1
        return _model_response(text)

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, _, err = _compile(vault, state_root, ctx, source_id)

    assert cs is None
    assert err is not None
    assert "invalid JSON" in err
    assert calls["n"] == 2  # normal stop → existing retry path, then quarantine

    stage, etype, _ = _failure_fields(state_root, ctx.run_id)
    assert stage == "parse"
    assert etype == "JSONDecodeError"
    rec = _single_record(state_root, ctx.run_id)
    assert rec["parse_ok"] is False
    assert rec["boundary_recovered"] is False
    assert rec["prefix_discarded_chars"] == 0
    assert rec["tail_discarded_chars"] == 0
    assert rec["final_status"] == "quarantined"
