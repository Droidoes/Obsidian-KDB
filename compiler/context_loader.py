"""context_loader — GraphDB-backed context snapshot for one compile job.

Called directly by the orchestrator (`kdb_orchestrate.py`). Does NOT read env
vars itself (Codex F-5 purity invariant) — the caller threads the pass-1.5
products (t2_selection / t1_slugs / search_summary / key_outcomes) as explicit
params. Fails explicitly if graph state is insufficient.

#123 P3a.2b (blueprint §4.3/§7): semantic selection is the sole T2 seeding
path (R-P3a-2). The legacy T2 family — T2Mode, the regex matchers, the
resolver wrappers, the cold-start 2-hop widening, and the `source_text` /
`mode` / `resolver` params — is DELETED, no compatibility shim.

Task #122: build_context_snapshot returns a ContextBuildResult — TWO products:
the prompt-facing ContextSnapshot + the persistence-facing ContextTelemetry
(event-time capture: per-expression key outcomes, pre/post-cap tier records,
the pass-1.5 search summary). The telemetry is NEVER serialized into the
prompt.

Task #129: the snapshot is TIER-STRUCTURED (t1/t2/t3 ContextPage lists) — the
projection partitions the ranked pages by tier so the prompt can state a
different obligation per tier. Selection, scoring, strict tier order, and the
global page_cap are untouched: `snapshot.pages` (derived flat view) is exactly
the slug sequence the pre-#129 flat snapshot emitted for the same inputs.

Ranking tiers (strict ordering — no cross-tier promotion):
    T1 (score=3): entities supported by this source (SUPPORTS edges)
    T2 (score=2): the adapter's validated selector hits (`t2_selection`), in
                  SELECTOR ORDER — rank_index is the fat-stage rank position
                  (§4.3); under a binding cap, selector rank — not PageRank —
                  decides which T2 pages survive (§3.2).
    T3 (score=1): 1-hop neighbors (in+out) of T1∪T2 seeds, excluding seeds —
                  ALWAYS 1-hop (the cold-start widening is gone).
    Sort key:     (-tier, rank_index, -pagerank, slug) — rank_index constant
                  for T1/T3, so PageRank (desc) then slug (asc) break ties there.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kdb_graph import queries
from common.types import (
    ContextBuildResult,
    ContextPage,
    ContextSnapshot,
    ContextTelemetry,
    TierRecord,
)

if TYPE_CHECKING:
    from common.source_io import SourceFrontmatter
    from common.types import SearchSummary

_VALID_PAGE_TYPES = frozenset({"summary", "concept", "article"})


_DEFAULT_PAGE_CAP = 50


def build_context_snapshot(
    conn: Any,
    *,
    source_id: str,
    page_cap: int = _DEFAULT_PAGE_CAP,
    frontmatter: "SourceFrontmatter | None" = None,
    t2_selection: list[str] | None = None,
    t1_slugs: frozenset[str] | None = None,
    search_summary: "SearchSummary | None" = None,
    key_outcomes: list | None = None,
) -> ContextBuildResult:
    """Build a tier-ranked, source-specific context snapshot from GraphDB —
    returning BOTH products (Task #122): the prompt-facing ContextSnapshot
    (tier-structured since #129: t1/t2/t3 lists — the same ranked pages,
    partitioned by tier) and the persistence-facing ContextTelemetry
    (event-time capture; never serialized into the prompt).

    Pure graph reads — no manifest access, no env var reads.
    Empty/missing source or empty graph → empty snapshot (never raises).

    #123 P3a.2b params:
        t2_selection: validated selector hits in selector order, or None when
            no search ran (pre-Pass-1 / replay path). T2 = `t2_selection or []`
            ∩ (active same-domain pool − T1), order preserved (§4.3).
        t1_slugs: the adapter's single scoped T1 read, passed through so the
            exclusion is computed once; None (replay/tooling path) ⇒ the
            builder reads and scopes it itself, as today.
        search_summary: the adapter's SearchSummary for the telemetry product
            (populated whenever a search ran — abstention included).
        key_outcomes: the adapter's per-expression KeyOutcomeV2 projection,
            passed through to the telemetry product.
    """
    keys_emitted = (
        list(frontmatter.entity_search_keys) if frontmatter is not None else [])
    domain = frontmatter.domain if frontmatter is not None else None
    outcomes = list(key_outcomes) if key_outcomes is not None else []

    active_entities = _load_active_entities(conn)
    if not active_entities:
        # Empty-graph early return: FULL telemetry — zero tiers, cold_start=True,
        # search/key_outcomes passed through (§4.3: the adapter searched the
        # empty space upstream — populated, not null).
        zero = TierRecord(candidates=0, delivered=0, slugs=[])
        return ContextBuildResult(
            snapshot=ContextSnapshot(source_id=source_id),
            telemetry=ContextTelemetry(
                source_id=source_id,
                keys_emitted=keys_emitted,
                key_outcomes=outcomes,
                t1=zero,
                t2=zero,
                t3=zero,
                candidate_universe_size=0,
                domain_scope=domain,
                cold_start=True,
                page_cap=page_cap,
                search=search_summary,
            ),
        )

    slug_set = set(active_entities.keys())

    # Same-domain gate (D3 override): T2/T3 pull only from the source's Pass-1
    # domain (entity anti-entropy). T1 stays on the full set — it is the source's
    # own SUPPORTS, same-domain by construction. A source with no Pass-1 domain
    # (pre-Pass-1 / un-enriched) cannot be scoped, so it falls back to the full graph.
    pool = (_domain_pool(conn, domain) & slug_set) if domain else slug_set

    # --- Tier assignment ---
    # The adapter's pass-through is authoritative (already scoped to active
    # entities, §4.1 step 2); None ⇒ the builder reads + scopes it itself.
    t1 = (set(t1_slugs) if t1_slugs is not None
          else _t1_source_supported(conn, source_id, slug_set))
    cold_start = len(t1) == 0

    # T2: selector hits ∩ (pool − T1), order preserved, first rank wins on
    # duplicates. The minus-T1 is a no-op safeguard under §4.1's pre-selector
    # T1 exclusion.
    scope = pool - t1
    t2_ordered: list[str] = []
    for slug in t2_selection or []:
        if slug in scope and slug not in t2_ordered:
            t2_ordered.append(slug)

    seeds = t1 | set(t2_ordered)
    t3_slugs = _t3_neighbors(conn, seeds, pool - seeds, max_hops=1)

    # --- Scoring + ranking ---
    pagerank_scores = _pagerank_scores(conn)
    rank_index = {slug: i for i, slug in enumerate(t2_ordered)}

    scored: list[tuple[str, int, int, float]] = []
    for slug in t1:
        scored.append((slug, 3, 0, pagerank_scores.get(slug, 0.0)))
    for slug in t2_ordered:
        scored.append((slug, 2, rank_index[slug], pagerank_scores.get(slug, 0.0)))
    for slug in t3_slugs:
        scored.append((slug, 1, 0, pagerank_scores.get(slug, 0.0)))

    # Strict tier ordering: tier desc, selector rank asc (T2), pagerank desc, slug asc
    scored.sort(key=lambda x: (-x[1], x[2], -x[3], x[0]))
    selected_slugs = [s[0] for s in scored[:page_cap]]

    # --- Projection ---
    outgoing_map = _batch_outgoing_links(conn, selected_slugs)
    pages = []
    for slug in selected_slugs:
        ent = active_entities[slug]
        page_type = ent["page_type"]
        if page_type not in _VALID_PAGE_TYPES:
            continue
        pages.append(ContextPage(
            slug=slug,
            title=ent["title"],
            page_type=page_type,
            outgoing_links=outgoing_map.get(slug, []),
        ))

    # --- TierRecords: candidates = pre-cap tier sets; delivered/slugs =
    # post-cap, post-projection prompt pages per tier, in rank order. The
    # tiers are disjoint by construction (t2 ⊆ pool−t1, t3 ⊆ pool−seeds), so
    # sum(delivered) == len(pages) ≤ page_cap.
    tier_of: dict[str, int] = {}
    for slug in t1:
        tier_of[slug] = 1
    for slug in t2_ordered:
        tier_of[slug] = 2
    for slug in t3_slugs:
        tier_of[slug] = 3
    tier_slugs: dict[int, list[str]] = {1: [], 2: [], 3: []}
    tier_pages: dict[int, list[ContextPage]] = {1: [], 2: [], 3: []}
    for page in pages:
        tier = tier_of[page.slug]
        tier_slugs[tier].append(page.slug)
        tier_pages[tier].append(page)

    # #129: the snapshot carries the SAME ranked pages, partitioned by tier —
    # snapshot.t{i} slugs are identical to telemetry.t{i}.slugs, and the
    # derived flat `snapshot.pages` is the pre-#129 rank-ordered sequence.
    return ContextBuildResult(
        snapshot=ContextSnapshot(
            source_id=source_id,
            t1=tier_pages[1],
            t2=tier_pages[2],
            t3=tier_pages[3],
        ),
        telemetry=ContextTelemetry(
            source_id=source_id,
            keys_emitted=keys_emitted,
            key_outcomes=outcomes,
            t1=TierRecord(len(t1), len(tier_slugs[1]), tier_slugs[1]),
            t2=TierRecord(len(t2_ordered), len(tier_slugs[2]), tier_slugs[2]),
            t3=TierRecord(len(t3_slugs), len(tier_slugs[3]), tier_slugs[3]),
            candidate_universe_size=len(pool),
            domain_scope=domain,
            cold_start=cold_start,
            page_cap=page_cap,
            search=search_summary,
        ),
    )


# ---------- Tier helpers ----------


def _load_active_entities(conn: Any) -> dict[str, dict]:
    """Load all active entities as {slug: {title, page_type}}."""
    return queries.active_entities(conn)


def _domain_pool(conn: Any, domain: str) -> set[str]:
    """Slugs of active entities that BELONGS_TO `domain` (the same-domain gate).

    The Pass-2 context is pulled only from the source's Pass-1 domain (D3
    override → hard same-domain gate). Domain nodes are keyed by `Domain.name`,
    which is exactly the string Pass-1 emits as `frontmatter.domain`.
    """
    return queries.domain_entity_slugs(conn, domain)


def _t1_source_supported(
    conn: Any, source_id: str, active_slugs: set[str]
) -> set[str]:
    """Entities the source currently SUPPORTS (restricted to active slugs)."""
    return queries.source_supported_slugs(conn, source_id) & active_slugs


def _t3_neighbors(
    conn: Any,
    seeds: set[str],
    candidate_slugs: set[str],
    *,
    max_hops: int = 1,
) -> set[str]:
    """Multi-hop in+out neighbors of seeds that are active and not already a seed."""
    if not seeds or not candidate_slugs:
        return set()
    current_frontier = set(seeds)
    all_neighbors: set[str] = set()
    visited = set(seeds)

    for _ in range(max_hops):
        next_frontier: set[str] = set()
        for slug in current_frontier:
            # outgoing
            for n in queries.outgoing_neighbor_slugs(conn, slug):
                if n in candidate_slugs and n not in visited:
                    all_neighbors.add(n)
                    next_frontier.add(n)
            # incoming
            for n in queries.incoming_neighbor_slugs(conn, slug):
                if n in candidate_slugs and n not in visited:
                    all_neighbors.add(n)
                    next_frontier.add(n)
        visited |= next_frontier
        current_frontier = next_frontier
    return all_neighbors


def _pagerank_scores(conn: Any) -> dict[str, float]:
    """Compute PageRank over LINKS_TO topology. Returns {slug: score}."""
    try:
        import networkx as nx
    except ImportError:
        return {}

    g = nx.DiGraph()
    for from_slug, to_slug in queries.links_to_edges(conn):
        g.add_edge(from_slug, to_slug)

    if not g.nodes:
        return {}

    # Add isolated active entities so they get a base score
    for slug in queries.active_entity_slugs(conn):
        g.add_node(slug)

    return nx.pagerank(g)


# ---------- Projection helpers ----------


def _batch_outgoing_links(
    conn: Any, slugs: list[str]
) -> dict[str, list[str]]:
    """For each slug, fetch its outgoing LINKS_TO target slugs."""
    out: dict[str, list[str]] = {}
    for slug in slugs:
        out[slug] = queries.outgoing_links_ordered(conn, slug)
    return out
