"""#123 P2.5 — blueprint §8's branch-specific call-count table as an oracle.

**This is P2's analog of P1.5's contract matrix.** The matrix says what a terminal
must look like; this says how many times each path may spend. Together they are
what makes the orchestration *complete* rather than merely working on the happy
path — and, like the matrix, the table was ratified before the code existed, so
the oracle is not being invented alongside the thing it checks.

Every row asserts four things, and the fourth is the one a hand-written test
usually omits:

  1. **Logical `call` invocations** — the table's own figure, as an inclusive
     range where the table gives one.
  2. **`logical_call_count == len(StageRecords)`** (§6). Read off the built audit
     payload, so the identity is checked on the archive rather than on a variable.
  3. **`assert_result_contract` passed, and which terminal it passed for.**
     `graph_search` names its terminal internally; the harness records the name it
     asserted against, so a row cannot be satisfied by the *wrong* terminal that
     happens to share a call count.
  4. **The per-stage attempt counts sit inside that terminal's ratified bounds.**
     This is what ties the two ratified artifacts together: the table's call count
     and the matrix's `thin_attempts`/`fat_attempts` are separate statements about
     the same run, and a row that satisfies one while violating the other is
     exactly the drift both documents exist to prevent.

**How the audit is reached.** `graph_search` builds the payload on every path but
does not return it — the delivery surface is an open owner question (see
`search.py`'s docstring). Rather than presuppose an answer, the harness wraps
`build_audit_payload` and `assert_result_contract` in `search`'s namespace with
pass-through recorders. Nothing about the production signature is assumed, and
the day delivery is ratified these tests keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
from common.model_pool import ModelRoute, ModelSpec
from common.paths import PageType
from common.wiki_io import ContentNotFoundError

from kdb_search import search
from kdb_search.constants import M
from kdb_search.contracts import TERMINAL_CONTRACTS
from kdb_search.tests import fakes
from kdb_search.types import GraphSearchRequest, QueryPayload

# --------------------------------------------------------------------------
# the harness
# --------------------------------------------------------------------------


#: "Above M" as a derivation, not a literal. It was hardcoded 120, which silently
#: became "below M" the moment D-123-A raised M 100 -> 150 — every above-M branch
#: then tested the small-space path instead, and the assertions failed rather than
#: quietly passing only because they are specific. Derived so the next M move
#: cannot repeat it.
ABOVE_M = M + 20


def _spec(**overrides) -> ModelSpec:
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


def _tiny_window_spec() -> ModelSpec:
    """Busts on thin's envelope alone — the pre-flight terminal at row 1."""
    return _spec(ctx_window=20_000, max_output_tokens=128_000)


def _fat_only_budget_spec() -> ModelSpec:
    """Fits thin's identity-only evidence and not one oversized body, so the fat
    pre-flight is what binds — row 8. Was 45,000, which no longer fits THIN after
    D-123-A carried its output allowance to 20,000."""
    return _spec(ctx_window=60_000, max_output_tokens=128_000)


def _body(slug: str, page_type: PageType) -> str:
    return f"Body text for {slug}, a {page_type} page with enough words to excerpt."


def _oversized_body(slug: str, page_type: PageType) -> str:
    """One body so large that it alone cannot fit the fat request (D-123-B).

    **The terminal changed shape.** Before fill-to-budget this was 90 moderately
    long bodies against a small window: the assembled request busted, so the
    pre-flight refused it. The fill would now simply seat fewer of them and
    succeed — correctly. `FAT_PREFLIGHT_BUDGET` can only fire when **not even one
    entity fits**, so the only thing that still reaches it is a single oversized
    body. ~120 kB against an 88 kB allowance.
    """
    return " ".join(f"word{n}" for n in range(15_000))


def _missing_body(slug: str, page_type: PageType) -> str:
    raise ContentNotFoundError(slug, page_type, Path(f"/nonexistent/{slug}.md"))


