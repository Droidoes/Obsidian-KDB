"""#123 P2.1f — golden byte pins for the two selector prompts.

**The rule this file enforces** (the repo's D-115-13 convention, established for
pass-2 at `compiler/tests/test_prompt_builder.py:101`): changing prompt bytes
requires bumping the prompt version **and** updating the pin here **in the same
commit**. An unversioned content change fails, so prose cannot drift away from
the version that names it or the review that approved it.

Under #123 the version lives in the *filename* (`prompts._version_of` — the file
name is the single source of the version), so "bump the version" means renaming
the file `_v1` → `_v2`. That is deliberately a visible act.

**Why the digest is not the only pin.** The compiler's pin covers one string.
Here there are two stages × four quantities, and they can drift apart:

  * `sha256` / `version` / `repo_path` are properties of the **template file**.
  * The **overhead bytes** are not. `prompts.template_overhead_bytes` renders the
    per-request wrapper with `M` and `MAX_RESULTS` substituted, so it is a
    function of `constants.py` too. Raising `MAX_RESULTS` 50 → 100 adds a byte to
    fat's rendered wrapper without touching a template — the digest pin stays
    green while the figure the M=100 budget guarantee rests on moves. So the
    overhead figures are pinned as their own literals, *and* the two constants
    they fold in are pinned beside them, so that change fails here, naming why,
    rather than surfacing as an arithmetic drift in `budget.py`.

**Why D10 is re-asserted on the rendered bytes.** `test_prompts.py` asserts the
`EVIDENCE`-before-`QUERY` order structurally. A pin file that carried only a
content hash and byte counts would stay green if a future edit swapped the two
blocks while preserving total length. These are the bytes a paid calibration run
is fired against, so the ordering claim is pinned in the artifact itself.

**`git_commit` is deliberately not pinned.** It moves with every commit; pinning
it would make this file fail on each one and train everyone to re-bless it
blindly, which is how a golden pin stops meaning anything. Content fidelity rests
on `sha256`, which is what `PromptRef` carries it for.

**Mutation sweep (12, standing repo practice): 10 caught by this file alone, 12
at package scope.** The two that this file does not catch are recorded because
each is a deliberate boundary, not a hole:

  * *`load_template` hardcodes `version = "1"`* — survives here because the file
    really is `_v1`, so the wrong value coincides with the right one. Caught by
    `test_prompts.py::test_the_version_TRACKS_the_filename_rather_than_matching_it_by_coincidence`,
    which exists for exactly this. Correct split: that file tests the loader's
    *behaviour*, this one pins *values*. Duplicating it here would put the same
    claim in two places and let one rot.
  * *the overhead pin loosened from `==` to a range* — a mutation of this file's
    own strictness, which no assertion can defend against; that is review's job,
    not a test's. Verified non-fatal: with the pin loosened, the `MAX_RESULTS`
    widening it was meant to catch is still caught, by
    `test_the_constants_folded_into_the_overhead_are_pinned`. Defense in depth,
    which is why the constants are pinned separately rather than only implied by
    the overhead figure.
"""

from __future__ import annotations

import pytest

from kdb_search import prompts
from kdb_search.budget import Stage
from kdb_search.constants import M, MAX_RESULTS, SYSTEM_TEMPLATE_BUDGET_BYTES

# --------------------------------------------------------------------------
# The pins. Update these ONLY together with a version bump (a file rename),
# in the same commit, with the prose change that moved them.
# --------------------------------------------------------------------------

#: `sha256_digest` over the loaded template TEXT (both halves, marker included).
#: Text mode, so a CRLF checkout cannot move it — `prompts.py` rule 3.
GOLDEN_DIGESTS: dict[Stage, str] = {
    "thin": "sha256:415c97f9c217aef939c6b2bcfbb1eecc1207cf85a0d8616c2aa64d5aab3ed2d3",
    "fat": "sha256:b4679b90fc62cc1675f4205f8b6e9c40155339b9bb263eb905fc1625649a37d4",
}

GOLDEN_VERSIONS: dict[Stage, str] = {"thin": "1", "fat": "1"}

GOLDEN_REPO_PATHS: dict[Stage, str] = {
    "thin": "kdb_search/prompts/selector_thin_v1.txt",
    "fat": "kdb_search/prompts/selector_fat_v1.txt",
}

