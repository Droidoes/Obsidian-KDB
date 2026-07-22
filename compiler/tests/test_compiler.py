"""Tests for compiler — per-source compile orchestration (mocked seam).

Coverage per blueprint §10:
    - happy path produces one CompiledSource with compile_meta threaded
    - source-read failure writes a resp-stats record (prompt=None, model_resp=None)
    - prompt-build failure writes a resp-stats record (prompt=None)
    - model-call (SDK) failure writes a resp-stats record (model_response=None)
    - extract failure (prose) is non-gating telemetry (#114): extract_ok=False
      on the record while recovery still selects the document; content gates
      (schema/semantic) arbitrate the payload
    - parse failure (broken JSON) writes a resp-stats record with parse_ok=False,
      parsed_summary=None
    - schema failure writes a resp-stats record with schema_ok=False and
      parsed_summary populated
    - semantic failure writes a resp-stats record with semantic_ok=False
    - resp-stats record written EXACTLY ONCE per compile_one call, in every branch

All tests use `monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)`
to stub the LLM. The resp-stats invariant check counts files on disk under
<state_root>/llm_resp/<run_id>/, which is the authoritative evidence.

prompt_builder caches the system prompt by vault path — an autouse fixture
clears that cache between tests so per-test vaults don't leak.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from common.call_model import ModelResponse
from common.run_context import RunContext
from common.types import (
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
    """Create a minimal vault: KDB/ + raw source + state dir. The system
    prompt is repo-packaged (post-#115) — no vault prompt file needed."""
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
    """compile_meta fields are threaded from the model response + compile loop.

    Fix 3a (#111 retry-telemetry): compile_meta.attempts now reflects the
    compile re-prompt count (state["compile_attempts"]), NOT model_response.attempts
    (the SDK-level transient retry counter).  On a single-pass compile,
    compile_attempts==1 regardless of any SDK-level retries (mr.attempts).
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # mr.attempts=2 simulates SDK transient retries (e.g., network hiccup → retry).
    # The compile loop succeeds on its first pass (no schema/semantic reject).
    # compile_meta.attempts must be 1 (compile-loop count), NOT 2 (SDK count).
    mr = _good_model_response(SOURCE_A, attempts=2)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
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
    # Fix 3a: compile_meta.attempts = compile re-prompt count (=1), not SDK attempts (=2).
    assert meta.attempts == 1
    assert meta.ok is True
    assert meta.error is None


def test_compile_meta_attempts_reflects_reprompt_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 3a (#111 retry-telemetry): compile_meta.attempts == 2 on a re-prompt recovery.

    Sequence: attempt 1 schema-rejected (extra field), attempt 2 clean.
    compile_meta.attempts must be 2 (compile-loop count), not 1 (model-API per-attempt).
    This lets the orchestrator recorder surface the retry count in console.log.
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    bad = _good_response(SOURCE_A)
    bad["description"] = "extra field triggers schema reject"
    good = _good_response(SOURCE_A)
    seq = [json.dumps(bad), json.dumps(good)]

    def schema_bad_then_good(req):
        return ModelResponse(
            text=seq.pop(0),
            input_tokens=100, output_tokens=50, latency_ms=123,
            model="claude-opus-4-7", provider="anthropic", attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", schema_bad_then_good)

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    assert err is None and cs is not None
    meta = cs.compile_meta
    assert meta is not None
    # compile_meta.attempts reflects the compile re-prompt count (2), not SDK attempts (1).
    assert meta.attempts == 2


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
        "compiler.compiler.call_model_with_retry",
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
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fail)

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
        "compiler.compiler.prompt_builder.build_prompt", boom
    )

    def noop(_req):
        raise AssertionError("call_model should not run after prompt-build failure")
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", noop)

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
        "compiler.compiler.call_model_with_retry",
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


def test_compile_one_truncation_guard_is_post_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#114: recovery runs FIRST — stop_reason='max_tokens' is terminal only
    AFTER recovery fails. A truncated-flagged response that still carries a
    complete document compiles; stop_reason is carrier metadata, persisted
    on the record (token_overrun derived from it)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Valid, complete JSON — but the call was flagged truncated.
    truncated = ModelResponse(
        text=json.dumps(_good_response(SOURCE_A)),
        input_tokens=100, output_tokens=4096, latency_ms=10,
        model="claude-haiku-4-5-20251001", provider="anthropic", attempts=1,
        stop_reason="max_tokens",
    )
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
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
    assert err is None
    assert cs is not None

    record = json.loads(_resp_stats_files(state_root, ctx.run_id)[0].read_text())
    assert record["extract_ok"] is True
    assert record["parse_ok"] is True
    assert record["stop_reason"] == "max_tokens"
    assert record["token_overrun"] is True


def test_compile_one_openai_length_stop_reason_also_guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OpenAI-compat providers emit 'length' instead of 'max_tokens'. With a
    genuinely truncated (unrecoverable) document, the post-recovery guard
    fires for 'length' too — terminal, no retry (#114)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    truncated = ModelResponse(
        text='{"source_name": "alpha.md", "pages": [{"slug": "summary-f',
        input_tokens=100, output_tokens=4096, latency_ms=10,
        model="gpt-something", provider="openai", attempts=1,
        stop_reason="length",
    )
    calls = {"n": 0}

    def counting_fake(req):
        calls["n"] += 1
        return truncated

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: counting_fake}),
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
    assert calls["n"] == 1  # terminal — no retry


def test_compile_one_extract_failure_is_non_gating_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#114: extract_ok is non-gating telemetry. Prose around the object
    fails the STRICT shape check (extract_ok=False) but the recovery ladder
    still selects the embedded document (parse_ok=True) — the schema gate,
    not extraction, arbitrates the undersized payload → quarantine."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Prose around the object -> strict extract rejects, recovery selects.
    bad = ModelResponse(
        text="sure, here you go:\n{\"source_id\": \"x\"}\n cheers!",
        input_tokens=10, output_tokens=5, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
    )
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
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
    assert record["extract_ok"] is False   # strict-shape verdict, telemetry only
    assert record["parse_ok"] is True      # recovery selected the document
    assert record["boundary_recovered"] is True
    assert record["schema_ok"] is False    # content gate did the rejecting


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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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


def test_semantic_failure_retries_then_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LB2 (#106): a semantic failure on a non-final attempt retries (consumes
    the 2nd model call) before erroring on the final attempt.  Pre-LB2, semantic
    ran post-loop (1 call total); post-LB2, it runs inside the loop (2 calls)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Schema-valid but summary_slug doesn't match any page slug -> semantic fails.
    bad_payload = _good_response(SOURCE_A)
    bad_payload["summary_slug"] = "summary-nonexistent"
    calls = {"n": 0}

    def always_semantic_bad(req):
        calls["n"] += 1
        return ModelResponse(
            text=json.dumps(bad_payload),
            input_tokens=10, output_tokens=5, latency_ms=10,
            model="claude-opus-4-7", provider="anthropic", attempts=1,
        )

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: always_semantic_bad}),
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

    assert cs is None
    assert "semantic" in (err or "")
    assert calls["n"] == 2   # LB2: retried before erroring (was 1 pre-LB2)


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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.prompt_builder.build_prompt", boom
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
        "compiler.compiler.call_model_with_retry",
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
    encodes the actual stop_reason and max_tokens for grouping. #114: the
    guard fires only AFTER recovery fails, so the document here is genuinely
    truncated (unrecoverable)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A)
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    truncated = ModelResponse(
        text='{"source_name": "alpha.md", "pages": [{"slug": "summary-f',
        input_tokens=100, output_tokens=4096, latency_ms=10,
        model="m", provider="anthropic", attempts=1,
        stop_reason="max_tokens",
    )
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
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


# ---------- Task #110 §3.3: PROACTIVE input-side ctx-overrun guard ----------

def test_compile_one_overrun_quarantines_without_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real prompt against a tiny ctx_window must skip-and-quarantine THIS
    source with NO API spend — the model is never called, compile_one returns
    its quarantine tuple, and the written RespStatsRecord carries the synthetic
    exception-type 'TokenOverrun' (mirrors Pass-1 §3.2)."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda *a, **k: pytest.fail("model called despite ctx overrun"),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="deepseek",
        model="m",
        max_tokens=32768,
        ctx_window=50,
    )
    assert cs is None
    assert err is not None
    # The persisted record carries the synthetic TokenOverrun stage/type, and
    # no API spend (no model call → zeroed token counters on the record).
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage == "truncation"
    assert etype == "TokenOverrun"
    assert "ctx_window=50" in msg
    record = json.loads(
        _resp_stats_files(state_root, ctx.run_id)[0].read_text(encoding="utf-8")
    )
    assert record["token_overrun"] is False  # output-truncation flag stays off
    assert record["input_tokens"] == 0
    assert record["output_tokens"] == 0


def test_compile_one_fits_context_proceeds_to_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must NOT false-trip: a small prompt against a large ctx_window
    proceeds to the (monkeypatched) model and produces a CompiledSource."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="m",
        max_tokens=4096,
        ctx_window=1_000_000,
    )
    assert err is None
    assert cs is not None


def test_failure_triplet_extract_stage_never_emitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#114: failure_stage="extract" is never emitted. The prose-wrapped
    payload below fails the strict shape check (extract_ok=False, telemetry
    only) but recovery still selects the embedded object; the SCHEMA gate
    rejects the undersized payload — and schema failures carry no failure
    triplet (they have the structured schema_errors surface instead)."""
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
        "compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad}),
    )

    cs, _, _, err = compiler.compile_one(
        _job(vault, SOURCE_A), vault_root=vault, state_root=state_root,
        ctx=ctx, provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )
    assert cs is None
    assert "schema validation failed" in (err or "")
    stage, etype, msg = _failure_fields(state_root, ctx.run_id)
    assert stage is None and etype is None and msg is None


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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
        "compiler.compiler.call_model_with_retry",
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
    from compiler.compiler import source_text_for
    from common.source_io import SourceFrontmatter

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
    from compiler.compiler import source_text_for

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
    from common.types import PageIntent
    fields = PageIntent.__dataclass_fields__
    assert "domain" not in fields
    assert "sub_domain" not in fields


