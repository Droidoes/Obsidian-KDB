"""#123 P2.2 — the `graph_search` spine and every terminal that spends nothing.

**What makes these tests oracles rather than restatements.**

  * **Every zero-call assertion is driven with `fakes.NeverCalled`.** A terminal
    that returns the right `status` *after* burning a call is the exact defect
    these rows exist to catch, and a status-only assertion passes it. `NeverCalled`
    raises on invocation, so the failure names the violation instead of surfacing
    as a wrong count three assertions later.
  * **The terminal names are checked against `contracts.TERMINAL_CONTRACTS`,
    which P1.5 ratified with no producer.** P2 is its first producer, so
    `assert_result_contract` at each return site is a real gate: `search.py`'s
    `_zero_call_result` builds *one* field pattern and the matrix decides which
    terminals may wear it.
  * **The pre-work gate ORDER is pinned by firing two faults at once.** Each gate
    tested alone would pass under any ordering, so precedence is asserted with a
    request that violates both — the one case that discriminates.

**P2.4 continues below the pre-work gates** with the two-stage flow itself —
thin → fat, retain-all, the F1 path, the D3 terminal, the fat pre-flight and
post-call terminals, and concordance. The zero-call section above keeps its
`NeverCalled` discipline unchanged; everything from the P2.4 banner down drives a
scripted `FakeSelector`, and the call-count assertion is part of nearly every
case because §8's branch table is a statement about how many times money was
spent, not only about what came back.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import openai
import pytest
from common.model_pool import ModelRoute, ModelSpec
from common.paths import PageType
from common.wiki_io import ContentNotFoundError

from kdb_search.budget import provider_max_tokens

from kdb_search import search
from kdb_search.budget import fat_input_byte_allowance
from kdb_search.constants import M
from kdb_search.contracts import TERMINAL_CONTRACTS, ContractViolation
from kdb_search.tests import fakes
from kdb_search.types import (
    GraphSearchRequest,
    InvalidGraphSearchRequest,
    QueryPayload,
    SearchConfigError,
)

# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


#: "Above M" as a derivation, not a literal. It was hardcoded 120, which silently
#: became "below M" the moment D-123-A raised M 100 -> 150 — every above-M branch
#: then tested the small-space path instead, and the assertions failed rather than
#: quietly passing only because they are specific. Derived so the next M move
#: cannot repeat it.
ABOVE_M = M + 20


def _spec(**overrides) -> ModelSpec:
    """A route that satisfies every §8 B10 precondition, so a test that wants one
    to fail says which one."""
    base = dict(
        id="test-selector",
        provider="deepseek",
        model="test",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000,
        max_output_tokens=128_000,
        tokens_lte_bytes=True,
    )
    return ModelSpec(**{**base, **overrides})


def _body_reader(slug: str, page_type: PageType) -> str:  # pragma: no cover - never reached
    """Matches `projection.BodyReader` exactly. It never runs on any path here —
    that is the point of it — so a signature that drifted from the real alias would
    be invisible until P2.3 actually called one."""
    raise AssertionError(f"a body was read on a zero-call path (slug={slug!r})")


def _request(
    *,
    count: int = 5,
    expressions: tuple[str, ...] = ("alpha", "beta"),
    scope_kind: str = "domain_subtree",
    domain: str | None = "investing",
    text: str = "QUERY TEXT",
) -> GraphSearchRequest:
    return GraphSearchRequest(
        query=QueryPayload(text=text, expressions=expressions),
        search_space=fakes.make_space_ref(count, scope_kind=scope_kind, domain=domain),
    )


def _run(request: GraphSearchRequest, **kwargs):
    """Always with `NeverCalled` and a body reader that raises — the two things a
    zero-spend terminal must not touch."""
    return search.graph_search(
        request,
        selector=kwargs.pop("selector", _spec()),
        call=kwargs.pop("call", fakes.NeverCalled()),
        body_reader=kwargs.pop("body_reader", _body_reader),
        **kwargs,
    )


# --------------------------------------------------------------------------
# 1. request validity — zero of everything (D9.2)
# --------------------------------------------------------------------------


def test_too_many_expressions_raises_rather_than_returning_a_result() -> None:
    """`InvalidGraphSearchRequest`, not a fifth `status`: a `GraphSearchResult`
    implies an audit payload for work performed, and this request was never
    valid."""
    with pytest.raises(InvalidGraphSearchRequest) as exc:
        _run(_request(expressions=tuple(f"e{i}" for i in range(11))))
    assert exc.value.code == "max_expressions_exceeded"


def test_the_invalid_request_pins_zero_work_not_merely_the_exception() -> None:
    """D9.2's actual claim. `NeverCalled` and `_body_reader` both raise
    `AssertionError`; if either ran, that — not `InvalidGraphSearchRequest` —
    is what would surface, so the raise type IS the zero-work assertion.

    The rendering half is proved separately: an over-long request is rejected
    before the space is even looked at, asserted by handing it a space whose
    entities would fail projection if touched.
    """
    request = GraphSearchRequest(
        query=QueryPayload(text="x", expressions=tuple(f"e{i}" for i in range(11))),
        search_space=fakes.make_space_ref(3),
    )
    with pytest.raises(InvalidGraphSearchRequest):
        _run(request)


def test_expressions_at_the_cap_are_valid() -> None:
    """The boundary is inclusive — 10 is fine, 11 is not. Without this the test
    above would pass an off-by-one that rejects every legitimate pass-1 payload.
    """
    result = _run(_request(count=0, expressions=tuple(f"e{i}" for i in range(10))))
    assert result.status == "abstain_empty_space"


# --------------------------------------------------------------------------
# 2. route resolution — §8 B10, before any rendering or calling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "because"),
    [
        ({"ctx_window": None}, "no window to budget against"),
        ({"tokens_lte_bytes": None}, "the allowance proof rests on the premise"),
        ({"tokens_lte_bytes": False}, "explicitly denied is not better than absent"),
        ({"max_output_tokens": 100}, "below the envelope both stages need"),
    ],
)
def test_a_route_precondition_failure_raises_before_any_work(overrides, because) -> None:
    """§8 B10 — typed `SearchConfigError`, never a `GraphSearchResult`. Driven with
    `NeverCalled`, so this also pins that resolution precedes the call."""
    with pytest.raises(SearchConfigError):
        _run(_request(), selector=_spec(**overrides))


def test_an_anthropic_route_is_rejected_because_it_cannot_honour_json_mode() -> None:
    """The P2.2 half of the `json_mode` requirement.

    `common/call_model.py` implements `json_mode` for openai_compat (`:291`) and
    gemini (`:232`) and NOT for anthropic — so an anthropic selector would
    free-form its JSON *silently*. That is the Pass-2 failure
    `compiler/tests/test_compile_source.py:139` pins, so it is made loud at
    resolution rather than discovered in a malformed response.
    """
    spec = _spec(
        id="anthropic-selector",
        provider="anthropic",
        route=ModelRoute("anthropic", None, "ANTHROPIC_API_KEY"),
    )
    with pytest.raises(SearchConfigError, match="json_mode"):
        _run(_request(), selector=spec)


def test_the_json_mode_check_names_anthropic_rather_than_allow_listing() -> None:
    """A gemini route passes. Guards against 'fix' by allow-listing one provider —
    which would reject every future openai-compatible route that is perfectly
    capable."""
    spec = _spec(
        id="gemini-selector",
        provider="gemini",
        route=ModelRoute("gemini", None, "GEMINI_API_KEY"),
    )
    result = _run(_request(count=0), selector=spec)
    assert result.status == "abstain_empty_space"


# --------------------------------------------------------------------------
# gate ORDER — the discriminating case
# --------------------------------------------------------------------------


def test_request_validation_precedes_route_resolution() -> None:
    """Both faults at once. Each gate tested alone passes under either ordering,
    so this is the only case that pins precedence.

    The choice is recorded in `search.py`: the request is checked first because it
    is the caller's own input and needs no configuration to judge — a caller
    sending 11 expressions is told about the 11 expressions, not about a route
    they may not have chosen. Ratified text fixes both as 'before any work' and
    does not order them, so this test exists to keep the decision from drifting
    silently rather than to enforce a spec clause.
    """
    with pytest.raises(InvalidGraphSearchRequest):
        _run(
            _request(expressions=tuple(f"e{i}" for i in range(11))),
            selector=_spec(ctx_window=None),
        )


# --------------------------------------------------------------------------
# 3. empty space → abstain_empty_space (§1.2)
# --------------------------------------------------------------------------


def test_an_empty_space_abstains_without_invoking_the_selector() -> None:
    result = _run(_request(count=0))
    assert result.status == "abstain_empty_space"
    assert result.execution == "not_executed"
    assert result.hits == ()
    assert result.evidence_status == "not_applicable"
    assert result.body_coverage is None
    assert result.telemetry.eligible_space_size == 0


def test_the_empty_space_terminal_reports_every_expression_unresolved() -> None:
    """Invariant 5 — honest empty. A caller asked about two expressions and got
    nothing, so both must come back unresolved rather than silently dropped."""
    result = _run(_request(count=0, expressions=("alpha", "beta")))
    assert result.unresolved_expressions == ("alpha", "beta")


def test_a_domain_scoped_space_with_no_domain_is_stamped_domain_missing() -> None:
    """§1.2 — never a silent whole-graph fallback."""
    result = _run(_request(count=0, domain=None))
    assert "domain_missing" in result.telemetry.watched


def test_an_empty_domain_CLUSTER_is_not_stamped_domain_missing() -> None:
    """The two reasons spec §3.4 names are distinct, and only one is in the closed
    `WatchedClass` literal. An empty cluster under a domain that DOES exist is not
    a missing domain, and reporting it as one would corrupt the series that exists
    to catch a broken pass-1 domain."""
    result = _run(_request(count=0, domain="investing"))
    assert result.telemetry.watched == ()


@pytest.mark.parametrize("scope_kind", ["whole_graph", "explicit"])
def test_a_non_domain_scope_never_reports_a_missing_domain(scope_kind) -> None:
    """These scopes legitimately carry no domain. Without this guard every empty
    whole-graph search would report a domain it never had."""
    result = _run(_request(count=0, scope_kind=scope_kind, domain=None))
    assert result.telemetry.watched == ()


# --------------------------------------------------------------------------
# 4. thin pre-flight → budget_exceeded, zero spend, never retried (R2)
# --------------------------------------------------------------------------


def _tiny_window_spec() -> ModelSpec:
    """A window too small for the thin render. `max_output_tokens` stays high so
    route resolution passes and the pre-flight is what binds — otherwise this
    would test B10 again by accident."""
    return _spec(ctx_window=20_000, max_output_tokens=128_000)


def test_the_thin_preflight_terminal_spends_nothing() -> None:
    result = _run(_request(count=100), selector=_tiny_window_spec())
    assert result.status == "budget_exceeded"
    assert result.execution == "not_executed"
    assert result.hits == ()
    assert result.evidence_status == "not_applicable"
    assert result.body_coverage is None


def test_the_thin_preflight_terminal_records_the_budget_decision() -> None:
    """A `BudgetRecord` for the stage that reached a decision — `pre_call` on the
    `input` side, which is what distinguishes this from the post-call output
    terminal D9 introduced."""
    result = _run(_request(count=100), selector=_tiny_window_spec())
    (record,) = result.telemetry.budget_records
    assert record.stage == "thin"
    assert record.fits is False
    assert record.detected == "pre_call"
    assert record.budget_side == "input"


def test_the_preflight_reports_the_space_it_actually_measured() -> None:
    """`eligible_space_size` is the measured space, not 0 — the empty-space
    terminal is the one that reports 0, and confusing the two would make the
    KPI series unable to tell an over-large space from a missing one."""
    result = _run(_request(count=100), selector=_tiny_window_spec())
    assert result.telemetry.eligible_space_size == 100


def test_the_estimate_actually_includes_the_RENDERED_EVIDENCE() -> None:
    """The gap the `_tiny_window_spec` tests above cannot close.

    At a 20,000-token window the thin envelope alone (29,000 reserved) exceeds the
    budget, so those tests would pass even if the evidence were never rendered or
    measured — they pin the terminal, not the estimate's inputs. Here the window is
    sized so the envelope fits with ~11,000 tokens to spare: a 5-entity space
    passes and a 2,000-entity space does not, and the *only* difference between
    them is the rendered evidence. So this is what proves the space is in the sum.
    """
    spec = _spec(ctx_window=50_000, max_output_tokens=128_000)

    small = _search(count=5, selector=spec)  # pre-flight passes: the search runs
    assert small.status == "completed"

    large = _run(_request(count=2_000), selector=spec)
    assert large.status == "budget_exceeded"
    assert large.telemetry.eligible_space_size == 2_000


def test_a_space_that_fits_passes_the_preflight_and_runs_BOTH_stages() -> None:
    """The negative control, and the proof that the pre-flight is not simply
    always-fails: every gate passes and the search reaches its ordinary terminal.
    """
    result, selector = _search_with(count=5)
    assert result.status == "completed"
    assert selector.calls == 2


def test_no_zero_spend_gate_falls_through_to_the_stages() -> None:
    """Ordering, from the other side: each zero-call terminal must return rather
    than continue. Driven with `NeverCalled`, so a dropped gate surfaces as the
    invocation it would cause and not as a wrong status three fields later."""
    assert _run(_request(count=0)).status == "abstain_empty_space"
    assert (
        _run(_request(count=100), selector=_tiny_window_spec()).status
        == "budget_exceeded"
    )


# --------------------------------------------------------------------------
# the contract guard is live at every return site
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("terminal", "make"),
    [
        ("empty_space", lambda: _run(_request(count=0))),
        (
            "thin_preflight_budget",
            lambda: _run(_request(count=100), selector=_tiny_window_spec()),
        ),
    ],
)
def test_each_zero_call_terminal_satisfies_its_RATIFIED_contract(terminal, make) -> None:
    """The result came back, so `assert_result_contract` already passed inside
    `graph_search`. This re-verifies against the matrix from outside, so the row
    being satisfied is not merely an artifact of the same helper that built it."""
    from kdb_search.contracts import verify_result_contract

    result = make()
    contract = TERMINAL_CONTRACTS[terminal]
    assert result.status == contract.status
    assert result.execution in contract.execution
    assert not verify_result_contract(
        terminal,
        result,
        request_expressions=result.unresolved_expressions,
        thin_attempts=0,
        fat_attempts=0,
    )


@pytest.mark.parametrize(
    ("terminal", "make"),
    [
        ("empty_space", lambda: _run(_request(count=0))),
        (
            "thin_preflight_budget",
            lambda: _run(_request(count=100), selector=_tiny_window_spec()),
        ),
    ],
)
def test_the_guard_is_WIRED_at_each_return_site_not_merely_present(
    terminal, make, monkeypatch
) -> None:
    """Closes the one mutation the rest of this file cannot catch.

    Deleting `assert_result_contract` from a return site changes nothing while the
    spine produces conforming results — so every other test here stays green and
    the fail-closed guarantee silently becomes decorative. The only way to observe
    the wiring is to make the spine produce a **non**-conforming result and require
    that it does not escape.

    Injected by patching the shared field-pattern helper to emit a hit, which every
    zero-call terminal forbids (`hits_empty=True`). If the guard were bypassed at
    the site under test, the malformed result would simply be returned.
    """
    from kdb_search.types import Hit

    real = search._zero_call_result

    def malformed(**kwargs):
        return replace(
            real(**kwargs),
            hits=(Hit(slug="ent-000", title="Entity 000", page_type="concept"),),
        )

    monkeypatch.setattr(search, "_zero_call_result", malformed)
    with pytest.raises(ContractViolation):
        make()


def test_the_return_site_guard_is_load_bearing_not_decorative() -> None:
    """Proves `assert_result_contract` would actually reject a malformed result,
    by naming the wrong terminal for a correct one. Without this, a guard that
    never fires is indistinguishable from no guard at all.
    """
    result = _run(_request(count=0))
    with pytest.raises(ContractViolation):
        from kdb_search.contracts import assert_result_contract

        assert_result_contract(
            "completed",  # wrong row for an abstention
            result,
            request_expressions=result.unresolved_expressions,
            thin_attempts=0,
            fat_attempts=0,
        )


# --------------------------------------------------------------------------
# the audit record exists on the zero-call paths (§6)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make",
    [
        lambda: _run(_request(count=0)),
        lambda: _run(_request(count=100), selector=_tiny_window_spec()),
    ],
)
def test_a_zero_call_terminal_still_produces_its_audit_record(make) -> None:
    """§6 — the emptiness is the finding, not a reason to skip the record.
    Observed through `telemetry.search_snapshot_hash`, the one part of the payload
    with a ratified home on the result; full delivery is P2.4's call."""
    result = make()
    assert result.telemetry.search_snapshot_hash
    assert result.telemetry.search_snapshot_hash.startswith("sha256:")


