"""In-memory MCP integration tests for the kdb_mcp server.

Covers:
- Tool registration (7 read tools expected)
- Round-trip call: get_entity, graph_neighborhood
- Error envelope: missing entity returns isError result, not a raised exception
"""
from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from kdb_graph.graphdb import GraphDB
from kdb_graph.testing import (
    make_compile_result, make_compiled_source, make_page, make_scan, make_scan_entry,
)
from kdb_mcp.server import mcp as app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def seeded_graph(tmp_path, monkeypatch):
    gdir = tmp_path / "g"
    pages = [make_page("a", title="Alpha", outgoing_links=["b"]), make_page("b", title="Beta")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(gdir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
    monkeypatch.setenv("KDB_GRAPH_PATH", str(gdir))
    return gdir


@pytest.mark.anyio
async def test_server_lists_seven_read_tools(seeded_graph):
    async with create_connected_server_and_client_session(app._mcp_server) as session:
        tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    assert names == {
        "get_entity", "graph_neighborhood", "find_path", "sources_for_entity",
        "entities_for_source", "resolve_search_keys", "get_body",
    }


@pytest.mark.anyio
async def test_get_entity_round_trip(seeded_graph):
    async with create_connected_server_and_client_session(app._mcp_server) as session:
        result = await session.call_tool("get_entity", {"slug": "a"})
    assert result.isError is False
    assert result.structuredContent["slug"] == "a"
    assert result.structuredContent["title"] == "Alpha"


@pytest.mark.anyio
async def test_graph_neighborhood_round_trip(seeded_graph):
    async with create_connected_server_and_client_session(app._mcp_server) as session:
        result = await session.call_tool(
            "graph_neighborhood", {"slug": "a", "direction": "out", "depth": 1}
        )
    nbrs = result.structuredContent["neighbors"]
    assert [n["slug"] for n in nbrs] == ["b"]


@pytest.mark.anyio
async def test_missing_entity_is_error_envelope(seeded_graph):
    # The server catches the adapter's EntityNotFoundError and returns it as an
    # isError result (the protocol error envelope), not a raised exception.
    async with create_connected_server_and_client_session(app._mcp_server) as session:
        result = await session.call_tool("get_entity", {"slug": "ghost"})
    assert result.isError is True


@pytest.mark.anyio
async def test_get_body_missing_is_error_envelope(tmp_path, monkeypatch):
    # get_body reads the vault (OBSIDIAN_VAULT_PATH), not the graph; point it at
    # an empty vault so the wiki file is absent -> ContentNotFoundError -> isError.
    empty_vault = tmp_path / "empty_vault"
    empty_vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(empty_vault))
    async with create_connected_server_and_client_session(app._mcp_server) as session:
        result = await session.call_tool("get_body", {"slug": "ghost", "page_type": "concept"})
    assert result.isError is True
