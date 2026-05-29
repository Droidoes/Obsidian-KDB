# C1 + F-ord Recommendation — Deepseek (2026-05-29)

## Decision 1 — C1 (cross-source LINKS_TO): **Option (b′) — Defer link-wiring to finalize, batch-wire**

### Why (b′)

**Live≡replay by construction.** The batch link-wire pass at finalize uses the exact same code path as batch replay — all entities exist, all `MATCH (a),(b) CREATE` patterns succeed. The live graph and the replay graph produce identical LINKS_TO edges for the same accumulated `compile_result`. No divergence.

**No stub management.** Option (a) requires creating inactive stubs, distinguishing "waiting for real source" from "genuinely dangling," and a finalize GC to clean un-promoted stubs. That's three new concerns (stub creation, stub promotion, stub GC) for one problem. Option (b′) adds one `wire_links=False` flag + one finalize pass — two changes, both narrow and testable. Mirrors the already-accepted `detect_orphans=False` deferral pattern (one flag, one deferred pass). Architectural symmetry.

**T3 degradation is bounded and acceptable.** Mid-loop, LINKS_TO edges from prior runs still exist (the graph keeps them). Only current-run cross-source edges are missing until finalize. T1 (SUPPORTS — per-source entities) and T2 (entity_search_keys → context loader) are unaffected — they anchor context on entity presence and search-key matches, not edges. T3 (neighbor expansion along LINKS_TO) is supplementary context; its mid-loop degradation means sources in the compile queue don't see each other's outgoing links, which is the same as the monolith's batch behavior (no source in a batch ever saw another source in the same batch via T3 either — because the monolith committed the whole batch at once). The per-source world is strictly better: at least SUPPORTS-based T1 context propagates immediately.

**The failure mode I'd most worry about:** finalize crashes *after* the batch link-wire begins but before it completes. In Kuzu, a partially-completed `BEGIN…COMMIT` block that crashes would ROLLBACK the whole link-wire pass. The finalize should wrap the batch link-wire in its own transaction so it's atomic. On re-run, all sources are UNCHANGED → skip compile → enter finalize → reload accumulated crs from per-source sidecars → retry batch link-wire. The link-wire pass is idempotent (`_replace_outgoing_links` does DROP+CREATE). The risk is a poison-page (one page's outgoing_links crashes the whole batch). Mitigation: the batch link-wire iterates pages and collects errors rather than failing the whole pass, or the fail-fast discipline applies (one bad page → abort → same state as pre-finalize; re-run after fix).

**Implementation sketch:**
```python
# apply_compile_result gains wire_links: bool = True
# Phase 3 pass 2: when wire_links=False, skip _replace_outgoing_links
# (keep _replace_supports_for_source, _update_source_ingest_state, _write_source_meta)

# Finalize:
def _finalize_link_wire(conn, accumulated_crs, run_id, now):
    conn.execute("BEGIN TRANSACTION")
    try:
        for cr in accumulated_crs:
            for cs in cr.get("compiled_sources", []):
                for page in cs.get("pages", []):
                    _replace_outgoing_links(conn, page, run_id, now, result)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
```

---

## Decision 2 — F-ord (commit ordering): **Option β — Graph-sync-first, revises D-91-13**

### Why β

**Eliminates case (b).** Under α, a post-manifest graph-sync failure leaves the system in a two-truth state: manifest+wiki say "committed," graph says "stale." The operator must fire `graphdb-kdb rebuild` manually. Under β, graph-sync happens first inside a Kuzu transaction — if it fails, the transaction rolls back cleanly, and no manifest is written. The source looks like it was never processed → self-healing on re-run. The entire case-(b) failure class disappears.

**The evidence that justifies revising D-91-13.** D-91-13 was ratified when:
1. Graph-sync was a batch operation at the end of a monolithic compile run (`kdb-compile` stages 1→10).
2. The single read-write connection model didn't exist yet — the planner opened its own read-only connection per batch.
3. Kuzu's clean ROLLBACK behavior on the shared connection wasn't empirically verified.

All three conditions have changed. Per-source graph-sync on a single read-write connection with verified Kuzu rollback is new evidence. D-91-13's case-(b) was a *necessary* concession given the batch world's constraints. In the per-source world on a verified connection, β is strictly safer.

**β honors D-91-13's intent *better* than α.** D-91-13's core intent was: "the sidecar is the replayable authority." Under α, a sidecar can exist while the graph is stale (case-b), meaning the sidecar is NOT authoritative — the graph disagrees with it. Under β, the sidecar is written only after graph-sync succeeds, so **sidecar exists → graph is consistent**. This is a stronger invariant, not a weaker one.

**The residual gap is bounded and already accepted.** Under β, the crash window is: graph-sync COMMIT succeeds, but sidecar write fails → graph has the mutation, sidecar doesn't. If the graph is subsequently lost, `graphdb-kdb rebuild` replays prior journals (which don't include this source) → the source's LINKS_TO edges are lost. BUT:
- The graph IS live (single-user, infrequent workload).
- Only one source's edges are at risk (per-source commit, not the whole run).
- This is the exact same double-fault class already accepted for the per-source-sidecar-vs-finalize journaling trade-off (F-jrnl in the review synthesis).

