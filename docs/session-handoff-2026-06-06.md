# Session handoff — 2026-06-06

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — Two arcs SHIPPED + pushed; first 3-model benchmark cohort run (deepseek #1)

A heavy build session, all merged to `main` and **pushed to `origin` (`origin/main` = `364effd`)**. Two complete arcs — the **benchmark CLI refactor + weak-spot penalty** (#109 follow-on) and the **Pass-2 `ingestor` → `intake` rename** — plus the **first real 3-model benchmark cohort**, which already points hard at deepseek as the best graph-builder. Working tree clean; no open commit gate on code. #109 is **not** closed — what remains is calibration (a clean cohort + setting parked weights), not code.

### What happened / what converged

1. **Benchmark CLI refactor + weak-spot penalty** (merged `8469fb8`, spec/plan `docs/superpowers/specs|plans/2026-06-06-benchmark-cli-refactor-penalty*`). Subagent-driven TDD, two-stage review per task + a final opus holistic review; **1175 non-live tests**.
   - **Legacy #5 run engine RETIRED** — deleted `runner`/`scorer`/`scorecard`/`registry` + `models.json` (~1,900 LOC, self-contained island) + their tests. `kdb-benchmark` is now single-purpose; `score` is a **real argparse subcommand** (visible in `--help`). "Running" a model = `kdb-orchestrate --emit-kpis`.
   - **Weak-spot penalty** in `compiler/kpi/score.py` `score_models` (the one idea carried over from the old D31 outlier penalty, re-adapted for an all-Borda leaderboard): `weakest = min` over the **4 composite axes** (quarantine / graph_score / recovery / latency, **equal treatment**), `penalty = 0.10·max(0,(0.5−weakest)/0.5)` **capped 0.10**, subtracted from the composite; `weakest_kpi` recorded; **leaderboard-only** (cross-model Borda is undefined for a single run → not in per-run `report.md`).
   - **0–100 headline score** + `PENALTY (weakest_kpi)` column (terminal + `leaderboard.md`); `per_kpi_borda`/`graph_score` stay `[0,1]` components.
   - **`λ=0.10` PINNED · `τ=0.5` PARKED** (deadband — a weakest axis ≥ 0.5 takes no penalty) for cohort calibration alongside the §6 weights.
   - New runbook **`docs/reference/benchmark-cohort-procedure.md`** (per-model `--emit-kpis` run → `kdb-benchmark score` → reading the board; cohort-size effects; the KPI-parity caveat).

2. **Pass-2 `ingestor` → `intake` rename** (merged `364effd`). Joseph: calling a Pass-2 component "ingestor" collides with the Pass-1 `ingestion/` pipeline. I first mis-proposed `sync` — he correctly pushed back (sync = the *adapter-level* `sync_current_run` step that **calls** the engine; different layer). Landed on **`intake`**: `kdb_graph/ingestor.py` → `kdb_graph/intake.py`, `SyncResult` → `IntakeResult`, 4 test files renamed, docstrings scrubbed. **Pure rename, no logic change**, 1175 tests green. **Deliberately NOT touched:** the schema columns `ingest_state`/`ingest_count`/`last_ingested_at` (D-A2 graph-side lifecycle names — renaming = a schema migration, out of scope).

3. **First 3-model benchmark cohort** (Joseph fired qwen3.5-flash live; the penalty + 0–100 in action):
   | rank | model | score (0-100) | penalty |
   |---|---|---|---|
   | 1 | **deepseek-v4-flash** | **86.67** | 0 (weakest axis latency = exactly τ → deadband) |
   | 2 | qwen3.5-flash | 34.00 | −10 (latency — slowest) |
   | 3 | gemini-3.1-flash-lite | 15.56 | −10 (quarantine — quarantines most) |
   - **deepseek is the clear best graph-builder** (cleanest quarantine + owns the graph richness trio). The penalty works exactly as designed with 3 entries.

## OPEN — pick up here

- [ ] **HEADLINE — close #109 calibration.** Re-run **all three models fresh on the current code** (one at a time, reset between — `docs/reference/benchmark-cohort-procedure.md`) so the cohort is apples-to-apples, then `kdb-benchmark score` → **set the parked weights + τ** from the cross-model spread → run the watched→scored **promotion rule** (`tools/benchmark/promotion.py`). Joseph fires the runs (API cost — [[feedback_user_fires_api_cost_runs]]).
- [ ] **Two cohort lessons that force the re-run:** (a) **recovery_rate parity** — only the qwen run carried `recovery_rate`; single-candidate Borda scored it auto-1.0 (artifact inflating qwen ~6 pts). (b) **penalty needs 4+ models for graded gradation** — at 3 it's "full cap or nothing" (last-on-axis = Borda 0). A 4th/5th model reads better.

## Housekeeping / open loops
- [ ] **COMMIT GATE:** code is fully committed + pushed (`origin/main` = `364effd`). **Uncommitted: this handoff + today's `2026-06-06` daily note only.** Joseph has not requested committing the docs this turn.
- [ ] **`CODEBASE_OVERVIEW.md §7` doc debt** — still describes the deleted #5 engine (runner/scorer/scorecard/registry, `models.json`, old dataflow). Tracked in the #109 ledger note; **rewrite §7 for the orchestrate-emit → score-only architecture when #109's Milestone Changelog entry lands** (i.e. at #109 close, not before).
- [ ] **DEFERRED:** corpus-independent graph-model-quality KPI brainstorm (no high-confidence one yet — run once multi-model spreads give something to reason from).
- [ ] **Optional / separate:** the schema `ingest_*` column vocabulary (`ingest_state`/`ingest_count`/`last_ingested_at`) — a real migration if the naming ever bothers Joseph; explicitly out of today's rename scope.
- [ ] Carry-over (untouched): **#107** (Phase-B polish), the **0.6 → 1.0 ingestion** arc.

## Pointers
- Resume artifact: **`docs/reference/benchmark-cohort-procedure.md`** (the exact cohort run+score runbook) + the current `benchmark/scores/leaderboard.md` (gitignored, on Joseph's machine).
- This arc's spec/plan: `docs/superpowers/specs/2026-06-06-benchmark-cli-refactor-penalty-design.md` · `docs/superpowers/plans/2026-06-06-benchmark-cli-refactor-penalty.md`.
- Scoring engine: `compiler/kpi/score.py` (`score_models`, `weak_spot_penalty`, `WEAK_SPOT_THRESHOLD`/`_PENALTY_CAP`, `COMPOSITE_SCALE`). CLI: `tools/benchmark/cli.py` (`_score_command`).
- Task ledger: `docs/TASKS.md` (#109 entry carries the full narrative + §7 doc-debt note). North Star: `docs/CODEBASE_OVERVIEW.md`. Test-run base: `docs/reference/test-run-procedure.md`. Sandbox: `~/Obsidian/Vault-in-place-test-run/` (36 src).
- Memory: [[project_benchmark_redesign_architecture]] (updated today — §6 + CLI/penalty + 3-model cohort + next steps), [[feedback_apples_to_apples_within_session]], [[feedback_user_fires_api_cost_runs]], [[feedback_conversational_over_askuserquestion]].
