"""#123 P2.3 — `stage_call`: attempts, records, and the post-call classifications.

**What these tests are oracles for**, beyond "the loop works":

  * **The retry/terminal split.** Four outcomes leave this function and only one
    is ordinary. Every test that asserts an outcome also asserts the *script was
    fully consumed* (`FakeSelector.assert_consumed`), because "never retried" is a
    claim about a call that did not happen, and an outcome assertion alone passes
    whether the second attempt fired or not.
  * **D9.3's conjunction, from both sides.** A cap stop with a complete usable
    document is R1 salvage; a cap stop with no usable document is the terminal.
    Two tests, same stop reason, opposite outcomes — which is the only way to show
    the predicate is a conjunction rather than a cap-stop test that happens to
    pass its positive case.
  * **The normalizer as a unit.** The anthropic row is unreachable through
    `graph_search` (P2.2 rejects anthropic routes over `json_mode`), so the
    ratified per-route stop-reason table is driven directly. Testing it only
    through the orchestrator would have left one third of a closed map uncovered
    while looking covered.
  * **The negative cases are the real ones.** `unrelated_bad_request()` must
    propagate, `STOP_UNKNOWN` must never become a budget class, and an
    `all_entries_dropped` response must retry rather than truncate. Each of those
    is a case where the naive implementation is green on every positive test.
"""

from __future__ import annotations

import pytest
from common.call_model import ModelRequest, ModelResponse
from common.model_pool import ModelRoute, ModelSpec

from kdb_search import stage
from kdb_search.artifact import SPACE_MANIFEST_REF
from kdb_search.budget import BudgetVerdict, provider_max_tokens, visible_output_allowance
from kdb_search.constants import EXCERPT_POLICY_VERSION, M, MAX_ATTEMPTS_PER_STAGE
from kdb_search.prompts import load_template
from kdb_search.response import (
    validate_response,
    validate_thin_response,
)
from kdb_search.tests import fakes

SPACE = fakes.make_space(6)
EXPRESSIONS = ("alpha", "beta")


def _spec(**overrides) -> ModelSpec:
    base = dict(
        id="test-selector",
        provider="deepseek",
        model="test-model",
        route=ModelRoute("openai_compat", "https://example.invalid", "DEEPSEEK_API_KEY"),
        ctx_window=400_000,
        max_output_tokens=128_000,
        tokens_lte_bytes=True,
        price_in=1.0,
        price_out=2.0,
    )
    return ModelSpec(**{**base, **overrides})


def _messages(stage_name: str = "thin"):
    from kdb_search import projection, prompts

    evidence = "\n".join(projection.render_thin_line(e) for e in SPACE)
    if stage_name == "thin":
        return prompts.render_thin_messages(evidence=evidence, query="QUERY TEXT")
    return prompts.render_fat_messages(
        evidence=evidence, query="QUERY TEXT", max_results=50
    )


def _verdict(stage_name: str = "thin") -> BudgetVerdict:
    return BudgetVerdict(
        fits=True,
        stage=stage_name,
        estimated_input_tokens=1_234,
        reserved_output_tokens=29_000,
        context_budget_tokens=320_000,
    )


def _thin_validate(raw: str):
    return validate_thin_response(raw, space=SPACE, cap=M)


def _fat_validate(raw: str):
    return validate_response(raw, space=SPACE, expressions=EXPRESSIONS, max_results=50)


def _run(
    *script,
    stage_name: str = "thin",
    spec: ModelSpec | None = None,
    evidence: dict | str = SPACE_MANIFEST_REF,
) -> tuple[stage.StageOutcome, fakes.FakeSelector]:
    selector = fakes.FakeSelector(*script)
    outcome = stage.stage_call(
        stage_name,
        messages=_messages(stage_name),
        evidence=evidence,
        spec=spec or _spec(),
        call=selector,
        validate=_thin_validate if stage_name == "thin" else _fat_validate,
        verdict=_verdict(stage_name),
    )
    return outcome, selector