def test_the_snapshot_hash_distinguishes_the_space_that_was_searched() -> None:
    """A constant hash would satisfy the assertion above while pinning nothing.

    Compared at the **same size, same `graph_ref`, different slugs** — deliberately
    not empty-vs-large, which differs in size *and* manifest length and so would
    pass even on a hash that only tracked `active_entity_count`. Same class of trap
    as the R2 oracle finding: the assertion would look right and prove less than
    its name claims.
    """
    base = _request(count=100)
    other_entities = tuple(
        replace(entity, slug=f"other-{index:03d}")
        for index, entity in enumerate(base.search_space.entities)
    )
    other = replace(
        base, search_space=replace(base.search_space, entities=other_entities)
    )

    first = _run(base, selector=_tiny_window_spec())
    second = _run(other, selector=_tiny_window_spec())

    assert len(base.search_space.entities) == len(other.search_space.entities)
    assert base.search_space.graph_ref == other.search_space.graph_ref
    assert first.telemetry.search_snapshot_hash != second.telemetry.search_snapshot_hash


def test_the_snapshot_hash_is_sensitive_to_space_ORDER() -> None:
    """The manifest digest is order-sensitive on purpose — the hash pins the exact
    space *in the exact order* presented, and stage-1 rank is meaningless against a
    manifest that could have been permuted."""
    base = _request(count=100)
    reversed_space = replace(
        base,
        search_space=replace(
            base.search_space, entities=tuple(reversed(base.search_space.entities))
        ),
    )
    forward = _run(base, selector=_tiny_window_spec())
    backward = _run(reversed_space, selector=_tiny_window_spec())
    assert forward.telemetry.search_snapshot_hash != backward.telemetry.search_snapshot_hash


