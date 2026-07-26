# Task #123 Blueprint v0.6 / Spec v0.8 Confirmation Review — Codex

**Date:** 2026-07-26  
**Reviewer:** Codex  
**Review basis:** working-tree revision represented by
`2026-07-26-task123-blueprint-v0.5-to-v0.6-confirmation.diff`

## Vote

**REVISE — L1–L3 are closed; one newly exposed output-contract blocker remains.**

The v0.6 revision closes all three approval conditions from my v0.5 review. I
also accept the evidence-based change from uniform 2,000-token output allowances
to THIN 3,000 / FAT 4,000; my earlier “2,000 remains closed” statement is
superseded.

The remaining blocker is not K1/L1 again. It is a separate consequence of
claiming the new allowances are “sized from response schemas”: the fat response
schema does not currently have enough numeric bounds to derive a 4,000-token
maximum.

## L1–L3 confirmation

| v0.5 approval condition | Result | Assessment |
|---|---|---|
| **L1 — coherent budget posture** | **Closed** | With M=100, the capped fat request is ≤~257 kB content bytes plus 4k output, below the configured pool's smallest 320k admission budget under the stated one-content-token-per-UTF-8-byte ceiling. Thin explicitly adopts the honest best-effort posture: a provider context rejection becomes `budget_estimation_miss`, attempted once, spend possible, never retried, and watched per model. |
| **L2 — unconditional query cap** | **Closed** | Every schema-unbounded SD-1 input now has a deterministic byte allocation; oversized author/themes/keys tests are named; original and rendered forms are archived; accounting uses what the selector saw. |
| **L3 — complete fat-budget terminal** | **Closed** | The result contract pins hits `[]`, all expressions unresolved, concordance null, `not_applicable`/None, no fat StageRecord, the two `budget_exceeded` execution rows, and the F1 interaction. |

### L1 settlement detail

D7 resolves the fat and thin cases differently but coherently:

- **Fat:** safety is established by bounded size for the configured model pool,
  not by trusting `bytes / 4`. Reducing M from 150 to 100 changes the static
  worst case from ~381 kB to ~257 kB while leaving the current largest domain
  (51) on retain-all behavior.
- **Thin:** N remains unbounded because the complete eligible space is searched.
  The calibrated estimate is explicitly best-effort. An estimation miss is no
  longer misrepresented as a zero-spend preflight result.

That is the honest-best-effort option requested in L1, with an additional static
fat guarantee for the current pool.

The static fat guarantee depends on the stated tokenizer premise that content
token count does not exceed UTF-8 byte count, plus the ample gap from ~261k to
the 320k budget for protocol framing. Capture that premise as a named supported
model-route invariant rather than an unqualified tokenizer-independent law.

## M1 — FAT 4,000 is not yet derivable from the output contract

This is a load-bearing P2 issue because `ModelRequest.max_tokens` is a hard
provider truncation limit. If the limit cuts a valid response mid-JSON, the
controller sees `unparseable_response`, retries the same capped request, and can
misreport a deterministic cap defect as hard-gate `selector_failure`.

The current fat output contract permits up to 50 selections:

```json
{
  "slug": "...",
  "matched_expressions": ["..."],
  "evidence": "..."
}
```

But:

- `evidence` is called “bounded” without a numeric byte/character maximum;
- each hit may carry multiple matched expressions;
- up to ten rendered expressions may exist, each as large as 128 bytes; and
- the expression strings may be repeated across 50 hits.

The truncation analysis in the diff establishes that 2,000 tokens is too close
to a typical 50-entry response. It does not establish that 4,000 tokens covers
the valid worst case above. The cited ~1,903-token rendering models one
expression per entry and does not include a numerically bounded evidence field.

### Resolution options

Two distinct wire contracts can close this:

1. **Bound the existing string schema.** Specify maxima for evidence bytes,
   matched-expression count per hit, and total response bytes. Derive
   `OUTPUT_ALLOWANCE_FAT` from the complete maximum with margin, then test the
   actual worst-case JSON document—not fixture-average entries.
2. **Use compact attribution on the wire.** Give each rendered expression a
   stable small index and have the selector return expression indices rather
   than repeating strings. Python maps indices back to the archived rendered
   expressions. Numerically bound evidence and derive the allowance from that
   compact schema.

Option 1 preserves the current public shape but may require a larger allowance.
Option 2 makes the provider response substantially smaller and more predictable
at the cost of a local prompt/wire-schema amendment. Neither changes graph
search semantics.

Do the same derivation for THIN 3,000 using 100 **schema-maximum** canonical
slugs, not merely the 100 longest fixture slugs. The fixture's measured
distribution is useful expected-case evidence; it is not the valid-response
maximum at vault scale.

## Consistency sweep

The v0.6 changes leave three inexpensive normative cleanups:

- spec §7.2 R4 still says “M=150 stays the production constant”; change it to
  M=100;
- blueprint §7's “Both stages guarded” bullet still cites the superseded
  ≤~381 kB fat request; change it to ≤~257 kB;
- blueprint §8's first call-count row should say **thin-preflight
  `budget_exceeded`** rather than the ambiguous “budget_exceeded,” and add the
  attempted-once thin `budget_estimation_miss` terminal.

Historical changelog and prior-concurrence descriptions may retain M=150 when
clearly describing the earlier decision. Current normative prose should not.

## What should remain closed

- D7's M=100 production cap and current-scale retain-all equivalence;
- static fat fit for the configured pool, subject to its named tokenizer-route
  premise;
- honest thin `budget_estimation_miss` semantics;
- per-field query allocation and original/rendered archival;
- complete fat-preflight terminal matrix and F1 interaction;
- immutable fixture v1 plus policy-v2 compatibility artifact;
- reduced-M gate protocol, with M=100 as the production constant;
- THIN/FAT having independently derived output allowances rather than sharing
  2,000.

## Approval condition

I will vote **APPROVE** once:

1. the thin and fat output schemas have numeric maxima from which their
   allowances are reproducibly derived;
2. worst-case response tests use those schema maxima; and
3. the three stale/ambiguous normative references above are synchronized.

No architecture, integration boundary, or phase ordering needs to be reopened.

## Verification

- The supplied 261-line file is byte-identical to the working-tree diff from
  `ff8ac7f` for the spec and blueprint (matching SHA-256:
  `d6e1f6a83c6906b48a42dce5c0e22b4381a772094aa69de4c59f5f511077256e`).
- Frozen-fixture smoke tests: **7 passed**.
- Query-field constraints and the fat output shape were checked directly
  against the repository and current spec.

