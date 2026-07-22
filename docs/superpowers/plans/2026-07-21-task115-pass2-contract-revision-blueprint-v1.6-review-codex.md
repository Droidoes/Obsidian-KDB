# Task #115 — Pass-2 contract revision blueprint v1.6: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.6  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Two functional blockers and one persisted-contract decision remain before Proceed

## Executive assessment

v1.6 resolves the renamed-stem transition and `--limit` contradiction cleanly. The
cross-store preflight now recognizes both ordinary ownership and the failed-move
reverse reservation; limit-unvisited moves intentionally reconcile in the current
queue; and the replay archive protocol has a named boundary and interruption tests.
The durable β intent is the right architectural direction.

Two details still make the proposed implementation unsafe:

1. a pending record written **before** the graph transaction is only an intent, not
   proof that the graph committed. Treating every uncleared record as a β residual
   can advance the manifest after a rollback or crash-before-graph. The record is
   also cleared after the manifest but before the eligibility journal, creating a
   crash window where live state is committed and replay permanently misses it;
2. the proposed NOISE entry `{source_id, pages: [], retired: true}` conflicts with
   the blueprint's ordinary compiled-source schema and exactly-one-summary invariant,
   and current intake would ignore `retired` and stamp `ingest_state=in_graph_db`.

The remaining persisted-format version must be chosen in the blueprint rather than
at implementation time. No other Task #115 area needs revision.

## Prior-review resolution

| v1.5-review amendment | v1.6 status | Assessment |
|---|---|---|
| Restart-safe β recovery | Partial | Durable intent added; recovery conflates intent with graph commit and clears before replay publication. |
| Define failed-rename reverse reservation | Resolved | The old-slug reverse mapping and stale compiled hash are explicit. |
| Add replay-visible NOISE disposition | Partial | Required semantics are right; the chosen shape is not valid or dispatchable under the surrounding aggregate contracts. |
| Align limit behavior and queue predicate | Resolved | Current-run move-only handling is now consistently specified and tested. |
| Pin archive writer and crash order | Partial | Writer/order are named; graph position, pending-record clearing, and persisted version remain unresolved. |

## Findings

### F1 — High: pending intent is neither graph-commit proof nor durable until replay publication

Task 2.5 says the pending record is written before the graph transaction and that any
uncleared record “IS the β state”; startup therefore completes the manifest and
clears the record (blueprint lines 355–365). Those statements are not equivalent.

The same uncleared intent exists after each of these distinct crash states:

1. intent persisted, crash before graph `BEGIN` — graph and manifest are both old;
2. graph transaction throws/rolls back — graph and manifest are both old;
3. graph commits, crash before manifest — real β residual;
4. manifest commits, crash before replay eligibility journal — graph and manifest
   are new, but rebuild cannot discover the sidecar pair; and
5. eligibility journal commits, crash before pending cleanup — every durable sink is
   already complete.

Blindly applying the manifest in states 1–2 creates graph/manifest divergence. The
specified clear point creates a separate data-loss window: the pending record is
cleared “after the manifest write” (line 360), while the eligibility journal is
published later (lines 378–390). A crash between those operations leaves no pending
recovery marker and no discoverable replay event, even though graph and manifest
have committed.

The record contents are also insufficiently precise. `source_id`, lineage, run ID,
and “expected effects” do not necessarily reconstruct the exact manifest state that
`build_source_state_update()` computed from the post-embed hash/mtime, compiled
source, and prior manifest (`orchestrator/kdb_orchestrate.py:90-151`). Recovery must
write the same intended manifest patch, not infer a nearby one from current state.

**Required correction:** define the pending record as a write-ahead transaction
record containing at least:

- prior-manifest fingerprint/precondition;
- exact target manifest or deterministic manifest patch and all inputs needed to
  reproduce it byte-for-byte;
- graph-effect fingerprint (destination Source, expected summary/SUPPORTS set,
  run ID and move lineage);
- replay sidecar paths/hashes and exact eligibility-journal payload; and
- transaction kind (`compiled_move`, `move_only_failure`, `noise`, or equivalent).

Startup recovery must classify observed durable state rather than assuming β:

| observed state | recovery |
|---|---|
| graph old, manifest old | discard/clear intent and retry normal work |
| graph target, manifest old | apply the recorded manifest target |
| graph target, manifest target, journal absent | publish the recorded eligibility journal |
| graph target, manifest target, journal present | clear pending record only |
| any partial/unrecognized combination | fail closed with a typed recovery error |

