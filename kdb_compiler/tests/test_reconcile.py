"""Tests for reconcile — post-validate repair of reconcilable defects."""
from __future__ import annotations

import pytest

from kdb_compiler import reconcile, validate_compile_result as vcr
from kdb_compiler.reconcile import ReconcileError
from kdb_compiler.validate_compile_result import ValidationFinding


SRC_ID = "KDB/raw/foo.md"


def _src(**overrides) -> dict:
    base = {
        "source_id": SRC_ID,
        "summary_slug": "foo",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [
            {"slug": "foo", "page_type": "summary", "title": "Foo", "body": "x"},
        ],
    }
    base.update(overrides)
    return base


def _cr(*sources: dict) -> dict:
    return {
        "run_id": "2026-04-21T00-00-00_EDT",
        "success": True,
        "compiled_sources": list(sources),
    }


# ---------- registry ----------

def test_registry_contains_pairing_rules() -> None:
    assert "pairing_commission" in reconcile.registered_types()
    assert "pairing_omission" in reconcile.registered_types()


# ---------- basic dispatch ----------

def test_empty_findings_is_noop() -> None:
    cr = _cr(_src())
    actions = reconcile.reconcile(cr, [])
    assert actions == []


def test_unknown_finding_type_raises() -> None:
    cr = _cr(_src())
    bogus = ValidationFinding(
        type="not_a_real_finding",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
    )
    with pytest.raises(ReconcileError, match="No reconcile rule"):
        reconcile.reconcile(cr, [bogus])


def test_unknown_source_id_raises() -> None:
    cr = _cr(_src())
    f = ValidationFinding(
        type="pairing_omission",
        severity="measure",
        detail="x",
        source_id="KDB/raw/does-not-exist.md",
        page_type="concept",
        slug="mencius",
    )
    with pytest.raises(ReconcileError, match="unknown source_id"):
        reconcile.reconcile(cr, [f])


# ---------- pairing_commission (remove slug) ----------

def test_fix_pairing_commission_concept() -> None:
    cr = _cr(_src(concept_slugs=["ghost", "keep-me"]))
    f = ValidationFinding(
        type="pairing_commission",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="concept",
        slug="ghost",
    )
    actions = reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["keep-me"]
    assert len(actions) == 1
    assert actions[0].finding_type == "pairing_commission"
    assert "removed 'ghost'" in actions[0].detail


def test_fix_pairing_commission_article() -> None:
    cr = _cr(_src(article_slugs=["ghost-article"]))
    f = ValidationFinding(
        type="pairing_commission",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="article",
        slug="ghost-article",
    )
    reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["article_slugs"] == []


# ---------- pairing_omission (add slug) ----------

def test_fix_pairing_omission_concept() -> None:
    cr = _cr(_src(
        pages=[
            {"slug": "foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "mencius", "page_type": "concept", "title": "Mencius", "body": "z"},
        ],
    ))
    f = ValidationFinding(
        type="pairing_omission",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="concept",
        slug="mencius",
    )
    actions = reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["mencius"]
    assert "added 'mencius'" in actions[0].detail


def test_fix_pairing_omission_article() -> None:
    cr = _cr(_src(
        pages=[
            {"slug": "foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "some-essay", "page_type": "article", "title": "E", "body": "z"},
        ],
    ))
    f = ValidationFinding(
        type="pairing_omission",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="article",
        slug="some-essay",
    )
    reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["article_slugs"] == ["some-essay"]


# ---------- mixed ----------

def test_fix_both_directions_in_one_pass() -> None:
    cr = _cr(_src(
        concept_slugs=["ghost"],
        pages=[
            {"slug": "foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "real-concept", "page_type": "concept", "title": "RC", "body": "z"},
        ],
    ))
    findings = [
        ValidationFinding(type="pairing_commission", severity="measure", detail="",
                          source_id=SRC_ID, page_type="concept", slug="ghost"),
        ValidationFinding(type="pairing_omission", severity="measure", detail="",
                          source_id=SRC_ID, page_type="concept", slug="real-concept"),
    ]
    actions = reconcile.reconcile(cr, findings)
    assert cr["compiled_sources"][0]["concept_slugs"] == ["real-concept"]
    assert len(actions) == 2


# ---------- idempotence ----------

def test_reconcile_is_idempotent_on_commission() -> None:
    """If the slug is already absent, rule is a no-op but still records an action."""
    cr = _cr(_src(concept_slugs=[]))
    f = ValidationFinding(
        type="pairing_commission",
        severity="measure",
        detail="",
        source_id=SRC_ID,
        page_type="concept",
        slug="ghost",
    )
    actions = reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == []
    assert "already absent" in actions[0].detail


def test_reconcile_is_idempotent_on_omission() -> None:
    cr = _cr(_src(concept_slugs=["already-here"]))
    f = ValidationFinding(
        type="pairing_omission",
        severity="measure",
        detail="",
        source_id=SRC_ID,
        page_type="concept",
        slug="already-here",
    )
    actions = reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["already-here"]
    assert "already present" in actions[0].detail


# ---------- round-trip with validator ----------

def test_validate_then_reconcile_then_validate_produces_no_pairing_findings() -> None:
    """The whole point: after reconcile, the compile_result looks like a clean LLM response."""
    src = _src(
        concept_slugs=["ghost"],           # commission
        article_slugs=[],
        pages=[
            {"slug": "foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "c1", "page_type": "concept", "title": "x", "body": "y"},    # omission
            {"slug": "a1", "page_type": "article", "title": "x", "body": "y"},    # omission
        ],
    )
    cr = _cr(src)

    before = vcr.validate(cr)
    assert before.is_valid  # pairing mismatches are measure, don't gate
    assert len(before.measure_findings) == 3   # 1 commission + 2 omissions

    reconcile.reconcile(cr, before.measure_findings)

    after = vcr.validate(cr)
    assert after.is_valid
    assert after.measure_findings == []


def test_reconcile_does_not_touch_other_sources() -> None:
    """Findings scoped to source A shouldn't mutate source B."""
    src_a = _src(source_id="KDB/raw/a.md", concept_slugs=["ghost"])
    src_b = _src(source_id="KDB/raw/b.md", concept_slugs=["untouched"])
    cr = _cr(src_a, src_b)
    f = ValidationFinding(
        type="pairing_commission",
        severity="measure",
        detail="",
        source_id="KDB/raw/a.md",
        page_type="concept",
        slug="ghost",
    )
    reconcile.reconcile(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == []
    assert cr["compiled_sources"][1]["concept_slugs"] == ["untouched"]
