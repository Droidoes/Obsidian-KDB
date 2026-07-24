# Task #119 Normalization Boundary Implementation Plan — Codex Review (Round 3)

- **Reviewed artifact:** `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md`
- **Governing blueprint:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md` v0.3 (ratified)
- **Review date:** 2026-07-23
- **Verdict:** **REVISE BEFORE EXECUTION**

The Round 2 findings are largely absorbed correctly. One load-bearing architecture mismatch and several verification gaps remain.

## Findings

### 1. High — Conservation no longer enforces the ratified decision-list contract

The blueprint requires every raw-to-canonical difference to be explained by the recorded decision list:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:161`

The Round 3 plan instead maintains separate `rename` and `body_ops` structures while excluding telemetry decisions from conservation:

- `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md:921`
- `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md:1055`

This creates two sources of truth that can drift. In particular, summary changes can pass conservation without proving that the corresponding stamp or ignore operation was recorded.

**Required resolution:** Define one lossless, typed internal `NormalizationOp` plan covering slug coercion, summary stamping or ignoring, and body rewrites. Apply transformations, derive bounded telemetry, and perform conservation checks from that single source. If the intended architecture is now that decisions are only a telemetry projection rather than the conservation authority, amend and re-ratify the blueprint before implementation.

### 2. Medium — `ParsedSummary` is incompatible with compliant 4.0 proposals

`compiler/resp_summary.py:56` calculates:

```python
page_count=len(page_slugs)
```

A valid 4.0 response has no model-supplied summary slug, so this calculation undercounts the number of well-formed page objects by one. The blueprint treats `parsed_summary` as always-on acceptance evidence:

- `compiler/resp_summary.py:56`
- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:99`

**Required resolution:** Count well-formed page objects independently of whether they contain a slug. Document `slugs` and `summary_slug` explicitly as the raw model-supplied slug evidence. Add tests for an absent summary slug and for stray-string and non-string summary-slug variants.

### 3. Medium — The retry matrix claims coverage that is absent

The plan states that proposal structural insufficiency is tested through a concept page missing its slug:

- `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md:1311`

No corresponding `compile_one` boundary test is specified. Likewise, malformed and non-string stray summary-slug variants are tested only at schema or bridge level, not through the required clean-compile, zero-retry behavior.

**Required resolution:** Add table-driven `compile_one` tests for:

- Proposal schema failure
- Zero summary pages
- Two summary pages
- Derived-slug collision
- Uncoercible slug
- Absent summary slug
- Deviating summary slug
- Malformed summary slug
- Non-string summary slug

For every case, assert model call count, final exception or success type, normalization decisions, and final status.

### 4. Medium — The Phase 3 dry-run gate is assigned to the wrong test surface

Prompt stamps are produced by the orchestrator, not by `common.measurement`. The existing authoritative test already checks prompt version and SHA:

- `orchestrator/tests/test_kdb_orchestrate.py:1025`

The plan instead directs new assertions into `common/tests/test_measurement.py`:

- `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md:1385`

The required `compile_source` integration test also remains prose rather than a concrete test:

- `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md:1426`

**Required resolution:** Explicitly extend or reference the orchestrator prompt-stamp test. Specify and implement an actual `compile_source` integration test that mocks the model response rather than mocking `compile_one`; mocking `compile_one` would bypass the bridge being verified.

### 5. Medium — Telemetry is still not fully bounded, and the blueprint type contract is stale

The proposed body-rewrite decision embeds the entire raw token in `location`:

- `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md:935`

That bypasses the 120-character bound. The blueprint also still states that all string values remain in `raw_value`, while the plan now hashes oversized strings:

- `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:71`

**Required resolution:** Use a bounded location such as page identity plus occurrence index or character offset. Update the blueprint's telemetry type and redaction contract before implementation so it matches the planned bounded representation.

### 6. Low — Remaining accuracy and consistency issues

- The CLI rejects `--source-id` without a canonical slug only after reading and parsing input. In stdin mode, this can block unnecessarily. Validate the argument relationship immediately after `parse_args`.
- Contract docstrings for `prompt_builder`, `compile_one`, and `semantic_check` still say that the model authors the summary slug.
- The Task 2.5 and Phase 4 headings are duplicated.
- The CLI section says there are three new tests but lists four.

## Conclusion

Once the conservation and telemetry contract has one source of truth and the missing system telemetry tests are assigned, the plan should be close to executable.

No implementation files were changed and no tests were run during this document review.
