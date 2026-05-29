# Panel Review — Task #91 Plan 5+6 (`kdb-orchestrate` loop)

**Reviewer:** Deepseek · **Date:** 2026-05-29 · **Model:** deepseek-v4-pro

---

## Verdict

**`proceed-with-changes`** — The architecture is sound and the plan correctly reuses all four shipped foundations, but one critical integration bug (pipeline_id gap in manifest reader) and one high-severity idempotency bug (noise-source re-enrichment loop) must be fixed before execution. The remaining findings are confirmations or medium/low refinements that don't gate `proceed`.

---

## Findings

### F1 — `load_manifest_sources` does not return `pipeline_id` — breaks `scan_scope` pipeline filtering

- **Dimension:** D3 (integration correctness)
- **Severity:** critical
- **Issue:** `scan_scope` (kdb_scan.py:472) filters prior manifest entries by `r.get("pipeline_id") == pipeline_id` to scope the DELETED/MOVED pass to one pipeline. But `load_manifest_sources` (kdb_scan.py:233-240) does NOT extract `pipeline_id` from the manifest record — it only returns `{hash, mtime, size_bytes, file_type, is_binary, last_compiled_hash}`. Consequently, `prior_scoped` at line 471-473 will always be **empty** (`None == pipeline_id` → `False` for every record), causing: (a) every source appears as NEW every run (no hash match against prior), (b) DELETED detection fails (no prior to miss from), (c) MOVED detection fails (no prior paths to match by hash). The orchestrator loop would compile the whole vault on every invocation.

- **Evidence:**
  - Plan line 104: `prior = load_manifest_sources(state_root / "manifest.json")` — the orchestrator's `prior` comes from this function.
  - `scan_scope` line 471-473: `prior_scoped = {p: r for p, r in prior.items() if r.get("pipeline_id") == pipeline_id}`.
  - `load_manifest_sources` lines 233-240: `pipeline_id` is absent from the returned record dict.
  - The manifest record *does* carry `pipeline_id` — `_seed_source_record` (source_state_update.py:97) writes it: `"pipeline_id": file_entry.get("pipeline_id")`. The gap is strictly in the reader.

- **Recommendation:** Add `"pipeline_id": rec.get("pipeline_id")` to `load_manifest_sources`'s return dict (kdb_scan.py:240). Update the docstring (line 216) to list the returned keys. This is a one-line fix that should be done in Plan 5 (or as a Plan-6 prerequisite). Add a failing test that verifies `pipeline_id` survives a `load_manifest_sources → classify → prior_scoped` roundtrip.

---

### F2 — Noise sources will be re-enriched every run: `last_compiled_hash` never set for `metadata_only` sources

- **Dimension:** D4 (idempotency / fail-fast)
- **Severity:** high
- **Issue:** The plan's scan-eligibility check (`build_scan_result`, kdb_scan.py:368) places a source in `to_compile` when `current_hash != compiled_hash`. `compiled_hash` comes from the prior manifest's `last_compiled_hash` field. For noise sources (Branch 2 — `kdb_signal=noise`), the plan routes: "commit: embed frontmatter + recalc hash → manifest write (compile_state=metadata_only, post-embed hash)." But the manifest commit for a noise source calls `build_source_state_update` which runs `apply_scan_reconciliation` (sets `hash` = post-embed hash) but does **not** call `apply_compile_sources` (line 273: `rec["last_compiled_hash"] = source_hash`) because the noise branch skips compile entirely. `apply_scan_reconciliation` for a NEW source seeds `last_compiled_hash = None` (source_state_update.py:90), and for a CHANGED source does not touch `last_compiled_hash` at all. Result: on the next scan, `compiled_hash` = `None` (or stale), `current_hash` = the post-embed whole-file hash, `current_hash != compiled_hash` → `True` → source lands in `to_compile` every run. This violates the spec's guarantee (spec line 149: "Tracked so it is never re-enriched").