# --------------------------------------------------------------------------
# §2.1 fail-hard posture — no catch-all
# --------------------------------------------------------------------------


def test_an_unexpected_exception_from_the_selector_propagates() -> None:
    """Joseph's #121 posture: typed outcomes are `status` values, and anything
    else is a defect that propagates. Pinned with a space that PASSES every gate,
    so the exception comes from the call boundary rather than from a gate — and
    with a fault the retry loop deliberately does not recognize, since the whole
    claim is that no `except Exception` sits between the caller and the stages.
    """
    with pytest.raises(openai.BadRequestError):
        _run(
            _request(count=5),
            call=fakes.FakeSelector(fakes.unrelated_bad_request()),
            body_reader=_ok_body_reader,
        )


# ==========================================================================
# P2.4 — the two-stage flow
#
# Everything below drives a scripted `FakeSelector`. Three habits, each
# earning its keep:
#
#   * **Call counts are asserted, not inferred.** §8's branch table is a
#     statement about how many times money was spent; a status assertion is
#     silent on an extra call that produced the same answer.
#   * **The script is asserted consumed.** A branch that stops early — retrying
#     when it should not, skipping a stage — leaves script behind, and no field
#     assertion notices.
#   * **The terminal NAME is what `assert_result_contract` checked.** These
#     tests read the resulting fields, but the guard inside `graph_search` is
#     what proves the whole row was satisfied, including the cells no test here
#     mentions.
# ==========================================================================


def _ok_body_reader(slug: str, page_type: PageType) -> str:
    """Every entity has a body. The title-only degrade gets its own reader, so a
    test that means to exercise drift has to say so."""
    return f"Body text for {slug}, a {page_type} page with enough words to excerpt."


def _oversized_body_reader(slug: str, page_type: PageType) -> str:
    """One body so large that it alone cannot fit the fat request (D-123-B).

    **The terminal changed shape.** Before fill-to-budget this was 90 moderately
    long bodies against a small window: the assembled request busted, so the
    pre-flight refused it. The fill would now simply seat fewer of them and
    succeed — correctly. `FAT_PREFLIGHT_BUDGET` can only fire when **not even one
    entity fits**, so the only thing that still reaches it is a single oversized
    body. ~120 kB against an 88 kB allowance.
    """
    return " ".join(f"word{n}" for n in range(15_000))


