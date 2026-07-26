"""#123 terminal contract matrix (blueprint §2.2/§8, spec §0 D6/D7/D9, §1.1).

Every way `graph_search` can end is a **named terminal** with a complete,
ratified field contract: `status`, `execution`, `evidence_status`,
`body_coverage`, whether hits are empty, whether every request expression is
unresolved, whether concordance is null, how many logical attempts each stage may
have made, and which watched telemetry classes must be present.

**Who calls this.** P2's orchestrator, at its single return site: it names the
terminal it took and `assert_result_contract` refuses to let a non-conforming
`GraphSearchResult` leave the function. That is the point of the table — not
documentation, but a fail-closed check that an unratified `(status, execution)`
pair or a half-filled terminal cannot escape. P1 has no orchestrator, so P1's
tests drive the rows whose producer already exists (`PRODUCIBLE_IN_P1`) through
real code and pin the rest as shape.

**Two rows the plan's P1.5 bullet did not enumerate.** It names the three
*output*-side post-call terminals. Blueprint §8's branch table also carries two
*input*-side post-call rows — `budget_estimation_miss` at thin and at fat (D7,
re-typed `budget_exceeded`/`detected: post_call` by D8/opus5 M1). They are
ratified terminals with the same structure, so they are in the matrix;
`THIN_INPUT_ESTIMATION_MISS` / `FAT_INPUT_ESTIMATION_MISS`. Recorded here rather
than absorbed silently.

**Where the ratified text stops.** Three cells are genuinely unenumerated: the
evidence side of `FAT_EXHAUSTED` and of `FAT_INPUT_ESTIMATION_MISS`, and
concordance on `FAT_EXHAUSTED`. The blueprint fixes their status/execution and
says nothing about evidence. Rather than infer them from the neighbouring
truncation rows, they are left `None` — unconstrained — and flagged in `note`.
An invented constraint would be indistinguishable from a ratified one to the next
reader, which is the failure mode #21 exists to fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import MAX_ATTEMPTS_PER_STAGE
from .result import GraphSearchResult, WatchedClass
from .types import BudgetDetected, BudgetSide, EvidenceStatus, Execution, Status


class ContractViolation(Exception):
    """A produced `GraphSearchResult` does not satisfy its named terminal. A
    defect in the controller, never a selector outcome — so it propagates rather
    than becoming a fifth `status` (§2.1 fail-hard posture)."""


@dataclass(frozen=True)
class TerminalContract:
    """One ratified terminal. `None` on a constraint field means the ratified
    text does not fix it — never "any value is fine by inference"."""

    name: str
    status: Status
    #: Allowed `execution` values. More than one only where the ratified text
    #: itself admits more than one (the completed path spans F1 and non-F1).
    execution: tuple[Execution, ...]
    #: Inclusive `(low, high)` bounds on logical attempts per stage. These are
    #: blueprint §8's branch table; `test_contract.py` cross-checks the totals
    #: against the table's own figures so the two cannot drift apart silently.
    thin_attempts: tuple[int, int]
    fat_attempts: tuple[int, int]
    evidence_status: tuple[EvidenceStatus, ...] | None = None
    #: `True` ⇒ must be a float; `False` ⇒ must be `None`; `None` ⇒ unconstrained.
    body_coverage_present: bool | None = None
    #: `True` ⇒ `hits` must be empty; `None` ⇒ unconstrained.
    hits_empty: bool | None = None
    #: `True` ⇒ every request expression must be unresolved.
    all_expressions_unresolved: bool | None = None
    #: `True` ⇒ `telemetry.concordance` must be `None`.
    concordance_null: bool | None = None
    detected: BudgetDetected | None = None
    budget_side: BudgetSide | None = None
    required_watched: tuple[WatchedClass, ...] = ()
    #: `selector_failure` must name its class; nothing else may.
    failure_class_required: bool = False
    note: str = ""

    @property
    def max_logical_calls(self) -> int:
        return self.thin_attempts[1] + self.fat_attempts[1]

    @property
    def min_logical_calls(self) -> int:
        return self.thin_attempts[0] + self.fat_attempts[0]


_ZERO = (0, 0)
_ONE = (1, 1)
_UP_TO_TWO = (1, MAX_ATTEMPTS_PER_STAGE)
_EXHAUSTED = (MAX_ATTEMPTS_PER_STAGE, MAX_ATTEMPTS_PER_STAGE)

# ---------------------------------------------------------------------------
# zero-call terminals — no model was invoked
# ---------------------------------------------------------------------------

EMPTY_SPACE = TerminalContract(
    name="empty_space",
    status="abstain_empty_space",
    execution=("not_executed",),
    thin_attempts=_ZERO,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    note="§1.2 — one audit path; `call` is never invoked. Missing pass-1 domain "
    "lands here with `domain_missing`, never a silent whole-graph fallback.",
)

THIN_PREFLIGHT_BUDGET = TerminalContract(
    name="thin_preflight_budget",
    status="budget_exceeded",
    execution=("not_executed",),
    thin_attempts=_ZERO,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="pre_call",
    budget_side="input",
    note="R2 — zero spend, never retried. The estimate is deterministic, so a "
    "retry would fail identically.",
)

# ---------------------------------------------------------------------------
# fat pre-flight terminal (D6, complete contract per codex L3 ≡ opus5 L2)
# ---------------------------------------------------------------------------

FAT_PREFLIGHT_BUDGET = TerminalContract(
    name="fat_preflight_budget",
    status="budget_exceeded",
    execution=("thin_attempted",),
    thin_attempts=_UP_TO_TWO,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="pre_call",
    budget_side="input",
    note="No fat StageRecord exists — that absence is what distinguishes this "
    "from the post-call fat terminal, where the pool WAS presented.",
)

FAT_PREFLIGHT_BUDGET_ON_F1 = TerminalContract(
    name="fat_preflight_budget_on_f1",
    status="budget_exceeded",
    execution=("thin_attempted",),
    thin_attempts=_EXHAUSTED,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="pre_call",
    budget_side="input",
    required_watched=("thin_failed_nonbinding",),
    note="The named F1 interaction. `execution` stays `thin_attempted`, NOT "
    "`fat_after_thin_failure`: that value means the fat call ran, and here the "
    "pre-flight stopped it before it did.",
)

# ---------------------------------------------------------------------------
# D3 — thin retained zero over N > M
# ---------------------------------------------------------------------------

THIN_RETAINED_ZERO = TerminalContract(
    name="thin_retained_zero",
    status="completed",
    execution=("thin_attempted",),
    thin_attempts=_UP_TO_TWO,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    required_watched=("thin_retained_zero",),
    note="D3 — no fat call. `completed` with the watched class, so the KPI series "
    "can separate it from an honest empty selection; a recall-oriented selector "
    "returning zero from a large in-domain space is more likely malfunctioning.",
)

# ---------------------------------------------------------------------------
# post-call OUTPUT terminals (D9.1/D9.3, codex P1) — the call was billed
# ---------------------------------------------------------------------------

THIN_OUTPUT_TRUNCATION = TerminalContract(
    name="thin_output_truncation",
    status="budget_exceeded",
    execution=("thin_attempted",),
    thin_attempts=_ONE,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="post_call",
    budget_side="output",
    note="Exactly one thin StageRecord, carrying raw + normalized stop reason and "
    "the spend. Terminal: F1's proceed-to-fat applies only to retry-exhausted "
    "failures, never to either budget side.",
)

FAT_OUTPUT_TRUNCATION = TerminalContract(
    name="fat_output_truncation",
    status="budget_exceeded",
    execution=("two_stage_attempted",),
    thin_attempts=_UP_TO_TWO,
    fat_attempts=_ONE,
    evidence_status=("complete", "partial"),
    body_coverage_present=True,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="post_call",
    budget_side="output",
    note="The evidence pool WAS built and presented — which is exactly what "
    "distinguishes this from FAT_PREFLIGHT_BUDGET. So evidence_status and "
    "body_coverage are measured, not `not_applicable`/None.",
)

FAT_OUTPUT_TRUNCATION_ON_F1 = TerminalContract(
    name="fat_output_truncation_on_f1",
    status="budget_exceeded",
    execution=("fat_after_thin_failure",),
    thin_attempts=_EXHAUSTED,
    fat_attempts=_ONE,
    evidence_status=("complete", "partial"),
    body_coverage_present=True,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="post_call",
    budget_side="output",
    required_watched=("thin_failed_nonbinding",),
    note="The same fat contract with the F1 execution value and the watched class "
    "preserved.",
)

# ---------------------------------------------------------------------------
# post-call INPUT terminals (D7 budget_estimation_miss, re-typed by opus5 M1)
# ---------------------------------------------------------------------------

THIN_INPUT_ESTIMATION_MISS = TerminalContract(
    name="thin_input_estimation_miss",
    status="budget_exceeded",
    execution=("thin_attempted",),
    thin_attempts=_ONE,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="post_call",
    budget_side="input",
    required_watched=("budget_estimation_miss",),
    note="Thin is estimate-guarded by design — N is unbounded because the space "
    "is searched whole. Attempted once, never retried, excluded from the §8.4 "
    "gate series.",
)

FAT_INPUT_ESTIMATION_MISS = TerminalContract(
    name="fat_input_estimation_miss",
    status="budget_exceeded",
    execution=("two_stage_attempted",),
    thin_attempts=_UP_TO_TWO,
    fat_attempts=_ONE,
    evidence_status=None,
    body_coverage_present=None,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    detected="post_call",
    budget_side="input",
    required_watched=("budget_estimation_miss",),
    note="UNENUMERATED: the evidence side is not fixed by the ratified text. "
    "Reachable only on sub-330k windows — at pool windows the M=100 static "
    "guarantee removes estimation from fat's safety path entirely.",
)

# ---------------------------------------------------------------------------
# retry-exhausted selector failures
# ---------------------------------------------------------------------------

THIN_EXHAUSTED = TerminalContract(
    name="thin_exhausted",
    status="selector_failure",
    execution=("thin_attempted",),
    thin_attempts=_EXHAUSTED,
    fat_attempts=_ZERO,
    evidence_status=("not_applicable",),
    body_coverage_present=False,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=True,
    failure_class_required=True,
    note="N > M. Below M the F1 path runs fat instead, so this terminal and "
    "FAT_*_ON_F1 partition the thin-exhausted case by space size.",
)

FAT_EXHAUSTED = TerminalContract(
    name="fat_exhausted",
    status="selector_failure",
    execution=("two_stage_attempted", "fat_after_thin_failure"),
    thin_attempts=_UP_TO_TWO,
    fat_attempts=_EXHAUSTED,
    evidence_status=None,
    body_coverage_present=None,
    hits_empty=True,
    all_expressions_unresolved=True,
    concordance_null=None,
    failure_class_required=True,
    note="UNENUMERATED: the ratified text fixes status/execution and is silent on "
    "the evidence side and concordance. The truncation rows' reasoning would "
    "apply, but inferring it here would make an implementer's guess look ratified.",
)

# ---------------------------------------------------------------------------
# the ordinary path
# ---------------------------------------------------------------------------

COMPLETED = TerminalContract(
    name="completed",
    status="completed",
    execution=("two_stage_attempted", "fat_after_thin_failure"),
    thin_attempts=_UP_TO_TWO,
    fat_attempts=_UP_TO_TWO,
    evidence_status=("complete", "partial"),
    body_coverage_present=True,
    hits_empty=None,
    all_expressions_unresolved=None,
    concordance_null=None,
    note="Hits may legitimately be empty — an honest empty selection. What "
    "separates it from D3's terminal is `execution`, and from the output "
    "terminal is `status`; no extra marker is needed (D9.6).",
)


TERMINAL_CONTRACTS: dict[str, TerminalContract] = {
    contract.name: contract
    for contract in (
        EMPTY_SPACE,
        THIN_PREFLIGHT_BUDGET,
        FAT_PREFLIGHT_BUDGET,
        FAT_PREFLIGHT_BUDGET_ON_F1,
        THIN_RETAINED_ZERO,
        THIN_OUTPUT_TRUNCATION,
        FAT_OUTPUT_TRUNCATION,
        FAT_OUTPUT_TRUNCATION_ON_F1,
        THIN_INPUT_ESTIMATION_MISS,
        FAT_INPUT_ESTIMATION_MISS,
        THIN_EXHAUSTED,
        FAT_EXHAUSTED,
        COMPLETED,
    )
}

#: The rows whose producer exists in P1 — driven end-to-end through real code by
#: `test_contract.py`. Everything else is shape until P2 supplies the producer.
PRODUCIBLE_IN_P1 = frozenset(
    {"empty_space", "thin_preflight_budget", "fat_preflight_budget"}
)

#: Fail-closed: every `(status, execution)` pair any terminal admits. A pair
#: outside this set is unratified by construction, whatever terminal claims it.
ALLOWED_STATUS_EXECUTION: frozenset[tuple[Status, Execution]] = frozenset(
    (contract.status, execution)
    for contract in TERMINAL_CONTRACTS.values()
    for execution in contract.execution
)


def is_ratified_pair(status: Status, execution: Execution) -> bool:
    """Terminal-agnostic closure check, for a reader holding an archived result
    with no terminal name — the replay/KPI path. `verify_result_contract` does not
    call it: with a terminal named, it is implied."""
    return (status, execution) in ALLOWED_STATUS_EXECUTION


def _watched(result: GraphSearchResult) -> frozenset[str]:
    return frozenset(result.telemetry.watched)


def verify_result_contract(
    terminal: str,
    result: GraphSearchResult,
    *,
    request_expressions: tuple[str, ...],
    thin_attempts: int,
    fat_attempts: int,
) -> tuple[str, ...]:
    """Check a produced result against its named terminal.

    Returns every violation rather than the first: a half-filled terminal usually
    breaks several cells at once, and seeing one of them sends the reader looking
    for a single-field bug that is not there.
    """
    contract = TERMINAL_CONTRACTS.get(terminal)
    if contract is None:
        return (f"unknown terminal {terminal!r}",)

    violations: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            violations.append(f"{terminal}: {message}")

    check(result.status == contract.status, f"status {result.status!r} != {contract.status!r}")
    check(
        result.execution in contract.execution,
        f"execution {result.execution!r} not in {contract.execution!r}",
    )
    # No pair check here on purpose: with the two checks above green, membership
    # in `ALLOWED_STATUS_EXECUTION` follows by construction, so the assertion
    # could never fire on its own. It was written, found unreachable by mutation,
    # and removed rather than left as an assertion that only ever echoes another.
    # The set's own consumer is `is_ratified_pair` — a reader that has an
    # artifact but no terminal name.

    if contract.evidence_status is not None:
        check(
            result.evidence_status in contract.evidence_status,
            f"evidence_status {result.evidence_status!r} not in {contract.evidence_status!r}",
        )
    if contract.body_coverage_present is True:
        check(result.body_coverage is not None, "body_coverage must be measured")
    elif contract.body_coverage_present is False:
        check(result.body_coverage is None, f"body_coverage must be None, got {result.body_coverage!r}")

    if contract.hits_empty is True:
        check(not result.hits, f"hits must be empty, got {len(result.hits)}")
    if contract.all_expressions_unresolved is True:
        check(
            set(result.unresolved_expressions) == set(request_expressions),
            "every request expression must be unresolved, got "
            f"{result.unresolved_expressions!r} for {request_expressions!r}",
        )
    if contract.concordance_null is True:
        check(
            result.telemetry.concordance is None,
            f"concordance must be null, got {result.telemetry.concordance!r}",
        )

    low, high = contract.thin_attempts
    check(low <= thin_attempts <= high, f"thin attempts {thin_attempts} outside {contract.thin_attempts}")
    low, high = contract.fat_attempts
    check(low <= fat_attempts <= high, f"fat attempts {fat_attempts} outside {contract.fat_attempts}")

    missing = set(contract.required_watched) - _watched(result)
    check(not missing, f"missing watched classes {sorted(missing)}")

    if contract.failure_class_required:
        check(
            result.telemetry.selector_failure_class is not None,
            "selector_failure must name its failure class",
        )
    else:
        check(
            result.telemetry.selector_failure_class is None,
            "only selector_failure may carry a failure class, got "
            f"{result.telemetry.selector_failure_class!r}",
        )

    if contract.detected is not None:
        matching = [
            record
            for record in result.telemetry.budget_records
            if (record.detected, record.budget_side) == (contract.detected, contract.budget_side)
        ]
        check(
            bool(matching),
            f"no budget record with detected={contract.detected!r} "
            f"budget_side={contract.budget_side!r}; got "
            f"{sorted((r.detected, r.budget_side) for r in result.telemetry.budget_records)}",
        )
        # A `budget_exceeded` terminal whose record says the budget FIT is the
        # one way this contract can be satisfied field-by-field and still be
        # wrong about what happened.
        check(
            all(not record.fits for record in matching),
            "a budget_exceeded terminal cannot carry a fitting budget record",
        )

    return tuple(violations)


def assert_result_contract(
    terminal: str,
    result: GraphSearchResult,
    *,
    request_expressions: tuple[str, ...],
    thin_attempts: int,
    fat_attempts: int,
) -> GraphSearchResult:
    """P2's return-site guard: returns the result, or raises. Fail-closed by
    design — an unratified terminal never leaves `graph_search`."""
    violations = verify_result_contract(
        terminal,
        result,
        request_expressions=request_expressions,
        thin_attempts=thin_attempts,
        fat_attempts=fat_attempts,
    )
    if violations:
        raise ContractViolation("; ".join(violations))
    return result


__all__ = [
    "ALLOWED_STATUS_EXECUTION",
    "COMPLETED",
    "EMPTY_SPACE",
    "FAT_EXHAUSTED",
    "FAT_INPUT_ESTIMATION_MISS",
    "FAT_OUTPUT_TRUNCATION",
    "FAT_OUTPUT_TRUNCATION_ON_F1",
    "FAT_PREFLIGHT_BUDGET",
    "FAT_PREFLIGHT_BUDGET_ON_F1",
    "PRODUCIBLE_IN_P1",
    "TERMINAL_CONTRACTS",
    "THIN_EXHAUSTED",
    "THIN_INPUT_ESTIMATION_MISS",
    "THIN_OUTPUT_TRUNCATION",
    "THIN_PREFLIGHT_BUDGET",
    "THIN_RETAINED_ZERO",
    "ContractViolation",
    "TerminalContract",
    "assert_result_contract",
    "is_ratified_pair",
    "verify_result_contract",
]
