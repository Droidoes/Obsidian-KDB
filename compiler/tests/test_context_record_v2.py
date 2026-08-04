"""#123 P3a.2a — ContextRecordV2 factory + strict parser + writer, UNWIRED
(blueprint §4.5, §9 P3a.2a row).

The V2 record carries the V1 skeleton minus the retiring vocabulary
(configured_t2_mode / effective_t2_strategy / max_hops), the per-expression
`matched | unresolved` key outcomes with the CLOSED annotation vocabulary, and
the `search` section — the adapter's SearchSummary, populated on every record
where a search ran (abstention included), null only when no search ran.

KeyOutcomeV1 / KeyOutcomeV2 are DISTINCT types so historical and current
vocabularies cannot mix (A19/B11); the cross-parser rejection is pinned here.
"""
from __future__ import annotations

import json
import logging

import pytest

from common.llm_telemetry import safe_source_id
from common.types import (
    SearchBudgetRecord,
    SearchHitSummary,
    SearchStageSplit,
    SearchSummary,
    TierRecord,
)
from compiler import context_record
from compiler.context_record import (
    CONTEXT_RECORD_V2_SCHEMA_VERSION,
    ContextFailureInputV2,
    ContextRecordError,
    ContextRecordV2,
    ContextTelemetryV2,
    KeyOutcomeV2,
    build_context_record_v2,
    parse_context_record_v1,
    parse_context_record_v2,
    project_key_outcomes_v2,
    write_context_record_v2,
)
from kdb_search.constants import MAX_RESULTS

SOURCE_ID = "KDB/raw/s.md"


# ---------- fixtures ----------

def _hits() -> tuple[SearchHitSummary, ...]:
    return (
        SearchHitSummary(slug="charlie-munger", first_run_id="run-1",
                         match_recency="cohort", matched_expressions=("moats",)),
        SearchHitSummary(slug="owner-earnings", first_run_id=None,
                         match_recency="age_unknown", matched_expressions=("moats",)),
        SearchHitSummary(slug="warren-buffett", first_run_id="r-old",
                         match_recency="pre_run", matched_expressions=("management",)),
    )


def _summary(**overrides) -> SearchSummary:
    base = dict(
        search_ran=True,
        query_kind="state_b",
        status="completed",
        failure_class=None,
        execution="two_stage_attempted",
        evidence_status="complete",
        body_coverage=1.0,
        query_truncated_indices=(),
        eligible_space_size=3,
        stage1_retained=3,
        stage2_pool_size=3,
        returned_entries=3,
        valid_entry_yield=1.0,
        unattributed_hit_count=0,
        retry_attempts=0,
        watched=(),
        concordance=1.0,
        selector_provider="deepseek",
        selector_model="test",
        selector_route="openai_compat",
        latency_ms=24,
        cost_usd=0.0,
        budget_records=(SearchBudgetRecord(
            stage="thin_selection", budget_estimate_tokens=1000,
            selector_window=400000, headroom_factor=0.8,
            visible_output_allowance=2000, hidden_output_reserve=1000,
            fits=True, detected="pre_call", budget_side="input",
            finish_reason_raw=None, finish_reason_normalized=None),),
        stage2_budget_bound=False,
        stage_splits=(
            SearchStageSplit(stage="thin", attempts=1, provider_input_tokens=1000, cost_usd=0.0),
            SearchStageSplit(stage="fat", attempts=1, provider_input_tokens=2000, cost_usd=0.0),
        ),
        artifact_path="/state/runs/run-1/search/s.json",
        search_snapshot_hash="sha256:abc",
        space_entity_count=3,
        hits=_hits(),
    )
    return SearchSummary(**{**base, **overrides})


def _abstain_summary() -> SearchSummary:
    """§4.1 step 3's outcome: the adapter searched the empty space and the core
    abstained — a REAL outcome producing a populated search section (A10)."""
    return _summary(
        status="abstain_empty_space",
        execution="not_executed",
        evidence_status="not_applicable",
        body_coverage=None,
        eligible_space_size=0,
        stage1_retained=0,
        stage2_pool_size=0,
        returned_entries=0,
        valid_entry_yield=None,
        watched=("domain_missing",),
        concordance=None,
        latency_ms=0,
        budget_records=(),
        stage_splits=(
            SearchStageSplit(stage="thin", attempts=0, provider_input_tokens=None, cost_usd=0.0),
            SearchStageSplit(stage="fat", attempts=0, provider_input_tokens=None, cost_usd=0.0),
        ),
        space_entity_count=0,
        hits=(),
    )


