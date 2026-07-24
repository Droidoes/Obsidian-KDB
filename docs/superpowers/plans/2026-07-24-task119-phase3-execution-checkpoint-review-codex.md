# Task #119 Phase 3 Execution Checkpoint — Codex Review

**Date:** 2026-07-24

**Scope:** commits `408dc42` and `4942913`, with lower-priority inspection of `c1e6766`, `7978e06`, and `40a2326`

**Verdict:** **REVISE**

The assembled proposal-to-canonical switch is structurally faithful to blueprint v0.4 in its retry routing, §3.5 telemetry truth table, decision capping, raw-proposal preservation, and downstream use of the bridge's canonical result. However, the plan verifier is not yet the exact, type-faithful bijection promised by the ratified architecture. Two Important findings must be corrected before Phase 2+3 acceptance.

## Findings

### 1. Important — `_freeze` is neither injective over JSON types nor sufficient to preserve the bijection

**Location:** `compiler/proposal_bridge.py:349`, `compiler/proposal_bridge.py:462-464`, `compiler/proposal_bridge.py:474-490`, `compiler/proposal_bridge.py:512-525`

**Contract:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:101-124`

The unhashable-value crash is fixed, and ordinary arbitrary-JSON values now traverse the intended summary-stray path. The encoding is nevertheless not injective up to JSON equality:

- `_freeze({"a": 1}) == _freeze([["a", 1]])`
- `_freeze(True) == _freeze(1)`
- `_freeze([1]) == _freeze((1,))`

The last collision is between a JSON array and the bridge's internal tuple representation; the first two are collisions between distinct JSON types.

This is not merely theoretical. Python's loose `True == 1` equality at the raw-match check combines with `_freeze(True) == _freeze(1)` to let an incorrectly constructed plan pass both application and conservation. For a raw summary slug of `true`, a fault-injected summary-resolution op carrying `raw=1` and `canonical="summary-x"` is accepted: line 349 accepts the wrong raw value, and lines 523-525 consider the independently observed diff and the incorrect op identical. The checker therefore cannot reliably detect the Python planner bugs it was introduced to catch.

**Concrete fix:**

1. Make the frozen representation type-tagged. Distinguish at least the internal tuple, JSON object, JSON array, string, boolean, number, null, and `ABSENT`; recursively sort JSON-object string keys inside the tagged object payload.
2. Use one type-faithful JSON-value comparison helper for the raw-match check, no-op discipline, slug diffing, and non-noop-op filtering. It may be built on the corrected frozen representation.
3. Add regressions for object-vs-array, boolean-vs-number, list-vs-internal-tuple, and the end-to-end fault-injected `true`/`1` raw mismatch. The final test must assert `CanonicalInvariantError`, not merely test `_freeze` directly.

### 2. Important — `_validate_plan` does not enforce the pinned slug-operation occurrence

**Location:** `compiler/proposal_bridge.py:445-471`

**Contract:** `docs/superpowers/specs/2026-07-23-task119-normalization-boundary-blueprint.md:111-124`

Blueprint v0.4 pins `occurrence == 0` for both slug-operation kinds and says `_validate_plan` validates occurrence. The implementation only rejects negative occurrences for body operations at lines 460-461. Both slug kinds therefore accept any occurrence value.

This can pass the complete verifier, not just the isolated validator. An already-canonical summary slug with a no-op `SUMMARY_IDENTITY_RESOLUTION` carrying `occurrence=99` passes `_validate_plan`, is applied because slug application ignores occurrence, and disappears from the conservation comparison because no-op ops are intentionally omitted.

**Concrete fix:**

1. Reject every slug op whose occurrence is not exactly zero.
2. Retain the existing non-negative body-occurrence check.
3. Add negative tests for nonzero occurrences on both `SLUG_FORM_COERCION` and `SUMMARY_IDENTITY_RESOLUTION`, including an already-canonical no-op summary resolution.

### 3. Minor — the migrated wikilink parity test computes occurrence differently from production

**Location:** `compiler/tests/test_wikilink_parity.py:46-72`

**Production behavior:** `compiler/proposal_bridge.py:299-316`, `compiler/proposal_bridge.py:367-392`

The migrated bridge projection assigns `occurrence` using one global `enumerate(...)`. Production assigns occurrence per `(page_index, raw_token)`, and `_apply_body_ops` interprets it that way. The current authority-valid parity cases each contain only one distinct mapped raw token, so this mismatch remains invisible. A body containing the first occurrence of two distinct renamed targets would assign occurrence `1` to the second target in the test harness even though production correctly assigns `0`.

This does not identify a production defect—the public `normalize_proposal` path handles the two-target case correctly—but it weakens the fidelity of the migrated coverage.

**Concrete fix:**

1. Prefer driving the parity assertion through public `normalize_proposal`; alternatively, build per-token occurrence counters identical to production.
2. Add one authority-valid case whose body references two distinct malformed response-page slugs.

### 4. Minor — `compile_source` still claims that it writes nothing

**Location:** `compiler/compiler.py:647-653`

The docstring says `Writes NOTHING`, but `compile_source` now persists response telemetry in its `finally` path. Blueprint v0.4 deliberately narrowed the claim to no product-state writes while allowing telemetry. The implementation and tests follow that architecture; the docstring does not.

**Concrete fix:** Change the statement to say that the function writes no product state and may persist per-source response telemetry.

### 5. Minor — prompt 4.0.0 still calls the proposal envelope “canonical”

**Location:** `compiler/prompts/KDB-Compiler-System-Prompt.md:18-22`, `compiler/prompts/KDB-Compiler-System-Prompt.md:135-142`

The example is correctly slugless for the summary and the schema routing is correct, but the prose calls it “the canonical shape.” Under Task #119 this is the model's proposal shape; Python owns the canonical projection. Retaining the old term blurs the boundary the versioned prompt is meant to establish.

**Concrete fix:** Replace both references with “proposal response shape” (or equivalent proposal terminology).

## Answers to the checkpoint questions

### Q1 — Is `_freeze` sound?

No. It is symmetric across `diffs` and `op_keys` and it prevents the original unhashable-container crash, but it is not injective across JSON types. In combination with Python's type-loose scalar equality, it can allow a malformed op to satisfy application and conservation. Finding 1 gives the required repair and regression shape.

### Q2 — Can arbitrary-JSON stray raw values reach another unhashable or ordering-sensitive context?

I found no second unhashable-key or mixed-type ordering site on proposal-schema-valid input:

- collision registries, rename maps, body-op maps, and token counters are keyed only by schema-enforced strings or integers;
- `_decision` uses `json.dumps(..., sort_keys=True)`, and parsed JSON object keys are strings, so nested arbitrary JSON remains deterministically serializable;
- set/frozenset membership is limited to enums, not stray raw values.

The additional risk is instead the type-loose raw-value comparisons at lines 349, 463, 513, and 524. Those comparisons should share the corrected type-faithful equality semantics with `_freeze`, as described in Finding 1.

## Architecture and migration assessment

Apart from the findings above, the Phase 2+3 implementation matches the ratified behavior I checked:

- proposal-schema failures and `BridgeReject`s retry once; `CanonicalInvariantError` is terminal;
- per-attempt bridge telemetry is reset before each attempt;
- `schema_ok`, `semantic_ok`, `slug_coerced`, `summary_identity_derived`, and `final_status` follow the §3.5 truth table;
- decision persistence is bounded to 50 samples with pre-truncation count and overflow-tail digest;
- canonical downstream construction uses only `bridge.canonical`;
- the raw proposal remains available for response telemetry;
- body rewrites remain response-local and code-aware.

The 17 rung-era test migrations are largely coverage-neutral or stronger: the old coercion expectations were re-expressed through proposal/bridge behavior rather than silently removed, and the known trap cases remain in the shared corpus. Finding 3 is the one migration-fidelity gap I found during the spot-check.

## Verification performed

- Focused bridge/schema/boundary/telemetry suites: **219 passed**
- Compiler and orchestrator integration suites: **131 passed**
- Full deterministic suite with the live DeepSeek key explicitly disabled: **1,625 passed, 2 skipped, 1 deselected**
- With the repository's configured DeepSeek key present, the only failure was the unrelated live Pass-1 smoke test attempting outbound access in the restricted review environment: **1 failed, 1,625 passed, 1 skipped, 1 deselected**
- Adversarial probes covered null, booleans, numbers, strings, arrays, objects, and nested JSON summary-stray values, plus fault-injected plan/op mismatches.

## Gate recommendation

Do not accept Phase 2+3 or close the next integration gate until Findings 1 and 2 are fixed and their regressions pass. Phase 4 replay/measurement work may continue in parallel because these repairs should not change the public bridge result or telemetry schema, but Phase 4 should not be declared complete against the current verifier.
