"""Tests for kdb_benchmark.scorer — Phase 3 spec §5–§9 implementation.

Tests are organized by section of docs/task19-kpi-design.md:
  - dataclass shapes (§5)
  - per-measure functions (§6) — S0/S1/S2/S3, M1–M7, 3 diagnostics
  - average-rank Borda (§7)
  - final-score formula (§8)
  - score_run / score_runs / borda_normalize (§9)

Edge-case policies (§4) covered inline at each measure.
"""
from __future__ import annotations

from typing import Optional

import pytest

from kdb_benchmark import scorer
from kdb_benchmark.scorer import MeasureScore


# ---------------------------------------------------------------------------
# Fixture helper — builds a minimal RespStatsRecord-shaped dict.
#
# Spec § 9 loader contract: scorer reads dict-shaped JSON; required fields
# enumerated there. This helper mirrors that contract so tests stay close
# to the on-disk shape the scorer will actually consume.
# ---------------------------------------------------------------------------

def _parsed_summary_for(slugs: list[str], outgoing_link_count: int = 0) -> dict:
    return {
        "summary_slug": slugs[0] if slugs else None,
        "page_count": len(slugs),
        "page_types": {"summary": 1} if slugs else {},
        "slugs": list(slugs),
        "outgoing_link_count": outgoing_link_count,
        "log_entry_count": 0,
        "warning_count": 0,
        "source_id_echoed": None,
    }


def _parsed_json_for(
    *,
    source_id: str,
    pages: list[dict] | None = None,
    summary_slug: str = "x",
    concept_slugs: list[str] | None = None,
    article_slugs: list[str] | None = None,
) -> dict:
    if pages is None:
        pages = [{
            "slug": summary_slug, "page_type": "summary", "title": "X",
            "body": "", "outgoing_links": [],
            "supports_page_existence": [source_id], "status": "active",
            "confidence": "medium",
        }]
    return {
        "source_id": source_id,
        "summary_slug": summary_slug,
        "pages": pages,
        "concept_slugs": list(concept_slugs or []),
        "article_slugs": list(article_slugs or []),
        "log_entries": [],
        "warnings": [],
    }


def fake_record(
    *,
    source_id: str = "src1",
    run_id: str = "test-run",
    provider: str = "anthropic",
    model: str = "claude-haiku-4-5-20251001",
    parse_ok: bool = True,
    schema_ok: bool = True,
    semantic_ok: bool = True,
    parsed_json: dict | None = None,
    source_words: int = 1000,
    input_tokens: int = 500,
    output_tokens: int = 300,
    latency_ms: int = 1000,
    attempts: int = 1,
    body_link_intersection: int = 0,
    body_link_union: int = 0,
    token_overrun: bool = False,
    stop_reason: str | None = "end_turn",
    summary_slug: str = "x",
    pages: list[dict] | None = None,
    concept_slugs: list[str] | None = None,
    article_slugs: list[str] | None = None,
) -> dict:
    """Build a minimal RespStatsRecord-shaped dict for tests."""
    if parse_ok:
        if parsed_json is None:
            parsed_json = _parsed_json_for(
                source_id=source_id,
                pages=pages,
                summary_slug=summary_slug,
                concept_slugs=concept_slugs,
                article_slugs=article_slugs,
            )
        slugs = [p.get("slug", "") for p in parsed_json.get("pages", [])]
        outgoing = sum(len(p.get("outgoing_links", [])) for p in parsed_json.get("pages", []))
        parsed_summary = _parsed_summary_for(slugs, outgoing)
    else:
        parsed_summary = None
    return {
        "run_id": run_id,
        "source_id": source_id,
        "provider": provider,
        "model": model,
        "attempts": attempts,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "prompt_hash": "sha256:" + "0" * 64,
        "response_hash": "sha256:" + "1" * 64,
        "extract_ok": parse_ok,
        "parse_ok": parse_ok,
        "schema_ok": schema_ok,
        "semantic_ok": semantic_ok,
        "schema_errors": [],
        "semantic_errors": [],
        "parsed_summary": parsed_summary,
        "parsed_json": parsed_json,
        "system_prompt": None,
        "user_prompt": None,
        "raw_response_text": None,
        "stop_reason": stop_reason,
        "token_overrun": token_overrun,
        "source_words": source_words,
        "body_link_intersection": body_link_intersection,
        "body_link_union": body_link_union,
    }


# ===========================================================================
# §5 — Dataclass shapes
# ===========================================================================

class TestMeasureScore:
    def test_measure_score_holds_raw_aggregates_and_derived_rate(self):
        ms = MeasureScore(name="S0", numerator=3, denominator=5, rate=0.6, weight=0.20)
        assert ms.name == "S0"
        assert ms.numerator == 3
        assert ms.denominator == 5
        assert ms.rate == 0.6
        assert ms.weight == 0.20

    def test_measure_score_rate_is_none_when_denom_zero(self):
        ms = MeasureScore(name="M1", numerator=0, denominator=0, rate=None, weight=0.20)
        assert ms.rate is None


# ===========================================================================
# §6 — S0 pipeline_success_rate
# ===========================================================================

