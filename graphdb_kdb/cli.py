"""graphdb-kdb CLI dispatcher.

Subcommands added incrementally per the #63.x plan.
#63.1 — init
#63.3 — neighbors, incoming, path, stats, cypher
#63.4 — pagerank, communities, orphans (analytics)
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

    return p


_DISPATCH = {
    "init": cmd_init,
    "stats": cmd_stats,
    "neighbors": cmd_neighbors,
    "incoming": cmd_incoming,
    "path": cmd_path,
    "cypher": cmd_cypher,
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
