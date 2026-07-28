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

**Not here, deliberately:** anything that requires a model reply. The stages are
P2.3; this file stops at `search.STAGE_CALL_SEAM` and one test asserts the spine
reaches exactly that boundary, which is how "no terminal below spends anything"
stays provable while the calling machinery does not yet exist.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from common.model_pool import ModelRoute, ModelSpec
from common.paths import PageType

from kdb_search import search
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

    with pytest.raises(NotImplementedError):  # small space: pre-flight passes
        _run(_request(count=5), selector=spec)

    large = _run(_request(count=2_000), selector=spec)
    assert large.status == "budget_exceeded"
    assert large.telemetry.eligible_space_size == 2_000


def test_a_space_that_fits_passes_the_preflight_and_reaches_the_call_seam() -> None:
    """The negative control, and the proof that the pre-flight is not simply
    always-fails. Reaching `STAGE_CALL_SEAM` is the correct P2.2 outcome: the
    spine ran every gate and stopped where money would be spent.
    """
    with pytest.raises(NotImplementedError, match="stage_call is P2.3"):
        _run(_request(count=5))


def test_the_seam_is_reached_only_AFTER_every_zero_spend_gate() -> None:
    """Ordering, from the other side: each zero-call terminal must return instead
    of falling through to the seam. If a gate were dropped, this would surface as
    `NotImplementedError` rather than a status."""
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
    so the exception comes from the call boundary rather than from a gate.

    Today the boundary raises `NotImplementedError`; P2.3 replaces it with a real
    call and this test keeps its meaning — no `except Exception` may appear
    between the caller and the stages.
    """
    with pytest.raises(NotImplementedError):
        _run(_request(count=5))


def test_the_seam_message_names_the_sub_phase_that_fills_it() -> None:
    """So the failure is legible to whoever hits it before P2.3 lands."""
    assert "P2.3" in search.STAGE_CALL_SEAM
