"""GRAPH-family benchmark KPI computation over a run's Kuzu knowledge graph (#109).

compute_graph(conn, finalize_artifacts)
    → {"scored": {...}, "watched": {...}, "diagnostic": {...}}

SINGLE-DOOR DISCIPLINE: every graph read goes through kdb_graph.queries — this
module owns only the computation (ratios, union-find), never raw Cypher.

None-on-zero everywhere: every ratio returns None when its denominator is 0,
consistent with kdb_graph_compiler.kpi.processing.

Task #122 §6/§7: compute_graph gains an execution branch keyed on
`finalize_ran`. When the run never crossed the finalize boundary
(finalize_ran=False), finalized-run graph quality is INELIGIBLE — none of the
finalized graph-quality or legacy-resolution reads execute (their established
keys emit None); the event-time fields are computed from the reconciled
context evidence instead. #123 P3a.3 §4.6 reshaped those fields for the V2
record (mixed V1/V2 populations, per-record schema dispatch; per-hit recency
baseline) and retired the KPI-time resolver read along with the seven
search_key_* series — the evidence computation performs NO graph read.

Scored set (2026-06-06 §6 — combined graph score): the four graph quality KPIs
``entity_reuse`` · ``graph_connectivity`` · ``link_density`` · ``supports_density``
(all ↑) are scored together — no single one suffices (entity_reuse alone inverts
the signal, rewarding the sparser graph), but combined they capture graph-build
quality. Weighting + direction live in kdb_graph_compiler.kpi.score. ``dangling_link_rate``
was deleted (degenerate — rewarded under-linking, trivially 0 on a sparse graph);
its emitted-link plumbing (the ``compile_result`` param + flattener) went with it.
"""
from __future__ import annotations

from typing import Any

import kuzu

from kdb_graph_compiler.context_record import ContextEvidence
from kdb_graph import queries

# Fixed domain taxonomy size for domain_breadth (distinct domains / 23).
DOMAIN_TAXONOMY_SIZE = 23


def _largest_component_fraction(
    canonical_slugs: list[str],
    edges: list[tuple[str, str]],
) -> float | None:
    """Largest-connected-component size ÷ total canonical entities, treating
    LINKS_TO as UNDIRECTED (union-find).

    Seeding: the full canonical slug set first (so an isolated canonical entity
    is a size-1 component), THEN union over edges whose BOTH endpoints are
    canonical (edges touching alias/dangling slugs are skipped — they are not
    members of the population being measured).

    0 canonical entities → None.
    """
    if not canonical_slugs:
        return None

    parent: dict[str, str] = {s: s for s in canonical_slugs}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        # path compression
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    members = set(canonical_slugs)
    for src, dst in edges:
        if src in members and dst in members:
            union(src, dst)

    sizes: dict[str, int] = {}
    for s in canonical_slugs:
        root = find(s)
        sizes[root] = sizes.get(root, 0) + 1

    return max(sizes.values()) / len(canonical_slugs)