**The failure mode I'd most worry about:** a crash *during* graph-sync COMMIT (e.g., Kuzu crashes mid-COMMIT). Kuzu's atomicity guarantee means the COMMIT either completes or doesn't — there's no partial-COMMIT state. If the process dies between Kuzu receiving the COMMIT and the Python process observing success, the next run can't tell whether the COMMIT succeeded. But since `apply_compile_result` is idempotent (MERGE entities, DROP+CREATE SUPPORTS), re-running it is safe regardless. The source re-detected as NEW/CHANGED → re-compile → re-graph-sync → idempotent. The worst case is a duplicate `ingest_count` increment and `last_run_id` update on the Source node, which is cosmetic.

**What breaks under β that α handles?** Nothing. α's only advantage is "sidecar written before graph-sync → always replayable." But that advantage is illusory because case-(b) means the sidecar exists while the graph is wrong — the sidecar's replayability is useful only after a `rebuild`, which the operator must fire manually. With β, `rebuild` is needed only in the double-fault scenario. The operator's burden is strictly reduced.

---

## Combined commit sequence

### Per-source (inside the orchestrator loop)

```
1. patch_applier.apply(vault_root, compile_result=cr, last_scan=single_scan,
                       run_ctx=ctx, write=True)
   ── wiki pages written (atomic per-page via atomic_io)

2. apply_compile_result(cr, single_scan, ctx.run_id, conn=conn,
                        detect_orphans=False, wire_links=False)
   ── Kuzu transaction: entities + SUPPORTS + aliases + source meta
   ── ROLLBACK on failure → clean (verified); return to caller as failure
   ── COMMIT on success → entities + SUPPORTS visible to next source's context read

3. atomic_write_json(manifest_path, next_manifest)
   ── ← COMMIT BOUNDARY (D-91-13 case a|b distinction collapses here)
   ── After this write, the source is "committed" for resume purposes

4. write per-source sidecar: state/sidecars/<run_id>/<source_id>.json
   ── Contains the source's cr dict (for finalize concatenation + rebuild replay)
   ── Best-effort; failure → log warning, continue (graph + manifest are authoritative)

5. accumulate cr into in-memory list for finalize batch link-wire
```

**Why this ordering works:**
- Steps 1-2 are pre-boundary: failure anywhere → manifest untouched → re-run self-heals.
- Step 2 COMMIT is the practical boundary for graph state — after it, read-after-write is live.
- Step 3 is the formal COMMIT BOUNDARY — after it, the source won't be re-processed on re-run (post-embed hash in manifest matches on-disk file).
- Step 4 is best-effort replayability — missing sidecar means rebuild loses this source's edges (double-fault).
- Step 5 is in-memory accumulation for finalize.

**Case analysis:**
| Failure point | Manifest | Graph | Wiki | Re-run behavior |
|---|---|---|---|---|
| During step 1 | untouched | untouched | partial pages | Source re-detected → re-compile → overwrites wiki |
| During step 2 (ROLLBACK) | untouched | rolled back | pages on disk | Source re-detected → re-compile → idempotent graph-sync |
| After step 2, before step 3 | untouched | committed | pages on disk | Source re-detected → re-compile → idempotent graph-sync |
| After step 3, before step 4 | committed | committed | pages written | Source UNCHANGED → skipped → sidecar missing for rebuild (double-fault) |
| After step 4 | committed | committed | pages written | Source UNCHANGED → skipped → full replayability |

### Finalize (after the per-source loop)

