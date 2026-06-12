from __future__ import annotations

import pytest

from kdb_graph.graphdb import GraphDB
from kdb_graph.testing import (
    make_compile_result, make_compiled_source, make_page, make_scan, make_scan_entry,
)
from kdb_mcp import adapters
from kdb_mcp.adapters import EntityNotFoundError


def _seed_chain(graph_dir):
    """a -> b (one source supports both)."""
    pages = [make_page("a", title="Alpha", outgoing_links=["b"]), make_page("b", title="Beta")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")


def test_get_entity_returns_card(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    card = adapters.get_entity(gdir, "a")
    assert card.slug == "a"
    assert card.title == "Alpha"
    assert card.page_type == "concept"
    assert card.status == "active"


def test_get_entity_missing_raises(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    with pytest.raises(EntityNotFoundError):
        adapters.get_entity(gdir, "nope")


def test_graph_neighborhood_out_depth1(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    nb = adapters.graph_neighborhood(gdir, "a", direction="out", depth=1)
    assert nb.center == "a"
    assert nb.direction == "out"
    assert nb.depth == 1
    assert [c.slug for c in nb.neighbors] == ["b"]


def test_graph_neighborhood_empty(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    nb = adapters.graph_neighborhood(gdir, "b", direction="out", depth=1)
    assert nb.neighbors == []
