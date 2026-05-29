# Independent Senior Architect Review: Task #91 Plan 5+6 (`kdb-orchestrate` loop)
**Reviewer:** agy (Gemini 3.5 Flash High)
**Date:** 2026-05-29

---

## 1. Verdict

**`proceed-with-changes`**

The Plan 5+6 implementation blueprint is an exceptionally well-thought-out integration plan that successfully ties together the feeder-scanner-enricher-compiler-graph chain on a shared read-write connection. However, changes are required to address a critical batch-assumption edge-wiring trap in `apply_compile_result`, optimize the D-91-13 commit boundary to maximize self-healing, and close the crash-window gap in journaling.

---

## 2. Findings

### **Finding F-1: The Cross-Source `LINKS_TO` Edge-Skip Trap (Batch-Assumption Trap)**
*   **Dimension:** D3 (Integration Correctness / Batch Assumptions)
*   **Severity:** Critical
*   **Issue:** In `graphdb_kdb/ingestor.py`, Phase 3 of `apply_compile_result` uses a two-pass architecture designed with a batch assumption: pass 1 upserts every `Entity` node across all compiled sources in the batch, and pass 2 wires the `LINKS_TO` edges. Under the hood, `_replace_outgoing_links` silently skips edge creation if the target entity does not exist in the graph yet:
    ```python
    # ingestor.py:313
    # If a target slug doesn't yet exist as an Entity node, the CREATE is silently skipped
    ```
    By compiling and graph-syncing **per source** in a loop, if Source A (compiled first) contains an outgoing link to Entity B (which is defined in Source B, compiled second), the edge `A -[:LINKS_TO]-> B` will be **silently skipped and never created** because Entity B does not exist in the graph at the moment Source A's sync runs. Even when Source B is processed in the next iteration and Entity B is upserted, the skipped link from Source A is never re-evaluated or wired.
*   **Evidence:** `graphdb_kdb/ingestor.py:305-333` (`_replace_outgoing_links`).
*   **Recommendation:** This is a load-bearing batch-assumption trap. To resolve this without rewriting `ingestor.py` Cypher queries, the orchestrator should:
    *   Either automatically upsert "stub" Entity nodes (status='inactive', title=slug) during Phase 3 for any referenced outgoing link targets that do not exist,
    *   Or accumulate all compiled sources (`cr`s) in-memory during the loop and execute `apply_compile_result` exactly **once at the end in the finalize stage** using the full accumulated batch `cr` and `scan` dict. Note: This restores perfect batch semantics for graph-sync (meaning all entities are guaranteed to be upserted before any edges are wired), though it defers read-after-write visibility for N+1 context snapshots within the same run. If intra-run read-after-write is highly desired, stubs must be upserted.

### **Finding F-2: Optimizing the D-91-13 Commit Boundary for Maximum Self-Healing**
*   **Dimension:** D2 (Per-Source Commit Ordering)
*   **Severity:** High
*   **Issue:** The plan's proposed commit sequence inside `_commit_source` writes the manifest *before* executing the graph-sync:
    1. `patch_applier.apply(write=True)`
    2. `atomic_write_json(manifest_path, next_manifest)` (COMMIT BOUNDARY)
    3. `apply_compile_result(...)` (graph-sync)
    If `apply_compile_result` fails, the transaction is rolled back, but the manifest and wiki pages have already been committed. This creates a Case-(b) failure: the manifest is updated, but the live graph is stale. Recovery requires a manual `graphdb-kdb rebuild`.
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md` lines 79–84.
*   **Recommendation:** Move the manifest write **after** the graph-sync has successfully committed on the Kuzu connection:
    1. `patch_applier.apply(write=True)`
    2. `apply_compile_result(detect_orphans=False)` (Kuzu transaction successfully commits)
    3. `atomic_write_json(manifest_path, next_manifest)` (COMMIT BOUNDARY)
    Since Kuzu supports robust transaction commits and rollbacks, if the graph-sync fails, it rolls back cleanly and the manifest write is never executed. This converts a severe Case-(b) failure (requiring manual operator rebuild) into a clean Case-(a) failure (no manifest change, meaning the next orchestrator run will see the file hash mismatch, re-compile, and automatically self-heal the wiki and graph).

### **Finding F-3: Per-Source Sidecar Journal Directory (D1 Crash-Window Resolution)**
*   **Dimension:** D1 (Per-Source Journaling / Replayability)
*   **Severity:** Medium
*   **Issue:** Accumulating all per-source `cr`s in-memory and writing the journal and sidecar once at `_finalize` is a highly pragmatic trade-off. However, a crash mid-loop before `_finalize` leaves committed-but-not-yet-journaled sources. While the live graph has them, the run journal on disk will be completely missing, meaning a subsequent `graphdb-kdb rebuild` would lose those edits if the graph had to be replayed.
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md` Design Point 1 (lines 15–17).
*   **Recommendation:** Implement a lightweight **Per-Source Sidecar Journal Directory** to close the crash window without adding complex append machinery:
    1. In `_commit_source`, immediately after a successful manifest commit, atomically write a tiny individual JSON file containing `cs.to_dict()` and `aliases_emitted` to a temporary run directory: `state/runs/<run_id>/<source_hash>.json`.
    2. In `_finalize`, read all small JSON files in `state/runs/<run_id>/`, aggregate them into the final batch `compile_result.json` and the standard run journal, then delete the temporary per-source directory.
    This provides perfect crash-consistency and guarantees replayability even if the run is aborted mid-loop, requiring zero complex JSON appending or file locking.

### **Finding F-4: MOVED-and-CHANGED Double-Routing Conflict**
*   **Dimension:** D4 (Fail-fast / Resume / Idempotency)
*   **Severity:** Medium
*   **Issue:** A file that is both moved and edited (MOVED-and-CHANGED) will appear in both `scan.to_compile` (due to hash mismatch) and `scan.to_reconcile` (due to old-path removal). Under the current plan routing, it will trigger the compile queue path first, and then the reconcile path. If not carefully coordinated, the reconcile path's `_handle_source_deleted` (which tombstones the old path and drops its supports) might execute after or during compile, potentially clashing with the new path's SUPPORTS upsert.
*   **Evidence:** `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md` lines 127–129.
*   **Recommendation:** Explicitly route MOVED-and-CHANGED operations. The orchestrator should process reconcile MOVED operations *before* compile operations, transferring existing SUPPORTS to the new path first, so that the subsequent compile step on the new path cleanly overwrites them. Reconcile DELETED operations should remain at the end.

---

## 3. What is Sound and Spec-Faithful

The following design decisions in the capstone plan are exceptionally robust:

1.  **Shared Database Connection Lifecycle:** Opening one read-write `GraphDB` connection at the orchestrator entry and threading it through the entire loop is perfectly aligned with our Kuzu 0.11.3 auto-commit transaction findings. It completely solves read-after-write latency across sources.
2.  **Deferred Orphan Marking:** Deferring Phase-4 orphan marking and cleanup detaches to the global finalize stage is an elegant architectural optimization. It completely eliminates the redundant per-source global orphan scan and avoids transient-orphan context pollution during T2 snapshot loading.
3.  **Deterministic `force_noise` Overrides:** Integrating overrides inside the Pass-1 enrich stage ensures that Daily Notes and other blacklisted scopes are cleanly cataloged in the manifest as `metadata_only` and blocked from graph sync in an idempotent, self-healing fashion.
4.  **Sandbox Isolation Scheme:** Treating the test sandbox directory as its own `vault_root` is a robust isolation fix that prevents dry-run and test wiki pages from polluting production vaults.
