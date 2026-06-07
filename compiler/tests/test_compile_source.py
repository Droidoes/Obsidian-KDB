"""Task #91 Plan 1 — compile_source (produce-don't-write Pass-2 core) tests.

All non-live: the model is faked via monkeypatch (the test_compiler.py pattern).
Run: python -m pytest compiler/tests/test_compile_source.py -v -m "not live"
"""
import json
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from common.call_model import ModelResponse
from compiler.canonicalize import load_or_empty
from common.run_context import RunContext
from common.source_io import SourceFrontmatter
from common.types import CompileJob, CompileSourceResult, ContextSnapshot
from kdb_graph.graphdb import GraphDB


@pytest.fixture(autouse=True)
def _clear_prompt_caches():
    prompt_builder.load_system_prompt.cache_clear()
    prompt_builder.load_response_schema_text.cache_clear()


def _fm() -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain="value-investing", source_type="essay",
        author="Test", summary="A summary.", key_themes=["a"],
        entity_search_keys=["value-investing"],
    )


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "KDB-Compiler-System-Prompt.md").write_text(
        "# KDB invariants\n", encoding="utf-8")
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _good_response(source_name: str, *, summary_slug="summary-foo",
                   concept_slugs=None, pages=None) -> dict:
    return {
        "source_name": source_name, "summary_slug": summary_slug,
        "concept_slugs": concept_slugs or [], "article_slugs": [],
        "pages": pages or [{
            "slug": summary_slug, "page_type": "summary", "title": "Foo",
            "body": "Body.", "status": "active", "outgoing_links": [],
            "confidence": "medium",
        }],
        "log_entries": [], "warnings": [],
    }


def _fake_model(response: dict):
    def fake(req):
        return ModelResponse(
            text=json.dumps(response), input_tokens=100, output_tokens=50,
            latency_ms=10, model="m", provider="p", attempts=1,
        )
    return fake


# ---------- Task 1: CompileJob in-memory fields + source_text_for ----------

def test_source_text_for_prefers_in_memory(tmp_path: Path) -> None:
    p = tmp_path / "s.md"
    p.write_text("DISK BODY", encoding="utf-8")
    fm = _fm()
    job = CompileJob(
        source_id="KDB/raw/s.md", abs_path=str(p),
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
        source_text="MEM BODY", frontmatter=fm,
    )
    got_fm, got_text = compiler.source_text_for(job)
    assert got_text == "MEM BODY"
    assert got_fm is fm


def test_source_text_for_falls_back_to_disk(tmp_path: Path) -> None:
    # Regression guard (passes pre-impl too); the in-memory test is the red one.
    p = tmp_path / "s.md"
    p.write_text("DISK BODY", encoding="utf-8")
    job = CompileJob(
        source_id="KDB/raw/s.md", abs_path=str(p),
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
    )
    got_fm, got_text = compiler.source_text_for(job)
    assert got_text == "DISK BODY"
    assert got_fm is None


# ---------- Task 2: CompileSourceResult shape ----------

def test_compile_source_result_shape() -> None:
    r = CompileSourceResult(cr={"run_id": "x"})
    assert r.cr["run_id"] == "x"
    assert r.failure_stage is None and r.exception_type is None and r.error is None
    assert r.artifacts == {}
    assert r.ok is True


def test_compile_source_result_error_not_ok() -> None:
    r = CompileSourceResult(cr=None, failure_stage="validate", error="boom")
    assert r.ok is False
    assert r.failure_stage == "validate"


# ---------- Task 3: compile_source produce-don't-write core ----------

def test_compile_source_produces_cr_and_writes_nothing(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )

    assert result.ok, (result.failure_stage, result.error)
    assert result.cr is not None
    assert len(result.cr["compiled_sources"]) == 1
    assert result.cr["compiled_sources"][0]["source_id"] == "KDB/raw/s.md"
    assert "canonical_meta" in result.cr            # canonicalize ran (stage 6)
    # produce-don't-write: no wiki pages written anywhere under the vault
    assert not list((vault / "KDB").rglob("summary-foo.md")), "compile_source must not write"


def test_compile_source_requests_json_mode(tmp_path, monkeypatch):
    """Pass-2 must request structured-output JSON mode, mirroring Pass-1.

    Run-2 root cause (2026-05-30): on a 95KB source deepseek-v4-flash emitted
    malformed JSON (JSONDecodeError, not truncation) because the compile call
    free-formed JSON instead of constraining it. Pass-1 already passes
    json_mode=True on the same model; Pass-2 did not.
    """
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    captured: dict = {}

    def capturing(req):
        captured["req"] = req
        return ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        )
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", capturing)

    with GraphDB(tmp_path / "graph") as g:
        compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )

    assert captured["req"].json_mode is True


