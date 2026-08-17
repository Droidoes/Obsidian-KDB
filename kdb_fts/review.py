"""review — batch freezer + local labeling web app (D22, §7.5).

Freezer (this file, top): pick a deterministic stratified sample of gated
articles and freeze it to review/<batch_id>.json — the frozen payload IS
the D13 exposure record (positions/scores shown are stamped from it
server-side on every event). A frozen batch is never overwritten.

Server (Task 7, bottom): stdlib http.server serving one static page;
POST /event writes back through feedback.py and nothing else.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from common.atomic_io import atomic_write_json

from kdb_fts import ledger

_KINDS = frozenset({"calibration"})  # v0: calibration only; queue kinds land
                                     # with the ranker (Phase 3+)
_MIN_PER_STRATUM = 2


def _stratified_sample(rows: list[dict], n: int) -> list[dict]:
    """Proportional-by-topic allocation (min _MIN_PER_STRATUM where stock
    allows), even-spacing within each topic ordered by
    (author, published_date, article_id). Deterministic."""
    by_topic: dict[str, list[dict]] = {}
    for r in rows:
        by_topic.setdefault(r["topic"], []).append(r)
    for group in by_topic.values():
        group.sort(key=lambda r: (r["author"] or "", r["published_date"] or "",
                                  r["article_id"]))
    total = len(rows)
    picked: list[dict] = []
    for topic in sorted(by_topic):
        group = by_topic[topic]
        k = round(n * len(group) / total) if total else 0
        k = min(len(group), max(_MIN_PER_STRATUM, k) if len(group) >= _MIN_PER_STRATUM else len(group))
        step = len(group) / k
        picked.extend(group[int(i * step)] for i in range(k))
    # trim or backfill to n deterministically
    if len(picked) > n:
        picked = sorted(picked, key=lambda r: r["article_id"])[:n]
    elif len(picked) < n:
        have = {r["article_id"] for r in picked}
        rest = sorted((r for r in rows if r["article_id"] not in have),
                      key=lambda r: r["article_id"])
        picked.extend(rest[: n - len(picked)])
    return picked[:n]


def freeze_batch(conn: sqlite3.Connection, root: Path, *, batch_id: str,
                 kind: str = "calibration", n: int = 150) -> Path:
    """Freeze a review batch to review/<batch_id>.json. Refuses overwrite."""
    if kind not in _KINDS:
        raise ValueError(f"kind {kind!r} not served by review v0 (have: {sorted(_KINDS)})")
    path = Path(root) / "review" / f"{batch_id}.json"
    if path.exists():
        raise FileExistsError(f"batch already frozen (immutable, D13): {path}")
    verdicts = {v["article_id"]: v for v in ledger.latest_verdicts(conn)}
    rows = []
    for a in conn.execute(
            """SELECT a.article_id, a.title,
                      COALESCE(au.canonical_name, a.raw_author),
                      a.published_date
               FROM articles a LEFT JOIN authors au ON au.author_id = a.author_id
               ORDER BY a.article_id"""):
        v = verdicts.get(a[0])
        if v is None:
            continue  # ungated articles are not calibration stock
        body = conn.execute(
            "SELECT GROUP_CONCAT(body, char(10)||char(10)) FROM paragraphs "
            "WHERE article_id = ?", (a[0],)).fetchone()[0] or ""
        rows.append({"article_id": a[0], "title": a[1], "author": a[2],
                     "published_date": a[3], "topic": v["topic"],
                     "signal": v["signal"], "body": body})
    sample = _stratified_sample(rows, min(n, len(rows)))
    items = [{**r, "position": i, "exploration": False}
             for i, r in enumerate(sample)]
    atomic_write_json(path, {
        "batch_id": batch_id, "kind": kind,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ranker_version": None,
        "items": items,
    })
    return path
