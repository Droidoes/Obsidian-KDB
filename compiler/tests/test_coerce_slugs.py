"""Rung-2 slug coercion — post-#115 contract (page slug + body wikilinks only).

The old 7-field propagation (summary_slug / concept/article lists /
outgoing_links / log_entries) died with those contract fields.
"""
from compiler.repair import coerce_slugs_and_propagate


def test_propagates_rename_across_page_slug_and_body():
    p = {
        "pages": [
            {"slug": "Foo---Bar", "page_type": "summary",
             "body": "see [[Foo---Bar]] and [[Foo---Bar|the alias]] and [[Foo---Bar#sec]]"},
            {"slug": "Foo---Bar", "page_type": "concept", "body": "x"},
        ],
    }
    changed = coerce_slugs_and_propagate(p)
    assert changed is True
    assert p["pages"][0]["slug"] == "foo-bar"
    assert p["pages"][1]["slug"] == "foo-bar"
    assert "[[foo-bar]]" in p["pages"][0]["body"]
    assert "[[foo-bar|the alias]]" in p["pages"][0]["body"]
    assert "[[foo-bar#sec]]" in p["pages"][0]["body"]


def test_noop_returns_false_when_all_valid():
    p = {"pages": [{"slug": "summary-foo", "page_type": "summary", "body": "ok"}]}
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][0]["slug"] == "summary-foo"


def test_refuses_collision_malformed_vs_valid():
    p = {
        "pages": [
            {"slug": "summary-x", "page_type": "summary", "body": "b"},
            {"slug": "foo-bar", "page_type": "concept", "body": "b"},
            {"slug": "foo--bar", "page_type": "concept", "body": "b"},
        ],
    }
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][2]["slug"] == "foo--bar"        # unchanged — refused


def test_refuses_uncoercible_value_unchanged():
    p = {
        "pages": [
            {"slug": "summary-x", "page_type": "summary", "body": "b"},
            {"slug": "---", "page_type": "concept", "body": "b"},
        ],
    }
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][1]["slug"] == "---"
