# Codex Review — Task #119 Normalization-Boundary Implementation Plan

**Reviewed artifact:** `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md`  
**Blueprint:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md` v0.3 (ratified)  
**Review date:** 2026-07-23  
**Verdict:** **REVISE BEFORE EXECUTION**

The architecture remains sound, but the implementation plan has three execution blockers and several verification gaps.

## Findings

### 1. High — Phase 3 breaks the ratified atomic-switch requirement

The plan commits pipeline rewiring in Task 3.1, then changes the prompt/schema/version in a separate Task 3.2 commit (`plan:1220`, `plan:1227`). The blueprint explicitly requires them to land together to prevent a transient proposal-validator/prompt-3.0 mismatch (`blueprint:197`).

**Required:** One atomic Task 3 commit and one verification gate after both rewiring and prompt 4.0.0 are present.

### 2. High — Deleting `repair.py` will break the current test suite

The plan retires `compiler/repair.py` (`plan:1068`) without assigning migration of three existing importers:

- `compiler/tests/test_wikilink_parity.py:18`
- `compiler/tests/test_repair.py:9`
- `compiler/tests/test_coerce_slugs.py:6`

**Required:** Explicitly migrate the authority-valid cases to `proposal_bridge`, remove obsolete body-only coercion expectations, and delete or re-role the old test modules before deleting `repair.py`.

### 3. High — Commit and acceptance sequencing conflicts with project gates

The plan directs commits after individual tasks without an explicit Joseph approval checkpoint. Phase 5 also merges to `main` before the live cohort gate (`plan:1360`). A failed cohort would therefore leave an acceptance-failing implementation on `main`.

**Required:** Keep a clean feature-branch anchor, run the live acceptance cohort there, and request explicit approval before commit and again before merge.

### 4. Medium — The Phase-0 corpus contains a failing fixture and misses a promised negative

The “>120” slug is only 99 characters. Its body token is also `[[alpha--beta]]`, which does not exactly match the raw `Alpha---…---Beta` page slug, so `body_reference_rewrite` cannot fire as expected (`plan:63`).

The plan additionally calls `REWRITE_AMBIGUITY` unreachable (`plan:478`) while claiming ambiguity-negative coverage.

**Required:** Use a genuinely >120-character slug and an exact matching body token. Either expose a testable lower-level ambiguity seam or formally classify `REWRITE_AMBIGUITY` as reserved/unreachable and remove the false coverage claim.

### 5. Medium — Telemetry truth-table coverage is asserted but not implemented

The proposed boundary test checks result and call count, but never captures `RespStatsRecord`; therefore it cannot demonstrate the claimed clean `final_status` (`plan:1111`, `plan:1218`). Tests are also missing for:

- stamping/ignoring not setting `slug_coerced`;
- `CanonicalInvariantError` triggering failed-response capture;
- every retry-classification row;
- raw proposal preservation;
- terminal `BridgeReject.decisions`.

The implementation only copies decisions after `BridgeSuccess`, despite `BridgeReject.decisions` being defined as partial telemetry.

**Required:** Add a response-stats sink and table-driven assertions covering the complete blueprint §3.5 truth table and retry matrix. Persist terminal reject decisions, with per-attempt state reset where required.

### 6. Medium — Alias-ledger provenance is not actually tested

The alias fixture only proves that `[[apple-inc]]` survives the bridge (`plan:73`). It never runs canonicalization with a ledger or checks `canonical_meta.aliases_emitted`, as required by the blueprint.

**Required:** Add a bridge-to-canonicalize integration test with a real alias-ledger mapping and provenance assertions, plus the specified `compile_source`/orchestrator dry-run coverage.

### 7. Medium — Normalization telemetry does not match its declared format or boundedness

`_decision()` emits Python type names such as `"dict"` (`plan:608`); the ratified type uses JSON names such as `"object"` (`blueprint:72`). String raw values are also stored without a limit even though the always-on decision list is described as bounded.

**Required:** Map Python values to JSON type names and use a bounded preview plus stable hash for oversized strings as well as non-strings.

### 8. Medium — Replay migration targets the wrong existing seam

The plan names `tools/tests/test_replay.py` and introduces `run_case()` (`plan:1283`). The repository currently uses `tools/tests/test_response_replay.py`, while both the CLI and tests call `replay_case()`.

**Required:** Modify the existing test file, preserve or deliberately migrate `replay_case`, and explicitly wire the CLI dispatch. Place the defaulted `prompt_version` after all non-default dataclass fields and test 2.x, unknown versions, and an underivable `source_id`.

## Minor correction

The sample constructs `ContextSnapshot(existing=[], recent_runs=[])`, but the real signature is `ContextSnapshot(source_id, pages=[])` (`common/types.py:322`). The plan acknowledges this caveat, but executable examples should already be valid.

## Conclusion

Once these findings are absorbed, I expect the plan to be ready for implementation. No implementation files were changed and no tests were run during this document review.
