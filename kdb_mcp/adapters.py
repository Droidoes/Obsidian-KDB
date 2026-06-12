"""Pure adapter functions: open GraphDB read-only per call (F5 reopen), query,
map to a stable response model. Imported by the FastMCP tool wrappers."""
from __future__ import annotations

from pathlib import Path

from kdb_graph import queries
from kdb_graph.graphdb import GraphDB
from kdb_graph.types import Entity, Source
from common import paths

from kdb_mcp.models import EntityCard, EntityProvenance, Neighborhood, PathResult, SearchKeyResolution, SourceCard, SourceProvenance


class EntityNotFoundError(Exception):
    """No entity for the given slug (valid slug, absent node)."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"No entity for slug={slug!r}")


def _entity_card(e: Entity) -> EntityCard:
    return EntityCard(
        slug=e.slug, title=e.title, page_type=e.page_type, status=e.status,
        confidence=e.confidence, canonical_id=e.canonical_id,
    )


def get_entity(graph_path: Path, slug: str) -> EntityCard:
    """Return node metadata for a slug. Raises EntityNotFoundError if absent."""
    with GraphDB(graph_path, read_only=True) as g:
        e = g.get_entity(slug)
    if e is None:
        raise EntityNotFoundError(slug)
    return _entity_card(e)


def graph_neighborhood(
    graph_path: Path, slug: str, *, direction: str = "both", depth: int = 1
) -> Neighborhood:
    """BFS expansion from slug. direction: out|in|both; depth >= 1."""
    with GraphDB(graph_path, read_only=True) as g:
        ents = g.neighbors(slug, direction=direction, depth=depth)
    return Neighborhood(
        center=slug, direction=direction, depth=depth,
        neighbors=[_entity_card(e) for e in ents],
    )


def find_path(
    graph_path: Path, from_slug: str, to_slug: str, *, max_hops: int = 10
) -> PathResult:
    """Shortest directed path of slugs; found=False when unreachable."""
    with GraphDB(graph_path, read_only=True) as g:
        path = g.shortest_path(from_slug, to_slug, max_hops=max_hops)
    if path is None:
        return PathResult(from_slug=from_slug, to_slug=to_slug, found=False)
    return PathResult(
        from_slug=from_slug, to_slug=to_slug, found=True,
        path=path, hops=len(path) - 1,
    )


def _source_card(s: Source) -> SourceCard:
    return SourceCard(
        source_id=s.source_id, source_type=s.source_type, status=s.status,
        domain=s.domain,
    )


def sources_for_entity(graph_path: Path, slug: str) -> EntityProvenance:
    """Sources currently supporting an entity (empty list if none)."""
    with GraphDB(graph_path, read_only=True) as g:
        srcs = g.sources_for_entity(slug)
    return EntityProvenance(slug=slug, sources=[_source_card(s) for s in srcs])


def entities_for_source(graph_path: Path, source_id: str) -> SourceProvenance:
    """Entities a source currently supports (empty list if none)."""
    with GraphDB(graph_path, read_only=True) as g:
        ents = g.entities_for_source(source_id)
    return SourceProvenance(source_id=source_id, entities=[_entity_card(e) for e in ents])


def resolve_search_keys(graph_path: Path, keys: list[str]) -> SearchKeyResolution:
    """Resolve human names/aliases to active canonical slugs. Each key is
    slugified first (so 'Amortization' -> 'amortization'), then alias-resolved.
    Keys that cannot be slugified or do not resolve land in `unresolved`
    (input order preserved). Returns the ORIGINAL key mapped to its canonical slug."""
    key_to_slug: dict[str, str] = {}
    for k in keys:
        try:
            key_to_slug[k] = paths.slugify(k)
        except paths.PathError:
            continue  # unslugifiable (empty / no ASCII) -> stays unresolved
    with GraphDB(graph_path, read_only=True) as g:
        slug_to_canon = queries.resolve_to_canonical_slugs(
            g.conn, sorted(set(key_to_slug.values()))
        )
    resolved = {k: slug_to_canon[s] for k, s in key_to_slug.items() if s in slug_to_canon}
    unresolved = [k for k in keys if k not in resolved]
    return SearchKeyResolution(resolved=resolved, unresolved=unresolved)
