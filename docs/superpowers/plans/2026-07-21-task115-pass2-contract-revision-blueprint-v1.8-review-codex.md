# Task #115 — Pass-2 contract revision blueprint v1.8: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.8  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`) and the ratified carve to Task #116  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** The carve is the correct architecture and v1.8 is close to executable. Resolve three record/contract blockers and two bounded clarifications before Phase 0; do not put the deferred subsystem back into #115.

## Executive assessment

v1.8 makes the right cut. The executable work under #115 is again a coherent
contract revision: provenance first, then the model contract and its deterministic
Python boundaries, then confidence/read-compat work and cross-boundary parity. The
reservation index, occupancy preflight, MOVED protocol, `source_dispositions`,
write-ahead records, and journal 2.3 no longer survive as hidden implementation
requirements. #94 remains a pre-production blocker and #116 now owns the full
lifecycle/durability decision.

The remaining findings do **not** argue for restoring any of that machinery to
#115. They are integrity problems at the new boundary:

1. the claimed v1.7 design seed is not actually present in git;
2. the ratified spec still assigns global collision work to #115;
3. the cohort guard both runs too late and inventories the wrong key;
4. the underivable-stem failure contract does not yet name an executable layer
   boundary; and
5. the MOVED/WAL wording overstates current behavior and partially pre-decides the
   architecture that #116 is supposed to choose from evidence.

## What v1.8 gets right

- The carve is complete in the implementation phases. Searches for the removed
  machinery find it only in history, explicit non-goals, accepted-risk language,
  and the #116 handoff—not as a remaining #115 task.
- The model-facing hardening remains intact: one derivation helper, exact-summary
  semantic validation on every attempt, post-canonicalization repetition of the
  invariant, body-authority links, and graph-owned `LINKS_TO` derivation.
- Phase 0 still gives the prompt experiment a clean causal baseline before the
  schema/prompt rewrite.
- New-write/old-read compatibility remains explicit through dual-mode aggregate
  validation, legacy `outgoing_links` preference, historical journal replay, and
  the normalized confidence-deprecation comparison.
- Repair-stage deletion and stage-flow renumbering remain in the North-Star gate,
  so the blueprint does not silently change the documented pipeline order.
- #116 has the right conceptual boundary: reservation, all source lifecycle
  transitions, interrupted-run recovery, replay material, and live/rebuild
  convergence belong in one design cycle paired with #94.

## Findings

### F1 — High: v1.7 is not currently preserved as a recoverable design seed

The blueprint says v1.7 is preserved (`v1.8:7-9`, `358-360`), and the #116 ledger
row points to the current blueprint path's “git history.” At the reviewed repository
state:

- `git ls-files` reports that blueprint path as untracked;
- `git log --all -- <blueprint path>` returns no commits; and
- the file at that path now contains v1.8, not v1.7.

The v1.7 Codex review records major parts of the design, but it is a review and
staging recommendation, not a complete copy of the v1.7 blueprint. Therefore four
rounds of detailed subsystem design are not recoverable from the repository pointer
currently recorded for #116.

**Required amendment:** archive the complete v1.7 text under a stable #116-owned
path, for example
`docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md`,
then point the v1.8 header and #116 ledger row directly to it. Preserve its status as
a **candidate design seed**, not a ratified #116 architecture. If the complete text
cannot be recovered from editor/session history, correct the “preserved” claim and
record exactly which R8–R11 review artifacts remain; do not rely on nonexistent git
history.

### F2 — High: the architecture basis still assigns collision handling to #115

The implementation blueprint explicitly carves global summary reservation and
collision preflight out (`v1.8:151-154`, `347-349`). The governing v1.5 spec still
says D-115-11's executable slug rule includes “collisions”
(`pass2-contract-audit-findings.md:109-112`) and its validation matrix still requires
summary-slug collision tests (`:166-168`). The #115 ledger simultaneously claims
all D-115-1..15 as its ratified basis.

That leaves two authoritative instructions for the implementer: the spec requires
collision behavior, while the blueprint forbids implementing it. Filing #116 does
not by itself amend D-115-11.

**Required amendment:** issue a small ratified carve addendum (or spec v1.6) that
splits D-115-11 cleanly:

- #115 retains deterministic per-source derivation, exactly-one-summary, exact
  expected slug, underivable-stem rejection, post-canonical validation, and
  fail-closed writer lookup;
- #116 owns cross-source derived-slug collision detection, occupancy/reservation,
  and lifecycle-aware ownership; and
- the validation-matrix “collision” item moves to #116 while #115 keeps local
  length/non-ASCII/empty and exact-match boundary tests.

Update the #115 ledger's “D-115-1..15” wording to cite that carve amendment. This
should happen before the North-Star documentation commit so Phase 1 is driven by one
unambiguous contract.

### F3 — High: the cohort guard can miss real collisions and runs after the baseline

Phase 5 inventories “duplicate filename stems” immediately before only the
comparison cohort (`v1.8:329-334`). That does not establish the stated conclusion
that the deferred reservation exposes the cohort to no known collision case.

