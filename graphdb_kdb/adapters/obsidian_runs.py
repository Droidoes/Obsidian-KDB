"""Obsidian-KDB producer adapter (reference implementation, #63.6).

Bridges `kdb-compile`'s run-journal artifacts to GraphDB-KDB mutations:

  state/runs/<run_id>.json              ← run journal (audit record; eligibility fields)
  state/runs/<run_id>/compile_result.json  ← per-run mutation payload (sidecar, post-#63.7)
  state/runs/<run_id>/last_scan.json       ← per-run scan/state payload (sidecar, post-#63.7)

Critical: no `import kdb_compiler.*` anywhere in this module. The adapter
reads producer JSON by documented field names (D-B1 invariant; PR1 of
extraction roadmap).

Per D-S0 the producer's Stage 9 wiring calls `sync_current_run` here — that
hookup itself lives in `kdb_compile.py` and is #63.7-pre's work.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import kuzu

from graphdb_kdb.adapters.base import (
    EligibilityResult,
    RunDescriptor,
)
from graphdb_kdb.types import SyncResult


class ObsidianRunsAdapter:
    """Reads kdb-compile run journals + sidecar archives; emits graph mutations
    via the core's `apply_compile_result()`. Producer-shape v1 per D32-tempered.
    """

    source_type:                ClassVar[str]        = "obsidian-kdb-raw"
    entity_id_namespace:        ClassVar[str | None] = None       # grandfathered per D-S1
    supported_journal_versions: ClassVar[list[str]]  = ["2.0"]    # per D-S3

    # ── discovery ─────────────────────────────────────────────────────────────

    def discover_runs(self, journals_dir: Path) -> list[RunDescriptor]:
        """Return descriptors for every top-level `<run_id>.json` under
        `journals_dir`. Sub-directories (the sidecar archives) are skipped.

        Unsortable / unreadable journals are still returned (`run_id` from the
        filename stem) so `is_eligible` can report `invalid_journal` cleanly.
        """
        if not journals_dir.is_dir():
            return []

        out: list[RunDescriptor] = []
        for path in sorted(journals_dir.iterdir()):
            if not path.is_file() or path.suffix != ".json":
                continue
            run_id, sort_key = self._descriptor_keys(path)
            out.append(RunDescriptor(
                run_id=run_id,
                sort_key=sort_key,
                journal_path=path,
            ))
        return out

    @staticmethod
    def _descriptor_keys(path: Path) -> tuple[str, str]:
        """Extract (run_id, sort_key). Fallback: file stem for both."""
        stem = path.stem
        try:
            with path.open() as f:
                journal = json.load(f)
        except (OSError, json.JSONDecodeError):
            return stem, stem
        run_id = str(journal.get("run_id", stem))
        # Prefer `started_at` (ISO-8601 timestamp) — guarantees chronological
        # ordering regardless of run_id formatting. Falls back to run_id which
        # for kdb-compile is itself an ISO timestamp.
        sort_key = str(journal.get("started_at", run_id))
        return run_id, sort_key

    # ── eligibility ───────────────────────────────────────────────────────────

    def is_eligible(self, descriptor: RunDescriptor) -> EligibilityResult:
        """Apply D39 filter (success && !dry_run && payload_present) plus
        D-S3 version check. Returns structured skip reason for audit.
        """
        # Direct descriptors (baton-style) are implicitly eligible: caller
        # opted in by constructing them with explicit payload_paths.
        if descriptor.payload_paths is not None:
            return EligibilityResult(True, None)

        if descriptor.journal_path is None:
            # Neither journal nor payload paths — malformed descriptor.
            return EligibilityResult(False, "invalid_journal")

        try:
            with descriptor.journal_path.open() as f:
                journal = json.load(f)
        except (OSError, json.JSONDecodeError):
            return EligibilityResult(False, "invalid_journal")

        # Version gate (D-S3) — runs before success/dry_run since unsupported
        # journal shapes can't be trusted to populate those fields correctly.
        version = str(journal.get("schema_version", ""))
        if version not in self.supported_journal_versions:
            return EligibilityResult(False, "unsupported_version")

        if not journal.get("success"):
            return EligibilityResult(False, "failed")
        if journal.get("dry_run"):
            return EligibilityResult(False, "dry_run")

        sidecar_dir = descriptor.journal_path.parent / descriptor.run_id
        if not (sidecar_dir / "compile_result.json").is_file():
            return EligibilityResult(False, "payload_missing")
        if not (sidecar_dir / "last_scan.json").is_file():
            return EligibilityResult(False, "payload_missing")

        return EligibilityResult(True, None)

    # ── payload loading ───────────────────────────────────────────────────────

    def load_payload(self, descriptor: RunDescriptor) -> tuple[dict, dict, str]:
        """Return (mutation_payload, scan_payload, run_id) for replay.

        Standard descriptors: reads sidecar at journal_path.parent/run_id/.
        Direct descriptors: reads from `payload_paths` directly.
        """
        if descriptor.payload_paths is not None:
            mutation_path, scan_path = descriptor.payload_paths
            with mutation_path.open() as f:
                mutation = json.load(f)
            with scan_path.open() as f:
                scan = json.load(f)
            return mutation, scan, descriptor.run_id

        assert descriptor.journal_path is not None, \
            "is_eligible should have screened out journal-less descriptors"
        sidecar_dir = descriptor.journal_path.parent / descriptor.run_id
        with (sidecar_dir / "compile_result.json").open() as f:
            mutation = json.load(f)
        with (sidecar_dir / "last_scan.json").open() as f:
            scan = json.load(f)
        return mutation, scan, descriptor.run_id

    # ── apply ─────────────────────────────────────────────────────────────────

    def apply(
        self,
        mutation: dict,
        scan: dict,
        run_id: str,
        conn: kuzu.Connection,
    ) -> SyncResult:
        """Delegate to core's `apply_compile_result` (Obsidian-flavored v1 per
        D32-tempered + producer-contract §5)."""
        from graphdb_kdb.ingestor import apply_compile_result
        return apply_compile_result(mutation, scan, run_id, conn=conn)

    # ── live-sync (D-S0) ──────────────────────────────────────────────────────

    def sync_current_run(
        self,
        mutation: dict,
        scan: dict,
        run_id: str,
        graph_dir: Path | None = None,
    ) -> SyncResult:
        """Open a GraphDB at `graph_dir` and apply one run's payload.

        Single Obsidian→graph entry point per D-S0; `kdb_compile.py` Stage 9
        calls this (wired in #63.7-pre). The adapter owns connection lifecycle
        here so the caller (producer code) never touches `graphdb_kdb.GraphDB`.
        """
        from graphdb_kdb import default_graph_path
        from graphdb_kdb.graphdb import GraphDB

        resolved = graph_dir if graph_dir is not None else default_graph_path()
        with GraphDB(resolved) as gdb:
            return self.apply(mutation, scan, run_id, gdb.conn)
