"""P1.2 — response salvage + controller accounting (#123 spec §2.3).

Governing principle (Joseph, 2026-07-25): **take the content, not the semantics —
a parseable response is never discarded.** Every test here is a statement about
that rule. The canonical case is his own: 10 returned slugs, 1 duplicate, 3
malformed => the 6 good slugs are kept.

Every numeric maximum is tested AT its bound, because a maximum tested only well
inside or well outside it pins nothing.
"""

from __future__ import annotations

import json

import pytest

from kdb_search.constants import MAX_EXPRESSIONS, MAX_RESULTS, MAX_SLUG_LEN
from kdb_search.response import (
    Violations,
    resolve_accounting,
    validate_response,
    validate_thin_retention,
)
from kdb_search.types import SpaceEntity

EXPRESSIONS = ("warren-buffett", "owner-earnings", "moats")


def _space(*slugs: str) -> tuple[SpaceEntity, ...]:
    return tuple(SpaceEntity(slug=s, title=s.title(), page_type="concept") for s in slugs)


SPACE = _space("warren-buffett", "berkshire-hathaway", "owner-earnings", "economic-moats")


def _wire(selections: list[dict], unresolved: list[int] | None = None) -> str:
    payload: dict = {"selections": selections}
    if unresolved is not None:
        payload["unresolved"] = unresolved
    return json.dumps(payload)


def _validate(raw: str, *, space=SPACE, expressions=EXPRESSIONS, max_results=MAX_RESULTS):
    return validate_response(
        raw, space=space, expressions=expressions, max_results=max_results
    )


# --------------------------------------------------------------------------
# four-way response classification — exactly one applies (codex concurrence #1)
# --------------------------------------------------------------------------

def test_no_complete_json_document_is_unparseable():
    r = _validate('{"selections": [{"slug": "warren-buff')
    assert r.classification == "unparseable_response"
    assert r.hits == ()
    assert r.valid_entry_yield is None


def test_valid_json_that_is_not_an_object_with_selections_is_structurally_unusable():
    for raw in ("{}", '{"selections": "invalid"}', "[]", '"a string"', "null"):
        r = _validate(raw)
        assert r.classification == "structurally_unusable_response", raw
        assert r.hits == ()


def test_a_non_empty_selections_array_with_every_entry_dropped_is_all_entries_dropped():
    """Systematically hallucinated foreign slugs: the selector malfunctioned, not
    the query. Distinct from an honest empty, and retried."""
    r = _validate(_wire([{"slug": "not-in-space"}, {"slug": "also-fake"}]))
    assert r.classification == "all_entries_dropped"
    assert r.hits == ()
    assert r.attempted_violations.foreign_slug == 2
    assert r.valid_entry_yield == 0.0, "2 returned, 0 valid — the yield is 0, not None"


def test_an_empty_selections_array_is_an_honest_empty_completed_response():
    """`selections: []` is NONE of the three failure classes — it is correct
    abstention (class E semantics), and its quality is metric 6's job."""
    r = _validate(_wire([]))
    assert r.classification == "usable"
    assert r.hits == ()
    assert r.valid_entry_yield is None, "no returned entries => no yield denominator"


def test_exactly_one_classification_applies():
    cases = [
        ("{", "unparseable_response"),
        ("{}", "structurally_unusable_response"),
        (_wire([{"slug": "ghost"}]), "all_entries_dropped"),
        (_wire([]), "usable"),
        (_wire([{"slug": "warren-buffett"}]), "usable"),
    ]
    seen = [_validate(raw).classification for raw, _ in cases]
    assert seen == [expected for _, expected in cases]


# --------------------------------------------------------------------------
# Joseph's 6-of-10 rule, as a table
# --------------------------------------------------------------------------

