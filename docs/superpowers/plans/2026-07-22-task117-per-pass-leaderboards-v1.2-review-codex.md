# Task #117 implementation plan v1.2 — Codex review

**Reviewed:** 2026-07-22  
**Plan:** `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md`  
**Verdict:** Request v1.3 before Proceed.

v1.2 is close, but it is not ready for ratification. Two v1.1 corrections are complete, one is partial, and one exposed a deeper projection-boundary problem.

## Findings

### 1. High — type-invalid telemetry can still abort all boards

The loader constructs dataclasses without runtime type validation, and the sidecar projections behave similarly. Values such as `"total_input_tokens": "100"` or `"scanned": "4"` are accepted, then raise `TypeError` during `compute_processing()`, outside the header exception guard in `_build_row()`.

This was reproduced against the current dataclasses: both invalid values remained strings and telemetry computation raised `TypeError`.

**Required correction:** Validate KPI-relevant field types at the projection boundary so malformed calls increment `*_malformed` and malformed headers make only that row unranked. Add tests for a wrong-typed header field and a wrong-typed sidecar or Pass-2 numeric field.

### 2. Medium — fallback rows still omit available header-derived evidence

`_fallback_raw()` preserves suffixed diagnostics and graph KPIs, but it cannot emit `pass2_eligibility_rate`, `p1_noise`, or `p1_failed`, even though those values remain available in `measurements.json`. CLI integration passes only `diagnostics_by_model`, not the already-read measurements header.

This only partially resolves the earlier `raw_values` finding and conflicts with the persisted evidence contract in spec §3.

**Required correction:** Pass the measurements headers or a prepared fallback-raw map into the builder. Include header-derived disposition and eligibility values, and represent unavailable coverage explicitly as `None`.

### 3. Medium — the header-failure path can report false `missing_kpis`

The expression `_missing_from(raw, pass_) or list(_AXES)` labels all three processing KPIs missing when fallback evidence actually contains every required KPI. In that case, only `completeness_errors=["header_unparseable"]` is true.

**Required correction:** Return `_missing_from(...)` unchanged. An empty `missing_kpis` list is valid when a separate completeness violation excludes the row.

### 4. Medium — the competition-ranking test does not verify `1, 1, 3`

`test_tied_models_share_competition_rank()` makes every model tie and expects `[1, 1, 1]`. That verifies shared rank but cannot distinguish competition ranking from dense ranking once a lower-scoring row follows. D-117-9 explicitly requires the skipped rank and displayed output.

**Required correction:** Create two tied leaders plus one lower row, assert `[1, 1, 3]`, and verify those ranks in rendered Markdown.

## v1.1 finding status

- The short-Pass-2 completeness test is correctly isolated with all four graph KPIs present.
- The renderer helper now passes an empty scored-value map and locates the raw table header robustly.
- Header exception handling is improved, but does not catch type-invalid values that fail after dataclass construction.
- Unranked raw-value preservation is improved, but missing-`run_state` and bad-header fallback rows still omit available header-derived evidence.

## Recommendation

Correct the four items above and issue v1.3. The architecture and seven-task decomposition do not need to be reopened.

This was a static plan/spec review plus a read-only reproduction of the type-validation failure. No implementation files were changed and implementation tests were not run.
