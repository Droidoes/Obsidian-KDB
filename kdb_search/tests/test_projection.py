"""P1.1 — text projection (#123 spec §4, blueprint §5).

The §5 grammar is frozen and golden-pinned: any "tidy" of the two G7 clauses
(split on "\\n" not splitlines(); blank lines indented) breaks these pins
deliberately. The fixture is the byte authority — 163 frozen excerpts.
"""

import json
import pathlib

import pytest

from common.wiki_io import ContentNotFoundError
from kdb_search.constants import EXCERPT_BLOCK_CEILING_BYTES, EXCERPT_POLICY_VERSION
from kdb_search.projection import (
    ProjectedEntity,
    project_entity,
    render_fat_block,
    render_thin_line,
    stream_contribution_bytes,
)
from kdb_search.types import SpaceEntity

FIXTURE = pathlib.Path(__file__).resolve().parents[2] / "benchmark/truth/task123_search_snapshot_v1"


def _identities() -> list[dict]:
    return json.loads((FIXTURE / "identities.json").read_text())


def _frozen_excerpt(slug: str, page_type: str) -> str:
    return (FIXTURE / "excerpts" / page_type / f"{slug}.txt").read_text()


def _entity(row: dict) -> SpaceEntity:
    return SpaceEntity(slug=row["slug"], title=row["title"], page_type=row["page_type"])


# --------------------------------------------------------------------------
# §5 grammar — exact bytes
# --------------------------------------------------------------------------

def test_thin_line_has_no_excerpt_and_two_space_field_separators():
    e = SpaceEntity(slug="owner-earnings", title="Owner Earnings", page_type="concept")
    assert render_thin_line(e) == "- slug: owner-earnings  title: Owner Earnings  type: concept"


def test_fat_block_grammar_identity_line_delimiters_and_four_space_content():
    e = SpaceEntity(slug="a-slug", title="A Title", page_type="concept")
    block = render_fat_block(ProjectedEntity(entity=e, excerpt="line one\nline two", truncated=False))
    assert block == (
        '- slug: a-slug  title: A Title  type: concept\n'
        '  excerpt: """\n'
        '    line one\n'
        '    line two\n'
        '  """'
    )


def test_g7_clause_1_trailing_newline_emits_a_final_whitespace_line():
    """Split on "\\n", never splitlines(): a trailing newline is a real final
    empty field line, rendered as four spaces. 161/163 fixture excerpts end
    with a newline, so this clause is load-bearing on almost the whole corpus."""
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    block = render_fat_block(ProjectedEntity(entity=e, excerpt="body\n", truncated=False))
    lines = block.split("\n")
    assert lines[2] == "    body"
    assert lines[3] == "    ", "trailing newline must emit a whitespace-only 4-space line"
    assert lines[4] == '  """'


def test_g7_clause_2_blank_lines_are_indented_too():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    block = render_fat_block(ProjectedEntity(entity=e, excerpt="a\n\nb", truncated=False))
    assert block.split("\n")[3] == "    ", "interior blank lines carry the 4-space indent"


def test_only_the_exact_two_space_delimiter_line_terminates_the_block():
    # An excerpt carrying its own triple-quote line cannot close the block early:
    # content sits at 4 spaces, the terminator at 2.
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    block = render_fat_block(ProjectedEntity(entity=e, excerpt='before\n"""\nafter', truncated=False))
    assert block.count('  """') == 2, "opening + closing delimiter only"
    assert '    """' in block, "the collided delimiter is indented as content"
    assert block.endswith('  """')


def test_delimiter_collision_is_counted_not_silently_allowed():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    p = project_entity(e, body_reader=lambda *_: 'x\n"""\ny')
    assert p.delimiter_collision_guard == 1
    clean = project_entity(e, body_reader=lambda *_: "x\ny")
    assert clean.delimiter_collision_guard == 0


# --------------------------------------------------------------------------
# excerpt policy v1 caps (word cap + sentence extension)
# --------------------------------------------------------------------------

def test_short_body_is_verbatim():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    body = "One two three. Four five."
    assert project_entity(e, body_reader=lambda *_: body).excerpt == body


def test_word_cap_extends_to_sentence_end_within_ten_percent():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    # 250 words, then 5 more completing the sentence => within the +10% (25 word) window
    body = " ".join(["w"] * 250) + " tail tail tail tail end. Next sentence here."
    ex = project_entity(e, body_reader=lambda *_: body).excerpt
    assert ex.endswith("end."), "extend to the sentence end when it lands inside the window"
    assert "Next sentence" not in ex


def test_word_cap_hard_cuts_when_no_sentence_end_inside_the_window():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    body = " ".join(["w"] * 250) + " " + " ".join(["x"] * 100) + "."
    ex = project_entity(e, body_reader=lambda *_: body).excerpt
    assert len(ex.split()) == 250, "no sentence end in the window => hard cut at word 250"


# --------------------------------------------------------------------------
# excerpt policy v2 — the hard byte ceiling (opus5 H1 / codex confirmation #3)
# --------------------------------------------------------------------------

