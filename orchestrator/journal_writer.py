"""Run-journal + replay-sidecar archival (#132) — D39 for the orchestrator era.

The live conductor ingests through `kdb_graph.intake` directly (Task #91) and
until #132 never archived per-run replay artifacts — `graphdb-kdb rebuild`
discovered zero eligible journals on a modern state tree. This module writes,
once per run, the D39 layout the rebuilder expects:

  state/runs/<run_id>.json                 — run journal (schema 2.3)
  state/runs/<run_id>/compile_result.json  — the exact combined intake payload
  state/runs/<run_id>/last_scan.json       — the exact intake scan inputs,
                                             split by live phase:
                                             files/to_compile (commits) vs
                                             moved_files/to_reconcile (reconcile)

Producer contract (`docs/reference/graphdb-kdb-producer-contract.md` §3.4):
sidecar contents are byte-identical to what was ingested live — archived, never
regenerated. The caller (run()'s finally) assembles the payloads from its
accumulators; this module only writes them.

Archival is audit infrastructure, never on the run's critical path: no function
here raises.
"""
from __future__ import annotations

from pathlib import Path

from common.atomic_io import atomic_write_json

JOURNAL_SCHEMA_VERSION = "2.3"

# Slim audit projection of run()'s counts dict (the full counts live in
# last_orchestrate.json; the journal carries only source-flow keys).
_JOURNAL_COUNT_KEYS = (
    "sources_scanned", "sources_compiled", "sources_noise",
    "sources_failed", "sources_moved", "sources_deleted",
)


def archive_replay_artifacts(
    runs_root: Path,
    *,
    run_id: str,
    started_at: str,
    finished_at: str,
    dry_run: bool,
    success: bool,
    finalize_progress: str,
    counts: dict,
    quarantined_sources: list[dict],
    compile_result: dict,
    last_scan: dict,
) -> Path | None:
    """Write the run journal + replay sidecars; return the journal path.

    Never raises. `replayable_payload` is False iff a sidecar write failed —
    the D50 amendment leg: the journal itself is still written (audit), and
    the adapter's eligibility filter will skip the run on replay. The caller
    treats a None return as warn-only (journal write itself failed).
    """
    replayable = True
    try:
        sidecar_dir = runs_root / run_id
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(sidecar_dir / "compile_result.json", compile_result)
        atomic_write_json(sidecar_dir / "last_scan.json", last_scan)
    except Exception:
        replayable = False

    journal = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "producer": "kdb-orchestrate",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "dry_run": dry_run,
        "success": success,
        "replayable_payload": replayable,
        "finalize_progress": finalize_progress,
        "counts": {k: counts.get(k, 0) for k in _JOURNAL_COUNT_KEYS},
        "quarantined_sources": list(quarantined_sources),
    }
    try:
        journal_path = runs_root / f"{run_id}.json"
        atomic_write_json(journal_path, journal)
        return journal_path
    except Exception:
        return None
