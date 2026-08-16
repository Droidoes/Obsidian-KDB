# Task #123 Blueprint v0.7 / Spec v0.9 Confirmation Review — Codex

**Date:** 2026-07-26

**Reviewer:** Codex

**Review basis:** `2026-07-26-task123-blueprint-v0.6-to-v0.7-confirmation.diff`

## Vote

**REVISE — D8 is the right architecture, but approval condition 1 is only
partially closed.**

The compact wire closes the original M1 defect: expression attribution no
longer repeats strings, selector-written free prose is gone, and
schema-maximum tests replace fixture-average tests. The stale-reference sweep
is also complete.

I would not ratify v0.7 yet, however. The documents still do not provide a
numeric contract from which a 4,000-token output limit follows without an
additional tokenizer-density assumption. There is also one direct result-shape
contradiction and two small route/integration contracts that must be made
executable.

No package boundary, orchestration decision, integration phase, or D7 budget
posture needs to be reopened.

## Approval-condition confirmation

| v0.6 approval condition | Result | Assessment |
|---|---|---|
| **1 — numerically bounded schemas and reproducibly derived allowances** | **Partially closed** | The wire is much smaller and its intended semantic values are bounded. But the displayed schemas do not state all numeric maxima, and the 4,000-token derivation assumes 3 UTF-8 bytes/token. The named `tokens_lte_bytes` invariant proves only tokens ≤ bytes, not tokens ≤ bytes/3. |
| **2 — schema-maximum worst-case tests** | **Closed** | Both spec and blueprint require synthetic schema-maximum documents rather than fixture maxima or averages. |
| **3 — stale references and branch table synchronized** | **Closed** | Current normative R4/SD-4 prose uses M=100 and the reduced-M gate; blueprint sizing uses ~257 kB; the branch table names thin-preflight `budget_exceeded` and includes both post-call estimation-miss terminals. Historical decision records correctly retain their old figures. |

The re-typing of `budget_estimation_miss` as
`budget_exceeded`/`detected: post_call`, attempted once and excluded from the
selector-behavior gate, is coherent and improves the contract.

## N1 — Public `Hit` still requires the field D8 removed

Spec §1.1 still declares:

```text
Hit
  ...
  matched_expressions: [str]
  evidence: str                    # bounded, selector-written
```

Spec D8, spec §2.2/§2.3, blueprint §2.3, and the P1 response tests all say that
the fat response has no per-hit `evidence`. The controller therefore has no
defined value with which to construct the declared public `Hit`.

**Required correction:** remove `Hit.evidence` from the public result contract
and from the planned type/tests. Keep `evidence_status` and `body_coverage`;
those describe the fat-stage evidence pool and are unaffected.

## N2 — The 4,000-token allowance is not derived by the stated invariant

D8 estimates:

- thin: roughly 100 × 96-byte slugs, or about 10 kB of JSON;
- fat: roughly 50 × 170-byte selections, or about 8.5 kB before the advisory
  unresolved list; and
- each output allowance: 4,000 tokens, using 3 bytes/token.

Calling 3 bytes/token “pessimistic” does not make it a schema bound. The new
route invariant is `tokens_lte_bytes`; for a 10 kB response it supports an
upper bound near 10k tokens, not 3.3k. A valid schema-maximum response can
therefore still be cut at 4,000 tokens, retried identically, and misreported as
a selector failure.

The conceptual schemas also omit maxima needed by the calculation:

- the generic `GraphSearchRequest.max_results` is not globally capped at 50;
- `matched` has no stated `maxItems`, uniqueness rule, or integer range in the
  schema block;
- `unresolved_expressions` remains an advisory string list without stated
  `maxItems`/item-byte limits, although Python computes the authoritative list;
  and
- the thin `retained` schema does not state its 100-item and per-item byte
  maxima in the schema itself.

Two distinct closures remain available:

1. **Complete the bounded string wire.** State every maximum, globally constrain
   `max_results` to 50, use the existing canonical slug maximum, remove the
   redundant advisory unresolved field (or return expression indices), compute
   the exact maximum compact serialization, and reserve at least that many
   tokens under `tokens_lte_bytes`. A roughly 10–12k allowance would still leave
   the D7 fat request comfortably below 320k and is below every cohort model's
   configured output capacity.
2. **Index identities as well as expressions.** Number the supplied entities;
   return entity indices from thin and fat, return expression indices for
   attribution, and remove the advisory unresolved field. The resulting
   schema can be made smaller than 4,000 bytes, so
   `tokens_lte_bytes` directly proves that a 4,000-token allowance is enough.

The first option retains human-readable provider output and increases the
allowance. The second provides the strongest compactness proof but adds
controller-side identity-index mapping. Both preserve the public result shape
and D8 semantics.

The synthetic tests should assert the exact maximum serialized **bytes** and
then prove the configured token allowance from the chosen route invariant;
dividing by an assumed density merely reproduces the gap.

## N3 — The 96-byte slug ceiling conflicts with the canonical data model

The repository's canonical contract permits ASCII slugs up to 120 characters
(`common.paths.MAX_SLUG_LEN` and the compile-result schemas). D8 introduces a
96-byte search-wire ceiling and says an oversized materialized slug produces a
typed outcome, but:

- entities with 97–120 byte canonical slugs are valid graph entities;
- `GraphSearchResult.status` contains no corresponding outcome;
- the blueprint does not name the exception/result type; and
- the test plan does not cover this branch.

Do not make semantic search unavailable for otherwise valid graph state merely
to preserve the 4,000 estimate. Either derive the string-wire maximum from the
existing 120-byte canonical bound, use identity indices, or explicitly ratify
and migrate a system-wide 96-byte canonical invariant. The last option is
cross-cutting and is not a local D8 amendment.

## N4 — `tokens_lte_bytes` has no declared owner or resolution test

The invariant is now named, which closes the wording problem, but the blueprint
does not say where it lives. Today `ModelSpec` and `common/models.json` have no
such field. Blueprint §2.1, §8/B10, P1, and the route-resolution tests mention
only the `ctx_window` assertion.

Before implementation, specify one source of truth:

- a validated boolean capability in the model registry carried by `ModelSpec`;
  or
- a selector-local supported-route declaration validated when a `ModelSpec` is
  accepted.

In either case, missing/false must raise the named typed configuration error
before rendering or calling, and all three D4 candidates need an explicit
test-covered declaration. Otherwise “asserted at route resolution” is prose,
not an implementation contract.

## What is accepted and should remain closed

- D8's no-free-prose selector wire;
- numbered expressions and controller-side attribution mapping;
- out-of-range attribution salvage;
- M=100 and the D7 static fat-input guarantee;
- honest thin preflight and post-call estimation-miss outcomes;
- synthetic schema-maximum response tests;
- the synchronized reduced-M gate and current sizing references;
- both estimation-miss branch-table rows;
- immutable fixture v1 and its policy-v2 compatibility artifact; and
- original/rendered QueryPayload archival.

## Approval condition

I will vote **APPROVE** when:

1. `Hit.evidence` is removed;
2. the complete thin/fat wire schemas state numeric maxima and the allowances
   follow from those maxima plus the declared route invariant, without the
   unsupported 3-bytes/token step;
3. the wire slug bound is reconciled with the canonical 120-byte data model;
   and
4. ownership and fail-configuration tests for `tokens_lte_bytes` are named.

These are narrow contract-completion changes around D8, not reasons to revisit
the selected architecture.

## Verification

- The supplied artifact is 258 lines and has SHA-256
  `537e60d1f257a2d01a913336e510e0650d69edae28b4acaa71b798b9cf05cec8`.
- It is byte-identical to the two-document diff for
  `743a2b3..49b2bc8`.
- Frozen SearchSnapshot fixture tests: **7 passed**.
- The resulting spec/blueprint, current `ModelSpec`/model registry, and the
  canonical 120-character slug limit were checked directly.
