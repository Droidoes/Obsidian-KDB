# Task #115 Phase 3 — Gate-3 Code Review, Round 2 (Codex)

**Reviewed:** 2026-07-22  
**Branch/base:** `feat/115-pass2-contract` at `610ef77` plus the amended uncommitted Gate-3 diff  
**Input:** `2026-07-22-task115-phase3-gate3-review-response.md`

## Verdict: GO-WITH-CHANGES

F1, F2, and F4 from round 1 are fully resolved. F3 is substantially resolved—the artifact now covers every schema table—but one nonvolatile relationship property is still omitted. Fix that small residual before the Gate-3 commit.

## (a) Inventory completeness & Claim-tier protection

None.

- Both executable viewer exporters remove `confidence` only from Entity props; static bake-off artifacts remain untouched.
- Direct legacy-value tests cover the official and fallback exporters.
- Verifier confidence-only drift is explicitly ignored and tested.
- MCP adapter and all three Entity-carrying protocol surfaces explicitly assert that `confidence` is absent.
- `kdb_graph/schema.py`, `core/belief_classifier.py`, and the O1 scenario corpus remain byte-identical to Gate 2. Claim snapshot confidence remains intact.

## (b) Gate-3 pre/post comparison soundness

### R2-F1 — `CONTRADICTS.contradiction_kind` is not normalized

**[Severity: Low]** · `kdb_graph/tests/gate3_dump.py:172` · The new Claim-relationship loop declares an `extra` value for `CONTRADICTS`, but never interpolates or consumes it. The query at lines 179-181 returns only endpoints and `run_id`, and the object at line 176 therefore drops the schema's nonvolatile `contradiction_kind` property (`kdb_graph/schema.py:187`). A manual populated-edge probe produced `{'from': 'c1', 'to': 'c2', 'run_id': 'r'}` with no kind. This contradicts the helper's “every property except volatile timestamps” contract. The pinned corpus leaves the Claim tier empty, so the existing Gate-3 equality cannot expose the mapper defect. **Suggested change:** project and serialize `r.contradiction_kind` for `CONTRADICTS` while leaving the other two Claim relationships unchanged; add a focused `dump_normalized` test with two Claims and a populated `CONTRADICTS {contradiction_kind: ...}` edge. Because the Gate-2 artifact correctly records `contradicts: []`, this mapper correction does not require changing its expected content.

All other F3 requirements are now met: `_SchemaMeta`, Claim, EVIDENCES, ABOUT, SUPERSEDES, CONTRADICTS, and QUALIFIES sections are present; Claim computed confidence is included rather than excluded; the Gate-2 artifact retains the varied legacy Entity values and schema version 2.4; and the pre/post test strips only Entity confidence.

## (c) Snapshot v7 & dead-column safety

None.

The snapshot test now seeds non-null legacy values directly, verifies the Kuzu precondition, and proves that v7 omits the key. The production writer and version/history contract remain correct.

## (d) Read-compat & scope

None.

The mixed legacy/new rebuild proof remains green. No Phase-4, #116, physical-column-removal, or compiler scope leakage was introduced by the remediation.

## Verification performed

- Focused Gate-3/snapshot/verifier/MCP/viewer/boundary bundle: **75 passed**.
- Gate-3 artifact tests alone: **2 passed**.
- Deterministic suite (`-m 'not bench and not live'`): **1384 passed, 1 environment-gated skip, 2 deselected**, exit 0.
- Claim-protection diff check: clean against Gate 2.
- `git diff --check HEAD`: clean.
- Manual populated-`CONTRADICTS` probe reproduced R2-F1.

## Bottom line

The production confidence deprecation and snapshot v7 implementation are now sound, and three of four round-1 findings are completely closed. Gate 3 needs one final, localized correction: retain `CONTRADICTS.contradiction_kind` in the full-graph normalizer and pin it with a populated-edge test. After that focused test and the deterministic suite pass, this phase is safe to commit.
