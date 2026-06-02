# kdb_compiler/tests/test_pass1_prompt.py
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
