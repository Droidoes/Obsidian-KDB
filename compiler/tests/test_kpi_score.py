"""Tests for compiler.kpi.score — borda_normalize parity + borda_score.

TDD: written before implementation, then run fail → pass.

Coverage:
  1. borda_normalize parity — same results as the original tools.benchmark.scorer
     tests using duck-typed shims (identical logic, verbatim assertions from
     the spec §7 worked example).
  2. borda_score — 3 synthetic models, one with a None on one KPI, verifying
     per-KPI Borda ranks + composite + None-model dropped from that KPI only.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from compiler.kpi.score import (
    GRAPH_WEIGHTS,
    TOP_WEIGHTS,
    borda_normalize,
    borda_score,
    combined_graph_score,
    score_models,
)


# ---------------------------------------------------------------------------
# Helpers — build shims borda_normalize can consume (duck-typed RunScore)
# ---------------------------------------------------------------------------

def _shim(model_id: str, rate: float | None) -> SimpleNamespace:
    """Minimal shim: exposes .model_id and .measures[key].rate."""
    return SimpleNamespace(
        model_id=model_id,
        measures={"M6": SimpleNamespace(rate=rate)},
    )


# ===========================================================================
# 1. borda_normalize parity
#    Verbatim assertions from the tools.benchmark.scorer §7 worked example.
# ===========================================================================

class TestBordaNormalizeParity:
    def test_spec_section_7_worked_example(self):
        """5 candidates, lower_is_better, rates [0.001,0.001,0.002,0.005,0.005]
        → [0.875, 0.875, 0.5, 0.125, 0.125]."""
        shims = [
            _shim("A", 0.001),
            _shim("B", 0.001),
            _shim("C", 0.002),
            _shim("D", 0.005),
            _shim("E", 0.005),
        ]
        result = borda_normalize(shims, "M6", lower_is_better=True)
        assert result["A"] == pytest.approx(0.875)
        assert result["B"] == pytest.approx(0.875)
        assert result["C"] == pytest.approx(0.5)
        assert result["D"] == pytest.approx(0.125)
        assert result["E"] == pytest.approx(0.125)

    def test_strict_extremes_no_ties(self):
        """No ties: best gets 1.0, worst gets 0.0."""
        shims = [_shim("A", 0.001), _shim("B", 0.005)]
        result = borda_normalize(shims, "M6", lower_is_better=True)
        assert result["A"] == 1.0
        assert result["B"] == 0.0

    def test_all_equal_returns_half(self):
        """All-equal → every candidate gets 0.5 (no signal)."""
        shims = [_shim("A", 0.005), _shim("B", 0.005)]
        result = borda_normalize(shims, "M6", lower_is_better=True)
        assert result["A"] == 0.5
        assert result["B"] == 0.5

    def test_single_candidate_gets_full_score(self):
        shims = [_shim("A", 0.005)]
        result = borda_normalize(shims, "M6", lower_is_better=True)
        assert result["A"] == 1.0

    def test_none_rate_dropped(self):
        """Run with rate=None is excluded from the result dict."""
        shims = [_shim("A", 0.001), _shim("B", None), _shim("C", 0.005)]
        result = borda_normalize(shims, "M6", lower_is_better=True)
        assert "B" not in result
        assert result["A"] == 1.0
        assert result["C"] == 0.0

    def test_higher_is_better_inverts_sort(self):
        shims = [_shim("A", 0.9), _shim("B", 0.1)]
        result = borda_normalize(shims, "M6", lower_is_better=False)
        assert result["A"] == 1.0
        assert result["B"] == 0.0


# ===========================================================================
# 2. borda_score — 3 models, one None on one KPI
# ===========================================================================

class TestBordaScore:
    """
    Fixture: 3 models, 2 KPIs — quarantine_rate (↓ lower better) and
    entity_reuse (↑ higher better — the post-2026-06-06 scored graph KPI).
    This exercises the mixed-direction path: borda_score reads direction from
    KPI_LOWER_IS_BETTER, where entity_reuse is registered False.

    Values:
      alpha:  quarantine_rate=0.01, entity_reuse=0.20
      beta:   quarantine_rate=0.05, entity_reuse=None  ← dropped from entity_reuse
      gamma:  quarantine_rate=0.03, entity_reuse=0.10

    quarantine_rate (lower_is_better=True), 3 models, distinct values:
      Sorted best→worst: alpha(0.01) < gamma(0.03) < beta(0.05)
      ordinal ranks: alpha=1, gamma=2, beta=3; N=3
      scores: alpha=(3-1)/(3-1)=1.0, gamma=(3-2)/2=0.5, beta=(3-3)/2=0.0

    entity_reuse (lower_is_better=False → HIGHER better), 2 eligible (beta dropped):
      Sorted best→worst: alpha(0.20) > gamma(0.10)
      ordinal ranks: alpha=1, gamma=2; N=2
      scores: alpha=(2-1)/(2-1)=1.0, gamma=(2-2)/1=0.0
      beta: None (not in result)

    Equal weights (weights=None → each KPI gets 1.0):

    alpha:
      present KPIs: quarantine_rate(1.0) + entity_reuse(1.0)
      composite = (1.0*1.0 + 1.0*1.0) / 2.0 = 1.0

    beta:
      present KPIs: quarantine_rate only (entity_reuse=None → dropped)
      composite = (1.0*0.0) / 1.0 = 0.0

    gamma:
      present KPIs: quarantine_rate(0.5) + entity_reuse(0.0)
      composite = (1.0*0.5 + 1.0*0.0) / 2.0 = 0.25
    """

    @pytest.fixture
    def models(self):
        return [
            {
                "model": "alpha",
                "scored": {
                    "quarantine_rate": 0.01,
                    "entity_reuse": 0.20,
                },
            },
            {
                "model": "beta",
                "scored": {
                    "quarantine_rate": 0.05,
                    "entity_reuse": None,   # beta dropped from this KPI
                },
            },
            {
                "model": "gamma",
                "scored": {
                    "quarantine_rate": 0.03,
                    "entity_reuse": 0.10,
                },
            },
        ]

    def test_per_kpi_borda_quarantine_rate(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        assert pm["alpha"]["per_kpi_borda"]["quarantine_rate"] == pytest.approx(1.0)
        assert pm["gamma"]["per_kpi_borda"]["quarantine_rate"] == pytest.approx(0.5)
        assert pm["beta"]["per_kpi_borda"]["quarantine_rate"] == pytest.approx(0.0)

    def test_per_kpi_borda_entity_reuse_higher_is_better(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        # entity_reuse is ↑: alpha highest (0.20) → best, gamma (0.10) → worst.
        # 2 eligible (beta None), N=2. Direction comes from KPI_LOWER_IS_BETTER.
        assert pm["alpha"]["per_kpi_borda"]["entity_reuse"] == pytest.approx(1.0)
        assert pm["gamma"]["per_kpi_borda"]["entity_reuse"] == pytest.approx(0.0)

    def test_none_model_dropped_from_entity_reuse_only(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        # beta's entity_reuse borda is None (dropped from that ranking)
        assert pm["beta"]["per_kpi_borda"]["entity_reuse"] is None
        # but beta IS present in quarantine_rate ranking
        assert pm["beta"]["per_kpi_borda"]["quarantine_rate"] is not None

    def test_composite_scores(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        assert pm["alpha"]["composite"] == pytest.approx(1.0)
        assert pm["beta"]["composite"] == pytest.approx(0.0)
        assert pm["gamma"]["composite"] == pytest.approx(0.25)

    def test_equal_weights_returned(self, models):
        result = borda_score(models)
        assert result["weights"] == {"quarantine_rate": 1.0, "entity_reuse": 1.0}

    def test_custom_weights_applied(self, models):
        """Custom weights shift the composite proportionally."""
        weights = {"quarantine_rate": 2.0, "entity_reuse": 1.0}
        result = borda_score(models, weights=weights)
        pm = result["per_model"]
        # alpha: (2.0*1.0 + 1.0*1.0) / 3.0 = 1.0
        assert pm["alpha"]["composite"] == pytest.approx(1.0)
        # beta: (2.0*0.0) / 2.0 = 0.0  (only quarantine_rate present)
        assert pm["beta"]["composite"] == pytest.approx(0.0)
        # gamma: (2.0*0.5 + 1.0*0.0) / 3.0 = 1/3
        assert pm["gamma"]["composite"] == pytest.approx(1.0 / 3.0)

    def test_all_models_present_in_result(self, models):
        result = borda_score(models)
        assert set(result["per_model"].keys()) == {"alpha", "beta", "gamma"}

    def test_result_keys(self, models):
        result = borda_score(models)
        assert set(result.keys()) == {"per_model", "weights"}


# ===========================================================================
# 3. combined_graph_score + weight invariants (§6)
# ===========================================================================

class TestCombinedGraphScore:
    def test_all_graph_kpis_present_weighted_mean(self):
        # GRAPH_WEIGHTS 35/30/20/15; reuse borda = 0 → 0.35+0.30+0.20 = 0.85.
        pkb = {
            "graph_connectivity": 1.0, "link_density": 1.0,
            "supports_density": 1.0, "entity_reuse": 0.0,
            "quarantine_rate": 0.5,  # non-graph KPI ignored
        }
        assert combined_graph_score(pkb) == pytest.approx(0.85)

    def test_missing_graph_kpi_prorata_renormalizes(self):
        # entity_reuse absent → renormalize over present (conn+link+supports).
        pkb = {"graph_connectivity": 1.0, "link_density": 0.0, "supports_density": 0.0}
        assert combined_graph_score(pkb) == pytest.approx(0.35 / 0.85)

    def test_no_graph_kpis_returns_none(self):
        assert combined_graph_score({"quarantine_rate": 1.0}) is None

    def test_top_weights_sum_to_one(self):
        assert sum(TOP_WEIGHTS.values()) == pytest.approx(1.0)

    def test_graph_weights_sum_to_one(self):
        assert sum(GRAPH_WEIGHTS.values()) == pytest.approx(1.0)


class TestScoreModelsHierarchical:
    """score_models: per-KPI Borda → graph_score → top-level composite, and the
    40/40/10/10 split holds EXACTLY even when a model is missing a graph KPI."""

    def test_missing_graph_kpi_keeps_graph_at_40_percent(self):
        # X wins the richness trio but has entity_reuse=None (degenerate corner);
        # Y has all four. The flat approach would redistribute X's missing-reuse
        # weight onto quarantine; the hierarchical scorer must NOT — graph stays 40%.
        models = [
            {"model": "X", "scored": {
                "quarantine_rate": 0.0, "recovery_rate": 0.0, "latency": 100.0,
                "graph_connectivity": 0.5, "link_density": 5.0,
                "supports_density": 8.0, "entity_reuse": None}},
            {"model": "Y", "scored": {
                "quarantine_rate": 0.0, "recovery_rate": 0.0, "latency": 100.0,
                "graph_connectivity": 0.1, "link_density": 1.0,
                "supports_density": 2.0, "entity_reuse": 0.3}},
        ]
        pm = score_models(models)["per_model"]
        # X: wins conn/link/supports (borda 1.0), reuse dropped → graph_score = 1.0
        assert pm["X"]["graph_score"] == pytest.approx(1.0)
        # Y: loses the trio (0.0), wins reuse (1.0) → 0.15
        assert pm["Y"]["graph_score"] == pytest.approx(0.15)
        # processing all tied → 0.5 each. composite = 0.40·0.5+0.10·0.5+0.10·0.5 + 0.40·graph
        # X: 0.30 + 0.40·1.0 = 0.70  (graph is a full 40% despite the missing reuse KPI)
        assert pm["X"]["composite"] == pytest.approx(0.70)
        # Y: 0.30 + 0.40·0.15 = 0.36
        assert pm["Y"]["composite"] == pytest.approx(0.36)

    def test_result_shape(self):
        models = [
            {"model": "A", "scored": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                                      "latency": 1.0, "graph_connectivity": 0.2,
                                      "link_density": 2.0, "supports_density": 5.0,
                                      "entity_reuse": 0.1}},
        ]
        res = score_models(models)
        assert set(res) == {"per_model", "top_weights", "graph_weights"}
        assert set(res["per_model"]["A"]) == {"composite", "graph_score", "per_kpi_borda"}
