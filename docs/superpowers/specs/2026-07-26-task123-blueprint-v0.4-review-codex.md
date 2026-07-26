# Task #123 Blueprint v0.4 / Spec v0.6 Confirmation Review — Codex

**Date:** 2026-07-26  
**Reviewer:** Codex  
**Review basis:** commit `960c8e0` and
`2026-07-26-task123-blueprint-v0.3-to-v0.4-confirmation.diff`

## Vote

**REVISE — one load-bearing context-safety correction plus targeted
documentation fixes.**

Blueprint v0.4 closes the calibration-policy, phase-ordering, provenance-boundary,
measurement-population, and sibling-artifact findings. It does not require an
architectural reset. The remaining blocker is narrower: the projector now
enforces a byte ceiling, but the documents treat `bytes / 4` as a guaranteed
token ceiling. Model context windows are measured in tokens, so that conclusion
does not follow.

## Prior approval-condition check

| v0.3 approval condition | Result | Assessment |
|---|---|---|
| **1 — reconcile D1, calibration, and phase order** | **Closed** | D5 is an explicit, narrow D1 amendment: one fixed, non-comparative call per candidate; hard three-call ceiling; Joseph fires at end of P2. P1 tests are structural-only and measurement assertions move to the calibration gate. |
| **2 — fold amendments through the normative spec** | **Partial** | The enum, branch call contract, test plan, gating paragraph, and resolved open items are synchronized. The R3 decision row still retains the pre-D1 “no implementation crosses D7” rule. |
| **3 — make the fat-stage maximum enforceable** | **Partial / blocking** | The 2,500-byte per-entry ceiling is enforceable. The derived `≈94k tokens < 102.4k` claim is not an enforceable bound and excludes the rest of the request. |
| **4 — separate calibration from the frozen fixture** | **Closed** | Calibration is a sibling artifact and the checksummed fixture manifest is not mutated. |

## K1 — the byte ceiling does not prove token fit

This is the sole load-bearing implementation blocker.

The new policy proves:

```text
fat evidence bytes <= 150 × 2,500 = 375,000 bytes
```

It does **not** prove:

```text
fat request tokens <= 375,000 / 4 = 93,750 tokens
```

`bytes / 4` is a planning estimate, not a tokenizer-independent upper bound.
Token density varies by model and content; code, unusual Unicode, short symbol
runs, and adversarial text can exceed the calibrated fixture's density. One
provider-reported measurement over the ordinary thin fixture cannot establish a
worst-case ratio for arbitrary future fat evidence.

The comparison is also incomplete. The 102.4k budget must cover the **entire**
request: system prompt, task template, query, evidence, delimiters, and reserved
output. At the asserted 93.75k evidence estimate, only 8.65k tokens remain, but
the documents define neither a complete static bound for those fields nor a fat
output allowance.

This same distinction affects R2: spec v0.6 calls the estimator
“conservative,” while blueprint v0.4 correctly says the “never underestimates”
claim is withdrawn. Both statements cannot be normative simultaneously.

### Resolution options

Two distinct contracts are viable:

1. **Authoritative token preflight.** Keep the 2,500-byte projection cap, but
   count the fully rendered thin and fat requests with the selected model's
   authoritative tokenizer. Include reserved output and apply the 80% headroom
   before every call. A selector route without an authoritative counter fails
   configuration rather than using a heuristic safety gate.
2. **Separate planning from a conservative hard guard.** Retain calibrated
   `bytes / 4` for cost and capacity estimates, but use a proved
   model-specific tokens-per-byte upper bound—or a deliberately conservative
   byte-fallback bound—for admission. Include templates, query, and output in
   the hard guard. If the project keeps a static fat guarantee instead, the
   byte ceiling or minimum supported context window must be derived from that
   conservative bound, not from an observed average.

The first optimizes usable context at the cost of tokenizer dependencies. The
second is simpler operationally but may reject requests that would actually
fit. Either closes the contract; the current heuristic labelled “by
construction” does not.

