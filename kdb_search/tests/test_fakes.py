"""P2.0 — the fake selector's own contract (#123 blueprint §8, spec §2.3).

A test-support module needs tests for one specific reason: **every P2 assertion
about a response class is only as true as the canned document that produced it.**
`response.py:184` makes space membership the sole identity authority, so a canned
"usable" document whose slugs are not in the test's space classifies as
`all_entries_dropped` — and a test asserting `usable` would still pass, for the
wrong reason, in a way no amount of orchestration testing would reveal.

So each document here is driven through the **real** `validate_response` /
`validate_thin_retention` and pinned to the class its name claims. The fake's own
mechanics — script order, over-call, exception injection, `assert_consumed` — are
pinned for the same reason: a fake that silently replies twice to one script entry
would make the §8 call-count table unfalsifiable.
"""

from __future__ import annotations

import json

import openai
import pytest
from google.genai import errors as genai_errors

from common.call_model import ModelRequest
from kdb_search.constants import MAX_EXPRESSIONS
from kdb_search.response import Violations, validate_response, validate_thin_retention
from kdb_search.tests.fakes import (
    ALL_CAP_STOP_SPELLINGS,
    LABELS,
    STOP_LENGTH_GEMINI,
    STOP_OK_GEMINI,
    STOP_UNKNOWN,
    FakeScriptExhausted,
    FakeSelector,
    NeverCalled,
    ScriptedReply,
    all_dropped_document,
    context_length_rejection_gemini,
    context_length_rejection_openai,
    honest_empty_document,
    make_space,
    make_space_ref,
    retained_all_foreign_document,
    retained_document,
    retained_empty_document,
    retained_salvage_document,
    salvage_document,
    structurally_unusable_document,
    thin_structurally_unusable_document,
    thin_truncated_text,
    timeout_failure,
    transport_failure,
    truncated_text,
    unparseable_text,
    unrelated_bad_request,
    usable_document,
)

EXPRESSIONS = ("warren-buffett", "owner-earnings", "margin-of-safety")


def _request() -> ModelRequest:
    return ModelRequest(provider="gemini", model="gemini-3.6-flash", prompt="p", system="s")


def _validate(raw: str, space, *, max_results: int = 50):
    return validate_response(
        raw, space=space, expressions=EXPRESSIONS, max_results=max_results
    )


# ---------------------------------------------------------------------------
# the fake `call` — script mechanics
# ---------------------------------------------------------------------------


def test_replies_in_script_order_and_records_requests() -> None:
    space = make_space(4)
    fake = FakeSelector(
        ScriptedReply(retained_document(space)),
        ScriptedReply(usable_document(space, count=2)),
    )

    first = fake(_request())
    second = fake(ModelRequest(provider="openai", model="gpt-5.4-mini"))

    assert json.loads(first.text)["retained"] == ["ent-000", "ent-001", "ent-002", "ent-003"]
    assert len(json.loads(second.text)["selections"]) == 2
    assert fake.calls == 2
    assert [r.model for r in fake.requests] == ["gemini-3.6-flash", "gpt-5.4-mini"]
    fake.assert_consumed()


def test_response_echoes_the_requests_route_by_default() -> None:
    """`ModelStamp` fidelity is asserted off the response in P2.3, so the fake
    must not invent a route the request never named."""
    fake = FakeSelector(ScriptedReply(honest_empty_document()))
    response = fake(ModelRequest(provider="deepseek", model="deepseek-v4-flash"))
    assert (response.provider, response.model) == ("deepseek", "deepseek-v4-flash")


def test_scripted_reply_overrides_the_route_when_asked() -> None:
    fake = FakeSelector(ScriptedReply(honest_empty_document(), provider="x", model="y"))
    response = fake(_request())
    assert (response.provider, response.model) == ("x", "y")


def test_attempts_stays_one_so_transport_subretries_cannot_be_read_as_logical() -> None:
    """§8: SDK sub-retries are excluded from `logical_call_count == StageRecords`.
    The controller's attempt count is its own; nothing may source it from here."""
    fake = FakeSelector(ScriptedReply(honest_empty_document()))
    assert fake(_request()).attempts == 1


def test_input_tokens_are_settable() -> None:
    """The post-call input-side evidence for D7's `budget_estimation_miss`."""
    fake = FakeSelector(ScriptedReply(honest_empty_document(), input_tokens=412_000))
    assert fake(_request()).input_tokens == 412_000


def test_over_call_raises_script_exhausted() -> None:
    fake = FakeSelector(ScriptedReply(honest_empty_document()))
    fake(_request())
    with pytest.raises(FakeScriptExhausted, match="call #2 is unscripted"):
        fake(_request())