- **Evidence:**
  - Plan Task 3 line 116-117: `if gate(...) == "noise": prior = commit metadata_only (manifest, no compile/graph); continue` — no compile, so `apply_compile_sources` never fires.
  - `apply_compile_sources` (source_state_update.py:273): `rec["last_compiled_hash"] = source_hash` — the only place `last_compiled_hash` gets a non-None value for non-binary sources.
  - `_seed_source_record` (source_state_update.py:90): `"last_compiled_hash": file_entry["current_hash"] if is_binary else None` — treats non-binary as `None`.
  - `build_scan_result` (kdb_scan.py:368): `to_compile = sorted(e.path for e in files if e.current_hash != e.compiled_hash)`.
  - Spec line 149: "Tracked so it is never re-enriched."

- **Recommendation:** The noise-branch manifest commit must also set `last_compiled_hash = post_embed_hash`. Options:
  1. **(Minimal)** Have the noise-branch pass `is_binary=True` in the scan entry so `_seed_source_record` sets `last_compiled_hash = current_hash`. Hack but zero new code.
  2. **(Cleaner)** After `build_source_state_update`, the orchestrator manually sets `next_manifest["sources"][source_id]["last_compiled_hash"] = post_embed_hash` before the atomic write. One extra dict mutation.
  3. **(Cleanest, more surgery)** Extract the `last_compiled_hash` assignment from `apply_compile_sources` into a small helper that both the compile and noise paths call.
  Option 2 is recommended for Plan 5/6 — minimal, explicit, auditable. Add a test: enrich a noise source, commit, re-scan → `to_compile` is empty for that source.

---

### F3 — Accumulated `cr` merge at finalize is under-specified

- **Dimension:** D1 (journaling) + D3 (integration)
- **Severity:** high
- **Issue:** The plan accumulates per-source `cr` dicts during the loop (Plan Task 2 line 82: `# (journaling: accumulate cr for finalize per Design Point 1)`) and defers the journal/sidecar write to finalize. But the plan does not specify how the per-source `cr`s are merged into one combined `cr` for the `compile_result.json` sidecar that `graphdb-kdb rebuild` replays. The merge involves:
  - `compiled_sources`: concatenation (straightforward).
  - `canonical_meta.aliases_emitted`: merge with dedup (same alias → last writer wins). If left as a raw list concatenation, the same alias→canonical pair could appear twice, or worse, two different canonicals for one alias could coexist — violating the flat-alias invariant.
  - `log_entries`: concatenation.
  - `errors`/`warnings`: concatenation.
  The merge is straightforward but the `aliases_emitted` dedup is load-bearing for rebuild correctness. A naive merge would produce an invalid `canonical_meta` that the verifier could catch, but the plan should specify the merge.

- **Evidence:**
  - Plan Task 2 line 82: `# (journaling: accumulate cr for finalize per Design Point 1)`.
  - Plan Task 4 line 141-148: `_finalize` runs `detect_orphans` + cleanup + `last_orchestrate.json` — journal/sidecar write is implied but not explicitly listed.
  - Spec line 287-289: "archive sidecar + run journal (replayable for graphdb-kdb rebuild)" in the per-source commit sequence — but the plan defers this to finalize.
  - `canonicalize.run` appends to `ledger`, and `canonical_meta.aliases_emitted` is the ledger serialized. Per-source ledgers produce independent alias lists.

- **Recommendation:** Add a merge step to Task 4 (finalize): `merged_cr = _merge_compile_results(accumulated_crs)` with explicit dedup of `aliases_emitted` (last-writer-wins by `canonical_slug`/`alias_slug` pair). Write the merged `cr` as the `compile_result.json` sidecar and the run journal. Add a test for the merge: two sources producing the same alias → merged `canonical_meta` has exactly one entry.

---

### F4 — `patch_applier.apply` write-before-manifest window: wiki pages on disk with no manifest entry

