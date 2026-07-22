# Task #117 implementation plan v1.3 — Codex review

**Reviewed:** 2026-07-22  
**Plan:** `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md`  
**Verdict:** Request v1.4 before Proceed.

v1.3 resolves the raw-evidence, false-`missing_kpis`, and competition-ranking logic from v1.2. Two validation gaps and one task-ordering defect remain.

## Findings

### 1. High — an invalid fallback header can still abort all boards

`_fallback_raw()` checks the type of `signal` but not `p1_attempted` before calculating `signal / p1_attempted`. For example, a `measurements.json` header containing `"p1_attempted": "4"` and `signal: 3` raises `TypeError`. The `p1_failed` calculation has the same problem.

Additionally, when all three values are zero, `p1_failed` becomes `None` because the condition requires truthy `p1_attempted`; the correct disposition count is zero.

**Required correction:** Validate `p1_attempted`, `signal`, and `noise` as non-boolean integers before arithmetic. Keep eligibility `None` for a zero denominator, but calculate `p1_failed=0` when all three valid fields are zero. Add a no-`run_state` CLI or builder test with a wrong-typed fallback header.

### 2. Medium — the production loader bypasses the new type validators

Header validation runs only when `tolerate_malformed=True`, and measurement validation is likewise restricted to that path. Consequently, the supposedly strict production loader can return wrong-typed objects, contradicting its own `"any malformed file raises"` contract.

**Required correction:** Run validation on both paths. On the strict path, raise `TypeError`; on the tolerant path, count malformed call records and continue. Add strict-loader tests for wrong-typed header and measurement fields.

### 3. Medium — Task 4 cannot reach its green commit gate as written

The competition-ranking test in Task 4 calls `_render_leaderboard_md(..., board=...)`, but board-aware rendering is not implemented until Task 5. Therefore Task 4's expected-green test run and commit gate will fail with the pre-Task-5 renderer.

**Required correction:** Keep the `[1, 1, 3]` payload assertion in Task 4 and move the rendered-Markdown assertion into Task 5.

## Resolved since v1.2

- Valid fallback rows now preserve measurements-header dispositions and eligibility.
- Header-failure rows no longer invent missing KPI names when the fallback evidence is complete.
- The competition-ranking scenario now contains two tied leaders and a lower third row, correctly exercising `[1, 1, 3]`.
- Wrong-typed run-state telemetry is validated on the tolerant score-time path, although the validation must still be extended to the strict and fallback paths above.

## Recommendation

Correct the three items above and issue v1.4. The architecture and seven-task decomposition remain sound and do not need to be reopened.

This was a static plan/spec review. No implementation files were changed and implementation tests were not run.
