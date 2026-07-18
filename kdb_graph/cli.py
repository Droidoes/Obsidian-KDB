"""graphdb-kdb CLI dispatcher.

Subcommands added incrementally per the #63.x plan.
#63.1 — init
#63.3 — neighbors, incoming, path, stats, cypher
#63.4 — pagerank, communities, structural-holes, orphans, subgraph-by-source
#63.5 — verify
#63.6 — rebuild (with --backfill-baton one-shot migration)
#63.9 — snapshot
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from kdb_graph import default_graph_path
from kdb_graph.graphdb import GraphDB


def _resolve_graph_dir(args: argparse.Namespace) -> Path:
    return Path(args.graph_dir) if args.graph_dir else default_graph_path()


def _open_read_only(args: argparse.Namespace) -> GraphDB:
    """Open the graph read-only for pure-read subcommands.

    #112 discipline: a read command must never silently trigger a schema
    migration — on version mismatch it fails loud with an actionable error
    instead. Write commands (init, rebuild, cypher escape hatch) open writable.
    """
    return GraphDB(_resolve_graph_dir(args), read_only=True)


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
    with _open_read_only(args) as gdb:
        s = gdb.stats()
    if args.json:
        _print_json(s)
    else:
        for k, v in s.items():
            print(f"  {k:<10} {v}")
    return 0


def cmd_neighbors(args: argparse.Namespace) -> int:
    with _open_read_only(args) as gdb:
        entities = gdb.neighbors(args.slug, direction=args.direction, depth=args.depth)
    if args.json:
        _print_json([dataclasses.asdict(e) for e in entities])
    else:
        if not entities:
            print(f"(no neighbors of {args.slug!r} via direction={args.direction} depth={args.depth})")
        for e in entities:
            print(f"  {e.slug:<40} {e.page_type:<10} {e.title}")
    return 0


def cmd_incoming(args: argparse.Namespace) -> int:
    with _open_read_only(args) as gdb:
        entities = gdb.incoming_links(args.slug)
    if args.json:
        _print_json([dataclasses.asdict(e) for e in entities])
    else:
        if not entities:
            print(f"(no incoming links to {args.slug!r})")
        for e in entities:
            print(f"  {e.slug:<40} {e.page_type:<10} {e.title}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    with _open_read_only(args) as gdb:
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
    with _open_read_only(args) as gdb:
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
    with _open_read_only(args) as gdb:
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
    with _open_read_only(args) as gdb:
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
    with _open_read_only(args) as gdb:
        entities = gdb.orphan_entities()
    if args.json:
        _print_json([dataclasses.asdict(e) for e in entities])
        return 0
    if not entities:
        print("(no orphan-candidate entities)")
        return 0
    for e in entities:
        print(f"  {e.slug:<40} {e.page_type:<10} last_run_id={e.last_run_id}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """D50 Phase G: replay-to-temp structural equality verification.

    --vault-root (preferred): derives state_root and manifest path.
    --state-root (advanced override): explicit state_root.
    --source-state-only: skip full replay, just run cheap preflight.
    --canonicalization-only: skip full replay + manifest preflight, just
        run cheap live-graph C1–C4 invariant checks (#74.6).
    """
    from kdb_graph import verifier

    if args.source_state_only and args.canonicalization_only:
        print(
            "verify: --source-state-only and --canonicalization-only are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    graph_dir = _resolve_graph_dir(args)

    # --canonicalization-only doesn't need state_root (pure live-graph check).
    state_root: Path | None = None
    if not args.canonicalization_only:
        if args.state_root:
            state_root = Path(args.state_root)
        elif args.vault_root:
            state_root = Path(args.vault_root) / "KDB" / "state"
        else:
            print(
                "verify requires --vault-root <path> (or --state-root as advanced override).",
                file=sys.stderr,
            )
            return 2

        journals_dir = state_root / "runs"
        if not journals_dir.is_dir() and not args.source_state_only:
            print(f"runs directory not found: {journals_dir}", file=sys.stderr)
            return 2

    # Load manifest for source-state preflight (optional, irrelevant for
    # --canonicalization-only).
    manifest: dict | None = None
    if state_root is not None:
        manifest_path = state_root / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    with GraphDB(graph_dir, read_only=True) as gdb:
        if args.canonicalization_only:
            divs = verifier.verify_canonicalization_invariants(gdb.conn)
            result = verifier.VerifyResult(ok=not divs, divergences=divs, counts={
                "invariant_violation": len(divs),
            })
        elif args.source_state_only:
            if manifest is None:
                print(f"manifest not found for preflight: {manifest_path}", file=sys.stderr)
                return 2
            divs = verifier.verify_source_state(gdb.conn, manifest)
            m_keys = set((manifest.get("sources") or {}).keys())
            l_keys = set(verifier._graph_sources(gdb.conn).keys())
            result = verifier.VerifyResult(ok=not divs, divergences=divs, counts={
                "sources_checked": len(m_keys | l_keys),
            })
        else:
            result = verifier.verify(
                gdb.conn,
                journals_dir=journals_dir,
                manifest=manifest,
            )

    if args.json:
        _print_json({
            "ok": result.ok,
            "rebuild_failed": result.rebuild_failed,
            "rebuild_error": result.rebuild_error,
            "counts": result.counts,
            "divergences": [dataclasses.asdict(d) for d in result.divergences],
        })
        return 0 if result.ok else 1

    if result.rebuild_failed:
        print(f"REBUILD FAILED — cannot verify")
        print(f"  error: {result.rebuild_error}")
        for k, v in result.counts.items():
            print(f"  {k:<22} {v}")
        return 1

    if result.ok:
        print("ok — replay and live graph agree")
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
                f"  [{d.source}] [{d.kind}] {d.category}={d.key} field={d.field} "
                f"expected={d.expected_value!r} actual={d.actual_value!r}"
            )
        elif d.kind == "invariant_violation":
            print(
                f"  [{d.source}] [{d.field}] {d.category}={d.key} "
                f"expected={d.expected_value!r} actual={d.actual_value!r}"
            )
        else:
            print(f"  [{d.source}] [{d.kind}] {d.category}={d.key}")
    return 1


def cmd_subgraph_by_source(args: argparse.Namespace) -> int:
    with _open_read_only(args) as gdb:
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
        print(f"(source {args.source_id!r} not found or has no supported entities)")
        return 0
    print(f"nodes ({len(nodes)}):")
    for n in nodes:
        print(f"  {n.slug:<40} {n.page_type:<10} {n.title}")
    print(f"edges ({len(edges)}):")
    for ed in edges:
        print(f"  {ed['from']:<40} -> {ed['to']}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    """Drop all Kuzu tables and replay eligible runs in chronological order
    (D-S2 whole-DB rebuild; D-B1 adapter-driven).

    `--backfill-baton` one-shot migration: synthesize a RunDescriptor pointing
    at `state/{compile_result,last_scan}.json` baton files using
    `manifest.runs.last_successful_run_id` as the synthetic run_id. Idempotent:
    if a sidecar already exists at `state/runs/<run_id>/`, the backfill is
    silently skipped.
    """
    from kdb_graph.adapters.base import RunDescriptor
    from kdb_graph.adapters.obsidian_runs import ObsidianRunsAdapter
    from kdb_graph.rebuilder import rebuild

    graph_dir = _resolve_graph_dir(args)
    if not args.vault_root:
        print(
            "rebuild requires --vault-root <path>.",
            file=sys.stderr,
        )
        return 2
    state_root = Path(args.vault_root) / "KDB" / "state"
    journals_dir = state_root / "runs"
    if not journals_dir.is_dir():
        print(
            f"runs directory not found: {journals_dir}",
            file=sys.stderr,
        )
        return 2

    extra: list[RunDescriptor] = []
    if args.backfill_baton:
        baton_cr = state_root / "compile_result.json"
        baton_scan = state_root / "last_scan.json"
        manifest_path = state_root / "manifest.json"
        if not (baton_cr.is_file() and baton_scan.is_file() and manifest_path.is_file()):
            print(
                "--backfill-baton: missing baton/manifest files at "
                f"{state_root}; skipping baton step.",
                file=sys.stderr,
            )
        else:
            with manifest_path.open() as f:
                manifest = json.load(f)
            last_run_id = (manifest.get("runs") or {}).get("last_successful_run_id")
            if not last_run_id:
                print(
                    "--backfill-baton: manifest has no runs.last_successful_run_id; "
                    "skipping baton step.",
                    file=sys.stderr,
                )
            else:
                sidecar_dir = journals_dir / last_run_id
                if (sidecar_dir / "compile_result.json").is_file():
                    print(
                        f"--backfill-baton: sidecar already exists for {last_run_id}; "
                        "skipping (idempotent).",
                        file=sys.stderr,
                    )
                else:
                    extra.append(RunDescriptor(
                        run_id=last_run_id,
                        sort_key="0000-pre-63-backfill",  # sorts first chronologically
                        journal_path=None,
                        payload_paths=(baton_cr, baton_scan),
                    ))

    adapter = ObsidianRunsAdapter()
    result = rebuild(
        graph_dir=graph_dir,
        adapter=adapter,
        journals_dir=journals_dir,
        confirm=not args.yes,
        extra_descriptors=extra or None,
    )

    if args.json:
        _print_json({
            "ok": result.ok,
            "replayed": result.replayed,
            "skipped": result.skipped,
            "failed": result.failed,
            "outcomes": [dataclasses.asdict(o) for o in result.outcomes],
        })
        return 0 if result.ok else 1

    print(f"  replayed: {result.replayed}")
    print(f"  skipped:  {result.skipped}")
    print(f"  failed:   {result.failed}")
    if result.skipped or result.failed:
        for o in result.outcomes:
            if o.state == "skipped":
                print(f"    [skip] {o.run_id}  reason={o.skip_reason}")
            elif o.state == "failed":
                print(f"    [FAIL] {o.run_id}  {o.error}")
    return 0 if result.ok else 1


def cmd_snapshot(args: argparse.Namespace) -> int:
    """#63.9: export the graph to JSONL+manifest under
    `<vault_root>/KDB/state/graph-snapshots/<ts>/` (or `--out`).

    Belt-and-suspenders backup per D35. Primary recovery remains
    `graphdb-kdb rebuild`; this artifact is a diffable plain-text
    safety net for "journals AND Kuzu both lost" scenarios.
    """
    from kdb_graph.snapshot import (
        default_snapshot_dirname,
        snapshot,
        update_latest_pointer,
    )

    graph_dir = _resolve_graph_dir(args)
    if args.out:
        out_dir = Path(args.out).resolve()
        snapshots_root = out_dir.parent
        snapshot_dir_name = out_dir.name
    elif args.vault_root:
        snapshots_root = (
            Path(args.vault_root) / "KDB" / "state" / "graph-snapshots"
        )
        snapshot_dir_name = default_snapshot_dirname()
        out_dir = snapshots_root / snapshot_dir_name
    else:
        print(
            "snapshot requires --vault-root <path> or --out <dir>.",
            file=sys.stderr,
        )
        return 2

    try:
        result = snapshot(graph_dir, out_dir)
    except FileExistsError as exc:
        print(f"snapshot: {exc}", file=sys.stderr)
        return 1

    latest_path = update_latest_pointer(
        snapshots_root, snapshot_dir_name, result.schema_version
    )

    if args.json:
        _print_json({
            "out_dir": str(result.out_dir),
            "latest": str(latest_path),
            "emitted_at": result.emitted_at,
            "schema_version": result.schema_version,
            "counts": result.counts,
        })
    else:
        print(f"snapshot written: {result.out_dir}")
        print(f"  emitted_at: {result.emitted_at}")
        print(f"  schema_version: {result.schema_version}")
        print(f"  counts: entities={result.counts['entities']}  "
              f"sources={result.counts['sources']}  "
              f"links_to={result.counts['links_to']}  "
              f"supports={result.counts['supports']}  "
              f"domain={result.counts['domain']}  "
              f"belongs_to={result.counts['belongs_to']}  "
              f"claims={result.counts['claims']}  "
              f"evidences={result.counts['evidences']}  "
              f"about={result.counts['about']}  "
              f"supersedes={result.counts['supersedes']}  "
              f"contradicts={result.counts['contradicts']}  "
              f"qualifies={result.counts['qualifies']}")
        print(f"  latest pointer: {latest_path}")
    return 0


def cmd_domains(args: argparse.Namespace) -> int:
    """#76.4: list Domain nodes sorted by entity count (blueprint §6.6)."""
    with _open_read_only(args) as gdb:
        result = gdb.conn.execute(
            """
            MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain)
            RETURN d.name AS domain, count(e) AS entities, d.first_run_id AS first_run
            ORDER BY entities DESC
            """
        )
        rows = []
        while result.has_next():
            r = result.get_next()
            rows.append({"domain": r[0], "entities": int(r[1]), "first_run": r[2]})
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print("(no domain nodes)")
        return 0
    print(f"  {'domain':<30}  {'entities':>8}  first_run")
    for row in rows:
        print(f"  {row['domain']:<30}  {row['entities']:>8}  {row['first_run']}")
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
        help="Override Kuzu directory location (default: $KDB_GRAPH_PATH, else <vault>/KDB/graph from $OBSIDIAN_VAULT_PATH or ~/Obsidian).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create the Kuzu directory + schema (idempotent).")

    p_stats = sub.add_parser("stats", help="Print node/edge counts.")
    p_stats.add_argument("--json", action="store_true", help="JSON output.")

    p_n = sub.add_parser("neighbors", help="BFS expansion from an entity slug.")
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

    p_path = sub.add_parser("path", help="Shortest directed path between two entities.")
    p_path.add_argument("from_slug", metavar="FROM_SLUG")
    p_path.add_argument("to_slug", metavar="TO_SLUG")
    p_path.add_argument("--max-hops", type=int, default=10, help="Max search depth (default 10).")
    p_path.add_argument("--json", action="store_true", help="JSON output.")

    p_c = sub.add_parser("cypher", help="Run ad-hoc Cypher (escape hatch).")
    p_c.add_argument("query")
    p_c.add_argument("--params", default=None, help="JSON dict of query parameters.")
    p_c.add_argument("--json", action="store_true", help="JSON output.")

    p_pr = sub.add_parser("pagerank", help="PageRank-ranked entities (NetworkX-backed).")
    p_pr.add_argument("--top", type=int, default=None, help="Truncate to top-N (default: all).")
    p_pr.add_argument("--json", action="store_true", help="JSON output.")

    p_com = sub.add_parser("communities", help="Louvain community assignments.")
    p_com.add_argument("--json", action="store_true", help="JSON output.")

    p_sh = sub.add_parser(
        "structural-holes",
        help="Inter-community bridge counts (sparsest first).",
    )
    p_sh.add_argument("--json", action="store_true", help="JSON output.")

    p_o = sub.add_parser("orphans", help="List orphan-candidate entities.")
    p_o.add_argument("--json", action="store_true", help="JSON output.")

    p_sg = sub.add_parser(
        "subgraph-by-source",
        help="Export a source's induced (nodes, edges) subgraph.",
    )
    p_sg.add_argument("source_id", metavar="SOURCE_ID")
    p_sg.add_argument("--json", action="store_true", help="JSON output.")

    p_v = sub.add_parser(
        "verify",
        help="Replay-to-temp structural equality verification (D50). "
             "Exit 0 = replay matches live; 1 = divergence or rebuild failure.",
    )
    p_v.add_argument(
        "--vault-root", default=None,
        help="Vault root (state at <root>/KDB/state/). Preferred.",
    )
    p_v.add_argument(
        "--state-root", default=None,
        help="Explicit state root (advanced override; skips vault-root derivation).",
    )
    p_v.add_argument(
        "--source-state-only", action="store_true",
        help="Skip full replay — only run cheap manifest-vs-graph source preflight.",
    )
    p_v.add_argument(
        "--canonicalization-only", action="store_true",
        help="Skip full replay — only run cheap canonicalization invariant "
             "checks (#74.6 C1–C4) on the live graph.",
    )
    p_v.add_argument("--json", action="store_true", help="JSON output.")

    p_rb = sub.add_parser(
        "rebuild",
        help="Drop all Kuzu tables and replay eligible runs from state/runs/ "
             "(D-S2 whole-DB rebuild). Use --backfill-baton on first run to "
             "import the pre-#63 baton.",
    )
    p_rb.add_argument(
        "--vault-root", required=True,
        help="Vault root (runs read from <root>/KDB/state/runs/).",
    )
    p_rb.add_argument(
        "--producer", default="obsidian", choices=("obsidian",),
        help="Adapter to use (only 'obsidian' shipped for v1; D-S2 + D-B1).",
    )
    p_rb.add_argument(
        "--backfill-baton", action="store_true",
        help="One-shot migration: replay state/{compile_result,last_scan}.json "
             "baton as the latest pre-#63 run. Idempotent — skipped if the "
             "corresponding sidecar already exists.",
    )
    p_rb.add_argument(
        "--yes", action="store_true",
        help="Skip the interactive whole-DB-drop warning.",
    )
    p_rb.add_argument("--json", action="store_true", help="JSON output.")

    p_dom = sub.add_parser(
        "domains",
        help="#76.4: list Domain nodes sorted by entity count.",
    )
    p_dom.add_argument("--json", action="store_true", help="JSON output.")

    p_snap = sub.add_parser(
        "snapshot",
        help="#63.9: export graph state to JSONL+manifest under "
             "<vault_root>/KDB/state/graph-snapshots/<ts>/ (or --out). "
             "Belt-and-suspenders backup per D35 — diffable, OneDrive-safe.",
    )
    p_snap.add_argument(
        "--vault-root", default=None,
        help="Vault root (snapshot lands under <root>/KDB/state/graph-snapshots/<ts>/).",
    )
    p_snap.add_argument(
        "--out", default=None,
        help="Explicit snapshot directory (overrides --vault-root).",
    )
    p_snap.add_argument("--json", action="store_true", help="JSON output.")

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
    "rebuild": cmd_rebuild,
    "domains": cmd_domains,
    "snapshot": cmd_snapshot,
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
