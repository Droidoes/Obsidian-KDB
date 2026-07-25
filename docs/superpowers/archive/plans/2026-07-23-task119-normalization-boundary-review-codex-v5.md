# Task #119 Normalization Boundary Implementation Plan — Codex Review (Round 5)

- **Reviewed artifact:** `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md`
- **Governing blueprint:** `docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md` v0.4 amendment (pending re-ratification)
- **Review date:** 2026-07-23
- **Verdict:** **REVISE BEFORE EXECUTION**

Round 5 correctly restores the v0.4 re-ratification gate and substantially improves the plan. Two load-bearing operation-model defects and several verification gaps remain.

## Findings

### 1. High — Duplicate body rewrites fail during plan application

Operations are constructed against the original body with occurrences `0`, `1`, and so on:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:993`

They are then applied sequentially to the already-mutated body:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1188`

For two `[[foo--bar]]` occurrences:

1. Operation 0 rewrites the first occurrence.
2. Only one raw occurrence remains.
3. Operation 1 searches for raw occurrence 1, but the remaining occurrence is now numbered 0.
4. `_rewrite_nth_occurrence` raises `CanonicalInvariantError`.

This breaks the duplicate-occurrence fixture that Round 5 specifically adds.

**Required resolution:** Apply all body operations for a page against the original body in one scan. Alternatively, apply occurrences in descending order, although a single-pass reconstruction is safer. Add an end-to-end `normalize_proposal` test with duplicate mapped tokens—not only direct conservation testing.

### 2. High — The claimed operation bijection still has semantic holes

`_check_conservation` removes every no-op operation before comparison:

```python
for op in ops if op.raw != op.canonical
```

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1324`

Consequences:

- If an already-canonical stray summary slug is present and the resolution operation is accidentally omitted, raw and canonical are identical, both multisets are empty, and conservation passes. The required ignore/stamp telemetry silently disappears.
- Arbitrary unused no-op operations also pass.
- Operation `kind` and `authority` are excluded from the comparison.
- `_apply_normalization_plan` dispatches on `field` only; every field other than `"slug"` is treated as `"body"`. A wrong kind/field combination can therefore be accepted.

**Required resolution:** Validate the plan’s structural contract independently:

- Exactly one `SUMMARY_IDENTITY_RESOLUTION` operation must exist for the summary, even when it is a no-op.
- Only summary identity resolution may be a no-op.
- Enforce the valid kind/field/authority matrix.
- Reject unknown fields, invalid indices, and invalid occurrences explicitly.
- Add tests for a missing already-canonical resolution operation, unused no-op, wrong kind, wrong authority, and unknown field.

### 3. Medium — Aggregate telemetry count is not wired consistently

`_cap_decisions` returns the total number of derived decisions:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:710`

The blueprint describes `normalization_decision_count` as the total number of operations:

- `docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md:98`

One summary-resolution operation may produce two decisions, so these quantities differ.

Phase 4 also says measurement should derive the count from `RespStatsRecord.normalization_decisions`:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1934`

After truncation, that list contains only 50 samples, so measurement would undercount.

**Required resolution:**

- Decide and document whether the field counts operations or decisions.
- Project the persisted `normalization_decision_count`, falling back to `len(normalization_decisions)` only for compatible older records.
- Add tests with more than 50 decisions for success and terminal-reject paths, asserting sample length, total count, stable overflow digest, and measurement projection.

### 4. Medium — The atomic Phase 3 commit still omits a required file

The revised staging command still omits:

- `compiler/validate_source_response.py`

That file is assigned a Phase 3 docstring update, but it is absent from the `git add` command:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1779`

**Required resolution:** Add it to the atomic commit list.

### 5. Medium — The `compile_source` write assertions check the wrong paths

The test passes `state_root=tmp_path`:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1753`

It checks:

```python
tmp_path / "state" / "compile_result.json"
tmp_path / "state" / "manifest.json"
```

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1763`

A regression writing directly beneath the supplied `state_root` would therefore pass unnoticed. Also, `compile_source` legitimately writes response telemetry, so “ZERO writes” is too broad.

**Required resolution:** Use a realistic `state_root = tmp_path / "KDB" / "state"` and assert the correct persistence paths. Document and permit the expected run telemetry while prohibiting wiki, compile-result, and manifest writes.

### 6. Low — The blueprint title still says v0.3

The status correctly identifies v0.4 as pending re-ratification, but the document title remains “Blueprint v0.3”:

- `docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md:1`

Update the title to v0.4 before presenting it for Joseph’s confirmation.

## Conclusion

Once the duplicate-operation executor and plan-validation holes are fixed, the plan should be close to ratification-ready. v0.4 must still receive Joseph’s explicit Proceed before implementation begins.

No implementation files were changed and no tests were run during this document review.
