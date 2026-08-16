"""kdb-fts — CLI for the parallel extraction/ranking system (#145).

Phase 0 surface: intake / search / status (no LLM). Later phases add
gate/extract/rank/review to this same argparse tree (blueprint §8).
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from kdb_fts import author_map, intake, ledger, state


def _default_raw_root() -> Path:
    from common import paths

    return paths.kdb_root() / "raw" / "joseph-ft-public-gmail"


def _cmd_intake(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    run_id = datetime.now().astimezone().isoformat(timespec="seconds")
    stats = intake.run_intake(
        conn, Path(args.raw_root).expanduser(), run_id, state_root=root
    )
    print(f"seen={stats['seen']} upserted={stats['upserted']} deleted={stats['deleted']}")
    print(f"cleanliness: {stats['by_cleanliness']}")
    print(f"content_kind: {stats['by_content_kind']}")
    print(f"raw_author_strings={stats['raw_author_strings']}")
    return 0


def _cmd_search(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    hits = ledger.search(conn, args.query, limit=args.n)
    if not hits:
        print("no hits")
        return 0
    for h in hits:
        print(f"{h['article_id']}  {h['title'] or '(untitled)'}  — {h['author'] or '?'}")
        print(f"    {h['snippet']}")
    return 0


def _cmd_status(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    print(f"db: {root / 'ledger.sqlite'}")
    for label, sql in (
        ("cleanliness", "SELECT cleanliness, COUNT(*) FROM articles GROUP BY 1 ORDER BY 1"),
        ("content_kind", "SELECT COALESCE(content_kind,'unknown'), COUNT(*) FROM articles GROUP BY 1 ORDER BY 1"),
    ):
        print(f"{label}:")
        for row in conn.execute(sql):
            print(f"  {row[0]}: {row[1]}")
    n_authors = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    unm = author_map.unmapped(conn)
    print(f"authors: {n_authors} canonical, {len(unm)} unmapped raw strings")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kdb-fts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("intake", help="walk raw tree → ledger + FTS rebuild")
    p.add_argument("--raw-root", default=str(_default_raw_root()))
    p.add_argument("--state", default=None, help="override state root (else $KDB_FTS_PATH else <vault>/KDB/fts)")
    p.set_defaults(fn=_cmd_intake)

    p = sub.add_parser("search", help="FTS5 query over title/author/body")
    p.add_argument("query")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_search)

    p = sub.add_parser("status", help="counts by cleanliness/kind, authors, db path")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_status)

    args = parser.parse_args(argv)
    return args.fn(args)
