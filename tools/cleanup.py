#!/usr/bin/env python3
"""kdb-clean — KDB maintenance CLI for review-gated cleanup of derived state.

`kdb-compile` derives the current wiki from raw sources. `kdb-clean` retires
state that derivation leaves behind. Same system, different risk class:
cleanup is destructive (archive-then-remove), so it lives in its own command
with its own review gate rather than as a `kdb-compile` flag.

Modes (`kdb-clean <mode>`):
    orphans   archive orphan_candidate pages and drop them from the manifest

Every mode is `--dry-run` by DEFAULT — it previews and writes nothing. Pass
`--apply` to commit.

GraphDB is REQUIRED (D50 Phase E): orphan enumeration reads from GraphDB —
the ontology authority. If the graph DB is missing or corrupt, `kdb-clean
orphans` cannot run (even in dry-run mode).

Cleanup journaling (Task #68): `orphans --apply` writes a replayable `cleanup`
run journal + `retraction.json` sidecar into `state/runs/` and live-syncs the
retraction into the graph through the Obsidian adapter. `graphdb-kdb rebuild`
replays the cleanup event chronologically, so the reaped pages stay retracted
instead of being re-introduced.

--- orphans mode ---------------------------------------------------------------
A full canonical recompile (all sources, one model) defines the manifest truth:
every page the run does not emit is left `orphan_candidate` by Task #64
supersession. `orphans` mode clears that residue so the live KB contains
exactly what the canonical run produced.

For each `orphan_candidate` page it:
  1. archives the .md file -> KDB/state/orphan-archive/<run-id>/<page_id>
     (in-vault, so the archive rides OneDrive version history — the vault is
     not under git, so a delete would be unrecoverable; archival preserves the
     content for optional manual re-authoring)
  2. removes the entry from manifest.pages AND manifest.orphans
     (manifest tombstones are source-scoped, not page-scoped — full removal is
     the only page-retirement mechanism; the orphans{} key must always exist in
     pages{}, so both go together)
  3. reports any *active* page whose outgoing_links still reference a reaped
     slug — a dead link to fix, surfaced before it bites. `orphans` mode only
     reports dead links; it never rewrites active pages (that would be a
     separate, also dry-run-first, cleanup mode).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import kuzu

from common import atomic_io
from common.paths import slug_to_relpath
from kdb_graph import default_graph_path
from kdb_graph.queries import orphan_entities, outgoing_links


def reap_orphans(manifest: dict) -> dict:
    """Mutate manifest in place: drop every orphan_candidate page from pages{}
    and orphans{}. Returns a report dict.

    report = {
      "reaped":          [{"page_id", "slug", "page_type"}, ...],  # sorted by page_id
      "dead_links":      [{"from_page", "to_slug"}, ...],          # active -> reaped
      "retracted_slugs": [slug, ...],  # reaped slugs no surviving page provides
    }
    """
    pages = manifest.get("pages", {})
    orphans = manifest.get("orphans", {})

    reaped = [
        {"page_id": pid, "slug": p.get("slug"), "page_type": p.get("page_type")}
        for pid, p in pages.items()
        if p.get("status") == "orphan_candidate"
    ]
    reaped_ids = {r["page_id"] for r in reaped}
    reaped_slugs = {r["slug"] for r in reaped if r["slug"]}
    # A slug survives the reap if any non-reaped page still carries it — the
    # same slug can exist under two page_types (an active article + an orphaned
    # concept), in which case a link to it still resolves.
    surviving_slugs = {
        p.get("slug") for pid, p in pages.items() if pid not in reaped_ids
    }

    # dead-link scan: an ACTIVE page (i.e. not itself reaped) linking to a slug
    # this reap removes and that no surviving page provides. Links between two
    # orphans are not dead links — both go.
    dead_links = [
        {"from_page": pid, "to_slug": link}
        for pid, p in pages.items()
        if pid not in reaped_ids
        for link in (p.get("outgoing_links") or [])
        if link in reaped_slugs and link not in surviving_slugs
    ]

    # retracted_slugs: reaped slugs that NO surviving page provides — the
    # slug-safe deletion key set for the graph (a slug still carried by a
    # surviving active page must not be retracted). #68.
    retracted_slugs = sorted(reaped_slugs - surviving_slugs)

    for pid in reaped_ids:
        pages.pop(pid, None)
        orphans.pop(pid, None)

    return {
        "reaped": sorted(reaped, key=lambda r: r["page_id"]),
        "dead_links": sorted(dead_links, key=lambda d: (d["from_page"], d["to_slug"])),
        "retracted_slugs": retracted_slugs,
    }


# ---- GraphDB-backed orphan enumeration (D50 Phase E) ----

def reap_orphans_from_graph(conn: kuzu.Connection) -> dict:
    """Identify orphan_candidate entities from GraphDB. Pure read — no mutations.

    Returns same report shape as reap_orphans(manifest):
        reaped:          [{page_id, slug, page_type}, ...]
        dead_links:      [{from_slug, to_slug}, ...]
        retracted_slugs: [slug, ...]
    """
    orphans = orphan_entities(conn)
    reaped = [
        {
            "page_id": slug_to_relpath(e.slug, e.page_type),
            "slug": e.slug,
            "page_type": e.page_type,
        }
        for e in orphans
    ]
    reaped_slugs = {r["slug"] for r in reaped}

    # A slug survives if any non-orphan entity still carries it.
    surviving_slugs: set[str] = set()
    r = conn.execute(
        "MATCH (e:Entity) WHERE e.status <> 'orphan_candidate' RETURN e.slug"
    )
    while r.has_next():
        surviving_slugs.add(r.get_next()[0])

    retracted_slugs = sorted(reaped_slugs - surviving_slugs)

    # Dead-link detection: active entities with LINKS_TO edges pointing at
    # reaped slugs that no surviving entity provides.
    dead_links: list[dict] = []
    truly_dead_slugs = reaped_slugs - surviving_slugs
    if truly_dead_slugs:
        for slug in sorted(surviving_slugs):
            targets = outgoing_links(conn, slug)
            for t in targets:
                if t.slug in truly_dead_slugs:
                    dead_links.append({"from_slug": slug, "to_slug": t.slug})

    return {
        "reaped": sorted(reaped, key=lambda r: r["page_id"]),
        "dead_links": sorted(dead_links, key=lambda d: (d["from_slug"], d["to_slug"])),
        "retracted_slugs": retracted_slugs,
    }



def build_cleanup_artifacts(
    report: dict,
    run_id: str,
    started_at: str,
    finished_at: str,
) -> tuple[dict, dict]:
    """Build the (journal, retraction) pair for a cleanup run (#68).

    journal     -> state/runs/<run_id>.json    (audit record; replay eligibility)
    retraction  -> state/runs/<run_id>/retraction.json  (the replay payload)

    `report` is a `reap_orphans()` return dict. Pure — also used by the
    one-shot backfill (scripts/backfill_cleanup_journal.py).
    """
    retraction = {
        "event_type": "cleanup",
        "run_id": run_id,
        "reaped": report["reaped"],
        "retracted_slugs": report["retracted_slugs"],
        "dead_links": report["dead_links"],
    }
    journal = {
        "schema_version": "2.1",
        "event_type": "cleanup",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "success": True,
        "dry_run": False,
        "summary": {
            "reaped_count": len(report["reaped"]),
            "retracted_slug_count": len(report["retracted_slugs"]),
            "dead_link_count": len(report["dead_links"]),
        },
        "artifacts": {"retraction_path": f"state/runs/{run_id}/retraction.json"},
    }
    return journal, retraction


def _cmd_orphans(args: argparse.Namespace) -> int:
    """`kdb-clean orphans` — archive + de-list orphan_candidate pages.

    D50 Phase F: manifest no longer stores pages/orphans — cleanup only
    archives files, writes a retraction journal, and live-syncs the graph.
    GraphDB is REQUIRED — if the graph is inaccessible, this command cannot run.
    """
    vault_root = Path(args.vault_root).resolve()
    state_root = vault_root / "KDB" / "state"

    # GraphDB is the authority for orphan candidates.
    from kdb_graph.graphdb import GraphDB
    graph_path = default_graph_path()
    try:
        gdb = GraphDB(graph_path)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR  cannot open GraphDB at {graph_path}: {exc}")
        return 1

    with gdb:
        report = reap_orphans_from_graph(gdb.conn)

    for r in report["reaped"]:
        print(f"reap    {r['page_id']}  ({r['page_type']})")
    for d in report["dead_links"]:
        print(f"WARN    dead link — {d['from_slug']} -> {d['to_slug']} (reaped)")
    print(f"\nsummary: {len(report['reaped'])} page(s) to reap, "
          f"{len(report['dead_links'])} dead link(s)")

    if not args.apply:
        print("\nDRY RUN — no files moved. "
              "Re-run with --apply to commit.")
        return 0

    if not report["reaped"]:
        print("\nnothing to reap — already clean.")
        return 0

    # Capture the clock ONCE (aware) so run_id and started_at can never disagree.
    now_dt = datetime.now().astimezone()
    run_id = f"clean-orphans-{now_dt.strftime('%Y-%m-%dT%H-%M-%S')}"
    started_at = now_dt.isoformat(timespec="seconds")
    runs_root = state_root / "runs"
    archive_root = state_root / "orphan-archive" / run_id

    # Write order: archive -> retraction sidecar -> journal -> live-sync.

    # 1. archive the .md files
    for r in report["reaped"]:
        src = vault_root / r["page_id"]
        dst = archive_root / r["page_id"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.move(str(src), str(dst))
        else:
            print(f"note    {r['page_id']} — file already absent, archive-only reap")

    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    journal, retraction = build_cleanup_artifacts(
        report, run_id, started_at, finished_at)

    # 2. retraction sidecar — inert until the journal references it
    sidecar_dir = runs_root / run_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    atomic_io.atomic_write_json(sidecar_dir / "retraction.json", retraction,
                                sort_keys=True)

    # 3. atomic journal write — commits replay state
    atomic_io.atomic_write_json(runs_root / f"{run_id}.json", journal,
                                sort_keys=True)

    print(f"\nAPPLIED — {len(report['reaped'])} page(s) archived to {archive_root}")
    print(f"          cleanup journal at {runs_root / (run_id + '.json')}")

    # 6. live-sync the retraction into the graph (best-effort).
    try:
        from kdb_graph.adapters.obsidian_runs import ObsidianRunsAdapter
        sync = ObsidianRunsAdapter().sync_cleanup_run(retraction, run_id)
        print(f"          graph live-sync: {sync.entities_deleted} "
              f"entity(ies) retracted")
    except Exception as exc:  # noqa: BLE001 — best-effort, never fails the reap
        print(f"WARN    graph live-sync failed ({type(exc).__name__}: {exc}); "
              f"run `graphdb-kdb rebuild` to reconverge.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-clean",
        description="KDB maintenance — review-gated cleanup of derived state "
                    "(dry-run default).",
    )
    sub = p.add_subparsers(dest="mode", required=True, metavar="<mode>")

    orphans = sub.add_parser(
        "orphans",
        help="archive orphan_candidate pages and drop them from the manifest",
        description="Archive every orphan_candidate page and remove it from "
                    "manifest.pages/orphans. Reports active dead links; does "
                    "not rewrite active pages and does not resync GraphDB-KDB "
                    "(known replay gap — Task #68).",
    )
    orphans.add_argument("--vault-root", required=True,
                         help="Absolute path to the Obsidian vault root")
    orphans.add_argument("--apply", action="store_true",
                         help="Archive files and mutate state/manifest.json "
                              "(default is dry-run)")
    orphans.set_defaults(func=_cmd_orphans)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
