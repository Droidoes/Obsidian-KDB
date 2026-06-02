# Panel Recommendation: Task #91 C1 + F-ord
**Reviewer:** agy (Gemini 3.5 Flash High)
**Date:** 2026-05-29

---

## 1. Decision 1 — C1 Pick & Recommendation

### **Recommended Pick: Option (b′) — Defer link-wiring to finalize, batch-wire**

### **Reasoning:**
Option (b′) is the only option that cleanly and robustly enforces **live ≡ replay invariance** by construction, without introducing graph state pollution, fragile cleanup passes, or masking validation alerts.

1.  **Preserves Declarative Graph Cleanliness:** Option (a) (Stub-upsert) requires the database to transiently store inactive "placeholder" nodes for entities that have not yet been defined by any source. If a link is genuinely dangling (i.e. the target entity is never defined by any source), these stubs will permanently clutter the graph as dead state unless we write a complex, custom Finalize Garbage Collection pass. 
2.  **No Masking of Validation Errors:** Option (a) masks dangling links at compile time, hiding the very signals the validator is built to catch. Option (b′) leaves dangling link detection entirely to the upstream validator.
3.  **Maintains Read-After-Write for Context Building:** Context loading (`graph_context_loader.py`) builds the T1 (supported) and T2 (slug-in-text) context snapshots based strictly on **Entity nodes** and **SUPPORTS edges**. Under Option (b′), both Entity nodes and `SUPPORTS` edges are committed *per-source* in the loop. Therefore, the N+1 source's context snapshot will see them in T1 and T2 immediately! The only deferred element is `LINKS_TO` (T3 neighbor expansion), which is an extremely minor and perfectly acceptable trade-off for a single-user system during the brief compilation window.
4.  **Simplicity over Imaginary Complexity:** Option (b′) utilizes simple, deterministic batch semantics during finalization, which is extremely easy to test and carries zero runtime state risks.

### **The Failure Mode to Worry About:**
If a crash occurs mid-loop before the finalize batch-wiring pass runs, the graph will have all newly compiled Entity nodes and `SUPPORTS` edges, but will be missing any *newly created* `LINKS_TO` edges for those sources. 
*   **Mitigation:** This failure mode is self-healing. Because the manifest write is also deferred or interrupted, the next run will detect the unfinished/hash-mismatched files, re-run them, and the finalization pass will execute cleanly on completion.

---

## 2. Decision 2 — F-ord Pick & Recommendation

### **Recommended Pick: Option β — Graph-sync-first**

### **Reasoning:**
Revising the ratified D-91-13 decision in favor of Option β is completely justified by the single read-write connection lifecycle and Kuzu 0.11.3 transaction rollback capabilities (which were not fully verified at the time D-91-13 was drafted).

1.  **Dramatically Shrunk Case-(b) Surface Area:** Under Option α (manifest-first), any database error or Kuzu transaction crash during the graph-sync stage leaves the manifest committed but the graph stale, forcing the operator to run a manual `rebuild`. Under Option β, because Kuzu transactions roll back cleanly, any database-level crash *prevents* the manifest and sidecar from being written. This collapses almost all operational errors into Case-(a) pre-commit failures, which **automatically self-heal** on the next run.
2.  **Pragmatic Risk Profile:** The residual risk of Option β—a crash occurring in the millisecond window *after* Kuzu commits but *before* the manifest is written, combined with a total graph loss—is a double-fault scenario of negligible probability on a single-user system.
3.  **Honors the "Replayability Authority" Spirit:** Option β ensures that a source is only committed to the manifest when both the wiki and the database have accepted the state. It treats the manifest as the absolute, atomic, final seal of completion.

---

## 3. Recommended Combined Commit Sequence

To cleanly compose both Option (b′) and Option β on the shared connection, I recommend the following exact commit sequence:

### **Part A: Per-Source Loop (`_commit_source`)**
For each source in the compile/delete queue:
1.  **Apply Wiki (Stage 8):** `patch_applier.apply(write=True)` writes the `.md` pages to `KDB/wiki/`. If this fails, no side effects are written to state or graph (Case a).
2.  **Kuzu Graph-Sync (Txn boundary):**
    *   Open Kuzu transaction (`BEGIN TRANSACTION`).
    *   Execute `apply_compile_result(cr, ..., detect_orphans=False, wire_links=False)`.
    *   This upserts the source, upserts the source's newly declared `Entity` nodes, and replaces its `SUPPORTS` edges. **No `LINKS_TO` edges are wired yet.**
    *   Commit Kuzu transaction.
    *   If this fails, Kuzu rolls back cleanly; manifest is untouched (Case a).
3.  **Manifest Commit (THE BOUNDARY):** Atomically write `manifest.json` on disk (stamping the post-embed hash and `pipeline_id`).
4.  **Per-Source Sidecar Journal:** Write `state/runs/<run_id>/<source_hash>.json` containing this source's `cr` slice.

### **Part B: Finalize Stage (`_finalize`)**
Runs once, globally, after a fully-successful loop:
1.  **Batch Link Wiring Pass (C1 Fix):**
    *   Execute `wire_all_links(conn, accumulated_crs)` (or a specialized batch `apply_compile_result(wire_links=True)` using Kuzu transactions) to wire `LINKS_TO` edges for all compiled sources. Since all entities are guaranteed to exist, no edges are skipped.
2.  **Batch Orphan Marking:** Run global `detect_orphans(conn, run_id)` to mark `orphan_candidate` states.
3.  **Batch Orphan Reap (Stage 10):** Run `apply_cleanup(reap_orphans_from_graph(conn), ...)` to delete orphaned entities.
4.  **Journal Compaction:** Read and compact all per-source sidecar files into the final run journal `state/runs/<run_id>.json` and write `last_orchestrate.json` summary.
5.  **Sidecar Clean:** Delete the temporary per-source sidecar directory.

---

## 4. Anything We Missed?

*   **Dry-Run Invariant:** Under `--dry-run`, the orchestrator should run the entire sequence with `write=False` and connection rollbacks. The final report should reflect which `LINKS_TO` edges *would* have been wired, ensuring the operator gets full simulation signal.
*   **Incremental Replays:** By using Option (b′), if a run fails mid-loop and is resumed, the finalization pass will cleanly process only the newly accumulated `cr`s, keeping the finalize stage fast and incremental.
