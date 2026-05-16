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

GraphDB-KDB caveat (Task #68): `orphans --apply` cleans manifest.json but does
NOT resync the graph. `graphdb-kdb rebuild` replays compile-history journals
that still contain the reaped pages, so it re-introduces them as orphan
entities rather than converging — the cleanup is not yet replayable. The
planned fix is a replayable cleanup/retraction event; until then the graph
stays queryable and `graphdb-kdb orphans` lists the residual entities.

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
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from kdb_compiler import atomic_io
from kdb_compiler.manifest_update import assert_manifest_invariants


def reap_orphans(manifest: dict) -> dict:
    """Mutate manifest in place: drop every orphan_candidate page from pages{}
    and orphans{}. Returns a report dict.

    report = {
      "reaped":     [{"page_id", "slug", "page_type"}, ...],  # sorted by page_id
      "dead_links": [{"from_page", "to_slug"}, ...],          # active -> reaped
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

    for pid in reaped_ids:
        pages.pop(pid, None)
        orphans.pop(pid, None)

    return {
        "reaped": sorted(reaped, key=lambda r: r["page_id"]),
        "dead_links": sorted(dead_links, key=lambda d: (d["from_page"], d["to_slug"])),
    }


def _cmd_orphans(args: argparse.Namespace) -> int:
    """`kdb-clean orphans` — archive + de-list orphan_candidate pages."""
    vault_root = Path(args.vault_root).resolve()
    state_root = vault_root / "KDB" / "state"
    manifest_path = state_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR  cannot read manifest {manifest_path}: {exc}")
        return 1

    report = reap_orphans(manifest)

    for r in report["reaped"]:
        print(f"reap    {r['page_id']}  ({r['page_type']})")
    for d in report["dead_links"]:
        print(f"WARN    dead link — {d['from_page']} -> {d['to_slug']} (reaped)")
    print(f"\nsummary: {len(report['reaped'])} page(s) to reap, "
          f"{len(report['dead_links'])} dead link(s)")

    if not args.apply:
        print("\nDRY RUN — no files moved, manifest untouched. "
              "Re-run with --apply to commit.")
        return 0

    if not report["reaped"]:
        print("\nnothing to reap — manifest already clean.")
        return 0

    run_id = f"clean-orphans-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    archive_root = state_root / "orphan-archive" / run_id
    for r in report["reaped"]:
        src = vault_root / r["page_id"]
        dst = archive_root / r["page_id"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.move(str(src), str(dst))
        else:
            print(f"note    {r['page_id']} — file already absent, manifest-only reap")

    assert_manifest_invariants(manifest)
    atomic_io.atomic_write_json(manifest_path, manifest, sort_keys=True)
    audit_path = state_root / f"kdb-clean-orphans-audit-{run_id}.json"
    atomic_io.atomic_write_json(audit_path, {"run_id": run_id, **report},
                                sort_keys=True)
    print(f"\nAPPLIED — {len(report['reaped'])} page(s) archived to {archive_root}")
    print(f"          manifest updated; audit at {audit_path}")
    print("\nNOTE: the manifest is clean, but GraphDB-KDB does NOT auto-resync.")
    print("      `graphdb-kdb rebuild` replays compile-history journals that")
    print("      still contain the reaped pages — it re-introduces them as")
    print("      orphan entities rather than converging. Known gap, tracked by")
    print("      Task #68. The graph stays queryable; `graphdb-kdb orphans`")
    print("      lists the residual entities.")
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