def _telemetry_v2(**overrides) -> ContextTelemetryV2:
    base = dict(
        source_id=SOURCE_ID,
        keys_emitted=["moats", "management"],
        key_outcomes=[
            KeyOutcomeV2("moats", "matched", None, "run-1", "cohort"),
            KeyOutcomeV2("management", "unresolved", "no_match", None, None),
        ],
        t1=TierRecord(candidates=1, delivered=1, slugs=["t1-page"]),
        t2=TierRecord(candidates=3, delivered=2, slugs=["charlie-munger", "warren-buffett"]),
        t3=TierRecord(candidates=4, delivered=1, slugs=["t3-page"]),
        candidate_universe_size=7,
        domain_scope="value-investing",
        cold_start=False,
        page_cap=50,
        search=_summary(),
    )
    return ContextTelemetryV2(**{**base, **overrides})


def _failure_input_v2(**overrides) -> ContextFailureInputV2:
    base = dict(
        source_id=SOURCE_ID,
        keys_emitted=["moats", "management"],   # frontmatter fallback (A9)
        domain_scope="value-investing",
        page_cap=50,
        search=_summary(),
    )
    return ContextFailureInputV2(**{**base, **overrides})


def _complete_dict() -> dict:
    return build_context_record_v2(
        run_id="run-1", status="complete", telemetry=_telemetry_v2()).to_dict()


# ---------- factory ----------

def test_v2_factory_complete_maps_fields():
    rec = build_context_record_v2(run_id="run-1", status="complete", telemetry=_telemetry_v2())
    assert isinstance(rec, ContextRecordV2)
    assert rec.schema_version == CONTEXT_RECORD_V2_SCHEMA_VERSION == 2
    assert rec.run_id == "run-1"
    assert rec.status == "complete"
    assert rec.source_id == SOURCE_ID
    assert rec.keys_emitted == ["moats", "management"]
    assert len(rec.key_outcomes) == 2
    assert rec.key_outcomes[0].status == "matched"
    assert rec.key_outcomes[0].annotation is None
    assert rec.key_outcomes[1].status == "unresolved"
    assert rec.key_outcomes[1].annotation == "no_match"
    assert rec.candidate_universe_size == 7
    assert rec.cold_start is False
    assert rec.page_cap == 50
    assert rec.search is not None and rec.search.status == "completed"
    # The retired V1 vocabulary is gone from the V2 shape.
    assert not hasattr(rec, "configured_t2_mode")
    assert not hasattr(rec, "effective_t2_strategy")
    assert not hasattr(rec, "max_hops")


def test_v2_factory_complete_pre_pass1_search_null():
    """Pre-Pass-1 record: no search ran ⇒ search section null (§4.5)."""
    rec = build_context_record_v2(
        run_id="run-1", status="complete",
        telemetry=_telemetry_v2(keys_emitted=[], key_outcomes=[], search=None))
    assert rec.search is None
    assert rec.keys_emitted == []
    assert rec.key_outcomes == []


def test_v2_factory_context_failed_with_search():
    """The search completed before the builder raised ⇒ context_failed.search
    is NON-NULL (B8, guaranteed by §4.1 step 6); observables stay null."""
    rec = build_context_record_v2(
        run_id="run-1", status="context_failed", failure_input=_failure_input_v2())
    assert rec.status == "context_failed"
    assert rec.keys_emitted == ["moats", "management"]
    assert rec.key_outcomes == []
    zero = TierRecord(0, 0, [])
    assert rec.t1 == rec.t2 == rec.t3 == zero
    assert rec.candidate_universe_size is None
    assert rec.cold_start is None
    assert rec.search is not None and rec.search.status == "completed"


def test_v2_factory_context_failed_without_search():
    """Adapter-error path (A9): no summary exists ⇒ search null, keys_emitted
    falls back to frontmatter.entity_search_keys."""
    rec = build_context_record_v2(
        run_id="run-1", status="context_failed",
        failure_input=_failure_input_v2(search=None))
    assert rec.search is None
    assert rec.keys_emitted == ["moats", "management"]


def test_v2_abstention_record_search_populated():
    """abstain_empty_space is a real outcome: the search section is POPULATED,
    not null (§4.1 step 3, A10) — and it round-trips through the parser."""
    rec = build_context_record_v2(
        run_id="run-1", status="complete",
        telemetry=_telemetry_v2(search=_abstain_summary()))
    assert rec.search is not None
    assert rec.search.status == "abstain_empty_space"
    assert "domain_missing" in rec.search.watched
    parsed = parse_context_record_v2(rec.to_dict())
    assert parsed == rec


