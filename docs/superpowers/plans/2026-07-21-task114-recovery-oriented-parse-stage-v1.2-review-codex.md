# Task #114 Plan v1.2 Review (Codex)

**Reviewed:** 2026-07-21  
**Plan:** `docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md`  
**Specification:** `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md` (v0.3.3)  
**Verdict:** **REVISE BEFORE EXECUTION**

Plan v1.2 addresses all six v1.1 findings, but one blocking defect and several
contract gaps remain.

## Findings

### 1. High: Task 1's implementation fails its own prose test

`_JSON_VALUE_STARTS` includes `n`, so `note: {"a": 1} trailing` is treated as
a JSON-root candidate. `raw_decode` fails at `note`, and the implementation
returns `None` without attempting the prose fallback. This contradicts the
test at plan lines 96-97 and follows directly from the implementation at lines
192-200.

**Required change:** Classify `t`/`f`/`n` using the actual
`true`/`false`/`null` lexical prefixes, not their first character alone. The
design must explicitly distinguish truncated literals such as `nul` from
ordinary prose such as `note:`.

### 2. Medium: Spec v0.3.3 still contains the superseded first-`{` contract

The root-preserving rule at specification lines 118-123 conflicts with:

- The multi-document rule saying the first object wins at lines 58-60.
- Ladder step 2 saying decode from the first `{` at lines 92-94.
- The util contract still returning `tuple[dict, ...]` at lines 232-237.

**Required change:** Rewrite those passages around "root value first,
prose-only first-`{` fallback."

### 3. Medium: The incomplete real fixture is not tested through `compile_one`

The specification requires `Negative cash-conversion cycle.md` to retry twice
and quarantine with zero boundary telemetry (spec lines 229-231). Plan Task 6
only tests that fixture through `recover_json_response`; the end-to-end tests
cover the 19 positives and synthetic failures.

**Required change:** Add a `compile_one` test for `INCOMPLETE[0]` asserting two
calls, quarantine, `parse_ok=False`, `boundary_recovered=False`, and zero
discard counts.

### 4. Medium: The persisted telemetry types still exclude non-object JSON

The new contract allows any recovered value, but
`build_resp_stats.parsed_json` remains `dict | None` and
`RespStatsRecord.parsed_json` remains `Optional[dict]`; `compile_one` passes
lists and scalars through this surface on schema failure.

References:

- `common/llm_telemetry.py:81`
- `common/types.py:419`

**Required change:** Update both annotations to `object | None` and add a
serialization test for a non-object recovered payload.

### 5. Medium: Task 7 does not pin safe placement of its defaulted dataclass field

`PassCallMeasurement` currently has only required fields. Placing
`boundary_recovered: bool = False` beside `syntax_repaired` and `slug_coerced`
would put a default before later required fields and make the dataclass
invalid. Task 7 line 994 should explicitly say to append it after
`semantic_ok`.

### 6. Low: One root-preservation assertion is vacuous

`assert ... is None or True` at plan line 127 can never fail. Replace it with
the intended whole-array assertion or remove it because the preceding test
already covers that behavior.

## Verification

No implementation files were modified and no test suite was run. This was a
static design and implementation-plan review.
