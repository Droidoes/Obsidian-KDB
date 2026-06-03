"""Tests for kdb_graph.queries (#63.3 — read API).

Covers the public read primitives surfaced via GraphDB methods:
neighbors / incoming_links / outgoing_links / shortest_path /
entities_for_source / sources_for_entity / subgraph_by_source /
orphan_entities / cypher.
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


# ---------- fixtures: pre-populated graphs ----------

def _seed_linear_chain(gdb: GraphDB) -> None:
    """a -> b -> c -> d (single source supporting all four pages)."""
    pages = [
        make_page("a", outgoing_links=["b"]),
        make_page("b", outgoing_links=["c"]),
        make_page("c", outgoing_links=["d"]),
        make_page("d"),
    ]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    gdb.apply_compile_result(cr, scan, "run-1")


def _seed_star(gdb: GraphDB) -> None:
    """hub -> {leaf-1, leaf-2, leaf-3}, plus an isolated 'lonely'."""
    pages = [
        make_page("hub", outgoing_links=["leaf-1", "leaf-2", "leaf-3"]),
        make_page("leaf-1"),
        make_page("leaf-2"),
        make_page("leaf-3"),
        make_page("lonely"),
    ]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    gdb.apply_compile_result(cr, scan, "run-1")


# ---------- 1. neighbors: direction + depth ----------

def test_neighbors_depth_1_out(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("a", direction="out", depth=1)
    assert [p.slug for p in n] == ["b"]


def test_neighbors_depth_2_out(graph_dir):
    """*1..2 returns all distinct nodes reachable in 1 or 2 hops."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("a", direction="out", depth=2)
    assert [p.slug for p in n] == ["b", "c"]