def test_script_exhausted_is_outside_every_injectable_retry_class() -> None:
    """The honest version of this claim.

    `AssertionError` is an `Exception`, so a broad `except Exception` *would*
    swallow an unscripted call — the fake cannot prevent that, and pinning
    "not an Exception" would be a test that can never fail. What is checkable is
    that it is outside every class the retry loop is allowed to catch, i.e. every
    failure type this module can inject. Combined with §2.1's no-catch-all
    posture, that is what makes an unscripted call propagate.
    """
    assert issubclass(FakeScriptExhausted, AssertionError)
    injectable = (openai.APIError, genai_errors.APIError)
    assert not isinstance(FakeScriptExhausted(), injectable)
    for factory in (
        transport_failure,
        timeout_failure,
        context_length_rejection_openai,
        context_length_rejection_gemini,
    ):
        assert isinstance(factory(), injectable), "an injectable failure must be catchable"


def test_assert_consumed_fails_when_a_branch_stops_early() -> None:
    fake = FakeSelector(
        ScriptedReply(honest_empty_document()), ScriptedReply(honest_empty_document())
    )
    fake(_request())
    with pytest.raises(AssertionError, match="1 of 2 scripted outcomes consumed"):
        fake.assert_consumed()


def test_never_called_names_the_violation() -> None:
    with pytest.raises(AssertionError, match="invoked on a zero-call path"):
        NeverCalled()(_request())


def test_zero_length_script_refuses_the_first_call() -> None:
    """The zero-call terminals can also be driven with an empty script; it must
    fail on call #1, not silently return."""
    with pytest.raises(FakeScriptExhausted, match="call #1 is unscripted"):
        FakeSelector()(_request())


# ---------------------------------------------------------------------------
# stop reasons — all three spellings present and distinct
# ---------------------------------------------------------------------------


def test_all_three_provider_cap_stop_spellings_are_offered_and_distinct() -> None:
    """D9.4 normalizes across three spellings; a fake offering two of them would
    leave the gemini path — the interim default selector's — uncovered."""
    assert ALL_CAP_STOP_SPELLINGS == ("length", "max_tokens", "MAX_TOKENS")
    assert len(set(ALL_CAP_STOP_SPELLINGS)) == 3


def test_unknown_stop_reason_is_neither_a_cap_stop_nor_a_normal_stop() -> None:
    """D9.4 forbids guessing an unknown stop reason into the budget class — only
    testable with a value that is genuinely outside both sets."""
    assert STOP_UNKNOWN not in ALL_CAP_STOP_SPELLINGS
    assert STOP_UNKNOWN not in {"stop", "end_turn", "STOP"}


def test_stop_reason_reaches_the_response_verbatim() -> None:
    """Raw, not normalized: the raw value is the archived evidence."""
    fake = FakeSelector(ScriptedReply(unparseable_text(), stop_reason=STOP_LENGTH_GEMINI))
    assert fake(_request()).stop_reason == "MAX_TOKENS"


@pytest.mark.parametrize(
    "provider, expected",
    [
        ("gemini", "STOP"),
        ("anthropic", "end_turn"),
        ("openai", "stop"),
        ("deepseek", "stop"),
    ],
)
def test_default_stop_reason_is_the_ROUTES_ordinary_completion(provider, expected) -> None:
    """A fixed default would hand an openai-compat request gemini's `"STOP"` — a
    finish reason that route never emits — and a normalizer keyed to the wrong
    family would pass on it."""
    fake = FakeSelector(ScriptedReply(honest_empty_document()))
    assert fake(ModelRequest(provider=provider, model="m")).stop_reason == expected


def test_gemini_default_matches_the_interim_selector() -> None:
    fake = FakeSelector(ScriptedReply(honest_empty_document()))
    assert fake(_request()).stop_reason == STOP_OK_GEMINI


def test_stop_reason_none_survives_as_an_explicit_value() -> None:
    """A route may report no stop reason at all, so `None` must not be captured by
    the route-default sentinel."""
    fake = FakeSelector(ScriptedReply(honest_empty_document(), stop_reason=None))
    assert fake(_request()).stop_reason is None


