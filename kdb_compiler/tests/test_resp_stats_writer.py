"""Tests for resp_stats_writer — per-call RespStatsRecord assembly and atomic writes.

Coverage per blueprint §10:
    - safe_source_id stable; sha256 suffix disambiguates colliding slashed
      forms (e.g. 'a/b.md' vs 'a__b.md').
    - metadata+parsed_summary record (no full bodies) when env var unset.
    - full record (parsed_json + system/user prompt + raw response)
      when KDB_RESP_STATS_CAPTURE_FULL=1.
    - write target path = <state_root>/llm_resp/<run_id>/<safe_id>.json.
    - hashes deterministic for the same input.
    - model_response=None -> response_hash='sha256:none', zeroed metrics.
    - prompt=None -> prompt_hash='sha256:none'.
    - missing state dir is created by atomic_write_json (mkdir parents=True).
    - build_parsed_summary reduces a full parsed_json faithfully.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from kdb_compiler import resp_stats_writer
from common.call_model import ModelResponse
from common.run_context import RunContext


@dataclass
class _FakePrompt:
    """Duck-typed BuiltPrompt stand-in for tests. resp_stats_writer only reads
    .system and .user str attrs."""
    system: str
    user: str


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext.new(dry_run=False, vault_root=tmp_path)


def _model_response(
    *, text: str = '{"source_id": "KDB/raw/foo.md"}', attempts: int = 1
) -> ModelResponse:
    return ModelResponse(
        text=text,
        input_tokens=123,
        output_tokens=45,
        latency_ms=678,
        model="claude-opus-4-7",
        provider="anthropic",
        attempts=attempts,
    )


def _parsed_json() -> dict:
    return {
        "source_id": "KDB/raw/foo.md",
        "summary_slug": "foo",
        "pages": [
            {
                "slug": "foo",
                "page_type": "summary",
                "title": "Foo",
                "body": "body-text",
                "status": "active",
                "supports_page_existence": ["KDB/raw/foo.md"],
                "outgoing_links": ["bar", "baz"],
                "confidence": "medium",
            },
            {
                "slug": "bar",
                "page_type": "concept",
                "title": "Bar",
                "body": "body-text-2",
                "status": "active",
                "supports_page_existence": ["KDB/raw/foo.md"],
                "outgoing_links": ["baz"],
                "confidence": "high",
            },
        ],
        "log_entries": [{"level": "info", "message": "ok"}],
        "warnings": [],
    }


# ---------- safe_source_id ----------

def test_safe_source_id_stable_for_same_input() -> None:
    a = resp_stats_writer.safe_source_id("KDB/raw/foo.md")
    b = resp_stats_writer.safe_source_id("KDB/raw/foo.md")
    assert a == b


def test_safe_source_id_shape() -> None:
    sid = "KDB/raw/foo/bar.md"
    out = resp_stats_writer.safe_source_id(sid)
    # slashes replaced; 8-hex suffix appended
    assert out.startswith("KDB__raw__foo__bar.md.")
    suffix = out.rsplit(".", 1)[-1]
    assert len(suffix) == 8
    assert all(c in "0123456789abcdef" for c in suffix)


def test_safe_source_id_suffix_disambiguates_collision() -> None:
    """'a/b.md' and 'a__b.md' both slash-escape to 'a__b.md' — only the
    sha256 suffix keeps them apart."""
    a = resp_stats_writer.safe_source_id("a/b.md")
    b = resp_stats_writer.safe_source_id("a__b.md")
    assert a != b
    assert a.startswith("a__b.md.") and b.startswith("a__b.md.")


# ---------- build_parsed_summary ----------

def test_build_parsed_summary_reduces_full_parsed_json() -> None:
    summary = resp_stats_writer.build_parsed_summary(_parsed_json())
    assert summary.summary_slug == "foo"
    assert summary.page_count == 2
    assert summary.page_types == {"summary": 1, "concept": 1}
    assert summary.slugs == ["foo", "bar"]
    assert summary.outgoing_link_count == 3
    assert summary.log_entry_count == 1
    assert summary.warning_count == 0
    assert summary.source_id_echoed == "KDB/raw/foo.md"


def test_build_parsed_summary_tolerates_missing_fields() -> None:
    summary = resp_stats_writer.build_parsed_summary({})
    assert summary.summary_slug is None
    assert summary.page_count == 0
    assert summary.page_types == {}
    assert summary.slugs == []
    assert summary.outgoing_link_count == 0
    assert summary.log_entry_count == 0
    assert summary.warning_count == 0
    assert summary.source_id_echoed is None


def test_build_parsed_summary_ignores_malformed_pages() -> None:
    payload = {
        "pages": [
            {"slug": "a", "page_type": "summary"},
            "not-a-dict",
            {"page_type": "concept"},        # slug missing
            {"slug": "b"},                   # page_type missing
        ]
    }
    summary = resp_stats_writer.build_parsed_summary(payload)
    assert summary.slugs == ["a", "b"]
    assert summary.page_types == {"summary": 1, "concept": 1}


# ---------- build_resp_stats: always-on fields + gated fields ----------

def test_metadata_only_record_when_capture_full_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KDB_RESP_STATS_CAPTURE_FULL", raising=False)
    ctx = _ctx(tmp_path)
    prompt = _FakePrompt(system="SYS", user="USR")
    parsed = _parsed_json()

    record = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        prompt=prompt,
        raw_response_text='{"source_id": "KDB/raw/foo.md"}',
        model_response=_model_response(),
        extract_ok=True,
        parse_ok=True,
        parsed_json=parsed,
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
    )

    # always-on
    assert record.provider == "anthropic"
    assert record.model == "claude-opus-4-7"
    assert record.input_tokens == 123 and record.output_tokens == 45
    assert record.latency_ms == 678
    assert record.extract_ok and record.parse_ok and record.schema_ok and record.semantic_ok
    assert record.parsed_summary is not None
    assert record.parsed_summary.page_count == 2

    # gated — None when env unset
    assert record.parsed_json is None
    assert record.system_prompt is None
    assert record.user_prompt is None
    assert record.raw_response_text is None


def test_full_record_when_capture_full_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KDB_RESP_STATS_CAPTURE_FULL", "1")
    ctx = _ctx(tmp_path)
    prompt = _FakePrompt(system="SYS", user="USR")
    parsed = _parsed_json()
    raw = '{"source_id": "KDB/raw/foo.md"}'

    record = resp_stats_writer.build_resp_stats(
        ctx=ctx,
        source_id="KDB/raw/foo.md",
        prompt=prompt,
        raw_response_text=raw,
        model_response=_model_response(text=raw),
        extract_ok=True,
        parse_ok=True,
        parsed_json=parsed,
        schema_ok=True,
        schema_errors=[],
        semantic_ok=True,
        semantic_errors=[],
    )
    assert record.parsed_json == parsed
    assert record.system_prompt == "SYS"
    assert record.user_prompt == "USR"
    assert record.raw_response_text == raw


def test_capture_full_only_exact_literal_1_enables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'true', 'yes', '2' must NOT enable capture — strict so operators
    don't get surprised by partial matches."""
    ctx = _ctx(tmp_path)
    for val in ("true", "yes", "2", "on", "TRUE"):
        monkeypatch.setenv("KDB_RESP_STATS_CAPTURE_FULL", val)
        record = resp_stats_writer.build_resp_stats(
            ctx=ctx,
            source_id="KDB/raw/foo.md",
            prompt=_FakePrompt(system="S", user="U"),
            raw_response_text="{}",
            model_response=_model_response(),
            extract_ok=True, parse_ok=True, parsed_json={},
            schema_ok=True, schema_errors=[],
            semantic_ok=True, semantic_errors=[],
        )
        assert record.parsed_json is None, f"env={val!r} must not enable capture"


