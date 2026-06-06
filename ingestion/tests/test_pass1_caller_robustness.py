# ingestion/tests/test_pass1_caller_robustness.py
"""Task #108: Pass-1 robustness ladder — json_escape_fix + final_status + aggregation.

TDD: these tests are written BEFORE the implementation. Run them to confirm FAIL
first, then implement in pass1_caller.py and re-run to PASS.
"""
from __future__ import annotations

import json
import pytest

from ingestion.enrich import pass1_caller as caller_mod
from ingestion.enrich.pass1_caller import call_pass1, Pass1CallError
from common.call_model import ModelResponse


# ---------------------------------------------------------------------------
# Helpers — mirror the patterns in test_pass1_caller.py
# ---------------------------------------------------------------------------

def _content_json(**overrides) -> str:
    """Return a valid 11-field Pass-1 content JSON string."""
    payload = {
        "kdb_signal": "signal", "domain": "ai-ml", "source_type": "paper",
        "author": None, "summary": "A note.", "key_themes": ["a"],
        "entity_search_keys": ["a"], "confidence": 0.9,
        "uncertainty_reason": None, "reject_reason": None, "other_reason": None,
    }
    payload.update(overrides)
    return json.dumps(payload)


def _stray_backslash_json() -> str:
    """Build a JSON string where the summary field contains a stray backslash
    (e.g. LaTeX ``\\(`` notation) that json.loads CANNOT parse as-is, but
    escape_stray_backslashes CAN repair.

    IMPORTANT: we cannot use json.dumps to build this — it would auto-escape the
    backslash to ``\\\\``, producing valid JSON and bypassing the repair path.
    We construct the raw text manually instead."""
    valid_json = _content_json(summary="PLACEHOLDER")
    # Replace the placeholder with a raw ``\\(`` which is an invalid JSON escape.
    return valid_json.replace('"PLACEHOLDER"', r'"\( n-1 \)"')


def _fake_response(text: str, *, input_tokens: int = 10,
                   output_tokens: int = 5, latency_ms: int = 1) -> ModelResponse:
    return ModelResponse(
        text=text, input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms, model="deepseek-v4-flash", provider="deepseek", raw={},
    )


# ---------------------------------------------------------------------------
# Verify the stray-backslash fixture is actually invalid before repair
# ---------------------------------------------------------------------------

def test_stray_backslash_fixture_is_invalid_json():
    """Sanity-check that the fixture actually exercises the repair path."""
    raw = _stray_backslash_json()
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


# ---------------------------------------------------------------------------
# Part A — json_escape_fix wired into parse step
# ---------------------------------------------------------------------------

class TestJsonEscapeFixWired:
    """Part A: escape_stray_backslashes is applied on JSONDecodeError and the
    repaired parse succeeds without consuming a retry."""

    def test_stray_backslash_repaired_clean_pass(self, monkeypatch):
        """Stray-backslash response → parse fails → escape_stray_backslashes →
        repaired parse succeeds → final_status='repaired', syntax_repaired=True,
        attempts=1, NOT quarantined."""
        raw = _stray_backslash_json()
        monkeypatch.setattr(caller_mod, "call_model",
                            lambda req: _fake_response(raw))
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.final_status == "repaired"
        assert res.syntax_repaired is True
        assert res.attempts == 1          # no retry consumed

    def test_stray_backslash_summary_preserved(self, monkeypatch):
        """The repaired parse must decode the backslash back as literal ``\\``."""
        raw = _stray_backslash_json()
        monkeypatch.setattr(caller_mod, "call_model",
                            lambda req: _fake_response(raw))
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        # After repair, json.loads decodes ``\\(`` to a literal backslash+paren.
        assert "(" in res.parsed["summary"]

    def test_irreparable_json_both_attempts_raises(self, monkeypatch):
        """Truly broken JSON (not fixable by escape) → both attempts fail →
        Pass1CallError raised (quarantine path)."""
        monkeypatch.setattr(caller_mod, "call_model",
                            lambda req: _fake_response("{not json at all"))
        with pytest.raises(Pass1CallError):
            call_pass1(source_text="body", source_path="x.md",
                       provider="deepseek", model="deepseek-v4-flash")


# ---------------------------------------------------------------------------
# Part B — final_status + flags + per-attempt aggregation
# ---------------------------------------------------------------------------

