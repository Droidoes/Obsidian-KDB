"""graphdb-kdb CLI dispatcher.

Subcommands added incrementally per the #63.x plan.
#63.1 — init
#63.3 — neighbors, incoming, path, stats, cypher
#63.4 — pagerank, communities, structural-holes, orphans, subgraph-by-source
#63.5 — verify
#63.5 — verify
#63.6 — rebuild, sync
#63.9 — snapshot
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from graphdb_kdb import default_graph_path
from graphdb_kdb.graphdb import GraphDB


def _resolve_graph_dir(args: argparse.Namespace) -> Path:
    return Path(args.graph_dir) if args.graph_dir else default_graph_path()


def _json_default(o: Any):
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    return str(o)


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=_json_default))


def cmd_init(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    print(f"Initializing GraphDB-KDB at: {graph_dir}")
    with GraphDB(graph_dir) as gdb:
        v = gdb.schema_version()
        s = gdb.stats()
    print(f"  schema_version = {v}")
    print(f"  stats          = {s}")
    print("  ok")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        s = gdb.stats()
    if args.json:
        _print_json(s)
    else:
        for k, v in s.items():
            print(f"  {k:<10} {v}")
    return 0


def cmd_neighbors(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        pages = gdb.neighbors(args.slug, direction=args.direction, depth=args.depth)
    if args.json:
        _print_json([dataclasses.asdict(p) for p in pages])
    else:
        if not pages:
            print(f"(no neighbors of {args.slug!r} via direction={args.direction} depth={args.depth})")
        for p in pages:
            print(f"  {p.slug:<40} {p.page_type:<10} {p.title}")
    return 0


def cmd_incoming(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        pages = gdb.incoming_links(args.slug)
    if args.json:
        _print_json([dataclasses.asdict(p) for p in pages])
    else:
        if not pages:
            print(f"(no incoming links to {args.slug!r})")
        for p in pages:
            print(f"  {p.slug:<40} {p.page_type:<10} {p.title}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        path = gdb.shortest_path(args.from_slug, args.to_slug, max_hops=args.max_hops)
    if args.json:
        _print_json(path)
        return 0 if path else 1
    if path is None:
        print(f"(no path from {args.from_slug!r} to {args.to_slug!r} within {args.max_hops} hops)")
        return 1
    print(" -> ".join(path))
    return 0


def cmd_pagerank(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        ranked = gdb.pagerank(top_n=args.top)
    if args.json:
        _print_json([{"slug": s, "score": sc} for s, sc in ranked])
    else:
        if not ranked:
            print("(empty graph)")
        for slug, score in ranked:
            print(f"  {score:0.6f}  {slug}")
    return 0


def cmd_communities(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        membership = gdb.communities()
    if args.json:
        _print_json(membership)
        return 0
    if not membership:
        print("(empty graph)")
        return 0
    # Plain output: group by community id for readability.
    by_comm: dict[int, list[str]] = {}
    for slug, cid in membership.items():
        by_comm.setdefault(cid, []).append(slug)
    for cid in sorted(by_comm):
        print(f"community {cid} ({len(by_comm[cid])}):")
        for slug in sorted(by_comm[cid]):
            print(f"  {slug}")
    return 0


def cmd_structural_holes(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        holes = gdb.structural_holes()
    if args.json:
        _print_json([{"comm_a": a, "comm_b": b, "n_bridges": n} for a, b, n in holes])
        return 0
    if not holes:
        print("(no inter-community bridges)")
        return 0
    for a, b, n in holes:
        print(f"  comm {a:<4} <-> comm {b:<4}  bridges={n}")
    return 0


def cmd_orphans(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        pages = gdb.orphan_pages()
    if args.json:
        _print_json([dataclasses.asdict(p) for p in pages])
        return 0
    if not pages:
        print("(no orphan-candidate pages)")
        return 0
    for p in pages:
        print(f"  {p.slug:<40} {p.page_type:<10} last_run_id={p.last_run_id}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    if args.manifest:
        manifest_path = Path(args.manifest)
    elif args.vault_root:
        manifest_path = Path(args.vault_root) / "state" / "manifest.json"
    else:
        print(
            "verify requires --vault-root <path> (manifest at <root>/state/manifest.json) "
            "or --manifest <path>.",
            file=sys.stderr,
        )
        return 2
    if not manifest_path.is_file():
        print(f"manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    with GraphDB(graph_dir) as gdb:
        result = gdb.verify_against_manifest(manifest_path)
    if args.json:
        _print_json({
            "ok": result.ok,
            "counts": result.counts,
            "divergences": [dataclasses.asdict(d) for d in result.divergences],
        })
        return 0 if result.ok else 1
    if result.ok:
        print("ok — graph and manifest agree")
        for k, v in result.counts.items():
            print(f"  {k:<22} {v}")
        return 0
    print(f"DIVERGENCE — {len(result.divergences)} issue(s)")
    for k, v in result.counts.items():
        print(f"  {k:<22} {v}")
    print()
    for d in result.divergences:
        if d.kind == "attribute_mismatch":
            print(
                f"  [{d.kind}] {d.entity}={d.key} field={d.field} "
                f"manifest={d.manifest_value!r} kuzu={d.kuzu_value!r}"
            )
        else:
            print(f"  [{d.kind}] {d.entity}={d.key}")
    return 1


def cmd_subgraph_by_source(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    with GraphDB(graph_dir) as gdb:
        sg = gdb.subgraph_by_source(args.source_id)
    if args.json:
        _print_json({
            "nodes": [dataclasses.asdict(p) for p in sg["nodes"]],
            "edges": sg["edges"],
        })
        return 0
    nodes = sg["nodes"]
    edges = sg["edges"]
    if not nodes:
        print(f"(source {args.source_id!r} not found or has no supported pages)")
        return 0
    print(f"nodes ({len(nodes)}):")
    for p in nodes:
        print(f"  {p.slug:<40} {p.page_type:<10} {p.title}")
    print(f"edges ({len(edges)}):")
    for e in edges:
        print(f"  {e['from']:<40} -> {e['to']}")
    return 0


def cmd_cypher(args: argparse.Namespace) -> int:
    graph_dir = _resolve_graph_dir(args)
    params: dict[str, Any] = {}
    if args.params:
        params = json.loads(args.params)
    with GraphDB(graph_dir) as gdb:
        rows = gdb.cypher(args.query, params)
    if args.json:
        _print_json(rows)
    else:
        if not rows:
            print("(no rows)")
        for row in rows:
            print(row)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="graphdb-kdb",
        description="GraphDB-KDB: Kuzu-backed multi-source knowledge-graph ontology CLI.",
    )
    p.add_argument(
        "--graph-dir",
        default=None,
        help="Override Kuzu directory location (default: $KDB_GRAPH_PATH or ~/Droidoes/GraphDB-KDB).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create the Kuzu directory + schema (idempotent).")

    p_stats = sub.add_parser("stats", help="Print node/edge counts.")
    p_stats.add_argument("--json", action="store_true", help="JSON output.")

    p_n = sub.add_parser("neighbors", help="BFS expansion from a page slug.")
    p_n.add_argument("slug")
    p_n.add_argument("--depth", type=int, default=1, help="Max hops (default 1).")
    p_n.add_argument(
        "--direction", choices=("out", "in", "both"), default="out",
        help="Edge direction to follow (default 'out').",
    )
    p_n.add_argument("--json", action="store_true", help="JSON output.")

    p_i = sub.add_parser("incoming", help="Sugar for `neighbors --direction in --depth 1`.")
    p_i.add_argument("slug")
    p_i.add_argument("--json", action="store_true", help="JSON output.")

    p_path = sub.add_parser("path", help="Shortest directed path between two pages.")
    p_path.add_argument("from_slug", metavar="FROM_SLUG")
    p_path.add_argument("to_slug", metavar="TO_SLUG")
    p_path.add_argument("--max-hops", type=int, default=10, help="Max search depth (default 10).")
    p_path.add_argument("--json", action="store_true", help="JSON output.")

    p_c = sub.add_parser("cypher", help="Run ad-hoc Cypher (escape hatch).")
    p_c.add_argument("query")
    p_c.add_argument("--params", default=None, help="JSON dict of query parameters.")
    p_c.add_argument("--json", action="store_true", help="JSON output.")

    p_pr = sub.add_parser("pagerank", help="PageRank-ranked pages (NetworkX-backed).")
    p_pr.add_argument("--top", type=int, default=None, help="Truncate to top-N (default: all).")
    p_pr.add_argument("--json", action="store_true", help="JSON output.")

    p_com = sub.add_parser("communities", help="Louvain community assignments.")
    p_com.add_argument("--json", action="store_true", help="JSON output.")

    p_sh = sub.add_parser(
        "structural-holes",
        help="Inter-community bridge counts (sparsest first).",
    )
    p_sh.add_argument("--json", action="store_true", help="JSON output.")

    p_o = sub.add_parser("orphans", help="List orphan-candidate pages.")
    p_o.add_argument("--json", action="store_true", help="JSON output.")

    p_sg = sub.add_parser(
        "subgraph-by-source",
        help="Export a source's induced (nodes, edges) subgraph.",
    )
    p_sg.add_argument("source_id", metavar="SOURCE_ID")
    p_sg.add_argument("--json", action="store_true", help="JSON output.")

    p_v = sub.add_parser(
        "verify",
        help="Diff Kuzu state vs manifest.json. Exit 0 = perfect; 1 = divergence.",
    )
    p_v.add_argument(
        "--vault-root", default=None,
        help="Vault root (manifest read from <root>/state/manifest.json).",
    )
    p_v.add_argument(
        "--manifest", default=None,
        help="Explicit manifest.json path (overrides --vault-root).",
    )
    p_v.add_argument("--json", action="store_true", help="JSON output.")

    return p


_DISPATCH = {
    "init": cmd_init,
    "stats": cmd_stats,
    "neighbors": cmd_neighbors,
    "incoming": cmd_incoming,
    "path": cmd_path,
    "cypher": cmd_cypher,
    "pagerank": cmd_pagerank,
    "communities": cmd_communities,
    "structural-holes": cmd_structural_holes,
    "orphans": cmd_orphans,
    "subgraph-by-source": cmd_subgraph_by_source,
    "verify": cmd_verify,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = _DISPATCH.get(args.cmd)
    if handler is None:
        parser.error(f"unknown command: {args.cmd}")
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
