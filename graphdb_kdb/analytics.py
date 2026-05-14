"""Hybrid analytics for graphdb_kdb (#63.4).

Per D40 (hybrid strategy): Kuzu Cypher fetches topology (node/edge lists);
NetworkX + python-louvain compute the algorithms.

Split out of queries.py because:
- Different conceptual category (graph algorithms vs direct Cypher reads).
- Heavier optional imports (networkx, community) live behind one module.
- Test cadence differs — analytics needs known-output reference graphs.
"""
from __future__ import annotations

import community as community_louvain  # python-louvain
import kuzu
import networkx as nx


_LOUVAIN_RANDOM_STATE = 42  # reproducibility for tests + cross-session stability


# ---------- topology loaders ----------

def _to_digraph(conn: kuzu.Connection) -> nx.DiGraph:
    """Load (Entity, LINKS_TO) topology as a directed graph.

    Self-loops are skipped (no semantic meaning here and they distort PageRank).
    """
    g = nx.DiGraph()
    r = conn.execute("MATCH (e:Entity) RETURN e.slug")
    while r.has_next():
        g.add_node(r.get_next()[0])
    r = conn.execute("MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug")
    while r.has_next():
        row = r.get_next()
        a, b = row[0], row[1]
        if a != b:
            g.add_edge(a, b)
    return g


def _to_undirected(conn: kuzu.Connection) -> nx.Graph:
    """Undirected projection of (Entity, LINKS_TO) for Louvain.

    Louvain modularity is defined on undirected graphs; we project by
    treating reciprocal edges as a single undirected edge.
    """
    g = nx.Graph()
    r = conn.execute("MATCH (e:Entity) RETURN e.slug")
    while r.has_next():
        g.add_node(r.get_next()[0])
    r = conn.execute("MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug")
    while r.has_next():
        row = r.get_next()
        a, b = row[0], row[1]
        if a != b:
            g.add_edge(a, b)
    return g


# ---------- PageRank ----------

def pagerank(
    conn: kuzu.Connection,
    *,
    top_n: int | None = None,
) -> list[tuple[str, float]]:
    """PageRank over the LINKS_TO directed graph.

    Returns `[(slug, score), ...]` sorted by score desc, slug asc.
    `top_n` truncates the result (None = return all). Empty graph → `[]`.
    """
    g = _to_digraph(conn)
    if not g.nodes:
        return []
    scores = nx.pagerank(g)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if top_n is not None:
        if top_n < 0:
            raise ValueError(f"top_n must be >= 0; got {top_n}")
        ranked = ranked[:top_n]
    return ranked


# ---------- Communities (Louvain) ----------

def communities(
    conn: kuzu.Connection,
    *,
    algorithm: str = "louvain",
) -> dict[str, int]:
    """Community assignment per Entity slug.

    Currently supports only Louvain (python-louvain). Returns a dict
    mapping slug → community_id (small ints). Empty graph → `{}`.
    """
    if algorithm != "louvain":
        raise ValueError(f"unsupported community algorithm: {algorithm!r}")
    g = _to_undirected(conn)
    if not g.nodes:
        return {}
    return community_louvain.best_partition(g, random_state=_LOUVAIN_RANDOM_STATE)


# ---------- Structural holes ----------

def structural_holes(
    conn: kuzu.Connection,
) -> list[tuple[int, int, int]]:
    """Inter-community bridge counts — pairs of communities connected by
    LINKS_TO edges, sorted ascending by edge count (sparsest bridges first).

    Returns `[(comm_a, comm_b, n_bridges), ...]` with `comm_a < comm_b`.
    Pairs with zero bridges are NOT enumerated (would be O(C²) noise);
    surfacing the sparsest *existing* bridges is the knowledge-hole signal.
    Empty graph or single community → `[]`.
    """
    membership = communities(conn)
    if not membership:
        return []
    g = _to_digraph(conn)
    pair_counts: dict[tuple[int, int], int] = {}
    for u, v in g.edges():
        cu = membership.get(u)
        cv = membership.get(v)
        if cu is None or cv is None or cu == cv:
            continue
        key = (cu, cv) if cu < cv else (cv, cu)
        pair_counts[key] = pair_counts.get(key, 0) + 1
    return sorted(
        ((a, b, n) for (a, b), n in pair_counts.items()),
        key=lambda t: (t[2], t[0], t[1]),
    )
