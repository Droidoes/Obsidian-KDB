"""Pin the kdb_graph public API surface (Phase 1).

Consumers (MCP server, compiler, tools) import from this surface; it must carry
the read-only contract added in #112.
"""
from __future__ import annotations

import kdb_graph


def test_read_only_error_is_public():
    assert hasattr(kdb_graph, "GraphDBReadOnlyError")
    assert "GraphDBReadOnlyError" in kdb_graph.__all__
    # It is the same class the wrapper raises.
    from kdb_graph.graphdb import GraphDBReadOnlyError as _E
    assert kdb_graph.GraphDBReadOnlyError is _E


def test_core_surface_present():
    for name in (
        "GraphDB", "GraphDBSchemaError", "GraphDBReadOnlyError",
        "Entity", "Source", "SCHEMA_VERSION", "default_graph_path",
    ):
        assert name in kdb_graph.__all__, f"{name} missing from public __all__"
        assert hasattr(kdb_graph, name), f"{name} not importable from kdb_graph"
