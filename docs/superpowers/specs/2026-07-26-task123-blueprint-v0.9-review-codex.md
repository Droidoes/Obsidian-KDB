# Task #123 Blueprint v0.9 / Spec v0.11 Confirmation Review — Codex

**Date:** 2026-07-26

**Reviewer:** Codex

**Review basis:** `2026-07-26-task123-blueprint-v0.8-to-v0.9-confirmation.diff`

## Vote

**REVISE — O1–O3 are architecturally closed, and I support both pending D9
owner decisions; the post-call output-budget path and request-bound violation
still need complete executable contracts before ratification.**

v0.9 adopts the right design:

- visible JSON allowance is separated from hidden provider output;
- the provider cap and pre-flight reservation use the total envelope;
- output-side exhaustion is no longer graded as selector behavior;
- `MAX_EXPRESSIONS = 10` is a consumer-neutral core bound;
- exact compact-JSON maxima and their executable test authority are recorded;
  and
- §8.6 and its false thinking-disabled premise are removed.

This closes the substance of all conditions from my v0.8 review. The remaining
issues are translation gaps between the new D9 contract and the orchestration,
result, retry, and provider-stop-reason contracts. No package boundary,
two-stage architecture, M=100 decision, fixture contract, or integration
sequence needs to be reopened.

## D9 owner decisions

| Pending decision | Codex vote | Assessment |
|---|---|---|
| **Visible 13,000/10,000 + hidden reserve 16,000; provider caps 29,000/26,000** | **APPROVE** | This is an honest operational envelope, preserves the D4 cohort, fits the static fat budget, and types the residual instead of presenting the reserve as proof. Remove the unsupported “orders of magnitude” prediction; 16,000 is an owner-selected policy reserve, not a measured hidden-token bound. |
| **Remove §8.6** | **APPROVE** | Its premise was false and the axis was not free. D8's minimal production wire stands independently. |

I also **approve `MAX_EXPRESSIONS = 10`** as the core v1 bound.

Joseph still needs to confirm the two owner decisions explicitly to convert D9
from drafted to binding.

## O1–O3 confirmation

| v0.8 condition | Result | Assessment |
|---|---|---|
| **O1 — separate provider-total output from visible JSON** | **Closed in architecture; execution contract incomplete** | The four quantities are separated and the static fit is recomputed at 283k. P1 and P2 below complete the terminal mechanics. |
| **O2 — remove or fully specify §8.6** | **Closed** | §8.6 is removed and the incorrect rationale is retracted. |
| **O3 — final sweep, global expression bound, exact serializer authority** | **Mostly closed** | The global bound and exact authority are present. Its violation outcome is unnamed, and several current prose values remain stale or contradictory. |

## P1 — Add output-budget branches to the orchestration and result matrix

D9 defines output exhaustion as:

```text
status: budget_exceeded
detected: post_call
budget_side: output
attempted once
never retried
```

The blueprint's orchestration does not execute that contract. Both current
stage-failure branches still route an exhausted `stage_call` to
`selector_failure`, and the pseudocode contains no post-call
`budget_exceeded` branch. The branch-count table says only “1 attempted at the
truncated stage,” without defining what happens before or after that stage.

Add classification before the ordinary unparseable/retry path and pin these
complete outcomes:

| Output-budget stage | Required result and audit contract |
|---|---|
| **Thin** | `budget_exceeded`; `thin_attempted`; hits `[]`; every request expression unresolved; concordance null; `not_applicable`/`None`; exactly one thin `StageRecord`, carrying the raw and normalized stop reason and spend. |
| **Fat after successful thin** | `budget_exceeded`; `two_stage_attempted`; hits `[]`; every expression unresolved; concordance null; `evidence_status: complete|partial` and the measured `body_coverage` because the fat evidence pool was built and presented; exactly one fat `StageRecord` for the truncated attempt. |
| **Fat after the F1 path** | Same fat contract, with `execution: fat_after_thin_failure` and `thin_failed_nonbinding` preserved. |

This differs deliberately from **fat pre-flight** `budget_exceeded`, where no
fat call ran, no fat `StageRecord` exists, and evidence is
`not_applicable`/`None`.

The thin-output/N≤M interaction also needs one explicit rule. I recommend that
the D9 terminal remain terminal and that F1 apply only to retry-exhausted
selector failures, not to either budget side. If the owner instead wants to
proceed to fat because thin is non-binding, then a successful final result
cannot itself have terminal `status: budget_exceeded`; the stage event,
execution value, and call-count row must be defined accordingly.

Update §2.2 pseudocode, §8's call-count table, the status × execution ×
evidence matrix, and the P1 tests together.

## P2 — Normalize provider stop reasons and distinguish truncation from success

