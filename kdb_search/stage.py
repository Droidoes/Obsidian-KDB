"""#123 `stage_call` — one executed stage: attempts, records, classification.

**P2.3.** `graph_search` decides *which* stages run and what each is given; this
module owns what happens inside one of them — up to `MAX_ATTEMPTS_PER_STAGE`
logical attempts, one `StageRecord` per attempt including the failures, and the
post-call budget classification that governs BOTH stages from this single site
(D9.3: the blueprint prints that block after the fat call in reading order and
says explicitly it lives inside `stage_call`).

**Four outcomes, and only one of them is ordinary** (`StageOutcome.outcome`):

  * `usable` — a validated document. Includes the honest empty; §2.3's fourth
    case is explicitly not a failure class.
  * `output_truncation` — cap stop **and** no complete usable document (D9.3).
    Terminal, never retried, `budget_side: output`.
  * `input_estimation_miss` — the provider rejected the request as over-window
    (D7). Terminal, never retried, `budget_side: input`; the call may have been
    billed.
  * `exhausted` — every attempt landed in an allowed retry class.

**Classification order is load-bearing.** The output-budget check runs *before*
the generic retry path, so a truncated response is typed as a budget event rather
than retried as an `unparseable_response` — retrying it would spend a second time
on a request that is deterministically too large for the envelope. And the
predicate is a **conjunction**: a cap stop on a complete usable document is
carrier metadata, validated normally with the stop recorded (R1's salvage rule,
following `compiler.py:405-409`'s ruling and its `test_compiler_recovery.py:200`
pin). A cap-stop test alone would discard a good document.

**No catch-all.** §2.1's fail-hard posture (Joseph's #121 ruling): only the
concrete SDK types below are caught. An unrelated `BadRequestError` — a bad
temperature, an unsupported parameter — propagates as the defect it is rather
than being laundered into `selector_failure`, which would report our own
misconfiguration as the selector's fault.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import httpx
import openai
from google.genai import errors as genai_errors

from common.call_model import ModelRequest, ModelResponse
from common.model_pool import ModelSpec

from .artifact import (
    ModelStamp,
    RenderedMessages,
    StageFailure,
    StageName,
    StageRecord,
    StageValidation,
)
from .budget import (
    BUDGET_HEADROOM,
    BudgetVerdict,
    Stage,
    hidden_output_reserve,
    provider_max_tokens,
    visible_output_allowance,
)
from .constants import MAX_ATTEMPTS_PER_STAGE
from .prompts import load_template
from .response import ValidatedResponse, ValidatedThinResponse, Violations
from .result import BudgetRecord

#: What `stage_call` validated, whichever stage it ran. A union rather than a
#: base class: the shared surface is four field names, and a common ancestor
#: would imply the payloads are interchangeable when `hits` and `retained` are
#: exactly what distinguishes the stages.
StageValidated = ValidatedResponse | ValidatedThinResponse

StageOutcomeKind = Literal[
    "usable", "output_truncation", "input_estimation_miss", "exhausted"
]

_STAGE_NAMES: dict[Stage, StageName] = {
    "thin": "thin_selection",
    "fat": "fat_selection",
}


# ---------------------------------------------------------------------------
# stop-reason normalization (D9.4) — one closed api_call_type-aware map
# ---------------------------------------------------------------------------

NormalizedStop = Literal["output_cap", "complete", "unknown"]

#: The cap-stop spelling each `api_call_type` emits. Verified at the source:
#: openai-compatible `"length"` (`common/call_model.py:299`), anthropic
#: `"max_tokens"` (`:207`), gemini the enum value's UPPERCASE name (`:250-254`,
#: via `finish_reason.value`). A literal `== "length"` test — which is what both
#: existing repo predicates do, `llm_telemetry.py:152` and `compiler.py:411` —
#: misses gemini entirely, and gemini is the interim default selector, so the
#: truncation terminal would be invisible on the exact route it ships on (#124).
_CAP_STOPS: dict[str, frozenset[str]] = {
    "openai_compat": frozenset({"length"}),
    "anthropic": frozenset({"max_tokens"}),
    "gemini": frozenset({"MAX_TOKENS"}),
}

#: Ordinary completion per family. Present so that "unknown" means *unknown*
#: rather than "not a cap stop" — a predicate with only the cap set would call
#: every ordinary completion unknown and make the D9.4 no-guessing rule vacuous.
_OK_STOPS: dict[str, frozenset[str]] = {
    "openai_compat": frozenset({"stop"}),
    "anthropic": frozenset({"end_turn"}),
    "gemini": frozenset({"STOP"}),
}


#: The SDK's own transport sub-retry allowance per `api_call_type`, verified at
#: the constructor call sites: the openai client passes `max_retries=2`
#: explicitly (`common/call_model.py:192`) and so does anthropic (`:273`), while
#: google-genai has no such kwarg at all and `HttpOptions.retry_options` defaults
#: to `None` (`:212`) — gemini gets one shot per logical attempt.
#:
#: Archived per `StageRecord`, **never counted as an attempt** (§8 G5): §6's
#: `logical_call_count == len(StageRecords)` excludes sub-retries from both
#: sides, because they are the provider's business and not a decision we made.
#: Recorded anyway, since "answered first try" and "the SDK tried three times"
#: are different reliability findings that look identical without it.
_SDK_SUB_RETRIES: dict[str, int] = {
    "openai_compat": 2,
    "anthropic": 2,
    "gemini": 0,
}


def normalize_stop_reason(raw: str | None, *, api_call_type: str) -> NormalizedStop:
    """Normalize one provider stop reason. **Never guesses** (D9.4).

    A value outside the route's two known sets — and `None`, which some routes
    report — is `"unknown"`, and an unknown stop reason is never classified into
    the budget class. That is the rule this function exists to make checkable:
    with no normalization, `SAFETY` and `MAX_TOKENS` are equally "not `length`".

    **The anthropic row is kept even though `graph_search` rejects anthropic
    selector routes** (`search._require_json_mode_capable`). This is a stop-reason
    table, not a capability table, and the two answer different questions: a route
    may become usable the day `call_model` implements `json_mode` for it, and a
    map that had silently dropped the row would then mis-type its truncations. It
    is unit-tested directly for the same reason — driving it through
    `graph_search` would fail at route resolution, not at the map.
    """
    if raw is None:
        return "unknown"
    if raw in _CAP_STOPS.get(api_call_type, frozenset()):
        return "output_cap"
    if raw in _OK_STOPS.get(api_call_type, frozenset()):
        return "complete"
    return "unknown"


# ---------------------------------------------------------------------------
# failure classification — the real SDK types, no catch-all
# ---------------------------------------------------------------------------

#: Non-response-shaped allowed retry classes (§8 B11). `APITimeoutError` is a
#: SUBCLASS of `APIConnectionError`, so it is named first where the two are
#: distinguished; here the tuple only has to catch both.
_TRANSPORT_RETRY: tuple[type[BaseException], ...] = (
    openai.APIConnectionError,
    httpx.TransportError,
    genai_errors.ServerError,
)

#: Substrings the gemini over-window rejection carries. Gemini types it only as
#: `INVALID_ARGUMENT` — there is no machine-readable code equivalent to openai's
#: `context_length_exceeded` — so the message is the only signal available. Kept
#: to phrases about the token count specifically, so an unrelated 400 (a bad
#: enum value, a malformed part) does not read as a budget event.
_GEMINI_CONTEXT_MARKERS: tuple[str, ...] = (
    "token count exceeds",
    "exceeds the maximum number of tokens",
    "input token count",
)


def is_context_length_rejection(exc: BaseException) -> bool:
    """D7's `budget_estimation_miss`: the provider refused the request as
    over-window. Typed `budget_exceeded` / `detected: post_call` /
    `budget_side: input`, attempted once, **never retried** — the same rendered
    bytes would be refused identically.

    Distinguishing this from an ordinary 400 is the whole job. `unrelated_bad_
    request()` in `fakes.py` is the negative case: a 400 with code
    `unsupported_value` is a defect in what we sent and must propagate, not be
    reported as the estimator missing.
    """
    if isinstance(exc, openai.BadRequestError):
        return getattr(exc, "code", None) == "context_length_exceeded"
    if isinstance(exc, genai_errors.ClientError):
        message = (getattr(exc, "message", "") or "").lower()
        return any(marker in message for marker in _GEMINI_CONTEXT_MARKERS)
    return False


def _transport_failure_class(exc: BaseException) -> str:
    """`timeout` and `transport` are separate classes in §8 B11's list, so they
    are recorded separately — a route that only ever times out is a different
    operational finding from one that cannot connect."""
    return "timeout" if isinstance(exc, openai.APITimeoutError) else "transport"


# ---------------------------------------------------------------------------
# the outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageOutcome:
    """Everything one executed stage produced. `graph_search` branches on
    `outcome` and never re-derives it from the records."""

    stage: Stage
    outcome: StageOutcomeKind
    #: One per logical attempt, in order, failures included. `len(records)` IS the
    #: stage's logical call count — §6's `logical_call_count == len(StageRecords)`
    #: invariant holds by construction rather than by accounting.
    records: tuple[StageRecord, ...]
    #: The validated document of the attempt that ENDED the stage — and `None` on
    #: `exhausted`, deliberately, even though the final attempt may well have
    #: parsed. A retry-exhausted stage produced no usable answer by definition, so
    #: exposing its last document would invite the F1 bug it exists to prevent:
    #: reading a thin retention off a stage that failed, when F1's whole premise
    #: is that the failed thin binds nothing. The attempts are still fully
    #: archived in `records`; this field is what a CONSUMER may act on.
    validated: StageValidated | None = None
    #: Set on `exhausted`, and on the two post-call budget outcomes so the
    #: archived record names what stopped the stage. `graph_search` promotes it to
    #: `telemetry.selector_failure_class` only on the paths whose terminal is
    #: `selector_failure` — the contract matrix forbids it anywhere else.
    failure_class: str | None = None
    #: Built here on the post-call outcomes, because this is the only place that
    #: holds both the pre-flight verdict's figures and the provider's own verdict.
    budget_record: BudgetRecord | None = None
    #: Summed over EVERY attempt, not read off the surviving one. "Attempted" is
    #: the operative word (§2.3): a first attempt that returned six foreign slugs
    #: and a second that succeeded is a selector that attempted six foreign slugs,
    #: and a per-outcome figure would report zero.
    attempted_violations: Violations = field(default_factory=Violations)
    #: How many attempts classified `all_entries_dropped` — its own telemetry
    #: counter in §6.3, separate from the violation classes because it is a
    #: property of the whole response rather than of any entry in it.
    all_entries_dropped_occurrences: int = 0
    #: Entries the selector returned, and entries that survived validation,
    #: summed over EVERY attempt. Accumulated for the same reason
    #: `attempted_violations` is, and load-bearing on exactly the path where
    #: `validated` is `None`: a stage that exhausted its retries on
    #: `all_entries_dropped` **did** return entries, and reporting 0/`None` there
    #: would enter the §8.4 per-model series as "no data" for a selector that
    #: hallucinated its whole answer twice — the strongest quality signal it can
    #: emit, recorded as its absence.
    returned_entries: int = 0
    validated_entries: int = 0

    @property
    def valid_entry_yield(self) -> float | None:
        """Validated ÷ returned across the stage. `None` only when the stage
        genuinely produced no entry population (D9.6) — a truncated attempt has
        no denominator, an all-dropped one has a real 0.0."""
        if self.returned_entries == 0:
            return None
        return self.validated_entries / self.returned_entries

    @property
    def attempts(self) -> int:
        return len(self.records)

    @property
    def retry_attempts(self) -> int:
        """Attempts beyond the first — the telemetry counter's per-stage share."""
        return max(0, len(self.records) - 1)


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------


