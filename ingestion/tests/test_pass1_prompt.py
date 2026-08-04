# ingestion/tests/test_pass1_prompt.py
from ingestion.enrich.pass1_prompt import build_pass1_prompt, PASS1_PROMPT_VERSION


def test_build_pass1_prompt_includes_all_domain_ids():
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    # All 23 domain IDs must appear in the prompt for LLM to classify
    assert "ai-ml" in prompt
    assert "value-investing" in prompt
    assert "undecided" in prompt


def test_build_pass1_prompt_includes_all_source_type_ids():
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    assert "blog" in prompt
    assert "interview" in prompt
    assert "chat-log" in prompt
    assert "other" in prompt


def test_build_pass1_prompt_includes_source_text():
    prompt = build_pass1_prompt(source_text="my essay content", source_path="x.md")
    assert "my essay content" in prompt


def test_prompt_version_is_set():
    assert PASS1_PROMPT_VERSION  # truthy, semver-shaped
    parts = PASS1_PROMPT_VERSION.split(".")
    assert len(parts) == 3


def test_prompt_does_not_use_shape_word():
    """Per [[feedback_drop_the_word_shape]]."""
    prompt = build_pass1_prompt(source_text="x", source_path="x.md")
    assert "shape" not in prompt.lower()


def test_prompt_renders_boundary_rules_as_separate_block():
    """Per D-NW7-6: scope texts + §3 boundary rules render as sibling blocks."""
    prompt = build_pass1_prompt(source_text="x", source_path="x.md")
    # Look for a header indicating boundary rules section
    assert "boundary" in prompt.lower() or "disambiguation" in prompt.lower()


def test_prompt_does_not_mention_force_signal_or_force_noise():
    """Per D-89-3 §4.5: LLM does not see the path lists."""
    prompt = build_pass1_prompt(source_text="x", source_path="Daily Notes/2026-05-26.md")
    assert "force_signal" not in prompt
    assert "force_noise" not in prompt


# ---------------------------------------------------------------------------
# Task #126 — `entity_search_keys` re-specified for semantic selection
#
# The field was introduced under D-89-20 with one consumer: a DETERMINISTIC
# PK/regex lookup, where imperfect keys were harmless by design ("imperfect
# slugs simply miss, no harm"). #123 retired that consumer and made the field
# the selector's query expressions, where a key that fails to express intent
# burns one of ten slots. The prompt still instructed for the retired contract.
#
# Measured over the 39 ratified probes BEFORE this change: 138 of 263 expression
# slots (52.5%) were verbatim `key_themes` copies, and all five E-class
# abstention probes were 1-of-1 duplicates.
# ---------------------------------------------------------------------------

import re

_EXAMPLE = re.compile(
    r"key_themes \[(?P<themes>[^\]]*)\]\)\s*\n\s*→ `\[(?P<keys>[^`]*)\]`",
    re.MULTILINE,
)


def _slugs(blob: str) -> list[str]:
    return re.findall(r'"([^"]+)"', blob)


def _examples():
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    return [
        (_slugs(m.group("themes")), _slugs(m.group("keys")))
        for m in _EXAMPLE.finditer(prompt)
    ]


def test_the_worked_examples_are_actually_parseable():
    """Guards the three assertions below: a regex that silently matched nothing
    would make every one of them vacuously true."""
    examples = _examples()
    assert len(examples) == 3
    assert all(themes and keys for themes, keys in examples)


def test_NO_worked_example_repeats_a_key_themes_slug():
    """The load-bearing edit. Deleting the "include each `key_themes` slug" rule
    is not enough on its own — every example USED to open by restating the
    themes verbatim, so the examples taught the duplication that the rule
    merely licensed. Examples ground shape more strongly than a rule states it.
    """
    for themes, keys in _examples():
        overlap = sorted(set(themes) & set(keys))
        assert not overlap, f"example repeats key_themes slugs: {overlap}"


def test_the_prompt_does_not_instruct_the_model_to_copy_key_themes():
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    assert "Include each `key_themes` slug" not in prompt
    assert "Do NOT repeat `key_themes`" in prompt


def test_the_keys_are_framed_as_QUERY_TERMS_not_as_lookup_identifiers():
    """The old framing — "these seed a later entity lookup, so emit the
    canonical form a reader would search by" — optimises for string identity,
    which was exactly right for a PK lookup and is the wrong objective for an
    LLM selector that needs the key to express WHAT TO LOOK FOR."""
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    assert "seed a later entity lookup" not in prompt
    assert "canonical form a reader would search by" not in prompt
    assert "search's query terms" in prompt


def test_an_empty_key_list_is_declared_valid():
    """A consequence of dropping the copy rule: a source engaging nothing beyond
    its themes now has nothing to add. Saying so explicitly stops the model
    padding to fill the field — the failure the old rule guaranteed."""
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    assert "an empty list" in prompt and "padding is a defect" in prompt


def test_the_author_sentinel_asks_for_the_JSON_LITERAL_not_the_word():
    """Q2b. "null otherwise" invited the four-character string "null", which
    `{"type": ["string", "null"]}` accepts — 9 of the 39 probes carry it against
    5 with a genuine null."""
    prompt = build_pass1_prompt(source_text="dummy", source_path="dummy.md")
    assert "null otherwise" not in prompt
    assert 'NOT the four-character string `"null"`' in prompt


def test_the_prompt_version_records_the_contract_change():
    """A prompt change bumps the version, and it must land before the P5a A/B
    or key quality and selector quality confound."""
    assert PASS1_PROMPT_VERSION == "1.3.0"
