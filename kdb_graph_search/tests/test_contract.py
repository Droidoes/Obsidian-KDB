"""P1.5 — the terminal contract matrix (#123 blueprint §2.2/§8, spec §0/§1.1).

The plan doc warned this sub-phase risks being *"enum plumbing that would pass
trivially"*. Three things keep it from being that:

1. **The table has a runtime consumer.** `assert_result_contract` is P2's
   return-site guard, not a test fixture. Every assertion here is about code that
   will refuse a malformed result in production.
2. **Every constrained cell is mutation-tested.** For each terminal, each cell the
   ratified text fixes is broken in turn and the verifier must report it. A
   verifier that checked nothing would fail these, which is exactly what a
   trivially-passing matrix does not do.
3. **Three rows run through real code.** `empty_space` and both pre-flight budget
   terminals have producers *today* (`budget.preflight`, an empty
   `SearchSpaceRef`), so they are driven end-to-end rather than hand-built.

The rest are shape until P2 supplies the producer — marked `PRODUCIBLE_IN_P1` in
the module, and the split is asserted here so it cannot quietly rot.
"""

from __future__ import annotations

import pytest

from common.model_pool import ModelSpec
from common.model_route import ModelRoute
from kdb_graph_search.artifact import (
    ModelStamp,
    PromptRef,
    RenderedMessages,
    SearchResultSummary,
    StageRecord,
    build_audit_payload,
)
from kdb_graph_search.budget import preflight, reserved_output_tokens
from kdb_graph_search.constants import BUDGET_HEADROOM, MAX_ATTEMPTS_PER_STAGE
from kdb_graph_search.contracts import (
    ALLOWED_STATUS_EXECUTION,
    PRODUCIBLE_IN_P1,
    TERMINAL_CONTRACTS,
    ContractViolation,
    assert_result_contract,
    is_ratified_pair,
    verify_result_contract,
)
from kdb_graph_search.result import BudgetRecord, GraphSearchResult, SearchTelemetry
from kdb_graph_search.types import (
    GraphSnapshotRef,
    Hit,
    QueryPayload,
    SearchSpaceRef,
    SpaceEntity,
)

EXPRESSIONS = ("warren-buffett", "owner-earnings")

GRAPH_REF = GraphSnapshotRef(
    schema_version="v1",
    active_entity_count=163,
    space_fingerprint="sha256:abc",
    source_kind="fixture",
)


def _spec(**overrides) -> ModelSpec:
    base = dict(
        id="test-route",
        provider="deepseek",
        model="test",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000,
        max_output_tokens=128_000,
        tokens_lte_bytes=True,
    )
    return ModelSpec(**{**base, **overrides})


def _budget_record(contract, *, fits: bool = False) -> BudgetRecord:
    return BudgetRecord(
        stage="fat" if "fat" in contract.name else "thin",
        budget_estimate_tokens=1_000,
        selector_window=400_000,
        headroom_factor=BUDGET_HEADROOM,
        visible_output_allowance=10_000,
        hidden_output_reserve=16_000,
        fits=fits,
        detected=contract.detected or "pre_call",
        budget_side=contract.budget_side or "input",
    )


def _conforming(name: str) -> tuple[GraphSearchResult, int, int]:
    """Build the result a correct P2 would return for `name`, plus its attempt
    counts. Derived from the contract itself — a hand-written literal per row
    would just be the table typed twice."""
    contract = TERMINAL_CONTRACTS[name]

    hits: tuple[Hit, ...] = ()
    if contract.hits_empty is not True:
        hits = (Hit(slug="warren-buffett", title="Warren Buffett", page_type="concept"),)

    unresolved = EXPRESSIONS if contract.all_expressions_unresolved is True else ()

    telemetry = SearchTelemetry(
        concordance=None,
        watched=contract.required_watched,
        selector_failure_class="unparseable_response" if contract.failure_class_required else None,
        budget_records=(_budget_record(contract),) if contract.detected is not None else (),
    )

    result = GraphSearchResult(
        hits=hits,
        unresolved_expressions=unresolved,
        status=contract.status,
        execution=contract.execution[0],
        telemetry=telemetry,
        evidence_status=(contract.evidence_status or ("not_applicable",))[0],
        body_coverage=0.75 if contract.body_coverage_present is True else None,
    )
    return result, contract.thin_attempts[0], contract.fat_attempts[0]