# ---------- hashing: determinism and sentinels ----------

def test_hashes_are_deterministic(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    prompt = _FakePrompt(system="SYS", user="USR")
    raw = '{"x": 1}'
    mr = _model_response(text=raw)

    a = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md", prompt=prompt,
        raw_response_text=raw, model_response=mr,
        extract_ok=True, parse_ok=True, parsed_json={"x": 1},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    b = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md", prompt=prompt,
        raw_response_text=raw, model_response=mr,
        extract_ok=True, parse_ok=True, parsed_json={"x": 1},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    assert a.prompt_hash == b.prompt_hash
    assert a.response_hash == b.response_hash

    expected_prompt = (
        "sha256:" + hashlib.sha256(b"SYS\n\nUSR").hexdigest()
    )
    expected_resp = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
    assert a.prompt_hash == expected_prompt
    assert a.response_hash == expected_resp


def test_none_model_response_zeroes_metrics_and_sentinels_response_hash(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="",
        model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=["no response"],
        semantic_ok=False, semantic_errors=[],
    )
    assert record.response_hash == "sha256:none"
    assert record.provider == ""
    assert record.model == ""
    assert record.attempts == 0
    assert record.latency_ms == 0
    assert record.input_tokens == 0 and record.output_tokens == 0
    assert record.parsed_summary is None


def test_none_prompt_sentinels_prompt_hash(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=None,
        raw_response_text="",
        model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=[],
        semantic_ok=False, semantic_errors=[],
    )
    assert record.prompt_hash == "sha256:none"


def test_parsed_summary_only_when_parse_ok(tmp_path: Path) -> None:
    """parsed_summary is None when parse_ok=False, regardless of parsed_json."""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="garbage",
        model_response=_model_response(text="garbage"),
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=[],
        semantic_ok=False, semantic_errors=[],
    )
    assert record.parsed_summary is None