@pytest.mark.parametrize("kwargs", [
    {},  # complete requires telemetry
    {"telemetry": _telemetry_v2(), "failure_input": _failure_input_v2()},  # mutually exclusive
])
def test_v2_factory_complete_invalid_combos(kwargs):
    with pytest.raises(ContextRecordError):
        build_context_record_v2(run_id="r", status="complete", **kwargs)


def test_v2_factory_complete_requires_non_null_observables():
    bad = ContextTelemetryV2(**{**_telemetry_v2().__dict__, "cold_start": None})  # type: ignore[arg-type]
    with pytest.raises(ContextRecordError, match="observables"):
        build_context_record_v2(run_id="r", status="complete", telemetry=bad)


@pytest.mark.parametrize("kwargs", [
    {},  # context_failed requires failure_input
    {"telemetry": _telemetry_v2(), "failure_input": _failure_input_v2()},
])
def test_v2_factory_context_failed_invalid_combos(kwargs):
    with pytest.raises(ContextRecordError):
        build_context_record_v2(run_id="r", status="context_failed", **kwargs)


def test_v2_factory_unknown_status_raises():
    with pytest.raises(ContextRecordError):
        build_context_record_v2(run_id="r", status="weird", telemetry=_telemetry_v2())  # type: ignore[arg-type]


# ---------- key-outcome projection (§4.5, A6) ----------

def test_projection_matched_and_unresolved():
    outcomes = project_key_outcomes_v2(
        keys_emitted=("moats", "management"),
        rendered_expressions=("moats", "management"),
        unresolved_expressions=("management",),
        search=_summary(),
    )
    assert outcomes[0] == KeyOutcomeV2("moats", "matched", None, "run-1", "cohort")
    assert outcomes[1] == KeyOutcomeV2("management", "unresolved", "no_match", None, None)


def test_projection_highest_ranked_hit_wins():
    """moats is attributed by BOTH charlie-munger (rank 1) and owner-earnings
    (rank 2) — the stamp is the highest-ranked hit's."""
    outcomes = project_key_outcomes_v2(
        keys_emitted=("moats",),
        rendered_expressions=("moats",),
        unresolved_expressions=(),
        search=_summary(),
    )
    assert outcomes[0].matched_first_run_id == "run-1"
    assert outcomes[0].match_recency == "cohort"


def test_projection_truncated_expression_aligned_by_index():
    """keys_emitted carries the ORIGINAL; hits/unresolved name the RENDERED
    form — the projection aligns by index, never by string equality."""
    outcomes = project_key_outcomes_v2(
        keys_emitted=("a-very-long-expression-original",),
        rendered_expressions=("a-very-long-expr",),
        unresolved_expressions=(),
        search=_summary(hits=(SearchHitSummary(
            slug="charlie-munger", first_run_id="run-1", match_recency="cohort",
            matched_expressions=("a-very-long-expr",)),)),
    )
    assert outcomes[0].expression == "a-very-long-expression-original"
    assert outcomes[0].status == "matched"


def test_projection_cap_exhausted_possible_annotation():
    """The controller-level cap flag projects onto every unresolved expression."""
    at_cap = _summary(hits=tuple(
        SearchHitSummary(slug=f"hit-{i}", first_run_id="run-1",
                         match_recency="cohort", matched_expressions=())
        for i in range(MAX_RESULTS)))
    outcomes = project_key_outcomes_v2(
        keys_emitted=("missing",),
        rendered_expressions=("missing",),
        unresolved_expressions=("missing",),
        search=at_cap,
    )
    assert outcomes[0].annotation == "cap_exhausted_possible"


def test_projection_unattributed_possible_annotation():
    outcomes = project_key_outcomes_v2(
        keys_emitted=("missing",),
        rendered_expressions=("missing",),
        unresolved_expressions=("missing",),
        search=_summary(unattributed_hit_count=2),
    )
    assert outcomes[0].annotation == "unattributed_possible"


def test_projection_cap_takes_precedence_over_unattributed():
    """Both controller flags on ⇒ cap_exhausted_possible wins: an exhausted cap
    explains EVERY unresolved expression; lost attribution only possibly does.
    (Precedence not fixed by the blueprint — pinned here.)"""
    at_cap_and_unattributed = _summary(
        unattributed_hit_count=1,
        hits=tuple(
            SearchHitSummary(slug=f"hit-{i}", first_run_id="run-1",
                             match_recency="cohort", matched_expressions=())
            for i in range(MAX_RESULTS)))
    outcomes = project_key_outcomes_v2(
        keys_emitted=("missing",),
        rendered_expressions=("missing",),
        unresolved_expressions=("missing",),
        search=at_cap_and_unattributed,
    )
    assert outcomes[0].annotation == "cap_exhausted_possible"


