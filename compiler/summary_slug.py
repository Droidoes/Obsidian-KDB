"""compiler.summary_slug — the ONE expected_summary_slug derivation (#115, Task 1.4).

Every consumer — the compile-time semantic gate, the pre-call underivable-stem
route, aggregate validation, replay, and kdb-validate-response — derives the
expected per-source summary slug through THIS function. The derivation is
pinned identical to scripts/cohort_slug_collision_guard.py (Task 0.3) by an
equivalence test; any change here is a contract change.

The expected value is NEVER injected into the prompt (model authorship, D-115).
"""
from __future__ import annotations

from pathlib import Path

from common.paths import PathError, slugify

SUMMARY_PREFIX = "summary-"
# 120 (MAX_SLUG_LEN) − len("summary-") — the stem budget so the full slug
# never exceeds the slug length cap.
STEM_BUDGET = 112


def expected_summary_slug(source_id: str) -> str:
    """Derive the expected summary slug for a source (pure).

    Path(source_id).stem → common.paths.slugify → 112-char stem budget
    (trailing-hyphen rstrip) → "summary-" prefix. Raises PathError on an
    underivable stem (empty / non-ASCII-only normalization).
    """
    normalized = slugify(Path(source_id).stem)
    if len(normalized) > STEM_BUDGET:
        normalized = normalized[:STEM_BUDGET].rstrip("-")
    return SUMMARY_PREFIX + normalized
