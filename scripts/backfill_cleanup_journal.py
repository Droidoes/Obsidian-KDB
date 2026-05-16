#!/usr/bin/env python3
"""One-shot #68 backfill — synthesize a cleanup journal for a pre-#68 reap.

`kdb-clean orphans --apply` runs before Task #68 wrote no cleanup journal, only
a standalone audit file (`state/kdb-clean-orphans-audit-<run-id>.json`). Without
a journal, `graphdb-kdb rebuild` re-introduces the reaped pages. This script
reads that audit file, computes `retracted_slugs` against the CURRENT manifest,
and writes the journal + retraction sidecar into `state/runs/` so rebuild
converges.

Dry-run by DEFAULT — pass `--apply` to write.

Usage:
    python -m scripts.backfill_cleanup_journal --vault-root <path> \\
        --audit <state/kdb-clean-orphans-audit-...json> [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from kdb_compiler import atomic_io
from kdb_compiler.kdb_clean import build_cleanup_artifacts


def compute_retracted_slugs(reaped: list[dict], manifest: dict) -> list[str]:
    """A reaped slug is retracted iff no page in the current manifest carries
    it. The manifest here is post-reap (and post-canonical-recompile), so a
    reaped slug absent from it is genuinely gone."""
    reaped_slugs = {r["slug"] for r in reaped if r.get("slug")}
    live_slugs = {p.get("slug") for p in manifest.get("pages", {}).values()}
    return sorted(reaped_slugs - live_slugs)


def started_at_from_run_id(run_id: str) -> str:
    """`clean-orphans-2026-05-16T10-16-00` -> local-ISO-with-offset.
    The run_id stem is a naive local timestamp; re-emit it with the offset."""
    stem = run_id.removeprefix("clean-orphans-")
    naive = datetime.strptime(stem, "%Y-%m-%dT%H-%M-%S")
    return naive.astimezone().isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="backfill_cleanup_journal")
    p.add_argument("--vault-root", required=True,
                   help="Absolute path to the Obsidian vault root")
    p.add_argument("--audit", required=True,
                   help="Path to the kdb-clean-orphans-audit-*.json file")
    p.add_argument("--apply", action="store_true",
                   help="Write the journal + sidecar (default is dry-run)")
    args = p.parse_args(argv)

    vault_root = Path(args.vault_root).resolve()
    state_root = vault_root / "KDB" / "state"
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    manifest = json.loads(
        (state_root / "manifest.json").read_text(encoding="utf-8"))

    run_id = audit["run_id"]
    reaped = audit["reaped"]
    retracted_slugs = compute_retracted_slugs(reaped, manifest)
    report = {
        "reaped": reaped,
        "dead_links": audit.get("dead_links", []),
        "retracted_slugs": retracted_slugs,
    }
    started = started_at_from_run_id(run_id)
    journal, retraction = build_cleanup_artifacts(report, run_id, started, started)

    print(f"run_id:           {run_id}")
    print(f"reaped pages:     {len(reaped)}")
    print(f"retracted slugs:  {len(retracted_slugs)}  {retracted_slugs}")
    print(f"journal -> state/runs/{run_id}.json")
    print(f"sidecar -> state/runs/{run_id}/retraction.json")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit.")
        return 0

    runs_root = state_root / "runs"
    sidecar_dir = runs_root / run_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    atomic_io.atomic_write_json(sidecar_dir / "retraction.json", retraction,
                                sort_keys=True)
    atomic_io.atomic_write_json(runs_root / f"{run_id}.json", journal,
                                sort_keys=True)
    print("\nAPPLIED — journal + retraction sidecar written. Next: "
          "`graphdb-kdb rebuild` then `graphdb-kdb verify`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