def _missing_for(*slugs: str):
    """A reader that raises `ContentNotFoundError` for the named slugs — the
    graph/disk drift `project_entity` degrades to title-only."""

    def read(slug: str, page_type: PageType) -> str:
        if slug in slugs:
            # The real constructor, not a stand-in: `project_entity` catches this
            # exact type, and a test raising an approximation would pass while
            # the production reader's exception fell through.
            raise ContentNotFoundError(slug, page_type, Path(f"/nonexistent/{slug}.md"))
        return _ok_body_reader(slug, page_type)

    return read


def _two_stage_script(count: int, *, hits: int = 3):
    """The ordinary pair of replies: thin retains, fat selects."""
    space = fakes.make_space(count)
    return (
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.usable_document(space, count=hits)),
    )


def _search_with(*script, count: int = 5, **kwargs):
    """Run a full search against a script, returning the result AND the selector
    so call counts stay assertable."""
    selector = fakes.FakeSelector(*(script or _two_stage_script(count)))
    result = _run(
        kwargs.pop("request", None) or _request(count=count),
        call=selector,
        body_reader=kwargs.pop("body_reader", _ok_body_reader),
        **kwargs,
    )
    return result, selector


def _search(*script, count: int = 5, **kwargs):
    return _search_with(*script, count=count, **kwargs)[0]


# --------------------------------------------------------------------------
# the ordinary path
# --------------------------------------------------------------------------


def test_the_ordinary_search_runs_thin_THEN_fat() -> None:
    result, selector = _search_with(count=5)
    selector.assert_consumed()
    assert result.status == "completed"
    assert result.execution == "two_stage_attempted"
    assert selector.calls == 2
    assert len(result.hits) == 3


def test_the_stages_are_identifiable_from_the_REQUESTS_not_the_script() -> None:
    """`FakeSelector` is order-scripted and never inspects the request, so stage
    identity has to be read off what was sent. A stage-keyed fake would agree
    with whatever the controller believes the boundary is — the one thing worth
    checking."""
    _, selector = _search_with(count=5)
    thin_request, fat_request = selector.requests
    assert thin_request.max_tokens == provider_max_tokens("thin")
    assert fat_request.max_tokens == provider_max_tokens("fat")
    assert "RETAIN" in thin_request.system.upper()
    assert "body:" in fat_request.prompt


def test_thin_ALWAYS_runs_even_where_its_answer_cannot_bind() -> None:
    """R4 as amended. At `N <= M` thin's retention is non-binding by
    construction, so the cheap implementation skips the call — and would lose the
    concordance series plus every thin defect the retain-all rule currently masks.
    Joseph's rationale: the development window is the only window in which finding
    those defects is free, because after `N > M` the same defect is silent,
    unrecoverable data loss."""
    _, selector = _search_with(count=3)
    assert selector.calls == 2
    assert selector.requests[0].max_tokens == provider_max_tokens("thin")


def test_a_five_entity_space_still_runs_BOTH_calls() -> None:
    """"No small-space skip" (§7.2 R4), asserted at the size where skipping is
    most tempting."""
    _, selector = _search_with(count=5)
    assert selector.calls == 2


def test_expression_accounting_is_the_CONTROLLERs_not_the_selectors() -> None:
    """§2.3: the selector's advisory `unresolved` is an input, and where the two
    disagree the controller wins. Here the selector claims everything is
    unresolved while attributing hits to `A` — the controller reports the truth."""
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(
            fakes.usable_document(space, count=2, matched=("A",), unresolved=("A", "B"))
        ),
        count=5,
    )
    assert result.unresolved_expressions == ("beta",)
    assert all("alpha" in hit.matched_expressions for hit in result.hits)


def test_an_EXHAUSTED_fat_stage_reports_a_real_zero_yield_not_no_data() -> None:
    """The §8.4 per-model series' sharpest single reading, and the one the
    obvious implementation loses.

    `StageOutcome.validated` is `None` on `exhausted` (deliberately — see its
    docstring), so reading `returned_entries` and `valid_entry_yield` off the
    surviving response reports 0 and `None`. But an `all_entries_dropped`
    exhaustion means the selector returned a full document twice and every entry
    was rejected on identity grounds — a real 0.0 yield over 8 returned entries,
    the strongest quality signal a selector can emit, filed as its absence. Both
    figures are therefore accumulated across attempts in the stage, not read off
    an outcome that by design has none.
    """
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.all_dropped_document(space)),
        fakes.ScriptedReply(fakes.all_dropped_document(space)),
        count=5,
    )
    assert result.status == "selector_failure"
    assert result.telemetry.returned_entries == 8  # 4 entries x 2 attempts
    assert result.telemetry.valid_entry_yield == 0.0
    assert result.telemetry.all_entries_dropped_occurrences == 2


def test_a_TRUNCATED_stage_still_reports_None_because_it_has_no_denominator() -> None:
    """The other side of D9.6, so the fix above cannot become "0.0 everywhere". A
    truncated attempt yields no usable document, hence no entry population, hence
    no denominator — it must never dilute a model's conformance ratio."""
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(
            fakes.truncated_text(space), stop_reason=fakes.STOP_LENGTH_OPENAI
        ),
        count=5,
    )
    assert result.telemetry.returned_entries == 0
    assert result.telemetry.valid_entry_yield is None


def test_the_fat_prompt_states_the_REQUESTs_cap_not_the_global_one() -> None:
    """`render_fat_messages` takes `max_results` with no default for exactly this
    reason: the prompt states the cap and `validate_response` counts `over_cap`
    against `request.max_results`, so a call site rendering the global constant
    would tell the selector 50 and then charge it against 5 — the selector obeys
    the rule it was given and is penalized under a different one, invisibly at
    both ends.

    Every other test here uses the default `max_results`, under which the two
    values coincide and the defect is unobservable. Found by mutation: replacing
    `request.max_results` with the literal 50 left the whole suite green.
    """
    space = fakes.make_space(5)
    request = GraphSearchRequest(
        query=QueryPayload(text="QUERY TEXT", expressions=("alpha", "beta")),
        search_space=fakes.make_space_ref(5),
        max_results=3,
    )
    _, selector = _search_with(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        request=request,
    )
    fat_prompt = selector.requests[1].prompt
    assert "3" in fat_prompt.split("EVIDENCE")[0] or " 3" in fat_prompt
    assert "50" not in fat_prompt


def test_the_request_cap_also_binds_the_VALIDATOR_not_only_the_prompt() -> None:
    """The other end of the same pairing: a response over the request's cap is
    truncated to it and the excess counted, rather than measured against the
    global 50."""
    space = fakes.make_space(6)
    request = GraphSearchRequest(
        query=QueryPayload(text="QUERY TEXT", expressions=("alpha", "beta")),
        search_space=fakes.make_space_ref(6),
        max_results=2,
    )
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.usable_document(space, count=5)),
        request=request,
    )
    assert len(result.hits) == 2
    assert result.telemetry.attempted_violations.over_cap == 3


