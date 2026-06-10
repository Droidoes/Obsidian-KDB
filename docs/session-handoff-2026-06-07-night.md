# Session handoff — 2026-06-07 (night)

> Third block of the 2026-06-07 mega-session. Covers #109 closure + strategic reflection on the 2.0/ingestion question.

## ⏩ END OF SESSION — #109 CLOSED; ingestion arc strategy open

Short session. **`main` @ `853a66d`**, 1 ahead of origin (unpushed wrap docs).

### What happened

1. **#109 CLOSED.** (`853a66d`)
   - τ=0.5 PINNED in `compiler/kpi/score.py` (comment: PINNED — baseline-1 confirmed)
   - λ=0.10 PINNED (cap comment updated)
   - `docs/CODEBASE_OVERVIEW.md §7` fully rewritten — describes the `kdb-orchestrate --emit-kpis` → `kdb-benchmark score` architecture; old #5 engine / M0-M7 / D26-D31 stale content removed
   - Milestone Changelog entry added (2026-06-07)
   - `docs/TASKS.md` #109 → closed
   - Promotion rule (`tools/benchmark/promotion.py`) deliberately NOT run — no stable cohort yet to exercise it (baseline-1 is 4 models; promotion needs ≥4 rounds to converge CoV/IQR gates)

2. **Strategic reflection: 2.0 Claim layer before or after the big ingest?**

   Joseph's question: *"should we build 2.0 into pass-1 and pass-2 before we should ingest large amount of source in earnest?"* — i.e., run the full Obsidian vault ONCE and get both the entity graph (1.0) and the Claim graph (2.0) in the same pass, rather than paying double.

   **What 2.0 actually enables:**
   - Synthesis: "what do my sources claim about [entity]?" — Claim nodes ABOUT that entity
   - Contradiction detection: CONTRADICTS edges between Claims on the same entity
   - Evidence weight: Claim EVIDENCED by N independent sources = load-bearing vs. single-source
   - Gap detection: entities with high LINKS_TO but no Claims = referenced but never asserted about
   - Belief revision (#83/#84): flag new Claims that CONTRADICT existing ones

   **Option B — the realistic double-sweep path:**
   - Claim tables already exist at v2.2 in schema.py (empty, non-destructive migration)
   - At 2.0, a targeted Claim extraction sweep reads `pages[].body` from `compile_result.json` (on disk), fires one focused LLM call per source
   - This is NOT a full re-orchestrate — body text is cached, extraction is a single targeted pass
   - Cost: ~$0.10–0.20 at deepseek rates for ~200 sources

   **Where the discussion landed (no decision made):**
   - The double-sweep cost via Option B is real but not painful
   - 2.0 Claim extraction design is NOT yet stable — prompt + pipeline integration are TBD
   - The risk of baking an unproven extraction pass into the pipeline is adding complexity before the basic ingest-at-scale is validated
   - Joseph wanted to "pause for reflection" — open question for next session

## OPEN — pick up here

- [ ] **Strategic decision (Joseph's call):** build 2.0 Claim extraction into the pipeline FIRST (one full vault pass gets entity+Claim graph), OR do 0.6→1.0 entity-only ingest first and run a targeted Option-B Claim sweep at 2.0?
  - **Lean for doing 1.0 first:** 2.0 design unproven; ingest-at-scale is where the risk is; Option B sweep cost is small
  - **Lean for 2.0 first:** avoid double LLM run; richer graph from day one; cleaner corpus consistency
- [ ] **0.6 → 1.0 arc** — feeder implementations (ingestion/feeder/ is currently empty: only `__init__.py`); design the Obsidian vault feeder
- [ ] **#107** — deferred Phase-B polish (viewer packaging, `compiler.compiler` double-name, orchestrator→tools.cleanup decoupling)

## Housekeeping

- `main` @ `853a66d`, 1 ahead of origin — push when wrap docs committed
- `__version__` stale at 0.5.2 — git-describe authoritative; cosmetic
- #91/#88 ledger entries somewhat stale (fully implemented but ledger says "v0.2 ratified" / "v0.4 ratified") — not blocking

## Pointers

- North Star: `docs/CODEBASE_OVERVIEW.md` (§7 freshly accurate, Milestone Changelog has #109 + #111 entries)
- Ledger: `docs/TASKS.md` (#109 closed, #111 closed)
- Benchmark: `benchmark/scores/leaderboard.md` (baseline-1: gpt #1 84.67 / deepseek #2 54.67 / gemini #3 21.33 / qwen #4 9.33)
- Schema: `kdb_graph/schema.py` SCHEMA_VERSION=2.4; Claim tables at v2.2, empty, ready
- Compiled output: `compile_result.json` per source has `pages[].body` — the Option B input for future Claim sweep
