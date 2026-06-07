# Session handoff — 2026-06-07

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — #110 shipped + `v0.5.4` released + #111 designed + Phase 0 built

A mega-session spanning the 06-06→06-07 rollover. Three arcs landed: **#110** (user-owned model pool + cost/ctx diagnostics) designed → built subagent-driven → reviewed → **merged + pushed** (`5d99900`); **`v0.5.4`** cut/tagged/pushed (closing the untagged-`main` gap); and **#111** (call each model optimally → clean-slate re-benchmark) scoped → specced → **Phase 0 built** subagent-driven on `feat/111-structured-output-upgrade` (committed, **not yet merged/tagged**). `main`/`origin` = `d41da4a` (`v0.5.4`). Next step is gated on Joseph: release `v0.5.5` + fire the baseline-0 benchmark.

### What happened / what converged

1. **#110 — user-owned model pool** (merge `5d99900`, 1209 tests, live-smoke clean). `common/models.json` (pool + ledger) + `common/model_pool.py` `resolve_models_json(id)→ModelSpec` (absolute dropped-guard `UnknownModelError`/`DroppedModelError`, `words×1.3` ctx helpers); `kdb-orchestrate --model` resolves the pool (`--provider` → escape hatch + conflict-check). **`cost_usd`** restored (pricing × aggregated tokens) on both telemetry paths; **input-side ctx-overrun guard** in both passes (skip-and-quarantine, no API spend, synthetic `TokenOverrun` persisted in the sidecar). **Holistic-review must-fix:** `use_completion_tokens`/`extra_body` were resolved but never threaded to the passes → fixed (makes thinking-disable real + unbreaks `gpt-5.4-mini`). Semantic **`thinking` field** (per-provider disable: verified alibaba `enable_thinking:false` + deepseek `thinking:disabled`; gemini/openai/xai no-op+TODO). **`deepseek-v4-pro` un-dropped.**

2. **`docs/reference/model-provider-api-calls.md`** — new per-provider reference (call shapes + structured-output/reasoning matrix). Verified: qwen slowness = thinking-on-by-default (no `enable_thinking:false`); openai/xai support `json_schema` strict **in the compat path**; openai `reasoning_effort` none/low/med/high/xhigh (low = extraction floor); xai `reasoning_effort:"none"` (unconfirmed for *our* grok); gemini needs native SDK `response_json_schema`. Architecture insight: structured-output is **mostly an in-compat `response_format` upgrade, NOT a per-provider split** — only Gemini forced native.

3. **`v0.5.4` released** (`d41da4a`, tag `v0.5.4`) — bundles #108 + #109-framework + #110 (all were merged untagged since `v0.5.3`; 54-commit gap closed). `__version__` left stale at 0.5.2 (git-describe becomes authoritative in #111 Phase 0).

4. **#111 — optimal per-model calls → clean-slate re-benchmark** (spec `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md`, ratified). Purpose corrected by Joseph: the #109 cohort ran every model through a *handicapped* path, so "Gemini worst / deepseek best" is meaningless until each is called right. **Two-phase tagged de-risk** (his): baseline-0 → Phase-1 (non-schema config) → baseline-1 → Phase-2 (json_schema) → baseline-2, each a semver tag (`v0.5.5/6/7`), isolating the schema variable; the `(model, release_version)` leaderboard key makes the deltas visible per-model.

5. **#111 Phase 0 built** (subagent-driven, 3 tasks, 1220 tests, plan `docs/superpowers/plans/2026-06-07-phase0-run-provenance-leaderboard-key.md`): `3bb6098` release_version helper + header field · `8cafca6` wire into run + orchestrate stdout → `console.log` · `de0ddee` leaderboard keyed on `(provider, model, release_version)`. All on `feat/111`.

## OPEN — pick up here

- [ ] **HEADLINE — close Phase 0: release `v0.5.5` + fire `baseline-0`.** Merge `feat/111` Phase-0 → `main`, cut **`v0.5.5`** (RELEASES.md entry + annotated tag), then **Joseph fires the clean-slate 4-model baseline benchmark** at v0.5.5: reset sandbox (`docs/reference/test-run-procedure.md`) → run **deepseek-v4-flash, qwen3.5-flash, gpt-5.4-mini, gemini-3.1-flash-lite** each `--emit-kpis` → `kdb-benchmark score`. (API cost — Joseph fires, [[feedback_user_fires_api_cost_runs]].)
- [ ] **#111 Phase 1** (then `v0.5.6` / baseline-1): pool-prep — split `models.json` (active) / `models_dropped.json` (archive, code-never-reads, option **b**) + roster (drop `grok-4-1-fast-reasoning`, add `grok-4.20-0309-non-reasoning` $1.25/$2.50 + `gemma-4-12b-qat`, later batch) + **retire the now-dead dropped-guard** — and gpt-5.4-mini `reasoning_effort` (none vs low) + gemini thinking config. **Gemini wrinkle:** does its compat endpoint accept the thinking-disable `extra_body`? if not, defer to Phase 2 native handler.
- [ ] **#111 Phase 2** (then `v0.5.7` / baseline-2): `json_schema` — thread schema into `ModelRequest`, **spike-first** strict-adapt of `compiler/schemas/compiled_source_response.schema.json` (nested `pages[]`; risk = too-strict rejects valid output → MORE quarantines), `strict:false` fallback, per-provider (compat for openai/xai, Gemini native `_call_gemini` contingency). For graded reasoning (openai/xai) use raw `extra_body` (`{"reasoning":{"effort":"low"}}`), not the binary `thinking` field.
- [ ] **Verifications Joseph fires:** gpt-5.4-mini reasoning none-vs-low; gemini compat thinking + `json_schema` (decides the native-handler question); deepseek/qwen `json_schema`.

## Housekeeping / open loops
- [ ] **COMMIT GATE:** `main`/`origin` clean at `v0.5.4` (`d41da4a`, pushed). **`feat/111` (spec + plan + 3 Phase-0 commits) committed locally but NOT pushed.** Uncommitted working tree: only the stale untracked `docs/session-handoff-2026-06-06.md` (superseded by this) + this handoff + today's daily note. Joseph hasn't requested pushing the branch or committing these docs this turn.
- [ ] **#109 close:** weight calibration after the clean-slate cohort lands; `CODEBASE_OVERVIEW.md §7` doc-debt (describes the deleted #5 engine) clears at #109-final.
- [ ] **Carry-over:** #107 (Phase-B polish); the per-provider adapter-registry refactor (only after a 2nd native concrete — concrete-first); the 0.6→1.0 ingestion arc.

## Pointers
- Resume artifact: **`docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md`** (#111 spec) + plan `docs/superpowers/plans/2026-06-07-phase0-run-provenance-leaderboard-key.md`.
- Reference: **`docs/reference/model-provider-api-calls.md`** (per-provider call shapes + structured-output/reasoning matrix + TODOs). Cohort runbook: `docs/reference/benchmark-cohort-procedure.md`; test-run: `docs/reference/test-run-procedure.md`.
- Ledger: `docs/TASKS.md` (#110 → Closed; **#111** open with the full arc). North Star: `docs/CODEBASE_OVERVIEW.md` (v0.5.4 / #110 Milestone Changelog entry). Releases: `docs/RELEASES.md` (`v0.5.4`).
- Branch: `feat/111-structured-output-upgrade` (5 commits ahead of `v0.5.4`). Memory: [[project_models_json_pool_110]], [[project_111_optimal_model_calls]], [[reference_model_provider_api_calls]], [[feedback_user_fires_api_cost_runs]], [[feedback_data_before_principle]].
