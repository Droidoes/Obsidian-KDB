# Task #114 Implementation Plan Review - Codex

Date: 2026-07-21

## Verdict

`REVISE BEFORE EXECUTION`

The task decomposition and shared recovery API are strong, but the
sticky-state defect would produce incorrect production telemetry, one unit
test is impossible under the ratified contract, and the final verification
command is unsafe. The plan's admitted test sketches should be completed
before Proceed, especially the two-attempt state-reset case.

## Findings

### [Severity: High] `boundary_recovered` is incorrectly made sticky across attempts

References: implementation plan lines 622-625 and 709-716;
`compiler/tests/test_compiler.py:1394-1465`.

The plan says repair flags are sticky and ORs `boundary_recovered` into state.
Existing repair telemetry deliberately describes the winning attempt and
resets per attempt.

Attempt 1 boundary recovery followed by schema rejection, then a clean
attempt 2, would incorrectly become `retried-and-repaired` with
`boundary_recovered=True` and zero counts. Reset all three boundary fields per
attempt and assign the winning result directly. Add that exact two-attempt
regression test.

### [Severity: High] The Task 3 `extract_ok` test contradicts the pinned contract

References: implementation plan lines 266-271 and 375-383;
`compiler/response_normalizer.py:70-73`.

The plan expects `extract_ok=False` for `{"pages": []}\n}`. The strict
function only checks that text starts with `{` and ends with `}`, so it returns
`True` for that response.

Keep two distinct tests:

- Duplicated closing brace: `extract_ok=True`,
  `boundary_recovered=True`.
- Non-brace/prose tail: `extract_ok=False`,
  `boundary_recovered=True`.

The Task 6 end-to-end fixture must likewise not assume arbitrary fixture
`01.txt` has `extract_ok=False`.

### [Severity: High] The final verification command can hide pytest failure

Reference: implementation plan lines 940-945.

`.venv/bin/python -m pytest 2>&1 | tail -3` returns `tail`'s status unless
`pipefail` is active. A red suite can therefore produce a successful shell
exit.

Run pytest directly, or explicitly enable `pipefail`.

### [Severity: Medium] The fixture tests do not satisfy the spec's compiler-level gate

References: implementation plan lines 642-678; design spec lines 194-203.

The all-19 test only exercises `recover_json_response` and does not run schema
validation or `compile_one`. The ratified design requires every positive
fixture to be schema-clean and carry final compiler telemetry.

At minimum, schema-validate all 19 decoded objects. Prefer parameterizing
`compile_one` over all 19 using each manifest `source_id`, asserting successful
compile, boundary counts, and `final_status="repaired"`. The captured
`source_name` must match the test job or semantic validation will fail.

### [Severity: Medium] Task 8 names the wrong test file

References: implementation plan lines 896-935; actual file
`tools/tests/test_response_replay.py`.

The plan edits and commits `tools/tests/test_replay.py`, but the existing suite
is `tools/tests/test_response_replay.py`. As written, the commit command will
miss the updated test.

### [Severity: Medium] Complete non-object JSON is reclassified from schema failure to parse failure

References: implementation plan lines 248-249 and 312-315.

`recover_json_response` rejects a successfully decoded list as "no complete
JSON document." That conflicts with the principle that a complete document's
content is judged by schema and changes existing telemetry from
`schema_ok=False` to `parse_ok=False`.

Either return any cleanly decoded JSON value and let the schema reject it, or
explicitly ratify this telemetry change in the design.

### [Process] Every task contains an unconditional commit step

Repository instructions require explicit confirmation before commit. Convert
these to proposed commit boundaries and stop at the commit gate unless the
user separately authorizes commits.

## Validation Note

No files other than this review were changed and the full test suite was not
run.