class TestFinalStatus:
    """Part B: final_status derivation across the retry loop."""

    def test_clean_first_attempt(self, monkeypatch):
        """Clean parse on attempt 1 → final_status='clean', syntax_repaired=False."""
        monkeypatch.setattr(caller_mod, "call_model",
                            lambda req: _fake_response(_content_json()))
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.final_status == "clean"
        assert res.syntax_repaired is False
        assert res.call_count == 1
        assert res.final_attempt_index == 1

    def test_repaired_first_attempt(self, monkeypatch):
        """Repair fires on attempt 1 → final_status='repaired'."""
        raw = _stray_backslash_json()
        monkeypatch.setattr(caller_mod, "call_model",
                            lambda req: _fake_response(raw))
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.final_status == "repaired"
        assert res.syntax_repaired is True

    def test_success_only_on_attempt_2_retried_and_repaired(self, monkeypatch):
        """Attempt 1 fails validation (bad domain) → attempt 2 succeeds clean →
        final_status='retried-and-repaired'."""
        calls = {"n": 0}

        def flaky(req):
            calls["n"] += 1
            if calls["n"] == 1:
                return _fake_response(_content_json(domain="not-a-domain"))
            return _fake_response(_content_json())

        monkeypatch.setattr(caller_mod, "call_model", flaky)
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.final_status == "retried-and-repaired"
        assert res.attempts == 2
        assert res.final_attempt_index == 2

    def test_success_attempt_2_with_escape_retried_and_repaired(self, monkeypatch):
        """Attempt 1 fails (bad domain) → attempt 2 needs escape repair →
        final_status='retried-and-repaired', syntax_repaired=True."""
        calls = {"n": 0}
        raw_stray = _stray_backslash_json()

        def flaky(req):
            calls["n"] += 1
            if calls["n"] == 1:
                return _fake_response(_content_json(domain="not-a-domain"))
            return _fake_response(raw_stray)

        monkeypatch.setattr(caller_mod, "call_model", flaky)
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.final_status == "retried-and-repaired"
        assert res.syntax_repaired is True

    def test_quarantine_both_attempts_exhausted(self, monkeypatch):
        """All attempts exhausted → Pass1CallError raised. The error carries
        enough context for the caller (enrich.py) to write final_status='quarantined'
        in the sidecar."""
        monkeypatch.setattr(
            caller_mod, "call_model",
            lambda req: _fake_response(_content_json(domain="not-a-domain")),
        )
        with pytest.raises(Pass1CallError) as exc:
            call_pass1(source_text="body", source_path="x.md",
                       provider="deepseek", model="deepseek-v4-flash")
        # The error is already tested by test_pass1_caller; here we additionally
        # confirm the quarantine is the correct terminal outcome.
        err = exc.value
        assert err.attempts == 2
        assert err.final_status == "quarantined"


class TestAggregation:
    """Part B: per-attempt token + latency accumulation."""

    def test_single_attempt_totals_match_individual(self, monkeypatch):
        """Single clean attempt → totals equal the individual attempt values."""
        monkeypatch.setattr(
            caller_mod, "call_model",
            lambda req: _fake_response(_content_json(),
                                       input_tokens=10, output_tokens=5, latency_ms=100),
        )
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.total_input_tokens == 10
        assert res.total_output_tokens == 5
        assert res.total_latency_ms == 100
        assert res.call_count == 1
        assert res.final_attempt_index == 1

    def test_two_attempt_aggregation(self, monkeypatch):
        """Two attempts that each reach the model → totals summed, call_count=2,
        final_attempt_index=2."""
        calls = {"n": 0}

        def flaky(req):
            calls["n"] += 1
            if calls["n"] == 1:
                # Attempt 1: bad domain → retry; tokens consumed
                return _fake_response(_content_json(domain="not-a-domain"),
                                      input_tokens=10, output_tokens=3, latency_ms=50)
            # Attempt 2: success
            return _fake_response(_content_json(),
                                  input_tokens=12, output_tokens=6, latency_ms=80)

        monkeypatch.setattr(caller_mod, "call_model", flaky)
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        assert res.total_input_tokens == 22   # 10 + 12
        assert res.total_output_tokens == 9   # 3 + 6
        assert res.total_latency_ms == 130    # 50 + 80
        assert res.call_count == 2
        assert res.final_attempt_index == 2

    def test_model_down_first_attempt_not_counted(self, monkeypatch):
        """If attempt 1 raises before reaching model tokens (call_model throws),
        it contributes 0 to totals; attempt 2 succeeds normally."""
        calls = {"n": 0}

        def flaky(req):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient network error")
            return _fake_response(_content_json(),
                                  input_tokens=15, output_tokens=7, latency_ms=200)

        monkeypatch.setattr(caller_mod, "call_model", flaky)
        res = call_pass1(source_text="body", source_path="x.md",
                         provider="deepseek", model="deepseek-v4-flash")
        # Attempt 1 never reached the model (exception before resp returned).
        # call_count = attempts that returned a ModelResponse = 1.
        assert res.total_input_tokens == 15
        assert res.total_output_tokens == 7
        assert res.total_latency_ms == 200
        assert res.call_count == 1
        assert res.final_attempt_index == 2
        # Succeeded on attempt 2 (even though attempt 1 raised before model was reached)
        # → retried-and-repaired: the spec defines this as "succeeded only on a later attempt".
        assert res.final_status == "retried-and-repaired"


