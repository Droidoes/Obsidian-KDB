"""kdb-fts — CLI for the parallel extraction/ranking system (#145).

Phase 0 surface: intake / search / status (no LLM). Later phases add
gate/extract/rank/review to this same argparse tree (blueprint §8).
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from kdb_fts import author_map, calibrate, feedback, gate, intake, ledger, review, state


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
    rows = conn.execute(
        """SELECT model, prompt_version, COUNT(*), SUM(input_tokens), SUM(output_tokens)
           FROM gate_verdicts GROUP BY 1, 2 ORDER BY 1"""
    ).fetchall()
    if rows:
        from common.model_pool import UnknownModelError, resolve_models_json
        print("gate verdicts:")
        total_cost = 0.0
        for model, pv, n, tin, tout in rows:
            try:
                spec = resolve_models_json(model)
            except UnknownModelError:
                print(f"  {model} {pv}: {n} verdicts, {tin or 0}+{tout or 0} tok, "
                      f"cost=n/a (model not in active pool)")
                continue
            cost = spec.price_in / 1e6 * (tin or 0) + spec.price_out / 1e6 * (tout or 0)
            total_cost += cost
            print(f"  {model} {pv}: {n} verdicts, {tin or 0}+{tout or 0} tok, ${cost:.4f}")
        print(f"  cost to date: ${total_cost:.4f}")
        for topic, n in conn.execute(
            "SELECT topic, COUNT(*) FROM gate_verdicts GROUP BY 1 ORDER BY 2 DESC"
        ):
            print(f"  topic {topic}: {n}")
    return 0


def _cmd_gate(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    run_id = datetime.now().astimezone().isoformat(timespec="seconds")
    stats = gate.run_gate(
        conn, state_root=root, run_id=run_id, model_id=args.model,
        max_n=args.max, dry_run=args.dry_run, call_fn=gate.call_model,
    )
    tag = "DRY-RUN " if args.dry_run else ""
    print(f"{tag}gated={stats['gated']} failed={stats['failed']} skipped={stats['skipped']}")
    print(f"topics: {stats['by_topic']}")
    print(f"exploration_marked={stats['exploration_marked']}")
    print(f"tokens in={stats['input_tokens']} out={stats['output_tokens']} "
          f"cost=${stats['cost_usd']:.4f}")
    return 0


def _cmd_feedback(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    ledger.connect(root)  # guarantees feedback/ exists
    event = feedback.append_event(
        root, action=args.action, target_type=args.target_type,
        target_id=args.target_id, reason_text=args.reason,
        reason_tags=args.tags.split(",") if args.tags else None,
    )
    print(f"event appended: {event['action']} {event['target_type']}:{event['target_id']} @ {event['ts']}")
    return 0


def _cmd_review(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    batch_path = root / "review" / f"{args.batch}.json"
    if not batch_path.exists():
        review.freeze_batch(conn, root, batch_id=args.batch, kind=args.kind, n=args.n)
        print(f"froze batch {args.batch} ({args.kind}, n={args.n})")
    conn.close()
    review.serve(root, args.batch)
    return 0


def _cmd_calibration(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    rep = calibrate.report(conn, root, args.batch)
    print(f"batch {rep['batch_id']}: {rep['labeled']} articles labeled")
    c = rep["confusion"]
    print(f"confusion (gate-relevant = investment ∪ finance-econ ∪ signal≥"
          f"{calibrate.SIGNAL_ACCEPT_THRESHOLD}): "
          f"tp={c['tp']} fp={c['fp']} fn={c['fn']} tn={c['tn']}")
    parts = []
    if rep["precision"] is not None:
        parts.append(f"precision={rep['precision']:.3f}")
    if rep["recall"] is not None:
        parts.append(f"recall={rep['recall']:.3f}")
    if rep["f1"] is not None:
        parts.append(f"f1={rep['f1']:.3f}")
    if parts:
        print(" ".join(parts))
    print("by topic (Joseph-positive / negative):")
    for topic, b in sorted(rep["by_topic"].items()):
        print(f"  {topic}: {b['pos']}/{b['neg']}")
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

    p = sub.add_parser("gate", help="one LLM verdict per ok article (§7.2); resumable")
    p.add_argument("--max", type=int, default=None, dest="max")
    p.add_argument("--model", default="deepseek-v4-flash")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_gate)

    p = sub.add_parser("feedback", help="append one immutable event (scripting path)")
    p.add_argument("target_type", choices=sorted(feedback.TARGET_TYPES))
    p.add_argument("target_id")
    p.add_argument("action", choices=sorted(feedback.ACTIONS))
    p.add_argument("--reason", default=None)
    p.add_argument("--tags", default=None, help="comma-separated")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_feedback)

    p = sub.add_parser("review", help="freeze a batch (if new) and serve the labeling app (D22)")
    p.add_argument("--batch", default="calibration-p1")
    p.add_argument("--kind", default="calibration",
                   choices=["calibration"])
    p.add_argument("--n", type=int, default=150)
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_review)

    p = sub.add_parser("calibration", help="gate precision/recall vs labels for a batch")
    p.add_argument("--batch", default="calibration-p1")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_calibration)

    args = parser.parse_args(argv)
    return args.fn(args)
