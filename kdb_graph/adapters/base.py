"""Adapter interface for producer→graph translation (D-B1, D-S3).

The adapter is the producer-specific bridge. The core's `rebuilder.rebuild()`
calls into this interface; producers also call `sync_current_run()` directly
for live sync (D-S0).

Critical invariant (D-B1): adapters parse producer JSON artifacts by documented
field names. Adapters MUST NOT import producer Python types (no
`from kdb_compiler.x import Y` inside `kdb_graph/`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, runtime_checkable

import kuzu

from kdb_graph.types import SyncResult


SkipReason = Literal[
    "failed",                # producer reported run failure (success != true)
    "dry_run",               # producer reported dry-run (excluded by D39 filter)
    "payload_missing",       # sidecar archive absent or incomplete
    "invalid_journal",       # journal JSON malformed or missing required fields
    "unsupported_version",   # journal schema_version not in supported_journal_versions
    "unsupported_event_type",  # journal event_type is neither 'compile' nor 'cleanup' (#68)
]


@dataclass(frozen=True)
class RunDescriptor:
    """One discovered run. The core sorts a list of descriptors by `sort_key`
    before iterating; the adapter doesn't pre-sort.

    Two construction shapes:
    1. Standard (journal-based): `journal_path` is set; `payload_paths` is None.
       Eligibility is determined from the journal; payload loaded from the
       sidecar at `journal_path.parent / run_id / {compile_result,last_scan}.json`.
    2. Direct (baton-style): `payload_paths` is set as `(mutation_path, scan_path)`;
       `journal_path` is None. Treated as implicitly eligible by the standard
       adapter. Used for one-shot pre-#63 baton backfill.
    """
    run_id: str
    sort_key: str
    journal_path: Path | None = None
    payload_paths: tuple[Path, Path] | None = None


@dataclass(frozen=True)
class EligibilityResult:
    """Outcome of an eligibility check. `skip_reason` is None iff eligible=True."""
    eligible: bool
    skip_reason: SkipReason | None = None


class UnsupportedJournalVersionError(Exception):
    """Adapter received a journal whose schema_version is not in
    `supported_journal_versions`. Adapters typically return
    `EligibilityResult(eligible=False, skip_reason='unsupported_version')`
    rather than raising — raising is reserved for cases where graceful skip
    is impossible (e.g., the schema mismatch is detected mid-apply)."""


@runtime_checkable
class ProducerAdapter(Protocol):
    """The contract every producer adapter implements.

    See docs/graphdb-kdb-producer-contract.md §4. Adapters live in
    `kdb_graph/adapters/<producer>_runs.py` per D-B1 naming convention.
    """

    # ── declarations (ClassVars on concrete adapter) ──────────────────────────

    source_type: ClassVar[str]
    """Discriminator value written to Source.source_type for this producer's
    sources. e.g., 'obsidian-kdb-raw'."""

    entity_id_namespace: ClassVar[str | None]
    """Per D-S1: prefix prepended to entity IDs before writing to graph. None
    for the Obsidian adapter (grandfathered as bare-slug namespace); explicit
    string (e.g., 'arxiv:') for all future producers."""

    supported_journal_versions: ClassVar[list[str]]
    """Per D-S3: which producer journal `schema_version` values this adapter
    handles. Mismatched versions are reported via `is_eligible` with
    `skip_reason='unsupported_version'`."""

    # ── replay path ───────────────────────────────────────────────────────────

    def discover_runs(self, journals_dir: Path) -> list[RunDescriptor]:
        """Return all run descriptors found under `journals_dir`. Unsorted —
        the core sorts by `sort_key` before iterating."""
        ...

    def is_eligible(self, descriptor: RunDescriptor) -> EligibilityResult:
        """Decide whether this run should be replayed. Reads journal at
        descriptor.journal_path (if set) to evaluate the D39 filter
        (success && !dry_run && payload_present) plus the D-S3 version check.

        Descriptors with `payload_paths` set (direct/baton) are implicitly
        eligible — the caller opted in by constructing them."""
        ...

    def load_payload(self, descriptor: RunDescriptor) -> tuple[dict, dict, str]:
        """Return (mutation_payload, scan_payload, run_id) for replay.

        Standard descriptors: reads sidecar at journal_path.parent/run_id/.
        Direct descriptors: reads directly from `payload_paths`.
        """
        ...

    def apply(
        self,
        mutation: dict,
        scan: dict,
        run_id: str,
        conn: kuzu.Connection,
    ) -> SyncResult:
        """Translate producer-flavored payload to graph mutations.

        For Obsidian v1: delegates to `kdb_graph.ingestor.apply_compile_result`.
        For future producers: delegates to `apply_mutations` once the normalized
        contract refactor lands per producer-contract §5 path (a). Adapters do
        NOT call producer-specific entry points (anti-pattern path (b)).
        """
        ...

    # ── live-sync path (D-S0) ─────────────────────────────────────────────────

    def sync_current_run(
        self,
        mutation: dict,
        scan: dict,
        run_id: str,
        graph_dir: Path | None = None,
    ) -> SyncResult:
        """Entry point for producer's live-sync hook (e.g., `kdb_orchestrate.py`
        graph-sync step — originally wired in #63.7-pre via the deleted kdb_compile.py).

        Adapter opens a GraphDB connection at `graph_dir` (or default), calls
        `apply()` within a transaction, closes. This is the single
        producer→graph entry point; producer code does NOT touch
        `kdb_graph.GraphDB` or `apply_compile_result` directly (D-S0).
        """
        ...
