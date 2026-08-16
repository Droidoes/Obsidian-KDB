"""Tests for Task #122 P2 — emit_kpis §5 reconciliation-through-emit, §6 rate
equations end-to-end, §7 no-finalize gate + lifecycle, §7b packaging sentinel.

Two harnesses:
- light: a synthetic run_dir (measurement_header + Pass-1 sidecars + context
  records) + a seeded GraphDB → emit_run_kpis → assert measurements.json.
- e2e: kdb_orchestrate.run() with faked LLM calls (helpers imported from
  test_kdb_orchestrate) for the no-finalize lifecycle cases.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import kdb_graph_orchestrator.emit_kpis as emit_mod
import kdb_graph_orchestrator.kdb_orchestrate as kdb_orchestrate
from common.measurement import (
    RunMeasurementHeader,
    SearchPassMeasurement,
    SearchStageMeasurement,
)
from common.types import SearchHitSummary, SearchSummary, TierRecord
from kdb_graph_compiler.context_record import (
    ContextRecordV1,
    ContextRecordV2,
    KeyOutcomeV1,
    KeyOutcomeV2,
)
from kdb_graph.graphdb import GraphDB
from kdb_graph_orchestrator.emit_kpis import emit_run_kpis, maybe_emit_kpis
from kdb_graph_orchestrator.tests.test_kdb_orchestrate import (
    _compiled_response,
    _fake_model,
    _fake_pass1,
    _vault,
    _write_pipelines,
)


# =====================================================================
# Light harness
# =====================================================================

def _header(run_id: str, p2_attempted: int, *, finalize_ran: bool = True,
            searches_attempted: int = 0, searches_written: int = 0) -> RunMeasurementHeader:
    return RunMeasurementHeader(
        run_id=run_id,
        corpus_fingerprint="fp",
        pass1_prompt_version="p1",
        pass2_prompt_version="p2",
        scanned=p2_attempted,
        to_compile=p2_attempted,
        signal=p2_attempted,
        noise=0,
        p1_attempted=p2_attempted,
        p2_attempted=p2_attempted,
        finalize_ran=finalize_ran,
        searches_attempted=searches_attempted,
        searches_written=searches_written,
    )


def _write_header(run_dir: Path, header: RunMeasurementHeader) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "measurement_header.json").write_text(
        json.dumps(dataclasses.asdict(header)), encoding="utf-8")


def _write_sidecar(run_dir: Path, source_id: str, *, signal: str = "signal",
                   keys: list[str] | None = None) -> None:
    pass1 = run_dir / "pass1"
    pass1.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": source_id,
        "request": {"prompt": "p", "model": "m", "provider": "p"},
        "raw_response": {
            "body": "{}", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1,
            "attempts": 1, "final_status": "clean", "syntax_repaired": False,
            "total_input_tokens": 1, "total_output_tokens": 1,
            "total_latency_ms": 1, "call_count": 1, "final_attempt_index": 1,
        },
        "parsed_envelope": {
            "kdb_signal": signal, "domain": "value-investing",
            "source_type": "essay", "author": None, "summary": "s",
            "key_themes": [], "entity_search_keys": keys or [],
            "confidence": 0.9, "uncertainty_reason": None, "reject_reason": None,
            "prompt_version": "p1", "model": "m", "schema_version": 1,
            "other_reason": None,
        },
        "outcome": "enriched",
    }
    (pass1 / f"{source_id.replace('/', '__')}.json").write_text(
        json.dumps(payload), encoding="utf-8")


def _record_v1(run_id: str, source_id: str, outcomes: list[tuple], *,
               t1=None, t2=None, t3=None, strategy="structured_keys") -> ContextRecordV1:
    # #123 P3a.2b: the V1 factory is retired (parse-only history) — tests build
    # V1 records directly.
    zero = TierRecord(0, 0, [])
    return ContextRecordV1(
        schema_version=1,
        run_id=run_id,
        source_id=source_id,
        status="complete",
        configured_t2_mode="structured",
        effective_t2_strategy=strategy,
        keys_emitted=[k for k, _d, _r, _s in outcomes],
        key_outcomes=[KeyOutcomeV1(k, d, r, s) for k, d, r, s in outcomes],
        t1=t1 or zero, t2=t2 or zero, t3=t3 or zero,
        candidate_universe_size=10, domain_scope="value-investing",
        cold_start=False, max_hops=1, page_cap=50,
    )


def _failed_record_v1(run_id: str, source_id: str) -> ContextRecordV1:
    zero = TierRecord(0, 0, [])
    return ContextRecordV1(
        schema_version=1,
        run_id=run_id,
        source_id=source_id,
        status="context_failed",
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=["k1"],
        key_outcomes=[],
        t1=zero, t2=zero, t3=zero,
        candidate_universe_size=None, domain_scope=None,
        cold_start=None, max_hops=None, page_cap=50,
    )


def _write_record(run_dir: Path, run_id: str, source_id: str,
                  outcomes: list[tuple], *, status="complete", **tier_kw) -> None:
    ctx = run_dir / "context"
    ctx.mkdir(parents=True, exist_ok=True)
    rec = (_record_v1(run_id, source_id, outcomes, **tier_kw)
           if status == "complete" else _failed_record_v1(run_id, source_id))
    (ctx / f"{source_id.replace('/', '__')}.json").write_text(
        json.dumps(rec.to_dict()), encoding="utf-8")


def _search_summary(**overrides) -> SearchSummary:
    """Canned §5.2 summary (same shape test_compile_source.py uses)."""
    base = dict(
        search_ran=True, query_kind="state_b", status="completed",
        failure_class=None, execution="two_stage_attempted",
        evidence_status="complete", body_coverage=1.0,
        query_truncated_indices=(), eligible_space_size=0,
        stage1_retained=0, stage2_pool_size=0, returned_entries=0,
        valid_entry_yield=1.0, unattributed_hit_count=0, retry_attempts=0,
        watched=(), concordance=1.0,
        selector_provider="deepseek", selector_model="test",
        selector_route="openai_compat",
        latency_ms=24, cost_usd=0.0, budget_records=(),
        stage2_budget_bound=False, stage_splits=(),
        artifact_path="/state/runs/run-1/search/s.json",
        search_snapshot_hash="sha256:abc", space_entity_count=0, hits=(),
    )
    return SearchSummary(**{**base, **overrides})


def _hit(slug: str, recency: str, *, first_run_id="r0") -> SearchHitSummary:
    return SearchHitSummary(
        slug=slug, first_run_id=first_run_id, match_recency=recency,
        matched_expressions=(slug,))


def _record_v2(run_id: str, source_id: str, outcomes: list[KeyOutcomeV2], *,
               t1=None, t2=None, t3=None, search=None) -> ContextRecordV2:
    zero = TierRecord(0, 0, [])
    return ContextRecordV2(
        schema_version=2,
        run_id=run_id,
        source_id=source_id,
        status="complete",
        keys_emitted=[o.expression for o in outcomes],
        key_outcomes=list(outcomes),
        t1=t1 or zero, t2=t2 or zero, t3=t3 or zero,
        candidate_universe_size=10, domain_scope="value-investing",
        cold_start=False, page_cap=50, search=search,
    )


def _outcome_v2(expression: str, status: str, *, annotation=None,
                stamp=None, recency=None) -> KeyOutcomeV2:
    return KeyOutcomeV2(
        expression=expression, status=status, annotation=annotation,
        matched_first_run_id=stamp, match_recency=recency)


def _write_record_v2(run_dir: Path, run_id: str, source_id: str,
                     outcomes: list[KeyOutcomeV2], *, search=None,
                     **tier_kw) -> None:
    ctx = run_dir / "context"
    ctx.mkdir(parents=True, exist_ok=True)
    rec = _record_v2(run_id, source_id, outcomes, search=search, **tier_kw)
    (ctx / f"{source_id.replace('/', '__')}.json").write_text(
        json.dumps(rec.to_dict()), encoding="utf-8")


def _emit(tmp_path: Path, monkeypatch, run_dir: Path,
          header: RunMeasurementHeader, *, finalize_ran: bool = True) -> dict:
    bench = tmp_path / "bench"
    monkeypatch.setattr(emit_mod, "get_benchmark_runs_dir", lambda: bench)
    out_path = emit_run_kpis(
        run_id=header.run_id, run_dir=run_dir,
        graph_path=tmp_path / "graph", state_root=tmp_path / "state",
        vault_root=tmp_path / "vault", provider="p", model="m",
        header=header, finalize_ran=finalize_ran)
    return json.loads(out_path.read_text(encoding="utf-8"))


def _seed_entity(conn, slug: str, *, first_run_id: str = "r0", status="active",
                 canonical_id=None) -> None:
    conn.execute(
        "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
        "status: $st, confidence: 'medium', canonical_id: $ci, "
        "created_at: '2026-01-01', updated_at: '2026-01-01', "
        "first_run_id: $fr, last_run_id: 'r0'})",
        {"s": slug, "st": status, "ci": canonical_id, "fr": first_run_id},
    )


def _watched(payload: dict) -> dict:
    return payload["graph"]["watched"]


# =====================================================================
# §6 rate equations through emit (exact counts, approx rates)
# =====================================================================

_RETIRED_SEARCH_KEY_SERIES = (
    "search_key_resolved_at_load_rate",
    "search_key_late_resolution_rate",
    "search_key_never_resolved_rate",
    "search_key_resolved_pre_run_rate",
    "search_key_resolved_cohort_rate",
    "search_key_resolved_age_unknown_rate",
    "search_key_t2_seed_rate",
)


def test_emit_expression_and_hit_rates_through_emit(tmp_path, monkeypatch):
    """§4.6 rates through the full emit path (N=3: alpha matched pre_run; k2
    unresolved no_match; k3 unresolved cap_exhausted_possible). Hits are a
    SEPARATE population: 2 hits (1 pre_run, 1 cohort)."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha", "k2", "k3"])
    _write_record_v2(run_dir, "run-1", "src-a", [
        _outcome_v2("alpha", "matched", stamp="r0", recency="pre_run"),
        _outcome_v2("k2", "unresolved", annotation="no_match"),
        _outcome_v2("k3", "unresolved", annotation="cap_exhausted_possible"),
    ], search=_search_summary(
        stage2_budget_bound=True,
        hits=(_hit("alpha", "pre_run", first_run_id="r0"),
              _hit("beta", "cohort", first_run_id="run-1"))))
    with GraphDB(tmp_path / "graph") as g:
        _seed_entity(g.conn, "alpha", first_run_id="r0")
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)
    w = _watched(payload)
    assert w["search_expression_matched_rate"] == pytest.approx(1 / 3)
    assert w["search_expression_unresolved_rate"] == pytest.approx(2 / 3)
    assert w["search_hit_recency_pre_run_rate"] == pytest.approx(0.5)
    assert w["search_hit_recency_cohort_rate"] == pytest.approx(0.5)
    assert w["search_hit_recency_age_unknown_rate"] == 0.0
    assert w["search_stage2_budget_bound_rate"] == 1.0
    for key in _RETIRED_SEARCH_KEY_SERIES:
        assert key not in w
    assert w["context_build_success_rate"] == 1.0
    assert w["context_integrity_ok"] is True
    assert payload["header"]["finalize_ran"] is True


