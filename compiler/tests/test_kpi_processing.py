"""TDD: compute_processing KPI over PassCallMeasurement lists (#109).

Fixture design
--------------
Five calls mixing pass1/pass2, clean/repaired/retried/quarantined/overrun with
known token totals so every scored + diagnostic value can be computed as
integer-fraction literals.

  C1: pass1, clean, attempts=1, in=500, out=200, lat=100
  C2: pass1, syntax_repaired+retried (attempts=2), in=600, out=300, lat=200
  C3: pass2, clean, semantic_ok=True, in=400, out=100, lat=50
  C4: pass2, quarantined, syntax_repaired (excluded from recovery), in=300, out=150, lat=80
  C5: pass2, slug_coerced+token_overrun, semantic_ok=False, in=200, out=100, lat=30

T (all tokens) = 700+900+500+450+300 = 2850
N = 5

Scored
------
quarantine_rate      = 1 * 1e6 / 2850          (C4 only)
recovery_rate  = 2 * 1e6 / 2850          (C2, C5 — C4 excluded as quarantined)
latency              = (100+200+50+80+30)*1e6/2850 = 460*1e6/2850

Diagnostic
----------
retry_load            = 1/5 = 0.2              (C2 has 1 extra attempt)
token_overrun_rate    = 1*1e6/2850             (C5)
repair_rung_rate      = 3*1e6/2850             (C2, C4, C5 — quarantine not excluded here)
semantic_pass_rate    = 0.5                    (C3=True, C5=False; C4 has None → excluded)
signal_noise_ratio    = 40/50 = 0.8           (header: signal=40, scanned=50)
quarantine_rate_pass1 = 0*1e6/1600 = 0.0      (0 quarantined in pass1; pass1 T=700+900=1600)
quarantine_rate_pass2 = 1*1e6/1250 = 800.0    (C4 quarantined; pass2 T=500+450+300=1250)
"""
from __future__ import annotations

import pytest

from common.measurement import PassCallMeasurement, RunMeasurementHeader
from compiler.kpi.processing import compute_processing


# ---------------------------------------------------------------------------
# Helper to build PassCallMeasurement without repeating every field
# ---------------------------------------------------------------------------

