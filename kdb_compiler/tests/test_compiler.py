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
    - mixed run (1 pass + 2 fail) -> success=False, errors=2, compiled=1
    - empty-jobs run -> success=True, compiled=[], log has 1 info entry
    - all-fail run -> success=False
    - dry_run=True skips compile_result.json write
    - resp-stats record written EXACTLY ONCE per compile_one call, in every branch
    - run_compile returns a CompileResult that passes validate_compile_result

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
from kdb_compiler.validate_compile_result import validate as validate_compile_result


SOURCE_A = "KDB/raw/alpha.md"
SOURCE_B = "KDB/raw/beta.md"
SOURCE_C = "KDB/raw/gamma.md"


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
    return {
        "source_id": source_id,
        "summary_slug": "foo-summary",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [
            {
                "slug": "foo-summary",
                "page_type": "summary",
                "title": "Foo Summary",
                "body": "Body.",
                "status": "active",
                "supports_page_existence": [source_id],
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
    instances, or callables (raise path)."""
    def fake(req):
        # user prompt is mandatory and begins with "source_id: <id>\n"
        first_line = req.prompt.splitlines()[0]
        assert first_line.startswith("source_id: "), first_line
        source_id = first_line[len("source_id: "):]
        entry = mapping[source_id]
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
    assert cs.summary_slug == "foo-summary"
    assert logs == []
    assert warns == []
    assert len(_resp_stats_files(state_root, ctx.run_id)) == 1


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


def test_compile_one_semantic_failure_writes_resp_stats_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Schema-valid but summary_slug doesn't match any page slug.
    bad_payload = _good_response(SOURCE_A)
    bad_payload["summary_slug"] = "not-in-pages"
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


# ---------- run_compile: aggregation ----------

def _scan(*ids: str) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "r1",
        "to_compile": list(ids),
        "files": [
            {
                "path": sid,
                "action": "NEW",
                "current_hash": "sha256:" + "a" * 64,
                "current_mtime": 0.0,
                "size_bytes": 1,
                "file_type": "markdown",
                "is_binary": False,
            }
            for sid in ids
        ],
    }


def test_run_compile_mixed_run_fail_does_not_block_success_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    for sid in (SOURCE_A, SOURCE_B, SOURCE_C):
        _write_raw(vault, sid)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def boom(_req):
        raise RuntimeError("transport broke")

    bad_schema = _good_response(SOURCE_C)
    bad_schema["summary_slug"] = "INVALID SLUG"
    bad_schema["pages"][0]["slug"] = "INVALID SLUG"

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({
            SOURCE_A: _good_model_response(SOURCE_A),
            SOURCE_B: boom,
            SOURCE_C: ModelResponse(
                text=json.dumps(bad_schema),
                input_tokens=1, output_tokens=1, latency_ms=1,
                model="m", provider="anthropic", attempts=1,
            ),
        }),
    )

    result = compiler.run_compile(
        vault,
        state_root=state_root,
        scan=_scan(SOURCE_A, SOURCE_B, SOURCE_C),
        ctx=ctx,
        write=False,
    )
    assert result.success is False
    assert len(result.compiled_sources) == 1
    assert result.compiled_sources[0].source_id == SOURCE_A
    assert len(result.errors) == 2

    # One resp-stats record per compile_one call — three calls.
    assert len(_resp_stats_files(state_root, ctx.run_id)) == 3


def test_run_compile_all_fail_success_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    _write_raw(vault, SOURCE_B)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def boom(_req):
        raise RuntimeError("nope")
    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: boom, SOURCE_B: boom}),
    )

    result = compiler.run_compile(
        vault,
        state_root=state_root,
        scan=_scan(SOURCE_A, SOURCE_B),
        ctx=ctx,
        write=False,
    )
    assert result.success is False
    assert result.compiled_sources == []
    assert len(result.errors) == 2


def test_run_compile_empty_jobs_is_success_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def fail(_req):
        raise AssertionError("call_model should never run on empty plan")
    monkeypatch.setattr("kdb_compiler.compiler.call_model_with_retry", fail)

    result = compiler.run_compile(
        vault,
        state_root=state_root,
        scan=_scan(),  # empty to_compile
        ctx=ctx,
        write=False,
    )
    assert result.success is True
    assert result.compiled_sources == []
    assert len(result.log_entries) == 1
    assert result.log_entries[0].level == "info"
    assert "no eligible sources" in result.log_entries[0].message


def test_run_compile_write_true_atomically_writes_compile_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    result = compiler.run_compile(
        vault,
        state_root=state_root,
        scan=_scan(SOURCE_A),
        ctx=ctx,
        write=True,
    )
    cr_path = state_root / "compile_result.json"
    assert cr_path.exists()
    on_disk = json.loads(cr_path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == result.run_id
    assert on_disk["success"] is True
    assert len(on_disk["compiled_sources"]) == 1


def test_run_compile_dry_run_skips_compile_result_write_but_keeps_resp_stats_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    compiler.run_compile(
        vault,
        state_root=state_root,
        scan=_scan(SOURCE_A),
        ctx=ctx,
        write=False,
    )
    assert not (state_root / "compile_result.json").exists()
    # Eval record still written — debug artifact, not gated by write.
    assert len(_resp_stats_files(state_root, ctx.run_id)) == 1


def test_run_compile_result_passes_aggregate_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run_compile output is the exact shape patch_applier consumes,
    so it must satisfy compile_result.schema.json + semantic checks."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    result = compiler.run_compile(
        vault,
        state_root=state_root,
        scan=_scan(SOURCE_A),
        ctx=ctx,
        write=False,
    )
    errors = validate_compile_result(result.to_dict())
    assert errors == []


# ---------- CLI ----------

def test_cli_missing_scan_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "KDB" / "state").mkdir(parents=True)
    rc = compiler.main(["--vault-root", str(tmp_path)])
    assert rc == 1
    assert "missing last_scan.json" in capsys.readouterr().err


def test_cli_happy_path_returns_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    (state_root / "last_scan.json").write_text(
        json.dumps(_scan(SOURCE_A)), encoding="utf-8"
    )

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    rc = compiler.main(["--vault-root", str(vault)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "success=True" in out
    assert (state_root / "compile_result.json").exists()
