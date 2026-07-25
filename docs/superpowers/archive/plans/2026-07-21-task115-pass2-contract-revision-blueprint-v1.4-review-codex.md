# Task #115 — Pass-2 contract revision blueprint v1.4: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.4  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Three functional corrections required before Proceed

## Executive assessment

v1.4 faithfully incorporates the post-canonical exact-summary gate, the split
preflight test expectations, the named graph-query boundary, and the concrete
zero-call telemetry/KPI contract. Those amendments are ready.

The MOVED amendment identifies the right architectural problem and fixes the main
happy/failure path, but it is not yet an executable “EVERY outcome” state machine.
The current conductor has additional terminal branches before and after Pass 2; a
failure-only move also mutates graph state without producing a fresh replay payload.
Separately, the proposed graph query result cannot distinguish an unused slug from
two collision states that must not silently pass.

These are narrow corrections. No ratified Task #115 product decision needs
reopening, and the rest of the blueprint does not need another broad rewrite.

## Prior-review resolution

| v1.3-review amendment | v1.4 status | Assessment |
|---|---|---|
| Complete MOVED reconciliation on success and failure | Partial | Main Pass-2 cases are described; Pass-1, noise, commit-failure, limit, next-run, and replay branches remain undefined. |
| Revalidate exact summary slug after canonicalization | Resolved | Both count and exact source-derived slug are checked before persistence, with typed alias failures. |
| Correct zero-call assertions for allowed preflights | Resolved | Rejecting and allowed call-through cases now have distinct assertions. |
| Use a named graph query API | Partial | Boundary placement is correct, but `list[str]` cannot represent the occupancy states the policy must distinguish. |
| Name the telemetry writer and KPI behavior | Resolved | Shared writer, scored-rate preservation, diagnostic, and mixed/all-zero tests are pinned. |
| Remove orphaned aliases if unused | Resolved | Included as correctly conditional cleanup. |

## Findings

### F1 — High: the MOVED lifecycle still omits real conductor outcomes and the next-run transition

Task 2.5 promises exactly-once reconciliation on every outcome, but its failure
branch names only preflight/model/schema/canonicalize failures and its system matrix
tests only success, preflight failure, and model/schema failure (blueprint lines
297–325).

The live conductor has more paths for a source that is both in `to_compile` and has
a MOVED op:

- Pass-1 enrichment failure commits source failure before `compile_source`
  (`orchestrator/kdb_orchestrate.py:627-662`);
- Pass-1 classifies the destination as noise and takes `_commit_noise_source`
  (`685-697`);
- page apply or transactional graph sync fails after a successful compile
  (`806-847`);
- manifest write fails after the graph transaction committed, producing the
  deliberate β residual and a run-fatal abort (`812-828`); and
- `--limit` can leave later moved compile candidates unprocessed before the
  reconcile queue (`868-878`).

These outcomes do not all have the same correct mutation. A source-local failure
should preserve the predecessor's usable graph state under the destination Source;
a successful noise classification should retire the predecessor without leaving the
destination as `no_graph_db` while it still SUPPORTS pages; graph-sync rollback needs
a separate move-only transaction; and a manifest-post-graph failure must not apply
the move twice on retry.

There is also a second-run state that the proposed tests do not cover. After a
rename-with-new-stem fails, the manifest record and SUPPORTS edges move to the new
Source while retaining the predecessor's old summary slug and
`last_compiled_hash`. On the next scan, `previous_path` is gone. The reservation
preflight must explicitly permit this current-source transitional ownership so the
source can compile its new expected summary slug and converge. A single-run
`live == rebuild` assertion does not prove that.

**Required correction:** add a compact outcome table to Task 2.5 with, for every
branch, (a) graph mutation, (b) manifest mutation, (c) whether prior SUPPORTS are
transferred or dropped, (d) when the move becomes handled, and (e) retry behavior.
At minimum cover Pass-1 failure, noise, Pass-2 failure, page-apply failure,
graph-sync failure, manifest-post-graph residual, and limit-deferred reconciliation.
Add a renamed-stem two-run test: first run fails, second run reaches the model and
converges without collision or a duplicate move.

### F2 — High: a failure-only MOVED mutation is not captured by the replay artifact path

Under v1.4, a failed moved source now changes the live graph even though it contributes
no compiled source. The current orchestrator calls `_finalize()` only when
`accumulated_crs` is non-empty (`orchestrator/kdb_orchestrate.py:895-909`), and
`_finalize()` is what writes the fresh combined `state/compile_result.json`
(`218-220`). An all-quarantined move run therefore has a new scan-driven graph
mutation but no corresponding fresh compile payload. Leaving the prior baton in
place is worse than omission because it can pair a new `last_scan.json` with a stale
compile result.