class TestS0:
    def test_s0_all_passing_records_yields_rate_1(self):
        records = [fake_record(source_id=f"src{i}") for i in range(3)]
        score = scorer.s0(records)
        assert score.name == "S0"
        assert score.numerator == 3
        assert score.denominator == 3
        assert score.rate == 1.0
        assert score.weight == 0.20

    def test_s0_parse_failures_excluded_from_numerator(self):
        records = [
            fake_record(source_id="ok1"),
            fake_record(source_id="ok2"),
            fake_record(source_id="fail", parse_ok=False, schema_ok=False, semantic_ok=False),
        ]
        score = scorer.s0(records)
        assert score.numerator == 2
        assert score.denominator == 3
        assert score.rate == pytest.approx(2/3)

    def test_s0_schema_failure_excluded(self):
        records = [
            fake_record(source_id="ok"),
            fake_record(source_id="schema_fail", schema_ok=False),
        ]
        score = scorer.s0(records)
        assert score.numerator == 1
        assert score.denominator == 2

    def test_s0_hard_zero_finding_excluded(self):
        """A source with duplicate_slug (a hard-zero finding type) does NOT
        count toward S0 even though parse_ok and schema_ok are True."""
        # Synthesize duplicate_slug situation via parsed_json with duplicate slugs
        bad_pages = [
            {"slug": "dup", "page_type": "summary", "title": "A", "body": "",
             "outgoing_links": [], "supports_page_existence": ["x"], "status": "active",
             "confidence": "medium"},
            {"slug": "dup", "page_type": "concept", "title": "B", "body": "",
             "outgoing_links": [], "supports_page_existence": ["x"], "status": "active",
             "confidence": "medium"},
        ]
        records = [
            fake_record(source_id="ok"),
            fake_record(
                source_id="dup_slug",
                summary_slug="dup",
                pages=bad_pages,
            ),
        ]
        score = scorer.s0(records)
        assert score.numerator == 1, "duplicate_slug record should NOT pass S0"
        assert score.denominator == 2

    def test_s0_non_dict_parsed_json_excluded(self):
        """Round 4 MF4: parse_ok=True but parsed_json is a list/scalar →
        treat as if parse_ok=False for S0; do not crash."""
        rec = fake_record(source_id="bad_shape")
        rec["parsed_json"] = ["foo", "bar"]   # parse succeeded into a list
        records = [rec, fake_record(source_id="good")]
        score = scorer.s0(records)
        assert score.numerator == 1
        assert score.denominator == 2

    def test_s0_semantic_failure_does_NOT_block_s0(self):
        """Locked Round 3 / Round 4 honesty note: S0 = parse ∧ schema ∧
        no-hard-zero. Semantic failures are captured at M4, not S0."""
        records = [
            fake_record(source_id="ok"),
            fake_record(source_id="sem_fail", semantic_ok=False),
        ]
        score = scorer.s0(records)
        assert score.numerator == 2, "semantic failure must NOT exclude from S0"
        assert score.denominator == 2

    def test_s0_empty_records_returns_none_rate(self):
        score = scorer.s0([])
        assert score.numerator == 0
        assert score.denominator == 0
        assert score.rate is None


# ===========================================================================
# §6 — S1 / S2 / S3 (diagnostics, weight 0)
# ===========================================================================

class TestS1:
    def test_s1_parse_pass_over_total(self):
        records = [
            fake_record(source_id="ok"),
            fake_record(source_id="ok2"),
            fake_record(source_id="fail", parse_ok=False),
        ]
        score = scorer.s1(records)
        assert score.name == "S1"
        assert score.numerator == 2
        assert score.denominator == 3
        assert score.rate == pytest.approx(2/3)
        assert score.weight == 0.0

    def test_s1_non_dict_parsed_json_does_not_count(self):
        rec = fake_record(source_id="bad_shape")
        rec["parsed_json"] = "not a dict"
        records = [rec, fake_record(source_id="good")]
        score = scorer.s1(records)
        assert score.numerator == 1


class TestS2:
    def test_s2_schema_pass_over_parse_pass(self):
        records = [
            fake_record(source_id="ok"),
            fake_record(source_id="schema_fail", schema_ok=False),
            fake_record(source_id="parse_fail", parse_ok=False, schema_ok=False),
        ]
        score = scorer.s2(records)
        assert score.name == "S2"
        # R_p = 2 (ok + schema_fail since both have parse_ok=True)
        # numerator = 1 (just ok)
        assert score.numerator == 1
        assert score.denominator == 2
        assert score.rate == 0.5
        assert score.weight == 0.0

    def test_s2_zero_parse_pass_returns_none(self):
        records = [fake_record(source_id="fail", parse_ok=False)]
        score = scorer.s2(records)
        assert score.rate is None


class TestS3:
    def test_s3_no_hard_zero_over_parse_pass(self):
        bad_pages = [
            {"slug": "dup", "page_type": "summary", "title": "A", "body": "",
             "outgoing_links": [], "supports_page_existence": ["x"], "status": "active",
             "confidence": "medium"},
            {"slug": "dup", "page_type": "concept", "title": "B", "body": "",
             "outgoing_links": [], "supports_page_existence": ["x"], "status": "active",
             "confidence": "medium"},
        ]
        records = [
            fake_record(source_id="ok"),
            fake_record(source_id="dup", summary_slug="dup", pages=bad_pages),
            fake_record(source_id="parse_fail", parse_ok=False),
        ]
        score = scorer.s3(records)
        assert score.numerator == 1
        assert score.denominator == 2
        assert score.rate == 0.5
        assert score.weight == 0.0


