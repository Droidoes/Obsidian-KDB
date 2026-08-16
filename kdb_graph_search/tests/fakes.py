"""#123 P2.0 — the shared fake selector `call` and its canned wire documents.

`graph_search` takes `call` as a parameter (D1), so every P2 test drives the
orchestrator through this module. Nothing here is production code; it is the
*input* side of P2's oracles.

**Order-scripted, not stage-keyed.** `FakeSelector` replies to invocations in the
order they arrive, and records every `ModelRequest`. It deliberately does not
inspect the request to decide which stage it is answering: the §8 branch table
counts calls in order (`1–2 thin + 1–2 fat`), so an order-scripted fake can
express every row, while a stage-keyed one would silently agree with whatever the
controller thinks the stage boundary is — the one thing the count assertions
exist to check. Tests assert stage identity off `requests`, not off the script.

**Documents are built FROM a space, never beside one.** `response.py:184` makes
membership in the search space the sole identity authority, so a canned "usable"
document whose slugs are not in the test's `SearchSpaceRef` classifies as
`all_entries_dropped` — and a test asserting "usable" would still pass, for the
wrong reason. Every builder here takes the space as its first argument, and
`test_fakes.py` runs each document through the real validators to prove it lands
in the class its name claims.

**Wire labels are hardcoded (`"A"`, `"B"`, …), not imported from
`constants.expression_labels()`.** These are bytes arriving from a model — an
input, not an expectation. Deriving them from the constant would give D11 a
fourth synchronized source and make a mutation to `WIRE_LABEL_ALPHABET` invisible
to every P2 test at once.

**Failure injection uses the real SDK exception types.** `common/call_model.py`
catches nothing (retry/backoff lives in `call_model_retry.py`, and blueprint §8
adopts pass-1's bare-`call_model` posture), so transport failures, timeouts and
the provider's context-length rejection reach the selector loop as raw
`openai.*` / `google.genai.errors.*` exceptions. P2.3's retry-class predicate is
written against those types, so the fake raises exactly them rather than a
stand-in that would let the predicate be tested against a fiction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import openai
from google.genai import errors as genai_errors

from common.call_model import ModelRequest, ModelResponse
from common.paths import PAGE_TYPES
from kdb_graph_search.types import GraphSnapshotRef, ScopeKind, SearchSpaceRef, SpaceEntity

# ---------------------------------------------------------------------------
# stop reasons — all three provider spellings, plus a non-cap and an unknown
# ---------------------------------------------------------------------------

#: openai-compatible cap stop (`common/call_model.py:299`).
STOP_LENGTH_OPENAI = "length"
#: anthropic cap stop (`:207`).
STOP_LENGTH_ANTHROPIC = "max_tokens"
#: gemini cap stop — the enum's UPPERCASE name (`:250-254`). The interim default
#: selector is gemini-native, so a fake omitting this spelling would leave the
#: live path uncovered while D9.4's normalization looked tested.
STOP_LENGTH_GEMINI = "MAX_TOKENS"

ALL_CAP_STOP_SPELLINGS: tuple[str, ...] = (
    STOP_LENGTH_OPENAI,
    STOP_LENGTH_ANTHROPIC,
    STOP_LENGTH_GEMINI,
)

#: Ordinary completions, per provider — a cap-stop predicate that fires on these
#: is broken in the direction that costs real spend.
STOP_OK_OPENAI = "stop"
STOP_OK_ANTHROPIC = "end_turn"
STOP_OK_GEMINI = "STOP"

#: A real gemini finish reason that is neither a cap stop nor a normal stop. D9.4
#: forbids guessing an unknown stop reason into the budget class, and that rule is
#: only testable with a value the normalizer genuinely does not know.
STOP_UNKNOWN = "SAFETY"

#: `ScriptedReply.stop_reason`'s default: resolve the *route's* ordinary
#: completion at reply time. A fixed default would hand an openai-compat request
#: gemini's `"STOP"` — a finish reason that route never emits — and a normalizer
#: bug keyed to the wrong family would pass. `None` stays a legitimate explicit
#: value (a route may report no stop reason at all), which is why this is a
#: sentinel rather than `None`.
ROUTE_DEFAULT_STOP = "<route-default>"

_OK_STOP_BY_PROVIDER: dict[str, str] = {
    "anthropic": STOP_OK_ANTHROPIC,
    "gemini": STOP_OK_GEMINI,
}


def ok_stop_for(provider: str) -> str:
    """The ordinary-completion spelling this provider's route actually emits.
    Everything not listed is openai-compatible (`common/call_model.py`'s Class-B
    registry: every non-anthropic, non-gemini row)."""
    return _OK_STOP_BY_PROVIDER.get(provider, STOP_OK_OPENAI)


# ---------------------------------------------------------------------------
# the fake `call`
# ---------------------------------------------------------------------------


class FakeScriptExhausted(AssertionError):
    """The controller called more times than the test scripted.

    An `AssertionError` on purpose: an unscripted call is a defect in the §8
    call-count contract, and `AssertionError` says that in the failure output
    without a custom class the reader has to look up.

    **Stated precisely, because the obvious stronger claim is false:**
    `AssertionError` *is* an `Exception`, so a broad `except Exception` would
    swallow this. What keeps that from happening is §2.1's fail-hard posture —
    the retry loop catches the allowed classes by their concrete SDK types and
    has no catch-all, so an unexpected exception propagates. This class relies on
    that posture rather than being immune to a violation of it. If a broad catch
    is ever introduced, this must move to `BaseException`.
    """


@dataclass(frozen=True)
class ScriptedReply:
    """One successful invocation's `ModelResponse` fields.

    `input_tokens` is settable and load-bearing, not decoration: the two
    `*_INPUT_ESTIMATION_MISS` terminals are `detected="post_call"`,
    `budget_side="input"`, and the provider-reported prompt-token count is the
    evidence archived alongside the rejection.

    `model`/`provider` default to echoing the request, so a test can assert
    `ModelStamp` fidelity without restating the route.

    `stop_reason` defaults to the *route's* ordinary completion (see
    `ROUTE_DEFAULT_STOP`), resolved against the request at reply time.
    """

    text: str
    stop_reason: str | None = ROUTE_DEFAULT_STOP
    input_tokens: int = 1_000
    output_tokens: int = 200
    latency_ms: int = 12
    model: str | None = None
    provider: str | None = None


class FakeSelector:
    """Scripted `Callable[[ModelRequest], ModelResponse]`.

    Each script entry is either a `ScriptedReply` or an exception *instance* to
    raise. `ModelResponse.attempts` is left at its default 1 deliberately — it
    counts `call_model`'s internal transport sub-retries, which §8 excludes from
    both sides of `logical_call_count == archived StageRecords`. The controller's
    logical attempts are its own count, and nothing here should let one be read
    as the other.
    """

    def __init__(self, *script: ScriptedReply | BaseException) -> None:
        self.script: tuple[ScriptedReply | BaseException, ...] = script
        self.requests: list[ModelRequest] = []

    @property
    def calls(self) -> int:
        """Logical invocations received — the §8 branch table's assertion target."""
        return len(self.requests)

    def __call__(self, req: ModelRequest) -> ModelResponse:
        self.requests.append(req)
        if len(self.requests) > len(self.script):
            raise FakeScriptExhausted(
                f"call #{len(self.requests)} is unscripted "
                f"({len(self.script)} scripted); the controller made more logical "
                "calls than the branch expects"
            )
        outcome = self.script[len(self.requests) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        stop_reason = outcome.stop_reason
        if stop_reason == ROUTE_DEFAULT_STOP:
            stop_reason = ok_stop_for(req.provider)
        return ModelResponse(
            text=outcome.text,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            latency_ms=outcome.latency_ms,
            model=outcome.model if outcome.model is not None else req.model,
            provider=outcome.provider if outcome.provider is not None else req.provider,
            stop_reason=stop_reason,
        )

    def assert_consumed(self) -> None:
        """Every scripted outcome was used.

        The complement of `FakeScriptExhausted`: a branch that stops early
        (retrying when it should not, or skipping a stage) leaves script behind,
        and a test asserting only the terminal's fields would not notice.
        """
        if self.calls != len(self.script):
            raise AssertionError(
                f"{self.calls} of {len(self.script)} scripted outcomes consumed"
            )


class NeverCalled:
    """A `call` that fails loudly. The zero-call terminals (`empty_space`,
    `thin_preflight_budget`, and every `InvalidGraphSearchRequest` path) are
    contracts about work *not* done, so they are driven with this rather than with
    an empty `FakeSelector` — the failure then names the violation directly.
    """

    def __call__(self, req: ModelRequest) -> ModelResponse:  # pragma: no cover
        raise AssertionError(
            f"the selector was invoked on a zero-call path (model={req.model!r})"
        )


# ---------------------------------------------------------------------------
# failure injection — the real SDK types
# ---------------------------------------------------------------------------


def _http_response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status, request=httpx.Request("POST", "https://fake.invalid/v1"), json=payload
    )