# --------------------------------------------------------------------------
# 1. stop-reason normalization (D9.4) — the closed map, driven directly
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("api_call_type", "raw"),
    [
        ("openai_compat", fakes.STOP_LENGTH_OPENAI),
        ("anthropic", fakes.STOP_LENGTH_ANTHROPIC),
        ("gemini", fakes.STOP_LENGTH_GEMINI),
    ],
)
def test_every_provider_cap_stop_spelling_normalizes_to_output_cap(
    api_call_type: str, raw: str
) -> None:
    """The gap #124 records: both existing repo predicates match `"length"` and
    `"max_tokens"` only, so gemini's `"MAX_TOKENS"` — the interim DEFAULT
    selector's spelling — is invisible to them. All three rows here."""
    assert stage.normalize_stop_reason(raw, api_call_type=api_call_type) == "output_cap"


@pytest.mark.parametrize(
    ("api_call_type", "raw"),
    [
        ("openai_compat", fakes.STOP_OK_OPENAI),
        ("anthropic", fakes.STOP_OK_ANTHROPIC),
        ("gemini", fakes.STOP_OK_GEMINI),
    ],
)
def test_every_ordinary_completion_normalizes_to_complete(
    api_call_type: str, raw: str
) -> None:
    """A predicate carrying only the cap set would call these `"unknown"` — and
    the no-guessing rule would then be vacuous, since everything unknown is
    already excluded from the budget class."""
    assert stage.normalize_stop_reason(raw, api_call_type=api_call_type) == "complete"


def test_a_cap_spelling_from_the_WRONG_family_is_not_a_cap_stop() -> None:
    """The map is per-`api_call_type` for a reason. `"max_tokens"` is anthropic's
    cap stop and is not a value an openai-compatible route emits — accepting it
    anywhere would make the three rows one flat set and lose the property that
    each route is checked against its own vocabulary."""
    assert (
        stage.normalize_stop_reason(
            fakes.STOP_LENGTH_ANTHROPIC, api_call_type="openai_compat"
        )
        == "unknown"
    )


@pytest.mark.parametrize("raw", [fakes.STOP_UNKNOWN, None, "", "totally-new-reason"])
def test_an_unknown_stop_reason_is_never_guessed(raw) -> None:
    """D9.4. `None` is in here because a route may report no stop reason at all,
    and "absent" must not read as "fine" any more than it reads as "capped"."""
    assert stage.normalize_stop_reason(raw, api_call_type="gemini") == "unknown"


def test_the_anthropic_row_exists_even_though_graph_search_rejects_the_route() -> None:
    """Recorded as a deliberate asymmetry. `search._require_json_mode_capable`
    refuses anthropic selector routes, so this row cannot be reached end-to-end —
    but it is a stop-reason table, not a capability table, and dropping the row
    would silently mis-type anthropic truncations the day `call_model` grows
    `json_mode` for that path."""
    assert "anthropic" in stage._CAP_STOPS
    assert "anthropic" in stage._OK_STOPS


# --------------------------------------------------------------------------
# 2. the context-length predicate (D7)
# --------------------------------------------------------------------------


def test_the_openai_over_window_rejection_is_recognized() -> None:
    assert stage.is_context_length_rejection(fakes.context_length_rejection_openai())


def test_the_gemini_over_window_rejection_is_recognized() -> None:
    """The gemini form carries no machine-readable code — only `INVALID_ARGUMENT`
    and a message — so it needs its own arm of the predicate. Without it the
    interim default selector's D7 miss would propagate as an unexpected defect."""
    assert stage.is_context_length_rejection(fakes.context_length_rejection_gemini())


def test_an_UNRELATED_400_is_not_a_budget_event() -> None:
    """The case that makes the predicate worth having. A 400 over a bad
    temperature is a defect in what we sent; reporting it as `budget_estimation_
    miss` would blame the estimator for our own malformed request and file the
    event in the D7 series."""
    assert not stage.is_context_length_rejection(fakes.unrelated_bad_request())