def test_an_honest_empty_fat_selection_is_completed_with_every_expression_open() -> None:
    """Spec §2.3's fourth case. `completed` with no hits is a real answer, and
    `COMPLETED` leaves `hits_empty` unconstrained precisely so this passes the
    contract rather than needing a terminal of its own (D9.6)."""
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.honest_empty_document()),
        count=5,
    )
    assert (result.status, result.hits) == ("completed", ())
    assert result.unresolved_expressions == ("alpha", "beta")


def test_the_salvage_rule_survives_the_whole_flow() -> None:
    """Joseph's 10-returned/6-kept rule, end to end rather than at the validator:
    a parseable response is never discarded, and the violations reach telemetry
    by class."""
    space = fakes.make_space(6)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.salvage_document(space)),
        count=6,
    )
    assert len(result.hits) == 6
    assert result.telemetry.returned_entries == 10
    assert result.telemetry.valid_entry_yield == pytest.approx(0.6)
    violations = result.telemetry.attempted_violations
    assert (violations.foreign_slug, violations.duplicate_slug, violations.malformed_entry) == (2, 1, 1)


# --------------------------------------------------------------------------
# retain-all (N <= M) and manifest order
# --------------------------------------------------------------------------




def test_stage_two_is_presented_in_MANIFEST_order_not_thins_ranked_order() -> None:
    """Spec §3.4 — fat's judgment stays unanchored to thin's. Thin returns its
    retention reversed; the fat evidence must still ascend by slug. Without this,
    fat inherits thin's ranking and the two stages stop being independent
    judgments, which is what the concordance series is trying to measure."""
    space = fakes.make_space(ABOVE_M)  # N > M, so thin's list actually selects
    retained = list(space[:30])
    document = fakes._dump({"retained": [e.slug for e in reversed(retained)]})
    _, selector = _search_with(
        fakes.ScriptedReply(document),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        count=ABOVE_M,
    )
    fat_prompt = selector.requests[1].prompt
    positions = [fat_prompt.index(e.slug) for e in retained]
    assert positions == sorted(positions)


def test_above_M_stage_two_is_thins_VALIDATED_retention() -> None:
    space = fakes.make_space(ABOVE_M)
    kept = space[:4]
    _, selector = _search_with(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in kept]})),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        count=ABOVE_M,
    )
    fat_prompt = selector.requests[1].prompt
    assert all(entity.slug in fat_prompt for entity in kept)
    assert space[50].slug not in fat_prompt


# --------------------------------------------------------------------------
# F1 — thin exhausted, N <= M
# --------------------------------------------------------------------------



def test_F1_reports_concordance_as_NULL_not_zero() -> None:
    """The distinction the metric depends on. Thin produced no validated ranking
    at all, so there is nothing to compare fat against — a computed 0.0 would
    report "the two stages agreed on nothing" about a comparison that never
    happened, and that value would then enter the watched series as evidence."""
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        count=5,
    )
    assert result.telemetry.concordance is None



def test_thin_exhaustion_above_M_records_WHICH_class_exhausted_it() -> None:
    """`THIN_EXHAUSTED.failure_class_required` — and the matrix forbids the field
    anywhere else, so a class leaking onto a non-failure terminal fails the guard
    rather than passing unnoticed."""
    result = _search(
        fakes.ScriptedReply(fakes.thin_structurally_unusable_document()),
        fakes.ScriptedReply(fakes.thin_structurally_unusable_document()),
        count=ABOVE_M,
    )
    assert result.telemetry.selector_failure_class == "structurally_unusable_response"


def test_a_completed_search_carries_NO_failure_class() -> None:
    result = _search(count=5)
    assert result.telemetry.selector_failure_class is None


# --------------------------------------------------------------------------
# D3 — thin retained zero over N > M
# --------------------------------------------------------------------------


def test_D3_skips_the_fat_call_entirely() -> None:
    """Every fat call is a thin→fat call (Joseph). With nothing retained above M
    there is no evidence pool to build, so `completed` is reported without a
    second call — and the watched class is what keeps it out of the honest-empty
    bucket in the KPI series."""
    result, selector = _search_with(
        fakes.ScriptedReply(fakes.retained_empty_document()), count=ABOVE_M
    )
    selector.assert_consumed()
    assert result.status == "completed"
    assert result.execution == "thin_attempted"
    assert selector.calls == 1
    assert "thin_retained_zero" in result.telemetry.watched
    assert result.hits == ()
    assert result.unresolved_expressions == ("alpha", "beta")
    assert result.evidence_status == "not_applicable"
    assert result.body_coverage is None
    assert result.telemetry.concordance is None


def test_D3_is_reached_only_by_an_HONEST_empty_not_by_a_hallucination() -> None:
    """The pair `fakes.retained_all_foreign_document` exists for. Both documents
    validate to `retained == ()`; one is the D3 terminal after ONE call, the other
    is an allowed retry class that exhausts thin over two. A controller branching
    on the validated list collapses them, and a malfunctioning selector then reads
    as an honest empty — exactly what D3's watched class exists to prevent."""
    space = fakes.make_space(ABOVE_M)
    honest, honest_selector = _search_with(
        fakes.ScriptedReply(fakes.retained_empty_document()), count=ABOVE_M
    )
    honest_selector.assert_consumed()
    assert honest.status == "completed"
    assert honest_selector.calls == 1

    foreign, foreign_selector = _search_with(
        fakes.ScriptedReply(fakes.retained_all_foreign_document(space)),
        fakes.ScriptedReply(fakes.retained_all_foreign_document(space)),
        count=ABOVE_M,
    )
    foreign_selector.assert_consumed()
    assert foreign.status == "selector_failure"
    assert foreign_selector.calls == 2
    assert "thin_retained_zero" not in foreign.telemetry.watched


# --------------------------------------------------------------------------
# the fat evidence pool
# --------------------------------------------------------------------------


def test_bodies_are_read_INSIDE_search_never_by_the_caller() -> None:
    """§1.1 — the caller passes identities only. Asserted by counting reads: the
    projector is what turns a slug into evidence, and a caller that had to
    pre-hydrate would make the snapshot hash a function of its own work."""
    seen: list[str] = []

    def counting_reader(slug: str, page_type: PageType) -> str:
        seen.append(slug)
        return _ok_body_reader(slug, page_type)

    _search(count=5, body_reader=counting_reader)
    assert seen == [entity.slug for entity in fakes.make_space(5)]


def test_full_hydration_reports_complete_evidence_and_full_coverage() -> None:
    result = _search(count=5)
    assert result.evidence_status == "complete"
    assert result.body_coverage == 1.0
    assert result.telemetry.stage2_hydrated == 5
    assert result.telemetry.stage2_title_only == 0


def test_a_missing_body_degrades_to_title_only_rather_than_dropping_the_entity() -> None:
    """Graph/disk drift (§4). The entity still competes, with weaker evidence —
    dropping it would silently shrink the closed world the selector was told it
    had, and `partial` is what makes that visible to a caller whose acceptance
    policy cares."""
    space = fakes.make_space(5)
    result, selector = _search_with(
        count=5, body_reader=_missing_for(space[1].slug, space[3].slug)
    )
    assert result.evidence_status == "partial"
    assert result.body_coverage == pytest.approx(0.6)
    assert result.telemetry.stage2_title_only == 2
    assert space[1].slug in selector.requests[1].prompt