def _model_request(
    stage: Stage, messages: RenderedMessages, spec: ModelSpec
) -> ModelRequest:
    """One logical attempt's request.

    `json_mode=True` is **not optional and not a default** — it is the ratified
    requirement on every selector request, both stages, and the regression it
    guards is already in the repo: `compiler/tests/test_compile_source.py:139`
    pins a pass-2 failure where free-form JSON reached a validator. `max_tokens`
    is the provider TOTAL (visible + hidden reserve, D9 quantity 3), never the
    visible allowance — sending the visible figure would cap the completion below
    the envelope the route was validated against.
    """
    return ModelRequest(
        provider=spec.provider,
        model=spec.model,
        prompt=messages.user,
        system=messages.system,
        json_mode=True,
        temperature=spec.temperature,
        max_tokens=provider_max_tokens(stage),
        use_completion_tokens=spec.use_completion_tokens,
        extra_body=spec.extra_body,
        route=spec.route,
    )


def _cost(spec: ModelSpec, response: ModelResponse) -> float:
    """Per-attempt spend. Prices are USD per 1e6 tokens (`common/llm_telemetry.py:177`)
    and every attempt is billed, including one whose response is unusable."""
    return (
        spec.price_in / 1e6 * response.input_tokens
        + spec.price_out / 1e6 * response.output_tokens
    )


