"""#115 Phase 4 (D-115-10): wikilink parity corpus — compiler-side consumers.

ONE shared dataset (tests/fixtures/wikilink_parity/cases.json) pins the token
semantics (plain / |alias / #heading / escaped / fenced-code / inline-code /
duplicates / malformed) across the compiler extractor, the canonicalizer
rewrite, and — post-#119 Phase 3 (repair.py retired) — the normalization
bridge's response-local body policy. The mirrored graph extractor runs the
same corpus in kdb_graph/tests/test_wikilink_parity_graph.py — test-only
shared data does not violate the import boundary.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.paths import collapse_slug
from compiler.canonicalize import _remap_body_wikilinks
from compiler.proposal_bridge import (
    NormalizationOp,
    OpKind,
    _apply_normalization_plan,
    _iter_mapped_tokens,
)
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
def test_bridge_body_projection_matches_corpus(case: dict) -> None:
    """#119 bridge projection (Codex PR4 F4): the response-local rename
    derives from the case's `response_pages` via collapse_slug; ops are built
    per mapped-token OCCURRENCE (`_iter_mapped_tokens`) and the body is
    produced via `_apply_normalization_plan` on a synthetic one-page
    proposal. Without `response_pages` nothing is mapped — the body is
    preserved verbatim (the new authority behavior, R6 F2)."""
    body = case["body"]
    rename: dict[str, str] = {}
    for raw in case.get("response_pages", []):
        coerced = collapse_slug(raw)
        if coerced is not None and coerced != raw:
            rename[raw] = coerced
    proposal = {
        "pages": [
            {"slug": "test-page", "page_type": "concept",
             "title": "T", "body": body}
        ],
    }
    ops = [
        NormalizationOp(OpKind.BODY_REFERENCE_REWRITE, "response-local",
                        0, "body", n, raw_tok, canon_tok)
        for n, (raw_tok, canon_tok) in enumerate(_iter_mapped_tokens(body, rename))
    ]
    canonical = _apply_normalization_plan(proposal, ops)
    assert canonical["pages"][0]["body"] == case["expected_body_bridge"]
