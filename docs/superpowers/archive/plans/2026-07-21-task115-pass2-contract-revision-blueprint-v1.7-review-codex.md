# Task #115 — Pass-2 contract revision blueprint v1.7: Codex review and staging recommendation

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.7  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Technical verdict on v1.7:** R11 amendments are incorporated, but the full plan should not Proceed as one task  
**Staging recommendation:** Choose Kimi K3's Option 2 — carve the reservation/MOVED/durability subsystem into a follow-up paired with #94

## Executive assessment

v1.7 faithfully incorporates the three R11 amendments:

- the write-ahead record now distinguishes intent from observed graph commit,
  carries deterministic recovery material, remains armed through replay-journal
  publication, and has a five-state recovery table;
- NOISE is represented by a typed Python-owned `source_dispositions[]` channel
  rather than an invalid zero-page compiled source; and
- journal v2.3 and historical adapter compatibility are pinned before
  implementation.

That closes the specific R11 defects. It also confirms the scope problem Kimi K3
identified. Tasks 1.4-preflight and 2.5 are no longer implementation details of a
Pass-2 contract revision. Together they form a source-lifecycle transaction and
recovery subsystem spanning compiler, orchestrator, manifest, GraphDB, replay
archives, journal versions, startup recovery, and fault injection.

This is exactly the territory already represented by blocker #94: interrupted-run
correctness, replay material, and convergence across persistent stores. Shipping it
inside #115 would couple a mature contract change to a new durability architecture
designed before the real-vault preflight. The project North Star also currently says
“no two-phase commits, no cross-file transactions” and favors cheap, recoverable
insurance (`docs/CODEBASE_OVERVIEW.md:71`). v1.7's write-ahead protocol may prove to
be the right exception, but that is a first-class architectural decision—not a
hidden prerequisite for removing six LLM fields.

## Technical review of v1.7

### R11 resolution status

| R11 amendment | v1.7 status | Assessment |
|---|---|---|
| Fully specified write-ahead record and recovery table | Resolved for the known β states | Record content, observed-state classification, and clear-after-journal rule are explicit. |
| Typed replay-visible NOISE disposition | Resolved in contract shape | `source_dispositions[]` is correctly separated from model-authored compiled sources. |
| Persisted version decision | Resolved | Journal 2.3 and adapter historical support are pinned. |

### F1 — High for Option 1: NOISE → signal reactivation remains outside the state machine

The new NOISE disposition clears destination SUPPORTS and leaves the Source active
with `ingest_state=no_graph_db` (blueprint lines 392–404). The collision preflight
rejects an existing summary Entity with zero supporting sources as an unowned
collision (lines 169–178).

The plan does not define what happens when that same source later changes and Pass 1
classifies it as signal again:

1. its previous summary Entity may still exist with zero SUPPORTS after the NOISE
   disposition;
2. the manifest may still carry the prior `summary_slug` unless the noise transition
   explicitly clears it (`_commit_noise_source()` currently changes run state and
   hashes but does not clear summary metadata at
   `orchestrator/kdb_orchestrate.py:316-334`); and
3. preflight can classify the expected slug as unowned or manifest/graph-disagreed
   and reject the source before it can reclaim its own prior summary.

Immediate orphan cleanup might remove the Entity, but v1.7 does not make that the
reactivation contract, and shared pages cannot be assumed removable. This is not a
reason for an R12 patch inside #115; it is evidence that lifecycle dispositions,
reservation ownership, and reactivation need one complete design covering
NEW/CHANGED/MOVED/DELETED/signal/noise—not another MOVED-only extension.

### F2 — Medium for Option 1: the total durable write order and journal values remain implicit

The plan separately states:

- write-ahead record before graph transaction;
- replay sidecars atomically;
- graph/manifest β ordering;
- manifest boundary;
- eligibility journal last; and
- pending cleanup after the journal.

It never presents the one total order that composes those statements. For the full
Option-1 design, the executable sequence should be pinned as one list, including
where wiki page writes occur and what is cleaned after rollback. Likewise journal
2.3 says event kinds have “exact `success`/`replayable_payload` semantics,” but does
not show the values for `compiled_move`, `move_only_failure`, `all_failure`, and
`noise` (blueprint lines 406–417).

These are straightforward in a dedicated durability blueprint; continuing to add
them here would further prove the carve.

## Scope decision

### Option 1 — Proceed on full v1.7

**Benefit:** collision safety, move convergence, replay durability, and recovery
land immediately as one integrated system.

**Cost/risk:** Gate 2 becomes the dominant project, introduces a write-ahead
transaction protocol and journal v2.3, overlaps #94, and still needs broader
lifecycle design such as NOISE→signal reactivation. It also requires an explicit
North-Star exception to the current simplicity rule before implementation.

**Assessment:** technically defensible only after another dedicated design pass;
not the right boundary for #115.

### Option 2 — Carve reservation/MOVED/durability from #115

**Benefit:** restores #115 to the already-ratified contract objective; preserves the
clean Phase-0 provenance experiment and comparison cohort; avoids coupling model
contract evaluation to a new state/recovery subsystem; lets the durability design
use real-vault evidence and resolve #94 once rather than twice.

**Accepted temporary behavior:** cross-source same-basename summary collisions keep
today's last-writer-wins/co-ownership behavior. This is existing behavior, not a new
regression introduced by the contract carve. The exact summary-slug semantic gate
still catches model non-compliance; it simply does not establish global reservation
authority yet.