# --------------------------------------------------------------------------
# concordance (§8.3)
# --------------------------------------------------------------------------


def test_concordance_is_the_fraction_of_fats_top_ten_inside_thins_top_twenty() -> None:
    space = fakes.make_space(ABOVE_M)
    result = _search(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in space[:4]]})),
        # Fat returns 4 hits, of which the first 2 are in thin's list.
        fakes.ScriptedReply(fakes.usable_document(space, count=4)),
        count=ABOVE_M,
    )
    assert result.telemetry.concordance == pytest.approx(1.0)


def test_concordance_is_null_when_fat_produced_no_validated_hits() -> None:
    """codex #12 — no denominator. Zero would say the stages disagreed
    completely, which is a claim about a comparison that has no left-hand side."""
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.honest_empty_document()),
        count=5,
    )
    assert result.telemetry.concordance is None


def test_a_thin_stage_that_RAN_and_retained_nothing_ENDS_the_search() -> None:
    """Behaviour change, 2026-08-02. This used to be the third concordance case:
    at N <= M, retain-all sent the whole space to fat anyway, so thin's honest
    empty produced a real 0.0 (fat found what thin did not).

    With `small_space` gone there is no retain-all, so an honestly empty thin is
    D3 at every N — no fat call, and concordance is `None` because no comparison
    happened rather than because the comparison scored zero. The genuine 0.0 is
    still reachable and still tested: see the top-twenty test below, where thin
    retains 40 slugs and fat's hit sits outside the window."""
    space = fakes.make_space(5)
    result = _search(fakes.ScriptedReply(fakes.retained_empty_document()), count=5)
    assert result.status == "completed"
    assert "thin_retained_zero" in result.telemetry.watched
    assert result.hits == ()
    assert result.telemetry.concordance is None


def test_concordance_measures_thins_TOP_TWENTY_not_its_whole_retention() -> None:
    """The window is part of the metric's definition (§8.3). Thin retains 40
    slugs; fat's hits sit at positions 0-1, inside the top 20, while a
    whole-retention reading would score identically for a hit at position 39 —
    and the series would stop discriminating exactly where ranking matters."""
    space = fakes.make_space(ABOVE_M)
    result = _search(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in space[:40]]})),
        fakes.ScriptedReply(
            fakes._dump({"selections": [{"slug": space[39].slug, "matched": ["A"]}]})
        ),
        count=ABOVE_M,
    )
    assert result.telemetry.concordance == 0.0


# --------------------------------------------------------------------------
# the fat pre-flight terminal (D6)
# --------------------------------------------------------------------------


def _fat_only_budget_spec() -> ModelSpec:
    """A window that fits thin's identity-only evidence and not one oversized
    body. 0.8 x 60,000 = 48,000 tokens; fat reserves 26,000, leaving an 88,000 B
    input allowance. Thin reserves 36,000 and needs ~1,750, so it passes — the two
    stages still differ by exactly the bodies, which is what makes this the fat
    pre-flight and not a second thin one.

    Was 45,000, which no longer fits THIN: D-123-A carried
    `VISIBLE_OUTPUT_ALLOWANCE_THIN` 13,000 -> 20,000, so thin's provider total is
    36,000 and a 36,000-token budget leaves it no input room at all."""
    return _spec(ctx_window=60_000, max_output_tokens=128_000)


def test_the_fat_preflight_stops_the_search_with_NO_fat_call() -> None:
    result, selector = _search_with(
        fakes.ScriptedReply(fakes.retained_document(fakes.make_space(90))),
        count=90,
        selector=_fat_only_budget_spec(),
        body_reader=_oversized_body_reader,
    )
    selector.assert_consumed()
    assert result.status == "budget_exceeded"
    assert result.execution == "thin_attempted"
    assert selector.calls == 1
    fat_records = [r for r in result.telemetry.budget_records if r.stage == "fat"]
    assert [r.fits for r in fat_records] == [False]
    assert [r.detected for r in fat_records] == ["pre_call"]


def test_the_fat_preflight_terminal_reports_NOT_APPLICABLE_evidence() -> None:
    """Deliberate, and it looks wrong: the bodies were read a moment earlier to
    size the request, so hydration data exists. The ratified contract distinguishes
    this terminal from the post-call one by whether the pool was **presented**, and
    here it never was — reporting measured coverage would make an unspent search
    indistinguishable from a billed one in the artifact."""
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(fakes.make_space(90))),
        count=90,
        selector=_fat_only_budget_spec(),
        body_reader=_oversized_body_reader,
    )
    assert result.evidence_status == "not_applicable"
    assert result.body_coverage is None



# --------------------------------------------------------------------------
# the post-call fat terminals
# --------------------------------------------------------------------------


def test_a_truncated_fat_response_reports_the_evidence_it_DID_present() -> None:
    """The mirror of the pre-flight case above, and the reason both exist: here
    the pool was built and sent, so `evidence_status` and `body_coverage` are
    measured. Same status, opposite evidence side — that difference is the whole
    content of the distinction."""
    space = fakes.make_space(5)
    result, selector = _search_with(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(
            fakes.truncated_text(space), stop_reason=fakes.STOP_LENGTH_OPENAI
        ),
        count=5,
    )
    selector.assert_consumed()
    assert result.status == "budget_exceeded"
    assert result.execution == "two_stage_attempted"
    assert result.evidence_status == "complete"
    assert result.body_coverage == 1.0


def test_a_truncated_THIN_response_ends_the_search_without_a_fat_call() -> None:
    """D9.3's terminal, and F1 explicitly does not apply: proceeding to fat is for
    retry-exhausted failures, never for either budget side (codex P1 — it removes
    a branch rather than adding one)."""
    space = fakes.make_space(5)
    result, selector = _search_with(
        fakes.ScriptedReply(
            fakes.thin_truncated_text(space), stop_reason=fakes.STOP_LENGTH_OPENAI
        ),
        count=5,
    )
    selector.assert_consumed()
    assert result.status == "budget_exceeded"
    assert result.execution == "thin_attempted"
    assert selector.calls == 1
    assert result.evidence_status == "not_applicable"



def test_a_thin_over_window_rejection_is_watched_as_an_estimation_miss() -> None:
    result, selector = _search_with(
        fakes.context_length_rejection_openai(), count=5
    )
    selector.assert_consumed()
    assert result.status == "budget_exceeded"
    assert "budget_estimation_miss" in result.telemetry.watched
    post = [r for r in result.telemetry.budget_records if r.detected == "post_call"]
    assert [(r.detected, r.budget_side) for r in post] == [("post_call", "input")]



def test_a_fat_stage_that_exhausts_its_retries_is_a_selector_failure() -> None:
    space = fakes.make_space(5)
    result, selector = _search_with(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.all_dropped_document(space)),
        fakes.ScriptedReply(fakes.all_dropped_document(space)),
        count=5,
    )
    selector.assert_consumed()
    assert result.status == "selector_failure"
    assert result.execution == "two_stage_attempted"
    assert result.telemetry.selector_failure_class == "all_entries_dropped"
    assert selector.calls == 3