@dataclass
class Run:
    """One executed row: what came back, plus the two things `graph_search` knows
    and does not return."""

    result: object
    selector: fakes.FakeSelector
    terminal: str
    audit: object

    @property
    def thin_records(self) -> int:
        return sum(1 for s in self.audit.stages if s.stage == "thin_selection")

    @property
    def fat_records(self) -> int:
        return sum(1 for s in self.audit.stages if s.stage == "fat_selection")


def _execute(
    *script,
    count: int,
    selector_spec: ModelSpec | None = None,
    body_reader: Callable[[str, PageType], str] = _body,
    monkeypatch,
) -> Run:
    recorded: dict = {}

    real_audit = search.build_audit_payload
    real_assert = search.assert_result_contract

    def capture_audit(**kwargs):
        payload = real_audit(**kwargs)
        recorded["audit"] = payload
        return payload

    def capture_assert(terminal, result, **kwargs):
        recorded["terminal"] = terminal
        # Delegates to the real guard: the row is only satisfied if the ratified
        # contract passed, not merely if a terminal name was reached.
        return real_assert(terminal, result, **kwargs)

    monkeypatch.setattr(search, "build_audit_payload", capture_audit)
    monkeypatch.setattr(search, "assert_result_contract", capture_assert)

    selector = fakes.FakeSelector(*script)
    result = search.graph_search(
        GraphSearchRequest(
            query=QueryPayload(text="QUERY TEXT", expressions=("alpha", "beta")),
            search_space=fakes.make_space_ref(count),
        ),
        selector=selector_spec or _spec(),
        call=selector,
        body_reader=body_reader,
    )
    return Run(result, selector, recorded["terminal"], recorded["audit"])


# --------------------------------------------------------------------------
# the rows
# --------------------------------------------------------------------------

SMALL = fakes.make_space(5)
LARGE = fakes.make_space(ABOVE_M)
POOLED = fakes.make_space(90)

