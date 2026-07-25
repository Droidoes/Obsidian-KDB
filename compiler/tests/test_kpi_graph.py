"""Tests for compiler.kpi.graph.compute_graph (#109).

GRAPH-family KPI computation over a hand-rolled Kuzu graph + a finalize_artifacts
report. Each KPI is asserted against hand-computed values.

The graph is hand-rolled via raw conn.execute (the established
test_canonicalization_invariants pattern) because the precise mix of canonical/
alias/orphan entities, SUPPORTS multiplicity, BELONGS_TO, and a null-domain
source cannot be produced through apply_compile_result without fighting the
ingestion derivations.

2026-06-06 refinement: dangling_link_rate (and the compile_result emitted-link
param) were deleted; entity_reuse is the sole scored graph KPI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from compiler.kpi.graph import compute_graph, _largest_component_fraction
from kdb_graph.graphdb import GraphDB


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    """Per-test ephemeral Kuzu directory (mirrors kdb_graph.tests.conftest —
    not importable here as compiler/tests has its own conftest scope)."""
    return tmp_path / "GraphDB-KDB"


# ---------- hand-rolled graph seeding ----------

def _mk_entity(conn, slug, *, canonical_id="NULL", page_type="concept",
               status="active"):
    cid = "NULL" if canonical_id == "NULL" else f"'{canonical_id}'"
    conn.execute(
        f"CREATE (e:Entity {{slug: '{slug}', canonical_id: {cid}, "
        f"title: '', page_type: '{page_type}', status: '{status}', "
        f"confidence: '', created_at: '2026-06-05', updated_at: '2026-06-05', "
        f"first_run_id: 'm', last_run_id: 'm'}})"
    )


def _mk_source(conn, sid, *, domain="'finance'"):
    conn.execute(
        f"CREATE (s:Source {{source_id: '{sid}', source_type: 'file', "
        f"canonical_path: '{sid}', status: 'active', file_type: 'markdown', "
        f"hash: 'h', size_bytes: 1, first_seen_at: '', last_seen_at: '', "
        f"last_ingested_at: '', ingest_state: '', ingest_count: 1, "
        f"last_run_id: 'm', moved_to: '', summary: '', author: '', "
        f"domain: {domain}}})"
    )


def _mk_supports(conn, sid, slug):
    conn.execute(
        f"MATCH (s:Source {{source_id: '{sid}'}}), (e:Entity {{slug: '{slug}'}}) "
        f"CREATE (s)-[:SUPPORTS {{role: '', hash_at_time: '', run_id: 'm', "
        f"created_at: ''}}]->(e)"
    )


def _seed(gdb):
    """Canonical entities: alpha, beta, gamma, summary-x (summary), orphan-z
    (status orphan_candidate). Alias: alpha-alias (canonical_id=alpha).
    Sources: s1, s2 (finance), s3 (NULL domain). SUPPORTS: alpha<-s1,s2;
    beta<-s1; gamma none. Domain finance + BELONGS_TO from alpha. LINKS_TO:
    alpha->beta (the only edge; both canonical → one 2-node component, the
    rest singletons)."""
    c = gdb.conn
    _mk_entity(c, "alpha")
    _mk_entity(c, "beta")
    _mk_entity(c, "gamma")
    _mk_entity(c, "summary-x", page_type="summary")
    _mk_entity(c, "orphan-z", status="orphan_candidate")
    _mk_entity(c, "alpha-alias", canonical_id="alpha", page_type="alias")
    c.execute(
        "MATCH (a:Entity {slug: 'alpha-alias'}), (b:Entity {slug: 'alpha'}) "
        "CREATE (a)-[:ALIAS_OF {run_id: 'm', created_at: '', algorithm: 'l'}]->(b)"
    )
    _mk_source(c, "s1")
    _mk_source(c, "s2")
    _mk_source(c, "s3", domain="NULL")
    _mk_supports(c, "s1", "alpha")
    _mk_supports(c, "s2", "alpha")
    _mk_supports(c, "s1", "beta")
    c.execute("CREATE (d:Domain {name: 'finance', created_at: '', first_run_id: 'm'})")
    c.execute(
        "MATCH (e:Entity {slug: 'alpha'}), (d:Domain {name: 'finance'}) "
        "CREATE (e)-[:BELONGS_TO {run_id: 'm', created_at: '', support_count: 2}]->(d)"
    )
    c.execute(
        "MATCH (a:Entity {slug: 'alpha'}), (b:Entity {slug: 'beta'}) "
        "CREATE (a)-[:LINKS_TO {run_id: 'm', created_at: ''}]->(b)"
    )


_FINALIZE = {"reaped": [{"page_id": "p", "slug": "orphan-z", "page_type": "concept"}],
             "retracted_slugs": ["orphan-z"]}


# ---------- SCORED: entity_reuse ----------

def test_entity_reuse_scored(graph_dir):
    """canonical non-summary: alpha(2 sources), beta(1), gamma(0), orphan-z(0).
    >=2 sources: alpha → 1/4 = 0.25. entity_reuse is now the SCORED graph KPI."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE)
    assert out["scored"]["entity_reuse"] == pytest.approx(0.25)


