"""Proposal-schema matrix (#119): per-variant structural sufficiency."""
from compiler.validate_proposal_response import validate


def _page(page_type, title="T", body="B.", **kw):
    p = {"page_type": page_type, "title": title, "body": body}
    p.update(kw)
    return p


def test_summary_without_slug_valid():
    assert validate({"pages": [_page("summary")]}) == []


def test_summary_with_stray_string_slug_valid():
    assert validate({"pages": [_page("summary", slug="anything-goes")]}) == []


def test_summary_with_stray_nonstring_slug_valid():
    assert validate({"pages": [_page("summary", slug={"unexpected": "object"})]}) == []


def test_concept_without_slug_invalid():
    errs = validate({"pages": [_page("concept")]})
    assert errs and "slug" in errs[0]


def test_concept_string_slug_valid():
    assert validate({"pages": [_page("concept", slug="Foo--Bar")]}) == []


def test_concept_nonstring_slug_invalid():
    errs = validate({"pages": [_page("concept", slug=42)]})
    assert errs


def test_concept_slug_over_512_invalid():
    errs = validate({"pages": [_page("concept", slug="a" * 513)]})
    assert errs


def test_bad_page_type_invalid():
    errs = validate({"pages": [_page("Summary")]})
    assert errs


def test_missing_body_invalid():
    p = _page("summary")
    del p["body"]
    errs = validate({"pages": [p]})
    assert errs


def test_undeclared_field_invalid():
    errs = validate({"pages": [_page("summary", confidence="high")]})
    assert errs


def test_empty_pages_invalid():
    assert validate({"pages": []})


def test_root_not_object_invalid():
    assert validate([1, 2])


def test_compilation_notes_shape():
    assert validate({"pages": [_page("summary")], "compilation_notes": ["ok"]}) == []
    assert validate({"pages": [_page("summary")], "compilation_notes": "nope"})
