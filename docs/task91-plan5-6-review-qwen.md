# Task #91 Plan 5+6 Review — Qwen CLI (qwen3.7-max)

**Reviewer:** Qwen CLI / qwen3.7-max
**Plan reviewed:** `docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md`
**Date:** 2026-05-27
**Guardrail compliance:** Single review file produced; no other repo files modified.

---

## 1. Verdict

**proceed-with-changes** — Plan 5+6 faithfully composes the four shipped foundations into a per-source loop that matches the spec's routing, commit ordering, and fail-fast semantics. The PRIMARY open fork (D1 journaling) should resolve toward per-source sidecar append rather than accumulate-at-finalize (F-1, high). Three medium findings address the `current_mtime` staleness after embed (F-2), an implicit `pipeline_id` assumption on legacy manifest records (F-3), and an undeclared interaction between the MOVED+CHANGED deferred edge and fail-fast (F-4).

---

## 2. Findings

### F-1: Accumulate-at-finalize journaling leaves a real crash gap — per-source sidecar is the right call

**Dimension:** D1 (journaling / replayability)
**Severity:** high

**Issue:** The plan's lean is to accumulate per-source `cr`s and write the run journal + `compile_result.json` sidecar **once at finalize**. A crash mid-loop (after source N commits to manifest + graph but before finalize writes the journal) leaves committed-but-not-journaled sources. The live graph has them (per-source committed), so no rebuild is needed *unless the graph is also lost*. But the graph-loss scenario is not hypothetical — `graphdb-kdb rebuild` exists precisely because graph corruption or loss happens (it's the tool's entire purpose). Without a journal, rebuild has nothing to replay for the crashed run's committed sources, and re-running the orchestrator won't re-compile them (UNCHANGED by hash match).

**The gap in concrete terms:**
1. Source A enriches → compiles → commits (manifest + graph). No journal written yet.
2. Source B fails at compile. Fail-fast aborts. No finalize. No journal.
3. Operator loses the graph (disk corruption, accidental `rm -rf`).
4. `graphdb-kdb rebuild` replays journals. The crashed run's journal doesn't exist → source A's graph mutations are unrecoverable from journals.
5. Re-running the orchestrator: source A → UNCHANGED (hash match) → skipped. Source A's entities are permanently missing from the graph.

**Evidence:** Plan Design Point 1: "accumulate per-source `cr`s into one run-level `compile_result` and write the journal + sidecar once at finalize." The monolith's `kdb_compile.py` writes the journal at the end of the batch run — same pattern, but the monolith's crash window is batch-wide (all-or-nothing). The per-source loop's crash window is narrower per source but the *journal* is still batch-wide, creating the mismatch.

