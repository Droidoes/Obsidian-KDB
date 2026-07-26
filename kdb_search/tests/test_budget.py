"""P1.3 — budget estimator + output envelope (#123 spec §7.2, D6/D7/D9).

**Structural only.** Measurement assertions live at the D5 calibration gate at the
end of P2 (H3) — nothing here claims a real bytes-per-token ratio. What is asserted
is arithmetic and contract: the exact serialized maxima, the four envelope
quantities, route preconditions, and the M=100 static guarantee.

The synthetic schema-maximum documents are the executable authority for §7.0a.
They are built mechanically from `WIRE_JSON_SEPARATORS`, `WIRE_INDEX_BASE` and
`MAX_EXPRESSIONS` — never from a byte figure copied out of the blueprint. That
rule exists because §7.0a itself once shipped an integer derived from an unnamed
serializer.
"""

from __future__ import annotations

import json
import math

import pytest

from common.model_pool import ModelSpec, load_pool, resolve_models_json
from common.model_route import ModelRoute
from kdb_search.budget import (
    context_budget,
    estimate_input_tokens,
    exact_max_visible_bytes,
    fat_static_guarantee_tokens,
    fat_worst_case_request_bytes,
    hidden_output_reserve,
    preflight,
    provider_max_tokens,
    reserved_output_tokens,
    resolve_selector_route,
    schema_maximum_fat_document,
    schema_maximum_thin_document,
    visible_output_allowance,
    worst_case_input_tokens,
)
from kdb_search.constants import (
    BUDGET_HEADROOM,
    ESTIMATOR_BYTES_PER_TOKEN,
    EXCERPT_BLOCK_CEILING_BYTES,
    HIDDEN_OUTPUT_RESERVE,
    M,
    MAX_EXPRESSIONS,
    MAX_RESULTS,
    MAX_SLUG_LEN,
    QUERY_BLOCK_CEILING_BYTES,
    SMALLEST_POOL_BUDGET_TOKENS,
    SYSTEM_TEMPLATE_BUDGET_BYTES,
    VISIBLE_OUTPUT_ALLOWANCE_FAT,
    VISIBLE_OUTPUT_ALLOWANCE_THIN,
    WIRE_INDEX_BASE,
    WIRE_JSON_SEPARATORS,
)
from kdb_search.types import InvalidGraphSearchRequest, QueryPayload, SearchConfigError

D4_COHORT = ("gemini-3.6-flash", "gpt-5.4-mini", "deepseek-v4-flash")


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


# --------------------------------------------------------------------------
# §7.0a exact serialized maxima — derived, never copied
# --------------------------------------------------------------------------

def test_the_serializer_is_the_named_constant_not_a_default():
    """`json.dumps`' default separators insert whitespace and inflate every
    figure. The maxima are only reproducible from the named tuple."""
    obj = {"a": [1, 2]}
    assert json.dumps(obj, separators=WIRE_JSON_SEPARATORS) == '{"a":[1,2]}'
    assert json.dumps(obj) != json.dumps(obj, separators=WIRE_JSON_SEPARATORS)


def test_thin_exact_max_is_12314_bytes_and_fits_its_allowance():
    exact = exact_max_visible_bytes("thin")
    assert exact == 12_314, f"thin exact max moved: {exact}"
    assert exact <= VISIBLE_OUTPUT_ALLOWANCE_THIN
    # Under tokens_lte_bytes, bytes bound tokens — no density step anywhere.
    assert exact <= VISIBLE_OUTPUT_ALLOWANCE_THIN, "tokens <= bytes <= allowance"


def test_fat_exact_max_is_8251_bytes_and_fits_its_allowance():
    exact = exact_max_visible_bytes("fat")
    assert exact == 8_251, f"fat exact max moved: {exact}"
    assert exact <= VISIBLE_OUTPUT_ALLOWANCE_FAT


def test_the_thin_document_is_built_from_the_declared_maxima():
    document = json.loads(schema_maximum_thin_document())
    assert len(document["retained"]) == M
    assert {len(slug) for slug in document["retained"]} == {MAX_SLUG_LEN}


