from common.measurement import PassCallMeasurement, RunMeasurementHeader


def test_passcallmeasurement_fields():
    m = PassCallMeasurement(
        run_id="r1", source_id="KDB/raw/a.md", pass_="pass2",
        provider="deepseek", model="deepseek-v4-flash", prompt_version="2.0",
        final_status="clean", attempts=1, syntax_repaired=False, slug_coerced=False,
        token_overrun=False, total_input_tokens=100, total_output_tokens=50,
        total_latency_ms=1200, call_count=1, final_attempt_index=1, source_words=400,
        parse_ok=True, schema_ok=True, semantic_ok=True,
    )
    assert m.pass_ == "pass2" and m.final_status == "clean"


def test_runheader_fields():
    h = RunMeasurementHeader(
        run_id="r1", corpus_fingerprint="sha", pass1_prompt_version="1.1",
        pass2_prompt_version="2.0", scanned=36, to_compile=36, signal=29,
        noise=7, p1_attempted=36, p2_attempted=29)
    assert h.signal == 29


# ---------------------------------------------------------------------------
# from_pass2 adapter (Task #109 B1)
# ---------------------------------------------------------------------------

def _make_resp_stats_dict(**overrides) -> dict:
    """Build a dict mirroring RespStatsRecord.to_dict() with sensible defaults."""
    base = {
        # identity
        "run_id": "run-2026-06-05",
        "source_id": "KDB/raw/test-source.md",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        # single-attempt telemetry (legacy fields)
        "attempts": 2,
        "latency_ms": 800,
        "input_tokens": 1000,
        "output_tokens": 200,
        # prompt / response hashes (not mapped to PassCallMeasurement)
        "prompt_hash": "sha256:abc",
        "response_hash": "sha256:def",
        # well-formedness flags
        "extract_ok": True,
        "parse_ok": True,
        "schema_ok": True,
        "semantic_ok": True,
        # optional lists / objects
        "schema_errors": [],
        "semantic_errors": [],
        "parsed_summary": None,
        "parsed_json": None,
        "system_prompt": None,
        "user_prompt": None,
        "raw_response_text": None,
        "stop_reason": "end_turn",
        # repair-ladder flags
        "token_overrun": False,
        "source_words": 350,
        "failure_stage": None,
        "failure_exception_type": None,
        "failure_exception_message": None,
        "compile_attempts": 2,
        "syntax_repaired": False,
        "slug_coerced": True,
        "final_status": "retried-and-repaired",
        # #109 aggregate fields
        "total_input_tokens": 2100,
        "total_output_tokens": 450,
        "total_latency_ms": 1750,
        "call_count": 2,
        "final_attempt_index": 2,
    }
    base.update(overrides)
    return base


def test_from_pass2_full_record():
    """from_pass2 maps all fields from a fully-populated RespStatsRecord dict."""
    rec = _make_resp_stats_dict()
    m = PassCallMeasurement.from_pass2(rec)

    assert m.pass_ == "pass2"
    assert m.run_id == "run-2026-06-05"
    assert m.source_id == "KDB/raw/test-source.md"
    assert m.provider == "anthropic"
    assert m.model == "claude-sonnet-4-6"
    # prompt_version: RespStatsRecord has no prompt_version field → ""
    assert m.prompt_version == ""
    # repair-ladder flags
    assert m.final_status == "retried-and-repaired"
    assert m.syntax_repaired is False
    assert m.slug_coerced is True
    assert m.token_overrun is False
    # aggregate totals from new #109 fields
    assert m.total_input_tokens == 2100
    assert m.total_output_tokens == 450
    assert m.total_latency_ms == 1750
    assert m.call_count == 2
    assert m.final_attempt_index == 2
    # per-call fields
    assert m.attempts == 2
    assert m.source_words == 350
    assert m.parse_ok is True
    assert m.schema_ok is True
    assert m.semantic_ok is True


def test_from_pass2_back_compat_missing_aggregate_fields():
    """Older persisted records without #109 aggregate fields fall back to
    single-attempt values: total_* = per-attempt, call_count=1, final_attempt_index=1."""
    rec = _make_resp_stats_dict()
    # Remove the new aggregate fields to simulate an older record
    for key in ("total_input_tokens", "total_output_tokens", "total_latency_ms",
                "call_count", "final_attempt_index"):
        rec.pop(key)

    m = PassCallMeasurement.from_pass2(rec)

    assert m.total_input_tokens == rec["input_tokens"]    # fallback to single-attempt
    assert m.total_output_tokens == rec["output_tokens"]
    assert m.total_latency_ms == rec["latency_ms"]
    assert m.call_count == 1
    assert m.final_attempt_index == 1


def test_from_pass2_semantic_ok_none():
    """semantic_ok=False (falsy) is carried through correctly (not confused with None)."""
    rec = _make_resp_stats_dict(semantic_ok=False)
    m = PassCallMeasurement.from_pass2(rec)
    assert m.semantic_ok is False


def test_from_pass2_final_status_none():
    """final_status missing/None is normalised to empty string."""
    rec = _make_resp_stats_dict(final_status=None)
    m = PassCallMeasurement.from_pass2(rec)
    assert m.final_status == ""
