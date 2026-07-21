import json
from pathlib import Path

import pytest

from common.measurement import PassCallMeasurement, RunMeasurementHeader, load_run_measurements


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


def test_header_carries_release_version():
    from common.measurement import RunMeasurementHeader
    import dataclasses
    h = RunMeasurementHeader(
        run_id="r", corpus_fingerprint="cf", pass1_prompt_version="1",
        pass2_prompt_version="", scanned=1, to_compile=1, signal=1, noise=0,
        p1_attempted=1, p2_attempted=1, release_version="v0.5.5",
    )
    assert dataclasses.asdict(h)["release_version"] == "v0.5.5"


def test_header_release_version_defaults_empty():
    from common.measurement import RunMeasurementHeader
    h = RunMeasurementHeader(
        run_id="r", corpus_fingerprint="cf", pass1_prompt_version="1",
        pass2_prompt_version="", scanned=1, to_compile=1, signal=1, noise=0,
        p1_attempted=1, p2_attempted=1,
    )
    assert h.release_version == ""


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


def test_from_pass2_reads_boundary_recovered():
    """boundary_recovered=True (#114 parse-stage recovery) is carried through."""
    rec = {
        "run_id": "r", "source_id": "s", "provider": "p", "model": "m",
        "final_status": "repaired", "boundary_recovered": True,
    }
    m = PassCallMeasurement.from_pass2(rec)
    assert m.boundary_recovered is True


def test_from_pass2_old_record_defaults_false():
    """Pre-#114 record with no boundary_recovered key projects to False."""
    rec = {"run_id": "r", "source_id": "s", "provider": "p", "model": "m",
           "final_status": "clean"}  # pre-#114 record: key absent
    assert PassCallMeasurement.from_pass2(rec).boundary_recovered is False


# ---------------------------------------------------------------------------
# Fix 1 (#111 retry-telemetry): from_pass2 attempts = final_attempt_index ONLY
# (compile re-prompt count; SDK transient retries deliberately excluded).
# ---------------------------------------------------------------------------

def test_from_pass2_reprompt_only_recovery_attempts_reflects_reprompt_count():
    """A re-prompt-only recovery (schema/semantic retry, no in-place repair):
    model_response.attempts==1 (single model-API call per compile attempt),
    final_attempt_index==2 (compile loop succeeded on attempt 2).
    PassCallMeasurement.attempts must be 2, not 1."""
    # Simulate: compile loop attempt-1 fails schema, re-prompts; attempt-2 succeeds.
    # model-API call per compile attempt = 1 (no SDK transient retries).
    rec = _make_resp_stats_dict(
        attempts=1,            # model_response.attempts = 1 (one SDK call per compile attempt)
        final_attempt_index=2, # compile loop won on attempt 2
        final_status="retried",
        syntax_repaired=False,
        slug_coerced=False,
    )
    m = PassCallMeasurement.from_pass2(rec)
    assert m.attempts == 2  # final_attempt_index=2 = two compile re-prompts


def test_from_pass2_sdk_only_retry_excluded_from_attempts():
    """A clean first-pass compile that merely hit an SDK transient retry
    (429/5xx/network): model_response.attempts==2 (SDK retried the call once),
    but final_attempt_index==1 (compile won on the first re-prompt, no content
    recovery). PassCallMeasurement.attempts must be 1 so recovery_rate/retry_load
    do NOT count infrastructure flakiness as a content/model recovery.
    This is the whole point of Fix 1's correction (dropping max(...))."""
    rec = _make_resp_stats_dict(
        attempts=2,            # model_response.attempts = 2 (one SDK transient retry)
        final_attempt_index=1, # compile loop won on the first attempt — no re-prompt
        final_status="clean",
    )
    m = PassCallMeasurement.from_pass2(rec)
    assert m.attempts == 1  # SDK transient retry excluded; not a content recovery


def test_from_pass2_single_attempt_unchanged():
    """Single-attempt success: both model-API attempts and final_attempt_index are 1.
    attempts == 1 — no change in the common case."""
    rec = _make_resp_stats_dict(
        attempts=1,
        final_attempt_index=1,
        final_status="clean",
    )
    m = PassCallMeasurement.from_pass2(rec)
    assert m.attempts == 1


# ---------------------------------------------------------------------------
# from_pass1 adapter (Task #109 B1 §3)
# ---------------------------------------------------------------------------