# ---------- write_resp_stats: path + atomicity + dir creation ----------

def test_write_resp_stats_target_path(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text='{"x": 1}',
        model_response=_model_response(),
        extract_ok=True, parse_ok=True, parsed_json={"x": 1},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    state_root = tmp_path / "state"
    out = resp_stats_writer.write_resp_stats(record, state_root)

    expected_name = resp_stats_writer.safe_source_id("KDB/raw/foo.md") + ".json"
    assert out == state_root / "llm_resp" / ctx.run_id / expected_name
    assert out.exists()


def test_write_resp_stats_can_target_run_artifact_dir(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text='{"x": 1}',
        model_response=_model_response(),
        extract_ok=True, parse_ok=True, parsed_json={"x": 1},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    state_root = tmp_path / "state"
    artifact_dir = state_root / "runs" / ctx.run_id / "pass2"
    out = resp_stats_writer.write_resp_stats(
        record, state_root, artifact_dir=artifact_dir)

    expected_name = resp_stats_writer.safe_source_id("KDB/raw/foo.md") + ".json"
    assert out == artifact_dir / expected_name
    assert out.exists()
    assert not (state_root / "llm_resp" / ctx.run_id).exists()


def test_write_resp_stats_creates_parent_dirs(tmp_path: Path) -> None:
    """atomic_write_json creates parents=True; state_root/llm_resp/<run_id>
    does not need to pre-exist."""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=None, raw_response_text="",
        model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=[],
        semantic_ok=False, semantic_errors=[],
    )
    state_root = tmp_path / "does" / "not" / "exist"
    assert not state_root.exists()
    out = resp_stats_writer.write_resp_stats(record, state_root)
    assert out.exists()
    assert out.parent.name == ctx.run_id
    assert out.parent.parent.name == "llm_resp"


def test_write_resp_stats_content_is_json(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text='{"x": 1}',
        model_response=_model_response(),
        extract_ok=True, parse_ok=True, parsed_json={"x": 1},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    out = resp_stats_writer.write_resp_stats(record, tmp_path / "state")
    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["run_id"] == ctx.run_id
    assert data["source_id"] == "KDB/raw/foo.md"
    assert data["provider"] == "anthropic"
    assert data["prompt_hash"].startswith("sha256:")
    assert data["response_hash"].startswith("sha256:")
    assert data["parsed_summary"]["page_count"] == 0  # parsed_json was {"x":1}
    # gated fields absent (serialized to null)
    assert data["parsed_json"] is None


# ---------- stop_reason / token_overrun / source_words (Task #29) ----------

def _model_response_with_stop(stop_reason: str | None) -> ModelResponse:
    return ModelResponse(
        text="{}", input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1, stop_reason=stop_reason,
    )


def _build_with(
    tmp_path: Path,
    *,
    model_response: ModelResponse | None,
    source_words: int = 0,
):
    ctx = _ctx(tmp_path)
    return resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=model_response,
        extract_ok=True, parse_ok=True, parsed_json={},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
        source_words=source_words,
    )


def test_stop_reason_persisted_from_model_response(tmp_path: Path) -> None:
    record = _build_with(tmp_path, model_response=_model_response_with_stop("end_turn"))
    assert record.stop_reason == "end_turn"


def test_stop_reason_none_when_no_model_response(tmp_path: Path) -> None:
    record = _build_with(tmp_path, model_response=None)
    assert record.stop_reason is None


def test_token_overrun_true_for_max_tokens(tmp_path: Path) -> None:
    record = _build_with(tmp_path, model_response=_model_response_with_stop("max_tokens"))
    assert record.token_overrun is True


def test_token_overrun_true_for_length(tmp_path: Path) -> None:
    """OpenAI-compat finish_reason='length' must also flip the flag."""
    record = _build_with(tmp_path, model_response=_model_response_with_stop("length"))
    assert record.token_overrun is True


def test_token_overrun_false_for_normal_stop(tmp_path: Path) -> None:
    for sr in ("stop", "end_turn", "tool_use", None):
        record = _build_with(tmp_path, model_response=_model_response_with_stop(sr))
        assert record.token_overrun is False, f"stop_reason={sr!r} should not overrun"


def test_token_overrun_false_when_no_model_response(tmp_path: Path) -> None:
    record = _build_with(tmp_path, model_response=None)
    assert record.token_overrun is False


def test_source_words_persisted(tmp_path: Path) -> None:
    record = _build_with(
        tmp_path, model_response=_model_response_with_stop("end_turn"),
        source_words=4242,
    )
    assert record.source_words == 4242


def test_source_words_defaults_to_zero(tmp_path: Path) -> None:
    """Pre-call failure path: caller may omit source_words, defaults to 0."""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=None, raw_response_text="",
        model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=[],
        semantic_ok=False, semantic_errors=[],
    )
    assert record.source_words == 0