- **Dimension:** D2 (commit ordering)
- **Severity:** medium (accepted trade-off, confirmed)
- **Issue:** The per-source commit sequence puts `patch_applier.apply` (wiki writes) BEFORE `atomic_write_json` for the manifest. If the manifest write fails, wiki pages exist on disk for an un-committed source. The spec (line 324-325) and plan both accept this as a "self-healing edge" — the next run re-detects the source as NEW, re-compiles, and `atomic_write_text` overwrites the stale wiki pages. This is correctly flagged as an accepted trade-off per the produce-don't-write decision and `[[feedback_no_imaginary_risk]]`. The plan should document this window explicitly in the `_commit_source` docstring for operator awareness.

- **Evidence:**
  - Plan Task 2 lines 78-84: `patch_applier.apply(...)` → `atomic_write_json(manifest_path, ...)` → `apply_compile_result(...)`.
  - Spec line 324-325: "A patch-apply failure may leave orphan wiki pages on disk with no manifest entry — accepted self-healing edge."

- **Recommendation:** Accept as-is. Document the window in `_commit_source`'s docstring: "Case (a) failure after `patch_applier.apply` but before manifest write leaves wiki pages on disk with no manifest entry; next-run re-compile overwrites them via `atomic_write_text`." No code change needed — the trade-off is well-understood and the blast radius (one source's wiki pages) is bounded.

---

### F5 — Accumulate-at-finalize journaling: design point analysis