# ===========================================================================
# §6 — M1 link_target_resolution (weight 20%, Quality Core)
# ===========================================================================

def _page(slug: str, *, page_type: str = "concept", outgoing_links: list[str] | None = None) -> dict:
    return {
        "slug": slug, "page_type": page_type, "title": slug.title(),
        "body": "", "outgoing_links": list(outgoing_links or []),
        "supports_page_existence": ["x"], "status": "active",
        "confidence": "medium",
    }


class TestM1:
    def test_m1_all_links_resolve_within_same_source(self):
        """Page 'foo' links to slug 'bar' which is also a page in the same source.
        Resolves to 1/1 = 1.0."""
        pages = [
            _page("foo", page_type="summary", outgoing_links=["bar"]),
            _page("bar", page_type="concept"),
        ]
        records = [fake_record(source_id="s1", summary_slug="foo", pages=pages)]
        score = scorer.m1(records)
        assert score.name == "M1"
        assert score.numerator == 1
        assert score.denominator == 1
        assert score.rate == 1.0
        assert score.weight == 0.20

    def test_m1_unresolved_link_lowers_rate(self):
        pages = [
            _page("foo", page_type="summary", outgoing_links=["bar", "missing"]),
            _page("bar", page_type="concept"),
        ]
        records = [fake_record(source_id="s1", summary_slug="foo", pages=pages)]
        score = scorer.m1(records)
        assert score.numerator == 1   # bar resolves
        assert score.denominator == 2 # bar + missing
        assert score.rate == 0.5

    def test_m1_list_semantics_duplicates_count_separately(self):
        """Round 4 CW3: outgoing_links: ['bar', 'bar'] → both occurrences count."""
        pages = [
            _page("foo", page_type="summary", outgoing_links=["bar", "bar"]),
            _page("bar", page_type="concept"),
        ]
        records = [fake_record(source_id="s1", summary_slug="foo", pages=pages)]
        score = scorer.m1(records)
        assert score.denominator == 2
        assert score.numerator == 2

    def test_m1_cross_source_resolution(self):
        """Source A's link to slug 'qux' resolves because source B has 'qux'."""
        pages_a = [_page("foo", page_type="summary", outgoing_links=["qux"])]
        pages_b = [_page("qux", page_type="summary")]
        records = [
            fake_record(source_id="A", summary_slug="foo", pages=pages_a),
            fake_record(source_id="B", summary_slug="qux", pages=pages_b),
        ]
        score = scorer.m1(records)
        assert score.numerator == 1
        assert score.denominator == 1
        assert score.rate == 1.0

    def test_m1_zero_denominator_scores_zero_not_none(self):
        """Round 4 MF6: model emits zero outgoing_links → M1 = 0.0 (penalty),
        NOT None (which would redistribute weight pro-rata, rewarding abstention)."""
        pages = [_page("foo", page_type="summary", outgoing_links=[])]
        records = [fake_record(source_id="s1", summary_slug="foo", pages=pages)]
        score = scorer.m1(records)
        assert score.denominator == 0
        assert score.rate == 0.0, "model-controlled zero-denom must score 0.0, not None"

    def test_m1_target_set_excludes_schema_failed_sources(self):
        """target_set is built from R_ps only. A schema-fail source's slugs
        do NOT serve as resolution targets for other sources."""
        pages_a = [_page("foo", page_type="summary", outgoing_links=["zzz"])]
        # zzz only exists in a schema-failed source — should NOT resolve
        pages_b = [_page("zzz", page_type="summary")]
        records = [
            fake_record(source_id="A", summary_slug="foo", pages=pages_a),
            fake_record(source_id="B", summary_slug="zzz", pages=pages_b, schema_ok=False),
        ]
        score = scorer.m1(records)
        assert score.numerator == 0  # zzz doesn't count (B failed schema)
        assert score.denominator == 1

    def test_m1_skips_non_dict_pages(self):
        """If a page entry is not a dict (defensive), skip it."""
        rec = fake_record(source_id="s1")
        rec["parsed_json"]["pages"].append("not a dict")  # garbage
        rec["parsed_json"]["pages"][0]["outgoing_links"] = ["x"]  # x is the summary slug
        records = [rec]
        score = scorer.m1(records)
        # x resolves, the "not a dict" entry is skipped
        assert score.numerator == 1
        assert score.denominator == 1


# ===========================================================================
# §6 — M2 / M3 Jaccard (weight 5% each)
# ===========================================================================

