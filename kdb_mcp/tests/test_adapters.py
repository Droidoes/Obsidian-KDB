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


def test_find_path_found(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    pr = adapters.find_path(gdir, "a", "b")
    assert pr.found is True
    assert pr.path == ["a", "b"]
    assert pr.hops == 1


def test_find_path_unreachable(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    pr = adapters.find_path(gdir, "b", "a")  # chain is a->b, no reverse edge
    assert pr.found is False
    assert pr.path is None
    assert pr.hops is None


def test_sources_for_entity(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    prov = adapters.sources_for_entity(gdir, "a")
    assert prov.slug == "a"
    assert [s.source_id for s in prov.sources] == ["KDB/raw/s.md"]


def test_entities_for_source(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    prov = adapters.entities_for_source(gdir, "KDB/raw/s.md")
    assert prov.source_id == "KDB/raw/s.md"
    assert sorted(c.slug for c in prov.entities) == ["a", "b"]