# ---------- WATCHED ----------

def test_graph_connectivity_two_components(graph_dir):
    """canonical = {alpha,beta,gamma,summary-x,orphan-z} (5). Edge alpha-beta
    → largest component {alpha,beta}=2; gamma/summary-x/orphan-z singletons.
    2/5 = 0.4.  graph_connectivity is now a SCORED graph KPI (§6)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE)
    assert out["scored"]["graph_connectivity"] == pytest.approx(0.4)


def test_orphan_rate(graph_dir):
    """len(reaped)=1 ÷ total entities=6 (5 canonical + 1 alias) = 1/6."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE)
    assert out["watched"]["orphan_rate"] == pytest.approx(1 / 6)


def test_orphan_rate_empty_finalize_is_zero(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, {})
    assert out["watched"]["orphan_rate"] == 0.0


# ---------- DIAGNOSTIC ----------

def test_scored_density_values(graph_dir):
    """link_density + supports_density are now SCORED graph KPIs (§6)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE)
    s = out["scored"]
    assert s["link_density"] == pytest.approx(1 / 5)          # 1 edge / 5 canonical
    assert s["supports_density"] == pytest.approx(3 / 3)      # 3 SUPPORTS / 3 sources


def test_diagnostic_values(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE)
    d = out["diagnostic"]
    assert d["belongs_to_coverage"] == pytest.approx(1 / 5)   # alpha of 5 canonical
    assert d["domain_null_rate"] == pytest.approx(1 / 3)      # s3 of 3 sources
    assert d["domain_breadth"] == pytest.approx(1 / 23)       # 1 domain / 23


def test_return_dict_keys(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE)
    assert set(out) == {"scored", "watched", "diagnostic"}
    # §6: the 4 graph quality KPIs are scored together (combined graph score).
    assert set(out["scored"]) == {
        "entity_reuse", "graph_connectivity", "link_density", "supports_density",
    }
    assert set(out["watched"]) == {
        "orphan_rate", "entity_search_key_resolution",
        # Task #122 event-time context fields (§6)
        "search_key_resolved_at_load_rate",
        "search_key_late_resolution_rate",
        "search_key_never_resolved_rate",
        "search_key_resolved_pre_run_rate",
        "search_key_resolved_cohort_rate",
        "search_key_resolved_age_unknown_rate",
        "search_key_t2_seed_rate",
        "context_build_success_rate",
        "context_explicit_empty_count",
        "context_t1_candidates_mean", "context_t1_delivered_mean",
        "context_t2_candidates_mean", "context_t2_delivered_mean",
        "context_t3_candidates_mean", "context_t3_delivered_mean",
        "context_record_coverage",
        "context_integrity_ok",
        "context_missing_record_count",
        "context_malformed_record_count",
        "context_duplicate_record_count",
        "context_unexpected_record_count",
        "context_wrong_run_record_count",
        "context_expected_count_mismatch",
    }
    assert set(out["diagnostic"]) == {
        "belongs_to_coverage", "domain_null_rate", "domain_breadth",
    }


# ---------- WATCHED: entity_search_key_resolution ----------

def test_entity_search_key_resolution_alias_aware(graph_dir):
    """alpha resolves (active canonical); alpha-alias resolves via ALIAS_OF to
    alpha (active canonical); nonexistent-key does not resolve.
    2 resolved / 3 total → 2/3."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(
            gdb.conn, _FINALIZE,
            pass1_search_keys=["alpha", "alpha-alias", "nonexistent-key"],
        )
    assert out["watched"]["entity_search_key_resolution"] == pytest.approx(2 / 3)


