"""Tests for validate_compile_result — JSON-Schema + semantic gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from compiler import validate_compile_result as vcr

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
        "summary_slug": "summary-foo",
        "pages": [
            {"slug": "summary-foo", "page_type": "summary", "title": "Foo", "body": "x"}
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
        {"slug": "summary-foo", "page_type": "summary", "title": "A", "body": "x"},
        {"slug": "summary-foo", "page_type": "concept", "title": "B", "body": "y"},
    ])
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("duplicate slug 'summary-foo'" in e for e in errors), errors
    assert any(f.type == "duplicate_slug" for f in result.gate_errors), result.gate_errors


def test_summary_slug_not_in_pages() -> None:
    result = vcr.validate(_payload(_src(summary_slug="summary-missing")))
    errors = _details(result)
    assert any("'summary-missing' not found in pages[]" in e for e in errors), errors
    assert any(f.type == "summary_slug_missing" for f in result.gate_errors)


def test_summary_slug_wrong_page_type() -> None:
    src = _src(
        summary_slug="summary-foo",
        pages=[{"slug": "summary-foo", "page_type": "concept", "title": "x", "body": "y"}],
    )
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("summary_slug" in e and "expected 'summary'" in e for e in errors), errors
    assert any(f.type == "summary_slug_wrong_type" for f in result.gate_errors)


def test_concept_slug_missing_from_pages() -> None:
    result = vcr.validate(_payload(_src(concept_slugs=["ghost"])))
    errors = _details(result)
    assert any("concept_slugs[0]" in e and "'ghost' not found in pages[]" in e for e in errors), errors
    # pairing_commission is MEASURE — reconcilable, doesn't gate the run.
    assert any(f.type == "pairing_commission" and f.slug == "ghost" for f in result.measure_findings)
    assert not any(f.type == "pairing_commission" for f in result.gate_errors)


def test_concept_slug_points_to_wrong_type() -> None:
    # 'summary-foo' is the default summary page slug. Listing it in concept_slugs
    # points at a page whose page_type is 'summary' → pairing_type_mismatch.
    result = vcr.validate(_payload(_src(concept_slugs=["summary-foo"])))
    errors = _details(result)
    assert any("concept_slugs[0]" in e and "expected 'concept'" in e for e in errors), errors
    # pairing_type_mismatch is a measure finding (Task #65 / D45) — the page
    # object is authoritative; reconcile_slug_lists() heals it.
    assert any(f.type == "pairing_type_mismatch" for f in result.measure_findings)
    assert not any(f.type == "pairing_type_mismatch" for f in result.gate_errors)


def test_article_slug_missing_from_pages() -> None:
    result = vcr.validate(_payload(_src(article_slugs=["ghost-article"])))
    errors = _details(result)
    assert any("article_slugs[0]" in e and "'ghost-article' not found in pages[]" in e for e in errors), errors
    assert any(f.type == "pairing_commission" and f.slug == "ghost-article" for f in result.measure_findings)


# ---------- omission direction (page exists, slug missing) ----------

def test_concept_page_missing_from_concept_slugs() -> None:
    """A concept page in pages[] without a matching entry in concept_slugs is an omission."""
    src = _src(
        concept_slugs=[],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "mencius", "page_type": "concept", "title": "Mencius", "body": "z"},
        ],
    )
    result = vcr.validate(_payload(src))
    assert result.is_valid, "omission is measure-level — should not gate the run"
    omissions = [f for f in result.measure_findings if f.type == "pairing_omission"]
    assert len(omissions) == 1, result.measure_findings
    assert omissions[0].slug == "mencius"
    assert omissions[0].page_type == "concept"
    assert "concept_slugs" in omissions[0].detail


def test_article_page_missing_from_article_slugs() -> None:
    src = _src(
        article_slugs=[],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "some-essay", "page_type": "article", "title": "Essay", "body": "z"},
        ],
    )
    result = vcr.validate(_payload(src))
    assert result.is_valid
    omissions = [f for f in result.measure_findings if f.type == "pairing_omission"]
    assert len(omissions) == 1
    assert omissions[0].slug == "some-essay"
    assert omissions[0].page_type == "article"


def test_pairing_omission_and_commission_both_caught_in_one_pass() -> None:
    """Both directions — page without slug AND slug without page — surface together as measures."""
    src = _src(
        concept_slugs=["ghost"],  # ghost has no page (commission)
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "real-concept", "page_type": "concept", "title": "RC", "body": "z"},
            # real-concept is a concept page but not in concept_slugs (omission)
        ],
    )
    result = vcr.validate(_payload(src))
    assert result.is_valid, "pairing mismatches are measure, not gate"
    commissions = [f for f in result.measure_findings if f.type == "pairing_commission"]
    omissions = [f for f in result.measure_findings if f.type == "pairing_omission"]
    assert len(commissions) == 1 and commissions[0].slug == "ghost"
    assert len(omissions) == 1 and omissions[0].slug == "real-concept"


def test_multiple_concept_pages_all_missing_produce_per_page_findings() -> None:
    src = _src(
        concept_slugs=[],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "c1", "page_type": "concept", "title": "x", "body": "y"},
            {"slug": "c2", "page_type": "concept", "title": "x", "body": "y"},
            {"slug": "c3", "page_type": "concept", "title": "x", "body": "y"},
        ],
    )
    result = vcr.validate(_payload(src))
    assert result.is_valid
    omissions = [f for f in result.measure_findings if f.type == "pairing_omission"]
    assert len(omissions) == 3
    assert {f.slug for f in omissions} == {"c1", "c2", "c3"}


def test_pairing_fully_correct_no_findings() -> None:
    src = _src(
        concept_slugs=["c1"],
        article_slugs=["a1"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "c1", "page_type": "concept", "title": "x", "body": "y"},
            {"slug": "a1", "page_type": "article", "title": "x", "body": "y"},
        ],
    )
    result = vcr.validate(_payload(src))
    assert result.is_valid, _details(result)


@pytest.mark.parametrize("reserved", ["index", "log"])
def test_reserved_slug_in_pages(reserved: str) -> None:
    """Reserved-slug check fires when a concept page uses a reserved slug.
    (Summary slugs can't trigger this anymore — the schema's `summarySlug`
    pattern requires the `summary-` prefix, which forecloses 'index'/'log'.)"""
    src = _src(
        concept_slugs=[reserved],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": reserved, "page_type": "concept", "title": "x", "body": "y"},
        ],
    )
    result = vcr.validate(_payload(src))
    errors = _details(result)
    assert any("pages[1].slug" in e and "Reserved" in e for e in errors), errors
    assert any(f.type == "reserved_slug" for f in result.gate_errors)


# `test_reserved_slug_in_summary_slug` removed: with the `summary-` prefix
# requirement on summary_slug (Task #37), a bare reserved slug like 'index'
# can never appear there — schema rejects before the reserved check runs.
# Reserved-slug coverage for summary contexts is structurally redundant.


def test_reserved_slug_in_concept_slugs() -> None:
    src = _src(
        concept_slugs=["log"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
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

def test_gate_severity_contract() -> None:
    """Every gate_error has severity='gate'; every measure_finding has severity='measure'."""
    result = vcr.validate(_load("compile_result.minimal.invalid.json"))
    for f in result.gate_errors:
        assert f.severity == "gate", f
    for f in result.measure_findings:
        assert f.severity == "measure", f


def test_pairing_mismatches_do_not_gate_the_run() -> None:
    """pairing_commission + pairing_omission are measure findings — is_valid stays True."""
    src = _src(
        concept_slugs=["ghost"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "real-concept", "page_type": "concept", "title": "x", "body": "y"},
        ],
    )
    result = vcr.validate(_payload(src))
    assert result.is_valid
    assert result.gate_errors == []
    assert len(result.measure_findings) == 2
    types = {f.type for f in result.measure_findings}
    assert types == {"pairing_commission", "pairing_omission"}


def test_pairing_type_mismatch_is_measure_not_gate() -> None:
    """pairing_type_mismatch is reconcilable (Task #65 / D45) — measure
    severity, does not block the run. The page object is authoritative;
    reconcile_slug_lists() rebuilds the slug lists from pages[]."""
    # 'summary-foo' is the default summary page slug; listing it in concept_slugs
    # points at the summary page → page_type mismatch.
    result = vcr.validate(_payload(_src(concept_slugs=["summary-foo"])))
    assert result.is_valid
    assert any(f.type == "pairing_type_mismatch" and f.severity == "measure"
               for f in result.measure_findings)
    assert not any(f.type == "pairing_type_mismatch" for f in result.gate_errors)


# ---------- CLI smoke ----------

def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "compiler.validate_compile_result", *args],
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


# ---------- HARD_ZERO_FINDING_TYPES + check_compiled_source (Round 4 CW1) ----------

def test_hard_zero_finding_types_set() -> None:
    """The hard-zero finding types are exactly the gate-severity types
    emitted by `_check_source` (excluding `schema_violation`, which is
    emitted by the top-level `validate()` against the aggregate schema).
    Stable contract for the benchmark scorer's hard-zero derivation.
    `pairing_type_mismatch` left this set in Task #65 / D45 — it is now
    reconcilable (measure severity), so it no longer hard-zeros a model."""
    assert vcr.HARD_ZERO_FINDING_TYPES == frozenset({
        "duplicate_slug",
        "summary_slug_missing",
        "summary_slug_wrong_type",
        "reserved_slug",
    })


def test_check_compiled_source_excludes_pairing_type_mismatch() -> None:
    """pairing_type_mismatch is measure-severity (Task #65 / D45) — the
    hard-zero wrapper must not surface it."""
    src = _src(concept_slugs=["summary-foo"])  # summary page slug mis-filed as concept
    findings = vcr.check_compiled_source(src)
    assert "pairing_type_mismatch" not in findings
    assert findings == [], findings


def test_check_compiled_source_clean_returns_empty_list() -> None:
    """A well-formed parsed source dict has no hard-zero findings."""
    src = _src()  # default: one summary page named 'foo' with summary_slug='foo'
    assert vcr.check_compiled_source(src) == []


def test_check_compiled_source_surfaces_duplicate_slug() -> None:
    """duplicate_slug is one of the 5 hard-zero types."""
    src = _src(pages=[
        {"slug": "foo", "page_type": "summary", "title": "Foo", "body": "x"},
        {"slug": "foo", "page_type": "concept", "title": "Foo2", "body": "y"},
    ])
    findings = vcr.check_compiled_source(src)
    assert "duplicate_slug" in findings


def test_check_compiled_source_filters_out_measure_findings() -> None:
    """`pairing_commission` and `pairing_omission` are measure-severity
    (reconcilable, not hard-zero) — the wrapper must NOT include them.
    A source with a missing concept slug should produce only the
    measure-finding internally; the wrapper returns []."""
    src = _src(concept_slugs=["missing_slug"])  # slug declared but no matching page
    findings = vcr.check_compiled_source(src)
    assert "pairing_commission" not in findings
    assert findings == [], findings  # nothing hard-zero here
