"""Read primitives for kdb_graph (#63.3).

Standalone functions taking a kuzu.Connection. GraphDB methods delegate
to these. Analytics primitives (pagerank, communities, structural_holes)
land in #63.4.

Cypher notes:
- Variable-length paths: `-[:LINKS_TO*1..N]->` (1 to N hops, directed).
- Shortest path: `-[:LINKS_TO* SHORTEST 1..N]->` (Kuzu-specific syntax).
- `nodes(p)` returns the path's node list; each is a dict with the
  property columns plus internal `_id`/`_label`.
"""
from __future__ import annotations

from typing import Any

import kuzu

from kdb_graph.types import Entity, Source


_ENTITY_RETURN_COLS = (
    "e.slug, e.title, e.page_type, e.status, "
    "e.created_at, e.updated_at, e.first_run_id, e.last_run_id"
)
_SOURCE_RETURN_COLS = (
    "s.source_id, s.source_type, s.canonical_path, s.status, s.file_type, "
    "s.hash, s.size_bytes, s.first_seen_at, s.last_seen_at, "
    "s.last_ingested_at, s.ingest_state, s.ingest_count, "
    "s.last_run_id, s.moved_to"
)


# ---------- row -> dataclass helpers ----------

def _row_to_entity(row: list[Any]) -> Entity:
    return Entity(
        slug=row[0], title=row[1], page_type=row[2], status=row[3],
        created_at=row[4], updated_at=row[5],
        first_run_id=row[6], last_run_id=row[7],
    )


def _row_to_source(row: list[Any]) -> Source:
    return Source(
        source_id=row[0], source_type=row[1], canonical_path=row[2],
        status=row[3], file_type=row[4], hash=row[5],
        size_bytes=int(row[6]) if row[6] is not None else 0,
        first_seen_at=row[7], last_seen_at=row[8], last_ingested_at=row[9],
        ingest_state=row[10],
        ingest_count=int(row[11]) if row[11] is not None else 0,
        last_run_id=row[12], moved_to=row[13],
    )


def _drain_entities(result) -> list[Entity]:
    out: list[Entity] = []
    while result.has_next():
        out.append(_row_to_entity(result.get_next()))
    return out


def _drain_sources(result) -> list[Source]:
    out: list[Source] = []
    while result.has_next():
        out.append(_row_to_source(result.get_next()))
    return out


# ---------- BFS expansion / neighbors ----------

def neighbors(
    conn: kuzu.Connection,
    slug: str,
    *,
    direction: str = "out",
    depth: int = 1,
) -> list[Entity]:
    """BFS expansion from `slug`. Returns distinct neighbor Entities
    (excluding the start node).

    direction: 'out' (outgoing), 'in' (incoming), or 'both'.
    depth: max hops, >= 1. Pattern is `*1..depth` (inclusive of all
    hop counts up to depth — that is the natural BFS expansion).
    """
    if direction not in ("out", "in", "both"):
        raise ValueError(f"direction must be 'out', 'in', or 'both'; got {direction!r}")
    if depth < 1:
        raise ValueError(f"depth must be >= 1; got {depth}")

    if direction == "out":
        pattern = f"(a:Entity {{slug: $slug}})-[:LINKS_TO*1..{depth}]->(e:Entity)"
    elif direction == "in":
        pattern = f"(a:Entity {{slug: $slug}})<-[:LINKS_TO*1..{depth}]-(e:Entity)"
    else:  # both
        pattern = f"(a:Entity {{slug: $slug}})-[:LINKS_TO*1..{depth}]-(e:Entity)"

    query = f"""
    MATCH {pattern}
    WHERE e.slug <> $slug
    RETURN DISTINCT {_ENTITY_RETURN_COLS}
    ORDER BY e.slug
    """
    return _drain_entities(conn.execute(query, {"slug": slug}))


def incoming_links(conn: kuzu.Connection, slug: str) -> list[Entity]:
    """Convenience: depth-1 incoming-direction neighbors."""
    return neighbors(conn, slug, direction="in", depth=1)


def outgoing_links(conn: kuzu.Connection, slug: str) -> list[Entity]:
    """Convenience: depth-1 outgoing-direction neighbors."""
    return neighbors(conn, slug, direction="out", depth=1)


# ---------- shortest path ----------

