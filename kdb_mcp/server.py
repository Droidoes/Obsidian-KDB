"""Read-only MCP stdio server over the KDB graph + wiki content stores.

Each tool opens the GraphDB read-only per call (F5 reopen). Writes never go
through this server. Run: `python -m kdb_mcp.server` (stdio).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.paths import PageType
from kdb_mcp import adapters, config
from kdb_mcp.models import (
    BodyResult, EntityCard, EntityProvenance, Neighborhood, PathResult,
    SearchKeyResolution, SourceProvenance,
)

mcp = FastMCP("kdb-graph")


@mcp.tool()
def get_entity(slug: str) -> EntityCard:
    """Return metadata for one graph entity by slug."""
    return adapters.get_entity(config.default_graph_path(), slug)


@mcp.tool()
def graph_neighborhood(slug: str, direction: str = "both", depth: int = 1) -> Neighborhood:
    """Entities reachable from `slug` within `depth` LINKS_TO hops. direction: out|in|both."""
    return adapters.graph_neighborhood(config.default_graph_path(), slug, direction=direction, depth=depth)


@mcp.tool()
def find_path(from_slug: str, to_slug: str, max_hops: int = 10) -> PathResult:
    """Shortest directed LINKS_TO path between two slugs."""
    return adapters.find_path(config.default_graph_path(), from_slug, to_slug, max_hops=max_hops)


@mcp.tool()
def sources_for_entity(slug: str) -> EntityProvenance:
    """Sources currently supporting an entity."""
    return adapters.sources_for_entity(config.default_graph_path(), slug)


@mcp.tool()
def entities_for_source(source_id: str) -> SourceProvenance:
    """Entities a source currently supports."""
    return adapters.entities_for_source(config.default_graph_path(), source_id)


@mcp.tool()
def resolve_search_keys(keys: list[str]) -> SearchKeyResolution:
    """Resolve names/aliases to active canonical slugs."""
    return adapters.resolve_search_keys(config.default_graph_path(), keys)


@mcp.tool()
def get_body(slug: str, page_type: PageType) -> BodyResult:
    """Return the prose body of a wiki page (frontmatter stripped). page_type is
    an enum (summary|concept|article) — invalid values are rejected by the SDK."""
    return adapters.get_body(config.default_vault_root(), slug, page_type)


def main() -> None:
    """Entry point — run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