def test_emit_mixed_v1_v2_records_one_population(tmp_path, monkeypatch):
    """The dispatching loader feeds V1 history and V2 current records into
    ONE expression-rate population (V1 disposition != 'unresolved' ⇒ matched)."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 2)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha", "ghost"])
    _write_sidecar(run_dir, "src-b", keys=["beta"])
    _write_record(run_dir, "run-1", "src-a",
                  [("alpha", "resolved_t2_seed", "alpha", "r0"),
                   ("ghost", "unresolved", None, None)])
    _write_record_v2(run_dir, "run-1", "src-b", [
        _outcome_v2("beta", "matched", stamp="r0", recency="pre_run"),
    ], search=_search_summary(hits=(_hit("beta", "pre_run"),)))
    with GraphDB(tmp_path / "graph") as g:
        _seed_entity(g.conn, "alpha", first_run_id="r0")
        _seed_entity(g.conn, "beta", first_run_id="r0")
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)
    w = _watched(payload)
    assert w["search_expression_matched_rate"] == pytest.approx(2 / 3)
    assert w["search_expression_unresolved_rate"] == pytest.approx(1 / 3)
    assert w["search_hit_recency_pre_run_rate"] == 1.0
    assert w["context_build_success_rate"] == 1.0
    assert w["context_record_coverage"] == 1.0


def test_emit_context_failed_in_coverage_not_in_means(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 2)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha"])
    _write_sidecar(run_dir, "src-b", keys=["beta"])
    _write_record(run_dir, "run-1", "src-a",
                  [("alpha", "resolved_t2_seed", "alpha", "r0")],
                  t1=TierRecord(2, 1, ["x"]), t2=TierRecord(4, 2, ["a", "b"]))
    _write_record(run_dir, "run-1", "src-b", [], status="context_failed")
    with GraphDB(tmp_path / "graph") as g:
        _seed_entity(g.conn, "alpha")
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)
    w = _watched(payload)
    assert w["context_record_coverage"] == 1.0          # failed IS captured
    assert w["context_build_success_rate"] == pytest.approx(0.5)
    assert w["context_t1_candidates_mean"] == pytest.approx(2.0)  # complete only
    assert w["context_t2_delivered_mean"] == pytest.approx(2.0)


def test_emit_legacy_resolution_unchanged(tmp_path, monkeypatch):
    """Legacy entity_search_key_resolution keeps working on the finalize path
    alongside the new fields."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha", "ghost"])
    _write_record(run_dir, "run-1", "src-a",
                  [("alpha", "resolved_t2_seed", "alpha", "r0"),
                   ("ghost", "unresolved", None, None)])
    with GraphDB(tmp_path / "graph") as g:
        _seed_entity(g.conn, "alpha")
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)
    w = _watched(payload)
    assert w["entity_search_key_resolution"] == pytest.approx(0.5)
    assert w["search_expression_matched_rate"] == pytest.approx(0.5)


