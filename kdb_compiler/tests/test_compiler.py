"""Tests for compiler — per-source compile orchestration (mocked seam).

Coverage per blueprint §10:
    - happy path produces one CompiledSource with compile_meta threaded
    - source-read failure writes a resp-stats record (prompt=None, model_resp=None)
    - prompt-build failure writes a resp-stats record (prompt=None)
    - model-call (SDK) failure writes a resp-stats record (model_response=None)
    - extract failure (prose) writes a resp-stats record with extract_ok=False
    - parse failure (broken JSON) writes a resp-stats record with parse_ok=False,
      parsed_summary=None
    - schema failure writes a resp-stats record with schema_ok=False and
      parsed_summary populated
    - semantic failure writes a resp-stats record with semantic_ok=False
    - resp-stats record written EXACTLY ONCE per compile_one call, in every branch

All tests use `monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", fake)`
to stub the LLM. The resp-stats invariant check counts files on disk under
<state_root>/llm_resp/<run_id>/, which is the authoritative evidence.

prompt_builder caches the system prompt by vault path — an autouse fixture
clears that cache between tests so per-test vaults don't leak.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler import compiler, prompt_builder
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import (
    CompileJob,
    ContextPage,
    ContextSnapshot,
)

SOURCE_A = "KDB/raw/alpha.md"


@pytest.fixture(autouse=True)
def _clear_prompt_caches() -> None:
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


# ---------- fixtures ----------

def _write_vault(tmp_path: Path) -> Path:
    """Create a minimal vault: KDB/KDB-Compiler-System-Prompt.md + raw source + state dir."""
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants\n\nRule 1: be honest.\n", encoding="utf-8"
    )
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_raw(vault: Path, source_id: str, body: str = "body") -> None:
    p = vault / source_id
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _job(vault: Path, source_id: str) -> CompileJob:
    return CompileJob(
        source_id=source_id,
        abs_path=str(vault / source_id),
        context_snapshot=ContextSnapshot(source_id=source_id, pages=[]),
    )


def _good_response(source_id: str) -> dict:
    """Build a slim LLM-emitted response (Task #41 — no source-id-space fields)."""
    return {
        "source_name": Path(source_id).name,
        "summary_slug": "summary-foo",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [
            {
                "slug": "summary-foo",
                "page_type": "summary",
                "title": "Foo Summary",
                "body": "Body.",
                "status": "active",
                "outgoing_links": [],
                "confidence": "medium",
            }
        ],
        "log_entries": [],
        "warnings": [],
    }


def _good_model_response(
    source_id: str, *, attempts: int = 1, extra_text: str = ""
) -> ModelResponse:
    text = extra_text + json.dumps(_good_response(source_id))
    return ModelResponse(
        text=text,
        input_tokens=100,
        output_tokens=50,
        latency_ms=123,
        model="claude-opus-4-7",
        provider="anthropic",
        attempts=attempts,
    )


def _ctx(vault: Path) -> RunContext:
    return RunContext.new(dry_run=False, vault_root=vault)


def _resp_stats_files(state_root: Path, run_id: str) -> list[Path]:
    return sorted((state_root / "llm_resp" / run_id).glob("*.json"))


def _fake_call(mapping: dict) -> callable:
    """Return a fake call_model_with_retry that dispatches on source_id in
    the request's user prompt. Supports text responses, ModelResponse
    instances, or callables (raise path).

    Task #41: the user prompt now begins with `source_name: <basename>` —
    we re-derive the source_id key by matching the basename against the
    mapping's source_id keys."""
    def fake(req):
        first_line = req.prompt.splitlines()[0]
        assert first_line.startswith("source_name: "), first_line
        source_name = first_line[len("source_name: "):]
        # mapping is keyed by source_id; match by basename
        match = next(
            (sid for sid in mapping if Path(sid).name == source_name),
            None,
        )
        if match is None:
            raise AssertionError(f"no mapping entry for source_name {source_name!r}")
        entry = mapping[match]
        if callable(entry):
            return entry(req)
        if isinstance(entry, ModelResponse):
            return entry
        raise AssertionError(f"unexpected fake entry type: {type(entry)}")
    return fake


# ---------- compile_one: happy path ----------

def test_compile_one_happy_path_returns_compiled_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert err is None
    assert cs is not None
    assert cs.source_id == SOURCE_A
    assert cs.summary_slug == "summary-foo"
    assert logs == []
    assert warns == []
    assert len(_resp_stats_files(state_root, ctx.run_id)) == 1


def test_compile_one_retries_on_bad_json_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    calls = {"n": 0}

    def bad_then_good(req):
        calls["n"] += 1
        if calls["n"] == 1:
            # invalid JSON: unescaped backslash (the run-4 LaTeX `\(` defect)
            return ModelResponse(
                text=r'{"summary_slug": "s", "body": "gets \(n-1\) points"}',
                input_tokens=10, output_tokens=5, latency_ms=1,
                model="claude-opus-4-7", provider="anthropic", attempts=1,
            )
        return _good_model_response(SOURCE_A)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad_then_good}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    assert calls["n"] == 2          # re-called once after the bad emission
    assert err is None              # retry recovered
    assert cs is not None
    assert cs.source_id == SOURCE_A


