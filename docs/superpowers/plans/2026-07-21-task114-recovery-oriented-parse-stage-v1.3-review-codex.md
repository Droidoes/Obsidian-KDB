# Task #114 Plan v1.3 Review (Codex)

**Reviewed:** 2026-07-21  
**Plan:** `docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md`  
**Specification:** `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md` (v0.3.4)  
**Verdict:** **REVISE BEFORE EXECUTION**

Most v1.2 findings are resolved, but the root-preservation fix is incomplete.

## Findings

### 1. High: Truncated literal roots can still be bypassed

`_is_value_start` recognizes only complete `true`/`false`/`null` prefixes.
Consequently, `nul {"a": 1}` is classified as prose, falls back to `{`, and
returns the nested object. This violates the rule that an undecodable root
must not be bypassed.

References:

- Plan lines 156-159: truncated-literal test and prose classification.
- Plan lines 199-204: `_is_value_start` implementation.

An isolated execution of the proposed logic confirmed:

```text
{'is_root_candidate': False, 'decoded': ({'a': 1}, 12)}
```

Add tests for `nul {"a": 1}`, `tru {"a": 1}`, and `fals {"a": 1}`. Two
coherent options exist:

1. **Strict root preservation:** Recognize proper prefixes of the three
   literals as attempted roots and return `None` when decoding fails.
2. **Exact-literal selection:** Retain the current implementation but
   explicitly ratify incomplete literal-like text as prose and narrow the
   "failed root is never scanned" safety claim.

Strict root preservation is consistent with the array-root rule and existing
safety argument.

### 2. Medium: Spec v0.3.4 and the plan interface still describe first-character classification

Both continue to say `t`, `f`, and `n` begin root candidates, while the
implementation requires full lexical prefixes.

References:

- Specification lines 119-124.
- Plan lines 85-90.

Pin the selected truncated-literal policy in both normative sections.

### 3. Low: Plan v1.3 still identifies its target as spec v0.3.3

Update the Goal and global root-preservation reference at plan lines 5 and 64
to v0.3.4.

### 4. Low: Task 1 contains 16 tests but expects 15 passed

Update the expected result at plan line 236.

### 5. Low: Task 6 bookkeeping excludes the newly added test 9

The failure-run instruction and self-review still say tests 3-8 at plan lines
876 and 1156. Change both to tests 3-9.

## Verification

No files other than this review were modified and no test suite was run. The
isolated prefix-classification probe above was the only execution.