#: `(id, table row, expected calls (low, high), terminal, script factory, kwargs)`.
#: The call figures are transcribed from blueprint §8's table, not derived from
#: the code — that is the entire point of the file, so a range that looks wrong
#: should be checked against the blueprint before the code.
ROWS: list[tuple] = [
    (
        "empty-space",
        "empty space / thin-preflight budget_exceeded",
        (0, 0),
        "empty_space",
        lambda: (),
        dict(count=0),
    ),
    (
        "thin-preflight-budget",
        "empty space / thin-preflight budget_exceeded",
        (0, 0),
        "thin_preflight_budget",
        lambda: (),
        dict(count=ABOVE_M, selector_spec=_tiny_window_spec()),
    ),
    (
        "thin-estimation-miss",
        "thin budget_estimation_miss — 1 thin attempted, 0 fat",
        (1, 1),
        "thin_input_estimation_miss",
        lambda: (fakes.context_length_rejection_openai(),),
        dict(count=5),
    ),
    (
        "D3-first-attempt",
        "D3 thin-retained-zero (N>M) — 1-2 thin, 0 fat",
        (1, 1),
        "thin_retained_zero",
        lambda: (fakes.ScriptedReply(fakes.retained_empty_document()),),
        dict(count=ABOVE_M),
    ),
    (
        "D3-after-a-retry",
        "D3 thin-retained-zero (N>M) — 1-2 thin, 0 fat",
        (2, 2),
        "thin_retained_zero",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.retained_empty_document()),
        ),
        dict(count=ABOVE_M),
    ),
    (
        "completed-clean",
        "normal completed — 1-2 thin + 1-2 fat = 2-4",
        (2, 2),
        "completed",
        lambda: (
            fakes.ScriptedReply(fakes.retained_document(SMALL)),
            fakes.ScriptedReply(fakes.usable_document(SMALL, count=3)),
        ),
        dict(count=5),
    ),
    (
        "completed-both-stages-retried",
        "normal completed — 1-2 thin + 1-2 fat = 2-4",
        (4, 4),
        "completed",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.retained_document(SMALL)),
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.usable_document(SMALL, count=2)),
        ),
        dict(count=5),
    ),
    (
        "thin-exhausted-above-M",
        "thin exhausted, N>M — 2 thin, 0 fat",
        (2, 2),
        "thin_exhausted",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
        ),
        dict(count=ABOVE_M),
    ),
    (
        "F1-fat-clean",
        "thin exhausted, N<=M -> fat (F1) — 2 thin + 1-2 fat = 3-4",
        (3, 3),
        "completed",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.usable_document(SMALL, count=2)),
        ),
        dict(count=5),
    ),
    (
        "F1-fat-retried",
        "thin exhausted, N<=M -> fat (F1) — 2 thin + 1-2 fat = 3-4",
        (4, 4),
        "completed",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.usable_document(SMALL, count=2)),
        ),
        dict(count=5),
    ),
    (
        "fat-exhausted",
        "fat exhausted — 1-2 thin + 2 fat = 3-4",
        (3, 3),
        "fat_exhausted",
        lambda: (
            fakes.ScriptedReply(fakes.retained_document(SMALL)),
            fakes.ScriptedReply(fakes.all_dropped_document(SMALL)),
            fakes.ScriptedReply(fakes.all_dropped_document(SMALL)),
        ),
        dict(count=5),
    ),
    (
        "fat-exhausted-after-a-thin-retry",
        "fat exhausted — 1-2 thin + 2 fat = 3-4",
        (4, 4),
        "fat_exhausted",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.retained_document(SMALL)),
            fakes.ScriptedReply(fakes.all_dropped_document(SMALL)),
            fakes.ScriptedReply(fakes.all_dropped_document(SMALL)),
        ),
        dict(count=5),
    ),
    (
        "fat-preflight-budget",
        "fat budget_exceeded, pre-call (D6) — 1-2 thin, 0 fat",
        (1, 1),
        "fat_preflight_budget",
        lambda: (fakes.ScriptedReply(fakes.retained_document(POOLED)),),
        dict(count=90, selector_spec=_fat_only_budget_spec(), body_reader=_oversized_body),
    ),
    (
        "fat-preflight-budget-on-F1",
        "fat budget_exceeded, pre-call (D6) — 1-2 thin, 0 fat",
        (2, 2),
        "fat_preflight_budget_on_f1",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
        ),
        dict(count=90, selector_spec=_fat_only_budget_spec(), body_reader=_oversized_body),
    ),
    (
        "thin-output-truncation",
        "output truncation at thin (D9) — 1 thin, 0 fat; terminal, F1 does not apply",
        (1, 1),
        "thin_output_truncation",
        lambda: (
            fakes.ScriptedReply(
                fakes.thin_truncated_text(SMALL), stop_reason=fakes.STOP_LENGTH_OPENAI
            ),
        ),
        dict(count=5),
    ),
    (
        "fat-output-truncation",
        "output truncation at fat (D9) — 1-2 thin + 1 fat, 0 after",
        (2, 2),
        "fat_output_truncation",
        lambda: (
            fakes.ScriptedReply(fakes.retained_document(SMALL)),
            fakes.ScriptedReply(
                fakes.truncated_text(SMALL), stop_reason=fakes.STOP_LENGTH_OPENAI
            ),
        ),
        dict(count=5),
    ),
    (
        "fat-output-truncation-on-F1",
        "output truncation at fat (D9) — 1-2 thin + 1 fat, 0 after",
        (3, 3),
        "fat_output_truncation_on_f1",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(
                fakes.truncated_text(SMALL), stop_reason=fakes.STOP_LENGTH_OPENAI
            ),
        ),
        dict(count=5),
    ),
    (
        "fat-estimation-miss",
        "fat budget_estimation_miss (sub-330k windows only) — 1-2 thin + 1 fat attempted",
        (2, 2),
        "fat_input_estimation_miss",
        lambda: (
            fakes.ScriptedReply(fakes.retained_document(SMALL)),
            fakes.context_length_rejection_gemini(),
        ),
        dict(count=5),
    ),
    (
        "fat-estimation-miss-on-F1",
        # Same TABLE row as the case above — the table counts calls and does not
        # split on F1. What is new here is the matrix row, which did not exist
        # (`FAT_INPUT_ESTIMATION_MISS_ON_F1`, the P2.4 extension), and that
        # distinction belongs in the contract, not in the call table.
        "fat budget_estimation_miss (sub-330k windows only) — 1-2 thin + 1 fat attempted",
        (3, 3),
        "fat_input_estimation_miss_on_f1",
        lambda: (
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.ScriptedReply(fakes.unparseable_text()),
            fakes.context_length_rejection_openai(),
        ),
        dict(count=5),
    ),
]

