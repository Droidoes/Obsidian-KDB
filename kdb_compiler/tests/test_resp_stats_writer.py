"""Tests for resp_stats_writer — per-call RespStatsRecord assembly and atomic writes.

Coverage per blueprint §10:
    - safe_source_id stable; sha256 suffix disambiguates colliding slashed
      forms (e.g. 'a/b.md' vs 'a__b.md').
    - metadata+parsed_summary record (no full bodies) when env var unset.
    - full record (parsed_json + system/user prompt + raw response)
      when KDB_RESP_STATS_CAPTURE_FULL=1.
    - write target path = <state_root>/llm_resp_stats/<run_id>/<safe_id>.json.
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
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.run_context import RunContext


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
    assert out == state_root / "llm_resp_stats" / ctx.run_id / expected_name
    assert out.exists()


def test_write_resp_stats_creates_parent_dirs(tmp_path: Path) -> None:
    """atomic_write_json creates parents=True; state_root/llm_resp_stats/<run_id>
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
    assert out.parent.parent.name == "llm_resp_stats"


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