`common.call_model` currently returns provider-native values:

- OpenAI-compatible responses use `finish_reason` such as `length`;
- Gemini returns the enum value, such as `MAX_TOKENS`; and
- Anthropic uses values such as `max_tokens`.

The new documents refer only to a generic “length finish reason.” A literal
test for `length` would miss Gemini, including the interim default. The
existing common telemetry likewise recognizes lowercase `max_tokens` and
`length`, not Gemini's uppercase value.

Define one closed, API-call-type-aware normalization, archive both raw and
normalized values, and test every D4 route. Unknown stop reasons must not be
guessed into the budget class.

A cap stop reason is also carrier metadata, not by itself proof that usable
output is absent. The repository's compiler tests already pin that distinction:
a complete valid JSON document can coincide with a length stop. To preserve
the spec's governing salvage rule, the recommended predicate is:

```text
normalized output-cap stop
AND no complete, structurally usable JSON document
→ post-call output budget_exceeded
```

That classification must run before generic `unparseable_response` retry.
Complete usable output should be validated normally while recording the cap
stop in telemetry. If Joseph wants the stricter policy—discard even a complete
usable response whenever the cap stop is present—that is a new explicit
exception to “a parseable response is never discarded” and must be stated and
tested.

## P3 — Name the `MAX_EXPRESSIONS` violation outcome

D9 says a caller exceeding ten expressions gets a “typed outcome with
telemetry,” and the test plan says this happens before rendering. No such
outcome exists in the declared result-status enum, and no typed exception is
named.

Two coherent contracts are available:

1. add `invalid_request` to `GraphSearchResult.status`, preserving the normal
   audit/telemetry path; or
2. raise a named request-validation exception such as
   `InvalidGraphSearchRequest(code="max_expressions_exceeded")`, and define
   where its counter is recorded.

Select and document one. Pin zero rendering, zero body reads, zero model calls,
and zero `StageRecord`s. Do not leave implementation to infer a fifth status or
an assertion from the phrase “typed outcome.”

## P4 — Complete the consistency sweep

The following current, non-changelog passages need correction:

- spec header: title says v0.11 while `Status` still says v0.10;
- spec D8's appended mechanics call FAT's exact maximum **9.6k**, contradicting
  the new exact authority of **8,404 B**;
- spec §9 and blueprint §12 still test the static guarantee with only
  **+10,000 output**, rather than the D9 provider-total **+26,000**;
- spec §10's resolved-blueprint summary still describes a **2k output
  allowance**;
- blueprint header says “two calls need his confirmation,” where “two
  decisions” is intended, and has an extra closing `**`;
- blueprint `Basis` says spec v0.10 although the reviewed spec is v0.11 with
  D9 drafted; and
- §7.0 claims no other passage restates a table value, although D7, D8, sizing,
  tests, and B3 do so repeatedly.

For the last item, either enforce the no-restatement rule or state the workable
contract: §7.0 is the normative authority, explanatory restatements cite it,
and executable tests derive values from the implementation constants. The
current absolute claim creates another false assurance against drift.

Historical values may remain in changelogs when clearly labeled as
superseded.

## What should remain closed

- the D9 split-envelope architecture and 16,000 policy reserve;
- output-side budget events excluded from the selector-failure gate;
- §8.6 removal;
- the v1 `MAX_EXPRESSIONS = 10` bound;
- exact schema-maximum compact serialization;
- `tokens_lte_bytes` ownership and fail-configuration behavior;
- M=100 and the 283k < 320k static fat fit;
- the compact indexed-expression wire;
- immutable fixture v1 and policy-v2 compatibility artifact; and
- all package, replay, projection, and pass-1.5 boundaries.

## Approval conditions

I will vote **APPROVE** when:

1. Joseph confirms the two pending D9 owner decisions;
2. thin and fat post-call output-budget branches have complete result, audit,
   F1-interaction, and call-count contracts;
3. provider stop reasons are normalized and the cap-stop/usable-document
   precedence is explicit;
4. the over-`MAX_EXPRESSIONS` typed outcome is named; and
5. the listed current-version inconsistencies are synchronized.

These are narrow contract-completion changes around the ratifiable v0.9
architecture, not a request for another design round.

## Verification

- The supplied artifact is 293 lines with SHA-256
  `34aea0604e442d5c5de37297b1f2f977a47e7018a067e15efc0adca6cc804a69`.
- It is byte-identical to the two-document diff for
  `e1b6d37..a1a7046`.
- Frozen SearchSnapshot fixture tests: **7 passed**.
- Provider output-cap plumbing, native stop-reason values, current status and
  result enums, orchestration branches, and normative sizing references were
  checked directly against the repository.
