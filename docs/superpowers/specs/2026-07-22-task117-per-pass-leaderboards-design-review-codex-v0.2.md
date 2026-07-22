# Task 117 Per-Pass Leaderboards — Codex Review of Spec v0.2

**Review date:** 2026-07-22  
**Reviewed spec:** `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md`  
**Verdict:** Revise before ratification

Spec v0.2 is materially stronger, and all seven first-round findings were addressed conceptually. Four load-bearing issues remain, mostly second-order consequences of the revised design.

## Findings

### 1. High — the Pass-2 coverage definition is currently tautological, and the Qwen evidence is misstated

The spec says Qwen attempted 28 instead of 29 Pass-2 sources because Pass-1 classified one additional source as noise. In the current orchestrator, however, `p2_attempted` is assigned directly from `signal`, so `p2_attempted / signal` is always 100% when nonzero.

The actual Qwen counts are seven noise sources plus one `enrich_failed` source—not eight noise sources. The failed source was quarantined during Pass-1.

Recommended replacement metrics:

- `pass2_eligibility_rate = signal / p1_attempted`, exposing upstream gating and Pass-1 failures.
- `pass2_measurement_coverage = loaded_pass2_records / p2_attempted`, exposing telemetry completeness.

The spec should describe Qwen as having one additional Pass-1 failure, not one additional noise classification.

Evidence:

- Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:68`
- Assignment of `p2_attempted`: `orchestrator/kdb_orchestrate.py:970`
- Failed Qwen sidecar: `benchmark/runs/qwen3.6-flash-us-2026-07-21T00-51-24_EDT/run_state/pass1/Value Investing__Li Lu__Li Lu Lecture at Columbia Business School 2006.md.json:10`

### 2. High — `cost_usd = 0` does not reliably mean a free call

D-117-3 maps absent cost to `0.0`, while D-117-8 presents the sum as a prominent model-selection column. Existing telemetry uses zero both for genuinely skipped work and for calls where pricing was unavailable or the call failed before cost attribution.

There is already a current-cohort Gemini Pass-1 call with 10,960 tokens but `cost_usd: 0.0`. Therefore, the proposed Pass-1 sum can understate cost today.

Recommended contract:

- Project absent cost as `None`, not zero.
- Persist `cost_complete_pass1/2` or `cost_unknown_calls_pass1/2`.
- Render incomplete totals as `≥$X` or `$X + N unknown`, rather than as authoritative totals.
- Test failed and unpriced calls with nonzero token usage.

Evidence:

- Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:60`
- Gemini sidecar with nonzero tokens and zero cost: `benchmark/runs/gemini-3.5-flash-2026-07-21T01-46-20_EDT/run_state/pass1/Daily Notes__2026-05-28.md.json:10`

### 3. High — fail-closed handling does not cover partial `run_state`, and the unranked JSON shape is undefined

The spec handles a missing `run_state/` directory, but the loader tolerates missing pass directories by returning empty measurements. KPI emission also catches `copytree` failures, meaning a partially copied `run_state/` can exist.

Such a row could still receive a pro-rata score from the remaining KPIs, defeating the fail-closed intent.

The spec should define per-board completeness explicitly:

- The header parses successfully.
- The required pass directory and measurements exist.
- Loaded records reconcile with expected attempted and skipped counts.
- Required KPI inputs are present.
- Otherwise, the row is unranked.

It also needs an exact JSON schema for unranked rows. For example, keep `ranking` ranked-only and add:

```json
{
  "unranked": [
    {
      "model": "...",
      "run_dir": "...",
      "measurement_source": "...",
      "missing_kpis": ["..."],
      "raw_values": {}
    }
  ]
}
```

Evidence:

- Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:86`
- Measurement loader: `common/measurement.py:190`
- Best-effort `run_state` copy: `orchestrator/emit_kpis.py:152`

### 4. High — future diagnostic emission conflicts with the promise that the main board remains byte-identical

D-117-1 and D-117-7 promise unchanged main-board columns and contents, while D-117-3 says future measurement files will carry the new recovery, retry, and cost diagnostics. The current renderer automatically turns every non-scored diagnostic field into a leaderboard column.

Consequently, future enriched measurements will change `leaderboard.md` unless the main renderer filters these fields.

Spec v0.3 should choose one contract:

- Preserve byte-identical main output by explicitly excluding Task 117 diagnostics from its renderer; or
- State that main scoring and ranking remain unchanged, while raw diagnostic columns may expand.

The test should use a future-shaped measurement containing the new fields—not only legacy fixtures.

Evidence:

- Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md:49`
- Diagnostic-column rendering: `tools/benchmark/cli.py:94`

### 5. Medium — six-file atomicity is overstated

Precomputing all outputs guarantees that validation or rendering failures occur before writes. Atomic replacement guarantees that each individual file is never torn. It does not make six replacements transactional: failure during the fourth replacement leaves a mixed generation.

Recommended wording for D-117-10:

- A pre-write failure leaves every existing artifact untouched.
- Each file replacement is individually atomic.
- A mid-commit failure may leave mixed generations.
- The shared generation timestamp detects that condition, and rerunning heals it.

This is preferable to introducing a manifest pointer or two-phase commit for six report files.

### 6. Low — effective weights should not be persisted as rounded decimals

`.667 + .167 + .167 = 1.001`. Compute and store full-precision normalized weights—`2/3`, `1/6`, and `1/6`—and round only for Markdown display.

## Conclusion

The downstream-outcome labeling, competition ranking, token-weighted recombination, graph-prose suppression, and North Star gate now look sound.

One focused spec v0.3 should address the four high-severity contracts before the blueprint is ratified.
