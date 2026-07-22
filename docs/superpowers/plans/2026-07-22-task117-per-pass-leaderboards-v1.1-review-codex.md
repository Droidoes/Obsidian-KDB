# Task #117 implementation plan v1.1 — Codex review

**Reviewed:** 2026-07-22  
**Plan:** `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md`  
**Verdict:** Request one more plan revision before Proceed.

The v1.1 plan is much stronger and resolves all seven findings from the prior review. Four issues remain—one blocks ratification. No architectural redesign is needed; these are contained contract and test corrections.

## Findings

### 1. High — malformed headers can still abort all three boards

`_build_row()` catches only `OSError` and `JSONDecodeError`. A valid JSON header with missing fields, the wrong top-level type, or invalid encoding can raise `TypeError`, `AttributeError`, or `UnicodeDecodeError` and escape the row-level fail-closed path. That contradicts D-117-5: the affected row should become unranked, not abort leaderboard generation.

The caught-error return also writes `"problems"` instead of `"completeness_errors"`, causing the reason to be discarded by `build_pass_board()`.

**Required correction:** Catch the bounded header-deserialization exceptions, return `completeness_errors=["header_unparseable"]`, and test both malformed JSON and valid-but-structurally-invalid headers.

### 2. Medium — the short Pass-2 test is masked by missing graph KPIs

`test_short_pass2_records_unranked_on_pass2_only()` supplies an empty graph map. The row therefore remains unranked because all four required graph KPIs are missing even if the `p2_records == p2_attempted` check is broken.

**Required correction:** Supply all four non-`None` graph KPIs so the short record count is the test's only failure condition.

### 3. Medium — unranked rows discard available raw evidence

The partial-row branch returns only the three split processing axes. It drops already available retry, cost, unknown-cost, Pass-2 graph, coverage, eligibility, and disposition values. This conflicts with the spec's `"available raw values"` contract for every unranked row.

The missing-`run_state` branch also hardcodes `missing_kpis=["recovery_rate"]` instead of deriving the field from the available evidence.

**Required correction:** Assemble `raw_values` and derive `missing_kpis` before the completeness return so ranked and unranked rows use the same evidence contract.

### 4. Medium — the renderer test helper contradicts the implementation contract

The `_render()` test helper passes Borda values as `scored_by_model`, although the plan correctly states that pass-board callers must pass `{}`. Consequently, the raw table gains the bare Borda columns that `test_raw_table_shows_measured_values_not_borda()` prohibits.

Additionally, `raw_section.splitlines()[1]` selects a blank line with the current renderer layout, not the column header.

**Required correction:** Pass `{}` as `scored_by_model` and locate the first line beginning with `| model |` instead of using a fixed line index.

## Prior-review resolution

The seven findings from the preceding review are otherwise addressed:

- all required processing and Pass-2 graph KPI inputs are gated;
- the production measurement loader remains strict;
- all six output payloads are serialized before the first write;
- the rendering contract separates measured values from Borda values;
- the Task 3 test mechanics are corrected;
- the main-board byte-equivalence test uses an independent golden fixture; and
- the overlap with Task #115 is explicitly documented.

## Recommendation

Revise the four items above, then request Proceed. The architecture and task decomposition do not need to be reopened.

This was a static plan/spec/code review. No implementation tests were run because the implementation does not yet exist.