def test_a_transport_failure_is_not_a_budget_event() -> None:
    assert not stage.is_context_length_rejection(fakes.transport_failure())


# --------------------------------------------------------------------------
# 3. the ordinary path + the request contract
# --------------------------------------------------------------------------


def test_a_usable_first_attempt_produces_exactly_one_record() -> None:
    outcome, selector = _run(
        fakes.ScriptedReply(fakes.retained_document(SPACE, count=3))
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.attempts == 1
    assert outcome.retry_attempts == 0
    assert outcome.validated.retained == tuple(e.slug for e in SPACE[:3])
    assert outcome.failure_class is None
    assert outcome.budget_record is None


@pytest.mark.parametrize("stage_name", ["thin", "fat"])
def test_json_mode_is_set_on_EVERY_selector_request(stage_name: str) -> None:
    """The ratified requirement, both stages. Mirrors
    `compiler/tests/test_compile_source.py:139`'s regression pin: pass-2 shipped
    once without it, and a selector that free-forms its JSON fails as an
    `unparseable_response` — a *selector-quality* reading of our own omission."""
    document = (
        fakes.retained_document(SPACE) if stage_name == "thin" else fakes.usable_document(SPACE)
    )
    _, selector = _run(fakes.ScriptedReply(document), stage_name=stage_name)
    assert [request.json_mode for request in selector.requests] == [True]


@pytest.mark.parametrize("stage_name", ["thin", "fat"])
def test_max_tokens_is_the_PROVIDER_TOTAL_not_the_visible_allowance(
    stage_name: str,
) -> None:
    """D9 keeps four output quantities apart. Sending the visible allowance would
    cap the completion below the envelope the route was validated against at
    resolution, so the hidden reserve would be spent out of the visible budget and
    every long response would truncate."""
    document = (
        fakes.retained_document(SPACE) if stage_name == "thin" else fakes.usable_document(SPACE)
    )
    _, selector = _run(fakes.ScriptedReply(document), stage_name=stage_name)
    sent = selector.requests[0].max_tokens
    assert sent == provider_max_tokens(stage_name)
    assert sent > visible_output_allowance(stage_name)


def test_the_request_carries_the_ROUTE_not_just_the_provider_name() -> None:
    """`ModelRequest.route` is authoritative in #121's dispatch — its
    `api_call_type` alone selects the handler. Omitting it would silently fall
    back to the Class-B registry row for `provider`, which for a custom
    `base_url` route is a different endpoint entirely."""
    spec = _spec()
    _, selector = _run(fakes.ScriptedReply(fakes.retained_document(SPACE)), spec=spec)
    assert selector.requests[0].route is spec.route


def test_the_rendered_messages_reach_the_provider_as_system_plus_prompt() -> None:
    messages = _messages("thin")
    _, selector = _run(fakes.ScriptedReply(fakes.retained_document(SPACE)))
    assert selector.requests[0].system == messages.system
    assert selector.requests[0].prompt == messages.user


# --------------------------------------------------------------------------
# 4. records — one per logical attempt, failures included
# --------------------------------------------------------------------------


def test_a_retry_produces_TWO_records_and_the_failure_is_archived() -> None:
    """§6's `logical_call_count == len(StageRecords)` holds by construction, so
    the thing worth pinning is that a *failed* attempt still gets a record: the
    malformed and the timed-out attempts are exactly the failure-audit cases."""
    outcome, selector = _run(
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.retained_document(SPACE, count=2)),
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.attempts == 2
    assert outcome.retry_attempts == 1
    first, second = outcome.records
    assert (first.attempt, second.attempt) == (1, 2)
    assert first.failure.failure_class == "unparseable_response"
    assert first.raw_response_text == fakes.unparseable_text()
    assert second.failure is None


def test_a_record_carries_the_prompt_ref_model_stamp_and_evidence() -> None:
    outcome, _ = _run(fakes.ScriptedReply(fakes.retained_document(SPACE)))
    record = outcome.records[0]
    assert record.prompt == load_template("thin").ref
    assert record.stage == "thin_selection"
    assert (record.model.provider, record.model.model) == ("deepseek", "test-model")
    assert record.model.route == "openai_compat"
    assert record.evidence == SPACE_MANIFEST_REF


def test_cost_is_computed_from_the_route_prices_and_the_attempt_tokens() -> None:
    """Per attempt, not per stage: every attempt is billed, including the ones
    whose response was unusable, and a per-stage figure would hide that."""
    outcome, _ = _run(
        fakes.ScriptedReply(
            fakes.retained_document(SPACE), input_tokens=2_000_000, output_tokens=1_000_000
        ),
        spec=_spec(price_in=3.0, price_out=5.0),
    )
    assert outcome.records[0].cost == pytest.approx(3.0 * 2 + 5.0 * 1)


def test_thin_records_carry_retained_identities_and_no_excerpt_policy() -> None:
    outcome, _ = _run(fakes.ScriptedReply(fakes.retained_document(SPACE, count=2)))
    record = outcome.records[0]
    assert record.retained_identities == tuple(e.slug for e in SPACE[:2])
    assert record.excerpt_policy_version is None


def test_fat_records_carry_the_excerpt_policy_and_no_retained_identities() -> None:
    """The two stage-specific `StageRecord` fields, each asserted absent on the
    other stage — a record that filled both would archive a thin retention for a
    fat call and make the replay reader's stage inference wrong."""
    outcome, _ = _run(
        fakes.ScriptedReply(fakes.usable_document(SPACE)),
        stage_name="fat",
        evidence={SPACE[0].slug: "body text"},
    )
    record = outcome.records[0]
    assert record.excerpt_policy_version == EXCERPT_POLICY_VERSION
    assert record.retained_identities is None
    assert record.evidence == {SPACE[0].slug: "body text"}


def test_parsed_output_comes_from_the_validator_not_a_second_parse() -> None:
    """`StageRecord.parsed_output` is the document validation actually ran on. A
    second `json.loads` at the record site would be a second source, and the
    archived document could then differ from the one the hits were drawn from."""
    outcome, _ = _run(fakes.ScriptedReply(fakes.retained_document(SPACE, count=2)))
    assert outcome.records[0].parsed_output == {
        "retained": [e.slug for e in SPACE[:2]]
    }


def test_parsed_output_is_None_when_there_was_nothing_to_parse() -> None:
    outcome, _ = _run(
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.unparseable_text()),
    )
    assert [r.parsed_output for r in outcome.records] == [None, None]
    assert outcome.records[0].raw_response_text == fakes.unparseable_text()


