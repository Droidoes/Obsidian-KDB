"""Tests for context_record — factory state invariants + strict v1 parser
(Task #122 §1). Rejects never coerce; both status-invariant sides enforced.
Empty-stamp normalization lives at the resolver's classifier (test_queries_context)
— the parser only ever sees the normalized form and REJECTS an empty stamp."""
from __future__ import annotations

import json

import pytest

from common.types import ContextTelemetry, KeyOutcome, TierRecord
from compiler.context_record import (
    CONTEXT_RECORD_SCHEMA_VERSION,
    ContextFailureInput,
    ContextRecordError,
    ContextRecordV1,
    build_context_record_v1,
    parse_context_record_v1,
)


# ---------- fixtures: valid payloads ----------

def _telemetry() -> ContextTelemetry:
    return ContextTelemetry(
        source_id="KDB/raw/s.md",
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=["k1", "k2"],
        key_outcomes=[
            KeyOutcome("k1", "resolved_t2_seed", "k1-canon", "r0"),
            KeyOutcome("k2", "unresolved", None, None),
        ],
        t1=TierRecord(candidates=1, delivered=1, slugs=["t1-page"]),
        t2=TierRecord(candidates=2, delivered=1, slugs=["t2-page"]),
        t3=TierRecord(candidates=4, delivered=0, slugs=[]),
        candidate_universe_size=7,
        domain_scope="value-investing",
        cold_start=False,
        max_hops=1,
        page_cap=50,
    )


def _failure_input() -> ContextFailureInput:
    return ContextFailureInput(
        source_id="KDB/raw/s.md",
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=["k1", "k2"],
        domain_scope="value-investing",
        page_cap=50,
    )


def _complete_dict() -> dict:
    return build_context_record_v1(
        run_id="run-1", status="complete", telemetry=_telemetry()).to_dict()


def _failed_dict() -> dict:
    return build_context_record_v1(
        run_id="run-1", status="context_failed",
        failure_input=_failure_input()).to_dict()


# ---------- factory: valid combos ----------

def test_factory_complete_maps_telemetry_fields():
    rec = build_context_record_v1(run_id="run-1", status="complete", telemetry=_telemetry())
    assert isinstance(rec, ContextRecordV1)
    assert rec.schema_version == CONTEXT_RECORD_SCHEMA_VERSION == 1
    assert rec.run_id == "run-1"
    assert rec.status == "complete"
    assert rec.source_id == "KDB/raw/s.md"
    assert rec.key_outcomes == _telemetry().key_outcomes
    assert rec.candidate_universe_size == 7
    assert rec.cold_start is False
    assert rec.max_hops == 1
    assert rec.page_cap == 50


def test_factory_context_failed_frozen_shape():
    rec = build_context_record_v1(
        run_id="run-1", status="context_failed", failure_input=_failure_input())
    assert rec.status == "context_failed"
    assert rec.keys_emitted == ["k1", "k2"]          # retained from frontmatter
    assert rec.key_outcomes == []
    zero = TierRecord(0, 0, [])
    assert rec.t1 == rec.t2 == rec.t3 == zero
    assert rec.candidate_universe_size is None
    assert rec.cold_start is None
    assert rec.max_hops is None
    assert rec.domain_scope == "value-investing"
    assert rec.page_cap == 50


# ---------- factory: invalid combos raise ----------

def test_factory_complete_requires_telemetry():
    with pytest.raises(ContextRecordError):
        build_context_record_v1(run_id="r", status="complete")


def test_factory_complete_forbids_failure_input():
    with pytest.raises(ContextRecordError):
        build_context_record_v1(run_id="r", status="complete",
                                telemetry=_telemetry(), failure_input=_failure_input())


def test_factory_complete_requires_non_null_observables():
    bad = ContextTelemetry(**{**_telemetry().__dict__, "cold_start": None})  # type: ignore[arg-type]
    with pytest.raises(ContextRecordError, match="observables"):
        build_context_record_v1(run_id="r", status="complete", telemetry=bad)


def test_factory_context_failed_requires_failure_input():
    with pytest.raises(ContextRecordError):
        build_context_record_v1(run_id="r", status="context_failed")


def test_factory_context_failed_forbids_telemetry():
    with pytest.raises(ContextRecordError):
        build_context_record_v1(run_id="r", status="context_failed",
                                telemetry=_telemetry(), failure_input=_failure_input())