# ---------------------------------------------------------------------------
# failure injection — the real SDK types escape `call_model` unwrapped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory, expected",
    [
        (transport_failure, openai.APIConnectionError),
        (timeout_failure, openai.APITimeoutError),
        (context_length_rejection_openai, openai.BadRequestError),
        (unrelated_bad_request, openai.BadRequestError),
        (context_length_rejection_gemini, genai_errors.ClientError),
    ],
)
def test_injected_failures_are_the_real_sdk_exception_types(factory, expected) -> None:
    """`common/call_model.py` catches nothing (retry lives in
    `call_model_retry.py`, and §8 adopts pass-1's bare-`call_model` posture), so
    P2.3's retry-class predicate is written against these concrete types."""
    fake = FakeSelector(factory())
    with pytest.raises(expected):
        fake(_request())
    assert fake.calls == 1, "a raising call still counts as a logical attempt"


def test_context_length_rejection_is_distinguishable_from_an_unrelated_400() -> None:
    """Both are `BadRequestError`; only one is D7's `budget_estimation_miss`. If
    these were indistinguishable, every malformed request would be typed a budget
    event."""
    miss = context_length_rejection_openai()
    other = unrelated_bad_request()
    assert (miss.status_code, other.status_code) == (400, 400)
    assert miss.code == "context_length_exceeded"
    assert other.code != "context_length_exceeded"


def test_gemini_context_length_rejection_carries_its_own_wording() -> None:
    error = context_length_rejection_gemini()
    assert error.code == 400
    assert "input token count exceeds" in error.message


# ---------------------------------------------------------------------------
# canned fat documents — driven through the real validator
# ---------------------------------------------------------------------------


def test_usable_document_is_usable_against_the_space_it_was_built_from() -> None:
    space = make_space(6)
    result = _validate(usable_document(space, count=3), space)
    assert result.classification == "usable"
    assert [hit.slug for hit in result.hits] == ["ent-000", "ent-001", "ent-002"]
    assert result.returned_entries == 3
    assert result.attempted_violations.foreign_slug == 0


def test_usable_document_against_a_DIFFERENT_space_collapses_to_all_dropped() -> None:
    """The exact silent-pass this module's coupling rule exists to prevent: same
    document, disjoint space, and the class flips with nothing else changing."""
    built_from = make_space(6)
    disjoint = tuple(
        entity.__class__(slug=f"other-{i}", title=entity.title, page_type=entity.page_type)
        for i, entity in enumerate(built_from)
    )
    assert _validate(usable_document(built_from, count=3), disjoint).classification == (
        "all_entries_dropped"
    )


def test_usable_document_attributes_the_labels_it_carries() -> None:
    space = make_space(3)
    result = _validate(usable_document(space, count=1, matched=("A", "C")), space)
    assert result.hits[0].matched_expressions == ("warren-buffett", "margin-of-safety")


def test_usable_document_can_carry_the_advisory_unresolved_list() -> None:
    space = make_space(3)
    result = _validate(usable_document(space, count=1, unresolved=("B",)), space)
    assert result.advisory_unresolved == (1,)


def test_salvage_document_is_exactly_six_of_ten() -> None:
    """Joseph's rule, as a measurement rather than a claim: 10 returned, 1
    duplicate, 3 unusable ⇒ the 6 good slugs are kept."""
    space = make_space(8)
    result = _validate(salvage_document(space), space)
    assert result.classification == "usable"
    assert result.returned_entries == 10
    assert len(result.hits) == 6
    assert result.valid_entry_yield == pytest.approx(0.6)
    assert result.attempted_violations.duplicate_slug == 1
    assert result.attempted_violations.foreign_slug == 2
    assert result.attempted_violations.malformed_entry == 1


def test_honest_empty_document_is_usable_not_a_failure_class() -> None:
    """Spec §2.3 case 4 — and its yield is `None`, not 0.0 (D9.6)."""
    space = make_space(3)
    result = _validate(honest_empty_document(), space)
    assert result.classification == "usable"
    assert result.hits == ()
    assert result.valid_entry_yield is None
    assert result.should_retry is False


def test_structurally_unusable_document_classifies_as_such() -> None:
    space = make_space(3)
    result = _validate(structurally_unusable_document(), space)
    assert result.classification == "structurally_unusable_response"
    assert result.should_retry is True


def test_all_dropped_document_classifies_as_all_entries_dropped() -> None:
    space = make_space(3)
    result = _validate(all_dropped_document(space), space)
    assert result.classification == "all_entries_dropped"
    assert result.returned_entries == 4
    assert result.hits == ()
    assert result.valid_entry_yield == 0.0
    assert result.should_retry is True


def test_unparseable_text_classifies_as_unparseable() -> None:
    space = make_space(3)
    result = _validate(unparseable_text(), space)
    assert result.classification == "unparseable_response"
    assert result.returned_entries == 0
    assert result.valid_entry_yield is None