def test_the_validation_split_separates_dropped_from_coerced() -> None:
    """Only `unknown_expression` is a coercion — an unrecognized label costs the
    entry its attribution, never the entry. Collapsing the two into one count
    would make a hallucinating selector and a label-confused one look alike."""
    outcome, _ = _run(
        fakes.ScriptedReply(fakes.retained_salvage_document(SPACE)),
    )
    validation = outcome.records[0].validation
    assert validation.dropped == {
        "foreign_slug": 1,
        "malformed_entry": 1,
        "duplicate_slug": 1,
    }
    assert validation.coerced == {}
    assert validation.counts["returned_entries"] == 5
    assert validation.counts["validated_entries"] == 2


@pytest.mark.parametrize(
    ("api_call_type", "expected"), [("openai_compat", 2), ("gemini", 0)]
)
def test_the_record_carries_the_route_s_OWN_sdk_sub_retry_allowance(
    api_call_type: str, expected: int
) -> None:
    """§8 G5, verified per family at the constructor: the openai client is
    given `max_retries=2` explicitly, google-genai has no such kwarg. Without
    this number, one logical attempt against gemini and one against an
    openai-compatible route look identical in the archive while the second may
    have hit the provider three times."""
    spec = _spec(
        provider="gemini" if api_call_type == "gemini" else "deepseek",
        route=ModelRoute(api_call_type, None, "GEMINI_API_KEY"),
    )
    outcome, _ = _run(fakes.ScriptedReply(fakes.retained_document(SPACE)), spec=spec)
    assert outcome.records[0].sdk_sub_retries == expected


