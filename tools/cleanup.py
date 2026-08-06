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

Historical `event_type='cleanup'` journals remain replayable through
`kdb_graph.intake.apply_cleanup` (the legacy `reap_orphans` /
`build_cleanup_artifacts` helpers and the fired one-shot backfill script were
deleted in #133).
"""
from __future__ import annotations

import argparse
import sys


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
