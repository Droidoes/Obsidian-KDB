Final code review request — Task #119 (Pass-2 normalization boundary), pre-merge whole-branch checkpoint.

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch feat/119-normalization-boundary. This is the last external review before the Phase-5 live acceptance cohort fires from this branch and the merge decision is made.

## Branch state

12 commits, `4d60e6d..727dd4c` (main..HEAD). Full suite 1650 passed / 1 skipped / 1 deselected.

- Phases 0–4 complete: regression corpus → proposal schema + canonical re-role + CLI → the bridge (PLAN-APPLY-VERIFY) → atomic switch (`compile_one` rewiring + prompt 4.0.0 + `repair.py` retirement) → replay era dispatch + measurement diagnostics.
- Your R1 (REVISE, 5 findings) absorbed as `c1f3f95`; your R2 (REVISE, 4 findings) absorbed as `436a996` (prompt now 4.0.1 with the golden version→SHA guard). Both fix waves independently re-reviewed clean.
- SDD final whole-branch review just completed: **Ready for the Phase-5 live gate — Yes**, 0 Critical/Important. Nine accumulated minors all triaged accept-as-is (they batch into the Phase-5 closure commit).

## What to review

  git log --oneline 4d60e6d..727dd4c
  git diff 4d60e6d..727dd4c -- compiler/ common/ tools/ tests/ orchestrator/ kdb_graph/

You have already seen the riskiest artifacts at R1/R2 — this pass is for what survives across review rounds: cross-phase seam defects, anything your earlier rounds missed, and anything that only matters on a LIVE run (the next step executes the real pipeline against the vault sandbox from this branch).

Specific asks:
1. **Live-run safety.** Phase 5 runs `sandbox-run.sh` with deepseek-v4-flash and gpt-5.4-mini from this branch. Anything in the rewired `compile_one` → `page_writer` → graph intake → manifest path that could corrupt vault, graph, or manifest state on real model output? The produce-don't-write seam: `compile_source` must still write nothing but resp-stats telemetry; the commit boundary (manifest LAST) must be intact.
2. **Seam re-verification post-R1/R2.** The fix waves touched `_freeze`/`_json_equal`, `_validate_plan`, prompt bytes, test harnesses. Confirm no comparison site on stray raw values bypasses `_json_equal`, and the truth-table/telemetry wiring is unchanged by the fix waves.
3. **The minors list** (below) — concur with accept-as-is, or does any of them bite in production?
   - `_rewrite_body` in proposal_bridge.py: defined, never called (plan-listed interface; superseded by `_apply_body_ops`)
   - dead `expected_slug` binding at compiler.py:237 (the call's PathError side-effect is load-bearing; the binding is dead)
   - rule-2 direct `p["page_type"]`/`p["slug"]` indexing (unreachable post-schema-gate)
   - body-rewrite telemetry `location` = per-page index, not per-token occurrence (doc wording)
   - "cleared per attempt by the reset below" comment misdirection (reset is at loop head)
   - no bool-stray BridgeSuccess success-path test (bool covered by fault-injection negatives)
   - plain "4.0.0" era wording at compiler.py:174, prompt_builder.py:103, resp_summary.py:13
   - CLI tests assert exit codes not stderr text; boundary-test lint nits (unused Path import, mid-file pytest import)
4. **KPI comparability across eras.** Phase 5 compares this branch's cohort against the zero-quarantine Phase-0 baseline (`e9ca323`, prompt 3.0.0). §3.5 semantics: clean-with-stamping must project as clean (never repaired/retried). Confirm the KPI consumer surface (`compiler/kpi/processing.py`) reads only fields whose semantics didn't change, so a 4.0.1 clean-with-stamping run is comparable to a 3.0.0 clean run.

## Verdict

GO (fire Phase 5) or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/plans/2026-07-24-task119-final-review-codex.md