def _context_watched_fields(
    *,
    evidence: ContextEvidence | None,
) -> dict[str, Any]:
    """Event-time search/context watched fields from reconciled context
    evidence (Task #122 §6, reshaped by #123 P3a.3 §4.6).

    Mixed V1/V2 populations with per-record schema dispatch (B11):
    V1 outcomes read `disposition` (matched ⟺ disposition != "unresolved");
    V2 outcomes read `status`. N = all emitted expressions across complete
    records; expression rates divide by N (N == 0 → None).

    Hit recency is a SEPARATE, per-HIT population (§4.6 re-baseline — NOT a
    rename): hits come from every record whose search section is non-null
    (context_failed records included, B8 — the search completed before the
    builder raised); each rate divides by total hits. V1 records have no
    search section and contribute no hits. stage2_budget_bound aggregates
    over search-ran records (any status) — None when no search ran.

    The frozen integrity diagnostics + coverage are emitted ALWAYS (None only
    when expected is empty); the substantive aggregates require
    evidence.complete — an integrity failure nulls the aggregates but never
    hides coverage/integrity. NO graph read happens here: the KPI-time
    resolver recomputation died with the seven search_key_* series.
    """
    records = evidence.records if evidence is not None else []
    complete_records = [r for r in records if r.status == "complete"]
    evidence_complete = evidence.complete if evidence is not None else False
    integrity = (evidence.integrity if evidence is not None else None)

    fields: dict[str, Any] = {
        # §5 frozen integrity diagnostics — emitted even when aggregates None.
        "context_record_coverage": evidence.coverage if evidence is not None else None,
        "context_integrity_ok": (
            evidence.complete
            if evidence is not None and evidence.expected_ids else None
        ),
        "context_missing_record_count": integrity.missing if integrity else 0,
        "context_malformed_record_count": integrity.malformed if integrity else 0,
        "context_duplicate_record_count": integrity.duplicate if integrity else 0,
        "context_unexpected_record_count": integrity.unexpected if integrity else 0,
        "context_wrong_run_record_count": integrity.wrong_run if integrity else 0,
        "context_expected_count_mismatch": (
            integrity.expected_count_mismatch if integrity else False),
    }

    def _gated(value):
        """evidence_complete == False ⇒ substantive aggregates None."""
        return value if evidence_complete else None

    # Expression population — per-record schema dispatch (V1 disposition vs
    # V2 status), one combined rate across a mixed run.
    matched = unresolved = 0
    for r in complete_records:
        for o in r.key_outcomes:
            if r.schema_version == 1:
                if o.disposition == "unresolved":
                    unresolved += 1
                else:
                    matched += 1
            elif o.status == "matched":
                matched += 1
            else:
                unresolved += 1
    n = matched + unresolved

    # Per-hit recency population — hits from EVERY record with a non-null
    # search section (B8: context_failed records still feed it).
    searches = [r.search for r in records if getattr(r, "search", None) is not None]
    hits = [h for s in searches for h in s.hits]
    h = len(hits)
    recency_counts = {"pre_run": 0, "cohort": 0, "age_unknown": 0}
    for hit in hits:
        recency_counts[hit.match_recency] += 1

    def _hit_rate(recency: str) -> float | None:
        return (recency_counts[recency] / h) if h else None

    def _tier_mean(tier: str, field: str) -> float | None:
        if not complete_records:
            return None
        return (sum(getattr(getattr(r, tier), field) for r in complete_records)
                / len(complete_records))

    fields.update({
        "search_expression_matched_rate": _gated((matched / n) if n else None),
        "search_expression_unresolved_rate": _gated((unresolved / n) if n else None),
        "search_hit_recency_pre_run_rate": _gated(_hit_rate("pre_run")),
        "search_hit_recency_cohort_rate": _gated(_hit_rate("cohort")),
        "search_hit_recency_age_unknown_rate": _gated(_hit_rate("age_unknown")),
        # B5: 0/N fail-safe evidence over search-ran records (any status).
        "search_stage2_budget_bound_rate": _gated(
            (sum(1 for s in searches if s.stage2_budget_bound) / len(searches))
            if searches else None),
        "context_build_success_rate": _gated(
            len(complete_records) / len(records) if records else None),
        # §4.6 re-source: V1 reads effective_t2_strategy (complete records);
        # V2 reads the search section (any status — B8 search survives).
        "context_explicit_empty_count": _gated(
            sum(1 for r in records
                if (r.schema_version == 1
                    and r.status == "complete"
                    and r.effective_t2_strategy == "explicit_empty")
                or (r.schema_version == 2
                    and r.search is not None
                    and r.search.query_kind == "state_c"))),
        "context_t1_candidates_mean": _gated(_tier_mean("t1", "candidates")),
        "context_t1_delivered_mean": _gated(_tier_mean("t1", "delivered")),
        "context_t2_candidates_mean": _gated(_tier_mean("t2", "candidates")),
        "context_t2_delivered_mean": _gated(_tier_mean("t2", "delivered")),
        "context_t3_candidates_mean": _gated(_tier_mean("t3", "candidates")),
        "context_t3_delivered_mean": _gated(_tier_mean("t3", "delivered")),
    })
    return fields