def test_neighbors_depth_3_out(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("a", direction="out", depth=3)
    assert [p.slug for p in n] == ["b", "c", "d"]


def test_neighbors_depth_1_in(graph_dir):
    """Inbound depth-1 to 'c' is just 'b'."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("c", direction="in", depth=1)
    assert [p.slug for p in n] == ["b"]


def test_neighbors_depth_2_in(graph_dir):
    """Inbound depth-2 to 'c' returns 'a' and 'b'."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("c", direction="in", depth=2)
    assert [p.slug for p in n] == ["a", "b"]


def test_neighbors_direction_both(graph_dir):
    """Undirected traversal from 'c' depth-1 reaches both 'b' (in) and 'd' (out)."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("c", direction="both", depth=1)
    assert [p.slug for p in n] == ["b", "d"]


def test_neighbors_out_direction_excludes_inbound(graph_dir):
    """#81 (§4.3 fail test ii): direction='out' must NOT return inbound
    neighbors. Linear chain a→b→c→d: out-traversal from 'c' yields only
    'd', never 'b'. Regression guard against a future change that
    accidentally widens 'out' to 'both'."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("c", direction="out", depth=1)
    slugs = [p.slug for p in n]
    assert slugs == ["d"]
    assert "b" not in slugs, "out direction leaked inbound neighbor 'b'"


def test_neighbors_in_direction_excludes_outbound(graph_dir):
    """#81 (§4.3 fail test ii): symmetric guard — direction='in' must
    NOT return outbound neighbors. Linear chain a→b→c→d: in-traversal
    from 'c' yields only 'b', never 'd'."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.neighbors("c", direction="in", depth=1)
    slugs = [p.slug for p in n]
    assert slugs == ["b"]
    assert "d" not in slugs, "in direction leaked outbound neighbor 'd'"


def test_neighbors_empty_for_isolated_node(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        n = gdb.neighbors("lonely", direction="out", depth=1)
    assert n == []


def test_neighbors_excludes_start_node(graph_dir):
    """The start node itself is filtered out of the result set."""
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        n = gdb.neighbors("hub", direction="out", depth=2)
    slugs = [p.slug for p in n]
    assert "hub" not in slugs
    assert sorted(slugs) == ["leaf-1", "leaf-2", "leaf-3"]


def test_neighbors_rejects_invalid_direction(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        with pytest.raises(ValueError, match="direction"):
            gdb.neighbors("a", direction="sideways", depth=1)


def test_neighbors_rejects_zero_depth(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        with pytest.raises(ValueError, match="depth"):
            gdb.neighbors("a", direction="out", depth=0)


# ---------- 2. incoming_links / outgoing_links convenience ----------

def test_incoming_links_convenience(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        n = gdb.incoming_links("c")
    assert [p.slug for p in n] == ["b"]


def test_outgoing_links_convenience(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        n = gdb.outgoing_links("hub")
    assert [p.slug for p in n] == ["leaf-1", "leaf-2", "leaf-3"]


# ---------- 3. shortest_path ----------

def test_shortest_path_direct_edge(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        path = gdb.shortest_path("a", "b")
    assert path == ["a", "b"]


def test_shortest_path_multi_hop(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        path = gdb.shortest_path("a", "d")
    assert path == ["a", "b", "c", "d"]


def test_shortest_path_same_node(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        path = gdb.shortest_path("b", "b")
    assert path == ["b"]


def test_shortest_path_unreachable_returns_none(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_star(gdb)
        # hub -> leaf-1 exists, but leaf-1 -> hub does NOT (directed)
        path = gdb.shortest_path("leaf-1", "leaf-2")
    assert path is None


def test_shortest_path_max_hops_cutoff(graph_dir):
    """a->b->c->d is 3 hops; max_hops=2 prevents reaching d."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        path = gdb.shortest_path("a", "d", max_hops=2)
    assert path is None


def test_shortest_path_same_unknown_node_returns_none(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        path = gdb.shortest_path("ghost", "ghost")
    assert path is None


def test_shortest_path_rejects_zero_max_hops(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        with pytest.raises(ValueError, match="max_hops"):
            gdb.shortest_path("a", "b", max_hops=0)


# ---------- 4. entities_for_source / sources_for_entity ----------

def test_entities_for_source(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        pages = gdb.entities_for_source("KDB/raw/s.md")
    assert sorted(p.slug for p in pages) == ["a", "b", "c", "d"]


def test_pages_for_unknown_source_is_empty(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        pages = gdb.entities_for_source("KDB/raw/missing.md")
    assert pages == []


def test_sources_for_entity(graph_dir):
    """Same page supported by two different sources yields both sources."""
    with GraphDB(graph_dir) as gdb:
        cs1 = make_compiled_source("KDB/raw/s1.md", [make_page("shared")])
        cs2 = make_compiled_source("KDB/raw/s2.md", [make_page("shared")])
        cr = make_compile_result([cs1, cs2])
        scan = make_scan([
            make_scan_entry("KDB/raw/s1.md"),
            make_scan_entry("KDB/raw/s2.md"),
        ])
        gdb.apply_compile_result(cr, scan, "run-1")
        sources = gdb.sources_for_entity("shared")
    assert sorted(s.source_id for s in sources) == ["KDB/raw/s1.md", "KDB/raw/s2.md"]


# ---------- 5. subgraph_by_source ----------

def test_subgraph_by_source_returns_nodes_and_edges(graph_dir):
    """Edges induced by a source = LINKS_TO between its supported pages."""
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        sg = gdb.subgraph_by_source("KDB/raw/s.md")
    node_slugs = sorted(p.slug for p in sg["nodes"])
    assert node_slugs == ["a", "b", "c", "d"]
    edges = [(e["from"], e["to"]) for e in sg["edges"]]
    assert edges == [("a", "b"), ("b", "c"), ("c", "d")]
    # Each edge carries run_id from the ingestion run.
    assert all(e["run_id"] == "run-1" for e in sg["edges"])


def test_subgraph_by_unknown_source_is_empty(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        sg = gdb.subgraph_by_source("KDB/raw/missing.md")
    assert sg == {"nodes": [], "edges": []}


# ---------- 6. orphan_entities ----------

def test_orphan_entities_listing(graph_dir):
    """Pages flagged orphan_candidate at ingestion are returned here."""
    src = "KDB/raw/s.md"
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r1",
        )
        # Drop 'b' from this source — b becomes orphan_candidate.
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a")])]),
            scan, "r2",
        )
        orphans = gdb.orphan_entities()
    assert [p.slug for p in orphans] == ["b"]


def test_orphan_entities_empty_when_none(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        orphans = gdb.orphan_entities()
    assert orphans == []


# ---------- 7. cypher escape hatch ----------

def test_cypher_returns_list_of_dicts(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        rows = gdb.cypher(
            "MATCH (p:Entity) RETURN p.slug AS slug ORDER BY p.slug"
        )
    assert rows == [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}, {"slug": "d"}]


def test_cypher_with_params(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        rows = gdb.cypher(
            "MATCH (p:Entity {slug: $slug}) RETURN p.slug AS slug",
            {"slug": "c"},
        )
    assert rows == [{"slug": "c"}]


def test_cypher_empty_result(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        rows = gdb.cypher("MATCH (p:Entity {slug: 'ghost'}) RETURN p.slug")
    assert rows == []


# ---------- #81: marked bench tests (opt-in via `pytest -m bench`) ----------

@pytest.mark.bench
def test_shortest_path_runtime_guard(graph_dir):
    """#81 (§3.1 row 5a regression-guardrail): shortest_path on a small
    graph completes well under a runtime ceiling tight enough to catch
    gradual drift, loose enough to absorb host-load jitter. Opt-in via
    `pytest -m bench`. Threshold 100 ms on a 4-node linear chain —
    production-realistic operations finish in single-digit ms; 100 ms
    is ~50x the typical observed runtime, which catches order-of-
    magnitude regressions while staying robust against transient load."""
    import time

    with GraphDB(graph_dir) as gdb:
        _seed_linear_chain(gdb)
        t0 = time.perf_counter()
        path = gdb.shortest_path("a", "d")
        elapsed = time.perf_counter() - t0
    assert path == ["a", "b", "c", "d"]
    assert elapsed < 0.1, (
        f"shortest_path('a','d') on 4-node chain took {elapsed:.3f}s "
        f"(threshold 0.1s) — runtime regression"
    )