def test_rendered_block_never_exceeds_the_byte_ceiling():
    e = SpaceEntity(slug="s" * 40, title="T" * 60, page_type="concept")
    # 60 lines x 200 chars: well under the 250-word cap, far over the byte ceiling
    body = "\n".join(["x" * 200] * 60)
    p = project_entity(e, body_reader=lambda *_: body)
    assert stream_contribution_bytes(p) <= EXCERPT_BLOCK_CEILING_BYTES
    assert p.truncated is True


def test_byte_truncation_takes_precedence_over_the_no_mid_sentence_rule():
    """When the ceiling binds, the sentence rule yields (codex confirmation minor)."""
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    # Long words: the 250-word cap is satisfied while the byte ceiling is not,
    # which is the only regime where the two rules can actually conflict.
    body = " ".join(["antidisestablishmentarianism" * 2] * 200) + " final clause here."
    p = project_entity(e, body_reader=lambda *_: body)
    assert p.truncated is True
    assert stream_contribution_bytes(p) <= EXCERPT_BLOCK_CEILING_BYTES
    assert not p.excerpt.endswith("."), "a mid-sentence cut is correct here — bytes win"


def test_truncation_lands_on_a_character_boundary():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    body = "é" * 4000  # 2 bytes each — a naive byte slice would split one
    p = project_entity(e, body_reader=lambda *_: body)
    rendered = render_fat_block(p)
    assert stream_contribution_bytes(p) <= EXCERPT_BLOCK_CEILING_BYTES
    rendered.encode().decode()  # would raise on a split multi-byte character
    assert "�" not in p.excerpt


def test_projection_is_deterministic():
    e = SpaceEntity(slug="s", title="T", page_type="concept")
    body = "\n".join(["some text here"] * 300)
    a = project_entity(e, body_reader=lambda *_: body)
    b = project_entity(e, body_reader=lambda *_: body)
    assert a.excerpt == b.excerpt and render_fat_block(a) == render_fat_block(b)


def test_policy_version_is_two():
    assert EXCERPT_POLICY_VERSION == "2"


# --------------------------------------------------------------------------
# missing body — graph/disk drift degrades to title-only (spec §4)
# --------------------------------------------------------------------------

def test_missing_body_degrades_to_title_only_and_is_flagged():
    e = SpaceEntity(slug="gone", title="Gone", page_type="concept")

    def reader(slug, page_type):
        raise ContentNotFoundError(slug, page_type, pathlib.Path("/nonexistent"))

    p = project_entity(e, body_reader=reader)
    assert p.body_missing is True
    assert p.excerpt is None
    assert render_fat_block(p) == "- slug: gone  title: Gone  type: concept"


# --------------------------------------------------------------------------
# the frozen fixture is the byte authority
# --------------------------------------------------------------------------

def test_every_fixture_entity_renders_under_the_ceiling_and_the_max_is_2209_bytes():
    """Policy v2's ceiling binds on NOTHING in fixture v1 (largest block 2,209 B)
    — the proof that no regeneration and no checksum change was needed."""
    blocks, contributions = {}, {}
    for row in _identities():
        e = _entity(row)
        frozen = _frozen_excerpt(row["slug"], row["page_type"])
        p = project_entity(e, body_reader=lambda *_, _f=frozen: _f)
        assert p.truncated is False, f"{row['slug']}: ceiling must not bind in fixture v1"
        blocks[row["slug"]] = len(render_fat_block(p).encode())
        contributions[row["slug"]] = stream_contribution_bytes(p)

    assert len(blocks) == 163
    # Both readings of "largest rendered block", reconciled: the bare block per
    # spec §4's enumeration, and the stream contribution the ratified 2,209 B
    # figure was measured as. The ceiling governs the latter.
    assert max(blocks.values()) == 2208, f"largest bare block moved: {max(blocks.values())}"
    assert max(contributions.values()) == 2209, f"largest contribution moved: {max(contributions.values())}"
    assert max(contributions.values()) < EXCERPT_BLOCK_CEILING_BYTES


def test_fixture_excerpts_exercise_both_g7_clauses():
    """The clauses are not hypothetical: 161/163 excerpts end with a newline and
    the corpus carries 377 blank lines."""
    rows = _identities()
    trailing = sum(1 for r in rows if _frozen_excerpt(r["slug"], r["page_type"]).endswith("\n"))
    blanks = sum(
        1
        for r in rows
        for line in _frozen_excerpt(r["slug"], r["page_type"]).split("\n")
        if line.strip() == ""
    )
    assert trailing == 161, f"trailing-newline count moved: {trailing}"
    assert blanks == 377, f"blank-line count moved: {blanks}"


@pytest.mark.parametrize("slug,page_type", [(r["slug"], r["page_type"]) for r in _identities()[:8]])
def test_fixture_excerpt_bytes_round_trip_into_the_grammar(slug, page_type):
    """Every content line of the frozen excerpt appears at exactly 4 spaces."""
    row = next(r for r in _identities() if r["slug"] == slug)
    frozen = _frozen_excerpt(slug, page_type)
    p = project_entity(_entity(row), body_reader=lambda *_: frozen)
    body_lines = render_fat_block(p).split("\n")[2:-1]
    assert body_lines == ["    " + line for line in frozen.split("\n")]
