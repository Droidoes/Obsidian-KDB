"""#123 result surface (spec §1.1 `GraphSearchResult`, §6.3 `SearchTelemetry`).

Separate from `types.py` for one reason: telemetry carries the per-class
`Violations` produced by `response.py`, and `response.py` imports `types.py`.
Putting the result here keeps that dependency one-way.

`SearchTelemetry` is **controller-produced, never the LLM** (§6.3). Every field is
either counted by P1 code or supplied by P2's orchestrator; nothing here is read
off the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .budget import Stage
from .response import Violations
from .types import (
    BudgetDetected,
    BudgetSide,
    EvidenceStatus,
    Execution,
    Hit,
    Status,
)

#: Named telemetry classes the ratified terminals refer to by name. Closed on
#: purpose — a contract that says "paired with `thin_failed_nonbinding`" needs the
#: name to be checkable, not a free-form string.
WatchedClass = Literal[
    "thin_failed_nonbinding",  # F1: thin exhausted, N ≤ M, fat ran anyway
    "thin_retained_zero",  # D3: thin retained nothing over N > M
    "domain_missing",  # §1.2: pass-1 domain missing/null ⇒ empty space
    "budget_estimation_miss",  # D7: the estimate was under, the provider was not
]


@dataclass(frozen=True)
class BudgetRecord:
    """The per-stage budget record (§6.3, §7.2 R2 as amended by D6/D9).

    Recorded for every stage that reached a budget decision — including the ones
    that *passed*, because a series of estimates that never bind is exactly how
    the estimator's calibration is judged.

    `finish_reason_raw` / `finish_reason_normalized` are populated only on the
    post-call path. Both are kept (D9.4/codex P2): the raw value is the evidence,
    the normalized value is the decision, and an unknown raw value must never be
    guessed into the budget class.
    """

    stage: Stage
    budget_estimate_tokens: int
    selector_window: int
    headroom_factor: float
    visible_output_allowance: int
    hidden_output_reserve: int
    fits: bool
    detected: BudgetDetected = "pre_call"
    budget_side: BudgetSide = "input"
    finish_reason_raw: str | None = None
    finish_reason_normalized: str | None = None


@dataclass(frozen=True)
class SearchTelemetry:
    """§6.3, controller-produced.

    **`status` and `execution` are deliberately absent** even though §6.3's prose
    lists them. They live on `GraphSearchResult`, and a second copy can disagree
    with the first — the emission reads them from the result. Recorded as a
    narrowing in the P1 plan, in the same class as `page_type`'s.
    """

    eligible_space_size: int = 0
    stage1_retained: int = 0
    #: Entities actually sent to fat (D-123-B). Was `min(retained, M)` and now
    #: varies with the budget, so it is reported rather than inferred.
    stage2_pool_size: int = 0
    #: True when the fill stopped on the budget rather than on running out of
    #: candidates — i.e. at least one retained entity was NOT presented to fat.
    #: Expected to be permanently false at current corpus density (bodies would
    #: have to average ~19x live reality to bind at M=150); it is a fail-safe, and
    #: this is the flag that says whether the fail-safe has ever engaged.
    stage2_budget_bound: bool = False
    stage2_hydrated: int = 0
    stage2_title_only: int = 0
    returned_entries: int = 0
    #: `None` when `returned_entries == 0` — D9.6. A truncated attempt has no
    #: entry population, so it cannot supply a denominator.
    valid_entry_yield: float | None = None
    attempted_violations: Violations = field(default_factory=Violations)
    all_entries_dropped_occurrences: int = 0
    unattributed_hit_count: int = 0
    query_truncated_occurrences: int = 0
    #: Warn-only envelope sink: a failed artifact write never fails the search.
    search_artifact_write_failures: int = 0
    retry_attempts: int = 0
    selector_failure_class: str | None = None
    budget_records: tuple[BudgetRecord, ...] = ()
    #: fat top-10 ∩ thin top-20 ÷ len(fat top-10). `None` when fat produced no
    #: validated hits or no fat stage ran (codex #12).
    concordance: float | None = None
    #: The MEASURED bytes-per-token of the request each stage actually sent —
    #: rendered bytes over the provider's own reported prompt-token count.
    #: `None` where the stage never ran or no response reached us; never 0.
    #:
    #: **A read-only VIEW over the archived `StageRecord`s, not a second store**
    #: (`StageRecord.measured_bytes_per_token` is the authority). Surfaced here
    #: because the caller cannot see `StageRecord`s at all yet — the envelope
    #: sink is P3a — and Joseph's ruling closing Fork C is that the estimator's
    #: calibration must be a live series rather than a frozen synthetic gate:
    #: *"we need to keep the stats for the real ratio when we run the tests
    #: end-to-end."*
    #:
    #: **Reported per stage, deliberately never blended.** Thin sends slug-heavy
    #: identity lines; fat sends whole prose bodies. Those tokenize at genuinely
    #: different densities, and one combined figure would hide exactly the spread
    #: the series exists to show. Compare each against
    #: `ESTIMATOR_BYTES_PER_TOKEN`: below it means the pre-flight under-estimated
    #: that request and the 0.8 headroom absorbed the difference.
    thin_bytes_per_token: float | None = None
    fat_bytes_per_token: float | None = None
    watched: tuple[WatchedClass, ...] = ()
    search_snapshot_hash: str | None = None
    artifact_ref: str | None = None


@dataclass(frozen=True)
class GraphSearchResult:
    """Spec §1.1. Returned on every non-defect path; an *unexpected* exception is
    a defect and propagates instead (§2.1 fail-hard posture), and a request that
    was never valid raises `InvalidGraphSearchRequest` rather than arriving here.
    """

    hits: tuple[Hit, ...]
    unresolved_expressions: tuple[str, ...]
    status: Status
    execution: Execution
    telemetry: SearchTelemetry
    evidence_status: EvidenceStatus = "not_applicable"
    #: `None` when no fat stage executed.
    body_coverage: float | None = None


__all__ = [
    "BudgetRecord",
    "GraphSearchResult",
    "SearchTelemetry",
    "WatchedClass",
]
