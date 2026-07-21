# Task #114 Plan v1.1 Review (Codex)

**Reviewed:** 2026-07-21  
**Plan:** `docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md`  
**Specification:** `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md` (v0.3.2)  
**Verdict:** **REVISE BEFORE EXECUTION**

Plan v1.1 resolves the previous review findings, but the v0.3.2 "any JSON
value" amendment introduces three new integration defects.

## Findings

### 1. High: JSON `null` is indistinguishable from recovery failure

`json.loads("null")` returns Python `None`, while
`RecoveryResult.parsed=None` is also the failure sentinel. Both `compile_one`
and replay use `result.parsed is None` to detect failure, so valid JSON `null`
would be reported as a parse or truncation failure instead of reaching schema
validation.

References:

- Plan lines 265-276: `RecoveryResult` interface.
- Plan lines 431-463: recovery implementation and failure sentinel.
- Plan lines 780-808: `compile_one` failure check.
- Plan lines 973-977: replay failure check.

**Required change:** Add an explicit `recovered: bool`/`success: bool` field or
a private sentinel. Test `null` through recovery, `compile_one`, and replay.

### 2. High: Boundary recovery can lift an object out of a top-level array

`parse_document_prefix` always starts at the first `{`. For
`[{"a": 1}]\nTAIL`, it skips the structural `[` and returns `{"a": 1}` rather
than the complete top-level list. A schema-valid compile object wrapped in an
invalid top-level array could therefore pass schema after carrier noise is
added, while the clean array correctly fails schema.

This violates the v0.3.2 rule that schema owns the top-level contract and
undermines the safety argument in specification section 3.2.

**Required change:** Preserve the root value. First attempt `raw_decode` at
the first non-whitespace character when it begins a JSON value. If that
character is `[` and decoding fails, do not scan into nested `{` values. Add a
regression test for an array containing a schema-valid object plus trailing
junk.

### 3. High: Non-object values crash the existing slug-coercion rung

The plan correctly sends lists and scalars to schema validation, but after
schema failure `compile_one` unconditionally calls
`coerce_slugs_and_propagate`. That function expects a dict and immediately
calls `.get()`, producing `AttributeError` instead of retry or quarantine.

References:

- `compiler/compiler.py:408-425`: unconditional coercion after schema failure.
- `compiler/repair.py:160-164`: `_all_slug_values` assumes a dict.

**Required change:** Guard coercion with `isinstance(parsed_json, dict)` or
make the helper accept `object` and return `False` for non-dicts. Add
compiler-level list, scalar, and `null` cases asserting schema retry or
quarantine without exceptions.

### 4. Medium: Task 2 will fail an existing architectural test

Adding public `unwrap_response` conflicts with the hard-coded public-function
assertion in `compiler/tests/test_response_normalizer.py:142-150`. Task 2 says
existing strict tests remain untouched, but this assertion must be updated to
include `unwrap_response`.

### 5. Medium: The plan does not verify the complete fixture acceptance contract

Specification lines 204-207 require all 19 positive fixtures to produce
`final_status="repaired"` with exact recovery telemetry. The plan runs
recovery, schema, and semantic checks over all 19 but sends only three through
`compile_one` (plan lines 697-730).

**Required change:** Parameterize `compile_one` over all 19, or explicitly
narrow the specification's acceptance criterion to three representative
end-to-end cases.

### 6. Low: The specification's `extract_ok` wording remains overbroad

Specification lines 226-228 say a trailing-junk response records
`extract_ok=False`, while brace-ending junk remains shape-conformant and
records `True`. Plan v1.1 handles this correctly. Amend the specification to
say "non-brace trailing junk."

## Verification

No implementation files were modified and no tests were run. This was a
static plan-and-integration review.