def test_projection_fail_closed_on_partition_violation():
    """A6: an expression in NEITHER the unresolved set NOR any hit's attribution
    would be silently lost — the projection refuses rather than guess."""
    with pytest.raises(ContextRecordError, match="partition"):
        project_key_outcomes_v2(
            keys_emitted=("ghost",),
            rendered_expressions=("ghost",),
            unresolved_expressions=(),
            search=_summary(hits=()),
        )


def test_projection_rejects_misaligned_rendered_forms():
    with pytest.raises(ContextRecordError):
        project_key_outcomes_v2(
            keys_emitted=("a", "b"),
            rendered_expressions=("a",),
            unresolved_expressions=(),
            search=_summary(),
        )


# ---------- round-trip: factory -> write -> parse ----------

def test_v2_round_trip_factory_write_parse(tmp_path):
    rec = build_context_record_v2(run_id="run-1", status="complete", telemetry=_telemetry_v2())
    path = write_context_record_v2(rec, tmp_path)
    assert path is not None
    assert path == (tmp_path / "runs" / "run-1" / "context"
                    / f"{safe_source_id(SOURCE_ID)}.json")
    on_disk = json.loads(path.read_text("utf-8"))
    assert on_disk == rec.to_dict()
    parsed = parse_context_record_v2(on_disk)
    assert parsed == rec
    # through real JSON bytes too (tuple/list normalization is the parser's job)
    parsed2 = parse_context_record_v2(json.loads(json.dumps(on_disk)))
    assert parsed2 == rec


def test_v2_round_trip_context_failed(tmp_path):
    rec = build_context_record_v2(
        run_id="run-1", status="context_failed", failure_input=_failure_input_v2())
    path = write_context_record_v2(rec, tmp_path)
    assert path is not None
    assert parse_context_record_v2(json.loads(path.read_text("utf-8"))) == rec


def test_v2_writer_warn_only_on_failure(tmp_path, monkeypatch, caplog):
    """The V1 writer's convention: the record is audit evidence — a write
    failure warns and never raises into the source outcome."""
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(context_record, "atomic_write_json", _boom)
    rec = build_context_record_v2(run_id="run-1", status="complete", telemetry=_telemetry_v2())
    with caplog.at_level(logging.WARNING, logger="compiler.context_record"):
        assert write_context_record_v2(rec, tmp_path) is None
    assert "context record write failed" in caplog.text


# ---------- strict parser rejections ----------

@pytest.mark.parametrize("version", [None, 1, "2", True, 2.0, 3])
def test_v2_parse_rejects_missing_or_unsupported_schema_version(version):
    payload = _complete_dict()
    if version is None:
        del payload["schema_version"]
    else:
        payload["schema_version"] = version
    with pytest.raises(ContextRecordError, match="schema_version"):
        parse_context_record_v2(payload)


@pytest.mark.parametrize("bad_search", [
    "nope",
    {"status": "completed"},  # nearly everything missing
])
def test_v2_parse_rejects_malformed_search_section(bad_search):
    payload = _complete_dict()
    payload["search"] = bad_search
    with pytest.raises(ContextRecordError, match="search"):
        parse_context_record_v2(payload)


def test_v2_parse_rejects_bad_search_status_enum():
    payload = _complete_dict()
    payload["search"]["status"] = "half_done"
    with pytest.raises(ContextRecordError, match="search.status"):
        parse_context_record_v2(payload)


def test_v2_parse_rejects_bad_hit_recency():
    payload = _complete_dict()
    payload["search"]["hits"][0]["match_recency"] = "ancient"
    with pytest.raises(ContextRecordError, match="match_recency"):
        parse_context_record_v2(payload)


