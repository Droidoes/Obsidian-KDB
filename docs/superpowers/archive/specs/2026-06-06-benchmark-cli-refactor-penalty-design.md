# kdb-benchmark CLI Refactor + Weak-Spot Penalty — Design

**Date:** 2026-06-06
**Status:** Ratified (brainstorm complete; ready for implementation plan)
**Task:** #109 follow-on (CLI consolidation + leaderboard penalty)
**Supersedes operationally:** the legacy Task #5 benchmark engine (#30/#31/#22/#33/#42/#46)

---

## 1. Context & Goal

`tools/benchmark/cli.py` currently hosts **two disjoint engines**:

| | Legacy `#5` run engine | `#109` score engine |
|---|---|---|
| Entry | `kdb-benchmark --models X` (`_main_run`) | `kdb-benchmark score <dirs>` (`_score_command`) |
| Modules | `runner` + `scorer` + `scorecard` + `registry` (~1,900 LOC) | `cli._score_command` + `compiler/kpi/*` + `orchestrator/emit_kpis` + `promotion` |
| Measures | S0 / M1–M7 fidelity dimensions, per-run + final scorecard merge | quarantine / recovery / latency / graph_score Borda leaderboard |
| Fires API? | yes (compiles every source itself) | no (reads `measurements.json` from `kdb-orchestrate --emit-kpis`) |

The legacy engine is a **self-contained island**: only its own modules and tests import `runner`/`scorer`/`scorecard`/`registry`. Nothing in `orchestrator/`, `compiler/`, or the new `score` path depends on it. The live workflow is `kdb-orchestrate … --emit-kpis` → `kdb-benchmark score`; the `--models` path is no longer in that loop.

The `--help` defect (score hidden behind a positional sniff in `main()`, help leading with the superseded engine) is a *symptom* of carrying two engines.

**Goal.** Retire the legacy engine; leave `kdb-benchmark` single-purpose and honest; and add the one thing worth carrying forward from the old engine — a penalty that punishes a lopsided model with a glaring weak spot — adapted to the all-Borda leaderboard, with scores rendered on a 0–100 scale.

---

## 2. Part A — Retire the Legacy Engine

### 2.1 Delete

- `tools/benchmark/runner.py`
- `tools/benchmark/scorer.py`
- `tools/benchmark/scorecard.py`
- `tools/benchmark/registry.py`
- `tools/benchmark/models.json`
- Legacy tests: `tools/benchmark/tests/test_runner.py`, `test_scorer.py`, `test_scorecard.py`, `test_registry.py`
- In `tools/benchmark/tests/test_cli.py`: the legacy `_main_run` / `--models` cases (keep only what exercises the surviving CLI).

> **`borda_normalize` is already safe.** It was lifted into `compiler/kpi/score.py` (B.3 contract); `scorer.py` only *re-exported* it. Deleting `scorer.py` removes the re-export, not the implementation. Confirm no surviving import path relies on `tools.benchmark.scorer.borda_normalize` before deleting (grep gate in the plan).

### 2.2 Keep

- `tools/benchmark/cli.py` — trimmed to the `score` engine only (§2.3).
- `tools/benchmark/paths.py` — still used by `score` for `SCORES_DIR`/`RUNS_DIR`. **Remove the now-dead `MODELS_JSON` export.** `TRUTH_DIR` (GT directory for the old GT-based scoring) is also legacy; flag it but leave the `benchmark/truth/` data alone in this task — code deletion only.
- `tools/benchmark/promotion.py` — this is #109 (watched→scored promotion helper), unrelated to the legacy engine.
- `compiler/kpi/*` and `orchestrator/emit_kpis.py` — the new engine.

### 2.3 Honest CLI shape

With one engine left, drop the positional-sniff dispatch in `main()`. Build a top-level `argparse` parser with a real subcommand:

```
kdb-benchmark score <RUN_DIR> [<RUN_DIR> ...] [--runs-root …] [--leaderboard …]
```

- `score` is a registered subparser, so `kdb-benchmark --help` and `kdb-benchmark score --help` both document it.
- A single explicit subcommand (rather than making scoring the bare command) leaves room to add future subcommands without another dispatch rewrite.
- Console entry point is unchanged: `kdb-benchmark = "tools.benchmark.cli:main"`.
- Remove from `cli.py`: `_main_run`, `_build_parser`, `_merge_with_prior_final`, and all imports of `runner`/`scorer`/`scorecard`/`registry`. `now_iso` import stays (used by `_score_command`).

