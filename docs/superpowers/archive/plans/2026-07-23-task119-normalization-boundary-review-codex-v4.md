# Task #119 Normalization Boundary Implementation Plan — Codex Review (Round 4)

- **Reviewed artifact:** `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md`
- **Governing blueprint:** `docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md` v0.3
- **Review date:** 2026-07-23
- **Verdict:** **REVISE BEFORE EXECUTION**

Round 4 absorbs the previous findings in direction, but one load-bearing conservation defect remains. The amended blueprint also needs explicit re-ratification.

## Findings

### 1. High — `NormalizationOp` is still not the true source of truth

The plan claims transformations are applied from operations and drift is structurally impossible:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:656`

In practice, slugs, summary identity, and bodies are still mutated directly alongside operation recording:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:851`
- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:924`
- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:973`

Conservation is only one-directional and loses operation identity:

- Repeated body rewrites collapse into `body_ops[page][raw] = canonical`. One recorded operation can therefore “explain” multiple changed occurrences.
- `r.get("slug")` conflates an absent summary slug with an explicit JSON `null`.
- A stray summary slug already equal to the derived slug bypasses the `rs != cs` block, so missing stamp and ignore operations are not detected.
- Unused or spurious operations are not rejected.

Relevant conservation implementation:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1137`

**Required resolution:** Give every operation an exact target path or occurrence offset, construct canonical output through a single `_apply_normalization_plan(raw, ops)` function, and verify a bijection: every diff consumes exactly one applicable operation and every operation is consumed. Add negative tests for duplicate token occurrences, explicit-null stray slugs, already-canonical stray slugs, missing operations, and unused operations.

### 2. High — The governing blueprint was amended after ratification

The blueprint still identifies itself as ratified v0.3:

- `docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md:1`

Its conservation authority was changed after the Proceed gate:

- `docs/superpowers/archive/specs/2026-07-23-task119-normalization-boundary-blueprint.md:161`

The plan itself acknowledges that Joseph must reconfirm this amendment:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1834`

This is load-bearing, not editorial.

**Required resolution:** Version the amendment explicitly—preferably v0.4—and obtain Joseph’s explicit re-ratification before implementation begins.

### 3. Medium — The Phase 3 atomic commit omits required files

The proposed `git add` command omits modifications assigned to Phase 3:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1604`

Missing files:

- `compiler/resp_summary.py`
- `compiler/validate_source_response.py`
- `orchestrator/tests/test_kdb_orchestrate.py`

That would leave the working tree dirty and exclude the page-count fix and authoritative prompt-stamp test from the supposedly atomic commit.

**Required resolution:** Add every Phase 3 file explicitly or stage through a tightly scoped directory set, then verify `git status --short` is empty before the commit gate.

### 4. Medium — Retiring `repair.py` drops token-parity coverage

The plan removes the coercion parity consumer and relies on only `page-mapped-rewrite` and `body-only-token-preserved`:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1517`

Those cases do not preserve coverage for authoritative mapped rewrites inside escaped tokens, fenced code, inline code, duplicates, unclosed syntax, and heading/display combinations.

**Required resolution:** Migrate the shared parity corpus to a bridge projection, such as `expected_body_bridge`. Construct response-page mappings for authority-valid cases and assert byte-identical preservation for protected or body-only cases. Update the corpus description and remove obsolete repair-specific fields only after equivalent bridge coverage exists.

### 5. Medium — The new system tests still contain placeholders and a vacuous assertion

The retry matrix contains:

```python
assert ... in slugs or True
```

That assertion can never fail:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1450`

The `compile_source` test calls undefined `_conn(tmp_path)` and refers to a nonexistent `kdb_graph.testing` helper:

- `docs/superpowers/archive/plans/2026-07-23-task119-normalization-boundary.md:1582`

It also claims zero-write coverage without asserting it.

**Required resolution:**

- Assert `expected_summary_slug(source_id)` exactly and require `cs is not None`.
- Use the established `GraphDB(tmp_path / "graph")` context pattern or pass a prebuilt `ContextSnapshot` with `conn=None`.
- Assert no wiki or manifest writes occurred.
- Provide local or imported definitions for every helper in the test listing.

### 6. Medium — “Bounded telemetry” is bounded per field, not in aggregate

Each repeated body-link occurrence emits another always-on decision. The list has no count or byte cap, despite being described as small and bounded.

**Required resolution:** Define an aggregate telemetry bound. A practical shape would retain total operation count plus bounded located samples and an overflow digest. The full internal operation plan can remain lossless in memory for conservation.

## Conclusion

Once the operation plan is genuinely authoritative, the blueprint is re-ratified, and the Phase 3 verification details are executable, this should be close to implementation-ready.

No implementation files were changed and no tests were run during this document review.