class TestM2:
    def test_m2_perfect_alignment_rate_one(self):
        """Declared concept slugs match emitted concept-typed pages exactly."""
        pages = [
            _page("foo", page_type="summary"),
            _page("c1", page_type="concept"),
            _page("c2", page_type="concept"),
        ]
        records = [fake_record(
            source_id="s", summary_slug="foo", pages=pages,
            concept_slugs=["c1", "c2"],
        )]
        score = scorer.m2(records)
        assert score.name == "M2"
        assert score.numerator == 2  # |{c1,c2} ∩ {c1,c2}|
        assert score.denominator == 2
        assert score.rate == 1.0
        assert score.weight == 0.05

    def test_m2_partial_jaccard(self):
        """D = {c1, c2}, E = {c2, c3} → ∩ = {c2}, ∪ = {c1,c2,c3} → 1/3."""
        pages = [
            _page("foo", page_type="summary"),
            _page("c2", page_type="concept"),
            _page("c3", page_type="concept"),  # emitted but not declared
        ]
        records = [fake_record(
            source_id="s", summary_slug="foo", pages=pages,
            concept_slugs=["c1", "c2"],  # c1 declared but not emitted
        )]
        score = scorer.m2(records)
        assert score.numerator == 1
        assert score.denominator == 3
        assert score.rate == pytest.approx(1/3)

    def test_m2_zero_denominator_scores_zero(self):
        """No concepts declared, no concept-typed pages → corpus-wide zero
        denominator. Round 4 MF6: model-controlled → score 0.0, not None."""
        pages = [_page("foo", page_type="summary")]
        records = [fake_record(source_id="s", summary_slug="foo", pages=pages)]
        score = scorer.m2(records)
        assert score.denominator == 0
        assert score.rate == 0.0

    def test_m2_non_list_concept_slugs_coerced_to_empty(self):
        """Round 4 CW2: if concept_slugs is a string, set('foo') would yield
        char-slugs. Coerce non-list to empty."""
        rec = fake_record(source_id="s")
        rec["parsed_json"]["concept_slugs"] = "garbage_string"
        records = [rec]
        score = scorer.m2(records)
        assert score.numerator == 0
        assert score.denominator == 0
        assert score.rate == 0.0   # zero-denom → 0.0, not crash from set('garbage_string')


class TestM3:
    def test_m3_uses_article_slugs_and_article_pages(self):
        """M3 mirrors M2 with concept→article. One test confirms symmetry."""
        pages = [
            _page("foo", page_type="summary"),
            _page("a1", page_type="article"),
            _page("c1", page_type="concept"),
        ]
        records = [fake_record(
            source_id="s", summary_slug="foo", pages=pages,
            article_slugs=["a1"],
            concept_slugs=["c1"],   # should NOT enter M3
        )]
        score = scorer.m3(records)
        assert score.name == "M3"
        assert score.numerator == 1
        assert score.denominator == 1
        assert score.rate == 1.0
        assert score.weight == 0.05


# ===========================================================================
# §6 — M4 semantic_pass_rate (weight 15%)
# ===========================================================================

class TestM4:
    def test_m4_semantic_pass_count_over_total(self):
        records = [
            fake_record(source_id="ok"),
            fake_record(source_id="sem_fail", semantic_ok=False),
            fake_record(source_id="parse_fail", parse_ok=False, schema_ok=False, semantic_ok=False),
        ]
        score = scorer.m4(records)
        assert score.name == "M4"
        assert score.numerator == 1
        assert score.denominator == 3
        assert score.rate == pytest.approx(1/3)
        assert score.weight == 0.15


# ===========================================================================
# §6 — M5 body_link_syntax_match (weight 5%)
# ===========================================================================

class TestM5:
    def test_m5_aggregates_body_link_counts_to_jaccard(self):
        records = [
            fake_record(source_id="s1", body_link_intersection=2, body_link_union=4),
            fake_record(source_id="s2", body_link_intersection=1, body_link_union=2),
        ]
        score = scorer.m5(records)
        assert score.name == "M5"
        assert score.numerator == 3
        assert score.denominator == 6
        assert score.rate == 0.5
        assert score.weight == 0.05

    def test_m5_zero_denom_scores_zero(self):
        """Round 4 MF6: model emits no declared/body wikilinks → M5 = 0.0."""
        records = [fake_record(source_id="s1", body_link_intersection=0, body_link_union=0)]
        score = scorer.m5(records)
        assert score.denominator == 0
        assert score.rate == 0.0


# ===========================================================================
# §6 — M6 cost_per_1k_source_words (weight 15%, raw $ rate, lower-is-better)
# ===========================================================================

