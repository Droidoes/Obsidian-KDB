# Session handoff — 2026-06-07

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.
> (Refreshed at end-of-day — supersedes the morning handoff that covered #110/`v0.5.4`/Phase-0-built.)

## ⏩ END OF SESSION — #111 CLOSED: Phase 0+1 shipped (`v0.5.5`/`v0.5.6`), baseline-1 locked, Phase 2 (json_schema) shelved

A second marathon block on 2026-06-07 (after the morning's #110/`v0.5.4`/Phase-0 work). Subagent-driven throughout. We released **`v0.5.5`** (Phase 0 — run provenance + release-keyed leaderboard) and **`v0.5.6`** (Phase 1 — optimized model calls), fired and locked the **baseline-1** 4-model cohort, and **closed #111** by shelving Phase 2 as data-mooted. `main` @ `f299ef4` (1 commit past the `v0.5.6` tag — intentional, post-baseline-1), pushed, clean, **1253 non-live tests green**.

### What happened / what converged

1. **`v0.5.5` (Phase 0) cut + pushed.** Merged `feat/111`. **Decision:** preserved the prior 3-model 06-06 cohort as the **`@v0.5.4` baseline-0** (stamped `release_version`, re-scored) — no separate v0.5.5 benchmark fired.

2. **`v0.5.6` (Phase 1) — optimized per-model calls.** Pool restructure (`models.json` active / `models_dropped.json` human-archive; **dead dropped-guard retired** → dropped id = `UnknownModelError`); roster swaps (−`grok-4-1-fast-reasoning`, +`grok-4.20-0309-non-reasoning`). `gpt-5.4-mini` → `reasoning_effort:"low"` (flat, chat.completions). **Gemini pulled INTO Phase 1** (Joseph's call): native **`_call_gemini`** (`google-genai` SDK, off the compat shim), json-mode + **`thinking_level:"minimal"`** (Gemini 3.x uses `thinking_level`, NOT the 2.5-era `thinking_budget`; flash-lite floor=minimal, full-off unsupported — corrected the original snippet). `response_json_schema` held for Phase 2.

3. **Two mid-cohort bugs found + fixed (folded into `v0.5.6`; the tag was moved in-place 3× to keep `release_version` clean, roadmap unchanged):**
   - **Retry-telemetry:** re-prompt recoveries were invisible to `recovery_rate`/`retry_load` (they read `model_response.attempts` = SDK transient retries, not the compile re-prompt count `final_attempt_index`). Fixed in `from_pass2`; **opus review caught** that an initial `max(final_attempt_index, attempts)` fudge would fold SDK-429 noise into the model-quality axis → corrected to `final_attempt_index` alone. Also: `final_status="retried"` for re-prompt-only recoveries + per-source `pass-2 ✓ (N attempts)`.
   - **gpt-5.4-mini 400'd on `temperature=0.0`** (GPT-5 reasoning rejects any non-default temp). Fix: **nullable per-model `temperature`** pool field; gpt sets it `null` → we omit the kwarg. NOT coupled to `use_completion_tokens` (a future non-reasoning GPT-5 may want temp=0).

4. **Per-source token in/out on the console → `console.log`** (display-only; Joseph wanted token visibility — built it instead of hand-extracting from transient sidecars).

5. **baseline-1 LOCKED (4-model cohort @v0.5.6):** **gpt-5.4-mini #1 on quality** (84.67; graph 0.95, 0 quarantine) once called correctly — **overturning #109's handicapped "deepseek best" and validating the #111 thesis.** deepseek 54.67 > gemini 21.33 (still quarantines most — its native path bought speed not quarantine-reduction) > qwen 9.33. **🎯 DECISION: `deepseek-v4-flash` stays the DEFAULT on cost** — $0.12/run vs gpt's $0.84 (**7.2×**), and deepseek is also 0-quarantine + 2nd-best graph. gpt = "premium quality" option.

6. **`gemma4-12b-qat-128k` tried → archived** — extremely slow, majority quarantined, couldn't finish 36 sources (local 12B capability/hardware limit). No active `ollama-local` model remains; Ollama Cloud won't be used (no structured output).

7. **#111 CLOSED — Phase 2 (`json_schema`) SHELVED (data-mooted).** Joseph asked *"is strict json_schema applicable for our use case?"* A grounded review (read `compiled_source_response.schema.json`) said **no**: (a) our output is generative synthesis (rich free-form `body`) — strict constrained-decoding risks quality; (b) our *hard* failures are **semantic** (slug-format, body↔`outgoing_links` invariant, slug-list consistency) which no json_schema expresses — the reconciler+coerce+semantic layer owns them regardless; (c) strict's per-provider keyword subset drops our value-constraints; (d) it contradicts coerce-don't-reject. **And the default (deepseek) is already 0-quarantine** — the real win was the **thinking/reasoning-disable latency cut (~30–70%)**, not structured output.

## OPEN — pick up here
- [ ] **Next session's fork (Joseph's call):** **(A)** close **#109** — baseline-1 *is* the clean multi-model cohort it was blocked on, so set the parked `§6` weights + τ and run the promotion rule (`tools/benchmark/promotion.py`); **or (B)** start the **0.6 → 1.0 ingestion arc** (the big roadmap item — tunnel-from-both-ends / #88 family). *My lean: (A) is the small, finishable close that banks #109; (B) is the larger new arc — do (A) first, it's nearly free now.*
- [ ] **#107** — deferred Phase-B polish (viewer packaging, `compiler.compiler` double-name, orchestrator→tools.cleanup decoupling).

## Housekeeping / open loops
- [ ] **COMMIT GATE:** code + all closure docs **committed + pushed** (`main` @ `f299ef4`). The only pending items are the **wrap docs** (this handoff + the daily note + the JOURNEY entry) — awaiting Joseph's go to commit.
- [ ] **#109 doc-debt:** `CODEBASE_OVERVIEW.md §7` still describes the deleted #5 engine — clears when #109 fully closes (the calibration step above).
- [ ] `__version__` still stale at 0.5.2 — git-describe is authoritative; cosmetic.

## Pointers
- **Resume artifact:** this file. Then the **`#111` Milestone Changelog entry** in `docs/CODEBASE_OVERVIEW.md` (full closure record) + ledger `docs/TASKS.md` (#111 → closed).
- Spec (with the Phase-2-SHELVED banner): `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md`. Plans: `docs/superpowers/plans/2026-06-07-phase1-*.md`.
- Reference: `docs/reference/model-provider-api-calls.md` (gpt temperature constraint, gemini native `thinking_level`, ollama notes). Cohort runbook: `docs/reference/benchmark-cohort-procedure.md`.
- Memory: [[project_111_optimal_model_calls]], [[reference_model_provider_api_calls]], [[feedback_coerce_dont_reject]], [[feedback_data_before_principle]], [[feedback_user_fires_api_cost_runs]], [[project_release_versioning_scheme]].
- Releases: `docs/RELEASES.md` (`v0.5.5`, `v0.5.6`). `main`/`origin` @ `f299ef4`; tags through `v0.5.6`.