First, summary identity is the **derived** value, not the raw stem. Distinct filename
stems can collapse after normalization and the 112-character stem budget—for
example, `Foo Bar.md` and `foo-bar.md`, or long stems that differ only after the
truncation boundary. An exact duplicate-stem inventory produces false negatives.

Second, the guard occurs after the Phase-0 baseline has already run
(`v1.8:95-97`). If the Phase-5 inventory finds a problem, the baseline is already an
uncontrolled observation. R12's staging recommendation was to guard **either
cohort**, not only the second one.

**Required amendment:** before the Phase-0 baseline, group the pinned cohort by the
fully normalized/truncated `expected_summary_slug` value, scoped exactly as the
future reservation policy will be scoped, and report underivable stems as well.
Persist the source list/corpus fingerprint, derived-key groups, and tool/algorithm
version with the baseline artifacts. Before Phase 5, recompute and require the same
corpus and zero-collision result. If the production helper is not yet landed at
Gate 0, use a spec-pinned read-only inventory and add a Phase-1 equivalence test
against the centralized helper.

### F4 — Medium: the zero-call derivation failure crosses two incompatible existing paths

Task 1.4 promises all of the following (`v1.8:141-145`):

- reject an underivable stem before API spend;
- use the existing `model_response=None` telemetry path; and
- return `failure_stage="validate"` without new telemetry machinery.

The existing code does not compose those statements automatically:

- `compile_source()` builds graph context before calling `compile_one()`
  (`compiler/compiler.py:634-665`);
- only `compile_one()` owns the `finally` block that writes exactly one response
  record (`:520-598`); and
- every error returned by `compile_one()` is currently converted to
  `CompileSourceResult(failure_stage="compile")` (`:666-675`).

`build_resp_stats()` does correctly emit `attempts=0` and zero tokens when
`model_response is None`; the ambiguity is where the typed failure is raised and
whether “failure_stage” means the response record, the outer result, or both.

**Required amendment:** pin one concrete route. The smallest is to execute the
helper inside `compile_one()` after telemetry state initialization and before prompt
construction/model call, set a typed validation failure for the response record,
and explicitly propagate/map that type if the outer `CompileSourceResult` must also
say `validate`. If the outer result may remain `compile`, say so and test the two
fields separately. If rejection must precede even the context read, the plan needs
an explicit outer telemetry seam; the current “existing path” is then insufficient.

Tests should assert exactly one response record, `attempts == 0`, zero token/cost
totals, the typed exception, the intended inner and outer failure stages, no model
call, and no retry.

### F5 — Medium: lifecycle wording should describe the accepted risk without pre-deciding #116

The accepted-behavior paragraph says “MOVED sources” currently produce de-facto
double ownership (`v1.8:20-24`). That is too broad. A normally compiled, same-hash
MOVED source is placed in `to_skip`, reaches reconciliation, and GraphDB transfers
its `SUPPORTS` edges. The known residue is the narrower branch where a MOVED entry
also appears in `to_compile`; the orchestrator skips its reconcile op after the new
path compiles (`orchestrator/kdb_orchestrate.py:872-878`), which can leave predecessor
ownership behind.

The #116 ledger also lists a write-ahead pending record and five-state recovery
table as though they are already required task outputs, then says WAL versus bundles
versus a simpler model will be chosen from evidence. The latter is the reason for
the carve; the former wording partially pre-ratifies v1.7.

**Required clarification:**

- distinguish wiki last-writer-wins from graph co-ownership for derived-slug
  collisions;
- describe the MOVED exception as the `MOVED ∩ to_compile` reconcile-skip branch,
  while acknowledging that ordinary move-only transfer already works;
- scope Phase 4's #115 live/rebuild batch to lifecycle-neutral NEW/CHANGED cases,
  leaving MOVED/fail-fast convergence to #116/#94; and
- describe WAL + the five-state table as the **v1.7 candidate**, one of the designs
  #116 will evaluate against evidence, not a foregone deliverable.

## Recommended disposition

| Item | Before Phase 0? | Disposition |
|---|---:|---|
| F1 — durable v1.7 seed | Yes | Archive it or correct the preservation claim and links. |
| F2 — spec/blueprint collision split | Yes | Ratify a narrow carve addendum before the North-Star commit. |
| F3 — derived-key cohort guard | Yes | Run and persist it before baseline; repeat before comparison. |
| F4 — zero-call failure seam | Before Phase 1 | Pin inner/outer failure staging and tests. |
| F5 — MOVED/WAL wording | Before #116 design; preferably now | Correct the accepted-risk and candidate-architecture descriptions. |

## Final verdict

**Approve the Option-2 architecture; hold Phase 0 for the three bounded blockers
above.** The scope split itself should stand. Once v1.7 has a real durable home, the
spec formally records which half of D-115-11 moved, and the cohort is guarded by the
actual derived key before baseline, #115 can proceed in the v1.8 stages without
reopening the reservation/MOVED/durability subsystem.

No implementation or test execution was performed for this documentation review.
