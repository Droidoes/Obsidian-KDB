# Codex R2 Review — Task #119 Normalization-Boundary Implementation Plan

**Reviewed artifact:** `docs/superpowers/plans/2026-07-23-task119-normalization-boundary.md`  
**Blueprint:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md` v0.3 (ratified)  
**Review date:** 2026-07-23  
**Verdict:** **REVISE BEFORE EXECUTION**

Kimi correctly absorbed the prior eight findings in intent. However, the revised executable details introduce two new blockers and several test gaps.

## Findings

### 1. High — Bounded telemetry breaks the conservation checker

The new fixture correctly uses a 129-character raw slug (`plan:63`). `_decision()` replaces strings over 120 characters with preview/hash and sets `raw_value=None` (`plan:613`).

But `_check_conservation()` attempts to reconstruct slug and body changes from `raw_value` (`plan:999`, `plan:1003`). The long slug therefore becomes `None`, causing both the slug comparison and body reconstruction to fail with `CanonicalInvariantError`.

**Required:** Separate the lossless internal transformation plan from bounded persisted telemetry. Conservation should consume full internal rename/rewrite operations; `NormalizationDecision` can remain bounded.

### 2. High — The new Phase-3 tests are not executable against current APIs

- `_ctx()` constructs `RunContext` with only two arguments (`plan:1117`), but the current dataclass requires `compiler_version`, `schema_version`, `dry_run`, `vault_root`, and `kdb_root` too (`common/run_context.py:62`). Use `RunContext.new(...)`.
- The alias test calls undefined `_make_ledger`, contains a dead `AliasLedger.load(...)` expression, and references nonexistent `compiler/tests/test_canonicalize.py` (`plan:1305`). The real helper pattern is in `compiler/tests/test_canonicalize_algorithm.py:41`.

**Required:** Provide complete runnable test code using `AliasEntry` plus `AliasLedger`, with `cr["canonical_meta"]` asserted directly.

### 3. Medium — Required conservation-negative tests remain absent

Task 2.5 only verifies successful preservation (`plan:936`). The blueprint explicitly requires simulated page deletion, notes loss, and unrelated prose mutation to raise `CanonicalInvariantError` (`blueprint:194`).

**Required:** Add negative fault-injection tests for page count/order, notes, title/page type, and non-token body edits.

### 4. Medium — Telemetry and retry tests still do not prove their claims

- `rec.parsed_json` is asserted without enabling `KDB_RESP_STATS_CAPTURE_FULL=1` (`plan:1157`); it is `None` by default (`common/llm_telemetry.py:196`).
- Zero summaries is a `ProposalReject:no_summary`, not `StructuralInsufficiency`.
- Its decision list is empty, so the test does not prove terminal partial-decision persistence.
- No `compile_one` boundary test exercises collision or uncoercible retry behavior.
- The invariant test does not assert that failed-response raw capture occurred.

**Required:** Make the retry table genuinely table-driven, use a reject occurring after a normalization decision, enable capture-full where raw proposal is asserted, and verify `raw_response_text` on invariant failure.

### 5. Medium — Replay still contains nonexistent helpers and changes recovery semantics

The revised tests call `_write_case`, but the existing helper is `_synth` (`tools/tests/test_response_replay.py:121`). `_flag_result` is also described but not implemented.

More importantly, the 4.x path hardcodes `extract_ok=True` after recovery (`plan:1410`). Boundary-recovered responses may legitimately have `extract_ok=False`; replay must preserve `result.extract_ok`. The broad `except Exception` would also hide programming defects as fixture failures.

**Required:** Provide the helpers, propagate `result.extract_ok`, catch `PathError` explicitly, and emit semantic detail for `BridgeReject`.

### 6. Medium — The Phase-3 blueprint gate remains incomplete

The blueprint requires version/SHA stamps verified in a dry run. The revised plan mentions a `compile_source` smoke only in prose and does not verify the orchestrator measurement header or prompt SHA. Its Phase-3 command also runs only compiler/common tests rather than the globally promised full suite.

**Required:** Add an explicit orchestrator dry-run/header test and run the full suite before the Phase-3 commit gate.

### 7. Low — `--source-id` can silently do nothing

In proposal mode, `--source-id` is accepted but ignored (`plan:402`). That can falsely imply semantic validation occurred.

**Required:** Reject `--source-id` unless `--canonical` is also present, and add a CLI test.

## Conclusion

The prior atomic-switch, repair migration, commit gating, branch-based acceptance, raw-length fixture, JSON type mapping, and replay-file targeting findings are otherwise correctly absorbed.

No implementation files were changed and no tests were run during this document review.