class TestM6:
    def test_m6_cost_aggregation(self):
        # haiku-4.5 prices: $1/M input, $5/M output
        # 500 input + 300 output tokens × $1/$5 per 1M:
        #   cost = (500*1 + 300*5)/1e6 = (500 + 1500)/1e6 = 0.002
        # source_words = 1000
        # rate = (0.002 / 1000) × 1000 = 0.002 $/1K source-words
        records = [fake_record(
            source_id="s1", input_tokens=500, output_tokens=300, source_words=1000,
        )]
        score = scorer.m6(records, price_in=1.0, price_out=5.0)
        assert score.name == "M6"
        assert score.denominator == 1000
        assert score.rate == pytest.approx(0.002)
        assert score.weight == 0.15

    def test_m6_includes_parse_failed_when_source_words_positive(self):
        """Round 4 MF1: failed calls bill cost; gate is source_words > 0,
        not parse_ok."""
        records = [
            fake_record(
                source_id="s1", parse_ok=False, schema_ok=False, semantic_ok=False,
                input_tokens=500, output_tokens=300, source_words=1000,
            ),
        ]
        score = scorer.m6(records, price_in=1.0, price_out=5.0)
        assert score.denominator == 1000   # included despite parse failure

    def test_m6_skips_zero_source_words_records(self):
        """source_words=0 is corpus-side pathology; record excluded entirely."""
        records = [
            fake_record(source_id="empty", source_words=0,
                        input_tokens=10, output_tokens=10),
            fake_record(source_id="ok", source_words=1000,
                        input_tokens=500, output_tokens=300),
        ]
        score = scorer.m6(records, price_in=1.0, price_out=5.0)
        assert score.denominator == 1000

    def test_m6_local_model_zero_prices_yields_zero_cost(self):
        records = [fake_record(
            source_id="s1", input_tokens=500, output_tokens=300, source_words=1000,
        )]
        score = scorer.m6(records, price_in=0.0, price_out=0.0)
        assert score.numerator == 0.0
        assert score.rate == 0.0

    def test_m6_zero_denom_returns_none_corpus_controlled(self):
        """Round 4 MF6: corpus-controlled denom → None, NOT 0.0."""
        records = [fake_record(source_id="empty", source_words=0)]
        score = scorer.m6(records, price_in=1.0, price_out=5.0)
        assert score.rate is None


# ===========================================================================
# §6 — M7 latency_per_1k_source_words (weight 15%)
# ===========================================================================

class TestM7:
    def test_m7_latency_per_1k_source_words(self):
        records = [
            fake_record(source_id="s1", latency_ms=2000, source_words=1000),
            fake_record(source_id="s2", latency_ms=3000, source_words=1000),
        ]
        score = scorer.m7(records)
        assert score.name == "M7"
        # (Σ 5000 / Σ 2000) × 1000 = 2500 ms / 1K source-words
        assert score.rate == 2500.0
        assert score.weight == 0.15

    def test_m7_zero_denom_returns_none(self):
        records = [fake_record(source_id="empty", source_words=0)]
        score = scorer.m7(records)
        assert score.rate is None


# ===========================================================================
# §6 — Diagnostics (weight 0)
# ===========================================================================

class TestDiagnostics:
    def test_retry_load_clamped_at_max_retries(self):
        """Round 4 MF8: per-record contribution clamped at MAX_RETRIES.
        With MAX_RETRIES=2, record with attempts=5 contributes 2 (not 4)."""
        records = [
            fake_record(source_id="s1", attempts=1),  # contributes 0
            fake_record(source_id="s2", attempts=3),  # contributes 2 (max retries used)
            fake_record(source_id="s3", attempts=5),  # contributes min(2, 4) = 2
        ]
        score = scorer.retry_load(records)
        assert score.name == "retry_load"
        # 0 + 2 + 2 = 4; denominator = 3 × 2 = 6 → 4/6 = 0.6667
        assert score.numerator == 4
        assert score.denominator == 6
        assert score.rate == pytest.approx(4/6)
        assert score.weight == 0.0

    def test_retry_load_clamps_negative_to_zero(self):
        """Pre-call failures: attempts=0 → max(0, 0-1)=0."""
        records = [fake_record(source_id="s1", attempts=0)]
        score = scorer.retry_load(records)
        assert score.numerator == 0

    def test_token_overrun_rate(self):
        records = [
            fake_record(source_id="s1", token_overrun=False),
            fake_record(source_id="s2", token_overrun=True),
            fake_record(source_id="s3", token_overrun=True),
        ]
        score = scorer.token_overrun_rate(records)
        assert score.name == "token_overrun_rate"
        assert score.numerator == 2
        assert score.denominator == 3

    def test_pages_per_1k_source_words(self):
        rec1 = fake_record(source_id="s1", source_words=1000)
        rec1["parsed_summary"]["page_count"] = 3
        rec2 = fake_record(source_id="s2", source_words=2000)
        rec2["parsed_summary"]["page_count"] = 4
        score = scorer.pages_per_1k_source_words([rec1, rec2])
        # (Σ 7 / Σ 3000) × 1000 ≈ 2.333
        assert score.name == "pages_per_1k_source_words"
        assert score.rate == pytest.approx(7/3000 * 1000)
        assert score.weight == 0.0

    def test_pages_per_1k_zero_for_parse_failed(self):
        records = [fake_record(source_id="fail", parse_ok=False, source_words=1000)]
        score = scorer.pages_per_1k_source_words(records)
        # Failed record contributes 0 pages; denominator stays 1000
        assert score.numerator == 0
        assert score.denominator == 1000
        assert score.rate == 0.0


# ===========================================================================
# §7 — Average-rank (Borda) normalization
# ===========================================================================

