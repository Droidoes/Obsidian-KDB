# Task #114 Plan v1.4 Review (Codex)

**Reviewed:** 2026-07-21  
**Plan:** `docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md`  
**Specification:** `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md` (v0.3.5)  
**Verdict:** **REVISE BEFORE EXECUTION**

Plan v1.4 resolves the five v1.3 findings, but one root-selection gap remains.

## Findings

### 1. High: A complete literal followed by alphabetic carrier noise is misclassified as prose

The classifier only checks `literal.startswith(tok)`. For
`nulljunk {"a": 1}`, the token is `nulljunk`, so it falls back to `{` and
returns the later object. However, `raw_decode` successfully decodes the root
`null` at offset zero. This again violates "the root value wins."

Reference: plan lines 228-242.

An isolated probe confirmed:

```text
{
  'token': 'nulljunk',
  'is_root_candidate': False,
  'raw_root': (None, 4),
  'selected': ({'a': 1}, 17)
}
```

Recognize both directions:

```python
return any(
    text.startswith(lit, i) or lit.startswith(tok)
    for lit in ("true", "false", "null")
)
```

This handles complete literals with adjacent noise (`nulljunk`) and truncated
literals (`nul`) while preserving prose fallback for `note:`. Add tests for
`nulljunk`, `trueTAIL`, and `falsehood` followed by objects. For `nulljunk`,
assert a successful tuple containing `None`, not function-level failure.

### 2. Medium: The truncated-literal test commentary contradicts the adopted policy

Plan lines 170-173 still say `nul` enters the prose branch, while v1.4 now
treats it as an attempted root. The test passes under either route because no
later `{` exists, so the comment hides regressions. Remove that redundant test
or rewrite it to assert the adopted classification through a later-object
case.

### 3. Low: Specification test wording remains ambiguous about `nul`

Specification lines 243-246 say "`nul` is not `null`." Replace it with
"`nul` is an attempted truncated root and never triggers prose fallback."

### 4. Low: Prefix telemetry still says it is measured before the first `{`

With any-value root recovery, describe it as characters before the selected
root boundary. Update specification line 156 and plan line 674.

## Verification

No files other than this review were modified and no test suite was run. The
isolated classifier probe above was the only execution.
