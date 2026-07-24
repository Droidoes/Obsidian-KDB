"""Corpus integrity for the #119 bridge regression corpus."""
import json
from pathlib import Path

import pytest

from compiler.summary_slug import expected_summary_slug

CORPUS = Path(__file__).parent / "fixtures" / "proposal_bridge" / "cases.json"


def load_cases() -> list[dict]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_corpus_loads_and_ids_unique():
    cases = load_cases()
    assert len(cases) >= 14
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_expected_summary_slugs_match_derivation():
    for c in load_cases():
        exp = c["expect"].get("summary_slug")
        if exp is not None:
            assert exp == expected_summary_slug(c["source_id"]), c["id"]


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_case_shape(case):
    assert isinstance(case["proposal"]["pages"], list) and case["proposal"]["pages"]
    assert case["expect"]["kind"] in ("success", "reject")
    if case["expect"]["kind"] == "reject":
        assert "reject_class" in case["expect"]
