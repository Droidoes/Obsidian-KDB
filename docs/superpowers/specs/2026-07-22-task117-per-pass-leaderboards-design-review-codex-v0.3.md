# Task 117 Per-Pass Leaderboards — Codex Review of Spec v0.3

**Review date:** 2026-07-22  
**Reviewed spec:** `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md`  
**Verdict:** Revise before ratification

Spec v0.3 resolves the previous six findings well and is close to ratification. One remaining blocker, three contract clarifications, and one low-severity guarantee issue remain.

## Findings

### 1. High — Pass-1 completeness still cannot detect a missing sidecar

D-117-5 requires every existing non-skipped sidecar to load, but it does not reconcile the number of Pass-1 sidecars against `p1_attempted`.

`p1_attempted` increments before `enrich_one` runs. A crash or unexpected exception can therefore produce `p1_attempted = 36` with only 35 copied sidecars. All 35 existing files could load successfully, and the row would incorrectly remain ranked. The loader also excludes `enrich_skipped` records, so loaded-measurement count alone is insufficient.

Specify the Pass-1 reconciliation invariant explicitly:

```text
identified_pass1_sidecars == p1_attempted
loaded_pass1_measurements == p1_attempted - enrich_skipped_sidecars
unique source_id count == identified_pass1_sidecars
```

Add tests for a missing Pass-1 sidecar, malformed sidecar, and duplicate `source_id`. This is the remaining ratification blocker.

Evidence:

- Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:101`
- `p1_attempted` increment: `orchestrator/kdb_orchestrate.py:608`
- Measurement loader: `common/measurement.py:223`

### 2. Medium — eligibility still conflates noise gating with Pass-1 failure

`pass2_eligibility_rate = signal / p1_attempted` is useful, but it cannot distinguish intentional noise gating from failed enrichment. The corrected Qwen explanation is also not uniformly true across the selected cohort:

- Qwen: signal 28, noise 7, failures 1.
- Current Gemini: signal 29, noise 6, failures 1.

Thus Qwen's gap versus DeepSeek, GPT, and GLM is an additional failure, while its gap versus Gemini is an additional noise classification.

Keep eligibility, but add raw Pass-1 disposition columns:

```text
p1_noise
p1_failed = p1_attempted - signal - noise
```

Also define eligibility and measurement coverage as `None` when their denominator is zero.

Evidence:

- Coverage contract: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:96`
- Qwen header: `benchmark/runs/qwen3.6-flash-us-2026-07-21T00-51-24_EDT/run_state/measurement_header.json:8`
- Gemini header: `benchmark/runs/gemini-3.5-flash-2026-07-21T01-46-20_EDT/run_state/measurement_header.json:8`

### 3. Medium — ranked-row JSON does not locate the promised raw values

The unranked shape is now explicit, but the ranked-row contract still does not say where cost, unknown-cost count, eligibility, coverage, or raw per-pass KPI values are stored. The spec only says these values “persist in the JSON” and that the payload has per-row `measurement_source`.

Define one exact representation, preferably:

```json
{
  "ranking": [
    {
      "model": "...",
      "rank": 1,
      "measurement_source": "run_state_recomputed",
      "raw_values": {
        "quarantine_rate_pass1": 0.0,
        "cost_usd_pass1": 0.05,
        "cost_unknown_calls_pass1": 0
      }
    }
  ]
}
```

Using `raw_values` consistently for ranked and unranked rows gives consumers one stable contract.

Evidence:

- Cost contract: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:141`
- Pass-board payload contract: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:180`

### 4. Medium — the task ledger still describes the rejected fallback

The Task 117 ledger entry still promises a “measurements-diagnostic fallback otherwise,” contradicting v0.3's fail-closed design. It also calls the combined board “untouched,” whereas D-117-1 now correctly permits new raw diagnostic columns.

Because the ledger is a project tracking authority, synchronize that entry before ratification.

Evidence:

- Task ledger: `docs/TASKS.md:47`

### 5. Low — `updated_at` is not a strict generation identifier

D-117-10 says the shared timestamp makes mixed generations detectable, but `now_iso()` has second precision. Two invocations within one second can share the same value. The test plan also does not inject a mid-commit failure.

Either weaken the wording to “normally detectable under the single-user execution model,” or introduce a genuinely unique generation identifier. The simpler wording change is consistent with D22.

Evidence:

- Write-boundary contract: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:155`
- Timestamp implementation: `common/run_context.py:31`

## Conclusion

A small v0.3.1 should be sufficient rather than another architectural revision. Once the Pass-1 count reconciliation is explicit, there is no remaining structural reason to withhold ratification.

This was a read-only review; no implementation tests were run.
