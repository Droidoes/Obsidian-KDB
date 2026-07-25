# Task #115 — Pass-2 contract revision blueprint v1.5: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.5  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Two functional blockers and two execution corrections remain before Proceed

## Executive assessment

v1.5 makes the requested architecture substantially more concrete. The occupancy
object is the correct graph-query boundary; missing, unowned, and cross-type states
are no longer conflated. The MOVED table now exposes the real conductor branches,
matched replay pairs are required, and observability is assigned to the durability
point. The prior post-canonical and zero-call amendments remain sound.

Two state transitions still cannot execute as written:

1. the manifest-post-graph β residual is supposed to recover using an in-memory
   handled marker, but the run abort destroys that marker; on restart the preflight
   table sees an unexplained manifest/graph disagreement and rejects before repair;
2. the NOISE path removes destination SUPPORTS live, while its specified empty
   compile-result + MOVED scan replays by transferring those SUPPORTS and has no
   instruction that removes them.

Two smaller contradictions should be resolved in the same narrow pass. No broad
Task #115 redesign is needed.

## Prior-review resolution

| v1.4-review amendment | v1.5 status | Assessment |
|---|---|---|
| Complete MOVED outcome/state table | Partial | All branches are listed, but β restart and limit behavior are internally inconsistent. |
| Add renamed-stem next-run convergence | Partial | Test is named; the reservation truth table does not yet define the reverse-index transition it must allow. |
| Persist matched failure/move replay pairs | Partial | Move-only failure is representable; NOISE live state is not reproduced by that pair. |
| Use occupancy-aware graph state | Resolved in shape | `SummarySlugState` is the right API; cross-store transitional/β rows need refinement. |
| Preserve exactly-once observability | Partial | Correct for one process; the β-retry instruction cannot survive a restart. |

## Findings

### F1 — High: the β residual cannot be recovered by an in-memory handled key

The manifest-post-graph row says the graph move has committed, the run aborts when
the manifest write fails, and retry “completes manifest only”; it also says a flag
prevents double application (blueprint lines 336 and 355–360). The only specified
flag is an in-memory `(from_path, to_path)` key. A run-fatal return or process restart
loses it.

The next invocation then observes this concrete state for a rename whose stem
changed:

- manifest: predecessor still owns its old summary slug;
- graph: destination Source already owns the newly compiled expected summary;
- scan: MOVED predecessor → destination is rediscovered; and
- handled set: empty, because it belongs to the new process.

Task 1.4 has no PASS row for this known β residual. “Owner == this source” requires a
consistent manifest; “owner == allowed predecessor” has the wrong graph owner; and
the final row rejects unexplained manifest/graph disagreement (lines 164–173).
Therefore preflight rejects before the implementation can “complete manifest only.”
Reapplying the full graph transaction instead is not exactly-once either:
`_update_source_ingest_state()` increments `ingest_count` on every application
(`kdb_graph/intake.py:396-427`).

The named “transitional self” row also needs a precise cross-store definition. After
a pre-commit failed rename, the destination Source owns the **old** summary slug and
the expected new slug is absent. At the expected slug this looks like first compile;
the transition is visible only through the reservation index's reverse
`source_id -> old_slug` mapping. Saying “transitional self at expected slug” does not
describe that state.

**Required correction:** replace the graph-only truth table with a compact
cross-store table that includes both known transitions:

- **failed move:** destination is reverse-reserved to the old slug, expected slug is
  absent, and `last_compiled_hash` remains stale — permit compile, then replace old
  SUPPORTS;
- **β residual:** scan lineage names the predecessor, manifest is still pre-move,
  and graph destination already owns the expected slug from the failed commit —
  enter an explicit recovery path rather than ordinary preflight rejection.

Choose a restart-safe mechanism for β recovery: a durable pending-commit record with
enough material to finish the manifest, or a run-id/idempotency guard that makes full
reapplication genuinely idempotent, including `ingest_count` and events. An
in-memory marker alone cannot provide this contract. Add a fault-injection system
test that fails the manifest write after graph commit, creates a fresh orchestrator
invocation, and proves convergence with no second model call, count increment, move
event, or SUPPORTS duplication.

### F2 — High: the NOISE live mutation and replay mutation diverge

The NOISE row correctly says a `no_graph_db` destination must not retain the
predecessor's SUPPORTS: live handling transfers and then retires them (blueprint line
333). Replay durability later specifies a fresh compile result with empty
`compiled_sources` paired with the original scan (lines 346–353).