def shortest_path(
    conn: kuzu.Connection,
    from_slug: str,
    to_slug: str,
    *,
    max_hops: int = 10,
) -> list[str] | None:
    """Shortest directed path of slugs from `from_slug` to `to_slug`.

    Returns the list of slugs along the path (inclusive of endpoints),
    or None if unreachable within `max_hops` LINKS_TO hops.
    Same-node returns [from_slug] when from == to.
    """
    if max_hops < 1:
        raise ValueError(f"max_hops must be >= 1; got {max_hops}")
    if from_slug == to_slug:
        # Kuzu's *1..N requires at least one hop; handle the degenerate case.
        r = conn.execute(
            "MATCH (a:Entity {slug: $slug}) RETURN a.slug LIMIT 1",
            {"slug": from_slug},
        )
        return [from_slug] if r.has_next() else None

    query = f"""
    MATCH path = (a:Entity {{slug: $from_}})-[:LINKS_TO* SHORTEST 1..{max_hops}]->(b:Entity {{slug: $to_}})
    RETURN nodes(path)
    """
    r = conn.execute(query, {"from_": from_slug, "to_": to_slug})
    if not r.has_next():
        return None
    nodes = r.get_next()[0]
    return [n["slug"] for n in nodes]


# ---------- source / page provenance queries ----------

def entities_for_source(conn: kuzu.Connection, source_id: str) -> list[Entity]:
    """All Entities a Source currently supports (current-state — historical
    SUPPORTS edges are not in v1 per Codex v2 NEW M2)."""
    query = f"""
    MATCH (s:Source {{source_id: $sid}})-[:SUPPORTS]->(e:Entity)
    RETURN DISTINCT {_ENTITY_RETURN_COLS}
    ORDER BY e.slug
    """
    return _drain_entities(conn.execute(query, {"sid": source_id}))


def sources_for_entity(conn: kuzu.Connection, slug: str) -> list[Source]:
    """All Sources currently supporting an Entity."""
    query = f"""
    MATCH (s:Source)-[:SUPPORTS]->(e:Entity {{slug: $slug}})
    RETURN DISTINCT {_SOURCE_RETURN_COLS}
    ORDER BY s.source_id
    """
    return _drain_sources(conn.execute(query, {"slug": slug}))


def subgraph_by_source(conn: kuzu.Connection, source_id: str) -> dict[str, Any]:
    """Subgraph induced by one source's supported entities.

    Returns `{"nodes": [Entity, ...], "edges": [{"from", "to", "run_id", "created_at"}, ...]}`.
    Edges are LINKS_TO edges between Entities both supported by this source.
    """
    entities = entities_for_source(conn, source_id)
    if not entities:
        return {"nodes": [], "edges": []}
    slugs = [e.slug for e in entities]
    r = conn.execute(
        """
        MATCH (a:Entity)-[r:LINKS_TO]->(b:Entity)
        WHERE list_contains($slugs, a.slug) AND list_contains($slugs, b.slug)
        RETURN a.slug, b.slug, r.run_id, r.created_at
        ORDER BY a.slug, b.slug
        """,
        {"slugs": slugs},
    )
    edges: list[dict[str, Any]] = []
    while r.has_next():
        row = r.get_next()
        edges.append({
            "from": row[0],
            "to": row[1],
            "run_id": row[2],
            "created_at": row[3],
        })
    return {"nodes": entities, "edges": edges}


# ---------- orphan listing ----------

def orphan_entities(conn: kuzu.Connection) -> list[Entity]:
    """Entities currently flagged orphan_candidate (zero SUPPORTS at last ingest).

    The flag itself is set during ingestion (Phase 4); this is the read view.
    """
    query = f"""
    MATCH (e:Entity) WHERE e.status = 'orphan_candidate'
    RETURN {_ENTITY_RETURN_COLS}
    ORDER BY e.slug
    """
    return _drain_entities(conn.execute(query))


# ---------- ad-hoc Cypher escape hatch ----------

