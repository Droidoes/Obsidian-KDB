"""Tests for validate_source_response — schema + semantic gate."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest

from compiler import validate_source_response as V


SOURCE_NAME = "foo.md"


def _page(
    *,
    slug: str = "summary-foo",
    page_type: str = "summary",
    title: str = "Foo",
    body: str = "A thing about foo.",
    status: str = "active",
    outgoing: list[str] | None = None,
    confidence: str = "medium",
) -> dict:
    return {
        "slug": slug,
        "page_type": page_type,
        "title": title,
        "body": body,
        "status": status,
        "outgoing_links": outgoing if outgoing is not None else [],
        "confidence": confidence,
    }


def _minimal() -> dict:
    return {
        "source_name": SOURCE_NAME,
        "summary_slug": "summary-foo",
        "pages": [_page()],
        "log_entries": [],
        "warnings": [],
    }


# ---------- schema: happy path ----------

def test_minimal_valid_passes_schema() -> None:
    assert V.validate(_minimal()) == []


def test_minimal_valid_passes_semantic() -> None:
    assert V.semantic_check(_minimal(), source_name=SOURCE_NAME) == []


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


def test_pages_empty_fails_schema() -> None:
    payload = _minimal()
    payload["pages"] = []
    errors = V.validate(payload)
    assert errors, "empty pages array must be rejected"


def test_missing_required_page_field_fails_schema() -> None:
    """Strict per-source contract: all 7 LLM-emitted page fields required."""
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


# ---------- schema: source_name (Task #41) ----------

def test_top_level_source_id_field_rejected_as_unexpected() -> None:
    """Task #41 dropped source_id from the LLM contract — runner injects it.
    A model that emits a top-level `source_id` violates the schema."""
    payload = _minimal()
    payload["source_id"] = "KDB/raw/foo.md"
    errors = V.validate(payload)
    assert any(
        "additional" in e.lower() or "source_id" in e
        for e in errors
    ), errors


def test_per_page_supports_page_existence_rejected_as_unexpected() -> None:
    """Task #41 dropped supports_page_existence from the LLM contract."""
    payload = _minimal()
    payload["pages"][0]["supports_page_existence"] = ["KDB/raw/foo.md"]
    errors = V.validate(payload)
    assert any(
        "additional" in e.lower() or "supports_page_existence" in e
        for e in errors
    ), errors


def test_per_log_entry_related_source_ids_rejected_as_unexpected() -> None:
    """Task #41 dropped related_source_ids from the LLM contract."""
    payload = _minimal()
    payload["log_entries"] = [{
        "level": "info",
        "message": "a note",
        "related_slugs": [],
        "related_source_ids": ["KDB/raw/foo.md"],
    }]
    errors = V.validate(payload)
    assert any(
        "additional" in e.lower() or "related_source_ids" in e
        for e in errors
    ), errors


def test_source_name_with_path_separator_fails_schema() -> None:
    """source_name is path-free — slashes belong to source_id, which is
    runner-injected, not LLM-emitted."""
    payload = _minimal()
    payload["source_name"] = "KDB/raw/foo.md"
    errors = V.validate(payload)
    assert any("source_name" in e or "pattern" in e.lower() for e in errors), errors


def test_source_name_must_end_with_md() -> None:
    payload = _minimal()
    payload["source_name"] = "foo.txt"
    errors = V.validate(payload)
    assert any("source_name" in e or "pattern" in e.lower() for e in errors), errors


def test_source_name_with_spaces_accepted() -> None:
    """Real vault filenames can have spaces (e.g. `EP1 - The Journey of China.md`).
    The pattern must accept any path-separator-free string ending in .md."""
    payload = _minimal()
    payload["source_name"] = "EP1 - The Journey of China.md"
    assert V.validate(payload) == []


# ---------- semantic rules ----------

def test_source_name_mismatch_fails_semantic() -> None:
    payload = _minimal()
    payload["source_name"] = "other.md"
    errors = V.semantic_check(payload, source_name=SOURCE_NAME)
    assert any("echo" in e.lower() or "source_name" in e for e in errors)


def test_summary_slug_not_in_pages_fails_semantic() -> None:
    payload = _minimal()
    payload["summary_slug"] = "summary-missing"
    errors = V.semantic_check(payload, source_name=SOURCE_NAME)
    assert any("summary_slug" in e for e in errors)


def test_two_summary_pages_fails_semantic() -> None:
    """Exactly one summary page whose slug == summary_slug."""
    payload = _minimal()
    payload["pages"].append(
        _page(slug="summary-foo", title="Foo duplicate")  # second page with same slug + page_type=summary
    )
    errors = V.semantic_check(payload, source_name=SOURCE_NAME)
    assert any("exactly one" in e.lower() for e in errors), errors


def test_summary_slug_wrong_page_type_fails_semantic() -> None:
    """summary_slug resolves to a page, but that page's page_type != 'summary'."""
    payload = _minimal()
    payload["pages"][0]["page_type"] = "concept"
    errors = V.semantic_check(payload, source_name=SOURCE_NAME)
    assert any("exactly one" in e.lower() for e in errors)


# ---------- CLI ----------

def test_cli_exit_0_on_valid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "resp.json"
    f.write_text(json.dumps(_minimal()), encoding="utf-8")
    rc = V.main([str(f), "--source-name", SOURCE_NAME])
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


def test_cli_source_name_triggers_semantic_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _minimal()
    payload["source_name"] = "other.md"  # schema-valid but wrong echo
    f = tmp_path / "resp.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    rc = V.main([str(f), "--source-name", SOURCE_NAME])
    assert rc == 1
    out = capsys.readouterr().out
    assert "source_name" in out or "echo" in out.lower()