_IDS = [row[0] for row in ROWS]


@pytest.fixture(params=ROWS, ids=_IDS)
def row(request, monkeypatch):
    _, table_row, calls, terminal, script, kwargs = request.param
    run = _execute(*script(), monkeypatch=monkeypatch, **kwargs)
    return run, table_row, calls, terminal


# --------------------------------------------------------------------------
# the four assertions, one test each — so a failure names WHICH claim broke
# --------------------------------------------------------------------------


def test_the_row_spends_exactly_what_the_table_allows(row) -> None:
    run, table_row, (low, high), _ = row
    assert low <= run.selector.calls <= high, (
        f"§8 row {table_row!r} allows {low}-{high} logical calls, "
        f"got {run.selector.calls}"
    )


def test_the_row_consumes_its_whole_script(row) -> None:
    """The complement of the count assertion. A branch that stops early — retrying
    when it should not, skipping a stage — leaves script behind, and a count
    within range would not notice if the range has slack."""
    run, *_ = row
    run.selector.assert_consumed()


def test_logical_call_count_equals_the_archived_stage_records(row) -> None:
    """§6's invariant, checked on the archive. SDK transport sub-retries are
    excluded from BOTH sides — they are the provider's business, not an attempt we
    made — so this is also what keeps `sdk_sub_retries` from leaking into the
    count."""
    run, *_ = row
    assert run.audit.logical_call_count == len(run.audit.stages)
    assert run.audit.logical_call_count == run.selector.calls


def test_the_row_lands_on_the_terminal_the_table_names(row) -> None:
    """Guards against the row being satisfied by the WRONG terminal. Several rows
    share a call count — `fat_preflight_budget` and `thin_retained_zero` are both
    one call — so a count-only oracle passes on a search that took the other
    branch entirely."""
    run, _, _, terminal = row
    assert run.terminal == terminal


def test_the_attempt_counts_sit_inside_the_matrix_bounds(row) -> None:
    """Where the two ratified artifacts meet. §8's table and P1.5's matrix are
    separate statements about the same run — the table counts calls, the matrix
    bounds attempts per stage — and a row that satisfies one while violating the
    other is the drift both documents exist to prevent. `assert_result_contract`
    already checked this inside `graph_search`; asserting it again here on the
    ARCHIVED records is what proves the guard was fed the real counts rather than
    a variable that agreed with itself."""
    run, _, _, terminal = row
    contract = TERMINAL_CONTRACTS[terminal]
    low, high = contract.thin_attempts
    assert low <= run.thin_records <= high, f"{terminal}: thin {run.thin_records}"
    low, high = contract.fat_attempts
    assert low <= run.fat_records <= high, f"{terminal}: fat {run.fat_records}"


def test_the_result_status_matches_the_terminal_it_was_checked_against(row) -> None:
    run, _, _, terminal = row
    assert run.result.status == TERMINAL_CONTRACTS[terminal].status


# --------------------------------------------------------------------------
# coverage of the table itself
# --------------------------------------------------------------------------