def test_entity_search_key_resolution_none_keys(graph_dir):
    """pass1_search_keys=None → None (not zero — don't conflate no-keys with
    zero-resolution)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE, pass1_search_keys=None)
    assert out["watched"]["entity_search_key_resolution"] is None


def test_entity_search_key_resolution_empty_keys(graph_dir):
    """pass1_search_keys=[] → None (same rationale as None)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, _FINALIZE, pass1_search_keys=[])
    assert out["watched"]["entity_search_key_resolution"] is None


# ---------- union-find unit coverage (empty + singleton + chain) ----------

def test_connectivity_empty_is_none():
    assert _largest_component_fraction([], [("a", "b")]) is None


def test_connectivity_all_singletons():
    """No edges among 3 canonical → largest component size 1 → 1/3."""
    frac = _largest_component_fraction(["a", "b", "c"], [])
    assert frac == pytest.approx(1 / 3)


def test_connectivity_undirected_chain():
    """a->b->c directed edges, treated undirected → one component of 3 → 3/3."""
    frac = _largest_component_fraction(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert frac == 1.0


def test_connectivity_skips_noncanonical_endpoints():
    """An edge to a non-canonical (alias/dangling) slug is ignored; it does not
    merge canonical nodes nor inflate the component."""
    frac = _largest_component_fraction(["a", "b"], [("a", "ghost"), ("ghost", "b")])
    # a and b stay separate singletons → largest = 1, 1/2.
    assert frac == pytest.approx(0.5)


# =====================================================================
# Task #122 §6 — event-time context fields + finalize_ran execution branch
# =====================================================================

from compiler.context_record import (
    ContextEvidence,
    ContextFailureInput,
    ContextIntegrity,
    build_context_record_v1,
)
from common.types import ContextTelemetry, KeyOutcome, TierRecord
from kdb_graph import queries

_ZERO_TIER = TierRecord(0, 0, [])


def _mk_record(source_id: str, outcomes: list[tuple], *,
               tiers=None, status="complete") -> object:
    """One complete/context_failed record. outcomes = [(key, disposition,
    resolved, stamp)] — status='context_failed' synthesizes the frozen shape."""
    if status == "context_failed":
        return build_context_record_v1(
            run_id="m", status="context_failed",
            failure_input=ContextFailureInput(
                source_id=source_id, configured_t2_mode="structured",
                effective_t2_strategy="structured_keys", keys_emitted=["k"],
                domain_scope=None, page_cap=50))
    t1, t2, t3 = tiers or (_ZERO_TIER, _ZERO_TIER, _ZERO_TIER)
    telemetry = ContextTelemetry(
        source_id=source_id,
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=[k for k, _d, _r, _s in outcomes],
        key_outcomes=[KeyOutcome(k, d, r, s) for k, d, r, s in outcomes],
        t1=t1, t2=t2, t3=t3,
        candidate_universe_size=10,
        domain_scope="value-investing",
        cold_start=False,
        max_hops=1,
        page_cap=50,
    )
    return build_context_record_v1(run_id="m", status="complete", telemetry=telemetry)


def _evidence(records, expected_ids, *, complete=True) -> ContextEvidence:
    matched = expected_ids & {r.source_id for r in records}
    return ContextEvidence(
        records=records,
        expected_ids=set(expected_ids),
        matched_ids=matched,
        coverage=(len(matched) / len(expected_ids)) if expected_ids else None,
        complete=complete,
        integrity=ContextIntegrity(0, 0, 0, 0, 0, False),
    )


def _seed_late_graph(gdb):
    """Minimal graph for the L/V read: 'late-hit' exists post-run (an
    event-time miss that became resolvable); 'never-hit' does not."""
    c = gdb.conn
    _mk_entity(c, "late-hit")


def test_context_fields_rate_equations(graph_dir):
    """N=5: R=3 (alpha cohort stamp 'm'; beta ×2 pre_run stamp 'r-old'),
    L=1 (late-hit resolves post-run), V=1 (never-hit). R+L+V==N;
    pre+cohort+unknown==R; all rates divide by N."""
    outcomes = [
        ("alpha", "resolved_t2_seed", "alpha", "m"),
        ("k1", "resolved_t2_seed", "beta", "r-old"),
        ("k2", "resolved_duplicate_seed", "beta", "r-old"),
        ("late-hit", "unresolved", None, None),
        ("never-hit", "unresolved", None, None),
    ]
    rec = _mk_record("src-a", outcomes)
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        _seed_late_graph(gdb)
        out = compute_graph(gdb.conn, _FINALIZE, run_id="m", context_evidence=ev)
    w = out["watched"]
    assert w["search_key_resolved_at_load_rate"] == pytest.approx(3 / 5)
    assert w["search_key_late_resolution_rate"] == pytest.approx(1 / 5)
    assert w["search_key_never_resolved_rate"] == pytest.approx(1 / 5)
    assert w["search_key_resolved_cohort_rate"] == pytest.approx(1 / 5)
    assert w["search_key_resolved_pre_run_rate"] == pytest.approx(2 / 5)
    # zero numerator with N>0 → 0.0 (NOT None)
    assert w["search_key_resolved_age_unknown_rate"] == 0.0
    assert w["search_key_t2_seed_rate"] == pytest.approx(2 / 5)
    assert w["context_build_success_rate"] == pytest.approx(1.0)
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is True


def test_context_fields_n_zero_rates_none(graph_dir):
    """N==0 (a complete record with zero emissions) → key rates None."""
    rec = _mk_record("src-a", [])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, run_id="m", context_evidence=ev)
    w = out["watched"]
    assert w["search_key_resolved_at_load_rate"] is None
    assert w["search_key_late_resolution_rate"] is None
    assert w["search_key_never_resolved_rate"] is None
    assert w["search_key_t2_seed_rate"] is None


