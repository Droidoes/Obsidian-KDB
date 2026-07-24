# Task #119 Final Whole-Branch Code Review — Codex

**Date:** 2026-07-24

**Scope:** `4d60e6d..727dd4c` on `feat/119-normalization-boundary`, including R1 fix `c1f3f95` and R2 fix `436a996`

**Verdict:** **GO — fire Phase 5**

No Critical, Important, or Minor findings remain. The branch is safe to advance to the Phase-5 live acceptance cohort. Fire the cohort from a clean committed tree so its release commit and prompt provenance identify the exact reviewed state.

## Findings

None.

## 1. Live-run safety

The produce/commit boundary remains intact:

- `compile_source` explicitly permits only response-stat telemetry and performs no product-state write (`compiler/compiler.py:624-656`). It builds and validates the compile result in memory, runs in-memory canonicalization, and rechecks the exact summary identity before returning (`compiler/compiler.py:707-756`).
- The bridge schema gate and PLAN-APPLY-VERIFY invariants run before a canonical object can reach downstream writers (`compiler/compiler.py:425-483`; `compiler/proposal_bridge.py:318-331`).
- The post-canonical summary check executes before page writing, graph intake, or manifest advancement (`compiler/compiler.py:735-754`). A model-produced summary stray therefore cannot become a path authority.
- `_commit_source` preserves the established β ordering: compute the next manifest without I/O, atomically apply wiki pages, perform graph intake in a Kuzu transaction, then atomically write the manifest last as the commit boundary (`orchestrator/kdb_orchestrate.py:116-148`).
- Task #119 did not modify `compiler/page_writer.py`, `orchestrator/manifest_writer.py`, or the production commit ordering in `orchestrator/kdb_orchestrate.py`. Existing source-local failure behavior remains: an apply failure leaves graph and manifest untouched; graph or post-graph manifest failures leave the manifest unadvanced and are recoverable on rerun.

I found no path by which real model output can bypass proposal validation, bridge conservation, canonical validation, or the post-canonical summary invariant and corrupt vault, graph, or manifest identity.

## 2. R1/R2 seam re-verification

The R1 and R2 fixes remain correct when evaluated in the complete branch:

- `_freeze` is type-tagged and checks Boolean before number, preserving JSON-type identity (`compiler/proposal_bridge.py:477-507`).
- Every comparison involving an arbitrary summary-stray raw value uses `_json_equal`: application raw-match, plan no-op validation, conservation diff construction, and non-noop-op filtering (`compiler/proposal_bridge.py:349`, `466`, `537`, `548`). The remaining direct comparisons operate on schema-guaranteed strings such as concept/article slugs and wikilink tokens, so they are not stray-value bypasses.
- Slug operations are constrained to occurrence zero (`compiler/proposal_bridge.py:458-464`), and conservation independently checks the raw-to-canonical diff multiset against the operation multiset (`compiler/proposal_bridge.py:518-551`).
- Bridge telemetry is reset at every attempt (`compiler/compiler.py:330-351`), retained on terminal rejects, capped consistently, and projected from the winning attempt on success (`compiler/compiler.py:451-483`).
- Summary stamping/stray removal sets `summary_identity_derived` but does not set `slug_coerced`; only `slug_form_coercion` does (`compiler/compiler.py:474-483`). Consequently a one-attempt stamping-only result remains `final_status="clean"` (`compiler/compiler.py:545-563`).
- The named punctuation regression pins exactly that truth-table row: one call, no quarantine, clean status, `slug_coerced=False`, and raw proposal evidence preserved (`compiler/tests/test_compile_one_boundary.py:50-71`).
- Prompt provenance is closed: `PASS2_PROMPT_VERSION` is `4.0.1` (`compiler/prompt_builder.py:49`), and the packaged bytes are pinned to SHA-256 `afeff429761a98b71eadccfc3ca5b067d542d7e37764a8b4a90ae2192a8e5e1b` (`compiler/tests/test_prompt_builder.py:91-107`).

An additional direct bridge probe with Boolean summary-slug stray `true` reached `BridgeSuccess`, stamped the canonical summary identity, and retained bounded Boolean raw preview/hash evidence. This closes the only untested success shape from the accumulated minor list without exposing a production defect.

## 3. Accumulated-minor disposition

I concur with accept-as-is for all listed items:

1. `_rewrite_body` is dead internal code superseded by `_apply_body_ops`; it has no runtime effect.
2. The `expected_slug` binding is dead, but the call that produces it retains the load-bearing `PathError` validation side effect.
3. Direct rule-2 indexing is downstream of the proposal schema gate in both live compilation and 4.x replay, so malformed page dictionaries cannot reach it.
4. Body-rewrite `location` wording is imprecise, but page index, occurrence, raw value, and canonical value retain the information needed for audit and conservation.
5. The “reset below” wording is directionally wrong; the reset itself is correctly at the loop head and is test-covered.
6. The Boolean-stray success path works in direct execution; Boolean/number separation and fault-injection negatives cover the load-bearing comparison risk.
7. Plain `4.0.0` wording describes the proposal-contract era introduced at 4.0.0; `4.0.1` changes wording/provenance, not the contract shape.
8. CLI stderr assertions and boundary-test import/lint nits are test-maintenance polish, not behavioral gaps.

These can be batched into Phase-5 closure cleanup if desired; none warrants reopening implementation.

## 4. KPI comparability across prompt eras

The scored processing surface is comparable for the Phase-5 cohort:

- `compiler/kpi/processing.py` was not changed by Task #119.
- Scored quarantine/recovery logic still consumes `final_status`, `syntax_repaired`, `slug_coerced`, `boundary_recovered`, attempts, latency, and token totals (`compiler/kpi/processing.py:61-85`).
- A clean 4.0.1 stamping-only record has `final_status="clean"`, `slug_coerced=False`, no recovery flags, and one attempt, exactly like a clean 3.0.0 record. Normalization-decision diagnostics and `summary_identity_derived` are not scored KPI inputs.
- A direct projection comparison of otherwise identical 3.0.0 clean and 4.0.1 stamping-only records produced identical `compute_processing` output.
- `semantic_pass_rate` remains a diagnostic final-acceptance signal, not a scored axis. Its inner validation seam is contract-era-specific, so detailed semantic failure causes should be compared using the era/provenance fields rather than treated as identical mechanisms.

The zero-quarantine Phase-0 baseline is therefore a valid scored comparator. Stamping does not masquerade as repair or retry.

## Verification

- Focused boundary/replay/orchestrator/KPI suite: **468 passed**
- Full deterministic suite, explicitly excluding `live` and `bench`: **1,649 passed, 1 skipped, 2 deselected**
- Default suite in this network-restricted review environment: **1,649 passed, 1 skipped, 1 deselected, 1 failed**; the sole failure was the marked live Pass-1 DeepSeek smoke test attempting an external connection. This is an environment limitation, not a Task #119 regression, and is the evidence the authorized Phase-5 live cohort is intended to supply.
- Kimi's credentialed pre-review run: **1,650 passed, 1 skipped, 1 deselected**
- `git diff --check 4d60e6d..727dd4c -- compiler common tools tests orchestrator kdb_graph`: clean

## Gate recommendation

**GO.** Commit the review/closure documentation, confirm the worktree is clean and the cohort header records prompt `4.0.1`, the golden prompt SHA, and a non-unknown release version, then fire the DeepSeek and GPT Phase-5 live acceptance cohort. No code revision is required before that gate.
