# Task #123 Blueprint v0.8 / Spec v0.10 Confirmation Review — Codex

**Date:** 2026-07-26

**Reviewer:** Codex

**Review basis:** `2026-07-26-task123-blueprint-v0.7-to-v0.8-confirmation.diff`

## Vote

**REVISE — N1–N4 are substantively closed; two newly exposed provider-envelope
contracts and one consistency sweep remain.**

The selected D8 mechanics are now sound at the visible JSON-wire level:

- `Hit.evidence` is gone;
- `max_results`, slug size, attribution, and advisory unresolved values are
  bounded;
- the canonical 120-byte slug authority is reused;
- THIN 13,000 / FAT 10,000 no longer depend on a bytes/token density estimate;
  and
- `tokens_lte_bytes` has a named owner and fail-configuration tests.

That closes all four conditions from my v0.7 review. I would still hold
ratification briefly because the provider's output-token cap can include hidden
thinking/reasoning tokens that are absent from the visible-wire calculation,
and because the new §8.6 experiment is not represented in the blueprint's
phases or test plan.

No search architecture, package boundary, M=100 decision, or integration
sequence needs to be reopened.

## N1–N4 confirmation

| v0.7 condition | Result | Assessment |
|---|---|---|
| **N1 — remove public `Hit.evidence`** | **Closed** | The result contract now matches the compact selector wire. |
| **N2 — derive allowances without a density assumption** | **Closed for visible JSON** | The response values are bounded and the allowances exceed the stated maximum serialized bytes under `tokens_lte_bytes`. The provider-total-output qualification in O1 remains. |
| **N3 — reconcile the slug authority** | **Closed** | `MAX_SLUG_LEN` is imported from `common.paths`; valid 97–120 byte canonical slugs no longer fail search. |
| **N4 — own and enforce `tokens_lte_bytes`** | **Closed** | The model registry/`ModelSpec` ownership, selector-resolution failure, cohort declarations, and tests are named. |

## O1 — Visible JSON tokens are not necessarily provider-total output tokens

The new proof establishes:

```text
visible JSON tokens ≤ visible JSON bytes ≤ OUTPUT_ALLOWANCE
```

But `ModelRequest.max_tokens` is passed to provider fields that may cap the
**total completion**, including hidden reasoning/thought tokens:

- `gpt-5.4-mini` is configured with `reasoning_effort: low`,
  `use_completion_tokens: true`, and therefore receives
  `max_completion_tokens`;
- Gemini is invoked with `ThinkingConfig(thinking_level="minimal")`, not with
  thinking off; and
- `call_model` explicitly adds Gemini `thoughts_token_count` to output tokens.

Consequently, hidden output can consume part of THIN 13,000 or FAT 10,000
before the complete schema-maximum JSON is emitted. A length-truncated response
would then enter the same unparseable → retry → selector-failure chain that the
allowance work is intended to prevent.

The related statement that the whole cohort is “thinking-disabled” is not true
of the current routing layer. `model_pool.py` explicitly says that OpenAI and
Gemini have no verified thinking-disable mapping and injects no disable
parameter for them. GPT carries low reasoning; Gemini defaults to minimal
thinking. DeepSeek is the only D4 route with an explicit verified disable
mapping.

Two distinct closures are available:

1. **Require verified no-hidden-output selector routes.** Define and test the
   provider-specific off control for every admitted selector. Then the visible
   schema allowance can also be the provider output cap. A route for which
   thinking cannot be disabled does not satisfy this stronger static proof.
2. **Separate visible and hidden allowances.** Keep
   `VISIBLE_OUTPUT_ALLOWANCE_THIN/FAT` at 13,000/10,000, add a route-owned
   maximum hidden-token allowance, send their sum to the provider, and reserve
   the sum in context accounting. The static fat fit must use that total. If a
   provider offers no enforceable hidden-token maximum, document an honest
   `output_budget_estimation_miss` terminal based on its length finish reason
   rather than grading the event as selector behavior.

Whichever path is selected, tests need to distinguish visible response tokens,
hidden output tokens, the provider cap, and the context-budget reservation.
The current single `OUTPUT_ALLOWANCE` name conflates them.

