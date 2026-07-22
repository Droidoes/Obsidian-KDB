"""Tests for the `score` subcommand of tools.benchmark.cli (Task #109).

2026-06-06 redesign: `score` is an incremental model **leaderboard** updater.
- A persistent leaderboard file maps {model_slug -> latest run_dir} + a ranking.
- Each invocation incorporates run dirs (one row per header.model, latest wins),
  re-reads every listed run's measurements.json live, Borda-ranks at equal weight.
- NO corpus_fingerprint gate (cross-run corpora are assumed to differ).
- Reset = delete the leaderboard file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark import cli


# ---------------------------------------------------------------------------
# Fixture helper — write a synthetic measurements.json keyed by header.model
# ---------------------------------------------------------------------------

def _make_measurements(
    *,
    run_dir: str,
    model: str,
    runs_root: Path,
    quarantine_rate: float | None = 0.0,
    recovery_rate: float | None = 0.0,
    latency: float | None = 1000.0,
    entity_reuse: float | None = 0.10,
    graph_connectivity: float | None = 0.2,
    link_density: float | None = 2.0,
    supports_density: float | None = 5.0,
    corpus_fingerprint: str = "fp",
    provider: str = "prov",
    release_version: str = "",
) -> None:
    """Write <runs_root>/<run_dir>/measurements.json with header.model = model.

    §6 structure: 3 processing scored + 4 graph scored KPIs.
    """
    d = runs_root / run_dir
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "header": {
            "run_id": run_dir,
            "provider": provider,
            "model": model,
            "release_version": release_version,
            "corpus_fingerprint": corpus_fingerprint,
            "pass1_prompt_version": "1.0",
            "pass2_prompt_version": "",
            "scanned": 10, "to_compile": 10, "signal": 8, "noise": 2,
            "p1_attempted": 10, "p2_attempted": 8,
        },
        "processing": {
            "scored": {
                "quarantine_rate": quarantine_rate,
                "recovery_rate": recovery_rate,
                "latency": latency,
            },
            "diagnostic": {"signal_noise_ratio": 0.8, "latency_pass1": 500.0,
                           "latency_pass2": 500.0},
        },
        "graph": {
            "scored": {
                "entity_reuse": entity_reuse,
                "graph_connectivity": graph_connectivity,
                "link_density": link_density,
                "supports_density": supports_density,
            },
            "watched": {"orphan_rate": 0.0, "entity_search_key_resolution": None},
            "diagnostic": {"belongs_to_coverage": 1.0, "domain_null_rate": 0.0,
                           "domain_breadth": 0.4},
        },
    }
    (d / "measurements.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load(lb: Path) -> dict:
    return json.loads(lb.read_text(encoding="utf-8"))


# Golden-fixture input (Task #117): single source for the pre-change golden
# generator and the byte-identical regression test (P-F6).
_GOLDEN_INPUT = {
    "ranking": [
        {"model": "prov/a@unversioned", "rank": 1, "composite": 80.0,
         "composite_pre_penalty": 82.0, "penalty": 2.0, "weakest_kpi": "latency",
         "graph_score": 1.0,
         "per_kpi_borda": {"quarantine_rate": 1.0, "recovery_rate": 1.0,
                           "latency": 0.5, "entity_reuse": 1.0,
                           "graph_connectivity": 1.0, "link_density": 1.0,
                           "supports_density": 1.0}},
        {"model": "prov/b@unversioned", "rank": 2, "composite": 40.0,
         "composite_pre_penalty": 50.0, "penalty": 10.0, "weakest_kpi": "graph",
         "graph_score": 0.0,
         "per_kpi_borda": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                           "latency": 1.0, "entity_reuse": 0.0,
                           "graph_connectivity": 0.0, "link_density": 0.0,
                           "supports_density": 0.0}},
    ],
    "scored_by_model": {
        "prov/a@unversioned": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                               "latency": 100.0, "entity_reuse": 0.1,
                               "graph_connectivity": 0.2, "link_density": 2.0,
                               "supports_density": 5.0},
        "prov/b@unversioned": {"quarantine_rate": 5.0, "recovery_rate": 3.0,
                               "latency": 900.0, "entity_reuse": 0.3,
                               "graph_connectivity": 0.1, "link_density": 1.0,
                               "supports_density": 3.0}},
    "diagnostics_by_model": {"prov/a@unversioned": {"signal_noise_ratio": 0.8},
                             "prov/b@unversioned": {"signal_noise_ratio": 0.7}},
    "top_weights": {"quarantine_rate": 0.4, "graph": 0.4,
                    "recovery_rate": 0.1, "latency": 0.1},
    "updated_at": "2026-07-22T00:00:00",
}


# ---------------------------------------------------------------------------
# Fresh leaderboard
# ---------------------------------------------------------------------------

class TestFreshLeaderboard:
    def test_creates_leaderboard_and_ranks_all_models(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        # identical processing KPIs (tie → 0.5 each), entity_reuse varies → decides
        _make_measurements(run_dir="model-a-T1", model="model-a", entity_reuse=0.10, runs_root=runs_root)
        _make_measurements(run_dir="model-b-T1", model="model-b", entity_reuse=0.30, runs_root=runs_root)
        _make_measurements(run_dir="model-c-T1", model="model-c", entity_reuse=0.20, runs_root=runs_root)

        rc = cli.main(["score", "model-a-T1", "model-b-T1", "model-c-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        assert lb.exists()

        data = _load(lb)
        # rows keyed on provider/model@release_version (#111 Phase 0)
        assert set(data["models"].keys()) == {
            "prov/model-a@unversioned", "prov/model-b@unversioned",
            "prov/model-c@unversioned",
        }
        # leaderboard stores POINTERS (run-dir strings), not KPI values
        assert data["models"]["prov/model-b@unversioned"] == "model-b-T1"
        assert all(isinstance(v, str) for v in data["models"].values())

        ranking = data["ranking"]
        assert len(ranking) == 3
        assert [r["rank"] for r in ranking] == [1, 2, 3]
        # entity_reuse is ↑ → highest reuse (model-b) ranks #1
        assert ranking[0]["model"] == "prov/model-b@unversioned"
        assert ranking[-1]["model"] == "prov/model-a@unversioned"

    def test_missing_run_dir_errors(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        rc = cli.main(["score", "does-not-exist",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc != 0
        assert not lb.exists()

    def test_writes_markdown_leaderboard(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root)
        _make_measurements(run_dir="model-b-T1", model="model-b",
                           entity_reuse=0.30, link_density=4.0, runs_root=runs_root)
        cli.main(["score", "model-a-T1", "model-b-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        md = lb.with_suffix(".md")
        assert md.exists(), "leaderboard.md should be written alongside the JSON"
        txt = md.read_text(encoding="utf-8")
        assert txt.startswith("# Model leaderboard")
        assert "| rank | model |" in txt          # markdown ranking table header
        assert "graph_score" in txt
        assert "## Raw measured values" in txt     # raw-values detail table
        assert "model-a" in txt and "model-b" in txt
        # raw values surface in the detail table (e.g. link_density 4.0 for model-b)
        assert "link_density" in txt


class TestCombinedGraphScore:
    """The §6 lesson encoded: the richness/coherence trio drives graph_score even
    when entity_reuse disagrees (the gemini-vs-deepseek case)."""

    def test_richness_trio_beats_lone_entity_reuse(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        # 'rich' wins connectivity + link + supports (3 of 4 graph KPIs, weight
        # 0.85) but loses entity_reuse; 'lean' is the sparse-but-high-reuse one.
        # Processing KPIs tied → graph decides.
        _make_measurements(run_dir="rich-T1", model="rich", runs_root=runs_root,
                           graph_connectivity=0.5, link_density=4.0,
                           supports_density=8.0, entity_reuse=0.05)
        _make_measurements(run_dir="lean-T1", model="lean", runs_root=runs_root,
                           graph_connectivity=0.1, link_density=1.0,
                           supports_density=3.0, entity_reuse=0.20)
        rc = cli.main(["score", "rich-T1", "lean-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        rows = {r["model"]: r for r in _load(lb)["ranking"]}
        rich, lean = "prov/rich@unversioned", "prov/lean@unversioned"
        # graph_score is reported, and the richer graph wins it despite lower reuse
        assert "graph_score" in rows[rich]
        assert rows[rich]["graph_score"] == pytest.approx(0.85)   # 0.35+0.30+0.20
        assert rows[lean]["graph_score"] == pytest.approx(0.15)   # reuse only
        # and 'rich' wins the overall composite (graph is 40%; processing tied)
        assert rows[rich]["rank"] == 1


# ---------------------------------------------------------------------------
# Incremental accumulation
# ---------------------------------------------------------------------------

class TestIncremental:
    def test_new_model_joins_existing_leaderboard(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root)
        _make_measurements(run_dir="model-b-T1", model="model-b", runs_root=runs_root)
        cli.main(["score", "model-a-T1", "model-b-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert set(_load(lb)["models"].keys()) == {
            "prov/model-a@unversioned", "prov/model-b@unversioned"}

        # incorporate a third model with just its run dir
        _make_measurements(run_dir="model-c-T1", model="model-c", runs_root=runs_root)
        rc = cli.main(["score", "model-c-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        data = _load(lb)
        assert set(data["models"].keys()) == {
            "prov/model-a@unversioned", "prov/model-b@unversioned",
            "prov/model-c@unversioned"}
        assert len(data["ranking"]) == 3

    def test_rerun_existing_model_replaces_its_run_dir(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-x-T1", model="model-x", entity_reuse=0.10, runs_root=runs_root)
        cli.main(["score", "model-x-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert _load(lb)["models"]["prov/model-x@unversioned"] == "model-x-T1"

        # a newer run of the SAME triple → replaces the pointer, still one row
        _make_measurements(run_dir="model-x-T2", model="model-x", entity_reuse=0.50, runs_root=runs_root)
        rc = cli.main(["score", "model-x-T2",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        data = _load(lb)
        assert list(data["models"].keys()) == ["prov/model-x@unversioned"]
        assert data["models"]["prov/model-x@unversioned"] == "model-x-T2"

    def test_two_runs_same_model_one_invocation_latest_wins(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-y-T1", model="model-y", runs_root=runs_root)
        _make_measurements(run_dir="model-y-T2", model="model-y", runs_root=runs_root)
        rc = cli.main(["score", "model-y-T1", "model-y-T2",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        data = _load(lb)
        assert list(data["models"].keys()) == ["prov/model-y@unversioned"]
        # lexically-greater run dir (T2) wins
        assert data["models"]["prov/model-y@unversioned"] == "model-y-T2"


# ---------------------------------------------------------------------------
# No fingerprint gate
# ---------------------------------------------------------------------------

class TestNoFingerprintGate:
    def test_different_fingerprints_still_rank(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a",
                           corpus_fingerprint="fingerprint-X", runs_root=runs_root)
        _make_measurements(run_dir="model-b-T1", model="model-b",
                           corpus_fingerprint="fingerprint-Y-DIFFERENT", runs_root=runs_root)
        rc = cli.main(["score", "model-a-T1", "model-b-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        # No gate → ranks both despite mismatched fingerprints
        assert rc == 0
        assert set(_load(lb)["models"].keys()) == {
            "prov/model-a@unversioned", "prov/model-b@unversioned"}


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_deleting_leaderboard_starts_fresh(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root)
        _make_measurements(run_dir="model-b-T1", model="model-b", runs_root=runs_root)
        cli.main(["score", "model-a-T1", "model-b-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert set(_load(lb)["models"].keys()) == {
            "prov/model-a@unversioned", "prov/model-b@unversioned"}

        lb.unlink()  # reset

        _make_measurements(run_dir="model-c-T1", model="model-c", runs_root=runs_root)
        cli.main(["score", "model-c-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        # fresh — only the newly-incorporated model
        assert set(_load(lb)["models"].keys()) == {"prov/model-c@unversioned"}


# ---------------------------------------------------------------------------
# Cross-tier KPI lookup
# ---------------------------------------------------------------------------

class TestCrossTierLookup:
    """Scored KPI values are looked up across ALL emitted tiers — a KPI sitting
    in watched/diagnostic (e.g. a pre-§6 run, before the values were promoted to
    `scored`) is still scored, no re-run needed. Unknown keys (e.g. an old
    `intervention_burden`) are carried as diagnostics, not scored."""

    def _write_pre_promotion(self, runs_root, run_dir, model, *, conn, link, sup, reuse):
        # graph quality KPIs live in watched/diagnostic (not scored), as older runs
        # emitted them; processing carries the pre-rename `intervention_burden`.
        d = runs_root / run_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / "measurements.json").write_text(json.dumps({
            "header": {"run_id": run_dir, "provider": "p", "model": model,
                       "corpus_fingerprint": "fp", "pass1_prompt_version": "1",
                       "pass2_prompt_version": "", "scanned": 10, "to_compile": 10,
                       "signal": 8, "noise": 2, "p1_attempted": 10, "p2_attempted": 8},
            "processing": {"scored": {"quarantine_rate": 0.0, "intervention_burden": 0.0,
                                      "latency": 1000.0}, "diagnostic": {}},
            "graph": {"scored": {"entity_reuse": reuse},
                      "watched": {"graph_connectivity": conn},
                      "diagnostic": {"link_density": link, "supports_density": sup}},
        }), encoding="utf-8")

    def test_graph_kpis_in_watched_diagnostic_are_still_scored(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        # 'rich' wins the trio (which sit in watched/diagnostic); 'lean' has higher reuse only.
        self._write_pre_promotion(runs_root, "rich-T1", "rich",
                                  conn=0.5, link=4.0, sup=8.0, reuse=0.05)
        self._write_pre_promotion(runs_root, "lean-T1", "lean",
                                  conn=0.1, link=1.0, sup=3.0, reuse=0.20)
        rc = cli.main(["score", "rich-T1", "lean-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        rows = {r["model"]: r for r in _load(lb)["ranking"]}
        rich, lean = "p/rich@unversioned", "p/lean@unversioned"
        # graph_score combines all 4 graph KPIs even though 3 were in watched/diagnostic
        assert rows[rich]["graph_score"] == pytest.approx(0.85)
        assert rows[lean]["graph_score"] == pytest.approx(0.15)
        # the cross-tier values made it into the scored set...
        assert rows[rich]["per_kpi_borda"]["link_density"] is not None
        assert rows[rich]["per_kpi_borda"]["graph_connectivity"] is not None
        # ...and the unknown pre-rename key is NOT scored (it's a diagnostic)
        assert "intervention_burden" not in rows[rich]["per_kpi_borda"]
        # recovery_rate was genuinely never measured here → None (dropped pro-rata)
        assert rows[rich]["per_kpi_borda"]["recovery_rate"] is None


# ---------------------------------------------------------------------------
# Penalty fields persisted in leaderboard JSON
# ---------------------------------------------------------------------------

class TestPenaltyFieldsPersisted:
    def test_ranking_rows_carry_penalty_fields(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root,
                           entity_reuse=0.9, graph_connectivity=0.9,
                           link_density=9.0, supports_density=9.0)
        _make_measurements(run_dir="model-b-T1", model="model-b", runs_root=runs_root,
                           entity_reuse=0.1, graph_connectivity=0.1,
                           link_density=1.0, supports_density=1.0)
        rc = cli.main(["score", "model-a-T1", "model-b-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        payload = _load(lb)
        assert payload["penalty_params"] == {"threshold": 0.5, "cap": 0.10}
        for row in payload["ranking"]:
            assert set(row) >= {
                "model", "rank", "composite", "composite_pre_penalty",
                "penalty", "weakest_kpi", "graph_score", "per_kpi_borda",
            }
            assert 0.0 <= row["composite"] <= 100.0     # 0-100 scale
            assert 0.0 <= row["penalty"] <= 10.0
        by = {r["model"]: r for r in payload["ranking"]}
        # model-b is lopsided on graph (graph_score Borda 0.0) -> capped penalty
        assert by["prov/model-b@unversioned"]["weakest_kpi"] == "graph"
        assert by["prov/model-b@unversioned"]["penalty"] == pytest.approx(10.0)
        assert by["prov/model-a@unversioned"]["penalty"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Penalty column rendered in leaderboard.md
# ---------------------------------------------------------------------------

class TestPenaltyRendered:
    def test_md_shows_penalty_column(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-a-T1", model="model-a", runs_root=runs_root,
                           entity_reuse=0.9, graph_connectivity=0.9,
                           link_density=9.0, supports_density=9.0)
        _make_measurements(run_dir="model-b-T1", model="model-b", runs_root=runs_root,
                           entity_reuse=0.1, graph_connectivity=0.1,
                           link_density=1.0, supports_density=1.0)
        rc = cli.main(["score", "model-a-T1", "model-b-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        md = (tmp_path / "leaderboard.md").read_text()
        assert "PENALTY" in md
        assert "score (0-100)" in md

    def test_terminal_table_annotates_penalty_only_when_nonzero(self):
        # m1: lopsided on latency (penalty 10, weakest=latency) -> annotated.
        # m2: penalty 0 but weakest_kpi populated (=graph) -> NO annotation leak.
        ranking = [
            {"model": "m1", "rank": 1, "composite": 72.22,
             "composite_pre_penalty": 82.22, "penalty": 10.0,
             "weakest_kpi": "latency", "graph_score": 1.0,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 0.0, "entity_reuse": 1.0,
                               "graph_connectivity": 1.0, "link_density": 1.0,
                               "supports_density": 1.0}},
            {"model": "m2", "rank": 2, "composite": 30.0,
             "composite_pre_penalty": 30.0, "penalty": 0.0,
             "weakest_kpi": "graph", "graph_score": 0.0,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 1.0, "entity_reuse": 0.0,
                               "graph_connectivity": 0.0, "link_density": 0.0,
                               "supports_density": 0.0}},
        ]
        out = cli._render_score_table(ranking, {"m1": {}, "m2": {}})
        assert "PENALTY" in out
        assert "10.00 (latency)" in out          # annotated when penalty > 0
        assert "0.00 (graph)" not in out         # no annotation leak at penalty 0


# ---------------------------------------------------------------------------
# Leaderboard keyed on (provider, model, release_version) — #111 Phase 0
# ---------------------------------------------------------------------------

class TestReleaseVersionKeying:
    """The leaderboard row key is (provider, model, release_version), so the same
    model at different release versions becomes distinct rows (baseline-to-baseline
    deltas), while a re-run at the same triple replaces (latest run dir wins)."""

    def test_leaderboard_keys_on_model_and_release_version(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "lb.json"
        # Same model+provider, two release_versions → TWO distinct rows.
        _make_measurements(run_dir="runA", model="deepseek-v4-flash",
                           provider="deepseek", release_version="v0.5.5",
                           runs_root=runs_root)
        _make_measurements(run_dir="runB", model="deepseek-v4-flash",
                           provider="deepseek", release_version="v0.5.6",
                           runs_root=runs_root)
        rc = cli.main(["score", "runA", "runB",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        keys = set(_load(lb)["models"].keys())
        assert len(keys) == 2
        assert any("v0.5.5" in k for k in keys) and any("v0.5.6" in k for k in keys)

    def test_leaderboard_same_triple_replaces(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "lb.json"
        # Same model+provider+release re-run → ONE row, latest run dir wins.
        _make_measurements(run_dir="run1", model="m", provider="p",
                           release_version="v0.5.5", runs_root=runs_root)
        _make_measurements(run_dir="run2", model="m", provider="p",
                           release_version="v0.5.5", runs_root=runs_root)
        rc = cli.main(["score", "run1", "run2",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        lb_data = _load(lb)
        assert len(lb_data["models"]) == 1
        assert list(lb_data["models"].values())[0] == "run2"


# ---------------------------------------------------------------------------
# Task #117 — board-aware rendering (pass boards + byte-identical main board)
# ---------------------------------------------------------------------------

class TestPassBoardRendering:
    def _board_rows(self):
        return [
            {"model": "prov/a@unversioned", "rank": 1, "composite": 80.0,
             "composite_pre_penalty": 80.0, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 1.0, "recovery_rate": 1.0,
                               "latency": 0.5},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"quarantine_rate_pass1": 0.0, "recovery_rate_pass1": 0.0,
                            "latency_pass1": 100.0, "retry_load_pass1": 0.0,
                            "cost_usd_pass1": 0.05, "cost_unknown_calls_pass1": 0}},
            {"model": "prov/b@unversioned", "rank": 2, "composite": 40.0,
             "composite_pre_penalty": 50.0, "penalty": 10.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                               "latency": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"quarantine_rate_pass1": 1.0, "recovery_rate_pass1": 2.0,
                            "latency_pass1": 900.0, "retry_load_pass1": 0.5,
                            "cost_usd_pass1": 0.30, "cost_unknown_calls_pass1": 1}},
        ]

    def _render(self, scope="pass1", unranked=None):
        ranking = self._board_rows()
        return cli._render_leaderboard_md(
            ranking,
            {},                                     # pass boards: raw table from
            {r["model"]: r["raw_values"] for r in ranking},   # raw_values only
            {"quarantine_rate": 2 / 3, "recovery_rate": 1 / 6, "latency": 1 / 6,
             "graph": 0.0},
            "2026-07-22T00:00:00",
            board={"scope": scope, "unranked": unranked or [],
                   "effective_top_weights": {"quarantine_rate": 2 / 3,
                                             "recovery_rate": 1 / 6,
                                             "latency": 1 / 6, "graph": 0.0}},
        )

    def test_pass1_render_suppresses_graph_and_titles_board(self):
        md = self._render()
        assert md.startswith("# Model leaderboard — Pass-1 (enrich)")
        assert "graph_score" not in md
        assert "graph KPIs" not in md
        assert "≥" in md and "unknown" in md          # cost honesty for row b
        assert "| rank | model | cost |" in md

    def test_competition_ranks_rendered_in_markdown(self):
        """D-117-9 display half (R7-F3): tied leaders share rank 1; next row 3."""
        rows = [
            {"model": "prov/a@unversioned", "rank": 1, "composite": 66.7,
             "composite_pre_penalty": 66.7, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"latency_pass1": 100.0, "cost_usd_pass1": 0.04,
                            "cost_unknown_calls_pass1": 0}},
            {"model": "prov/b@unversioned", "rank": 1, "composite": 66.7,
             "composite_pre_penalty": 66.7, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"latency_pass1": 100.0, "cost_usd_pass1": 0.04,
                            "cost_unknown_calls_pass1": 0}},
            {"model": "prov/c@unversioned", "rank": 3, "composite": 40.0,
             "composite_pre_penalty": 50.0, "penalty": 10.0, "weakest_kpi": "latency",
             "graph_score": None,
             "per_kpi_borda": {"quarantine_rate": 0.5, "recovery_rate": 0.5,
                               "latency": 0.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"latency_pass1": 900.0, "cost_usd_pass1": 0.36,
                            "cost_unknown_calls_pass1": 0}},
        ]
        md = cli._render_leaderboard_md(
            rows, {},
            {r["model"]: r["raw_values"] for r in rows},
            {"quarantine_rate": 2 / 3, "recovery_rate": 1 / 6, "latency": 1 / 6,
             "graph": 0.0},
            "2026-07-22T00:00:00",
            board={"scope": "pass1", "unranked": [],
                   "effective_top_weights": {"quarantine_rate": 2 / 3,
                                             "recovery_rate": 1 / 6,
                                             "latency": 1 / 6, "graph": 0.0}},
        )
        rank_cells = [ln.split("|")[1].strip() for ln in md.splitlines()
                      if ln.startswith("| ") and "prov/" in ln
                      and ln.split("|")[1].strip().isdigit()]
        assert rank_cells == ["1", "1", "3"]

    def test_raw_table_shows_measured_values_not_borda(self):
        """P-F4 guard: the raw section must contain measured values
        (latency 100 ms, cost 0.05), never the row's Borda scores."""
        md = self._render()
        raw_section = md.split("## Raw measured values", 1)[1]
        header_line = next(ln for ln in raw_section.splitlines()
                           if ln.startswith("| model |"))
        # raw columns are the suffixed measured KPIs, not canonical Borda axes
        assert "latency_pass1" in header_line
        assert "cost_usd_pass1" in header_line
        assert "| quarantine_rate |" not in header_line   # no bare Borda axis column
        # measured values present in the body
        assert "100" in raw_section                     # measured latency
        assert "0.05" in raw_section                    # measured cost (model a)

    def test_unranked_section_rendered(self):
        md = self._render(unranked=[{
            "model": "prov/c@unversioned", "run_dir": "c-T1",
            "measurement_source": "measurements_fallback",
            "missing_kpis": ["recovery_rate"], "raw_values": {}}])
        assert "## Unranked" in md
        assert "prov/c@unversioned" in md
        assert "measurements_fallback" in md

    def test_pass2_render_keeps_graph_and_states_caveat(self):
        rows = [
            {"model": "prov/a@unversioned", "rank": 1, "composite": 80.0,
             "composite_pre_penalty": 80.0, "penalty": 0.0, "weakest_kpi": "latency",
             "graph_score": 0.85,
             "per_kpi_borda": {"quarantine_rate": 1.0, "recovery_rate": 1.0,
                               "latency": 0.5, "entity_reuse": 1.0,
                               "graph_connectivity": 1.0, "link_density": 1.0,
                               "supports_density": 1.0},
             "measurement_source": "run_state_recomputed",
             "raw_values": {"quarantine_rate_pass2": 0.0, "recovery_rate_pass2": 0.0,
                            "latency_pass2": 300.0, "retry_load_pass2": 0.0,
                            "cost_usd_pass2": 0.54, "cost_unknown_calls_pass2": 0,
                            "entity_reuse": 0.1, "graph_connectivity": 0.2,
                            "link_density": 2.0, "supports_density": 5.0,
                            "pass2_eligibility_rate": 0.75,
                            "pass2_measurement_coverage": 1.0,
                            "p1_noise": 1, "p1_failed": 0}},
        ]
        md = cli._render_leaderboard_md(
            rows,
            {},                                     # pass boards: no scored raw cols
            {r["model"]: r["raw_values"] for r in rows},
            {"quarantine_rate": 0.4, "graph": 0.4, "recovery_rate": 0.1,
             "latency": 0.1},
            "2026-07-22T00:00:00",
            board={"scope": "pass2", "unranked": [],
                   "effective_top_weights": {"quarantine_rate": 0.4, "graph": 0.4,
                                             "recovery_rate": 0.1, "latency": 0.1}},
        )
        assert "Pass-2" in md and "downstream" in md
        assert "#118" in md
        assert "graph_score" in md                   # graph column retained
        assert "0.85" in md                          # populated graph_score shown
        raw_section = md.split("## Raw measured values", 1)[1]
        assert "pass2_eligibility_rate" in raw_section
        assert "p1_failed" in raw_section

    def test_main_board_render_byte_identical_golden(self):
        """Full-byte guard (P-F6): board=None output must equal the golden
        fixture generated from the pre-#117 renderer (characterization test —
        green before AND after the renderer change)."""
        golden = (Path(__file__).parent / "fixtures"
                  / "leaderboard_main_golden.md").read_text(encoding="utf-8")
        md = cli._render_leaderboard_md(**_GOLDEN_INPUT)
        assert md == golden
