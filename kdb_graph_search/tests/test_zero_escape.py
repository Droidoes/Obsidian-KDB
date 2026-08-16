"""P1.3 — the zero-foreign-identity-escape property (#123 §8.4 hard gate).

The gate says the escaped foreign-identity rate is **0 by construction**: whatever
a selector returns, every slug in `hits` is a member of the search space. The
targeted cases in `test_response.py` assert it for hand-picked hostile inputs; this
asserts it over a broad generated sweep, including responses no fixture author
would think to write.

Seeded `random.Random` rather than a property-testing library: hypothesis is not a
declared dependency, and adding one for a single sweep buys shrinking we do not
need. A fixed seed keeps every failure reproducible, and the seed list is the
knob if the sweep ever needs widening.
"""

from __future__ import annotations

import json
import random

import pytest

from kdb_graph_search.constants import (
    MAX_EXPRESSIONS,
    MAX_RESULTS,
    MAX_SLUG_LEN,
    WIRE_LABEL_ALPHABET,
)
from kdb_graph_search.response import resolve_accounting, validate_response, validate_thin_retention
from kdb_graph_search.types import SpaceEntity

SPACE = tuple(
    SpaceEntity(slug=f"member-{i}", title=f"Member {i}", page_type="concept") for i in range(40)
)
MEMBERS = tuple(e.slug for e in SPACE)
EXPRESSIONS = tuple(f"expression-{i}" for i in range(MAX_EXPRESSIONS))

#: Slug-shaped values that are NOT members. Every one must be dropped.
FOREIGN_POOL = (
    "member",                    # prefix of a member
    "member-",                   # near-miss
    "member-0 ",                 # trailing space
    " member-0",                 # leading space
    "MEMBER-0",                  # case variant
    "member–0",                  # en-dash homoglyph
    "member-0/../member-1",      # path traversal
    "../../etc/passwd",
    "member-999",                # plausible but absent
    "x" * (MAX_SLUG_LEN + 1),    # over the length bound
    "x" * MAX_SLUG_LEN,          # at the bound, still not a member
    "",
    "member-0\n",
    "member-0\x00",         # embedded NUL
    "member-0\t",
    "член-0",
    "🙂",
)


#: Wire label values, mixed so the sweep exercises every decode branch. Under
#: D11 `matched` carries LETTERS, so an all-integer generator would make every
#: value an unknown-expression coercion — leaving `matched_expressions` uniformly
#: empty and the partition assertion below passing trivially. A generator whose
#: values can never resolve tests nothing, so valid and wrong-case labels are
#: drawn deliberately alongside the hostile ones.
VALID_LABELS = tuple(WIRE_LABEL_ALPHABET[:MAX_EXPRESSIONS])
WRONG_CASE_LABELS = tuple(label.lower() for label in VALID_LABELS)  # coerced, not dropped
UNRESOLVABLE_LABELS = (
    "Z", "AA", "a1", "", " A", "A ", "A.", "0", "-1",   # not the verbatim echo
    *(str(i) for i in range(3)),                          # the D8 index form, now foreign
)


def _random_label_list(rng: random.Random) -> list:
    pool = (
        VALID_LABELS
        + WRONG_CASE_LABELS
        + UNRESOLVABLE_LABELS
        + (True, False, None, 0, 1, 1.5, [], {"k": "v"})  # wrong-typed
    )
    return [rng.choice(pool) for _ in range(rng.randint(0, 12))]


def _random_matched(rng: random.Random) -> object:
    return rng.choice(
        [
            _random_label_list(rng),
            [rng.choice(VALID_LABELS)],
            [rng.choice(WRONG_CASE_LABELS)],
            rng.choice(["not-a-list", 7, {"k": "v"}, None]),
            [],
        ]
    )


def _random_entry(rng: random.Random) -> object:
    kind = rng.random()
    if kind < 0.10:
        return rng.choice(["a string", 7, None, [], {}])
    if kind < 0.20:
        return {"matched": _random_matched(rng)}  # no slug
    if kind < 0.30:
        return {"slug": rng.choice([None, 7, [], {}, True]), "matched": _random_matched(rng)}
    slug = rng.choice(MEMBERS) if kind < 0.65 else rng.choice(FOREIGN_POOL)
    entry: dict = {"slug": slug}
    if rng.random() < 0.8:
        entry["matched"] = _random_matched(rng)
    if rng.random() < 0.2:
        # Attacker-supplied identity metadata that must never be believed.
        entry["title"] = "ATTACKER TITLE"
        entry["page_type"] = "article"
    return entry


def _random_document(rng: random.Random) -> str:
    body: dict = {"selections": [_random_entry(rng) for _ in range(rng.randint(0, 70))]}
    if rng.random() < 0.6:
        body["unresolved"] = _random_label_list(rng)
    return json.dumps(body)


