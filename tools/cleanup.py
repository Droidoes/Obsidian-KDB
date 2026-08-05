#!/usr/bin/env python3
"""kdb-clean — KDB maintenance CLI (retired in #130).

`kdb-clean orphans` was the review-gated archive-and-remove pass for
orphan_candidate pages. #130 replaced that lifecycle:

  * pages the model drops (SUPPORTS-loss) are marked `deprecated` in place —
    graph node AND file frontmatter flipped at finalize, never reaped, never
    archived, revivable on re-emit;
  * pages of a deleted source are ERASED at reconcile time (node DETACH
    DELETEd + file unlinked — no archive).

There is nothing left for this command to reap; it now prints a retirement
notice and exits 0.

Kept for legacy tooling (do not delete):
  * reap_orphans(manifest)  — pure slug-safe retraction math over legacy
                              manifest.pages/orphans; used by
                              scripts/backfill_cleanup_journal.py and
                              replay-era tests.
  * build_cleanup_artifacts — builds historical (journal, retraction) pairs;
                              imported by scripts/backfill_cleanup_journal.py.
                              Historical event_type='cleanup' journals remain
                              replayable through kdb_graph.intake.apply_cleanup.
"""
from __future__ import annotations

import argparse
import sys


def reap_orphans(manifest: dict) -> dict:
    """Mutate manifest in place: drop every orphan_candidate page from pages{}
    and orphans{}. Returns a report dict. LEGACY (pre-#130): the
    orphan_candidate status no longer exists in the live system; this remains
    for historical-journal tooling only.

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


def build_cleanup_artifacts(
    report: dict,
    run_id: str,
    started_at: str,
    finished_at: str,
) -> tuple[dict, dict]:
    """Build the (journal, retraction) pair for a cleanup run (#68). LEGACY
    (pre-#130): new cleanup journals are no longer written — this remains for
    the historical backfill tooling only.

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
    """`kdb-clean orphans` — RETIRED (#130). Prints the notice, exits 0.

    orphan_candidate no longer exists: model-dropped pages are marked
    `deprecated` in place (graph + frontmatter, never reaped), and source
    deletion erases pages at reconcile time (no archive).
    """
    print(
        "kdb-clean orphans is RETIRED (#130 — deprecated page lifecycle).\n"
        "  The orphan_candidate status no longer exists:\n"
        "    - model-dropped pages are marked 'deprecated' in place\n"
        "      (graph + frontmatter at finalize; revivable on re-emit);\n"
        "    - pages of a deleted source are erased at reconcile time\n"
        "      (node + file, no archive).\n"
        "  Nothing to reap."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-clean",
        description="KDB maintenance CLI (orphans mode retired in #130).",
    )
    sub = p.add_subparsers(dest="mode", required=True, metavar="<mode>")

    orphans = sub.add_parser(
        "orphans",
        help="RETIRED (#130) — prints a retirement notice, exits 0",
        description="Retired in #130: orphan_candidate no longer exists. "
                    "Model-dropped pages are deprecated in place; source "
                    "deletion erases at reconcile time. Nothing to reap.",
    )
    orphans.add_argument("--vault-root", required=True,
                         help="(ignored — retired command)")
    orphans.add_argument("--apply", action="store_true",
                         help="(ignored — retired command)")
    orphans.set_defaults(func=_cmd_orphans)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
