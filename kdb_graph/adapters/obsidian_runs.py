"""Obsidian-KDB producer adapter (reference implementation, #63.6).

Bridges `kdb-compile`'s run-journal artifacts to GraphDB-KDB mutations:

  state/runs/<run_id>.json              ← run journal (audit record; eligibility fields)
  state/runs/<run_id>/compile_result.json  ← per-run mutation payload (sidecar, post-#63.7)
  state/runs/<run_id>/last_scan.json       ← per-run scan/state payload (sidecar, post-#63.7)

Critical: no imports from `compiler`, `ingestion`, or `orchestrator` anywhere
in this module. The adapter reads producer JSON by documented field names
(D-B1 / D34 invariant; PR1 of extraction roadmap).

Live sync: since Task #91 the orchestrator holds a shared `GraphDB` connection
and calls `kdb_graph.intake` entry points directly (superseding D-S0's
adapter-mediated Stage 9); this adapter remains the entry for rebuild/replay
and for cleanup live-sync (`sync_cleanup_run`, #68).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import kuzu

from kdb_graph.adapters.base import (
    EligibilityResult,
    RunDescriptor,
)
from kdb_graph.types import IntakeResult


class ObsidianRunsAdapter:
    """Reads kdb-compile run journals + sidecar archives; emits graph mutations
    via the core's `apply_compile_result()`. Producer-shape v1 per D32-tempered.
    """

    source_type:                ClassVar[str]        = "obsidian-kdb-raw"
    entity_id_namespace:        ClassVar[str | None] = None       # grandfathered per D-S1
    # +cleanup #68 added 2.1; +canonicalize #74.4 added 2.2 (run journals
    # with a Stage 6 entry + compile_result carrying canonical_meta).
    # The adapter accepts 2.2 journals for replay; alias-Entity / ALIAS_OF
    # writes from canonical_meta land in #74.5 — until then a 2.2 journal
    # replays identically to a 2.0 journal (canonical_meta block ignored).
    supported_journal_versions: ClassVar[list[str]]  = ["2.0", "2.1", "2.2"]

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
        """D39 amended (D50): dry_run=false AND replayable_payload=true.

        Accepts runs with success=false IF replayable_payload=true (e.g.,
        graph_sync failed but compile output is valid and sidecar archived).
        Falls back to success=true for pre-D50 journals without the field.
        """
        # Direct descriptors (baton-style) are implicitly eligible: caller
        # opted in by constructing them with explicit payload_paths.
        if descriptor.payload_paths is not None:
            return EligibilityResult(True, None)

        if descriptor.journal_path is None:
            return EligibilityResult(False, "invalid_journal")

        try:
            with descriptor.journal_path.open() as f:
                journal = json.load(f)
        except (OSError, json.JSONDecodeError):
            return EligibilityResult(False, "invalid_journal")

        # Version gate (D-S3)
        version = str(journal.get("schema_version", ""))
        if version not in self.supported_journal_versions:
            return EligibilityResult(False, "unsupported_version")

        if journal.get("dry_run"):
            return EligibilityResult(False, "dry_run")

        # D50 amended eligibility: replayable_payload=true is sufficient.
        # For pre-D50 journals without the field, fall back to success=true.
        replayable = journal.get("replayable_payload")
        if replayable is None:
            # Legacy journal — use original D39 rule
            if not journal.get("success"):
                return EligibilityResult(False, "failed")
        elif not replayable:
            return EligibilityResult(False, "failed")

        # Event-type routing (#68): absent ⇒ 'compile' (back-compat with 2.0
        # compile journals). 'cleanup' uses a retraction.json sidecar instead of
        # compile_result.json + last_scan.json. Anything else is a hard skip —
        # it must not fall through to 'compile'.
        event_type = journal.get("event_type", "compile")
        sidecar_dir = descriptor.journal_path.parent / descriptor.run_id
        if event_type == "compile":
            if not (sidecar_dir / "compile_result.json").is_file():
                return EligibilityResult(False, "payload_missing")
            if not (sidecar_dir / "last_scan.json").is_file():
                return EligibilityResult(False, "payload_missing")
        elif event_type == "cleanup":
            if not (sidecar_dir / "retraction.json").is_file():
                return EligibilityResult(False, "payload_missing")
        else:
            return EligibilityResult(False, "unsupported_event_type")

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
        # event_type lives in the journal; re-read to route payload loading (#68).
        with descriptor.journal_path.open() as f:
            event_type = json.load(f).get("event_type", "compile")
        if event_type == "cleanup":
            with (sidecar_dir / "retraction.json").open() as f:
                retraction = json.load(f)
            return retraction, {}, descriptor.run_id
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
    ) -> IntakeResult:
        """Route to the core intake by event_type (#68). A 'cleanup' payload
        carries `event_type` + `retracted_slugs`; a compile payload has no
        `event_type` key (absent ⇒ compile). An unrecognized `event_type`
        raises ValueError — `is_eligible` screens these out on the replay path,
        but `apply` is also reachable directly (live sync), so it guards too."""
        event_type = mutation.get("event_type", "compile")
        if event_type == "cleanup":
            from kdb_graph.intake import apply_cleanup
            return apply_cleanup(mutation, run_id, conn=conn)
        if event_type == "compile":
            from kdb_graph.intake import apply_compile_result
            return apply_compile_result(mutation, scan, run_id, conn=conn)
        raise ValueError(f"unsupported event_type: {event_type!r}")

    # ── live-sync path (#68 cleanup; D-S0 superseded by Task #91) ────────────

    def sync_cleanup_run(
        self,
        retraction: dict,
        run_id: str,
        graph_dir: Path | None = None,
    ) -> IntakeResult:
        """Live-sync a cleanup run into the graph (#68).

        The compile live-sync path goes through `kdb_graph.intake` directly
        (Task #91) and has no slot for a scan-less retraction payload — cleanup
        gets its own entry point. `kdb-clean orphans --apply` calls this;
        `apply()` routes the retraction (event_type='cleanup') to
        `apply_cleanup`."""
        from kdb_graph import default_graph_path
        from kdb_graph.graphdb import GraphDB

        resolved = graph_dir if graph_dir is not None else default_graph_path()
        with GraphDB(resolved) as gdb:
            return self.apply(retraction, {}, run_id, gdb.conn)