def transport_failure(detail: str = "connection reset") -> openai.APIConnectionError:
    """An allowed retry class that is not response-shaped (§8 B11)."""
    return openai.APIConnectionError(
        message=detail, request=httpx.Request("POST", "https://fake.invalid/v1")
    )


def timeout_failure() -> openai.APITimeoutError:
    """The second non-response-shaped retry class."""
    return openai.APITimeoutError(request=httpx.Request("POST", "https://fake.invalid/v1"))


def context_length_rejection_openai() -> openai.BadRequestError:
    """The openai-compat form of D7's `budget_estimation_miss` — a 400 whose code
    is `context_length_exceeded`. Never retried: the same rendered request would
    be rejected identically."""
    body = {
        "message": "This model's maximum context length is 32768 tokens",
        "type": "invalid_request_error",
        "code": "context_length_exceeded",
    }
    response = _http_response(400, {"error": body})
    return openai.BadRequestError(body["message"], response=response, body=body)


def context_length_rejection_gemini() -> genai_errors.ClientError:
    """The gemini-native form of the same event — the interim default selector's,
    so the two spellings of the rejection are covered for the same reason the
    three stop-reason spellings are."""
    payload = {
        "error": {
            "code": 400,
            "message": "The input token count exceeds the maximum number of tokens allowed",
            "status": "INVALID_ARGUMENT",
        }
    }
    return genai_errors.ClientError(400, payload, _http_response(400, payload))