def test_context_failed_in_coverage_not_in_means(graph_dir):
    """context_failed records count for coverage + build-success denominator
    but NEVER for the tier means (complete records only)."""
    good = _mk_record(
        "src-a", [("alpha", "resolved_t2_seed", "alpha", "m")],
        tiers=(TierRecord(2, 1, ["x"]), TierRecord(4, 3, ["a", "b", "c"]),
               TierRecord(6, 0, [])))
    failed = _mk_record("src-b", [], status="context_failed")
    ev = _evidence([good, failed], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, run_id="m", context_evidence=ev)
    w = out["watched"]
    assert w["context_record_coverage"] == 1.0          # failed IS captured
    assert w["context_build_success_rate"] == pytest.approx(0.5)
    assert w["context_t1_candidates_mean"] == pytest.approx(2.0)  # complete only
    assert w["context_t1_delivered_mean"] == pytest.approx(1.0)
    assert w["context_t2_candidates_mean"] == pytest.approx(4.0)
    assert w["context_t2_delivered_mean"] == pytest.approx(3.0)
    assert w["context_t3_candidates_mean"] == pytest.approx(6.0)
    assert w["context_t3_delivered_mean"] == pytest.approx(0.0)


def test_evidence_incomplete_nulls_aggregates_keeps_integrity(graph_dir):
    """evidence_complete == False ⇒ substantive aggregates None; coverage +
    integrity diagnostics still emitted."""
    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m")])
    ev = _evidence([rec], {"src-a"}, complete=False)
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, run_id="m", context_evidence=ev)
    w = out["watched"]
    for k in ("search_key_resolved_at_load_rate", "search_key_t2_seed_rate",
              "context_build_success_rate", "context_explicit_empty_count",
              "context_t1_candidates_mean"):
        assert w[k] is None, k
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is False      # expected non-empty → bool False
    assert w["context_missing_record_count"] == 0


def test_no_evidence_all_aggregates_none(graph_dir):
    """Pre-#122 artifact (context_evidence=None): aggregates None, integrity
    counts 0, coverage/integrity_ok None — and no resolver read fires."""
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, run_id="m", context_evidence=None)
    w = out["watched"]
    assert w["search_key_resolved_at_load_rate"] is None
    assert w["context_record_coverage"] is None
    assert w["context_integrity_ok"] is None
    assert w["context_missing_record_count"] == 0
    assert w["context_expected_count_mismatch"] is False


