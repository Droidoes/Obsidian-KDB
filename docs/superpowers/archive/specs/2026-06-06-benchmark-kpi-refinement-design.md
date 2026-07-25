# Benchmark KPI Refinement — run-9-driven (#109)

**Date:** 2026-06-06 · **Status:** 🟢 ratified (Joseph approved 2026-06-06, conversational)
**Depends on:** B3 framework `2026-06-05-benchmark-framework-design.md` (shipped, merged `610e2c8`) · KPI list `2026-06-05-benchmark-kpi-enumeration-brief.md` (v0.2).
**Ledger:** #109 (still open — this is a pre-calibration refinement, not closure).

---

## 0. Why this round

run-9 (`--emit-kpis`, deepseek-v4-flash, the framework's first real emission) produced clean,
well-formed measurements and exposed three things worth fixing **before** spending on the
multi-model cohort:

1. **`dangling_link_rate` is a degenerate scored KPI.** It rewards under-linking (one safe link → 0.0)
   and is trivially 0.0 on a sparse graph. Its only path to meaning was "a dense graph someday" —
   Joseph's call: that's not a near-term promotion candidate, so it's **dead weight**, not "watched."
2. **The graph family had no defensible scored KPI** once dangling goes. run-9's watched/diagnostic
   graph numbers (`entity_reuse 2.7%`, `connectivity 14.5%`, `search-key-resolution 24.6%`) are all
   confounded by **corpus selection + prior-graph density + empty-start** — none cleanly isolates
   model quality on a single run. The least-confounded of the candidates is **`entity_reuse`**
   (canonicalization/consolidation is a real model capability).
3. **Per-run output is thin.** Only `measurements.json` lands, in a bare-timestamp dir — losing the
   old model-prefixed naming and offering no human-readable view.

## 1. Decisions

### D1 — Delete `dangling_link_rate` entirely
Remove from `compiler/kpi/graph.py` (scored), from `KPI_LOWER_IS_BETTER` (score.py), and from the
emitted payload. **Not** demoted to watched/diagnostic: a metric whose value is purely hypothetical-
future is noise. (Reason it's coupled to D2: dangling was the *link-hygiene guardrail*; with it gone,
we must **not** score `link_density` either — raw density with no hygiene check rewards link-spam.)

### D2 — `entity_reuse` is the sole scored graph KPI (↑)
Move `entity_reuse` watched→scored. It's the best available model-quality signal (share of canonical
non-summary entities cited by ≥2 sources = consolidation vs. fragmentation). First higher-is-better
KPI → `KPI_LOWER_IS_BETTER["entity_reuse"] = False` (the table is the only touch-point; Borda already
honors direction).

**Acknowledged caveats** (recorded, not blocking): mildly gameable by over-merging distinct entities;
corpus-confounded. The 3-model cohort is the validation — if `entity_reuse` clusters tight across
models it was corpus-bound and we revisit.

**Explicitly NOT scored:**
- `link_density` → stays diagnostic (spam-reward, no hygiene guard after D1).
- `domain_breadth` → stays diagnostic. "Big-rock" domain categorization is something any competent
  model does from the source; its value reflects what the **corpus contains**, not model reasoning
  (Joseph). Scoring it would measure the sandbox.

### D5 — `score` becomes an incremental leaderboard (no fingerprint gate)
The one-shot `score <run-ids>` + same-`corpus_fingerprint` rejection gate is **replaced**. `score` now maintains a persistent **leaderboard file** (default `benchmark/scores/leaderboard.json`):
- `models`: `{ model_slug → latest run-dir }` — **one row per unique model slug** (`header.model`); no grouping by provider, **no `group_key`**.
- `ranking`: the last-computed Borda ranking (display only; recomputed every invocation).

`kdb-benchmark score <run-dir…>`: load the leaderboard (empty if absent) → for each incoming run dir, read its `measurements.json` header, set `models[header.model] = run-dir` (**latest replaces** an existing model) → read every listed run's `measurements.json` **live** → Borda-rank across all of them at **equal weight** → rewrite the leaderboard + a rendered table.

- **No `corpus_fingerprint` anywhere in scoring** — cross-run corpora are *assumed* to differ (every reset+run re-enriches stochastically); comparability is the **user's judgment**, not a gate.
- **Reset** = delete the leaderboard file → next `score` starts fresh.
- The leaderboard stores only run-dir **pointers** + the latest ranking. **No KPI values are copied or composed** — they live solely in each run's `measurements.json` and are re-read on every rank (no historical data store).
- Borda is **relative**: adding a model *or* re-running an existing one re-ranks the whole field (expected).
- `group_key` is **removed** from the emitted header, replaced by explicit `provider` + `model` (the score path keys on `model`).