def test_response_schema_omits_page_domain():
    import json, pathlib
    schema = json.loads(pathlib.Path(
        "compiler/schemas/compiled_source_response.schema.json").read_text())
    # pages.items uses $ref -> #/$defs/pageIntent; resolve through $defs
    page_props = schema["$defs"]["pageIntent"]["properties"]
    assert "domain" not in page_props
    assert "sub_domain" not in page_props


# ---------- rung-1 / rung-2 repair ladder (#106) ----------

def test_rung1_escape_recovers_latex_on_attempt_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rung-1: a stray LaTeX backslash (invalid JSON) is escaped in-place without
    a model re-call.  The backslash survives into the compiled page body verbatim."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    payload = _good_response(SOURCE_A)
    payload["pages"][0]["body"] = "PLACEHOLDER_BODY"
    raw = json.dumps(payload)
    # Re-introduce the stray backslash the model would have emitted:
    raw = raw.replace('"PLACEHOLDER_BODY"', r'"the term \(n-1\) matters"')

    calls = {"n": 0}

    def fake(req):
        calls["n"] += 1
        return ModelResponse(
            text=raw,
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert err is None and cs is not None      # recovered
    assert calls["n"] == 1                     # deterministic — no retry
    # Content fidelity: the backslash survived into the compiled page body.
    body = next(p.body for p in cs.pages if r"n-1" in p.body)
    assert r"\(n-1\)" in body


def test_rung2_coerce_recovers_bad_slug_on_attempt_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rung-2: uppercase + triple-hyphen slug is coerced (lowercase + collapse)
    in-place without a model re-call; cs.summary_slug reflects the coerced form."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    payload = _good_response(SOURCE_A)
    # Corrupt the summary slug with uppercase + triple hyphen.
    old = payload["summary_slug"]
    bad = (
        old.replace("summary-", "summary-Sleep-and-Aging---", 1)
        if old.startswith("summary-")
        else "summary-Bad---Slug"
    )
    payload["summary_slug"] = bad
    for p in payload["pages"]:
        if p.get("page_type") == "summary":
            p["slug"] = bad

    calls = {"n": 0}

    def fake(req):
        calls["n"] += 1
        return ModelResponse(
            text=json.dumps(payload),
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert err is None and cs is not None
    assert calls["n"] == 1
    # Coerced form: lowercased + triple-hyphen collapsed to single.
    assert cs.summary_slug == bad.lower().replace("---", "-")


def test_final_status_retried_when_attempt1_repaired_but_attempt2_is_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression guard for #106 + Fix 2 (#111 retry-telemetry):
    repair flags reset per attempt so attempt-2 winning cleanly is NOT
    mis-labelled 'retried-and-repaired', AND Fix 2 ensures a re-prompt sequence
    is labelled 'retried' (not 'clean' as the pre-#111 bug produced).

    Sequence:
      Attempt 1 — rung-2 fires (bad summary_slug coerced → slug_coerced=True),
                  but semantic still fails (coerced slug doesn't match any page)
                  → continue.  slug_coerced is reset to False for attempt 2.
      Attempt 2 — fully clean response → succeeds.

    #106 guarantee: slug_coerced stays False from the per-attempt reset →
    attempt-2 win is NOT labelled 'retried-and-repaired'.
    Fix 2 (#111): _compile_attempts==2, no repair flags → 'retried' (was 'clean').
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Attempt 1: summary_slug has uppercase + triple-hyphen (schema-invalid).
    # coerce_slugs_and_propagate will coerce it to "summary-bar-baz", which
    # passes schema but does NOT match the page slug "summary-foo" → semantic
    # fails → retry.
    bad = _good_response(SOURCE_A)
    bad["summary_slug"] = "SUMMARY-Bar---Baz"
    # Leave pages[0].slug as "summary-foo" (valid, stays unchanged by coercion)
    # so after coercion summary_slug != any page slug → semantic fail.

    # Attempt 2: fully clean (the standard good response).
    good = _good_response(SOURCE_A)

    seq = [bad, good]

    def fake(req):
        return ModelResponse(
            text=json.dumps(seq.pop(0)),
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert cs is not None and err is None   # recovered on attempt 2

    # Read the on-disk resp-stats record and assert telemetry reflects the
    # winning attempt 2, not the repaired-but-failed attempt 1.
    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    # #106: repair flags reset per attempt — winning attempt 2 is clean of repairs.
    assert rec["syntax_repaired"] is False
    assert rec["slug_coerced"] is False
    # Fix 2 (#111): re-prompt sequence → "retried", not "clean" or "retried-and-repaired".
    assert rec["final_status"] == "retried"


# ---------- ladder edge cases (#106 Task 7) ----------

def test_both_rungs_on_one_emission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both rung-1 (syntax) and rung-2 (slug) fire on the same attempt-1 emission.

    The payload has BOTH a stray LaTeX backslash in the body AND an uppercase +
    triple-hyphen summary slug (and matching page slug). The pipeline must:
      - escape the backslash (parse_ok), then
      - coerce both slugs (schema_ok), then
      - pass semantic (coerced summary_slug matches coerced page slug).

    Expected: recovers on attempt 1 (calls["n"]==1), err is None, the LaTeX
    survives verbatim in the compiled page body, summary_slug is coerced
    (lowercase + hyphen-collapsed), and the resp-stats record shows
    syntax_repaired=True, slug_coerced=True, final_status="repaired".
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Build a payload with a bad slug on both the summary_slug and the page slug
    # so coercion leaves them consistent, and semantic passes.
    bad_slug = "Summary-Sleep-and-Aging---Deep"  # uppercase + triple-hyphen
    payload = _good_response(SOURCE_A)
    payload["summary_slug"] = bad_slug
    for p in payload["pages"]:
        if p.get("page_type") == "summary":
            p["slug"] = bad_slug
    payload["pages"][0]["body"] = "PLACEHOLDER_BODY"

    raw = json.dumps(payload)
    # Re-introduce the stray LaTeX backslash the model would have emitted:
    raw = raw.replace('"PLACEHOLDER_BODY"', r'"the term \(n-1\) matters"')

    calls = {"n": 0}

    def fake(req):
        calls["n"] += 1
        return ModelResponse(
            text=raw,
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", fake)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert err is None and cs is not None      # both rungs recovered
    assert calls["n"] == 1                     # deterministic — no retry

    # LaTeX backslash must survive into the compiled page body.
    body = next(p.body for p in cs.pages if r"n-1" in p.body)
    assert r"\(n-1\)" in body

    # summary_slug must be coerced (lowercase + collapsed hyphens).
    expected_slug = bad_slug.lower().replace("---", "-")  # "summary-sleep-and-aging-deep"
    assert cs.summary_slug == expected_slug

    # Resp-stats telemetry on the written record.
    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["syntax_repaired"] is True
    assert rec["slug_coerced"] is True
    assert rec["final_status"] == "repaired"


def test_collision_falls_through_to_quarantine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rung-2 refuses when two distinct slugs collapse to the same value (collision).

    Two concept pages have slugs 'Foo--Bar' and 'Foo----Bar'. Both collapse to
    'foo-bar' via coerce_slugs_and_propagate, which detects the collision and
    returns False (no mutation). Schema stays invalid, both attempts fail, and
    the source is quarantined.

    Expected: calls["n"]==2, cs is None, err mentions schema, resp-stats
    final_status=="quarantined", slug_coerced==False.
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Build payload with two concept pages whose slugs collide on coercion.
    payload = _good_response(SOURCE_A)
    payload["concept_slugs"] = ["Foo--Bar", "Foo----Bar"]
    payload["pages"] += [
        {
            "slug": "Foo--Bar",
            "page_type": "concept",
            "title": "Foo Bar A",
            "body": "Body A.",
            "status": "active",
            "outgoing_links": [],
            "confidence": "medium",
        },
        {
            "slug": "Foo----Bar",
            "page_type": "concept",
            "title": "Foo Bar B",
            "body": "Body B.",
            "status": "active",
            "outgoing_links": [],
            "confidence": "medium",
        },
    ]

    calls = {"n": 0}

    def always_collision(req):
        calls["n"] += 1
        return ModelResponse(
            text=json.dumps(payload),
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", always_collision)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert calls["n"] == 2                    # exhausted both attempts
    assert cs is None
    assert err is not None
    assert "schema" in err                    # schema validation failed

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["slug_coerced"] is False
    assert rec["final_status"] == "quarantined"


def test_non_slug_schema_error_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rung-2 is a safe no-op on schema errors that are not slug problems.

    A response with an int summary_slug (wrong type) makes schema validation
    fail. coerce_slugs_and_propagate has nothing to fix (the slug field isn't
    a str); it returns False unchanged. Both attempts fail → quarantined.

    Expected: calls["n"]==2, cs is None, schema error, slug_coerced==False.
    This proves rung-2's class-agnostic "attempt on any schema failure, let
    re-validation decide" is harmless on non-slug errors.
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # summary_slug is an int — wrong type, not a slug pattern error, so
    # collapse_slug gets None back (non-str) and coerce returns False immediately.
    payload = _good_response(SOURCE_A)
    payload["summary_slug"] = 42  # type: ignore[assignment]  # int, not str

    calls = {"n": 0}

    def always_bad(req):
        calls["n"] += 1
        return ModelResponse(
            text=json.dumps(payload),
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", always_bad)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert calls["n"] == 2                    # retried then quarantined
    assert cs is None
    assert err is not None
    assert "schema" in err

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["slug_coerced"] is False
    assert rec["final_status"] == "quarantined"


# ---------- discarded-attempt aggregation (#109 Task 2) ----------

def test_two_attempt_compile_aggregates_tokens_and_latency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Attempt 1 fails to parse (invalid JSON); attempt 2 succeeds.  The
    resulting RespStatsRecord must aggregate across BOTH model calls:
      - total_input_tokens  == sum of both calls' input_tokens
      - total_output_tokens == sum of both calls' output_tokens
      - total_latency_ms    == sum of both calls' latency_ms
      - call_count          == 2
      - final_attempt_index == 2
    and the existing single-call fields (input_tokens, output_tokens,
    latency_ms) must still reflect the WINNING attempt's response.
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    calls = {"n": 0}

    def bad_then_good(req):
        calls["n"] += 1
        if calls["n"] == 1:
            # attempt 1: invalid JSON — forces a retry
            return ModelResponse(
                text='{"bad": "json",,}',
                input_tokens=30, output_tokens=15, latency_ms=200,
                model="claude-opus-4-7", provider="anthropic", attempts=1,
            )
        # attempt 2: good response
        return ModelResponse(
            text=json.dumps(_good_response(SOURCE_A)),
            input_tokens=100, output_tokens=50, latency_ms=400,
            model="claude-opus-4-7", provider="anthropic", attempts=1,
        )

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad_then_good}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    assert calls["n"] == 2
    assert err is None
    assert cs is not None

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))

    # Aggregate fields: sum of both attempts
    assert rec["total_input_tokens"] == 30 + 100   # 130
    assert rec["total_output_tokens"] == 15 + 50   # 65
    assert rec["total_latency_ms"] == 200 + 400    # 600
    assert rec["call_count"] == 2
    assert rec["final_attempt_index"] == 2

    # Single-attempt back-compat: winning attempt's per-call values intact
    assert rec["input_tokens"] == 100
    assert rec["output_tokens"] == 50
    assert rec["latency_ms"] == 400


def test_single_attempt_compile_totals_equal_per_attempt_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Back-compat: a 1-attempt compile must set totals == per-attempt values,
    call_count == 1, final_attempt_index == 1."""
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: _good_model_response(SOURCE_A)}),
    )

    compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))

    # For 1 attempt, totals == per-call values
    assert rec["total_input_tokens"] == rec["input_tokens"]
    assert rec["total_output_tokens"] == rec["output_tokens"]
    assert rec["total_latency_ms"] == rec["latency_ms"]
    assert rec["call_count"] == 1
    assert rec["final_attempt_index"] == 1


def test_irreparable_json_quarantines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rung-1 cannot fix JSON that is broken by more than stray backslashes.

    Take a valid JSON dump of _good_response, delete the first comma (so it
    becomes structurally invalid). escape_stray_backslashes returns the text
    unchanged (no backslashes) → parse still fails → retries → quarantines.

    Expected: calls["n"]==2, cs is None, err mentions "invalid JSON",
    syntax_repaired==False, final_status=="quarantined".
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Drop the first comma from a valid JSON dump — creates a structural error
    # that escape_stray_backslashes cannot recover.
    good_json = json.dumps(_good_response(SOURCE_A))
    broken_json = good_json.replace(",", "", 1)  # remove first comma only

    calls = {"n": 0}

    def always_broken(req):
        calls["n"] += 1
        return ModelResponse(
            text=broken_json,
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", always_broken)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert calls["n"] == 2                    # retried then quarantined
    assert cs is None
    assert err is not None
    assert "invalid JSON" in err              # parse failure message

    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["syntax_repaired"] is False
    assert rec["final_status"] == "quarantined"


# ---------- Fix 2 (#111 retry-telemetry): "retried" final_status ----------

def test_final_status_retried_on_reprompt_only_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fix 2 (#111): a re-prompt-only recovery (schema/semantic retry, no in-place
    repair) must be labelled final_status='retried', NOT 'clean'.

    Sequence:
      Attempt 1 — schema invalid: response includes an unknown extra top-level
                  field ('description') that additionalProperties:false rejects.
                  coerce_slugs_and_propagate returns False (slugs are already
                  valid — nothing to coerce).  No syntax repair fires (JSON is
                  well-formed).  Loop continues to attempt 2.
      Attempt 2 — fully clean response → succeeds.

    Pre-fix: compile_attempts=2, _syntax_repaired=False, _slug_coerced=False
    → the finally block fell through to the bare 'else: clean' branch → bug.
    Post-fix: the elif _compile_attempts > 1 guard fires → final_status='retried'.
    """
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    # Attempt 1: well-formed JSON with an extra top-level field 'description'
    # (mirrors the live deepseek bug — an over-supplied field that schema rejects).
    bad = _good_response(SOURCE_A)
    bad["description"] = "This field is not in the schema"

    good = _good_response(SOURCE_A)

    seq = [json.dumps(bad), json.dumps(good)]
    calls = {"n": 0}

    def schema_bad_then_good(req):
        calls["n"] += 1
        return ModelResponse(
            text=seq.pop(0),
            input_tokens=100,
            output_tokens=50,
            latency_ms=123,
            model="claude-opus-4-7",
            provider="anthropic",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", schema_bad_then_good)

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault,
        state_root=state_root,
        ctx=ctx,
        provider="anthropic",
        model="claude-opus-4-7",
        max_tokens=4096,
    )

    assert calls["n"] == 2          # attempt 1 schema-rejected, re-prompted
    assert err is None              # attempt 2 succeeded
    assert cs is not None

    # Read the persisted resp-stats record and assert telemetry is correct.
    files = _resp_stats_files(state_root, ctx.run_id)
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    # No in-place repair was applied.
    assert rec["syntax_repaired"] is False
    assert rec["slug_coerced"] is False
    # Fix 2: re-prompt-only recovery → "retried" (was "clean" before the fix).
    assert rec["final_status"] == "retried"
    # compile_attempts records the winning attempt index.
    assert rec["compile_attempts"] == 2
