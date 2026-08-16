"""P1.3 — budget estimator + output envelope (#123 spec §7.2, D6/D7/D9).

**Structural only.** Measurement assertions live at the D5 calibration gate at the
end of P2 (H3) — nothing here claims a real bytes-per-token ratio. What is asserted
is arithmetic and contract: the exact serialized maxima, the four envelope
quantities, route preconditions, and the stage-2 fill allowance that replaced the
M=100 static guarantee (D-123-B/D).

The synthetic schema-maximum documents are the executable authority for §7.0a.
They are built mechanically from `WIRE_JSON_SEPARATORS`, `expression_labels()` and
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
from kdb_graph_search.budget import (
    context_budget,
    estimate_input_tokens,
    exact_max_visible_bytes,
    fat_input_byte_allowance,
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
from kdb_graph_search.constants import (
    BUDGET_HEADROOM,
    ESTIMATOR_BYTES_PER_TOKEN,
    HIDDEN_OUTPUT_RESERVE,
    M,
    MAX_EXPRESSIONS,
    MAX_RESULTS,
    MAX_SLUG_LEN,
    QUERY_BLOCK_CEILING_BYTES,
    SYSTEM_TEMPLATE_BUDGET_BYTES,
    VISIBLE_OUTPUT_ALLOWANCE_FAT,
    VISIBLE_OUTPUT_ALLOWANCE_THIN,
    WIRE_JSON_SEPARATORS,
    WIRE_LABEL_ALPHABET,
    expression_labels,
)
from kdb_graph_search.types import InvalidGraphSearchRequest, QueryPayload, SearchConfigError

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


def test_thin_exact_max_is_18464_bytes_and_fits_its_allowance():
    """Was 12,314 at M=100. Thin's wire is `M x MAX_SLUG_LEN` bounded, so the
    maximum tracks M — and D-123-A's M=150 carried the allowance up with it."""
    exact = exact_max_visible_bytes("thin")
    assert exact == 18_464, f"thin exact max moved: {exact}"
    assert exact <= VISIBLE_OUTPUT_ALLOWANCE_THIN
    # Under tokens_lte_bytes, bytes bound tokens — no density step anywhere.
    assert exact <= VISIBLE_OUTPUT_ALLOWANCE_THIN, "tokens <= bytes <= allowance"


def test_fat_exact_max_is_9216_bytes_and_fits_its_allowance():
    """9,271 -> 9,216 at v0.16: D-123-F took the advisory `unresolved` list off
    the wire, and at MAX_EXPRESSIONS=10 that list serialized to 55 B. The
    allowance stays 10,000 — it is an upper bound and the maximum only shrank.

    (D11 history, for the figure's lineage: letter labels quote where indices did
    not, `"A"` costing 3 B against `0`'s 1 B over 51 label lists, so 8,251 ->
    9,271. One of those 51 lists was `unresolved`; 50 remain.)"""
    exact = exact_max_visible_bytes("fat")
    assert exact == 9_216, f"fat exact max moved: {exact}"
    assert exact <= VISIBLE_OUTPUT_ALLOWANCE_FAT


def test_the_thin_document_is_built_from_the_declared_maxima():
    document = json.loads(schema_maximum_thin_document())
    assert len(document["retained"]) == M
    assert {len(slug) for slug in document["retained"]} == {MAX_SLUG_LEN}


def test_the_thin_maximum_is_unmoved_by_labels():
    """D11 touches only expression addressing, and thin's wire carries none —
    it is a retained-slug list. Pinned so a future reader cannot read the fat
    move as a change to the whole wire."""
    assert exact_max_visible_bytes("thin") == 18_464


def test_the_fat_document_is_built_from_the_declared_maxima_and_letter_labels():
    document = json.loads(schema_maximum_fat_document())
    assert len(document["selections"]) == MAX_RESULTS
    assert document["selections"][0]["matched"] == ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    assert "unresolved" not in document, "D-123-F took the advisory list off the wire"


@pytest.mark.parametrize(
    "expressions,expected,fits",
    [(10, 9_216, True), (13, 9_816, True), (14, 10_016, False), (22, 11_616, False), (26, 12_416, False)],
)
def test_the_fat_maximum_is_a_function_of_max_expressions(expressions, expected, fits):
    """The break-even table (§7.0a, re-derived at v0.16 for D11's labels). The
    10/14 pair is the load-bearing one: a fits/exceeds contrast. A pair where both
    points fit would ship a test demonstrating nothing about the bound it exists to
    pin — the defect codex caught in the superseded `10/20` pair."""
    exact = exact_max_visible_bytes("fat", expressions=expressions)
    assert exact == expected, f"{expressions} expressions => {exact}, table says {expected}"
    assert (exact <= VISIBLE_OUTPUT_ALLOWANCE_FAT) is fits


def test_the_break_even_is_14_labels_not_22():
    """D11 moved the break-even from 22 expressions to 14 — quoted labels cost
    2 B each more than single-digit indices. `MAX_EXPRESSIONS = 10` still sits
    under it, but by 4 rather than by 12, which is why D9.2's argument for a
    consumer-neutral bound gets STRONGER, not weaker: a P5b CLI/MCP caller now
    needs only 14 expressions to re-open the truncation chain."""
    fitting = [
        n for n in range(1, len(WIRE_LABEL_ALPHABET) + 1)
        if exact_max_visible_bytes("fat", expressions=n) <= VISIBLE_OUTPUT_ALLOWANCE_FAT
    ]
    assert max(fitting) == 13
    assert exact_max_visible_bytes("fat", expressions=14) > VISIBLE_OUTPUT_ALLOWANCE_FAT


