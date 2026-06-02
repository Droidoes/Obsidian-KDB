#!/usr/bin/env python3
# HISTORICAL one-shot migration (already applied); references modules that no longer exist. Not part of the live pipeline.
"""Task #66 one-shot migration — backfill last_compiled_hash on the live manifest.

Existing source records predate Task #66 and have no `last_compiled_hash`. Without
a backfill every source would read as "never compiled" and recompile spuriously on
the first post-#66 run. This script writes the field once (Q2), and performs the
EP1 `compile_state` repair as a distinct labeled local data repair (Q4).

Q2 backfill rule:
    file_type == "binary"                                  -> last_compiled_hash = hash
        (a binary has no LLM compile — metadata recording IS its successful
         processing, Q6 — so it is "compiled at its current hash" regardless
         of compile_state, including a stray "error" from the pre-#66 wart)
    compile_state in {compiled, recompiled, metadata_only}  -> last_compiled_hash = hash
    compile_state == "error" (or anything else), markdown   -> leave absent (eligible)

Q4 EP1 repair (--repair-error-source, repeatable): a source hand-edited to
`compile_state: "error"` that was in fact successfully compiled at its recorded
`hash`. The repair sets compile_state error -> recompiled BEFORE the Q2 loop, so the
uniform rule then backfills it. This is a specific local data repair, not
compile-state logic — no code path reads compile_state for a decision.

--dry-run is the DEFAULT. Pass --apply to mutate state/manifest.json.

last_compiled_hash is a manifest-only field — no graphdb-kdb resync is needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from common import atomic_io
from kdb_compiler.manifest_update import assert_manifest_invariants

_COMPILED_STATES = {"compiled", "recompiled", "metadata_only"}


def backfill_manifest(manifest: dict, *, repair_error_sources: list[str]) -> dict:
    """Mutate manifest in place. Returns a report dict of what changed."""
    sources = manifest.get("sources", {})
    report: dict = {"repaired": [], "repair_skipped": [],
                    "backfilled": [], "left_eligible": []}

    # --- EP1 kludge revert (one-time local repair, Q4) ---
    for sid in repair_error_sources:
        rec = sources.get(sid)
        if rec is None:
            raise SystemExit(f"ERROR  --repair-error-source {sid}: not in manifest")
        if rec.get("compile_state") != "error":
            report["repair_skipped"].append(sid)
            continue
        rec["compile_state"] = "recompiled"
        report["repaired"].append(sid)

    # --- uniform Q2 backfill ---
    for sid, rec in sorted(sources.items()):
        if rec.get("last_compiled_hash") is not None:
            continue                                  # idempotent
        is_binary = rec.get("file_type") == "binary"
        if is_binary or rec.get("compile_state") in _COMPILED_STATES:
            # binary: metadata recording IS successful processing (Q6), so it
            # is compiled-at-current-hash regardless of compile_state.
            rec["last_compiled_hash"] = rec.get("hash")
            report["backfilled"].append(sid)
        else:
            report["left_eligible"].append(sid)        # error/other markdown -> absent
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="migrate_task66_compiled_hash")
    ap.add_argument("--vault-root", required=True,
                    help="Absolute path to the Obsidian vault root")
    ap.add_argument("--apply", action="store_true",
                    help="Mutate state/manifest.json (default is dry-run)")
    ap.add_argument("--repair-error-source", action="append", default=[],
                    metavar="SOURCE_ID",
                    help="Source whose 'error' compile_state is a known-bad "
                         "hand-edit to revert to 'recompiled' (repeatable)")
    args = ap.parse_args(argv)

    state_root = Path(args.vault_root).resolve() / "KDB" / "state"
    manifest_path = state_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR  cannot read manifest {manifest_path}: {exc}")
        return 1

    report = backfill_manifest(
        manifest, repair_error_sources=args.repair_error_source,
    )

    for sid in report["repaired"]:
        print(f"repair  {sid} — compile_state error -> recompiled (local data repair)")
    for sid in report["repair_skipped"]:
        print(f"skip    {sid} — not in 'error' state; repair not applied")
    for sid in report["backfilled"]:
        print(f"backfill {sid} — last_compiled_hash <- hash")
    for sid in report["left_eligible"]:
        print(f"eligible {sid} — left without last_compiled_hash (will compile)")

    print(f"\nsummary: {len(report['repaired'])} repaired, "
          f"{len(report['backfilled'])} backfilled, "
          f"{len(report['left_eligible'])} left eligible")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    assert_manifest_invariants(manifest)
    run_id = f"task66-migration-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    atomic_io.atomic_write_json(manifest_path, manifest, sort_keys=True)
    audit_path = state_root / f"task66-migration-audit-{run_id}.json"
    atomic_io.atomic_write_json(audit_path, {"run_id": run_id, **report},
                                sort_keys=True)
    print(f"\nAPPLIED — manifest updated; audit at {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