# --------------------------------------------------------------------------
# the audit payload, on every path
# --------------------------------------------------------------------------


def test_the_stage_trace_holds_one_record_per_logical_call() -> None:
    """§6's invariant, observed through the hash that covers the trace: a search
    with a retried thin and a fat call must move the integrity hash relative to
    one with a clean thin, because the archived attempt count differs."""
    space = fakes.make_space(5)
    clean = _search(count=5)
    retried = _search(
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.usable_document(space, count=3)),
        count=5,
    )
    assert clean.telemetry.retry_attempts == 0
    assert retried.telemetry.retry_attempts == 1
    assert clean.hits == retried.hits


def test_the_snapshot_hash_covers_the_EVIDENCE_the_fat_stage_was_shown() -> None:
    """The snapshot answers "what was searched", so two runs over the same space
    that presented different evidence bytes must not share it. Here one run's
    entity is title-only and the other's is hydrated — same manifest, same graph,
    different evidence."""
    space = fakes.make_space(5)
    hydrated = _search(count=5)
    degraded = _search(count=5, body_reader=_missing_for(space[0].slug))
    assert (
        hydrated.telemetry.search_snapshot_hash
        != degraded.telemetry.search_snapshot_hash
    )


def test_the_snapshot_hash_ignores_what_the_selector_ANSWERED() -> None:
    """The other half of the split: a run that differs only in its outcome moves
    the integrity hash and leaves the snapshot hash alone. That is what makes
    selector A/B over a frozen snapshot meaningful — without it, "the two models
    faced the same world" would be unverifiable."""
    space = fakes.make_space(5)
    three = _search(count=5)
    one = _search(
        fakes.ScriptedReply(fakes.retained_document(space)),
        fakes.ScriptedReply(fakes.usable_document(space, count=1)),
        count=5,
    )
    assert len(three.hits) != len(one.hits)
    assert three.telemetry.search_snapshot_hash == one.telemetry.search_snapshot_hash


@pytest.mark.parametrize(
    "terminal",
    ["completed", "d3", "thin_exhausted", "fat_preflight"],
)
def test_every_terminal_produces_a_snapshot_hash(terminal: str) -> None:
    """§6 — the audit is built on every path, and its emptiness on an abstention
    is the finding rather than a reason to skip the record. The snapshot hash is
    the observable end of that obligation."""
    if terminal == "completed":
        result = _search(count=5)
    elif terminal == "d3":
        result = _search(fakes.ScriptedReply(fakes.retained_empty_document()), count=ABOVE_M)
    elif terminal == "thin_exhausted":
        result = _search(
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
            count=ABOVE_M,
        )
    else:
        result = _search(
            fakes.ScriptedReply(fakes.retained_document(fakes.make_space(90))),
            count=90,
            selector=_fat_only_budget_spec(),
            body_reader=_oversized_body_reader,
        )
    assert result.telemetry.search_snapshot_hash is not None


# --------------------------------------------------------------------------
# the stage-2 fill (D-123-B) — dynamic pool, 1..M
#
# The fill replaced the M x per-entity-ceiling static guarantee. Its contract has
# five independent parts, asserted separately on purpose: a fill that simply
# returned everything would pass an order-only test, and one that returned a
# single entity would pass a never-over-budget test.
# --------------------------------------------------------------------------


def _sized_body_reader(size: int):
    """Bodies of a known byte size, so a budget can be chosen that binds."""

    def read(slug: str, page_type: PageType) -> str:
        return "w" * size

    return read


def _fill_binds_spec() -> ModelSpec:
    """0.8 x 60,000 = 48,000 tokens; fat reserves 26,000, so the input allowance
    is (48,000 - 26,000) x 4 = 88,000 B. Against 8 kB bodies that seats roughly
    ten of them — a fill that genuinely binds."""
    return _spec(ctx_window=60_000, max_output_tokens=128_000)


def test_the_fill_stops_on_the_budget_and_says_so() -> None:
    """Without this the fill is untested at current corpus density: real bodies
    never reach the bound (they would have to average ~19x live reality), so only
    synthetic oversized bodies exercise the stop condition at all."""
    space = fakes.make_space(ABOVE_M)
    result, selector = _search_with(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in space]})),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        count=ABOVE_M,
        selector=_fill_binds_spec(),
        body_reader=_sized_body_reader(8_000),
    )
    assert result.status == "completed"
    assert result.telemetry.stage2_budget_bound is True
    assert 0 < result.telemetry.stage2_pool_size < len(space)


def test_the_filled_request_never_exceeds_the_allowance() -> None:
    """The by-construction property, measured on the bytes actually sent rather
    than on the accumulator that chose them."""
    space = fakes.make_space(ABOVE_M)
    spec = _fill_binds_spec()
    _, selector = _search_with(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in space]})),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        count=ABOVE_M,
        selector=spec,
        body_reader=_sized_body_reader(8_000),
    )
    request = selector.requests[1]
    rendered = len(request.system.encode()) + len(request.prompt.encode())
    assert rendered <= fat_input_byte_allowance(spec)


def test_the_fill_seats_at_least_one_entity_whenever_one_fits() -> None:
    """The boundary between a bound fill and the FAT_PREFLIGHT_BUDGET terminal.
    One body just under the whole allowance must still be sent, not refused."""
    space = fakes.make_space(3)
    result, selector = _search_with(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in space]})),
        fakes.ScriptedReply(fakes.usable_document(space, count=1)),
        count=3,
        selector=_fill_binds_spec(),
        body_reader=_sized_body_reader(70_000),
    )
    assert result.status == "completed"
    assert result.telemetry.stage2_pool_size == 1
    assert result.telemetry.stage2_budget_bound is True


def test_an_unbound_fill_reports_neither_a_bound_nor_a_short_pool() -> None:
    """The negative case — at live density the flag must stay false, or it is
    useless as the signal that the fail-safe has engaged."""
    space = fakes.make_space(ABOVE_M)
    result = _search(
        fakes.ScriptedReply(fakes._dump({"retained": [e.slug for e in space[:30]]})),
        fakes.ScriptedReply(fakes.usable_document(space, count=2)),
        count=ABOVE_M,
    )
    assert result.telemetry.stage2_budget_bound is False
    assert result.telemetry.stage2_pool_size == 30


