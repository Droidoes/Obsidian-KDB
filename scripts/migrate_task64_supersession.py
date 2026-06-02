#!/usr/bin/env python3
# HISTORICAL one-shot migration (already applied); references modules that no longer exist. Not part of the live pipeline.
"""Task #64 one-shot migration — apply recompile supersession to the live
manifest for sources already recompiled before the Task #64 code fix landed.

For every source whose latest run archived a Stage 9 sidecar, the emitted
page set is read from state/runs/<run_id>/compile_result.json and asserted
equal to the manifest's sources[source_id].outputs_touched. Pages that still
list the source but were not emitted lose that source from
supports_page_existence + source_refs; pages left with empty support are
flagged orphan_candidate.

--dry-run is the DEFAULT. Pass --apply to mutate state/manifest.json.

After --apply, run:  graphdb-kdb rebuild --vault-root <root>
            then:    graphdb-kdb verify  --vault-root <root>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from common import atomic_io, paths
from kdb_compiler.manifest_update import (
    _supersede_omitted_pages,
    assert_manifest_invariants,
)


def _emitted_keys_from_sidecar(sidecar: dict, source_id: str) -> set[str] | None:
    """Page keys emitted for source_id per the archived compile_result.
    Returns None if the source is absent from the sidecar."""
    for cs in sidecar.get("compiled_sources", []):
        if cs.get("source_id") == source_id:
            return {
                paths.slug_to_relpath(p["slug"], p["page_type"])
                for p in cs.get("pages", [])
            }
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="migrate_task64_supersession")
    ap.add_argument("--vault-root", required=True,
                    help="Absolute path to the Obsidian vault root")
    ap.add_argument("--apply", action="store_true",
                    help="Mutate state/manifest.json (default is dry-run)")
    args = ap.parse_args(argv)

    state_root = Path(args.vault_root).resolve() / "KDB" / "state"
    manifest_path = state_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR  cannot read manifest {manifest_path}: {exc}")
        return 1

    now = datetime.now().astimezone().isoformat()
    run_id = f"task64-migration-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"

    audit: dict = {"run_id": run_id, "started_at": now, "apply": args.apply,
                   "sources": []}
    total_affected = 0

    for source_id, rec in sorted(manifest.get("sources", {}).items()):
        last_run_id = rec.get("last_run_id")
        if not last_run_id:
            continue
        sidecar_path = state_root / "runs" / last_run_id / "compile_result.json"
        if not sidecar_path.exists():
            print(f"skip   {source_id} — no sidecar ({last_run_id})")
            continue

        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR  cannot read sidecar {sidecar_path}: {exc}")
            return 1
        emitted = _emitted_keys_from_sidecar(sidecar, source_id)
        if emitted is None:
            print(f"skip   {source_id} — not in sidecar {last_run_id}")
            continue

        # Q1 guard: sidecar emitted set must match the manifest bookkeeping.
        outputs_touched = set(rec.get("outputs_touched", []))
        if emitted != outputs_touched:
            print(f"ERROR  {source_id}: sidecar emitted set != outputs_touched "
                  f"(sidecar run_id={last_run_id})")
            print(f"  only in sidecar : {sorted(emitted - outputs_touched)}")
            print(f"  only in manifest: {sorted(outputs_touched - emitted)}")
            return 1

        affected = _supersede_omitted_pages(
            manifest, source_id, emitted, started_at=now, run_id=run_id,
        )
        if affected:
            total_affected += len(affected)
            print(f"affect {source_id} — {len(affected)} page(s):")
            for k in affected:
                emptied = not manifest["pages"][k]["supports_page_existence"]
                tag = " → ORPHANED" if emptied else ""
                print(f"         {k}{tag}")
        audit["sources"].append({
            "source_id": source_id, "emitted_count": len(emitted),
            "affected_pages": affected,
        })

    # Flag status on any page left with empty support (orphans[] entries were
    # already seeded by _supersede_omitted_pages).
    newly_orphaned: list[str] = []
    for page_key, page in manifest["pages"].items():
        if not page.get("supports_page_existence", []):
            if page.get("status") != "orphan_candidate":
                newly_orphaned.append(page_key)
            page["status"] = "orphan_candidate"
            page["orphan_candidate"] = True
    audit["newly_orphaned"] = sorted(newly_orphaned)

    print(f"\nsummary: {total_affected} page-source link(s) superseded, "
          f"{len(newly_orphaned)} page(s) newly orphaned")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    assert_manifest_invariants(manifest)
    atomic_io.atomic_write_json(manifest_path, manifest, sort_keys=True)
    audit_path = state_root / f"task64-migration-audit-{run_id}.json"
    atomic_io.atomic_write_json(audit_path, audit, sort_keys=True)
    print(f"\nAPPLIED — manifest updated; audit at {audit_path}")
    print(f"Next: graphdb-kdb rebuild --vault-root {args.vault_root}")
    print(f"      graphdb-kdb verify  --vault-root {args.vault_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
