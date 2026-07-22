# Session handoff — 2026-07-22 (written 00:25 EDT, covers the 7-21 evening session)

> Richest single catch-up artifact for the next session. Resume from this file alone.

## ⏩ STATE — #114 MERGED + PUSHED; #115 fully designed (spec v1.6 + blueprint v1.10 DESCOPED, committed `5946081`) with #116 split out; **NEXT ACTION: North-Star docs update (pre-implementation gate), then Phase 0**

An evening session (Kimi Code) with two arcs: (1) #114 closed out — Codex pre-merge review → 2 Important fixes → merge → push; (2) #115 taken from a one-line ledger row through a full design cycle — audit → 4 spec rounds → Joseph's §1–§8 decision walk → blueprint through 10 Codex rounds → descoped v1.10 ratified. Everything is committed on `main`, unpushed (`5946081` + `8af7139`, 2 ahead).

---

### Arc 1: #114 closure (merged + pushed)

- Codex pre-merge review (`docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage-pre-merge-review-codex.md`): GO WITH CHANGES, 2 Important, both verified + fixed + tested:
  - **F1**: `unwrap_response` fused multiple fenced blocks — a `null` block + object block would recover JSON `null` → quarantine. Fixed with the spec-mandated parse-based disambiguation (`compiler/response_normalizer.py:98`).
  - **F2**: `failed_after_response` treated non-gating `extract_ok=False` as failure → raw source text persisted on recovered successes even with capture unset. Fixed to derive from gating verdicts only (`common/llm_telemetry.py:156`).
- Suite 1384 green; merged ff `3b4e300..7d8263b` (14 commits); **pushed `718e75d..7d8263b`**.
- No tag cut — `v0.5.7` still the latest; #114 is the first untagged feature on main.

### Arc 2: #115 design cycle (complete, implementation-ready)

**What it became:** not a prompt cleanup — a derivation-first Pass-2 contract revision. The LLM emits wiki-native data only; Python owns everything mechanical.

**Spec v1.6** (`docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md`) — D-115-1..15 + carve addendum, 4 Codex spec rounds absorbed. Joseph's ratified calls (several reversed reviewer leans):
- Six fields OUT of the LLM contract: `concept_slugs`, `article_slugs`, top-level `summary_slug`, `outgoing_links`, `source_name`, `status`. No Python reconstruction of the removed aggregates.
- **Design principle (Joseph): the contract speaks wiki, not graph** — pages, bodies, `[[wikilinks]]`; no edge-list projections.
- Summary page stays fully model-authored INcluding its slug (no prompt injection — Joseph rejected the exception mechanism; exact-stem rule enforced by gate).
- **Prompt moves to the repo** (`compiler/prompts/`); provenance = git + `pass2_prompt_version` + one loaded-text SHA (Joseph killed the 6-component fingerprint set as unwanted complexity).
- `warnings` → **`compilation_notes`** (kept, optional — 12/115 cohort sources proved real diagnostic value); `log_entries` dropped (write-only journal; `related_source_ids` injection was fictitious).
- `confidence` deprecated end-to-end (logical — Entity scope only; Claim tier untouched). Joseph: "a dimension we don't need." 956 high/45 med/0 low.
- `page_type` kept — the model's one earned classification field. No GLM A/B (retired, too slow; mechanism stays a supported hypothesis).

**Blueprint v1.10** (`docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md`) — 10 Codex rounds (R5–R14). Key structural content:
- **The carve (R12 + Joseph):** reservation-preflight / MOVED-lifecycle / durability subsystem carved to **#116** after R8–R11 accreted a write-ahead transaction subsystem inside what was supposed to be a contract task. Accepted temporary behavior: normalized derived-slug collisions keep wiki-LWW/graph-co-ownership (existing behavior, NOT a regression).
- **#116 filed** (ledger): source-lifecycle convergence + durability, paired with #94 as a WS3 pre-production gate. v1.7 archived verbatim as its CANDIDATE (not ratified) design seed: `docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md` (R13 F1 caught that the untracked blueprint had been overwritten — reconstructed from session history).
- D-115-11 formally split: #115 keeps per-source exactness; #116 owns cross-source collision/reservation.
- Phases: 0 (prompt to repo + stamps + **normalized-`expected_summary_slug` cohort guard BEFORE baseline**) → baseline cohort (Joseph fires) → 1–2 contract commit → 3 confidence deprecation → 4 parity/system tests → 5 comparison cohort. Every gate = Joseph's explicit approval.
- Notable hardening preserved from review: post-canon EXACT summary re-validation (alias-bypass), body-authority links (losing-body links die — accepted), graph-owned wikilink derivation w/ legacy `outgoing_links` fallback INSIDE the contract commit (else Gate-2 HEAD erases edges on recompile), repair stage deleted whole, dual-mode aggregate validation, `ParsedSummary` best-effort migration, stem-failure route pinned (`FailureStage` gains `"validate"`).

---

### Next (in order)

1. **North-Star docs update** (pre-implementation gate): `docs/CODEBASE_OVERVIEW.md` — body-only Pass-2 response + graph-owned edge derivation; canonicalization rewrites body wikilinks; logical confidence deprecation (D-A2 reversal); repo-owned prompt; Python-owned `status` boundary; Repair-stage deletion + stage-flow renumbering. NO MOVED/WAL content. Own docs commit (Joseph's approval).
2. **Phase 0**: prompt copy + anchor-hash verify (`dcfa3d1c…`), loader switch, package-data + offline wheel smoke, stamps populate, harnesses off vault-prompt writes, **Task 0.3 cohort collision guard (zero normalized derived-slug collisions, persisted)**. Gate-0 commit → **Joseph fires baseline cohort** (gpt-5.4-mini + deepseek-v4-flash).
3. Phases 1–2 contract commit → Phase 3 → Phase 4 → Phase 5 comparison cohort → #115 closure.
4. Push `main` (2 commits ahead) — Joseph's gate.
5. WS2 OneNote preflight → WS3 (gated on #94 + #116) → WS4/WS5.

### Housekeeping

- **Subagent usage**: last billing note said prefer inline — this whole session was inline (no dispatches). Continue inline unless told otherwise.
- `kdb-orchestrate` on PATH is broken — always use `.venv/bin/` binaries. Bare `pytest` for counts (`-q` stacks to `-qq`).
- Codex CLI: `codex exec review --base main` REJECTS a custom prompt — use plain `codex exec` with the prompt, or run interactively (Joseph ran all 14 review rounds himself by pasting prompts).
- The review-round pattern that worked: I draft the artifact + the review prompt with evidence anchors; Joseph runs Codex; I verify EVERY finding against code before absorbing (caught zero false positives this session — Codex was right every time, incl. 3 contradictions in my own blueprint drafts).
- Live vault prompt SHA (pre-move anchor, pinned in Gate-0 test): `dcfa3d1cd9c1e7c543527b5d4357ce46fb9f1e31a766a8127b8565942c11e12a`.
- Vault prompt defects awaiting Phase 1 fix: line-1 `do youd#`, "manifest snapshot" (line 13), "aborts the run" (line 209).

### Pointers

- Blueprint: `docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md` (v1.10) + 10 Codex review files beside it.
- Spec: `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md` (v1.6) + 4 spec review files.
- #116 seed: `docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md`.
- Ledger: `docs/TASKS.md` rows #115 (v1.10 descoped), #116 (proposed).
- Prior handoff: `docs/session-handoff-2026-07-21-pm.md` (WS1 closure + #114 execution detail).