def test_compile_source_threads_pool_knobs_to_model_request(tmp_path, monkeypatch):
    """#110 final review: compile_source must forward use_completion_tokens +
    extra_body (resolved from the model-pool ModelSpec by the orchestrator)
    into the constructed ModelRequest. Without this, deepseek's
    extra_body={"thinking":{"type":"disabled"}} and gpt-5.4-mini's
    use_completion_tokens=True are dropped on the floor.
    """
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    captured: dict = {}

    def capturing(req):
        captured["req"] = req
        return ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        )
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", capturing)

    knob_extra_body = {"thinking": {"type": "disabled"}}
    with GraphDB(tmp_path / "graph") as g:
        compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            use_completion_tokens=True, extra_body=knob_extra_body,
        )

    assert captured["req"].use_completion_tokens is True
    assert captured["req"].extra_body == knob_extra_body


def test_compile_source_accepts_prebuilt_snapshot(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))
    snap = ContextSnapshot(source_id="KDB/raw/s.md", pages=[])

    # conn=None proves the pre-built snapshot path does no graph read.
    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096, context_snapshot=snap,
    )
    assert result.ok, (result.failure_stage, result.error)
    assert result.cr is not None


# ---------- Task 4: alias-singleton-rename on one-element cr (Qwen F-1) ----------

def test_compile_source_alias_singleton_rename(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    ledger_dir = state_root / "canonicalization"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "aliases.json").write_text(
        json.dumps({"aliases": [{"surface": "aapl", "canonical": "apple-inc"}]}),
        encoding="utf-8")
    ledger = load_or_empty(ledger_dir / "aliases.json")

    resp = _good_response(
        "s.md", concept_slugs=["aapl"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "Foo",
             "body": "About [[aapl]].", "status": "active",
             "outgoing_links": ["aapl"], "confidence": "medium"},
            {"slug": "aapl", "page_type": "concept", "title": "AAPL",
             "body": "Apple Inc.", "status": "active",
             "outgoing_links": [], "confidence": "medium"},
        ])
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(resp))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx, ledger=ledger,
            provider="p", model="m", max_tokens=4096,
        )

    assert result.ok, (result.failure_stage, result.error)
    slugs = {p["slug"] for p in result.cr["compiled_sources"][0]["pages"]}
    assert "apple-inc" in slugs and "aapl" not in slugs, "alias not renamed to canonical"
    aliases = {(a["alias_slug"], a["canonical_slug"])
               for a in result.cr["canonical_meta"]["aliases_emitted"]}
    assert ("aapl", "apple-inc") in aliases


# ---------- Task 5: error paths + failure_stage (D-91-13 case a) ----------

def test_compile_source_compile_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(req):
        raise RuntimeError("model exploded")
    monkeypatch.setattr("compiler.compiler.call_model_with_retry", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.cr is None
    assert result.failure_stage == "compile" and result.error
    assert "resp_stats" in result.artifacts
    assert Path(result.artifacts["resp_stats"]).parent == (
        state_root / "runs" / ctx.run_id / "pass2"
    )
    assert "raw_response" not in result.artifacts


def test_compile_source_parse_error_exposes_raw_resp_stats_artifact(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def bad_json(req):
        return ModelResponse(
            text='{"source_name": "s.md",,}',
            input_tokens=10,
            output_tokens=5,
            latency_ms=10,
            model="m",
            provider="p",
            attempts=1,
        )

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", bad_json)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )

    assert not result.ok and result.failure_stage == "compile"
    assert "raw_response" in result.artifacts
    record = json.loads(Path(result.artifacts["raw_response"]).read_text(encoding="utf-8"))
    assert record["raw_response_text"] == '{"source_name": "s.md",,}'


def test_compile_source_gate_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    from compiler.validate_compile_result import ValidationResult, ValidationFinding
    def fake_validate(cr):
        r = ValidationResult()
        r.gate_errors.append(ValidationFinding(
            type="forced_gate", severity="gate", detail="forced for test",
            source_id="KDB/raw/s.md"))
        return r
    monkeypatch.setattr(
        "compiler.compiler.validate_compile_result.validate", fake_validate)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.cr is None
    assert result.failure_stage == "validate" and "forced for test" in result.error


def test_compile_source_reconcile_error(tmp_path, monkeypatch):
    # Task #91 (m3): a ReconcileError must surface as a case-(a) failure result,
    # not escape the CompileSourceResult contract.
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    from compiler import repair as _rec

    def boom(cr, findings):
        raise _rec.RepairError("forced reconcile failure")
    monkeypatch.setattr("compiler.compiler.repair.repair", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.cr is None
    assert result.failure_stage == "repair"
    assert result.exception_type == "RepairError"
