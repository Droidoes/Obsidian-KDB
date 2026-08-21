"""extract: prompt build + pure parse/salvage (no LLM, no DB)."""
from __future__ import annotations

import json

import pytest

from kdb_fts import extract


def _payload(**over):
    base = {
        "ideas": [{
            "company": "Alibaba", "stance": "long", "thesis": "Cloud re-acceleration",
            "evidence": {"paragraph_id": "p0001", "head_anchor": "Cloud revenue", "tail_anchor": "grew"},
        }],
        "lessons": [],
        "downgraded": False,
    }
    base.update(over)
    return json.dumps(base)


def test_political_fixture_zero_mentions():
    r = extract.parse_extraction(json.dumps({"ideas": [], "lessons": [], "downgraded": True}))
    assert r.mentions == [] and r.cards == [] and r.downgraded is True


def test_thesis_fixture_one_mention_with_span():
    r = extract.parse_extraction(_payload())
    assert len(r.mentions) == 1
    m = r.mentions[0]
    assert m.company == "Alibaba" and m.stance == "long"
    assert m.evidence["head_anchor"] == "Cloud revenue"


def test_unknown_stance_drops_mention():
    r = extract.parse_extraction(_payload(ideas=[{
        "company": "X", "stance": "yolo", "thesis": "t",
        "evidence": {"paragraph_id": "p0001", "head_anchor": "a", "tail_anchor": "b"}}]))
    assert r.mentions == []


def test_invalid_json_raises():
    with pytest.raises(extract.ExtractParseError):
        extract.parse_extraction("not json {")


def test_build_prompt_numbers_paragraphs_and_no_truncation():
    paras = [(f"p{i:04d}", "word " * 100) for i in range(1, 10)]  # 900 words total
    p = extract.build_prompt(title="T", author="A", published_date="d", paragraphs=paras)
    assert "[p0001]" in p and "[p0009]" in p and "word" in p


def test_prompt_version_matches_filename():
    from pathlib import Path
    prompts = Path(__file__).parents[1] / "prompts"
    assert (prompts / f"{extract.EXTRACT_PROMPT_VERSION}.j2").exists()
