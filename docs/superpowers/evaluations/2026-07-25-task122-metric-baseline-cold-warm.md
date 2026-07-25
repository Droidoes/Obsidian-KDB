# #122 — First Live Baseline with Event-Time Context Metrics (Cold ×3 + Warm ×1)

Date: 2026-07-25 · Code: `ee37407` (#122 closure) · Suite at run time: 1956 green
Runs scored into leaderboard: 3 cold runs (ranks noted below). Warm run deliberately **not** scored (2-source corpus, not Borda-comparable).

## Runs

| # | run_id | model | mode | compiled | links wired | cost (p1+p2) |
|---|--------|-------|------|----------|-------------|--------------|
| 1 | 2026-07-25T09-25-10_EDT | deepseek-v4-flash | cold (wiped) | 28/36 (8 noise) | 197 | ~$0.10 |
| 2 | 2026-07-25T09-34-38_EDT | gpt-5.4-mini | cold (wiped) | 28/36 (7 noise, 1 quarantined) | 441 | ~$0.73 |
| 3 | 2026-07-25T09-41-46_EDT | gemini-3.6-flash | cold (wiped) | 29/36 (7 noise) | 278 | ~$1.32 |
| 4 | 2026-07-25T09-48-25_EDT | deepseek-v4-flash | **warm** (no wipe; +2 probe sources vs run-3 graph) | 2/38 (36 unchanged, skipped) | 11 | pennies |

Cold = `scripts/sandbox-run.sh` step-2 wipe (graph/wiki/state removed; sources + pipelines.json kept). Warm = no wipe; two new probe notes (`Warm probe - Henry Singleton capital allocation.md`, `Warm probe - Circle of competence in practice.md`) added to `Value Investing/` so their keys could resolve against the surviving run-3 graph. Probes deleted after analysis — the 36-source baseline corpus is restored; content preserved in git history of this doc's conversation if ever needed again.

## Capture integrity (all four runs)

`context_record_coverage` 1.0, `context_integrity_ok` true, `context_build_success_rate` 1.0, `finalize_ran` true, every missing/malformed/duplicate/unexpected/wrong-run count 0, `expected_count_mismatch` false. 87 context records (28+28+29+2), zero capture failures on first live contact.

Arithmetic identities hold on every run (±0.0001 rounding):
- `at_load + late + never = 1.0` (partition of all emitted keys)
- `pre_run + cohort + age_unknown = at_load` (provenance of at-load resolutions)

## Headline decomposition

| metric | ds cold | gpt cold | gem cold | ds warm |
|---|---|---|---|---|
| legacy `entity_search_key_resolution` | 0.293 | 0.388 | 0.267 | 0.444 |
| **resolved_at_load** | 0.035 | 0.024 | 0.030 | **0.389** |
| … pre_run | 0.000 | 0.000 | 0.000 | **0.389** |
| … cohort | 0.035 | 0.024 | 0.030 | 0.000 |
| late_resolution | 0.296 | 0.406 | 0.226 | 0.056 |
| never_resolved | 0.668 | 0.570 | 0.744 | 0.556 |
| t2_seed_rate | 0.031 | 0.016 | 0.030 | 0.389 |
| t2 delivered mean (pages) | 0.25 | 0.14 | 0.24 | 3.5 |
| t3 delivered mean (pages) | 0.0 | 0.0 | 0.0 | 22.0 |
| t1 delivered mean (pages) | 0.0 | 0.0 | 0.0 | 0.0 |

## Findings

1. **The legacy metric's over-credit is confirmed and quantified.** On cold starts ~90% of the legacy number is late-resolution credit (targets materialized only *after* the key was consumed at context-build time). Deepseek: legacy 0.293 vs at-load truth 0.035. GPT: 0.388 vs 0.024. Gemini: 0.267 vs 0.030. The old headline said "1 in 3 keys resolve"; the truth on cold start is "~1 in 30 resolve when it matters; ~2 in 3 never resolve at all."

2. **Cold vs warm is a different world — and the metrics prove they can now tell it apart.** Warm run: at-load jumps 0.035 → 0.389 (11×), entirely `pre_run` (provenance: `target_first_run_id` = run 3's id on every resolved key, verified at record level). Late collapses 0.296 → 0.056. T3 delivered goes 0 → 22 pages/source — pass-2 prompts on warm start finally carry the designed neighborhood context. Every prior sandbox run was a cold start, so this steady-state profile (the production-normal case) had never been measured.

3. **`never_resolved` is high everywhere — but it cannot be read as key weakness.** 0.57–0.74 across cold runs, 0.556 warm; `t2_seed_rate` ≤ 0.031 cold. Under exact-slug lookup, a correct key naming a deeply-known entity fails exactly like a junk key — so this number says "at-load identification is rare" and says *nothing yet* about whose fault that is. Any pass-1-quality reading is deferred until #123 exists (finding 4).

4. **The graph knows; the lookup is literal — semantic graph search does not exist (the headliner, filed as #123).** Keys `warren-buffett`, `charlie-munger`, `mohnish-pabrai` — the three most-mentioned people in this corpus — were unresolved even warm. Evidence chain: (a) record-level `unresolved` dispositions on both warm probes; (b) a direct graph query confirms **no slug-equal node exists** — yet the graph is *rich* with Buffett/Munger/Pabrai knowledge (`buffett-balance-sheet-rules`, `buffett-capital-allocation-and-philanthropy-framework`, three Buffett summaries, …); (c) all three models' preserved `compile_result.json`s show no standalone person node was ever minted by any of them — uniform behavior, so the cause is upstream of model choice; (d) the prompts explain the uniformity: pass-1 is *instructed* to emit person keys (`warren-buffett` is the prompt's own example form), while the compiler's three page kinds (summary/concept/article) contain no kind under which a person becomes a node. **Conclusion (Joseph's framing, 2026-07-25):** the missing capability is *semantic graph search — identifying relevant knowledge sources in terms of graphDB elements* — the project's single objective. The context loader currently impersonates it with exact-slug matching: a placeholder posing as a component that was never built. Filed as **#123**; **#118 resumes after #123**.

5. **`cold_start: true` is per-source, not per-graph.** Both warm-run records carry it (brand-new sources ⇒ T1 = 0 even with a rich graph). T1 will only light up on re-compiles of previously compiled sources (modified notes) — expected, not a bug.

6. **Instrumentation is behavior-neutral.** Legacy metric continuity vs the 4.0.2 matrix holds: deepseek 0.293 (vs 0.2705), gpt 0.388 (vs 0.3636), gemini 0.267 (vs 0.2677). Board placement today: gemini@84 4th (62.82), gpt@84 8th (46.06 — quarantine penalty from the recurring `Quotes from Napoleon.md` quarantine), deepseek@84 9th (45.12 — latency penalty). gemini-3.6-flash is the strongest gemini result to date and its latency ranked 1st on the board.

## Operational notes

- Alias-ledger warning observed on the warm run (`state/canonicalization/aliases.json` absent → empty-ledger string-normalization-only mode, D-R5-8). Pre-existing sandbox condition, unrelated to #122; flagged here so it isn't rediscovered as news.
- Warm run's 2 probe sources were deepseek-compiled against a gemini-built graph — an accidental but clean split-model data point: pass-1 keys are content-derived, so cross-model resolution worked exactly as same-model would. Relevant to #118's split-model experiment design.

## What this surfaced

This baseline was run to establish "before" numbers for pass-1/pass-2 work. What it actually surfaced is bigger: **#123 — semantic graph search, the project's single objective, does not exist** (finding 4). The numbers above are the "before" for that work: T2 delivered ≈ 0 pages/source cold and 3.5 warm, when it should be full. #122's T1/T2/T3 event-time metrics stand unchanged as the measurement each #123 iteration will be judged by; #118 (split-model + pass-1 diagnostics) resumes after #123.
