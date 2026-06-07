# Benchmark Cohort Procedure — multi-model `--emit-kpis` runs → leaderboard

Operational runbook for the **#109 quality benchmark**: run several models over the
sandbox vault, then score them into a cross-model leaderboard. The question this
answers is **"among these models, which builds the best graph?"** — model
*selection* is already settled on cost (`deepseek-v4-flash`), so this measures
**quality only**.

> **These are API-cost steps — Joseph fires the runs himself**
> ([[feedback_user_fires_api_cost_runs]]). `kdb-benchmark score` is **free** (no API)
> and may be run by anyone.

This builds on the plain-run runbook — see **`docs/reference/test-run-procedure.md`**
for the shared **OneDrive pause** (§0) and **reset** (§1) steps, which are identical
here and are **not** repeated below.

---

## 1. Per-model run (one model at a time, reset between each)

For **each** model in the cohort, in its own clean run:

1. **Pause OneDrive** + **reset** the sandbox — exactly as in the test-run runbook
   §0–§1 (`cd ~/Obsidian/Vault-in-place-test-run/KDB && rm -rf graph graph-view.html
   wiki state/runs state/manifest.json state/compile_result.json
   state/last_orchestrate.json`).
2. Run the orchestrator with the model's provider/model and the **`--emit-kpis`**
   flag:

```bash
kdb-orchestrate \
  --pipeline vault-test \
  --vault-root ~/Obsidian/Vault-in-place-test-run \
  --provider <provider> --model <model> \
  --emit-kpis
```

`--emit-kpis` writes `benchmark/runs/<model>-<run_id>/measurements.json` (+ a
rendered `report.md`) after the run finalizes. The repo's `benchmark/runs/` is
gitignored — these are regenerable outputs, never committed.

**Reset between models** so every run sees the same fresh corpus — this keeps the
cohort apples-to-apples ([[feedback_apples_to_apples_within_session]]).

### Provider / model / API-key reference

The orchestrator routes by `--provider`; each provider reads one env var (see
`common/config/__init__.py`, dispatch in `common/call_model.py`):

| `--provider` | example `--model` | API key env var |
|---|---|---|
| `deepseek`     | `deepseek-v4-flash`        | `DEEPSEEK_API_KEY` |
| `gemini`       | `gemini-3.1-flash-lite`    | `GEMINI_API_KEY` |
| `alibaba`      | `qwen3.5-flash`            | `QWEN_US_API_KEY` (DashScope US) |
| `anthropic`    | `haiku-4.5` / `sonnet-4.6` | `ANTHROPIC_API_KEY` |
| `openai`       | `gpt-5.4-mini`             | `OPENAI_API_KEY` |
| `xai`          | `grok-4-1-fast-reasoning`  | `XAI_GROK_API_KEY` |
| `ollama-cloud` | (cloud model id)           | `OLLAMA_API_KEY` |
| `ollama-local` | (local model id)           | — (none; `OLLAMA_BASE_URL`) |

The `--model` value becomes the run-dir prefix (`<model>-<run_id>`), so use the
slug you want to see on the leaderboard.

## 2. Build the leaderboard (free — no API)

Score the per-model run dirs into the leaderboard:

```bash
kdb-benchmark score \
  <model-a>-<run_id> \
  <model-b>-<run_id> \
  <model-c>-<run_id>
```

- Each run dir contributes **one row, keyed by `header.model`**; the **latest run
  per model wins** (re-score with a newer dir to replace a model's row).
- The leaderboard **accumulates across invocations** — score a new model alone and
  it joins the existing board: `kdb-benchmark score <new-model>-<run_id>`.
- Output: `benchmark/scores/leaderboard.json` + `leaderboard.md` (both gitignored)
  and a terminal table.
- **Reset** the board = delete the leaderboard file:
  `rm -f benchmark/scores/leaderboard.{json,md}`.
- **No `corpus_fingerprint` gate** — cross-run corpora are assumed to differ;
  comparability is the operator's judgment.

## 3. Reading the leaderboard

Scoring is a **hierarchical weighted Borda** (per-KPI rank-normalize across the
cohort → combine the 4 graph KPIs into one `graph_score` → top-level composite).
Columns:

- **Processing KPIs** (`quarantine_rate ↓`, `recovery_rate ↓`, `latency ↓`) and
  **`graph_score ↑`** are shown as **Borda values in [0,1]** (1 = best in field).
- **`pre-pen` / `PENALTY` / `score (0-100)`** are on a **0–100 scale**. `score` is
  the post-penalty composite — the rank-by value.

**Weights (§6 starting point, in `compiler.kpi.score`):** quarantine 40 / **graph
40** (within-graph: connectivity 35 / link 30 / supports 20 / reuse 15) / recovery
10 / latency 10. These are **PARKED for calibration** — tuned once a ≥3-model cohort
exists.

### The weak-spot PENALTY

A model is penalized for its **single weakest composite axis** (don't reward a
lopsided model that's strong on three axes but dead-last on one):

- `weakest = min` over the 4 composite axes (quarantine / graph_score / recovery /
  latency), equal treatment.
- `penalty = 0.10 · max(0, (τ − weakest) / τ)`, **capped at 0.10** (= 10 points).
- **`τ = 0.5` (PARKED)** is a deadband: a weakest axis **at or above mid-field**
  (Borda ≥ 0.5) takes **no penalty** — only genuinely last-place weakness bites.
- **`λ = 0.10` (PINNED)** is the cap.
- The `PENALTY` cell annotates the triggering axis, e.g. `10.00 (latency)`.

This is **leaderboard-only** — cross-model Borda is undefined for a single run, so
the per-run `report.md` has no penalty.

### Cohort-size effects (why 2 entries is degenerate)

- **2 models:** every KPI is binary (winner 1.0 / loser 0.0) → the penalty is
  all-or-nothing and uninformative. **Don't trust a 2-model board.**
- **3 models:** Borda is graded (0 / 0.5 / 1.0), but whoever is *last* on their weak
  axis still gets Borda 0.0 → the **full cap**. Penalty reads as "full 10 or
  nothing."
- **4+ models:** finer Borda gradation → the penalty scales smoothly between 0 and
  the cap. This is where the leaderboard reads best.

### ⚠️ KPI-parity caveat (re-run the whole cohort on one code version)

Borda **drops a model from any KPI it didn't emit**, and a KPI emitted by **only one
model** is scored as a **single candidate → automatic 1.0** (best possible) — an
artifact, not a real comparison. This bit the first 3-model board: only the qwen run
carried `recovery_rate` (the deepseek/gemini runs predated it), so qwen got a free
best-recovery score.

**Rule:** when the KPI set changes, **re-run every model in the cohort on the same
code version** so all rows share the same KPI set. Mixing runs from different code
generations silently distorts the composite.

---

**To close #109:** run a ≥3-model cohort on one code version → `kdb-benchmark score`
→ set the parked weights (and τ) from the observed cross-model spread → run the
watched-diagnostic promotion rule (`tools/benchmark/promotion.py`). See
[[project_benchmark_redesign_architecture]], the design specs under
`docs/superpowers/specs/2026-06-0*-benchmark-*`.