# ---------- requested provider/model fallback (Task #19 Round 4 MF2) ----------

def test_requested_provider_model_fallback_when_no_model_response(tmp_path: Path) -> None:
    """When model_response is None (pre-response failure), the persisted
    provider/model fall back to the REQUESTED values from the runner's
    call site — so the benchmark scorer's filter contract holds for
    pre-call/source-read/prompt-build failures too. Round 4 MF2."""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        provider="anthropic", model="claude-opus-4-7",
        prompt=None, raw_response_text="",
        model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=["pre-response failure"],
        semantic_ok=False, semantic_errors=[],
    )
    assert record.provider == "anthropic"
    assert record.model == "claude-opus-4-7"
    # Other pre-response sentinels still hold.
    assert record.attempts == 0
    assert record.latency_ms == 0
    assert record.response_hash == "sha256:none"


def test_model_response_overrides_requested_provider_model(tmp_path: Path) -> None:
    """When model_response IS present, its provider/model echoes the
    request and is used directly — the requested kwargs are only a
    fallback. (Belt-and-braces: in practice model_response.provider/model
    matches the request, but the contract is unambiguous.)"""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        provider="ignored-fallback", model="ignored-fallback",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(),
        extract_ok=True, parse_ok=True, parsed_json={},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    assert record.provider == "anthropic"
    assert record.model == "claude-opus-4-7"


