"""Tests for validate_compile_result — JSON-Schema + semantic gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from compiler import validate_compile_result as vcr

FIXTURES = Path(__file__).parents[2] / "tests" / "fixtures"
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


def test_legacy_slug_lists_are_ignored_no_findings() -> None:
    """#115 dual-mode: historical concept/article slug lists are read-tolerated
    but produce NO findings — the pairing defect class is deleted with the fields."""
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


def test_cli_underivable_stem_exits_one_not_traceback(tmp_path: Path) -> None:
    """Codex Gate-2 F5: kdb-validate on a NEW-mode payload with an
    underivable (non-ASCII-only) stem reports the gate finding and exits 1
    — no traceback."""
    payload = _payload(_new_src(
        source_id="KDB/raw/日本語.md",
        pages=[{"slug": "summary-x", "page_type": "summary", "title": "x", "body": "y"}],
    ))
    p = tmp_path / "cr.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli(str(p))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot derive expected summary slug" in result.stdout
    assert "Traceback" not in result.stderr


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
        "summary_slug_mismatch",
        "summary_slug_underivable",
        "reserved_slug",
    })


def test_all_retained_legacy_fields_annotated() -> None:
    """Codex Gate-2 round-2 F8 (D-115-14, blueprint T2.2): EVERY contract
    field removed by #115 but retained optional for historical payloads
    carries the machine-readable `"deprecated": true` + `"readOnly": true`
    annotations. Walks the COMPLETE legacy field list (top level, page,
    source) so a future removal can't miss the annotation."""
    schema = json.loads(
        (Path(vcr.__file__).parent / "schemas" / "compile_result.schema.json")
        .read_text(encoding="utf-8")
    )
    legacy = {
        "top-level": (schema["properties"], {"log_entries", "warnings"}),
        "page": (
            schema["$defs"]["pageIntent"]["properties"],
            {"status", "outgoing_links", "confidence"},
        ),
        "source": (
            schema["$defs"]["compiledSource"]["properties"],
            {"summary_slug", "concept_slugs", "article_slugs"},
        ),
    }
    for where, (props, fields) in legacy.items():
        for f in sorted(fields):
            assert f in props, f"{where}.{f} missing from schema"
            assert props[f].get("deprecated") is True, \
                f"{where}.{f} lacks deprecated: true"
            assert props[f].get("readOnly") is True, \
                f"{where}.{f} lacks readOnly: true"


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


# ---------- NEW mode (#115): derived summary identity ----------

def _new_src(**overrides) -> dict:
    """NEW-mode compiled source: no summary_slug (derived, never emitted)."""
    base = {
        "source_id": "KDB/raw/foo.md",
        "pages": [
            {"slug": "summary-foo", "page_type": "summary", "title": "Foo", "body": "x"}
        ],
    }
    base.update(overrides)
    return base


def test_new_mode_exactly_one_summary_required() -> None:
    src = _new_src(pages=[
        {"slug": "c1", "page_type": "concept", "title": "x", "body": "y"},
    ])
    result = vcr.validate(_payload(src))
    assert not result.is_valid
    assert any(f.type == "summary_slug_missing" for f in result.gate_errors)


def test_new_mode_derived_slug_mismatch_gated() -> None:
    src = _new_src(pages=[
        {"slug": "summary-other", "page_type": "summary", "title": "x", "body": "y"},
    ])
    result = vcr.validate(_payload(src))
    assert not result.is_valid
    mismatches = [f for f in result.gate_errors if f.type == "summary_slug_mismatch"]
    assert len(mismatches) == 1
    assert "summary-foo" in mismatches[0].detail  # expected value in the detail


def test_new_mode_clean_payload_valid() -> None:
    result = vcr.validate(_payload(_new_src()))
    assert result.is_valid, _details(result)
    assert result.measure_findings == []


def test_new_mode_underivable_stem_fails_closed() -> None:
    """Codex Gate-2 F5: a NEW-mode source whose stem normalizes to nothing
    (non-ASCII-only) must produce a hard-zero gate finding, NOT raise
    PathError out of validate()."""
    src = _new_src(
        source_id="KDB/raw/日本語.md",
        pages=[{"slug": "summary-x", "page_type": "summary", "title": "x", "body": "y"}],
    )
    result = vcr.validate(_payload(src))
    assert not result.is_valid
    underivable = [f for f in result.gate_errors if f.type == "summary_slug_underivable"]
    assert len(underivable) == 1
    assert "summary_slug_underivable" in vcr.HARD_ZERO_FINDING_TYPES


def test_mixed_legacy_and_new_sources_validate_per_source() -> None:
    """Codex Gate-2 F6: ONE aggregate payload carrying a LEGACY source
    (summary_slug present → referential checks) and a NEW source (derived
    exact match) validates per-source — mode selection is not global."""
    legacy = _src(source_id="KDB/raw/old.md", summary_slug="summary-old", pages=[
        {"slug": "summary-old", "page_type": "summary", "title": "Old", "body": "x"},
        {"slug": "c1", "page_type": "concept", "title": "C1", "body": "y"},
    ])
    new = _new_src(source_id="KDB/raw/new.md", pages=[
        {"slug": "summary-new", "page_type": "summary", "title": "New", "body": "x"},
        {"slug": "c2", "page_type": "concept", "title": "C2", "body": "y"},
    ])
    result = vcr.validate(_payload(legacy, new))
    assert result.is_valid, _details(result)

    # And a mixed payload where ONLY the new source is broken flags exactly
    # that source — the legacy source's mode is unaffected.
    new_bad = _new_src(source_id="KDB/raw/new.md", pages=[
        {"slug": "summary-wrong", "page_type": "summary", "title": "New", "body": "x"},
    ])
    result = vcr.validate(_payload(legacy, new_bad))
    assert not result.is_valid
    mismatches = [f for f in result.gate_errors if f.type == "summary_slug_mismatch"]
    assert len(mismatches) == 1
    assert mismatches[0].source_id == "KDB/raw/new.md"


def test_legacy_mode_referential_still_gated() -> None:
    """Historical payload (summary_slug present): the referential check
    still fires (dual-mode read-compat)."""
    src = _src(summary_slug="summary-ghost")  # not present in pages[]
    result = vcr.validate(_payload(src))
    assert not result.is_valid
    assert any(f.type == "summary_slug_missing" for f in result.gate_errors)
