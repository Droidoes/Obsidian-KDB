"""Guard test: pass1_prompt.j2 template path resolves after the enrich/ move.

If config_loader can't find domains.json/source_types.json (vocab data path wrong)
or the Jinja loader can't find pass1_prompt.j2 (template path wrong), this test
fails with FileNotFoundError — catching both path-resolution hazards in one shot.
"""
from ingestion.enrich.pass1_prompt import build_pass1_prompt


def test_pass1_prompt_renders_nonempty_string():
    result = build_pass1_prompt(
        source_text="Test note content.",
        source_path="test/note.md",
    )
    assert isinstance(result, str)
    assert len(result) > 0
