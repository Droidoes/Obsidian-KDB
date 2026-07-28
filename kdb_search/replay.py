"""#123 replay (spec §5.2, blueprint §9) — the two non-live modes.

Spec §5.2 names three modes and forbids conflating them:

  * **live search** — `search.graph_search`. Not here.
  * **record replay** (the default) — returns the persisted historical selection.
    **No call, no body read.** The integrity hash is validated first.
  * **historical selector re-call** (opt-in) — runs a selector against the
    **archived artifact**: frozen evidence, archived rendered messages. For
    selector-version A/B, and **never** presented as current graph search.

**What record replay returns, and why it is not a `GraphSearchResult`.** §5.2 says
"the persisted historical selection", and that is exactly what the archive holds:
`SearchAuditPayload` carries a `SearchResultSummary` plus `execution`, so six of
`GraphSearchResult`'s seven fields reconstruct exactly — and `telemetry` does not
reconstruct at all. Some of it could be *derived* (space size from the manifest,
title-only counts from the fat evidence, retry counts from the record count), but
`budget_records` genuinely cannot: pre-flight verdicts were never archived. A
`GraphSearchResult` with `budget_records=()` reads as "the estimates were never
taken", not as "this is a replay", and it would enter the D5 calibration series
as a measurement of zero. So `ReplayedSearch` returns the selection as the spec
words it, and a reader that wants telemetry is told where it isn't.

**Historical re-call bypasses the projector and the budget pre-flight by
construction, and that is the point.** The archived `RenderedMessages` are the
bytes that were actually sent; re-rendering them through the live projector would
produce *different* bytes — today's excerpt policy, today's template version —
and silently defeat the mode, whose entire purpose is holding the input fixed
while the selector varies. `stage_call` takes `messages` as a parameter rather
than rendering internally, so the archived bytes feed straight through with no
bypass hack.

There is no pre-flight either, for the same reason: a budget verdict is a
decision about whether to *build* a request, and this request was built in the
past. A synthesized `BudgetVerdict` would put invented
`budget_estimate_tokens` / `selector_window` figures into a fresh record.
`stage_call` requires one, so re-call passes an explicitly **archival** verdict
whose figures are zeros and whose `fits` is true — inert, and named so it cannot
be mistaken for a measurement.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from common.call_model import ModelRequest, ModelResponse
from common.model_pool import ModelSpec

from .artifact import (
    SearchAuditPayload,
    SearchResultSummary,
    StageRecord,
    compute_artifact_integrity_hash,
)
from .budget import BudgetVerdict, Stage
from .response import (
    ValidatedResponse,
    ValidatedThinResponse,
    validate_response,
    validate_thin_response,
)
from .stage import StageOutcome, stage_call
from .types import Hit, SpaceEntity

#: Stamped on every re-call outcome. Spec §5.2: results from this mode are
#: **never** presented as current graph search, so the mode travels with the
#: result rather than being remembered by whoever asked for it.
HISTORICAL_RECALL = "historical_recall"

_STAGE_OF: dict[str, Stage] = {"thin_selection": "thin", "fat_selection": "fat"}


class ReplayIntegrityError(Exception):
    """The archived payload does not hash to its own recorded integrity hash.

    Raised before anything is returned or re-called. A tampered or truncated
    record is not a search outcome — replaying it would present someone else's
    edit as history, which is the one failure an audit artifact exists to make
    impossible.
    """


@dataclass(frozen=True)
class ReplayedSearch:
    """The persisted historical selection (§5.2), and nothing invented.

    Six fields, all read from the archive. Deliberately **not** a
    `GraphSearchResult`: the seventh field, `telemetry`, is not in the payload
    and `budget_records` cannot be derived from it (see the module docstring).
    Returning a result with empty telemetry would present absent measurements as
    measured zeros.
    """

    hits: tuple[Hit, ...]
    unresolved_expressions: tuple[str, ...]
    status: str
    execution: str
    evidence_status: str
    body_coverage: float | None
    #: Carried through so a reader can tie the replay back to the world it ran
    #: against without re-deriving it.
    search_snapshot_hash: str
    logical_call_count: int


def verify_integrity(audit: SearchAuditPayload) -> None:
    """Recompute the integrity hash and compare. Raises, never returns a flag —
    an integrity check whose result can be ignored is decoration."""
    recomputed = compute_artifact_integrity_hash(
        query=audit.query,
        stages=audit.stages,
        result=audit.result,
        execution=audit.execution,
    )
    if recomputed != audit.artifact_integrity_hash:
        raise ReplayIntegrityError(
            "archived artifact does not match its integrity hash "
            f"(recorded {audit.artifact_integrity_hash}, recomputed {recomputed}) — "
            "the record was altered after it was written, so nothing in it can be "
            "replayed as history"
        )


def replay_record(audit: SearchAuditPayload) -> ReplayedSearch:
    """Record replay — the DEFAULT mode. No model call, no body read.

    Takes the payload rather than a path: persistence is the caller's (§6, "one
    path, caller owns persistence"), and a function that opened files would make
    this package the owner of a storage format it does not define.
    """
    verify_integrity(audit)
    result = audit.result
    return ReplayedSearch(
        hits=result.hits,
        unresolved_expressions=result.unresolved_expressions,
        status=result.status,
        execution=audit.execution,
        evidence_status=result.evidence_status,
        body_coverage=result.body_coverage,
        search_snapshot_hash=audit.search_snapshot_hash,
        logical_call_count=audit.logical_call_count,
    )


#: The inert verdict handed to `stage_call` on the re-call path. Every figure is
#: zero and `fits` is `True`, so nothing here can be read as a measurement: there
#: was no pre-flight, because the request was built in the past and the mode's
#: whole purpose is to hold it fixed. Named rather than inlined so a reader who
#: finds a zeroed `BudgetRecord` in a re-call trace can find out why in one hop.
def _archival_verdict(stage: Stage) -> BudgetVerdict:
    return BudgetVerdict(
        fits=True,
        stage=stage,
        estimated_input_tokens=0,
        reserved_output_tokens=0,
        context_budget_tokens=0,
    )


def _archived_manifest(audit: SearchAuditPayload) -> tuple[SpaceEntity, ...]:
    return audit.eligible_space_manifest


def _pool_for(
    audit: SearchAuditPayload, record: StageRecord
) -> tuple[SpaceEntity, ...]:
    """The closed world the re-called stage is validated against.

    Thin's is the whole archived manifest. **Fat's is the archived evidence
    keys**, not the manifest — the fat stage only ever saw the retained pool, and
    validating a re-call against the full manifest would accept a slug the
    selector was never shown, turning the closed-world guarantee into a wider one
    than the original run had.
    """
    if _STAGE_OF[record.stage] == "thin" or not isinstance(record.evidence, dict):
        return _archived_manifest(audit)
    shown = set(record.evidence)
    return tuple(e for e in _archived_manifest(audit) if e.slug in shown)


@dataclass(frozen=True)
class RecalledStage:
    """One re-called stage, **stamped with its mode** (§5.2).

    The stamp travels with the result rather than being remembered by whoever
    asked for it, because the rule it enforces is about presentation: results
    from this mode are never shown as current graph search. A bare `StageOutcome`
    is indistinguishable from a live one at the point where that matters.
    """

    mode: str
    outcome: StageOutcome
    #: Which archived stage was re-run, so an A/B reader does not have to infer
    #: it from the records.
    stage: Stage


def recall_stage(
    audit: SearchAuditPayload,
    *,
    stage: Stage,
    selector: ModelSpec,
    call: Callable[[ModelRequest], ModelResponse],
    max_results: int,
) -> RecalledStage:
    """Historical selector re-call — **opt-in**, for selector-version A/B.

    Re-runs ONE archived stage against a possibly different selector, using the
    archived rendered messages verbatim. The manifest and evidence are the
    archive's, so the comparison isolates the selector: same input bytes, same
    closed world, different model.

    Uses the FIRST archived attempt for the stage — the bytes are identical
    across a stage's attempts (nothing in this contract reformulates a retry), so
    any attempt would do, and the first is the one that is always present.
    """
    verify_integrity(audit)
    records = [r for r in audit.stages if _STAGE_OF[r.stage] == stage]
    if not records:
        raise ReplayIntegrityError(
            f"the archived artifact has no {stage!r} stage to re-call "
            f"(it carries {sorted({r.stage for r in audit.stages})}) — this run "
            "never reached that stage, so there is no historical request to send"
        )
    record = records[0]
    pool = _pool_for(audit, record)

    def validate(raw: str) -> ValidatedResponse | ValidatedThinResponse:
        if stage == "thin":
            return validate_thin_response(raw, space=pool)
        return validate_response(
            raw,
            space=pool,
            expressions=audit.query.expressions,
            max_results=max_results,
        )

    outcome = stage_call(
        stage,
        # The archived bytes, verbatim. Re-rendering would produce today's
        # excerpt policy and template version against yesterday's data and
        # silently defeat the mode.
        messages=record.rendered_messages,
        evidence=record.evidence,
        spec=selector,
        call=call,
        validate=validate,
        verdict=_archival_verdict(stage),
    )
    return RecalledStage(mode=HISTORICAL_RECALL, outcome=outcome, stage=stage)


__all__ = [
    "HISTORICAL_RECALL",
    "RecalledStage",
    "ReplayIntegrityError",
    "ReplayedSearch",
    "recall_stage",
    "replay_record",
    "verify_integrity",
]