def _stage_validation(validated: StageValidated) -> StageValidation:
    """Map the per-class counts onto the archive's drop/coerce split.

    The split is not cosmetic: a *dropped* entry is content the selector lost,
    a *coerced* one is content we normalized and kept. Only `unknown_expression`
    is a coercion — an unrecognized label costs the entry its attribution, never
    the entry itself.
    """
    violations = validated.attempted_violations
    dropped = {
        name: count
        for name, count in (
            ("foreign_slug", violations.foreign_slug),
            ("malformed_entry", violations.malformed_entry),
            ("duplicate_slug", violations.duplicate_slug),
            ("over_cap", violations.over_cap),
        )
        if count
    }
    coerced = (
        {"unknown_expression": violations.unknown_expression}
        if violations.unknown_expression
        else {}
    )
    validated_count = (
        len(validated.hits)
        if isinstance(validated, ValidatedResponse)
        else len(validated.retained)
    )
    return StageValidation(
        dropped=dropped,
        coerced=coerced,
        counts={
            "returned_entries": validated.returned_entries,
            "validated_entries": validated_count,
        },
    )


def _has_usable_document(validated: StageValidated) -> bool:
    """D9.3's second conjunct: was there a **complete, structurally usable** JSON
    document at all?

    `all_entries_dropped` counts as one. The document parsed, its array was
    present, its entries were whole — every one of them was rejected on *identity*
    grounds, which is a selector-quality event, not a truncation. Reading it as
    "no usable document" would type a hallucinating selector as a budget failure
    and never retry it, when it is precisely the case §8 B11 says to retry.
    """
    return validated.classification in ("usable", "all_entries_dropped")


