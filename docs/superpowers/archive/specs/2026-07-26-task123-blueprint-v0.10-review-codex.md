# Task #123 Blueprint v0.10 / Spec v0.12 Confirmation Review — Codex

**Date:** 2026-07-26

**Reviewer:** Codex

**Review basis:** `2026-07-26-task123-blueprint-v0.9-to-v0.10-confirmation.diff`

## Vote

**APPROVE / CONCUR-WITH-ITEMS.**

P1–P4 are closed in substance and in the executable blueprint contract. D9 is
ready for Joseph's two owner confirmations:

1. the 13,000/10,000 visible allowances plus the 16,000 hidden-output policy
   reserve; and
2. removal of §8.6.

I continue to approve both decisions and `MAX_EXPRESSIONS = 10`. Once Joseph
confirms the two D9 decisions, no further Codex concurrence round is needed
before ratification and P1.

The one wire-arithmetic correction below should be absorbed before its golden
tests are written. It does not reopen the architecture or invalidate either
output allowance.

## P1–P4 confirmation

| Prior item | Result | Assessment |
|---|---|---|
| **P1 — complete post-call output-budget outcomes** | **Closed** | Thin, fat-after-thin, and fat-after-F1 outcomes now pin result fields, evidence/body coverage, spend, `StageRecord` counts, F1 interaction, and terminal call counts. Keeping the terminal terminal is the simpler contract. |
| **P2 — normalize stop reasons and preserve salvage** | **Closed** | The contract uses a closed `api_call_type`-aware map, archives raw and normalized values, rejects guessing on unknown values, and applies `cap stop AND no complete usable document` before generic retry. Complete usable JSON remains salvageable. |
| **P3 — name the expression-bound violation** | **Closed** | `InvalidGraphSearchRequest(code="max_expressions_exceeded")` is the coherent option: the request is invalid before a search/audit result exists. Zero rendering, reads, calls, and `StageRecord`s are pinned. |
| **P4 — synchronize the current contract** | **Closed** | The stale provider-envelope figures, version/basis labels, §7.0 authority rule, and unsupported reserve claim are corrected. |

The P1 tests should implement output-cap classification inside the common
`stage_call` flow, immediately after each provider response and before
response-class retry. Blueprint §2.2's explanatory block is visually placed
after the fat call even though it governs both thin and fat; its explicit
outcomes and tests already make the intended behavior unambiguous.

## Scope of the Gemini stop-reason defect

Agreed: the omission outside #123 is intentional and correct for this diff.
Changing shared Pass-1/Pass-2 telemetry here would mix a pre-existing defect
and a watched-series re-baseline into the semantic-search feature.

It is nevertheless a live defect, not merely follow-up polish:
`token_overrun` and the compiler truncation guard both miss Gemini
`MAX_TOKENS`. It should receive a separate task-ledger ID and verification
plan. That task can decide whether normalization becomes a shared
`common.call_model` boundary primitive or remains consumer-side. This is not a
#123 approval condition.

## Review-label calibration

The process observation is fair. My v0.9 body said the architecture was
ratifiable and the remaining work was narrow, while the **REVISE** label
communicated another design stop. In hindsight, **CONCUR-WITH-ITEMS** would
have represented that state more accurately while preserving P1–P4 verbatim.

Going forward:

- **REVISE** means an unresolved owner fork, an invalid safety/correctness
  argument, or a contract that permits materially divergent implementations.
- **CONCUR-WITH-ITEMS** means the architecture and owner path are coherent and
  bounded translation/consistency fixes can be absorbed without another
  design decision.

I will keep filing concrete defects at full strength; I will not use the vote
label itself as a proxy for their count.

## Decision — truncated attempts and `valid_entry_yield`

Choose **option 1: keep `valid_entry_yield = None` when
`returned_entries = 0`; do not put the truncated attempt in its denominator.**

`valid_entry_yield` is an entry-level conformance ratio:

```text
validated entries / entries in a complete, structurally usable response
```

A truncated attempt with no usable document has no entry population. Treating
the attempt as a zero-valued entry would redefine the metric into a mixture of
entry conformance and output-budget reliability, contaminating the selector
quality series with controller/provider-envelope mechanics.

No new exclusion marker is required. The existing fields already distinguish
the two null cases:

| Case | `valid_entry_yield` | Existing discriminator |
|---|---:|---|
| Honest empty selection | `None` | `status: completed` |
| Output-cap terminal with no usable document | `None` | `status: budget_exceeded`, `detected: post_call`, `budget_side: output` |

The watched per-model presentation should show the output-budget terminal rate
beside yield rather than interpret the yield column in isolation. If a cap
stop accompanies a complete usable document, normal validation applies and
its returned entries participate in yield, exactly as D9.4 states.

## Non-blocking wire correction before implementation

The claimed exact FAT serialization is not reproducible from the stated
zero-based wire contract:

- spec §2.3 bounds every index to `[0, len(expressions))`, so ten expressions
  use `0..9`;
- blueprint §7.0a says the index width is single-digit at ten; but
- **8,404 B** corresponds to a one-based `1..10` list under a serializer with a
  space after each colon, while the contract says zero-based.

Under strict compact JSON separators, the shown zero-based grammar produces
**8,251 B** at ten expressions (and THIN **12,314 B**). Using the colon-space
form that explains the recorded THIN **12,315 B** produces FAT **8,353 B**.
The counterfactual **10,414 B at twenty expressions** likewise does not follow
from either fixed grammar.

Recommendation: retain the already normative **zero-based** index contract,
name the exact JSON separators, and derive all displayed maxima mechanically
from that serializer and `MAX_EXPRESSIONS`. The 13,000/10,000 allowances remain
safe under every listed figure, so this is an attribution/golden-test
correction—not a budget or architecture blocker.

Pure editorial cleanup: the spec's Status line nests a second `**...**` around
“D9 drafted” inside an existing bold span. Remove the inner markers.

## Verification

- The supplied artifact is **182 lines**, SHA-256
  `6f7196aff5a5dc4ccde0dfee9eba506a7ca65d276291c5c72baad5a5d3de7c81`.
- It is byte-identical to the targeted two-document diff for
  `a1a7046..25474c4`.
- Frozen SearchSnapshot fixture tests: **7 passed**.
- No code or architecture change is requested by this review.