def test_the_fat_document_is_built_from_the_declared_maxima_and_zero_based_indices():
    document = json.loads(schema_maximum_fat_document())
    assert len(document["selections"]) == MAX_RESULTS
    assert document["unresolved"] == list(range(WIRE_INDEX_BASE, WIRE_INDEX_BASE + MAX_EXPRESSIONS))
    assert document["selections"][0]["matched"][0] == WIRE_INDEX_BASE == 0
    assert max(document["selections"][0]["matched"]) == MAX_EXPRESSIONS - 1


@pytest.mark.parametrize(
    "expressions,expected,fits",
    [(10, 8_251, True), (20, 9_781, True), (21, 9_934, True), (22, 10_087, False), (50, 14_371, False)],
)
def test_the_fat_maximum_is_a_function_of_max_expressions(expressions, expected, fits):
    """The ratified break-even table (§7.0a, corrected at v0.11). The 10/22 pair is
    the load-bearing one: a fits/exceeds contrast. The superseded `20 => 10,414`
    point would have shipped a test whose two data points BOTH fit — demonstrating
    nothing about the bound it existed to pin."""
    exact = exact_max_visible_bytes("fat", expressions=expressions)
    assert exact == expected, f"{expressions} expressions => {exact}, table says {expected}"
    assert (exact <= VISIBLE_OUTPUT_ALLOWANCE_FAT) is fits


def test_the_break_even_is_22_expressions_not_15():
    """Pins the v0.11 correction itself. The superseded ~15 came from a one-based
    index list under `separators=(",", ": ")`; nothing at 15 exceeds."""
    fitting = [n for n in range(1, 40) if exact_max_visible_bytes("fat", expressions=n) <= VISIBLE_OUTPUT_ALLOWANCE_FAT]
    assert max(fitting) == 21
    assert exact_max_visible_bytes("fat", expressions=22) > VISIBLE_OUTPUT_ALLOWANCE_FAT


def test_max_expressions_stays_far_inside_the_break_even():
    assert MAX_EXPRESSIONS < 22, "the declared bound must sit under the break-even"


# --------------------------------------------------------------------------
# the four envelope quantities, separately (D9 / codex O1)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stage,visible", [("thin", VISIBLE_OUTPUT_ALLOWANCE_THIN), ("fat", VISIBLE_OUTPUT_ALLOWANCE_FAT)])
def test_visible_and_provider_quantities_are_distinct(stage, visible):
    """codex O1: D8's proof bounded only the VISIBLE JSON, while `max_tokens` caps
    the whole completion. Four quantities, separately addressable."""
    assert visible_output_allowance(stage) == visible
    assert hidden_output_reserve() == HIDDEN_OUTPUT_RESERVE
    assert provider_max_tokens(stage) == visible + HIDDEN_OUTPUT_RESERVE
    assert reserved_output_tokens(stage) == provider_max_tokens(stage)
    assert provider_max_tokens(stage) > visible_output_allowance(stage), (
        "the provider cap must exceed the visible allowance, or hidden reasoning "
        "eats the response"
    )


def test_the_provider_totals_are_29000_thin_and_26000_fat():
    assert provider_max_tokens("thin") == 29_000
    assert provider_max_tokens("fat") == 26_000


def test_the_hidden_reserve_is_a_policy_figure_not_derived_from_the_wire():
    """It cannot be a function of the visible maxima — hidden output is
    unenforceable at two of three D4 providers, so no wire bound implies it."""
    assert HIDDEN_OUTPUT_RESERVE not in (
        exact_max_visible_bytes("thin"),
        exact_max_visible_bytes("fat"),
        VISIBLE_OUTPUT_ALLOWANCE_THIN,
        VISIBLE_OUTPUT_ALLOWANCE_FAT,
    )


# --------------------------------------------------------------------------
# route resolution — fail hard, before any work
# --------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", D4_COHORT)
def test_every_d4_candidate_declares_tokens_lte_bytes(model_id):
    """The allowances are proved THROUGH this premise, so every screening
    candidate has to declare it (codex N4)."""
    assert resolve_models_json(model_id).tokens_lte_bytes is True


def test_every_pool_entry_declares_tokens_lte_bytes():
    """Any pool model may be configured as the selector, so a silent `None` is a
    latent typed failure rather than a safe default."""
    undeclared = [e["id"] for e in load_pool() if e.get("tokens_lte_bytes") is not True]
    assert undeclared == [], f"pool entries without the premise: {undeclared}"