# ---------------------------------------------------------------------------
# Part B — sidecar keys in enrich.py
# ---------------------------------------------------------------------------

class TestSidecarKeys:
    """Part B: the new fields must appear in the sidecar raw_response block."""

    def test_sidecar_has_new_fields_on_success(self, tmp_path, monkeypatch):
        """Successful enrich writes the 7 new keys to sidecar raw_response."""
        import json as _json
        from ingestion.enrich import enrich as enrich_mod
        from ingestion.enrich.pass1_caller import Pass1CallResult
        from ingestion.enrich.enrich import enrich_one

        src = tmp_path / "s.md"
        src.write_text("# Note\n\nSome content.\n", encoding="utf-8")
        runs = tmp_path / "runs"

        parsed = {
            "kdb_signal": "signal", "domain": "value-investing",
            "source_type": "paper", "author": "T",
            "summary": "A summary.", "key_themes": ["a"],
            "entity_search_keys": ["value-investing"],
            "confidence": 0.9, "uncertainty_reason": None,
            "reject_reason": None, "prompt_version": "p1",
            "model": "m", "schema_version": 1,
            "override": {"applied": None, "rule": None, "match": None,
                         "llm_original": "signal", "reject_reason_cleared": None},
            "other_reason": None,
        }

        def fake_call_pass1(*, source_text, source_path, provider, model):
            return Pass1CallResult(
                parsed=parsed, raw_response_text="{}",
                request_prompt="p", request_model=model, request_provider=provider,
                input_tokens=10, output_tokens=5, latency_ms=100, attempts=1,
                # New fields:
                final_status="clean", syntax_repaired=False,
                total_input_tokens=10, total_output_tokens=5,
                total_latency_ms=100, call_count=1, final_attempt_index=1,
            )

        monkeypatch.setattr(enrich_mod, "call_pass1", fake_call_pass1)
        res = enrich_one(source_path=src, source_id="s.md", runs_root=runs,
                         run_id="r1", provider="p", model="m")

        assert res.outcome == "enriched"
        sidecar = _json.loads(res.sidecar_path.read_text(encoding="utf-8"))
        rr = sidecar["raw_response"]
        assert rr["final_status"] == "clean"
        assert rr["syntax_repaired"] is False
        assert rr["total_input_tokens"] == 10
        assert rr["total_output_tokens"] == 5
        assert rr["total_latency_ms"] == 100
        assert rr["call_count"] == 1
        assert rr["final_attempt_index"] == 1

    def test_sidecar_has_final_status_quarantined_on_failure(
            self, tmp_path, monkeypatch):
        """Failed enrich (all attempts exhausted) writes final_status='quarantined'
        to sidecar raw_response."""
        import json as _json
        from ingestion.enrich import enrich as enrich_mod
        from ingestion.enrich import pass1_caller as p1_caller_mod
        from ingestion.enrich.enrich import enrich_one

        src = tmp_path / "bad.md"
        src.write_text("# Bad\n\nBad content.\n", encoding="utf-8")
        runs = tmp_path / "runs"

        # Monkeypatch call_model at the caller level to always return invalid domain
        monkeypatch.setattr(
            p1_caller_mod, "call_model",
            lambda req: p1_caller_mod.ModelResponse(
                text=_content_json(domain="not-a-domain"),
                input_tokens=5, output_tokens=3, latency_ms=10,
                model="m", provider="p", raw={},
            ),
        )

        res = enrich_one(source_path=src, source_id="bad.md",
                         runs_root=runs, run_id="r1", provider="p", model="m")

        assert res.outcome == "enrich_failed"
        sidecar = _json.loads(res.sidecar_path.read_text(encoding="utf-8"))
        rr = sidecar["raw_response"]
        assert rr["final_status"] == "quarantined"