---

## 3. Part B — Weak-Spot Penalty

**Intent.** Don't be lopsided: punish a glaring weak spot. A model must not top the leaderboard on the strength of three strong axes while being dead-last on the fourth. This replaces the old D31 outlier penalty — *not* a port of it. D31 penalized cumulative shortfall vs. the field mean on *raw rates* and deliberately excluded the Borda-relative measures; our leaderboard is **all-Borda**, so D31's "below-the-mean" logic would double-count relative standing. The weakest-link rule is the correct adaptation.

### 3.1 Signal

Each model has a Borda value in `[0, 1]` (1 = best in field) for each of the **four composite axes**:

```
quarantine_rate (Borda) · recovery_rate (Borda) · latency (Borda) · graph_score (combined)
```

- `graph_score` is the existing `combined_graph_score(...)` (the 4 graph sub-KPIs already blended at 35/30/20/15) — it counts as **one** axis. The penalty does **not** range over the 7 raw KPIs; a 15%-weighted sub-metric must not trigger a penalty as hard as the 40% quarantine pillar.
- All four axes are treated **equally** for the weak-spot test (no scaling by `TOP_WEIGHTS`). A glaring capability gap is glaring regardless of how the composite weights that axis.

```
weakest = min(axis_borda for the present axes)
```

Only **present** axes participate (a `None` axis — model absent from that KPI, or no graph KPI at all — is skipped), consistent with the pro-rata philosophy already in `score_models`. `weakest_kpi` records which axis produced the minimum (one of `quarantine_rate` / `recovery_rate` / `latency` / `graph`), for transparency.

### 3.2 Formula

```
τ (WEAK_SPOT_THRESHOLD)  = 0.5     # deadband — below mid-field = "glaring"; PARKED for calibration
λ (WEAK_SPOT_PENALTY_CAP) = 0.10   # max deduction (10 points on the 0–100 scale); PINNED

penalty = λ · max(0, τ − weakest) / τ
```

