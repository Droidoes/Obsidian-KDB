"""Tests for repair — post-validate repair of reconcilable defects."""
from __future__ import annotations

import pytest

from kdb_compiler import repair as reconcile, validate_compile_result as vcr
from kdb_compiler.repair import RepairError as ReconcileError
from kdb_compiler.validate_compile_result import ValidationFinding


SRC_ID = "KDB/raw/foo.md"


def _src(**overrides) -> dict:
    base = {
        "source_id": SRC_ID,
        "summary_slug": "summary-foo",
        "concept_slugs": [],
        "article_slugs": [],
        "pages": [
            {"slug": "summary-foo", "page_type": "summary", "title": "Foo", "body": "x"},
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
    assert "pairing_type_mismatch" in reconcile.registered_types()


# ---------- basic dispatch ----------

def test_empty_findings_is_noop() -> None:
    cr = _cr(_src())
    actions = reconcile.repair(cr, [])
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
        reconcile.repair(cr, [bogus])


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
        reconcile.repair(cr, [f])


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
    actions = reconcile.repair(cr, [f])
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
    reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["article_slugs"] == []


# ---------- pairing_omission (add slug) ----------

def test_fix_pairing_omission_concept() -> None:
    cr = _cr(_src(
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
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
    actions = reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["mencius"]
    assert "added 'mencius'" in actions[0].detail


def test_fix_pairing_omission_article() -> None:
    cr = _cr(_src(
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
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
    reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["article_slugs"] == ["some-essay"]


# ---------- mixed ----------

def test_fix_both_directions_in_one_pass() -> None:
    cr = _cr(_src(
        concept_slugs=["ghost"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "real-concept", "page_type": "concept", "title": "RC", "body": "z"},
        ],
    ))
    findings = [
        ValidationFinding(type="pairing_commission", severity="measure", detail="",
                          source_id=SRC_ID, page_type="concept", slug="ghost"),
        ValidationFinding(type="pairing_omission", severity="measure", detail="",
                          source_id=SRC_ID, page_type="concept", slug="real-concept"),
    ]
    actions = reconcile.repair(cr, findings)
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
    actions = reconcile.repair(cr, [f])
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
    actions = reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["already-here"]
    assert "already present" in actions[0].detail


# ---------- round-trip with validator ----------

def test_validate_then_reconcile_then_validate_produces_no_pairing_findings() -> None:
    """The whole point: after reconcile, the compile_result looks like a clean LLM response."""
    src = _src(
        concept_slugs=["ghost"],           # commission
        article_slugs=[],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "c1", "page_type": "concept", "title": "x", "body": "y"},    # omission
            {"slug": "a1", "page_type": "article", "title": "x", "body": "y"},    # omission
        ],
    )
    cr = _cr(src)

    before = vcr.validate(cr)
    assert before.is_valid  # pairing mismatches are measure, don't gate
    assert len(before.measure_findings) == 3   # 1 commission + 2 omissions

    reconcile.repair(cr, before.measure_findings)

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
    reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == []
    assert cr["compiled_sources"][1]["concept_slugs"] == ["untouched"]


# ---------- pairing_type_mismatch (Task #65 — remove slug from wrong list) ----------

def test_fix_pairing_type_mismatch_article_page() -> None:
    # An article-typed page whose slug was mis-filed into concept_slugs.
    cr = _cr(_src(
        concept_slugs=["ethnic-integration-in-china", "real-concept"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "ethnic-integration-in-china", "page_type": "article", "title": "E", "body": "z"},
        ],
    ))
    f = ValidationFinding(
        type="pairing_type_mismatch",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="article",
        slug="ethnic-integration-in-china",
    )
    actions = reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["real-concept"]
    assert len(actions) == 1
    assert actions[0].finding_type == "pairing_type_mismatch"
    assert "removed 'ethnic-integration-in-china'" in actions[0].detail


def test_fix_pairing_type_mismatch_concept_page() -> None:
    # A concept-typed page whose slug was mis-filed into article_slugs.
    cr = _cr(_src(
        article_slugs=["mencius"],
        pages=[
            {"slug": "summary-foo", "page_type": "summary", "title": "x", "body": "y"},
            {"slug": "mencius", "page_type": "concept", "title": "M", "body": "z"},
        ],
    ))
    f = ValidationFinding(
        type="pairing_type_mismatch",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="concept",
        slug="mencius",
    )
    reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["article_slugs"] == []


def test_fix_pairing_type_mismatch_idempotent() -> None:
    cr = _cr(_src(concept_slugs=["real-concept"]))
    f = ValidationFinding(
        type="pairing_type_mismatch",
        severity="measure",
        detail="x",
        source_id=SRC_ID,
        page_type="article",
        slug="already-gone",
    )
    actions = reconcile.repair(cr, [f])
    assert cr["compiled_sources"][0]["concept_slugs"] == ["real-concept"]
    assert "already absent" in actions[0].detail


# ---------- reconcile_body_links (Task #57) ----------

class TestReconcileBodyLinks:
    def test_drops_declared_only_slugs(self) -> None:
        parsed = {
            "pages": [
                {
                    "slug": "summary-foo",
                    "body": "Discusses [[bar]] only.",
                    "outgoing_links": ["bar", "baz", "qux"],
                },
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 1
        assert parsed["pages"][0]["outgoing_links"] == ["bar"]

    def test_adds_body_only_slugs(self) -> None:
        parsed = {
            "pages": [
                {
                    "slug": "p",
                    "body": "Mentions [[alpha]] and [[beta]].",
                    "outgoing_links": [],
                },
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 1
        assert parsed["pages"][0]["outgoing_links"] == ["alpha", "beta"]

    def test_aligned_page_unchanged(self) -> None:
        parsed = {
            "pages": [
                {
                    "slug": "p",
                    "body": "[[a]] and [[b]].",
                    "outgoing_links": ["a", "b"],
                },
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 0
        assert parsed["pages"][0]["outgoing_links"] == ["a", "b"]

    def test_empty_body_clears_outgoing_links(self) -> None:
        parsed = {
            "pages": [
                {
                    "slug": "p",
                    "body": "Plain prose with no wikilinks.",
                    "outgoing_links": ["abandoned-slug"],
                },
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 1
        assert parsed["pages"][0]["outgoing_links"] == []

    def test_alias_and_heading_forms_recognized(self) -> None:
        parsed = {
            "pages": [
                {
                    "slug": "p",
                    "body": "See [[alpha|the alpha]] and [[beta#intro]].",
                    "outgoing_links": [],
                },
            ],
        }
        reconcile.reconcile_body_links(parsed)
        assert parsed["pages"][0]["outgoing_links"] == ["alpha", "beta"]

    def test_code_spans_stripped_before_scan(self) -> None:
        parsed = {
            "pages": [
                {
                    "slug": "p",
                    "body": "Real link [[real]].\n\n```\nfake [[fake]] link\n```\n",
                    "outgoing_links": ["fake", "real"],
                },
            ],
        }
        reconcile.reconcile_body_links(parsed)
        assert parsed["pages"][0]["outgoing_links"] == ["real"]

    def test_idempotent_on_second_pass(self) -> None:
        parsed = {
            "pages": [
                {"slug": "p", "body": "[[a]] [[b]]", "outgoing_links": ["zzz"]},
            ],
        }
        n1 = reconcile.reconcile_body_links(parsed)
        snapshot = list(parsed["pages"][0]["outgoing_links"])
        n2 = reconcile.reconcile_body_links(parsed)
        assert n1 == 1
        assert n2 == 0
        assert parsed["pages"][0]["outgoing_links"] == snapshot

    def test_multi_page_independent(self) -> None:
        parsed = {
            "pages": [
                {"slug": "a", "body": "[[x]]", "outgoing_links": ["x"]},
                {"slug": "b", "body": "no links", "outgoing_links": ["y"]},
                {"slug": "c", "body": "[[z]]", "outgoing_links": []},
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 2
        assert parsed["pages"][0]["outgoing_links"] == ["x"]
        assert parsed["pages"][1]["outgoing_links"] == []
        assert parsed["pages"][2]["outgoing_links"] == ["z"]

    def test_tolerant_missing_pages(self) -> None:
        assert reconcile.reconcile_body_links({}) == 0

    def test_tolerant_non_list_pages(self) -> None:
        assert reconcile.reconcile_body_links({"pages": "oops"}) == 0

    def test_tolerant_non_dict_page_entry(self) -> None:
        parsed = {
            "pages": [
                "not a dict",
                {"slug": "p", "body": "[[a]]", "outgoing_links": []},
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 1
        assert parsed["pages"][1]["outgoing_links"] == ["a"]

    def test_tolerant_non_string_body(self) -> None:
        parsed = {
            "pages": [
                {"slug": "p", "body": None, "outgoing_links": ["a"]},
            ],
        }
        n = reconcile.reconcile_body_links(parsed)
        assert n == 1
        assert parsed["pages"][0]["outgoing_links"] == []

    def test_output_is_sorted(self) -> None:
        parsed = {
            "pages": [
                {"slug": "p", "body": "[[zeta]] [[alpha]] [[mu]]", "outgoing_links": []},
            ],
        }
        reconcile.reconcile_body_links(parsed)
        assert parsed["pages"][0]["outgoing_links"] == ["alpha", "mu", "zeta"]

    def test_duplicate_body_links_dedup(self) -> None:
        parsed = {
            "pages": [
                {"slug": "p", "body": "[[a]] [[a]] [[a|alias]] and [[b]]", "outgoing_links": []},
            ],
        }
        reconcile.reconcile_body_links(parsed)
        assert parsed["pages"][0]["outgoing_links"] == ["a", "b"]


# ---------- reconcile_slug_lists (Task #65) ----------

class TestReconcileSlugLists:
    def test_rebuilds_lists_from_page_types(self) -> None:
        parsed = {
            "concept_slugs": [],
            "article_slugs": [],
            "pages": [
                {"slug": "summary-foo", "page_type": "summary"},
                {"slug": "concept-a", "page_type": "concept"},
                {"slug": "concept-b", "page_type": "concept"},
                {"slug": "article-x", "page_type": "article"},
            ],
        }
        n = reconcile.reconcile_slug_lists(parsed)
        assert n == 2
        assert parsed["concept_slugs"] == ["concept-a", "concept-b"]
        assert parsed["article_slugs"] == ["article-x"]

    def test_moves_mis_filed_slug(self) -> None:
        # EP1 case: an article-typed page whose slug the model wrongly
        # filed into concept_slugs (Task #65 motivating defect).
        parsed = {
            "concept_slugs": ["ethnic-integration-in-china", "real-concept"],
            "article_slugs": [],
            "pages": [
                {"slug": "real-concept", "page_type": "concept"},
                {"slug": "ethnic-integration-in-china", "page_type": "article"},
            ],
        }
        reconcile.reconcile_slug_lists(parsed)
        assert parsed["concept_slugs"] == ["real-concept"]
        assert parsed["article_slugs"] == ["ethnic-integration-in-china"]

    def test_aligned_lists_unchanged(self) -> None:
        parsed = {
            "concept_slugs": ["c1"],
            "article_slugs": ["a1"],
            "pages": [
                {"slug": "c1", "page_type": "concept"},
                {"slug": "a1", "page_type": "article"},
            ],
        }
        n = reconcile.reconcile_slug_lists(parsed)
        assert n == 0
        assert parsed["concept_slugs"] == ["c1"]
        assert parsed["article_slugs"] == ["a1"]

    def test_summary_slug_in_neither_list(self) -> None:
        parsed = {
            "concept_slugs": ["summary-foo"],
            "article_slugs": [],
            "pages": [{"slug": "summary-foo", "page_type": "summary"}],
        }
        reconcile.reconcile_slug_lists(parsed)
        assert parsed["concept_slugs"] == []
        assert parsed["article_slugs"] == []

    def test_output_sorted_and_deduped(self) -> None:
        parsed = {
            "concept_slugs": [],
            "article_slugs": [],
            "pages": [
                {"slug": "zeta", "page_type": "concept"},
                {"slug": "alpha", "page_type": "concept"},
                {"slug": "zeta", "page_type": "concept"},
            ],
        }
        reconcile.reconcile_slug_lists(parsed)
        assert parsed["concept_slugs"] == ["alpha", "zeta"]

    def test_idempotent_on_second_pass(self) -> None:
        parsed = {
            "concept_slugs": ["wrong"],
            "article_slugs": [],
            "pages": [{"slug": "c", "page_type": "concept"}],
        }
        n1 = reconcile.reconcile_slug_lists(parsed)
        snapshot_c = list(parsed["concept_slugs"])
        snapshot_a = list(parsed["article_slugs"])
        n2 = reconcile.reconcile_slug_lists(parsed)
        assert n1 == 1
        assert n2 == 0
        assert parsed["concept_slugs"] == snapshot_c
        assert parsed["article_slugs"] == snapshot_a

    def test_tolerant_missing_pages(self) -> None:
        parsed: dict = {}
        assert reconcile.reconcile_slug_lists(parsed) == 0
        assert parsed == {}  # missing pages → no mutation

    def test_tolerant_non_list_pages(self) -> None:
        assert reconcile.reconcile_slug_lists({"pages": "oops"}) == 0

    def test_tolerant_non_dict_page_entry(self) -> None:
        parsed = {
            "concept_slugs": [],
            "article_slugs": [],
            "pages": ["not a dict", {"slug": "c", "page_type": "concept"}],
        }
        reconcile.reconcile_slug_lists(parsed)
        assert parsed["concept_slugs"] == ["c"]
