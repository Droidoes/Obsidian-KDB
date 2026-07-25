# Task #115 — Pass-2 contract revision blueprint v1.3: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.3  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Two functional corrections required before Proceed

## Executive assessment

v1.3 fully absorbs the six requested v1.2 amendments. New aggregates now omit
`status`; summary identity has one pure derivation helper; the reservation index is
threaded from the live manifest into `compile_source`; preflight telemetry is
explicitly zero-call; replay and CLI identity migrate to `source_id`;
`ParsedSummary` remains non-throwing; and the North-Star commit finally describes the
complete stage change.

The plan is close, but the deeper call-graph pass found two functional blockers:

1. MOVED+CHANGED is allowed through collision preflight, but the current live commit
   path never performs the graph's MOVED reconciliation and unconditionally skips it
   later. The predecessor therefore remains an active graph owner; failure paths can
   also move the manifest without moving the graph, guaranteeing the next fail-closed
   preflight rejects the source.
2. exact summary identity is checked before canonicalization, while an alias-ledger
   singleton can rename the summary page afterward. The post-canonical gate checks
   only the number of summaries, so a canonical summary alias can bypass both the
   filename rule and the reservation index.

Three medium execution details should be pinned in the same narrow revision. No
ratified product decision needs reopening.

## Prior-review resolution

| v1.2 amendment | v1.3 status | Assessment |
|---|---|---|
| Remove `status` from new aggregates | Resolved | `PageIntent` drops it and operational consumers own the `active` default. |
| Define typed reservation-index plumbing and MOVED predecessor semantics | Partial | The preflight flow is explicit; the subsequent live graph/manifest move mutation is not. |
| Pin zero-call telemetry | Resolved in outcome | Persisted values are stated; the concrete writer/KPI surface needs one more sentence. |
| Centralize summary derivation and migrate replay/CLI | Resolved | One pure helper feeds all four validation surfaces. |
| Keep `ParsedSummary` non-throwing | Resolved | Invalid parsed responses are explicitly covered through the real finally path. |
| Complete the North-Star commit scope | Resolved | Status ownership and Repair-stage deletion are now included. |

## Findings

### F1 — High: MOVED+CHANGED preflight passes, but graph ownership is never transferred

Task 1.4 correctly treats `ScanEntry.previous_path` as an allowed predecessor
(blueprint lines 146–168). That prevents the old source ID from being mistaken for a
different source during preflight. It does not complete the move.

The current mutation paths are split:

- manifest reconciliation handles a file entry with `action == "MOVED"` by popping
  the predecessor, installing the new source ID, and writing a tombstone
  (`orchestrator/manifest_writer.py:193-255`);
- graph reconciliation transfers SUPPORTS and marks the old Source moved **only**
  when a MOVED op is present in `scan_dict.to_reconcile`
  (`kdb_graph/intake.py:63-75`, `174-229`);
- `_commit_source()` builds its per-source scan with `to_reconcile: []`
  (`orchestrator/kdb_orchestrate.py:90-133`);
- `_commit_source_failure()` also uses `to_reconcile: []` while still applying the
  MOVED file entry to the manifest (lines 361–389); and
- the later reconcile queue skips every MOVED op whose destination appeared in
  `scan.to_compile`, regardless of whether compile succeeded or failed (lines
  872–878).

Consequences:

- **success:** the new Source gains current SUPPORTS, while the old Source remains
  active with its old SUPPORTS. The next reservation check sees multiple owners;
- **preflight/model failure:** the manifest moves to the new source and records its
  failure, but the graph retains only the old owner. The next run sees a guaranteed
  manifest/graph disagreement and fails closed again; and
- **rebuild:** the archived full scan still contains the MOVED op, so replay can
  produce a different graph from the live path.

**Required correction:** define MOVED reconciliation as a lifecycle mutation that
lands exactly once regardless of compile outcome. A coherent implementation is:

1. pass the source's MOVED op into the successful `_commit_source` graph transaction
   so Phase 1 creates the destination Source, Phase 2 transfers/marks the predecessor,
   and Phase 3 replaces destination SUPPORTS with the newly compiled pages;
2. on any pre-commit compile failure, run a move-aware graph/manifest reconciliation
   that transfers the prior graph state while preserving the new source's failure
   record and `last_compiled_hash`;
3. track whether the move was handled instead of skipping solely because the
   destination was in `to_compile`; and
4. prove success and failure both converge on the next run.

Add system tests for MOVED+CHANGED success, preflight failure, and model/schema
failure. Each must assert: predecessor Source marked moved, predecessor SUPPORTS
removed, destination owns the correct SUPPORTS, manifest ownership agrees, and live
graph equals rebuild.

### F2 — High: canonicalization can invalidate exact summary identity after the only exact gate

The semantic gate enforces `expected_summary_slug` before canonicalization
(blueprint lines 169–173). Task 2.1's post-canonical gate enforces only “exactly one
summary page” (lines 227–240), not that its slug still equals the source-derived
expected value.

