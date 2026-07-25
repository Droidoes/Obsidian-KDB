# Task #119 Execution Review — Codex R2

**Date:** 2026-07-24

**Scope:** R1 fix wave `c1f3f95`; Phase 4 commits `cdbc75f` and `b1a4202`; fresh-eyes pass over `4f356f0..b1a4202`

**Verdict:** **REVISE**

The two R1 Important defects are fixed correctly, all five R1 findings are absorbed, and the Phase 4 replay and measurement implementations follow the ratified plan. One new Important provenance defect prevents overall Phase 2+3 acceptance: the R1 wording correction changed the packaged Pass-2 prompt bytes without changing `PASS2_PROMPT_VERSION`.

## Findings

### 1. Important — two different packaged prompts now identify themselves as version `4.0.0`

**Location:** `compiler/prompt_builder.py:40-46`; `compiler/prompts/KDB-Compiler-System-Prompt.md:18-22,135-142`; `compiler/tests/test_prompt_builder.py:90-95`; `orchestrator/tests/test_kdb_orchestrate.py:1068-1076`

The repository's D-115-13 rule is explicit: any prompt-content change bumps `PASS2_PROMPT_VERSION` in the same commit so content and version never drift. Blueprint v0.4 carries that same-commit discipline forward.

Commit `c1f3f95` correctly changed the prompt terminology from “canonical shape” to “proposal response shape,” but left the version at `4.0.0`. Consequently:

- prompt at `4942913`, version `4.0.0`: SHA-256 `14852d0ba244da24060631f0aa85e9594cc70adb9e8bfc29ac5ea9fc59270a82`
- prompt at `c1f3f95`, version `4.0.0`: SHA-256 `afeff429761a98b71eadccfc3ca5b067d542d7e37764a8b4a90ae2192a8e5e1b`

The run-level SHA and release commit still make individual runs attributable, so this is not silent byte loss. It does, however, break the version identity used to describe contract cohorts and contradicts the exact provenance gate immediately before the Phase 5 live comparison. The current tests do not guard the invariant: they pin `4.0.0` separately and compare the run SHA to whatever prompt happens to be loaded, so both pass after an unversioned content change.

**Concrete fix:**

1. Bump the corrected prompt to `4.0.1` in `PASS2_PROMPT_VERSION` and update the prompt-version assertions and current architecture/runbook references. Replay dispatch already accepts all `4.x` versions.
2. Add one golden version-to-packaged-prompt-SHA assertion so changing prompt bytes without changing the version fails a test. Keep the existing dry-run assertion that the emitted header matches the loaded bytes.
3. If the team instead intends versions to represent schema eras only while the SHA distinguishes wording changes, ratify that different rule explicitly and update the D-115-13 comments/tests before Phase 5; the current code and architecture state the stricter rule.

### 2. Minor — the freeze regression assumes unequal objects must have unequal hashes

**Location:** `compiler/tests/test_proposal_bridge.py:347-350`

`assert hash(_freeze(True)) != hash(_freeze(1))` is not a valid Python hash-table invariant. Unequal values are permitted to have the same hash; dictionaries remain correct by resolving collisions with equality. The production fix is sound because the frozen keys compare unequal, regardless of whether their hashes collide.

**Concrete fix:** Replace the hash-inequality assertion with a dictionary/multiset assertion proving the two frozen values remain two distinct keys with independent counts.

### 3. Minor — fail-closed replay tests do not pin the complete fail-closed result

**Location:** `tools/tests/test_response_replay.py:253-262`

The implementation at `tools/replay.py:101-114` correctly returns all four flags as `False` and forces `matches_expected=False` for 2.x and unknown versions. The tests assert only the error-detail substring, so a future regression could return one of the flags—or `matches_expected`—incorrectly while these tests stay green.

**Concrete fix:** In both tests, assert:

```python
assert (r.extract_ok, r.parse_ok, r.schema_ok, r.semantic_ok) == (
    False, False, False, False
)
assert r.matches_expected is False
```

### 4. Minor — the measurement field comment contradicts its intended compatibility fallback

**Location:** `common/measurement.py:44-49`, `common/measurement.py:187-193`

The implementation correctly follows the plan: when the persisted count is absent, it returns `len(normalization_decisions or [])`, which is `0` when an old record has no decision list. The dataclass comment instead says the value is `None` for pre-#119 records without decision lists.

**Concrete fix:** Update the comment to say Pass-1 projections remain `None`, while Pass-2 records without either field project a compatibility count of `0`.