def test_explicit_empty_count(graph_dir):
    rec = _mk_record("src-a", [])
    # flip strategy to explicit_empty via a custom telemetry
    telemetry = ContextTelemetry(
        source_id="src-b", configured_t2_mode="structured",
        effective_t2_strategy="explicit_empty", keys_emitted=[], key_outcomes=[],
        t1=TierRecord(0, 0, []), t2=TierRecord(0, 0, []), t3=TierRecord(0, 0, []),
        candidate_universe_size=0, domain_scope=None, cold_start=False,
        max_hops=1, page_cap=50)
    rec2 = build_context_record_v1(run_id="m", status="complete", telemetry=telemetry)
    ev = _evidence([rec, rec2], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, run_id="m", context_evidence=ev)
    assert out["watched"]["context_explicit_empty_count"] == 1


# ---------- R4 F1 execution branch (finalize_ran=False) ----------

def test_no_finalize_branch_skips_finalized_reads(graph_dir, monkeypatch):
    """R4 F1 pin: on the no-finalize branch an ordinary finalized graph-quality
    read is NEVER executed; finalized keys emit None; Task-122 fields still
    compute; the unresolved resolver runs (unresolved evidence exists)."""
    def boom(*_args, **_kwargs):
        raise AssertionError("finalized graph-quality read executed on no-finalize branch")
    monkeypatch.setattr("compiler.kpi.graph.queries.active_canonical_entity_slugs", boom)
    monkeypatch.setattr("compiler.kpi.graph.queries.total_source_count", boom)
    monkeypatch.setattr("compiler.kpi.graph.queries.links_to_edges", boom)

    resolver_calls: list[list[str]] = []
    real_resolve = queries.resolve_to_canonical_slugs

    def counting(conn, keys):
        resolver_calls.append(list(keys))
        return real_resolve(conn, keys)
    monkeypatch.setattr("compiler.kpi.graph.queries.resolve_to_canonical_slugs", counting)

    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m"),
                               ("never-hit", "unresolved", None, None)])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, finalize_ran=False,
                            run_id="m", context_evidence=ev)
    assert out["scored"] == {"entity_reuse": None, "graph_connectivity": None,
                             "link_density": None, "supports_density": None}
    w = out["watched"]
    assert w["orphan_rate"] is None
    assert w["entity_search_key_resolution"] is None
    assert out["diagnostic"] == {"belongs_to_coverage": None,
                                 "domain_null_rate": None, "domain_breadth": None}
    # Task-122 fields retained; the L/V read fired exactly once on the
    # unresolved population only.
    assert resolver_calls == [["never-hit"]]
    assert w["search_key_resolved_at_load_rate"] == pytest.approx(0.5)
    assert w["search_key_never_resolved_rate"] == pytest.approx(0.5)
    assert w["search_key_late_resolution_rate"] == 0.0


def test_no_finalize_branch_no_query_when_no_unresolved(graph_dir, monkeypatch):
    """The L/V resolver read is skipped entirely when the unresolved-at-load
    population is empty (R4 F1: no wasted query)."""
    def boom_resolve(*_args, **_kwargs):
        raise AssertionError("resolver read fired with an empty unresolved population")
    monkeypatch.setattr("compiler.kpi.graph.queries.resolve_to_canonical_slugs", boom_resolve)

    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m")])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, _FINALIZE, finalize_ran=False,
                            run_id="m", context_evidence=ev)
    w = out["watched"]
    assert w["search_key_resolved_at_load_rate"] == 1.0
    assert w["search_key_late_resolution_rate"] == 0.0
    assert w["search_key_never_resolved_rate"] == 0.0


def test_finalize_branch_legacy_resolution_unchanged_with_evidence(graph_dir):
    """On the finalize path the legacy entity_search_key_resolution is
    byte-identical whether or not context evidence is present."""
    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m")])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out_no_ev = compute_graph(
            gdb.conn, _FINALIZE,
            pass1_search_keys=["alpha", "alpha-alias", "nonexistent-key"])
        out_ev = compute_graph(
            gdb.conn, _FINALIZE,
            pass1_search_keys=["alpha", "alpha-alias", "nonexistent-key"],
            run_id="m", context_evidence=ev)
    assert (out_no_ev["watched"]["entity_search_key_resolution"]
            == out_ev["watched"]["entity_search_key_resolution"]
            == pytest.approx(2 / 3))
