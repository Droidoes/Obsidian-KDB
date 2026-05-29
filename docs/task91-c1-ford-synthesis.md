# C1 + F-ord — Panel Recommendation Synthesis (2026-05-29)

5-model panel (Codex · Deepseek · Qwen · Grok · Gemini). Briefs: `docs/task91-c1-ford-*` review files. Strong convergence.

## Decision 1 — C1 (cross-source `LINKS_TO`): **defer link-wiring to finalize batch-wire, NO stubs** (4/5)

- **defer-to-finalize: Codex, Deepseek, Qwen, Gemini (4/5).** **stub-upsert: Grok (1/5).**
- **Why defer wins (all 4 reject stubs, concretely):** stub-upsert creates entities the model never emitted → (Qwen) "a link to a ghost" if the stub's source fails to compile; masks the dangling-link signal the validator exists to surface; **breaks live≡replay** unless a finalize stub-GC drops un-promoted stubs (batch replay skips dangling); and (Codex) inactive stubs can leak into prompt projection via `_batch_outgoing_links` (no status filter on targets). Defer = `live≡replay by construction`, mirrors the existing `detect_orphans=False` deferral, no new entity vocabulary.
- **Grok's dissent (mid-run T3):** stubs let a later source see cross-source edges *during* the loop; defer makes T3 cross-source-incomplete until finalize. **Resolved:** T1 (SUPPORTS) + T2 (entity_search_keys) anchor context per-source and are unaffected; T3 is supplementary; Deepseek's point — the *monolith never had intra-batch T3 either* (committed the whole batch at once), so per-source is strictly ≥ monolith. Mid-run T3 degradation is acceptable for v1.
- **Codex's enhancement (optional):** *incremental prefix-rewire* — rewire `LINKS_TO` over the accumulated-so-far `cr`s after each source (not just at finalize) → restores mid-run T3 for already-committed sources, no stubs. Adopt only if the live run shows mid-run T3 matters; **default = finalize-only** (simpler).
- **Mechanism (convergent):** `apply_compile_result(wire_links=False)` per source (skip only `_replace_outgoing_links`; keep SUPPORTS/ingest-state/meta); extract a standalone `wire_links(cr, conn)` (Qwen-(i)/Codex) the orchestrator calls once at finalize over accumulated `cr`s. Idempotent (drop+recreate). live≡replay holds — rebuild replays the combined `compile_result` batch-wise (verified rebuilder.py:151).

## Decision 2 — F-ord (commit ordering): **β — graph-sync-first; revise D-91-13** (5/5 UNANIMOUS)

- **All five pick β.** apply-wiki → graph-sync (Kuzu txn) → [on success] manifest + sidecar. Graph-sync failure rolls back cleanly → manifest never written → **case-(a) self-heal**; **case-(b) is eliminated** (no more manifest-committed-but-graph-stale → no manual rebuild path).
- **Why revising ratified D-91-13 is justified:** the three conditions that made case-(b) load-bearing all post-date D-91-13 — (1) batch→per-source graph-sync, (2) the single read-write connection, (3) *verified* clean Kuzu rollback + per-source `apply_compile_result` idempotency. β honors D-91-13's **intent better**: under α a sidecar can exist while the graph is stale (sidecar not truly authoritative); under β `sidecar exists ⇒ manifest written ⇒ graph-sync succeeded ⇒ graph consistent` — a *stronger* replayable-authority invariant (Deepseek/Qwen).
- **Residual:** crash between graph-sync COMMIT and sidecar-write + graph loss = bounded one-source double-fault — the same class already accepted for per-source journaling. Idempotency makes manifest-write-failure-after-graph-sync self-heal on re-run.
- **Action:** amend the blueprint — **D-91-15** (or D-91-13-am1): "graph-sync-first; eliminates case-(b); justified by single-rw-conn + verified rollback post-dating D-91-13." **Needs Joseph's explicit nod (revises a ratified decision).**

## Recommended combined commit sequence (convergent across all 5)

**Per-source (`_commit_source`):**
1. `patch_applier.apply(write=True)` — wiki pages (stage 8).
2. `apply_compile_result(cr, single_scan, conn, detect_orphans=False, wire_links=False)` — Kuzu txn: Source + Entities + SUPPORTS + aliases + meta. Rollback-clean on failure (case-a).
3. **[on success]** `atomic_write_json(manifest)` — post-embed hash + `pipeline_id` + `last_compiled_hash`. ← **commit boundary** (revised: after graph-sync).
4. per-source sidecar `state/runs/<run_id>/<source_id>.json` (best-effort; replay payload). Accumulate `cr` in memory.

**Finalize (after fully-successful loop):**
5. `wire_links(accumulated_crs, conn)` — batch LINKS_TO, all entities present (C1 fix). Own txn, idempotent.
6. `detect_orphans(conn, run_id)` — single deferred pass. (Order vs step 5 immaterial — orphan is SUPPORTS-only, not LINKS_TO.)
7. `kdb-clean orphans` — `reap_orphans_from_graph` + `apply_cleanup` **+ `build_cleanup_artifacts`** (cleanup journal + `retraction.json`, m1 — else rebuild resurrects reaped entities).
8. compact per-source sidecars → combined `compile_result.json` + run journal; `last_orchestrate.json`.

**Noise source:** no graph step — embed/enrich → manifest `metadata_only` with `last_compiled_hash=post_embed_hash` (M2).

## Implementation notes folded from the panel
- `wire_links: bool = True` flag on `apply_compile_result` (guards only `_replace_outgoing_links`).
- Extract standalone `wire_links(cr, conn, run_id, now)` for the finalize pass.
- `last_orchestrate.json` distinguishes `manifest_failed_after_graph_commit` from pre-graph failures (Codex — self-healing but a distinct class under β).
- Finalize-crash resume: a `state/runs/<run_id>_state.json` phase marker so a crash *in finalize* resumes the batch-wire/orphan/cleanup from per-source sidecars (Deepseek #5) — v1-optional.
- `--dry-run`: whole sequence with `write=False` + connection rollback; report what *would* wire (Gemini).

## Net
Both forks resolved by the panel: **C1 → defer-to-finalize batch-wire (no stubs); F-ord → β (graph-sync-first, amend D-91-13).** Fold into Plan 5+6 (Tasks 2/3/4 + the new `wire_links` + finalize sequence); the β revision needs Joseph's explicit ratification before it's amended.