#: Bytes of each half as loaded (system) and as declared (user template, slots
#: unexpanded). Split out from the overhead below because these two ARE pure
#: functions of the file, where the overhead is not.
GOLDEN_HALF_BYTES: dict[Stage, tuple[int, int]] = {
    "thin": (2_446, 96),
    "fat": (2_938, 94),
}

#: `template_overhead_bytes` — system + rendered wrapper, content slots empty,
#: widest cap. A function of the template AND of the two constants pinned below.
#: These are the figures in the blueprint's §7.0 byte table; fat is the normative
#: one (`budget.fat_worst_case_request_bytes()` is the only consumer).
GOLDEN_OVERHEAD_BYTES: dict[Stage, int] = {"thin": 2_507, "fat": 2_998}

#: The constants `template_overhead_bytes` substitutes. Pinned so that changing
#: one fails HERE — naming the coupling — instead of silently moving the overhead.
GOLDEN_OVERHEAD_INPUTS = {"M": 100, "MAX_RESULTS": 50}

STAGES: tuple[Stage, ...] = ("thin", "fat")


@pytest.fixture(autouse=True)
def _isolate_template_cache():
    """`load_template` is `@cache`d; pins must read the file, not a neighbour's
    cached copy."""
    prompts.load_template.cache_clear()
    yield
    prompts.load_template.cache_clear()


# --------------------------------------------------------------------------
# File-derived pins
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_template_digest_is_pinned(stage: Stage) -> None:
    """The content pin. Any prose edit — a word, a comma, a trailing space —
    lands here first."""
    actual = prompts.load_template(stage).ref.sha256
    assert actual == GOLDEN_DIGESTS[stage], (
        f"{stage} prompt bytes changed. This is the D-115-13 gate, not a nuisance: "
        f"rename {GOLDEN_REPO_PATHS[stage]} to bump its version, update the pin here, "
        "and land both with the prose change in ONE commit. If the change was not "
        f"intended, revert it.\n  pinned: {GOLDEN_DIGESTS[stage]}\n  actual: {actual}"
    )


@pytest.mark.parametrize("stage", STAGES)
def test_version_and_digest_are_pinned_as_a_PAIR(stage: Stage) -> None:
    """Version and digest together — that pairing IS the coupling rule. A content
    change with a stale version, or a version bump with unchanged content, is a
    defect in one direction or the other and both show up here."""
    ref = prompts.load_template(stage).ref
    assert (ref.version, ref.sha256) == (GOLDEN_VERSIONS[stage], GOLDEN_DIGESTS[stage])


@pytest.mark.parametrize("stage", STAGES)
def test_repo_path_is_pinned(stage: Stage) -> None:
    """`repo_path` is the provenance label stamped on every `StageRecord` for the
    stage, and it is a literal in `prompts.py` rather than a computed path — so it
    can silently disagree with the file that was actually loaded. Pinned against
    the filename the loader really opened."""
    ref = prompts.load_template(stage).ref
    assert ref.repo_path == GOLDEN_REPO_PATHS[stage]
    assert ref.repo_path.endswith(f"_v{ref.version}.txt"), (
        "repo_path and version are derived from the same filename; disagreement "
        "means one of them is hardcoded stale"
    )


@pytest.mark.parametrize("stage", STAGES)
def test_half_byte_counts_are_pinned(stage: Stage) -> None:
    """Pure functions of the file: the loaded SYSTEM block and the USER template
    with its slots still unexpanded."""
    template = prompts.load_template(stage)
    actual = (len(template.system.encode()), len(template.user_template.encode()))
    assert actual == GOLDEN_HALF_BYTES[stage]


# --------------------------------------------------------------------------
# Overhead pins — template AND constants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_overhead_bytes_are_pinned(stage: Stage) -> None:
    """The blueprint §7.0 figures. Fat's is normative — it is what
    `fat_worst_case_request_bytes()` consumes and what the M=100 static guarantee
    rests on, so it must not move without the guarantee being recomputed."""
    actual = prompts.template_overhead_bytes(stage)
    assert actual == GOLDEN_OVERHEAD_BYTES[stage], (
        f"{stage} template overhead moved {GOLDEN_OVERHEAD_BYTES[stage]} → {actual} B. "
        "If a template changed, see the digest pin. If not, a constant folded into "
        "the rendered wrapper changed (M / MAX_RESULTS) — recompute the §7.0 table "
        "and, for fat, the static guarantee."
    )


