# Session handoff — 2026-06-02

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ STATUS UPDATE (end of session) — Phase B SHIPPED as v0.5.2

Everything below this box was the *morning* plan; it has all been executed. Current state:
- **🏁 v0.5.2 shipped to `main`** — codebase realignment **Phase B** (Task #105 CLOSED). Six-package split (`common`/`ingestion`/`compiler`/`kdb_graph`/`orchestrator`/`tools`), executed **subagent-driven** (13 tasks), **run-7 clean**, B.3 dependency contract guard-tested, `resp_stats_writer` split. **5-panel code review → GO-WITH-FIXES**, all F1–F6 folded. Merge `f28220e`, closure `d6620b9`, tag `v0.5.2`. 1191 non-live tests green.
- **⚠ NOT pushed** — the merge + tag are local only; **push is held for Joseph** (`git push && git push --tags`). Branch `refactor/phase-b-package-split` merged (can be deleted).
- **Resume OneDrive sync** (was paused for run-7).
- **NEXT ARC = Task #106** (JSON-repair + slug-coercion robustness ladder), now landing in the real `common/util` + `compiler/repair` homes: **panel-review its spec** (`docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md`) → `writing-plans` → TDD → run-8. Then **Task #107** (3 non-blocking Phase-B follow-ups: viewer packaging · `compiler.compiler` rename · cleanup decoupling).

---

## Where we are

- **v0.5.1 shipped** earlier today — codebase realignment **Phase A** (Task #105), tagged + pushed (`fede8f6`; Phase-A code `8fac79f`). Zero-behavior-change refactor; **run-6 clean** (29 compiled / 7 noise / 0 quarantined / 478 links / 0 orphans; graph 180 Entity / 29 Source / 10 Domain / 100% BELONGS_TO). 1175 non-live tests green. Working tree clean on `main`.
- This session's work was **design + documentation only** (no code): we shaped **Task #106** (JSON-repair + slug-coercion ladder) and **re-sequenced** it behind Phase B.

## Decisions made this session

1. **SEQUENCE FLIP — Phase B FIRST, then #106** (reverses the morning's "#106-first" call). Rationale: #106's helpers belong in `common/` + `compiler/repair` — exactly the packages Phase B *creates* — so B-first lands them in final homes with zero relocation, makes placement trivial, and makes #106 a real-feature shakedown of B's boundaries. Phase B is zero-behavior-change, so the two recurring malformation cases stay retry-rescued throughout B → **no robustness gap from waiting**. Both still land before 0.6.
   **Order: Phase B → run-7 (validate zero-behavior-change) → #106 → run-8 (validate robustness).**
2. **`util` ⊂ `common` taxonomy** (Joseph: *"util is common, common may not be util"*): generic stateless helpers → `common/util/` (json_repair = first occupant; Phase B does **not** pre-create the dir). Slug-collapse stays in `common/paths` — it's slug **policy** (sibling of `slugify`/`validate_slug`), common but not a util.
3. **#106 design conservative + re-validation-gated** — ladder `emit → repair/normalize → retry → repair/normalize → quarantine`; slug coercion = collapse `-{2,}`→`-` + edge-strip only (enforce the D19 `slugify` rule; no intent-guessing — uppercase/space slugs still fail→retry→quarantine).

## #106 design is fully captured — no memory-dig needed

**Spec: `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md`** — homes table, full slug-propagation field list, collision guard, conservative-scope boundary, the rung-1 LaTeX content-fidelity ⚠, placement in `compile_one`, measurability rung taxonomy, TDD test plan. Two live cases ground it: Borda (JSON-syntax, unescaped LaTeX `\(n-1\)`), Sleep-and-Aging (`summary-…aging---research-on-aging` slug).

## Next session — exact plan

1. **Realignment Phase B** (Task #105 Phase B) — split `kdb_compiler` monolith into peer packages `common`/`ingestion`/`compiler`/`graph`(=`kdb_graph`)/`orchestrator`/`tools`. **PLAN WRITTEN + COMMITTED (`9bb9f60`): `docs/superpowers/plans/2026-06-02-phase-b-package-split.md`** (13 tasks, leaf-first `common→kdb_graph→ingestion→compiler→orchestrator→tools`, move-don't-rewrite, 1175-test net per task). **Decision (Joseph 2026-06-02): skip plan-level panel** (design already 5-panel ratified; mechanical refactor; Phase-A precedent) → **execute subagent-driven** (two-stage review per task *is* the plan's review). Branch `refactor/phase-b-package-split`. Gate: non-live green + **run-7** (Joseph fires). **After run-7 clean: full external panel CODE review of the whole migration diff** (Joseph), then merge + tag `v0.5.2`. Deferred Phase-B cleanups (`failure_stage="reconcile"`→`"repair"`, `JOURNEY.md:118` noun fix, `resp_stats_writer` split) are folded into the plan (Tasks 8, 12).
2. **Then Task #106** into the new homes — **first: external panel review of the spec** (project-default panel; CLI reviewers under output-file-only guardrail) against the now-real `common/`+`compiler/` structure; fold feedback → `writing-plans` from the spec → TDD → live **run-8**. Own branch. **Writing-plans MUST address:** (a) rung-1 content-fidelity — probe `json-repair`'s actual behavior on an invalid `\(` escape and decide targeted backslash-escaping vs. trusting the guess; the test asserts the LaTeX *survives*, not just that it parses. (b) body `[[slug]]` rewrite is whole-token, not substring-replace.

## Open loops (housekeeping)

- [ ] **Resume OneDrive sync** (paused for run-6 — vault + Kuzu graph are OneDrive-synced; corruption hazard while a run is mid-flight).
- [ ] Confirm the orchestrator path has canonicalize-as-a-stage integration coverage (the deleted legacy test was driver-coupled; the end-to-end-stage assertion was lost).
- [ ] This session's doc/memory updates are **uncommitted** — commit when ready (spec, TASKS.md #106 row, daily note, this handoff; memory files are outside the repo).

## Pointers

- Task ledger: `docs/TASKS.md` (#105 Phase B open; #106 design-ratified/deferred).
- North Star: `docs/CODEBASE_OVERVIEW.md`. Journey: `docs/JOURNEY.md`.
- Memory: `project_json_repair_coerce_ladder` (updated this session — sequence flipped, homes, spec path), `project_codebase_realignment`.
