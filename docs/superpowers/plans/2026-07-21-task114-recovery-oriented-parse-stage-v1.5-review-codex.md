# Task #114 Plan v1.5 Review (Codex)

**Reviewed:** 2026-07-21  
**Plan:** `docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md`  
**Specification:** `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md` (v0.3.6)  
**Verdict:** **GO WITH CHANGES**

The architecture and implementation sequence are ready. All substantive
findings from v1.4 are resolved; two mechanical corrections remain.

## Findings

### 1. Medium: The `nulljunk` test has the wrong tail count

`nulljunk {"a": 1}` is 17 characters, and `raw_decode` ends after the
four-character root `null`, leaving **13** trailing characters. Plan line 195
expects 12, so Task 1 cannot reach its 22-passing-test gate.

Correct assertion:

```python
assert parse_document_prefix('nulljunk {"a": 1}') == (None, 0, 13)
```

The isolated oracle check produced:

```text
nulljunk {"a": 1} -> root=None, end=4, tail=13
trueTAIL {"a": 1} -> root=True, end=4, tail=13
falsehood          -> root=False, end=5, tail=4
```

### 2. Low: Plan v1.5 still targets spec v0.3.5

Update the Goal at plan line 5 and the global root-preservation reference at
plan line 90 to v0.3.6. Historical revision entries should remain unchanged.

## Conclusion

After those corrections, I find no remaining design or sequencing blockers.

## Verification

No files other than this review were modified and no test suite was run. Only
the isolated decoder-oracle check above was executed.
