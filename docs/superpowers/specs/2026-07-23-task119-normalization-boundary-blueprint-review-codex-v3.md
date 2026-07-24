# Task #119 Normalization Boundary Blueprint — Codex Re-review

- **Reviewed artifact:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md`
- **Reviewed version:** v0.4 amendment (pending re-ratification)
- **Review date:** 2026-07-23
- **Verdict:** **REVISE BEFORE RE-RATIFICATION**

The core Option 2 architecture remains sound, and the v0.4 status/version and decision-count semantics are improved. One load-bearing contract and several telemetry inconsistencies remain.

## Findings

### 1. High — `NormalizationOp` is authoritative but has no blueprint-level contract

Section 3.3 defines decisions and bridge results, but not `NormalizationOp`:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:53`

Section 5 then makes that undefined type the transformation and conservation authority:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:161`

This leaves unresolved:

- Exact target identity—field, page, token occurrence or offset.
- Absent slug versus explicit JSON `null`.
- Valid kind/field/authority combinations.
- No-op policy for an already-canonical stray summary slug.
- Plan completeness: exactly one summary-resolution operation on every accepted proposal.
- Whether body operations are applied against immutable raw text or sequentially mutated text.
- Whether every operation and every raw-to-canonical difference must match bijectively.

These ambiguities have already produced multiple incompatible implementation-plan revisions.

**Required resolution:** Add a discriminated `NormalizationOp` contract and pin PLAN → APPLY → VERIFY:

1. Construct a complete plan without mutation.
2. Validate kind, authority, target, raw presence/value, and occurrence.
3. Apply all operations against the immutable raw proposal.
4. Require exactly one summary-resolution operation, including no-op resolution.
5. Independently verify operation/difference bijection.
6. Reject missing, extra, malformed, or inapplicable operations as `CanonicalInvariantError`.

### 2. Medium — Capped decisions cannot always reconstruct canonical output

The persisted list is capped at 50 decisions with only a digest for the remaining tail:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:98`

The next paragraph still says raw proposal plus decisions reconstruct the canonical object under capture-full:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:100`

That is true only when no overflow occurred; a digest cannot reconstruct omitted transformations.

**Required resolution:** Qualify reconstruction as requiring both capture-full and `normalization_decisions_overflow_sha256 is None`. With overflow, describe the evidence as auditable but non-reconstructive.

### 3. Medium — The typed rejection surface includes unreachable classes

`REWRITE_AMBIGUITY` appears in the enum, retry table, bridge rules, and required Phase 0 negatives:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:62`
- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:141`
- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:194`

Under the defined algorithm, exact response-local mappings are unique and collisions reject before rewriting. No ambiguity can reach the rewrite stage.

`STRUCTURAL_INSUFFICIENCY` is similarly listed as a bridge reject class even though proposal validation occurs before the bridge.

**Required resolution:** Remove unreachable members from the active bridge contract, or define a concrete reachable algorithm and fixture for each. Removing them is simpler and keeps rejection ownership honest.

### 4. Medium — The telemetry truth table contradicts itself

`semantic_ok` is defined as bridge acceptance plus successful canonical self-check:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:111`

The invariant-error row then says `CanonicalInvariantError` may occur after `semantic_ok` passed:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:116`

Both cannot be true.

**Required resolution:** State that canonical invariant failure leaves `semantic_ok=False`; failed-response capture fires because the complete gating tuple did not pass.

### 5. Medium — `ParsedSummary` 4.0 semantics are absent from the blueprint

The blueprint treats `parsed_summary` as always-on acceptance evidence, but current code calculates `page_count` from collected slugs:

- `compiler/resp_summary.py:56`

A compliant 4.0 summary has no raw slug, so it is undercounted.

The implementation plan contains a fix, but the governing blueprint does not record this telemetry contract change.

**Required resolution:** Add to the decision delta and test plan:

- `page_count` counts well-formed page dictionaries.
- `slugs` and `summary_slug` represent raw model-supplied slug evidence only.
- Slugless, string-stray, and non-string-stray summary cases retain the correct page count.

### 6. Low — “No writes” overstates the system-test boundary

The system test says `compile_source` performs no writes:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:208`

However, `compile_one` always persists response telemetry:

- `compiler/compiler.py:596`

Use: “no product-state writes—wiki, manifest, compile-result, or graph; response telemetry remains allowed.”

## Conclusion

Once the operation contract and telemetry contradictions are resolved, v0.4 should be ready for explicit re-ratification.

No files other than this review artifact were changed, and no tests were run during this architecture review.