def cypher(
    conn: kuzu.Connection,
    query: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run an arbitrary Cypher query. Returns list of dicts keyed by column name."""
    r = conn.execute(query, params or {})
    col_names = r.get_column_names()
    rows: list[dict[str, Any]] = []
    while r.has_next():
        row = r.get_next()
        rows.append(dict(zip(col_names, row)))
    return rows


# ---------- context-snapshot read primitives (single Kuzu door) ----------
#
# Raw reads extracted verbatim from compiler.context_loader so the graph
# package owns all Kuzu I/O. Each function is one `conn.execute` + drain,
# returning plain data. The composition/ranking logic (tiering, BFS frontier
# control, set algebra, networkx PageRank) lives in the loader, not here.


def active_entities(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    """All active entities as {slug: {title, page_type}}."""
    result = conn.execute(
        "MATCH (e:Entity) WHERE e.status = 'active' "
        "RETURN e.slug, e.title, e.page_type"
    )
    entities: dict[str, dict[str, Any]] = {}
    while result.has_next():
        row = result.get_next()
        entities[row[0]] = {"title": row[1], "page_type": row[2]}
    return entities


def domain_entity_slugs(conn: kuzu.Connection, domain: str) -> set[str]:
    """Slugs of active entities that BELONGS_TO `domain` (the same-domain gate)."""
    result = conn.execute(
        "MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: $name}) "
        "WHERE e.status = 'active' RETURN e.slug",
        {"name": domain},
    )
    slugs: set[str] = set()
    while result.has_next():
        slugs.add(result.get_next()[0])
    return slugs


def source_supported_slugs(conn: kuzu.Connection, source_id: str) -> set[str]:
    """Raw slugs of entities a Source SUPPORTS (no active filter — caller scopes)."""
    result = conn.execute(
        "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(e:Entity) "
        "RETURN e.slug",
        {"sid": source_id},
    )
    slugs: set[str] = set()
    while result.has_next():
        slugs.add(result.get_next()[0])
    return slugs


def outgoing_neighbor_slugs(conn: kuzu.Connection, slug: str) -> list[str]:
    """Direct (1-hop) outgoing LINKS_TO target slugs of `slug` (unordered)."""
    result = conn.execute(
        "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug",
        {"s": slug},
    )
    out: list[str] = []
    while result.has_next():
        out.append(result.get_next()[0])
    return out


def incoming_neighbor_slugs(conn: kuzu.Connection, slug: str) -> list[str]:
    """Direct (1-hop) incoming LINKS_TO source slugs of `slug` (unordered)."""
    result = conn.execute(
        "MATCH (a:Entity {slug: $s})<-[:LINKS_TO]-(b:Entity) RETURN b.slug",
        {"s": slug},
    )
    out: list[str] = []
    while result.has_next():
        out.append(result.get_next()[0])
    return out


def links_to_edges(conn: kuzu.Connection) -> list[tuple[str, str]]:
    """All LINKS_TO edges as (from_slug, to_slug) tuples (for PageRank topology)."""
    result = conn.execute(
        "MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug"
    )
    edges: list[tuple[str, str]] = []
    while result.has_next():
        row = result.get_next()
        edges.append((row[0], row[1]))
    return edges


def active_entity_slugs(conn: kuzu.Connection) -> list[str]:
    """Slugs of all active entities (for PageRank isolated-node seeding)."""
    result = conn.execute("MATCH (e:Entity) WHERE e.status = 'active' RETURN e.slug")
    out: list[str] = []
    while result.has_next():
        out.append(result.get_next()[0])
    return out


# ---------- GRAPH-family KPI read primitives (#109) ----------
#
# Single-door reads feeding compiler.kpi.graph.compute_graph. Each is one
# conn.execute + drain returning plain counts/slugs. The KPI module owns the
# computation (ratios, union-find); these own the Kuzu I/O.
#
# Two canonical populations are deliberately distinct (do not unify):
#   - active_canonical_entity_slugs: status='active' AND canonical_id IS NULL —
#     the membership set for link_resolution (a link resolves iff it lands here).
#   - canonical_entity_slugs: canonical_id IS NULL (no status filter) — the
#     denominator for entity_reuse / connectivity / belongs_to_coverage /
#     link_density.


def active_canonical_entity_slugs(conn: kuzu.Connection) -> set[str]:
    """Active, non-alias entities (status='active' AND canonical_id IS NULL).

    The link_resolution membership set: an emitted link resolves iff its
    alias-resolved canonical slug is in this set.
    """
    result = conn.execute(
        "MATCH (e:Entity) WHERE e.status = 'active' AND e.canonical_id IS NULL "
        "RETURN e.slug"
    )
    out: set[str] = set()
    while result.has_next():
        out.add(result.get_next()[0])
    return out


def canonical_entity_slugs(conn: kuzu.Connection) -> list[str]:
    """All canonical (non-alias) entity slugs (canonical_id IS NULL; no status
    filter). The denominator population for entity_reuse / connectivity /
    belongs_to_coverage / link_density."""
    result = conn.execute("MATCH (e:Entity) WHERE e.canonical_id IS NULL RETURN e.slug")
    out: list[str] = []
    while result.has_next():
        out.append(result.get_next()[0])
    return out


def total_entity_count(conn: kuzu.Connection) -> int:
    """Count of ALL Entity nodes (any status, alias or canonical). The
    orphan_rate denominator."""
    result = conn.execute("MATCH (e:Entity) RETURN count(e)")
    return int(result.get_next()[0]) if result.has_next() else 0


def canonical_nonsummary_supports_counts(conn: kuzu.Connection) -> list[int]:
    """For each canonical (canonical_id IS NULL) non-summary (page_type !=
    'summary') entity, the number of DISTINCT supporting Sources.

    Returns one int per qualifying entity (0 for entities with no SUPPORTS).
    Feeds entity_reuse (share with >= 2 distinct sources).
    """
    result = conn.execute(
        "MATCH (e:Entity) "
        "WHERE e.canonical_id IS NULL AND e.page_type <> 'summary' "
        "OPTIONAL MATCH (s:Source)-[:SUPPORTS]->(e) "
        "RETURN e.slug, count(DISTINCT s.source_id)"
    )
    out: list[int] = []
    while result.has_next():
        out.append(int(result.get_next()[1]))
    return out


def canonical_belongs_to_count(conn: kuzu.Connection) -> int:
    """Count of canonical (canonical_id IS NULL) entities with >= 1 BELONGS_TO
    edge. The belongs_to_coverage numerator."""
    result = conn.execute(
        "MATCH (e:Entity)-[:BELONGS_TO]->(:Domain) "
        "WHERE e.canonical_id IS NULL "
        "RETURN count(DISTINCT e.slug)"
    )
    return int(result.get_next()[0]) if result.has_next() else 0


def total_source_count(conn: kuzu.Connection) -> int:
    """Count of all Source nodes. Denominator for domain_null_rate +
    supports_density."""
    result = conn.execute("MATCH (s:Source) RETURN count(s)")
    return int(result.get_next()[0]) if result.has_next() else 0


def null_domain_source_count(conn: kuzu.Connection) -> int:
    """Count of Sources whose domain is NULL or empty-string. The
    domain_null_rate numerator."""
    result = conn.execute(
        "MATCH (s:Source) WHERE s.domain IS NULL OR s.domain = '' RETURN count(s)"
    )
    return int(result.get_next()[0]) if result.has_next() else 0


def total_links_to_count(conn: kuzu.Connection) -> int:
    """Count of all LINKS_TO edges. The link_density numerator."""
    result = conn.execute("MATCH (:Entity)-[r:LINKS_TO]->(:Entity) RETURN count(r)")
    return int(result.get_next()[0]) if result.has_next() else 0


def total_supports_count(conn: kuzu.Connection) -> int:
    """Count of all SUPPORTS edges. The supports_density numerator."""
    result = conn.execute("MATCH (:Source)-[r:SUPPORTS]->(:Entity) RETURN count(r)")
    return int(result.get_next()[0]) if result.has_next() else 0


def distinct_domain_count(conn: kuzu.Connection) -> int:
    """Count of distinct Domain nodes. The domain_breadth numerator."""
    result = conn.execute("MATCH (d:Domain) RETURN count(d)")
    return int(result.get_next()[0]) if result.has_next() else 0


def outgoing_links_ordered(conn: kuzu.Connection, slug: str) -> list[str]:
    """Outgoing LINKS_TO target slugs of `slug`, ordered ascending by slug."""
    result = conn.execute(
        "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) "
        "RETURN b.slug ORDER BY b.slug",
        {"s": slug},
    )
    out: list[str] = []
    while result.has_next():
        out.append(result.get_next()[0])
    return out


# ---------- alias-aware canonical resolution (Task #90 v0.2 — D-90-9; #122 provenance) ----------
#
# Row shape shared by BOTH query shapes (neutral — no resolution CASE in
# Cypher; #122): (raw, e_status, canonical_id, e_first_run_id, target_status,
# target_first_run_id, alias_slug, alias_status, alias_first_run_id). The
# shared classifier below applies the §3.1 precedence + per-path first_run_id
# selection exactly once. Legacy slug-only resolvers are projections over the
# provenance resolvers — simple ≡ batch by construction.


def _resolution_rows(
    conn: kuzu.Connection,
    cleaned: list[str],
) -> list[tuple]:
    """Simple 2-query shape: MATCH by slug set, neutral resolution rows."""
    q = conn.execute(
        """
        MATCH (e:Entity)
        WHERE e.slug IN $slugs
        OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
        OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
        RETURN e.slug, e.status, e.canonical_id, e.first_run_id,
               CASE WHEN target IS NULL THEN NULL ELSE target.status END,
               CASE WHEN target IS NULL THEN NULL ELSE target.first_run_id END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.slug END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.status END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.first_run_id END
        """,
        {"slugs": cleaned},
    )
    rows: list[tuple] = []
    while q.has_next():
        rows.append(q.get_next())
    return rows


def _resolution_rows_batch(
    conn: kuzu.Connection,
    cleaned: list[str],
) -> list[tuple]:
    """Batch shape (UNWIND; Codex-tested on Kuzu 0.11.3): one neutral row per
    raw key — including misses (e IS NULL) so every input is accounted for."""
    q = conn.execute(
        """
        UNWIND $raw_slugs AS raw
        OPTIONAL MATCH (e:Entity {slug: raw})
        WITH raw, e
        OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
        OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
        RETURN raw,
               CASE WHEN e IS NULL THEN NULL ELSE e.status END,
               CASE WHEN e IS NULL THEN NULL ELSE e.canonical_id END,
               CASE WHEN e IS NULL THEN NULL ELSE e.first_run_id END,
               CASE WHEN target IS NULL THEN NULL ELSE target.status END,
               CASE WHEN target IS NULL THEN NULL ELSE target.first_run_id END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.slug END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.status END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.first_run_id END
        """,
        {"raw_slugs": cleaned},
    )
    rows: list[tuple] = []
    while q.has_next():
        rows.append(q.get_next())
    return rows


def classify_resolution_rows(rows: list[tuple]) -> dict[str, tuple[str, str | None]]:
    """THE row classifier (#122) — §3.1 precedence + per-path first_run_id
    selection, exactly once for both query shapes.

    Precedence: canonical_id active > ALIAS_OF active > direct leaf active;
    dead targets fail-closed (an entity that DECLARED itself an alias — via
    canonical_id or an outgoing ALIAS_OF — never falls back to Path 1).
    Stamps: Path 2 → target's first_run_id; Path 3 → the ALIAS_OF canonical's;
    Path 1 → the entity's own. Empty first_run_id → None HERE (normalization
    at construction — the strict record parser rejects an empty persisted
    stamp, so it must never survive classification).
    """
    resolved: dict[str, tuple[str, str | None]] = {}
    for (raw, status, canonical_id, e_first_run_id,
         target_status, target_first_run_id,
         alias_slug, alias_status, alias_first_run_id) in rows:
        if canonical_id is not None:
            # Path 2 — canonical_id resolution (B-2 active check)
            if target_status == "active":
                resolved[raw] = (canonical_id, target_first_run_id or None)
            # else: dead canonical_id target — unresolved
        elif alias_slug is not None:
            # Path 3 — ALIAS_OF safety net (entity declared itself an alias)
            if alias_status == "active":
                resolved[raw] = (alias_slug, alias_first_run_id or None)
            # else: dead alias target — unresolved (NOT Path 1 fallback)
        elif status == "active":
            # Path 1 — direct leaf entity (no canonical_id, no outgoing ALIAS_OF)
            resolved[raw] = (raw, e_first_run_id or None)
    return resolved


def resolve_to_canonical_slugs_with_provenance(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, tuple[str, str | None]]:
    """{raw: (canonical_slug, target_first_run_id)} — simple query shape.

    Reachability per §3.1: direct PK → canonical_id (with target.status='active'
    check — fixes B-2) → ALIAS_OF (canonical.status='active' check). Unresolved
    raws are absent from the dict. Defensive: trims whitespace + drops
    empty/whitespace-only entries (Qwen O-2).
    """
    cleaned = [s.strip() for s in raw_slugs if s and s.strip()]
    if not cleaned:
        return {}
    return classify_resolution_rows(_resolution_rows(conn, cleaned))


def resolve_to_canonical_slugs_with_provenance_batch(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, tuple[str, str | None]]:
    """Batch twin (D-90-9 escape hatch) — same classifier, same outcomes."""
    cleaned = [s.strip() for s in raw_slugs if s and s.strip()]
    if not cleaned:
        return {}
    return classify_resolution_rows(_resolution_rows_batch(conn, cleaned))


def resolve_to_canonical_slugs(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Legacy slug-only projection (D-90-9 v1 default) over the shared
    provenance resolver — parity with the batch shape is structural."""
    return {raw: canonical
            for raw, (canonical, _stamp)
            in resolve_to_canonical_slugs_with_provenance(conn, raw_slugs).items()}


def resolve_to_canonical_slugs_batch(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Legacy slug-only projection (Codex-tested batch escape hatch)."""
    return {raw: canonical
            for raw, (canonical, _stamp)
            in resolve_to_canonical_slugs_with_provenance_batch(conn, raw_slugs).items()}
