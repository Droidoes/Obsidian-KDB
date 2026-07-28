"""#123 `graph_search` — the orchestration spine (spec §2.1, blueprint §2.2/§8).

**P2.2 builds the spine and every terminal that spends nothing.** The stages
themselves are P2.3 (`stage_call`), so this module currently ends at a single
explicit seam: everything before the first model call is complete and contract-
guarded, and the point where the thin call would happen raises `NotImplementedError`
naming the sub-phase. That split is deliberate — a zero-call terminal is a claim
about work *not* done, so it must be reachable and testable without the machinery
that does the work. If a zero-call path ever needed a scripted selector reply to
be exercised, it would not be a zero-call path.

**Order of the pre-work gates**, which the ratified text fixes only partly:

1.  `request.query.validate()` → `InvalidGraphSearchRequest`. Zero rendering,
    zero body reads, zero calls, zero `StageRecord`s (D9.2).
2.  `budget.resolve_selector_route(selector)` → `SearchConfigError` (§8 B10).
3.  Empty / reason-stamped-empty space → `abstain_empty_space`.
4.  Thin pre-flight → `budget_exceeded`, zero spend, never retried (R2).

**Steps 1 and 2 are both "before any work" in the ratified text, which does not
order them relative to each other.** Chosen: the request first, because it is the
caller's own input and is checkable without any configuration at all — a caller
sending 11 expressions gets told about the 11 expressions rather than about a
route they may not have chosen. Recorded as a decision, not read off the spec, and
pinned by a test that fires both faults at once so the precedence cannot drift
silently.

**`json_mode` splits across two sub-phases.** The ratified requirement is
`json_mode=True` on every selector `ModelRequest` — but requests are built in
`stage_call`, so that assertion belongs to P2.3. What lands *here* is the half
that must fail before any work: a route whose `api_call_type` cannot honour
`json_mode` at all is rejected at resolution. `common/call_model.py` implements
`json_mode` on the openai-compat path (`:291`) and the gemini path (`:232`) and
**not** on the anthropic path — so an anthropic selector would silently free-form
its JSON, which is the exact failure Pass-2 shipped and `test_compile_source.py:139`
now pins. Silent is the problem, so it is made loud at resolution.

**The audit payload is built on every terminal, including the zero-call ones**
(§6 — their emptiness is the finding, not a reason to skip the record). How the
full payload reaches the caller is deliberately still open: ratified §1.1 fixes
`GraphSearchResult` at seven fields and `audit` is not among them, so the
blueprint §2.1 gloss "audit (always, §6)" describes an obligation rather than a
field. P2.2 discharges the obligation to *build* it and surfaces the part that has
a ratified home — `telemetry.search_snapshot_hash` — leaving delivery to P2.4,
which is where the caller-persistence bullet lives. Nothing here is shaped in a
way that presupposes the answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from common.call_model import ModelRequest, ModelResponse
from common.model_pool import ModelSpec

from . import budget, projection
from .artifact import SearchAuditPayload, SearchResultSummary, build_audit_payload
from .contracts import assert_result_contract
from .prompts import render_thin_messages
from .result import BudgetRecord, GraphSearchResult, SearchTelemetry, WatchedClass
from .types import (
    Execution,
    GraphSearchRequest,
    SearchConfigError,
    SearchSpaceRef,
    Status,
)

#: The seam P2.3 fills. Named rather than left as a bare `NotImplementedError`
#: so a test can assert the spine reached the call boundary and stopped there —
#: which is how "every zero-call terminal returns before any call" is proved
#: while the calling machinery does not yet exist.
STAGE_CALL_SEAM = (
    "stage_call is P2.3 — the P2.2 spine covers request validation, route "
    "resolution and every zero-spend terminal, and stops at the thin call"
)


def _empty_space_watched(space: SearchSpaceRef) -> tuple[WatchedClass, ...]:
    """`domain_missing` when a domain-scoped space has no domain at all (§1.2).

    Deliberately narrow. Spec §3.4 names two reasons, `domain_empty` and
    `domain_missing`, but `WatchedClass` is a **closed** literal carrying only the
    latter — so an empty domain cluster emits no watched class rather than a
    string the type does not admit. The distinction is still recoverable from the
    record: `domain` is `None` in one case and set in the other, and both land on
    the same terminal. Widening the literal would be a contract change, and the
    contract does not require the second reason to be watched
    (`EMPTY_SPACE.required_watched` is empty).

    A `whole_graph` or `explicit` space legitimately carries no domain, so the
    class fires only for `domain_subtree` — otherwise every empty whole-graph
    search would report a missing domain it never had.
    """
    if space.scope_kind == "domain_subtree" and space.domain is None:
        return ("domain_missing",)
    return ()


def _zero_call_result(
    *,
    request: GraphSearchRequest,
    status: Status,
    execution: Execution,
    telemetry: SearchTelemetry,
) -> GraphSearchResult:
    """The shared field pattern of the zero-call terminals.

    Every one of them is `hits=[]`, every request expression unresolved,
    `evidence_status=not_applicable`, `body_coverage=None` — read off
    `contracts.EMPTY_SPACE` / `THIN_PREFLIGHT_BUDGET`, which is why
    `assert_result_contract` at the return site is a real check and not a
    restatement of this helper: the helper builds one shape, the matrix says which
    terminals may wear it.
    """
    return GraphSearchResult(
        hits=(),
        unresolved_expressions=request.query.expressions,
        status=status,
        execution=execution,
        telemetry=telemetry,
        evidence_status="not_applicable",
        body_coverage=None,
    )


def _audit_for(
    *,
    request: GraphSearchRequest,
    result: GraphSearchResult,
    execution: Execution,
) -> SearchAuditPayload:
    """Build the record for a zero-call terminal — no stages, by construction."""
    return build_audit_payload(
        graph_ref=request.search_space.graph_ref,
        query=request.query,
        manifest=request.search_space.entities,
        execution=execution,
        stages=(),
        result=SearchResultSummary(
            hits=result.hits,
            unresolved_expressions=result.unresolved_expressions,
            status=result.status,
            evidence_status=result.evidence_status,
            body_coverage=result.body_coverage,
        ),
    )


def graph_search(
    request: GraphSearchRequest,
    *,
    selector: ModelSpec,
    call: Callable[[ModelRequest], ModelResponse],
    body_reader: projection.BodyReader,
) -> GraphSearchResult:
    """Spec §2.1. Consumer-neutral: nothing here knows about pass-1.5.

    Typed, deliberate outcomes are `status` values. An **unexpected** exception is
    a defect and propagates — there is no catch-all (§2.1 fail-hard posture,
    Joseph's #121 ruling). `body_reader` is required rather than defaulted:
    `get_body` lives in `kdb_graph`, which this package must not import (B1), so
    the "default: get_body bound to the caller's vault_root" in §2.1 is the
    *adapter's* default, not the core's.
    """
    # 1. Request validity. Before any rendering, body read, call or StageRecord.
    request.query.validate()

    # 2. Route preconditions (§8 B10) — ctx_window, tokens_lte_bytes, the output
    #    envelope, and json_mode honourability.
    budget.resolve_selector_route(selector)
    _require_json_mode_capable(selector)

    space = request.search_space

    # 3. Empty / reason-stamped-empty space — `call` is never invoked (§1.2).
    if not space.entities:
        telemetry = SearchTelemetry(
            eligible_space_size=0,
            watched=_empty_space_watched(space),
        )
        result = _zero_call_result(
            request=request,
            status="abstain_empty_space",
            execution="not_executed",
            telemetry=telemetry,
        )
        audit = _audit_for(request=request, result=result, execution="not_executed")
        return assert_result_contract(
            "empty_space",
            _with_snapshot(result, audit),
            request_expressions=request.query.expressions,
            thin_attempts=0,
            fat_attempts=0,
        )

    # 4. Thin pre-flight (R2). Rendering is allowed here — the terminal is
    #    zero-*call*, not zero-work — but nothing is spent and it is never retried,
    #    the estimate being deterministic.
    messages = render_thin_messages(
        evidence="\n".join(projection.render_thin_line(entity) for entity in space.entities),
        query=request.query.text,
    )
    rendered_bytes = len(messages.system.encode()) + len(messages.user.encode())
    verdict = budget.preflight("thin", rendered_bytes=rendered_bytes, spec=selector)

    if not verdict.fits:
        telemetry = SearchTelemetry(
            eligible_space_size=len(space.entities),
            budget_records=(_budget_record(verdict, selector),),
        )
        result = _zero_call_result(
            request=request,
            status="budget_exceeded",
            execution="not_executed",
            telemetry=telemetry,
        )
        audit = _audit_for(request=request, result=result, execution="not_executed")
        return assert_result_contract(
            "thin_preflight_budget",
            _with_snapshot(result, audit),
            request_expressions=request.query.expressions,
            thin_attempts=0,
            fat_attempts=0,
        )

    # ---- everything below spends money; P2.3 fills it in --------------------
    raise NotImplementedError(STAGE_CALL_SEAM)


def _require_json_mode_capable(spec: ModelSpec) -> None:
    """Reject a route that cannot honour `json_mode` (see the module docstring).

    Lives here rather than inside `budget.resolve_selector_route` because it is a
    *prompt-contract* precondition, not a budget one: `resolve_selector_route`'s
    three existing checks are all about window and output sizing, and folding an
    unrelated premise into it would make the function's name stop matching its
    contents.
    """
    if spec.route.api_call_type == "anthropic":
        raise SearchConfigError(
            f"selector route {spec.id!r} dispatches api_call_type='anthropic', which "
            "does not implement json_mode (common/call_model.py implements it for "
            "openai_compat and gemini only) — the selector would free-form its JSON "
            "silently, which is the Pass-2 failure test_compile_source.py:139 pins"
        )


def _budget_record(verdict: budget.BudgetVerdict, spec: ModelSpec) -> BudgetRecord:
    """A record for every stage that reached a budget decision — including the
    ones that pass, since a series of estimates that never bind is how the
    estimator's calibration gets judged (`result.BudgetRecord`)."""
    return BudgetRecord(
        stage=verdict.stage,
        budget_estimate_tokens=verdict.estimated_input_tokens,
        selector_window=spec.ctx_window or 0,
        headroom_factor=budget.BUDGET_HEADROOM,
        visible_output_allowance=budget.visible_output_allowance(verdict.stage),
        hidden_output_reserve=budget.hidden_output_reserve(),
        fits=verdict.fits,
        detected="pre_call",
        budget_side="input",
    )


def _with_snapshot(
    result: GraphSearchResult, audit: SearchAuditPayload
) -> GraphSearchResult:
    """Carry the built audit's snapshot hash onto the result.

    The one part of the audit with a ratified home on the result
    (`SearchTelemetry.search_snapshot_hash`). This is also what makes the
    zero-call audit build *observable*, and therefore tested rather than dead
    code, without inventing a delivery surface P2.4 has yet to decide.
    """
    return replace(
        result,
        telemetry=replace(
            result.telemetry, search_snapshot_hash=audit.search_snapshot_hash
        ),
    )


__all__ = ["STAGE_CALL_SEAM", "graph_search"]
