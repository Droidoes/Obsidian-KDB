# Task #123 Blueprint v0.5 / Spec v0.7 Confirmation Review — Codex

**Date:** 2026-07-26  
**Reviewer:** Codex  
**Review basis:** commit `ff8ac7f` and
`2026-07-26-task123-blueprint-v0.4-to-v0.5-confirmation.diff`

## Vote

**REVISE — targeted contract correction.**

K2, K3, and all three minor edits from my v0.4 review are closed. D6 also
removes the thin/fat calculation asymmetry and adds full-request inputs and a
fat output allowance. Those are good corrections.

K1 is not closed, however. My option 2 separated the calibrated planning
estimate from a **conservative hard-admission guard**. Blueprint v0.5 instead
uses the calibrated `bytes / 4` estimate as the admission guard itself. Applying
the same heuristic to both stages makes the behavior consistent; it does not
make an underestimated request detectable before the call.

## Confirmation table

| v0.4 item | Result | Assessment |
|---|---|---|
| **K1 — full-request token admission** | **Open / blocking** | Both stages now include system, template, query, evidence, and reserved output. But the operative guard remains `bytes / 4`; it cannot detect when actual token density exceeds that estimate. |
| **K2 — stale normative rows** | **Closed** | R3 now carries D1/D5, while SD-4 and R4 name the reduced-M stage-1 recall gate and retain M=150 as the production constant. |
| **K3 — fixture-v1/policy-v2 relationship** | **Closed at blueprint level** | Fixture v1 remains immutable; a checked sibling compatibility artifact will prove byte equivalence; the harness records effective policy version `2`. |
| **Sentence-rule precedence** | **Closed** | Byte truncation explicitly takes precedence. |
| **Cost estimate wording** | **Closed** | The expected-case 160M and policy-ceiling 273M token scenarios are distinguished and priced separately. |
| **Warn-only artifact completeness** | **Closed** | Envelope equality is a successful-write completeness condition; failures produce an incomplete state and `search_artifact_write_failures`. |

## L1 — the preflight cannot detect a broken estimate

Spec v0.7 correctly acknowledges:

- the worst-case full fat request is approximately 381 kB;
- its absolute content-token case can approach one token per byte;
- `bytes / 4` is calibrated, not proved; and
- the “never underestimates” claim is withdrawn.

It then incorrectly concludes that if real content breaks the estimate, the fat
preflight will return typed, zero-spend `budget_exceeded` before a provider
error. The preflight uses the same estimate that has been broken, so it has no
independent signal with which to detect that condition.

A concrete counterexample for the stated 128k-window case:

```text
fully rendered request             381,000 bytes
preflight estimate at bytes / 4     95,250 tokens
reserved fat output                  2,000 tokens
estimated total                     97,250 tokens  # admitted below 102,400

actual density at 2 bytes/token    190,500 tokens
plus reserved output                2,000 tokens
actual total                       192,500 tokens  # does not fit 128,000
```

The preflight admits the request. The API is invoked and the provider—not the
controller—detects the overflow. The promised zero-spend typed preflight
terminal therefore cannot be guaranteed.

The 80% factor is useful operating headroom, but it is not a proof: it covers
only a 1.25× estimation error, while the documents explicitly admit density
variance up to roughly 4× the operative estimate. The single ordinary-fixture
calibration call in D5 measures one observed point; it does not establish a
future-input upper bound.

### Resolution options

The contract must choose between two genuinely different postures:

1. **Preserve the hard safety guarantee.** Keep calibrated `bytes / 4` for cost
   and capacity reporting, but use an independent conservative admission bound
   for safety. That can be an authoritative model tokenizer or a proved
   model-specific tokens-per-byte ceiling, with a deliberately conservative
   fallback. Apply it to the fully rendered request plus chat-protocol overhead
   and reserved output. False rejections are acceptable; false admissions are
   not.
2. **Adopt an honest best-effort guard.** Record that `bytes / 4` plus 20%
   headroom is an owner-accepted operating estimate, not a zero-spend safety
   boundary. Catch a provider context-length rejection as a distinct
   `budget_estimation_miss` outcome, record that a call was attempted and may
   incur spend, and make its rate watched or gated. Remove every claim that an
   estimation miss becomes preflight `budget_exceeded` or can never become a
   provider error.

Option 1 favors integrity and deterministic admission at the cost of tokenizer
dependencies or conservative false rejects. Option 2 preserves the simple,
provider-neutral estimator but explicitly accepts operational misses. Either is
coherent. The current document combines option 2's estimator with option 1's
guarantees.

## L2 — truncating only `summary` does not guarantee the query cap

D6 says the rendered query block never exceeds 4,096 UTF-8 bytes because the
projector truncates `summary`. Repository verification shows that all of these
SD-1 inputs are schema-unbounded:

- `author`;
- `summary`;
- the number and item length of `key_themes`; and
- each `entity_search_keys` string, although the array is capped at ten items.

Consequently, the non-summary fields can exceed 4,096 bytes by themselves.
Calling `summary` the only “realistically” unbounded field is an observed-input
assumption, not the projector property the budget argument requires.

Two valid fixes are:

1. define deterministic byte allocations and character-boundary truncation for
   every variable query field, preserving the query template; or
2. reject a query whose non-summary fields exceed their declared limits with a
   typed, zero-call input/configuration outcome.

Tests should cover oversized `author`, `key_themes`, and individual search keys,
not only an oversized summary. If truncation changes an expression used for
attribution/accounting, the archived QueryPayload must distinguish its original
and rendered forms.

## L3 — specify the complete fat-budget terminal

The new branch defines `status: budget_exceeded`,
`execution: thin_attempted`, stage `fat`, zero fat calls, and no retry. Complete
the result matrix with:

- hits and unresolved expressions;
- `evidence_status` and `body_coverage`;
- concordance;
- stage-2 hydration/yield fields; and
- `logical_call_count` / StageRecord behavior.

Based on the existing semantics, no fat selector call means
`evidence_status: not_applicable`, `body_coverage: None`, hits `[]`, all request
expressions unresolved, concordance null, and no fat StageRecord. If a different
meaning is intended because hydration occurred before preflight, state it
explicitly.

## What should remain closed

- D5 calibration authorization, timing, and sibling artifact;
- one full-request calculation pipeline shared by thin and fat;
- `OUTPUT_ALLOWANCE_THIN = OUTPUT_ALLOWANCE_FAT = 2,000`;
- typed, never-retried budget outcomes when the **operative guard itself**
  evaluates over budget;
- R3 synchronization and reduced-M gate naming;
- immutable fixture v1 plus checked policy-v2 compatibility;
- sentence/byte precedence;
- expected-case versus policy-ceiling expense record;
- successful-write completeness and artifact-write-failure telemetry.

## Approval condition

I will vote **APPROVE** once the next targeted revision:

1. chooses either a conservative independent admission guard or honest
   best-effort overflow semantics;
2. guarantees the query byte ceiling across every unbounded input field; and
3. pins the complete fat-stage budget terminal contract.

No selected search architecture or phase boundary needs to change.

## Verification

- The supplied 252-line file is byte-identical to the two-file diff from
  `960c8e0` to `ff8ac7f` (matching SHA-256:
  `8b5c9e16fc161a9cde50e4a2ccdfda0d2d18ba8d2a1ff95b746760a4784656f7`).
- Frozen-fixture smoke tests: **7 passed**.
- Query-field constraints checked directly in
  `ingestion/enrich/pass1_schema.py`.