# =====================================================================
# §5 reconciliation cases through emit — evidence_complete False ⇒
# substantive aggregates None, coverage + integrity visible
# =====================================================================

def _reconcile_case(tmp_path, monkeypatch, *, sidecars, records, p2=None,
                    extra_files=None):
    """sidecars: list of source_ids (signal). records: list of (name, payload_dict)."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", p2 if p2 is not None else len(sidecars))
    _write_header(run_dir, hdr)
    for sid in sidecars:
        _write_sidecar(run_dir, sid, keys=["k"])
    ctx = run_dir / "context"
    ctx.mkdir(parents=True, exist_ok=True)
    for name, payload in records:
        (ctx / name).write_text(json.dumps(payload), encoding="utf-8")
    for name, text in (extra_files or {}).items():
        (ctx / name).write_text(text, encoding="utf-8")
    with GraphDB(tmp_path / "graph"):
        pass
    return _emit(tmp_path, monkeypatch, run_dir, hdr)


def _rec(source_id: str, run_id: str = "run-1") -> dict:
    return _record_v1(
        run_id, source_id, [("k", "resolved_t2_seed", "k", "r0")]).to_dict()


def test_emit_reconcile_missing(tmp_path, monkeypatch):
    payload = _reconcile_case(
        tmp_path, monkeypatch, sidecars=["src-a", "src-b"],
        records=[{"a.json": _rec("src-a")}][0].items())
    w = _watched(payload)
    assert w["context_integrity_ok"] is False
    assert w["context_missing_record_count"] == 1
    assert w["context_record_coverage"] == 0.5
    assert w["search_expression_matched_rate"] is None


def test_emit_reconcile_substituted(tmp_path, monkeypatch):
    payload = _reconcile_case(
        tmp_path, monkeypatch, sidecars=["src-a", "src-b"],
        records={"x.json": _rec("src-x")}.items())
    w = _watched(payload)
    assert w["context_integrity_ok"] is False
    assert w["context_missing_record_count"] == 2
    assert w["context_unexpected_record_count"] == 1
    assert w["search_expression_matched_rate"] is None


def test_emit_reconcile_duplicate(tmp_path, monkeypatch):
    payload = _reconcile_case(
        tmp_path, monkeypatch, sidecars=["src-a"],
        records={"a.json": _rec("src-a"), "a2.json": _rec("src-a")}.items())
    w = _watched(payload)
    assert w["context_integrity_ok"] is False
    assert w["context_duplicate_record_count"] == 1
    assert w["context_record_coverage"] == 1.0


def test_emit_reconcile_unexpected_coverage_1_with_extra(tmp_path, monkeypatch):
    """Coverage 1.0 WITH an extra record — the extra still breaks completeness."""
    payload = _reconcile_case(
        tmp_path, monkeypatch, sidecars=["src-a"],
        records={"a.json": _rec("src-a"), "x.json": _rec("src-x")}.items())
    w = _watched(payload)
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is False
    assert w["context_unexpected_record_count"] == 1


def test_emit_reconcile_malformed(tmp_path, monkeypatch):
    payload = _reconcile_case(
        tmp_path, monkeypatch, sidecars=["src-a"],
        records={"a.json": _rec("src-a")}.items(),
        extra_files={"bad.json": "{not json"})
    w = _watched(payload)
    assert w["context_integrity_ok"] is False
    assert w["context_malformed_record_count"] == 1


def test_emit_reconcile_wrong_run(tmp_path, monkeypatch):
    payload = _reconcile_case(
        tmp_path, monkeypatch, sidecars=["src-a"],
        records={"a.json": _rec("src-a"), "s.json": _rec("src-b", run_id="run-0")}.items())
    w = _watched(payload)
    assert w["context_integrity_ok"] is False
    assert w["context_wrong_run_record_count"] == 1


def test_emit_reconcile_zero_expected(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 0)
    _write_header(run_dir, hdr)          # no pass1 sidecars → expected empty
    with GraphDB(tmp_path / "graph"):
        pass
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)
    w = _watched(payload)
    assert w["context_record_coverage"] is None
    assert w["context_integrity_ok"] is None
    assert w["search_expression_matched_rate"] is None
    assert w["context_missing_record_count"] == 0
    assert w["context_expected_count_mismatch"] is False


def test_emit_expected_count_mismatch_flagged(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 5)            # header claims 5, sidecars say 1
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["k"])
    _write_record(run_dir, "run-1", "src-a", [("k", "resolved_t2_seed", "k", "r0")])
    with GraphDB(tmp_path / "graph"):
        pass
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)
    w = _watched(payload)
    assert w["context_expected_count_mismatch"] is True
    assert w["context_integrity_ok"] is False
    assert w["search_expression_matched_rate"] is None   # aggregates gated


# =====================================================================
# §7 gate (maybe_emit_kpis)
# =====================================================================

def test_gate_skips_when_no_finalize_and_no_expected(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 0, finalize_ran=False)
    _write_header(run_dir, hdr)
    bench = tmp_path / "bench"
    monkeypatch.setattr(emit_mod, "get_benchmark_runs_dir", lambda: bench)
    with pytest.warns(UserWarning, match="no context evidence"):
        maybe_emit_kpis(
            emit_kpis=True, run_id="run-1", run_dir=run_dir,
            graph_path=tmp_path / "graph", state_root=tmp_path / "state",
            vault_root=tmp_path / "vault", provider="p", model="m",
            header=hdr, finalize_ran=False)
    assert not list(bench.rglob("measurements.json"))


def test_gate_emits_when_expected_despite_no_finalize(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1, finalize_ran=False)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["k"])
    _write_record(run_dir, "run-1", "src-a", [("k", "resolved_t2_seed", "k", "r0")])
    bench = tmp_path / "bench"
    monkeypatch.setattr(emit_mod, "get_benchmark_runs_dir", lambda: bench)
    with GraphDB(tmp_path / "graph"):
        pass
    maybe_emit_kpis(
        emit_kpis=True, run_id="run-1", run_dir=run_dir,
        graph_path=tmp_path / "graph", state_root=tmp_path / "state",
        vault_root=tmp_path / "vault", provider="p", model="m",
        header=hdr, finalize_ran=False)
    matches = list(bench.rglob("measurements.json"))
    assert len(matches) == 1
    payload = json.loads(matches[0].read_text(encoding="utf-8"))
    assert payload["header"]["finalize_ran"] is False
    assert payload["graph"]["scored"]["entity_reuse"] is None
    assert _watched(payload)["search_expression_matched_rate"] == 1.0


def test_gate_emit_kpis_false_writes_nothing(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1)
    _write_header(run_dir, hdr)
    bench = tmp_path / "bench"
    monkeypatch.setattr(emit_mod, "get_benchmark_runs_dir", lambda: bench)
    maybe_emit_kpis(
        emit_kpis=False, run_id="run-1", run_dir=run_dir,
        graph_path=tmp_path / "graph", state_root=tmp_path / "state",
        vault_root=tmp_path / "vault", provider="p", model="m",
        header=hdr, finalize_ran=True)
    assert not list(bench.rglob("measurements.json"))


# =====================================================================
# §7 no-finalize lifecycle (e2e via kdb_orchestrate.run)
# =====================================================================

def _bench(tmp_path, monkeypatch) -> Path:
    bench = tmp_path / "benchmark" / "runs"
    monkeypatch.setattr(emit_mod, "get_benchmark_runs_dir", lambda: bench)
    return bench


def _only_payload(bench: Path) -> dict:
    matches = list(bench.rglob("measurements.json"))
    assert len(matches) == 1, f"expected exactly one artifact, got {matches}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


def test_lifecycle_all_context_failed_unchanged_graph(tmp_path, monkeypatch):
    """Builder raises per source ⇒ all records context_failed (unchanged
    graph, no finalize) ⇒ audit emitted, success rate 0.0, scored None."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(*_args, **_kwargs):
        raise RuntimeError("graph wedged")
    monkeypatch.setattr("kdb_graph_compiler.compiler.build_context_snapshot", boom)
    bench = _bench(tmp_path, monkeypatch)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m",
        max_tokens=4096, emit_kpis=True)

    assert res.ok and res.finalize is None
    payload = _only_payload(bench)
    assert payload["header"]["finalize_ran"] is False
    assert payload["graph"]["scored"] == {
        "entity_reuse": None, "graph_connectivity": None,
        "link_density": None, "supports_density": None}
    w = _watched(payload)
    assert w["context_build_success_rate"] == 0.0
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is True
    # the record in run_state is the frozen context_failed shape
    ctx_records = list(matches_dir(bench, "context"))
    assert ctx_records, "context records must be packaged in run_state/"
    rec = json.loads(ctx_records[0].read_text(encoding="utf-8"))
    assert rec["status"] == "context_failed"
    assert rec["cold_start"] is None