- `weakest ≥ τ` → `penalty = 0` (mild imbalance forgiven — echoes D31's old `floor(dev%/10)` deadband).
- `weakest = 0` → `penalty = λ = 0.10` (the cap, enforced by construction — no separate clamp needed).
- Linear between. At τ=0.5: `penalty = 0.10 · (1 − 2·weakest)` for `weakest < 0.5`.

### 3.3 Application

```
composite_pre_penalty = _hierarchical_composite(per_kpi_borda, graph_score)   # in [0,1]
penalty               = weak_spot_penalty(per_kpi_borda, graph_score)         # in [0, 0.10]
composite             = max(0, composite_pre_penalty − penalty)               # in [0,1]
```

Rank by `composite` (post-penalty). The penalty operates entirely in `[0,1]` space; the 0–100 scaling (§4) is applied afterward to the score fields.

### 3.4 Calibration knobs

- **`τ = 0.5`** — PARKED, tuned with the ≥3-model cohort alongside the §6 composite weights.
- **`λ = 0.10`** — PINNED by decision (penalty capped at 10%).

Both live as module-level constants in `compiler/kpi/score.py` next to `TOP_WEIGHTS` / `GRAPH_WEIGHTS`, so calibration is a one-line edit.

---

## 4. Part C — 0–100 Score Scale

The **headline score is 0–100.** Multiply the three score fields by `COMPOSITE_SCALE = 100`:

- `composite` (post-penalty, the rank-by value) → `0–100`
- `composite_pre_penalty` → `0–100`
- `penalty` → `0–10` (the 0.10 cap shows as 10 points)

**Components stay in `[0,1]`:** `per_kpi_borda` and `graph_score` are sub-signals, not the score — they remain Borda-native `[0,1]` in the persisted data. Renderers may display them as-is. (This keeps the penalty math, which consumes Borda/graph_score, in `[0,1]` and applies the ×100 only to the final score fields.)

---

## 5. Data Model & Rendering Changes

### 5.1 `score_models` return (compiler/kpi/score.py)

Each `per_model[slug]` gains the penalty + scaled fields:

```python
{
    "composite":             float,   # 0–100, post-penalty (rank-by)
    "composite_pre_penalty": float,   # 0–100
    "penalty":               float,   # 0–10
    "weakest_kpi":           str,     # axis that triggered the min (or None if no axis present)
    "graph_score":           float | None,  # [0,1], unchanged
    "per_kpi_borda":         {kpi: float | None},  # [0,1], unchanged
}
```

`top_weights` / `graph_weights` unchanged. Add `penalty_params: {"threshold": τ, "cap": λ}` to the top-level return for self-description.

### 5.2 Leaderboard JSON (`_score_command`)

`ranking` rows carry the new fields (`composite`, `composite_pre_penalty`, `penalty`, `weakest_kpi`, `graph_score`, `per_kpi_borda`, `rank`). Add `penalty_params` to the persisted payload alongside `top_weights`/`graph_weights`. Pointers (`models: {slug: run_dir}`) unchanged.

### 5.3 Renderers (terminal + Markdown)

Both `_render_score_table` and `_render_leaderboard_md` gain a **`PENALTY`** column (mirrors the old scorecard's penalty column) and show `composite` on the 0–100 scale. Suggested ranking columns:

```
rank | model | <processing Borda ×3> | graph_score | pre-pen | PENALTY | score(0–100)
```

`weakest_kpi` annotates the penalty (e.g. `-7.0 (graph)`), so a demotion is legible. The raw-values / graph-component detail sections are unchanged.

### 5.4 Untouched

`compiler/kpi/report.py` (per-run `report.md`) does **not** get the penalty: it renders a single run's raw KPI values, where cross-model Borda — and therefore the penalty — is undefined. The penalty is a **leaderboard-only** (multi-model) construct.

---

## 6. Testing (TDD)

**Penalty unit tests** (`compiler/kpi/tests/test_kpi_score.py`):
- Balanced model (all axes ≥ τ) → `penalty == 0`, `composite == composite_pre_penalty`.
- Lopsided model (`[0.9,0.9,0.9,0.05]`, one axis well below τ) → penalty > 0, near cap; demoted below a balanced competitor whose pre-penalty composite was lower.
- `weakest = 0` → `penalty == 0.10` (×100 = 10.0); cap is exact.
- `weakest == τ` boundary → `penalty == 0` (deadband is half-open at τ).
- Missing-axis fidelity: a `None` axis is skipped by `min`; `min` over present axes only. A model with no graph KPI penalizes on its weakest *present* processing axis.
- `weakest_kpi` reports the correct axis.
- Scaling: `composite`/`composite_pre_penalty` in `[0,100]`; `per_kpi_borda`/`graph_score` still `[0,1]`.

**Leaderboard tests** (`tools/benchmark/tests/test_score.py`):
- Penalty fields persisted in `leaderboard.json`; `penalty_params` present.
- `.md` + terminal render the `PENALTY` column and 0–100 scores.
- Cross-tier lookup (existing `TestCrossTierLookup`) still passes.

**Retirement tests:**
- Grep gate: no surviving import of `tools.benchmark.{runner,scorer,scorecard,registry}` or `tools.benchmark.scorer.borda_normalize`.
- `kdb-benchmark --help` exits 0 and lists the `score` subcommand.
- Full suite green (currently 1358; net change = legacy tests removed + penalty tests added).

---

## 7. Out of Scope

- The `benchmark/truth/` data directory and `TRUTH_DIR` runtime use (GT-based scoring) — flag only; no data deletion this task.
- Re-running models to regenerate leaderboards (user fires API-cost runs; existing runs re-score via cross-tier lookup).
- Calibrating `τ` / the §6 composite weights — deferred to the post-cohort calibration step.
- A corpus-independent model-quality KPI — separate deferred brainstorm.

---

## 8. File Touch Summary

**Delete:** `runner.py`, `scorer.py`, `scorecard.py`, `registry.py`, `models.json`, `test_runner.py`, `test_scorer.py`, `test_scorecard.py`, `test_registry.py`.
**Modify:** `cli.py` (trim to `score` subcommand), `paths.py` (drop `MODELS_JSON`), `score.py` (penalty + scaling), `test_cli.py` (drop legacy cases), `test_score.py` (penalty/render), `test_kpi_score.py` (penalty units).
**Unchanged:** `promotion.py`, `report.py`, `processing.py`, `graph.py`, `emit_kpis.py`, `orchestrator/kdb_orchestrate.py`.