The current canonicalizer explicitly renames an alias singleton to its ledger target
(`compiler/canonicalize.py:378-392`). Therefore a ledger entry such as
`summary-source-a -> summary-source-b` can produce this flow:

1. model emits the correct `summary-source-a`; semantic validation passes;
2. collision preflight checked only `summary-source-a` and passes;
3. canonicalization renames the summary page to `summary-source-b`; and
4. the count-only post gate passes, after which page_writer/manifest/graph can
   overwrite or co-own another source's summary.

This violates D-115-11's executable filename rule and bypasses the new reservation
index. Summary/non-summary cross-type rejection does not catch a summary-to-summary
alias.

**Required correction:** after `canonicalize.run()`, rerun both parts of the summary
invariant for each source: exactly one summary **and** its slug equals
`expected_summary_slug(source_id)`. A summary alias that changes that slug should
raise the typed `CanonicalizationError` and quarantine before any write. Add explicit
summary→summary alias and summary→concept alias tests. This keeps per-source summary
identity out of the generic ontology-alias mechanism without reopening canonical
collision policy for concept/article pages.

### F3 — Medium: pass-case preflight tests cannot all assert zero model calls

Task 1.4 lists same-source recompile and MOVED+CHANGED as passing cases, then says all
listed cases assert zero model calls (blueprint lines 166–168). A successful
`compile_source` preflight must proceed to the model; zero calls would mean the source
never compiles.

Split the assertions:

- rejecting preflights (distinct owner, ambiguous graph, manifest/graph mismatch,
  invalid stem) assert zero calls and the zero-call telemetry record;
- allowed cases (same-source and allowed MOVED predecessor) assert preflight success
  and exactly one normal model call in an integration test.

Pure reservation-index unit tests may of course run without a model, but they do not
replace the `compile_source` call-through tests.

### F4 — Medium: assign the graph ownership check to the graph query API

Task 1.4 says `compile_source` performs the graph consistency check but does not name
the integration boundary. The compiler already reads graph state through
`kdb_graph.queries` (`compiler/context_loader.py`), and the North Star calls that the
single graph query API. Raw Cypher added to `compiler.py` would create a second,
unreviewed graph contract.

Add a small read helper to `kdb_graph.queries`, such as
`summary_supporting_source_ids(conn, slug) -> list[str]`, and define ownership as the
set of Source IDs supporting an Entity whose page type is `summary`. The compiler
compares that result with the reservation index and allowed predecessor. Tests should
pin missing Entity, unowned Entity, one owner, multiple owners, moved owner, and a
non-summary Entity occupying the expected slug.

### F5 — Medium: zero-call telemetry names values but not its writer or KPI semantics

v1.3 specifies the right persisted values (blueprint lines 160–165), but preflight
now returns from `compile_source` before `compile_one`, whose `finally` block is the
current response-stat writer. The plan should name the new write surface so “exactly
one record” is mechanically enforceable—for example, a shared compiler helper used
by both the preflight return and `compile_one`'s finally block.

Also pin KPI behavior. The current quarantine metrics are per-token; a zero-token
preflight record increments the numerator but not the denominator, and a run with
only zero-call Pass-2 quarantines yields `quarantine_rate_pass2=None`
(`compiler/kpi/processing.py:40-47`, `115-126`). Preserve the scored formula for
cohort comparability and add an explicit diagnostic such as
`preflight_quarantine_count`, or document the intended alternative. Tests should
cover a mixed normal/zero-call run and an all-zero-call Pass-2 run.

## Non-blocking cleanup

Removing `PageIntent.status` and `.confidence` leaves the common-only aliases
`PageStatus` and `Confidence` unused (`common/types.py:20-21`). Delete them if the
final scoped search confirms no remaining consumer. This is an orphan cleanup, not a
reason to hold Proceed by itself.

## Required v1.4 amendments

- [ ] Complete MOVED+CHANGED graph/manifest reconciliation on success and every
      failure path; prove next-run convergence and live=rebuild.
- [ ] Revalidate exact summary slug after canonicalization and reject summary alias
      rewrites before persistence.
- [ ] Correct zero-call assertions for preflight pass cases.
- [ ] Route graph ownership reads through a named `kdb_graph.queries` helper.
- [ ] Name the zero-call telemetry writer and pin KPI/diagnostic behavior.

## What is ready

- Prompt provenance, package data, and clean-commit cohort sequencing.
- The four-field model response and removal of every deprecated aggregate projection.
- Dual-mode historical/new validation and mixed-journal replay.
- Body-authority canonical links and Gate-2 graph-side edge derivation.
- Finding-driven Repair-stage deletion while keeping slug coercion.
- Best-effort response telemetry migration.
- Logical Entity-confidence deprecation and snapshot v7 isolation.
- North-Star-first documentation scope and explicit commit approval gates.

## Final verdict

Revise before Proceed, but only around move lifecycle and post-canonical summary
identity. v1.3 resolves the previous review faithfully. The two high findings are
state-convergence defects that happy-path contract tests will not catch unless they
are designed now; the three medium items make those fixes executable and observable.
After these amendments, the blueprint should be ready to ratify without another
broad review cycle.
