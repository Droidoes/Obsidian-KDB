"""Tests for validate_compiled_source_response — schema + semantic gate."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest

from kdb_compiler import validate_compiled_source_response as V


SOURCE_ID = "KDB/raw/foo.md"


def _page(
    *,
    slug: str = "foo",
    page_type: str = "summary",
    title: str = "Foo",
    body: str = "A thing about foo.",
    status: str = "active",
    supports: list[str] | None = None,
    outgoing: list[str] | None = None,
    confidence: str = "medium",
) -> dict:
    return {
        "slug": slug,
        "page_type": page_type,
        "title": title,
        "body": body,
        "status": status,
        "supports_page_existence": supports if supports is not None else [SOURCE_ID],
        "outgoing_links": outgoing if outgoing is not None else [],
        "confidence": confidence,
    }


def _minimal() -> dict:
    return {
        "source_id": SOURCE_ID,
        "summary_slug": "foo",
        "pages": [_page()],
        "log_entries": [],
        "warnings": [],
    }


# ---------- schema: happy path ----------

def test_minimal_valid_passes_schema() -> None:
    assert V.validate(_minimal()) == []


def test_minimal_valid_passes_semantic() -> None:
    assert V.semantic_check(_minimal(), source_id=SOURCE_ID) == []


# ---------- schema: structural failures ----------

def test_missing_summary_slug_fails_schema() -> None:
    payload = _minimal()
    del payload["summary_slug"]
    errors = V.validate(payload)
    assert any("summary_slug" in e for e in errors), errors


def test_bad_slug_pattern_fails_schema() -> None:
    payload = _minimal()
    payload["pages"][0]["slug"] = "Foo_Bar"  # underscores and uppercase not allowed
    errors = V.validate(payload)
    assert any("Foo_Bar" in e or "pattern" in e.lower() for e in errors), errors


def test_supports_page_existence_empty_fails_schema() -> None:
    payload = _minimal()
    payload["pages"][0]["supports_page_existence"] = []
    errors = V.validate(payload)
    # minItems=1 violation surfaces at schema layer
    assert any(
        "supports_page_existence" in e or "minItems" in e.lower() or "short" in e.lower()
        for e in errors
    ), errors


def test_pages_empty_fails_schema() -> None:
    payload = _minimal()
    payload["pages"] = []
    errors = V.validate(payload)
    assert errors, "empty pages array must be rejected"


def test_missing_required_page_field_fails_schema() -> None:
    """Strict per-source contract: all 8 page fields required, no Python backfill."""
    payload = _minimal()
    del payload["pages"][0]["status"]
    errors = V.validate(payload)
    assert any("status" in e for e in errors), errors


def test_extra_top_level_field_fails_schema() -> None:
    payload = _minimal()
    payload["run_id"] = "r1"  # run_id is Python-owned, must NOT appear in model output
    errors = V.validate(payload)
    assert any(
        "additional" in e.lower() or "run_id" in e
        for e in errors
    ), errors


def test_bad_source_id_shape_fails_schema() -> None:
    payload = _minimal()
    payload["source_id"] = "some/other/path.md"  # must start with KDB/raw/
    errors = V.validate(payload)
    assert any("source_id" in e or "pattern" in e.lower() for e in errors), errors


# ---------- semantic: the four rules ----------

def test_source_id_mismatch_fails_semantic() -> None:
    payload = _minimal()
    payload["source_id"] = "KDB/raw/other.md"
    errors = V.semantic_check(payload, source_id=SOURCE_ID)
    assert any("echo" in e.lower() or "source_id" in e for e in errors)


def test_summary_slug_not_in_pages_fails_semantic() -> None:
    payload = _minimal()
    payload["summary_slug"] = "missing-slug"
    errors = V.semantic_check(payload, source_id=SOURCE_ID)
    assert any("summary_slug" in e for e in errors)


def test_two_summary_pages_fails_semantic() -> None:
    """Exactly one summary page whose slug == summary_slug."""
    payload = _minimal()
    payload["pages"].append(
        _page(slug="foo", title="Foo duplicate")  # second page with same slug + page_type=summary
    )
    errors = V.semantic_check(payload, source_id=SOURCE_ID)
    assert any("exactly one" in e.lower() for e in errors), errors


def test_summary_slug_wrong_page_type_fails_semantic() -> None:
    """summary_slug resolves to a page, but that page's page_type != 'summary'."""
    payload = _minimal()
    payload["pages"][0]["page_type"] = "concept"
    errors = V.semantic_check(payload, source_id=SOURCE_ID)
    assert any("exactly one" in e.lower() for e in errors)


def test_page_missing_source_id_in_supports_fails_semantic() -> None:
    payload = _minimal()
    payload["pages"].append(
        _page(
            slug="concept-a", page_type="concept", title="Concept A",
            supports=["KDB/raw/unrelated.md"],  # MUST include SOURCE_ID
        )
    )
    errors = V.semantic_check(payload, source_id=SOURCE_ID)
    assert any("supports_page_existence" in e for e in errors)


# ---------- CLI ----------

