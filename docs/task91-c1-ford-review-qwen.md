# C1 + F-ord Recommendation — Qwen CLI (qwen3.7-max)

**Reviewer:** Qwen CLI / qwen3.7-max  
**Date:** 2026-05-27  
**Guardrail compliance:** Single review file; no repo files modified.

---

## Decision 1 (C1): **Option (b′) — defer link-wiring to finalize batch pass**

### Pick: (b′)

Defer `LINKS_TO` edge creation to a finalize batch pass. Per-source `apply_compile_result` upserts entities + SUPPORTS only (`wire_links=False`, mirroring the existing `detect_orphans=False` deferral). Finalize runs one batch `LINKS_TO` wiring pass over accumulated `cr`'s with every entity present.

### Reasoning

1. **live≡replay by construction.** This is the strongest possible invariant — the live graph and the replay graph are structurally identical. No divergence, no verifier false-positives from the #73 Phase-G live≡replay check. The alternative (stub-upsert) introduces a class of entities (inactive stubs) that exist in the live graph but not in batch replay, creating a permanent divergence unless a finalize stub-GC pass is added.

2. **Mirrors the existing deferral pattern.** `detect_orphans=False` already defers Phase 4 orphan-marking to finalize — for the same structural reason (per-source execution can't see cross-source state). `wire_links=False` is the symmetric deferral for link-wiring. This is consistent architecture, not a special case. Two deferrals of the same kind (cross-source state requires batch visibility) → same solution shape.

3. **T3 incompleteness mid-loop is a secondary signal.** T1 (source-supported entities) and T2 (Pass-1 `entity_search_keys`) anchor context correctly throughout the loop. T3 (neighbor expansion via `LINKS_TO`) enriches context but is not load-bearing for variant prevention. The brief acknowledges this: "T1 and T2 still anchor per-source; the full graph (incl. T3 edges) is complete at finalize." Context quality is degraded for sources compiled mid-loop (missing some T3 neighbors) but not broken.

4. **Stub-upsert (a) has compounding failure modes:**
   - **Genuinely dangling links** (B never defined by any source) create permanent inactive stubs. A finalize stub-GC pass is required to clean these — but how does it distinguish "stub for a source that failed to compile" (should be cleaned) from "stub for a source not yet compiled in this run" (should be kept for next run)? The GC logic needs to know the run's source set — coupling finalize to scan state.
   - **Stub promotion race:** if Source B fails to compile (fail-fast aborts the run), the stub for Entity B stays inactive forever. Next run: Source B is UNCHANGED (hash match) → skipped. The stub is never promoted. The link A→B exists but points to an inactive entity. This is a worse state than "no link" — it's a link to a ghost.
   - **Masks the dangling-link signal.** The validator is designed to surface when the LLM emits links to non-existent entities. Stub-upsert swallows this signal silently — the link "succeeds" by creating a stub, hiding the LLM's hallucination from the operator.

### Failure mode I'd worry about

**Finalize crashes before link-wiring completes.** The per-source commits have entities + SUPPORTS in the graph but no `LINKS_TO`. The graph is in a degraded-but-not-broken state: T1 and T2 context work; T3 returns empty. Recovery: `graphdb-kdb rebuild` replays from per-source sidecars in batch mode → complete graph with all links. Or: a standalone `kdb-orchestrate --finalize-links` command re-runs just the finalize link-wire pass (idempotent — drops and recreates all `LINKS_TO` edges from accumulated cr's). For v1, `rebuild` is sufficient; the standalone command is v2 machinery.

---

## Decision 2 (F-ord): **Option β — graph-sync-first**

### Pick: β

Reverse the D-91-13 commit boundary: graph-sync runs **before** manifest-write. A graph-sync failure rolls back cleanly (verified Kuzu `BEGIN/ROLLBACK` is leak-free) → manifest never written → case-(a) self-heal. Manifest-write + sidecar-write happen only after successful graph-sync. **Eliminates case-(b).**

### Reasoning

1. **Eliminates case-(b) entirely.** The failure taxonomy collapses from two cases to one: "all pre-commit failures self-heal on re-run." This is a major simplification — no "committed-but-graph-stale" state, no manual `graphdb-kdb rebuild` remediation path to document, no run-summary field distinguishing case-(a) from case-(b).

2. **Honors D-91-13's *intent* better than α.** The intent behind D-91-13 is **sidecar-as-replayable-authority**: when a sidecar exists, the graph is guaranteed to have the mutation, so rebuild produces the correct result. α weakens this — a sidecar can exist while the graph is stale (case-b). β makes the invariant strict: sidecar exists → manifest written → graph-sync succeeded → graph has the mutation. The replayable-authority guarantee is *stronger* under β.

3. **Kuzu rollback is verified clean + `apply_compile_result` is idempotent.** These two facts (both post-date D-91-13's ratification) change the calculus:
   - Clean rollback means a graph-sync failure leaves no partial state — the shared connection is usable for the next source (or the next run).
   - Idempotency (drop+recreate SUPPORTS/links/entities) means re-syncing a source that was rolled back is safe — no duplicate edges, no stale state.
   
   D-91-13 was ratified before these properties were empirically verified. The new evidence justifies revision.

4. **Manifest-write failure after graph-sync is self-healing.** If manifest-write fails (disk full, permissions, etc.) but graph-sync succeeded: the source is in the graph but not in the manifest. Next run: manifest has old hash → source detected as CHANGED → re-enrich → re-compile → re-graph-sync. The redundant LLM call is the cost; `apply_compile_result` idempotency makes re-sync safe. For single-user infrequent workload, one extra LLM call on a manifest-write failure is negligible.

5. **Revising a ratified decision is justified here.** D-91-13 was a Codex critical catch against the *monolith's* batch model, where graph-sync happened at batch-end and a failure meant the whole batch's graph mutations were lost. In the per-source model with a shared rw connection and verified rollback, the structural conditions that made case-(b) load-bearing no longer apply. The revision is not capricious — it's driven by new architectural facts.

### Failure mode I'd worry about

**Crash between graph-sync commit and sidecar-write, combined with graph loss.** This is the bounded one-source double-fault: the graph has the source's mutation (committed), but the sidecar doesn't exist yet. If the graph is then lost (disk corruption), rebuild can't replay this source. Self-healing: next run detects hash mismatch (manifest has old hash), re-compiles, re-syncs, writes sidecar. The window is one source, one run, and recovery is automatic. This is the same risk class already accepted for per-source journaling (the "crash mid-loop before finalize" gap from the Plan 5+6 review) — bounded, single-user, self-healing.

### What breaks under β that α handles?

Nothing breaks. The only "regression" is that case-(b) no longer exists as a distinct failure mode — which is the point. α's advantage (conservative, keeps ratified decision) is not a technical advantage; it's inertia. The technical case for β is clean.

---

## Recommended combined commit sequence

Given C1=(b′) and F-ord=β:

### Per-source (inside the loop):
```
1. apply-wiki pages (build_page_patches + write, stage 8)
2. graph-sync: apply_compile_result(cr, single-source scan, conn,
       wire_links=False,        ← (b′): defer LINKS_TO
       detect_orphans=False)    ← existing deferral
   [Kuzu BEGIN → entities+supports → COMMIT; rollback clean on failure]
3. manifest write (post-embed hash)     ← COMMIT BOUNDARY (revised)
4. sidecar write (per-source append)    ← replayable authority
```

### Finalize (after successful loop):
```
5. link-wire batch pass (over accumulated cr's, all entities present)
   [idempotent: drop all LINKS_TO from this run, recreate from cr's]
6. detect_orphans(conn, run_id)          ← deferred Phase 4
7. kdb-clean orphans (reap orphan_candidate with zero support)
8. last_orchestrate.json (run summary)
```

### Ordering rationale:
- **Graph-sync before manifest** (β) — eliminates case-(b); manifest-write only happens when graph is consistent.
- **Sidecar after manifest** — when a sidecar exists, manifest+graph are guaranteed consistent. Stronger replayable-authority invariant than α.
- **Link-wire at finalize** (b′) — after all entities from all sources exist.
- **Link-wire before detect_orphans** — orphan detection needs the complete graph (including `LINKS_TO`) to make correct decisions. An entity with zero `SUPPORTS` but incoming `LINKS_TO` from other entities might be a link-target worth keeping.
- **Per-source sidecar append** (from F-1 in my Plan 5+6 review) — closes the journaling crash window. Each committed source has a replayable record independent of finalize.

### Recovery paths under this sequence:

| Failure point | State after failure | Recovery |
|---|---|---|
| apply-wiki fails | Nothing committed | Self-heal: re-run |
| graph-sync fails | Wiki written, no manifest, no graph | Self-heal: re-run (orphan wiki pages overwritten) |
| manifest-write fails | Wiki + graph committed, no manifest | Self-heal: re-run (hash mismatch → re-enrich → re-compile → re-sync; idempotent) |
| sidecar-write fails | Wiki + graph + manifest committed, no sidecar | Re-run: UNCHANGED (hash match) → skipped. Graph has the source. Only gap: rebuild can't replay this source if graph is also lost. Bounded one-source double-fault. |
| Crash before finalize | N sources fully committed (wiki+graph+manifest+sidecar), no LINKS_TO, no orphan-marking | `graphdb-kdb rebuild` replays from per-source sidecars → complete graph. Or: re-run + standalone link-wire command (v2). |

---

## What we might have missed

### 1. The `wire_links` flag needs to suppress LINKS_TO in both passes of Phase 3

`apply_compile_result`'s Phase 3 currently has two internal passes (ingestor.py:74-82): pass 1 upserts entities, pass 2 wires LINKS_TO + SUPPORTS + ingest-state. The `wire_links=False` flag must suppress the `_replace_outgoing_links` call in pass 2 while keeping `_replace_supports_for_source` and `_update_source_ingest_state`. This is a surgical change — one conditional guard around the `_replace_outgoing_links` call. Verify during implementation that no other Phase 3.5 or Phase 4 code depends on `LINKS_TO` existing.

### 2. The finalize link-wire pass needs its own `apply_compile_result` variant

The finalize link-wire pass needs to wire `LINKS_TO` edges for the accumulated `cr`'s *without* re-upserting entities or re-replacing SUPPORTS (those are already correct from per-source commits). Options:
- **(i)** Extract `_replace_outgoing_links` into a standalone function and call it directly from the orchestrator's finalize. Cleanest.
- **(ii)** Add a `wire_links_only=True` flag to `apply_compile_result` that skips phases 1, 2, 3.5, 4 and only runs the link-wiring portion of phase 3. More flags, less clean.
- **(iii)** Call `apply_compile_result` with the accumulated batch `cr` and `wire_links=True, detect_orphans=False` — but this re-upserts all entities and re-replaces all SUPPORTS (idempotent but redundant work).

Recommend **(i)**: extract a `wire_links(cr, conn, run_id, now)` function. The orchestrator accumulates cr's and calls it once at finalize.

### 3. Link-wire idempotency at finalize

The finalize link-wire pass must be **idempotent** — safe to re-run if a previous finalize crashed partway through. `_replace_outgoing_links` already drops all existing `LINKS_TO` from each source entity before recreating (ingestor.py:318-321: `DELETE r`), so re-running over the same cr's produces the same result. This is already safe.

### 4. D-91-13 revision documentation

If β is adopted, D-91-13 needs a formal amendment entry in the blueprint decision table. The revision rationale: "New architectural facts (single rw connection + verified Kuzu rollback + per-source idempotent graph-sync) post-date the original ratification. β eliminates case-(b), strengthening the sidecar-as-replayable-authority invariant." File as D-91-13-am1 or D-91-15.