def matches_dir(bench: Path, dirname: str) -> list[Path]:
    return [p for p in bench.rglob("*.json") if p.parent.name == dirname]


def test_lifecycle_manifest_post_graph_first_source_residual(tmp_path, monkeypatch):
    """manifest_post_graph on the FIRST source (residual graph, no finalize):
    audit evidence emitted, Task-122 fields retained, finalized KPIs None."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry",
                        _fake_model(_compiled_response("a.md", "summary-a")))

    real_write = kdb_orchestrate.atomic_write_json

    def fail_manifest(path, obj, **kwargs):
        if Path(path).name == "manifest.json":
            raise OSError("injected manifest failure")
        return real_write(path, obj, **kwargs)
    monkeypatch.setattr(kdb_orchestrate, "atomic_write_json", fail_manifest)
    bench = _bench(tmp_path, monkeypatch)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m",
        max_tokens=4096, emit_kpis=True)

    assert res.exit_reason.startswith("manifest_post_graph")
    assert res.finalize is None
    payload = _only_payload(bench)
    assert payload["header"]["finalize_ran"] is False
    assert payload["graph"]["scored"]["entity_reuse"] is None
    w = _watched(payload)
    assert w["context_build_success_rate"] == 1.0
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is True


def test_lifecycle_one_committed_then_manifest_post_graph_partial(tmp_path, monkeypatch):
    """One committed source + a later manifest_post_graph (partial graph):
    same no-finalize contract; both sources' context records present."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nFirst.\n", encoding="utf-8")
    (vault / "AIML" / "b.md").write_text("# B\n\nSecond.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def fake_both(req):
        name = "a.md" if "source_name: a.md" in req.prompt else "b.md"
        return _fake_model(_compiled_response(name, f"summary-{name[0]}"))(req)
    monkeypatch.setattr("kdb_graph_compiler.compiler.call_model_with_retry", fake_both)

    real_write = kdb_orchestrate.atomic_write_json
    manifest_calls = {"n": 0}

    def fail_second_manifest(path, obj, **kwargs):
        if Path(path).name == "manifest.json":
            manifest_calls["n"] += 1
            if manifest_calls["n"] == 2:
                raise OSError("injected manifest failure on second source")
        return real_write(path, obj, **kwargs)
    monkeypatch.setattr(kdb_orchestrate, "atomic_write_json", fail_second_manifest)
    bench = _bench(tmp_path, monkeypatch)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="p", model="m",
        max_tokens=4096, emit_kpis=True)

    assert res.exit_reason.startswith("manifest_post_graph")
    assert res.finalize is None
    payload = _only_payload(bench)
    assert payload["header"]["finalize_ran"] is False
    assert payload["graph"]["scored"]["graph_connectivity"] is None
    w = _watched(payload)
    assert w["context_record_coverage"] == 1.0
    assert w["context_build_success_rate"] == 1.0
    assert w["context_integrity_ok"] is True
    assert len(matches_dir(bench, "context")) == 2