def test_cli_exit_0_on_valid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "resp.json"
    f.write_text(json.dumps(_minimal()), encoding="utf-8")
    rc = V.main([str(f), "--source-id", SOURCE_ID])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_exit_1_on_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = _minimal()
    del payload["summary_slug"]
    f = tmp_path / "resp.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    rc = V.main([str(f)])
    assert rc == 1
    assert "summary_slug" in capsys.readouterr().out


def test_cli_exit_2_on_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = V.main([str(tmp_path / "nope.json")])
    assert rc == 2


def test_cli_source_id_triggers_semantic_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _minimal()
    payload["source_id"] = "KDB/raw/other.md"  # schema-valid but wrong echo
    f = tmp_path / "resp.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    rc = V.main([str(f), "--source-id", SOURCE_ID])
    assert rc == 1
    out = capsys.readouterr().out
    assert "source_id" in out or "echo" in out.lower()


# ---------- body_link_check (Task #28 / M5 symmetric Jaccard inputs) ----------

def _payload(*pages: dict) -> dict:
    """Build a minimal payload around one-or-more handcrafted pages.
    Schema-validity is irrelevant for body_link_check; only `pages` is read."""
    return {
        "source_id": SOURCE_ID,
        "summary_slug": pages[0].get("slug", "x") if pages else "x",
        "pages": list(pages),
        "log_entries": [],
        "warnings": [],
    }


def test_body_link_check_happy_path() -> None:
    """declared {a,b}, body has [[a]] and [[c]] -> intersection={a},
    union={a,b,c}."""
    page = _page(slug="foo", outgoing=["a", "b"], body="see [[a]] and [[c]]")
    assert V.body_link_check(_payload(page)) == (1, 3)


def test_body_link_check_alias_token_captures_slug() -> None:
    page = _page(outgoing=["a"], body="link: [[a|nice label]]")
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_heading_anchor_captures_slug() -> None:
    page = _page(outgoing=["a"], body="link: [[a#section-1]]")
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_combined_anchor_and_alias_captures_slug() -> None:
    page = _page(outgoing=["a"], body="link: [[a#sec|x]]")
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_excludes_fenced_code_block() -> None:
    """Fenced ```...[[fake]]...``` must not contribute to body set."""
    body = "real: [[a]]\n\n```\nexample [[fake]] inside fence\n```\n"
    page = _page(outgoing=["a"], body=body)
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_excludes_inline_code() -> None:
    """Inline `[[fake]]` must not contribute."""
    body = "real [[a]]; sample `[[fake]]` shown."
    page = _page(outgoing=["a"], body=body)
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_excludes_escaped_brackets() -> None:
    r"""`\[[fake]]` (single-backslash escape) must not contribute."""
    body = "real [[a]]; literal \\[[fake]] in prose."
    page = _page(outgoing=["a"], body=body)
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_dedupes_repeats_in_body() -> None:
    """Set semantics: [[a]] [[a]] [[a]] still contributes one slug."""
    page = _page(outgoing=["a"], body="[[a]] [[a]] [[a]]")
    assert V.body_link_check(_payload(page)) == (1, 1)


def test_body_link_check_dedupes_repeats_in_declared() -> None:
    """outgoing_links=[a,a,b] dedups to {a,b}."""
    page = _page(outgoing=["a", "a", "b"], body="[[a]]")
    assert V.body_link_check(_payload(page)) == (1, 2)


def test_body_link_check_case_mismatch_does_not_match_slug() -> None:
    """`[[Foo]]` is not a valid slug pattern (lowercase only); does not
    join the body set. declared {foo} vs body {} -> (0, 1)."""
    page = _page(outgoing=["foo"], body="see [[Foo]]")
    assert V.body_link_check(_payload(page)) == (0, 1)


def test_body_link_check_empty_body_only_declared_contributes() -> None:
    page = _page(outgoing=["a", "b"], body="prose with no links here.")
    assert V.body_link_check(_payload(page)) == (0, 2)


def test_body_link_check_empty_declared_only_body_contributes() -> None:
    page = _page(outgoing=[], body="see [[a]]")
    assert V.body_link_check(_payload(page)) == (0, 1)


def test_body_link_check_aggregates_across_pages() -> None:
    """page1: D={a},B={a} (∩=1, ∪=1); page2: D={},B={c} (∩=0, ∪=1).
    Source totals: (1, 2)."""
    p1 = _page(slug="p1", outgoing=["a"], body="[[a]]")
    p2 = _page(slug="p2", outgoing=[], body="[[c]]")
    assert V.body_link_check(_payload(p1, p2)) == (1, 2)


def test_body_link_check_tolerates_malformed_payloads() -> None:
    """Never raises on missing/wrong-typed fields. All return (0, 0)."""
    assert V.body_link_check({}) == (0, 0)
    assert V.body_link_check({"pages": "not-a-list"}) == (0, 0)
    assert V.body_link_check({"pages": [None, "x", 42]}) == (0, 0)
    # Page with non-list outgoing_links + non-string body
    bad_page = {"slug": "x", "outgoing_links": "oops", "body": 12345}
    assert V.body_link_check({"pages": [bad_page]}) == (0, 0)
    # Page without body or outgoing_links keys at all
    assert V.body_link_check({"pages": [{"slug": "x"}]}) == (0, 0)
