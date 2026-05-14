"""Read primitives for graphdb_kdb (#63.3).

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

from graphdb_kdb.types import Page, Source


_PAGE_RETURN_COLS = (
    "p.slug, p.title, p.page_type, p.status, p.confidence, "
    "p.created_at, p.updated_at, p.first_run_id, p.last_run_id"
)
_SOURCE_RETURN_COLS = (
    "s.source_id, s.source_type, s.canonical_path, s.status, s.file_type, "
    "s.hash, s.size_bytes, s.first_seen_at, s.last_seen_at, "
    "s.last_compiled_at, s.compile_state, s.compile_count, "
    "s.last_run_id, s.moved_to"
)


# ---------- row -> dataclass helpers ----------

def _row_to_page(row: list[Any]) -> Page:
    return Page(
        slug=row[0], title=row[1], page_type=row[2], status=row[3],
        confidence=row[4], created_at=row[5], updated_at=row[6],
        first_run_id=row[7], last_run_id=row[8],
    )


def _row_to_source(row: list[Any]) -> Source:
    return Source(
        source_id=row[0], source_type=row[1], canonical_path=row[2],
        status=row[3], file_type=row[4], hash=row[5],
        size_bytes=int(row[6]) if row[6] is not None else 0,
        first_seen_at=row[7], last_seen_at=row[8], last_compiled_at=row[9],
        compile_state=row[10],
        compile_count=int(row[11]) if row[11] is not None else 0,
        last_run_id=row[12], moved_to=row[13],
    )


def _drain_pages(result) -> list[Page]:
    out: list[Page] = []
    while result.has_next():
        out.append(_row_to_page(result.get_next()))
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
) -> list[Page]:
    """BFS expansion from `slug`. Returns distinct neighbor Pages
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
        pattern = f"(a:Page {{slug: $slug}})-[:LINKS_TO*1..{depth}]->(p:Page)"
    elif direction == "in":
        pattern = f"(a:Page {{slug: $slug}})<-[:LINKS_TO*1..{depth}]-(p:Page)"
    else:  # both
        pattern = f"(a:Page {{slug: $slug}})-[:LINKS_TO*1..{depth}]-(p:Page)"

    query = f"""
    MATCH {pattern}
    WHERE p.slug <> $slug
    RETURN DISTINCT {_PAGE_RETURN_COLS}
    ORDER BY p.slug
    """
    return _drain_pages(conn.execute(query, {"slug": slug}))


def incoming_links(conn: kuzu.Connection, slug: str) -> list[Page]:
    """Convenience: depth-1 incoming-direction neighbors."""
    return neighbors(conn, slug, direction="in", depth=1)


def outgoing_links(conn: kuzu.Connection, slug: str) -> list[Page]:
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
            "MATCH (a:Page {slug: $slug}) RETURN a.slug LIMIT 1",
            {"slug": from_slug},
        )
        return [from_slug] if r.has_next() else None

    query = f"""
    MATCH p = (a:Page {{slug: $from_}})-[:LINKS_TO* SHORTEST 1..{max_hops}]->(b:Page {{slug: $to_}})
    RETURN nodes(p)
    """
    r = conn.execute(query, {"from_": from_slug, "to_": to_slug})
    if not r.has_next():
        return None
    nodes = r.get_next()[0]
    return [n["slug"] for n in nodes]


# ---------- source / page provenance queries ----------

def pages_for_source(conn: kuzu.Connection, source_id: str) -> list[Page]:
    """All Pages a Source currently supports (current-state — historical
    SUPPORTS edges are not in v1 per Codex v2 NEW M2)."""
    query = f"""
    MATCH (s:Source {{source_id: $sid}})-[:SUPPORTS]->(p:Page)
    RETURN DISTINCT {_PAGE_RETURN_COLS}
    ORDER BY p.slug
    """
    return _drain_pages(conn.execute(query, {"sid": source_id}))


def sources_for_page(conn: kuzu.Connection, slug: str) -> list[Source]:
    """All Sources currently supporting a Page."""
    query = f"""
    MATCH (s:Source)-[:SUPPORTS]->(p:Page {{slug: $slug}})
    RETURN DISTINCT {_SOURCE_RETURN_COLS}
    ORDER BY s.source_id
    """
    return _drain_sources(conn.execute(query, {"slug": slug}))


def subgraph_by_source(conn: kuzu.Connection, source_id: str) -> dict[str, Any]:
    """Subgraph induced by one source's supported pages.

    Returns `{"nodes": [Page, ...], "edges": [{"from", "to", "run_id", "created_at"}, ...]}`.
    Edges are LINKS_TO edges between Pages both supported by this source.
    """
    pages = pages_for_source(conn, source_id)
    if not pages:
        return {"nodes": [], "edges": []}
    slugs = [p.slug for p in pages]
    r = conn.execute(
        """
        MATCH (a:Page)-[r:LINKS_TO]->(b:Page)
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
    return {"nodes": pages, "edges": edges}


# ---------- orphan listing ----------

def orphan_pages(conn: kuzu.Connection) -> list[Page]:
    """Pages currently flagged orphan_candidate (zero SUPPORTS at last ingest).

    The flag itself is set during ingestion (Phase 4); this is the read view.
    """
    query = f"""
    MATCH (p:Page) WHERE p.status = 'orphan_candidate'
    RETURN {_PAGE_RETURN_COLS}
    ORDER BY p.slug
    """
    return _drain_pages(conn.execute(query))


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
