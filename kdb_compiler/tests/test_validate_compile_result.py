"""Tests for validate_compile_result — JSON-Schema + semantic gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kdb_compiler import validate_compile_result as vcr

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _details(result: vcr.ValidationResult) -> list[str]:
    """Flatten a ValidationResult to the legacy string list for assertions."""
    return result.detail_strings()


# ---------- fixture-based cases ----------

def test_valid_fixture_produces_no_errors() -> None:
    result = vcr.validate(_load("compile_result.minimal.valid.json"))
    assert result.is_valid, _details(result)
    assert result.gate_errors == []
    assert result.measure_findings == []


def test_invalid_fixture_surfaces_multiple_violations() -> None:
    result = vcr.validate(_load("compile_result.minimal.invalid.json"))
    errors = _details(result)
    assert len(errors) >= 5, f"expected >=5 errors, got {len(errors)}: {errors}"


# ---------- helpers for constructed payloads ----------

def _src(**overrides) -> dict:
    base = {
        "source_id": "KDB/raw/foo.md",
        "summary_slug": "foo",
        "pages": [
            {"slug": "foo", "page_type": "summary", "title": "Foo", "body": "x"}
        ],
    }
    base.update(overrides)
    return base


def _payload(*sources: dict) -> dict:
    return {
        "run_id": "2026-04-19T00-00-00Z",
        "success": True,
        "compiled_sources": list(sources),
    }


# ---------- semantic checks ----------

def test_duplicate_slug_in_pages() -> None:
    src = _src(pages=[
        {"slug": "foo", "page_type": "summary", "title": "A", "body": "x"},
        {"slug": "foo", "page_type": "concept", "title": "B", "body": "y"},
    ])
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("duplicate slug 'foo'" in e for e in errors), errors
    assert any(f.type == "duplicate_slug" for f in result.gate_errors), result.gate_errors


def test_summary_slug_not_in_pages() -> None:
    result = vcr.validate(_payload(_src(summary_slug="missing")))
    errors = _details(result)
    assert any("'missing' not found in pages[]" in e for e in errors), errors
    assert any(f.type == "summary_slug_missing" for f in result.gate_errors)


def test_summary_slug_wrong_page_type() -> None:
    src = _src(
        summary_slug="foo",
        pages=[{"slug": "foo", "page_type": "concept", "title": "x", "body": "y"}],
    )
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("summary_slug" in e and "expected 'summary'" in e for e in errors), errors
    assert any(f.type == "summary_slug_wrong_type" for f in result.gate_errors)


def test_concept_slug_missing_from_pages() -> None:
    result = vcr.validate(_payload(_src(concept_slugs=["ghost"])))
    errors = _details(result)
    assert any("concept_slugs[0]" in e and "'ghost' not found in pages[]" in e for e in errors), errors
    assert any(f.type == "pairing_commission" and f.slug == "ghost" for f in result.gate_errors)


def test_concept_slug_points_to_wrong_type() -> None:
    result = vcr.validate(_payload(_src(concept_slugs=["foo"])))
    errors = _details(result)
    assert any("concept_slugs[0]" in e and "expected 'concept'" in e for e in errors), errors
    assert any(f.type == "pairing_type_mismatch" for f in result.gate_errors)


def test_article_slug_missing_from_pages() -> None:
    result = vcr.validate(_payload(_src(article_slugs=["ghost-article"])))
    errors = _details(result)
    assert any("article_slugs[0]" in e and "'ghost-article' not found in pages[]" in e for e in errors), errors
    assert any(f.type == "pairing_commission" and f.slug == "ghost-article" for f in result.gate_errors)


@pytest.mark.parametrize("reserved", ["index", "log"])
def test_reserved_slug_in_pages(reserved: str) -> None:
    src = _src(
        summary_slug=reserved,
        pages=[{"slug": reserved, "page_type": "summary", "title": "x", "body": "y"}],
    )
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("pages[0].slug" in e and "Reserved" in e for e in errors), errors
    assert any(f.type == "reserved_slug" for f in result.gate_errors)


def test_reserved_slug_in_summary_slug() -> None:
    src = _src(
        summary_slug="index",
        pages=[{"slug": "index", "page_type": "summary", "title": "x", "body": "y"}],
    )
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("summary_slug" in e and "Reserved" in e for e in errors), errors


def test_reserved_slug_in_concept_slugs() -> None:
    src = _src(
        concept_slugs=["log"],
        pages=[
            {"slug": "foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "log", "page_type": "concept", "title": "x", "body": "y"},
        ],
    )
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("concept_slugs[0]" in e and "Reserved" in e for e in errors), errors


# ---------- non-dict / malformed payloads ----------

def test_non_dict_payload_caught_by_schema() -> None:
    result = vcr.validate("not a dict")
    assert result.gate_errors
    assert not result.is_valid


def test_missing_compiled_sources_caught_by_schema() -> None:
    result = vcr.validate({"run_id": "x", "success": True})
    assert any("compiled_sources" in f.detail for f in result.gate_errors)


# ---------- gate/measure split ----------

def test_all_current_findings_are_gate_severity() -> None:
    """Commit 1 preserves behavior — every finding is still severity='gate'."""
    result = vcr.validate(_load("compile_result.minimal.invalid.json"))
    assert not result.is_valid
    assert result.measure_findings == []
    for f in result.gate_errors:
        assert f.severity == "gate", f


def test_score_response_stub_returns_none() -> None:
    """Scoring stub is wired but returns None until M2 eval work implements it."""
    cr = _load("compile_result.minimal.valid.json")
    result = vcr.validate(cr)
    assert vcr.score_response(cr, result) is None


# ---------- CLI smoke ----------

def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "kdb_compiler.validate_compile_result", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_valid_exits_zero() -> None:
    result = _run_cli(str(FIXTURES / "compile_result.minimal.valid.json"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_cli_invalid_exits_one() -> None:
    result = _run_cli(str(FIXTURES / "compile_result.minimal.invalid.json"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.strip()


def test_cli_missing_file_exits_two(tmp_path: Path) -> None:
    result = _run_cli(str(tmp_path / "does-not-exist.json"))
    assert result.returncode == 2