## O2 — The §8.6 evidence experiment is not a one-line/free axis

Measuring with-/without-`evidence` can be useful, but the new spec section
creates a second selector task and response schema:

- the with-evidence schema again needs a numeric evidence maximum and a
  separately derived output allowance;
- the research-only prompt and response validator must exist and be archived;
- the harness call budget is multiplied by the variant axis;
- interactions with model, reduced-M, and scoped/whole-graph arms need a
  predeclared run matrix; and
- the result must not silently change the owner-ratified no-evidence production
  contract.

None of those mechanics appears in blueprint §10, P4, P5a, or the P4 harness
tests. P5a still lists only the three-candidate screening, reduced-M gate, and
§8.5 cross-domain A/B.

There are two clean decisions:

1. **Drop §8.6.** D8 remains an owner decision based on an unused,
   unverifiable output field. This is the simpler production architecture.
2. **Keep it as an explicit research-only experiment.** Bound the legacy
   evidence value, derive its visible and provider-total allowances, add its
   prompt/schema to the harness, predeclare the factorial/sampled run matrix and
   call ceiling, update P4/P5a and harness self-tests, and state that it cannot
   mutate the production wire without a later owner amendment.

In either case, remove the incorrect “thinking-disabled cohort” rationale.

## O3 — Complete the final numeric and normative sweep

Four current normative passages still carry superseded mechanics:

- spec D7 says D8 finalized THIN/FAT at 4,000/4,000;
- the binding spec D8 paragraph still contains the 96-byte,
  3-bytes/token, 4,000/4,000 derivation before appending the new mechanics;
- spec §7.1's vault projection still says `+ 4k output`; and
- blueprint §7's vault-scale projection still says `+ 4k output`.

The last two must say FAT `+ 10k output`. More importantly, rewrite the binding
D7/D8 text to state only the final contract. Preserve the superseded
4,000/4,000 derivation in the changelog, where historical decisions belong.
The current document otherwise claims “no density step anywhere” while its
binding D8 paragraph still performs that step.

One numeric input bound is also implicit rather than declared:
`QueryPayload.expressions` has no global ≤10 constraint in the core type, even
though `matched`, `unresolved`, and their maximum integer width are derived from
at most ten expressions. State and validate `len(expressions) ≤ 10` for every
consumer before rendering. “Pass-1.5 emits at most ten” and “human uses one”
are adapter conventions, not a consumer-neutral core invariant.

For reproducibility, record the exact maximum byte integers and the compact
JSON serialization grammar used by the synthetic maxima—not only “12.3k” and
“9.6k.” The tests can be the executable authority, but the blueprint should
name that authority and serializer.

Finally, add the v0.7 confirmation reviews to the spec's `Basis` line; the
blueprint already does so.

## What should remain closed

- all N1–N4 settlements;
- the bounded string-slug wire rather than identity indexing;
- indexed `matched` and advisory `unresolved`;
- duplicate-attribution deduplication;
- M=100 and the fat-input ceiling;
- post-call `budget_estimation_miss` semantics;
- immutable fixture and replay contracts; and
- synthetic schema-maximum tests.

## Approval condition

I will vote **APPROVE** when:

1. provider-total output accounting either excludes hidden output by verified
   route contract or reserves/types it separately;
2. §8.6 is removed or fully represented as a bounded, budgeted, research-only
   P4/P5a experiment;
3. the remaining current 4k/96-byte/density references are removed from
   normative prose and the global ≤10 expression bound is explicit; and
4. the exact serialization maxima/authority and v0.7 review basis are named.

These are final contract-completion changes around the provider envelope and
document consistency, not a request for another architectural round.

## Verification

- The supplied artifact is 187 lines and has SHA-256
  `5707e53d83e16b9e38da61876427b35ef690b6bb5892f4cfcbe4389507a4cb3d`.
- It is byte-identical to the two-document diff for
  `49b2bc8..e1b6d37`.
- Frozen SearchSnapshot fixture tests: **7 passed**.
- The output-token plumbing, model-pool thinking mappings, three D4 model
  entries, and current normative sizing references were checked directly.