def _rs(model_id: str, m6_rate: Optional[float] = None, m7_rate: Optional[float] = None) -> "scorer.RunScore":
    return scorer.RunScore(
        run_id=f"{model_id}-test",
        model_id=model_id,
        provider="anthropic",
        model="m",
        n_attempted=5,
        s0=MeasureScore("S0", 5, 5, 1.0, 0.20),
        s1=MeasureScore("S1", 5, 5, 1.0, 0.0),
        s2=MeasureScore("S2", 5, 5, 1.0, 0.0),
        s3=MeasureScore("S3", 5, 5, 1.0, 0.0),
        measures={
            "M1": MeasureScore("M1", 1, 1, 1.0, 0.20),
            "M2": MeasureScore("M2", 1, 1, 1.0, 0.05),
            "M3": MeasureScore("M3", 1, 1, 1.0, 0.05),
            "M4": MeasureScore("M4", 5, 5, 1.0, 0.15),
            "M5": MeasureScore("M5", 1, 1, 1.0, 0.05),
            "M6": MeasureScore("M6", 0.0, 1, m6_rate, 0.15),
            "M7": MeasureScore("M7", 0,   1, m7_rate, 0.15),
        },
        diagnostics={},
        m6_borda=None,
        m7_borda=None,
        final_score=None,
    )


class TestBordaNormalize:
    def test_borda_worked_example_from_spec_section_7(self):
        """Spec § 7 worked example: 5 candidates, lower_is_better,
        rates [0.001, 0.001, 0.002, 0.005, 0.005] → scores
        [0.875, 0.875, 0.5, 0.125, 0.125]."""
        runs = [
            _rs("A", m6_rate=0.001),
            _rs("B", m6_rate=0.001),
            _rs("C", m6_rate=0.002),
            _rs("D", m6_rate=0.005),
            _rs("E", m6_rate=0.005),
        ]
        result = scorer.borda_normalize(runs, "M6", lower_is_better=True)
        assert result["A"] == pytest.approx(0.875)
        assert result["B"] == pytest.approx(0.875)
        assert result["C"] == pytest.approx(0.5)
        assert result["D"] == pytest.approx(0.125)
        assert result["E"] == pytest.approx(0.125)

    def test_borda_strict_extremes(self):
        """No ties: best gets 1.0, worst gets 0.0."""
        runs = [
            _rs("A", m6_rate=0.001),
            _rs("B", m6_rate=0.005),
        ]
        result = scorer.borda_normalize(runs, "M6", lower_is_better=True)
        assert result["A"] == 1.0
        assert result["B"] == 0.0

    def test_borda_all_equal_returns_half(self):
        """Round 4 MF5: all-equal → every candidate gets 0.5 (no signal)."""
        runs = [_rs("A", m6_rate=0.005), _rs("B", m6_rate=0.005)]
        result = scorer.borda_normalize(runs, "M6", lower_is_better=True)
        assert result["A"] == 0.5
        assert result["B"] == 0.5

    def test_borda_single_candidate_gets_full_score(self):
        runs = [_rs("A", m6_rate=0.005)]
        result = scorer.borda_normalize(runs, "M6", lower_is_better=True)
        assert result["A"] == 1.0

    def test_borda_drops_none_rate_runs(self):
        """A run with rate=None is excluded from the dict."""
        runs = [
            _rs("A", m6_rate=0.001),
            _rs("B", m6_rate=None),
            _rs("C", m6_rate=0.005),
        ]
        result = scorer.borda_normalize(runs, "M6", lower_is_better=True)
        assert "B" not in result
        assert result["A"] == 1.0
        assert result["C"] == 0.0

    def test_borda_higher_is_better_inverts_sort(self):
        """For non-cost measures (e.g., scores), higher rate wins."""
        runs = [
            _rs("A", m6_rate=0.9),  # higher is better → A wins
            _rs("B", m6_rate=0.1),
        ]
        result = scorer.borda_normalize(runs, "M6", lower_is_better=False)
        assert result["A"] == 1.0
        assert result["B"] == 0.0


# ===========================================================================
# §8 — Final score (post-Borda)
# ===========================================================================

class TestFinalScore:
    def test_final_score_all_components_present_simple_weighted_sum(self):
        """All 8 components present and = 1.0 → final_score = 1.0."""
        run = _rs("A", m6_rate=0.001, m7_rate=1.0)
        run = scorer.RunScore(
            **{**run.__dict__, "m6_borda": 1.0, "m7_borda": 1.0}
        )
        final = scorer.final_score(run)
        assert final == pytest.approx(1.0)

    def test_final_score_pro_rata_when_m6_none(self):
        """If M6 borda is None (corpus-controlled zero-denom), redistribute
        its weight pro-rata. With S0/M1/M2/M3/M4/M5/M7 all = 1.0, final
        stays 1.0."""
        run = _rs("A", m6_rate=None, m7_rate=1.0)
        run = scorer.RunScore(
            **{**run.__dict__, "m6_borda": None, "m7_borda": 1.0}
        )
        final = scorer.final_score(run)
        assert final == pytest.approx(1.0)

# ===========================================================================
# §9 — score_run integration
# ===========================================================================

def _write_records(tmp_path, run_id: str, records: list[dict]):
    """Helper: write fake records as <tmp>/llm_resp/<run_id>/<source_id>.json."""
    import json
    run_dir = tmp_path / "llm_resp" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        path = run_dir / f"{r['source_id'].replace('/', '__')}.json"
        path.write_text(json.dumps(r), encoding="utf-8")


