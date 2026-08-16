"""Task #91 Plan 1 — compile_source (produce-don't-write Pass-2 core) tests,
#123 P3a.2b wiring contract (blueprint §4.4/§4.5, §9 P3a.2b row).

All non-live: the Pass-2 model is faked via monkeypatch (the test_compiler.py
pattern); Pass-1.5 runs for real against the temp graph — on an EMPTY graph
the core abstains with zero selector calls (§4.1 step 3), and the selector
seat is a route-valid fake spec. The canned-outcome tests patch the
`kdb_graph_compiler.compiler.run_pass15` seam.

Run: python -m pytest kdb_graph_compiler/tests/test_compile_source.py -v -m "not live"
"""
import json
import logging
from pathlib import Path

import pytest

from kdb_graph_compiler import compiler, prompt_builder
from kdb_graph_compiler.summary_slug import expected_summary_slug
from common.call_model import ModelResponse
from common.model_pool import ModelSpec
from common.model_route import ModelRoute
from kdb_graph_compiler.canonicalize import load_or_empty
from kdb_graph_compiler.context_record import KeyOutcomeV2, parse_context_record_v2
from kdb_graph_compiler.search_adapter import Pass15Outcome
from common.llm_telemetry import safe_source_id
from common.run_context import RunContext
from common.source_io import SourceFrontmatter
from common.types import CompileJob, CompileSourceResult, ContextSnapshot, SearchSummary
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


def _spec(**overrides) -> ModelSpec:
    """A selector seat satisfying every selector-route precondition (the same
    shape test_search_adapter.py uses); the empty-graph tests never reach the
    call seam — the core abstains first."""
    base = dict(
        id="test-selector",
        provider="deepseek",
        model="test",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000,
        max_output_tokens=65_536,
        tokens_lte_bytes=True,
    )
    return ModelSpec(**{**base, **overrides})


def _search_summary(**overrides) -> SearchSummary:
    base = dict(
        search_ran=True,
        query_kind="state_b",
        status="completed",
        failure_class=None,
        execution="two_stage_attempted",
        evidence_status="complete",
        body_coverage=1.0,
        query_truncated_indices=(),
        eligible_space_size=0,
        stage1_retained=0,
        stage2_pool_size=0,
        returned_entries=0,
        valid_entry_yield=1.0,
        unattributed_hit_count=0,
        retry_attempts=0,
        watched=(),
        concordance=1.0,
        selector_provider="deepseek",
        selector_model="test",
        selector_route="openai_compat",
        latency_ms=24,
        cost_usd=0.0,
        budget_records=(),
        stage2_budget_bound=False,
        stage_splits=(),
        artifact_path="/state/runs/run-1/search/s.json",
        search_snapshot_hash="sha256:abc",
        space_entity_count=0,
        hits=(),
    )
    return SearchSummary(**{**base, **overrides})


def _pass15_outcome(**overrides) -> Pass15Outcome:
    base = dict(
        search_ran=True,
        t2_selection=[],
        search_summary=None,
        envelope_written=True,
        t1_slugs=frozenset(),
        keys_emitted=[],
        key_outcomes=[],
    )
    return Pass15Outcome(**{**base, **overrides})


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
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md"),
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
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md"),
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
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
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
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", capturing)

    with GraphDB(tmp_path / "graph") as g:
        compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )

    assert captured["req"].json_mode is True