The MOVED operation lives in `last_scan.to_reconcile`; replay can represent it with
an empty `compiled_sources` mutation payload. The plan must nevertheless make that
pair durable for the run. Without it, Task 2.5's promised `live graph == rebuild`
cannot be demonstrated through `ObsidianRunsAdapter`, whose eligible compile event
requires both per-run `compile_result.json` and `last_scan.json`
(`kdb_graph/adapters/obsidian_runs.py:89-145`).

**Required correction:** make every run that commits a graph lifecycle mutation
emit/archive a matched replay pair, including move-only and failure-only runs. Define
the empty compile-result shape and journal eligibility explicitly. Exercise the
actual adapter/rebuilder path in the failure tests; calling `apply_compile_result`
twice with an in-memory scan is not an independence proof.

### F3 — High: `summary_supporting_source_ids() -> list[str]` cannot enforce fail-closed slug occupancy

Task 1.4 defines graph state solely as Source IDs supporting an Entity whose
`page_type` is `summary` (blueprint lines 151–157). That result collapses three
materially different states to the same empty list:

1. no Entity exists at the expected slug — normal first compile;
2. a summary Entity exists but has no SUPPORTS owner — an orphan/unowned collision;
3. a concept/article Entity occupies the slug — a cross-type collision.

The test list mentions missing, unowned, and non-summary cases but does not state
their outcomes, and the proposed return type cannot report which state occurred.
This is not harmless: `Entity.slug` is the graph primary key
(`kdb_graph/schema.py:62-65`), and `_upsert_entity()` overwrites `page_type` on a
MERGE (`kdb_graph/intake.py:283-299`). Treating a non-summary occupant as “no owner”
can retype the graph Entity while page_writer leaves the prior type's Markdown file
in a different directory.

**Required correction:** return a richer occupancy value, for example
`SummarySlugState(exists, page_type, supporting_source_ids)`, or add a companion
named query. Pin an explicit truth table. The safe default is: absent+unreserved
passes; current owner and permitted MOVED predecessor pass; distinct/ambiguous owner,
unowned existing Entity, non-summary occupant, and unexplained manifest/graph
disagreement reject before the model. If reclaiming an unowned summary is desired,
that is a separate explicit policy—not an empty-list accident.

### F4 — Medium: exactly-once move observability must move with the mutation

Today `sources_moved` and `reconcile_completed` are emitted only from the reconcile
queue (`orchestrator/kdb_orchestrate.py:884-893`). Once compile/failure paths mark a
move handled and the queue skips it, those paths will under-report moves unless the
counter/event responsibility moves too.

Pin one event and one count increment at the point the move becomes durable on every
successful handling path, and none on rollback or retry. Prefer an in-memory handled
key such as `(from_path, to_path)` over adding a live-only flag to the serialized
`ReconcileOp`; the archived scan must remain a complete replay instruction.

## Required v1.5 amendments

- [ ] Replace Task 2.5's partial branch list with an explicit MOVED outcome/state
      table covering Pass 1, noise, Pass 2, commit failures, β residual, and limit.
- [ ] Add renamed-stem next-run convergence tests, not only first-run state checks.
- [ ] Persist a matched replay payload for move-only/failure-only graph mutations
      and test equality through the actual adapter/rebuilder.
- [ ] Replace the owner-list-only graph API with occupancy-aware state and pin the
      missing/unowned/non-summary outcomes.
- [ ] Preserve exactly-once move counts/events without contaminating replay input.

## What is ready

- Prompt provenance, packaging, clean-commit sequencing, and cohort gates.
- Four-field model response, aggregate migration, and historical read compatibility.
- Exact summary identity before and after canonicalization.
- Body-authority canonical links and Gate-2 graph-side edge derivation.
- Repair-stage deletion, `ParsedSummary` migration, and fixture split.
- Zero-call response telemetry and KPI diagnostic semantics.
- Logical Entity-confidence deprecation and snapshot-v7 isolation.

## Final verdict

Revise before Proceed. v1.4 resolves four of the five prior amendment areas cleanly,
but the MOVED work needs to be expressed as a complete state machine and a replayable
mutation, and the graph preflight needs occupancy—not only ownership—to be genuinely
fail-closed. These corrections are localized to Tasks 1.4 and 2.5 plus their system
tests; the broader Task #115 architecture remains ratifiable.