def test_max_expressions_stays_inside_the_break_even():
    assert MAX_EXPRESSIONS < 14, "the declared bound must sit under the break-even"


def test_the_byte_bound_binds_long_before_the_alphabet_does():
    """Why `expression_labels` stops at Z instead of extending to `AA`: the
    allowance is exceeded at 14 labels, so a multi-letter scheme would be untested
    reach for a case the contract already forbids."""
    assert exact_max_visible_bytes("fat", expressions=14) > VISIBLE_OUTPUT_ALLOWANCE_FAT
    assert 14 < len(WIRE_LABEL_ALPHABET)
    with pytest.raises(ValueError, match="alphabet"):
        expression_labels(len(WIRE_LABEL_ALPHABET) + 1)


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


def test_the_provider_totals_are_36000_thin_and_26000_fat():
    """Thin was 29,000 before D-123-A carried its visible allowance 13,000 ->
    20,000. Fat is unmoved: its wire is bounded by MAX_RESULTS and
    MAX_EXPRESSIONS, neither of which M touches."""
    assert provider_max_tokens("thin") == 36_000
    assert provider_max_tokens("fat") == 26_000


def test_the_thin_provider_total_still_clears_every_pool_route():
    """The constraint that would have blocked M=150 if it bound. gemini-3.6-flash
    is the binding route at 65,536."""
    for entry in load_pool():
        limit = entry.get("max_output_tokens")
        assert limit is not None and provider_max_tokens("thin") < limit, entry["id"]


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
# the stage-2 fill allowance (D-123-B) — replaces the M=100 static guarantee
#
# What used to live here: `fat_worst_case_request_bytes()` (M x 2,500 B evidence
# + 4,096 query + 4,096 template = 258,192 B), `fat_static_guarantee_tokens()`
# (284,192 < 320,000), and a test asserting the guarantee BREAKS at retained=150
# — M=100 was load-bearing precisely because the guarantee was sized on it.
#
# That whole scheme is withdrawn (D-123-D). Boundedness no longer comes from
# `M x per-entity ceiling` holding; it comes from never constructing a request
# that does not fit. The property below is what replaced it, and it is stronger:
# the old guarantee held only while the per-entity ceiling held, and the ceiling
# held by corrupting evidence.
# --------------------------------------------------------------------------

def test_the_allowance_is_exactly_the_preflight_boundary():
    """The load-bearing property. `fat_input_byte_allowance` is derived from
    `preflight`'s own inequality, so a pool filled exactly to it MUST pass the
    pre-flight that follows — and one byte more must fail. A drift between the two
    would break the single thing the fill design promises."""
    spec = _spec(ctx_window=100_000)
    allowance = fat_input_byte_allowance(spec)
    assert preflight("fat", rendered_bytes=allowance, spec=spec).fits is True
    assert preflight("fat", rendered_bytes=allowance + 1, spec=spec).fits is False


@pytest.mark.parametrize("window", [50_000, 100_000, 128_000, 400_000, 1_000_000])
def test_the_boundary_is_exact_at_every_window_not_just_one(window):
    """`ceil(b/K) <= budget - reserved  <=>  b <= (budget - reserved) * K` is an
    identity for integer b, not an approximation — so the boundary is exact at
    every window, including ones where the division does not land evenly."""
    spec = _spec(ctx_window=window)
    allowance = fat_input_byte_allowance(spec)
    assert preflight("fat", rendered_bytes=allowance, spec=spec).fits is True
    assert preflight("fat", rendered_bytes=allowance + 1, spec=spec).fits is False


def test_every_pool_route_can_afford_at_least_one_entity():
    """A route whose allowance could not seat a single maximal entity would make
    the narrowed FAT_PREFLIGHT_BUDGET terminal the normal outcome rather than the
    pathological one."""
    for model_id in D4_COHORT:
        spec = resolve_models_json(model_id)
        allowance = fat_input_byte_allowance(spec)
        assert allowance > SYSTEM_TEMPLATE_BUDGET_BYTES + QUERY_BLOCK_CEILING_BYTES + 2_209, model_id


def test_the_allowance_dwarfs_live_body_density_at_the_M_ceiling():
    """The fill is a fail-safe, not an active mechanism. At M=150 and the fixture's
    own density (84.9 kB), the pool uses a single-digit percentage of the smallest
    route's allowance — bodies would have to average ~19x live reality to bind."""
    spec = resolve_models_json("gpt-5.4-mini")
    allowance = fat_input_byte_allowance(spec)
    fixture_density_at_150 = 84_900
    assert fixture_density_at_150 / allowance < 0.10


def test_the_allowance_is_never_negative():
    """Clamped, so the fill degrades to "nothing fits" rather than to a nonsense
    bound. `resolve_selector_route` refuses such a route first; this is the guard
    behind that guard."""
    spec = _spec(ctx_window=1)
    assert fat_input_byte_allowance(spec) == 0


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