def test_MEMBERSHIP_is_decided_by_thins_rank_not_by_manifest_position() -> None:
    """Half of §3.4's split. Thin ranks the manifest's TAIL first, so a fill that
    walked the manifest would seat the head instead — the two orders disagree
    completely, which is what makes this assertion mean something."""
    space = fakes.make_space(ABOVE_M)
    ranked = list(reversed([e.slug for e in space]))
    result, selector = _search_with(
        fakes.ScriptedReply(fakes._dump({"retained": ranked})),
        # A hit on a SEATED slug: thin ranked the tail first, so the manifest head
        # is exactly what the fill declines — a canned document built from
        # `space[:2]` would be validated as foreign and trigger a retry.
        fakes.ScriptedReply(
            fakes._dump({"selections": [{"slug": space[-1].slug, "matched": ["A"]}]})
        ),
        count=ABOVE_M,
        selector=_fill_binds_spec(),
        body_reader=_sized_body_reader(8_000),
    )
    seated = result.telemetry.stage2_pool_size
    assert 0 < seated < len(space)
    prompt = selector.requests[1].prompt
    for slug in ranked[:seated]:
        assert slug in prompt, f"{slug} was in thin's top {seated} and must be seated"
    for slug in ranked[seated:]:
        assert slug not in prompt, f"{slug} was below thin's cut and must not be seated"


def test_PRESENTATION_order_stays_the_manifest_even_when_rank_decided_the_cut() -> None:
    """The other half. The entities thin ranked LAST are the ones seated above, so
    if the fill also dictated order they would appear reversed. Spec §3.4 keeps
    fat's judgment unanchored to thin's ranking, and that survives D-123-B."""
    space = fakes.make_space(ABOVE_M)
    ranked = list(reversed([e.slug for e in space]))
    result, selector = _search_with(
        fakes.ScriptedReply(fakes._dump({"retained": ranked})),
        # A hit on a SEATED slug: thin ranked the tail first, so the manifest head
        # is exactly what the fill declines — a canned document built from
        # `space[:2]` would be validated as foreign and trigger a retry.
        fakes.ScriptedReply(
            fakes._dump({"selections": [{"slug": space[-1].slug, "matched": ["A"]}]})
        ),
        count=ABOVE_M,
        selector=_fill_binds_spec(),
        body_reader=_sized_body_reader(8_000),
    )
    prompt = selector.requests[1].prompt
    seated = [e.slug for e in space if f"- slug: {e.slug}" in prompt]
    assert seated == sorted(seated), "manifest order is slug-ascending by construction"
    assert seated != [s for s in ranked if s in seated], "and it is NOT thin's order"


def test_a_pool_filled_to_the_LAST_BYTE_still_passes_its_own_pre_flight() -> None:
    """The invariant the whole design rests on, tested where it can actually fail.

    The fill accepts on an accumulator (`overhead + sum(stream_contribution)`);
    the pre-flight then re-measures the true rendering. Those are two different
    computations, and if the accumulator ever UNDER-counts, a pool would be
    accepted by the fill and refused by the pre-flight it was built to satisfy.
    It cannot today — `"\\n".join()` over n blocks costs n-1 separators while the
    accumulator charges n, so it overstates by exactly one byte — but the other
    tests all run with kilobytes of slack, where a sign error would hide.

    This one walks the body size up until the fill is one entity from refusing,
    then asserts the real rendered request fits.
    """
    spec = _fill_binds_spec()
    allowance = fat_input_byte_allowance(spec)
    space = fakes.make_space(1)

    def run(size: int):
        return _search_with(
            fakes.ScriptedReply(fakes._dump({"retained": [space[0].slug]})),
            fakes.ScriptedReply(fakes.usable_document(space, count=1)),
            count=1,
            selector=spec,
            body_reader=_sized_body_reader(size),
        )

    # Largest body the fill still seats, to the byte.
    low, high = 1, allowance
    while low < high:
        mid = (low + high + 1) // 2
        result, _ = run(mid)
        if result.telemetry.stage2_pool_size == 1:
            low = mid
        else:
            high = mid - 1

    result, selector = run(low)
    assert result.telemetry.stage2_pool_size == 1
    request = selector.requests[1]
    rendered = len(request.system.encode()) + len(request.prompt.encode())
    assert rendered <= allowance, f"the fill seated a pool its pre-flight refuses: {rendered} > {allowance}"
    assert allowance - rendered <= 2, f"not actually at the boundary — {allowance - rendered} B of slack"

    # And one byte more is refused, so the boundary is the fill's, not an artefact.
    refused, _ = run(low + 1)
    assert refused.status == "budget_exceeded"
    assert refused.telemetry.stage2_pool_size == 0


# --------------------------------------------------------------------------
# the live bytes-per-token series, surfaced on the RESULT (Joseph, 2026-08-02)
#
# The StageRecords are the authority; these are a read-only VIEW over them, so
# the caller can watch the estimator's real calibration before P3a's envelope
# sink exists. Joseph, closing Fork C: "we need to keep the stats for the real
# ratio when we run the tests end-to-end."
# --------------------------------------------------------------------------


def test_a_two_stage_search_surfaces_BOTH_stages_measured_ratios() -> None:
    """Separately, never blended: thin sends slug-heavy identity lines and fat
    sends whole prose bodies, which tokenize at genuinely different densities.
    One combined figure would hide exactly the spread the series exists to show.
    """
    space = fakes.make_space(5)
    result = _search(
        fakes.ScriptedReply(fakes.retained_document(space), input_tokens=400),
        fakes.ScriptedReply(fakes.usable_document(space, count=2), input_tokens=800),
        count=5,
    )
    assert result.telemetry.thin_bytes_per_token is not None
    assert result.telemetry.fat_bytes_per_token is not None
    assert result.telemetry.thin_bytes_per_token != result.telemetry.fat_bytes_per_token


def test_the_surfaced_ratio_is_the_BYTES_ACTUALLY_SENT_over_the_tokens_reported() -> None:
    """Checked against the request the fake selector received, not against the
    telemetry restating itself. The measurement is only worth surfacing if it is
    the real quotient of what went on the wire and what the provider counted."""
    space = fakes.make_space(5)
    result, selector = _search_with(
        fakes.ScriptedReply(fakes.retained_document(space), input_tokens=400),
        fakes.ScriptedReply(fakes.usable_document(space, count=2), input_tokens=800),
        count=5,
    )
    thin_request, fat_request = selector.requests
    thin_sent = len(thin_request.system.encode()) + len(thin_request.prompt.encode())
    fat_sent = len(fat_request.system.encode()) + len(fat_request.prompt.encode())
    assert result.telemetry.thin_bytes_per_token == pytest.approx(thin_sent / 400)
    assert result.telemetry.fat_bytes_per_token == pytest.approx(fat_sent / 800)


def test_a_thin_only_terminal_reports_thin_and_leaves_fat_null() -> None:
    """D3 — thin retained nothing above M, so no fat call was made. `None` means
    "not measured", which must stay distinguishable from a measured value."""
    space = fakes.make_space(ABOVE_M)
    result = _search(
        fakes.ScriptedReply(fakes.retained_empty_document(), input_tokens=4_500),
        count=ABOVE_M,
    )
    assert result.telemetry.thin_bytes_per_token is not None
    assert result.telemetry.fat_bytes_per_token is None


def test_a_zero_call_terminal_measures_nothing() -> None:
    """An abstention spends nothing, so there is no request to measure. Reporting
    0.0 here would enter the calibration series as a real observation."""
    result = _run(_request(count=0))
    assert result.status == "abstain_empty_space"
    assert result.telemetry.thin_bytes_per_token is None
    assert result.telemetry.fat_bytes_per_token is None