def test_truncated_text_is_unparseable_so_the_output_terminal_has_a_producer() -> None:
    """The D9 conjunction is *cap stop AND no usable document*; this supplies the
    second half, and is genuinely cut off rather than merely short."""
    space = make_space(8)
    raw = truncated_text(space)
    assert _validate(raw, space).classification == "unparseable_response"
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


# ---------------------------------------------------------------------------
# canned thin documents — driven through the real thin validator
# ---------------------------------------------------------------------------


def test_retained_document_retains_the_whole_space_by_default() -> None:
    space = make_space(5)
    slugs = json.loads(retained_document(space))["retained"]
    retained, violations = validate_thin_retention(slugs, space=space, cap=100)
    assert retained == tuple(entity.slug for entity in space)
    assert violations == Violations()


def test_retained_document_honours_count_and_stays_ranked() -> None:
    space = make_space(5)
    assert json.loads(retained_document(space, count=2))["retained"] == ["ent-000", "ent-001"]


def test_retained_empty_document_retains_nothing() -> None:
    """D3's producer — `completed`/no-fat-call over N > M."""
    space = make_space(5)
    slugs = json.loads(retained_empty_document())["retained"]
    retained, _ = validate_thin_retention(slugs, space=space, cap=100)
    assert retained == ()


def test_thin_empty_and_thin_all_foreign_validate_IDENTICALLY() -> None:
    """The sharpest distinction in the two-stage flow, pinned as a measurement.

    Both documents validate to `retained == ()`. One is D3's `thin_retained_zero`
    terminal (`completed`, no fat call, **no retry**); the other is
    `all_entries_dropped` (**an allowed retry class**). So the controller cannot
    branch on the validated list — it must branch on the response class, and a
    controller that gets this wrong reads a malfunctioning selector as an honest
    empty. This test exists to make that indistinguishability explicit rather than
    leaving it to be discovered by a P2.3 bug.
    """
    space = make_space(5)
    empty = json.loads(retained_empty_document())["retained"]
    foreign = json.loads(retained_all_foreign_document(space))["retained"]

    empty_retained, empty_violations = validate_thin_retention(empty, space=space, cap=100)
    foreign_retained, foreign_violations = validate_thin_retention(foreign, space=space, cap=100)

    assert empty_retained == foreign_retained == ()
    # The documents themselves are what differ: one returned nothing, the other
    # returned three identities that do not exist.
    assert empty == []
    assert len(foreign) == 3
    assert empty_violations == Violations()
    assert foreign_violations.foreign_slug == 3


def test_thin_structurally_unusable_document_is_thin_shaped() -> None:
    """Thin's document-level failure is a missing/invalid `retained`, not a
    missing `selections` — a shared fixture would test the fat key here."""
    document = json.loads(thin_structurally_unusable_document())
    assert "selections" not in document
    assert not isinstance(document.get("retained"), list)


def test_thin_truncated_text_is_a_severed_retained_list() -> None:
    """`THIN_OUTPUT_TRUNCATION`'s stage-correct producer."""
    space = make_space(8)
    raw = thin_truncated_text(space)
    assert raw.startswith('{"retained":[')
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


def test_retained_salvage_document_exercises_all_three_thin_drop_classes() -> None:
    space = make_space(5)
    slugs = json.loads(retained_salvage_document(space))["retained"]
    retained, violations = validate_thin_retention(slugs, space=space, cap=100)
    assert retained == ("ent-000", "ent-001")
    assert violations.foreign_slug == 1
    assert violations.duplicate_slug == 1
    assert violations.malformed_entry == 1


# ---------------------------------------------------------------------------
# the space fixtures
# ---------------------------------------------------------------------------


def test_space_is_slug_ascending_and_page_types_are_real() -> None:
    space = make_space(7)
    slugs = [entity.slug for entity in space]
    assert slugs == sorted(slugs)
    assert {entity.page_type for entity in space} == {"summary", "concept", "article"}


def test_space_ref_carries_the_same_rows_the_documents_are_built_from() -> None:
    ref = make_space_ref(4)
    assert ref.entities == make_space(4)
    assert ref.graph_ref.active_entity_count == 4
    assert ref.scope_kind == "domain_subtree"
    assert ref.domain == "investing"


def test_wire_labels_are_hardcoded_and_cover_max_expressions() -> None:
    """Hardcoded on purpose (D11): wire bytes are inputs, not expectations, so
    deriving them from `expression_labels()` would give the alphabet a fourth
    synchronized source and hide a mutation to it from every P2 test at once. The
    length is still pinned, because a `LABELS` shorter than `MAX_EXPRESSIONS`
    would silently cap what the fake can express."""
    assert LABELS == ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")
    assert len(LABELS) == MAX_EXPRESSIONS
