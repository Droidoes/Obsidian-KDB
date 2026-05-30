# Task #91 v0.1 Blueprint — Deepseek Review

**Reviewer:** deepcode CLI / Deepseek
**Artifact:** `docs/task91-kdb-orchestrate-blueprint.md` v0.1
**Date:** 2026-05-27

---

## Summary

The v1 simplification is architecturally sound — collapsing the elaborate filesystem-watching + event-taxonomy design into a single `kdb-orchestrate` command with manifest-diff routing is the right call for a single-user infrequent workload. The workflow algorithm (§4) is a clean seven-step pipeline that correctly sequences feeders → scan → enrich → compile → manifest-update → cleanup. However, there is one critical implementation gap (F-1: per-source manifest atomicity doesn't match `source_state_update`'s batch API) and one load-bearing design decision (OQ-91-1: source-retraction journal) where the Task #68 precedent demands option (a). I recommend proceeding to v0.2 after addressing F-1 and OQ-91-1, with most other findings being polish-level.

---

## Findings

### F-1: Manifest consistency invariant doesn't hold with current `source_state_update` API (severity: critical)

**Where:** §4 workflow lines 128–146 + §7.2 manifest consistency invariant.

**What:** The pseudocode calls `source_state_update(source, enrich_result, compile_result)` per-source inside the fail-fast loop (lines 142–146), implying per-source atomic manifest writes. But `source_state_update.build_source_state_update()` (`source_state_update.py:427`) takes `(prior, last_scan, compile_result, ctx)` — it applies the **full** scan result and the **full** compile result in one batch call. There is no per-source update API.

**Why it matters:** Under D-91-8 fail-fast, the §7.2 invariant states:
> "On abort, the manifest reflects all sources processed BEFORE the failing source (those are already committed in their atomic updates)."

This invariant can only hold if each source's manifest update is committed independently before the next source begins. The existing `build_source_state_update` cannot do this — it expects the complete `last_scan` and `compile_result` at once. Two resolutions:

- **(A) Add a per-source update function** to `source_state_update.py` (e.g., `apply_single_source(prior, source_scan_entry, source_compile_output, ctx)`). The orchestrator loads manifest, applies one source, atomic-writes, continues. This is the correct path — it preserves fail-fast semantics and the invariant.
- **(B) Accumulate all enrich/compile results in memory, call `build_source_state_update` once at end.** This contradicts D-91-8: if source 8 of 12 fails, sources 1–7 were processed but their manifest updates never committed. On re-run, they'd be re-processed (CHANGED → CHANGED ≠ compiled_hash). More wastefully, if the failure was a transient LLM error, sources 1–7 would be re-enriched and re-compiled unnecessarily.

**Resolution:** Add `apply_source_enrich_and_compile` (or similar) to `source_state_update.py` as a Phase A implementation prerequisite. The batch `build_source_state_update` can remain as the "apply all at end" path used by the existing `kdb-compile` pipeline — the orchestrator just doesn't use it.

**Convergence signal:** I suspect Codex will flag this too — it's the single biggest gap between the pseudocode's assumptions and the current codebase's API surface.

---

### F-2: Deleted sources leave Source nodes and SUPPORTS edges in GraphDB (severity: high)

**Where:** §4 Step 6 (`source_state_remove(source)`) + OQ-91-1.

**What:** Step 6 removes the source from the manifest. Step 7 runs `kdb-clean orphans`, which prunes orphan **entities** via `DETACH DELETE`. It does NOT prune:
- Deleted sources' Source nodes in GraphDB (the Source node was ingested during compile and has no cleanup path)
- Deleted sources' SUPPORTS edges (these are `DETACH DELETE`'d only if the target Entity is also orphaned — but popular entities with multiple supporting sources survive)

A source deleted from manifest but with a surviving Source node in GraphDB would:
- Re-appear on `graphdb-kdb rebuild` (the compile journal that created it is still in the stream)
- Leave SUPPORTS edges that artificially inflate T1 context for remaining sources
- Cause `graphdb-kdb verify` to report drift