def _call(
    *,
    pass_: str,
    final_status: str = "clean",
    attempts: int = 1,
    syntax_repaired: bool = False,
    slug_coerced: bool = False,
    token_overrun: bool = False,
    boundary_recovered: bool = False,
    total_input_tokens: int,
    total_output_tokens: int,
    total_latency_ms: int,
    semantic_ok: bool | None = None,
    cost_usd: float | None = None,
) -> PassCallMeasurement:
    return PassCallMeasurement(
        run_id="run-test",
        source_id="KDB/raw/foo.md",
        pass_=pass_,
        provider="anthropic",
        model="claude-test",
        prompt_version="v1",
        final_status=final_status,
        attempts=attempts,
        syntax_repaired=syntax_repaired,
        slug_coerced=slug_coerced,
        token_overrun=token_overrun,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_latency_ms=total_latency_ms,
        call_count=attempts,
        final_attempt_index=attempts,
        source_words=0,
        parse_ok=(final_status != "quarantined"),
        schema_ok=(final_status != "quarantined"),
        semantic_ok=semantic_ok,
        boundary_recovered=boundary_recovered,
        cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

C1 = _call(pass_="pass1", final_status="clean",       attempts=1, total_input_tokens=500, total_output_tokens=200, total_latency_ms=100)
C2 = _call(pass_="pass1", final_status="clean",       attempts=2, syntax_repaired=True,   total_input_tokens=600, total_output_tokens=300, total_latency_ms=200)
C3 = _call(pass_="pass2", final_status="clean",       attempts=1, total_input_tokens=400, total_output_tokens=100, total_latency_ms=50,  semantic_ok=True)
C4 = _call(pass_="pass2", final_status="quarantined", attempts=1, syntax_repaired=True,   total_input_tokens=300, total_output_tokens=150, total_latency_ms=80,  semantic_ok=None)
C5 = _call(pass_="pass2", final_status="clean",       attempts=1, slug_coerced=True, token_overrun=True, total_input_tokens=200, total_output_tokens=100, total_latency_ms=30, semantic_ok=False)

ALL_CALLS = [C1, C2, C3, C4, C5]

HEADER = RunMeasurementHeader(
    run_id="run-test",
    corpus_fingerprint="abc123",
    pass1_prompt_version="v1",
    pass2_prompt_version="v1",
    scanned=50,
    to_compile=45,
    signal=40,
    noise=10,
    p1_attempted=30,
    p2_attempted=30,
)

T = 2850  # total tokens across all calls
N = 5


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputeProcessingStructure:
    """Output has exactly the expected top-level keys and sub-keys."""

    def test_returns_scored_and_diagnostic_keys(self):
        result = compute_processing(HEADER, ALL_CALLS)
        assert set(result.keys()) == {"scored", "diagnostic"}

    def test_scored_has_exactly_three_keys(self):
        result = compute_processing(HEADER, ALL_CALLS)
        assert set(result["scored"].keys()) == {
            "quarantine_rate",
            "recovery_rate",
            "latency",
        }

    def test_diagnostic_has_exactly_seventeen_keys(self):
        result = compute_processing(HEADER, ALL_CALLS)
        assert set(result["diagnostic"].keys()) == {
            "retry_load",
            "token_overrun_rate",
            "repair_rung_rate",
            "semantic_pass_rate",
            "signal_noise_ratio",
            "quarantine_rate_pass1",
            "quarantine_rate_pass2",
            "latency_pass1",
            "latency_pass2",
            # #117 per-pass splits + cost
            "recovery_rate_pass1",
            "recovery_rate_pass2",
            "retry_load_pass1",
            "retry_load_pass2",
            "cost_usd_pass1",
            "cost_usd_pass2",
            "cost_unknown_calls_pass1",
            "cost_unknown_calls_pass2",
        }


class TestScoredKPIs:
    """Each scored KPI matches its hand-computed value."""

    def setup_method(self):
        self.result = compute_processing(HEADER, ALL_CALLS)
        self.scored = self.result["scored"]

    def test_quarantine_rate(self):
        # 1 quarantined (C4) × 1e6 / 2850
        expected = 1 * 1e6 / T
        assert self.scored["quarantine_rate"] == pytest.approx(expected)

    def test_recovery_rate(self):
        # Non-quarantined that needed retry or repair: C2 (retry+syntax_repair),
        # C5 (slug_coerced) → 2.  C4 is quarantined → excluded.  token_overrun
        # is NOT a recovery trigger (§6) — C5 still counts via slug_coerced.
        expected = 2 * 1e6 / T
        assert self.scored["recovery_rate"] == pytest.approx(expected)

    def test_token_overrun_alone_is_not_recovery(self):
        # §6 behavior change: a survivor that ONLY hit the token ceiling (no
        # retry, no repair) is NOT counted as recovery — token_overrun was
        # dropped from the definition (it remains its own diagnostic).
        overrun_only = _call(
            pass_="pass2", final_status="clean", attempts=1, token_overrun=True,
            total_input_tokens=100, total_output_tokens=100, total_latency_ms=10,
        )
        result = compute_processing(HEADER, [overrun_only])
        assert result["scored"]["recovery_rate"] == 0.0
        # but it still shows up in the token_overrun_rate diagnostic
        assert result["diagnostic"]["token_overrun_rate"] == pytest.approx(1 * 1e6 / 200)

    def test_latency(self):
        # sum latency = 100+200+50+80+30 = 460 ms × 1e6 / 2850
        expected = 460 * 1e6 / T
        assert self.scored["latency"] == pytest.approx(expected)


class TestDiagnosticKPIs:
    """Each diagnostic KPI matches its hand-computed value."""

    def setup_method(self):
        self.result = compute_processing(HEADER, ALL_CALLS)
        self.diag = self.result["diagnostic"]

    def test_retry_load(self):
        # sum extra attempts = 0+1+0+0+0 = 1; N=5 → 0.2
        assert self.diag["retry_load"] == pytest.approx(0.2)

    def test_token_overrun_rate(self):
        # C5 only → 1 × 1e6 / 2850
        expected = 1 * 1e6 / T
        assert self.diag["token_overrun_rate"] == pytest.approx(expected)

    def test_repair_rung_rate(self):
        # syntax_repaired or slug_coerced: C2, C4, C5 → 3 (quarantined NOT excluded for rung rate)
        expected = 3 * 1e6 / T
        assert self.diag["repair_rung_rate"] == pytest.approx(expected)

    def test_semantic_pass_rate(self):
        # P2 with semantic_ok not None: C3(True), C5(False); C4 has None → excluded
        # mean = (1+0)/2 = 0.5
        assert self.diag["semantic_pass_rate"] == pytest.approx(0.5)

    def test_signal_noise_ratio(self):
        # header.signal=40, header.scanned=50 → 0.8
        assert self.diag["signal_noise_ratio"] == pytest.approx(0.8)

    def test_quarantine_rate_pass1(self):
        # pass1 calls: C1, C2; quarantined=0; pass1 T=700+900=1600
        # 0 * 1e6 / 1600 = 0.0
        assert self.diag["quarantine_rate_pass1"] == pytest.approx(0.0)

    def test_quarantine_rate_pass2(self):
        # pass2 calls: C3, C4, C5; quarantined=C4; pass2 T=500+450+300=1250
        # 1 * 1e6 / 1250 = 800.0
        assert self.diag["quarantine_rate_pass2"] == pytest.approx(800.0)

    def test_latency_pass1(self):
        # pass1 latency = 100+200 = 300 ms; pass1 T=1600 → 300 * 1e6 / 1600
        assert self.diag["latency_pass1"] == pytest.approx(300 * 1e6 / 1600)

    def test_latency_pass2(self):
        # pass2 latency = 50+80+30 = 160 ms; pass2 T=1250 → 160 * 1e6 / 1250
        assert self.diag["latency_pass2"] == pytest.approx(160 * 1e6 / 1250)


class TestInterventionDisjointFromQuarantine:
    """A quarantined call that also has syntax_repaired must NOT count in recovery_rate."""

    def test_quarantined_with_repair_excluded_from_recovery(self):
        # C4 is quarantined AND syntax_repaired; it should count in quarantine_rate
        # but NOT in recovery_rate.
        result = compute_processing(HEADER, ALL_CALLS)
        scored = result["scored"]
        # quarantine_rate includes C4
        assert scored["quarantine_rate"] == pytest.approx(1 * 1e6 / T)
        # recovery_rate must be exactly 2 (C2 + C5), not 3
        assert scored["recovery_rate"] == pytest.approx(2 * 1e6 / T)


class TestEdgeCaseTZero:
    """When T==0, all per-token rates return None; retry_load still works if N>0."""

    def setup_method(self):
        # A call with zero tokens
        zero_call = _call(
            pass_="pass2",
            final_status="clean",
            total_input_tokens=0,
            total_output_tokens=0,
            total_latency_ms=0,
            semantic_ok=True,
        )
        self.result = compute_processing(HEADER, [zero_call])
        self.scored = self.result["scored"]
        self.diag = self.result["diagnostic"]

    def test_quarantine_rate_is_none(self):
        assert self.scored["quarantine_rate"] is None

    def test_recovery_rate_is_none(self):
        assert self.scored["recovery_rate"] is None

    def test_latency_is_none(self):
        assert self.scored["latency"] is None

    def test_token_overrun_rate_is_none(self):
        assert self.diag["token_overrun_rate"] is None

    def test_repair_rung_rate_is_none(self):
        assert self.diag["repair_rung_rate"] is None

    def test_quarantine_rate_pass1_is_none_when_no_pass1_tokens(self):
        # No pass1 calls → pass1 T=0 → None
        assert self.diag["quarantine_rate_pass1"] is None

    def test_quarantine_rate_pass2_not_none(self):
        # pass2 call has 0 tokens → T_pass2=0 → None
        assert self.diag["quarantine_rate_pass2"] is None

    def test_retry_load_not_none(self):
        # N=1, retry_load = 0 / 1 = 0.0
        assert self.diag["retry_load"] == pytest.approx(0.0)


class TestEdgeCaseNZero:
    """Empty call list returns zeros/None gracefully."""

    def setup_method(self):
        self.result = compute_processing(HEADER, [])
        self.scored = self.result["scored"]
        self.diag = self.result["diagnostic"]

    def test_scored_all_none(self):
        assert self.scored["quarantine_rate"] is None
        assert self.scored["recovery_rate"] is None
        assert self.scored["latency"] is None

    def test_retry_load_is_none_when_n_zero(self):
        assert self.diag["retry_load"] is None

    def test_semantic_pass_rate_none_when_no_eligible_calls(self):
        assert self.diag["semantic_pass_rate"] is None

    def test_signal_noise_ratio_still_works(self):
        # Depends only on header, not calls
        assert self.diag["signal_noise_ratio"] == pytest.approx(0.8)


class TestEdgeCaseNoSemanticCalls:
    """semantic_pass_rate is None when no P2 calls have semantic_ok not None."""

    def test_no_eligible_semantic_calls(self):
        calls = [
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50, total_latency_ms=10),
            _call(pass_="pass2", total_input_tokens=200, total_output_tokens=80, total_latency_ms=20, semantic_ok=None),
        ]
        result = compute_processing(HEADER, calls)
        assert result["diagnostic"]["semantic_pass_rate"] is None


