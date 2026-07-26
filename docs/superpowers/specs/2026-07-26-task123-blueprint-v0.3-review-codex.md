# Task #123 Blueprint v0.3 / Spec v0.5 Confirmation Review — Codex

**Date:** 2026-07-26  
**Reviewer:** Codex  
**Review basis:** `51a16f2` and
`2026-07-26-task123-blueprint-v0.2-to-v0.3-confirmation.diff`

## Vote

**REVISE — targeted corrections only.**

The v0.3 changes close the core execution, provenance, and measurement-contract
findings. I do not recommend reopening the selected architecture. Approval is
blocked only on the remaining policy contradictions and on making the fat-stage
context limit enforceable.

## Confirmation

| Codex item | Result | Assessment |
|---|---|---|
| **C1 — stage/attempt contract** | **Closed** | The branch table now models zero, one, or two logical calls correctly; `logical_call_count == len(StageRecord[])` is explicit; and the D3 thin-failure terminal result is complete. |
| **C2 — multi-hit provenance** | **Closed** | Provenance is carried per hit, KPI aggregation uses the hit-level facts, and the expression-level value is a deterministic representative projection. State C and unattributed hits are covered. |
| **C3 — pass-1.5 measurement contract** | **Closed** | Pass 1.5 is diagnostic and outside the scored union; the non-movement test protects the existing leaderboard; per-search records, `searches_attempted`, and reconciliation are specified. |
| **C4 — calibration mechanics** | **Open** | Paid live calibration before D7 conflicts with D1's zero-live-selector-spend rule, and a P1 test depends on measurements that are not produced until the end of P2. |
| **C5 — spec and North-Star synchronization** | **Partial** | D1–D4, the ledger, North Star, and B1 status are updated, but the spec's later normative sections still retain incompatible v0.4 behavior. |

## Required corrections

### 1. Reconcile calibration with D1 and the phase gates

Calling each candidate once at the end of P2 is still paid live selector spend,
even if those calls are labelled “calibration” rather than “experiment.” That
directly conflicts with D1's requirement that P1–P4 use canned or mocked
responses with zero live selector spend before D7.

The blueprint must choose and record one of these distinct contracts:

1. **Preserve D1 unchanged.** Keep P1–P4 fully offline, use canned calibration
   records to test estimator arithmetic, and perform real provider calibration
   only after D7 authorization.
2. **Amend D1 narrowly.** Authorize exactly one non-comparative calibration call
   per candidate after P2, with a fixed prompt, no ranking or selection effect,
   a hard three-call ceiling, and a separately recorded Joseph authorization.

Under either contract, P1 cannot assert against measurements generated after
P2. P1 should test estimator structure with deterministic fixtures. Any
assertion against provider-reported measurements belongs in the calibration or
P2 gate.

### 2. Synchronize the complete spec body

Spec v0.5 records D1–D4 in §0, but an amendment preamble alone does not make the
document implementation-safe. The later normative body still needs direct
edits, including:

- add `fat_after_thin_failure` everywhere the closed `execution` enum is
  defined;
- replace “exactly two calls” and unconditional thin-then-fat language with the
  branch-specific zero/one/two-call contract;
- replace the obsolete 55k/64k stage-2 bound;
- update integration and KPI tests that still assume two calls, recall@150, or
  the former live-cohort model;
- remove stale gating language that says implementation must wait for labels;
- retire open items already resolved by D1–D4 and blueprint v0.3.

The blueprint and spec should describe one executable contract without requiring
the implementer to infer which later paragraphs §0 silently overrides.

### 3. Make the fat-stage maximum enforceable

`275 words × an observed bytes-per-word ratio` is a corpus estimate, not a
policy maximum. A whitespace-delimited word can be arbitrarily large or
multi-byte, and the evidence block is not the entire model input. Therefore the
current calculation cannot guarantee the asserted byte or token ceiling.

Two distinct remedies are available:

1. **Bound the projection.** Introduce an excerpt-policy version with a hard
   UTF-8 byte ceiling per entity. Recompute the whole rendered-input bound,
   including fixed prompt, query, delimiters, and output allowance.
2. **Guard the rendered request.** Preserve the current excerpt policy, but run
   an exact fat-stage preflight over the fully rendered input and return a typed,
   deterministic budget outcome when it exceeds the selected model's headroom.
   This requires the corresponding R2 and terminal-contract amendment.

Either remedy is valid. The ratified documents must select one; the present word
count must not be described or tested as a static byte bound.

### 4. Keep calibration outside the frozen evaluation fixture

Calibration measurements should not mutate the checksummed
`task123_search_snapshot_v1/manifest.json`. Persist them as a separate artifact
that references the fixture version, input hash, prompt versions, model ID, and
counting source. If they must live inside the fixture, create a new fixture
version and regenerate its checksums explicitly.

## Approval condition

I will vote **APPROVE** once the next revision:

1. resolves the D1/calibration policy and phase dependency;
2. folds D1–D4 through the complete normative spec;
3. replaces the estimated fat-stage “maximum” with an enforceable guard; and
4. separates mutable calibration evidence from the frozen fixture.

These are contract-hardening changes, not an architectural reset. C1–C3 should
remain closed.

## Verification performed

- Reviewed the supplied v0.2-to-v0.3 confirmation diff and its paired spec
  v0.4-to-v0.5 changes.
- Confirmed the retry and context-window assumptions against the current model
  calling/configuration code.
- Ran the task #123 frozen-fixture smoke tests: **7 passed**.

