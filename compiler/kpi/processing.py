"""GT-free PROCESSING-family KPI computation over PassCallMeasurement lists.

compute_processing(header, calls) → {"scored": {...}, "diagnostic": {...}}

All rates are per 1M tokens unless noted.  Returns floats or None (never raises
on empty/zero-token input).  Pure function — no I/O.
"""
from __future__ import annotations

from common.measurement import (
    PassCallMeasurement,
    RunMeasurementHeader,
    SearchPassMeasurement,
)


def compute_processing(
    header: RunMeasurementHeader,
    calls: list[PassCallMeasurement],
) -> dict:
    """Compute PROCESSING-family KPIs for one benchmark run.

    Parameters
    ----------
    header:
        Run-level metadata (scanned, signal, etc.).
    calls:
        All PassCallMeasurement objects for the run (pass1 + pass2 combined).

    Returns
    -------
    dict with exactly two keys:
      "scored"     — {"quarantine_rate", "recovery_rate", "latency"}
      "diagnostic" — {"retry_load", "token_overrun_rate", "repair_rung_rate",
                      "semantic_pass_rate", "signal_noise_ratio",
                      "quarantine_rate_pass1", "quarantine_rate_pass2",
                      "latency_pass1", "latency_pass2",
                      # #117 per-pass splits + cost
                      "recovery_rate_pass1", "recovery_rate_pass2",
                      "retry_load_pass1", "retry_load_pass2",
                      "cost_usd_pass1", "cost_usd_pass2",
                      "cost_unknown_calls_pass1", "cost_unknown_calls_pass2"}

    All per-token rates are None when the relevant token denominator is 0.
    retry_load is None when N == 0.
    semantic_pass_rate is None when no P2 call has semantic_ok is not None.
    signal_noise_ratio is None when header.scanned == 0.
    """
    N = len(calls)
    T = sum(c.total_input_tokens + c.total_output_tokens for c in calls)

    # --- helpers -----------------------------------------------------------

    def _rate(count: int | float, tokens: int) -> float | None:
        """count × 1e6 / tokens, or None if tokens == 0."""
        return count * 1e6 / tokens if tokens else None

    # --- partition by pass -------------------------------------------------
    pass1_calls = [c for c in calls if c.pass_ == "pass1"]
    pass2_calls = [c for c in calls if c.pass_ == "pass2"]

    T_pass1 = sum(c.total_input_tokens + c.total_output_tokens for c in pass1_calls)
    T_pass2 = sum(c.total_input_tokens + c.total_output_tokens for c in pass2_calls)

    # --- SCORED ------------------------------------------------------------

    n_quarantined = sum(1 for c in calls if c.final_status == "quarantined")

    # recovery_rate: non-quarantined survivors that needed RETRY or REPAIR to
    # succeed (syntax_repaired ∨ slug_coerced ∨ boundary_recovered = repair;
    # attempts>1 = retry).
    # token_overrun is NOT counted here — it's degraded-survival, not
    # retry/repair, and lives as its own diagnostic (token_overrun_rate).
    # Disjoint from the quarantine set (survivors only → no double-count).
    n_recovery = sum(
        1 for c in calls
        if c.final_status != "quarantined"
        and (c.syntax_repaired or c.slug_coerced or c.boundary_recovered or c.attempts > 1)
    )

    total_latency_ms = sum(c.total_latency_ms for c in calls)
    latency_ms_pass1 = sum(c.total_latency_ms for c in pass1_calls)
    latency_ms_pass2 = sum(c.total_latency_ms for c in pass2_calls)

    scored: dict = {
        "quarantine_rate": _rate(n_quarantined, T),
        "recovery_rate": _rate(n_recovery, T),
        "latency": _rate(total_latency_ms, T),
    }

    # --- DIAGNOSTIC --------------------------------------------------------

    # retry_load: avg extra attempts per call; None if no calls.
    retry_load: float | None
    if N == 0:
        retry_load = None
    else:
        retry_load = sum(max(0, c.attempts - 1) for c in calls) / N

    # token_overrun_rate: quarantined NOT excluded (counts all calls).
    n_overrun = sum(1 for c in calls if c.token_overrun)

    # repair_rung_rate: syntax_repaired OR slug_coerced OR boundary_recovered;
    # quarantined NOT excluded.
    n_repair_rung = sum(
        1 for c in calls
        if c.syntax_repaired or c.slug_coerced or c.boundary_recovered
    )

    # semantic_pass_rate: mean over P2 calls where semantic_ok is not None.
    eligible_semantic = [c for c in pass2_calls if c.semantic_ok is not None]
    if eligible_semantic:
        semantic_pass_rate: float | None = sum(
            1 if c.semantic_ok else 0 for c in eligible_semantic
        ) / len(eligible_semantic)
    else:
        semantic_pass_rate = None

    # signal_noise_ratio: from header only.
    signal_noise_ratio: float | None = (
        header.signal / header.scanned if header.scanned else None
    )

    # Per-pass quarantine breakdown.
    n_quar_pass1 = sum(1 for c in pass1_calls if c.final_status == "quarantined")
    n_quar_pass2 = sum(1 for c in pass2_calls if c.final_status == "quarantined")

    # Per-pass recovery split (#117) — same survivor-retry/repair predicate as
    # the combined recovery_rate, partitioned by pass.
    n_recovery_pass1 = sum(
        1 for c in pass1_calls
        if c.final_status != "quarantined"
        and (c.syntax_repaired or c.slug_coerced or c.boundary_recovered or c.attempts > 1)
    )
    n_recovery_pass2 = sum(
        1 for c in pass2_calls
        if c.final_status != "quarantined"
        and (c.syntax_repaired or c.slug_coerced or c.boundary_recovered or c.attempts > 1)
    )

    retry_load_pass1: float | None = (
        sum(max(0, c.attempts - 1) for c in pass1_calls) / len(pass1_calls)
        if pass1_calls else None
    )
    retry_load_pass2: float | None = (
        sum(max(0, c.attempts - 1) for c in pass2_calls) / len(pass2_calls)
        if pass2_calls else None
    )

    # Cost split (#117 D-117-3/D-117-8): sums over PRICED calls only; calls
    # with token usage but no positive cost attribution (unpriced, or
    # failed-before-attribution — the #110 deferred item) count as unknown,
    # never as $0.
    def _cost_split(calls: list[PassCallMeasurement]) -> tuple[float | None, int | None]:
        if not calls:
            return None, None
        priced = sum(c.cost_usd for c in calls if c.cost_usd and c.cost_usd > 0)
        unknown = sum(
            1 for c in calls
            if (c.total_input_tokens + c.total_output_tokens) > 0
            and not (c.cost_usd and c.cost_usd > 0)
        )
        return priced, unknown

    cost_pass1, unknown_pass1 = _cost_split(pass1_calls)
    cost_pass2, unknown_pass2 = _cost_split(pass2_calls)

    diagnostic: dict = {
        "retry_load": retry_load,
        "token_overrun_rate": _rate(n_overrun, T),
        "repair_rung_rate": _rate(n_repair_rung, T),
        "semantic_pass_rate": semantic_pass_rate,
        "signal_noise_ratio": signal_noise_ratio,
        "quarantine_rate_pass1": _rate(n_quar_pass1, T_pass1),
        "quarantine_rate_pass2": _rate(n_quar_pass2, T_pass2),
        # Per-pass latency split (ms per 1M tokens of that pass) — combined
        # `latency` stays the scored KPI; these isolate where time is spent.
        "latency_pass1": _rate(latency_ms_pass1, T_pass1),
        "latency_pass2": _rate(latency_ms_pass2, T_pass2),
        # #117 per-pass recovery/retry splits + cost diagnostics.
        "recovery_rate_pass1": _rate(n_recovery_pass1, T_pass1),
        "recovery_rate_pass2": _rate(n_recovery_pass2, T_pass2),
        "retry_load_pass1": retry_load_pass1,
        "retry_load_pass2": retry_load_pass2,
        "cost_usd_pass1": cost_pass1,
        "cost_usd_pass2": cost_pass2,
        "cost_unknown_calls_pass1": unknown_pass1,
        "cost_unknown_calls_pass2": unknown_pass2,
    }

    return {"scored": scored, "diagnostic": diagnostic}


