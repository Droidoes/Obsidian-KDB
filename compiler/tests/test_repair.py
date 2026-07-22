"""Tests for repair — rung-2 slug coercion (post-#115, body-only propagation).

The #65 Repair stage (pairing fixers + finding-driven dispatch) is deleted
whole; what survives is `coerce_slugs_and_propagate` over page `slug`
fields and body [[wikilinks]].
"""
from __future__ import annotations

from compiler.repair import coerce_slugs_and_propagate


def _payload(slug: str, body: str, *, extra_pages: list[dict] | None = None) -> dict:
    pages = [{"slug": slug, "page_type": "summary", "title": "T", "body": body}]
    if extra_pages:
        pages.extend(extra_pages)
    return {"pages": pages}


def test_renames_page_slug_and_body_wikilinks() -> None:
    pj = _payload("Foo--Bar", "See [[Foo--Bar]] and [[ok-slug]].")
    assert coerce_slugs_and_propagate(pj) is True
    assert pj["pages"][0]["slug"] == "foo-bar"
    assert pj["pages"][0]["body"] == "See [[foo-bar]] and [[ok-slug]]."


def test_rewrite_preserves_display_and_anchor() -> None:
    pj = _payload("ok", "L [[Bad--Slug|Display Text]] and [[Bad--Slug#Section]].")
    assert coerce_slugs_and_propagate(pj) is True
    assert pj["pages"][0]["body"] == "L [[bad-slug|Display Text]] and [[bad-slug#Section]]."


def test_all_valid_returns_false_and_untouched() -> None:
    pj = _payload("foo", "See [[foo]] and [[bar-baz]].")
    assert coerce_slugs_and_propagate(pj) is False
    assert pj["pages"][0]["slug"] == "foo"
    assert pj["pages"][0]["body"] == "See [[foo]] and [[bar-baz]]."


def test_uncoercible_slug_refuses_without_mutation() -> None:
    pj = _payload("no spaces allowed", "Body.")
    assert coerce_slugs_and_propagate(pj) is False
    assert pj["pages"][0]["slug"] == "no spaces allowed"


def test_collapse_collision_refuses() -> None:
    pj = _payload("foo--bar", "B.", extra_pages=[
        {"slug": "Foo-Bar", "page_type": "concept", "title": "T", "body": "x"},
    ])
    # both collapse to "foo-bar"
    assert coerce_slugs_and_propagate(pj) is False


def test_collapse_into_existing_valid_slug_refuses() -> None:
    pj = _payload("Foo--Bar", "B.", extra_pages=[
        {"slug": "foo-bar", "page_type": "concept", "title": "T", "body": "x"},
    ])
    assert coerce_slugs_and_propagate(pj) is False


def test_removed_contract_fields_are_not_propagation_targets() -> None:
    """Legacy payloads may still carry the deleted fields; coerce must not
    'fix' them — post-#115 propagation is page slug + body wikilinks only."""
    pj = _payload("ok", "B.")
    pj["summary_slug"] = "Bad_Summary"          # legacy key, present but dead
    pj["pages"][0]["outgoing_links"] = ["Bad_Link"]  # legacy key, dead
    pj["concept_slugs"] = ["Bad_Concept"]        # legacy key, dead
    # only valid slugs elsewhere → no rename needed → False, and the legacy
    # keys are untouched either way
    assert coerce_slugs_and_propagate(pj) is False
    assert pj["summary_slug"] == "Bad_Summary"
    assert pj["pages"][0]["outgoing_links"] == ["Bad_Link"]
    assert pj["concept_slugs"] == ["Bad_Concept"]