```
6. detect_orphans(conn, ctx.run_id)
   ── Single global pass: mark orphan_candidate / revive re-supported entities
   ── Own transaction; ROLLBACK on failure → exit (no clean state harmed)

7. batch-wire ALL LINKS_TO from accumulated crs:
   for cr in accumulated_crs:
       for cs in cr["compiled_sources"]:
           for page in cs["pages"]:
               _replace_outgoing_links(conn, page, run_id, now, result)
   ── Single Kuzu transaction; all entities exist → no silent skips
   ── ROLLBACK on failure → exit; re-run retries idempotently (drop+recreate)
   ── After COMMIT: live graph ≡ batch replay graph (live≡replay restored)

8. kdb-clean orphans:
   report = reap_orphans_from_graph(conn)
   apply_cleanup(report, ctx.run_id, conn=conn)
   build_cleanup_artifacts(report, run_id, ...)  # m1 fix — cleanup journal
   ── DETACH DELETEs orphan_candidate entities with zero SUPPORTS

9. write combined compile_result.json + run journal + last_orchestrate.json
   ── Accumulated crs merged into one batch compile_result (aliases_emitted dedup'd)
   ── Run journal with per-source stats
   ── last_orchestrate.json summary
```

### Why finalize ordering matters

- Step 6 *before* step 7: orphan status is computed on the post-all-sources graph (entities+supports complete), matching the deferred-marking decision. If step 7 ran first, newly-wired LINKS_TO could affect context but orphan status isn't affected by LINKS_TO (it's SUPPORTS-based only).
- Step 7 *before* step 8: cleanup must run after all links are wired — otherwise a genuinely-orphaned entity that has only inbound LINKS_TO and zero SUPPORTS wouldn't be reaped (it was marked orphan_candidate in step 6 but not reaped until step 8; link-wire in step 7 doesn't affect orphan status).
- Step 8 *before* step 9: the cleanup journal must exist before the run journal references it.

---

## Anything we missed

**1. The `wire_links=False` flag scope.** Currently `apply_compile_result`'s Phase 3 pass 2 does four things per compiled_source: `_replace_outgoing_links` → `_replace_supports_for_source` → `_update_source_ingest_state` → `_write_source_meta`. With `wire_links=False`, only `_replace_outgoing_links` is skipped. The other three fire normally. This means SUPPORTS edges, ingest_state, and source_meta are committed per-source (read-after-write for T1/T2). Verified correct.

**2. Rebuild replay of the finalize batch link-wire.** Rebuild replays per-run `compile_result` journals through `apply_compile_result` (rebuilder.py:151-152: `adapter.apply(mutation, scan, run_id, graph.conn)`). The combined `compile_result.json` written at finalize contains ALL compiled_sources from the run. Rebuild replays it in ONE `apply_compile_result` call → all entities upserted before all links wired → complete. The per-source sidecars are NOT replayed individually (they're intermediate artifacts). The combined `compile_result.json` is the single replayable artifact. **live≡replay holds.**

**3. The `kdb-clean orphans` integration needs a cleanup journal (m1 from review synthesis).** The finalize step 8 must call `build_cleanup_artifacts` + write the `retraction.json` sidecar + cleanup journal to `state/runs/` so rebuild replays the cleanup alongside the compile event. Without this, rebuild would resurrect reaped entities. This is a mechanical fix, not a design fork — Codex caught it.

**4. Per-source sidecar write should not gate the commit.** The sidecar write at step 4 is best-effort. If it fails, the source is still committed (manifest + graph are authoritative). Log the failure; continue. The combined `compile_result.json` at finalize provides the authoritative batch replay artifact.

**5. What if finalize itself fails (crash)?** On re-run, all sources are UNCHANGED → skip compile loop → enter finalize. Finalize must detect whether it has pending work:
   - Load per-source sidecars for this run_id (or a `run_state.json` marker).
   - If sidecars exist, reconstruct accumulated crs and resume from step 6.
   - If no sidecars and no pending state, finalize is a no-op (just write `last_orchestrate.json` with zero counts).

   This is a small addition: write a `state/runs/<run_id>_state.json` with `{"phase": "finalize", "source_count": N}` before entering finalize. On orchestrator startup, check for an incomplete prior run → resume at finalize.

**6. Option (b′) + β interaction with MOVED/DELETED.** The reconcile queue (DELETED + MOVED) is processed after the compile queue (spec line 123-128). Deleted sources lose their SUPPORTS and LINKS_TO — but with `wire_links=False`, LINKS_TO were never wired for current-run sources, so only prior-run edges exist. `_handle_source_deleted` drops SUPPORTS edges; `_handle_source_moved` transfers SUPPORTS. LINKS_TO edges from MOVED/DELETED sources are on entity nodes, not source nodes — they persist regardless. The finalize batch link-wire overwrites them with the accumulated crs' current state. This is correct — the final link-wire pass is authoritative.
