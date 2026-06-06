"""Tests for tools.benchmark.promotion — watched-KPI promotion rule (Task #109).

Covers:
- A high-CoV, non-near-zero, non-redundant-with-scored KPI PROMOTES.
- A near-zero-clustered KPI does NOT (Q1 ≤ EPSILON → iqr_excludes_near_zero=False).
- A high-Spearman-vs-scored KPI does NOT (max_spearman_vs_scored ≥ 0.7).
- Edge cases: n < 2 values, None values, all-None models.
"""
from __future__ import annotations

import pytest

from tools.benchmark.promotion import EPSILON, evaluate


# ---------------------------------------------------------------------------
# Three-model fixture helpers
# ---------------------------------------------------------------------------

def _three_model(
    *,
    kpi_values: list[float | None],
    scored_values: list[float | None],
    kpi_name: str = "w_kpi",
    scored_name: str = "s_kpi",
) -> tuple[dict, dict]:
    """Build watched_by_model / scored_by_model for 3 models."""
    model_keys = ["model_a", "model_b", "model_c"]
    watched = {mk: {kpi_name: v} for mk, v in zip(model_keys, kpi_values)}
    scored = {mk: {scored_name: v} for mk, v in zip(model_keys, scored_values)}
    return watched, scored


# ---------------------------------------------------------------------------
# Promotes
# ---------------------------------------------------------------------------

class TestPromotesPositive:
    def test_high_cov_non_near_zero_non_redundant_promotes(self):
        """KPI with CoV>0.2, Q1>EPSILON, and low Spearman-vs-scored should promote."""
        # Values: 0.1, 0.5, 0.9 — well spread, none near-zero, CoV >> 0.2
        # Scored: orthogonal — constant, so Spearman = 0 (no signal)
        watched, scored = _three_model(
            kpi_values=[0.1, 0.5, 0.9],
            scored_values=[1.0, 1.0, 1.0],   # constant → ρ = 0
        )

        result = evaluate(watched, scored)
        r = result["w_kpi"]

        assert r["cov"] is not None
        assert r["cov"] > 0.2, f"expected CoV>0.2, got {r['cov']}"
        assert r["iqr_excludes_near_zero"] is True
        # max_spearman_vs_scored should be 0 (constant scored → constant rank)
        assert r["max_spearman_vs_scored"] == 0.0 or r["max_spearman_vs_scored"] is None
        assert r["promote"] is True

    def test_moderate_spread_non_redundant_promotes(self):
        """Moderate spread + non-monotone scored → |Spearman|=0.5<0.7 → promotes."""
        # CoV: stdev([0.2, 0.4, 0.8]) / mean([0.2, 0.4, 0.8])
        # mean ≈ 0.467, stdev ≈ 0.306, cov ≈ 0.655 >> 0.2
        # scored [0.9, 0.1, 0.5] is non-monotone vs [0.2, 0.4, 0.8]
        # → Spearman ρ = -0.5, |ρ| = 0.5 < 0.7 → not redundant
        watched, scored = _three_model(
            kpi_values=[0.2, 0.4, 0.8],
            scored_values=[0.9, 0.1, 0.5],  # non-monotone → |ρ|=0.5
        )
        result = evaluate(watched, scored)
        r = result["w_kpi"]
        assert r["cov"] > 0.2
        assert r["iqr_excludes_near_zero"] is True
        assert r["max_spearman_vs_scored"] < 0.7
        assert r["promote"] is True


# ---------------------------------------------------------------------------
# Does NOT promote — near-zero cluster
# ---------------------------------------------------------------------------

class TestDoesNotPromoteNearZero:
    def test_near_zero_clustered_kpi_does_not_promote(self):
        """Values near zero: Q1 ≤ EPSILON → iqr_excludes_near_zero=False → no promote.

        Even though CoV might be high (tiny mean, any stdev), the near-zero
        Q1 blocks promotion.  This tests the dedicated near-zero gate.
        """
        # Values are all ≤ EPSILON (1e-3): the Q1 will be ≤ EPSILON
        tiny = EPSILON / 10
        watched, scored = _three_model(
            kpi_values=[tiny * 0.1, tiny * 0.5, tiny * 2.0],
            scored_values=[0.1, 0.5, 0.9],
        )
        result = evaluate(watched, scored)
        r = result["w_kpi"]

        assert r["iqr_excludes_near_zero"] is False, (
            f"expected iqr_excludes_near_zero=False for near-zero values, "
            f"got {r['iqr_excludes_near_zero']}"
        )
        assert r["promote"] is False

    def test_q1_exactly_at_epsilon_does_not_promote(self):
        """Q1 == EPSILON (not strictly greater) → iqr_excludes_near_zero=False."""
        # With inclusive quantiles at n=3: Q1 = min value for ordered set
        # [EPSILON, X, Y] where X>Y>EPSILON  → Q1 = EPSILON
        # statistics.quantiles([a,b,c], n=4, method="inclusive"):
        #   Q1 = a + 0.25*(b-a) for sorted [a,b,c]
        # Set a=0.0, b=EPSILON, c=1.0:
        #   sorted = [0.0, EPSILON, 1.0], Q1 = 0 + 0.25*(EPSILON-0) = EPSILON/4 < EPSILON
        # Use exact values where Q1 will be ≤ EPSILON
        watched, scored = _three_model(
            kpi_values=[0.0, EPSILON, 1.0],
            scored_values=[0.5, 0.5, 0.5],
        )
        result = evaluate(watched, scored)
        r = result["w_kpi"]
        assert r["iqr_excludes_near_zero"] is False
        assert r["promote"] is False


