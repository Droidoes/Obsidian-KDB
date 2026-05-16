"""Tests for graphdb_kdb.ingestor.apply_cleanup (#68).

apply_cleanup DETACH DELETEs Entity nodes by retraction['retracted_slugs'].
It is the graph-side counterpart of `kdb-clean orphans`.
"""
from __future__ import annotations

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


def _seed(gdb, slugs, *, source_id="KDB/raw/s.md"):
    """Ingest one compile run with the given page slugs as one source."""
    cr = make_compile_result([
        make_compiled_source(source_id, [make_page(s) for s in slugs])
    ])
    scan = make_scan([make_scan_entry(source_id)])
    gdb.apply_compile_result(cr, scan, "seed-run")


def test_apply_cleanup_deletes_retracted_entity(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb, ["alpha"])
        assert gdb.get_entity("alpha") is not None
        res = gdb.apply_cleanup({"retracted_slugs": ["alpha"]}, "clean-1")
        assert gdb.get_entity("alpha") is None
        assert res.entities_deleted == 1


def test_apply_cleanup_deletes_only_listed_slugs(graph_dir):
    # slug-safe (graph side): retract 'solo' only — 'foo' must survive.
    with GraphDB(graph_dir) as gdb:
        _seed(gdb, ["foo", "solo"])
        res = gdb.apply_cleanup({"retracted_slugs": ["solo"]}, "clean-1")
        assert gdb.get_entity("solo") is None
        assert gdb.get_entity("foo") is not None
        assert res.entities_deleted == 1


def test_apply_cleanup_removes_supports_and_links_edges(graph_dir):
    with GraphDB(graph_dir) as gdb:
        # 'a' links to 'b'; both supported by the source.
        cr = make_compile_result([
            make_compiled_source("KDB/raw/s.md", [
                make_page("a", outgoing_links=["b"]),
                make_page("b"),
            ])
        ])
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        gdb.apply_compile_result(cr, scan, "seed-run")
        assert gdb.stats()["links_to"] == 1
        gdb.apply_cleanup({"retracted_slugs": ["b"]}, "clean-1")
        s = gdb.stats()
        assert s["entities"] == 1          # only 'a' remains
        assert s["links_to"] == 0          # a->b edge gone with b
        assert s["supports"] == 1          # source still SUPPORTS 'a'


def test_apply_cleanup_absent_slug_is_noop(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb, ["alpha"])
        res = gdb.apply_cleanup({"retracted_slugs": ["never-existed"]}, "clean-1")
        assert res.entities_deleted == 0
        assert gdb.get_entity("alpha") is not None