def test_lifecycle_packaging_sentinel_no_stale_finalized_output(tmp_path, monkeypatch):
    """§7b sentinel: a PRIOR run's compile_result.json + wiki/ sit on disk;
    the no-finalize run must package NEITHER (run_state/ + report + prompt +
    console only)."""
    vault = _vault(tmp_path)
    state_root = vault / "KDB" / "state"
    (vault / "AIML").mkdir()
    (vault / "AIML" / "a.md").write_text("# A\n\nNote.\n", encoding="utf-8")
    _write_pipelines(state_root, vault)
    # Pre-seed stale finalized output from a "previous run".
    (state_root / "compile_result.json").write_text('{"prior": "MARKER"}', encoding="utf-8")
    (vault / "KDB" / "wiki").mkdir(parents=True)
    (vault / "KDB" / "wiki" / "prior.md").write_text("PRIOR MARKER", encoding="utf-8")

    monkeypatch.setattr("ingestion.enrich.enrich.call_pass1", _fake_pass1)

    def boom(*_args, **_kwargs):
        raise RuntimeError("graph wedged")
    monkeypatch.setattr("kdb_graph_compiler.compiler.build_context_snapshot", boom)
    bench = _bench(tmp_path, monkeypatch)

    res = kdb_orchestrate.run(
        pipeline_id="vt", vault_root=vault, state_root=state_root,
        graph_path=tmp_path / "graph", provider="testmodel", model="testmodel",
        max_tokens=4096, emit_kpis=True)
    assert res.ok and res.finalize is None

    out_dir = bench / f"testmodel-{res.run_id}"
    assert (out_dir / "measurements.json").exists()
    assert (out_dir / "report.md").exists()
    assert (out_dir / "system_prompt.md").exists()
    assert (out_dir / "console.log").exists()
    assert (out_dir / "run_state").is_dir()
    assert (out_dir / "run_state" / "context").is_dir()
    # §7b: NO compile_result.json, NO wiki/ — the stale prior-run artifacts
    # must never be packaged into a no-finalize record.
    assert not (out_dir / "compile_result.json").exists()
    assert not (out_dir / "wiki").exists()