def _make_sidecar_dict(**overrides) -> dict:
    """Build a dict mirroring a real Pass-1 sidecar (from enrich.py write paths).

    Mirrors the SidecarPayload layout from ingestion/enrich/replay_archive.py and
    the raw_response block constructed in ingestion/enrich/enrich.py (success path).
    parsed_envelope matches the Pass-1 envelope dict with prompt_version and model.
    """
    base = {
        "source_id": "KDB/raw/concepts/test-concept.md",
        "source_path": "/home/user/Obsidian/KDB/raw/concepts/test-concept.md",
        "source_content_hash": "sha256:abc123",
        "request": {
            "prompt": "<prompt text>",
            "model": "claude-sonnet-4-6",
            "provider": "anthropic",
        },
        "raw_response": {
            "body": '{"kdb_signal": "signal", "domain": "engineering"}',
            "input_tokens": 800,
            "output_tokens": 150,
            "latency_ms": 1100,
            "attempts": 1,
            # Task #108 repair-ladder telemetry
            "final_status": "clean",
            "syntax_repaired": False,
            "total_input_tokens": 800,
            "total_output_tokens": 150,
            "total_latency_ms": 1100,
            "call_count": 1,
            "final_attempt_index": 1,
        },
        "parsed_envelope": {
            "kdb_signal": "signal",
            "domain": "engineering",
            "source_type": "concept",
            "author": None,
            "summary": "A test concept.",
            "key_themes": ["testing"],
            "entity_search_keys": ["test-concept"],
            "confidence": 0.9,
            "uncertainty_reason": None,
            "reject_reason": None,
            "prompt_version": "2.1",
            "model": "claude-sonnet-4-6",
            "schema_version": "1.0",
            "override": {"applied": None},
            "other_reason": None,
        },
        "override": {"applied": None},
        "user_overrides_detected": [],
        "timestamp": "2026-06-05T10:00:00+08:00",
        "outcome": "enriched",
    }
    base.update(overrides)
    return base


def test_from_pass1_full_sidecar():
    """from_pass1 maps all fields from a fully-populated success-path sidecar."""
    sidecar = _make_sidecar_dict()
    m = PassCallMeasurement.from_pass1(sidecar, run_id="run-2026-06-05")

    assert m.pass_ == "pass1"
    assert m.run_id == "run-2026-06-05"
    assert m.source_id == "KDB/raw/concepts/test-concept.md"
    assert m.provider == "anthropic"
    assert m.model == "claude-sonnet-4-6"
    assert m.prompt_version == "2.1"
    # repair-ladder fields from raw_response
    assert m.final_status == "clean"
    assert m.syntax_repaired is False
    assert m.total_input_tokens == 800
    assert m.total_output_tokens == 150
    assert m.total_latency_ms == 1100
    assert m.call_count == 1
    assert m.final_attempt_index == 1
    # attempts: derived from call_count
    assert m.attempts == 1
    # Pass-1 fixed fields
    assert m.slug_coerced is False
    assert m.token_overrun is False
    assert m.source_words == 0
    assert m.semantic_ok is None
    # parse_ok / schema_ok: clean (not quarantined) → True
    assert m.parse_ok is True
    assert m.schema_ok is True


def test_from_pass1_quarantined_sidecar():
    """Quarantined sidecar (failure path): parsed_envelope is None, final_status='quarantined'.
    from_pass1 must not crash, and parse_ok/schema_ok must be False."""
    sidecar = _make_sidecar_dict()
    # Simulate the failure write path (_write_sidecar_failed):
    # parsed_envelope=None, final_status='quarantined'
    sidecar["parsed_envelope"] = None
    sidecar["outcome"] = "enrich_failed"
    sidecar["raw_response"]["final_status"] = "quarantined"
    sidecar["raw_response"]["call_count"] = 2
    sidecar["raw_response"]["final_attempt_index"] = 2

    m = PassCallMeasurement.from_pass1(sidecar, run_id="run-q")

    assert m.pass_ == "pass1"
    assert m.final_status == "quarantined"
    # parse_ok / schema_ok: quarantined → False
    assert m.parse_ok is False
    assert m.schema_ok is False
    # semantic_ok always None for Pass-1
    assert m.semantic_ok is None
    # prompt_version: no envelope → ""
    assert m.prompt_version == ""
    # provider/model still readable from request
    assert m.provider == "anthropic"
    assert m.model == "claude-sonnet-4-6"
    # attempts from call_count
    assert m.attempts == 2


def test_from_pass1_syntax_repaired():
    """syntax_repaired=True is carried through from raw_response."""
    sidecar = _make_sidecar_dict()
    sidecar["raw_response"]["syntax_repaired"] = True
    sidecar["raw_response"]["final_status"] = "repaired"

    m = PassCallMeasurement.from_pass1(sidecar, run_id="run-r")

    assert m.syntax_repaired is True
    assert m.final_status == "repaired"
    # repaired is not quarantined → parse/schema ok
    assert m.parse_ok is True
    assert m.schema_ok is True


def test_from_pass1_boundary_recovered_always_false():
    """Pass-1 has no parse-stage boundary recovery — always False."""
    sidecar = _make_sidecar_dict()
    m = PassCallMeasurement.from_pass1(sidecar, run_id="run-2026-06-05")
    assert m.boundary_recovered is False


# ---------------------------------------------------------------------------
# load_run_measurements (Task #109 B1 §3)
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _make_header_dict(run_id: str = "run-test") -> dict:
    return {
        "run_id": run_id,
        "corpus_fingerprint": "sha256:corpus",
        "pass1_prompt_version": "2.1",
        "pass2_prompt_version": "",
        "scanned": 10,
        "to_compile": 8,
        "signal": 6,
        "noise": 2,
        "p1_attempted": 8,
        "p2_attempted": 6,
    }