def test_joseph_six_of_ten_rule():
    """His example IS the rule: 10 returned, 1 duplicate, 3 malformed => 6 kept."""
    space = _space(*[f"slug-{i}" for i in range(6)])
    selections = [{"slug": f"slug-{i}", "matched": [0]} for i in range(6)]
    selections.append({"slug": "slug-0", "matched": [0]})          # duplicate
    selections.append({"matched": [0]})                             # malformed: no slug
    selections.append({"slug": 42, "matched": [0]})                 # malformed: wrong type
    selections.append({"slug": ["nested"], "matched": [0]})         # malformed: wrong type
    r = _validate(_wire(selections), space=space, expressions=("k",))

    assert [h.slug for h in r.hits] == [f"slug-{i}" for i in range(6)]
    assert r.returned_entries == 10
    assert r.attempted_violations == Violations(duplicate_slug=1, malformed_entry=3)
    assert r.valid_entry_yield == 0.6


def test_a_parseable_response_is_never_discarded_wholesale():
    """One good entry among nine bad ones still completes."""
    selections = [{"slug": "ghost-%d" % i} for i in range(9)]
    selections.insert(4, {"slug": "warren-buffett"})
    r = _validate(_wire(selections))
    assert r.classification == "usable"
    assert [h.slug for h in r.hits] == ["warren-buffett"]


# --------------------------------------------------------------------------
# per-entry drops (identity invalid — never repaired)
# --------------------------------------------------------------------------

def test_foreign_slug_is_dropped_and_never_repaired_by_similarity():
    """`warren-buffet` is one character from a real member. It is still foreign."""
    r = _validate(_wire([{"slug": "warren-buffet"}, {"slug": "warren-buffett"}]))
    assert [h.slug for h in r.hits] == ["warren-buffett"]
    assert r.attempted_violations.foreign_slug == 1


def test_an_overlong_slug_is_foreign_by_membership():
    """The wire states `slug` <= MAX_SLUG_LEN, but membership is the authority:
    an over-long slug cannot be a canonical member, so it drops as foreign."""
    r = _validate(_wire([{"slug": "x" * (MAX_SLUG_LEN + 1)}]))
    assert r.hits == ()
    assert r.attempted_violations.foreign_slug == 1


def test_a_slug_at_the_length_bound_is_accepted_when_it_is_a_real_member():
    at_bound = "x" * MAX_SLUG_LEN
    r = _validate(_wire([{"slug": at_bound}]), space=_space(at_bound))
    assert [h.slug for h in r.hits] == [at_bound]
    assert r.attempted_violations == Violations()


@pytest.mark.parametrize(
    "entry",
    [{}, {"slug": None}, {"slug": 1}, {"slug": []}, {"slug": {}}, "not-an-object", 7, None],
)
def test_malformed_entries_are_dropped_and_counted(entry):
    r = _validate(_wire([entry, {"slug": "warren-buffett"}]))
    assert [h.slug for h in r.hits] == ["warren-buffett"]
    assert r.attempted_violations.malformed_entry == 1


def test_hits_carry_the_titles_and_page_types_from_the_space_never_the_wire():
    """The wire sends slugs only; identity metadata comes from the closed world.
    A response echoing a different title cannot influence what we return."""
    r = _validate(_wire([{"slug": "owner-earnings", "title": "ATTACKER", "page_type": "article"}]))
    assert r.hits[0].title == "Owner-Earnings"
    assert r.hits[0].page_type == "concept"


# --------------------------------------------------------------------------
# per-field coercion (a unique deterministic reading exists)
# --------------------------------------------------------------------------

def test_out_of_range_matched_index_is_removed_leaving_the_hit_standing():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0, 99]}]))
    assert r.hits[0].matched_expressions == ("warren-buffett",)
    assert r.attempted_violations.unknown_expression == 1


def test_a_hit_stripped_of_every_matched_index_stands_as_an_unattributed_hit():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [99]}]))
    assert [h.slug for h in r.hits] == ["warren-buffett"]
    assert r.hits[0].matched_expressions == ()
    assert r.attempted_violations.unknown_expression == 1


@pytest.mark.parametrize("index", [-1, 3, 4, 1_000])
def test_indices_outside_the_zero_based_half_open_range_are_coerced_away(index):
    """`matched` indices are in [0, len(expressions)) — three expressions means
    0,1,2. A negative index would silently address the tail under Python slicing."""
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [index]}]))
    assert r.hits[0].matched_expressions == ()
    assert r.attempted_violations.unknown_expression == 1


