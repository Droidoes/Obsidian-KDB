# Task 91 Plan 5+6 Review — Codex

## 1. Verdict

**revise-before-execution** — the loop shape is right, but the plan currently breaks replayability in real case-(b) failures and has two concrete foundation-contract mismatches that should be corrected before implementation.

## 2. Findings

### Finding 1 — Finalize-only journaling breaks case-(b) recovery

**Dimension:** D1 / D2  
**Severity:** Critical

**Issue:** The plan leans toward accumulating per-source `cr`s and writing the run journal + sidecar once at finalize, but `_commit_source` performs graph-sync after the manifest boundary. If graph-sync fails, D-91-13 says the source is committed and recovery is `graphdb-kdb rebuild`; that only works if a replayable sidecar + eligible journal already exist before graph-sync. Finalize-only journaling turns an ordinary graph-sync failure into an unreplayable committed state.

**Evidence:** Plan design point 1 proposes writing journal + sidecar "once at finalize" (`docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md:17`). `_commit_source` writes manifest, then only comments "journaling: accumulate cr for finalize", then calls `apply_compile_result(...)` (`...plan5-6-orchestrator-loop.md:75-83`). The spec's full branch says sidecar/journal archival precedes graph-sync (`docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md:285-290`). D-91-13 requires post-manifest graph-sync failure to be remediable by rebuild (`docs/task91-kdb-orchestrate-blueprint.md:50`). The current monolith explicitly archives sidecars before live sync and writes failure journals with `replayable_payload=True` on sync failure (`kdb_compiler/kdb_compile.py:596-647`).

**Recommendation:** Do not use finalize-only replay artifacts for committed sources. After manifest write and before graph-sync, write a replayable per-source compile artifact: sidecar `state/runs/<event_id>/{compile_result,last_scan}.json` plus an eligible journal with `replayable_payload=true`. The `event_id` can be the run id plus a source-safe suffix, or a per-source event id under the orchestrator run. A final aggregate summary can still be written, but rebuild safety must be per committed mutation.

### Finding 2 — Cleanup finalize is not replayable

**Dimension:** D1 / D3  
**Severity:** High

**Issue:** `_finalize` plans to run `detect_orphans()`, compute `reap_orphans_from_graph()`, and call `apply_cleanup()` directly, then write only `last_orchestrate.json`. That mutates the live graph but does not write the cleanup journal + `retraction.json` sidecar that rebuild needs to keep reaped entities deleted.

**Evidence:** Plan Task 4 pseudocode calls `detect_orphans(conn, ctx.run_id)`, then `reap_orphans_from_graph(conn); apply_cleanup(...)`, then `write_last_orchestrate_json(...)` (`docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md:137-146`). `kdb-clean` documents cleanup journaling as a replayable `cleanup` run journal plus `retraction.json` sidecar (`kdb_compiler/kdb_clean.py:19-23`), and provides `build_cleanup_artifacts()` for that shape (`kdb_compiler/kdb_clean.py:165-201`). The replay adapter requires cleanup sidecars for eligible cleanup events (`graphdb_kdb/adapters/obsidian_runs.py:126-143`).

**Recommendation:** Make finalize use the existing cleanup artifact path: build the cleanup journal/retraction sidecar before or with `apply_cleanup()`, and ensure it is replay-eligible. Treat cleanup graph mutation like any other committed mutation; otherwise a GraphDB rebuild can resurrect entities that the successful orchestrator run reaped.

### Finding 3 — `load_manifest_sources()` drops `pipeline_id`, so scoped scans mis-diff

**Dimension:** D3 / D4  
**Severity:** Critical

**Issue:** The plan says the orchestrator loads `prior = load_manifest_sources(...)` and passes it to `scan_scope()`, which filters prior rows by `pipeline_id`. In current code, `load_manifest_sources()` does not include `pipeline_id` in its returned records, so `scan_scope()` filters every prior row out. That makes reruns look like first runs for the selected pipeline and breaks resume/idempotency.

**Evidence:** Plan design point 2 flags this exact seam (`docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md:18`), and Task 3 uses `prior = load_manifest_sources(...)` followed by `scan_scope(..., pipeline_id=pipeline_id, prior=prior, ...)` (`...plan5-6-orchestrator-loop.md:101-108`). `scan_scope()` filters with `r.get("pipeline_id") == pipeline_id` (`kdb_compiler/kdb_scan.py:471-473`). `load_manifest_sources()` returns hash, mtime, size, file type, binary flag, and `last_compiled_hash`, but not `pipeline_id` (`kdb_compiler/kdb_scan.py:215-241`).

**Recommendation:** Fix Plan 5/6 to include `pipeline_id` in `load_manifest_sources()` before orchestrator work starts, and add a regression test: a source committed under pipeline `p1` must scan as `UNCHANGED` / `to_skip` on the next `p1` run. For older records without `pipeline_id`, choose an explicit migration policy rather than silently dropping them from scoped prior state.