def test_load_run_measurements_returns_header_and_both_passes(tmp_path):
    """load_run_measurements reads the header + one Pass-1 sidecar + one Pass-2 record."""
    run_id = "run-test"
    run_dir = tmp_path / run_id

    # Write measurement_header.json
    _write_json(run_dir / "measurement_header.json", _make_header_dict(run_id))

    # Write one Pass-1 sidecar under pass1/
    sidecar = _make_sidecar_dict()
    sidecar["source_id"] = "KDB/raw/alpha.md"
    _write_json(run_dir / "pass1" / "KDB__raw__alpha.json", sidecar)

    # Write one Pass-2 RespStatsRecord under pass2/
    p2_rec = _make_resp_stats_dict()
    p2_rec["run_id"] = run_id
    p2_rec["source_id"] = "KDB/raw/beta.md"
    _write_json(run_dir / "pass2" / "KDB__raw__beta.json", p2_rec)

    header, measurements = load_run_measurements(run_dir)

    assert isinstance(header, RunMeasurementHeader)
    assert header.run_id == run_id
    assert header.signal == 6

    assert len(measurements) == 2
    passes = {m.pass_ for m in measurements}
    assert passes == {"pass1", "pass2"}

    p1 = next(m for m in measurements if m.pass_ == "pass1")
    p2 = next(m for m in measurements if m.pass_ == "pass2")

    assert p1.source_id == "KDB/raw/alpha.md"
    assert p1.run_id == run_id
    assert p1.final_status == "clean"

    assert p2.source_id == "KDB/raw/beta.md"
    assert p2.run_id == run_id


def test_load_run_measurements_skips_enrich_skipped(tmp_path):
    """Sidecars with outcome='enrich_skipped' are excluded from measurements."""
    run_id = "run-skip"
    run_dir = tmp_path / run_id
    _write_json(run_dir / "measurement_header.json", _make_header_dict(run_id))

    # Write a normal sidecar under pass1/
    normal = _make_sidecar_dict()
    normal["source_id"] = "KDB/raw/normal.md"
    _write_json(run_dir / "pass1" / "KDB__raw__normal.json", normal)

    # Write a skipped sidecar (empty source, no real LLM call)
    skipped = _make_sidecar_dict()
    skipped["source_id"] = "KDB/raw/empty.md"
    skipped["outcome"] = "enrich_skipped"
    skipped["raw_response"]["call_count"] = 0
    _write_json(run_dir / "pass1" / "KDB__raw__empty.json", skipped)

    _, measurements = load_run_measurements(run_dir)

    source_ids = {m.source_id for m in measurements}
    assert "KDB/raw/normal.md" in source_ids
    assert "KDB/raw/empty.md" not in source_ids
    assert len(measurements) == 1


def test_load_run_measurements_excludes_non_sidecar_json(tmp_path):
    """Non-sidecar JSON files in pass1/ (no source_id/raw_response) are ignored."""
    run_id = "run-admin"
    run_dir = tmp_path / run_id
    _write_json(run_dir / "measurement_header.json", _make_header_dict(run_id))

    # Admin files in run root are not scanned at all (pass1/ only).
    _write_json(run_dir / "retraction.json", {"retracted": ["KDB/raw/foo.md"]})

    # A non-sidecar file that lands in pass1/ is filtered by predicate.
    _write_json(run_dir / "pass1" / "admin.json", {"some": "metadata"})

    # Write a real sidecar alongside the admin file.
    sidecar = _make_sidecar_dict()
    _write_json(run_dir / "pass1" / "KDB__raw__concepts__test-concept.json", sidecar)

    _, measurements = load_run_measurements(run_dir)

    assert len(measurements) == 1
    assert measurements[0].pass_ == "pass1"


def test_load_run_measurements_no_pass2_dir(tmp_path):
    """Missing pass2/ directory is tolerated — only Pass-1 sidecars are returned."""
    run_id = "run-nopass2"
    run_dir = tmp_path / run_id
    _write_json(run_dir / "measurement_header.json", _make_header_dict(run_id))

    sidecar = _make_sidecar_dict()
    _write_json(run_dir / "pass1" / "KDB__raw__x.json", sidecar)

    _, measurements = load_run_measurements(run_dir)

    assert len(measurements) == 1
    assert measurements[0].pass_ == "pass1"


def test_load_run_measurements_quarantined_included(tmp_path):
    """Quarantined (failed) Pass-1 sidecars are included — they are failure-mode signal."""
    run_id = "run-q2"
    run_dir = tmp_path / run_id
    _write_json(run_dir / "measurement_header.json", _make_header_dict(run_id))

    quarantined = _make_sidecar_dict()
    quarantined["parsed_envelope"] = None
    quarantined["outcome"] = "enrich_failed"
    quarantined["raw_response"]["final_status"] = "quarantined"
    _write_json(run_dir / "pass1" / "KDB__raw__bad.json", quarantined)

    _, measurements = load_run_measurements(run_dir)

    assert len(measurements) == 1
    assert measurements[0].final_status == "quarantined"
    assert measurements[0].parse_ok is False