def test_the_generator_actually_reaches_both_decode_outcomes():
    """A liveness check on the sweep itself, not on the validator.

    The generator is the sweep's only source of coverage, and a silent way to
    lose it is for every generated `matched` value to stop resolving — which is
    exactly what happened when D11 moved the wire from indices to labels while an
    integer generator stayed behind. The remaining assertions would all still have
    passed, over a population where no attribution ever survived. So: prove the
    sweep produces resolved attributions AND coercions before trusting what it
    says about escapes.
    """
    rng = random.Random(99)
    resolved = coerced = 0
    for _ in range(400):
        response = validate_response(
            _random_document(rng), space=SPACE, expressions=EXPRESSIONS, max_results=MAX_RESULTS
        )
        resolved += sum(len(hit.matched_expressions) for hit in response.hits)
        coerced += response.attempted_violations.unknown_expression
    assert resolved > 0, "no generated label ever resolved — the sweep tests nothing"
    assert coerced > 0, "no generated label was ever coerced away"


@pytest.mark.parametrize("seed", range(40))
def test_no_foreign_identity_ever_escapes_validation(seed):
    rng = random.Random(seed)
    members = set(MEMBERS)
    by_slug = {e.slug: e for e in SPACE}
    for _ in range(60):
        raw = _random_document(rng)
        response = validate_response(
            raw, space=SPACE, expressions=EXPRESSIONS, max_results=MAX_RESULTS
        )
        for hit in response.hits:
            assert hit.slug in members, f"foreign identity escaped: {hit.slug!r} from {raw[:200]}"
            # Identity metadata comes from the space, never from the wire.
            assert hit.title == by_slug[hit.slug].title
            assert hit.page_type == by_slug[hit.slug].page_type
            for expression in hit.matched_expressions:
                assert expression in EXPRESSIONS


@pytest.mark.parametrize("seed", range(20))
def test_every_invariant_holds_on_arbitrary_input(seed):
    """The bounds are properties of the validator, not of the input it happened to
    receive: no duplicates, never over cap, attribution always in range."""
    rng = random.Random(1_000 + seed)
    for _ in range(60):
        response = validate_response(
            _random_document(rng), space=SPACE, expressions=EXPRESSIONS, max_results=MAX_RESULTS
        )
        slugs = [hit.slug for hit in response.hits]
        assert len(slugs) == len(set(slugs)), "duplicate slug survived"
        assert len(slugs) <= MAX_RESULTS
        for hit in response.hits:
            matched = hit.matched_expressions
            assert len(matched) == len(set(matched)), "duplicate attribution survived"
            assert len(matched) <= MAX_EXPRESSIONS
        assert response.classification in {
            "unparseable_response", "structurally_unusable_response",
            "all_entries_dropped", "usable",
        }
        yield_ = response.valid_entry_yield
        assert yield_ is None or 0.0 <= yield_ <= 1.0


@pytest.mark.parametrize("seed", range(20))
def test_accounting_never_invents_or_loses_an_expression(seed):
    """matched and unresolved partition the request's expressions exactly — no
    expression is dropped, duplicated across both, or invented."""
    rng = random.Random(2_000 + seed)
    for _ in range(60):
        response = validate_response(
            _random_document(rng), space=SPACE, expressions=EXPRESSIONS, max_results=MAX_RESULTS
        )
        accounting = resolve_accounting(
            response, expressions=EXPRESSIONS, max_results=MAX_RESULTS
        )
        matched = set(accounting.matched_expressions)
        unresolved = set(accounting.unresolved_expressions)
        assert matched.isdisjoint(unresolved)
        assert matched | unresolved == set(EXPRESSIONS)
        assert len(accounting.matched_expressions) + len(accounting.unresolved_expressions) == len(
            EXPRESSIONS
        )
        assert accounting.unattributed_hit_count <= len(response.hits)


@pytest.mark.parametrize("seed", range(20))
def test_thin_retention_holds_the_same_invariants(seed):
    """One rule, both stages — so the property has to hold on the thin path too."""
    rng = random.Random(3_000 + seed)
    members = set(MEMBERS)
    for _ in range(60):
        candidates = [
            rng.choice(MEMBERS) if rng.random() < 0.6 else rng.choice(FOREIGN_POOL + (None, 7, [], {}))
            for _ in range(rng.randint(0, 140))
        ]
        retained, _violations = validate_thin_retention(candidates, space=SPACE, cap=100)
        assert all(slug in members for slug in retained)
        assert len(retained) == len(set(retained))
        assert len(retained) <= 100
        # Returned order is preserved among the survivors.
        order = [s for s in candidates if isinstance(s, str) and s in members]
        seen: list[str] = []
        for slug in order:
            if slug not in seen:
                seen.append(slug)
        assert list(retained) == seen[:100]