- **Dimension:** D1 (primary open fork)
- **Severity:** medium (endorsement of plan's lean)
- **Issue:** The plan's Design Point 1 asks the panel to weigh accumulate-at-finalize vs per-source journal append. Analysis:
  - **Residual gap with accumulate-at-finalize:** A crash mid-loop (after ≥1 source committed, before finalize) leaves committed sources in the live graph and manifest, but no journal/sidecar. `graphdb-kdb rebuild` from scratch would miss those sources. This requires a double fault (crash + subsequent graph loss).
  - **Probability assessment:** Single-user, infrequent workload. Crash mid-loop is rare. Subsequent graph loss (disk failure, accidental deletion) coinciding with that crash window is extremely unlikely.
  - **Machinery cost of per-source journal append:** Would need to open the run journal, append a per-source entry + update the sidecar, all atomically or with crash-consistency guarantees. Adds significant complexity (append semantics, partial-journal replay, interleaved journal + sidecar writes).
  - **Mitigation without per-source journaling:** The `last_orchestrate.json` summary is written on abort (Plan Task 5 line 163: "Written always (success + abort)"), recording the failed source — providing operator observability without the journaling complexity.

- **Evidence:**
  - Plan Design Point 1 (lines 17-18).
  - Plan Task 5 line 163: `last_orchestrate.json` written on abort.
  - `apply_compile_result` (ingestor.py:54-111): per-source atomic transaction with `BEGIN/COMMIT`.

- **Recommendation:** **Endorse the plan's lean — accumulate at finalize.** The double-fault scenario's probability does not justify the per-source journaling machinery for v1. Add a comment in the loop code: "Sources committed to graph + manifest; journal/sidecar deferred to finalize. A crash before finalize leaves committed-but-not-journaled sources — recoverable unless the graph is also lost (double fault)." If empirical operation shows mid-loop crashes (e.g., from OOM on large sources), revisit with per-source journaling then.

---

### F6 — `load_or_empty(ledger)` is under-specified

- **Dimension:** D3 (integration)
- **Severity:** medium
- **Issue:** Plan Task 3 line 120 references `ledger=load_or_empty(...)` as a parameter to `compile_source`. The `AliasLedger` is used by `canonicalize.run(cr, ledger, ctx.run_id)` (compiler.py:693). The plan does not specify whether the ledger is per-source (empty each iteration) or accumulated across the loop. Since canonicalize is per-source (spec line 171: "per-source; not cross-source-batch-bound"), an empty ledger per source is correct — alias canonicalization is source-local. But `load_or_empty(...)` suggests persistence/loading, which would only be needed for cross-source alias sharing (a batch concern). The ambiguity could lead to implementation drift.

- **Evidence:**
  - Plan Task 3 line 120: `compile_source(source_id, enrich.body, ..., ledger=load_or_empty(...))`.
  - Spec line 171 (stage table): "6 canonicalize — compiler core (per-source; not cross-source-batch-bound)".
  - `canonicalize.run` (compiler.py:693): mutates `cr` in place, appends to `ledger`.

- **Recommendation:** Explicitly use `AliasLedger()` (empty, no loading) per source. Drop `load_or_empty(...)` — the name implies a persistence concern that doesn't exist for per-source canonicalization. The `AliasLedger` default constructor is the correct call. If cross-source alias sharing is ever needed, it would be a batch concern, not a loop concern.

---

### F7 — `scan.to_compile` ordering is alphabetical, not dependency-aware

- **Dimension:** D4 (read-after-write)
- **Severity:** low (known v1 limitation)
- **Issue:** `build_scan_result` (kdb_scan.py:368) sorts `to_compile` by path: `sorted(e.path for e in files if ...)`. The orchestrator loop processes sources in this alphabetical order. If source `B.md` semantically depends on source `A.md` (B's context snapshot should see A's just-compiled pages), and `A.md` sorts after `B.md`, B's context read will miss A's pages. Since the single shared connection provides immediate read-after-write, the fix is purely ordering, not a connection model issue. This is a known v1 limitation — dependency ordering requires a graph traversal the v1 scanner doesn't do.

- **Evidence:**
  - `build_scan_result` (kdb_scan.py:368): `to_compile = sorted(e.path for e in files if e.current_hash != e.compiled_hash)`.
  - Spec line 291: "Next source's context read sees this source's committed graph mutation" — holds for sources processed BEFORE the reader, not after.

- **Recommendation:** Accept for v1 — this is the same limitation the monolith had (planner processes jobs in scan order). Document in the loop code: "Sources processed in alphabetical path order; a source that depends on a later-alphabetical source won't see its pages in the context snapshot. Resolved on next run." If this proves problematic, the v2 fix would sort `to_compile` by a topological order derived from existing graph edges.

---

### F8 — `_commit_source` wraps `build_source_state_update`'s tuple return into a dict

- **Dimension:** D3 (contract composition)
- **Severity:** low (implementation detail)
- **Issue:** The plan's `_commit_source` returns `{"next_manifest": next_manifest, "pages_written": [...]}`. But `build_source_state_update` returns a `tuple[dict, dict]` — `(next_state, stage_payload)`. The `_commit_source` function is a new wrapper (not an existing shipped function), so it correctly unpacks the tuple and repackages into a dict. The plan's pseudocode at line 78 should explicitly show the tuple unpacking to avoid implementation confusion: `next_manifest, stage_payload = source_state_update.build_source_state_update(...)`.

- **Evidence:**
  - Plan Task 2 line 79: `next_manifest, _ = source_state_update.build_source_state_update(prior_manifest, single_scan, cr, ctx)` — actually the plan DOES show the tuple unpacking at line 79! This is correct.
  - `source_state_update.py` line 429-431: return type is `tuple[dict, dict]`.

- **Recommendation:** No change needed — the plan's pseudocode at line 79 already correctly unpacks the tuple. Confirming the contract is composed correctly.

---

## What I checked and found sound

1. **Per-source commit ordering (D-91-13 cases a/b).** The plan's `_commit_source` sequence (apply-wiki → manifest-write → graph-sync) correctly places the COMMIT BOUNDARY at the manifest write. Case (a) failures before the boundary leave the manifest untouched; case (b) failures after (graph-sync throws) leave manifest+wiki committed with graph stale. The boundary placement matches the spec.

2. **`build_source_state_update` per-source safety.** Verified: `apply_scan_reconciliation` (source_state_update.py:146) iterates only `last_scan["files"]` — with a single-source scan dict, only that source is touched. Other sources in the manifest are untouched. No mass-tombstoning. **Confirmed.**

3. **`apply_compile_result` with 1-source `cr` + 1-file `scan_dict`.** Traced through Phases 1→3.5: Phase 1 upserts one source, Phase 2 is empty (`to_reconcile=[]`), Phase 3 processes one `compiled_source`'s pages/supports/meta, Phase 3.5 handles aliases, Phase 4 skipped (`detect_orphans=False`). The `BEGIN TRANSACTION`/`COMMIT`/`ROLLBACK` in `apply_compile_result` correctly bounds the per-source graph mutation atomically.

3. **`patch_applier.apply` per-source.** `build_page_patches` accumulates `source_refs` across `compiled_sources[]` — with a single-source `cr`, this produces one `source_ref` per page. Cross-source wiki merge (the Plan-1 finding) is vacuous — last-writer-wins on the wiki page, graph stays authoritative. **Matches the accepted trade-off.**

4. **Single shared read-write connection model.** The plan opens one `GraphDB` for the loop and threads `g.conn` through `compile_source` (context read) and `apply_compile_result` (graph write). The Kuzu probe evidence confirms interleaved read-after-write works on one connection. **Correct and empirically grounded.**

5. **Deferred orphan-marking (`detect_orphans=False` per-source, one `detect_orphans()` at finalize).** The `detect_orphans` flag already exists in `apply_compile_result` (ingestor.py:32, defaults `True`). The standalone `detect_orphans()` function (ingestor.py:712-733) already exists. The plan's finalize sequence (detect → reap → cleanup → summary) correctly composes them. **Already shipped.**

6. **Fail-fast + resume/idempotency (verified paths).**
   - Committed source → UNCHANGED on next scan (post-embed hash matches) → skipped. ✓
   - Mid-run-failed source (enrich succeeded, compile/manifest failed) → no manifest entry → NEW on next scan → re-enriched + re-compiled + overwrites wiki. ✓
   - Failed-enrich source → manifest untouched → re-enriched next run. ✓
   - `apply_compile_result` ROLLBACK on failure → graph unchanged. ✓

7. **`kdb-clean orphans` integration.** `reap_orphans_from_graph(conn)` (kdb_clean.py:117) reads orphan_candidate entities from GraphDB. `apply_cleanup(retraction, run_id, conn=conn)` (ingestor.py:738) DETACH DELETEs them. The plan correctly sequences these at finalize after `detect_orphans()`. **No subprocess — direct Python API per D-91-12.**

8. **Sandbox isolation.** The plan's sandbox scaffold (Task 6 Step 3) uses `~/Obsidian/Vault-in-place-test-run/` as its own `vault_root` with `KDB/wiki/`, `KDB/state/`, and `KDB/graph/` all self-contained. Production `~/Obsidian/KDB/` is untouched. **Correct isolation per advisor B's fix.**

9. **`compile_source` produce-don't-write contract.** Returns `CompileSourceResult(cr=...)` with no I/O. The orchestrator owns stage-8 apply-pages, manifest commit, and graph-sync. **Already shipped and tested.**

---

## Summary

| Severity | Count | Findings |
|----------|-------|----------|
| Critical | 1 | F1 — `load_manifest_sources` pipeline_id gap |
| High | 2 | F2 — noise-source re-enrichment loop; F3 — accumulated `cr` merge under-specified |
| Medium | 3 | F4 — wiki-before-manifest window (confirmed accepted); F5 — accumulate-at-finalize journaling (endorsed); F6 — ledger ambiguity |
| Low | 2 | F7 — alphabetical ordering (known v1 limit); F8 — contract composition (confirmed correct) |

**Gating items before execution:** Fix F1 (one-line addition to `load_manifest_sources`) and F2 (set `last_compiled_hash` for noise sources). F3 should be specified before writing Task 4 but doesn't gate Task 1-3. The remaining findings are confirmations or documentation refinements.

**Overall architectural assessment:** The plan correctly composes the four shipped foundations. The per-source commit sequence, fail-fast routing, deferred orphan-marking, single-connection model, and sandbox isolation are all correctly specified and code-grounded. The two bugs (F1, F2) are narrow, fixable gaps between the plan and shipped code — not architectural flaws.
