"""graph_context_loader — GraphDB-backed context snapshot for one compile job.

Parallel to context_loader.py (manifest-backed). Selected by planner.py via
KDB_CONTEXT_SOURCE=graphdb. Does NOT read env vars itself — planner owns the
branch. Fails explicitly if graph state is insufficient.

Ranking tiers (strict ordering — no cross-tier promotion):
    T1 (score=3): entities supported by this source (SUPPORTS edges)
    T2 (score=2): entities whose slug appears as whole-word in source_text
    T3 (score=1): 1-hop neighbors (in+out) of T1∪T2 seeds, excluding seeds
    Tie-break:    PageRank (desc), then slug (asc) — within same tier only
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import kuzu

from kdb_compiler.types import ContextPage, ContextSnapshot

if TYPE_CHECKING:
    pass

_VALID_PAGE_TYPES = frozenset({"summary", "concept", "article"})


def build_context_snapshot(
    conn: kuzu.Connection,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = 50,
) -> ContextSnapshot:
    """Build a tier-ranked, source-specific context snapshot from GraphDB.

    Pure graph reads — no manifest access, no env var reads.
    Empty/missing source or empty graph → empty snapshot (never raises).
    """
    active_entities = _load_active_entities(conn)
    if not active_entities:
        return ContextSnapshot(source_id=source_id, pages=[])

    slug_set = set(active_entities.keys())

    # --- Tier assignment ---
    t1_slugs = _t1_source_supported(conn, source_id, slug_set)
    t2_slugs = _t2_slug_in_text(source_text, slug_set - t1_slugs)
    seeds = t1_slugs | t2_slugs
    t3_slugs = _t3_neighbors(conn, seeds, slug_set - seeds)

    # --- Scoring + ranking ---
    pagerank_scores = _pagerank_scores(conn)

    scored: list[tuple[str, int, float]] = []
    for slug in t1_slugs:
        scored.append((slug, 3, pagerank_scores.get(slug, 0.0)))
    for slug in t2_slugs:
        scored.append((slug, 2, pagerank_scores.get(slug, 0.0)))
    for slug in t3_slugs:
        scored.append((slug, 1, pagerank_scores.get(slug, 0.0)))

    # Strict tier ordering: tier desc, pagerank desc, slug asc
    scored.sort(key=lambda x: (-x[1], -x[2], x[0]))
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

    return ContextSnapshot(source_id=source_id, pages=pages)


# ---------- Tier helpers ----------


def _load_active_entities(conn: kuzu.Connection) -> dict[str, dict]:
    """Load all active entities as {slug: {title, page_type}}."""
    result = conn.execute(
        "MATCH (e:Entity) WHERE e.status = 'active' "
        "RETURN e.slug, e.title, e.page_type"
    )
    entities: dict[str, dict] = {}
    while result.has_next():
        row = result.get_next()
        entities[row[0]] = {"title": row[1], "page_type": row[2]}
    return entities


def _t1_source_supported(
    conn: kuzu.Connection, source_id: str, active_slugs: set[str]
) -> set[str]:
    """Entities the source currently SUPPORTS."""
    result = conn.execute(
        "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(e:Entity) "
        "RETURN e.slug",
        {"sid": source_id},
    )
    slugs: set[str] = set()
    while result.has_next():
        slug = result.get_next()[0]
        if slug in active_slugs:
            slugs.add(slug)
    return slugs


def _t2_slug_in_text(source_text: str, candidate_slugs: set[str]) -> set[str]:
    """Slugs that appear as whole-word tokens in source_text."""
    if not candidate_slugs or not source_text:
        return set()
    pattern = _whole_word_alternation(sorted(candidate_slugs))
    return {m.group(0).lower() for m in pattern.finditer(source_text)}


def _t3_neighbors(
    conn: kuzu.Connection, seeds: set[str], candidate_slugs: set[str]
) -> set[str]:
    """1-hop in+out neighbors of seeds that are active and not already a seed."""
    if not seeds:
        return set()
    neighbors: set[str] = set()
    for slug in seeds:
        # outgoing
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug",
            {"s": slug},
        )
        while result.has_next():
            n = result.get_next()[0]
            if n in candidate_slugs:
                neighbors.add(n)
        # incoming
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})<-[:LINKS_TO]-(b:Entity) RETURN b.slug",
            {"s": slug},
        )
        while result.has_next():
            n = result.get_next()[0]
            if n in candidate_slugs:
                neighbors.add(n)
    return neighbors


def _pagerank_scores(conn: kuzu.Connection) -> dict[str, float]:
    """Compute PageRank over LINKS_TO topology. Returns {slug: score}."""
    try:
        import networkx as nx
    except ImportError:
        return {}

    result = conn.execute(
        "MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug"
    )
    g = nx.DiGraph()
    while result.has_next():
        row = result.get_next()
        g.add_edge(row[0], row[1])

    if not g.nodes:
        return {}

    # Add isolated active entities so they get a base score
    result2 = conn.execute("MATCH (e:Entity) WHERE e.status = 'active' RETURN e.slug")
    while result2.has_next():
        g.add_node(result2.get_next()[0])

    return nx.pagerank(g)


# ---------- Projection helpers ----------


def _batch_outgoing_links(
    conn: kuzu.Connection, slugs: list[str]
) -> dict[str, list[str]]:
    """For each slug, fetch its outgoing LINKS_TO target slugs."""
    out: dict[str, list[str]] = {}
    for slug in slugs:
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug ORDER BY b.slug",
            {"s": slug},
        )
        links = []
        while result.has_next():
            links.append(result.get_next()[0])
        out[slug] = links
    return out


# ---------- Regex helper (duplicated from context_loader — sunset-bound) ----------


def _whole_word_alternation(slugs: list[str]) -> re.Pattern[str]:
    """Case-insensitive whole-word pattern. Hyphens are intra-token."""
    escaped = [re.escape(s) for s in slugs]
    return re.compile(
        r"(?<![\w-])(" + "|".join(escaped) + r")(?![\w-])",
        re.IGNORECASE,
    )
