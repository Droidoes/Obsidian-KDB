from compiler.repair import coerce_slugs_and_propagate


def _payload(summary_slug, pages, concept_slugs=None, article_slugs=None, log_entries=None):
    return {
        "source_name": "x.md",
        "summary_slug": summary_slug,
        "concept_slugs": concept_slugs or [],
        "article_slugs": article_slugs or [],
        "pages": pages,
        "log_entries": log_entries or [],
        "warnings": [],
    }


def test_propagates_rename_across_all_fields():
    p = _payload(
        summary_slug="summary-Foo---Bar",
        concept_slugs=["Foo---Bar"],
        pages=[
            {"slug": "summary-Foo---Bar", "page_type": "summary",
             "body": "see [[Foo---Bar]] and [[Foo---Bar|the alias]] and [[Foo---Bar#sec]]",
             "outgoing_links": ["Foo---Bar"]},
            {"slug": "Foo---Bar", "page_type": "concept", "body": "x", "outgoing_links": []},
        ],
        log_entries=[{"level": "info", "message": "m", "related_slugs": ["Foo---Bar"]}],
    )
    changed = coerce_slugs_and_propagate(p)
    assert changed is True
    assert p["summary_slug"] == "summary-foo-bar"
    assert p["concept_slugs"] == ["foo-bar"]
    assert p["pages"][0]["slug"] == "summary-foo-bar"
    assert p["pages"][1]["slug"] == "foo-bar"
    assert p["pages"][0]["outgoing_links"] == ["foo-bar"]
    assert "[[foo-bar]]" in p["pages"][0]["body"]
    assert "[[foo-bar|the alias]]" in p["pages"][0]["body"]
    assert "[[foo-bar#sec]]" in p["pages"][0]["body"]
    assert p["log_entries"][0]["related_slugs"] == ["foo-bar"]


def test_noop_returns_false_when_all_valid():
    p = _payload("summary-foo", [{"slug": "summary-foo", "page_type": "summary",
                                   "body": "ok", "outgoing_links": []}])
    assert coerce_slugs_and_propagate(p) is False
    assert p["summary_slug"] == "summary-foo"


def test_refuses_collision_malformed_vs_valid():
    p = _payload(
        summary_slug="summary-x",
        pages=[
            {"slug": "summary-x", "page_type": "summary", "body": "b", "outgoing_links": []},
            {"slug": "foo-bar", "page_type": "concept", "body": "b", "outgoing_links": []},
            {"slug": "foo--bar", "page_type": "concept", "body": "b", "outgoing_links": []},
        ],
    )
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][2]["slug"] == "foo--bar"        # unchanged — refused


def test_refuses_uncoercible_value_unchanged():
    p = _payload("summary-x", [
        {"slug": "summary-x", "page_type": "summary", "body": "b", "outgoing_links": []},
        {"slug": "---", "page_type": "concept", "body": "b", "outgoing_links": []},
    ])
    assert coerce_slugs_and_propagate(p) is False
    assert p["pages"][1]["slug"] == "---"
