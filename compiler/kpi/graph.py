"""GRAPH-family benchmark KPI computation over a run's Kuzu knowledge graph (#109).

compute_graph(conn, finalize_artifacts)
    → {"scored": {...}, "watched": {...}, "diagnostic": {...}}

SINGLE-DOOR DISCIPLINE: every graph read goes through kdb_graph.queries — this
module owns only the computation (ratios, union-find), never raw Cypher.

None-on-zero everywhere: every ratio returns None when its denominator is 0,
consistent with compiler.kpi.processing.

Task #122 §6/§7: compute_graph gains an execution branch keyed on
`finalize_ran`. When the run never crossed the finalize boundary
(finalize_ran=False), finalized-run graph quality is INELIGIBLE — none of the
finalized graph-quality or legacy-resolution reads execute (their established
keys emit None); the Task #122 event-time fields are computed from the
reconciled context evidence instead, and the ONLY graph read is the
deterministic unresolved-at-load resolver read for late/never classification
(skipped entirely when that population is empty).

Scored set (2026-06-06 §6 — combined graph score): the four graph quality KPIs
``entity_reuse`` · ``graph_connectivity`` · ``link_density`` · ``supports_density``
(all ↑) are scored together — no single one suffices (entity_reuse alone inverts
the signal, rewarding the sparser graph), but combined they capture graph-build
quality. Weighting + direction live in compiler.kpi.score. ``dangling_link_rate``
was deleted (degenerate — rewarded under-linking, trivially 0 on a sparse graph);
its emitted-link plumbing (the ``compile_result`` param + flattener) went with it.
"""
from __future__ import annotations

from typing import Any

import kuzu

