# Session Handoff — 2026-07-22 (evening) — #115 Gate-2 ready, pre-commit review pending

## Where we are

- **Branch**: `feat/115-pass2-contract` (HEAD = `e9ca323` Gate 0 + uncommitted Phases 1–2 work).
- **Full suite GREEN: 1360 passed / 1 live-skip** (Gate 0 was 1386: −55 retired pairing/reconcile tests, +29 new contract tests).
- **Next action**: Joseph decides on a **Codex review of the working-tree diff BEFORE the Gate-2 commit** (option 1 recommended over commit-then-review), then **Gate-2 commit** (ONE commit per blueprint):
  `feat(compiler): #115 — Pass-2 contract revision (Phases 1-2, Gate 2)`

## Session arc

1. **#117 CLOSED** (per-pass leaderboards): spec v0.3.1 + plan v1.4 (Codex 3+5 rounds), 9 commits, merged to `main` (`241c1ae`), branch deleted, suite 1436 green on main. Live 3-board leaderboard in `benchmark/scores/` — Pass-1 cost spread visible (deepseek $0.050 vs gpt-5.4-mini $0.306), the #118 evidence base. **All three boards are TRACKED now** (`.gitignore` rule removed — Joseph's call).
2. **#118 filed** (split-model runs, revive after #116).
3. **#115 baseline cohort COMPLETE**: deepseek + gpt-5.4-mini fired from Gate-0 `e9ca323` (stamps verified: `pass2_prompt_version 2.0.0` + sha `dcfa3d1c…`), scored into 3 boards, checkpoints committed (`c4083f6`, `72cd309`). GPT baseline = main-board #1 (78.83); deepseek baseline = Pass-1 board #1.
4. **#115 Phases 1–2 implemented** (all 12 blueprint tasks, TDD, suite green).

## #115 Phases 1–2 — what shipped (uncommitted, ~45 files)

- Schema: 4-field pages + optional `compilation_notes`; aggregate schema dual-mode (removed fields optional-deprecated).
- Prompt: rewritten in `compiler/prompts/` (D-115-7 fixes), `PASS2_PROMPT_VERSION = "3.0.0"`; exemplar rewritten.
- `compiler/summary_slug.expected_summary_slug` centralized (guard equivalence pinned); pre-call underivable-stem route (`FailureStage` + `"validate"`; inner record AND outer result both `validate`, attempts=0, zero tokens, no model call); semantic gate = exactly one summary + derived slug; post-canon re-check.
- `compile_one` rewired (3-tuple return); `Repair` stage deleted whole; canonicalize body-authority + `CanonicalizationError` (summary merges/renames rejected); dual-mode `validate_compile_result`; graph intake derives LINKS_TO from body wikilinks, legacy `outgoing_links` preferred (R8 edge-erasure pinned); `_combine_crs` → `compilation_notes`; `summary_page()` fail-closed helper in `common/types.py`; `PageStatus`/`Confidence` aliases deleted; `ParsedSummary` modernized; recovery fixtures migrated (18 new-shape + 19.txt legacy-negative); replay + `kdb-validate-response` on `--source-id`; mixed-shape journal pair rebuild test.

## Known loose ends / decisions pending

- **Codex review of the Gate-2 diff before commit?** Joseph asked; recommendation given (yes, option 1: review-then-commit). He hasn't picked yet.
- **Phase-0 loose end (unanswered)**: `compiler/prompts/KDB-Compiler-System-Prompt.md` was committed mode 100755 — cosmetic; offer to `chmod 644` + amend still open.
- **Graph-HTML gap**: accepted by Joseph ("keeping the graph for the last run is good enough"). No #119.
- **Runbook checklist refresh**: deferred by Joseph (cohort ritual lives in `docs/reference/test-run-procedure.md` + `benchmark-cohort-procedure.md` — the latter has 2 stale lines: `--provider/--model` style + "leaderboard gitignored").
- **After Gate 2**: Phases 3 (confidence deprecation + snapshot v7), 4 (parity corpus + system tests), 5 (comparison cohort, Joseph). **Merge reconciliation with #117 on `common/measurement.py`** at merge time (keep #115 stamps + #117 cost_usd/filtering/stats loader).
- `main` is 13+ commits ahead of origin — push stays Joseph's gate.