### Finding 4 — Noise / metadata-only sources need a real manifest path

**Dimension:** D3 / D4  
**Severity:** High

**Issue:** The plan says noise sources are enriched, embedded, and committed as `metadata_only`, but it does not define how to do that with the shipped `source_state_update` API. `build_source_state_update()` cannot currently mark a non-binary text source as `metadata_only` and advance `last_compiled_hash` for a no-Pass-2 source.

**Evidence:** Plan Task 3 says noise routes to "commit metadata_only (manifest, no compile/graph)" (`docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md:116-118`). `source_state_update._seed_source_record()` sets non-binary sources to `compile_state="pending"` and `last_compiled_hash=None` (`kdb_compiler/source_state_update.py:74-98`). `apply_compile_sources()` marks entries in `last_scan.to_compile` that lack compiled output as `compile_state="error"` (`kdb_compiler/source_state_update.py:235-287`). The spec requires noise sources to be tracked so they are not re-enriched every run (`docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md:293-299`).

**Recommendation:** Add an explicit metadata-only source-state helper or a documented `build_source_state_update()` mode for Pass-1 noise results. It should set `compile_state="metadata_only"`, `last_compiled_hash=post_embed_hash`, source hash/mtime/size to the post-embed values, and `pipeline_id`. Do not fake this as binary; it is a text source intentionally gated out of Pass-2.

### Finding 5 — Post-embed provenance is incomplete

**Dimension:** D2 / D4  
**Severity:** Medium

**Issue:** Task 1 adds `post_embed_hash`, but the commit machinery also records `current_mtime` and `size_bytes`, and `patch_applier` uses `current_mtime` for wiki frontmatter. Reusing the pre-enrich `scan_entry` after embedding frontmatter records stale mtime/size and stale raw_mtime in rendered pages.

**Evidence:** Plan Task 1 returns only `body` and `post_embed_hash` (`docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md:31-60`). `_commit_source` says the scan entry carries `current_hash = post_embed_hash` but does not mention restatting mtime or size (`...plan5-6-orchestrator-loop.md:75-85`). Source-state records consume `current_mtime` and `size_bytes` (`kdb_compiler/source_state_update.py:74-98`, `146-204`). `patch_applier` derives page `raw_mtime` from scan metadata (`kdb_compiler/patch_applier.py:145-181`).

**Recommendation:** After `embed_frontmatter()`, return or restat all post-embed file metadata: `post_embed_hash`, `post_embed_mtime`, and `post_embed_size_bytes`. Build the single-source scan from those values, not from the original scan entry except for path/action/previous fields.

### Finding 6 — `compile_source()` still has an unclassified reconcile exception path

**Dimension:** D3  
**Severity:** Medium

**Issue:** The orchestrator plan routes on `result.ok` and `result.failure_stage`, but the shipped `compile_source()` can still raise from reconcile instead of returning `CompileSourceResult`. That turns a pre-commit source failure into a generic orchestrator exception unless the loop wraps it explicitly.

**Evidence:** Plan Task 3 expects `if not result.ok: return fail-fast(stage=result.failure_stage)` (`docs/superpowers/plans/2026-05-29-task91-plan5-6-orchestrator-loop.md:118-122`). Current `compile_source()` catches context and canonicalize failures but calls `reconcile.reconcile(...)` without a wrapper (`kdb_compiler/compiler.py:681-699`). `reconcile.reconcile()` can raise `ReconcileError` for unknown findings or missing source ids (`kdb_compiler/reconcile.py:220-241`).

**Recommendation:** Either update `compile_source()` before Plan 6 to return `failure_stage="reconcile"` on `ReconcileError`, or have the orchestrator wrap the entire `compile_source()` call and classify unexpected exceptions as pre-commit case (a) with the source id and exception type. Prefer fixing the core result contract once.

## 3. What Checked And Found Sound

- The high-level loop shape matches the spec: registry selection, one shared read-write GraphDB connection, scoped scan, compile queue before reconcile queue, deferred orphan marking, and fail-fast.
- `compile_source()` is now correctly produce-don't-write; moving stage 8 into the orchestrator resolves the Plan 1 dirty-disk problem.
- `apply_compile_result(..., detect_orphans=False)` is the right per-source graph-sync call; orphan marking belongs in one finalize pass.
- `build_source_state_update()` is per-source-safe for signal commits as claimed; it iterates only the supplied `last_scan.files` and `to_reconcile`.
- The accepted cross-source wiki last-writer-wins trade-off is consistently represented: GraphDB remains authoritative, with wiki drift left to audit/repair.
- The isolated sandbox layout is correct: making the sandbox directory the `vault_root` keeps wiki, state, prompt, and graph under one disposable tree.