def test_factory_unknown_status_raises():
    with pytest.raises(ContextRecordError):
        build_context_record_v1(run_id="r", status="weird")  # type: ignore[arg-type]


# ---------- serialization round-trip ----------

@pytest.mark.parametrize("payload_fn", [_complete_dict, _failed_dict])
def test_round_trip_dict_json_parse(payload_fn):
    rec = parse_context_record_v1(payload_fn())
    assert isinstance(rec, ContextRecordV1)
    assert rec.to_dict() == payload_fn()
    # through actual JSON bytes too (to_dict is the only serialization path)
    rec2 = parse_context_record_v1(json.loads(json.dumps(payload_fn())))
    assert rec2 == rec


# ---------- strict parser rejections ----------

def test_parse_rejects_non_dict():
    with pytest.raises(ContextRecordError):
        parse_context_record_v1(["not", "a", "dict"])  # type: ignore[arg-type]


@pytest.mark.parametrize("version", [None, 2, "1", True, 1.0])
def test_parse_rejects_missing_or_unsupported_schema_version(version):
    payload = _complete_dict()
    if version is None:
        del payload["schema_version"]
    else:
        payload["schema_version"] = version
    with pytest.raises(ContextRecordError, match="schema_version"):
        parse_context_record_v1(payload)


@pytest.mark.parametrize("field_name", ["run_id", "source_id"])
@pytest.mark.parametrize("bad", [None, "", 7, ["x"]])
def test_parse_rejects_missing_or_wrong_typed_ids(field_name, bad):
    payload = _complete_dict()
    payload[field_name] = bad
    with pytest.raises(ContextRecordError, match=field_name):
        parse_context_record_v1(payload)


@pytest.mark.parametrize("field_name,bad", [
    ("status", "done"),
    ("configured_t2_mode", "turbo"),
    ("effective_t2_strategy", "best_effort"),
    ("status", None),
])
def test_parse_rejects_wrong_enums(field_name, bad):
    payload = _complete_dict()
    payload[field_name] = bad
    with pytest.raises(ContextRecordError, match=field_name):
        parse_context_record_v1(payload)


@pytest.mark.parametrize("bad", ["k1", ["k1", 2], None])
def test_parse_rejects_wrong_typed_keys_emitted(bad):
    payload = _complete_dict()
    payload["keys_emitted"] = bad
    with pytest.raises(ContextRecordError, match="keys_emitted"):
        parse_context_record_v1(payload)


def test_parse_rejects_non_list_outcomes():
    payload = _complete_dict()
    payload["key_outcomes"] = "nope"
    with pytest.raises(ContextRecordError, match="key_outcomes"):
        parse_context_record_v1(payload)


def test_parse_rejects_complete_outcomes_not_aligned_with_keys():
    # count mismatch (1 outcome for 2 keys)
    payload = _complete_dict()
    payload["key_outcomes"] = payload["key_outcomes"][:1]
    with pytest.raises(ContextRecordError, match="1:1"):
        parse_context_record_v1(payload)
    # order/key mismatch (positional alignment, emission order)
    payload = _complete_dict()
    payload["key_outcomes"] = list(reversed(payload["key_outcomes"]))
    with pytest.raises(ContextRecordError, match="1:1"):
        parse_context_record_v1(payload)


def test_parse_rejects_unresolved_outcome_with_target():
    payload = _complete_dict()
    payload["key_outcomes"][1] = {"key": "k2", "disposition": "unresolved",
                                  "resolved": "k2-canon", "target_first_run_id": None}
    with pytest.raises(ContextRecordError, match="unresolved"):
        parse_context_record_v1(payload)


def test_parse_rejects_resolved_outcome_without_target():
    payload = _complete_dict()
    payload["key_outcomes"][0] = {"key": "k1", "disposition": "resolved_t2_seed",
                                  "resolved": None, "target_first_run_id": None}
    with pytest.raises(ContextRecordError, match="without a resolved target"):
        parse_context_record_v1(payload)


