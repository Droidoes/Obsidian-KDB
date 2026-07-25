"""Task #91 Plan 1 — compile_source (produce-don't-write Pass-2 core) tests.

All non-live: the model is faked via monkeypatch (the test_compiler.py pattern).
Run: python -m pytest compiler/tests/test_compile_source.py -v -m "not live"
"""
import json
import logging
from pathlib import Path

import pytest

from compiler import compiler, prompt_builder
from compiler.summary_slug import expected_summary_slug
from common.call_model import ModelResponse
from common.model_route import ModelRoute
from compiler.canonicalize import load_or_empty
from compiler.context_record import parse_context_record_v1
from common.llm_telemetry import safe_source_id
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
    # The system prompt is repo-packaged (post-#115) — no vault prompt file.
    (tmp_path / "KDB").mkdir(parents=True, exist_ok=True)
    (tmp_path / "KDB" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _good_response(source_name: str, *, pages=None) -> dict:
    """New #115 shape: pages (4 fields); the summary slug follows the
    derived convention (expected_summary_slug)."""
    slug = expected_summary_slug(f"KDB/raw/{source_name}")
    return {
        "pages": pages or [{
            "slug": slug, "page_type": "summary", "title": "Foo",
            "body": "Body.",
        }],
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


def test_compile_source_threads_route_to_model_request(tmp_path, monkeypatch):
    """#121 P2 §6: compile_source → compile_one forwards the pool ModelRoute
    into the constructed ModelRequest — the SAME object reaches the Pass-2
    leaf (identity pin)."""
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

    route = ModelRoute("openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    with GraphDB(tmp_path / "graph") as g:
        compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="deepseek", model="deepseek-v4-flash", max_tokens=4096,
            route=route,
        )

    assert captured["req"].route is route


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
        "s.md",
        pages=[
            {"slug": "summary-s", "page_type": "summary", "title": "Foo",
             "body": "About [[aapl]]."},
            {"slug": "aapl", "page_type": "concept", "title": "AAPL",
             "body": "Apple Inc."},
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


def test_compile_source_canonicalize_error(tmp_path, monkeypatch):
    # A CanonicalizationError must surface as a case-(a) failure result,
    # not escape the CompileSourceResult contract (replaces the deleted
    # Repair-stage routing test — repair is gone, T2.3).
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    from compiler import canonicalize as _canon

    def boom(cr, ledger, run_id):
        raise _canon.CanonicalizationError("forced canonicalization failure")
    monkeypatch.setattr("compiler.compiler.canonicalize.run", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.cr is None
    assert result.failure_stage == "canonicalize"
    assert result.exception_type == "CanonicalizationError"


# ---------- #115 Task 1.4: pre-call underivable-stem route ----------

def test_precall_underivable_stem_inner_and_outer_validate(tmp_path, monkeypatch):
    """Pinned route (R13 F4/R14): inner record AND outer result both carry
    stage 'validate'; attempts=0, zero tokens/cost, exactly one record,
    no model call, no retry."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    calls = {"n": 0}

    def counting(req):
        calls["n"] += 1
        raise AssertionError("model must NOT be called on the pre-call route")

    monkeypatch.setattr("compiler.compiler.call_model_with_retry", counting)

    result = compiler.compile_source(
        source_id="KDB/raw/日本語.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/日本語.md", pages=[]))

    # OUTER stage pinned (≠ generic "compile")
    assert not result.ok and result.cr is None
    assert result.failure_stage == "validate"
    assert result.exception_type == "PathError"
    assert calls["n"] == 0

    # INNER record: exactly one, attempts=0, zero tokens/cost
    records = list((state_root / "runs" / ctx.run_id / "pass2").glob("*.json"))
    assert len(records) == 1
    rec = json.loads(records[0].read_text(encoding="utf-8"))
    assert rec["failure_stage"] == "validate"
    assert rec["attempts"] == 0
    assert rec["input_tokens"] == 0 and rec["output_tokens"] == 0
    assert rec["total_input_tokens"] == 0 and rec["total_output_tokens"] == 0
    assert rec["cost_usd"] == 0.0
    assert rec["final_status"] == "quarantined"
    assert rec["call_count"] == 1  # sentinel for pre-model failures (never 0)


def test_postcall_semantic_failure_inner_and_outer_validate(tmp_path, monkeypatch):
    """Codex Gate-2 F3, re-cased #119: a TERMINAL post-call semantic rejection
    (proposal-schema-valid payload that the bridge rejects — here no summary
    page) carries stage 'validate' on BOTH the inner record and the outer
    result — not generic 'compile'. semantic_errors remains the structured
    detail surface; the exception_type is the synthetic ProposalReject class."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    bad = {"pages": [
        {"slug": "concept-a", "page_type": "concept", "title": "A",
         "body": "Body."},
    ]}
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(bad))

    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]))

    # OUTER stage pinned (≠ generic "compile")
    assert not result.ok and result.cr is None
    assert result.failure_stage == "validate"
    assert result.exception_type == "ProposalReject:no_summary"

    # INNER record: typed validate failure + structured semantic_errors kept
    records = list((state_root / "runs" / ctx.run_id / "pass2").glob("*.json"))
    assert len(records) == 1
    rec = json.loads(records[0].read_text(encoding="utf-8"))
    assert rec["failure_stage"] == "validate"
    assert rec["failure_exception_type"] == "ProposalReject:no_summary"
    assert rec["failure_exception_message"]
    assert rec["schema_ok"] is True
    assert rec["semantic_ok"] is False
    assert rec["semantic_errors"]


