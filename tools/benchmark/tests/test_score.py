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
        assert set(data["models"].keys()) == {"model-a", "model-b", "model-c"}
        # leaderboard stores POINTERS (run-dir strings), not KPI values
        assert data["models"]["model-b"] == "model-b-T1"
        assert all(isinstance(v, str) for v in data["models"].values())

        ranking = data["ranking"]
        assert len(ranking) == 3
        assert [r["rank"] for r in ranking] == [1, 2, 3]
        # entity_reuse is ↑ → highest reuse (model-b) ranks #1
        assert ranking[0]["model"] == "model-b"
        assert ranking[-1]["model"] == "model-a"

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
        # graph_score is reported, and the richer graph wins it despite lower reuse
        assert "graph_score" in rows["rich"]
        assert rows["rich"]["graph_score"] == pytest.approx(0.85)   # 0.35+0.30+0.20
        assert rows["lean"]["graph_score"] == pytest.approx(0.15)   # reuse only
        # and 'rich' wins the overall composite (graph is 40%; processing tied)
        assert rows["rich"]["rank"] == 1


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
        assert set(_load(lb)["models"].keys()) == {"model-a", "model-b"}

        # incorporate a third model with just its run dir
        _make_measurements(run_dir="model-c-T1", model="model-c", runs_root=runs_root)
        rc = cli.main(["score", "model-c-T1",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        data = _load(lb)
        assert set(data["models"].keys()) == {"model-a", "model-b", "model-c"}
        assert len(data["ranking"]) == 3

    def test_rerun_existing_model_replaces_its_run_dir(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-x-T1", model="model-x", entity_reuse=0.10, runs_root=runs_root)
        cli.main(["score", "model-x-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert _load(lb)["models"]["model-x"] == "model-x-T1"

        # a newer run of the SAME model slug → replaces the pointer, still one row
        _make_measurements(run_dir="model-x-T2", model="model-x", entity_reuse=0.50, runs_root=runs_root)
        rc = cli.main(["score", "model-x-T2",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        data = _load(lb)
        assert list(data["models"].keys()) == ["model-x"]
        assert data["models"]["model-x"] == "model-x-T2"

    def test_two_runs_same_model_one_invocation_latest_wins(self, tmp_path):
        runs_root = tmp_path / "runs"
        lb = tmp_path / "leaderboard.json"
        _make_measurements(run_dir="model-y-T1", model="model-y", runs_root=runs_root)
        _make_measurements(run_dir="model-y-T2", model="model-y", runs_root=runs_root)
        rc = cli.main(["score", "model-y-T1", "model-y-T2",
                       "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        assert rc == 0
        data = _load(lb)
        assert list(data["models"].keys()) == ["model-y"]
        # lexically-greater run dir (T2) wins
        assert data["models"]["model-y"] == "model-y-T2"


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
        assert set(_load(lb)["models"].keys()) == {"model-a", "model-b"}


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
        assert set(_load(lb)["models"].keys()) == {"model-a", "model-b"}

        lb.unlink()  # reset

        _make_measurements(run_dir="model-c-T1", model="model-c", runs_root=runs_root)
        cli.main(["score", "model-c-T1",
                  "--runs-root", str(runs_root), "--leaderboard", str(lb)])
        # fresh — only the newly-incorporated model
        assert set(_load(lb)["models"].keys()) == {"model-c"}


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
        # graph_score combines all 4 graph KPIs even though 3 were in watched/diagnostic
        assert rows["rich"]["graph_score"] == pytest.approx(0.85)
        assert rows["lean"]["graph_score"] == pytest.approx(0.15)
        # the cross-tier values made it into the scored set...
        assert rows["rich"]["per_kpi_borda"]["link_density"] is not None
        assert rows["rich"]["per_kpi_borda"]["graph_connectivity"] is not None
        # ...and the unknown pre-rename key is NOT scored (it's a diagnostic)
        assert "intervention_burden" not in rows["rich"]["per_kpi_borda"]
        # recovery_rate was genuinely never measured here → None (dropped pro-rata)
        assert rows["rich"]["per_kpi_borda"]["recovery_rate"] is None


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
        assert by["model-b"]["weakest_kpi"] == "graph"
        assert by["model-b"]["penalty"] == pytest.approx(10.0)
        assert by["model-a"]["penalty"] == pytest.approx(0.0)


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
