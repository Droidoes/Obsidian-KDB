# Session handoff — 2026-07-23 (written 00:47 EDT, covers the 7-22 late-night → 7-23 session)

> Richest single catch-up artifact for the next session. Resume from this file alone.

## ⏩ STATE — #115 CLOSED END-TO-END (merged `cc85a6d`, boards `f8c9ad8`, **PUSHED to origin**, branch + vault prompts cleaned); **#119 FILED** (Pass-2 normalization boundary); **NEXT ACTION: #119 design pass** (architecture options → Joseph's pick → blueprint → Codex rounds)

Session arc: Phase-5 comparison cohort fired and analyzed → the first-ever Pass-2 quarantines surfaced a real design defect → first-principle failure analysis → Codex design review (revise-before-ratify, 6 blocking findings, all code-verified) → Joseph ratified: **close #115 with an explicit Phase-5 waiver; root-cause fix ships as #119** → closure committed, merged to main, leaderboards re-scored, **pushed** (`7d8263b..f8c9ad8`), branch deleted, stale vault prompts deleted. Working tree clean; `main == origin/main`.

---

### Arc 1: Phase-5 comparison cohort — gate FAILED, machinery worked

- Both models fired from the Gate-4 anchor `782120b` via `./scripts/sandbox-run.sh --model <m>` (Google Drive sync pause = Joseph's manual step; script text updated from OneDrive in `f4233f7`). Stamps verified: both runs `pass2_prompt_version 3.0.0` / prompt SHA `c550a69a…` (baseline 2.0.0 / `dcfa3d1c…`). Runs: deepseek `2026-07-22T22-27-32_EDT` (`v0.5.7-28-g782120b-dirty` — dirt = exactly the 2 files later committed as `f4233f7`), gpt `2026-07-22T23-10-03_EDT` (clean `v0.5.7-29-gf4233f7`).
- **Each model quarantined exactly one source — the first Pass-2 quarantines ever on this corpus.** deepseek authored `summary-…-gemini31` vs derived `summary-…-gemini3-1`; gpt authored `summary-whats-react-and-tailwind` vs `summary-what-s-react-and-tailwind`. Same class: model *deletes* punctuation instead of hyphenating. Typed telemetry correct (`failure_stage: validate`, `SemanticCheckError`); zero bad writes; Pass-1 zero quarantines.
- **Proved pre-existing:** baseline `parsed_summary` records show identical deviations at prompt 2.0.0, passed silently (no gate existed). The gate made an old behavior visible.
- **The ratified KPI gate (quarantine/retry stable vs baseline) FAILED:** 0 → 1 quarantine + one wasted retry per model. Kimi's v1.0 "explained deltas" reading **retracted** (Codex F1; the gate's delta carve-out covers graph-KPI canonical-collision cases only).

### Arc 2: Failure analysis + Codex R1 + disposition

- Analysis doc: `docs/superpowers/specs/2026-07-22-task115-phase5-summary-slug-failure-analysis.md` — **v1.1** (disposition ratified, Codex R1 absorbed, v1.0 errors corrected).
- Codex R1 (`…-review-codex.md`, same dir): **revise before ratification** — root issue broader than the summary slug: **canonical representation is enforced at the raw model-response boundary before any deterministic normalization stage exists** (`compiler/compiler.py:309-475`; strict schema requires `slug` on raw pages, `compiled_source_response.schema.json:37-42`). Governing rule: **reject ambiguity, not harmless representational differences** — normalize when Python can resolve exactly one valid meaning by role/provenance/registry/context authority (never string similarity); reject on ambiguity/collision/loss.
- **Verification: all 6 blocking + 3 accuracy findings code-verified; zero false positives.** v1.0 had 4 genuine errors, corrected in v1.1: (1) "explained deltas"; (2) "deletes the source's content" (actually `error_compile`, prior content survives — `orchestrator/kdb_orchestrate.py:754-770`); (3) "uniqueness only" (slug = wiki filename + graph identity + wikilink target + manifest identity + replay identity); (4) "post-canon invariant trivially true" (canonicalize guard + post-canon invariant stay the fail-closed pair — `canonicalize.py:424-457`, `compiler.py:717-736`).
- **Joseph's disposition (2026-07-23):** close #115 with the **explicit waiver** (quarantine behavior accepted as temporary production behavior — fail-closed: retry spend + per-run source absence); **#119** carries the full root-cause fix, with the identical KPI gate + cohort re-fire as its acceptance criterion.

