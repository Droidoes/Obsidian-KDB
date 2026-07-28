"""#123 response salvage + controller accounting (spec §2.3).

**Take the content, not the semantics — a parseable response is never discarded**
(Joseph, 2026-07-25). Entries are validated independently against the closed
world; only what is invalid drops, anything with a unique deterministic reading is
coerced, and every deviation is counted by class. His example is the rule: 10
returned slugs, 1 duplicate, 3 malformed => the 6 good slugs are kept.

Nothing here trusts the wire for identity. The response carries slugs; titles and
page types come from the search space, so a response cannot smuggle in metadata.
That is also what makes the §8.4 escaped-foreign-identity gate hold at 0 by
construction rather than by measurement.

One rule, both stages: `validate_thin_retention` is the same per-entry logic over
stage 1's retained-slug list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from .constants import MAX_EXPRESSIONS, wire_vocabulary
from .types import Hit, SpaceEntity

#: `usable` covers both a populated selection and the honest empty — spec §2.3's
#: fourth case is explicitly NOT a failure class, so it is not named as one here.
ResponseClass = Literal[
    "unparseable_response", "structurally_unusable_response", "all_entries_dropped", "usable"
]

RETRY_CLASSES: frozenset[str] = frozenset(
    {"unparseable_response", "structurally_unusable_response", "all_entries_dropped"}
)


@dataclass(frozen=True)
class Violations:
    """`attempted_violations` — per-class deviation counts (spec §2.3 telemetry).

    "Attempted" is the operative word: these count what the selector tried, not
    what got through. Escaped violations are 0 by construction.
    """

    foreign_slug: int = 0
    malformed_entry: int = 0
    unknown_expression: int = 0
    duplicate_slug: int = 0
    over_cap: int = 0

    def __add__(self, other: "Violations") -> "Violations":
        return Violations(
            foreign_slug=self.foreign_slug + other.foreign_slug,
            malformed_entry=self.malformed_entry + other.malformed_entry,
            unknown_expression=self.unknown_expression + other.unknown_expression,
            duplicate_slug=self.duplicate_slug + other.duplicate_slug,
            over_cap=self.over_cap + other.over_cap,
        )


@dataclass(frozen=True)
class ValidatedResponse:
    classification: ResponseClass
    hits: tuple[Hit, ...]
    #: The selector's advisory `unresolved`, decoded from wire labels to positions,
    #: bounded and de-duplicated — INPUT to accounting, never its authority.
    advisory_unresolved: tuple[int, ...]
    attempted_violations: Violations
    #: Entries the selector returned, before validation — `valid_entry_yield`'s
    #: denominator, and 0 whenever there is no usable document at all.
    returned_entries: int

    @property
    def valid_entry_yield(self) -> float | None:
        """`valid / returned`, `None` when `returned == 0` (D9.6).

        A truncated attempt yields no usable document, hence no entry population,
        hence no denominator — it can never dilute a model's conformance ratio.
        An `all_entries_dropped` response, by contrast, DID return entries, so its
        yield is a real 0.0.
        """
        if self.returned_entries == 0:
            return None
        return len(self.hits) / self.returned_entries

    @property
    def should_retry(self) -> bool:
        return self.classification in RETRY_CLASSES


@dataclass(frozen=True)
class ExpressionAccounting:
    matched_expressions: tuple[str, ...]
    unresolved_expressions: tuple[str, ...]
    #: Disagreement between the selector's advisory list and the controller's
    #: computation. Counted, never a failure class.
    selector_accounting_delta: int
    #: Keeps cap-induced unresolveds out of the abstention metric (§8.3 metric 6).
    cap_exhausted_possible: bool
    unattributed_hit_count: int
    #: True when some expression's only validated hits are unattributed — an
    #: attribution artifact, not an abstention judgment (opus5 §2.4).
    unattributed_possible: bool


def _parse(raw: str) -> tuple[object | None, ResponseClass | None]:
    """Classify at the document level. A cap-stop truncation lands here as
    `unparseable_response`: there is no complete JSON document to salvage."""
    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, TypeError):
        return None, "unparseable_response"


def _bounded_labels(values: object, expression_count: int) -> tuple[tuple[int, ...], int]:
    """Decode a wire label list to unique, in-range, `MAX_EXPRESSIONS`-bounded
    positions. Returns the positions and the count of unknown-expression coercions.

    **Labels, not indices (D11).** The wire carries `"A"`, `"B"`, … — a verbatim
    echo of the marker printed beside each expression. Positions are an internal
    representation the wire never sees, which is why D8's `isinstance(bool)` guard
    is gone rather than kept: it existed because `bool` is an `int` subclass, so
    `True` silently addressed expression 1. A `bool` is not a `str`, so the same
    input is now an ordinary unknown-expression coercion — the guard's whole
    concern is what letters remove.

    Case is coerced, not counted: `"a"` has exactly one deterministic reading, and
    the project's rule is to normalize a benign deviation rather than drop it.

    Uses `wire_vocabulary` rather than `expression_labels`: this path must never
    raise, or a parseable response would be discarded by exception (see the
    constant's docstring).
    """
    if not isinstance(values, list):
        return (), 0
    positions = {label: i for i, label in enumerate(wire_vocabulary(expression_count))}
    seen: list[int] = []
    unknown = 0
    for value in values:
        if not isinstance(value, str):
            unknown += 1
            continue
        position = positions.get(value.upper())
        if position is None:
            unknown += 1
            continue
        if position not in seen:
            seen.append(position)
    return tuple(seen[:MAX_EXPRESSIONS]), unknown


def validate_response(
    raw: str,
    *,
    space: tuple[SpaceEntity, ...],
    expressions: tuple[str, ...],
    max_results: int,
) -> ValidatedResponse:
    """Validate and salvage one selector response against the closed world."""
    document, failure = _parse(raw)
    if failure is not None:
        return ValidatedResponse(failure, (), (), Violations(), 0)

    if not isinstance(document, dict) or not isinstance(document.get("selections"), list):
        return ValidatedResponse("structurally_unusable_response", (), (), Violations(), 0)

    by_slug = {entity.slug: entity for entity in space}
    selections: list = document["selections"]
    violations = Violations()
    hits: list[Hit] = []
    kept: set[str] = set()

    for entry in selections:
        if not isinstance(entry, dict):
            violations += Violations(malformed_entry=1)
            continue
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug:
            violations += Violations(malformed_entry=1)
            continue
        # Membership is the sole identity authority — never repaired by
        # similarity, and an over-long or path-like slug fails here for free.
        entity = by_slug.get(slug)
        if entity is None:
            violations += Violations(foreign_slug=1)
            continue
        if slug in kept:
            # The selector's own returned order is the authority: first wins.
            violations += Violations(duplicate_slug=1)
            continue
        positions, unknown = _bounded_labels(entry.get("matched"), len(expressions))
        violations += Violations(unknown_expression=unknown)
        kept.add(slug)
        hits.append(
            Hit(
                slug=entity.slug,
                title=entity.title,
                page_type=entity.page_type,
                matched_expressions=tuple(expressions[i] for i in sorted(positions)),
            )
        )

    # Counted against the RETURNED length — that is what the selector attempted.
    if len(selections) > max_results:
        violations += Violations(over_cap=len(selections) - max_results)
    # Truncation runs after salvage, so invalid entries never consume cap slots
    # (R1: keep the most content a valid response can give us).
    hits = hits[:max_results]

    advisory, advisory_unknown = _bounded_labels(document.get("unresolved"), len(expressions))
    violations += Violations(unknown_expression=advisory_unknown)

    classification: ResponseClass = (
        "all_entries_dropped" if selections and not hits else "usable"
    )
    return ValidatedResponse(
        classification=classification,
        hits=tuple(hits),
        advisory_unresolved=advisory,
        attempted_violations=violations,
        returned_entries=len(selections),
    )


def resolve_accounting(
    response: ValidatedResponse,
    *,
    expressions: tuple[str, ...],
    max_results: int,
) -> ExpressionAccounting:
    """Controller-side expression accounting (spec §2.3).

    Every request expression is *matched* (>= 1 validated hit attributes it) or
    *unresolved*. The selector's advisory list is an input; where it disagrees the
    controller wins and the disagreement is counted.
    """
    attributed = {
        expression for hit in response.hits for expression in hit.matched_expressions
    }
    matched = tuple(e for e in expressions if e in attributed)
    unresolved = tuple(e for e in expressions if e not in attributed)

    claimed = {expressions[i] for i in response.advisory_unresolved}
    delta = len(claimed.symmetric_difference(set(unresolved))) if response.advisory_unresolved else 0

    unattributed = sum(1 for hit in response.hits if not hit.matched_expressions)
    return ExpressionAccounting(
        matched_expressions=matched,
        unresolved_expressions=unresolved,
        selector_accounting_delta=delta,
        cap_exhausted_possible=len(response.hits) == max_results,
        unattributed_hit_count=unattributed,
        # An unattributed hit means some expression may be reported unresolved
        # purely because attribution was lost — never because nothing was found.
        unattributed_possible=unattributed > 0 and bool(unresolved),
    )


def validate_thin_retention(
    slugs: list,
    *,
    space: tuple[SpaceEntity, ...],
    cap: int,
) -> tuple[tuple[str, ...], Violations]:
    """Stage-1 validation — the identical per-entry rule over the retained-slug
    list: foreign and malformed dropped, duplicates deduped, over-cap truncated in
    returned order. Reusing `validate_response` here would mean synthesizing a
    fake wire document; the rule is short enough to state once per shape.
    """
    by_slug = {entity.slug for entity in space}
    violations = Violations()
    retained: list[str] = []
    for slug in slugs:
        if not isinstance(slug, str) or not slug:
            violations += Violations(malformed_entry=1)
            continue
        if slug not in by_slug:
            violations += Violations(foreign_slug=1)
            continue
        if slug in retained:
            violations += Violations(duplicate_slug=1)
            continue
        retained.append(slug)
    if len(slugs) > cap:
        violations += Violations(over_cap=len(slugs) - cap)
    return tuple(retained[:cap]), violations


__all__ = [
    "ExpressionAccounting",
    "ResponseClass",
    "RETRY_CLASSES",
    "ValidatedResponse",
    "Violations",
    "resolve_accounting",
    "validate_response",
    "validate_thin_retention",
]
