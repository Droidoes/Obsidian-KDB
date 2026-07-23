"""#115 Phase 4 (D-115-10): wikilink parity corpus — compiler-side consumers.

ONE shared dataset (tests/fixtures/wikilink_parity/cases.json) pins the token
semantics (plain / |alias / #heading / escaped / fenced-code / inline-code /
duplicates / malformed) across the compiler extractor, the canonicalizer
rewrite, and the coercion rewrite. The mirrored graph extractor runs the same
corpus in kdb_graph/tests/test_wikilink_parity_graph.py — test-only shared
data does not violate the import boundary.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler.canonicalize import _remap_body_wikilinks
from compiler.repair import coerce_slugs_and_propagate
from compiler.validate_source_response import body_wikilink_slugs

CASES: list[dict] = json.loads(
    (Path(__file__).parents[2] / "tests" / "fixtures" / "wikilink_parity" / "cases.json")
    .read_text(encoding="utf-8")
)["cases"]
_IDS = [c["id"] for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_extractor_matches_corpus(case: dict) -> None:
    assert body_wikilink_slugs(case["body"]) == set(case["expected_slugs"])


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_canonicalizer_rewrite_matches_corpus(case: dict) -> None:
    new_body, _ = _remap_body_wikilinks(case["body"], case["resolve"])
    assert new_body == case["expected_body_canonicalize"]


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_coercion_rewrite_matches_corpus(case: dict) -> None:
    payload = {
        "pages": [
            {"slug": case.get("page_slug", "test-page"), "page_type": "concept",
             "title": "T", "body": case["body"]}
        ],
    }
    changed = coerce_slugs_and_propagate(payload)
    assert payload["pages"][0]["body"] == case["expected_body_coerce"]
    assert changed == case["expect_coerce_changed"]
    if "expected_page_slug" in case:
        assert payload["pages"][0]["slug"] == case["expected_page_slug"]
