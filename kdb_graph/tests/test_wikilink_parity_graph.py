"""#115 Phase 4 (D-115-10): wikilink parity corpus — graph-side consumer.

The mirrored extractor (kdb_graph.intake.body_wikilink_slugs) runs the SAME
shared dataset (tests/fixtures/wikilink_parity/cases.json) as the compiler
consumers (compiler/tests/test_wikilink_parity.py). kdb_graph imports no
sibling package — the corpus is test-only shared DATA, not a code import.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_graph.intake import body_wikilink_slugs

CASES: list[dict] = json.loads(
    (Path(__file__).parents[2] / "tests" / "fixtures" / "wikilink_parity" / "cases.json")
    .read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_graph_extractor_matches_corpus(case: dict) -> None:
    assert body_wikilink_slugs(case["body"]) == set(case["expected_slugs"])
