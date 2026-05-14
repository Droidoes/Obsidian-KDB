"""graphdb-kdb CLI dispatcher.

Subcommands added incrementally per the #63.x plan. #63.1 ships `init`; others
land in #63.3 (read queries), #63.5 (verify), #63.6 (rebuild), #63.9 (snapshot).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graphdb_kdb import default_graph_path
from graphdb_kdb.graphdb import GraphDB


def cmd_init(args: argparse.Namespace) -> int:
    graph_dir = Path(args.graph_dir) if args.graph_dir else default_graph_path()
    print(f"Initializing GraphDB-KDB at: {graph_dir}")
    with GraphDB(graph_dir) as gdb:
        v = gdb.schema_version()
        s = gdb.stats()
    print(f"  schema_version = {v}")
    print(f"  stats          = {s}")
    print("  ok")
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
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
