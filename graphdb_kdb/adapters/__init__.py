"""Producer adapters for GraphDB-KDB.

Each adapter bridges one producer's filesystem artifacts (run journals + sidecar
payloads) to graph mutations via the core's `apply_compile_result()` (D-B1).

See `docs/graphdb-kdb-producer-contract.md` for the contract that any new
adapter must satisfy. Naming convention: `<producer>_runs.py`.
"""
from __future__ import annotations

from graphdb_kdb.adapters.base import (
    EligibilityResult,
    ProducerAdapter,
    RunDescriptor,
    SkipReason,
    UnsupportedJournalVersionError,
)

__all__ = [
    "ProducerAdapter",
    "RunDescriptor",
    "EligibilityResult",
    "SkipReason",
    "UnsupportedJournalVersionError",
]