from compiler.context_record import ContextEvidence
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
    conn: kuzu.Connection,
    *,
    run_id: str | None,
    evidence: ContextEvidence | None,
) -> dict[str, Any]:
    """Task #122 event-time watched fields from reconciled context evidence.

    Over status=="complete" records only. N = all emitted keys; R = resolver
    hits at load; L = unresolved-at-load resolving on the deterministic
    post-run read; V = unresolved-at-load still unresolved. R + L + V == N
    (exact); pre_run + cohort + age_unknown == R (exact); every key rate
    divides by N (N == 0 → None; zero numerator → 0.0).

    The frozen integrity diagnostics + coverage are emitted ALWAYS (None only
    when expected is empty); the substantive aggregates require
    evidence.complete — an integrity failure nulls the aggregates but never
    hides coverage/integrity. The unresolved-at-load resolver read is the ONLY
    graph read here and is skipped entirely when that population is empty.
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

    outcomes = [o for r in complete_records for o in r.key_outcomes]
    n = len(outcomes)
    resolved = [o for o in outcomes if o.disposition != "unresolved"]
    r_count = len(resolved)
    unresolved_keys = [o.key for o in outcomes if o.disposition == "unresolved"]

    # L/V — the deterministic post-run read (§7.3): reads the ACTUAL post-run
    # graph state solely to classify event-time misses; never redefines a
    # load-time outcome and never makes the artifact rankable. Skipped
    # entirely when the unresolved population is empty.
    l_count = 0
    if unresolved_keys:
        l_count = len(queries.resolve_to_canonical_slugs(conn, unresolved_keys))
    v_count = len(unresolved_keys) - l_count

    # Age decomposition of R: stamp == this run → cohort (created earlier in
    # the same run); stamp ≠ this run → pre_run; missing stamp → age_unknown.
    pre_run = cohort = age_unknown = 0
    for o in resolved:
        if o.target_first_run_id is None:
            age_unknown += 1
        elif run_id is not None and o.target_first_run_id == run_id:
            cohort += 1
        else:
            pre_run += 1

    def _rate(num: int) -> float | None:
        return (num / n) if n else None

    def _gated(value):
        """evidence_complete == False ⇒ substantive aggregates None."""
        return value if evidence_complete else None

    t2_seeds = sum(1 for o in outcomes if o.disposition == "resolved_t2_seed")

    def _tier_mean(tier: str, field: str) -> float | None:
        if not complete_records:
            return None
        return (sum(getattr(getattr(r, tier), field) for r in complete_records)
                / len(complete_records))

    fields.update({
        "search_key_resolved_at_load_rate": _gated(_rate(r_count)),
        "search_key_late_resolution_rate": _gated(_rate(l_count)),
        "search_key_never_resolved_rate": _gated(_rate(v_count)),
        "search_key_resolved_pre_run_rate": _gated(_rate(pre_run)),
        "search_key_resolved_cohort_rate": _gated(_rate(cohort)),
        "search_key_resolved_age_unknown_rate": _gated(_rate(age_unknown)),
        # pre-cap: t2_seed outcomes over ALL emissions
        "search_key_t2_seed_rate": _gated(_rate(t2_seeds)),
        "context_build_success_rate": _gated(
            len(complete_records) / len(records) if records else None),
        "context_explicit_empty_count": _gated(
            sum(1 for r in complete_records
                if r.effective_t2_strategy == "explicit_empty")),
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
    finalize_artifacts: dict,
    *,
    finalize_ran: bool = True,
    pass1_search_keys: list[str] | None = None,
    run_id: str | None = None,
    context_evidence: ContextEvidence | None = None,
) -> dict:
    """Compute GRAPH-family KPIs for one benchmark run.

    Parameters
    ----------
    conn:
        Live Kuzu connection to the graph the run built.
    finalize_artifacts:
        The cleanup/finalize report (tools.cleanup.reap_orphans_from_graph
        shape): {"reaped": [...], "retracted_slugs": [...], ...}. orphan_rate
        is derived from len(reaped); pass {} if cleanup did not run.
    finalize_ran:
        Task #122 §7 execution branch. False = the run did not complete the
        finalize boundary — finalized graph-quality and legacy-resolution
        reads are NEVER executed (their established keys emit None); only the
        Task-122 fields and the deterministic unresolved-at-load read run.
    pass1_search_keys:
        Union/concat of all emitted entity_search_keys across the run's
        Pass-1 sidecars (kebab-case slugs). Feeds entity_search_key_resolution
        (watched diagnostic, ↑ better). None or [] → None (don't conflate
        no-keys with zero-resolution). Wired by the orchestrator (#109 §3D).
    run_id:
        The run being measured — stamps the cohort age decomposition
        (first_run_id == run_id → cohort; ≠ → pre_run; missing → age_unknown).
    context_evidence:
        Reconciled Task #122 context evidence (orchestrator.emit_kpis §5).
        None (pre-#122 artifacts) → all event-time aggregates None, integrity
        counts 0, coverage/integrity_ok None.

    Returns
    -------
    dict with three keys — "scored", "watched", "diagnostic".
    """
    if finalize_ran:
        # ---- shared reads -------------------------------------------------
        active_canonical = queries.active_canonical_entity_slugs(conn)
        canonical = queries.canonical_entity_slugs(conn)
        n_canonical = len(canonical)
        edges = queries.links_to_edges(conn)
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
        # orphan_rate: orphans marked by finalize ÷ total entities (all Entity
        # nodes). Derivation: len(finalize_artifacts["reaped"]) — the cleanup
        # report's list of orphan_candidate entities reaped this run. None when
        # 0 total entities.
        total_entities = queries.total_entity_count(conn)
        n_orphans = len(finalize_artifacts.get("reaped", []) or [])
        orphan_rate: float | None = (
            n_orphans / total_entities if total_entities else None
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
        # combination + direction live in compiler.kpi.score.
        scored: dict[str, Any] = {
            "entity_reuse": entity_reuse,
            "graph_connectivity": graph_connectivity,
            "link_density": link_density,
            "supports_density": supports_density,
        }
        watched: dict[str, Any] = {
            "orphan_rate": orphan_rate,
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
            "orphan_rate": None,
            "entity_search_key_resolution": None,
        }
        diagnostic = {
            "belongs_to_coverage": None,
            "domain_null_rate": None,
            "domain_breadth": None,
        }

    # Task #122 event-time watched fields — computed from the reconciled
    # evidence in BOTH branches; the ONLY graph read on the no-finalize path
    # is the unresolved-at-load resolver read inside (skipped when empty).
    watched.update(_context_watched_fields(conn, run_id=run_id, evidence=context_evidence))

    return {"scored": scored, "watched": watched, "diagnostic": diagnostic}
