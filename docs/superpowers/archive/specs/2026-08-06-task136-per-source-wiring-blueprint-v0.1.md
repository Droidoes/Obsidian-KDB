# Task #136 Blueprint v0.1 — Per-Source Iterative LINKS_TO Wiring + Per-Source Deprecation

**Date:** 2026-08-06 · **Status:** SHIPPED 2026-08-07 (suite 3208 green; P3 sandbox gates (a)(b)(c) passed — see TASKS.md #136 resolution) · **Architecture:** ratified 2026-08-06 (Joseph — Option A)
**Supersedes:** #94 (patch options a/b/c rejected — the strand is deleted by construction)

---

## 1. Problem

The C1 deferral (Task #91) wires every page→page `LINKS_TO` edge in **one end-of-run batch**: per-source commits run `apply_compile_result(..., wire_links=False, detect_deprecations=False)`; `_finalize` then calls the standalone `wire_links(combined)` over `accumulated_crs` held in RAM, followed by the whole-graph `detect_deprecations()` scan.

Two structural failures:

1. **#94 — the strand.** `_finalize` is gated on `abort is None`. A mid-run abort leaves every committed source with entities + SUPPORTS but **zero LINKS_TO**; a warm re-run skips them as unchanged, so those links are never created. Recovery = `--cold` redo.
2. **Scaling.** Memory during a run is O(the run's entire edge set) — every link of every source sits in `accumulated_crs` until the end — and nothing is wired until everything survives. Unacceptable at vault scale (~1,600 sources) and absurd at the 2M-source horizon (Joseph's case).

The deferral existed for one reason: a page from source #3 can link to a page minted by source #30 — at #3's commit the target doesn't exist yet. The batch "solves" this by waiting. Option A solves it by **remembering**.

## 2. Ratified architecture (Option A — drain-as-you-go)

Each per-source commit transaction:

1. **Upserts** the source's page entities (as today).
2. **Wires** each page's outgoing links whose targets exist in the graph (backward references + intra-source references — pass 1 upserts all of the source's pages first, so intra-source links never pend).
3. **Pends** links whose targets don't exist: upsert into a durable `PendingLink` node table — inside the same Kuzu txn, so pendings are crash-safe by construction.
4. **Drains**: each newly upserted page may satisfy earlier pendings keyed on its slug — create those `LINKS_TO` edges, delete the pending rows.
5. **Deprecation diff**: pages that lost their last SUPPORTS in this commit flip `deprecated` in the same txn; newly re-supported deprecated pages revive.

End-of-run `wire_links` and the whole-graph `detect_deprecations()` scan are **deleted**. Finalize shrinks to frontmatter convergence + stats + journal archive.

**#94 is deleted, not patched:** committed sources are always fully wired (their forward references sit durably in the ledger), an abort loses nothing, and the next run's commits keep draining — no special resume path.

**Alternatives rejected:** (B) backward-wiring + end-of-run sweep for forward links — keeps a shrunken strand and in-memory accumulation; (C) checkpointed batch every K sources — a patch, still O(run) memory between checkpoints.

## 3. Detailed design

### 3.1 Schema — `kdb_graph/schema.py`

New node table, created in the same DDL pass as the existing tables (init is idempotent; fresh + rebuilt graphs get it; existing graphs get it via the init path on open — verify `IF NOT EXISTS` semantics and mirror the `Entity` pattern):

```
CREATE NODE TABLE PendingLink (
    link_id      STRING PRIMARY KEY,   -- source_slug + "|" + target_slug  (slugs exclude "|" by charset)
    source_slug  STRING,               -- the page carrying the unresolved outgoing link
    target_slug  STRING,               -- the not-yet-existent target
    first_run_id STRING,
    last_run_id  STRING,
    created_at   STRING,
    updated_at   STRING
)
```

Notes: `PendingLink` is a node table because Kuzu rel tables require both endpoints to exist — the target doesn't, that's the point. Kuzu secondary indexes are not assumed; drain lookup is `WHERE target_slug = $slug` (scan over the pending set — see §7 risk R1).

### 3.2 Intake — `kdb_graph/intake.py`

**`_replace_outgoing_links` (extend).** Per target, after the existing drop-outgoing step:
- `MATCH (b:Entity {slug: $target})` exists → `CREATE (a)-[:LINKS_TO …]->(b)` (today's path).
- Target absent → upsert pending: `MERGE (p:PendingLink {link_id: $id}) ON CREATE SET first_run_id/created_at … SET last_run_id=$run_id, updated_at=$ts`. Count `result.links_pended += 1` on create.

**`_upsert_entity` (extend) — drain.** After the entity upsert, drain pendings on its slug:
```
MATCH (p:PendingLink {target_slug: $slug}) …
for each: MATCH (a:Entity {slug: p.source_slug}), (b:Entity {slug: $slug})
          CREATE (a)-[:LINKS_TO {run_id, created_at}]->(b)
          DELETE p
result.links_drained += <count>
```
Incoming edges to the page are never touched by `_replace_outgoing_links` (which drops only *outgoing* edges), so drain-created edges are stable. Drain runs for every upserted page; for already-existing pages it is a no-op (pendings on an existing slug cannot exist — see §4.3).

**Per-source deprecation (new `_deprecations_for_source`, replaces Phase 4 in the per-source path).** `_replace_supports_for_source` currently drops all of the source's SUPPORTS then recreates per current pages. Change:
1. Before the drop: `MATCH (s:Source {source_id})-[:SUPPORTS]->(p:Entity) RETURN p.slug` → `pre_set`.
2. After recreate: `lost = pre_set − emitted_slugs`.
3. For each `lost` slug that is canonical (`canonical_id IS NULL`) and now has zero SUPPORTS: `SET status='deprecated'`; collect `(slug, page_type)` into `result.deprecations_detected` (same shape as today).
4. Revivals: emitted slugs whose entity is `status='deprecated'` → `SET status='active'` (symmetric revive at the re-supporter's commit).

This is a per-source set-diff instead of an O(graph) scan — cheaper per commit, exact, and immune to cross-source interference. Alias entities remain ineligible for deprecation (they never carry SUPPORTS).

**Deleted:** standalone `wire_links()` (intake.py:832) and `detect_deprecations()` (intake.py:808), the `wire_links`/`detect_deprecations` flag parameters on `apply_compile_result` (single behavior remains: wired + deprecation-diff per source), and their `graphdb.py` wrappers.

**Ordering within the commit txn (unchanged skeleton):** Phase 1 source refresh → Phase 2 reconcile → Phase 3 pass 1 upsert entities (+drain per page) → pass 2 wire/pend outgoing + SUPPORTS + ingest state → domains → aliases → Phase 4 per-source deprecation diff. Pass-1-before-pass-2 means intra-source links resolve without pendings.

### 3.3 Reconcile GC — `_handle_source_deleted`

Source deletion DETACH-DELETEs its pages (existing #130 erasure). Extend: delete `PendingLink` rows whose `source_slug` is among the erased pages (their carrier is gone). Pendings keyed on *target* slugs of erased pages **stay** — a later source may legitimately emit that slug (this is the re-emit revival path, now for links too).

### 3.4 Orchestrator — `orchestrator/kdb_orchestrate.py`

- `_commit_source`: call `apply_compile_result` with defaults (wired + per-source deprecation). Accumulate per-source `IntakeResult` counts into run totals: `links_wired += edges_upserted + links_drained`, `links_pended`, `deprecated += deprecations_detected` (page slugs for file marking below).
- Frontmatter: newly deprecated pages' files marked at commit (`page_writer.mark_deprecated` on the commit's lost set). Revive needs no file work — re-support ⇒ re-emit ⇒ fresh active frontmatter (page_writer owns the file on re-emit).
- `_finalize` slimmed to: frontmatter convergence fixpoint (retained — idempotent crash/dry-run heal + `deprecated_pages_total` stat, both ratified under #130/#135), `compile_result.json` archive, summary stats. New stats: `links_pended_open` (end-of-run `MATCH (p:PendingLink) RETURN COUNT(p)`), `links_drained`.
- Abort story: nothing correctness-critical sits behind `abort is None` anymore. The finalize gate disappears for wiring/deprecation; `manifest_post_graph` remains the only run_fatal abort (unchanged), and its consequence is now bookkeeping-only, recoverable by warm resume + reconcile.

### 3.5 Replay — `kdb_graph/adapters/obsidian_runs.py` (#132 simplification)

- Delete the `_finalize_progress` gating and the derive calls to the (now deleted) standalone `wire_links`/`detect_deprecations`.
- Replay applies each source's `apply_compile_result` **with defaults, in journal order** — the same deterministic sequence as live ⇒ the same edges, pendings, and deprecations ⇒ live ≡ replay preserved by the per-source path itself.
- **Old 2.3 journals** (written live with `wire_links=False` + batch finalize): replaying them under the new path yields the same *final* graph — batch wiring and incremental wiring compute the same complete edge set once all entities exist; end-state deprecation status is a function of final SUPPORTS (transient mid-replay flips settle identically). `finalize_progress` in old journals is ignored (parsed, unused). Pinned by the verifier test in §6.

### 3.6 Metrics

Run-summary stats only (v1): `links_wired` (wired + drained), `links_pended_open`, `links_drained`, `deprecated*`. The durable ledger *improves* the dangling-link story: today's silent-skip dangling links become durable, queryable `PendingLink` rows — KPI wiring of a `dangling_link_rate` from the ledger is a later, optional step.

## 4. Correctness arguments

1. **Atomicity.** Pendings, drains, edges, and deprecation flips all live inside the existing per-source commit txn — β self-containment preserved; a crash rolls back the whole source, never half a drain.
2. **Idempotency.** Re-committing a source re-runs drop+recreate for its outgoing edges (unchanged semantics); pendings MERGE on `link_id` (no duplicates); drained pendings are deleted in-txn so a drain fires once.
3. **Drain safety.** Pendings on slug X exist only while no `Entity X` exists (creation of X drains them in the same txn). Page erasure (`DETACH DELETE`) removes the entity *and* its incident edges, after which pendings on X may legitimately re-form — consistent.
4. **No duplicate edges.** `_replace_outgoing_links` drops before creating; drain-created incoming edges are recreated only via a pending row, which is deleted on drain.
5. **Deprecation exactness.** The lost-set diff touches only entities whose SUPPORTS changed in this commit; canonical-only; revive symmetric. End state after any source sequence equals the whole-graph scan's verdict on final SUPPORTS.
6. **Replay equivalence.** Live and replay run the same `apply_compile_result` sequence; determinism of order ⇒ identical graph. Old journals: §3.5.

## 5. Implementation plan

**P1 — kdb_graph core.**
Schema table; `_replace_outgoing_links` pend; `_upsert_entity` drain; `_deprecations_for_source`; `_handle_source_deleted` pending-GC; delete standalone passes + flags + `graphdb.py` wrappers; `IntakeResult` gains `links_pended` / `links_drained`.
*Gate: new + existing kdb_graph tests green.*

**P2 — orchestrator + adapter.**
`_commit_source` defaults + per-commit file marking + count accumulation; `_finalize` slimmed (convergence fixpoint, archive, stats); `obsidian_runs.py` simplification; journal `finalize_progress` ignored (parse-tolerated).
*Gate: orchestrator + adapter + replay/verifier tests green; full suite green.*

**P3 — verification + docs.**
Sandbox: (a) cold run ≡ replay graph diff (verifier); (b) abort-injection — SIGKILL mid-run on the sandbox vault, warm resume, assert pendings drained + complete edge set vs an uninterrupted control run; (c) warm-run deprecation behavior (drop/re-emit). Docs: TASKS.md closure, CODEBASE_OVERVIEW milestone + architecture paragraph (finalize `wire_links` → per-source), AGENTS.md pipeline sketch, JOURNEY entry.
*Gate: (a) exact graph equality, (b) edge-set equality with control, (c) no zombie/churn regression vs #129 baseline.*

No panel review: success is machine-checkable (suite + live≡replay diff + abort-injection equality), per the #132 precedent.

## 6. TDD test plan (write first)

P1 (`kdb_graph/tests/`):
- `test_pending_created_for_unresolved_target` — wire with absent target ⇒ edge absent, `PendingLink` row present with correct fields.
- `test_drain_on_target_arrival` — later upsert of the target slug ⇒ edge created, pending deleted, `links_drained` counted.
- `test_pending_merge_idempotent` — same source re-pends same target ⇒ one row, `last_run_id` bumped.
- `test_no_duplicate_edges_on_recommit` — re-commit source ⇒ edge count unchanged.
- `test_per_source_deprecation_diff` — recompile dropping a page ⇒ deprecated in-txn; sibling pages untouched.
- `test_revive_on_resupport_at_commit` — second source re-supports a deprecated page ⇒ active in its commit txn.
- `test_pending_gc_on_source_delete` — DELETED source ⇒ its pages' outgoing pendings removed; target-keyed pendings of others survive.
- `test_aliases_not_deprecated` (retain existing coverage against the new diff path).

P2 (`orchestrator/tests/`, `kdb_graph/tests/`):
- `test_commit_accumulates_wiring_counts` — links_wired/pended/drained roll up.
- `test_finalize_has_no_wiring_role` — finalize stats carry accumulated counts; deleting accumulated_crs wiring changes nothing (structural).
- `test_replay_equals_live_without_finalize_derive` — 2.3 journal with `finalize_progress` replays to graph equality under the new path (regression for §3.5).
- `test_abort_mid_run_resume_drains` (integration) — kill between commits; resume; final edge set == uninterrupted control.

P3: sandbox gates as in §5.

## 7. Risks & open decisions

- **R1 — drain lookup is a scan** over `PendingLink` (no Kuzu secondary index assumed). Pending sets are expected to be small (hundreds–thousands; bounded by outstanding forward references, not corpus size). Pinned by a synthetic stress test (10k pendings, drain latency budget). If profiling ever hurts, options: in-graph index evolution or a slim sidecar index — deferred until measured.
- **R2 — transient deprecation window** (source A drops page P, source B re-supports later in the run): between the two commits, active-only readers don't see P. Accepted (ratified per-source semantics); self-heals at B's commit; was previously hidden by end-of-run batching. The #129 stewardship makes genuine drops rarer, but the window is inherent to per-source marking.
- **R3 — `accumulated_crs` still accumulates for the journal archive** (#132 replay payloads). Not worsened by this task; at 2M scale this wants sharded per-source journals — noted as the *next* scaling task, out of scope here.
- **D1 — dangling pendings aging policy**: none in v1 (rows are tiny; they are the dangling-link metric made durable). Decide an aging/GC window only if counts ever matter.

## 8. Out of scope

KPI wiring of pending/dangling metrics; PendingLink aging/GC window; streaming/sharded journal archives (R3); MCP exposure of pending counts; any prompt changes (the model contract — link to context pages — is unchanged).

## 9. Implementation deviations & notes (recorded 2026-08-07, P1/P2)

1. **Selective pending-GC on rewire (addition to §3.2).** `_replace_outgoing_links` also deletes *stale* PendingLink rows keyed on the rewiring page's `source_slug` whose `target_slug` is NOT in the current target-set (`WHERE NOT p.target_slug IN $targets`). The blueprint text didn't spell this out; it is required for batch-equivalence — the deleted batch pass only ever produced the current target-set's edges, so a stale pending from an earlier compile (target since dropped from the body) would otherwise drain into an edge the batch would never create. Rows for still-present targets stay untouched (MERGE-idempotency preserved). Pinned by `test_stale_pending_cleared_on_rewire`.
2. **Drain fires only on canonical entity upsert** (`_upsert_entity`); the alias upsert path does not drain. Post-canonicalization, body wikilinks are remapped to canonical slugs before intake, so a pending keyed on an alias form indicates a pre-canonicalize bug — draining it would wire to the alias row, violating canonical-only LINKS_TO. Deliberate corner, documented in the intake docstring.
3. **`links_pended` counts creates only** — a per-target existence pre-check precedes the MERGE, so a re-pend bumps `last_run_id` without inflating the counter.
4. **Schema migration mechanics** — PendingLink DDL appended LAST in `NODE_TABLE_DDL` (positional migrations depend on declaration order); `_migrate_2_4_to_2_5` registered; `rebuilder._DROP_ORDER` gained `PendingLink` (rebuild drops + recreates; surfaced by verifier tests — "PendingLink already exists in catalog").
5. **`finalize_progress` vocabulary** — now `"none"` / `"complete"`, audit-only; its *presence* still selects the 2.3 two-phase replay path, its *value* is ignored (§3.5 holds). The adapter pops it with a `_MISSING` sentinel rather than a default.
6. **`graphdb.stats()`** gained `pending_links`; the run summary's `links_pended_open` reads the live count at finalize.
7. **Orchestrator `manifest_post_graph` path** also accumulates wiring counts and marks deprecated files — the graph commit happened, so totals and frontmatter must reflect it even though the manifest write failed.
8. **R1 stress test** shipped at n=2,000 pendings with a 120s budget (`test_drain_stress_pendings_at_scale`) instead of 10k — drain latency is far under budget at 2k; scaling further is profiler bait, not information.
