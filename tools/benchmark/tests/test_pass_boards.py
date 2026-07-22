"""Tests for tools.benchmark.pass_boards (Task #117, spec v0.3.1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark.pass_boards import (
    SRC_FALLBACK,
    SRC_PARTIAL,
    SRC_RECOMPUTED,
    build_pass_board,
    effective_top_weights,
)


def _write_run(runs_root: Path, run_dir: str, *, model: str, provider: str = "prov",
               release: str = "", p1: int = 4, signal: int = 3, noise: int = 1,
               failed_p1: int = 0, pass2_records: int | None = None,
               cost_p1: float = 0.01, latency_ms_p1: int = 100,
               tokens_p1: int = 100,
               quarantine_p2: bool = False, graph: dict | None = None,
               skip_sidecar: int | None = None, malformed_p1: bool = False,
               dup_source: bool = False, no_run_state: bool = False):
    """Write measurements.json + run_state/ for one synthetic run.

    p1 sources: sidecars s0..s{p1-1} (dispositions come from the header
    counts; sidecars just need to exist and load). pass2 records default to
    `signal`.
    """
    d = runs_root / run_dir
    d.mkdir(parents=True, exist_ok=True)
    p2 = signal if pass2_records is None else pass2_records
    (d / "measurements.json").write_text(json.dumps({
        "header": {"run_id": run_dir, "provider": provider, "model": model,
                   "release_version": release, "corpus_fingerprint": "fp",
                   "pass1_prompt_version": "1", "pass2_prompt_version": "",
                   "scanned": p1, "to_compile": p1, "signal": signal,
                   "noise": noise, "p1_attempted": p1, "p2_attempted": signal},
        "processing": {"scored": {}, "diagnostic": {
            "quarantine_rate_pass1": 0.0, "latency_pass1": 111.0,
            "quarantine_rate_pass2": 0.0, "latency_pass2": 222.0}},
        "graph": {"scored": graph or {"entity_reuse": 0.1, "graph_connectivity": 0.2,
                                      "link_density": 2.0, "supports_density": 5.0},
                  "watched": {}, "diagnostic": {}},
    }))
    if no_run_state:
        return
    rs = d / "run_state"
    (rs / "pass1").mkdir(parents=True)
    (rs / "pass2").mkdir(parents=True)
    (rs / "measurement_header.json").write_text(json.dumps({
        "run_id": run_dir, "corpus_fingerprint": "fp", "pass1_prompt_version": "1",
        "pass2_prompt_version": "", "scanned": p1, "to_compile": p1,
        "signal": signal, "noise": noise, "p1_attempted": p1,
        "p2_attempted": signal}))
    n_sidecars = p1 if skip_sidecar is None else skip_sidecar
    for i in range(n_sidecars):
        sid = "src0.md" if (dup_source and i > 0) else f"src{i}.md"
        (rs / "pass1" / f"s{i}.json").write_text(json.dumps({
            "source_id": sid,
            "outcome": "enriched",
            "request": {"provider": provider, "model": model},
            "raw_response": {"final_status": "quarantined" if i < failed_p1 else "clean",
                             "call_count": 1, "total_input_tokens": tokens_p1,
                             "total_output_tokens": tokens_p1 // 2,
                             "total_latency_ms": latency_ms_p1},
            "parsed_envelope": {"prompt_version": "1"},
            "cost_usd": cost_p1,
        }))
    if malformed_p1:
        (rs / "pass1" / "broken.json").write_text("{not json")
    for i in range(p2):
        (rs / "pass2" / f"c{i}.json").write_text(json.dumps({
            "run_id": run_dir, "source_id": f"c{i}.md", "provider": provider,
            "model": model,
            "final_status": "quarantined" if (quarantine_p2 and i == 0) else "clean",
            "total_input_tokens": 200, "total_output_tokens": 100,
            "total_latency_ms": 300, "cost_usd": 0.30}))


class TestEffectiveWeights:
    def test_pass1_full_precision_pro_rata(self):
        w = effective_top_weights("pass1")
        assert w["quarantine_rate"] == pytest.approx(2 / 3)
        assert w["recovery_rate"] == pytest.approx(1 / 6)
        assert w["latency"] == pytest.approx(1 / 6)
        assert w["graph"] == 0.0
        assert sum(w.values()) == pytest.approx(1.0)

    def test_pass2_canonical(self):
        assert effective_top_weights("pass2") == {
            "quarantine_rate": 0.40, "recovery_rate": 0.10,
            "latency": 0.10, "graph": 0.40}


class TestRankedBoard:
    def test_pass1_board_scores_and_carries_raw_values(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", latency_ms_p1=100, cost_p1=0.01)
        _write_run(rr, "b-T1", model="b", latency_ms_p1=900, cost_p1=0.30)
        m2r = {"prov/a@unversioned": "a-T1", "prov/b@unversioned": "b-T1"}
        board = build_pass_board(m2r, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["board_scope"] == "pass1"
        assert len(board["ranking"]) == 2 and board["unranked"] == []
        rows = {r["model"]: r for r in board["ranking"]}
        a = rows["prov/a@unversioned"]
        assert a["rank"] == 1                       # lower latency wins (all else tied)
        assert a["graph_score"] is None             # graph inactive on pass-1
        assert a["measurement_source"] == SRC_RECOMPUTED
        assert a["raw_values"]["cost_usd_pass1"] == pytest.approx(4 * 0.01)
        assert a["raw_values"]["cost_unknown_calls_pass1"] == 0
        assert a["raw_values"]["latency_pass1"] is not None
        assert board["effective_top_weights"]["quarantine_rate"] == pytest.approx(2 / 3)

    def test_pass2_board_has_graph_score_and_coverage_columns(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", signal=3, noise=1)
        _write_run(rr, "b-T1", model="b", signal=2, noise=1, failed_p1=0)
        # b: p1=4, signal=2, noise=1 → p1_failed = 1; eligibility 2/4
        m2r = {"prov/a@unversioned": "a-T1", "prov/b@unversioned": "b-T1"}
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5, "supports_density": 0.5},
                "prov/b@unversioned": {"entity_reuse": 0.1, "graph_connectivity": 0.1,
                                       "link_density": 0.1, "supports_density": 0.1}}
        board = build_pass_board(m2r, rr, "pass2",
                                 graph_scored_by_model=gsbm, fallback_diag_by_model={})
        rows = {r["model"]: r for r in board["ranking"]}
        b = rows["prov/b@unversioned"]
        assert b["graph_score"] is not None
        assert b["raw_values"]["pass2_eligibility_rate"] == pytest.approx(2 / 4)
        assert b["raw_values"]["pass2_measurement_coverage"] == pytest.approx(1.0)
        assert b["raw_values"]["p1_noise"] == 1
        assert b["raw_values"]["p1_failed"] == 4 - 2 - 1
        a = rows["prov/a@unversioned"]
        assert a["raw_values"]["pass2_eligibility_rate"] == pytest.approx(3 / 4)

    def test_tied_models_share_competition_rank(self, tmp_path):
        """D-117-9: two identical leaders tie at rank 1; the next row SKIPS to
        rank 3 (competition ranking, not dense). Payload assertion here; the
        rendered-Markdown half lives in Task 5 (R7-F3)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")                    # tied leader
        _write_run(rr, "b-T1", model="b")                    # tied leader
        _write_run(rr, "c-T1", model="c", latency_ms_p1=900) # lower row
        m2r = {f"prov/{m}@unversioned": f"{m}-T1" for m in "abc"}
        board = build_pass_board(m2r, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert [r["rank"] for r in board["ranking"]] == [1, 1, 3]


class TestCompleteness:
    def test_missing_run_state_unranked_fallback(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", no_run_state=True)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={},
                                 fallback_diag_by_model={"prov/a@unversioned": {
                                     "quarantine_rate_pass1": 0.0,
                                     "latency_pass1": 111.0}})
        assert board["ranking"] == []
        u = board["unranked"][0]
        assert u["measurement_source"] == SRC_FALLBACK
        assert "recovery_rate" in u["missing_kpis"]
        assert u["raw_values"]["latency_pass1"] == 111.0

    def test_missing_pass1_sidecar_unranked(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", skip_sidecar=3)   # p1_attempted=4, only 3 sidecars
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert board["unranked"][0]["measurement_source"] == SRC_PARTIAL

    def test_malformed_sidecar_unranked(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", malformed_p1=True)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["unranked"][0]["measurement_source"] == SRC_PARTIAL

    def test_duplicate_source_id_unranked(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", dup_source=True)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["unranked"][0]["measurement_source"] == SRC_PARTIAL

    def test_short_pass2_records_unranked_on_pass2_only(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", pass2_records=2)   # signal=3, only 2 records
        m2r = {"prov/a@unversioned": "a-T1"}
        # all four graph KPIs present — the short record count is the ONLY
        # failure condition (R5-F2: not masked by missing graph evidence)
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5, "supports_density": 0.5}}
        b2 = build_pass_board(m2r, rr, "pass2", graph_scored_by_model=gsbm,
                              fallback_diag_by_model={})
        assert b2["ranking"] == [] and len(b2["unranked"]) == 1
        assert any("pass2_records" in e
                   for e in b2["unranked"][0]["completeness_errors"])
        b1 = build_pass_board(m2r, rr, "pass1", graph_scored_by_model={},
                              fallback_diag_by_model={})
        assert len(b1["ranking"]) == 1        # same row still ranks on pass-1

    def test_zero_token_pass1_unranked_despite_complete_counts(self, tmp_path):
        """Count-complete but zero-token pass → all rates None → unranked
        (never pro-rated on missing evidence, D-117-5e)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", tokens_p1=0)
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        u = board["unranked"][0]
        assert set(u["missing_kpis"]) == {"quarantine_rate", "recovery_rate", "latency"}
        assert u["completeness_errors"] == []

    def test_pass2_unranked_when_graph_kpi_absent(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5}}   # supports_density absent
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model=gsbm, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert "supports_density" in board["unranked"][0]["missing_kpis"]

    def test_pass2_unranked_when_graph_kpi_none(self, tmp_path):
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": None,
                                       "link_density": 0.5, "supports_density": 0.5}}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model=gsbm, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert "graph_connectivity" in board["unranked"][0]["missing_kpis"]

    def test_malformed_header_json_unranked_not_abort(self, tmp_path):
        """R5-F1: bad header JSON marks the row unranked; the board still builds."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        (rr / "a-T1" / "run_state" / "measurement_header.json").write_text("{not json")
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert board["unranked"][0]["completeness_errors"] == ["header_unparseable"]

    def test_structurally_invalid_header_unranked_not_abort(self, tmp_path):
        """R5-F1: valid JSON missing required header fields → TypeError caught
        the same way (row unranked, board builds)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        (rr / "a-T1" / "run_state" / "measurement_header.json").write_text(
            json.dumps({"run_id": "a-T1"}))       # missing required fields
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert board["unranked"][0]["completeness_errors"] == ["header_unparseable"]

    def test_wrong_typed_sidecar_field_unranked(self, tmp_path):
        """R6-F1: type-invalid telemetry counts as malformed → row unranked,
        board still builds (no mid-board TypeError)."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a")
        bad = rr / "a-T1" / "run_state" / "pass1" / "s0.json"
        d = json.loads(bad.read_text())
        d["raw_response"]["total_input_tokens"] = "100"      # string, not int
        bad.write_text(json.dumps(d))
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass1",
                                 graph_scored_by_model={}, fallback_diag_by_model={})
        assert board["ranking"] == []
        assert any("malformed" in e
                   for e in board["unranked"][0]["completeness_errors"])

    def test_fallback_row_carries_header_derived_evidence(self, tmp_path):
        """R6-F2: a no-run_state row on the Pass-2 board still shows the
        measurements-header dispositions + eligibility; coverage is None."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", no_run_state=True)
        hdr = {"p1_attempted": 4, "signal": 3, "noise": 1}
        gsbm = {"prov/a@unversioned": {"entity_reuse": 0.5, "graph_connectivity": 0.5,
                                       "link_density": 0.5, "supports_density": 0.5}}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model=gsbm,
                                 fallback_diag_by_model={},
                                 header_by_model={"prov/a@unversioned": hdr})
        u = board["unranked"][0]
        assert u["raw_values"]["pass2_eligibility_rate"] == pytest.approx(3 / 4)
        assert u["raw_values"]["pass2_measurement_coverage"] is None
        assert u["raw_values"]["p1_noise"] == 1
        assert u["raw_values"]["p1_failed"] == 0

    def test_fallback_wrong_typed_header_degrades_not_aborts(self, tmp_path):
        """R7-F1: a wrong-typed measurements header yields None dispositions —
        the board still builds; and all-zero valid fields give p1_failed=0."""
        rr = tmp_path / "runs"
        _write_run(rr, "a-T1", model="a", no_run_state=True)
        bad = {"p1_attempted": "4", "signal": 3, "noise": 1}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model={},
                                 fallback_diag_by_model={},
                                 header_by_model={"prov/a@unversioned": bad})
        u = board["unranked"][0]
        assert u["raw_values"]["pass2_eligibility_rate"] is None
        assert u["raw_values"]["p1_failed"] is None
        zero = {"p1_attempted": 0, "signal": 0, "noise": 0}
        board = build_pass_board({"prov/a@unversioned": "a-T1"}, rr, "pass2",
                                 graph_scored_by_model={},
                                 fallback_diag_by_model={},
                                 header_by_model={"prov/a@unversioned": zero})
        assert board["unranked"][0]["raw_values"]["p1_failed"] == 0