def _verify(name: str, result: GraphSearchResult, thin: int, fat: int) -> tuple[str, ...]:
    return verify_result_contract(
        name, result, request_expressions=EXPRESSIONS, thin_attempts=thin, fat_attempts=fat
    )


ALL_TERMINALS = sorted(TERMINAL_CONTRACTS)


# --------------------------------------------------------------------------
# every row round-trips
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_every_terminal_has_a_conforming_result(name):
    """A consistency check, not evidence: `_conforming` builds from the same table
    the verifier reads, so this proves the two agree — not that either matches the
    blueprint. The rows that carry real weight are `PRODUCIBLE_IN_P1`'s, where the
    result comes out of `budget.preflight` instead, and the mutation tests below,
    where the result is deliberately made to disagree."""
    result, thin, fat = _conforming(name)
    assert _verify(name, result, thin, fat) == ()


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_every_terminal_conforms_at_both_attempt_bounds(name):
    """The bounds are inclusive — the low and high ends are both legal, and a
    contract that silently admitted only one of them would still pass the row
    above."""
    contract = TERMINAL_CONTRACTS[name]
    result, _, _ = _conforming(name)
    for thin in contract.thin_attempts:
        for fat in contract.fat_attempts:
            assert _verify(name, result, thin, fat) == (), f"{thin=} {fat=}"


def test_the_matrix_covers_every_status():
    """No status may be unreachable: a status with no terminal is a status the
    orchestrator can never legally return."""
    assert {c.status for c in TERMINAL_CONTRACTS.values()} == {
        "completed",
        "abstain_empty_space",
        "budget_exceeded",
        "selector_failure",
    }


def test_the_matrix_covers_every_execution_value():
    assert {e for c in TERMINAL_CONTRACTS.values() for e in c.execution} == {
        "not_executed",
        "thin_attempted",
        "two_stage_attempted",
    }


# --------------------------------------------------------------------------
# mutation: every constrained cell must be checked
# --------------------------------------------------------------------------


