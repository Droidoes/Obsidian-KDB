#!/usr/bin/env python3
"""ONE-OFF (#151, CLEAN-UP-RUN #1, 2026-08-19): quarantine unsubscribed-author sources.

Moves every md source whose canonical author is on the post-calibration
blacklist out of the gmail-substack raw tree into `<raw>/_blacklist/`
(move-not-delete per the 2026-08-15 `_promo/` precedent; movelog at
`_blacklist/_movelog.jsonl`). Re-run `kdb-fts intake` afterwards to sync
the ledger (deletions cascade to paragraphs/gate_verdicts).

Blacklist = the 15-entry unsubscribe list Joseph acted on after
calibration-p1, with publication-level coverage for The Bulwark (16
canonical aliases) and Savage Minds (2 aliases). Selection is by SQL
pattern on the canonical name; the matched set is printed for review
before anything moves (and with --dry-run nothing moves).

Usage: python scripts/fts_blacklist_cleanup.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

LEDGER = Path.home() / "Obsidian" / "KDB" / "fts" / "ledger.sqlite"
RAW = Path.home() / "Obsidian" / "KDB" / "raw" / "joseph-ft-public-gmail"
DEST_DIR = RAW / "_blacklist"

# (label, SQL WHERE fragment on canonical_name) — exact = equality, else LIKE
RULES = [
    ("Savage Minds (both aliases)", "au.canonical_name LIKE '%Savage Minds%'"),
    ("Robert Reich", "au.canonical_name = 'Robert Reich'"),
    ("Glenn Diesen", "au.canonical_name LIKE '%Diesen%'"),
    ("Substack platform mail", "au.canonical_name = 'Substack'"),
    ("The New Republic", "au.canonical_name = 'The New Republic'"),
    ("The Bulwark (all aliases)", "au.canonical_name LIKE '%Bulwark%'"),
    ("Democracy At Work", "au.canonical_name LIKE '%Democracy At Work%'"),
    ("Mearsheimer", "au.canonical_name LIKE '%Mearsheimer%'"),
    ("Chris Hedges", "au.canonical_name = 'The Chris Hedges Report'"),
    ("The Substack Post", "au.canonical_name = 'The Substack Post'"),
    ("Dugin", "au.canonical_name LIKE '%Dugin%'"),
    ("Dan Koe", "au.canonical_name = 'Dan Koe'"),
    ("Silver Bulletin", "au.canonical_name = 'Silver Bulletin'"),
    ("Perry Bacon", "au.canonical_name = 'Perry Bacon'"),
    ("Glenn Greenwald", "au.canonical_name = 'Glenn Greenwald'"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(LEDGER)
    where = " OR ".join(f"({w})" for _, w in RULES)
    rows = conn.execute(
        f"""SELECT a.article_id, a.path, au.canonical_name
            FROM articles a JOIN authors au ON au.author_id = a.author_id
            WHERE {where} ORDER BY au.canonical_name, a.path"""
    ).fetchall()

    by_author: dict[str, int] = {}
    for _, _, name in rows:
        by_author[name] = by_author.get(name, 0) + 1
    print(f"matched {len(rows)} articles across {len(by_author)} canonical authors:")
    for name, n in sorted(by_author.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>5}  {name}")

    missing = [p for _, p, _ in rows if not Path(p).is_file()]
    if missing:
        print(f"WARNING: {len(missing)} ledger paths missing on disk (first: {missing[0]})")

    if args.dry_run:
        print("DRY RUN — nothing moved")
        return 0

    DEST_DIR.mkdir(exist_ok=True)
    log = DEST_DIR / "_movelog.jsonl"
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    moved = 0
    with log.open("a", encoding="utf-8") as fh:
        for article_id, path, name in rows:
            src = Path(path)
            if not src.is_file():
                continue
            dest = DEST_DIR / src.name
            if dest.exists():  # name collision — keep both, suffix with id
                dest = DEST_DIR / f"{src.stem}--{article_id}{src.suffix}"
            src.rename(dest)
            fh.write(json.dumps({
                "file": src.name, "dest": dest.name, "author": name,
                "article_id": article_id, "run": "cleanup-1-blacklist",
                "ts": ts,
            }, sort_keys=True) + "\n")
            moved += 1
    print(f"moved {moved} files → {DEST_DIR} (movelog: {log})")
    print("next: add '_blacklist/' to the pipeline excludes, then re-run kdb-fts intake")
    return 0


if __name__ == "__main__":
    sys.exit(main())