# =====================================================================
# #123 P3a.4 (§4.7) — search section + envelope reconciliation
# =====================================================================

def _search_measurement(run_id: str = "run-1", source_id: str = "src-a",
                        **overrides) -> SearchPassMeasurement:
    """Canned §4.7 measurement: 1 logical call, 2 attempts (thin known
    tokens + cost, fat retry no-response ⇒ unknown), 42ms."""
    base = dict(
        run_id=run_id, source_id=source_id, pass_="pass1_5",
        provider="p", model="m",
        prompt_versions={"thin": "1.0", "fat": None},
        status="completed", execution="two_stage_attempted",
        calls=1, attempts=2,
        total_input_tokens=100, input_token_unknown_attempts=1,
        stage_splits=(
            SearchStageMeasurement(stage="thin", attempts=1,
                                   provider_input_tokens=100,
                                   cost_usd=0.001, sent_bytes=500),
            SearchStageMeasurement(stage="fat", attempts=1,
                                   provider_input_tokens=None,
                                   cost_usd=0.0, sent_bytes=700),
        ),
        total_latency_ms=42, cost_usd=0.001,
        search_snapshot_hash="sha256:abc",
    )
    return SearchPassMeasurement(**{**base, **overrides})


def _write_search_envelope(run_dir: Path, source_id: str,
                           measurement: SearchPassMeasurement) -> None:
    d = run_dir / "search"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{source_id.replace('/', '__')}.json").write_text(
        json.dumps({"schema_version": 1, "measurement": measurement.to_dict()}),
        encoding="utf-8")