def compute_graph(
    conn: kuzu.Connection,
    *,
    finalize_ran: bool = True,
    run_id: str | None = None,
    pass1_search_keys: list[str] | None = None,
    context_evidence: ContextEvidence | None = None,
) -> dict:
    """Compute GRAPH-family KPIs for one benchmark run.

    Parameters
    ----------
    conn:
        Live Kuzu connection to the graph the run built.
    run_id:
        The run being measured. Feeds deprecation_rate (#130): newly deprecated
        pages are read from the graph itself (status='deprecated' AND
        last_run_id=run_id — the finalize mark persists both). None →
        deprecation_rate None (don't conflate unknown-run with zero-deprecation).
    finalize_ran:
        Task #122 §7 execution branch. False = the run did not complete the
        finalize boundary — finalized graph-quality and legacy-resolution
        reads are NEVER executed (their established keys emit None); only the
        event-time evidence fields compute (no graph read at all on this
        path — #123 P3a.3 §4.6 retired the KPI-time resolver read).
    pass1_search_keys:
        Union/concat of all emitted entity_search_keys across the run's
        Pass-1 sidecars (kebab-case slugs). Feeds entity_search_key_resolution
        (watched diagnostic, ↑ better). None or [] → None (don't conflate
        no-keys with zero-resolution). Wired by the kdb_graph_orchestrator (#109 §3D).
    context_evidence:
        Reconciled Task #122 context evidence (kdb_graph_orchestrator.emit_kpis §5).
        None (pre-#122 artifacts) → all event-time aggregates None, integrity
        counts 0, coverage/integrity_ok None.

    Returns
    -------
    dict with three keys — "scored", "watched", "diagnostic".
    """
    if finalize_ran:
        # ---- shared reads -------------------------------------------------
        # #130: every KPI population is ACTIVE-only. Deprecated pages persist
        # in the graph (pre-#130 they were reaped before KPI time); without
        # the active filter they would silently dilute every denominator.
        active_canonical = queries.active_canonical_entity_slugs(conn)
        canonical = active_canonical
        n_canonical = len(canonical)
        edges = [
            (f, t) for f, t in queries.links_to_edges(conn)
            if f in active_canonical and t in active_canonical
        ]
        total_sources = queries.total_source_count(conn)

        # ---- SCORED -----------------------------------------------------------
        # entity_reuse (↑, scored — the sole scored graph KPI): share of canonical
        # (canonical_id IS NULL) non-summary entities with >= 2 distinct SUPPORTS
        # sources. Measures canonicalization / consolidation vs. fragmentation — a
        # real model capability. None when no such entities (don't conflate
        # no-entities with zero-reuse).
        supports_counts = queries.canonical_nonsummary_supports_counts(conn)
        if supports_counts:
            entity_reuse: float | None = (
                sum(1 for c in supports_counts if c >= 2) / len(supports_counts)
            )
        else:
            entity_reuse = None

        # graph_connectivity (scored ↑): largest-connected-component fraction over
        # canonical entities, LINKS_TO undirected (union-find). None when 0 canonical.
        graph_connectivity = _largest_component_fraction(canonical, edges)

        # link_density (scored ↑): LINKS_TO per canonical entity. None when 0.
        link_density: float | None = (
            queries.total_links_to_count(conn) / n_canonical if n_canonical else None
        )

        # supports_density (scored ↑): SUPPORTS entities per source. None when 0.
        supports_density: float | None = (
            queries.total_supports_count(conn) / total_sources
            if total_sources else None
        )

        # ---- WATCHED (finalize-dependent) ------------------------------------
        # deprecation_rate (#130): pages THIS run's finalize marked deprecated ÷
        # total entities (all Entity nodes). Derived from the graph itself — the
        # finalize mark persists the node with last_run_id set (no retraction
        # artifact needed). None when run_id unknown or 0 total entities.
        total_entities = queries.total_entity_count(conn)
        n_deprecated = (
            queries.newly_deprecated_count(conn, run_id) if run_id else None
        )
        deprecation_rate: float | None = (
            (n_deprecated / total_entities)
            if (n_deprecated is not None and total_entities) else None
        )

        # entity_search_key_resolution (#120 D3, spec v1.4): the MIXED downstream
        # final-graph realization rate of Pass-1 entity_search_keys — the
        # alias-aware fraction resolving to an active canonical entity in the
        # FINAL post-intake graph. Influenced by Pass-1 key selection, Pass-2
        # materialization, and canonicalization; it is NOT a reuse/maturity
        # measure and NOT an extraction-quality measure. Cross-model comparison
        # is valid only for controlled runs (same corpus fingerprint + equivalent
        # initial graph state). Watched, never scored. Keys are kebab-case slugs
        # (same anchor space as link targets) so the same
        # resolve_to_canonical_slugs + active_canonical membership pattern
        # applies.  None when pass1_search_keys is None or empty — don't conflate
        # no-keys with zero-resolution.
        if not pass1_search_keys:
            entity_search_key_resolution: float | None = None
        else:
            key_resolved = queries.resolve_to_canonical_slugs(conn, pass1_search_keys)
            n_resolved = sum(
                1 for k in pass1_search_keys
                if key_resolved.get(k) in active_canonical
            )
            entity_search_key_resolution = n_resolved / len(pass1_search_keys)

        # ---- DIAGNOSTIC -------------------------------------------------------
        # All over canonical-entity or source denominators; None when 0.
        belongs_to_coverage: float | None = (
            queries.canonical_belongs_to_count(conn) / n_canonical
            if n_canonical else None
        )
        domain_null_rate: float | None = (
            queries.null_domain_source_count(conn) / total_sources
            if total_sources else None
        )
        domain_breadth = queries.distinct_domain_count(conn) / DOMAIN_TAXONOMY_SIZE

        # SCORED graph KPIs — the combined graph score (2026-06-06 §6): no single
        # one is sufficient (entity_reuse alone inverts the signal — rewards the
        # sparser graph), but together they capture graph-build quality. Weighted
        # combination + direction live in kdb_graph_compiler.kpi.score.
        scored: dict[str, Any] = {
            "entity_reuse": entity_reuse,
            "graph_connectivity": graph_connectivity,
            "link_density": link_density,
            "supports_density": supports_density,
        }
        watched: dict[str, Any] = {
            "deprecation_rate": deprecation_rate,
            "entity_search_key_resolution": entity_search_key_resolution,
        }
        diagnostic: dict[str, Any] = {
            "belongs_to_coverage": belongs_to_coverage,
            "domain_null_rate": domain_null_rate,
            "domain_breadth": domain_breadth,
        }
    else:
        # §7: finalize_ran=False means "the run did not complete the finalize
        # boundary" — nothing more. Graph state may be unchanged, residual, or
        # partially committed, so finalized-run graph quality is INELIGIBLE:
        # none of the finalized graph-quality or legacy-resolution reads
        # execute — their established keys emit None.
        scored = {
            "entity_reuse": None,
            "graph_connectivity": None,
            "link_density": None,
            "supports_density": None,
        }
        watched = {
            "deprecation_rate": None,
            "entity_search_key_resolution": None,
        }
        diagnostic = {
            "belongs_to_coverage": None,
            "domain_null_rate": None,
            "domain_breadth": None,
        }

    # Task #122 event-time watched fields — computed from the reconciled
    # evidence in BOTH branches. #123 P3a.3 §4.6: pure evidence computation,
    # NO graph read on either path (the KPI-time resolver read is retired;
    # the only remaining resolver use is entity_search_key_resolution above,
    # driven by pass1_search_keys on the finalize branch).
    watched.update(_context_watched_fields(evidence=context_evidence))

    return {"scored": scored, "watched": watched, "diagnostic": diagnostic}
