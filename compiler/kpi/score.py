"""compiler.kpi.score — Borda scoring mechanism for cross-model benchmark ranking.

Provides:
  borda_normalize(...)  — lifted verbatim from tools.benchmark.scorer (§7 spec).
                          tools.benchmark.scorer re-exports this symbol so its
                          existing callers/tests remain unchanged.  The lift
                          satisfies the B.3 contract: compiler must NOT import
                          tools; tools MAY import compiler.

  borda_score(...)      — composite Borda scorer over the per-model "scored" KPI
                          dicts produced by compiler.kpi.processing / graph.
                          Weights default to equal; pluggable post-run-1
                          calibration supply a weight dict.

Direction table
---------------
Every KPI in the current scored set is lower-is-better (↓):
  quarantine_rate, intervention_burden, latency   (processing.py)
  dangling_link_rate                            (graph.py)

The ``KPI_LOWER_IS_BETTER`` lookup is the extension point: add a new KPI with
``False`` to register it as higher-is-better without touching any other code.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Direction lookup — single source of truth for KPI ranking direction.
# ---------------------------------------------------------------------------

KPI_LOWER_IS_BETTER: dict[str, bool] = {
    # PROCESSING-family scored KPIs
    "quarantine_rate":      True,
    "intervention_burden":  True,
    "latency":              True,
    # GRAPH-family scored KPIs
    "dangling_link_rate": True,
}


# ---------------------------------------------------------------------------
# borda_normalize — lifted verbatim from tools.benchmark.scorer (§7 spec).
#
# Signature and behaviour are UNCHANGED.  The type annotation uses a forward-
# reference string ("RunScore") so this module never imports RunScore from
# tools.benchmark.scorer — that would violate the B.3 compiler→tools ban.
# At runtime the annotation is never evaluated (from __future__ import
# annotations ensures string-mode for all annotations in this file).
# ---------------------------------------------------------------------------

def borda_normalize(
    runs: "list",
    measure: str,
    *,
    lower_is_better: bool,
) -> dict[str, float]:
    """Average-rank (fractional rank) Borda normalization across candidates.

    Identical to the original in tools.benchmark.scorer:

      1. Drop items where ``item.measures[measure].rate`` is None.
      2. Sort the remaining N items by raw rate (asc if lower_is_better else
         desc).
      3. Assign fractional ranks — ties share the average of their ordinal
         positions.
      4. Convert rank → score in [0, 1]:
             score = (N − rank) / (N − 1)     if N ≥ 2
             score = 1.0                       if N == 1
         All-equal candidates → 0.5 each (no signal).

    Parameters
    ----------
    runs:
        Any sequence of objects that expose ``.model_id`` (str) and
        ``.measures[measure].rate`` (float | None).  Originally typed as
        ``list[RunScore]``; kept as bare ``list`` here so this module
        imports nothing from tools.
    measure:
        Key to look up inside each item's ``.measures`` dict.
    lower_is_better:
        Ranking direction.

    Returns
    -------
    dict mapping model_id → normalized score in [0, 1].
    """
    eligible = [
        (r.model_id, r.measures[measure].rate)
        for r in runs
        if r.measures[measure].rate is not None
    ]
    n = len(eligible)
    if n == 0:
        return {}
    if n == 1:
        return {eligible[0][0]: 1.0}

    sorted_pairs = sorted(eligible, key=lambda mr: mr[1], reverse=not lower_is_better)

    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j + 1

    distinct_rates = {rate for _, rate in eligible}
    if len(distinct_rates) == 1:
        return {model_id: 0.5 for model_id, _ in eligible}

    return {
        model_id: (n - rank) / (n - 1)
        for model_id, rank in ranks.items()
    }


# ---------------------------------------------------------------------------
# borda_score — composite Borda scorer for benchmark KPI dicts.
# ---------------------------------------------------------------------------

def borda_score(
    models: list[dict],
    weights: dict | None = None,
) -> dict:
    """Compute per-model Borda composite scores from scored KPI dicts.

    Parameters
    ----------
    models:
        List of per-model records, each::

            {
                "group_key": str,          # unique model identifier
                "scored": {
                    kpi_name: float | None,  # None = model absent from this KPI
                    ...
                },
            }

        ``group_key`` is the identifier used in the returned dict.  A model
        whose value for a KPI is None is excluded from that KPI's ranking
        (Borda-normalize drops it), but still receives a composite from the
        remaining KPIs it participated in.

    weights:
        Optional mapping ``{kpi_name: float}``.  When None, every KPI present
        in any model's ``scored`` dict receives equal weight (1.0).  Weights
        are normalised by the sum of weights for the KPIs a given model
        participated in (pro-rata redistribution — mirrors ``final_score`` in
        tools.benchmark.scorer lines 990-999).

    Returns
    -------
    dict::

        {
            "per_model": {
                group_key: {
                    "composite": float,           # weighted Borda sum, normalised
                    "per_kpi_borda": {
                        kpi_name: float | None,   # None = dropped from that KPI
                    },
                }
            },
            "weights": {kpi_name: float},         # effective weights used
        }

    Notes
    -----
    *Direction*: ``KPI_LOWER_IS_BETTER`` is the lookup; unknown KPIs default to
    ``True`` (lower-is-better) and a direction entry should be added to the
    lookup table.

    *All-None composite*: if a model has None borda on every KPI (it was
    absent from every ranking), its composite is ``0.0`` (not None) — the
    convention mirrors a fully-degenerate run getting the lowest score rather
    than being excluded from the result.
    """
    from types import SimpleNamespace

    # Collect the union of all KPI names across models.
    all_kpis: list[str] = []
    seen: set[str] = set()
    for m in models:
        for kpi in (m.get("scored") or {}):
            if kpi not in seen:
                all_kpis.append(kpi)
                seen.add(kpi)

    # Effective weight table.
    if weights is None:
        effective_weights = {kpi: 1.0 for kpi in all_kpis}
    else:
        effective_weights = {kpi: weights.get(kpi, 1.0) for kpi in all_kpis}

    # Build shims that borda_normalize can consume (duck-typed, not RunScore).
    # Each shim exposes .model_id and .measures[kpi].rate via SimpleNamespace.
    def _make_shim(m: dict) -> "SimpleNamespace":
        scored = m.get("scored") or {}
        measures = {
            kpi: SimpleNamespace(rate=scored.get(kpi))
            for kpi in all_kpis
        }
        return SimpleNamespace(model_id=m["group_key"], measures=measures)

    shims = [_make_shim(m) for m in models]

    # Per-KPI Borda normalization.
    per_kpi_results: dict[str, dict[str, float]] = {}
    for kpi in all_kpis:
        direction = KPI_LOWER_IS_BETTER.get(kpi, True)
        per_kpi_results[kpi] = borda_normalize(shims, kpi, lower_is_better=direction)

    # Build per-model composite (pro-rata weighted sum).
    per_model: dict[str, dict] = {}
    for m in models:
        gk = m["group_key"]
        per_kpi_borda: dict[str, float | None] = {}
        score_sum = 0.0
        present_weights = 0.0
        for kpi in all_kpis:
            borda_val = per_kpi_results[kpi].get(gk)  # None if dropped
            per_kpi_borda[kpi] = borda_val
            if borda_val is not None:
                w = effective_weights[kpi]
                score_sum += w * borda_val
                present_weights += w

        composite = score_sum / present_weights if present_weights > 0.0 else 0.0
        per_model[gk] = {
            "composite": composite,
            "per_kpi_borda": per_kpi_borda,
        }

    return {
        "per_model": per_model,
        "weights": effective_weights,
    }