class TestScoreRun:
    def test_score_run_returns_runscore_with_raw_rates(self, tmp_path):
        records = [
            fake_record(source_id="s1", provider="anthropic", model="claude-haiku-4-5-20251001",
                        run_id="haiku-test"),
            fake_record(source_id="s2", provider="anthropic", model="claude-haiku-4-5-20251001",
                        run_id="haiku-test"),
        ]
        _write_records(tmp_path, "haiku-test", records)
        run = scorer.score_run(tmp_path, "haiku-test", "haiku-4.5")
        assert run.run_id == "haiku-test"
        assert run.model_id == "haiku-4.5"
        assert run.provider == "anthropic"
        assert run.model == "claude-haiku-4-5-20251001"
        assert run.n_attempted == 2
        assert run.s0.rate == 1.0
        assert run.measures["M6"].rate is not None  # raw $ rate
        assert run.m6_borda is None  # not yet normalized
        assert run.final_score is None

    def test_score_run_raises_on_no_records(self, tmp_path):
        # Empty run dir
        (tmp_path / "llm_resp" / "haiku-test").mkdir(parents=True)
        with pytest.raises(ValueError, match="no records"):
            scorer.score_run(tmp_path, "haiku-test", "haiku-4.5")

    def test_score_run_raises_on_unknown_model_id(self, tmp_path):
        records = [fake_record(source_id="s1", provider="anthropic", model="claude-haiku-4-5-20251001")]
        _write_records(tmp_path, "haiku-test", records)
        with pytest.raises(ValueError, match="not found in registry"):
            scorer.score_run(tmp_path, "haiku-test", "no-such-model")

    def test_score_run_raises_on_provider_model_mismatch(self, tmp_path):
        """Record's persisted (provider, model) doesn't match the registry's
        ModelEntry for the requested model_id."""
        # Registry haiku-4.5 expects ('anthropic', 'claude-haiku-4-5-20251001');
        # write a record with wrong model name.
        records = [fake_record(source_id="s1", provider="anthropic", model="claude-WRONG")]
        _write_records(tmp_path, "haiku-test", records)
        with pytest.raises(ValueError, match="provider/model mismatch"):
            scorer.score_run(tmp_path, "haiku-test", "haiku-4.5")

    def test_score_run_raises_on_capture_full_violation(self, tmp_path):
        """Round 4: parse_ok=True with parsed_json=None means capture-full
        wasn't on for the runner; scorer raises RuntimeError."""
        rec = fake_record(source_id="s1", provider="anthropic", model="claude-haiku-4-5-20251001")
        rec["parsed_json"] = None  # simulate capture-full off
        _write_records(tmp_path, "haiku-test", [rec])
        with pytest.raises(RuntimeError, match="KDB_RESP_STATS_CAPTURE_FULL"):
            scorer.score_run(tmp_path, "haiku-test", "haiku-4.5")

    def test_score_run_raises_on_duplicate_source_id(self, tmp_path):
        # Need to write to two different files but with same source_id inside
        import json
        run_dir = tmp_path / "llm_resp" / "haiku-test"
        run_dir.mkdir(parents=True)
        rec = fake_record(source_id="s1", provider="anthropic", model="claude-haiku-4-5-20251001")
        (run_dir / "a.json").write_text(json.dumps(rec))
        (run_dir / "b.json").write_text(json.dumps(rec))
        with pytest.raises(ValueError, match="duplicate"):
            scorer.score_run(tmp_path, "haiku-test", "haiku-4.5")


# ===========================================================================
# §9 — score_runs (cross-model Borda enrichment)
# ===========================================================================

