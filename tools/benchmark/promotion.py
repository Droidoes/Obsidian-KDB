"""tools.benchmark.promotion — watched-diagnostic promotion helper (#109).

evaluate(watched_by_model, scored_by_model) -> dict[str, dict]

For each watched KPI, computes signal metrics across models and returns a
per-KPI dict with a `promote` boolean that gates whether the watched KPI
should be elevated to the scored (Borda-ranking) set.

Promote gate (all three must hold):
  1. CoV > 0.2           — the KPI varies meaningfully across models
  2. iqr_excludes_near_zero — the bulk of values are non-trivial
                             (Q1 of the distribution > EPSILON)
  3. max_spearman_vs_scored < 0.7 — not redundant with existing scored KPIs

Design choices documented in this module's docstring:
  - CoV uses SAMPLE stdev (statistics.stdev, n-1 denominator); n<2 → None.
  - Spearman is computed as Pearson-on-ranks (rank-then-pearson, no scipy).
    Ties receive average (fractional) ranks.  If a scored KPI is constant
    across models its rank vector has zero variance; that KPI is skipped
    (ρ treated as 0 for the "max" step).
  - Models where either watched or the candidate scored KPI value is None
    are dropped pairwise (Spearman is computed only on the paired set).
  - EPSILON = 1e-3.  "iqr_excludes_near_zero" requires Q1 > EPSILON.
    statistics.quantiles(method="inclusive") is used (n>=2 guaranteed by
    the n>=2 guard from CoV; method="inclusive" is stable at n=2..4).
"""
from __future__ import annotations

import statistics
from typing import Union

# Epsilon for near-zero detection in iqr_excludes_near_zero.
# A watched KPI whose first quartile is at or below this value is considered
# near-zero-clustered and will not promote.
EPSILON: float = 1e-3


def _fractional_ranks(values: list[float]) -> list[float]:
    """Return average (fractional) ranks for a list of floats (ascending).

    Ties share the average of their ordinal positions (1-indexed).
    Example: [3, 1, 1] → ranks for ordinals 1,2,3 → tied 1,2 get 1.5 each
    → result ordered by input position: [3.0, 1.5, 1.5].
    """
    n = len(values)
    indexed = sorted(range(n), key=lambda i: values[i])
    rank = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            rank[indexed[k]] = avg
        i = j + 1
    return rank


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation on paired lists.  Returns None if either list has
    zero variance (constant sequence) — caller treats this as ρ=0."""
    n = len(xs)
    if n < 2:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = (vx * vy) ** 0.5
    if denom == 0.0:
        return None  # constant sequence — no signal
    return cov / denom


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman ρ via rank-then-Pearson."""
    if len(xs) < 2:
        return None
    return _pearson(_fractional_ranks(xs), _fractional_ranks(ys))


def evaluate(
    watched_by_model: dict[str, dict[str, Union[float, None]]],
    scored_by_model: dict[str, dict[str, Union[float, None]]],
) -> dict[str, dict]:
    """Evaluate watched KPIs for promotion eligibility.

    Parameters
    ----------
    watched_by_model:
        ``{model_key: {watched_kpi: value | None, ...}, ...}``
    scored_by_model:
        ``{model_key: {scored_kpi: value | None, ...}, ...}``

    Returns
    -------
    ``{watched_kpi: {
        "cov": float | None,
        "iqr_excludes_near_zero": bool,
        "max_spearman_vs_scored": float | None,
        "promote": bool,
    }, ...}``

    Notes
    -----
    - CoV (coefficient of variation) = stdev / mean.  When mean == 0 → 0.0.
      When n < 2 → None (can't compute sample stdev).  Returns None if all
      values are None.
    - ``iqr_excludes_near_zero``: requires at least 2 non-None values.
      Q1 computed via ``statistics.quantiles(..., method="inclusive")``.
      True iff Q1 > EPSILON.
    - ``max_spearman_vs_scored``: maximum |ρ| across all scored KPIs.
      A scored KPI with constant values (zero rank-variance) is skipped;
      its ρ is treated as 0.  None when no scored KPI can be paired.
    - ``promote``: True iff cov > 0.2 AND iqr_excludes_near_zero AND
      max_spearman_vs_scored < 0.7.
    """
    # Collect all watched KPI names
    all_watched: list[str] = []
    seen: set[str] = set()
    for model_vals in watched_by_model.values():
        for kpi in model_vals:
            if kpi not in seen:
                all_watched.append(kpi)
                seen.add(kpi)

    # Collect all scored KPI names
    all_scored: list[str] = []
    seen_s: set[str] = set()
    for model_vals in scored_by_model.values():
        for kpi in model_vals:
            if kpi not in seen_s:
                all_scored.append(kpi)
                seen_s.add(kpi)

    model_keys = list(watched_by_model.keys())

    result: dict[str, dict] = {}

    for w_kpi in all_watched:
        # Non-None values for this watched KPI across all models
        w_values = [
            watched_by_model[mk].get(w_kpi)
            for mk in model_keys
        ]
        non_none = [v for v in w_values if v is not None]

        # --- CoV ---
        cov: float | None
        if len(non_none) < 2:
            cov = None
        else:
            mean = statistics.mean(non_none)
            sd = statistics.stdev(non_none)  # sample stdev (n-1 denom)
            cov = sd / mean if mean != 0.0 else 0.0

        # --- IQR / near-zero ---
        iqr_excludes_near_zero: bool = False
        if len(non_none) >= 2:
            qs = statistics.quantiles(non_none, n=4, method="inclusive")
            q1 = qs[0]  # quantiles(n=4) returns [Q1, Q2, Q3]
            iqr_excludes_near_zero = q1 > EPSILON

        # --- Max |Spearman| vs scored KPIs ---
        max_spearman: float | None = None

        for s_kpi in all_scored:
            # Build paired list (drop models where either side is None)
            paired_w: list[float] = []
            paired_s: list[float] = []
            for mk in model_keys:
                wv = watched_by_model[mk].get(w_kpi)
                sv = scored_by_model[mk].get(s_kpi)
                if wv is not None and sv is not None:
                    paired_w.append(wv)
                    paired_s.append(sv)

            if len(paired_w) < 2:
                continue

            rho = _spearman(paired_w, paired_s)
            abs_rho = abs(rho) if rho is not None else 0.0  # constant scored → skip
            if max_spearman is None or abs_rho > max_spearman:
                max_spearman = abs_rho

        # --- Promote gate ---
        promote = (
            cov is not None
            and cov > 0.2
            and iqr_excludes_near_zero
            and max_spearman is not None
            and max_spearman < 0.7
        )

        result[w_kpi] = {
            "cov": cov,
            "iqr_excludes_near_zero": iqr_excludes_near_zero,
            "max_spearman_vs_scored": max_spearman,
            "promote": promote,
        }

    return result