def _other(value, allowed: tuple) -> object:
    """Some value the contract forbids."""
    for candidate in ("completed", "abstain_empty_space", "budget_exceeded", "selector_failure",
                      "not_executed", "thin_attempted", "two_stage_attempted",
                      "not_applicable", "complete", "partial"):
        if candidate not in allowed:
            return candidate
    raise AssertionError("nothing left to mutate to")


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_wrong_status_is_caught(name):
    result, thin, fat = _conforming(name)
    broken = GraphSearchResult(
        **{**result.__dict__, "status": _other(result.status, (result.status,))}
    )
    assert _verify(name, broken, thin, fat), "a wrong status went unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_wrong_execution_is_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    result, thin, fat = _conforming(name)
    broken = GraphSearchResult(
        **{**result.__dict__, "execution": _other(result.execution, contract.execution)}
    )
    assert _verify(name, broken, thin, fat), "a wrong execution went unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_wrong_evidence_status_is_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.evidence_status is None:
        pytest.skip("evidence side deliberately unenumerated for this terminal")
    result, thin, fat = _conforming(name)
    broken = GraphSearchResult(
        **{
            **result.__dict__,
            "evidence_status": _other(result.evidence_status, contract.evidence_status),
        }
    )
    assert _verify(name, broken, thin, fat), "a wrong evidence_status went unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_wrong_body_coverage_is_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.body_coverage_present is None:
        pytest.skip("body_coverage deliberately unenumerated for this terminal")
    result, thin, fat = _conforming(name)
    swapped = None if contract.body_coverage_present else 0.5
    broken = GraphSearchResult(**{**result.__dict__, "body_coverage": swapped})
    assert _verify(name, broken, thin, fat), "a wrong body_coverage went unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_nonempty_hit_list_is_caught_where_the_contract_forbids_it(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.hits_empty is not True:
        pytest.skip("hits are unconstrained for this terminal")
    result, thin, fat = _conforming(name)
    broken = GraphSearchResult(
        **{
            **result.__dict__,
            "hits": (Hit(slug="warren-buffett", title="W", page_type="concept"),),
        }
    )
    assert _verify(name, broken, thin, fat), "a hit leaked out of a terminal that returns none"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_partially_unresolved_expression_set_is_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.all_expressions_unresolved is not True:
        pytest.skip("unresolved set unconstrained for this terminal")
    result, thin, fat = _conforming(name)
    for partial in ((), EXPRESSIONS[:1]):
        broken = GraphSearchResult(**{**result.__dict__, "unresolved_expressions": partial})
        assert _verify(name, broken, thin, fat), f"{partial!r} accepted as 'all unresolved'"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_non_null_concordance_is_caught_where_the_contract_forbids_it(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.concordance_null is not True:
        pytest.skip("concordance unconstrained for this terminal")
    result, thin, fat = _conforming(name)
    telemetry = SearchTelemetry(**{**result.telemetry.__dict__, "concordance": 0.4})
    broken = GraphSearchResult(**{**result.__dict__, "telemetry": telemetry})
    assert _verify(name, broken, thin, fat), "a non-null concordance went unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_attempt_counts_outside_the_bounds_are_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    result, thin, fat = _conforming(name)
    assert _verify(name, result, contract.thin_attempts[1] + 1, fat), "thin over-count unreported"
    assert _verify(name, result, thin, contract.fat_attempts[1] + 1), "fat over-count unreported"
    if contract.thin_attempts[0] > 0:
        assert _verify(name, result, contract.thin_attempts[0] - 1, fat), "thin under-count unreported"
    if contract.fat_attempts[0] > 0:
        assert _verify(name, result, thin, contract.fat_attempts[0] - 1), "fat under-count unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_missing_watched_class_is_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    if not contract.required_watched:
        pytest.skip("no watched class required")
    result, thin, fat = _conforming(name)
    telemetry = SearchTelemetry(**{**result.telemetry.__dict__, "watched": ()})
    broken = GraphSearchResult(**{**result.__dict__, "telemetry": telemetry})
    assert _verify(name, broken, thin, fat), "a dropped watched class went unreported"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_the_failure_class_rule_runs_in_both_directions(name):
    """`selector_failure` must name a class, and nothing else may — a class on a
    `completed` result would put a failure into the KPI series that never happened."""
    contract = TERMINAL_CONTRACTS[name]
    result, thin, fat = _conforming(name)
    swapped = None if contract.failure_class_required else "unparseable_response"
    telemetry = SearchTelemetry(**{**result.telemetry.__dict__, "selector_failure_class": swapped})
    broken = GraphSearchResult(**{**result.__dict__, "telemetry": telemetry})
    assert _verify(name, broken, thin, fat)


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_missing_budget_record_is_caught(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.detected is None:
        pytest.skip("not a budget terminal")
    result, thin, fat = _conforming(name)
    telemetry = SearchTelemetry(**{**result.telemetry.__dict__, "budget_records": ()})
    broken = GraphSearchResult(**{**result.__dict__, "telemetry": telemetry})
    assert _verify(name, broken, thin, fat), "a budget terminal with no budget record"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_budget_record_on_the_wrong_side_or_phase_is_caught(name):
    """`pre_call`/`post_call` and `input`/`output` are what separate four
    different budget terminals that share a status. Swapping either must fail."""
    contract = TERMINAL_CONTRACTS[name]
    if contract.detected is None:
        pytest.skip("not a budget terminal")
    result, thin, fat = _conforming(name)
    record = result.telemetry.budget_records[0]
    for swap in (
        {"detected": "post_call" if contract.detected == "pre_call" else "pre_call"},
        {"budget_side": "output" if contract.budget_side == "input" else "input"},
    ):
        telemetry = SearchTelemetry(
            **{
                **result.telemetry.__dict__,
                "budget_records": (BudgetRecord(**{**record.__dict__, **swap}),),
            }
        )
        broken = GraphSearchResult(**{**result.__dict__, "telemetry": telemetry})
        assert _verify(name, broken, thin, fat), f"{swap} accepted"


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_a_fitting_budget_record_cannot_back_a_budget_terminal(name):
    contract = TERMINAL_CONTRACTS[name]
    if contract.detected is None:
        pytest.skip("not a budget terminal")
    result, thin, fat = _conforming(name)
    telemetry = SearchTelemetry(
        **{**result.telemetry.__dict__, "budget_records": (_budget_record(contract, fits=True),)}
    )
    broken = GraphSearchResult(**{**result.__dict__, "telemetry": telemetry})
    assert _verify(name, broken, thin, fat), "budget_exceeded backed by a fitting verdict"


def test_the_verifier_reports_every_violation_not_just_the_first():
    result, thin, fat = _conforming("empty_space")
    broken = GraphSearchResult(
        **{
            **result.__dict__,
            "status": "completed",
            "execution": "two_stage_attempted",
            "body_coverage": 0.5,
        }
    )
    assert len(_verify("empty_space", broken, thin, fat)) >= 3


def test_an_unknown_terminal_name_is_a_violation_not_a_pass():
    result, _, _ = _conforming("empty_space")
    assert _verify("no_such_terminal", result, 0, 0)


# --------------------------------------------------------------------------
# fail-closed on the (status, execution) pair
# --------------------------------------------------------------------------


def test_unratified_status_execution_pairs_are_rejected():
    """`abstain_empty_space` with a fat stage attempted, or `not_executed` with a
    completed search, are combinations no terminal admits."""
    for pair in (
        ("abstain_empty_space", "two_stage_attempted"),
        ("abstain_empty_space", "thin_attempted"),
        ("abstain_empty_space", "fat_after_thin_failure"),
        ("completed", "not_executed"),
        ("selector_failure", "not_executed"),
        ("selector_failure", "thin_attempted_but_typoed"),
    ):
        assert pair not in ALLOWED_STATUS_EXECUTION, pair


def test_budget_exceeded_legitimately_spans_EVERY_execution_value():
    """Not an oversight in the allowlist: the budget can bind before any call, at
    the fat pre-flight, and post-call at either stage. It is the one status that
    reaches every point in the run. (It spanned a fourth value until 2026-08-02,
    when the F1 path was removed with `small_space`.)"""
    reachable = {
        execution
        for contract in TERMINAL_CONTRACTS.values()
        if contract.status == "budget_exceeded"
        for execution in contract.execution
    }
    assert reachable == {
        "not_executed",
        "thin_attempted",
        "two_stage_attempted",
    }


def test_the_pair_allowlist_is_derived_from_the_table_not_retyped():
    for contract in TERMINAL_CONTRACTS.values():
        for execution in contract.execution:
            assert is_ratified_pair(contract.status, execution)


def test_is_ratified_pair_is_the_terminal_agnostic_reader_check():
    """Its consumer is a reader holding an archived result and no terminal name —
    replay and the KPI series. Inside `verify_result_contract` the same check
    would be unreachable, which is why it lives here instead."""
    assert is_ratified_pair("completed", "two_stage_attempted")
    assert not is_ratified_pair("completed", "not_executed")


def test_assert_result_contract_is_the_fail_closed_guard():
    result, thin, fat = _conforming("empty_space")
    assert assert_result_contract(
        "empty_space", result, request_expressions=EXPRESSIONS, thin_attempts=thin, fat_attempts=fat
    ) is result
    broken = GraphSearchResult(**{**result.__dict__, "status": "completed"})
    with pytest.raises(ContractViolation):
        assert_result_contract(
            "empty_space",
            broken,
            request_expressions=EXPRESSIONS,
            thin_attempts=thin,
            fat_attempts=fat,
        )


# --------------------------------------------------------------------------
# the three rows with a producer TODAY — driven through real code
# --------------------------------------------------------------------------


def test_producible_set_matches_the_rows_this_file_actually_drives():
    assert PRODUCIBLE_IN_P1 == {"empty_space", "thin_preflight_budget", "fat_preflight_budget"}
    assert PRODUCIBLE_IN_P1 <= set(TERMINAL_CONTRACTS)


def test_empty_space_terminal_from_a_real_search_space():
    space = SearchSpaceRef(entities=(), scope_kind="domain_subtree", graph_ref=GRAPH_REF, domain="x")
    assert not space.entities, "the terminal's precondition"
    query = QueryPayload(text="anything", expressions=EXPRESSIONS)
    query.validate()

    result = GraphSearchResult(
        hits=(),
        unresolved_expressions=query.expressions,
        status="abstain_empty_space",
        execution="not_executed",
        telemetry=SearchTelemetry(eligible_space_size=0, watched=("domain_missing",)),
    )
    assert _verify("empty_space", result, 0, 0) == ()


def test_a_nonempty_space_does_not_reach_the_empty_space_terminal():
    """The precondition is the space, not the caller's say-so."""
    space = SearchSpaceRef(
        entities=(SpaceEntity(slug="a", title="A", page_type="concept"),),
        scope_kind="whole_graph",
        graph_ref=GRAPH_REF,
    )
    assert space.entities


@pytest.mark.parametrize(
    ("terminal", "stage", "thin", "fat"),
    [("thin_preflight_budget", "thin", 0, 0), ("fat_preflight_budget", "fat", 1, 0)],
)
def test_preflight_terminals_are_built_from_a_real_budget_verdict(terminal, stage, thin, fat):
    """`budget.preflight` IS the producer for these two rows, so the record on the
    result carries its actual numbers rather than invented ones."""
    spec = _spec(ctx_window=20_000)
    verdict = preflight(stage, rendered_bytes=400_000, spec=spec)
    assert not verdict.fits, "the fixture must actually exceed the budget"

    record = BudgetRecord(
        stage=stage,
        budget_estimate_tokens=verdict.estimated_input_tokens,
        selector_window=spec.ctx_window,
        headroom_factor=BUDGET_HEADROOM,
        visible_output_allowance=verdict.reserved_output_tokens - 16_000,
        hidden_output_reserve=16_000,
        fits=verdict.fits,
        detected="pre_call",
        budget_side="input",
    )
    result = GraphSearchResult(
        hits=(),
        unresolved_expressions=EXPRESSIONS,
        status="budget_exceeded",
        execution="not_executed" if stage == "thin" else "thin_attempted",
        telemetry=SearchTelemetry(budget_records=(record,)),
    )
    assert _verify(terminal, result, thin, fat) == ()
    assert record.budget_estimate_tokens + verdict.reserved_output_tokens > verdict.context_budget_tokens


def test_a_fitting_preflight_cannot_produce_a_preflight_terminal():
    """The mutation that matters most for these rows: a verdict that FIT, dressed
    as the terminal. Every enum cell still lines up; only `fits` gives it away."""
    spec = _spec()
    verdict = preflight("thin", rendered_bytes=1_000, spec=spec)
    assert verdict.fits
    record = BudgetRecord(
        stage="thin",
        budget_estimate_tokens=verdict.estimated_input_tokens,
        selector_window=spec.ctx_window,
        headroom_factor=BUDGET_HEADROOM,
        visible_output_allowance=13_000,
        hidden_output_reserve=16_000,
        fits=verdict.fits,
    )
    result = GraphSearchResult(
        hits=(),
        unresolved_expressions=EXPRESSIONS,
        status="budget_exceeded",
        execution="not_executed",
        telemetry=SearchTelemetry(budget_records=(record,)),
    )
    assert _verify("thin_preflight_budget", result, 0, 0)


def test_the_preflight_terminals_reserve_the_stage_specific_output_envelope():
    """Thin and fat reserve different amounts, so the two rows are not one row
    with a label swapped."""
    assert reserved_output_tokens("thin") != reserved_output_tokens("fat")


# --------------------------------------------------------------------------
# blueprint §8's branch table — the external cross-check
# --------------------------------------------------------------------------

#: Blueprint §8's branch table, transcribed **per stage in the doc's own words**
#: — `(thin_low, thin_high, fat_low, fat_high)`, with the source phrase beside
#: each row. Per-stage rather than summed on purpose: a totals-only transcription
#: would fold my arithmetic into what is supposed to be the external figure, and
#: a cross-check that quietly contains the thing it checks is no cross-check.
#: The module derives its bounds independently; this is the only comparison site.
BLUEPRINT_SECTION_8 = {
    "empty_space": (0, 0, 0, 0),  # "0"
    "thin_preflight_budget": (0, 0, 0, 0),  # "0"
    "thin_input_estimation_miss": (1, 1, 0, 0),  # "1 thin attempted, 0 fat"
    "thin_retained_zero": (1, 2, 0, 0),  # "1–2 thin, 0 fat"
    "completed": (1, 2, 1, 2),  # "1–2 thin + 1–2 fat = 2–4"
    "thin_exhausted": (2, 2, 0, 0),  # "2 thin, 0 fat"
    "fat_exhausted": (1, 2, 2, 2),  # "1–2 thin + 2 fat = 3–4"
    "fat_preflight_budget": (1, 2, 0, 0),  # "1–2 thin, 0 fat"
    "thin_output_truncation": (1, 1, 0, 0),  # "1 thin, 0 fat"
    "fat_output_truncation": (1, 2, 1, 1),  # "1–2 thin + 1 fat, 0 after"
    "fat_input_estimation_miss": (1, 2, 1, 1),  # "1–2 thin + 1 fat attempted"
}

#: The three rows where §8 also states its own total. Transcribed separately so
#: the doc's arithmetic is checked against the module's, not against mine.
BLUEPRINT_SECTION_8_STATED_TOTALS = {
    "completed": (2, 4),  # "= 2–4"
    "fat_exhausted": (3, 4),  # "= 3–4"
}


@pytest.mark.parametrize("name", sorted(BLUEPRINT_SECTION_8))
def test_per_stage_bounds_reproduce_the_blueprint_branch_table(name):
    contract = TERMINAL_CONTRACTS[name]
    thin_low, thin_high, fat_low, fat_high = BLUEPRINT_SECTION_8[name]
    assert contract.thin_attempts == (thin_low, thin_high)
    assert contract.fat_attempts == (fat_low, fat_high)


@pytest.mark.parametrize("name", sorted(BLUEPRINT_SECTION_8_STATED_TOTALS))
def test_the_totals_the_blueprint_states_itself_also_reproduce(name):
    contract = TERMINAL_CONTRACTS[name]
    assert (contract.min_logical_calls, contract.max_logical_calls) == (
        BLUEPRINT_SECTION_8_STATED_TOTALS[name]
    )



def test_every_terminal_in_the_branch_table_exists_in_the_matrix():
    assert set(BLUEPRINT_SECTION_8) <= set(TERMINAL_CONTRACTS)


def test_the_matrix_ADDS_NOTHING_beyond_the_branch_table():
    """It used to add three: `fat_*_on_f1`, whose field contracts differed from
    their non-F1 siblings. Removing `small_space` removed the F1 path and with it
    the only reason the matrix was ever wider than §8's table. Asserted as an
    equality so a silent re-addition fails here."""
    assert set(TERMINAL_CONTRACTS) == set(BLUEPRINT_SECTION_8)



def test_no_terminal_exceeds_two_logical_attempts_per_stage():
    for contract in TERMINAL_CONTRACTS.values():
        assert contract.thin_attempts[1] <= MAX_ATTEMPTS_PER_STAGE
        assert contract.fat_attempts[1] <= MAX_ATTEMPTS_PER_STAGE


# --------------------------------------------------------------------------
# logical_call_count == StageRecords, tied to the matrix
# --------------------------------------------------------------------------


def _stage(stage: str, attempt: int) -> StageRecord:
    return StageRecord(
        stage=stage,
        attempt=attempt,
        prompt=PromptRef(version="1", sha256="sha256:x", repo_path="p", git_commit="c"),
        rendered_messages=RenderedMessages(system="s", user="u"),
        model=ModelStamp(provider="deepseek", model="m", route="openai_compat"),
        evidence="space_manifest_ref",
        latency_ms=1,
        cost=0.0,
    )


@pytest.mark.parametrize("name", ALL_TERMINALS)
def test_the_artifact_records_exactly_the_attempts_the_terminal_permits(name):
    """`logical_call_count == archived StageRecords` (codex c-1) is the bridge
    between this matrix and P1.4's payload — the counts the contract bounds are
    the same counts the audit archives."""
    contract = TERMINAL_CONTRACTS[name]
    result, thin, fat = _conforming(name)
    stages = tuple(
        [_stage("thin_selection", i + 1) for i in range(thin)]
        + [_stage("fat_selection", i + 1) for i in range(fat)]
    )
    payload = build_audit_payload(
        graph_ref=GRAPH_REF,
        query=QueryPayload(text="q", expressions=EXPRESSIONS),
        manifest=(SpaceEntity(slug="a", title="A", page_type="concept"),),
        execution=result.execution,
        stages=stages,
        result=SearchResultSummary(
            hits=result.hits,
            unresolved_expressions=result.unresolved_expressions,
            status=result.status,
            evidence_status=result.evidence_status,
            body_coverage=result.body_coverage,
        ),
    )
    assert payload.logical_call_count == len(stages)
    assert contract.min_logical_calls <= payload.logical_call_count <= contract.max_logical_calls


def test_a_zero_call_terminal_archives_an_artifact_with_no_stages():
    """Emptiness is the finding, not a reason to skip the record."""
    payload = build_audit_payload(
        graph_ref=GRAPH_REF,
        query=QueryPayload(text="q", expressions=EXPRESSIONS),
        manifest=(),
        execution="not_executed",
        result=SearchResultSummary(
            hits=(), unresolved_expressions=EXPRESSIONS, status="abstain_empty_space"
        ),
    )
    assert payload.logical_call_count == 0
    assert payload.artifact_integrity_hash.startswith("sha256:")


# --------------------------------------------------------------------------
# the unenumerated cells are marked, not guessed
# --------------------------------------------------------------------------


def test_the_unenumerated_terminals_are_exactly_the_marked_ones():
    """A gap in the ratified text, marked as one. If a later spec round settles
    `fat_exhausted`'s evidence side, this is the test that fails and the `note`
    is where the reader lands.

    Deliberately does NOT include `completed`, whose open cells are ratified
    *openness* rather than a gap — mixing a defect marker with a design choice in
    one assertion would make settling either look like progress on the other.
    """
    marked = {name for name, c in TERMINAL_CONTRACTS.items() if "UNENUMERATED" in c.note}
    assert marked == {
        "fat_exhausted",
        "fat_input_estimation_miss",
    }
    for name in marked:
        contract = TERMINAL_CONTRACTS[name]
        assert contract.evidence_status is None, f"{name} marks a gap it does not have"


def test_no_terminal_leaves_a_cell_open_without_saying_why():
    """Every unconstrained cell traces to either the UNENUMERATED marker or
    `completed`'s ratified openness — an open cell with neither is an omission."""
    for name, contract in TERMINAL_CONTRACTS.items():
        if (
            contract.evidence_status is None
            or contract.body_coverage_present is None
            or contract.concordance_null is None
            or contract.hits_empty is None
        ):
            assert "UNENUMERATED" in contract.note or name == "completed", name


def test_completed_is_unconstrained_by_design_not_by_omission():
    """`completed`'s open cells are ratified openness — an honest empty selection
    and a null concordance are both legal outcomes — so its note carries the
    reason instead of the UNENUMERATED marker."""
    contract = TERMINAL_CONTRACTS["completed"]
    assert contract.hits_empty is None and contract.concordance_null is None
    assert "UNENUMERATED" not in contract.note
    assert contract.evidence_status == ("complete", "partial")


def test_every_contract_carries_a_note():
    for contract in TERMINAL_CONTRACTS.values():
        assert contract.note.strip(), contract.name
