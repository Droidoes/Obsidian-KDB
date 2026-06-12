"""Pure adapter functions: open GraphDB read-only per call (F5 reopen), query,
map to a stable response model. Imported by the FastMCP tool wrappers."""
from __future__ import annotations

from pathlib import Path

from kdb_graph.graphdb import GraphDB
from kdb_graph.types import Entity

from kdb_mcp.models import EntityCard, Neighborhood, PathResult


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
