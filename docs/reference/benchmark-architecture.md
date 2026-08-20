# Benchmark Architecture — Scoring Reference

Moved verbatim from `docs/CODEBASE_OVERVIEW.md` §7.4–§7.7 on 2026-08-19 (Task #146 housekeeping): the overview stays the living map; this static scoring reference lives here. Section numbers are the original overview numbering. §7.1–§7.3 (package layout, how to run, KPI families) remain in the overview.

### 7.4 Weights & penalty (all PINNED)

**Top-level composite** (`kdb_graph_compiler.kpi.score.TOP_WEIGHTS`):

| Axis | Weight |
|---|---|
| `quarantine_rate` | 40% |
| `graph_score` (combined) | 40% |
| `recovery_rate` | 10% |
| `latency` | 10% |

**Within-graph** (`kdb_graph_compiler.kpi.score.GRAPH_WEIGHTS`):

| KPI | Weight |
|---|---|
| `graph_connectivity` | 35% |
| `link_density` | 30% |
| `supports_density` | 20% |
| `entity_reuse` | 15% |

Weighting is hierarchical: the four graph KPIs first combine into one `graph_score`, then `graph_score` enters the composite as the single 40% term. This preserves the 40/40/10/10 split exactly even when a model is missing a graph KPI (pro-rata renormalization happens within each family, not across the flat composite).

**Weak-spot penalty** (leaderboard-only): **τ=0.5 PINNED**, **λ=0.10 PINNED**. Operates on the four composite axes (`quarantine_rate` / `recovery_rate` / `latency` / `graph_score` Borda values — equal treatment). A model with a glaring weak composite axis (weakest < τ) loses up to 10 pts on the 0–100 headline score: `penalty = λ · max(0, (τ − weakest) / τ)`. Baseline-1 validated the parameters: deepseek penalized on latency, gemini on quarantine, qwen on recovery — each hitting the cap.

### 7.5 Data flow

```
~/Obsidian/Vault-in-place-test-run   (36-source sandbox)
        │
        ▼
kdb-orchestrate --emit-kpis --model <id>   (one per candidate; reset sandbox between runs)
        │  Pass-1 + Pass-2 + graph build + graph-KPI computation
        ▼
benchmark/runs/<run-id>/measurements.json   (header + processing.scored/watched + graph.scored/watched/diagnostic)
benchmark/runs/<run-id>/report.md           (per-run human summary)
        │
        ▼ (collect one run-id per candidate model)
kdb-benchmark score <run-id…>
        │  Borda rank → hierarchical composite → penalty → leaderboards (§7.7)
        ▼
benchmark/scores/leaderboard.json            (+ .md)
benchmark/scores/leaderboard-pass1.json      (+ .md)   # #117
benchmark/scores/leaderboard-pass2.json      (+ .md)   # #117
```

### 7.6 Promotion rule

`tools/benchmark/promotion.py` evaluates watched diagnostics for promotion to the scored set after each multi-model cohort. A watched KPI promotes when **all three** hold:

1. **CoV > 0.2** — varies meaningfully across models
2. **Q1 > ε** — the bulk of values are non-trivially non-zero
3. **max |Spearman| vs scored < 0.7** — not redundant with any already-scored KPI

Promotion is advisory (human decision, not automatic). Prime candidates from baseline-1: `entity_search_key_resolution`, `orphan_rate`.

### 7.7 Per-pass leaderboards (#117, spec v0.3.1)

`kdb-benchmark score` writes **three** boards per invocation: the combined board (§7.4 scoring, unchanged) plus `leaderboard-pass1.{json,md}` and `leaderboard-pass2.{json,md}` (filenames derive from the `--leaderboard` stem). Rationale: model performance is pass-specific (own prompt/contract/failure modes); the split boards are the evidence base for a later cheap-Pass-1 / quality-Pass-2 model split (#118).

- **Recompute, don't re-run.** Per-pass processing KPIs are recomputed at score time from each row's `run_state/` (`load_run_measurements` → `compute_processing`); graph KPIs come from `measurements.json` (emit-time graph state, not reproducible at score time). No pipeline change, no re-runs.
- **Same machinery, pass-scoped inputs.** Pass KPIs map onto the canonical processing names and go through the §6 `score_models` path: Pass-1 = 3 processing KPIs (pro-rata 4:1:1 + weak-spot penalty, graph term inactive); Pass-2 = 3 processing + 4 graph KPIs (identical 40/40/10/10 shape). The Pass-2 board is explicitly a **downstream-outcome** board (Pass-1 gating/failures decide Pass-2 coverage — e.g. Qwen's 28 vs 29) — isolated per-pass attribution waits on #118. It carries `pass2_eligibility_rate` (`signal/p1_attempted`), `pass2_measurement_coverage` (`loaded/p2_attempted`), and `p1_noise`/`p1_failed` disposition columns.
- **Cost is a selection column, never a Borda axis.** `cost_usd_pass1/2` render prominently; `cost_unknown_calls > 0` ⇒ `≥$X (+N unknown)` (zero cost can mean unpriced/failed, not free — cf. #110 deferred item).
- **Fail closed.** A row is ranked on a pass board only if its `run_state/` passes the per-board completeness contract (header parses; Pass-1 sidecar count reconciles with `p1_attempted` incl. skipped; Pass-2 records == `p2_attempted`; required KPI inputs present). Incomplete rows render `unranked` with `measurement_source` + `missing_kpis` — never pro-rata on missing evidence.
- **Honest metadata.** Pass boards persist `board_scope`, full-precision `effective_top_weights` (Pass-1: 2/3, 1/6, 1/6, graph 0.0), `unranked[]`, and per-row `raw_values` (one contract for ranked + unranked rows). Competition ranking: tied composites share a rank (1, 1, 3); the main board keeps sequential ranks.
- **Write boundary.** All three boards are computed/validated/rendered before any write; each file is replaced individually-atomically under one shared `updated_at` (mixed-generation detection is best-effort under the single-user model; rerun heals).

Main-board contract: scored KPIs, ranking, composite, and scored columns unchanged; its data-driven raw-values table may additionally surface the #117 diagnostics on newly emitted runs. Spec: `docs/superpowers/archive/specs/2026-07-22-task117-per-pass-leaderboards-design.md` (v0.3.1, Codex 3 rounds).