The entity side is handled by Step 7. The **Source-node side is unhandled in the current blueprint.** This directly feeds into OQ-91-1 — see dedicated section below.

---

### F-3: Vault-in-place default excludes are incomplete for hidden directories (severity: medium)

**Where:** §6.1 default excludes.

**What:** The excludes block `KDB/`, `.obsidian/`, `.trash/` — but the walker traverses ALL directories and filters by `.md` extension. Any hidden directory containing `.md` files would be ingested. Specific cases:
- `.github/ISSUE_TEMPLATE/*.md` — would be ingested as sources
- `.cursor/rules/*.md` — AI editor config, would be ingested
- `.vscode/` — less likely to have `.md` but possible

The `.md` filter alone doesn't protect against this — these are valid markdown files. Recommendation: add a blanket hidden-directory exclude: skip any directory whose name starts with `.` (except the explicit allowlist `[]` for now). Since `kdb_scan.py` already prunes symlinked subdirs (line 124), adding a prefix-based skip is a one-line change in the walker. Alternatively, add `.git/` and common tool directories to the default excludes.

---

### F-4: `scan_result.new` and `scan_result.changed` don't exist as attributes on `ScanResult` (severity: medium)

**Where:** §4 pseudocode line 129: `for source in scan_result.new + scan_result.changed`

**What:** The `ScanResult` dataclass (`types.py:134`) has `files: list[ScanEntry]` but no `.new` or `.changed` convenience properties. Each `ScanEntry` carries an `action` field (`"NEW"`, `"CHANGED"`, etc.). The pseudocode implies filtered views. Similarly, `scan_result.moved` and `scan_result.deleted` don't exist.

**Resolution:** Add filtered properties or filtered-accessor methods to `ScanResult` during implementation. Trivial fix, but the pseudocode should acknowledge the gap — otherwise the implementation phase starts with an API that doesn't match the spec.

---

### F-5: No re-entry guard against feeders producing no output (severity: low)

**Where:** §8.3 sequencing + feeder contract.

**What:** If `--feeders=rss` is specified and the RSS feeder runs but produces zero new files (no new articles since last pull), the orchestrator proceeds to scan, finds nothing changed, and exits 0. This is correct behavior. But the blueprint doesn't specify what the orchestrator reports in this case — does it say "feeder rss: 0 new files" or stay silent? The `--verbose` path should surface this for observability; the non-verbose path can stay silent (0 changes = nothing to report).

---

## OQ Takes

### OQ-91-1: Source-retraction journal — pick (a), new `event_type: "source_retraction"`, following Task #68 pattern

**Position:** (a) — write a replayable journal event. **Not** (b) — direct manifest+graph removal without a journal.

**Reasoning:**

Task #68's history is the governing precedent (read `docs/archive/tasks/task68-cleanup-retraction-event-blueprint.md` §1–§2):

> "The historical compile runs that originally emitted the reaped pages are still in that stream — so on replay, `ingestor.apply_compile_result` Phase 3 re-creates the reaped entities as active. The cleanup is invisible to replay."

The same dynamic applies here: a source was compiled → its compile journal is in `state/runs/` → `graphdb-kdb rebuild` replays it → the Source node + SUPPORTS edges are re-created. Without a retraction event in the same stream, the deletion is invisible to replay.

**Implementation shape (proposed):**

A new `event_type: "source_retraction"` journal, following the Task #68 cleanup journal structure:

```json
{
  "schema_version": "2.2",
  "event_type": "source_retraction",
  "run_id": "source-retraction-<orchestrate-run-id>",
  "started_at": "...",
  "finished_at": "...",
  "success": true,
  "summary": {
    "deleted_source_count": 3,
    "deleted_source_ids": ["KDB/raw/old-note.md", "Daily Notes/2025-01-01.md"]
  },
  "artifacts": {
    "retraction_path": "state/runs/<run_id>/retraction.json"
  }
}
```

The retraction sidecar carries:
```json
{
  "event_type": "source_retraction",
  "run_id": "...",
  "deleted_source_ids": ["KDB/raw/old-note.md", ...],
  "deleted_source_hashes": {"KDB/raw/old-note.md": "sha256:..."}
}
```

