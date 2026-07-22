# Task 117 Per-Pass Leaderboards — Codex Implementation-Plan Review

**Review date:** 2026-07-22  
**Reviewed plan:** `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md`  
**Verdict:** Revise before execution

The overall decomposition is good, but the plan is not ready to execute as written. Four implementation-level blockers and several test-plan defects remain. These are localized fixes; the ratified architecture does not need reopening.

## Findings

### 1. High — Task 4 still permits pro-rata scoring on missing required KPIs

The builder calculates missing processing axes, but never uses `missing` to exclude the row. It also never checks missing graph KPIs.

Consequently, a count-complete row with zero-token processing values or a missing graph KPI reaches `score_models`, which silently pro-rates the remaining axes—the exact behavior D-117-5 prohibits.

Use all required axes in the gate:

```python
required = list(_AXES)
if pass_ == "pass2":
    required.extend(GRAPH_KPIS)

missing = [k for k in required if scored.get(k) is None]

if problems or missing:
    return unranked_row(...)
```

Add tests for:

- Count-complete Pass-1 records with zero tokens and therefore `None` KPIs.
- A complete Pass-2 telemetry set with one absent graph KPI.
- A complete Pass-2 set with one graph KPI explicitly `None`.

`missing_kpis` should contain canonical KPI names. Completeness violations should be carried separately as something like `completeness_errors`; currently `_why(problems)` places non-KPI reason strings inside `missing_kpis`.

Evidence:

- Plan: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:793`
- Scorer pro-rata behavior: `compiler/kpi/score.py:109`

### 2. High — Task 2 changes production-pipeline failure behavior

The proposed `load_run_measurements` wrapper delegates to the tolerant stats loader. That means malformed files which currently raise would instead be silently skipped.

This affects production KPI emission because `emit_run_kpis` uses `load_run_measurements`. Today a malformed record causes KPI emission to fail safely; the proposed wrapper could emit measurements computed from partial evidence. That contradicts the plan's “no pipeline behavior changes” constraint.

Keep the existing loader strict. One option is:

```python
_load_run_measurements(run_dir, *, tolerate_malformed: bool)
```

with:

- `load_run_measurements(...): tolerate_malformed=False`
- `load_run_measurements_with_stats(...): tolerate_malformed=True`

The tolerant path must also catch structurally valid but invalid records. The current proposal catches JSON decoding only; `from_pass1` and `from_pass2` can also raise `KeyError`, `TypeError`, `AttributeError`, or `ValueError`. Those should mark the individual file malformed and make that row unranked, not abort all three boards.

Add regression tests proving the original loader still raises while the stats loader records the same file as malformed.

Evidence:

- Proposed wrapper: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:250`
- Production caller: `orchestrator/emit_kpis.py:107`
- Existing emit failure boundary: `orchestrator/emit_kpis.py:198`

### 3. High — Task 6 does not validate JSON before beginning the commit

The plan renders Markdown before writing, but JSON serialization still occurs inside `atomic_write_json` during the write sequence. A non-serializable value in the second or third payload could therefore leave earlier artifacts replaced, despite being a failure that should have been detected during pre-write validation.

Pre-serialize all three payloads before the first write:

```python
json_texts = {
    main_path: json.dumps(main_payload, indent=2, ensure_ascii=False) + "\n",
    pass1_path: json.dumps(pass1_payload, indent=2, ensure_ascii=False) + "\n",
    pass2_path: json.dumps(pass2_payload, indent=2, ensure_ascii=False) + "\n",
}
```

After all JSON and Markdown strings are successfully prepared, write all six with `atomic_write_text`.

Add a test injecting a non-serializable value into the second pass-board payload and asserting that all prior artifacts remain byte-identical.

Evidence:

- Render/write sequence: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:1229`
- Atomic JSON serialization: `common/atomic_io.py:61`

### 4. High — the pass-board “raw measured values” table will contain Borda values

Task 6 passes each ranking row's `per_kpi_borda` as `scored_by_model`. The existing renderer treats that argument as the actual measurements behind the ranks.

The resulting table would label normalized values such as `0.0`, `0.5`, and `1.0` as raw quarantine, recovery, and latency measurements.

Either:

- Construct canonical raw values from each row's suffixed `raw_values`; or
- Make the board-aware renderer consume `raw_values` directly and reserve `per_kpi_borda` for the ranking table.

Add a test asserting that the raw table contains a known measured latency or rate—not its Borda score.

Evidence:

- Proposed renderer call: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:1235`
- Current raw-values renderer: `tools/benchmark/cli.py:94`

### 5. Medium — several TDD steps will fail for plan errors

The following mechanical problems remain:

- The recombination test reads `recovery_rate` from `diagnostic`, but it lives under `scored`.
- Task 3 adds eight diagnostics, taking the diagnostic tier from 9 to 17—not six and 15. The proposed set itself contains 17 keys.
- Task 2's tests call `load_run_measurements_with_stats` without adding it to the test module's import.
- `-k stats or wrapper` needs quoting: `-k "stats or wrapper"`.

These should be corrected before Task 1 begins so red/green failures remain meaningful.

Evidence:

- Broken recombination lookup: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:315`
- Diagnostic-count description: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:279`
- Unquoted test selector: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:182`

### 6. Medium — the renderer tests do not prove the stated contracts

The “byte-identical” main-board test only checks the title and presence of `graph_score`; it never compares complete output bytes. Use a pinned legacy golden string or fixture and assert exact equality.

The Pass-2 renderer test reuses rows whose `graph_score` is `None`. It therefore cannot prove that Pass-2 retains graph columns and prose. Give it genuine Pass-2 rows with populated graph scores and Pass-2 raw values.

Evidence:

- Main-board test: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:989`
- Pass-2 renderer test: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:984`

### 7. Medium — the branch-overlap constraint is inaccurate

The plan says never to touch files from `feat/115-pass2-contract`, but Tasks 1–2 modify `common/measurement.py` and its tests—the same files changed by #115 commit `e9ca323`.

Keeping #117 based on `main` may still be the right sequencing choice, but the plan should record the expected reconciliation:

- Preserve #115's `pass2_system_prompt_sha256` field and historical defaults.
- Preserve #117's forward-compatible header filtering, cost field, and stats loader.
- Run the combined measurement and orchestrator suites after rebasing or merging the two branches.

Evidence:

- Branch constraint: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:13`
- Task 1 files: `docs/superpowers/plans/2026-07-22-task117-per-pass-leaderboards.md:22`

## Conclusion

Revise the plan before authorizing Task 1. The task boundaries and overall architecture are solid; the required changes are corrections to the loader contract, required-KPI gate, serialization boundary, rendering data flow, and test fixtures.

This was a read-only implementation-plan review; no implementation tests were run.
