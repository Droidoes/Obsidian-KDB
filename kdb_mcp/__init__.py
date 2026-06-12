"""kdb_mcp — read-only MCP stdio server over the kdb_graph + wiki content stores.

In-repo sibling to kdb_graph (NOT inside it): imports both kdb_graph (graph
reads) and common.wiki_io (content), so it stays outside the package to keep
kdb_graph's zero-`common` dependency intact. Read-only by construction.
"""