def test_the_highest_in_range_index_resolves():
    last = len(EXPRESSIONS) - 1
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [last]}]))
    assert r.hits[0].matched_expressions == (EXPRESSIONS[last],)
    assert r.attempted_violations == Violations()


def test_duplicate_slug_keeps_the_first_occurrence():
    """The selector's own returned order is the authority — the first mention
    wins, and its attribution is the one kept."""
    r = _validate(
        _wire([
            {"slug": "warren-buffett", "matched": [0]},
            {"slug": "warren-buffett", "matched": [1, 2]},
        ])
    )
    assert len(r.hits) == 1
    assert r.hits[0].matched_expressions == ("warren-buffett",)
    assert r.attempted_violations.duplicate_slug == 1


def test_duplicate_matched_index_within_an_entry_is_deduped():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [1, 1, 1, 0]}]))
    assert r.attempted_violations.unknown_expression == 0
    # Canonical INDEX order, not the selector's emission order. `matched` carries
    # no ranking claim among expressions, and canonicalizing means two responses
    # attributing the same set render identically — which the artifact integrity
    # hash and replay comparison both depend on. (Returned order IS authoritative
    # for duplicate-slug resolution; that is a different question.)
    assert r.hits[0].matched_expressions == ("warren-buffett", "owner-earnings")


def test_matched_expression_order_is_canonical_regardless_of_emission_order():
    forward = _validate(_wire([{"slug": "warren-buffett", "matched": [0, 2]}]))
    reversed_ = _validate(_wire([{"slug": "warren-buffett", "matched": [2, 0]}]))
    assert forward.hits == reversed_.hits


def test_matched_holding_more_than_max_expressions_unique_indices_is_bounded():
    r = _validate(
        _wire([{"slug": "warren-buffett", "matched": list(range(MAX_EXPRESSIONS + 5))}]),
        expressions=tuple(f"e{i}" for i in range(MAX_EXPRESSIONS)),
    )
    assert len(r.hits[0].matched_expressions) <= MAX_EXPRESSIONS


@pytest.mark.parametrize("matched", ["not-a-list", 5, {"a": 1}, [None], ["0"], [1.5]])
def test_a_wrong_typed_matched_field_never_invalidates_the_hit(matched):
    """R1: the hit's identity is valid; a broken attribution is noise."""
    r = _validate(_wire([{"slug": "warren-buffett", "matched": matched}]))
    assert [h.slug for h in r.hits] == ["warren-buffett"]
    assert r.hits[0].matched_expressions == ()


@pytest.mark.parametrize("value,would_address", [(True, 1), (False, 0)])
def test_json_booleans_are_not_accepted_as_indices(value, would_address):
    """`bool` is an `int` subclass in Python, so `[true]` on the wire would
    silently attribute the hit to expression 1 and `[false]` to expression 0 —
    a wrong attribution that looks like a correct one. It is a type violation,
    counted as unknown_expression, not a valid index."""
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [value]}]))
    assert [h.slug for h in r.hits] == ["warren-buffett"]
    assert r.hits[0].matched_expressions == (), (
        f"a JSON boolean was read as index {would_address} ({EXPRESSIONS[would_address]})"
    )
    assert r.attempted_violations.unknown_expression == 1


def test_json_booleans_are_not_accepted_in_the_advisory_list_either():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0]}], unresolved=[True]))
    assert r.advisory_unresolved == ()
    assert r.attempted_violations.unknown_expression == 1


# --------------------------------------------------------------------------
# over-cap
# --------------------------------------------------------------------------

def test_over_cap_truncates_in_returned_order_and_counts_the_overage():
    space = _space(*[f"s{i}" for i in range(60)])
    r = _validate(
        _wire([{"slug": f"s{i}"} for i in range(60)]),
        space=space, expressions=("k",), max_results=50,
    )
    assert len(r.hits) == 50
    assert [h.slug for h in r.hits] == [f"s{i}" for i in range(50)], "returned order preserved"
    assert r.attempted_violations.over_cap == 10


