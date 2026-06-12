"""Stable Pydantic response shapes for MCP tools (do not leak kdb_graph dataclasses)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EntityCard(BaseModel):
    """Public metadata for one graph entity (node)."""
    slug: str
    title: str
    page_type: str = Field(description="summary | concept | article")
    status: str
    confidence: str
    canonical_id: str | None = Field(default=None, description="non-null => this is an alias")


class Neighborhood(BaseModel):
    """Entities reachable from a center slug within `depth` LINKS_TO hops."""
    center: str
    direction: str
    depth: int
    neighbors: list[EntityCard]