**Recommendation:** After each per-source manifest commit, append a per-source sidecar (the `cr` dict serialized to `state/sidecars/<run_id>/compile_result_<source_id>.json`). Cost: one `atomic_write_json` call per committed source (~1ms on local disk). Benefit: each committed source has a replayable record independent of finalize. `graphdb-kdb rebuild` would need a minor adaptation to discover per-source sidecars (glob `compile_result_*.json` in the run's sidecar dir) — or the finalize step can still concatenate them into one batch sidecar for backward compat. The crash window shrinks to zero for already-committed sources.

The alternative (accept the gap) is defensible only if you judge the double-fault (crash + graph loss) as negligible risk. I judge it as the exact scenario the journal/rebuild machinery exists to handle — accepting it undermines the purpose of the replay infrastructure.

---

### F-2: `current_mtime` in the ScanEntry is stale after embed — `patch_applier` stamps pre-embed mtime into page frontmatter

**Dimension:** D2 (commit ordering)
**Severity:** medium

**Issue:** `scan_scope` runs before the per-source loop. The `ScanEntry.current_mtime` is captured at scan time (pre-embed). Then `enrich_one` calls `embed_frontmatter`, which writes to the source file — updating its mtime. The plan's `_commit_source` constructs `single_scan` with the original ScanEntry (overriding `current_hash` to `post_embed_hash`), but does **not** override `current_mtime`. `patch_applier._source_mtime_from_scan` (`patch_applier.py:143-148`) reads `current_mtime` from the scan entry and stamps it into every page's frontmatter as `raw_mtime`.

The result: page frontmatter `raw_mtime` records the pre-embed mtime, not the actual time the source was last modified (which is the embed time). The `raw_hash` is correct (post-embed), so hash-based change detection works. But `raw_mtime` is a few seconds stale and semantically misleading — it says "the source was modified at T_scan" when it was actually modified at T_embed > T_scan.

**Evidence:** `enrich.py:63` — `embed_frontmatter(source_path, envelope)` writes to disk, changing mtime. Plan Task 2 Step 3 pseudocode — `single_scan = {"files": [scan_entry_dict_with_pipeline_id_and_post_embed_hash]}` overrides `current_hash` but not `current_mtime`. `patch_applier.py:146` — `mtime = entry.get("current_mtime")`.

**Recommendation:** After `embed_frontmatter`, also capture the post-embed mtime: `post_embed_mtime = source_path.stat().st_mtime`. Thread it into `EnrichResult` alongside `post_embed_hash`. In `_commit_source`, override both `current_hash` and `current_mtime` in the scan entry dict. Cost: one `stat()` call and one additional field. Ensures `raw_mtime` and `raw_hash` are consistent (both post-embed).

---

### F-3: `scan_scope` filters `prior` by `pipeline_id` — legacy manifest records without `pipeline_id` are silently excluded

**Dimension:** D3 (integration correctness)
**Severity:** medium

**Issue:** `scan_scope` (line 474-476) filters `prior` with `r.get("pipeline_id") == pipeline_id`. Manifest records created before Plan 4 T2 (which added `pipeline_id` to the seed record) have no `pipeline_id` field — `r.get("pipeline_id")` returns `None`, which doesn't match any `pipeline_id` string. These legacy records are silently excluded from the pipeline's scan scope.

On first orchestrator run against a vault with pre-existing manifest records, all legacy sources appear as NEW (not in scoped `prior`) and get re-classified, re-enriched, and re-compiled. This is a **mass re-enrichment** of the entire vault — expensive (LLM calls) and unnecessary (content hasn't changed).

**Evidence:** `kdb_scan.py:474-476`:
```python
prior_scoped = {
    p: r for p, r in prior.items() if r.get("pipeline_id") == pipeline_id
}
```
Plan Design Point 2: "Confirm the manifest record exposes `pipeline_id` for the filter (Plan 4 T2 added it to the seed record — verify older records degrade gracefully)." The plan flags this but does not resolve it.

**Recommendation:** Add a migration step at orchestrator startup: load the full manifest, check if any source records lack `pipeline_id`, and if so, stamp them with a default (e.g., the first registered pipeline's id, or a configurable `default_pipeline_id`). This is a one-time operation that makes legacy records visible to `scan_scope`. Alternatively, `scan_scope` could treat `pipeline_id is None` as "belongs to the default pipeline" — but this couples the scanner to migration logic. The orchestrator-level migration is cleaner.

---

### F-4: MOVED+CHANGED deferred edge interacts badly with fail-fast ordering

**Dimension:** D4 (fail-fast / idempotency)
**Severity:** medium

**Issue:** The plan acknowledges the MOVED+CHANGED edge (a file both moved AND edited in the same scan) and defers it: "Plan v1: dedupe to the compile path (recompile at new path); confirm/route explicitly during execution (or keep deferred with a logged skip)."

But the loop processes `scan.to_compile` first, then `scan.to_reconcile`. A MOVED+CHANGED source appears in **both** lists:
- `to_compile`: because `current_hash != compiled_hash` (content changed)
- `to_reconcile`: because the scanner detected a MOVED op (same hash at new path, but content also changed — the rename pass matches by hash, but the hash changed, so...)

Actually, let me trace the scanner logic more carefully. `classify()` in `kdb_scan.py` does:
1. Phase B: intersection of current and prior by path → UNCHANGED or CHANGED
2. Phase C: rename pass on leftovers (current-only ∩ prior-only, matched by hash) → MOVED
3. Phase D: remaining current-only → NEW; remaining prior-only → DELETED

For MOVED+CHANGED: the file moved from path A to path B, AND its content changed. Phase B: path A is prior-only (no current match), path B is current-only (no prior match). Phase C: rename pass tries to match path B (current-only) with path A (prior-only) by hash. But the hash changed (content edited), so no match. Phase D: path B → NEW, path A → DELETED.

So MOVED+CHANGED doesn't appear as MOVED in `to_reconcile` — it appears as NEW (at new path) + DELETED (at old path). The compile path processes the NEW source (recompiling at the new path). The reconcile path processes the DELETED source (severing SUPPORTS). This is actually **correct** — it's the same outcome as "recompile at new path" that the plan intends.

The concern is: the DELETED reconcile op severs the old source's SUPPORTS edges. The NEW compile creates new SUPPORTS at the new path. If the DELETED runs AFTER the compile (which the plan's ordering ensures), the new SUPPORTS are not affected. If the ordering were reversed, the DELETED would sever edges that the compile hasn't created yet — but the compile would recreate them. So ordering doesn't matter for correctness, only for transient state.

**Revised assessment:** This is not a real finding — the scanner's classification logic naturally decomposes MOVED+CHANGED into NEW+DELETED, and the plan's ordering (compile first, reconcile second) handles both correctly. The plan's "deferred edge" comment is misleading — the edge is already handled correctly by the scanner's existing logic. I'll downgrade this to an observation.

**Observation O-1:** The plan's "MOVED+CHANGED" deferred edge is a non-issue. The scanner decomposes it into NEW+DELETED, and the plan's compile-then-reconcile ordering handles both correctly. The deferred comment can be removed or clarified to note that the scanner already handles this case.

---

## 3. What I checked and found sound

### Spec fidelity (cross-cutting)

- **Stage redistribution:** Plan 5+6 correctly owns stages 1-2 (scan), 7 (manifest), 8 (apply-pages), 9 (persist), 10 (graph-sync). `compile_source` owns 3-6. No overlap or gap.
- **Single read-write connection:** `with GraphDB(graph_path) as g:` opens one connection; `g.conn` threaded through `compile_source` and `apply_compile_result`. Matches the spec's empirically-verified connection model.
- **3-branch routing:** signal → enrich → compile → commit; noise → enrich → metadata_only manifest; DELETE/MOVED → reconcile. Matches the spec's per-source routing pseudocode.
- **Fail-fast (D-91-8):** Any enrich or compile failure aborts the run. Prior committed sources stay committed. The `failure_stage` from `CompileSourceResult` threads into the abort result. Correct.
- **D-91-13 two-phase boundary:** Manifest write is the commit boundary. Pre-manifest failures = case (a); post-manifest graph-sync failures = case (b). Ordering is correct.
- **`last_orchestrate.json` (D-91-10):** Fields match the decision spec. Written always (success + abort). Correct.

### D2 — Commit ordering

- **apply-wiki → manifest → sidecar → graph-sync:** Correct ordering. The manifest write is the case-(a)/(b) boundary. Partial-write windows are self-healing:
  - Wiki written, manifest fails → orphan wiki pages; next run re-detects source (hash mismatch) → re-enrich → overwrite. Self-healing.
  - Manifest written, graph-sync fails → case (b); remediation is `graphdb-kdb rebuild`. Correct.
- **`single_scan` construction:** Overrides `current_hash` to `post_embed_hash` (correct — manifest stores post-embed hash). `to_compile: [source_id]` ensures `apply_compile_sources` doesn't false-mark other sources as error. `to_reconcile: []` ensures no spurious reconcile ops. All correct.

### D3 — Integration correctness (batch-assumption traps)

- **`apply_compile_result` with 1-source cr + 1-file scan_dict:** Phase 1 upserts 1 Source. Phase 3 upserts entities and wires links/supports for 1 source's pages. Phase 4 skipped (detect_orphans=False). All correct — no cross-source or batch assumptions violated.
- **`build_source_state_update` per-source:** `apply_scan_reconciliation` iterates only `last_scan.files` (1 entry) and `last_scan.to_reconcile` (empty). Does not diff the full prior keyset. Confirmed per-source safe (matches advisor A's verification).
- **`patch_applier.apply` per-source:** `build_page_patches` accumulates `source_refs` per page_key across all compiled_sources in the cr. With a 1-source cr, each page gets only the current source in `source_refs`. This is the accepted last-writer-wins trade-off — the graph has the full SUPPORTS picture. Correct.
- **`enrich_one` body return:** `body` in `EnrichResult` is the body after `parse_existing_frontmatter` strips frontmatter. This is exactly what `compile_source` needs — the clean body for the prompt. Correct.
- **`SourceFrontmatter.from_dict(enrich.envelope)` projection:** Converts the Pass-1 envelope dict to the typed `SourceFrontmatter` dataclass. If required keys are missing, returns `None` — compile proceeds without source metadata (same as monolith behavior). Correct.

### D4 — Fail-fast / resume / idempotency

- **Re-run idempotency:** Committed source → manifest has post-embed hash → scan hashes the file (post-embed, unchanged) → current_hash == manifest hash → UNCHANGED → skipped. Mid-run failed source → manifest has old hash → current_hash (post-embed from failed run) != old hash → CHANGED → re-enriched (deterministic embed overwrites) → re-compiled → committed. Self-healing. Correct.
- **Read-after-write on single connection:** Spec verified empirically. Source N's graph-sync writes are immediately visible to source N+1's `build_context_snapshot`. Correct.
- **`detect_orphans=False` per-source + single finalize pass:** Avoids transient-orphan context pollution. Orphan status computed once over the final graph. Correct per the spec's decision.

### Plan 5 — `enrich_one` egress

- **`body` + `post_embed_hash` on `EnrichResult`:** Clean extension. Skipped/failed paths correctly leave these as their available values. The hash is recomputed from the on-disk file after embed — deterministic and correct.

### Task structure

- **TDD sequencing:** Each task follows fail-then-pass. Task 1 (enrich egress) → Task 2 (commit helper) → Task 3 (loop + routing) → Task 4 (finalize) → Task 5 (summary) → Task 6 (CLI + live run). Dependencies flow forward only. Clean.
- **Sandbox isolation:** `~/Obsidian/Vault-in-place-test-run/` as its own vault_root. `KDB/wiki/`, `KDB/state/`, `KDB/graph/` all under the sandbox. Production `~/Obsidian/KDB/` untouched. Cleanup = `rm -rf`. Correct.
- **Live run gate:** Joseph fires. Deepseek model. Observable outputs listed. Clean.
