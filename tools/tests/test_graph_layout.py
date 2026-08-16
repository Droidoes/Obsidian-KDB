"""#144 — tests for the precomputed force-layout engine (tools/viewer/graph_layout.py).

The layout is a deterministic numpy/scipy port of the d3 force set that the
viewer template used to run live in the browser (link / many-body capped at
distanceMax / x/y gravity / center / collide). Baking positions at build
time kills the 10-15 min main-thread freeze on every graph-view.html open.
"""
import math

import pytest

from tools.viewer.graph_layout import force_layout

W, H = 1920, 1080


def _data(n_nodes, edges=()):
    """Synthetic neutral-export dict: nodes n0..nN, edges as (i, j, type)."""
    return {
        "nodes": [{"id": f"n{i}", "type": "Entity:concept", "name": f"n{i}",
                   "props": {}} for i in range(n_nodes)],
        "edges": [{"id": f"E:{i}->{j}", "source": f"n{i}", "target": f"n{j}",
                   "type": t} for i, j, t in edges],
        "summary": {"node_types": {}, "edge_types": {}},
    }


def test_deterministic_same_seed_identical_positions():
    d1 = force_layout(_data(30, [(i, i + 1, "LINKS_TO") for i in range(29)]),
                      width=W, height=H, seed=42)
    d2 = force_layout(_data(30, [(i, i + 1, "LINKS_TO") for i in range(29)]),
                      width=W, height=H, seed=42)
    for a, b in zip(d1["nodes"], d2["nodes"]):
        assert (a["x"], a["y"]) == (b["x"], b["y"])


def test_positions_finite_and_centered():
    d = force_layout(_data(50, [(i, (i + 1) % 50, "LINKS_TO") for i in range(50)]),
                     width=W, height=H, seed=42)
    xs = [n["x"] for n in d["nodes"]]
    ys = [n["y"] for n in d["nodes"]]
    assert all(math.isfinite(v) for v in xs + ys)
    # forceCenter recenters the mean onto the canvas center every tick
    assert abs(sum(xs) / len(xs) - W / 2) < 1.0
    assert abs(sum(ys) / len(ys) - H / 2) < 1.0


def test_empty_and_single_node_graphs():
    assert force_layout(_data(0), width=W, height=H)["nodes"] == []
    d = force_layout(_data(1), width=W, height=H)
    assert (abs(d["nodes"][0]["x"] - W / 2) < 1.0
            and abs(d["nodes"][0]["y"] - H / 2) < 1.0)


def test_linked_pair_settles_closer_than_isolated_node():
    # 2 linked nodes + 1 isolated: the link spring should pull the pair
    # well under the isolated node's typical separation.
    d = force_layout(_data(3, [(0, 1, "SUPPORTS")]), width=W, height=H,
                     seed=42)
    p = [(n["x"], n["y"]) for n in d["nodes"]]
    linked = math.dist(p[0], p[1])
    far = min(math.dist(p[0], p[2]), math.dist(p[1], p[2]))
    assert linked < far


def test_disconnected_components_do_not_overlap_badly():
    # two disjoint pairs: all positions finite, both pairs internally close
    d = force_layout(_data(4, [(0, 1, "SUPPORTS"), (2, 3, "SUPPORTS")]),
                     width=W, height=H, seed=42)
    p = [(n["x"], n["y"]) for n in d["nodes"]]
    assert all(math.isfinite(c) for pt in p for c in pt)
    assert math.dist(p[0], p[1]) < 200
    assert math.dist(p[2], p[3]) < 200


def test_scale_graph_completes_and_spreads():
    # 2k-node sparse chain+c ring must finish in reasonable time and spread
    # out (not collapse to a point): std of positions should be sizable.
    n = 2000
    edges = [(i, i + 1, "LINKS_TO") for i in range(n - 1)]
    edges += [(i, (i * 7 + 13) % n, "BELONGS_TO") for i in range(0, n, 10)]
    d = force_layout(_data(n, edges), width=W, height=H, seed=42, ticks=100)
    xs = [nd["x"] for nd in d["nodes"]]
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    assert math.sqrt(var) > 50   # actually spread, not collapsed


def test_input_not_mutated_caller_data_copied():
    d = _data(5, [(0, 1, "LINKS_TO")])
    force_layout(d, width=W, height=H, seed=42)
    assert all("x" not in n for n in d["nodes"])


def test_high_degree_hub_does_not_explode():
    """Regression (2026-08-15): the real graph's coherent-spring clusters
    diverge ~5-6x/tick under a vectorized (Jacobi) link-force update —
    positions blew past 1e13. d3 survives because its link force is
    SEQUENTIAL (Gauss-Seidel): each edge sees the velocity updates of the
    edges before it, making the integration semi-implicit. A 20-clique
    (degree 19, bias ~0.5, k_eff ~ 5.7 > 5.25 stability cliff) reproduces
    the instability class; a star alone does NOT (leaf bias ~1 keeps
    per-node stiffness low)."""
    spokes = 300
    edges = [(0, i, "SUPPORTS") for i in range(1, spokes + 1)]
    d = force_layout(_data(spokes + 1, edges), width=W, height=H, seed=42)
    xs = [n["x"] for n in d["nodes"]]
    ys = [n["y"] for n in d["nodes"]]
    assert all(math.isfinite(v) for v in xs + ys)
    assert max(abs(v) for v in xs) < 1e5
    assert max(abs(v) for v in ys) < 1e5


def test_dense_clique_does_not_explode():
    """The actual regression pin: 20-clique, coherent springs, k_eff over
    the explicit-Euler stability cliff."""
    m = 20
    edges = [(i, j, "LINKS_TO") for i in range(m) for j in range(i + 1, m)]
    d = force_layout(_data(m, edges), width=W, height=H, seed=42)
    xs = [n["x"] for n in d["nodes"]]
    ys = [n["y"] for n in d["nodes"]]
    assert all(math.isfinite(v) for v in xs + ys)
    assert max(abs(v) for v in xs) < 1e5   # Jacobi update blows past 1e13
    assert max(abs(v) for v in ys) < 1e5