### Arc 3: Closure + merge + push (all landed)

- Closure commit `175671e` (docs-only): analysis v1.1, TASKS.md (#115→Closed with waiver on record; **#119 filed**, full scope + acceptance gate), Milestone Changelog 2026-07-23 entry, handoff. Suite exit 0.
- Merge `cc85a6d` into `main` (12-commit #117 arc vs 6-commit #115 arc; 4 conflict files, all keep-BOTH): `common/measurement.py` (#117 forward-compat header filter kept; #115 `pass2_system_prompt_sha256` loads via dataclass default), `common/tests/test_measurement.py` (auto-merged), TASKS.md (union: Open #116/#118/#119; Closed …#114/#117/#115), CODEBASE_OVERVIEW.md (both changelog entries, reverse-chron). **Merged suite: 1502 passed, 1 live-skip, 1 bench-deselected.**
- Leaderboard re-score committed `f8c9ad8`: both 3.0.0 comparison rows live on all three boards (9 models; baselines stay separate keys). Phase-5 finding visible in diagnostics: `quarantine_rate_pass2` 2.88 (deepseek) / 2.65 (gpt) vs 0.0 baselines; gpt retry in `recovery_rate_pass2` 5.31; no `unranked` rows.
- **Pushed** `7d8263b..f8c9ad8` → `main == origin/main`. Branch `feat/115-pass2-contract` deleted (was `175671e`; `-d` confirmed fully merged).
- **Vault prompts deleted** (Joseph-approved): `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` + sandbox copy. The Pass-2 prompt is now **repo-only** (`compiler/prompts/`); 2.0.0 text preserved in git at `e9ca323`; `compiler/tests/test_prompt_builder.py` 22/22 green post-deletion.

---

### Next (in order)

1. **#119 design pass** — architecture cycle per the AGENTS.md state machine: options (1 in-place proposal normalizer / 2 explicit dual schemas / 3 typed intent decoder) → Joseph's pick → North-Star update FIRST (it still records "fully model-authored including its slug") → blueprint → Codex rounds. Seed: analysis v1.1 §5 + Codex R1. Open design questions: does summary `slug` stay in the proposal contract (links-to-summary constraint; prompt injection stays a #115-ratified non-goal); bypass-vs-fail-closed for summary identities in alias resolution; per-field ownership audit drives the rest.
2. WS2 OneNote preflight → WS3 vault-in-place rollout (gated on #94 + #116) → WS4 MCP revisit → WS5 GraphDB-KDB extraction Stage 1.

### Housekeeping

- Always `.venv/bin/python -m pytest` (bare `pytest` is the broken system install). **Count quirk:** addopts already carries `-q`; adding another `-q` stacks to `-qq` and SWALLOWS the final count line — run bare (no extra flags) for counts, or trust the exit code.
- Vault state: `~/Obsidian/Vault-in-place-test-run` holds the gpt comparison run's output. `benchmark/runs/` is git-ignored — measurements live on disk only.
- Joseph migrated vault sync OneDrive → **Google Drive**; `scripts/sandbox-run.sh` prompts accordingly (since `f4233f7`).
- Codex review pattern held again: Kimi drafts artifact + prompt, Joseph runs Codex, Kimi verifies EVERY finding against code before absorbing. This round: Codex right on everything; v1.0's errors were Kimi's to fix.
- Entire session inline (no subagent dispatches), per standing preference.

### Pointers

- #119 seed + verification record: `docs/superpowers/specs/2026-07-22-task115-phase5-summary-slug-failure-analysis.md` (v1.1) + `…-review-codex.md`.
- Ledger: `docs/TASKS.md` (#115 Closed; #119 Open with full scope).
- North Star: `docs/CODEBASE_OVERVIEW.md` Milestone Changelog 2026-07-23 (closure+waiver) atop 2026-07-22 (#117, DESIGN LOCKED).
- #119 regression fixtures (future): `GraphRAG for Adaptive KB - Gemini3.1.md`, `what's React and Tailwind.md`.
- Prior handoffs: `docs/session-handoff-2026-07-22.md` (+ `-evening`).
