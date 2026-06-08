"""compiler.kpi.score — Borda scoring mechanism for cross-model benchmark ranking.

Provides:
  borda_normalize(...)  — average-rank Borda normalization (§7 spec). Originally
                          lifted from the now-retired tools.benchmark.scorer; this
                          module is its sole home. Kept here per the B.3 contract:
                          compiler must NOT import tools; tools MAY import compiler.

  borda_score(...)      — composite Borda scorer over the per-model "scored" KPI
                          dicts produced by compiler.kpi.processing / graph.
                          Weights default to equal; pluggable post-run-1
                          calibration supply a weight dict.

Direction table
---------------
Scored KPIs and their ranking direction (§6, 2026-06-06):
  quarantine_rate, recovery_rate, latency                  (processing, ↓ lower better)
  entity_reuse, graph_connectivity, link_density, supports_density  (graph, ↑ higher better)

The ``KPI_LOWER_IS_BETTER`` lookup is the extension point: register a KPI with
``False`` for higher-is-better or ``True`` for lower-is-better, without touching
any other code — borda_normalize absorbs direction via ``reverse=not lower_is_better``.

Scoring
-------
``score_models`` is the §6 hierarchical scorer: per-KPI Borda → combined
graph_score (``GRAPH_WEIGHTS``) → top-level composite (``TOP_WEIGHTS`` =
quarantine 40 / graph 40 / recovery 10 / latency 10). Hierarchical (not a flat
7-KPI weighted sum) so the 40/40/10/10 split holds EXACTLY even when a model is
missing a scored KPI — a missing graph KPI renormalizes within graph_score, not
across the whole composite. Weight VALUES are a rationale-based starting point
tuned with multi-model data; the weighting MECHANISM is the deliverable.
``borda_score`` remains the per-KPI Borda engine that ``score_models`` builds on.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Direction lookup — single source of truth for KPI ranking direction.
# ---------------------------------------------------------------------------

KPI_LOWER_IS_BETTER: dict[str, bool] = {
    # PROCESSING-family scored KPIs (↓ lower-is-better)
    "quarantine_rate":      True,
    "recovery_rate":        True,
    "latency":              True,
    # GRAPH-family scored KPIs (↑ higher-is-better) — components of the
    # combined graph score; no single one suffices (see compiler.kpi.graph).
    "entity_reuse":         False,
    "graph_connectivity":   False,
    "link_density":         False,
    "supports_density":     False,
}

# Top-level composite weights — §6 calibration STARTING point (2026-06-06).
# HIERARCHICAL: the four scored graph KPIs first combine into one graph_score
# (GRAPH_WEIGHTS), then graph_score enters the composite as a single 40% term
# alongside the processing KPIs. This honors 40/40/10/10 EXACTLY even when a
# model is missing a scored KPI (pro-rata happens within each family, not across
# the flat 7) — see score_models. Sum = 1.0.
TOP_WEIGHTS: dict[str, float] = {
    "quarantine_rate": 0.40,
    "recovery_rate":   0.10,
    "latency":         0.10,
    "graph":           0.40,   # the combined graph score (see GRAPH_WEIGHTS)
}

# Within-graph weights for the combined graph score (sum to 1.0).
GRAPH_WEIGHTS: dict[str, float] = {
    "graph_connectivity": 0.35,
    "link_density":       0.30,
    "supports_density":   0.20,
    "entity_reuse":       0.15,
}

# Weak-spot penalty (spec 2026-06-06): punish a lopsided model with a glaring
# weak spot. Range over the four COMPOSITE axes (3 processing Borda values +
# the combined graph_score) — NOT the 7 raw KPIs — at equal treatment.
WEAK_SPOT_THRESHOLD = 0.5     # tau: below mid-field => "glaring". PINNED — baseline-1 (4-model) confirmed all penalized models hit the cap.
WEAK_SPOT_PENALTY_CAP = 0.10  # lambda: max deduction (10 pts on the 0-100 scale). PINNED.

# Headline composite is rendered 0-100; components (per_kpi_borda, graph_score)
# stay Borda-native [0,1].
COMPOSITE_SCALE = 100

# The processing KPIs that enter the composite directly (TOP_WEIGHTS keys minus
# the synthetic "graph" term).
_PROCESSING_KPIS = ("quarantine_rate", "recovery_rate", "latency")


def combined_graph_score(per_kpi_borda: dict) -> float | None:
    """Synthesize the four graph KPIs' Borda values into one graph-quality score.

    ``per_kpi_borda`` is a model's ``{kpi: borda_value|None}`` map (from
    ``borda_score(...)["per_model"][model]["per_kpi_borda"]``). Returns the
    GRAPH_WEIGHTS-weighted mean over the *present* (non-None) graph KPIs
    (pro-rata), in [0, 1], higher = better. None when the model has no graph
    KPI present.
    """
    num = 0.0
    den = 0.0
    for kpi, w in GRAPH_WEIGHTS.items():
        b = per_kpi_borda.get(kpi)
        if b is not None:
            num += w * b
            den += w
    return num / den if den > 0 else None


def _hierarchical_composite(per_kpi_borda: dict, graph_score: float | None) -> float:
    """Top-level weighted composite from the processing-KPI Borda values + the
    combined graph_score, using TOP_WEIGHTS. Pro-rata over *present* top-level
    terms (a None processing KPI or a None graph_score drops only its own term),
    so the family split stays faithful (graph is 40% of whatever's present)
    rather than redistributing a missing graph KPI's weight onto quarantine.
    Returns 0.0 when nothing is present.
    """
    num = 0.0
    den = 0.0
    for kpi in _PROCESSING_KPIS:
        b = per_kpi_borda.get(kpi)
        if b is not None:
            num += TOP_WEIGHTS[kpi] * b
            den += TOP_WEIGHTS[kpi]
    if graph_score is not None:
        num += TOP_WEIGHTS["graph"] * graph_score
        den += TOP_WEIGHTS["graph"]
    return num / den if den > 0 else 0.0


def weak_spot_penalty(
    per_kpi_borda: dict, graph_score: float | None
) -> tuple[float, str | None]:
    """Penalty for a model's single weakest composite axis (spec 2026-06-06).

    Axes = the three processing Borda values (quarantine_rate / recovery_rate /
    latency, from ``per_kpi_borda``) plus the combined ``graph_score`` — four
    axes, each in [0,1], equal treatment. graph counts as ONE axis (its four
    sub-KPIs are already blended in graph_score).

    ``weakest`` = min over the *present* (non-None) axes. Penalty rises linearly
    from 0 at the deadband (weakest >= WEAK_SPOT_THRESHOLD) to WEAK_SPOT_PENALTY_CAP
    at weakest == 0. Returns ``(penalty in [0, CAP], weakest_axis_label | None)``.
    No present axis -> ``(0.0, None)``.
    """
    axes: dict[str, float | None] = {
        "quarantine_rate": per_kpi_borda.get("quarantine_rate"),
        "recovery_rate":   per_kpi_borda.get("recovery_rate"),
        "latency":         per_kpi_borda.get("latency"),
        "graph":           graph_score,
    }
    present = {k: v for k, v in axes.items() if v is not None}
    if not present:
        return 0.0, None
    weakest_kpi = min(present, key=lambda k: present[k])
    weakest = present[weakest_kpi]
    tau = WEAK_SPOT_THRESHOLD
    penalty = WEAK_SPOT_PENALTY_CAP * max(0.0, (tau - weakest) / tau)
    return penalty, weakest_kpi


def score_models(models: list[dict]) -> dict:
    """Hierarchical benchmark scorer (§6).

    1. per-KPI Borda-normalize every scored KPI across the cohort (via
       borda_score — weight-independent ranks).
    2. combine the four graph KPIs → one graph_score per model (GRAPH_WEIGHTS).
    3. composite = top-level weighted sum of the processing Borda values +
       graph_score (TOP_WEIGHTS = quarantine 40 / graph 40 / recovery 10 /
       latency 10), pro-rata within family.
    4. weak-spot penalty: deduct up to WEAK_SPOT_PENALTY_CAP from the composite
       when the model's single weakest composite axis is below WEAK_SPOT_THRESHOLD.
    5. scale headline scores (composite, composite_pre_penalty, penalty) by
       COMPOSITE_SCALE (100) so the leaderboard renders on a 0–100 scale.
       graph_score and per_kpi_borda stay Borda-native [0, 1].

    Returns::

        {
          "per_model": {
              model: {
                  "composite":             float,   # [0,100] post-penalty headline
                  "composite_pre_penalty": float,   # [0,100] before penalty
                  "penalty":               float,   # [0,10]  deduction (scaled)
                  "weakest_kpi":           str|None,# weakest composite axis (even if no penalty fired)
                  "graph_score":           float|None,  # [0,1] Borda-native
                  "per_kpi_borda":         dict,    # {kpi: float|None}, [0,1] each
              }
          },
          "top_weights":    TOP_WEIGHTS,
          "graph_weights":  GRAPH_WEIGHTS,
          "penalty_params": {"threshold": WEAK_SPOT_THRESHOLD, "cap": WEAK_SPOT_PENALTY_CAP},
        }
    """
    base = borda_score(models)  # only per_kpi_borda is used (weight-independent)
    per_model: dict[str, dict] = {}
    for m in models:
        slug = m["model"]
        pkb = base["per_model"][slug]["per_kpi_borda"]
        gscore = combined_graph_score(pkb)
        pre = _hierarchical_composite(pkb, gscore)
        penalty, weakest_kpi = weak_spot_penalty(pkb, gscore)
        post = max(0.0, pre - penalty)
        per_model[slug] = {
            "composite": post * COMPOSITE_SCALE,
            "composite_pre_penalty": pre * COMPOSITE_SCALE,
            "penalty": penalty * COMPOSITE_SCALE,
            "weakest_kpi": weakest_kpi,
            "graph_score": gscore,
            "per_kpi_borda": pkb,
        }
    return {
        "per_model": per_model,
        "top_weights": dict(TOP_WEIGHTS),
        "graph_weights": dict(GRAPH_WEIGHTS),
        "penalty_params": {
            "threshold": WEAK_SPOT_THRESHOLD,
            "cap": WEAK_SPOT_PENALTY_CAP,
        },
    }


# ---------------------------------------------------------------------------
# borda_normalize — average-rank Borda normalization (§7 spec).
#
# The type annotation uses a forward-reference string ("RunScore") so this
# module never needs to import a concrete RunScore type from tools — that would
# violate the B.3 compiler→tools ban. At runtime the annotation is never
# evaluated (from __future__ import annotations ensures string-mode for all
# annotations in this file); callers pass any duck-typed .model_id/.measures shim.
# ---------------------------------------------------------------------------

def borda_normalize(
    runs: "list",
    measure: str,
    *,
    lower_is_better: bool,
) -> dict[str, float]:
    """Average-rank (fractional rank) Borda normalization across candidates.

    Algorithm:

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
                "model": str,              # unique model slug (the identifier)
                "scored": {
                    kpi_name: float | None,  # None = model absent from this KPI
                    ...
                },
            }

        ``model`` is the unique model slug used as the identifier in the
        returned dict (one row per model — no provider grouping).  A model
        whose value for a KPI is None is excluded from that KPI's ranking
        (Borda-normalize drops it), but still receives a composite from the
        remaining KPIs it participated in.

    weights:
        Optional mapping ``{kpi_name: float}``.  When None, every KPI present
        in any model's ``scored`` dict receives equal weight (1.0).  Weights
        are normalised by the sum of weights for the KPIs a given model
        participated in (pro-rata redistribution — a missing KPI drops only its
        own weight rather than penalising the model's whole composite).

    Returns
    -------
    dict::

        {
            "per_model": {
                model_slug: {
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
        return SimpleNamespace(model_id=m["model"], measures=measures)

    shims = [_make_shim(m) for m in models]

    # Per-KPI Borda normalization.
    per_kpi_results: dict[str, dict[str, float]] = {}
    for kpi in all_kpis:
        direction = KPI_LOWER_IS_BETTER.get(kpi, True)
        per_kpi_results[kpi] = borda_normalize(shims, kpi, lower_is_better=direction)

    # Build per-model composite (pro-rata weighted sum).
    per_model: dict[str, dict] = {}
    for m in models:
        slug = m["model"]
        per_kpi_borda: dict[str, float | None] = {}
        score_sum = 0.0
        present_weights = 0.0
        for kpi in all_kpis:
            borda_val = per_kpi_results[kpi].get(slug)  # None if dropped
            per_kpi_borda[kpi] = borda_val
            if borda_val is not None:
                w = effective_weights[kpi]
                score_sum += w * borda_val
                present_weights += w

        composite = score_sum / present_weights if present_weights > 0.0 else 0.0
        per_model[slug] = {
            "composite": composite,
            "per_kpi_borda": per_kpi_borda,
        }

    return {
        "per_model": per_model,
        "weights": effective_weights,
    }
