# Task #91 Plan 5+6 — Panel Review Synthesis (2026-05-29)

5-model panel (Codex · Deepseek · Grok · Gemini · Qwen). Reviews: `docs/task91-plan5-6-review-{codex,deepseek,grok,gemini,qwen}.md`. Verdicts: Codex **revise-before-execution**; the other four **proceed-with-changes**. Net: real revision needed — two clean must-fixes, one **critical design-reopening trap (4/5 MISSED it)**, and the journaling fork now resolves.

> **Model-diversity headline:** the cross-source `LINKS_TO` trap (C1) is a *verified critical* that **only Gemini caught** — Codex, Deepseek, Grok, AND Qwen all explicitly said "no batch assumptions found" in `apply_compile_result`. One independent model prevented a silently-incomplete graph in the live run. That single finding justifies the whole panel round.

## Convergence

| # | Finding | Who | Sev | Disposition |
|---|---|---|---|---|
| **M1** | `load_manifest_sources` drops `pipeline_id` → `scan_scope` filters ALL prior out → every run recompiles the whole pipeline (resume/idempotency broken) | **Codex + Deepseek + Qwen (3/5)** | **Critical** | **Fix now** — add `pipeline_id` to the reader's return dict + **stamp legacy records (no pipeline_id) with a default at startup** (Qwen) + regression test |
| **M2** | Noise sources re-enriched every run — `last_compiled_hash` never set for `metadata_only` (stays None → `current_hash != compiled_hash` → re-compile) | Codex + Deepseek | **High** | **Fix now** — noise commit sets `last_compiled_hash = post_embed_hash` |
| **C1** | **Cross-source `LINKS_TO` edge-skip** — per-source graph-sync wires a source's links before later sources' entities exist; missing-target edges silently skipped + never re-created → incomplete graph | **Gemini ONLY (4/5 missed it)**; verified vs ingestor.py:326-333 | **Critical** | **Design decision** (below) — reopens per-source-vs-batch |
| **m2** | Post-embed provenance incomplete — return `post_embed_mtime` (+ size) too; `patch_applier` stamps stale pre-embed `raw_mtime` into pages | **Codex + Qwen (2/5)** | Med→Fix | Fix — restat after embed, override `current_mtime` in `single_scan` |
| **F-jrnl** | Per-source journaling vs finalize-only | **per-source: Codex + Qwen + Gemini (+ Grok-F2) (3-4/5)** vs finalize: Deepseek (+ Grok-F1) | High | **RESOLVE → per-source sidecar** (Qwen's concrete shape: write `cr` per committed source to `state/sidecars/<run_id>/`, finalize concatenates) |
| **F-ord** | Commit ordering: graph-sync **before** manifest-write converts case-(b) into a self-healing case-(a) via Kuzu rollback | Gemini F-2 (1/5) | High | **Fork** — unique; revises ratified D-91-13. Scrutinize *with* C1 (both touch the commit sequence); don't adopt on one voice |
| **m1** | Finalize cleanup not replayable — needs cleanup journal + `retraction.json` (else rebuild resurrects reaped entities) | Codex | Med | Fix — use `build_cleanup_artifacts` |
| **m3** | `compile_source` doesn't wrap `reconcile.reconcile` → `ReconcileError` escapes the result contract | Codex | Med | Fix — wrap → `failure_stage="reconcile"` (a Plan-1 gap) |
| **m4** | Alias ledger: load `aliases.json` **once** before the loop (shared config), not per-source/empty | Deepseek F6 (corrected: shared, not empty) | Med | Fix — load once, thread in |
| **m5** | ~~MOVED+CHANGED ordering~~ | Gemini + Grok raised; **Qwen REFUTED** | — | **Non-issue** — Qwen traced `classify()`: MOVED+CHANGED decomposes to NEW(new path)+DELETED(old path) (rename pass matches by hash; changed hash → no MOVED match). compile-then-reconcile handles it; old-path DELETE doesn't touch new-path SUPPORTS. **Remove the deferred comment.** |
| **m6** | `to_compile` is alphabetical, not dependency-ordered (a source may miss a later-sorted source's pages in context) | Deepseek | Low | Accept v1 + document |

**Strong corroboration (all found sound):** per-source `build_source_state_update` safety (re-verified by 3), single-connection read-after-write, deferred orphan-marking, fail-fast/idempotency, produce-don't-write, sandbox isolation, accepted cross-source-wiki trade-off.

## The interacting forks (need decisions, deliberate together)

**C1 (cross-source LINKS_TO)** is the deep one — per-source graph-sync (which we need for read-after-write) conflicts with the batch "upsert-all-entities-then-wire-edges" that cross-source edges require. Options:
- **(a) Stub-upsert** missing link targets as `status='inactive'` Entities during graph-sync; the real source later upserts them active. Preserves per-source graph-sync + read-after-write; inactive stubs are excluded from context (`_load_active_entities` filters `status='active'`). Small foundation change.
- **(b) Finalize link-rewire pass** — after all sources compiled (all entities exist), re-wire LINKS_TO from accumulated crs. Completes the graph by end; cross-source edges missing *during* the loop (degraded T3 mid-run only).
- **(c) Accept + `kdb-audit`/rebuild reconciles** — weakest (graph incomplete until audit).
- **(d) Single apply at finalize** — restores full batch semantics BUT **defeats read-after-write** (no per-source graph mutations → variant proliferation). **Rejected** — kills the central design.

**F-ord + F-jrnl interact:** if graph-sync goes **before** manifest-write (Gemini F-2) and only-on-success do we write manifest+journal, then a graph-sync failure rolls back cleanly (Kuzu) → case-(a) self-heal, **eliminating case-(b)** — which also dissolves Codex's per-source-journaling-for-case-b requirement (no committed-but-graph-stale state to replay). This is elegant but **revises ratified D-91-13**. Per-source idempotency of `apply_compile_result` (drop+recreate) makes even manifest-write-failure-after-graph-sync self-heal on re-run.

## Recommendation

The panel resolved more than it opened. Clear path:

1. **Fold the convergent fixes into Plan 5+6 now** (mechanical, grounded): M1 (+legacy-record migration), M2, m1 (cleanup replayability), m2 (post-embed mtime/size), m3 (wrap reconcile in `compile_source` — a Plan-1 gap), m4 (load ledger once), m6 (document alphabetical ordering). **Remove** the MOVED+CHANGED deferred comment (m5 — Qwen refuted it).
2. **F-jrnl RESOLVED → per-source sidecar** (3-4/5 convergence): write each committed source's `cr` to `state/sidecars/<run_id>/` right after its manifest commit; finalize concatenates into the batch `compile_result.json` + run journal. Closes the crash-replayability gap; cheap. Fold in.
3. **The one genuine remaining decision: C1 (cross-source `LINKS_TO`).** Per-source graph-sync (needed for read-after-write) conflicts with the batch upsert-all-then-wire that cross-source edges require. Options:
   - **(a) stub-upsert** missing link targets as `status='inactive'` Entities (excluded from context via the active-filter; promoted when their real source compiles) — preserves read-after-write; small foundation change to `_replace_outgoing_links`. **My lean.**
   - **(b) finalize link-rewire** — re-wire all LINKS_TO after the loop; cross-source edges missing *during* the loop (degraded T3 mid-run only).
   - **(c) accept + `kdb-audit`/rebuild reconciles** — weakest (graph incomplete until audit).
   - **(d) single apply at finalize** — **REJECTED** (defeats read-after-write → variant proliferation).
   Weigh **F-ord (Gemini's graph-sync-before-manifest, 1/5)** here too — it's in the same commit sequence and would self-heal case-(b), but it revises ratified D-91-13, so it needs scrutiny, not adoption-on-one-voice.
4. Then revise Plan 5+6 → quick re-verify (advisor) → execute → live run.

**Given the session length, C1 + F-ord deserve a fresh, focused deliberation** — they're the only items that aren't mechanical, and C1 (which 4/5 missed) would have silently corrupted the live-run graph. That single catch justified the panel round.
