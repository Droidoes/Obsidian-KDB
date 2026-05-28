# Task #91 v0.1 Blueprint — Codex Review

## Summary

The v1 simplification is sound. Replacing watcher/event/batching machinery with a manual `kdb-orchestrate` command is the right scope for a single-user, infrequent workload, and manifest-diff is enough to recover the lifecycle events v1 actually needs. The blueprint is not yet implementation-ready, though: §4 describes a cleaner per-source workflow than the current CLIs expose. v0.2 should pin the exact execution unit for Pass-1 and Pass-2, make source deletion replayable by reusing the existing run-journal/sidecar pattern, and correct the manifest-consistency claim around graph-sync failures.

## Findings

### F-1: Pass-1 CLI success semantics do not currently support fail-fast (severity: high)

Blueprint §4 lines 128-134 and §7.1 lines 271-272 assume `kdb_enrich(source)` raises or returns a failing status on Pass-1 failure. Current `kdb-enrich` does not enforce that. In `kdb_compiler/ingestion/kdb_enrich.py:65-80`, each `enrich_one()` result is printed and counted, but `enrich_failed` does not cause a nonzero exit. `main()` also returns `None`, so a subprocess caller will see success even if one source failed.

That matters because D-91-8 depends on first-failure detection. If `kdb-orchestrate` shells out to `kdb-enrich`, it can silently proceed to Pass-2 after failed or missing frontmatter. v0.2 should specify one of these:

- call `enrich_one()` directly and treat `outcome == "enrich_failed"` as exit 3;
- or amend `kdb-enrich` to return nonzero when any source has `enrich_failed`;
- or add a single-source `kdb-enrich --fail-on-error` mode for orchestrator use.

Direct function use is cleaner for v1 because the orchestrator already needs the scan entry and source id.

### F-2: Positional `kdb-enrich` gives the wrong source_id for orchestrated sources (severity: high)

Current positional mode resolves source ids as `s.name` (`kdb_compiler/ingestion/kdb_enrich.py:83-94`). That is acceptable for ad-hoc enrichment but wrong for `kdb-orchestrate`, whose graph/manifest source identity is vault-relative (`KDB/raw/...` or another vault-relative path). If the orchestrator passes absolute paths positionally, Pass-1 sidecars/journals record only basenames, while Pass-2 and GraphDB use full source ids.

This is not a frontmatter-write blocker, but it breaks audit lineage and makes per-source troubleshooting harder. v0.2 should state that `kdb-orchestrate` must call `enrich_one(source_path=abs_path, source_id=scan_entry.path, ...)` directly, or add a CLI surface that accepts explicit `(path, source_id)` pairs.

### F-3: Current Pass-2 runner is aggregate, not true per-source fail-fast (severity: high)

Blueprint §4 lines 128-146 models `kdb_compile(source)` as one source at a time. Existing `compiler.run_compile()` plans all `scan.to_compile` jobs, loops through all jobs, accumulates errors, and only returns `success=False` after the full job list has been attempted (`kdb_compiler/compiler.py:509-605`). The higher-level `kdb-compile` pipeline then validates and persists an aggregate `compile_result`.

That means the blueprint's D-91-8 behavior is not achieved by simply invoking today's `kdb-compile` after a multi-source scan. To preserve fail-fast, v0.2 should define the concrete unit:

- preferred: build a one-source synthetic scan per source and call the existing full `kdb_compile.compile()` pipeline once per source;
- acceptable: add a `fail_fast=True` option to `compiler.run_compile()` and the surrounding `kdb_compile.compile()` stages;
- avoid: run one aggregate compile and infer fail-fast after the fact, because several later sources may already have spent LLM calls.

The one-source synthetic scan is simpler and aligns with §7.2's "previously committed sources are now UNCHANGED" invariant.

### F-4: Manifest consistency invariant is too strong for graph-sync failures (severity: critical)

Blueprint §7.1 treats graph-sync error as a Pass-2 compile failure, and §7.2 says the failing source is "NOT committed." Current `kdb-compile` writes wiki pages and `manifest.json` before graph sync. Stage 9 writes the manifest (`kdb_compiler/kdb_compile.py:560-563`); Stage 10 then archives sidecars and syncs GraphDB (`kdb_compiler/kdb_compile.py:589-633`). On graph-sync failure, the compile result is replayable and the command returns failure, but the manifest and wiki may already reflect the source.

This is not necessarily a code bug; it is the existing D50 trade-off. But Task #91 should not promise "manifest stays in pre-failure state" for graph-sync failures. v0.2 should split compile failures into:

- pre-commit failures: model, validation, canonicalization, patch apply, manifest write; failing source not committed;
- post-manifest graph-sync failures: manifest/wiki committed, live graph stale, replayable sidecar exists, remediation is `graphdb-kdb rebuild`.

Then `kdb-orchestrate` can still fail-fast with exit 4, but the run summary must say "committed-but-graph-sync-failed" rather than "not committed."

### F-5: OQ-91-1 should not invent a parallel deletion mechanism; reuse the replayable scan sidecar shape (severity: high)

Source deletion is already handled graph-side when a compile replay includes `last_scan.to_reconcile=[{"type":"DELETED", ...}]`: `_handle_source_deleted()` drops SUPPORTS, marks Source deleted, and orphan detection flags dependent entities (`graphdb_kdb/ingestor.py:224-246`). The missing piece in Task #91 is not graph semantics; it is ensuring a deletion-only orchestration run writes a replayable journal + sidecar so rebuild sees the DELETED op.