# ---------- failure_* triplet (Task #25) ----------

def test_failure_none_leaves_all_three_fields_none(tmp_path: Path) -> None:
    """Success path: build_resp_stats called without `failure` kwarg leaves
    all three failure_* fields as None. Verifies the all-or-none invariant
    holds for the default-success case."""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="{}",
        model_response=_model_response(),
        extract_ok=True, parse_ok=True, parsed_json={},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    assert record.failure_stage is None
    assert record.failure_exception_type is None
    assert record.failure_exception_message is None


def test_failure_triplet_populated_from_telemetry(tmp_path: Path) -> None:
    """Passing a FailureTelemetry NamedTuple populates all three flat
    fields on the record. Uses a duck-typed stand-in to avoid taking a
    compiler import into the resp_stats_writer test surface."""
    from typing import NamedTuple

    class _FakeFailure(NamedTuple):
        stage: str
        exception_type: str
        message: str

    ctx = _ctx(tmp_path)
    failure = _FakeFailure(
        stage="source_read",
        exception_type="OSError",
        message="[Errno 13] Permission denied: '/x'",
    )
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=None, raw_response_text="",
        model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=[],
        semantic_ok=False, semantic_errors=[],
        failure=failure,
    )
    assert record.failure_stage == "source_read"
    assert record.failure_exception_type == "OSError"
    assert record.failure_exception_message == "[Errno 13] Permission denied: '/x'"


def test_failure_triplet_serializes_to_json_round_trip(tmp_path: Path) -> None:
    """Failure fields appear in the on-disk JSON with their string values.
    Confirms the dataclass -> asdict -> atomic_write_json -> json.loads
    round trip preserves the triplet."""
    from typing import NamedTuple

    class _FakeFailure(NamedTuple):
        stage: str
        exception_type: str
        message: str

    ctx = _ctx(tmp_path)
    failure = _FakeFailure(
        stage="model_call",
        exception_type="APIConnectionError",
        message="connection reset by peer",
    )
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text="", model_response=None,
        extract_ok=False, parse_ok=False, parsed_json=None,
        schema_ok=False, schema_errors=[],
        semantic_ok=False, semantic_errors=[],
        failure=failure,
    )
    out = resp_stats_writer.write_resp_stats(record, tmp_path / "state")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["failure_stage"] == "model_call"
    assert data["failure_exception_type"] == "APIConnectionError"
    assert data["failure_exception_message"] == "connection reset by peer"


def test_failure_fields_serialize_as_null_when_absent(tmp_path: Path) -> None:
    """Success-path record persists failure_* triplet as JSON nulls (not
    omitted) — so downstream consumers can rely on the keys existing."""
    ctx = _ctx(tmp_path)
    record = resp_stats_writer.build_resp_stats(
        ctx=ctx, source_id="KDB/raw/foo.md",
        prompt=_FakePrompt(system="S", user="U"),
        raw_response_text='{"x": 1}',
        model_response=_model_response(),
        extract_ok=True, parse_ok=True, parsed_json={"x": 1},
        schema_ok=True, schema_errors=[],
        semantic_ok=True, semantic_errors=[],
    )
    out = resp_stats_writer.write_resp_stats(record, tmp_path / "state")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "failure_stage" in data and data["failure_stage"] is None
    assert "failure_exception_type" in data and data["failure_exception_type"] is None
    assert "failure_exception_message" in data and data["failure_exception_message"] is None