**Graph sync:** `apply_source_retraction` in `ingestor.py` would, for each `deleted_source_id`:
1. `MATCH (s:Source {source_id: $sid}) DETACH DELETE s` — removes the Source node and all its SUPPORTS/SUPPORTS edges. Entities are untouched (entity pruning remains `kdb-clean orphans`'s job).

**Adapter routing:** `ObsidianRunsAdapter.is_eligible` gains a branch for `event_type: "source_retraction"`. `load_payload` loads `retraction.json`. `apply` routes to `apply_source_retraction`.

**Cost:** ~60–80 lines of adapter/routing code + ~40 lines in `ingestor.py`. The Task #68 cleanup journal infrastructure already exists — this is a second event type in the same framework, not a new framework.

**Why not recycle the Task #68 cleanup event:** The cleanup event's retraction payload carries `retracted_slugs` (Entity slugs). Source deletion carries `deleted_source_ids` (Source IDs). Mixing them in one event type would make the payload shape ambiguous and the adapter routing fragile. Separate event types with clean payload shapes.

**Why not option (b):** Direct manifest+graph removal is simpler but non-replayable. Task #68 proved empirically (25 reap-residue entities after rebuild) that non-replayable deletions ALWAYS resurface. The lesson is encoded in the Task #68 blueprint §2 — "Flag-only is exactly what is already broken." If we ship option (b), we file a follow-up bug within weeks.

**Implementation note:** The source-retraction journal should be written in Step 6 (DELETED processing), before `source_state_remove` commits the manifest change. Write order: retraction sidecar → manifest removal → journal write (same crash-consistency discipline as Task #68 §6.1).

---

### OQ-91-2: Scan-roots config location — confirm separate `scan_roots.json`

**Position:** Agree with the lean. Separate file is cleaner: config is version-controlled, state is not. Placing config in `manifest.json` would make it part of the state ledger, which complicates migration and makes the manifest less self-describing (is the config block part of the current state, or a bootstrap artifact?). Keep them separate.

---

### OQ-91-3: MOVED detection per-root — confirm per-root

**Position:** Agree with D-91-9 candidate (per-root). Cross-root same-hash detection would misclassify a user copying `KDB/raw/essay.md` to `AIML/essay.md` as a MOVE when it's actually a NEW entry in a different root. Per-root scoping also simplifies the Phase C rename pass — the hash buckets are already partitioned by root_id. Implementation: add `root_id` to `_RawFile`; in `classify()`, partition current and prior by root, run Phase B/C/D independently per root, merge results.

---

### OQ-91-4: Per-run summary `last_orchestrate.json` — yes, with caveat

**Position:** Yes, but slim the payload. The summary should include:
- `run_id`, `started_at`, `finished_at`
- Exit code + exit reason string (not just the integer)
- Counts: `feeders_run`, `sources_scanned`, `sources_enriched`, `sources_compiled`, `sources_moved`, `sources_deleted`, `sources_failed`
- `manifest_delta`: {added, removed, changed} counts

Do NOT include full source lists (those are in `last_scan.json`). The file should be ~200 bytes for a typical run, not a replica of `last_scan.json`.

---

### OQ-91-5: Unknown feeder name → error

**Position:** Agree with the lean (error). This is consistent with D-91-8 fail-fast. If the user types `--feeders=rsss` (typo), a silent skip would be confusing — they'd think the feeder ran when it didn't. Error, exit code 1, message: `"feeder 'rsss' not found in feeders.json; registered: rss, podcasts, gmail"`.

---

### OQ-91-6: Cleanup empty-set (0 orphans) → exit 0 with report

**Position:** Agree with the lean. `kdb-clean orphans --apply` already handles the empty case (line 238–240 of `kdb_clean.py`: `"nothing to reap — already clean."`). Verify the exit code — it should be 0, and looking at line 240, it returns 0. The orchestrator just inherits this behavior.

---

### OQ-91-7: Re-entry safety — lean "no lock-file" is correct for v1

**Position:** Agree with the lean. A single user manually triggering from a terminal won't fire the command twice concurrently. If we add a lock-file, we're designing for a multi-user scenario that D-91-7 explicitly deferred to v2. However, document the risk in the CLI help text: `"kdb-orchestrate is not re-entrant — do not run concurrent instances against the same vault."`

---

## Probes / Questions

**Probe 1: Does the `kdb-enrich` CLI exist and accept a single-source invocation?**

The blueprint calls `kdb_enrich(source)` per-source. The current Pass-1 enrichment (Task #89) is invoked via CLI or Python API — but I need to verify it accepts a single-source mode. If `kdb-enrich` only supports batch mode (all files in a directory), the orchestrator would need to call it with a single file path. This is resolvable at implementation time but worth confirming.

**Probe 2: Step 4 processes NEW before CHANGED — does order matter?**

The pseudocode iterates `scan_result.new + scan_result.changed`. If a NEW source and a CHANGED source reference the same entity, enrich+compile order shouldn't matter (each is independently processed). But if they reference each other (cross-references), order could affect context snapshots. Since context is built from GraphDB (not from other sources being processed in the same run), this is a non-issue — GraphDB state is stable during the run. Confirmed safe.

**Probe 3: What if `--dry-run` reports changes but feeders have already run?**

The workflow runs feeders (Step 1) before the dry-run check (Step 3). If `--dry-run` is specified, feeders still fire, potentially pulling new content into `KDB/raw/` that the dry-run then reports. Is this intended? The feeder output is real filesystem state — it can't be rolled back. Two options: (a) feeders should NOT run under `--dry-run`, or (b) feeders run but the orchestrator reports "WARNING: feeders ran; files written to KDB/raw/ — re-run without --dry-run to process." I lean (a) — `--dry-run` should mean "no side effects," and feeders are side-effectful by definition.

**Probe 4: `kdb_scan` currently relativizes paths as `KDB/raw/...` — how does vault-in-place relativization work?**

The current `_rel_to_vault` function (`kdb_scan.py:164`) computes `abs_path.relative_to(raw_abs.parent.parent)` — vault-relative. For vault-in-place roots, the raw_abs equivalent would be the vault root itself, so `relative_to(vault_root)` gives paths like `AIML/foo.md`. This is correct for manifest path-keying. But the `_rel_to_vault` function is hardcoded for `KDB/raw/` — the multi-root rewrite needs a generalized `_rel_to_vault(abs_path, root_abs, vault_root)` that handles different root-to-vault relationships.

---

## Suggestions for v0.2 Fold

1. **Critical — F-1 (per-source manifest atomicity):** Add `apply_source_enrich_and_compile` to `source_state_update.py` as a Phase A prerequisite. Document the new API surface in the blueprint before TDD starts.

2. **High — OQ-91-1 (source-retraction journal):** Ratify option (a) in v0.2. Add new `event_type: "source_retraction"` to the producer contract and `ObsidianRunsAdapter`. Extend `ingestor.py` with `apply_source_retraction`. Implement alongside Step 6 in Phase C.

3. **High — F-2 (Source node cleanup):** Add explicit Source-node cleanup to the workflow: after `source_state_remove`, also DETACH DELETE the Source node from GraphDB (as part of the source-retraction journal's live-sync path). Without this, `graphdb-kdb verify` will report drift.

4. **Medium — F-3 (hidden directory excludes):** Add `.*/` glob exclude to vault-in-place default excludes, or add `.git/`, `.github/`, `.cursor/`, `.vscode/` explicitly. Document that users can override.

5. **Medium — F-4 (ScanResult convenience accessors):** Add filtered properties to `ScanResult` or document the list-comprehension pattern in the implementation plan.

6. **Low — Probe 3 (dry-run + feeders):** Clarify in the blueprint: `--dry-run` skips feeder execution. Add to §3.2 flags table.

7. **Low — Probe 4 (path relativization):** Generalize `_rel_to_vault` for multi-root support in Phase A implementation notes.
