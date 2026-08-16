"""Tests for emit_kpis §5 — load_context_records + reconcile_context_records
(Task #122). Filesystem loading with strict parse (rejections travel as
issues, never as records) and the pinned reconciliation order."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.types import TierRecord
from kdb_graph_compiler.context_record import (
    ContextRecordV1,
    ContextRecordV2,
    KeyOutcomeV1,
    KeyOutcomeV2,
)
from kdb_graph_orchestrator.emit_kpis import (
    load_context_records,
    reconcile_context_records,
)


# ---------- payload builders ----------
# #123 P3a.2b: the V1 factory is retired (parse-only history) — V1 payloads
# are built directly here.

def _complete_payload(source_id: str, run_id: str = "run-1") -> dict:
    return ContextRecordV1(
        schema_version=1,
        run_id=run_id,
        source_id=source_id,
        status="complete",
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=["k1"],
        key_outcomes=[KeyOutcomeV1("k1", "resolved_t2_seed", "k1", "r0")],
        t1=TierRecord(0, 0, []),
        t2=TierRecord(1, 1, ["k1"]),
        t3=TierRecord(0, 0, []),
        candidate_universe_size=3,
        domain_scope="value-investing",
        cold_start=True,
        max_hops=2,
        page_cap=50,
    ).to_dict()


def _write_record(context_dir: Path, name: str, payload: dict) -> Path:
    context_dir.mkdir(parents=True, exist_ok=True)
    p = context_dir / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _failed_payload(source_id: str, run_id: str = "run-1") -> dict:
    zero = TierRecord(0, 0, [])
    return ContextRecordV1(
        schema_version=1,
        run_id=run_id,
        source_id=source_id,
        status="context_failed",
        configured_t2_mode="structured",
        effective_t2_strategy="structured_keys",
        keys_emitted=["k1"],
        key_outcomes=[],
        t1=zero,
        t2=zero,
        t3=zero,
        candidate_universe_size=None,
        domain_scope=None,
        cold_start=None,
        max_hops=None,
        page_cap=50,
    ).to_dict()


def _v2_payload(source_id: str, run_id: str = "run-1") -> dict:
    """One minimal complete V2 payload (search=None — no search ran)."""
    return ContextRecordV2(
        schema_version=2,
        run_id=run_id,
        source_id=source_id,
        status="complete",
        keys_emitted=["k1"],
        key_outcomes=[KeyOutcomeV2(
            expression="k1", status="matched", annotation=None,
            matched_first_run_id="r0", match_recency="pre_run")],
        t1=TierRecord(0, 0, []),
        t2=TierRecord(1, 1, ["k1"]),
        t3=TierRecord(0, 0, []),
        candidate_universe_size=3,
        domain_scope="value-investing",
        cold_start=False,
        page_cap=50,
        search=None,
    ).to_dict()


# ---------- load_context_records ----------

def test_load_reads_all_valid_records_sorted(tmp_path):
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "b.json", _complete_payload("src-b"))
    _write_record(ctx_dir, "a.json", _complete_payload("src-a"))
    result = load_context_records(ctx_dir, "run-1")
    assert [r.source_id for r in result.records] == ["src-a", "src-b"]
    assert result.issues == []


def test_load_missing_dir_is_empty(tmp_path):
    result = load_context_records(tmp_path / "nope", "run-1")
    assert result.records == [] and result.issues == []


def test_load_malformed_becomes_issue_no_record(tmp_path):
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "good.json", _complete_payload("src-a"))
    bad = ctx_dir / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    strict = _write_record(ctx_dir, "strict.json", {"schema_version": 99})
    result = load_context_records(ctx_dir, "run-1")
    assert [r.source_id for r in result.records] == ["src-a"]
    reasons = {(i.path, i.reason) for i in result.issues}
    assert reasons == {(str(bad), "malformed"), (str(strict), "malformed")}
    assert all(i.detail for i in result.issues)


def test_load_v2_record_dispatches_to_v2_parser(tmp_path):
    """§4.5 dispatching loader: a schema_version=2 file parses via the V2
    reader and lands as a ContextRecordV2 — zero issues."""
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "v2.json", _v2_payload("src-v2"))
    result = load_context_records(ctx_dir, "run-1")
    assert result.issues == []
    assert len(result.records) == 1
    rec = result.records[0]
    assert isinstance(rec, ContextRecordV2)
    assert rec.source_id == "src-v2"
    assert rec.search is None


def test_load_mixed_v1_v2_dir_loads_both(tmp_path):
    """A mixed run dir (V1 history + V2 current) loads both versions through
    one loader, sorted by source_id."""
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "b.json", _v2_payload("src-b"))
    _write_record(ctx_dir, "a.json", _complete_payload("src-a"))
    result = load_context_records(ctx_dir, "run-1")
    assert result.issues == []
    assert [r.source_id for r in result.records] == ["src-a", "src-b"]
    assert isinstance(result.records[0], ContextRecordV1)
    assert isinstance(result.records[1], ContextRecordV2)


def test_load_unknown_schema_version_is_malformed(tmp_path):
    """The dispatcher rejects unknown versions (never coerces, never guesses)."""
    ctx_dir = tmp_path / "context"
    bad = _write_record(ctx_dir, "v3.json", {"schema_version": 3})
    result = load_context_records(ctx_dir, "run-1")
    assert result.records == []
    assert [(i.path, i.reason) for i in result.issues] == [
        (str(bad), "malformed")]


def test_load_wrong_run_becomes_issue_no_record(tmp_path):
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "good.json", _complete_payload("src-a"))
    stale = _write_record(ctx_dir, "stale.json", _complete_payload("src-b", run_id="run-0"))
    result = load_context_records(ctx_dir, "run-1")
    assert [r.source_id for r in result.records] == ["src-a"]
    assert len(result.issues) == 1
    assert result.issues[0].reason == "wrong_run"
    assert result.issues[0].path == str(stale)
    assert "run-0" in result.issues[0].detail


def test_load_context_failed_records_parse(tmp_path):
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "f.json", _failed_payload("src-x"))
    result = load_context_records(ctx_dir, "run-1")
    assert [r.status for r in result.records] == ["context_failed"]


# ---------- reconcile_context_records ----------

def _load_result(tmp_path, payloads: dict[str, dict]) -> object:
    ctx_dir = tmp_path / "context"
    for name, payload in payloads.items():
        _write_record(ctx_dir, name, payload)
    return load_context_records(ctx_dir, "run-1")


def test_reconcile_all_matched_complete(tmp_path):
    lr = _load_result(tmp_path, {
        "a.json": _complete_payload("src-a"),
        "b.json": _complete_payload("src-b"),
    })
    ev = reconcile_context_records(lr, {"src-a", "src-b"}, 2)
    assert ev.complete is True
    assert ev.matched_ids == {"src-a", "src-b"}
    assert ev.coverage == 1.0
    assert ev.integrity.missing == 0
    assert ev.integrity.expected_count_mismatch is False


def test_reconcile_missing_record(tmp_path):
    lr = _load_result(tmp_path, {"a.json": _complete_payload("src-a")})
    ev = reconcile_context_records(lr, {"src-a", "src-b"}, 2)
    assert ev.complete is False
    assert ev.coverage == 0.5
    assert ev.integrity.missing == 1


def test_reconcile_duplicate_record(tmp_path):
    lr = _load_result(tmp_path, {
        "a.json": _complete_payload("src-a"),
        "a2.json": _complete_payload("src-a"),
    })
    ev = reconcile_context_records(lr, {"src-a"}, 1)
    assert ev.complete is False
    assert ev.coverage == 1.0                     # coverage counts presence
    assert ev.integrity.duplicate == 1            # one excess record


def test_reconcile_unexpected_record(tmp_path):
    lr = _load_result(tmp_path, {
        "a.json": _complete_payload("src-a"),
        "x.json": _complete_payload("src-x"),
    })
    ev = reconcile_context_records(lr, {"src-a"}, 1)
    assert ev.complete is False
    assert ev.coverage == 1.0                     # 1.0 WITH an extra record
    assert ev.integrity.unexpected == 1


def test_reconcile_malformed_and_wrong_run_counted(tmp_path):
    ctx_dir = tmp_path / "context"
    _write_record(ctx_dir, "a.json", _complete_payload("src-a"))
    (ctx_dir / "bad.json").write_text("{oops", encoding="utf-8")
    _write_record(ctx_dir, "stale.json", _complete_payload("src-b", run_id="run-0"))
    lr = load_context_records(ctx_dir, "run-1")
    ev = reconcile_context_records(lr, {"src-a"}, 1)
    assert ev.complete is False
    assert ev.integrity.malformed == 1
    assert ev.integrity.wrong_run == 1


def test_reconcile_expected_count_mismatch_flags_expected_ids_win(tmp_path):
    """header.p2_attempted disagrees with the sidecar-derived expected set:
    the mismatch flags integrity; reconciliation still runs on expected_ids."""
    lr = _load_result(tmp_path, {"a.json": _complete_payload("src-a")})
    ev = reconcile_context_records(lr, {"src-a"}, 5)   # header claims 5
    assert ev.complete is False
    assert ev.integrity.expected_count_mismatch is True
    assert ev.matched_ids == {"src-a"}                  # expected_ids win
    assert ev.coverage == 1.0


def test_reconcile_zero_expected(tmp_path):
    lr = _load_result(tmp_path, {})
    ev = reconcile_context_records(lr, set(), 0)
    assert ev.complete is False                       # never vacuous
    assert ev.coverage is None
    assert ev.matched_ids == set()
    assert ev.integrity.missing == 0
    assert ev.integrity.expected_count_mismatch is False