def unrelated_bad_request() -> openai.BadRequestError:
    """A 400 that is NOT a context-length rejection. The predicate that types
    D7's miss must distinguish these, or every malformed request would be
    reported as a budget event."""
    body = {
        "message": "Unsupported value: temperature does not support 0.0",
        "type": "invalid_request_error",
        "code": "unsupported_value",
    }
    response = _http_response(400, {"error": body})
    return openai.BadRequestError(body["message"], response=response, body=body)


# ---------------------------------------------------------------------------
# the search space
# ---------------------------------------------------------------------------


def space_slug(index: int) -> str:
    return f"ent-{index:03d}"


def make_space(count: int) -> tuple[SpaceEntity, ...]:
    """Deterministic entities, slug-ascending. `page_type` cycles the real
    `common.paths` Literal so nothing here can pass a page type projection would
    reject."""
    return tuple(
        SpaceEntity(
            slug=space_slug(i),
            title=f"Entity {i:03d}",
            page_type=PAGE_TYPES[i % len(PAGE_TYPES)],
        )
        for i in range(count)
    )


def make_graph_ref(count: int) -> GraphSnapshotRef:
    return GraphSnapshotRef(
        schema_version="v1",
        active_entity_count=count,
        space_fingerprint=f"sha256:fake-{count}",
        source_kind="fixture",
        source_detail="kdb_graph_search/tests/fakes.py",
    )