The pending record is cleared only after the eligibility journal is durable—not
after the manifest. Include fault injection after intent write, graph commit,
manifest write, eligibility-journal write, and pending cleanup, each with a fresh
process. The graph-rollback case must prove the manifest is not advanced.

### F2 — High: the proposed NOISE replay entry violates the aggregate contract and intake semantics

The NOISE row proposes a fresh compile-result entry
`{source_id, pages: [], retired: true}` so Phase 3 replaces destination SUPPORTS
with an empty set (blueprint line 349). As written, this is not an ordinary compiled
source:

- Task 2.2 requires every NEW compiled source to contain exactly one summary page
  with the source-derived slug (blueprint lines 289–300);
- the current aggregate schema requires a non-empty `pages` array and rejects
  unknown properties (`compiler/schemas/compile_result.schema.json:138-188`);
- `summary_page()` and the post-canonical per-source invariant intentionally fail on
  zero summaries; and
- intake ignores `retired`; after replacing SUPPORTS it calls
  `_update_source_ingest_state()`, whose default is `in_graph_db`, not
  `no_graph_db` (`kdb_graph/intake.py:396-427`).

Simply relaxing `pages.minItems` would weaken the compiled-output invariant and let
invalid LLM-derived aggregates masquerade as lifecycle instructions.

**Required correction:** make graph lifecycle dispositions a typed Python-owned
aggregate channel, distinct from ordinary model-compiled sources. Two coherent
options are:

1. add a top-level `source_dispositions[]` replay field with a closed shape such as
   `{source_id, disposition: "no_graph_db"}`, consumed by intake after MOVED
   reconciliation to clear destination SUPPORTS and stamp the intended Source
   ingest state; or
2. define `compiled_sources[]` as an explicit tagged union of normal compiled output
   and a Python-only lifecycle variant, then exempt only that tagged variant from
   summary/canonicalization/page-writer rules.

Whichever is chosen, pin schema validation, canonicalizer/page-writer exclusion,
manifest semantics, graph Source `status` and `ingest_state`, adapter compatibility,
and historical loading. Tests must prove the replay payload itself validates, writes
no wiki page, leaves the destination active with `ingest_state=no_graph_db`, and
leaves both predecessor and destination with zero SUPPORTS as intended.

### F3 — Medium: journal/payload versioning cannot remain an implementation-time decision

The archive section says implementation will decide whether move-only/all-failure
events fit journal schema 2.2 or require a version bump (blueprint lines 378–390).
That is a persisted compatibility decision and belongs before the North-Star gate,
especially now that v1.6 adds a new Python-owned noise mutation shape and a pending
transaction protocol.

Pin separately:

- compile-result schema version for the lifecycle-disposition field/variant;
- run-journal schema version and exact `success` / `replayable_payload` semantics for
  success, move-only failure, all-failure, and noise events; and
- the adapter's supported-version update plus historical 2.0/2.1/2.2 behavior.

A version may remain 2.2 only if its documented compatibility contract already
permits these additions and older readers cannot misinterpret them. Otherwise bump
it explicitly and test both old and new journals. “Decided at implementation” is too
late for a replay authority.

## Required v1.7 amendments

- [ ] Turn the pending intent into a fully specified write-ahead record with exact
      manifest, graph, sidecar, and journal expectations.
- [ ] Add the five-state startup recovery table and clear pending only after the
      eligibility journal is durable.
- [ ] Add crash/rollback tests at every boundary, including intent-with-no-graph and
      manifest-committed/journal-missing.
- [ ] Replace the untagged zero-page NOISE compiled source with a typed Python-owned
      lifecycle disposition and route it explicitly through validation and intake.
- [ ] Pin compile-result and run-journal versions plus adapter compatibility before
      implementation begins.

## What is ready

- Prompt provenance, packaging, version stamps, and cohort sequencing.
- Four-field model response and historical aggregate read compatibility.
- Occupancy-aware preflight, including unowned/cross-type rejection.
- Failed-rename reverse-reservation transition and next-run convergence intent.
- Exact summary identity before and after canonicalization.
- Body-authority graph derivation, Repair-stage deletion, and parity corpus.
- Zero-call telemetry and KPI semantics.
- Logical Entity-confidence deprecation and snapshot-v7 isolation.
- Mainline move, failure-transfer, limit, and exactly-once observability design.

## Final verdict

Revise before Proceed. v1.6 resolves the previous branch-coverage problems, but the
new durability machinery needs one more precision pass: recovery must distinguish
intent from committed graph state and remain armed until replay publication, while
NOISE needs a typed lifecycle channel rather than an invalid compiled source. After
those contracts and their versions are pinned, the blueprint should be ready for
ratification.
