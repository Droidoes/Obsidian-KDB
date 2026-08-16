"""Corpus integrity for the #119 bridge regression corpus."""
import json
from pathlib import Path

import pytest

from kdb_graph_compiler.summary_slug import expected_summary_slug

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


from kdb_graph_compiler.proposal_bridge import BridgeReject, BridgeSuccess, normalize_proposal


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_corpus_execution(case):
    r = normalize_proposal(case["proposal"], source_id=case["source_id"])
    exp = case["expect"]
    if exp["kind"] == "reject":
        assert isinstance(r, BridgeReject), case["id"]
        assert r.reject_class.value == exp["reject_class"], case["id"]
        assert r.retriable
        return
    assert isinstance(r, BridgeSuccess), case["id"]
    if "summary_slug" in exp:
        summaries = [p for p in r.canonical["pages"] if p["page_type"] == "summary"]
        assert summaries[0]["slug"] == exp["summary_slug"], case["id"]
    for rule in exp.get("decisions_include", []):
        assert any(d.rule == rule for d in r.decisions), (case["id"], rule)
    for token in exp.get("body_preserved", []):
        assert any(token in p["body"] for p in r.canonical["pages"]), (case["id"], token)