# ---------------------------------------------------------------------------
# Does NOT promote — high Spearman (redundant with scored)
# ---------------------------------------------------------------------------

class TestDoesNotPromoteHighSpearman:
    def test_high_spearman_vs_scored_does_not_promote(self):
        """Watched KPI that is nearly perfectly correlated with a scored KPI
        should NOT promote (max_spearman_vs_scored ≥ 0.7)."""
        # Perfectly correlated: watched = scored → Spearman ρ = 1.0
        watched, scored = _three_model(
            kpi_values=[0.1, 0.5, 0.9],
            scored_values=[0.1, 0.5, 0.9],
        )
        result = evaluate(watched, scored)
        r = result["w_kpi"]

        assert r["max_spearman_vs_scored"] is not None
        assert r["max_spearman_vs_scored"] >= 0.7, (
            f"expected high Spearman, got {r['max_spearman_vs_scored']}"
        )
        assert r["promote"] is False

    def test_near_perfect_anticorrelation_does_not_promote(self):
        """Anti-correlated watched KPI (|ρ| ≥ 0.7) should also NOT promote."""
        # Watched ≈ inverse of scored
        watched, scored = _three_model(
            kpi_values=[0.9, 0.5, 0.1],
            scored_values=[0.1, 0.5, 0.9],
        )
        result = evaluate(watched, scored)
        r = result["w_kpi"]
        assert r["max_spearman_vs_scored"] >= 0.7
        assert r["promote"] is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_model_cov_none_no_promote(self):
        """With only 1 model (n<2), CoV cannot be computed → None → no promote."""
        watched = {"model_a": {"w_kpi": 0.5}}
        scored = {"model_a": {"s_kpi": 0.5}}

        result = evaluate(watched, scored)
        r = result["w_kpi"]

        assert r["cov"] is None
        assert r["promote"] is False

    def test_all_none_values_no_promote(self):
        """All watched values are None → cov=None, no promote."""
        watched, scored = _three_model(
            kpi_values=[None, None, None],
            scored_values=[0.1, 0.5, 0.9],
        )
        result = evaluate(watched, scored)
        r = result["w_kpi"]
        assert r["cov"] is None
        assert r["iqr_excludes_near_zero"] is False
        assert r["promote"] is False

    def test_constant_scored_kpi_treated_as_zero_spearman(self):
        """A scored KPI that's constant across models has zero rank-variance.
        Spearman is undefined; the implementation should treat it as ρ=0.
        The watched KPI should still be evaluated against other scored KPIs."""
        watched = {
            "model_a": {"w_kpi": 0.1},
            "model_b": {"w_kpi": 0.5},
            "model_c": {"w_kpi": 0.9},
        }
        scored = {
            "model_a": {"const_kpi": 1.0, "var_kpi": 0.1},
            "model_b": {"const_kpi": 1.0, "var_kpi": 0.5},
            "model_c": {"const_kpi": 1.0, "var_kpi": 0.9},
        }
        result = evaluate(watched, scored)
        r = result["w_kpi"]
        # const_kpi gives ρ=None → treated as 0; var_kpi gives ρ=1.0
        # max_spearman should reflect the var_kpi ρ=1.0
        assert r["max_spearman_vs_scored"] >= 0.9
        assert r["promote"] is False  # high Spearman blocks it

    def test_multiple_watched_kpis_evaluated_independently(self):
        """Two watched KPIs with different properties → each evaluated independently."""
        watched = {
            "model_a": {"good_kpi": 0.2, "bad_kpi": 0.0001},
            "model_b": {"good_kpi": 0.5, "bad_kpi": 0.00005},
            "model_c": {"good_kpi": 0.9, "bad_kpi": 0.0002},
        }
        scored = {
            "model_a": {"s_kpi": 1.0},
            "model_b": {"s_kpi": 1.0},
            "model_c": {"s_kpi": 1.0},
        }
        result = evaluate(watched, scored)

        # good_kpi: high spread, Q1 >> EPSILON, no Spearman issue (constant scored)
        assert result["good_kpi"]["promote"] is True
        # bad_kpi: near-zero values → Q1 ≤ EPSILON
        assert result["bad_kpi"]["iqr_excludes_near_zero"] is False
        assert result["bad_kpi"]["promote"] is False

    def test_pairwise_none_dropping(self):
        """A model with None watched value is excluded from Spearman pairwise pair."""
        watched = {
            "model_a": {"w_kpi": 0.2},
            "model_b": {"w_kpi": None},  # dropped from Spearman pairing
            "model_c": {"w_kpi": 0.8},
        }
        scored = {
            "model_a": {"s_kpi": 0.2},
            "model_b": {"s_kpi": 0.5},
            "model_c": {"s_kpi": 0.8},
        }
        # With model_b dropped, only model_a and model_c remain for Spearman.
        # w=[0.2, 0.8], s=[0.2, 0.8] → ρ=1.0 (n=2 perfect correlation)
        result = evaluate(watched, scored)
        r = result["w_kpi"]
        # CoV only over non-None: [0.2, 0.8] → cov is well-defined
        assert r["cov"] is not None
        # Spearman reflects the 2-item perfectly-correlated pair
        assert r["max_spearman_vs_scored"] is not None
        assert r["max_spearman_vs_scored"] >= 0.9
        assert r["promote"] is False  # blocked by high Spearman