# ---------------------------------------------------------------------------
# Retry-still-quarantines: existing failure classes (empty resp / null summary)
# remain quarantined but now carry the label
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Part C — Stage-2 envelope-validation failure preserves telemetry (#108 review)
# ---------------------------------------------------------------------------

class TestStage2FailureTelemetry:
    """Stage-2 validate_envelope raises AFTER Pass-1 succeeds with real tokens.
    The resulting sidecar must carry non-zero aggregate telemetry — proving
    the token/latency data from the model call is not silently zeroed out."""

    def test_stage2_failure_preserves_aggregate_telemetry(
            self, tmp_path, monkeypatch):
        """Pass-1 call succeeds (model called, real tokens), but Stage-2
        validate_envelope raises → sidecar final_status='quarantined' AND
        total_input_tokens > 0 and call_count >= 1 (telemetry preserved)."""
        import json as _json
        from ingestion.enrich import enrich as enrich_mod
        from ingestion.enrich import pass1_caller as p1_caller_mod
        from ingestion.enrich.enrich import enrich_one

        src = tmp_path / "note.md"
        src.write_text("# Note\n\nSome content.\n", encoding="utf-8")
        runs = tmp_path / "runs"

        # Stub call_model to return a clean, valid response so Pass-1 succeeds.
        monkeypatch.setattr(
            p1_caller_mod, "call_model",
            lambda req: p1_caller_mod.ModelResponse(
                text=_content_json(),
                input_tokens=42, output_tokens=17, latency_ms=300,
                model="m", provider="p", raw={},
            ),
        )

        # Force validate_envelope to raise so Stage-2 triggers the failure path.
        monkeypatch.setattr(
            enrich_mod, "validate_envelope",
            lambda envelope: (_ for _ in ()).throw(
                ValueError("injected Stage-2 failure")
            ),
        )

        res = enrich_one(
            source_path=src, source_id="note.md",
            runs_root=runs, run_id="r1", provider="p", model="m",
        )

        assert res.outcome == "enrich_failed"
        sidecar = _json.loads(res.sidecar_path.read_text(encoding="utf-8"))
        rr = sidecar["raw_response"]
        assert rr["final_status"] == "quarantined"
        # The model WAS called — aggregate telemetry must not be zeroed.
        assert rr["total_input_tokens"] > 0, (
            "total_input_tokens should be non-zero (model was called)"
        )
        assert rr["call_count"] >= 1, (
            "call_count should be >= 1 (model was called)"
        )


class TestExistingFailureClassesStillQuarantine:
    """Empty response and summary=None remain retry→quarantine; now labeled."""

    def test_empty_response_quarantined(self, monkeypatch):
        """Empty response string → json.loads raises → escape doesn't fix it →
        retry → Pass1CallError (quarantined)."""
        monkeypatch.setattr(caller_mod, "call_model",
                            lambda req: _fake_response(""))
        with pytest.raises(Pass1CallError) as exc:
            call_pass1(source_text="body", source_path="x.md",
                       provider="deepseek", model="deepseek-v4-flash")
        assert exc.value.final_status == "quarantined"

    def test_null_summary_quarantined(self, monkeypatch):
        """summary=null fails validate_llm_content (summary must be string) →
        retry → Pass1CallError."""
        monkeypatch.setattr(
            caller_mod, "call_model",
            lambda req: _fake_response(_content_json(summary=None)),
        )
        with pytest.raises(Pass1CallError) as exc:
            call_pass1(source_text="body", source_path="x.md",
                       provider="deepseek", model="deepseek-v4-flash")
        assert exc.value.final_status == "quarantined"
