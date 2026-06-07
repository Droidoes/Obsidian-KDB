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
from compiler.kpi.score import (
    weak_spot_penalty,
    _hierarchical_composite,
    WEAK_SPOT_THRESHOLD,
    WEAK_SPOT_PENALTY_CAP,
    COMPOSITE_SCALE,
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
        # graph_score unchanged ([0,1] component): X=1.0, Y=0.15
        assert pm["X"]["graph_score"] == pytest.approx(1.0)
        assert pm["Y"]["graph_score"] == pytest.approx(0.15)
        # X: processing tied (0.5 each), graph 1.0 -> pre = 0.70.
        #    weakest axis = 0.5 (processing) == tau -> penalty 0. composite = 70.0
        assert pm["X"]["composite_pre_penalty"] == pytest.approx(70.0)
        assert pm["X"]["penalty"] == pytest.approx(0.0)
        assert pm["X"]["composite"] == pytest.approx(70.0)
        # Y: pre = 0.30 + 0.40*0.15 = 0.36. weakest = graph 0.15 -> penalty
        #    0.10*(0.5-0.15)/0.5 = 0.07. composite = 0.29. Scaled: pre 36, pen 7, comp 29
        assert pm["Y"]["composite_pre_penalty"] == pytest.approx(36.0)
        assert pm["Y"]["penalty"] == pytest.approx(7.0)
        assert pm["Y"]["weakest_kpi"] == "graph"
        assert pm["Y"]["composite"] == pytest.approx(29.0)

    def test_result_shape(self):
        models = [
            {"model": "A", "scored": {"quarantine_rate": 0.0, "recovery_rate": 0.0,
                                      "latency": 1.0, "graph_connectivity": 0.2,
                                      "link_density": 2.0, "supports_density": 5.0,
                                      "entity_reuse": 0.1}},
        ]
        res = score_models(models)
        assert set(res) == {"per_model", "top_weights", "graph_weights", "penalty_params"}
        assert set(res["per_model"]["A"]) == {
            "composite", "composite_pre_penalty", "penalty", "weakest_kpi",
            "graph_score", "per_kpi_borda",
        }
        assert res["penalty_params"] == {
            "threshold": WEAK_SPOT_THRESHOLD, "cap": WEAK_SPOT_PENALTY_CAP}
        # single model -> every KPI borda 1.0 -> pre 1.0, no penalty -> 100.0
        assert res["per_model"]["A"]["composite"] == pytest.approx(100.0)


# ===========================================================================
# 4. weak_spot_penalty unit tests
# ===========================================================================

class TestWeakSpotPenalty:
    def test_balanced_model_no_penalty(self):
        # all four axes at/above tau=0.5 -> no glaring weak spot
        pkb = {"quarantine_rate": 0.6, "recovery_rate": 0.7, "latency": 0.5}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=0.9)
        assert penalty == 0.0
        assert weakest == "latency"  # the min, but it is AT tau -> no penalty

    def test_weakest_zero_hits_cap(self):
        pkb = {"quarantine_rate": 1.0, "recovery_rate": 1.0, "latency": 1.0}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=0.0)
        assert penalty == pytest.approx(WEAK_SPOT_PENALTY_CAP)  # 0.10
        assert weakest == "graph"

    def test_partial_weak_spot_linear(self):
        # weakest=0.15, tau=0.5 -> 0.10 * (0.5-0.15)/0.5 = 0.07
        pkb = {"quarantine_rate": 0.9, "recovery_rate": 0.9, "latency": 0.9}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=0.15)
        assert penalty == pytest.approx(0.07)
        assert weakest == "graph"

    def test_threshold_boundary_is_zero(self):
        pkb = {"quarantine_rate": 0.5, "recovery_rate": 0.9, "latency": 0.9}
        penalty, _ = weak_spot_penalty(pkb, graph_score=0.9)
        assert penalty == 0.0  # weakest == tau exactly -> deadband

    def test_none_axes_skipped(self):
        # graph_score None and one processing KPI None -> min over present axes
        pkb = {"quarantine_rate": 0.1, "recovery_rate": None, "latency": 0.8}
        penalty, weakest = weak_spot_penalty(pkb, graph_score=None)
        assert weakest == "quarantine_rate"
        assert penalty == pytest.approx(0.10 * (0.5 - 0.1) / 0.5)  # 0.08

    def test_no_present_axis_returns_zero_none(self):
        penalty, weakest = weak_spot_penalty({}, graph_score=None)
        assert penalty == 0.0
        assert weakest is None

    def test_penalty_flips_ranking_lopsided_below_balanced(self):
        # The headline behavior (spec §6): a lopsided model that leads on
        # pre-penalty composite is demoted BELOW a balanced competitor whose
        # pre-penalty composite was lower. Tested against the score internals
        # directly (deterministic — no dependence on Borda field composition).
        # A: strong on 3 axes, glaring weak spot on graph (0.05 << tau).
        a_pkb = {"quarantine_rate": 0.9, "recovery_rate": 0.9, "latency": 0.9}
        a_graph = 0.05
        # B: balanced — every axis at mid (0.5 == tau, no weak spot).
        b_pkb = {"quarantine_rate": 0.5, "recovery_rate": 0.5, "latency": 0.5}
        b_graph = 0.5

        a_pre = _hierarchical_composite(a_pkb, a_graph)   # 0.56
        b_pre = _hierarchical_composite(b_pkb, b_graph)   # 0.50
        a_pen, a_weak = weak_spot_penalty(a_pkb, a_graph)  # 0.09, "graph"
        b_pen, _ = weak_spot_penalty(b_pkb, b_graph)       # 0.0

        # Pre-penalty: the lopsided model leads.
        assert a_pre > b_pre
        # Only the lopsided model is penalized, on its weak (graph) axis.
        assert a_weak == "graph"
        assert a_pen > 0.0
        assert b_pen == 0.0
        # Post-penalty: the balanced model overtakes — the flip.
        assert (a_pre - a_pen) < (b_pre - b_pen)