def test_exactly_at_max_results_is_not_an_over_cap_violation():
    space = _space(*[f"s{i}" for i in range(50)])
    r = _validate(
        _wire([{"slug": f"s{i}"} for i in range(50)]),
        space=space, expressions=("k",), max_results=50,
    )
    assert len(r.hits) == 50
    assert r.attempted_violations.over_cap == 0


def test_truncation_runs_after_salvage_so_invalid_entries_do_not_consume_cap_slots():
    """Validate first, then truncate: 60 returned with 20 foreign yields 40 good
    hits, not the ~33 that truncating the raw list first would leave."""
    space = _space(*[f"s{i}" for i in range(40)])
    selections = [{"slug": f"s{i}"} for i in range(40)] + [{"slug": f"ghost{i}"} for i in range(20)]
    r = _validate(_wire(selections), space=space, expressions=("k",), max_results=50)
    assert len(r.hits) == 40
    assert r.attempted_violations.foreign_slug == 20
    assert r.attempted_violations.over_cap == 10, "counted against the returned length"


# --------------------------------------------------------------------------
# valid_entry_yield (D9.6)
# --------------------------------------------------------------------------

def test_valid_entry_yield_is_valid_over_returned():
    r = _validate(_wire([{"slug": "warren-buffett"}, {"slug": "ghost"}, {"slug": "owner-earnings"}]))
    assert r.returned_entries == 3
    assert r.valid_entry_yield == pytest.approx(2 / 3)


@pytest.mark.parametrize("raw", ["{", "{}", '{"selections": []}'])
def test_valid_entry_yield_is_none_when_there_are_no_returned_entries(raw):
    """D9.6: no usable document, or an honest empty, means no entry population —
    so there is no denominator. A truncated attempt never enters one."""
    assert _validate(raw).valid_entry_yield is None


def test_a_truncated_attempt_contributes_no_denominator():
    """The D9.6 pin: a cap-stop attempt with no complete usable document is
    unparseable, so it cannot dilute a model's entry-conformance ratio."""
    truncated = '{"selections": [{"slug": "warren-buffett"}, {"slug": "owner-ear'
    r = _validate(truncated)
    assert r.classification == "unparseable_response"
    assert r.returned_entries == 0
    assert r.valid_entry_yield is None


# --------------------------------------------------------------------------
# controller-computed expression accounting
# --------------------------------------------------------------------------

def test_accounting_splits_expressions_into_matched_and_unresolved():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0]}], unresolved=[1, 2]))
    a = resolve_accounting(r, expressions=EXPRESSIONS, max_results=MAX_RESULTS)
    assert a.matched_expressions == ("warren-buffett",)
    assert a.unresolved_expressions == ("owner-earnings", "moats")
    assert a.selector_accounting_delta == 0


def test_the_advisory_list_is_input_to_accounting_never_the_authority():
    """The selector claims everything is unresolved while attributing a hit. The
    controller's computation wins; the discrepancy is counted, never a failure."""
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0]}], unresolved=[0, 1, 2]))
    a = resolve_accounting(r, expressions=EXPRESSIONS, max_results=MAX_RESULTS)
    assert a.matched_expressions == ("warren-buffett",)
    assert a.selector_accounting_delta == 1


def test_a_missing_advisory_list_is_not_a_discrepancy_by_itself():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0]}]))
    a = resolve_accounting(r, expressions=EXPRESSIONS, max_results=MAX_RESULTS)
    assert a.unresolved_expressions == ("owner-earnings", "moats")
    assert a.selector_accounting_delta == 0


def test_out_of_range_advisory_indices_are_bounded_and_counted():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0]}], unresolved=[99, -1]))
    a = resolve_accounting(r, expressions=EXPRESSIONS, max_results=MAX_RESULTS)
    assert a.unresolved_expressions == ("owner-earnings", "moats")
    assert r.attempted_violations.unknown_expression == 2