class TestEdgeCaseScannedZero:
    """signal_noise_ratio is None when header.scanned==0."""

    def test_signal_noise_ratio_none_when_scanned_zero(self):
        header_zero = RunMeasurementHeader(
            run_id="run-test",
            corpus_fingerprint="abc",
            pass1_prompt_version="v1",
            pass2_prompt_version="v1",
            scanned=0,
            to_compile=0,
            signal=0,
            noise=0,
            p1_attempted=0,
            p2_attempted=0,
        )
        result = compute_processing(header_zero, [])
        assert result["diagnostic"]["signal_noise_ratio"] is None


class TestBoundaryRecovered:
    """#114 parse-stage recovery: a boundary-recovered call with no other
    repair/retry signal must count in BOTH recovery_rate and repair_rung_rate."""

    def test_boundary_recovered_counts_in_recovery_and_repair_rung(self):
        recovered = _call(
            pass_="pass2", final_status="repaired", attempts=1,
            syntax_repaired=False, slug_coerced=False, boundary_recovered=True,
            total_input_tokens=400, total_output_tokens=100, total_latency_ms=50,
            semantic_ok=True,
        )
        result = compute_processing(HEADER, [recovered])
        T_single = 400 + 100  # 500
        assert result["scored"]["recovery_rate"] == pytest.approx(1 * 1e6 / T_single)
        assert result["diagnostic"]["repair_rung_rate"] == pytest.approx(1 * 1e6 / T_single)