_REMOVED_KEYS = {
    "source_name", "summary_slug", "concept_slugs", "article_slugs",
    "log_entries", "warnings", "status", "outgoing_links", "confidence",
}


def test_compile_source_payload_contains_no_removed_keys(tmp_path, monkeypatch):
    """T1.5 recursive assertion: NO new page/aggregate payload contains ANY
    of the removed contract fields; a historical payload WITH them still
    validates (T2.2 bridge)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096)
    assert result.ok, (result.failure_stage, result.error)

    def walk(obj, path="$"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in _REMOVED_KEYS, f"removed key {path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(result.cr)

    # Historical payload WITH the removed fields still validates (dual-mode).
    from compiler import validate_compile_result as vcr
    legacy = json.loads(
        Path("tests/fixtures/compile_result.minimal.valid.json").read_text(encoding="utf-8"))
    assert vcr.validate(legacy).is_valid


# ---------- Task #122 P1: per-source context record writer ----------

def _record_path(state_root: Path, run_id: str, source_id: str) -> Path:
    return (state_root / "runs" / run_id / "context"
            / f"{safe_source_id(source_id)}.json")


def test_compile_source_writes_complete_context_record(tmp_path, monkeypatch):
    """Success path: one complete record per source per run, parseable by the
    strict parser, observables non-null (empty-graph telemetry here)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda req: ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        ),
    )
    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert result.ok, (result.failure_stage, result.error)

    path = _record_path(state_root, ctx.run_id, "KDB/raw/s.md")
    assert path.is_file(), f"context record not written at {path}"
    rec = parse_context_record_v1(json.loads(path.read_text(encoding="utf-8")))
    assert rec.status == "complete"
    assert rec.run_id == ctx.run_id
    assert rec.source_id == "KDB/raw/s.md"
    assert rec.configured_t2_mode == "structured"
    assert rec.effective_t2_strategy == "structured_keys"
    assert rec.keys_emitted == ["value-investing"]
    # strict 1:1 — the empty graph leaves every emitted key unresolved
    assert [o.key for o in rec.key_outcomes] == rec.keys_emitted
    assert [o.disposition for o in rec.key_outcomes] == ["unresolved"]
    # complete-side observables non-null (empty-graph values)
    assert rec.candidate_universe_size == 0
    assert rec.cold_start is True
    assert rec.max_hops == 2
    assert rec.page_cap == 50


def test_compile_source_writes_context_failed_record_on_builder_exception(
    tmp_path, monkeypatch,
):
    """Builder raises → synthesized context_failed record (frozen shape: keys
    retained from frontmatter, empty outcomes, zero tiers, null observables)
    alongside the unchanged failure_stage='context' result."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(*_args, **_kwargs):
        raise RuntimeError("graph wedged")
    monkeypatch.setattr("compiler.compiler.build_context_snapshot", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.failure_stage == "context"
    assert "graph wedged" in (result.error or "")

    path = _record_path(state_root, ctx.run_id, "KDB/raw/s.md")
    assert path.is_file(), f"context_failed record not written at {path}"
    rec = parse_context_record_v1(json.loads(path.read_text(encoding="utf-8")))
    assert rec.status == "context_failed"
    assert rec.run_id == ctx.run_id
    assert rec.source_id == "KDB/raw/s.md"
    assert rec.configured_t2_mode == "structured"
    assert rec.effective_t2_strategy == "structured_keys"
    assert rec.keys_emitted == ["value-investing"]   # retained from frontmatter
    assert rec.key_outcomes == []
    assert rec.t1.candidates == rec.t2.candidates == rec.t3.candidates == 0
    assert rec.t1.delivered == rec.t2.delivered == rec.t3.delivered == 0
    assert rec.candidate_universe_size is None
    assert rec.cold_start is None
    assert rec.max_hops is None
    assert rec.domain_scope == "value-investing"


def test_compile_source_context_record_write_failure_is_warn_only(
    tmp_path, monkeypatch, caplog,
):
    """A record-write failure must NEVER affect the source outcome."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda req: ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        ),
    )

    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("compiler.compiler.atomic_write_json", disk_full)

    with caplog.at_level(logging.WARNING, logger="compiler.compiler"):
        with GraphDB(tmp_path / "graph") as g:
            result = compiler.compile_source(
                source_id="KDB/raw/s.md", body="A note about value investing.",
                frontmatter=_fm(), conn=g.conn,
                vault_root=vault, state_root=state_root, ctx=ctx,
                ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
                provider="p", model="m", max_tokens=4096,
            )
    assert result.ok, (result.failure_stage, result.error)
    assert any("context record write failed" in r.message for r in caplog.records)


def test_compile_source_caller_supplied_snapshot_writes_no_record(
    tmp_path, monkeypatch,
):
    """The replay/tooling path (caller-supplied context_snapshot=) supplies no
    telemetry and writes NO record."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "compiler.compiler.call_model_with_retry",
        lambda req: ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        ),
    )
    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="A note about value investing.",
        frontmatter=_fm(), conn=None,          # pre-built snapshot: no graph read
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md", pages=[]),
    )
    assert result.ok, (result.failure_stage, result.error)
    context_dir = state_root / "runs" / ctx.run_id / "context"
    assert not context_dir.exists() or not list(context_dir.iterdir()), \
        "caller-supplied snapshot path must not write a context record"