### D3 — Add per-pass latency diagnostics
`latency_pass1`, `latency_pass2` (ms per 1M tokens, partitioned by `pass_`) added to processing
**diagnostics**. Combined `latency` stays the scored KPI (holistic end-to-end). The compute already
partitions calls + token totals by pass — trivial addition.

### D4 — Per-run dir: model-prefixed naming + rendered report
- Dir: `benchmark/runs/<model>-<run_id>/` (restores the pre-refactor convention, e.g.
  `deepseek-v4-flash-2026-06-06T09-59-00_EDT`). `header.run_id` stays the bare timestamp (the link
  back to the operational `<vault>/KDB/state/runs/<run_id>/`); the model prefix is for human browsing.
- Contents: `measurements.json` (unchanged shape) + **`report.md`** — the rendered KPI table
  (scored / watched / diagnostic, with the graph-confound caveats inline), generated at `--emit-kpis`
  time so each run dir is self-describing without running `score`.
- `kdb-benchmark score <dir-name…>` addresses each run by its dir name (`runs_root / <dir-name> /
  measurements.json`) and keys the leaderboard on `header.model` (see D5).

## 2. Resulting KPI structure

| family | scored | watched | diagnostic |
|---|---|---|---|
| **processing** | quarantine_rate ↓, intervention_burden ↓, latency ↓ | — | retry_load, token_overrun_rate, repair_rung_rate, semantic_pass_rate, signal_noise_ratio, quarantine_rate_pass1/pass2, **latency_pass1, latency_pass2** |
| **graph** | **entity_reuse ↑** | graph_connectivity, orphan_rate, entity_search_key_resolution | link_density, domain_breadth, belongs_to_coverage, domain_null_rate, supports_density |

## 3. Files

- `compiler/kpi/graph.py` — move `entity_reuse` scored→ (it currently lives in watched); delete `dangling_link_rate` block; watched loses entity_reuse + dangling never existed there; diagnostic unchanged.
- `compiler/kpi/score.py` — `KPI_LOWER_IS_BETTER`: drop `dangling_link_rate`, add `entity_reuse: False`; update docstring direction table.
- `compiler/kpi/processing.py` — add `latency_pass1`/`latency_pass2` diagnostics (partition `total_latency_ms` by pass, `_rate` over `T_pass1`/`T_pass2`).
- `compiler/kpi/report.py` (NEW) — `render_report(payload: dict) -> str`: markdown table from a measurements payload (title/metadata keyed on `header.model`/`provider`).
- `compiler/kpi/score.py` — also (D5) rename the per-model identifier field `group_key` → `model` in `borda_score`.
- `orchestrator/emit_kpis.py` — dir name `f"{model}-{run_id}"`; write `report.md` alongside `measurements.json`; (D5) emit `provider`+`model` in the header, drop `group_key`.
- `tools/benchmark/cli.py` (D5) — rewrite `_score_command` as the incremental leaderboard: `--leaderboard` arg (default `benchmark/scores/leaderboard.json`), drop the fingerprint gate + one-shot scorecard, key on `header.model`, persist `{models, ranking, weights, updated_at}`; `_score_command` helpers `_read_measurements` / `_scored_and_diag`; rename table column `group_key`→`model`; update module docstring.
- Tests: `compiler/tests/test_kpi_graph.py`, `test_kpi_score.py` (incl. `group_key`→`model`), `test_kpi_processing.py`, NEW `test_kpi_report.py`, `orchestrator/tests/test_kdb_orchestrate.py` (emit dir/report + `provider`/`model` header), `tools/benchmark/tests/test_score.py` (rewritten for leaderboard: fresh/incremental/rerun-replace/no-gate/reset).

## 4. Deferred (open, captured so it doesn't evaporate)

- **Corpus-independent model-quality KPI brainstorm** (broadened 2026-06-06, Joseph). We do **not** yet
  have a high-confidence KPI that isolates *model* quality from corpus selection / prior-graph density —
  not just for graph KPIs but across the board. `entity_reuse` is a placeholder-grade pick. The owed
  brainstorm: *"which KPIs are corpus-independent yet still discriminate model quality?"* — the deepest
  validity question for the whole benchmark. Run once multi-model spreads give us data to reason from.
- **Post-run-1 calibration** (unchanged from B3 §9): weights + promotion, gated on the cohort.