def test_cap_exhausted_possible_is_annotated_only_at_the_cap():
    space = _space(*[f"s{i}" for i in range(5)])
    at_cap = _validate(
        _wire([{"slug": f"s{i}", "matched": [0]} for i in range(5)]),
        space=space, expressions=("k", "unmatched"), max_results=5,
    )
    assert resolve_accounting(at_cap, expressions=("k", "unmatched"), max_results=5).cap_exhausted_possible
    under_cap = _validate(
        _wire([{"slug": "s0", "matched": [0]}]),
        space=space, expressions=("k", "unmatched"), max_results=5,
    )
    assert not resolve_accounting(under_cap, expressions=("k", "unmatched"), max_results=5).cap_exhausted_possible


def test_unattributed_hits_are_counted_and_their_expressions_annotated():
    """opus5 §2.4: a genuinely relevant entity can sit in `hits` while its
    expression reports unresolved. That is an attribution artifact, not an
    abstention judgment, so it must not score as abstention."""
    r = _validate(_wire([{"slug": "warren-buffett", "matched": []}]))
    a = resolve_accounting(r, expressions=EXPRESSIONS, max_results=MAX_RESULTS)
    assert a.unattributed_hit_count == 1
    assert a.unattributed_possible is True
    assert a.unresolved_expressions == EXPRESSIONS


def test_unattributed_possible_is_false_when_every_hit_carries_attribution():
    r = _validate(_wire([{"slug": "warren-buffett", "matched": [0]}]))
    a = resolve_accounting(r, expressions=EXPRESSIONS, max_results=MAX_RESULTS)
    assert a.unattributed_hit_count == 0
    assert a.unattributed_possible is False


def test_accounting_over_an_empty_expression_list_is_honest_not_a_crash():
    """State C searches with `expressions: []` (D2)."""
    r = _validate(_wire([{"slug": "warren-buffett"}]), expressions=())
    a = resolve_accounting(r, expressions=(), max_results=MAX_RESULTS)
    assert a.matched_expressions == () and a.unresolved_expressions == ()
    assert [h.slug for h in r.hits] == ["warren-buffett"]


# --------------------------------------------------------------------------
# stage-1 (thin) validation — one rule, both stages
# --------------------------------------------------------------------------

def test_thin_retention_applies_the_identical_per_entry_rule():
    retained, violations = validate_thin_retention(
        ["warren-buffett", "ghost", "warren-buffett", "owner-earnings", 7, None],
        space=SPACE, cap=100,
    )
    assert retained == ("warren-buffett", "owner-earnings")
    assert violations == Violations(foreign_slug=1, duplicate_slug=1, malformed_entry=2)


def test_thin_retention_truncates_over_the_cap_in_returned_order():
    space = _space(*[f"s{i}" for i in range(120)])
    retained, violations = validate_thin_retention([f"s{i}" for i in range(120)], space=space, cap=100)
    assert len(retained) == 100
    assert retained[0] == "s0" and retained[-1] == "s99"
    assert violations.over_cap == 20


def test_thin_retention_at_the_cap_is_not_a_violation():
    space = _space(*[f"s{i}" for i in range(100)])
    retained, violations = validate_thin_retention([f"s{i}" for i in range(100)], space=space, cap=100)
    assert len(retained) == 100 and violations.over_cap == 0


def test_zero_foreign_identity_escapes_by_construction():
    """The §8.4 hard gate. Post-validation output is membership-checked, so the
    escaped foreign-identity rate is 0 for ANY response — this is the property
    the gate rests on, asserted over a deliberately hostile mix."""
    hostile = _wire([
        {"slug": "warren-buffett"}, {"slug": "ghost"}, {"slug": "warren-buffet"},
        {"slug": "x" * 500}, {"slug": ""}, {"slug": "../../etc/passwd"},
        {"slug": "WARREN-BUFFETT"}, {"slug": "warren buffett"}, {"slug": None},
    ])
    r = _validate(hostile)
    members = {e.slug for e in SPACE}
    assert all(h.slug in members for h in r.hits)
    assert [h.slug for h in r.hits] == ["warren-buffett"]


def test_validation_is_deterministic():
    raw = _wire(
        [{"slug": "warren-buffett", "matched": [0, 99, 1]}, {"slug": "ghost"},
         {"slug": "warren-buffett"}, {"slug": "owner-earnings", "matched": [2, 2]}],
        unresolved=[2],
    )
    first, second = _validate(raw), _validate(raw)
    assert first == second