@pytest.mark.parametrize("bad_stamp", ["", 7, ["r0"]])
def test_parse_rejects_bad_target_first_run_id(bad_stamp):
    """target_first_run_id must be null or a NON-EMPTY str — an empty persisted
    stamp rejects (normalization is the classifier's job, never the parser's)."""
    payload = _complete_dict()
    payload["key_outcomes"][0]["target_first_run_id"] = bad_stamp
    with pytest.raises(ContextRecordError, match="target_first_run_id"):
        parse_context_record_v1(payload)


def test_parse_accepts_none_target_first_run_id():
    """The classifier-normalized form (None) parses fine; a resolved hit with a
    missing stamp is the legal age_unknown case."""
    payload = _complete_dict()
    payload["key_outcomes"][0]["target_first_run_id"] = None
    rec = parse_context_record_v1(payload)
    assert rec.key_outcomes[0].target_first_run_id is None


@pytest.mark.parametrize("tier_name", ["t1", "t2", "t3"])
@pytest.mark.parametrize("bad_tier", [
    {"candidates": -1, "delivered": 0, "slugs": []},          # negative count
    {"candidates": True, "delivered": 0, "slugs": []},        # bool-as-int
    {"candidates": 1, "delivered": -1, "slugs": []},          # negative delivered
    {"candidates": 2, "delivered": 1, "slugs": ["a", "b"]},   # delivered != len(slugs)
    {"candidates": 0, "delivered": 1, "slugs": ["a"]},        # delivered > candidates
    "not-a-dict",
])
def test_parse_rejects_bad_tiers(tier_name, bad_tier):
    payload = _complete_dict()
    payload[tier_name] = bad_tier
    with pytest.raises(ContextRecordError):
        parse_context_record_v1(payload)


def test_parse_rejects_sum_delivered_over_page_cap():
    payload = _complete_dict()
    payload["t1"] = {"candidates": 40, "delivered": 30,
                     "slugs": [f"p{i}" for i in range(30)]}
    payload["t2"] = {"candidates": 40, "delivered": 30,
                     "slugs": [f"q{i}" for i in range(30)]}
    # t1+t2 delivered = 60 > page_cap=50
    with pytest.raises(ContextRecordError, match="page_cap"):
        parse_context_record_v1(payload)


@pytest.mark.parametrize("bad", [-1, True, "50"])
def test_parse_rejects_bad_page_cap(bad):
    payload = _complete_dict()
    payload["page_cap"] = bad
    with pytest.raises(ContextRecordError, match="page_cap"):
        parse_context_record_v1(payload)


def test_parse_rejects_wrong_typed_domain_scope():
    payload = _complete_dict()
    payload["domain_scope"] = 7
    with pytest.raises(ContextRecordError, match="domain_scope"):
        parse_context_record_v1(payload)


# ---------- both status-invariant sides ----------

@pytest.mark.parametrize("field_name,bad", [
    ("candidate_universe_size", None),
    ("candidate_universe_size", -1),
    ("cold_start", None),
    ("cold_start", 1),                    # int is not bool
    ("max_hops", None),
    ("max_hops", -2),
])
def test_parse_rejects_complete_with_null_or_bad_observables(field_name, bad):
    """Side 1: a `complete` record whose observables are null/mistyped rejects."""
    payload = _complete_dict()
    payload[field_name] = bad
    with pytest.raises(ContextRecordError, match=field_name):
        parse_context_record_v1(payload)


@pytest.mark.parametrize("field_name,bad", [
    ("candidate_universe_size", 7),
    ("cold_start", True),
    ("max_hops", 1),
])
def test_parse_rejects_context_failed_with_non_null_observables(field_name, bad):
    """Side 2: a `context_failed` record carrying observables rejects."""
    payload = _failed_dict()
    payload[field_name] = bad
    with pytest.raises(ContextRecordError, match=field_name):
        parse_context_record_v1(payload)


def test_parse_rejects_context_failed_with_outcomes():
    payload = _failed_dict()
    payload["key_outcomes"] = [
        {"key": "k1", "disposition": "unresolved", "resolved": None,
         "target_first_run_id": None},
    ]
    with pytest.raises(ContextRecordError, match="outcomes"):
        parse_context_record_v1(payload)


def test_parse_rejects_context_failed_with_non_zero_tier():
    payload = _failed_dict()
    payload["t2"] = {"candidates": 1, "delivered": 0, "slugs": []}
    with pytest.raises(ContextRecordError, match="t2"):
        parse_context_record_v1(payload)
