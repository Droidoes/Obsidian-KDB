"""Tests for validate_source_response — schema + semantic gate (#115 new contract)."""
from __future__ import annotations

import pytest

from compiler import validate_source_response as V

SOURCE_ID = "KDB/raw/foo.md"
EXPECTED = "summary-foo"


def _page(
    *,
    slug: str = "summary-foo",
    page_type: str = "summary",
    title: str = "Foo",
    body: str = "A thing about foo.",
) -> dict:
    return {
        "slug": slug,
        "page_type": page_type,
        "title": title,
        "body": body,
    }


def _minimal() -> dict:
    return {"pages": [_page()]}


# ---------- schema: happy path ----------

def test_minimal_valid_passes_schema() -> None:
    assert V.validate(_minimal()) == []


def test_minimal_valid_passes_semantic() -> None:
    assert V.semantic_check(_minimal(), expected_summary_slug=EXPECTED) == []


def test_compilation_notes_optional_and_accepted() -> None:
    payload = _minimal()
    assert V.validate(payload) == []                       # absent → fine
    payload["compilation_notes"] = ["thin source, kept short"]
    assert V.validate(payload) == []                       # present → fine


# ---------- schema: structural failures ----------

def test_bad_slug_pattern_fails_schema() -> None:
    payload = _minimal()
    payload["pages"][0]["slug"] = "Foo_Bar"  # underscores and uppercase not allowed
    errors = V.validate(payload)
    assert any("Foo_Bar" in e or "pattern" in e.lower() for e in errors), errors


def test_pages_empty_fails_schema() -> None:
    payload = _minimal()
    payload["pages"] = []
    errors = V.validate(payload)
    assert errors, "empty pages array must be rejected"


def test_pages_missing_fails_schema() -> None:
    errors = V.validate({})
    assert any("pages" in e for e in errors), errors


# ---------- schema: removed fields rejected (the six + warnings/log_entries) ----------

@pytest.mark.parametrize("key", [
    "source_name", "summary_slug", "concept_slugs", "article_slugs",
    "log_entries", "warnings",
])
def test_removed_top_level_fields_rejected(key: str) -> None:
    payload = _minimal()
    payload[key] = [] if key != "source_name" and key != "summary_slug" else "x"
    errors = V.validate(payload)
    assert errors, f"removed field {key} must be rejected"


@pytest.mark.parametrize("key", ["status", "outgoing_links", "confidence"])
def test_removed_page_fields_rejected(key: str) -> None:
    payload = _minimal()
    payload["pages"][0][key] = "active" if key == "status" else (
        [] if key == "outgoing_links" else "high")
    errors = V.validate(payload)
    assert errors, f"removed page field {key} must be rejected"


# ---------- semantic gate: exact summary identity ----------

def test_summary_slug_mismatch_fails_semantic() -> None:
    payload = _minimal()
    payload["pages"][0]["slug"] = "summary-other"
    errors = V.semantic_check(payload, expected_summary_slug=EXPECTED)
    assert any(EXPECTED in e for e in errors), errors


def test_zero_summary_pages_fails_semantic() -> None:
    payload = {"pages": [_page(slug="foo", page_type="concept")]}
    errors = V.semantic_check(payload, expected_summary_slug=EXPECTED)
    assert any("exactly one" in e for e in errors), errors


def test_two_summary_pages_fails_semantic() -> None:
    payload = {"pages": [_page(), _page(slug="summary-foo-2")]}
    errors = V.semantic_check(payload, expected_summary_slug=EXPECTED)
    assert any("exactly one" in e for e in errors), errors


# ---------- body_wikilink_slugs (pure extractor — kept) ----------

def test_body_wikilink_slugs_basic() -> None:
    body = "See [[foo]] and [[bar-baz|Alias]] and [[qux#Heading]]."
    assert V.body_wikilink_slugs(body) == {"foo", "bar-baz", "qux"}


def test_body_wikilink_slugs_strips_code_spans() -> None:
    body = "Real [[foo]]. ```\nExample [[not-a-link]].\n``` Inline `[[nope]]`."
    assert V.body_wikilink_slugs(body) == {"foo"}
