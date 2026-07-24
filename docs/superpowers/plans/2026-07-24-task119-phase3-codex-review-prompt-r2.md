Code review request, round 2 — Task #119 execution checkpoint (Pass-2 normalization boundary).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch feat/119-normalization-boundary. All implementation phases (0–4) are now committed; full suite 1649 passed / 1 skipped / 1 deselected.

Your round-1 review (docs/superpowers/plans/2026-07-24-task119-phase3-execution-checkpoint-review-codex.md) returned REVISE with 2 Important + 3 Minor findings and a gate recommendation: do not accept Phase 2+3 until Findings 1 and 2 are fixed and their regressions pass. This round-2 has three parts.

## Part A — Phase 2+3 acceptance: verify your R1 fixes

Every R1 finding was controller-verified before fixing (your F1 True/1 fault-injection and F2 occurrence=99 no-op were both reproduced live). The fix wave is `c1f3f95`:

  git show c1f3f95

Verify finding by finding:
1. F1 (Important): `_freeze` now type-tagged for every JSON type + ABSENT + internal tuples (bool checked before int — the subclass trap); `_json_equal` applied at exactly your four named sites (apply raw-match, no-op discipline, slug diffing, non-noop-op filtering); regressions cover dict-vs-nested-array, True-vs-1 (value and hash), list-vs-tuple, ABSENT-vs-None, plus the end-to-end fault injection asserting CanonicalInvariantError on BOTH apply and conservation; legit non-string strays (dict/list/null) still succeed with bounded telemetry (D-119).
2. F2 (Important): slug ops with occurrence != 0 rejected for both kinds; negatives include the already-canonical no-op resolution with occurrence=99.
3. F3 (Minor): parity harness counts occurrences per-token identical to production; new corpus case `two-malformed-pages-authority-valid` exercises two distinct mapped tokens (verified to fail under the old global-enumerate harness).
4. F4/F5 (Minor): `compile_source` docstring and prompt prose now match blueprint v0.4 (no product-state writes; proposal response shape).

Confirm each regression is non-vacuous (fails pre-fix, passes post-fix), and adversarially probe the new type-tagged freeze itself (number unification int/float, nested key ordering, tuple-vs-array tagging) for anything the fix introduced.

## Part B — Phase 4 review (new since R1)

Phase 4 builds only on the public bridge interface, which the fix wave did not change:

  git show cdbc75f   # 4a: replay prompt_version dispatch in replay_case
  git show b1a4202   # 4b: measurement watched diagnostics

Constraints to check against:
- Era correctness (D-BQ-1): 3.x replays the legacy stack (recover → schema → semantic) — the v3 body must be a verbatim move; 4 existing fixtures untouched, keep era-correct verdicts via the "3.0.0" default. 4.x runs recover → proposal validate → bridge; `schema_ok` := proposal-schema ok, `semantic_ok` := BridgeSuccess; `result.extract_ok` propagated, never hardcoded; only `CanonicalInvariantError` and `PathError` caught (no broad except). 2.x/unknown → fail closed, all flags False + `matches_expected=False`.
- Measurement (D-BQ-3): the two new fields are watched diagnostics, never scored axes; `normalization_decision_count` projects the persisted count when present (63 must beat the truncated 50-sample list), falls back to `len(decisions or [])`; `summary_identity_derived` None-tolerant.

## Part C — fresh-eyes pass

Anything R1 missed across the branch's code commits (`git diff 4f356f0..b1a4202 -- compiler/ common/ tools/ tests/`) — especially the seams between phases: bridge → compile_one telemetry plumbing, resp_summary page_count on slugless summaries, prompt 4.0.0 contract text vs the proposal schema actually injected.

## Verdict

GO (Phase 2+3 accepted, Phase 4 accepted) or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/plans/2026-07-24-task119-execution-review-codex-r2.md

A final whole-branch Codex review follows before any merge to main (Phase 5 is the live acceptance cohort, Joseph-gated).
