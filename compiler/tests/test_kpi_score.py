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

from compiler.kpi.score import borda_normalize, borda_score


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
    Fixture: 3 models, 2 KPIs: quarantine_rate (↓) and link_resolution_rate (↓).

    Values:
      alpha:  quarantine_rate=0.01, link_resolution_rate=0.20
      beta:   quarantine_rate=0.05, link_resolution_rate=None  ← dropped from link_resolution_rate
      gamma:  quarantine_rate=0.03, link_resolution_rate=0.10

    quarantine_rate (lower_is_better=True), 3 models, distinct values:
      Sorted best→worst: alpha(0.01) < gamma(0.03) < beta(0.05)
      ordinal ranks: alpha=1, gamma=2, beta=3; N=3
      scores: alpha=(3-1)/(3-1)=1.0, gamma=(3-2)/2=0.5, beta=(3-3)/2=0.0

    link_resolution_rate (lower_is_better=True), 2 eligible models (beta dropped):
      Sorted best→worst: gamma(0.10) < alpha(0.20)
      ordinal ranks: gamma=1, alpha=2; N=2
      scores: gamma=(2-1)/(2-1)=1.0, alpha=(2-2)/1=0.0
      beta: None (not in result)

    Equal weights (weights=None → each KPI gets 1.0):

    alpha:
      present KPIs: quarantine_rate(1.0) + link_resolution_rate(0.0)
      composite = (1.0*1.0 + 1.0*0.0) / 2.0 = 0.5

    beta:
      present KPIs: quarantine_rate only (link_resolution_rate=None → dropped)
      composite = (1.0*0.0) / 1.0 = 0.0

    gamma:
      present KPIs: quarantine_rate(0.5) + link_resolution_rate(1.0)
      composite = (1.0*0.5 + 1.0*1.0) / 2.0 = 0.75
    """

    @pytest.fixture
    def models(self):
        return [
            {
                "group_key": "alpha",
                "scored": {
                    "quarantine_rate": 0.01,
                    "link_resolution_rate": 0.20,
                },
            },
            {
                "group_key": "beta",
                "scored": {
                    "quarantine_rate": 0.05,
                    "link_resolution_rate": None,   # beta dropped from this KPI
                },
            },
            {
                "group_key": "gamma",
                "scored": {
                    "quarantine_rate": 0.03,
                    "link_resolution_rate": 0.10,
                },
            },
        ]

    def test_per_kpi_borda_quarantine_rate(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        assert pm["alpha"]["per_kpi_borda"]["quarantine_rate"] == pytest.approx(1.0)
        assert pm["gamma"]["per_kpi_borda"]["quarantine_rate"] == pytest.approx(0.5)
        assert pm["beta"]["per_kpi_borda"]["quarantine_rate"] == pytest.approx(0.0)

    def test_per_kpi_borda_link_resolution_rate(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        # gamma best (0.10), alpha worst (0.20) — 2 eligible, N=2
        assert pm["gamma"]["per_kpi_borda"]["link_resolution_rate"] == pytest.approx(1.0)
        assert pm["alpha"]["per_kpi_borda"]["link_resolution_rate"] == pytest.approx(0.0)

    def test_none_model_dropped_from_link_resolution_rate_only(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        # beta's link_resolution_rate borda is None (dropped from that ranking)
        assert pm["beta"]["per_kpi_borda"]["link_resolution_rate"] is None
        # but beta IS present in quarantine_rate ranking
        assert pm["beta"]["per_kpi_borda"]["quarantine_rate"] is not None

    def test_composite_scores(self, models):
        result = borda_score(models)
        pm = result["per_model"]
        assert pm["alpha"]["composite"] == pytest.approx(0.5)
        assert pm["beta"]["composite"] == pytest.approx(0.0)
        assert pm["gamma"]["composite"] == pytest.approx(0.75)

    def test_equal_weights_returned(self, models):
        result = borda_score(models)
        assert result["weights"] == {"quarantine_rate": 1.0, "link_resolution_rate": 1.0}

    def test_custom_weights_applied(self, models):
        """Custom weights shift the composite proportionally."""
        weights = {"quarantine_rate": 2.0, "link_resolution_rate": 1.0}
        result = borda_score(models, weights=weights)
        pm = result["per_model"]
        # alpha: (2.0*1.0 + 1.0*0.0) / 3.0 = 2/3
        assert pm["alpha"]["composite"] == pytest.approx(2.0 / 3.0)
        # beta: (2.0*0.0) / 2.0 = 0.0  (only quarantine_rate present)
        assert pm["beta"]["composite"] == pytest.approx(0.0)
        # gamma: (2.0*0.5 + 1.0*1.0) / 3.0 = 2/3
        assert pm["gamma"]["composite"] == pytest.approx(2.0 / 3.0)

    def test_all_models_present_in_result(self, models):
        result = borda_score(models)
        assert set(result["per_model"].keys()) == {"alpha", "beta", "gamma"}

    def test_result_keys(self, models):
        result = borda_score(models)
        assert set(result.keys()) == {"per_model", "weights"}