def test_compile_one_quarantines_after_all_attempts_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def always_bad(req):
        return ModelResponse(
            text=r'{"body": "gets \(n-1\) points"}',
            input_tokens=10, output_tokens=5, latency_ms=1,
            model="claude-opus-4-7", provider="anthropic", attempts=1,
        )

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: always_bad}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    assert cs is None
    assert err is not None  # still fails after exhausting attempts


def test_compile_one_threads_compile_meta_from_model_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    mr = _good_model_response(SOURCE_A, attempts=2)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: mr}),
    )

    cs, _, _, _ = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is not None
    meta = cs.compile_meta
    assert meta is not None
    assert meta.provider == "anthropic"
    assert meta.model == "claude-opus-4-7"
    assert meta.input_tokens == 100
    assert meta.output_tokens == 50
    assert meta.latency_ms == 123
    assert meta.attempts == 2
    assert meta.ok is True
    assert meta.error is None


def test_compile_one_reconciles_mis_filed_slug_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """compile_one applies reconcile_slug_lists (Task #65 / D45): concept_slugs
    and article_slugs are rebuilt from pages[].page_type, so a slug the model
    mis-filed is corrected before the payload reaches downstream validation."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    response = {
        "source_name": Path(SOURCE_A).name,
        "summary_slug": "summary-foo",
        # 'article-y' is an article page but the model mis-filed its slug
        # into concept_slugs; article_slugs was left empty.
        "concept_slugs": ["concept-x", "article-y"],
        "article_slugs": [],
        "pages": [
            {"slug": "summary-foo", "page_type": "summary", "title": "S",
             "body": "Body.", "status": "active", "outgoing_links": [],
             "confidence": "medium"},
            {"slug": "concept-x", "page_type": "concept", "title": "C",
             "body": "Body.", "status": "active", "outgoing_links": [],
             "confidence": "medium"},
            {"slug": "article-y", "page_type": "article", "title": "A",
             "body": "Body.", "status": "active", "outgoing_links": [],
             "confidence": "medium"},
        ],
        "log_entries": [],
        "warnings": [],
    }
    mr = ModelResponse(
        text=json.dumps(response), input_tokens=100, output_tokens=50,
        latency_ms=123, model="claude-opus-4-7", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: mr}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert err is None, err
    assert cs is not None
    assert cs.concept_slugs == ["concept-x"]
    assert cs.article_slugs == ["article-y"]


# ---------- compile_one: failure paths (all write exactly one resp-stats record) ----------

def test_compile_one_source_read_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    # SOURCE_A raw file deliberately NOT written
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def fail(_req):
        raise AssertionError("call_model should not run after source-read failure")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", fail)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "source read failed" in (err or "")

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["prompt_hash"] == "sha256:none"
    assert record["response_hash"] == "sha256:none"
    assert record["extract_ok"] is False
    assert record["input_tokens"] == 0
    # Source-read failure happens before source_words capture; defaults to 0.
    assert record["source_words"] == 0


def test_compile_one_prompt_build_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def boom(**_kwargs):
        raise RuntimeError("prompt build exploded")
    monkeypatch.setattr(
        "kdb_compiler.compiler.prompt_builder.build_prompt", boom
    )

    def noop(_req):
        raise AssertionError("call_model should not run after prompt-build failure")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", noop)

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "prompt build failed" in (err or "")
    assert "prompt build exploded" in (err or "")

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["prompt_hash"] == "sha256:none"


def test_compile_one_model_call_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def blow_up(_req):
        raise RuntimeError("transport broke")
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: blow_up}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "model call failed" in (err or "")

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    # prompt was built, so prompt_hash is real; response failed pre-body.
    assert record["prompt_hash"] != "sha256:none"
    assert record["response_hash"] == "sha256:none"


def test_compile_one_truncation_guard_short_circuits_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop_reason='max_tokens' must fail with a clear truncation error
    before extract — otherwise we'd get a misleading 'unclosed fence'."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Valid-looking JSON, but the call was truncated.
    truncated = ModelResponse(
        text=json.dumps(_good_response(SOURCE_A)),
        input_tokens=100, output_tokens=4096, latency_ms=10,
        model="claude-haiku-4-5-20251001", provider="anthropic", attempts=1,
        stop_reason="max_tokens",
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: truncated}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
    )
    assert cs is None
    assert err is not None
    assert "truncated at max_tokens=4096" in err
    assert "stop_reason='max_tokens'" in err

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    # Guard fires before extract — extract_ok stays False.
    assert record["extract_ok"] is False
    assert record["parse_ok"] is False


def test_compile_one_openai_length_stop_reason_also_guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OpenAI-compat providers emit 'length' instead of 'max_tokens'."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    truncated = ModelResponse(
        text=json.dumps(_good_response(SOURCE_A)),
        input_tokens=100, output_tokens=4096, latency_ms=10,
        model="gpt-something", provider="openai", attempts=1,
        stop_reason="length",
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: truncated}),
    )

    _, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="openai",
        model="gpt-something",
        max_tokens=4096,
    )
    assert err is not None
    assert "truncated" in err
    assert "stop_reason='length'" in err


def test_compile_one_extract_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Prose around the object -> extract should reject.
    bad = ModelResponse(
        text="sure, here you go:\n{\"source_id\": \"x\"}\n cheers!",
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "extract failed" in (err or "")

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["extract_ok"] is False
    assert record["parse_ok"] is False


def test_compile_one_parse_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Passes extract (bare { ... }), but body is broken JSON.
    bad = ModelResponse(
        text='{"source_id": "x",,}',
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "invalid JSON" in (err or "")

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["extract_ok"] is True
    assert record["parse_ok"] is False
    assert record["parsed_summary"] is None
    assert record["raw_response_text"] == '{"source_id": "x",,}'


def test_compile_one_schema_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    bad_payload = _good_response(SOURCE_A)
    bad_payload["pages"][0]["slug"] = "INVALID SLUG"  # breaks slug pattern
    bad_payload["summary_slug"] = "INVALID SLUG"
    bad = ModelResponse(
        text=json.dumps(bad_payload),
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "schema validation failed" in (err or "")

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["parse_ok"] is True
    assert record["schema_ok"] is False
    assert record["semantic_ok"] is False
    # parsed_summary populated from the parsed (even if schema-invalid) payload
    assert record["parsed_summary"] is not None
    assert record["parsed_summary"]["page_count"] == 1
    assert record["raw_response_text"] == json.dumps(bad_payload)


def test_compile_one_semantic_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Schema-valid but summary_slug doesn't match any page slug.
    bad_payload = _good_response(SOURCE_A)
    bad_payload["summary_slug"] = "summary-not-in-pages"
    bad = ModelResponse(
        text=json.dumps(bad_payload),
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )
    assert cs is None
    assert "semantic check failed" in (err or "")

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["schema_ok"] is True
    assert record["semantic_ok"] is False


# ---------- source_words capture (Task #29) ----------

def test_compile_one_persists_source_words_on_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """source_words = whitespace-split count of source_text, captured
    after successful read and persisted on the resp-stats record."""
    vault = _write_vault(tmp_path)
    body = "the quick brown fox jumps over the lazy dog"  # 9 whitespace tokens
    _write_raw(vault, SOURCE_A, body)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["source_words"] == 9


def test_compile_one_persists_stop_reason_and_token_overrun_on_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Truncated calls flow through the finally block — stop_reason and
    token_overrun must end up on the persisted record."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "two words")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    truncated = ModelResponse(
        text=json.dumps(_good_response(SOURCE_A)),
        input_tokens=10, output_tokens=4096, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
        stop_reason="max_tokens",
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: truncated}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="m",
        max_tokens=4096,
    )

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["stop_reason"] == "max_tokens"
    assert record["token_overrun"] is True
    assert record["source_words"] == 2  # captured before the truncation guard fired


# ---------- failure_* triplet wiring (Task #25) ----------

def _failure_fields(state_root: Path, run_id: str) -> tuple:
    """Helper: read the (single) resp-stats record and return the
    (failure_stage, failure_exception_type, failure_exception_message)
    triplet."""
    files = _resp_stats_files(state_root, run_id)
    assert len(files) == 1, files
    record = json.loads(files[0].read_text(encoding="utf-8"))
    return (
        record["failure_stage"],
        record["failure_exception_type"],
        record["failure_exception_message"],
    )


def test_failure_triplet_source_read_populates_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    # SOURCE_A raw file deliberately NOT written → FileNotFoundError (OSError)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        lambda _req: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "source_read"
    assert etype == "FileNotFoundError"  # OSError subclass
    assert "No such file" in msg or "Errno 2" in msg


def test_failure_triplet_prompt_build_populates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def boom(**_kwargs):
        raise RuntimeError("prompt build exploded")
    monkeypatch.setattr(
        "kdb_compiler.compiler.prompt_builder.build_prompt", boom
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "prompt_build"
    assert etype == "RuntimeError"
    assert msg == "prompt build exploded"


def test_failure_triplet_model_call_populates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def blow_up(_req):
        raise ValueError("transport broke")
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: blow_up}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "model_call"
    assert etype == "ValueError"
    assert msg == "transport broke"


def test_failure_triplet_truncation_uses_synthetic_token_overrun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Truncation is not an exception — we use the synthetic stage name
    'truncation' and synthetic exception_type 'TokenOverrun'. The message
    encodes the actual stop_reason and max_tokens for grouping."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    truncated = ModelResponse(
        text=json.dumps(_good_response(SOURCE_A)),
        input_tokens=100, output_tokens=4096, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
        stop_reason="max_tokens",
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: truncated}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="m", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "truncation"
    assert etype == "TokenOverrun"
    assert "stop_reason='max_tokens'" in msg
    assert "max_tokens=4096" in msg


def test_failure_triplet_extract_populates_valueerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    bad = ModelResponse(
        text="sure, here you go:\n{\"source_id\": \"x\"}\n cheers!",
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "extract"
    assert etype == "ValueError"
    assert msg  # non-empty (extract_json_text raises a specific msg)


def test_failure_triplet_parse_populates_jsondecodeerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    bad = ModelResponse(
        text='{"source_id": "x",,}',  # passes extract (bare {}), fails json.loads
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "parse"
    assert etype == "JSONDecodeError"
    assert msg  # str(JSONDecodeError) includes line/col info


def test_failure_triplet_all_none_on_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Success path: no failure_* fields populated. Regression guard
    against accidental leakage from earlier compile_one invocations."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage is None and etype is None and msg is None


def test_failure_triplet_stays_none_for_schema_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Schema validation has its own structured surface (schema_errors).
    The failure_* triplet is scoped to non-validation halts and must NOT
    overlap with schema/semantic — they're querying different things."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    bad_payload = _good_response(SOURCE_A)
    bad_payload["pages"][0]["slug"] = "INVALID SLUG"
    bad_payload["summary_slug"] = "INVALID SLUG"
    bad = ModelResponse(
        text=json.dumps(bad_payload),
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage is None and etype is None and msg is None
    # schema_errors still populated on the same record.
    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["schema_ok"] is False
    assert len(record["schema_errors"]) > 0


def test_failure_message_truncated_at_2000_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Long exception messages (HTTP error dumps, etc.) are capped to
    2000 chars + '...[truncated]' so the resp-stats artifact stays small."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    long_msg = "x" * 5000

    def boom(_req):
        raise RuntimeError(long_msg)
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: boom}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "model_call"
    assert etype == "RuntimeError"
    assert msg.endswith("...[truncated]")
    assert len(msg) == 2000 + len("...[truncated]")


# ---------- _truncate_msg helper (Task #25) ----------

def test_truncate_msg_below_cap_unchanged() -> None:
    assert compiler._truncate_msg("hello") == "hello"


def test_truncate_msg_at_exact_cap_unchanged() -> None:
    s = "x" * 2000
    assert compiler._truncate_msg(s) == s


def test_truncate_msg_above_cap_truncated() -> None:
    s = "x" * 2001
    out = compiler._truncate_msg(s)
    assert out == "x" * 2000 + "...[truncated]"


# ---------- D-89-17: source_text_for returns (frontmatter, body) tuple ----------

def test_source_text_for_returns_tuple_with_frontmatter(tmp_path: Path) -> None:
    """Per D-89-17 + §10.5: source_text_for splits frontmatter from body."""
    from kdb_compiler.compiler import source_text_for
    from kdb_compiler.source_io import SourceFrontmatter

    src = tmp_path / "essay.md"
    src.write_text(
        "---\n"
        "kdb_signal: signal\n"
        "domain: ai-ml\n"
        "source_type: blog\n"
        "author: Joseph\n"
        "summary: Test.\n"
        "key_themes:\n  - y\n"
        "entity_search_keys:\n  - y\n  - related-thing\n"
        "confidence: 0.9\n"
        "uncertainty_reason: null\n"
        "reject_reason: null\n"
        "prompt_version: 1.0.0\n"
        "model: deepseek\n"
        "schema_version: 1\n"
        "override:\n"
        "  applied: null\n"
        "  rule: null\n"
        "  match: null\n"
        "  llm_original: signal\n"
        "  reject_reason_cleared: null\n"
        "other_reason: null\n"
        "---\n"
        "The body content here.\n",
        encoding="utf-8",
    )
    job = CompileJob(
        source_id="essay",
        abs_path=str(src),
        context_snapshot=ContextSnapshot(source_id="essay", pages=[]),
    )
    fm, body = source_text_for(job)
    assert isinstance(fm, SourceFrontmatter)
    assert fm.domain == "ai-ml"
    assert fm.source_type == "blog"
    assert fm.author == "Joseph"
    assert fm.summary == "Test."
    assert fm.key_themes == ["y"]
    assert fm.entity_search_keys == ["y", "related-thing"]
    assert "The body content here." in body
    assert "kdb_signal" not in body  # frontmatter stripped


def test_source_text_for_handles_pristine_source(tmp_path: Path) -> None:
    """A source without frontmatter (pre-Pass-1) still works — returns (None, body)."""
    from kdb_compiler.compiler import source_text_for

    src = tmp_path / "essay.md"
    src.write_text("# Essay\n\nBody only.\n", encoding="utf-8")
    job = CompileJob(
        source_id="essay",
        abs_path=str(src),
        context_snapshot=ContextSnapshot(source_id="essay", pages=[]),
    )
    fm, body = source_text_for(job)
    assert fm is None
    assert "# Essay" in body


def test_page_intent_has_no_domain_fields():
    """0.5.0: page-level domain/sub_domain removed (domain is Source-level only)."""
    from kdb_compiler.types import PageIntent
    fields = PageIntent.__dataclass_fields__
    assert "domain" not in fields
    assert "sub_domain" not in fields


def test_response_schema_omits_page_domain():
    import json, pathlib
    schema = json.loads(pathlib.Path(
        "kdb_compiler/schemas/compiled_source_response.schema.json").read_text())
    # pages.items uses $ref -> #/$defs/pageIntent; resolve through $defs
    page_props = schema["$defs"]["pageIntent"]["properties"]
    assert "domain" not in page_props
    assert "sub_domain" not in page_props