@pytest.mark.parametrize("model_id", D4_COHORT)
def test_every_d4_candidate_admits_both_output_envelopes(model_id):
    spec = resolve_models_json(model_id)
    assert resolve_selector_route(spec) is spec
    for stage in ("thin", "fat"):
        assert provider_max_tokens(stage) <= spec.max_output_tokens


@pytest.mark.parametrize("declared", [None, False])
def test_a_route_without_the_premise_fails_typed_at_resolution(declared):
    with pytest.raises(SearchConfigError, match="tokens_lte_bytes"):
        resolve_selector_route(_spec(tokens_lte_bytes=declared))


def test_a_route_without_a_context_window_fails_typed_at_resolution():
    with pytest.raises(SearchConfigError, match="ctx_window"):
        resolve_selector_route(_spec(ctx_window=None))


def test_a_route_whose_output_cap_is_below_the_envelope_fails_typed():
    with pytest.raises(SearchConfigError, match="caps output"):
        resolve_selector_route(_spec(max_output_tokens=1_000))


def test_the_premise_is_not_enforced_at_gate_1():
    """Gate 1 cannot know which entries serve as a selector; failing the whole
    pool over a premise one consumer needs would break every unrelated call."""
    load_pool.cache_clear()
    assert load_pool(), "the pool still loads"
    spec = ModelSpec(
        id="no-premise", provider="deepseek", model="m",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
    )
    assert spec.tokens_lte_bytes is None, "undeclared is representable, not a load error"


# --------------------------------------------------------------------------
# estimation vs the pathological bound — two quantities, never interchangeable
# --------------------------------------------------------------------------

def test_the_estimator_is_one_method_for_both_stages():
    assert estimate_input_tokens(4_000) == 1_000
    assert estimate_input_tokens(4_001) == 1_001, "ceil, never floor"
    assert estimate_input_tokens(0) == 0


def test_the_estimator_and_the_worst_case_bound_are_different_quantities():
    """The estimate is a guard that can under-call; the bound is a proof. The
    static guarantee uses the bound — conflating them would turn a
    by-construction argument into a measurement."""
    assert worst_case_input_tokens(4_000) == 4_000
    assert estimate_input_tokens(4_000) == 4_000 // ESTIMATOR_BYTES_PER_TOKEN
    assert worst_case_input_tokens(4_000) > estimate_input_tokens(4_000)


def test_headroom_is_applied_here_not_by_fits_context():
    spec = _spec(ctx_window=100_000)
    assert context_budget(spec) == math.floor(100_000 * BUDGET_HEADROOM) == 80_000


def test_context_budget_on_a_windowless_route_raises_rather_than_guessing():
    with pytest.raises(SearchConfigError):
        context_budget(_spec(ctx_window=None))


# --------------------------------------------------------------------------
# the pre-flight verdict — zero-spend, at BOTH stages (D6)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stage", ["thin", "fat"])
def test_a_request_over_the_budget_does_not_fit_at_either_stage(stage):
    spec = _spec(ctx_window=100_000)  # budget 80,000
    verdict = preflight(stage, rendered_bytes=4 * 80_000, spec=spec)
    assert verdict.fits is False
    assert verdict.total_reserved_tokens > verdict.context_budget_tokens


@pytest.mark.parametrize("stage", ["thin", "fat"])
def test_a_request_inside_the_budget_fits_at_either_stage(stage):
    spec = _spec(ctx_window=1_000_000)
    verdict = preflight(stage, rendered_bytes=10_000, spec=spec)
    assert verdict.fits is True
    assert verdict.reserved_output_tokens == provider_max_tokens(stage)


@pytest.mark.parametrize("stage", ["thin", "fat"])
def test_the_verdict_binds_exactly_at_the_budget(stage):
    """The bound itself, not a value near it."""
    spec = _spec(ctx_window=100_000)
    budget = context_budget(spec)
    allowed_input = budget - reserved_output_tokens(stage)
    assert preflight(stage, rendered_bytes=allowed_input * ESTIMATOR_BYTES_PER_TOKEN, spec=spec).fits
    assert not preflight(
        stage, rendered_bytes=(allowed_input + 1) * ESTIMATOR_BYTES_PER_TOKEN, spec=spec
    ).fits


