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
                     "signal": v["signal"], "body": body,
                     "exploration": bool(v["exploration"])})
    sample = _stratified_sample(rows, min(n, len(rows)))
    items = [{**r, "position": i, "exploration": r["exploration"]}
             for i, r in enumerate(sample)]
    atomic_write_json(path, {
        "batch_id": batch_id, "kind": kind,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ranker_version": None,
        "items": items,
    })
    return path


# --- server half (Task 7): stdlib http.server + one static page (D22) ------

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kdb_fts import feedback

_PAGE_PATH = Path(__file__).parent / "assets" / "review.html"

# Article-label buckets — same semantics as calibrate._BUCKET_ACTIONS:
# latest event per target_id wins (file order = ts order).
_BUCKET_ACTIONS = frozenset({"strong", "interesting", "weak", "noise"})


def make_server(root: Path, batch_id: str,
                port: int = 0) -> ThreadingHTTPServer:
    """Build (not start) the review server for one frozen batch."""
    root = Path(root)
    batch_path = root / "review" / f"{batch_id}.json"
    frozen_text = batch_path.read_text(encoding="utf-8")  # missing → FileNotFoundError, good
    frozen = json.loads(frozen_text)
    by_id = {item["article_id"]: item for item in frozen["items"]}
    page_bytes = _PAGE_PATH.read_bytes()
    batch_bytes = frozen_text.encode("utf-8")
    lock = threading.Lock()  # serializes event appends across handler threads

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/review.html"):
                self._send(200, page_bytes, "text/html; charset=utf-8")
            elif self.path == "/batch":
                self._send(200, batch_bytes, "application/json")
            elif self.path == "/labels":
                # fresh read per request — labels persist across reloads/restarts
                latest: dict[str, str] = {}
                for e in feedback.load_events(root, batch_id=batch_id):
                    if (e["target_type"] == "article"
                            and e["action"] in _BUCKET_ACTIONS):
                        latest[e["target_id"]] = e["action"]
                body = json.dumps(latest, sort_keys=True).encode("utf-8")
                self._send(200, body, "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/event":
                self._send(404, b"not found", "text/plain")
                return
            try:
                length = int(self.headers["Content-Length"])
                if length < 0:
                    raise ValueError(f"negative Content-Length {length}")
                data = json.loads(self.rfile.read(length))
                item = by_id[data["article_id"]]  # KeyError → 400 below
                action = data["action"]
                reason = data.get("reason_text") or None
                if action not in feedback.ACTIONS:
                    raise ValueError(f"bad action {action!r}")
            except (KeyError, ValueError, json.JSONDecodeError, TypeError):
                self._send(400, b"bad event", "text/plain")
                return
            with lock:
                feedback.append_event(
                    root, action=action, target_type="article",
                    target_id=item["article_id"], reason_text=reason,
                    ranker_version=frozen.get("ranker_version"),
                    score_shown=item.get("signal"),
                    position_shown=item["position"],
                    batch_id=batch_id, exploration=bool(item.get("exploration", False)))
            self._send(200, b'{"ok": true}', "application/json")

        def log_message(self, *args) -> None:  # quiet
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(root: Path, batch_id: str) -> None:
    """Start the app for a frozen batch until Ctrl-C."""
    server = make_server(root, batch_id)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"review batch {batch_id!r} at {url}  (Ctrl-C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