## Part A — R1 fix verification

### R1 F1 — accepted

The corrected `_freeze` is type-tagged for `ABSENT`, Boolean, object, array, internal tuple, string, null, and number. Boolean is checked before number, avoiding Python's `bool`-is-an-`int` trap. `_json_equal` is used at all four requested locations:

- slug raw-match during apply;
- plan no-op discipline;
- slug diff construction;
- non-noop op filtering.

Adversarial checks passed:

- integer/float JSON-number unification (`1 == 1.0`) and equal hashes;
- Boolean/number separation;
- nested object key-order normalization;
- array/internal-tuple separation;
- `ABSENT`/null separation;
- nested object/array values;
- legitimate object, array, and null summary-stray values still reach `BridgeSuccess` with bounded telemetry.

The end-to-end `True`/`1` fault injection now raises `CanonicalInvariantError` in both application and conservation.

The regressions are non-vacuous. Executing the parent implementation from `c1f3f95^` reproduced both object-vs-array and Boolean-vs-number collisions.

### R1 F2 — accepted

`_validate_plan` now rejects every slug op whose occurrence is not zero. Both slug-operation kinds are covered, including the already-canonical no-op summary resolution with `occurrence=99`.

The regression is non-vacuous: the parent implementation accepted the exact `occurrence=99` no-op plan.

### R1 F3 — accepted

The parity harness now counts occurrences per raw token, matching production. The new `two-malformed-pages-authority-valid` case exercises two distinct mapped targets.

The regression is non-vacuous: applying the old global-enumerate harness to the new case raises `CanonicalInvariantError` because it assigns occurrence `1` to the first `Baz--Qux` token.

### R1 F4/F5 — accepted

The `compile_source` docstring now accurately distinguishes product-state writes from response telemetry, and the packaged prompt consistently calls the model output the proposal response shape. Finding 1 concerns the missing version bump for that correct wording change, not the wording itself.

## Part B — Phase 4 assessment

### Replay dispatch — accepted

- The 3.x implementation is the prior `replay_case` body moved verbatim into `_replay_case_v3`.
- All four existing fixture files are untouched and default to `"3.0.0"`.
- 4.x runs recovery, proposal validation, then the bridge.
- `schema_ok` means proposal-schema success; `semantic_ok` means bridge/canonical success.
- `result.extract_ok` is propagated on every 4.x return path.
- Only `CanonicalInvariantError` and `PathError` are converted to fixture results; programming defects are not hidden by a broad catch.
- 2.x and unknown versions fail closed with all flags false and `matches_expected=False`.

Finding 3 is test hardening only; the runtime dispatch behavior is correct.

### Measurement projection — accepted

- A persisted `normalization_decision_count` wins over sample-list length, including `63` over a capped 50-item list.
- Absent counts fall back to `len(normalization_decisions or [])`.
- `summary_identity_derived` projects as `True`, `False`, or `None`.
- The fields are additive diagnostics on `PassCallMeasurement` and do not enter any scored KPI axis.

Finding 4 is documentation-only; the projection behavior is correct.

## Part C — fresh-eyes seam assessment

Apart from Finding 1, the reviewed seams match blueprint v0.4:

- bridge success and rejection decisions flow through compile telemetry with per-attempt resets and the correct persisted count/digest;
- summary stamping and stray-ignore decisions do not set `slug_coerced` or recovery status;
- `parsed_json` and `ParsedSummary` remain raw-proposal evidence;
- `resp_summary.page_count` counts well-formed page dictionaries, including a compliant slugless summary;
- prompt 4.x tells the model not to emit a summary slug, the exemplar is slugless, and the injected proposal schema requires concept/article slugs while tolerating arbitrary summary strays;
- canonical downstream construction uses `bridge.canonical`.

## Verification

- R1/Phase4/seam-focused suite: **220 passed**
- Full deterministic suite with the live DeepSeek key explicitly empty: **1,648 passed, 2 skipped, 1 deselected**
- Kimi's **1,649 passed, 1 skipped, 1 deselected** total includes the credentialed live Pass-1 smoke that is intentionally skipped in the restricted review environment.
- `git diff --check 4f356f0..b1a4202 -- compiler common tools tests`: clean

## Gate recommendation

Accept the R1 invariant fixes and the Phase 4 implementation. Keep the overall Phase 2+3 acceptance gate open until Finding 1 is resolved and the focused/full suites remain green. Findings 2–4 are non-blocking cleanup, but they are small enough to absorb in the same correction wave before the final whole-branch review.