class TestScoreRuns:
    def test_score_runs_populates_borda_and_final_score(self, tmp_path):
        # Build two single-model runs via score_run
        haiku_records = [fake_record(
            source_id="s1", provider="anthropic", model="claude-haiku-4-5-20251001",
            run_id="haiku-r", input_tokens=500, output_tokens=300, latency_ms=2000,
            source_words=1000,
        )]
        sonnet_records = [fake_record(
            source_id="s1", provider="anthropic", model="claude-sonnet-4-6",
            run_id="sonnet-r", input_tokens=500, output_tokens=300, latency_ms=3000,
            source_words=1000,
        )]
        _write_records(tmp_path, "haiku-r", haiku_records)
        _write_records(tmp_path, "sonnet-r", sonnet_records)
        haiku = scorer.score_run(tmp_path, "haiku-r", "haiku-4.5")
        sonnet = scorer.score_run(tmp_path, "sonnet-r", "sonnet-4.6")

        enriched = scorer.score_runs([haiku, sonnet])

        # Original objects untouched (frozen anyway, but explicit)
        assert haiku.m6_borda is None
        assert haiku.final_score is None

        # Enriched objects have Borda + final_score
        haiku_e = next(r for r in enriched if r.model_id == "haiku-4.5")
        sonnet_e = next(r for r in enriched if r.model_id == "sonnet-4.6")

        # Haiku: cheaper (lower $/M tokens × same input) → wins M6 Borda
        assert haiku_e.m6_borda == 1.0
        assert sonnet_e.m6_borda == 0.0
        # Haiku faster (2000ms vs 3000ms) → wins M7 Borda
        assert haiku_e.m7_borda == 1.0
        assert sonnet_e.m7_borda == 0.0

        # final_score populated and in [0, 1]
        assert haiku_e.final_score is not None
        assert 0.0 <= haiku_e.final_score <= 1.0
        # Haiku scores higher (faster + cheaper, all else equal)
        assert haiku_e.final_score > sonnet_e.final_score


    def test_final_score_raises_when_all_components_none(self):
        # Synthesize a RunScore where every component rate is None
        run = scorer.RunScore(
            run_id="degenerate", model_id="x", provider="x", model="x",
            n_attempted=0,
            s0=MeasureScore("S0", 0, 0, None, 0.20),
            s1=MeasureScore("S1", 0, 0, None, 0.0),
            s2=MeasureScore("S2", 0, 0, None, 0.0),
            s3=MeasureScore("S3", 0, 0, None, 0.0),
            measures={
                "M1": MeasureScore("M1", 0, 0, None, 0.20),
                "M2": MeasureScore("M2", 0, 0, None, 0.05),
                "M3": MeasureScore("M3", 0, 0, None, 0.05),
                "M4": MeasureScore("M4", 0, 0, None, 0.15),
                "M5": MeasureScore("M5", 0, 0, None, 0.05),
                "M6": MeasureScore("M6", 0, 0, None, 0.15),
                "M7": MeasureScore("M7", 0, 0, None, 0.15),
            },
            diagnostics={},
            m6_borda=None, m7_borda=None, final_score=None,
        )
        with pytest.raises(ValueError, match="degenerate"):
            scorer.final_score(run)


# ===========================================================================
# §9b — verbose trace M5 per-page asymmetry block (Task #39)
# ===========================================================================

def _record_with_pages(
    *,
    source_id: str,
    pages: list[dict],
    body_link_intersection: int,
    body_link_union: int,
):
    """Build a record whose parsed_json carries the supplied pages and whose
    persisted body_link_* counters can be set independently — so a test can
    drive M5 rate < 1.0 from the aggregate while controlling per-page detail."""
    return fake_record(
        source_id=source_id,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        run_id="haiku-test",
        pages=pages,
        body_link_intersection=body_link_intersection,
        body_link_union=body_link_union,
    )


class TestVerboseTraceM5Asymmetry:
    def _aligned_page(self):
        return {
            "slug": "summary-foo", "page_type": "summary", "title": "Foo",
            "body": "[[a]] and [[b]]", "outgoing_links": ["a", "b"],
            "supports_page_existence": ["s1"], "status": "active", "confidence": "high",
        }

    def _asymmetric_page(self):
        # Mirrors the haiku 2026-05-08 slip: declared 3, body 2 → declared-only=[c]
        return {
            "slug": "summary-foo", "page_type": "summary", "title": "Foo",
            "body": "[[a]] and [[b]]", "outgoing_links": ["a", "b", "c"],
            "supports_page_existence": ["s1"], "status": "active", "confidence": "high",
        }

    def test_trace_omits_m5_block_when_perfect(self, tmp_path):
        """M5 = 1.0 (rate exactly 1) → no per-page asymmetry block in trace."""
        rec = _record_with_pages(
            source_id="s1", pages=[self._aligned_page()],
            body_link_intersection=2, body_link_union=2,
        )
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        assert run.measures["M5"].rate == 1.0
        joined = "\n".join(sink)
        assert "per-page M5 asymmetry" not in joined

    def test_trace_emits_m5_block_when_asymmetric(self, tmp_path):
        """M5 < 1.0 → block present, names the offending page + slug."""
        rec = _record_with_pages(
            source_id="s1", pages=[self._asymmetric_page()],
            body_link_intersection=2, body_link_union=3,
        )
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        assert run.measures["M5"].rate == pytest.approx(2 / 3)
        joined = "\n".join(sink)
        assert "per-page M5 asymmetry:" in joined
        assert "s1 → page summary-foo" in joined
        assert "declared-only" in joined and "['c']" in joined
        assert "body-only" in joined and "[]" in joined

    def test_trace_omits_m5_block_when_no_link_activity(self, tmp_path):
        """When the union is 0 (no link activity), M5 rate is 0.0 per
        Round 4 MF6. The trigger (rate<1.0) fires, but the helper finds
        nothing — so no header and no entries land in the sink."""
        rec = _record_with_pages(
            source_id="s1", pages=[self._aligned_page()],
            body_link_intersection=0, body_link_union=0,
        )
        rec["parsed_json"]["pages"][0]["outgoing_links"] = []
        rec["parsed_json"]["pages"][0]["body"] = "no links."
        _write_records(tmp_path, "haiku-test", [rec])
        sink: list[str] = []
        run = scorer.score_run(
            tmp_path, "haiku-test", "haiku-4.5", trace_sink=sink,
        )
        assert run.measures["M5"].rate == 0.0
        joined = "\n".join(sink)
        assert "per-page M5 asymmetry" not in joined


