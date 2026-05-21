"""Generic replay driver — `graphdb-kdb rebuild` core (#63.6).

Per D-B1: producer-agnostic. Adapter (passed in) handles producer-specific
discovery, eligibility, payload loading, and apply.

Per D-S2: rebuild always drops the WHOLE Kuzu DB (single-producer assumption
documented as L8). Producer-scoped rebuild deferred to TR-3 (post producer #2).

Per D39: replay is the independence proof — Kuzu state at end-of-replay equals
what live ingestion of eligible runs would have produced.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import kuzu

from graphdb_kdb.adapters.base import (
    EligibilityResult,
    ProducerAdapter,
    RunDescriptor,
    SkipReason,
)
from graphdb_kdb.graphdb import GraphDB

# Order matters: rel tables reference node tables. Drop rels first.
# ALIAS_OF added in #74.1 (schema v2.0).
_DROP_ORDER: tuple[str, ...] = (
    "LINKS_TO",
    "SUPPORTS",
    "ALIAS_OF",
    "Entity",
    "Source",
    "_SchemaMeta",
)


OutcomeState = Literal["replayed", "skipped", "failed"]


@dataclass(frozen=True)
class RunOutcome:
    """Per-run replay result, preserved for audit."""
    run_id: str
    state: OutcomeState
    skip_reason: SkipReason | None = None
    error: str | None = None


@dataclass
class RebuildResult:
    """Aggregate replay summary returned by `rebuild()`."""
    replayed: int = 0
    skipped: int = 0
    failed: int = 0
    outcomes: list[RunOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True iff no replay failed (skips are acceptable per D39 filter)."""
        return self.failed == 0


def _drop_all_tables(conn: kuzu.Connection) -> None:
    """Drop every Kuzu table the graph might hold. Idempotent — missing tables
    are silently tolerated (fresh DB is the same as post-drop)."""
    for name in _DROP_ORDER:
        try:
            conn.execute(f"DROP TABLE {name}")
        except RuntimeError:
            # Kuzu raises generic RuntimeError for "table doesn't exist" and
            # similar. Per D-S2 single-producer assumption, no other tables
            # exist; failure = already-dropped, ignore.
            pass


def _print_drop_warning(graph_dir: Path) -> None:
    print(
        f"⚠️  About to drop ALL tables in Kuzu DB at:\n"
        f"   {graph_dir}\n"
        f"   This is the v1 whole-DB rebuild (L8 — see blueprint §14).\n"
        f"   All current graph state will be replaced by replay results.",
        file=sys.stderr,
    )


def rebuild(
    graph_dir: Path,
    adapter: ProducerAdapter,
    *,
    journals_dir: Path,
    confirm: bool = True,
    extra_descriptors: list[RunDescriptor] | None = None,
) -> RebuildResult:
    """Drop all Kuzu tables and replay eligible runs in chronological order.

    Args:
        graph_dir: Path to the Kuzu DB directory.
        adapter: Producer adapter (see ProducerAdapter protocol).
        journals_dir: Directory containing the producer's run journals.
        confirm: When True, print a stderr warning before dropping. Tests pass
            False; CLI sets via --yes flag.
        extra_descriptors: Optional extra RunDescriptors to merge into the
            discovered list (e.g., a baton-backfill descriptor with
            `payload_paths` set). Per D-S2 they go through the same
            sort+apply pipeline as discovered descriptors.

    Returns:
        RebuildResult with per-run outcomes + aggregate counts.

    Per D-S2: always whole-DB drop.
    Per D-B1: producer-specific logic lives in the adapter; this function
    knows nothing about Obsidian, arxiv, or any specific producer.
    """
    if confirm:
        _print_drop_warning(graph_dir)

    with GraphDB(graph_dir) as graph:
        _drop_all_tables(graph.conn)
        # Re-init schema. _ensure_schema() recreates if absent.
        # We close and re-open to force re-detection from a clean catalog.
        graph._ensure_schema()  # noqa: SLF001 — internal API for the rebuilder

        descriptors = list(adapter.discover_runs(journals_dir))
        if extra_descriptors:
            descriptors.extend(extra_descriptors)
        descriptors.sort(key=lambda d: d.sort_key)

        result = RebuildResult()
        for desc in descriptors:
            elig = adapter.is_eligible(desc)
            if not elig.eligible:
                result.skipped += 1
                result.outcomes.append(
                    RunOutcome(desc.run_id, "skipped", elig.skip_reason)
                )
                continue
            try:
                mutation, scan, run_id = adapter.load_payload(desc)
                adapter.apply(mutation, scan, run_id, graph.conn)
                result.replayed += 1
                result.outcomes.append(RunOutcome(run_id, "replayed"))
            except Exception as e:
                result.failed += 1
                result.outcomes.append(
                    RunOutcome(
                        desc.run_id,
                        "failed",
                        error=f"{type(e).__name__}: {e}",
                    )
                )

    return result
