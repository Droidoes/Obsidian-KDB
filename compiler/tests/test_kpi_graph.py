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
    """Canonical entities: alpha, beta, gamma, summary-x (summary), dep-z
    (status deprecated — #130: invisible to every KPI denominator except the
    deprecation_rate numerator). Alias: alpha-alias (canonical_id=alpha).
    Sources: s1, s2 (finance), s3 (NULL domain). SUPPORTS: alpha<-s1,s2;
    beta<-s1; gamma none. Domain finance + BELONGS_TO from alpha. LINKS_TO:
    alpha->beta (the only edge; both canonical → one 2-node component, the
    rest singletons)."""
    c = gdb.conn
    _mk_entity(c, "alpha")
    _mk_entity(c, "beta")
    _mk_entity(c, "gamma")
    _mk_entity(c, "summary-x", page_type="summary")
    _mk_entity(c, "dep-z", status="deprecated")
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


# ---------- SCORED: entity_reuse ----------

def test_entity_reuse_scored(graph_dir):
    """ACTIVE canonical non-summary (#130): alpha(2 sources), beta(1), gamma(0);
    dep-z excluded (deprecated). >=2 sources: alpha → 1/3."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn)
    assert out["scored"]["entity_reuse"] == pytest.approx(1 / 3)


# ---------- WATCHED ----------

def test_graph_connectivity_two_components(graph_dir):
    """active canonical = {alpha,beta,gamma,summary-x} (4 — dep-z excluded).
    Edge alpha-beta → largest component {alpha,beta}=2 → 2/4 = 0.5."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn)
    assert out["scored"]["graph_connectivity"] == pytest.approx(0.5)


def test_deprecation_rate(graph_dir):
    """dep-z (status='deprecated', last_run_id='m') ÷ total entities=6
    (4 active canonical + 1 deprecated + 1 alias) = 1/6."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, run_id="m")
    assert out["watched"]["deprecation_rate"] == pytest.approx(1 / 6)


def test_deprecation_rate_unknown_run_is_zero(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, run_id="zzz-no-such-run")
    assert out["watched"]["deprecation_rate"] == 0.0


def test_deprecation_rate_no_run_id_is_none(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn)
    assert out["watched"]["deprecation_rate"] is None


# ---------- DIAGNOSTIC ----------

def test_scored_density_values(graph_dir):
    """link_density + supports_density are now SCORED graph KPIs (§6)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn)
    s = out["scored"]
    assert s["link_density"] == pytest.approx(1 / 4)          # 1 active edge / 4 active canonical
    assert s["supports_density"] == pytest.approx(3 / 3)      # 3 SUPPORTS / 3 sources


def test_diagnostic_values(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn)
    d = out["diagnostic"]
    assert d["belongs_to_coverage"] == pytest.approx(1 / 4)   # alpha of 4 active canonical
    assert d["domain_null_rate"] == pytest.approx(1 / 3)      # s3 of 3 sources
    assert d["domain_breadth"] == pytest.approx(1 / 23)       # 1 domain / 23


def test_return_dict_keys(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn)
    assert set(out) == {"scored", "watched", "diagnostic"}
    # §6: the 4 graph quality KPIs are scored together (combined graph score).
    assert set(out["scored"]) == {
        "entity_reuse", "graph_connectivity", "link_density", "supports_density",
    }
    assert set(out["watched"]) == {
        "deprecation_rate", "entity_search_key_resolution",
        # Task #123 §4.6 event-time search fields (B5)
        "search_expression_matched_rate",
        "search_expression_unresolved_rate",
        "search_hit_recency_pre_run_rate",
        "search_hit_recency_cohort_rate",
        "search_hit_recency_age_unknown_rate",
        "search_stage2_budget_bound_rate",
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
            gdb.conn,
            pass1_search_keys=["alpha", "alpha-alias", "nonexistent-key"],
        )
    assert out["watched"]["entity_search_key_resolution"] == pytest.approx(2 / 3)