def test_compile_source_threads_pool_knobs_to_model_request(tmp_path, monkeypatch):
    """#110 final review: compile_source must forward use_completion_tokens +
    extra_body (resolved from the model-pool ModelSpec by the kdb_graph_orchestrator)
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
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", capturing)

    knob_extra_body = {"thinking": {"type": "disabled"}}
    with GraphDB(tmp_path / "graph") as g:
        compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            use_completion_tokens=True, extra_body=knob_extra_body,
            selector=_spec(),
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
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", capturing)

    route = ModelRoute("openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    with GraphDB(tmp_path / "graph") as g:
        compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="deepseek", model="deepseek-v4-flash", max_tokens=4096,
            route=route,
            selector=_spec(),
        )

    assert captured["req"].route is route


def test_compile_source_accepts_prebuilt_snapshot(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))
    snap = ContextSnapshot(source_id="KDB/raw/s.md")

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
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(resp))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx, ledger=ledger,
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
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
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
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

    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", bad_json)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
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
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    from kdb_graph_compiler.validate_compile_result import ValidationResult, ValidationFinding
    def fake_validate(cr):
        r = ValidationResult()
        r.gate_errors.append(ValidationFinding(
            type="forced_gate", severity="gate", detail="forced for test",
            source_id="KDB/raw/s.md"))
        return r
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.validate_compile_result.validate", fake_validate)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
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
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    from kdb_graph_compiler import canonicalize as _canon

    def boom(cr, ledger, run_id):
        raise _canon.CanonicalizationError("forced canonicalization failure")
    monkeypatch.setattr("kdb_graph_compiler.compiler.canonicalize.run", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
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

    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", counting)

    result = compiler.compile_source(
        source_id="KDB/raw/日本語.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/日本語.md"))

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
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(bad))

    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md"))

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
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec())
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
    from kdb_graph_compiler import validate_compile_result as vcr
    legacy = json.loads(
        Path("tests/fixtures/compile_result.minimal.valid.json").read_text(encoding="utf-8"))
    assert vcr.validate(legacy).is_valid


# ---------- #123 P3a.2b: Pass-1.5 wiring (§4.4) + V2 context records (§4.5) ----------

def _record_path(state_root: Path, run_id: str, source_id: str) -> Path:
    return (state_root / "runs" / run_id / "context"
            / f"{safe_source_id(source_id)}.json")


def test_one_search_per_source_before_the_build(tmp_path, monkeypatch):
    """§4.4 step 1: exactly one run_pass15 per compile_source, invoked inside
    the step-1 try, and its products flow into build_context_snapshot."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    calls = {"pass15": 0}
    real_pass15 = compiler.run_pass15

    def spy_pass15(*args, **kwargs):
        calls["pass15"] += 1
        return real_pass15(*args, **kwargs)

    builder_kwargs: dict = {}
    real_build = compiler.build_context_snapshot

    def spy_build(*args, **kwargs):
        builder_kwargs.update(kwargs)
        return real_build(*args, **kwargs)

    monkeypatch.setattr("kdb_graph_compiler.compiler.run_pass15", spy_pass15)
    monkeypatch.setattr("kdb_graph_compiler.compiler.build_context_snapshot", spy_build)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(), intra_run_order=3,
        )
    assert result.ok, (result.failure_stage, result.error)
    assert calls["pass15"] == 1
    # The adapter's products flow into the builder (§4.3's new inputs)…
    assert {"t2_selection", "t1_slugs", "search_summary"} <= set(builder_kwargs)
    # …and the builder is NEVER given source_text (deleted with the regex family).
    assert "source_text" not in builder_kwargs
    assert "mode" not in builder_kwargs and "resolver" not in builder_kwargs


def test_compile_source_writes_complete_v2_context_record(tmp_path, monkeypatch):
    """Success path: one V2 record per source per run — strict-parser
    round-trip, the search section POPULATED (the empty graph abstains —
    a real outcome, not null), no V1 vocabulary on disk."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry",
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
            selector=_spec(),
        )
    assert result.ok, (result.failure_stage, result.error)

    path = _record_path(state_root, ctx.run_id, "KDB/raw/s.md")
    assert path.is_file(), f"context record not written at {path}"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 2
    for retired in ("configured_t2_mode", "effective_t2_strategy", "max_hops"):
        assert retired not in on_disk
    rec = parse_context_record_v2(on_disk)
    assert rec.status == "complete"
    assert rec.run_id == ctx.run_id
    assert rec.source_id == "KDB/raw/s.md"
    assert rec.keys_emitted == ["value-investing"]   # originals, pre-truncation
    # strict 1:1 — the empty graph abstains: every expression unresolved
    assert [o.expression for o in rec.key_outcomes] == rec.keys_emitted
    assert [o.status for o in rec.key_outcomes] == ["unresolved"]
    assert [o.annotation for o in rec.key_outcomes] == ["no_match"]
    # complete-side observables non-null (empty-graph values; no max_hops)
    assert rec.candidate_universe_size == 0
    assert rec.cold_start is True
    assert rec.page_cap == 50
    # §4.3: the search section is populated, not null (abstain is a record)
    assert rec.search is not None
    assert rec.search.status == "abstain_empty_space"


def test_selector_failure_is_honest_empty_t2_and_compile_continues(tmp_path, monkeypatch):
    """§4.1 failure channels: a typed selector_failure outcome is NOT an
    exception — T2 is honestly empty, the compile continues, and the V2
    record's search section carries the typed status."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.run_pass15",
        lambda *a, **k: _pass15_outcome(
            t2_selection=[],
            # 1:1-aligned with _fm()'s keys — the strict parser enforces it.
            keys_emitted=["value-investing"],
            key_outcomes=[KeyOutcomeV2(
                expression="value-investing", status="unresolved",
                annotation="no_match", matched_first_run_id=None,
                match_recency=None)],
            search_summary=_search_summary(
                status="selector_failure", failure_class="thin_exhausted",
                execution="thin_attempted", evidence_status="partial"),
        ))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert result.ok, (result.failure_stage, result.error)   # compile continues
    rec = parse_context_record_v2(json.loads(
        _record_path(state_root, ctx.run_id, "KDB/raw/s.md").read_text("utf-8")))
    assert rec.status == "complete"
    assert rec.t2.candidates == 0                            # honest empty T2
    assert rec.search is not None
    assert rec.search.status == "selector_failure"