def test_emit_search_section_computed_and_reconciled(tmp_path, monkeypatch):
    """§4.7: the search diagnostics aggregate lands on measurements.json as
    payload["search"], with the envelope-vs-header reconciliation passing
    (1 envelope written == header.searches_written)."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1, searches_attempted=1, searches_written=1)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha"])
    _write_record_v2(run_dir, "run-1", "src-a",
                     [_outcome_v2("alpha", "unresolved", annotation="no_match")])
    _write_search_envelope(run_dir, "src-a", _search_measurement())
    with GraphDB(tmp_path / "graph"):
        pass
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)

    s = payload["search"]
    assert s["calls_pass1_5"] == 1
    assert s["attempts_pass1_5"] == 2
    assert s["retries_pass1_5"] == 1
    assert s["cost_usd_pass1_5"] == pytest.approx(0.001)
    assert s["cost_unknown_calls_pass1_5"] == 1
    assert s["input_tokens_pass1_5"] == 100
    assert s["input_token_unknown_attempts_pass1_5"] == 1
    assert s["latency_pass1_5"] == pytest.approx(42.0)
    assert s["envelope_count"] == 1
    assert s["reconciled"] is True


def test_emit_search_reconciliation_mismatch_warns(tmp_path, monkeypatch):
    """§4.7/B10: header.searches_written=1 but NO envelope on disk — the
    measurement state is incomplete: reconciled=False AND a warning (never
    silent)."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1, searches_attempted=1, searches_written=1)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha"])
    _write_record_v2(run_dir, "run-1", "src-a",
                     [_outcome_v2("alpha", "unresolved", annotation="no_match")])
    with GraphDB(tmp_path / "graph"):
        pass
    with pytest.warns(UserWarning, match="search envelope reconciliation"):
        payload = _emit(tmp_path, monkeypatch, run_dir, hdr)

    s = payload["search"]
    assert s["envelope_count"] == 0
    assert s["reconciled"] is False
    # No measurement-bearing files ⇒ the diagnostics are the empty population.
    assert s["calls_pass1_5"] is None


