# Session handoff — 2026-06-03

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — Benchmark redesign brainstorm (mid-flight, not ratified)

Design-only session. No code. We opened the **benchmark redesign** arc and got the architectural backbone to converge, but stopped **mid-brainstorm** — one fork + a few smaller decisions + the whole KPI deep-dive remain.

**THE resume artifact:** `docs/superpowers/specs/2026-06-03-benchmark-redesign-directions.md` — DRAFT, with a clear **LOCKED vs OPEN** split. Read it first. Don't re-litigate LOCKED.

### The redesign in one paragraph
Model selection is settled on price; **quality is the only open axis**, and the old engine (`tools/benchmark/`, Task #5) measures **Pass-2 only** — blind to Pass-1 and to *graph* quality. The inversion: **drop the isolated harness, run the real `kdb-orchestrate` pipeline over the sandbox vault** (36 sources, full-corpus) as the benchmark vehicle, scoring **two KPI families — processing + graph — kept separate**, apples-to-apples across models.

### LOCKED (don't reopen)
- **GT-free** KPIs; **per-token normalization** on every KPI (with ratio pass-through allowed).
- **Two KPI families kept SEPARATE:** processing (sources touched this run; every run) vs graph (whole graph; full-corpus runs only) — incremental runs can't meaningfully score graph-KPIs.
- **Benchmark = full-corpus sandbox runs.** **"Running score"** = each model's **latest** sandbox run, no historical averaging.
- **Borda by layer:** Borda **kept** for the cross-model running score (candidate set → needs weights, not anchors); **absolute, no Borda** for the deferred per-invocation self-score (needs anchors). ⇒ today's build **sidesteps the anchor problem**.
- **Architecture:** computation in new `compiler/kpi/` (`processing.py` / `graph.py` / `score.py`-pluggable), production-importable, honors v0.5.2 D25, no relocation at "shoo-in." Invocation = **tools-side post-processor** (rec) → `kdb-orchestrate` untouched, zero pipeline risk. Storage = **repo** `benchmark/runs/<id>/score.json` (reset-surviving; KPIs+metadata only, not raw responses) + `benchmark/scores/`.
- **Scope:** sandbox benchmark **first**; always-on per-invocation processing telemetry **deferred**.

### OPEN — pick up here
1. **Confirm the fork:** post-processor (rec) vs orchestrate-stage-now.
2. **Smaller decisions:** capture command shape (`kdb-benchmark capture <run>` vs auto) · grouping key for "latest run per model" (`model` vs `provider:model:prompt-version`) · corpus fingerprint (assert same 36 sources) · prompt-version capture (Pass-1+Pass-2) · TDD fixtures (reuse existing `benchmark/runs/` data?).
3. Then: write the ratified `-design.md` → spec self-review → user review gate → `writing-plans`.
4. **KPI deep-dive** = its own *separate* spec/session (processing + graph KPI defs, weights, anchors-where-absolute, composite/Borda formula, outlier-penalty D31 back-or-not).

## Housekeeping / open loops
- [ ] **Directions doc + daily note + this handoff are UNCOMMITTED** — commit when ready (Joseph didn't request commit this session).
- [ ] **File a Task #** in `docs/TASKS.md` for the benchmark redesign (not yet assigned).
- [ ] OneDrive sync was already resumed after run-8 (last session); no run fired today.
- [ ] Carry-over from yesterday (untouched today): **#108** (Pass-1 repair ladder), **#107** (Phase-B polish), the 0.6→1.0 ingestion arc — all still queued; benchmark jumped the line by Joseph's call.

## Pointers
- Resume artifact: `docs/superpowers/specs/2026-06-03-benchmark-redesign-directions.md`.
- Old engine: `tools/benchmark/` + `benchmark/runs|sources|scores|truth/`; North Star §7 (old KPI/Borda machinery).
- Test-run procedure: `docs/reference/test-run-procedure.md`. Sandbox: `~/Obsidian/Vault-in-place-test-run/`.
- Task ledger: `docs/TASKS.md`. North Star: `docs/CODEBASE_OVERVIEW.md`. Journey: `docs/JOURNEY.md`.
- Memory: [[project_run3_next_sandbox_vault]] (benchmark-redesign direction + sandbox), [[feedback_apples_to_apples_within_session]], [[feedback_no_parallel_storage_to_authority]], [[feedback_user_fires_api_cost_runs]], [[feedback_devils_advocate_gate]].
