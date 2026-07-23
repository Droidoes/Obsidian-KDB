"""Stable Pydantic response shapes for MCP tools (do not leak kdb_graph dataclasses)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EntityCard(BaseModel):
    """Public metadata for one graph entity (node)."""
    slug: str
    title: str
    page_type: str = Field(description="summary | concept | article")
    status: str
    # #115 Phase 3 (D-115-12): confidence removed — logically deprecated.
    canonical_id: str | None = Field(default=None, description="non-null => this is an alias")


class Neighborhood(BaseModel):
    """Entities reachable from a center slug within `depth` LINKS_TO hops."""
    center: str
    direction: str
    depth: int
    neighbors: list[EntityCard]


class PathResult(BaseModel):
    """Shortest directed LINKS_TO path between two slugs."""
    from_slug: str
    to_slug: str
    found: bool
    path: list[str] | None = None
    hops: int | None = None


class SourceCard(BaseModel):
    """Public metadata for one source note."""
    source_id: str
    source_type: str
    status: str
    domain: str | None = None


class EntityProvenance(BaseModel):
    """Sources that currently support an entity."""
    slug: str
    sources: list[SourceCard]


class SourceProvenance(BaseModel):
    """Entities a source currently supports."""
    source_id: str
    entities: list[EntityCard]


class SearchKeyResolution(BaseModel):
    """Alias-aware mapping of input keys (human names) to canonical slugs."""
    resolved: dict[str, str]
    unresolved: list[str]


class BodyResult(BaseModel):
    """The prose body of one wiki page."""
    slug: str
    page_type: str
    body: str