class TestRepromptOnlyRecovery:
    """Fix 1 + Fix 2 regression guard (#111 retry-telemetry):
    a re-prompt-only recovery (schema/semantic retry, no in-place repair)
    must be visible in recovery_rate and retry_load.

    Prior to Fix 1, from_pass2 set attempts=model_response.attempts (1),
    and the KPI layer saw attempts==1 → neither recovery_rate nor retry_load
    counted this call.  After Fix 1, attempts=max(final_attempt_index,
    model_response.attempts) = max(2, 1) = 2 → both KPIs fire correctly.
    """

    def test_reprompt_only_recovery_rate_positive(self):
        """A non-quarantined call with attempts==2 (no repair flags) is recovery."""
        reprompt = _call(
            pass_="pass2", final_status="retried", attempts=2,
            total_input_tokens=400, total_output_tokens=100, total_latency_ms=50,
            semantic_ok=True,
        )
        result = compute_processing(HEADER, [reprompt])
        T_single = 400 + 100  # 500
        assert result["scored"]["recovery_rate"] == pytest.approx(1 * 1e6 / T_single)

    def test_reprompt_only_retry_load_positive(self):
        """A call with attempts==2 contributes 1 extra attempt → retry_load>0."""
        reprompt = _call(
            pass_="pass2", final_status="retried", attempts=2,
            total_input_tokens=400, total_output_tokens=100, total_latency_ms=50,
            semantic_ok=True,
        )
        result = compute_processing(HEADER, [reprompt])
        # retry_load = sum(max(0, c.attempts - 1)) / N = 1 / 1 = 1.0
        assert result["diagnostic"]["retry_load"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Task #117 — per-pass splits (recovery / retry) + cost diagnostics
# ---------------------------------------------------------------------------

class TestPerPassSplits:
    """Fixture math (C1..C5 from the module docstring):
      pass1: C1 clean (T=700), C2 repaired+retried (T=900)   → T_pass1=1600
      pass2: C3 clean (T=500), C4 quarantined (T=450),
             C5 slug_coerced+overrun (T=300)                  → T_pass2=1250
    """

    def test_recovery_rate_pass1(self):
        r = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        # C2 only: 1 * 1e6 / 1600
        assert r["recovery_rate_pass1"] == pytest.approx(1e6 / 1600)

    def test_recovery_rate_pass2(self):
        r = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        # C5 only (C4 quarantined-excluded): 1 * 1e6 / 1250
        assert r["recovery_rate_pass2"] == pytest.approx(1e6 / 1250)

    def test_token_weighted_recombination(self):
        r = compute_processing(HEADER, ALL_CALLS)
        combined = r["scored"]["recovery_rate"]          # scored tier, not diagnostic
        d = r["diagnostic"]
        recombined = (d["recovery_rate_pass1"] * 1600
                      + d["recovery_rate_pass2"] * 1250) / (1600 + 1250)
        assert combined == pytest.approx(recombined)

    def test_retry_load_pass_split_and_recombination(self):
        d = compute_processing(HEADER, ALL_CALLS)["diagnostic"]
        assert d["retry_load_pass1"] == pytest.approx(1 / 2)   # C2: 1 extra / 2 calls
        assert d["retry_load_pass2"] == pytest.approx(0.0)
        assert d["retry_load"] == pytest.approx(
            (d["retry_load_pass1"] * 2 + d["retry_load_pass2"] * 3) / 5)

    def test_empty_pass_yields_none(self):
        d = compute_processing(HEADER, [c for c in ALL_CALLS
                                        if c.pass_ == "pass1"])["diagnostic"]
        assert d["recovery_rate_pass2"] is None
        assert d["retry_load_pass2"] is None
        assert d["cost_usd_pass2"] is None
        assert d["cost_unknown_calls_pass2"] is None


class TestCostDiagnostics:
    def _calls_with_cost(self):
        return [
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50,
                  total_latency_ms=10, cost_usd=0.01),   # priced
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50,
                  total_latency_ms=10, cost_usd=0.0),    # tokens, no cost → unknown
            _call(pass_="pass1", total_input_tokens=100, total_output_tokens=50,
                  total_latency_ms=10, cost_usd=None),   # absent → unknown
            _call(pass_="pass1", total_input_tokens=0, total_output_tokens=0,
                  total_latency_ms=0, cost_usd=None),    # no tokens → not unknown
            _call(pass_="pass2", total_input_tokens=200, total_output_tokens=100,
                  total_latency_ms=10, cost_usd=0.30),
        ]

    def test_cost_sums_priced_calls_only(self):
        d = compute_processing(HEADER, self._calls_with_cost())["diagnostic"]
        assert d["cost_usd_pass1"] == pytest.approx(0.01)
        assert d["cost_usd_pass2"] == pytest.approx(0.30)

    def test_unknown_counts_unpriced_token_calls(self):
        d = compute_processing(HEADER, self._calls_with_cost())["diagnostic"]
        assert d["cost_unknown_calls_pass1"] == 2      # 0.0-with-tokens + None
        assert d["cost_unknown_calls_pass2"] == 0