## 5. Validation
**All-fresh** 3-model cohort (each model: reset → `--emit-kpis` run; the reset forces full
recompile, so each run produces a current-schema `measurements.json` with `header.model`). Then
`kdb-benchmark score <the 3 dir-names>` builds the leaderboard → read watched/diagnostic spreads +
confirm `entity_reuse` actually discriminates. This run is calibration, not a final ranking.

> Pre-redesign runs (run-9/run-10, old `group_key` schema, no `header.model`) are **not scoreable** by
> the new `score` (it errors cleanly: "missing header.model"). The cohort must be all-fresh runs.
> The leaderboard stores run-dir *pointers*, so a referenced run dir must stay on disk; deleting one
> makes subsequent `score` error until that model is re-incorporated or the board is reset.

## 6. Next round — combined graph score + weight scheme (designed 2026-06-06; PENDING implementation)

Designed with Joseph after the 2-model cohort (gemini vs deepseek). **Supersedes D2's "`entity_reuse`
as the sole scored graph KPI"** — that was the interim shipped on `feat/benchmark-kpi-refine`. The
2-model data showed `entity_reuse` *alone* inverted the signal (ranked gemini's sparser graph above
deepseek's richer one); all four graph KPIs **read together** correctly say deepseek builds the better
graph. So the next round promotes all four into a **weighted combined graph score**.

### Rename `intervention_burden` → `recovery_rate`
Name matches contents: survivors that needed **retry or repair** to succeed (↓ lower-is-better; pairs
with `quarantine_rate`). **Drop `token_overrun` from the definition** — degraded-survival, not
retry/repair; it stays as the standalone `token_overrun_rate` diagnostic. New def: non-quarantined ∧
(`syntax_repaired ∨ slug_coerced ∨ attempts>1`).

### Scored set (4 graph KPIs promoted; processing ↓, graph ↑)
- processing: `quarantine_rate ↓`, `recovery_rate ↓`, `latency ↓`
- graph: `graph_connectivity ↑`, `link_density ↑`, `supports_density ↑`, `entity_reuse ↑`

The **combined graph score** = weighted Borda over the 4 graph KPIs (the graph 40% bucket), reported
explicitly per model. Weights are the *synthesis mechanism* for that score (not just a global balance).

### Weight scheme — calibration STARTING point (rationale-based, not fitted)
| term | within-bucket | of total |
|---|---|---|
| `quarantine_rate` ↓ | — | **0.40** |
| **graph (combined)** | — | **0.40** |
| — `graph_connectivity` ↑ | 35% | 0.14 |
| — `link_density` ↑ | 30% | 0.12 |
| — `supports_density` ↑ | 20% | 0.08 |
| — `entity_reuse` ↑ | 15% | 0.06 |
| `recovery_rate` ↓ | — | 0.10 |
| `latency` ↓ | — | 0.10 |

Flat dict for `borda_score`: `{quarantine_rate:.40, latency:.10, recovery_rate:.10,
graph_connectivity:.14, link_density:.12, supports_density:.08, entity_reuse:.06}` (Σ = 1.0).

**Rationale (the value system):** reliability (`quarantine` = unrecoverable failure) and graph quality
are co-equal and paramount (40/40); recovery (recoverable friction) and latency (speed — model
*selection* is cost-settled, so speed is a tiebreaker) are minor (10/10); 4:1 quarantine:recovery =
unrecoverable ≫ recoverable. Within graph: relationships + coherence (connectivity 35, link 30) over
raw volume (supports 20); `entity_reuse` smallest (15) because it's non-monotonic.

**Validation (non-circular):** these weights reproduce the *independent* read deepseek > gemini —
deepseek wins `quarantine` (40%) + 3 of 4 graph KPIs → wins overall, flipping the equal-weight gemini
result. Reproduced from principle, not reverse-fitted to make deepseek win.

**Tune with ≥3 models:**
- `supports_density` ↔ `link_density` likely correlate (both volume) → promotion-rule Spearman check;
  may merge into one volume term to avoid double-counting.
- `entity_reuse` non-monotonicity: at 6% it informs without inverting; cleaner long-term is a
  volume-normalized consolidation metric (then it earns more weight). The mechanism is the deliverable;
  the weight *values* are a starting point.

**Implementation:** promote the 3 graph KPIs to scored (`KPI_LOWER_IS_BETTER` += `False` entries);
rename `intervention_burden`→`recovery_rate` (drop `token_overrun` condition); set default weights;
compute + display an explicit combined graph score (graph-subset weighted Borda) alongside the overall
composite. The existing weighted `borda_score` already consumes the flat dict — minimal new mechanism.