That pair cannot reproduce the live outcome. `apply_compile_result()` processes the
MOVED op in Phase 2 and transfers predecessor SUPPORTS to the destination
(`kdb_graph/intake.py:65-75`, `_handle_source_moved()` at 174–229). With no
`compiled_sources` entry, Phase 3 never invokes `_replace_supports_for_source()` to
delete them (`81-90`, `347-393`). Rebuild therefore leaves the destination supporting
the old pages while live state has no SUPPORTS.

D-91-14's empty-compile precedent works for DELETED because DELETED itself carries
the retraction instruction. A bare MOVED op carries transfer semantics, not
noise/retraction semantics.

**Required correction:** make the noise disposition replay-visible. For example,
add a producer mutation/scan instruction that means “destination active/no_graph_db,
zero SUPPORTS” and implement it identically in live intake and the adapter, or choose
another existing payload shape that explicitly triggers destination SUPPORTS
replacement with an empty set. Do not rely on manifest state during graph rebuild.
The NOISE system test must rebuild through `ObsidianRunsAdapter` and compare Source
status/ingest state and SUPPORTS, not only node/edge counts.

### F3 — Medium: the `--limit` row contradicts the handled-key queue rule

The table says an unprocessed move receives no mutation this run and the reconcile
queue handles it on the next run (blueprint line 337). The observability section says
the queue skips according to whether the move is already in the handled set
(355–360). At the end of the current run, an unprocessed move is not handled, so that
rule causes the current reconcile queue to process it immediately—not next run.

Either behavior can be coherent:

- process it in the current reconcile queue as a move-only transition, persist the
  matched replay pair, and let the next run compile from transitional self; or
- deliberately defer it by tracking “not visited because of limit” separately from
  “handled,” leaving manifest and graph unchanged so scan rediscovers the move.

Pick one and make the table, queue predicate, counts/events, and two-run test agree.

### F4 — Medium: matched replay-pair durability needs the D-91-14 write protocol, not only a payload shape

v1.5 requires a pair and says adapter eligibility is defined, but it does not assign
the concrete writer, top-level compile journal, or crash-consistent order. The cited
D-91-14 precedent includes all three: sidecar first, manifest second, eligibility
journal last. The current orchestrator writes the baton compile result only from
`_finalize()` and only when at least one compiled source accumulated
(`orchestrator/kdb_orchestrate.py:895-909`; `_finalize()` lines 218–220); it does not
currently create the adapter's top-level `state/runs/<run_id>.json` compile event.

**Required correction:** name the archive helper and pin its write order and failure
semantics. At minimum: write the matched per-run sidecars atomically, apply the
manifest boundary as designed, then publish the eligibility journal last so rebuild
never discovers a partial pair. State whether move-only/all-failure events are
`success`, `replayable_payload`, and journal schema 2.2 (or require a version bump).
Test interruption after each write boundary, not merely the completed archive.

## Required v1.6 amendments

- [ ] Define restart-safe β-residual detection/recovery and its exact idempotency
      boundary; add a fresh-process fault-injection test.
- [ ] Define the failed-rename reverse-reservation transition explicitly rather
      than calling it ownership at the expected slug.
- [ ] Add a replay-visible NOISE disposition so live and adapter rebuild both end
      with zero destination SUPPORTS.
- [ ] Resolve whether limit-unvisited moves reconcile now or defer, and align the
      queue predicate and test.
- [ ] Pin the matched-pair writer, compile journal fields/version, crash-consistent
      ordering, and interruption tests.

## What is ready

- Prompt provenance, package data, clean-commit sequencing, and cohort gates.
- Four-field response contract, historical aggregate compatibility, and fixtures.
- Occupancy-aware slug-query type and rejection policy for unowned/cross-type state.
- Exact summary identity before and after canonicalization.
- Body-authority graph-edge derivation and Repair-stage deletion.
- Zero-call telemetry, KPI diagnostics, and call-through assertions.
- Logical Entity-confidence deprecation and snapshot-v7 isolation.
- Mainline MOVED success and pre-commit failure transfer semantics.

## Final verdict

Revise before Proceed. v1.5 is close and the remaining work is confined to the
MOVED/replay state machine: make β recovery durable across process boundaries, give
NOISE an explicit replay instruction, and remove the limit/archive ambiguities. Once
those are pinned, the blueprint should be implementable without reopening the
Pass-2 contract decisions.