def test_sdk_sub_retries_are_NOT_counted_as_logical_attempts() -> None:
    """The identity §6 rests on. A route that allows two SDK sub-retries still
    produces exactly one `StageRecord` for one logical attempt — folding them in
    would make `logical_call_count` count events we never decided to make."""
    outcome, _ = _run(fakes.ScriptedReply(fakes.retained_document(SPACE)))
    assert outcome.records[0].sdk_sub_retries == 2
    assert outcome.attempts == 1


def test_a_retry_is_IMMEDIATE_with_no_backoff(monkeypatch) -> None:
    """§8 G5b — deliberately pass-1's posture (precedent
    `ingestion/enrich/pass1_caller.py:179`), recorded as an adoption rather than
    an oversight. Asserted by making a sleep fail: a backoff layer added later
    would be a real change to the cost/latency profile and should have to break
    this test to arrive."""
    import time

    monkeypatch.setattr(
        time, "sleep", lambda *_: pytest.fail("the retry loop must not back off")
    )
    outcome, selector = _run(
        fakes.transport_failure(), fakes.ScriptedReply(fakes.retained_document(SPACE))
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"


# --------------------------------------------------------------------------
# 5. the retry classes (§8 B11)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("document", "expected_class"),
    [
        (fakes.unparseable_text(), "unparseable_response"),
        (fakes.thin_structurally_unusable_document(), "structurally_unusable_response"),
        (fakes.retained_all_foreign_document(SPACE), "all_entries_dropped"),
    ],
)
def test_every_allowed_retry_class_exhausts_after_two_attempts(
    document: str, expected_class: str
) -> None:
    outcome, selector = _run(
        fakes.ScriptedReply(document), fakes.ScriptedReply(document)
    )
    selector.assert_consumed()
    assert outcome.outcome == "exhausted"
    assert outcome.attempts == MAX_ATTEMPTS_PER_STAGE
    assert outcome.failure_class == expected_class


def test_the_honest_empty_is_NOT_retried_but_all_foreign_IS() -> None:
    """The sharpest distinction in the stage, and the one a controller branching
    on the validated list collapses: both documents validate to `retained == ()`.

    `{"retained": []}` is a selector that looked and found nothing — D3's
    terminal, never retried. All-foreign is a selector that hallucinated — an
    allowed retry class. Scripting exactly one reply for the first case is what
    proves it: a second attempt would raise `FakeScriptExhausted`.
    """
    honest, honest_selector = _run(fakes.ScriptedReply(fakes.retained_empty_document()))
    honest_selector.assert_consumed()
    assert honest.outcome == "usable"
    assert honest.attempts == 1
    assert honest.validated.retained == ()

    foreign, foreign_selector = _run(
        fakes.ScriptedReply(fakes.retained_all_foreign_document(SPACE)),
        fakes.ScriptedReply(fakes.retained_all_foreign_document(SPACE)),
    )
    foreign_selector.assert_consumed()
    assert foreign.outcome == "exhausted"
    # And nothing consumable survives the exhaustion, though the attempts are
    # archived — see `StageOutcome.validated`. Both documents validate to the
    # same empty retention; only one of them is an answer.
    assert foreign.validated is None
    assert foreign.records[-1].retained_identities == ()


