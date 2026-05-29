# Task 91 C1 + F-ord Recommendation — Codex

## Decision 1 — C1 Pick

**Pick: a better option than b′: incremental prefix batch-rewire.** If implementation must choose only from the named options, choose **b′** over stubs, but the cleaner version is:

1. Per-source `apply_compile_result(..., wire_links=False, detect_orphans=False)` upserts Source, Entity, SUPPORTS, aliases/domains.
2. After each successful source graph-sync, run a deterministic `rewire_links(accumulated_crs_so_far)` pass over every committed source in the current orchestrator run.
3. Finalize runs the same rewire once more as a cheap belt-and-suspenders pass before `detect_orphans()`.

This gives the live graph the same semantics as "batch replay of the committed prefix." Source B's compile immediately makes A→B wireable if A was already committed, so source C can see the A→B T3 topology. It avoids stub entities, avoids masking dangling-link defects, and still gives final live≡replay.

I would not choose stub-upsert. It changes the graph vocabulary by creating entities the model did not emit, and the inactive-stub edge can leak into projections: `_batch_outgoing_links()` returns target slugs without filtering target status. Even if T3 seed expansion filters active entities, prompt projection can still carry an inactive target slug. Stub GC can fix final state, but that is more machinery than simply rewiring known emitted links against known entities.

**Failure mode I worry about most:** a rewire failure after per-source entity/support sync. Put entity/support upsert plus prefix rewire in one Kuzu transaction for the current source step. Rollback then restores the prior prefix graph cleanly.

## Decision 2 — F-ord Pick

**Pick: β, graph-sync-first, but make the real commit boundary graph+journal, not manifest.**

D-91-13's intent was not "manifest is sacred"; it was "do not mark a source processed unless there is either a clean graph mutation or a replay path." The facts changed after D-91-13: Kuzu rollback is verified clean, and `apply_compile_result` is idempotent per source. That makes graph-sync-first the simpler operational model:

- graph-sync failure rolls back and the manifest remains untouched;
- next run re-detects via hash mismatch and retries;
- the case-(b) state "manifest says done, graph stale" disappears.

β honors the replayability intent **if** replay material is written immediately after graph success and before manifest advancement. The manifest is then only the source eligibility pointer; GraphDB plus sidecar/journal are the ontology authority.

What β handles worse than α: a crash after graph success but before manifest write leaves graph ahead of manifest. That is acceptable only if the graph mutation is journaled before the manifest is advanced, and the next run treats the manifest mismatch as a retry. The retry is idempotent. This is less operator-hostile than α's manifest-committed/graph-stale case requiring manual rebuild.

## Recommended Combined Commit Sequence

For a signal source:

1. `enrich_one()` embeds Pass-1 frontmatter and returns body + post-embed hash/mtime/size.
2. `compile_source()` returns one-source `cr`.
3. `patch_applier.apply()` writes wiki pages from `cr` and the post-embed scan metadata.
4. Prepare sidecar payloads for the one-source `cr` and single-source scan.
5. In one Kuzu transaction:
   - `apply_compile_result(cr, single_scan, conn, detect_orphans=False, wire_links=False)`
   - `rewire_links(accumulated_crs + [cr], conn)`
6. Write replayable per-source sidecar + journal/commit marker for that graph mutation.
7. Write manifest with the post-embed hash, `last_compiled_hash`, and `pipeline_id`.
8. Add `cr` to the in-memory accumulated list.

Finalize:

1. Run `rewire_links(all_accumulated_crs, conn)` once more.
2. Run `detect_orphans(conn, run_id)`.
3. Run `kdb-clean` orphan cleanup through replayable cleanup artifacts.
4. Write `last_orchestrate.json`.

For noise sources, no graph step: embed/enrich, then manifest `metadata_only` with `last_compiled_hash=post_embed_hash`.

## Anything Missed

The link rewire pass must be a first-class graph operation, not hidden inside rebuild-only code. It needs tests for:

- A emits `outgoing_links=["b"]`, B is compiled later, and A→B exists before C compiles.
- A emits a truly dangling `b`; after finalize there is no stub and no A→B edge.
- Live graph after orchestrate equals rebuild from the emitted sidecars.

Also, if graph+journal-before-manifest is adopted, `last_orchestrate.json` should distinguish `manifest_failed_after_graph_commit` from ordinary pre-graph failures. It is self-healing, but it is not the same failure class operationally.