def test_the_verdict_reserves_output_and_is_not_input_only():
    """A verdict ignoring reserved output would pass a request that then overruns
    mid-response — the truncation chain D7(iii) exists to prevent."""
    spec = _spec(ctx_window=100_000)
    just_input = context_budget(spec) * ESTIMATOR_BYTES_PER_TOKEN
    assert not preflight("thin", rendered_bytes=just_input, spec=spec).fits


@pytest.mark.parametrize("stage", ["thin", "fat"])
def test_the_verdict_is_deterministic_which_is_why_it_is_never_retried(stage):
    """`budget_exceeded` is not a retry class: the same rendered request fails
    identically, so a retry can only spend time."""
    spec = _spec(ctx_window=100_000)
    first = preflight(stage, rendered_bytes=999_999, spec=spec)
    second = preflight(stage, rendered_bytes=999_999, spec=spec)
    assert first == second and first.fits is False


# --------------------------------------------------------------------------
# the M=100 static guarantee (D7) — sizing, not measurement
# --------------------------------------------------------------------------

def test_the_fat_worst_case_is_the_declared_sum():
    assert fat_worst_case_request_bytes() == (
        M * EXCERPT_BLOCK_CEILING_BYTES + QUERY_BLOCK_CEILING_BYTES + SYSTEM_TEMPLATE_BUDGET_BYTES
    )
    assert fat_worst_case_request_bytes() == 257_168


def test_the_static_guarantee_holds_against_the_smallest_pool_budget():
    """D7: fat's absolute worst case fits BY CONSTRUCTION — codex's 381 kB
    counterexample dies by sizing, not by measurement."""
    total = fat_static_guarantee_tokens()
    assert total == 283_168, f"the guarantee's total moved: {total}"
    assert total < SMALLEST_POOL_BUDGET_TOKENS
    assert SMALLEST_POOL_BUDGET_TOKENS - total > 0


def test_the_guarantee_uses_the_pathological_bound_not_the_estimate():
    """If it used bytes/4 it would claim ~4x more headroom than it has, and would
    be a measurement dressed as a proof."""
    assert fat_static_guarantee_tokens() > estimate_input_tokens(
        fat_worst_case_request_bytes()
    ) + reserved_output_tokens("fat")


def test_the_guarantee_covers_every_pool_route():
    """Stated against the smallest budget, so it holds for the whole pool."""
    for entry in load_pool():
        window = entry.get("ctx_window")
        assert window is not None
        assert fat_static_guarantee_tokens() < math.floor(window * BUDGET_HEADROOM), entry["id"]


def test_fat_needs_no_estimation_in_its_safety_path_at_pool_windows():
    """The D6 preflight still runs (one method, both stages) but never reaches the
    guard at pool windows — that is what "no estimation in fat's safety path" means."""
    for model_id in D4_COHORT:
        spec = resolve_models_json(model_id)
        verdict = preflight("fat", rendered_bytes=fat_worst_case_request_bytes(), spec=spec)
        assert verdict.fits, model_id


def test_the_guarantee_scales_with_m_and_would_fail_at_a_larger_retention():
    """M=100 is load-bearing, not incidental: the constant is what makes the
    guarantee true, so a much larger M must break it."""
    assert fat_static_guarantee_tokens(retained=100) < SMALLEST_POOL_BUDGET_TOKENS
    assert fat_static_guarantee_tokens(retained=150) > SMALLEST_POOL_BUDGET_TOKENS


# --------------------------------------------------------------------------
# over-bound request => zero work (D9.2)
# --------------------------------------------------------------------------

def test_too_many_expressions_raises_before_any_rendering_or_reading():
    """`InvalidGraphSearchRequest` pins zero rendering, zero body reads, zero
    calls, zero StageRecords — a `GraphSearchResult` would imply an audit payload
    for a request that was never valid (codex P3 option 2)."""
    payload = QueryPayload(text="q", expressions=tuple(f"e{i}" for i in range(MAX_EXPRESSIONS + 1)))
    with pytest.raises(InvalidGraphSearchRequest) as excinfo:
        payload.validate()
    assert excinfo.value.code == "max_expressions_exceeded"


def test_exactly_max_expressions_is_valid():
    QueryPayload(text="q", expressions=tuple(f"e{i}" for i in range(MAX_EXPRESSIONS))).validate()


def test_an_empty_expression_list_is_valid_state_c_searches_with_one():
    QueryPayload(text="q", expressions=()).validate()
