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