@pytest.mark.parametrize("outcome,match", [
    # unknown annotation — the vocabulary is CLOSED (B11)
    ({"expression": "management", "status": "unresolved", "annotation": "maybe",
      "matched_first_run_id": None, "match_recency": None}, "annotation"),
    # annotation on a clean matched — must be null
    ({"expression": "moats", "status": "matched", "annotation": "no_match",
      "matched_first_run_id": "run-1", "match_recency": "cohort"}, "annotation"),
    # unresolved without an annotation — required on unresolved
    ({"expression": "management", "status": "unresolved", "annotation": None,
      "matched_first_run_id": None, "match_recency": None}, "annotation"),
    # unresolved carrying provenance
    ({"expression": "management", "status": "unresolved", "annotation": "no_match",
      "matched_first_run_id": "run-1", "match_recency": None}, "unresolved"),
    # matched without its recency
    ({"expression": "moats", "status": "matched", "annotation": None,
      "matched_first_run_id": "run-1", "match_recency": None}, "match_recency"),
    # stamp/recency mismatch: non-null stamp implies a KNOWN recency
    ({"expression": "moats", "status": "matched", "annotation": None,
      "matched_first_run_id": "run-1", "match_recency": "age_unknown"}, "match_recency"),
    # empty persisted stamp rejects (normalization is upstream, never the parser's)
    ({"expression": "moats", "status": "matched", "annotation": None,
      "matched_first_run_id": "", "match_recency": "age_unknown"}, "matched_first_run_id"),
])
def test_v2_parse_enforces_closed_annotation_vocabulary(outcome, match):
    payload = _complete_dict()
    payload["key_outcomes"][1] = outcome
    # keep the 1:1 alignment honest for the cases replacing outcome 1
    payload["key_outcomes"][1]["expression"] = payload["keys_emitted"][1]
    with pytest.raises(ContextRecordError, match=match):
        parse_context_record_v2(payload)


def test_v1_and_v2_vocabularies_cannot_mix():
    """A19/B11: a V1-shaped outcome in a V2 record rejects, a V2-shaped outcome
    in a V1 record rejects, and each parser refuses the other's version stamp."""
    v2_payload = _complete_dict()
    v2_payload["key_outcomes"][0] = {
        "key": "moats", "disposition": "resolved_t2_seed",
        "resolved": "moats", "target_first_run_id": "r0"}
    with pytest.raises(ContextRecordError):
        parse_context_record_v2(v2_payload)

    # A hand-built V1 payload (the V1 factory is retired read-only, §7 row 5).
    v1_payload = {
        "schema_version": 1, "run_id": "run-1", "source_id": SOURCE_ID,
        "status": "context_failed", "configured_t2_mode": "structured",
        "effective_t2_strategy": "structured_keys", "keys_emitted": ["moats"],
        "key_outcomes": [],
        "t1": {"candidates": 0, "delivered": 0, "slugs": []},
        "t2": {"candidates": 0, "delivered": 0, "slugs": []},
        "t3": {"candidates": 0, "delivered": 0, "slugs": []},
        "candidate_universe_size": None, "domain_scope": "value-investing",
        "cold_start": None, "max_hops": None, "page_cap": 50,
    }
    with pytest.raises(ContextRecordError):
        parse_context_record_v1(v2_payload)  # version 2 through the V1 parser
    v2_as_v1 = {**v1_payload, "schema_version": 1,
                "key_outcomes": [{"expression": "moats", "status": "matched",
                                  "annotation": None, "matched_first_run_id": "r0",
                                  "match_recency": "cohort"}]}
    with pytest.raises(ContextRecordError):
        parse_context_record_v1(v2_as_v1)


# ---------- status invariants, both sides ----------

@pytest.mark.parametrize("field_name,bad", [
    ("candidate_universe_size", None),
    ("candidate_universe_size", -1),
    ("cold_start", None),
    ("cold_start", 1),
])
def test_v2_parse_rejects_complete_with_null_or_bad_observables(field_name, bad):
    payload = _complete_dict()
    payload[field_name] = bad
    with pytest.raises(ContextRecordError, match=field_name):
        parse_context_record_v2(payload)


def test_v2_parse_rejects_context_failed_with_observables_or_outcomes():
    payload = build_context_record_v2(
        run_id="run-1", status="context_failed",
        failure_input=_failure_input_v2()).to_dict()
    for field_name, bad in [("candidate_universe_size", 7), ("cold_start", True)]:
        broken = {**payload, field_name: bad}
        with pytest.raises(ContextRecordError, match=field_name):
            parse_context_record_v2(broken)
    broken = json.loads(json.dumps(payload))
    broken["key_outcomes"] = [{"expression": "moats", "status": "matched", "annotation": None,
                               "matched_first_run_id": "r0", "match_recency": "cohort"}]
    with pytest.raises(ContextRecordError, match="outcomes"):
        parse_context_record_v2(broken)


def test_v2_parse_rejects_complete_outcomes_not_aligned_with_keys():
    payload = _complete_dict()
    payload["key_outcomes"] = payload["key_outcomes"][:1]
    with pytest.raises(ContextRecordError, match="1:1"):
        parse_context_record_v2(payload)
    payload = _complete_dict()
    payload["key_outcomes"] = list(reversed(payload["key_outcomes"]))
    with pytest.raises(ContextRecordError, match="1:1"):
        parse_context_record_v2(payload)
