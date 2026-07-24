# Task #120 Spec v1.4 Review — Codex R5

**Date:** 2026-07-24

**Reviewed:** `docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md`

**Repository anchor:** `main` at `9a320fd`

**Verdict:** **GO**

Both R4 findings are correctly absorbed. The upper audit now samples the same all-edge population as `overall_resolved_density`, including summary/article edges; the clean-per-model cohort reset makes the current-cohort qualification exact. The task ledger also identifies v1.4 as a candidate awaiting ratification rather than closing the gate prematurely.

No architectural, acceptance, compatibility, or test-plan blocker remains. One non-blocking version-reference typo should be corrected when the design-doc commit is prepared.

## Findings

### 1. Minor — the implementation sketch still calls the design artifact spec v1.3

**Location:** spec `:59`

The v1.4 header, status, supersession note, and task ledger are current, but commit boundary 0 still says:

> design docs (spec v1.3 + review files + TASKS.md)

This does not change the implementation or acceptance design, but it would make the planned commit narrative point to the superseded version.

**Concrete fix:** change `spec v1.3` to `spec v1.4` before the design-doc commit.

## R4 absorption status

| R4 finding | v1.4 status |
|---|---|
| F1 — sample the same edge population measured by the upper trigger | **Fully absorbed.** Candidates now include all resolved edges counted by `overall_resolved_density`; ordering, min-denominator, final-occurrence authority, source page type, excerpts, and the tracked evaluation path remain pinned. |
| F2 — keep the ledger explicitly pre-ratification | **Fully absorbed.** Task #120 now says `Candidate design v1.4 (awaiting ratification)` and remains `proposed`. |

## Final design assessment

- **D1:** the constrained B+ wording restores both lost schema surfaces without mirror fields or invented-target authority.
- **D2:** `PASS2_PROMPT_VERSION = "4.0.2"` is the correct prompt-contract stamp; the system-prompt SHA remains unchanged.
- **D3:** `entity_search_key_resolution` is honestly documented as a mixed downstream realization signal, remains watched-not-scored, and its real decomposition is tracked in #118.
- **D4:** the DeepSeek restoration gate, GPT non-regression gate, exact resolved-edge equations, dangling/self/current-summary/namespace safety checks, exact upper trigger, all-edge semantic audit, and tracked evidence artifacts form a reproducible acceptance contract.
- **D5:** post-coercion `summary-` rejection is correctly model-retriable; applying the corrected invariant retrospectively across 4.x is explicit and replay-tested.
- **Gates:** implementation commits, live API cohort, and ratification/commit actions remain Joseph-gated.

## Verification performed

- Compared spec v1.4 with the R4 review and Kimi's round-5 prompt.
- Confirmed the upper candidate population now includes summary, concept, and article source edges.
- Confirmed the standard cohort procedure resets the graph before each model, so all edges counted by the trigger come from that run's final compiled-page occurrences.
- Confirmed `source_page_type` and the concrete final occurrence/raw-source evidence are persisted under the tracked `docs/superpowers/evaluations/` path.
- Confirmed the #118 decomposition scope and #120 candidate-v1.4 wording are present in the `docs/TASKS.md` worktree diff.
- Rechecked D1-D5 and found no regression from v1.3.
- No production code changed; this was a design review, so no test suite was rerun.

## Recommendation

**GO for Joseph's explicit ratification.** Correct the single `v1.3` typo while preparing the design-doc commit; it does not require another architecture-review round.