def compute_search_diagnostics(
    measurements: list[SearchPassMeasurement],
) -> dict:
    """#123 P3a.4 (§4.7) — the DEDICATED pass-1.5 diagnostic aggregation.

    Separate from compute_processing by contract (A15/H4): the processing
    KPIs keep their pass1+pass2 population; search measurements feed ONLY
    this aggregation — never a scored axis. All values are None when the
    population is empty (no searches ran / pre-P3a.4 run).

    Cost + tokens are LOWER BOUNDS over known data, never zero-coerced
    (B10): a no-response attempt contributes cost 0.0 and tokens None, and
    its count surfaces in cost_unknown_calls / input_token_unknown_attempts
    (the same attempts — a missing response makes both unknown).
    `latency_pass1_5` is the mean ms per search (not token-normalized —
    tokens may be unknown).
    """
    if not measurements:
        return {
            "calls_pass1_5": None,
            "attempts_pass1_5": None,
            "retries_pass1_5": None,
            "cost_usd_pass1_5": None,
            "cost_unknown_calls_pass1_5": None,
            "input_tokens_pass1_5": None,
            "input_token_unknown_attempts_pass1_5": None,
            "latency_pass1_5": None,
        }
    calls = sum(m.calls for m in measurements)
    attempts = sum(m.attempts for m in measurements)
    unknown = sum(m.input_token_unknown_attempts for m in measurements)
    known_tokens = [m.total_input_tokens for m in measurements
                    if m.total_input_tokens is not None]
    return {
        "calls_pass1_5": calls,                 # logical — one per search (B10)
        "attempts_pass1_5": attempts,           # StageRecord count, incl. no-response
        "retries_pass1_5": attempts - calls,
        "cost_usd_pass1_5": sum(m.cost_usd for m in measurements),
        "cost_unknown_calls_pass1_5": unknown,
        "input_tokens_pass1_5": sum(known_tokens) if known_tokens else None,
        "input_token_unknown_attempts_pass1_5": unknown,
        "latency_pass1_5": (
            sum(m.total_latency_ms for m in measurements) / len(measurements)),
    }