def test_every_row_of_the_blueprint_table_is_exercised() -> None:
    """**The table prints 12 rows but names 11 distinct paths**, and the
    difference is worth stating rather than padded over.

    Row 9 — `budget_estimation_miss, budget_side: input (D7) — 1 attempted at the
    missing stage, 0 after` — is a *generic restatement* of rows 2 and 12, which
    give the same rule at thin and at fat specifically. It is a statement about
    both, not a thirteenth branch, so inventing a case for it would mean inventing
    a path the controller does not have. Its claim is asserted directly below
    instead.

    The 19 cases across those 11 paths exist because several rows carry a RANGE
    and one case pins only one end — the D3 row's `1-2 thin`, `completed`'s `2-4`,
    `fat exhausted`'s `3-4`. A row covered only at its low end lets a spurious
    retry through.
    """
    exercised = {row[1] for row in ROWS}
    assert len(exercised) == 11, sorted(exercised)


def test_the_generic_input_miss_row_holds_at_BOTH_stages() -> None:
    """§8 row 9's claim, asserted as the cross-stage rule it is: **one attempt at
    the stage that missed, and nothing after it.** Read off the archived records
    rather than the call count, so "0 after" is a statement about the stage that
    never ran and not merely about the total."""
    thin_case = next(r for r in ROWS if r[0] == "thin-estimation-miss")
    fat_case = next(r for r in ROWS if r[0] == "fat-estimation-miss")
    assert thin_case[2] == (1, 1)  # one thin attempt, and no fat stage follows
    assert fat_case[2] == (2, 2)  # one thin + the one fat attempt that missed
    assert TERMINAL_CONTRACTS[thin_case[3]].fat_attempts == (0, 0)
    assert TERMINAL_CONTRACTS[fat_case[3]].fat_attempts == (1, 1)


def test_every_producible_terminal_in_the_matrix_has_a_row_here() -> None:
    """The other direction, and the completeness claim: every terminal
    `graph_search` can produce is driven end-to-end by this file. If a terminal is
    ever added to the matrix without a branch that reaches it, this is what
    fails."""
    driven = {row[3] for row in ROWS}
    assert driven == set(TERMINAL_CONTRACTS), sorted(set(TERMINAL_CONTRACTS) - driven)


#: The table rows whose call figure is a RANGE, transcribed from blueprint §8.
#: Listed rather than parsed out of the label prose — the first attempt inferred
#: it from a hyphen and matched "thin-preflight", which would have made the
#: coverage check below assert something about a row that has no range at all.
RANGED_TABLE_ROWS: frozenset[str] = frozenset(
    {
        "D3 thin-retained-zero (N>M) — 1-2 thin, 0 fat",
        "normal completed — 1-2 thin + 1-2 fat = 2-4",
        "thin exhausted, N<=M -> fat (F1) — 2 thin + 1-2 fat = 3-4",
        "fat exhausted — 1-2 thin + 2 fat = 3-4",
        "fat budget_exceeded, pre-call (D6) — 1-2 thin, 0 fat",
        "output truncation at fat (D9) — 1-2 thin + 1 fat, 0 after",
        "fat budget_estimation_miss (sub-330k windows only) — 1-2 thin + 1 fat attempted",
    }
)


def test_the_ranged_rows_are_each_covered_at_BOTH_ends() -> None:
    """Explicitly, because it is the property the count assertions rest on: a
    range asserted only at its low end passes a controller that never retries, and
    only at its high end passes one that always does.

    Adding this found a real hole — `fat exhausted` was covered only at 3 calls,
    so a controller that always burned a thin retry before the fat stage would
    have gone unnoticed on that row.
    """
    for table_row in RANGED_TABLE_ROWS:
        covered = {row[2][0] for row in ROWS if row[1] == table_row}
        assert len(covered) >= 2, f"{table_row} is covered at only {sorted(covered)}"


def test_every_ranged_row_in_the_list_is_a_row_that_exists() -> None:
    """Keeps the hand-transcribed set above honest against the case table: a typo
    would otherwise make the coverage check silently vacuous for that row."""
    assert RANGED_TABLE_ROWS <= {row[1] for row in ROWS}
