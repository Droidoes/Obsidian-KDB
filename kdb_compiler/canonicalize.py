"""Canonicalization stage for KDB compile (Task #74).

Stage [6] of the kdb-compile pipeline (post-#74.4). Sits between Stage [5]
reconcile and Stage [7] build_source_state. Resolves alias surface forms
to canonical entity slugs so wiki pages and graph entities agree on
names (wiki ≡ graph on entity names per blueprint D-R5-12).

This module currently exposes the **ledger loader** (Task #74.2). The
algorithm `canonicalize.run()` lands in Task #74.3; pipeline wiring in
Task #74.4.

References:
- docs/task74-canonicalization-blueprint.md §6 (contract) and §7 (algorithm)
- docs/what-is-the-ontology-for.md §8.2 (canonicalization-first mandate)

Errors raised here are fatal per D-R5-9 — Stage [6] failure prevents the
compile from progressing to patch_applier so the vault is not written
inconsistently with the graph.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# Sentinel sha for the "missing file → empty ledger" path (D-R5-8). Stored
# into canonical_meta.ledger_snapshot_sha256 so replay (D39 / D-R5-7) can
# verify the same condition held during the original compile.
EMPTY_LEDGER_SHA = "empty"


class LedgerLoadError(RuntimeError):
    """Raised when aliases.json is present but cannot be loaded or
    validated (malformed JSON, wrong shape, duplicate surface, missing
    required field). Fatal per D-R5-9 — caller must surface the failure
    journal and halt the pipeline before patch_applier."""


@dataclass(frozen=True)
class AliasEntry:
    """One entry in the alias ledger.

    `surface` — the form the LLM might emit (e.g. "AAPL").
    `canonical` — the slug it should resolve to (e.g. "apple-inc").
    `note` — optional human comment for ledger maintainers; no runtime effect.
    """
    surface: str
    canonical: str
    note: str | None = None


@dataclass(frozen=True)
class AliasLedger:
    """Immutable snapshot of `aliases.json` returned by `load_or_empty`.

    `entries` is the parsed list of mappings.
    `snapshot_sha256` is sha256 of the raw file bytes — captured into
        `canonical_meta.ledger_snapshot_sha256` so `graphdb-kdb rebuild`
        can prove the ledger state matched what was archived.
        Equals `EMPTY_LEDGER_SHA` ("empty") when the file was missing.
    `path` is the source location for diagnostics; `None` for purely
        synthetic ledgers built in tests.
    """
    entries: tuple[AliasEntry, ...] = ()
    snapshot_sha256: str = EMPTY_LEDGER_SHA
    path: Path | None = None

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def by_surface(self) -> Mapping[str, AliasEntry]:
        """Build a dict view keyed by raw surface form. Surface keys are
        not normalized here — canonicalize.run() (Task #74.3) normalizes
        the LLM-emitted slug before lookup, so the ledger key shape must
        match the post-normalization form the algorithm produces."""
        return {e.surface: e for e in self.entries}


def load_or_empty(path: Path | str) -> AliasLedger:
    """Load the alias ledger from `path`. Behavior per D-R5-8:

    - **Missing file** → returns an empty `AliasLedger` (sha = "empty")
      and emits a `UserWarning` so the operator sees that string
      normalization is the only canonicalization mechanism running.
      First-run convenience: nothing breaks before any aliases exist.
    - **Present + valid** → returns a populated `AliasLedger` with sha
      computed over the raw file bytes.
    - **Present + malformed** → raises `LedgerLoadError`. Fatal per
      D-R5-9; Stage [6] writes a failure journal and the pipeline halts
      before patch_applier so wiki and graph stay aligned on the
      previous state.

    Validation enforced:
    - Root is a JSON object.
    - `aliases` is a list (default `[]` if absent).
    - Each entry is an object with non-empty string `surface` and
      `canonical`; optional `note` is a string if present.
    - No surface appears twice. Duplicate surfaces (whether they map to
      the same canonical or not) raise `LedgerLoadError` so ledger
      ambiguity surfaces at edit time, not at compile time.
    """
    p = Path(path)
    if not p.exists():
        warnings.warn(
            f"Alias ledger not found at {p}; running with empty ledger "
            "(string normalization only — D-R5-8).",
            UserWarning,
            stacklevel=2,
        )
        return AliasLedger(entries=(), snapshot_sha256=EMPTY_LEDGER_SHA, path=p)

    raw_bytes = p.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as e:
        raise LedgerLoadError(f"malformed JSON in ledger at {p}: {e}") from e

    if not isinstance(payload, dict):
        raise LedgerLoadError(
            f"ledger root at {p} must be a JSON object, "
            f"got {type(payload).__name__}"
        )

    raw_entries = payload.get("aliases", [])
    if not isinstance(raw_entries, list):
        raise LedgerLoadError(
            f"`aliases` in ledger at {p} must be a list, "
            f"got {type(raw_entries).__name__}"
        )

    parsed: list[AliasEntry] = []
    seen_surfaces: set[str] = set()
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] must be an object, "
                f"got {type(raw).__name__}"
            )
        surface = raw.get("surface")
        canonical = raw.get("canonical")
        if not isinstance(surface, str) or not surface:
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] missing required non-empty "
                "string field 'surface'"
            )
        if not isinstance(canonical, str) or not canonical:
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] missing required non-empty "
                "string field 'canonical'"
            )
        note = raw.get("note")
        if note is not None and not isinstance(note, str):
            raise LedgerLoadError(
                f"ledger at {p}: entry [{i}] 'note' must be a string if "
                f"present, got {type(note).__name__}"
            )
        if surface in seen_surfaces:
            raise LedgerLoadError(
                f"ledger at {p}: surface {surface!r} appears more than once "
                "— resolve the duplicate in aliases.json before re-running"
            )
        seen_surfaces.add(surface)
        parsed.append(AliasEntry(surface=surface, canonical=canonical, note=note))

    return AliasLedger(
        entries=tuple(parsed),
        snapshot_sha256=sha,
        path=p,
    )