def test_emit_search_old_run_no_search_dir_reconciled(tmp_path, monkeypatch):
    """Pre-P3a.4 run shape: no search dir, header counters 0/0 ⇒ reconciled
    vacuously True, envelope_count 0, diagnostics None."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha"])
    _write_record_v2(run_dir, "run-1", "src-a",
                     [_outcome_v2("alpha", "unresolved", annotation="no_match")])
    with GraphDB(tmp_path / "graph"):
        pass
    payload = _emit(tmp_path, monkeypatch, run_dir, hdr)

    s = payload["search"]
    assert s["envelope_count"] == 0
    assert s["reconciled"] is True
    assert s["calls_pass1_5"] is None
    assert s["latency_pass1_5"] is None


def test_emit_search_malformed_measurement_fails_safely(tmp_path, monkeypatch):
    """The STRICT loader backs emit (B10): a malformed search measurement
    aborts the emission — maybe_emit_kpis converts it to a warning and the
    run is unaffected."""
    run_dir = tmp_path / "run"
    hdr = _header("run-1", 1, searches_attempted=1, searches_written=1)
    _write_header(run_dir, hdr)
    _write_sidecar(run_dir, "src-a", keys=["alpha"])
    _write_record_v2(run_dir, "run-1", "src-a",
                     [_outcome_v2("alpha", "unresolved", annotation="no_match")])
    bad = _search_measurement().to_dict()
    del bad["attempts"]
    (run_dir / "search").mkdir(parents=True, exist_ok=True)
    (run_dir / "search" / "src-a.json").write_text(
        json.dumps({"schema_version": 1, "measurement": bad}), encoding="utf-8")

    bench = tmp_path / "bench"
    monkeypatch.setattr(emit_mod, "get_benchmark_runs_dir", lambda: bench)
    with pytest.warns(UserWarning, match="KPI emission failed"):
        maybe_emit_kpis(
            emit_kpis=True, run_id="run-1", run_dir=run_dir,
            graph_path=tmp_path / "graph", state_root=tmp_path / "state",
            vault_root=tmp_path / "vault", provider="p", model="m",
            header=hdr, finalize_ran=True)
    assert not (bench / "m-run-1" / "measurements.json").exists()