def test_t2_selection_flows_into_the_compile_prompt(tmp_path, monkeypatch):
    """End-to-end of the wiring: the adapter's t2_selection is tiered by the
    builder and rendered into EXISTING CONTEXT in the Pass-2 prompt."""
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
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", capturing)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.run_pass15",
        lambda *a, **k: _pass15_outcome(
            t2_selection=["alpha-concept"],
            search_summary=_search_summary(),
        ))

    with GraphDB(tmp_path / "graph") as g:
        g.conn.execute(
            "CREATE (e:Entity {slug: 'alpha-concept', title: 'Alpha Concept', "
            "page_type: 'concept', status: 'active', confidence: 'medium', "
            "created_at: '2026-01-01', updated_at: '2026-01-01', "
            "first_run_id: 'r1', last_run_id: 'r1'})")
        g.conn.execute(
            "CREATE (d:Domain {name: 'value-investing', created_at: '2026-01-01', "
            "first_run_id: 'r1'})")
        g.conn.execute(
            "MATCH (e:Entity {slug: 'alpha-concept'}), (d:Domain {name: 'value-investing'}) "
            "CREATE (e)-[:BELONGS_TO {run_id: 'r1'}]->(d)")
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert result.ok, (result.failure_stage, result.error)
    assert "alpha-concept" in captured["req"].prompt