**Assessment:** recommended.

### Option 3 — Keep a partial preflight but exempt MOVED/lifecycle cases

For completeness, a middle path could reject ordinary NEW/CHANGED collisions while
bypassing preflight for MOVED, NOISE, or disagreement states.

**Assessment:** reject. It creates two ownership policies, makes safety depend on
scanner classification, and leaves precisely the transition ambiguity that caused
R8–R11. It saves less work than it appears to and produces a harder follow-up.

## Exact carve for v1.8

### Keep in Task #115

- Phase 0 prompt relocation, package-data smoke, prompt version, prompt SHA, and
  clean baseline cohort.
- `expected_summary_slug(source_id)` as one pure derivation helper.
- Model-response semantic gate on every attempt: exactly one summary and exact
  source-derived slug.
- Post-canonicalization repetition of the same exact invariant.
- Four-field `PageIntent`, aggregate field removals, `compilation_notes`, and
  `ParsedSummary` migration.
- Dual-mode historical/new aggregate validation and replay/CLI `source_id`
  migration.
- Body-authority canonicalization and graph-owned wikilink→LINKS_TO derivation,
  including legacy `outgoing_links` fallback.
- Repair-stage deletion, fixture migration, parity corpus, confidence deprecation,
  snapshot v7, and the comparison cohort.

### Remove from Task #115

- `SummaryReservationIndex` and all manifest/graph ownership comparison.
- `summary_slug_state()` / `SummarySlugState` and its occupancy truth tables.
- Pre-call collision rejection, its special zero-call telemetry writer, and
  `preflight_quarantine_count`.
- All cross-store transitional-self and β-residual paths.
- Task 2.5 in full: MOVED outcome table, handled keys, move-only commits,
  `source_dispositions[]`, write-ahead records, startup recovery, journal 2.3, and
  lifecycle replay-pair publication.
- MOVED-specific Gate-2 tests and risks. Preserve the v1.7 text in the follow-up
  design seed rather than deleting the learned work.

### Documentation changes required by the carve

- North-Star update for #115 should describe only the contract, stage, body-link,
  status, prompt, and confidence changes—not a new MOVED/WAL architecture.
- Add an explicit #115 non-goal: global summary-slug reservation and source-lifecycle
  convergence remain current behavior until the follow-up.
- Update the Task #115 ledger narrative to name the accepted temporary collision
  behavior and link the follow-up task.
- Keep #94 marked as a pre-production blocker. The carve must not be read as
  permission for a production vault rollout before #94/follow-up closes.

## Recommended staged path

### Stage 1 — Ratify the carve

Produce v1.8 as the contract-only blueprint above. File the lifecycle/durability
follow-up in the task ledger with #94 as a paired dependency and link v1.7 as its
design seed. No implementation begins until Joseph confirms the carve.

### Stage 2 — Provenance baseline

Execute Phase 0 only, commit with approval, and fire the two-model baseline from the
clean commit. This preserves D-115-13's causal attribution before prompt/schema
changes.

### Stage 3 — Contract + graph derivation

Implement the descoped Phases 1–2 as one reviewed contract commit:

- response schema/prompt/exemplar/types;
- semantic and post-canonical exact-summary gates;
- aggregate migration and historical compatibility;
- body-owned links and graph derivation; and
- Repair-stage deletion.

Gate on the focused contract, canonicalization, graph-link, replay, and full suites.

### Stage 4 — Confidence + parity

Land logical confidence deprecation/snapshot v7, then the cross-boundary parity and
mixed-journal system tests at their existing gates.

### Stage 5 — Comparison cohort and #115 closure

Fire the comparison cohort from the clean Gate-4 commit. Compare prompt stamps,
quarantine/retry/recovery, and explained canonical-link deltas. Close #115 only
after Joseph's sign-off.

### Stage 6 — Data-ground the durability follow-up

During the OneNote/real-vault preflight, collect read-only evidence before choosing
the recovery architecture:

- duplicate filename stems within each pipeline scope;
- existing manifest tombstones/move frequency;
- signal↔noise reclassification cases;
- all-quarantined and interrupted-run artifact shapes; and
- current live-vs-rebuild divergence reproductions for #94 and MOVED.

A simple duplicate-stem inventory is also a practical temporary guard before either
cohort: if the cohort corpus has no duplicate stems, deferring global reservation
does not expose that corpus to the known collision class.

### Stage 7 — One lifecycle/recovery task before WS3 production

Design the follow-up around the full source lifecycle, not “MOVED fixes” alone. Its
scope should jointly resolve:

- #94 interrupted-run/finalize correctness;
- global summary reservation and occupancy policy;
- NEW/CHANGED/MOVED/DELETED plus signal/noise/reactivation transitions;
- per-run replay material and adapter journal evolution;
- live==rebuild invariants; and
- whether the right architecture is v1.7's WAL, immutable per-source commit bundles,
  or a simpler recovery model justified by real-vault data.

The follow-up is a pre-production gate for WS3. v1.7's four rounds of design work
become its starting evidence, not discarded effort.

## Final verdict

Do not Proceed on v1.7 as one implementation plan. Choose Option 2 and produce a
descoped v1.8. The contract work is mature and causally testable now; the
reservation/MOVED/replay machinery is a distinct durability subsystem with a wider
lifecycle boundary and an existing natural partner in #94. Splitting now is not
deferral by exhaustion—it is the architecture becoming clear enough to draw the
correct task boundary.
