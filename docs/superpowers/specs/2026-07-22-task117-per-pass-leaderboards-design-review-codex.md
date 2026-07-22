# Task #117 — Per-Pass Leaderboards Design Review (Codex)

**Reviewed:** 2026-07-22  
**Artifact:** `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md` v0.1  
**Verdict:** Revise before ratification

The split-board direction is sound, but v0.1 has four material correctness gaps.

## Findings

### 1. High — The Pass-1 board cannot answer the stated cost question

The motivation asks whether a "cost-effective model" can handle Pass-1, but the
composite contains only quarantine, recovery, and latency (spec lines 14 and 43).
In the real cohort, DeepSeek Pass-1 cost about `$0.050`, versus GPT-5.4-mini at
`$0.306`, yet the proposed composite favors GPT because monetary cost is
invisible. `cost_usd` exists in both pass sidecars but is absent from
`PassCallMeasurement` (`common/measurement.py:20`).

**Required amendment:** Either redefine the board as reliability/throughput-only,
or surface `cost_usd_pass1/2` prominently. The recommended path is to keep cost
outside the quality composite but make it a first-class selection column.

### 2. High — The Pass-2 board is conditional on Pass-1, not an isolated Pass-2 measurement

Pass-1 determines which sources reach Pass-2 and supplies enrichment/context;
graph KPIs therefore reflect both passes. The current cohort already demonstrates
unequal coverage: Qwen has 28 Pass-2 calls while the other current rows have 29.
Calling graph structure solely "Pass-2's authored artifact" overstates attribution
(spec line 48).

**Required amendment:** Label it a **Pass-2 downstream-outcome board**, include
`p2_attempted / signal` coverage, and state that causal Pass-2 model attribution
remains unavailable until #118 supplies controlled split-model runs.

### 3. High — The fallback silently compares different scoring contracts

Rows with `run_state/` receive three processing axes; fallback rows lack recovery
and have that weight redistributed pro-rata (spec line 51). Missing recovery also
removes it from the weak-spot penalty (`compiler/kpi/score.py:145`). Such rows can
rank more favorably simply because evidence is missing.

**Required amendment:** Fail closed for ranking incomplete rows. Optionally render
fallback rows as `unranked`, with `measurement_source` and `missing_kpis`. Since
every current row has `run_state/`, permissive fallback provides little immediate
value.

### 4. High — Pass-1 weight metadata and rendering would be misleading

`score_models()` always returns the canonical graph-inclusive weights
(`compiler/kpi/score.py:211`); the renderer always prints graph weight and
graph-score explanatory text (`tools/benchmark/cli.py:63`, `:118`). Merely hiding
the graph column does not make the Pass-1 board honest.

**Required amendment:** Persist `board_scope` and `effective_top_weights`. For
Pass-1 these are approximately `.667/.167/.167`, with graph explicitly inactive.
Suppress all graph-specific header/footer prose.

### 5. Medium — "Honest ties" still receive arbitrary distinct ranks

The scorer returns `0.5` for an all-equal KPI, but the CLI assigns sequential
ranks after sorting equal composites (`tools/benchmark/cli.py:416`). Equal models
can therefore display as ranks 1, 2, 3 based on insertion order.

**Required amendment:** Define competition ranking for pass boards—equal
composites share a rank—and test the displayed `rank`, not only the `0.5` Borda
value.

### 6. Medium — The recombination test is underspecified mathematically

Per-pass normalized rates do not add. The test at spec line 87 should verify:

```text
combined_rate = (pass1_rate × pass1_tokens + pass2_rate × pass2_tokens)
                / (pass1_tokens + pass2_tokens)
```

`retry_load` needs the analogous call-count-weighted formula.

### 7. Medium — Six output files need an explicit consistency boundary

The design promises all boards use identical row pointers, but does not define
failure behavior during recompute/render/write.

**Required amendment:** Validate and render all three boards before any write,
use one shared `updated_at`/generation ID, atomically replace each artifact, and
define how pass filenames derive from a custom `--leaderboard` path.

## Required Process Gate

The task-ledger entry exists, but North Star §7 still documents only the combined
board. After revising and ratifying the spec, update `docs/CODEBASE_OVERVIEW.md`
before implementation. The spec should also record at least the rejected
alternative to score-time recomputation and its tradeoff.

## Verification

- `compiler/tests/test_kpi_processing.py` and
  `tools/benchmark/tests/test_score.py` are green on the reviewed baseline.
- The review used the current 2026-07-21 cohort's persisted `run_state/` evidence.
- No implementation conclusions depend on re-running either LLM pass.