def test_entity_search_key_resolution_none_keys(graph_dir):
    """pass1_search_keys=None → None (not zero — don't conflate no-keys with
    zero-resolution)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, pass1_search_keys=None)
    assert out["watched"]["entity_search_key_resolution"] is None


def test_entity_search_key_resolution_empty_keys(graph_dir):
    """pass1_search_keys=[] → None (same rationale as None)."""
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out = compute_graph(gdb.conn, pass1_search_keys=[])
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
# #123 P3a.3 — V1/V2 dispatching readers (blueprint §4.6): the seven
# search_key_* series are retired (one rename, one per-key→per-hit
# re-baseline, three clean cuts); the KPI-time resolver read is dead.
# =====================================================================

from compiler.context_record import (
    ContextEvidence,
    ContextIntegrity,
    ContextRecordV1,
    ContextRecordV2,
    KeyOutcomeV1,
    KeyOutcomeV2,
)
from common.types import SearchHitSummary, SearchSummary, TierRecord

_ZERO_TIER = TierRecord(0, 0, [])

_RETIRED_SEARCH_KEY_SERIES = (
    "search_key_resolved_at_load_rate",
    "search_key_late_resolution_rate",
    "search_key_never_resolved_rate",
    "search_key_resolved_pre_run_rate",
    "search_key_resolved_cohort_rate",
    "search_key_resolved_age_unknown_rate",
    "search_key_t2_seed_rate",
)


def _mk_record(source_id: str, outcomes: list[tuple], *,
               tiers=None, status="complete") -> object:
    """One V1 complete/context_failed record. outcomes = [(key, disposition,
    resolved, stamp)] — status='context_failed' synthesizes the frozen shape.
    #123 P3a.2b: the V1 factory is retired (parse-only history) — V1 records
    are built directly."""
    if status == "context_failed":
        return ContextRecordV1(
            schema_version=1, run_id="m", source_id=source_id,
            status="context_failed",
            configured_t2_mode="structured",
            effective_t2_strategy="structured_keys",
            keys_emitted=["k"], key_outcomes=[],
            t1=_ZERO_TIER, t2=_ZERO_TIER, t3=_ZERO_TIER,
            candidate_universe_size=None, domain_scope=None,
            cold_start=None, max_hops=None, page_cap=50)
    t1, t2, t3 = tiers or (_ZERO_TIER, _ZERO_TIER, _ZERO_TIER)
    return ContextRecordV1(
        schema_version=1, run_id="m", source_id=source_id,
        status="complete",
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=[k for k, _d, _r, _s in outcomes],
        key_outcomes=[KeyOutcomeV1(k, d, r, s) for k, d, r, s in outcomes],
        t1=t1, t2=t2, t3=t3,
        candidate_universe_size=10,
        domain_scope="value-investing",
        cold_start=False,
        max_hops=1,
        page_cap=50,
    )


def _outcome_v2(expression: str, status: str, *, annotation=None,
                stamp=None, recency=None) -> KeyOutcomeV2:
    return KeyOutcomeV2(
        expression=expression, status=status, annotation=annotation,
        matched_first_run_id=stamp, match_recency=recency)


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
        artifact_path="/state/runs/m/search/s.json",
        search_snapshot_hash="sha256:abc", space_entity_count=0, hits=(),
    )
    return SearchSummary(**{**base, **overrides})


def _hit(slug: str, recency: str, *, first_run_id="r0") -> SearchHitSummary:
    return SearchHitSummary(
        slug=slug, first_run_id=first_run_id, match_recency=recency,
        matched_expressions=("k",))


def _mk_record_v2(source_id: str, outcomes: list[KeyOutcomeV2] | None = None, *,
                  tiers=None, search=None, status="complete") -> ContextRecordV2:
    """One V2 record, built directly (mirrors _mk_record). `search` is the
    §5.2 summary or None (no search ran)."""
    if status == "context_failed":
        return ContextRecordV2(
            schema_version=2, run_id="m", source_id=source_id,
            status="context_failed",
            keys_emitted=["k"], key_outcomes=[],
            t1=_ZERO_TIER, t2=_ZERO_TIER, t3=_ZERO_TIER,
            candidate_universe_size=None, domain_scope=None,
            cold_start=None, page_cap=50, search=search)
    outcomes = outcomes or []
    t1, t2, t3 = tiers or (_ZERO_TIER, _ZERO_TIER, _ZERO_TIER)
    return ContextRecordV2(
        schema_version=2, run_id="m", source_id=source_id,
        status="complete",
        keys_emitted=[o.expression for o in outcomes],
        key_outcomes=list(outcomes),
        t1=t1, t2=t2, t3=t3,
        candidate_universe_size=10,
        domain_scope="value-investing",
        cold_start=False,
        page_cap=50,
        search=search,
    )


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


def test_retired_search_key_series_are_gone(graph_dir):
    """§4.6: the seven search_key_* series are removed — one rename, one
    per-key→per-hit re-baseline, three clean cuts, no tombstones."""
    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m")])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    for key in _RETIRED_SEARCH_KEY_SERIES:
        assert key not in out["watched"]


def test_expression_rates_mixed_v1_v2(graph_dir):
    """The RENAME: search_expression_matched_rate is resolved_at_load's
    population under the V2 vocabulary. V1 maps disposition != 'unresolved';
    V2 reads status — one combined population across a mixed run."""
    v1 = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m"),
                              ("ghost", "unresolved", None, None)])
    v2 = _mk_record_v2("src-b", [
        _outcome_v2("k1", "matched", stamp="m", recency="cohort"),
        _outcome_v2("k2", "unresolved", annotation="no_match")])
    ev = _evidence([v1, v2], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    w = out["watched"]
    assert w["search_expression_matched_rate"] == pytest.approx(0.5)
    assert w["search_expression_unresolved_rate"] == pytest.approx(0.5)
    assert w["context_build_success_rate"] == 1.0
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is True


def test_hit_recency_rates_are_per_hit(graph_dir):
    """§4.6's explicit RE-BASELINE (denominator change, NOT a rename): the
    recency series divide by HITS, not keys. 2 matched keys but 3 hits —
    a per-key read would give halves; the per-hit read gives thirds."""
    v2 = _mk_record_v2("src-a", [
        _outcome_v2("k1", "matched", stamp="m", recency="cohort"),
        _outcome_v2("k2", "matched", stamp="r-old", recency="pre_run")],
        search=_search_summary(hits=(
            _hit("a", "cohort", first_run_id="m"),
            _hit("b", "cohort", first_run_id="m"),
            _hit("c", "pre_run", first_run_id="r-old"))))
    ev = _evidence([v2], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    w = out["watched"]
    assert w["search_hit_recency_cohort_rate"] == pytest.approx(2 / 3)
    assert w["search_hit_recency_pre_run_rate"] == pytest.approx(1 / 3)
    assert w["search_hit_recency_age_unknown_rate"] == 0.0


def test_hit_recency_includes_context_failed_search_sections(graph_dir):
    """B8: a context_failed record's non-null search section still feeds the
    per-hit population (the search completed before the builder raised)."""
    good = _mk_record_v2("src-a", [
        _outcome_v2("k1", "matched", stamp="m", recency="cohort")],
        search=_search_summary(hits=(_hit("a", "cohort", first_run_id="m"),)))
    failed = _mk_record_v2("src-b", status="context_failed",
                           search=_search_summary(
                               hits=(_hit("b", "pre_run", first_run_id="r-old"),)))
    ev = _evidence([good, failed], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    w = out["watched"]
    assert w["search_hit_recency_cohort_rate"] == pytest.approx(0.5)
    assert w["search_hit_recency_pre_run_rate"] == pytest.approx(0.5)
    assert w["context_build_success_rate"] == pytest.approx(0.5)


def test_expression_and_recency_rates_none_on_empty_populations(graph_dir):
    """N==0 expressions ⇒ both expression rates None; zero hits ⇒ recency
    rates None; a search-ran record still answers stage2_budget_bound (0.0)."""
    v1 = _mk_record("src-a", [])
    v2 = _mk_record_v2("src-b", [], search=_search_summary(query_kind="state_c"))
    ev = _evidence([v1, v2], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    w = out["watched"]
    assert w["search_expression_matched_rate"] is None
    assert w["search_expression_unresolved_rate"] is None
    assert w["search_hit_recency_cohort_rate"] is None
    assert w["search_hit_recency_pre_run_rate"] is None
    assert w["search_hit_recency_age_unknown_rate"] is None
    assert w["search_stage2_budget_bound_rate"] == 0.0


def test_stage2_budget_bound_rate(graph_dir):
    """B5/§4.5: the 0/N fail-safe evidence, aggregated over search-ran
    records — 1 of 2 bound ⇒ 0.5. None when no search ran (V1-only run)."""
    v2_bound = _mk_record_v2("src-a", [
        _outcome_v2("k1", "matched", stamp="m", recency="cohort")],
        search=_search_summary(stage2_budget_bound=True))
    v2_free = _mk_record_v2("src-b", [
        _outcome_v2("k2", "unresolved", annotation="no_match")],
        search=_search_summary(stage2_budget_bound=False))
    ev = _evidence([v2_bound, v2_free], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    assert out["watched"]["search_stage2_budget_bound_rate"] == pytest.approx(0.5)

    v1_only = _evidence([_mk_record("src-c", [])], {"src-c"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=v1_only)
    assert out["watched"]["search_stage2_budget_bound_rate"] is None


def test_context_failed_in_coverage_not_in_means(graph_dir):
    """context_failed records count for coverage + build-success denominator
    but NEVER for the tier means (complete records only) — mixed V1/V2."""
    good = _mk_record(
        "src-a", [("alpha", "resolved_t2_seed", "alpha", "m")],
        tiers=(TierRecord(2, 1, ["x"]), TierRecord(4, 3, ["a", "b", "c"]),
               TierRecord(6, 0, [])))
    failed = _mk_record_v2("src-b", status="context_failed",
                           search=_search_summary())   # B8: non-null search
    ev = _evidence([good, failed], {"src-a", "src-b"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
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
        out = compute_graph(gdb.conn, context_evidence=ev)
    w = out["watched"]
    for k in ("search_expression_matched_rate", "search_hit_recency_cohort_rate",
              "search_stage2_budget_bound_rate", "context_build_success_rate",
              "context_explicit_empty_count", "context_t1_candidates_mean"):
        assert w[k] is None, k
    assert w["context_record_coverage"] == 1.0
    assert w["context_integrity_ok"] is False      # expected non-empty → bool False
    assert w["context_missing_record_count"] == 0


def test_no_evidence_all_aggregates_none(graph_dir):
    """Pre-#122 artifact (context_evidence=None): aggregates None, integrity
    counts 0, coverage/integrity_ok None — and no resolver read fires."""
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=None)
    w = out["watched"]
    assert w["search_expression_matched_rate"] is None
    assert w["search_hit_recency_cohort_rate"] is None
    assert w["search_stage2_budget_bound_rate"] is None
    assert w["context_record_coverage"] is None
    assert w["context_integrity_ok"] is None
    assert w["context_missing_record_count"] == 0
    assert w["context_expected_count_mismatch"] is False


def test_explicit_empty_count_mixed_v1_v2(graph_dir):
    """§4.6 re-source: V1 counts effective_t2_strategy == 'explicit_empty'
    (complete records); V2 counts search.query_kind == 'state_c' over records
    where a search ran (search section non-null). Population change, stated:
    a pre-Pass-1 V2 source cannot answer."""
    v1_normal = _mk_record("src-a", [])
    v1_empty = ContextRecordV1(
        schema_version=1, run_id="m", source_id="src-b", status="complete",
        configured_t2_mode="structured", effective_t2_strategy="explicit_empty",
        keys_emitted=[], key_outcomes=[],
        t1=_ZERO_TIER, t2=_ZERO_TIER, t3=_ZERO_TIER,
        candidate_universe_size=0, domain_scope=None, cold_start=False,
        max_hops=1, page_cap=50)
    v2_state_c = _mk_record_v2("src-c", [], search=_search_summary(query_kind="state_c"))
    v2_state_b = _mk_record_v2(
        "src-d", [_outcome_v2("k1", "unresolved", annotation="no_match")],
        search=_search_summary(query_kind="state_b"))
    v2_no_search = _mk_record_v2("src-e", [], search=None)
    ev = _evidence(
        [v1_normal, v1_empty, v2_state_c, v2_state_b, v2_no_search],
        {"src-a", "src-b", "src-c", "src-d", "src-e"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    assert out["watched"]["context_explicit_empty_count"] == 2


# ---------- R4 F1 execution branch (finalize_ran=False) ----------

def test_no_finalize_branch_skips_finalized_reads(graph_dir, monkeypatch):
    """R4 F1 pin: on the no-finalize branch an ordinary finalized graph-quality
    read is NEVER executed; finalized keys emit None; the context fields still
    compute — and #123 P3a.3: WITHOUT any resolver read, even with an
    unresolved population present (late/never classification is dead)."""
    def boom(*_args, **_kwargs):
        raise AssertionError("finalized graph-quality read executed on no-finalize branch")
    monkeypatch.setattr("compiler.kpi.graph.queries.active_canonical_entity_slugs", boom)
    monkeypatch.setattr("compiler.kpi.graph.queries.total_source_count", boom)
    monkeypatch.setattr("compiler.kpi.graph.queries.links_to_edges", boom)
    monkeypatch.setattr("compiler.kpi.graph.queries.resolve_to_canonical_slugs", boom)

    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m"),
                               ("never-hit", "unresolved", None, None)])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, finalize_ran=False,
                            context_evidence=ev)
    assert out["scored"] == {"entity_reuse": None, "graph_connectivity": None,
                             "link_density": None, "supports_density": None}
    w = out["watched"]
    assert w["deprecation_rate"] is None
    assert w["entity_search_key_resolution"] is None
    assert out["diagnostic"] == {"belongs_to_coverage": None,
                                 "domain_null_rate": None, "domain_breadth": None}
    # Event-time rates computed WITHOUT the (deleted) L/V resolver read.
    assert w["search_expression_matched_rate"] == pytest.approx(0.5)
    assert w["search_expression_unresolved_rate"] == pytest.approx(0.5)


def test_no_resolver_call_in_the_context_evidence_path(graph_dir, monkeypatch):
    """§4.6: the KPI-time resolver recomputation dies with the seven series —
    on the finalize path the context-evidence computation fires NO resolver
    call either (the only remaining resolver use is the established
    entity_search_key_resolution series, driven by pass1_search_keys)."""
    def boom_resolve(*_args, **_kwargs):
        raise AssertionError("resolver read fired from the context-evidence path")
    monkeypatch.setattr(
        "compiler.kpi.graph.queries.resolve_to_canonical_slugs", boom_resolve)

    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m"),
                               ("never-hit", "unresolved", None, None)])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        out = compute_graph(gdb.conn, context_evidence=ev)
    w = out["watched"]
    assert w["search_expression_matched_rate"] == pytest.approx(0.5)
    assert w["search_expression_unresolved_rate"] == pytest.approx(0.5)


def test_finalize_branch_legacy_resolution_unchanged_with_evidence(graph_dir):
    """On the finalize path the legacy entity_search_key_resolution is
    byte-identical whether or not context evidence is present."""
    rec = _mk_record("src-a", [("alpha", "resolved_t2_seed", "alpha", "m")])
    ev = _evidence([rec], {"src-a"})
    with GraphDB(graph_dir) as gdb:
        _seed(gdb)
        out_no_ev = compute_graph(
            gdb.conn,
            pass1_search_keys=["alpha", "alpha-alias", "nonexistent-key"])
        out_ev = compute_graph(
            gdb.conn,
            pass1_search_keys=["alpha", "alpha-alias", "nonexistent-key"],
            context_evidence=ev)
    assert (out_no_ev["watched"]["entity_search_key_resolution"]
            == out_ev["watched"]["entity_search_key_resolution"]
            == pytest.approx(2 / 3))