def make_space_ref(
    count: int,
    *,
    scope_kind: ScopeKind = "domain_subtree",
    domain: str | None = "investing",
) -> SearchSpaceRef:
    """The request-side closed world for `count` entities — paired with the same
    `make_space` rows the canned documents are built from, which is the coupling
    the module docstring is about."""
    return SearchSpaceRef(
        entities=make_space(count),
        scope_kind=scope_kind,
        graph_ref=make_graph_ref(count),
        domain=domain,
    )


# ---------------------------------------------------------------------------
# canned wire documents — fat (stage 2)
# ---------------------------------------------------------------------------

#: Hardcoded on purpose (see the module docstring): wire bytes are inputs.
LABELS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")

FOREIGN_SLUG = "not-in-this-space"


def _dump(document: object) -> str:
    """Normative compact separators (blueprint §7.0a) — the grammar a real
    selector's response is measured against."""
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False)


def usable_document(
    space: tuple[SpaceEntity, ...],
    *,
    count: int = 3,
    matched: tuple[str, ...] = ("A",),
    unresolved: tuple[str, ...] = (),
) -> str:
    """`count` valid selections drawn from the head of `space`."""
    document: dict = {
        "selections": [
            {"slug": entity.slug, "matched": list(matched)} for entity in space[:count]
        ]
    }
    if unresolved:
        document["unresolved"] = list(unresolved)
    return _dump(document)


def salvage_document(space: tuple[SpaceEntity, ...]) -> str:
    """Joseph's rule made concrete: 10 returned entries, 6 kept.

    6 valid uniques + 1 duplicate + 2 foreign + 1 malformed ⇒ `usable`, 6 hits,
    `valid_entry_yield == 0.6`, and one violation in each of three classes.
    """
    valid = [{"slug": entity.slug, "matched": [LABELS[0]]} for entity in space[:6]]
    return _dump(
        {
            "selections": [
                *valid[:3],
                {"slug": FOREIGN_SLUG, "matched": [LABELS[0]]},
                *valid[3:],
                {"slug": space[0].slug, "matched": [LABELS[1]]},  # duplicate
                {"slug": f"{FOREIGN_SLUG}-2", "matched": []},
                {"matched": [LABELS[0]]},  # malformed: no slug
            ]
        }
    )


def honest_empty_document() -> str:
    """`selections: []` — spec §2.3 case 4. A `completed` terminal, NOT a failure
    class; scripted often enough to be named rather than spelled inline."""
    return _dump({"selections": []})


def structurally_unusable_document() -> str:
    """Valid JSON, no `selections` array — an allowed retry class."""
    return _dump({"selections": "invalid"})


def all_dropped_document(space: tuple[SpaceEntity, ...]) -> str:
    """Non-empty `selections`, every entry dropped — systematically hallucinated
    foreign slugs. The space is taken (and only asserted against) so the builder
    cannot be called without the caller holding the space these slugs must stay
    out of."""
    assert not any(entity.slug.startswith(FOREIGN_SLUG) for entity in space)
    return _dump(
        {"selections": [{"slug": f"{FOREIGN_SLUG}-{i}", "matched": [LABELS[0]]} for i in range(4)]}
    )


def unparseable_text() -> str:
    """Prose instead of a document — the retry class json_mode is meant to
    prevent, kept because the flag is a request the provider may not honour."""
    return "Sure! Here are the entities I selected: ent-000, ent-001."


