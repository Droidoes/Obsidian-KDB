# Task #115 — Pass-2 contract revision blueprint v1.9: Codex follow-up review

**Date:** 2026-07-22  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.9  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** R13 is resolved in substance. Make three bounded amendments—one implementation-seam pin and two documentation sweeps—then proceed to the North-Star/docs gate. Do not reopen or re-expand the carve.

## R13 resolution audit

| R13 item | Status | Evidence / assessment |
|---|---|---|
| F1 — durable v1.7 seed | Resolved in the working tree | The 556-line v1.7 blueprint is archived at `docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md`; its banner explicitly says candidate/not ratified and preserves WAL, the five-state table, lifecycle channel, and journal 2.3 as design-seed content. The #116 ledger now points directly to it. Include this currently-untracked file in the approved docs commit so the preservation becomes durable. |
| F2 — D-115-11 split | Resolved substantively | The spec addendum assigns deterministic per-source exactness to #115 and cross-source collision/reservation to #116; the validation matrix makes the same split, and the ledger cites it. Only version metadata remains stale (R14 F2 below). |
| F3 — cohort collision guard | Resolved | Task 0.3 runs before Gate 0, groups by the fully normalized/truncated derived key, reports underivable stems, persists corpus/tool evidence, and repeats against the same corpus before Phase 5. |
| F4 — zero-call failure route | Mostly resolved | Placement, inner/outer intended stages, no-call telemetry, retry behavior, and tests are pinned. One concrete propagation detail remains (R14 F1 below). |
| F5 — lifecycle wording/scope | Resolved substantively | The blueprint limits the existing MOVED defect to `MOVED ∩ to_compile`, separates wiki last-writer-wins from graph co-ownership, scopes Phase 4 to lifecycle-neutral cases, and treats WAL as one candidate rather than #116's predetermined deliverable. Only stale shorthand remains (R14 F3 below). |

## Residual findings

### R14 F1 — Medium: the typed stem failure still needs an explicit propagation carrier

Task 1.4 now says `compile_one` “returns the typed error” and
`compile_source` maps it to outer `failure_stage="validate"`
(`v1.9:171-180`). Current `compile_one` returns an error **string**, not an
exception or structured failure, and Task 1.5's replacement tuple still leaves the
error carrier unspecified. The existing `FailureStage` literal also does not include
`"validate"` (`compiler/compiler.py:57-60`), even though Task 1.4 intends to pass
that value through `_set_failure()`.

The implementation intent is clear, but two plausible implementations remain: alter
the `compile_one` return contract, or classify from the captured response record.
Pinning one avoids an improvised signature change during Phase 1.

**Recommended minimal amendment:**

1. Define the typed derivation exception and add `"validate"` to the telemetry
   `FailureStage` literal.
2. Inside `compile_one`, catch it and call `_set_failure(state, "validate",
   type(e).__name__, str(e))`; keep the outward human error as a string.
3. In `compile_source`, map the outer stage from the captured record's typed
   `failure_exception_type` (or add an explicit structured result discriminator).
   State which one the plan chooses. The captured-record route preserves the
   existing tuple shape and is the smaller change.
4. Keep the already-listed assertions for one record, zero spend, typed exception,
   inner/outer `validate`, no call, and no retry.

### R14 F2 — Low: spec version metadata still identifies v1.5

The addendum and ledger call the governing spec v1.6, but:

- the spec header still says `Version: v1.5` (`pass2-contract-audit-findings.md:3`);
- the blueprint architecture-basis line still says `spec v1.5` (`v1.9:3-4`); and
- the ledger calls the same file `spec v1.6`.

The contract body is no longer contradictory, so this is not a renewed F2 blocker.
It is a provenance mismatch in the document that the North-Star gate will cite.

**Required cleanup:** update the spec header to v1.6 (preserving the v1.5 ratification
history in its description/changelog) and update the blueprint basis to “spec v1.6,
including the ratified carve addendum.”

### R14 F3 — Low: four stale raw-stem phrases survive the normalized-key correction

Task 0.3 uses the correct derived key, but residual wording still narrows the known
collision class to raw/same basenames:

- blueprint accepted behavior: “same-basename derived-slug collisions” (`v1.9:20-22`);
- blueprint #116 evidence list: “duplicate-stem inventory” (`:404`);
- blueprint risk register: “duplicate-stem inventory” (`:422-424`); and
- spec v1.6 changelog: “same-basename collisions”
  (`pass2-contract-audit-findings.md:202-203`).

Distinct stems can derive the same key, which is the reason Task 0.3 was corrected.
These phrases should not leave a competing shorthand in the architecture record.

**Required cleanup:** use “cross-source derived-slug collisions” and “normalized
derived-slug collision inventory” consistently in all four locations.

## Final verdict

The R13 blockers are closed at the architectural level. R14 F1–F3 are narrow enough
to fold directly into v1.10 without another design round: pin the existing telemetry
carrier, align the spec version metadata, and finish the derived-key terminology
sweep. After that, #115 is ready for its North-Star/docs commit and staged execution.

No implementation or test execution was performed for this documentation review.