Required tests:

- a high-token-density request that defeats `bytes / 4`;
- full-request accounting, including fixed fields and output allowance;
- zero invocation on a thin or fat budget failure;
- candidate-specific counting/guard behavior;
- a clear typed outcome for a fat-stage budget rejection.

## K2 — normative-body synchronization has one stale ruling

Spec v0.6's R3 decision row still says:

> no implementation/tuning/vault ingestion crosses D7

D1 and the updated §8.1 instead authorize canned/mocked P1–P4 implementation at
blueprint ratification, with D5 as the only pre-D7 live-call exception. Update
the R3 row to carry that amended contract. Until then, the changelog's claim
that D1 is folded through the normative body is slightly overstated.

The SD-4 and R4 decision rows should also name the actual gate as **stage-1
recall at the predeclared reduced-M points**, while preserving M=150 as the
production constant. Calling it a “recall@150 gate” is misleading because the
spec itself explains that recall@150 is non-binding on this fixture.

## K3 — fixture v1 and excerpt policy v2 need an explicit relationship

The frozen fixture manifest still records:

```json
"excerpt_policy_version": "1"
```

Spec v0.6 and blueprint v0.4 require artifacts to record
`excerpt_policy_version: "2"`. The projected bytes happen to be unchanged
because the 2,500-byte ceiling binds on no fixture entity, but byte equality
does not update the fixture's policy identity.

Two clean choices are available:

1. create `task123_search_snapshot_v2` with policy-v2 metadata and fresh
   checksums, reusing identical excerpt blobs where their hashes are unchanged;
2. keep fixture v1 immutable and add a checked compatibility artifact proving
   every v1 excerpt renders identically under policy v2, with the harness
   explicitly recording effective policy v2.

Do not mutate fixture v1 in place. Labels have not yet been ratified, so either
choice is inexpensive now.

## Minor contract edits

- State explicitly that the policy-v2 byte ceiling takes precedence over the
  no-mid-sentence-cut rule; byte truncation can otherwise contradict that rule.
- Relabel the `~160M input tokens` re-ingest figure as an expected-case planning
  estimate. The stated policy maximum is approximately
  `160k × 1,706 = 273M` input tokens before accounting for output; 160M is not
  the policy upper bound.
- Qualify `len(search envelopes) == searches_attempted` as the successful-write
  completeness condition. Envelope persistence is warn-only, so a write
  failure must produce an incomplete measurement state or a separate
  `search_artifact_write_failures` count rather than violate an unconditional
  invariant.

## What is closed and should stay closed

- D5's explicit calibration authorization and three-call ceiling;
- calibration timing and P1/P2 test ownership;
- sibling calibration artifact and frozen-manifest protection;
- `fat_after_thin_failure` in both closed enum sites;
- branch-specific logical-call accounting;
- hit-level provenance and adapter-side batched read;
- pass-1.5 exclusion from scored and legacy diagnostic populations;
- independent envelope-count completeness evidence;
- restored V2 kept fields, #119 byte-pinning clause, resolver non-surfacing
  enumeration, SD-5 trend series, fail-hard posture, and T3 seed contract.

## Approval condition

I will vote **APPROVE** after:

1. the documents distinguish the byte projection cap from a safe,
   full-request token-admission guard;
2. the stale R3 decision row is synchronized with D1/D5; and
3. the fixture-v1/policy-v2 relationship is versioned or pinned explicitly.

The remaining minor edits can land in the same targeted revision. No selected
architecture needs to be reopened.

## Verification

- The supplied 313-line diff is byte-identical to the two-file diff from
  `51a16f2` to `960c8e0` (matching SHA-256:
  `1eab6662b46178a8490010d80357c5e5bfac3f6a1de2032d1715e038545f9b32`).
- Frozen-fixture smoke tests: **7 passed**.
- Confirmed directly that fixture v1 still records excerpt policy version `1`.