def test_adapter_defect_lands_in_context_failed_with_keys_fallback(tmp_path, monkeypatch):
    """B4/B7: an adapter defect (unexpected exception, InvalidGraphSearchRequest,
    ContractViolation — anything propagating out of run_pass15) lands in the
    existing context_failed channel; keys_emitted falls back to
    frontmatter.entity_search_keys (§4.5, A9); search is null (no summary
    ever existed)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(*_args, **_kwargs):
        raise RuntimeError("adapter wedged")
    monkeypatch.setattr("kdb_graph_compiler.compiler.run_pass15", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert not result.ok and result.failure_stage == "context"
    assert result.exception_type == "RuntimeError"
    assert "adapter wedged" in (result.error or "")

    rec = parse_context_record_v2(json.loads(
        _record_path(state_root, ctx.run_id, "KDB/raw/s.md").read_text("utf-8")))
    assert rec.status == "context_failed"
    assert rec.keys_emitted == ["value-investing"]   # frontmatter fallback
    assert rec.key_outcomes == []
    assert rec.candidate_universe_size is None
    assert rec.cold_start is None
    assert rec.domain_scope == "value-investing"
    assert rec.search is None                        # no summary ever existed


def test_builder_defect_after_search_keeps_the_summary(tmp_path, monkeypatch):
    """B8: the builder raises AFTER the adapter's search completed — the
    context_failed record's search section is NON-NULL (the summary exists
    by §4.1 step 6, before failure-sensitive post-processing)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(*_args, **_kwargs):
        raise RuntimeError("graph wedged")
    monkeypatch.setattr("kdb_graph_compiler.compiler.build_context_snapshot", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="A note about value investing.",
            frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert not result.ok and result.failure_stage == "context"
    assert "graph wedged" in (result.error or "")

    rec = parse_context_record_v2(json.loads(
        _record_path(state_root, ctx.run_id, "KDB/raw/s.md").read_text("utf-8")))
    assert rec.status == "context_failed"
    assert rec.keys_emitted == ["value-investing"]
    assert rec.key_outcomes == []
    assert rec.candidate_universe_size is None
    assert rec.cold_start is None
    # The empty-graph search abstained BEFORE the builder raised — populated.
    assert rec.search is not None
    assert rec.search.status == "abstain_empty_space"


def test_post_search_defect_carries_the_summary_on_the_exception(tmp_path, monkeypatch):
    """B9's compile-side half: an exception escaping run_pass15 AFTER the
    summary was built carries it (the adapter attaches `_kdb_graph_search_summary`)
    so context_failed.search stays non-null."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def raise_with_summary(*_args, **_kwargs):
        exc = RuntimeError("post-search defect")
        exc._kdb_graph_search_summary = _search_summary()  # noqa: SLF001 — the adapter's channel
        raise exc
    monkeypatch.setattr("kdb_graph_compiler.compiler.run_pass15", raise_with_summary)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert not result.ok and result.failure_stage == "context"
    rec = parse_context_record_v2(json.loads(
        _record_path(state_root, ctx.run_id, "KDB/raw/s.md").read_text("utf-8")))
    assert rec.status == "context_failed"
    assert rec.search is not None
    assert rec.search.status == "completed"


def test_missing_selector_is_a_config_defect_context_failed(tmp_path, monkeypatch):
    """§4.4: selector=None + context_snapshot=None is a configuration defect
    ⇒ SearchConfigError ⇒ context_failed (fail-hard; replay callers always
    pass a snapshot)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.failure_stage == "context"
    assert result.exception_type == "SearchConfigError"
    rec = parse_context_record_v2(json.loads(
        _record_path(state_root, ctx.run_id, "KDB/raw/s.md").read_text("utf-8")))
    assert rec.status == "context_failed"
    assert rec.keys_emitted == ["value-investing"]
    assert rec.search is None


def test_compile_source_context_record_write_failure_is_warn_only(
    tmp_path, monkeypatch, caplog,
):
    """A record-write failure must NEVER affect the source outcome."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry",
        lambda req: ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        ),
    )

    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("kdb_graph_compiler.context_record.atomic_write_json", disk_full)

    with caplog.at_level(logging.WARNING, logger="kdb_graph_compiler.context_record"):
        with GraphDB(tmp_path / "graph") as g:
            result = compiler.compile_source(
                source_id="KDB/raw/s.md", body="A note about value investing.",
                frontmatter=_fm(), conn=g.conn,
                vault_root=vault, state_root=state_root, ctx=ctx,
                ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
                provider="p", model="m", max_tokens=4096,
                selector=_spec(),
            )
    assert result.ok, (result.failure_stage, result.error)
    assert any("context record write failed" in r.message for r in caplog.records)


def test_compile_source_caller_supplied_snapshot_never_searches_writes_no_record(
    tmp_path, monkeypatch,
):
    """The replay/tooling path (caller-supplied context_snapshot=) NEVER
    searches and writes NO record — unchanged by the wiring (§4.4)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry",
        lambda req: ModelResponse(
            text=json.dumps(_good_response("s.md")), input_tokens=100,
            output_tokens=50, latency_ms=10, model="m", provider="p", attempts=1,
        ),
    )

    def no_search(*_args, **_kwargs):
        raise AssertionError("run_pass15 must not run on the replay path")
    monkeypatch.setattr("kdb_graph_compiler.compiler.run_pass15", no_search)

    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="A note about value investing.",
        frontmatter=_fm(), conn=None,          # pre-built snapshot: no graph read
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md"),
    )
    assert result.ok, (result.failure_stage, result.error)
    context_dir = state_root / "runs" / ctx.run_id / "context"
    assert not context_dir.exists() or not list(context_dir.iterdir()), \
        "caller-supplied snapshot path must not write a context record"
    search_dir = state_root / "runs" / ctx.run_id / "search"
    assert not search_dir.exists() or not list(search_dir.iterdir()), \
        "replay path must not write a search envelope"


# ---------- #123 P3a.4: search counters channel (§4.7, §9 P3a.4 row) ----------

def test_compile_source_result_search_counters_default_false() -> None:
    """CompileSourceResult carries the §4.7 counting channel with False
    defaults — a constructed result never implies a search ran."""
    r = CompileSourceResult(cr={"run_id": "x"})
    assert r.search_attempted is False
    assert r.search_envelope_written is False


