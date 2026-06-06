"""GRAPH-family benchmark KPI computation over a run's Kuzu knowledge graph
plus the emitted-link payload (#109).

compute_graph(conn, compile_result, finalize_artifacts)
    → {"scored": {...}, "watched": {...}, "diagnostic": {...}}

SINGLE-DOOR DISCIPLINE: every graph read goes through kdb_graph.queries — this
module owns only the computation (ratios, union-find), never raw Cypher.

None-on-zero everywhere: every ratio returns None when its denominator is 0,
consistent with compiler.kpi.processing.
"""
from __future__ import annotations

from typing import Any

import kuzu

from kdb_graph import queries

# Fixed domain taxonomy size for domain_breadth (distinct domains / 23).
DOMAIN_TAXONOMY_SIZE = 23


def _iter_emitted_links(compile_result: dict) -> list[str]:
    """Flatten every page's outgoing_links across the compile_result.

    Order-preserving, NOT de-duplicated — dangling_link_rate is over the
    total count of emitted links (a slug linked twice counts twice).
    """
    targets: list[str] = []
    for cs in compile_result.get("compiled_sources", []):
        for page in cs.get("pages", []):
            targets.extend(page.get("outgoing_links", []) or [])
    return targets


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


def compute_graph(
    conn: kuzu.Connection,
    compile_result: dict,
    finalize_artifacts: dict,
    *,
    pass1_search_keys: list[str] | None = None,
) -> dict:
    """Compute GRAPH-family KPIs for one benchmark run.

    Parameters
    ----------
    conn:
        Live Kuzu connection to the graph the run built.
    compile_result:
        The run's aggregated Pass-2 output (compiled_sources[].pages[].
        outgoing_links). The emitted-link payload for dangling_link_rate.
    finalize_artifacts:
        The cleanup/finalize report (tools.cleanup.reap_orphans_from_graph
        shape): {"reaped": [...], "retracted_slugs": [...], ...}. orphan_rate
        is derived from len(reaped); pass {} if cleanup did not run.
    pass1_search_keys:
        Union/concat of all emitted entity_search_keys across the run's
        Pass-1 sidecars (kebab-case slugs). Feeds entity_search_key_resolution
        (watched diagnostic, ↑ better). None or [] → None (don't conflate
        no-keys with zero-resolution). Wired by the orchestrator (#109 §3D).

    Returns
    -------
    dict with three keys — "scored", "watched", "diagnostic".
    """
    # ---- shared reads -----------------------------------------------------
    active_canonical = queries.active_canonical_entity_slugs(conn)
    canonical = queries.canonical_entity_slugs(conn)
    n_canonical = len(canonical)
    edges = queries.links_to_edges(conn)
    total_sources = queries.total_source_count(conn)

    # ---- SCORED -----------------------------------------------------------
    # dangling_link_rate (dangling fraction, ↓): denominator = total emitted
    # outgoing_links; numerator = those that DON'T resolve to an active
    # canonical entity. Alias-aware: resolve_to_canonical_slugs maps an alias
    # slug to its canonical (so a link to an alias RESOLVES, not dangling).
    # Unresolved raws are ABSENT from the resolver dict — .get(...) yields None,
    # which is correctly not in active_canonical → dangling. None when 0 links.
    emitted = _iter_emitted_links(compile_result)
    if not emitted:
        dangling_link_rate: float | None = None
    else:
        resolved = queries.resolve_to_canonical_slugs(conn, emitted)
        dangling = sum(
            1 for t in emitted if resolved.get(t) not in active_canonical
        )
        dangling_link_rate = dangling / len(emitted)

    scored: dict[str, Any] = {
        "dangling_link_rate": dangling_link_rate,
    }

    # ---- WATCHED ----------------------------------------------------------
    # entity_reuse: share of canonical (canonical_id IS NULL) non-summary
    # entities with >= 2 distinct SUPPORTS sources. None when no such entities.
    supports_counts = queries.canonical_nonsummary_supports_counts(conn)
    if supports_counts:
        entity_reuse: float | None = (
            sum(1 for c in supports_counts if c >= 2) / len(supports_counts)
        )
    else:
        entity_reuse = None

    # graph_connectivity: largest-connected-component fraction over canonical
    # entities, LINKS_TO undirected (union-find). None when 0 canonical.
    graph_connectivity = _largest_component_fraction(canonical, edges)

    # orphan_rate: orphans marked by finalize ÷ total entities (all Entity
    # nodes). Derivation: len(finalize_artifacts["reaped"]) — the cleanup
    # report's list of orphan_candidate entities reaped this run. None when
    # 0 total entities.
    total_entities = queries.total_entity_count(conn)
    n_orphans = len(finalize_artifacts.get("reaped", []) or [])
    orphan_rate: float | None = (
        n_orphans / total_entities if total_entities else None
    )

    # entity_search_key_resolution: alias-aware fraction of Pass-1
    # entity_search_keys that resolve to an active canonical entity.
    # Keys are kebab-case slugs (same anchor space as link targets) so the
    # same resolve_to_canonical_slugs + active_canonical membership pattern
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

    watched: dict[str, Any] = {
        "entity_reuse": entity_reuse,
        "graph_connectivity": graph_connectivity,
        "orphan_rate": orphan_rate,
        "entity_search_key_resolution": entity_search_key_resolution,
    }

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
    link_density: float | None = (
        queries.total_links_to_count(conn) / n_canonical if n_canonical else None
    )
    supports_density: float | None = (
        queries.total_supports_count(conn) / total_sources
        if total_sources else None
    )
    domain_breadth = queries.distinct_domain_count(conn) / DOMAIN_TAXONOMY_SIZE

    diagnostic: dict[str, Any] = {
        "belongs_to_coverage": belongs_to_coverage,
        "domain_null_rate": domain_null_rate,
        "link_density": link_density,
        "supports_density": supports_density,
        "domain_breadth": domain_breadth,
    }

    return {"scored": scored, "watched": watched, "diagnostic": diagnostic}