Recommendation: choose OQ-91-1 option (a), but implement it as a normal replayable producer event with an empty `compile_result` plus `last_scan.json` carrying DELETED/MOVED reconciliation, not as a new cleanup event type. Task #68's cleanup event is for entity retractions after orphan cleanup; source deletion is scan reconciliation. Reusing the compile-event sidecar keeps `ObsidianRunsAdapter.apply_compile_result()` as the replay path and avoids a third mutation channel.

### F-6: `scan_result.new + scan_result.changed` is not the current scan shape (severity: medium)

The pseudocode uses `scan_result.new`, `scan_result.changed`, `scan_result.moved`, and `scan_result.deleted` (§4 lines 128-157). Current `ScanResult` has `files[]`, `to_compile[]`, `to_reconcile[]`, and summary counts; DELETED lives only in `to_reconcile[]`. This is fine for pseudocode, but v0.2 should state the normalized orchestrator view explicitly:

- `compile_queue = files where path in to_compile and action in {"NEW", "CHANGED", "MOVED" if hash differs}`
- `move_queue = to_reconcile where type == "MOVED"` and not already covered by compile work
- `delete_queue = to_reconcile where type == "DELETED"`

This matters because current eligibility is hash-based (`to_compile`), not action-name-based. A moved file with unchanged content should be path-only; a moved+changed file will probably appear as NEW + DELETED unless richer move detection is added.

### F-7: Multi-root source identity needs a collision invariant (severity: medium)

Adding `root_id` to `last_scan.json` (§5.6) is useful, but D-91-1 says manifest schema is unchanged and path-keyed. That is workable only if `path` remains a unique vault-relative POSIX path for every root. v0.2 should explicitly state that manifest identity is still `path`, while `root_id` is classification/provenance metadata only. It should also add a test that overlapping roots cannot emit duplicate current rows for the same vault-relative path.

The example excludes `KDB/` from the vault-in-place root, which prevents the obvious overlap with `KDB/raw`. Keep that as a hard default, not user-removable unless the user disables the `kdb-raw` root.

## OQ Takes

### OQ-91-1 (source-retraction journal)

Take option (a): source deletion must be replayable. Direct manifest+graph removal is the same class of bug Task #68 already closed. However, source deletion should be replayed through the existing compile-run sidecar shape: `event_type` absent/`compile`, empty `compiled_sources`, and `last_scan.to_reconcile` containing DELETED. The graph adapter already knows how to apply that. Then `kdb-clean orphans --apply` can run afterward and emit its own Task #68 cleanup event for actual entity deletion. Cost is low: mostly journal/sidecar emission and tests around deletion-only runs.

### OQ-91-2

Use separate `state/scan_roots.json`. Config does not belong in the volatile manifest ledger. Add validation for duplicate root ids, missing paths, and paths outside the vault unless explicitly allowed.

### OQ-91-3

Scope MOVED detection per root for v1. Cross-root same-hash should be NEW + DELETED unless a future explicit "promote from raw to in-place" workflow is designed. Cross-root move inference is too likely to misclassify copies.

### OQ-91-4

Yes to `state/last_orchestrate.json`. Keep it an overwrite-only operational summary, not a replay journal. Include start/end, exit code, failing source if any, committed sources, and whether failure was pre-commit or post-manifest graph-sync.

### OQ-91-5

Unknown feeder name should be an error. With explicit `--feeders=NAME`, typo-as-warning is worse than fail-fast.

### OQ-91-6

Exit 0 with a report. Current `kdb-clean orphans --apply` already returns success when nothing is reaped.

### OQ-91-7

No lock file for v1. Document "do not run concurrently." If the implementation adds `last_orchestrate.json`, it can opportunistically note a running state, but it should not become a lock protocol.

## Probes / Questions

1. Should `kdb-orchestrate` call Python functions directly rather than subprocess CLIs? Direct calls give correct source ids, structured `EnrichResult`, and structured `CompileRunResult`. Subprocesses make exit-code contracts more brittle.

2. Should source deletion-only runs always create a run journal even when there are no NEW/CHANGED sources? My answer is yes, because otherwise rebuild misses the deletion.

3. Should scan errors abort if they are only unreadable excluded paths? The config loader should apply excludes before stat/hash where possible so ignored trees cannot fail the run.

4. Does vault-in-place scanning need default excludes beyond `KDB/`, `.obsidian/`, `.trash/`? I would add `.git/`, `.venv/`, `node_modules/`, and possibly `Templates/` as default disabled-or-excluded candidates, with Joseph able to opt in later. The `.md` rule removes most noise, but generated documentation under dependency folders can still be expensive.

## Suggestions for v0.2 Fold

1. Define the orchestrator execution unit precisely: for each source, Pass-1 direct `enrich_one()`, then one-source Pass-2 compile pipeline using a synthetic scan or a new `source_filter`/`fail_fast` path.

2. Replace the blanket §7.2 invariant with a two-phase failure model: pre-commit failure leaves manifest untouched for that source; post-manifest graph-sync failure leaves committed replayable state and requires rebuild/live-sync recovery.

3. Resolve OQ-91-1 as replayable source reconciliation via existing compile-event sidecars, not direct removal and not a new cleanup event type.

4. Amend scan-root spec: path identity remains vault-relative; `root_id` is metadata; MOVED matching is per-root; overlapping roots that emit the same path are a config error.

5. Require `kdb-orchestrate --dry-run` to report all three queues: compile, move-only, delete-only. That is the cheapest way to validate multi-root scope before spending LLM calls.

6. Add implementation tests for: failed Pass-1 returns exit 3, first failed Pass-2 stops later sources, deletion-only run writes replayable sidecar, graph-sync failure is reported as committed/rebuild-needed, unknown feeder exits 1, and cleanup empty-set exits 0.