def _post_call_budget_record(
    *,
    verdict: BudgetVerdict,
    spec: ModelSpec,
    budget_side: Literal["input", "output"],
    raw: str | None,
    normalized: str | None,
) -> BudgetRecord:
    return BudgetRecord(
        stage=verdict.stage,
        budget_estimate_tokens=verdict.estimated_input_tokens,
        selector_window=spec.ctx_window or 0,
        headroom_factor=BUDGET_HEADROOM,
        visible_output_allowance=visible_output_allowance(verdict.stage),
        hidden_output_reserve=hidden_output_reserve(),
        # The estimate said it fit and the provider disagreed — which is the
        # whole content of a post-call budget event, and why `fits=False` here
        # is not a restatement of the verdict but a correction of it.
        fits=False,
        detected="post_call",
        budget_side=budget_side,
        finish_reason_raw=raw,
        finish_reason_normalized=normalized,
    )


def stage_call(
    stage: Stage,
    *,
    messages: RenderedMessages,
    evidence: dict[str, str] | str,
    spec: ModelSpec,
    call: Callable[[ModelRequest], ModelResponse],
    validate: Callable[[str], StageValidated],
    verdict: BudgetVerdict,
) -> StageOutcome:
    """Run one stage to a terminal outcome.

    `validate` is injected rather than selected from `stage`: the thin and fat
    validators need the search space, the request's expressions and the caps,
    which are the orchestrator's to hold — passing them all through here would
    make this function take the whole request in order to look up two of its
    fields. What this module owns is the attempt/record/classification contract,
    which is identical for both stages.

    `evidence` is what gets archived on every record for this stage:
    `SPACE_MANIFEST_REF` for thin, `{slug: excerpt}` for fat. Passed in rather
    than derived, because the fat pool's composition — including which entities
    degraded to title-only — is decided during projection, upstream of here.
    """
    ref = load_template(stage).ref
    stamp = ModelStamp(
        provider=spec.provider, model=spec.model, route=spec.route.api_call_type
    )
    records: list[StageRecord] = []
    # Accumulated across attempts, never read off the surviving one — see
    # `StageOutcome.attempted_violations`.
    tally = Violations()
    dropped_occurrences = 0
    returned = 0
    kept = 0

    def record(
        *,
        response: ModelResponse | None = None,
        validated: StageValidated | None = None,
        normalized: str | None = None,
        failure: StageFailure | None = None,
    ) -> StageRecord:
        return StageRecord(
            stage=_STAGE_NAMES[stage],
            attempt=len(records) + 1,
            prompt=ref,
            rendered_messages=messages,
            model=stamp,
            evidence=evidence,
            latency_ms=response.latency_ms if response else 0,
            cost=_cost(spec, response) if response else 0.0,
            raw_response_text=response.text if response else None,
            parsed_output=validated.document if validated else None,
            stop_reason_raw=response.stop_reason if response else None,
            stop_reason_normalized=normalized,
            sdk_sub_retries=_SDK_SUB_RETRIES.get(spec.route.api_call_type, 0),
            failure=failure,
            validation=_stage_validation(validated) if validated else None,
            retained_identities=(
                validated.retained
                if isinstance(validated, ValidatedThinResponse)
                else None
            ),
        )

    for _ in range(MAX_ATTEMPTS_PER_STAGE):
        try:
            response = call(_model_request(stage, messages, spec))
        except (openai.BadRequestError, genai_errors.ClientError) as exc:
            # Only the over-window rejection is ours to interpret. Anything else
            # is a defect in the request we built and propagates (§2.1).
            if not is_context_length_rejection(exc):
                raise
            records.append(
                record(failure=StageFailure("budget_estimation_miss", str(exc)))
            )
            return StageOutcome(
                stage=stage,
                outcome="input_estimation_miss",
                records=tuple(records),
                failure_class="budget_estimation_miss",
                attempted_violations=tally,
                all_entries_dropped_occurrences=dropped_occurrences,
                returned_entries=returned,
                validated_entries=kept,
                budget_record=_post_call_budget_record(
                    verdict=verdict,
                    spec=spec,
                    budget_side="input",
                    raw=None,
                    normalized=None,
                ),
            )
        except _TRANSPORT_RETRY as exc:
            failure_class = _transport_failure_class(exc)
            records.append(record(failure=StageFailure(failure_class, str(exc))))
            continue

        normalized = normalize_stop_reason(
            response.stop_reason, api_call_type=spec.route.api_call_type
        )
        validated = validate(response.text)
        tally += validated.attempted_violations
        returned += validated.returned_entries
        kept += (
            len(validated.hits)
            if isinstance(validated, ValidatedResponse)
            else len(validated.retained)
        )
        if validated.classification == "all_entries_dropped":
            dropped_occurrences += 1

        # D9.3 — before the generic retry path, and a conjunction.
        if normalized == "output_cap" and not _has_usable_document(validated):
            records.append(
                record(
                    response=response,
                    validated=validated,
                    normalized=normalized,
                    failure=StageFailure(
                        "output_truncation",
                        f"{response.stop_reason!r} with no complete usable document "
                        f"({validated.classification})",
                    ),
                )
            )
            return StageOutcome(
                stage=stage,
                outcome="output_truncation",
                records=tuple(records),
                validated=validated,
                attempted_violations=tally,
                all_entries_dropped_occurrences=dropped_occurrences,
                returned_entries=returned,
                validated_entries=kept,
                failure_class="output_truncation",
                budget_record=_post_call_budget_record(
                    verdict=verdict,
                    spec=spec,
                    budget_side="output",
                    raw=response.stop_reason,
                    normalized=normalized,
                ),
            )

        if validated.should_retry:
            records.append(
                record(
                    response=response,
                    validated=validated,
                    normalized=normalized,
                    failure=StageFailure(
                        validated.classification, "allowed retry class"
                    ),
                )
            )
            continue

        records.append(
            record(response=response, validated=validated, normalized=normalized)
        )
        return StageOutcome(
            stage=stage,
            outcome="usable",
            records=tuple(records),
            validated=validated,
            attempted_violations=tally,
            all_entries_dropped_occurrences=dropped_occurrences,
            returned_entries=returned,
            validated_entries=kept,
        )

    last = records[-1].failure
    return StageOutcome(
        stage=stage,
        outcome="exhausted",
        records=tuple(records),
        failure_class=last.failure_class if last else None,
        attempted_violations=tally,
        all_entries_dropped_occurrences=dropped_occurrences,
        returned_entries=returned,
        validated_entries=kept,
    )


__all__ = [
    "NormalizedStop",
    "StageOutcome",
    "StageOutcomeKind",
    "StageValidated",
    "is_context_length_rejection",
    "normalize_stop_reason",
    "stage_call",
]