def test_the_constants_folded_into_the_overhead_are_pinned() -> None:
    """The coupling the digest pin cannot see (advisor catch).

    `template_overhead_bytes` renders `{{RETENTION_CAP}}` / `{{MAX_RESULTS}}` from
    `M` / `MAX_RESULTS`. Widening either changes the overhead with every template
    byte identical, so the digest pin stays green while a budgeted figure moves.
    Asserted as a *named* pin so the failure says which constant and why, rather
    than leaving a reader to explain a one-byte drift.
    """
    assert {"M": M, "MAX_RESULTS": MAX_RESULTS} == GOLDEN_OVERHEAD_INPUTS


def test_widening_a_cap_constant_really_would_move_the_overhead() -> None:
    """Proves the pin above is load-bearing rather than decorative — the digit
    count of the rendered cap is what reaches the model.

    Renders the wrapper at the pinned cap and at a wider one and asserts the byte
    count differs, so nobody can later 'simplify' the constants pin away on the
    grounds that the digest already covers everything.
    """
    at_pin = prompts.render_fat_messages(evidence="", query="", max_results=MAX_RESULTS)
    wider = prompts.render_fat_messages(evidence="", query="", max_results=MAX_RESULTS * 10)
    assert len(wider.user.encode()) > len(at_pin.user.encode())


@pytest.mark.parametrize("stage", STAGES)
def test_the_pinned_overhead_still_fits_the_declared_reserve(stage: Stage) -> None:
    """The pins and `SYSTEM_TEMPLATE_BUDGET_BYTES` must not disagree.

    `test_prompts.py` asserts the measured overhead fits the reserve; this asserts
    the *pinned* figure does. The two together mean a pin cannot be updated to a
    value that breaks the reserve without a second failure naming the reserve.
    """
    assert GOLDEN_OVERHEAD_BYTES[stage] <= SYSTEM_TEMPLATE_BUDGET_BYTES


# --------------------------------------------------------------------------
# Ordering, pinned in the artifact itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_D10_ordering_is_pinned_in_the_rendered_bytes(stage: Stage) -> None:
    """D10 in the frozen artifact: `EVIDENCE` precedes `QUERY`, and the query is
    last.

    Re-asserted here, not only in `test_prompts.py`, because a content-hash pin
    plus byte counts would stay green under a length-preserving swap of the two
    blocks — and these are the exact bytes calibration is fired against.
    """
    messages = (
        prompts.render_thin_messages(evidence="", query="", retention_cap=M)
        if stage == "thin"
        else prompts.render_fat_messages(evidence="", query="", max_results=MAX_RESULTS)
    )
    evidence_at = messages.user.index("EVIDENCE:")
    query_at = messages.user.index("QUERY:")
    assert evidence_at < query_at
    assert messages.user.rstrip().endswith("QUERY:"), (
        "with an empty query slot the QUERY header is the last thing in the "
        "message — the query sits adjacent to the generation point (D10)"
    )


# --------------------------------------------------------------------------
# What is deliberately NOT pinned
# --------------------------------------------------------------------------


def test_git_commit_is_deliberately_NOT_pinned() -> None:
    """Recorded as a decision, so nobody 'completes' the pin set by adding it.

    `git_commit` moves with every commit. Pinning it would fail this file on each
    one and train the team to re-bless pins without reading them, which destroys
    the signal the other pins carry. It is provenance colour; fidelity rests on
    `sha256`.
    """
    ref = prompts.load_template("fat").ref
    assert ref.sha256 == GOLDEN_DIGESTS["fat"]
    # Present and a string — it just is not pinned to a value.
    assert isinstance(ref.git_commit, str) and ref.git_commit
    assert ref.git_commit not in GOLDEN_DIGESTS.values()


def test_every_pinned_stage_is_a_real_stage_the_loader_serves() -> None:
    """Guards the pin tables themselves: a stage renamed in `prompts._FILENAMES`
    without a pin update would otherwise leave a table entry pinning nothing and
    the new stage unpinned — the parameterized tests above only iterate `STAGES`.
    """
    assert set(STAGES) == set(prompts._FILENAMES)
    for table in (
        GOLDEN_DIGESTS,
        GOLDEN_VERSIONS,
        GOLDEN_REPO_PATHS,
        GOLDEN_HALF_BYTES,
        GOLDEN_OVERHEAD_BYTES,
    ):
        assert set(table) == set(STAGES)