def test_a_transport_failure_is_retried_and_recorded_as_transport() -> None:
    outcome, selector = _run(
        fakes.transport_failure(), fakes.ScriptedReply(fakes.retained_document(SPACE))
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.records[0].failure.failure_class == "transport"
    assert outcome.records[0].raw_response_text is None
    assert outcome.records[0].stop_reason_raw is None


def test_a_timeout_is_recorded_as_TIMEOUT_not_transport() -> None:
    """`APITimeoutError` subclasses `APIConnectionError`, so the obvious
    `isinstance` ordering silently files every timeout as a transport fault. §8
    B11 lists them separately because they are different operational findings: a
    route that only ever times out is over-loaded, not unreachable."""
    outcome, _ = _run(fakes.timeout_failure(), fakes.timeout_failure())
    assert [r.failure.failure_class for r in outcome.records] == ["timeout", "timeout"]
    assert outcome.outcome == "exhausted"
    assert outcome.failure_class == "timeout"


def test_an_unrelated_bad_request_PROPAGATES_rather_than_becoming_a_failure() -> None:
    """§2.1's fail-hard posture. A catch-all `except Exception` would turn our own
    malformed request into `selector_failure` — blaming the model for a
    misconfiguration, and filing it in the §8.4 selector-quality series."""
    import openai

    with pytest.raises(openai.BadRequestError):
        _run(fakes.unrelated_bad_request())


# --------------------------------------------------------------------------
# 6. D9.3 — the post-call OUTPUT terminal, and its conjunction
# --------------------------------------------------------------------------


def test_a_cap_stop_with_no_usable_document_is_the_truncation_terminal() -> None:
    outcome, selector = _run(
        fakes.ScriptedReply(
            fakes.thin_truncated_text(SPACE), stop_reason=fakes.STOP_LENGTH_OPENAI
        )
    )
    selector.assert_consumed()
    assert outcome.outcome == "output_truncation"
    assert outcome.attempts == 1
    assert outcome.failure_class == "output_truncation"
    record = outcome.budget_record
    assert (record.detected, record.budget_side) == ("post_call", "output")
    assert record.fits is False


def test_the_truncated_attempt_archives_the_stop_reason_RAW_and_normalized() -> None:
    """Both, per D9.4. The raw value is the evidence and the normalized value is
    the decision; keeping only the decision makes "an unknown stop reason was
    never guessed" an unverifiable claim about past runs."""
    outcome, _ = _run(
        fakes.ScriptedReply(
            fakes.thin_truncated_text(SPACE), stop_reason=fakes.STOP_LENGTH_OPENAI
        )
    )
    record = outcome.records[0]
    assert record.stop_reason_raw == fakes.STOP_LENGTH_OPENAI
    assert record.stop_reason_normalized == "output_cap"
    assert outcome.budget_record.finish_reason_raw == fakes.STOP_LENGTH_OPENAI
    assert outcome.budget_record.finish_reason_normalized == "output_cap"


def test_the_truncation_terminal_is_NEVER_retried() -> None:
    """Scripted with one reply against a two-attempt budget: a retry raises
    `FakeScriptExhausted`. Deterministic — the same rendered request produces the
    same overflow — so a second attempt is pure spend."""
    _, selector = _run(
        fakes.ScriptedReply(
            fakes.thin_truncated_text(SPACE), stop_reason=fakes.STOP_LENGTH_OPENAI
        )
    )
    selector.assert_consumed()


def test_a_cap_stop_on_a_COMPLETE_usable_document_is_validated_normally() -> None:
    """R1's salvage rule, and the other half of D9.3's conjunction. The repo has
    already ruled on this shape once — `compiler.py:405-409` treats a cap stop as
    carrier metadata, pinned by `test_compiler_recovery.py:200-224`. A cap-stop
    test that ignored the document would discard a perfectly good selection."""
    outcome, selector = _run(
        fakes.ScriptedReply(
            fakes.retained_document(SPACE, count=3), stop_reason=fakes.STOP_LENGTH_OPENAI
        )
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.validated.retained == tuple(e.slug for e in SPACE[:3])
    # The stop is recorded even though it changed nothing — that is the telemetry
    # the D7 selector-admission series reads.
    assert outcome.records[0].stop_reason_normalized == "output_cap"
    assert outcome.budget_record is None


def test_a_cap_stop_on_an_ALL_DROPPED_document_retries_rather_than_truncating() -> None:
    """The boundary of "complete usable document". Every entry was rejected on
    *identity* grounds — the document itself parsed and was structurally whole —
    so this is a selector-quality event and an allowed retry class, not a
    truncation. Typing it as a budget miss would never retry the one case §8 B11
    says to retry."""
    document = fakes.retained_all_foreign_document(SPACE)
    outcome, selector = _run(
        fakes.ScriptedReply(document, stop_reason=fakes.STOP_LENGTH_OPENAI),
        fakes.ScriptedReply(fakes.retained_document(SPACE, count=1)),
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.attempts == 2


def test_an_UNKNOWN_stop_reason_with_a_bad_document_retries_as_an_ordinary_class() -> None:
    """D9.4's no-guessing rule, at the one site where guessing would cost money's
    worth of wrong accounting: `SAFETY` is not a cap stop, so the unparseable
    response is an ordinary retry class rather than a budget terminal."""
    outcome, selector = _run(
        fakes.ScriptedReply(fakes.unparseable_text(), stop_reason=fakes.STOP_UNKNOWN),
        fakes.ScriptedReply(fakes.retained_document(SPACE, count=1)),
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.records[0].stop_reason_normalized == "unknown"
    assert outcome.records[0].failure.failure_class == "unparseable_response"


def test_a_gemini_cap_stop_is_classified_on_a_gemini_route() -> None:
    """End-to-end on the interim default selector's own route and spelling — the
    combination the flat `"length"` predicate misses (#124)."""
    outcome, _ = _run(
        fakes.ScriptedReply(
            fakes.thin_truncated_text(SPACE), stop_reason=fakes.STOP_LENGTH_GEMINI
        ),
        spec=_spec(provider="gemini", route=ModelRoute("gemini", None, "GEMINI_API_KEY")),
    )
    assert outcome.outcome == "output_truncation"


def test_the_truncation_check_runs_BEFORE_the_generic_retry_path() -> None:
    """Ordering, asserted by the outcome that only one ordering produces. The
    truncated document is *also* an `unparseable_response`, so a loop that
    retried first would spend a second attempt and land on `exhausted`."""
    outcome, selector = _run(
        fakes.ScriptedReply(
            fakes.thin_truncated_text(SPACE), stop_reason=fakes.STOP_LENGTH_OPENAI
        ),
        fakes.ScriptedReply(fakes.retained_document(SPACE)),
    )
    assert outcome.outcome == "output_truncation"
    assert selector.calls == 1


# --------------------------------------------------------------------------
# 7. D7 — the post-call INPUT terminal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rejection",
    [fakes.context_length_rejection_openai, fakes.context_length_rejection_gemini],
)
def test_an_over_window_rejection_is_a_post_call_INPUT_budget_event(rejection) -> None:
    outcome, selector = _run(rejection())
    selector.assert_consumed()
    assert outcome.outcome == "input_estimation_miss"
    assert outcome.attempts == 1
    assert outcome.failure_class == "budget_estimation_miss"
    record = outcome.budget_record
    assert (record.detected, record.budget_side) == ("post_call", "input")
    assert record.fits is False
    assert record.budget_estimate_tokens == _verdict().estimated_input_tokens


def test_the_estimation_miss_is_never_retried() -> None:
    """One scripted rejection against a two-attempt budget. The same rendered
    bytes would be refused identically, so a retry is spend with a known
    outcome."""
    _, selector = _run(fakes.context_length_rejection_openai())
    selector.assert_consumed()


def test_the_estimation_miss_still_archives_its_attempt() -> None:
    """The call was made and may have been billed — an attempt with no record
    would break `logical_call_count == len(StageRecords)` in the direction that
    hides spend."""
    outcome, _ = _run(fakes.context_length_rejection_openai())
    assert len(outcome.records) == 1
    assert outcome.records[0].failure.failure_class == "budget_estimation_miss"
    assert outcome.records[0].raw_response_text is None


def test_the_input_miss_carries_NO_stop_reason() -> None:
    """No response existed — the provider rejected the request. A normalized stop
    reason here would be invented, which is exactly what D9.4 forbids."""
    outcome, _ = _run(fakes.context_length_rejection_openai())
    assert outcome.records[0].stop_reason_raw is None
    assert outcome.budget_record.finish_reason_raw is None
    assert outcome.budget_record.finish_reason_normalized is None


# --------------------------------------------------------------------------
# 8. the fat stage, through the same loop
# --------------------------------------------------------------------------


def test_the_fat_stage_validates_hits_against_the_space() -> None:
    outcome, _ = _run(
        fakes.ScriptedReply(fakes.salvage_document(SPACE)), stage_name="fat"
    )
    assert outcome.outcome == "usable"
    # Joseph's rule made concrete: 10 returned, 6 kept.
    assert len(outcome.validated.hits) == 6
    assert outcome.validated.returned_entries == 10


def test_a_fat_honest_empty_is_usable_not_a_failure() -> None:
    """Spec §2.3's fourth case is explicitly NOT a failure class, so it must not
    consume a retry — an honest empty selection is an answer."""
    outcome, selector = _run(
        fakes.ScriptedReply(fakes.honest_empty_document()), stage_name="fat"
    )
    selector.assert_consumed()
    assert outcome.outcome == "usable"
    assert outcome.validated.hits == ()


def test_the_fat_stage_uses_the_FAT_prompt_ref_and_envelope() -> None:
    outcome, selector = _run(
        fakes.ScriptedReply(fakes.usable_document(SPACE)), stage_name="fat"
    )
    assert outcome.records[0].prompt == load_template("fat").ref
    assert outcome.records[0].prompt != load_template("thin").ref
    assert selector.requests[0].max_tokens == provider_max_tokens("fat")


# --------------------------------------------------------------------------
# 9. the loop's own invariants
# --------------------------------------------------------------------------


def test_the_attempt_ceiling_is_the_ratified_constant_not_a_literal() -> None:
    """A hardcoded `2` here would silently ignore a change to
    `MAX_ATTEMPTS_PER_STAGE`, which is also the per-stage `StageRecord` ceiling
    the contract matrix bounds every terminal against."""
    outcome, _ = _run(
        *[fakes.ScriptedReply(fakes.unparseable_text())] * MAX_ATTEMPTS_PER_STAGE
    )
    assert outcome.attempts == MAX_ATTEMPTS_PER_STAGE
    assert outcome.records[-1].attempt == MAX_ATTEMPTS_PER_STAGE


def test_records_are_numbered_from_one_in_call_order() -> None:
    outcome, _ = _run(
        fakes.transport_failure(), fakes.ScriptedReply(fakes.unparseable_text())
    )
    assert [r.attempt for r in outcome.records] == [1, 2]


def test_an_unscripted_call_surfaces_as_the_fake_s_own_assertion() -> None:
    """`FakeScriptExhausted` is an `AssertionError`, so it survives only because
    the loop has no catch-all. This test is what keeps that dependency honest: if
    a broad `except Exception` were ever added, this fails rather than the
    call-count contract silently becoming untestable."""
    with pytest.raises(fakes.FakeScriptExhausted):
        _run(fakes.ScriptedReply(fakes.unparseable_text()))


def test_every_attempt_renders_the_SAME_bytes() -> None:
    """A retry re-sends the identical request — there is no reformulation step in
    this contract, and the archived `rendered_messages` on each record must
    therefore match. If a retry ever varies the prompt, the byte pins and the
    replay path both need to know."""
    outcome, selector = _run(
        fakes.ScriptedReply(fakes.unparseable_text()),
        fakes.ScriptedReply(fakes.unparseable_text()),
    )
    assert selector.requests[0].prompt == selector.requests[1].prompt
    assert {r.rendered_messages for r in outcome.records} == {_messages("thin")}
