"""#123 `graph_search` — the orchestration spine (spec §2.1, blueprint §2.2/§8).

**This module decides WHICH stages run and what each is given; `stage.py` owns
what happens inside one.** Every terminal returns through one `finish` helper, so
the audit payload is built on every path (§6) by construction rather than by each
branch remembering to, and `assert_result_contract` cannot be omitted from a
return site — the one mutation P2.2's sweep showed the rest of the suite cannot
catch.

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

**`json_mode` splits across two modules.** The ratified requirement is
`json_mode=True` on every selector `ModelRequest`, and requests are built in
`stage_call`, so that assertion lives there. What lands *here* is the half that
must fail before any work: a route whose `api_call_type` cannot honour
`json_mode` at all is rejected at resolution. `common/call_model.py` implements
`json_mode` on the openai-compat path (`:291`) and the gemini path (`:232`) and
**not** on the anthropic path — so an anthropic selector would silently free-form
its JSON, which is the exact failure Pass-2 shipped and `test_compile_source.py:139`
now pins. Silent is the problem, so it is made loud at resolution.

**The two-stage order and its two enforced guarantees** (§2.2, R4 as amended):

  * **Thin always runs**, even where its answer cannot bind. At `N <= M` stage 2
    is **every** eligible identity regardless of what thin returned (codex #3) —
    a recall-oriented selector can omit an identity by judgment, and validation
    cannot distinguish omission from judgment, so retain-all is enforced
    controller-side rather than asked for in a prompt. That is also what makes
    the F1 path work with no thin output at all.
  * **Stage 2 is presented in MANIFEST order, never thin's ranked order**, so
    fat's judgment stays unanchored to thin's.

**D-123-B splits those two words apart, and the distinction is easy to misread.**
Thin's rank decides **membership** — it always did, since the cut to `M` was made
from thin's list — and §3.4 governs **presentation**. The fill extends the cut
from "top M" to "top K that fit the 0.8 budget", which reuses the mechanism §3.4
already permits rather than amending it. Select by rank; present in manifest
order. That also gives thin's `BEST FIRST` a second consumer beyond the
concordance metric: it now decides who survives a binding budget.

**The audit payload is built on every terminal, including the zero-call ones**
(§6 — their emptiness is the finding, not a reason to skip the record). How the
full payload reaches the CALLER is still open and deliberately not answered here:
ratified §1.1 fixes `GraphSearchResult` at seven fields and `audit` is not among
them, so the blueprint §2.1 gloss "audit (always, §6)" describes an obligation
rather than a field. This module discharges the obligation to *build* it on every
path and surfaces the part with a ratified home
(`telemetry.search_snapshot_hash`). The adapter needs the whole payload to write
its envelope, so a delivery surface has to be decided — it changes this function's
public signature, which wants a ratification rather than an inference. Nothing
here is shaped in a way that presupposes the answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from common.call_model import ModelRequest, ModelResponse
from common.model_pool import ModelSpec

from . import budget, projection
from .artifact import (
    SPACE_MANIFEST_REF,
    TITLE_ONLY_MARKER,
    SearchAuditPayload,
    SearchResultSummary,
    StageRecord,
    build_audit_payload,
)
from .constants import M
from .contracts import assert_result_contract
from .prompts import render_fat_messages, render_thin_messages
from .response import ValidatedResponse, resolve_accounting, validate_response, validate_thin_response
from .result import BudgetRecord, GraphSearchResult, SearchTelemetry, WatchedClass
from .stage import StageOutcome, stage_call
from .types import (
    EvidenceStatus,
    Execution,
    GraphSearchRequest,
    Hit,
    SearchConfigError,
    SearchSpaceRef,
    Status,
)

def _measured_ratio(stages: tuple[StageRecord, ...], stage: str) -> float | None:
    """That stage's real bytes-per-token, or `None` if it was never measured.

    First measuring attempt wins, and the choice is safe rather than arbitrary:
    every attempt of a stage re-sends the **same rendered bytes**, so a retry
    cannot report a different ratio. What a later attempt can be is *unmeasured*
    — a transport failure carries no token count — which is why this skips
    `None`s instead of simply reading `stages[0]`.
    """
    for record in stages:
        if record.stage == stage and record.measured_bytes_per_token is not None:
            return record.measured_bytes_per_token
    return None


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

    # ---- stage 1 ------------------------------------------------------------
    budget_records = [_budget_record(verdict, selector)]
    thin = stage_call(
        "thin",
        messages=messages,
        evidence=SPACE_MANIFEST_REF,
        spec=selector,
        call=call,
        validate=lambda raw: validate_thin_response(raw, space=space.entities, cap=M),
        verdict=verdict,
    )
    if thin.budget_record is not None:
        budget_records.append(thin.budget_record)

    def finish(
        terminal: str,
        *,
        status: Status,
        execution: Execution,
        telemetry: SearchTelemetry,
        hits: tuple[Hit, ...] = (),
        unresolved: tuple[str, ...] | None = None,
        evidence_status: EvidenceStatus = "not_applicable",
        body_coverage: float | None = None,
        stages: tuple[StageRecord, ...] = (),
    ) -> GraphSearchResult:
        """The single shape every post-thin terminal returns through.

        One helper rather than a return statement per branch, so the audit is
        built on **every** path by construction (§6) rather than by each branch
        remembering to — and so `assert_result_contract` cannot be omitted from a
        return site, which is the mutation P2.2's sweep showed the rest of the
        suite cannot catch.
        """
        # Derived HERE rather than in each branch's telemetry closure: `finish`
        # is the one site every post-thin terminal returns through, and the
        # stages are only complete at this point.
        telemetry = replace(
            telemetry,
            thin_bytes_per_token=_measured_ratio(stages, "thin_selection"),
            fat_bytes_per_token=_measured_ratio(stages, "fat_selection"),
        )
        result = GraphSearchResult(
            hits=hits,
            unresolved_expressions=(
                request.query.expressions if unresolved is None else unresolved
            ),
            status=status,
            execution=execution,
            telemetry=telemetry,
            evidence_status=evidence_status,
            body_coverage=body_coverage,
        )
        audit = build_audit_payload(
            graph_ref=space.graph_ref,
            query=request.query,
            manifest=space.entities,
            execution=execution,
            stages=stages,
            result=SearchResultSummary(
                hits=result.hits,
                unresolved_expressions=result.unresolved_expressions,
                status=result.status,
                evidence_status=result.evidence_status,
                body_coverage=result.body_coverage,
            ),
        )
        return assert_result_contract(
            terminal,
            _with_snapshot(result, audit),
            request_expressions=request.query.expressions,
            thin_attempts=thin.attempts,
            fat_attempts=sum(
                1 for record in stages if record.stage == "fat_selection"
            ),
        )

    watched: tuple[WatchedClass, ...] = ()

    def thin_telemetry(**overrides) -> SearchTelemetry:
        base = dict(
            eligible_space_size=len(space.entities),
            stage1_retained=len(thin.validated.retained) if thin.validated else 0,
            attempted_violations=thin.attempted_violations,
            all_entries_dropped_occurrences=thin.all_entries_dropped_occurrences,
            retry_attempts=thin.retry_attempts,
            budget_records=tuple(budget_records),
            watched=watched,
        )
        return SearchTelemetry(**{**base, **overrides})

    # 5. Thin's own post-call budget terminals (D9.3 / D7). Terminal at thin:
    #    F1's proceed-to-fat applies only to retry exhaustion, never to a budget
    #    side (codex P1 — that removes a branch rather than adding one).
    if thin.outcome == "output_truncation":
        return finish(
            "thin_output_truncation",
            status="budget_exceeded",
            execution="thin_attempted",
            telemetry=thin_telemetry(),
            stages=thin.records,
        )
    if thin.outcome == "input_estimation_miss":
        return finish(
            "thin_input_estimation_miss",
            status="budget_exceeded",
            execution="thin_attempted",
            telemetry=thin_telemetry(watched=watched + ("budget_estimation_miss",)),
            stages=thin.records,
        )

    # 6. Stage-2 membership. `N <= M` is retain-all **regardless of the thin
    #    response** (codex #3): a recall-oriented selector can omit an identity by
    #    judgment, and validation cannot distinguish omission from judgment, so
    #    the guarantee is enforced controller-side rather than requested in a
    #    prompt. It is also what makes the F1 path work without thin's output.
    #
    #    **D-123-B qualifies it:** retain-all means every eligible identity is
    #    OFFERED to the fill, not that every one is sent. The budget can still
    #    decline the tail — step 7.
    if thin.outcome == "exhausted":
        return finish(
            "thin_exhausted",
            status="selector_failure",
            execution="thin_attempted",
            telemetry=thin_telemetry(selector_failure_class=thin.failure_class),
            stages=thin.records,
        )

    retained = set(thin.validated.retained) if thin.validated else set()
    candidates = tuple(entity for entity in space.entities if entity.slug in retained)
    if not candidates:
        # D3 — no fat call. `completed` with the watched class, so the KPI
        # series can tell it apart from an honest empty selection.
        return finish(
            "thin_retained_zero",
            status="completed",
            execution="thin_attempted",
            telemetry=thin_telemetry(watched=watched + ("thin_retained_zero",)),
            stages=thin.records,
        )

    # 7. Fat evidence + the fill (D-123-B). Bodies are read HERE — inside search,
    #    never by the caller (§1.1) — a missing body degrades the entity to
    #    title-only rather than dropping it, and a present body is delivered
    #    WHOLE (D-123-C).
    #
    #    Entities are projected in THIN'S RANK order and accumulated until the
    #    next one would exceed the 0.8 budget, so **a request that does not fit is
    #    never constructed**. This replaced `M x per-entity ceiling` as fat's
    #    boundedness argument and is stronger than it: the old guarantee held only
    #    while the ceiling held, and the ceiling held by corrupting evidence.
    #
    #    Rank decides MEMBERSHIP; §3.4 governs PRESENTATION, and the pool is
    #    presented in manifest order below — so extending the cut from "top M" to
    #    "top K that fit" reuses the mechanism §3.4 already permits rather than
    #    amending it. This is also thin's `BEST FIRST` earning a second consumer
    #    beyond the concordance diagnostic: it now decides who survives a binding
    #    budget.
    rank = (
        {slug: i for i, slug in enumerate(thin.validated.retained)}
        if thin.validated
        else {}
    )
    fill_order = sorted(candidates, key=lambda entity: rank.get(entity.slug, len(rank)))

    def rendered_request_bytes(evidence: str) -> int:
        messages = render_fat_messages(
            evidence=evidence,
            query=request.query.text,
            max_results=request.max_results,
        )
        return len(messages.system.encode()) + len(messages.user.encode())

    allowance = budget.fat_input_byte_allowance(selector)
    overhead = rendered_request_bytes("")
    accepted: list[projection.ProjectedEntity] = []
    used = overhead
    declined_cost = 0
    for entity in fill_order:
        candidate = projection.project_entity(entity, body_reader=body_reader)
        cost = projection.stream_contribution_bytes(candidate)
        if used + cost > allowance:
            declined_cost = cost
            break
        accepted.append(candidate)
        used += cost

    # Presentation order: manifest, never thin's (spec §3.4).
    by_slug = {entity.entity.slug: entity for entity in accepted}
    projected = tuple(by_slug[e.slug] for e in space.entities if e.slug in by_slug)
    stage2 = tuple(entity.entity for entity in projected)
    title_only = sum(1 for entity in projected if entity.body is None)
    hydrated = len(projected) - title_only

    def fat_telemetry(**overrides) -> SearchTelemetry:
        base = dict(
            stage2_pool_size=len(projected),
            stage2_budget_bound=len(projected) < len(fill_order),
            stage2_hydrated=hydrated,
            stage2_title_only=title_only,
        )
        return thin_telemetry(**{**base, **overrides})

    # 8. The narrowed pre-flight terminal (D6, narrowed by D-123-B / §7.1). Under
    #    fill-to-budget this can fire for exactly one reason: **not even one
    #    entity fits.** Evidence status stays `not_applicable` and `body_coverage`
    #    stays `None` even though a body was just read — the ratified contract
    #    distinguishes this terminal from the post-call one by whether the pool
    #    was PRESENTED, and here it never was.
    if not projected:
        verdict = budget.preflight(
            "fat", rendered_bytes=overhead + declined_cost, spec=selector
        )
        budget_records.append(_budget_record(verdict, selector))
        return finish(
            "fat_preflight_budget",
            status="budget_exceeded",
            execution="thin_attempted",
            telemetry=fat_telemetry(),
            stages=thin.records,
        )

    fat_evidence = {
        entity.entity.slug: (
            TITLE_ONLY_MARKER if entity.body is None else entity.body
        )
        for entity in projected
    }
    fat_messages = render_fat_messages(
        evidence="\n".join(projection.render_fat_block(entity) for entity in projected),
        query=request.query.text,
        max_results=request.max_results,
    )
    # The fill already bounded this; the pre-flight re-measures the true rendering
    # and is the authority on the record. `fits` is True by construction here —
    # asserted in `test_budget.py`, because a pool that fit its own fill but
    # failed its own pre-flight would break the one property this design promises.
    fat_verdict = budget.preflight(
        "fat",
        rendered_bytes=len(fat_messages.system.encode()) + len(fat_messages.user.encode()),
        spec=selector,
    )
    budget_records.append(_budget_record(fat_verdict, selector))

    # ---- stage 2 ------------------------------------------------------------
    fat = stage_call(
        "fat",
        messages=fat_messages,
        evidence=fat_evidence,
        spec=selector,
        call=call,
        validate=lambda raw: validate_response(
            raw,
            space=stage2,
            expressions=request.query.expressions,
            max_results=request.max_results,
        ),
        verdict=fat_verdict,
    )
    if fat.budget_record is not None:
        budget_records.append(fat.budget_record)

    stages = thin.records + fat.records
    execution: Execution = "two_stage_attempted"
    evidence_status: EvidenceStatus = "complete" if title_only == 0 else "partial"
    body_coverage = hydrated / len(projected)

    def both_telemetry(**overrides) -> SearchTelemetry:
        base = dict(
            attempted_violations=thin.attempted_violations + fat.attempted_violations,
            all_entries_dropped_occurrences=(
                thin.all_entries_dropped_occurrences + fat.all_entries_dropped_occurrences
            ),
            retry_attempts=thin.retry_attempts + fat.retry_attempts,
            budget_records=tuple(budget_records),
            # Fat's, summed over its attempts — and set on EVERY fat-executed
            # terminal, not only the completed one. A stage that exhausted its
            # retries on `all_entries_dropped` did return entries, and reporting
            # 0/`None` there would enter the §8.4 per-model series as "no data"
            # for a selector that hallucinated its whole answer twice.
            returned_entries=fat.returned_entries,
            valid_entry_yield=fat.valid_entry_yield,
        )
        return fat_telemetry(**{**base, **overrides})

    if fat.outcome == "output_truncation":
        return finish(
            "fat_output_truncation",
            status="budget_exceeded",
            execution=execution,
            telemetry=both_telemetry(),
            evidence_status=evidence_status,
            body_coverage=body_coverage,
            stages=stages,
        )
    if fat.outcome == "input_estimation_miss":
        return finish(
            "fat_input_estimation_miss",
            status="budget_exceeded",
            execution=execution,
            telemetry=both_telemetry(
                watched=watched + ("budget_estimation_miss",)
            ),
            stages=stages,
        )
    if fat.outcome == "exhausted":
        return finish(
            "fat_exhausted",
            status="selector_failure",
            execution=execution,
            telemetry=both_telemetry(selector_failure_class=fat.failure_class),
            stages=stages,
        )

    # 9. The ordinary path. Expression accounting is the CONTROLLER's: the
    #    selector's advisory `unresolved` is an input, and where the two disagree
    #    the controller wins and the disagreement is counted (§2.3).
    validated = fat.validated
    accounting = resolve_accounting(
        validated,
        expressions=request.query.expressions,
        max_results=request.max_results,
    )
    return finish(
        "completed",
        status="completed",
        execution=execution,
        hits=validated.hits,
        unresolved=accounting.unresolved_expressions,
        telemetry=both_telemetry(
            unattributed_hit_count=accounting.unattributed_hit_count,
            concordance=_concordance(thin, validated),
        ),
        evidence_status=evidence_status,
        body_coverage=body_coverage,
        stages=stages,
    )


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


#: Joseph's [1] — the "does fat earn its cost" watched series (§8.3). Fat's top
#: 10 measured against thin's ranked top 20.
_FAT_TOP = 10
_THIN_TOP = 20


def _concordance(thin: StageOutcome, fat: ValidatedResponse) -> float | None:
    """`len(fat_top10 ∩ thin_top20) / len(fat_top10)`, `None` where the ratio has
    no meaning.

    Three null cases, and the third is the one worth stating: **no fat stage ran**
    and **fat produced no validated hits** are the ratified two (codex #12), and
    **thin produced no validated retention at all** is the F1 path — thin
    exhausted its attempts, so there is no ranked list to compare against and a
    computed 0.0 would report "fat and thin agreed on nothing" about a comparison
    that never happened.

    A thin stage that *ran* and honestly retained nothing is NOT that case: the
    ranked list exists and is empty, so 0.0 is a real measurement — fat found
    things thin did not. The distinction is `thin.validated is None` versus
    `thin.validated.retained == ()`, which is exactly the distinction
    `validate_thin_response` exists to preserve.
    """
    if thin.validated is None or not fat.hits:
        return None
    top_fat = [hit.slug for hit in fat.hits[:_FAT_TOP]]
    top_thin = set(thin.validated.retained[:_THIN_TOP])
    return len([slug for slug in top_fat if slug in top_thin]) / len(top_fat)


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
    """Carry the built audit onto the result — whole (D-123-H).

    It used to carry only `search_snapshot_hash`, the one part with a ratified
    home on the result, "without inventing a delivery surface P2.4 has yet to
    decide". P3a is that decision (Joseph, 2026-08-02): the receipt rides back on
    the result, and the caller writes whatever log it wants. Search still does no
    I/O of its own.

    The hash stays where it is as well. It is ratified onto `SearchTelemetry` and
    is the field the KPI series reads; making callers reach through `audit` for it
    would move a ratified field for no gain.
    """
    return replace(
        result,
        audit=audit,
        telemetry=replace(
            result.telemetry, search_snapshot_hash=audit.search_snapshot_hash
        ),
    )


__all__ = ["graph_search"]
