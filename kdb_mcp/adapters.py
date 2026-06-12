"""Pure adapter functions: open GraphDB read-only per call (F5 reopen), query,
map to a stable response model. Imported by the FastMCP tool wrappers."""
from __future__ import annotations

from pathlib import Path

from kdb_graph.graphdb import GraphDB
from kdb_graph.types import Entity

from kdb_mcp.models import EntityCard


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