def test_compile_source_search_counters_success_path(tmp_path, monkeypatch):
    """Happy path: the pass-1.5 search ran (empty-graph abstain) and its
    envelope write succeeded ⇒ both counters True."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert result.ok, (result.failure_stage, result.error)
    assert result.search_attempted is True
    assert result.search_envelope_written is True


def test_compile_source_search_counters_caller_supplied_snapshot_false(
    tmp_path, monkeypatch,
):
    """The replay/tooling path (context_snapshot=) NEVER searches ⇒ both
    counters False on every outcome."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    result = compiler.compile_source(
        source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=None,
        vault_root=vault, state_root=state_root, ctx=ctx,
        ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
        provider="p", model="m", max_tokens=4096,
        context_snapshot=ContextSnapshot(source_id="KDB/raw/s.md"),
    )
    assert result.ok, (result.failure_stage, result.error)
    assert result.search_attempted is False
    assert result.search_envelope_written is False


def test_compile_source_search_counters_threaded_through_compile_failure(
    tmp_path, monkeypatch,
):
    """A post-search failure (here: compile stage) keeps the counters from
    the completed outcome — the search DID run and its envelope WAS written."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry",
        lambda req: ModelResponse(
            text="not json at all", input_tokens=100, output_tokens=50,
            latency_ms=10, model="m", provider="p", attempts=1),
    )
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.run_pass15",
        lambda *a, **k: _pass15_outcome(
            t2_selection=[], search_summary=_search_summary()))

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert not result.ok and result.failure_stage == "compile"
    assert result.search_attempted is True
    assert result.search_envelope_written is True


def test_compile_source_search_counters_envelope_write_failure(tmp_path, monkeypatch):
    """Envelope write failure is warn-only (B9): the source outcome is
    unaffected, but the counters split — attempted True, written False."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)
    monkeypatch.setattr(
        "kdb_graph_compiler.compiler.call_model_with_retry", _fake_model(_good_response("s.md")))

    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("kdb_graph_compiler.search_adapter.atomic_write_json", disk_full)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert result.ok, (result.failure_stage, result.error)
    assert result.search_attempted is True
    assert result.search_envelope_written is False


def test_compile_source_search_counters_context_failure_from_outcome(
    tmp_path, monkeypatch,
):
    """Context failure AFTER the search completed (builder defect): counters
    come from the outcome — attempted True, written True."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def boom(*_args, **_kwargs):
        raise RuntimeError("graph wedged")
    monkeypatch.setattr("kdb_graph_compiler.compiler.build_context_snapshot", boom)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert not result.ok and result.failure_stage == "context"
    assert result.search_attempted is True
    assert result.search_envelope_written is True


def test_compile_source_search_counters_context_failure_from_exception_channel(
    tmp_path, monkeypatch,
):
    """Context failure INSIDE run_pass15 (no outcome): counters come from the
    exception channel (`_kdb_graph_search_attempted` / `_kdb_graph_search_envelope_written`,
    attached by the adapter's B9 except-block)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    def raise_with_counters(*_args, **_kwargs):
        exc = RuntimeError("post-search defect")
        exc._kdb_graph_search_attempted = True  # noqa: SLF001 — the adapter's channel
        exc._kdb_graph_search_envelope_written = False  # noqa: SLF001
        raise exc
    monkeypatch.setattr("kdb_graph_compiler.compiler.run_pass15", raise_with_counters)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
            selector=_spec(),
        )
    assert not result.ok and result.failure_stage == "context"
    assert result.search_attempted is True
    assert result.search_envelope_written is False


def test_compile_source_search_counters_config_defect_false(tmp_path, monkeypatch):
    """A pre-search defect (missing selector ⇒ SearchConfigError before the
    adapter runs) reports no search: both counters False."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    ctx = RunContext.new(dry_run=False, vault_root=vault)

    with GraphDB(tmp_path / "graph") as g:
        result = compiler.compile_source(
            source_id="KDB/raw/s.md", body="Body.", frontmatter=_fm(), conn=g.conn,
            vault_root=vault, state_root=state_root, ctx=ctx,
            ledger=load_or_empty(state_root / "canonicalization" / "aliases.json"),
            provider="p", model="m", max_tokens=4096,
        )
    assert not result.ok and result.failure_stage == "context"
    assert result.search_attempted is False
    assert result.search_envelope_written is False
