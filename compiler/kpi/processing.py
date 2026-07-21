"""GT-free PROCESSING-family KPI computation over PassCallMeasurement lists.

compute_processing(header, calls) → {"scored": {...}, "diagnostic": {...}}

All rates are per 1M tokens unless noted.  Returns floats or None (never raises
on empty/zero-token input).  Pure function — no I/O.
"""
from __future__ import annotations

from common.measurement import PassCallMeasurement, RunMeasurementHeader


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
                      "latency_pass1", "latency_pass2"}

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
    }

    return {"scored": scored, "diagnostic": diagnostic}
