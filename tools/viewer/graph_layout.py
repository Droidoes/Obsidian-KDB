"""graph_layout — deterministic precomputed force layout for the KDB viewer (#144).

Faithful numpy/scipy port of the d3-force set the viewer template
(`kdb_graph_viewer_template.html`) used to run live in the browser on every
open — 8k nodes × ~300 ticks on the browser main thread hung the desktop for
10-15 minutes, and positions were never persisted. Now the builder computes
the layout once and bakes x/y into the HTML; the browser renders static.

Forces ported (parameters identical to the template):
  link    — per-type target distance (LINKS_TO 110 / SUPPORTS 70 /
            BELONGS_TO 130 / default 80), strength 0.6, degree bias
  charge  — many-body strength -240, distanceMax 280. d3 approximates with
            Barnes-Hut (theta 0.9); we do EXACT local summation via cKDTree
            pairs (same physics within the cap, no approximation)
  x / y   — gravity toward canvas center, strength 0.08
  center  — recenter the position mean onto the canvas center each tick
  collide — radius getNodeRadius(deg) + 14, 2 iterations, r²-weighted split

d3 simulation mechanics preserved: phyllotaxis initial placement,
velocityDecay 0.6, alpha decay over 300 ticks, 1e-6 jiggle on exact
coincidence. Fixed seed => byte-identical layouts for identical input.

CRITICAL d3 semantic (2026-08-15 explosion fix): the link force is applied
SEQUENTIALLY (Gauss-Seidel) — each edge reads velocities already updated by
the edges before it, making spring integration semi-implicit. A vectorized
(Jacobi) link update is unconditionally unstable for coherent springs once
per-node stiffness passes the explicit-Euler cliff (k_eff > ~5); on the real
graph a degree-18 node diverged ~5-6x/tick and positions blew past 1e13.
Charge and collide stay vectorized: their forces are bounded (<=240/pair,
<=overlap) and mostly cancel, so Jacobi is safe there — and a sequential
charge pass over millions of pairs would be prohibitively slow.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

LINK_DISTANCE = {"LINKS_TO": 110.0, "SUPPORTS": 70.0, "BELONGS_TO": 130.0}
LINK_DEFAULT_DISTANCE = 80.0
LINK_STRENGTH = 0.6
CHARGE_STRENGTH = -240.0
CHARGE_DISTANCE_MAX = 280.0
GRAVITY_STRENGTH = 0.08
COLLIDE_PADDING = 14.0
COLLIDE_ITERATIONS = 2
VELOCITY_DECAY = 0.6
DEFAULT_TICKS = 300
INITIAL_RADIUS = 10.0
INITIAL_ANGLE = math.pi * (3.0 - math.sqrt(5.0))  # golden-angle phyllotaxis
ALPHA_MIN = 0.001


def _node_radius(deg: float) -> float:
    """Template getNodeRadius(): degree-scaled, 2/3 of the bake-off scale."""
    return max(7.0, min(22.0, 5.5 + 1.6 * math.sqrt(deg))) * 2.0 / 3.0


def force_layout(data: dict, *, width: int = 1920, height: int = 1080,
                 seed: int = 42, ticks: int = DEFAULT_TICKS) -> dict:
    """Return a COPY of the neutral-export dict with x/y baked per node."""
    nodes_in = data.get("nodes", [])
    edges_in = data.get("edges", [])
    out = {**data,
           "nodes": [dict(n) for n in nodes_in],
           "edges": list(edges_in),
           "summary": data.get("summary", {}),
           "layout": {"width": width, "height": height,
                      "seed": seed, "ticks": ticks,
                      "engine": "graph_layout.force_layout v1"}}
    n = len(nodes_in)
    if n == 0:
        return out

    id_index = {nd["id"]: i for i, nd in enumerate(nodes_in)}
    rng = np.random.default_rng(seed)

    # --- static per-node / per-edge tables ---
    idx_pairs = [(id_index[e["source"]], id_index[e["target"]])
                 for e in edges_in
                 if e["source"] in id_index and e["target"] in id_index]
    deg = np.zeros(n)
    for s, t in idx_pairs:
        deg[s] += 1
        deg[t] += 1
    radii = np.array([_node_radius(d) for d in deg]) + COLLIDE_PADDING

    if idx_pairs:
        src = np.array([p[0] for p in idx_pairs])
        tgt = np.array([p[1] for p in idx_pairs])
        link_dist = np.array([
            LINK_DISTANCE.get(e["type"], LINK_DEFAULT_DISTANCE)
            for e in edges_in
            if e["source"] in id_index and e["target"] in id_index])
        link_bias = deg[src] / (deg[src] + deg[tgt])
    else:
        src = tgt = np.array([], dtype=int)
        link_dist = link_bias = np.array([])

    # --- phyllotaxis initial placement (d3 initializeNodes) ---
    i = np.arange(n)
    r0 = INITIAL_RADIUS * np.sqrt(0.5 + i)
    a0 = i * INITIAL_ANGLE
    pos = np.column_stack([r0 * np.cos(a0), r0 * np.sin(a0)])
    vel = np.zeros((n, 2))

    center = np.array([width / 2.0, height / 2.0])
    alpha = 1.0
    alpha_decay = 1.0 - ALPHA_MIN ** (1.0 / ticks) if ticks else 1.0

    # Gauss-Seidel link force needs plain-list views for its sequential loop
    es = src.tolist()
    et = tgt.tolist()
    edist = link_dist.tolist()
    ebias = link_bias.tolist()
    px = pos[:, 0].copy()
    py = pos[:, 1].copy()
    vx = vel[:, 0].copy()
    vy = vel[:, 1].copy()
    jiggle = rng.uniform(-0.5e-6, 0.5e-6, size=(max(len(es), 1), ticks, 2))

    for tick in range(ticks):
        alpha += (0.0 - alpha) * alpha_decay

        # --- link (SEQUENTIAL, d3 Gauss-Seidel semantics: each edge reads
        #     velocities already updated by earlier edges this tick — a
        #     vectorized Jacobi update is unconditionally unstable for
        #     coherent springs past the explicit-Euler stiffness cliff) ---
        for k in range(len(es)):
            s = es[k]
            t = et[k]
            dx = (px[t] + vx[t]) - (px[s] + vx[s]) or jiggle[k, tick, 0]
            dy = (py[t] + vy[t]) - (py[s] + vy[s]) or jiggle[k, tick, 1]
            ln = math.sqrt(dx * dx + dy * dy)
            f = (ln - edist[k]) / ln * alpha * LINK_STRENGTH
            fx = dx * f
            fy = dy * f
            b = ebias[k]
            vx[t] -= fx * b
            vy[t] -= fy * b
            vx[s] += fx * (1.0 - b)
            vy[s] += fy * (1.0 - b)

        pos = np.column_stack([px, py])
        vel = np.column_stack([vx, vy])
        eff = pos + vel  # d3 forces read x + vx

        # --- charge (exact local summation within distanceMax) ---
        tree = cKDTree(eff)
        pairs = tree.query_pairs(CHARGE_DISTANCE_MAX, output_type="ndarray")
        if len(pairs):
            pi, pj = pairs[:, 0], pairs[:, 1]
            d = eff[pj] - eff[pi]
            zero = (np.abs(d) < 1e-12).all(axis=1)
            if zero.any():
                d[zero] = rng.uniform(-0.5e-6, 0.5e-6, size=(zero.sum(), 2))
            w = np.maximum((d * d).sum(axis=1), 1.0)      # distanceMin² = 1
            f = (CHARGE_STRENGTH * alpha / w)[:, None] * d
            np.add.at(vel, pi, f)
            np.add.at(vel, pj, -f)

        # --- x / y gravity ---
        vel += (center - pos) * (GRAVITY_STRENGTH * alpha)

        # --- center (d3 shifts positions directly, mid-force-order) ---
        pos += (center - pos.mean(axis=0))

        # --- collide (2 iterations, r²-weighted split) ---
        for _c in range(COLLIDE_ITERATIONS):
            effc = pos + vel
            tree = cKDTree(effc)
            max_r = float(radii.max())
            pairs = tree.query_pairs(2.0 * max_r, output_type="ndarray")
            if not len(pairs):
                break
            pi, pj = pairs[:, 0], pairs[:, 1]
            rsum = radii[pi] + radii[pj]
            d = effc[pj] - effc[pi]
            ln = np.linalg.norm(d, axis=1)
            hit = ln < rsum
            if not hit.any():
                break
            pi, pj, d, ln, rsum = pi[hit], pj[hit], d[hit], ln[hit], rsum[hit]
            ln = np.maximum(ln, 1e-9)
            l = ((ln - rsum) / ln)[:, None] * d            # overlap push
            rb_i = (radii[pj] ** 2 / (radii[pi] ** 2 + radii[pj] ** 2))[:, None]
            np.add.at(vel, pi, l * rb_i)
            np.add.at(vel, pj, -l * (1.0 - rb_i))

        # --- integrate (d3: velocityDecay then x += vx) ---
        vel *= VELOCITY_DECAY
        pos += vel

        # write back into the Gauss-Seidel list views for the next tick
        px = pos[:, 0]
        py = pos[:, 1]
        vx = vel[:, 0]
        vy = vel[:, 1]

    for nd, (x, y) in zip(out["nodes"], pos):
        nd["x"] = round(float(x), 2)
        nd["y"] = round(float(y), 2)
    return out