def truncated_text(space: tuple[SpaceEntity, ...]) -> str:
    """A document cut off mid-object.

    Pairs with a cap-stop `stop_reason` to drive the D9 output terminals: the cut
    makes it `unparseable_response`, and the stop reason is what types it
    `budget_exceeded`/`budget_side: output` instead of an ordinary retry. Also the
    negative case for D9's *cap stop AND no usable document* conjunction.
    """
    full = usable_document(space, count=4)
    return full[: len(full) // 2]


# ---------------------------------------------------------------------------
# canned wire documents — thin (stage 1)
# ---------------------------------------------------------------------------


def retained_document(space: tuple[SpaceEntity, ...], *, count: int | None = None) -> str:
    """`{"retained": [...]}` — the stage-1 schema (spec §2.2), ranked best-first."""
    rows = space if count is None else space[:count]
    return _dump({"retained": [entity.slug for entity in rows]})


def retained_empty_document() -> str:
    """Thin retained nothing. Over `N > M` this is D3's `thin_retained_zero`
    terminal — `completed`, no fat call, watched class present, **never retried**.

    Its counterpart is `retained_all_foreign_document`; read that docstring before
    using either, because the two validate to the identical post-validation state
    and take opposite control-flow branches.
    """
    return _dump({"retained": []})


def retained_all_foreign_document(space: tuple[SpaceEntity, ...]) -> str:
    """Non-empty `retained`, every slug foreign — the thin side of
    `all_entries_dropped`, an **allowed retry class** (§8 B11).

    This is the fixture that makes the sharpest distinction in the two-stage flow
    testable at all. It validates down to `retained == ()` — *byte-identical
    post-validation state to `retained_empty_document`* — and yet:

    | document | validated | class | control flow |
    |---|---|---|---|
    | `{"retained": []}` | `()` | honest empty | D3 terminal, **no retry**, no fat call |
    | all-foreign | `()` | `all_entries_dropped` | **retry**, then F1 or `thin_exhausted` |

    A controller that branches on the *validated list* rather than on the response
    class collapses these, and a malfunctioning selector then reads as an honest
    empty — precisely what D3's watched class exists to prevent. Without this
    fixture that bug is invisible to every test in the phase.
    """
    assert not any(entity.slug.startswith(FOREIGN_SLUG) for entity in space)
    return _dump({"retained": [f"{FOREIGN_SLUG}-{i}" for i in range(3)]})


def thin_structurally_unusable_document() -> str:
    """Valid JSON object, no `retained` array — thin's structural failure.

    Separate from `structurally_unusable_document()`, which is fat-shaped
    (`selections`). One rule governs per-*entry* validation across both stages
    (spec §2.2), but the document-level key differs, so a shared fixture would
    test the fat key on the thin path.
    """
    return _dump({"retained": "invalid"})


def thin_truncated_text(space: tuple[SpaceEntity, ...]) -> str:
    """A thin document cut off mid-list — `THIN_OUTPUT_TRUNCATION`'s producer.

    Reachable via `unparseable_text()` plus a cap stop, but the point of this
    module is that each terminal has a named, stage-correct producer: a thin
    truncation looks like a severed `retained` list, not like prose.
    """
    full = retained_document(space)
    return full[: len(full) // 2]


def retained_salvage_document(space: tuple[SpaceEntity, ...]) -> str:
    """The same per-entry rule on the thin side (spec §2.2, one rule both stages):
    valid slugs plus a foreign, a duplicate and a malformed entry."""
    return _dump(
        {
            "retained": [
                space[0].slug,
                FOREIGN_SLUG,
                space[1].slug,
                space[0].slug,  # duplicate
                42,  # malformed: not a string
            ]
        }
    )


__all__ = [
    "ALL_CAP_STOP_SPELLINGS",
    "FOREIGN_SLUG",
    "LABELS",
    "ROUTE_DEFAULT_STOP",
    "STOP_LENGTH_ANTHROPIC",
    "STOP_LENGTH_GEMINI",
    "STOP_LENGTH_OPENAI",
    "STOP_OK_ANTHROPIC",
    "STOP_OK_GEMINI",
    "STOP_OK_OPENAI",
    "STOP_UNKNOWN",
    "FakeScriptExhausted",
    "FakeSelector",
    "NeverCalled",
    "ScriptedReply",
    "all_dropped_document",
    "context_length_rejection_gemini",
    "context_length_rejection_openai",
    "honest_empty_document",
    "make_graph_ref",
    "make_space",
    "make_space_ref",
    "ok_stop_for",
    "retained_all_foreign_document",
    "retained_document",
    "retained_empty_document",
    "retained_salvage_document",
    "salvage_document",
    "space_slug",
    "structurally_unusable_document",
    "thin_structurally_unusable_document",
    "thin_truncated_text",
    "timeout_failure",
    "transport_failure",
    "truncated_text",
    "unparseable_text",
    "unrelated_bad_request",
    "usable_document",
]
