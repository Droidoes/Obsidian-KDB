"""Tests for kdb_graph.analytics (#63.4).

Reference graphs are small enough that algorithm output is verifiable by
hand. Per D40 the analytics layer is a hybrid: Kuzu fetches topology,
NetworkX/python-louvain computes the algorithm.
"""
from __future__ import annotations

import pytest

from kdb_graph.graphdb import GraphDB
from kdb_graph.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


# ---------- seed helpers ----------

def _seed_star(gdb: GraphDB) -> None:
    """hub -> {leaf-1, leaf-2, leaf-3}. The hub is the unambiguous PageRank winner
    if we also add reciprocal links so it accumulates inbound mass.
    """
    pages = [
        make_page("hub", outgoing_links=["leaf-1", "leaf-2", "leaf-3"]),
        make_page("leaf-1", outgoing_links=["hub"]),
        make_page("leaf-2", outgoing_links=["hub"]),
        make_page("leaf-3", outgoing_links=["hub"]),
    ]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    gdb.apply_compile_result(cr, scan, "run-1")


def _seed_two_clusters_bridge(gdb: GraphDB) -> None:
    """Two tight triangles linked by a single bridge edge.

    Cluster A: a1 <-> a2 <-> a3 <-> a1   (3 reciprocal pairs)
    Cluster B: b1 <-> b2 <-> b3 <-> b1
    Bridge:    a1 -> b1

    Louvain on the undirected projection should produce exactly two
    communities split on the triangle boundary.
    """
    pages = [
        make_page("a1", outgoing_links=["a2", "a3", "b1"]),
        make_page("a2", outgoing_links=["a1", "a3"]),
        make_page("a3", outgoing_links=["a1", "a2"]),
        make_page("b1", outgoing_links=["b2", "b3"]),
        make_page("b2", outgoing_links=["b1", "b3"]),
        make_page("b3", outgoing_links=["b1", "b2"]),
    ]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    gdb.apply_compile_result(cr, scan, "run-1")


# ---------- 1. PageRank ----------

def test_pagerank_empty_graph(graph_dir):
    with GraphDB(graph_dir) as gdb:
        assert gdb.pagerank() == []


def test_pagerank_star_hub_is_highest(graph_dir):
    """hub receives 3 inbound edges; leaves each receive 1 → hub wins."""
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        ranked = gdb.pagerank()
    slugs = [s for s, _ in ranked]
    assert slugs[0] == "hub"
    # All four nodes show up exactly once.
    assert sorted(slugs) == ["hub", "leaf-1", "leaf-2", "leaf-3"]
    # Scores sum to ~1.0 (NetworkX normalization).
    assert abs(sum(score for _, score in ranked) - 1.0) < 1e-6


def test_pagerank_top_n_truncates(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        top1 = gdb.pagerank(top_n=1)
        top2 = gdb.pagerank(top_n=2)
    assert len(top1) == 1
    assert len(top2) == 2
    assert top1[0][0] == "hub"


def test_pagerank_top_n_zero_returns_empty(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        assert gdb.pagerank(top_n=0) == []


def test_pagerank_rejects_negative_top_n(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        with pytest.raises(ValueError, match="top_n"):
            gdb.pagerank(top_n=-1)


# ---------- 2. Communities (Louvain) ----------

def test_communities_empty_graph(graph_dir):
    with GraphDB(graph_dir) as gdb:
        assert gdb.communities() == {}


def test_communities_two_clusters_separated(graph_dir):
    """Two triangles + one bridge: Louvain finds 2 communities split on the triangle boundary."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_clusters_bridge(gdb)
        membership = gdb.communities()
    # All 6 nodes assigned.
    assert set(membership) == {"a1", "a2", "a3", "b1", "b2", "b3"}
    # Each triangle is internally homogeneous.
    a_comms = {membership[s] for s in ("a1", "a2", "a3")}
    b_comms = {membership[s] for s in ("b1", "b2", "b3")}
    assert len(a_comms) == 1
    assert len(b_comms) == 1
    # And the two triangles land in different communities.
    assert a_comms != b_comms


def test_communities_reproducible(graph_dir):
    """Fixed random_state in the analytics module → identical assignments across calls."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_clusters_bridge(gdb)
        m1 = gdb.communities()
        m2 = gdb.communities()
    assert m1 == m2


def test_communities_rejects_unknown_algorithm(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        with pytest.raises(ValueError, match="unsupported"):
            gdb.communities(algorithm="leiden")


# ---------- 3. Structural holes ----------

def test_structural_holes_empty_graph(graph_dir):
    with GraphDB(graph_dir) as gdb:
        assert gdb.structural_holes() == []


def test_structural_holes_single_bridge_pair(graph_dir):
    """Two triangles linked by 1 directed edge → exactly one (comm_a, comm_b, 1)."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_clusters_bridge(gdb)
        holes = gdb.structural_holes()
    assert len(holes) == 1
    a, b, n = holes[0]
    assert n == 1
    assert a < b


def test_structural_holes_pair_count_increases_with_bridges(graph_dir):
    """Adding a second cross-community edge bumps n_bridges to 2."""
    with GraphDB(graph_dir) as gdb:
        # Same shape as two-clusters seed, plus a2 -> b2 second bridge.
        pages = [
            make_page("a1", outgoing_links=["a2", "a3", "b1"]),
            make_page("a2", outgoing_links=["a1", "a3", "b2"]),
            make_page("a3", outgoing_links=["a1", "a2"]),
            make_page("b1", outgoing_links=["b2", "b3"]),
            make_page("b2", outgoing_links=["b1", "b3"]),
            make_page("b3", outgoing_links=["b1", "b2"]),
        ]
        cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        gdb.apply_compile_result(cr, scan, "run-1")
        holes = gdb.structural_holes()
    assert len(holes) == 1
    assert holes[0][2] == 2


def test_structural_holes_single_community_returns_empty(graph_dir):
    """All-internal edges → no inter-community pairs to surface."""
    with GraphDB(graph_dir) as gdb:
        # Tight triangle only, no bridge.
        pages = [
            make_page("a1", outgoing_links=["a2", "a3"]),
            make_page("a2", outgoing_links=["a1", "a3"]),
            make_page("a3", outgoing_links=["a1", "a2"]),
        ]
        cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        gdb.apply_compile_result(cr, scan, "run-1")
        holes = gdb.structural_holes()
    assert holes == []
