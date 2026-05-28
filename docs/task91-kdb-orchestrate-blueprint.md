# Task #91 — `kdb-orchestrate`: End-to-end Ingestion Orchestrator + Extended `kdb_scan.py`

**Status:** v0.2 ratified (2026-05-27 evening) — Joseph-ratified D-91-1..D-91-14 after panel β fold (Codex + Deepseek, 2/2 guardrail-clean, 2 critical + 1 high-convergent + 4 medium + 7 OQs resolved). v0.1 status: drafted 2026-05-27 evening, reviewed via panel β, folded into v0.2 same evening.

**Parent:** Task #88 (Ingestion System). **Subsumes:** Component #3 (Trigger) + Component #6 (Orchestrator) from #88 v0.2 blueprint, per Joseph's v1 simplification 2026-05-27. **Sibling/orthogonal:** Component #5 (Move-from-compile survey) stays separate.

**Anchors:** `[[feedback_no_imaginary_risk]]`, `[[feedback_concrete_first_extract_later]]`, `[[feedback_name_must_match_contents]]`, `[[project_tunnel_from_both_ends_pivot]]`.

---

## 1. Strategic context

Task #88 v0.2 designed Component #3 (Trigger) as an elaborate filesystem-watching + 8-event-taxonomy + batching subsystem, and Component #6 (Orchestrator) as a separate thin entry-point script. That decomposition was inherited from reviewer-driven elaborations, none of which are load-bearing for the actual v1 workload (single-user, manual-trigger, infrequent runs, vault ≤5k files).

**Joseph's v1 simplification (2026-05-27):**
> "We can just manually trigger a scan against a given ingestion-pipeline repo... compare the manifest against last scan, anything new we send to feeder → ingestion pipeline → compiler pipeline → update manifest etc."

This collapses #3 + #6 into a single conceptual operation: **scan-and-diff-then-route**. Implementation-wise it splits into two artifacts:
- **Extended `kdb_scan.py`** — walks multiple scan roots, diffs against the unified manifest, emits a change ledger
- **`kdb-orchestrate` CLI** — thin wrapper that wires `[optional] feeders → kdb_scan → kdb-enrich → kdb-compile → kdb-clean orphans`

This finishes the tunnel-from-both-ends pivot's "ship ONE end-to-end tunnel first" discipline. Component #5 (move-from-compile survey) remains orthogonal — a passive deliverable that doesn't gate v1 ship.

**When v0.2's elaborate Component #3 design WOULD become load-bearing (v2+ revisit triggers):**
- Multiple parallel source-feeders firing independently → need event-batching
- Real-time / scheduled / watcher-based ingestion → need polling
- Multi-user shared state → need locking
- High-churn vault (>10k files, frequent changes) → need incremental indexing

None apply to v1. Captured here so future-us knows what triggers a redesign.

---

## 2. Decision log

| ID | Decision | Date | Source |
|---|---|---|---|
| **D-91-1** | Single unified `manifest.json` at `~/Obsidian/KDB/state/manifest.json` (no rename, no relocation); schema unchanged from Task #73 v3.0 — already path-keyed | 2026-05-27 | Joseph ratification |
| **D-91-2** | File-type hard rule for v1: `.md` only. Drop `.markdown` and `.txt` from current `_MARKDOWN_EXTS` allowlist | 2026-05-27 | Joseph ratification |
| **D-91-3** | Orphan-cascade at scan-time: policy (a) hands-off — scan emits DELETED entries, does NOT cascade-prune entities | 2026-05-27 | Joseph ratification |
| **D-91-4** | `kdb-clean orphans` runs as final step of every `kdb-orchestrate` E2E run — full reconciliation per run; separation preserved (scan stays simple, cleanup is its own explicit step) | 2026-05-27 | Joseph refinement |
| **D-91-5** | Orchestrator command name: `kdb-orchestrate` (NOT `kdb-ingest` — the latter is too narrow given the command runs the FULL pipeline end-to-end through Pass-2 + graph sync + cleanup) per `[[feedback_name_must_match_contents]]` | 2026-05-27 | Joseph naming call |
| **D-91-6** | Task #91 subsumes Component #3 (Trigger) and Component #6 (Orchestrator) per v1 simplification; Component #5 (move-from-compile survey) stays orthogonal | 2026-05-27 | Joseph simplification |
| **D-91-7** | Real-time / scheduled / watcher-based triggering documented as OUT of v1 scope; v2 roadmap line in §11 below + `task88-ingestion-pipeline-blueprint.md` §6.2 | 2026-05-27 | Joseph deferral |
| **D-91-8** | **Fail-fast at first source failure.** If any source fails Pass-1 enrich OR Pass-2 compile, abort the whole `kdb-orchestrate` run immediately. No skip-and-continue; no partial commit. Manifest stays in known-good pre-failure state (subject to D-91-13 two-phase refinement). | 2026-05-27 | Joseph call (overrode assistant's skip-and-continue lean) |
| **D-91-9** | MOVED detection scoped per-root (cross-root same-hash files → independent NEW + DELETED, NOT MOVE). Prevents `KDB/raw/foo.md` + `AIML/foo.md` from being misclassified as a move. | 2026-05-27 | 2/2 panel β convergence (Codex OQ-91-3 + Deepseek OQ-91-3) |
| **D-91-10** | Per-run summary at `state/last_orchestrate.json` — slim payload: `run_id`, `started_at`, `finished_at`, exit code + exit reason string, counts (`feeders_run`, `sources_scanned`, `sources_enriched`, `sources_compiled`, `sources_moved`, `sources_deleted`, `sources_failed`), `manifest_delta` {added, removed, changed}. NO full source lists (those live in `last_scan.json`). ~200 bytes typical. | 2026-05-27 | 2/2 panel β + Deepseek payload spec |
| **D-91-11** | `--dry-run` SKIPS feeder execution. Feeders are side-effectful by definition (write to filesystem); `--dry-run` means no side effects. Resolves Deepseek Probe 3. | 2026-05-27 | Deepseek panel β unique catch |
| **D-91-12** | Orchestrator calls Python APIs directly (`enrich_one()`, in-process compile pipeline) — NOT subprocess CLIs. Required for: (a) D-91-8 fail-fast (subprocess exit-code contracts are brittle); (b) correct vault-relative source_id (positional CLI mode currently uses basename, breaks audit lineage). | 2026-05-27 | 2/2 panel β convergence (Codex F-1+F-2+F-3 + Deepseek Probe 1) |
| **D-91-13** | **Two-phase failure model.** D-91-8 fail-fast distinguishes: (a) **pre-commit failures** (model error, validation, canonicalization, patch apply, manifest write) — failing source NOT committed, manifest untouched; (b) **post-manifest graph-sync failures** — manifest + wiki committed, replayable sidecar exists, live graph stale; remediation is `graphdb-kdb rebuild`. Orchestrator exits 4 in both cases but run summary distinguishes "not committed" vs "committed-but-graph-sync-failed". Respects existing D50 trade-off (Task #73). | 2026-05-27 | Codex F-4 critical (unique catch) |
| **D-91-14** | **Source-retraction via existing compile-event sidecar (OQ-91-1 Shape A).** Source deletion replays through existing `event_type: "compile"` event with empty `compiled_sources` + DELETED entries in `last_scan.to_reconcile`. Uses existing `apply_compile_result()` + `_handle_source_deleted()` path (`ingestor.py:224-246`). Zero new mutation channel; zero new event_type; zero new adapter routing. `kdb-clean orphans` runs afterward (D-91-4) for entity-side cleanup. Crash-consistent write order (sidecar → manifest → journal) per Task #68 §6.1. | 2026-05-27 | Joseph ratified Shape A over Deepseek's Shape B (new `event_type: "source_retraction"`); both shapes correct; Shape A wins on minimum-additional-code per v1 simplification spirit |

**D-91-8 trade-off captured for future revisit:**
- Pro (Joseph): debuggability (first error caught immediately, full context preserved, no cascading failures masking root cause); manifest consistency (no partial state); simplicity (no error-aggregation logic); aligned with `[[feedback_no_imaginary_risk]]` (no resume/retry/partial-success machinery)
- Con (assistant's prior lean): single bad source can block whole-vault progress when one file has e.g. malformed frontmatter the LLM rejects
- Revisit if: empirical operation shows single-source failures are frequent + unrelated to systemic bugs (a class indication that fail-fast is hurting throughput)

---

## 3. `kdb-orchestrate` CLI shape

### 3.1 Invocation

```
kdb-orchestrate [--feeders=NAME[,NAME...]] [--dry-run] [--verbose]
```

### 3.2 Flags (v1)

| Flag | Purpose | v1 behavior |
|---|---|---|
| `--feeders=NAME[,NAME...]` | Run named feeder scripts before scan | Default: skip. If specified, runs each feeder in listed order; fail-fast on feeder error |
| `--dry-run` | Scan + diff + report; no Pass-1, no Pass-2, no cleanup, no manifest mutation | Default: off |
| `--verbose` | Per-source progress reporting | Default: off |

**Flags explicitly NOT included in v1** (knobs without concrete need per `[[feedback_no_imaginary_risk]]`):
- `--skip-cleanup` — cleanup is part of "complete reconciliation per run" (D-91-4); if user needs to skip, they run sub-commands manually
- `--parallel=N` — sources processed sequentially in v1; parallelism is v2 concern
- `--resume-from=PATH` — fail-fast (D-91-8) makes resume-from unnecessary

### 3.3 Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Feeder error (when `--feeders=...` specified) |
| `2` | Scan or diff error |
| `3` | Pass-1 enrich error (D-91-8 fail-fast: aborted at first failing source) |
| `4` | Pass-2 compile error (D-91-8 fail-fast: aborted at first failing source) |
| `5` | Manifest-update error |
| `6` | Cleanup error (`kdb-clean orphans` final step) |

### 3.4 Output format

`stdout`: one-line summary per stage (`[scan] 1663 files scanned, 12 NEW, 3 CHANGED, 1 DELETED, 0 MOVED, 1647 UNCHANGED`); `--verbose` adds per-source progress lines.
`stderr`: errors only.
`state/last_scan.json`: full diff ledger (existing schema, extended for multi-root).
Optional `state/last_orchestrate.json`: per-run summary (start time, end time, sources processed, exit reason, manifest delta count).

---

## 4. Workflow algorithm

> **v0.2 rewrite** per panel β: uses direct Python API (D-91-12) with per-source atomic manifest commits (CR-1 / D-91-13). Replaces v0.1's subprocess-shelling pseudocode.

### 4.1 ScanResult shape normalization

Current `ScanResult` has `files: list[ScanEntry]` + `to_reconcile: list[ReconcileOp]` + summary counts; DELETED lives only in `to_reconcile[]` (Codex F-6 / Deepseek F-4). The orchestrator's normalized view uses filtered accessor properties added to `ScanResult` during Phase A:

```python
# Added to ScanResult during Phase A — Codex F-6 / Deepseek F-4
@property
def compile_queue(self) -> list[ScanEntry]:
    """NEW + CHANGED entries (content-hash differ vs manifest); excludes path-only MOVED."""
    return [e for e in self.files if e.action in ("NEW", "CHANGED")
            and self._is_in_to_compile(e.path)]

@property
def move_queue(self) -> list[ScanEntry]:
    """Path-only MOVED entries (content unchanged, path different); excludes MOVED+CHANGED."""
    return [e for e in self.files if e.action == "MOVED" and not self._is_in_to_compile(e.path)]

@property
def delete_queue(self) -> list[ReconcileOp]:
    """DELETED entries from to_reconcile."""
    return [op for op in self.to_reconcile if op.type == "DELETED"]
```

A MOVED+CHANGED file (rare) appears as NEW + DELETED unless richer move detection is added — captured as **OQ-91-8 (post-v0.2)**.

### 4.2 Pseudocode

```python
def kdb_orchestrate(feeders: list[str] | None = None,
                   dry_run: bool = False,
                   verbose: bool = False) -> int:
    """End-to-end ingestion orchestrator (D-91-1..D-91-14)."""

    run_id = generate_run_id()
    summary = OrchestrateRunSummary(run_id=run_id, started_at=now_local())

    # Step 1 (optional): trigger feeders — D-91-11 SKIP under --dry-run
    if feeders and not dry_run:
        for feeder_name in feeders:
            try:
                run_feeder(load_feeder(feeder_name))  # D-91-12: direct invocation
            except UnknownFeederError as e:
                return _exit(1, f"unknown feeder: {feeder_name}", summary)
            except FeederError as e:
                return _exit(1, f"feeder {feeder_name} failed: {e}", summary)
            summary.feeders_run += 1

    # Step 2: scan all configured roots, diff against manifest (D-91-1, D-91-9)
    try:
        scan_result = kdb_scan(
            roots=load_scan_roots_config(),     # state/scan_roots.json (OQ-91-2)
            file_type_allowlist={".md"},        # D-91-2
        )
        summary.sources_scanned = scan_result.summary.total
    except Exception as e:
        return _exit(2, f"scan failed: {e}", summary)

    # Step 3: dry-run short-circuit — report all three queues
    if dry_run:
        report_three_queues(scan_result.compile_queue,
                          scan_result.move_queue,
                          scan_result.delete_queue)
        return _exit(0, "dry-run complete", summary)

    # Step 4: process compile_queue (NEW + CHANGED) sequentially with fail-fast (D-91-8 + D-91-13)
    for scan_entry in scan_result.compile_queue:
        source_id = scan_entry.path  # vault-relative POSIX path (Codex F-2 fix)
        abs_path = scan_entry.abs_path

        # Pass-1 enrich — direct Python API (D-91-12)
        try:
            enrich_result = enrich_one(source_path=abs_path, source_id=source_id)
            if enrich_result.outcome == "enrich_failed":
                return _exit(3, f"enrich failed: {source_id} — {enrich_result.error}", summary)
            summary.sources_enriched += 1
        except Exception as e:
            return _exit(3, f"enrich exception: {source_id} — {e}", summary)

        # Pass-2 compile — one-source synthetic scan + full compile pipeline (D-91-12, Codex F-3 fix)
        try:
            single_source_scan = build_single_source_scan(scan_entry)
            compile_result = kdb_compile_pipeline(scan=single_source_scan, run_id=run_id)
            summary.sources_compiled += 1
        except CompilerError as e:
            # Pre-commit failure (D-91-13 phase a) — manifest untouched
            return _exit(4, f"compile failed (pre-commit): {source_id} — {e}", summary)
        except GraphSyncError as e:
            # Post-manifest failure (D-91-13 phase b) — manifest+wiki committed, graph stale
            summary.committed_but_graph_sync_failed = source_id
            return _exit(4, f"compile failed (post-manifest graph-sync): {source_id} — "
                          f"manifest committed; run `graphdb-kdb rebuild` to resync — {e}",
                       summary)

        # Per-source manifest atomic commit — D-91-13 phase a invariant (CR-1 fix)
        try:
            apply_source_enrich_and_compile(  # NEW API in source_state_update.py — Phase A prereq
                source_scan_entry=scan_entry,
                enrich_result=enrich_result,
                compile_result=compile_result,
                ctx=run_context,
            )
            summary.manifest_delta_changed += 1
        except Exception as e:
            return _exit(5, f"manifest update failed: {source_id} — {e}", summary)

    # Step 5: process move_queue (path update, no recompile)
    for scan_entry in scan_result.move_queue:
        try:
            apply_source_path_update(scan_entry)  # NEW API in source_state_update.py
            summary.sources_moved += 1
        except Exception as e:
            return _exit(5, f"manifest path-update failed: {scan_entry.path} — {e}", summary)

    # Step 6: process delete_queue — source-retraction via existing compile-event sidecar (D-91-14)
    if scan_result.delete_queue:
        try:
            # Emit a compile-event journal with:
            #   - empty compiled_sources
            #   - last_scan.to_reconcile carrying DELETED entries
            # Write order (crash-consistent per Task #68 §6.1):
            #   1. compile_result.json sidecar (empty compiled_sources)
            #   2. last_scan.json (with DELETED to_reconcile)
            #   3. manifest update (remove deleted sources)
            #   4. run journal write
            emit_source_retraction_run(
                deleted_entries=scan_result.delete_queue,
                run_id=run_id,
            )
            # ObsidianRunsAdapter.apply_compile_result() will see DELETED and call
            # _handle_source_deleted() (ingestor.py:224-246) on next replay — same path
            # used by inline-mode graph sync during live run.
            summary.sources_deleted = len(scan_result.delete_queue)
        except Exception as e:
            return _exit(5, f"source-retraction failed: {e}", summary)

    # Step 7: final cleanup (D-91-4) — kdb-clean orphans handles entity orphan-pruning
    try:
        cleanup_result = kdb_clean_orphans(apply=True)
        summary.entities_reaped = cleanup_result.entities_reaped
    except Exception as e:
        return _exit(6, f"cleanup failed: {e}", summary)

    return _exit(0, "orchestrate complete", summary)


def _exit(code: int, reason: str, summary: OrchestrateRunSummary) -> int:
    """Finalize summary, write last_orchestrate.json (D-91-10), return exit code."""
    summary.finished_at = now_local()
    summary.exit_code = code
    summary.exit_reason = reason
    write_last_orchestrate_json(summary)  # D-91-10
    return code
```

### 4.3 Step sequencing rationale

- **Step 1 (feeders) before Step 2 (scan)** — feeders write into vault; scan must see post-feeder state
- **Step 4 (compile) before Step 5 (moves)** — moves are path-only updates; doing them first would conflict with NEW-detection ordering
- **Step 5 (moves) before Step 6 (deletes)** — moves are content-preserving; if a delete-then-recreate happened across runs it would have been classified as MOVE, not DELETE
- **Step 6 (deletes) before Step 7 (cleanup)** — source-retraction must commit before entity orphan-pruning so that `kdb-clean orphans` sees the correct set of "entities with no active supporting source"

---

## 5. `kdb_scan.py` rewrite scope

Current `kdb_scan.py` walks `KDB/raw/` only. The rewrite extends the walker to handle multiple roots with per-root scope config.

### 5.1 New scan-root config schema

Stored at `~/Obsidian/KDB/state/scan_roots.json` (or in `manifest.json` as a nested `config` block — OQ-91-2):

```json
{
  "roots": [
    {
      "id": "kdb-raw",
      "path": "~/Obsidian/KDB/raw",
      "scope_relative_to": "vault",
      "excludes": [],
      "file_types": [".md"]
    },
    {
      "id": "vault-in-place",
      "path": "~/Obsidian",
      "scope_relative_to": "vault",
      "excludes": ["KDB/", ".obsidian/", ".trash/"],
      "file_types": [".md"]
    }
  ]
}
```

### 5.2 Walker behavior (unchanged from existing kdb_scan)

- `os.walk(followlinks=False)` per root
- Per-file: sha256 + mtime + size + ext check (D-91-2 hard rule: `.md` only)
- Symlinks → `skipped_symlinks[]`
- Read/stat errors → `errors[]`

### 5.3 Diff logic (unchanged from existing kdb_scan)

- Phase B: intersection of current ∩ manifest → UNCHANGED (hash eq) or CHANGED (hash differ)
- Phase C: current-only ∩ manifest-only → MOVED (matched by hash)
- Phase D leftover: current-only → NEW; manifest-only → DELETED reconcile op

### 5.4 Multi-root reconciliation (D-91-9 ratified)

A file at `~/Obsidian/KDB/raw/foo.md` could match (by content-hash) a file at `~/Obsidian/AIML/foo.md` and be mis-reported as MOVED across roots. **D-91-9 RATIFIED 2026-05-27** (panel β unanimous): MOVED detection scoped per-root — matches must share the same `root_id`; cross-root same-hash files treated as independent NEW entries. Implementation: add `root_id` to `_RawFile`; in `classify()`, partition current and prior by root, run Phase B/C/D independently per root, merge results (Deepseek OQ-91-3 implementation note).

### 5.5 Multi-root identity collision invariant (Codex F-7)

**Manifest identity stays vault-relative POSIX path** (unchanged from D-88-1). `root_id` is provenance/classification metadata only — NOT part of the manifest key. This is workable only if `path` remains a unique vault-relative POSIX path for every root:

- **Hard rule:** Overlapping roots that emit the same vault-relative path = config error. `load_scan_roots_config()` MUST validate that no two roots could produce the same `path`.
- **Mandatory default exclude:** When both `kdb-raw` and `vault-in-place` roots are configured, vault-in-place MUST exclude `KDB/` (matched in §6.1 below). This is a hard default, not user-removable — only removable when `kdb-raw` root itself is disabled.
- **Phase A test:** add a test that overlapping roots cannot emit duplicate current rows for the same vault-relative path.

### 5.5 Manifest reader/writer

Unchanged — already path-keyed per D-88-1. No schema migration needed.

### 5.6 Output `last_scan.json`

Schema extended with `root_id` per entry; otherwise unchanged.

### 5.7 Backward compat

Existing KDB/raw-only behavior preserved when only `kdb-raw` root is configured. Make-before-break refactor (Task #73 precedent).

---

## 6. Per-root scope-config details

### 6.1 Default excludes (vault-in-place root)

**Mandatory** (cannot be removed unless `kdb-raw` root is also disabled):
- `KDB/` — would create circular ingestion (the machine side ingesting itself) + multi-root identity collision per §5.5

**Walker-time prefix skip** (Deepseek F-3 / Codex Probe 4):
- `.*/` glob — skip any directory whose name starts with `.`. Catches `.git/`, `.github/`, `.cursor/`, `.vscode/`, `.venv/`, `.obsidian/`, `.trash/`, and any future tool-prefix dirs. Implemented in the walker (`os.walk` `dirnames[:] = [d for d in dirnames if not d.startswith('.')]`) BEFORE per-file processing — so excluded trees never incur stat/hash cost (resolves Codex Probe 3 — apply excludes before stat/hash).

**Default optional** (user-configurable):
- `Templates/` — common Obsidian template folder, usually meta-content
- `node_modules/` — dependency dirs (mostly noise; .md files inside are usually package docs)
- Any user-specified excludes

**Note:** The `.*/` glob makes the explicit `.obsidian/` and `.trash/` excludes from v0.1 redundant. Keep them in v0.2 documentation for clarity, but the walker rule subsumes them.

### 6.2 Default excludes (KDB/raw root)

None — everything in KDB/raw is in-scope by definition.

### 6.3 File-type hard rule

`.md` only (D-91-2). Non-`.md` files silently skipped at walker layer; not even logged as errors (would be noise on a 1663-file vault).

### 6.4 Daily Notes handling (cross-reference D-89-14)

`Daily Notes/` is IN scope but routed to `force_noise` post-LLM per D-89-14. Joseph's intent (D-88-11): "I would like daily notes enhanced by the LLM" — Pass-1 still runs against them; path-based override routes them to noise unless content judgment overrides.

---

## 7. Error handling (D-91-8 fail-fast + D-91-13 two-phase failure model)

> **v0.2 rewrite** per Codex F-4 critical finding. The blanket "manifest stays in pre-failure state" promise from v0.1 was too strong — it doesn't hold for graph-sync failures, which happen AFTER manifest write per the existing D50 trade-off (Task #73).

### 7.1 Two-phase failure taxonomy

| Stage | Failure type | Phase | Manifest state | Exit | Remediation |
|---|---|---|---|---|---|
| Feeder | Script returns non-zero or feeder unknown | — | untouched | 1 | fix feeder; re-run |
| Scan | I/O error, permission denied, unreadable file | — | untouched | 2 | fix permission; re-run |
| Enrich | Pass-1 LLM error, schema validation fail, network timeout | pre-commit (a) | untouched for failing source | 3 | fix root cause; re-run |
| Compile — pre-commit | Pass-2 LLM error, validator gate fail, canonicalization, patch-apply, manifest-write | pre-commit (a) | untouched for failing source | 4 | fix root cause; re-run |
| Compile — post-manifest | Graph-sync failure (Stage 10 after manifest committed at Stage 9) | post-manifest (b) | **manifest + wiki committed for failing source**; live graph stale; replayable sidecar exists | 4 | `graphdb-kdb rebuild` to resync; then re-run |
| Manifest update (orchestrator-level) | Atomic-write fail, schema validation fail | pre-commit (a) | untouched for failing source | 5 | investigate; re-run |
| Cleanup | `kdb-clean orphans` failure | post-everything | manifest + graph committed; orphan entities remain | 6 | investigate; re-run cleanup standalone |

### 7.2 Manifest consistency invariant — two-phase

**Phase (a) — pre-commit failures:** On abort, manifest reflects all sources processed BEFORE the failing source (already committed via per-source `apply_source_enrich_and_compile`). The failing source is NOT committed. Re-running `kdb-orchestrate` after fixing the root cause picks up where it left off (previously-committed sources are now UNCHANGED on next scan).

**Phase (b) — post-manifest graph-sync failures:** Manifest + wiki for the failing source ARE committed. Live graph is stale (missing the just-written compile_result's graph updates). Sidecar is replayable — `graphdb-kdb rebuild` brings live graph back into sync with manifest. Run summary reports `committed_but_graph_sync_failed: <source_id>` so operator knows to fire rebuild.

This is the existing D50 trade-off (Task #73): we accept this asymmetry because `graphdb-kdb rebuild` is reliable + replayable. D-91-13 honors it instead of fighting it.

### 7.3 No partial-run journal

D-91-8 implies no resume-from / checkpoint / replay-failed-only logic. The orchestrator is restartable as a fresh run because (a) the manifest absorbs partial progress as a side effect of per-source atomic commits, and (b) `graphdb-kdb rebuild` is the recovery path for phase-(b) failures.

### 7.4 Exit-reason field (D-91-10 cross-reference)

`last_orchestrate.json` `exit_reason` string distinguishes phase-(a) from phase-(b) failures. Examples:
- `"enrich failed (pre-commit): KDB/raw/foo.md — LLM timeout"`
- `"compile failed (pre-commit): KDB/raw/bar.md — validator gate fail"`
- `"compile failed (post-manifest graph-sync): KDB/raw/baz.md — manifest committed; run graphdb-kdb rebuild to resync — kuzu connection error"`

---

## 8. Optional feeder triggering

### 8.1 Feeder contract (v1 minimal)

A "feeder" in v1 is any executable script (bash, Python, anything) that:
- Takes no required arguments
- Writes/updates files in a specific subdir of `~/Obsidian/KDB/raw/<feeder-name>/`
- Returns exit code 0 on success, non-zero on failure
- Logs to stderr (orchestrator captures and surfaces on failure)

### 8.2 Feeder registry

Stored at `~/Obsidian/KDB/state/feeders.json`:

```json
{
  "feeders": {
    "rss": {"command": "~/scripts/feeders/rss-pull.sh", "target": "raw/rss/"},
    "podcasts": {"command": "python3 ~/scripts/feeders/podcast-transcribe.py", "target": "raw/podcasts/"},
    "gmail": {"command": "python3 ~/scripts/feeders/gmail-extract.py", "target": "raw/gmail/"}
  }
}
```

### 8.3 Sequencing

Feeders run in order specified by `--feeders=NAME1,NAME2,...`. Sequential, not parallel (v1 simplicity). Fail-fast applies.

**`--dry-run` interaction (D-91-11):** When `--dry-run` is specified, feeders are SKIPPED entirely. Feeders are side-effectful by definition (they write files into the vault); `--dry-run` means no side effects. The dry-run report shows what WOULD be scanned + processed against the current filesystem state, not a hypothetical post-feeder state.

**Empty-output feeder (Deepseek F-5):** A feeder that runs successfully but produces no new files (e.g., RSS pull with no new articles since last run) is normal. `--verbose` surfaces this as `"feeder rss: 0 new files"`; non-verbose stays silent (0 changes = nothing to report).

**Unknown feeder (D-91-5/OQ-91-5):** `--feeders=NAME` where `NAME` is not in `feeders.json` registry → error with helpful message: `"feeder 'NAME' not found in feeders.json; registered: rss, podcasts, gmail"`. Exit 1.

### 8.4 No v1 feeder implementations included

This task does NOT ship any actual feeders. v1 ships:
- The `kdb-orchestrate` `--feeders=...` flag
- The feeder contract + registry schema
- A test feeder for plumbing verification

Real feeders (RSS, podcasts, gmail) are filed as separate tasks per `[[feedback_concrete_first_extract_later]]` — first concrete feeder is filed when there's a real source the user wants to ingest from.

---

## 9. Open questions

### 9.1 Resolved at v0.2 (post-panel-β fold)

| ID | Resolution | Source |
|---|---|---|
| **OQ-91-1** | **RESOLVED (D-91-14, Shape A):** source deletion via existing `event_type: "compile"` event with empty `compiled_sources` + DELETED in `last_scan.to_reconcile`; uses existing `apply_compile_result()` + `_handle_source_deleted()`; zero new mutation channel. | Joseph ratification + Codex Shape A proposal + 2/2 panel β endorsement of replayable-journal principle |
| **OQ-91-2** | **RESOLVED:** separate `state/scan_roots.json` (config separate from state ledger). Add validation for duplicate root_ids + missing paths + paths outside vault. | 2/2 panel β convergence |
| **OQ-91-3** | **RESOLVED (D-91-9):** per-root MOVED detection. | 2/2 panel β convergence |
| **OQ-91-4** | **RESOLVED (D-91-10):** yes, slim `state/last_orchestrate.json` per spec in D-91-10. | 2/2 panel β + Deepseek payload spec |
| **OQ-91-5** | **RESOLVED:** unknown feeder → exit 1 with `"not found in feeders.json; registered: ..."` message. | 2/2 panel β convergence |
| **OQ-91-6** | **RESOLVED:** cleanup empty-set → exit 0 with report. `kdb-clean orphans --apply` already handles this (`kdb_clean.py:238-240`). | Deepseek code-grounded verification |
| **OQ-91-7** | **RESOLVED:** no lock-file for v1; CLI help text MUST include `"kdb-orchestrate is not re-entrant — do not run concurrent instances against the same vault."` | 2/2 panel β + Deepseek doc-the-risk recommendation |

### 9.2 New open questions (post-v0.2)

| ID | Question | Status |
|---|---|---|
| **OQ-91-8** | MOVED+CHANGED file (rare): currently appears as NEW + DELETED in `compile_queue` + `delete_queue` respectively. Should richer move detection be added (e.g., similarity-hash matching) to coalesce? | Defer — empirical question; revisit if observed frequently in production telemetry. Codex F-6 surfaced. |
| **OQ-91-9** | Should `last_orchestrate.json` opportunistically note a "running" state (in-progress marker that gets overwritten on completion)? | Lean: yes but minimal — just a `state: "running" \| "complete" \| "failed"` field in `last_orchestrate.json` written at start (`running`) + updated at exit. NOT a lock file (no exclusive-access enforcement); just observability. Defer to implementation-time decision. Codex OQ-91-7 ancillary. |

---

## 10. Implementation plan (post-blueprint-ratification)

Phases mirror Task #89 / #90 precedent. Estimates assume blueprint v0.2 ratified.

### Phase A — Infrastructure prerequisites + `kdb_scan.py` multi-root extension

**Phase A.0 — `source_state_update.py` per-source API (CR-1 prereq, blocks Phase B):**
- Add `apply_source_enrich_and_compile(prior, source_scan_entry, enrich_result, compile_result, ctx) → new_manifest_state`
- Add `apply_source_path_update(prior, source_scan_entry, ctx) → new_manifest_state`
- Existing batch `build_source_state_update()` stays for non-orchestrator callers (kdb-compile pipeline still uses it)
- Tests: ~8-12 unit tests for atomic per-source updates

**Phase A.1 — `ScanResult` filtered-accessor properties (Codex F-6 / Deepseek F-4 prereq, blocks §4 pseudocode):**
- Add `.compile_queue` / `.move_queue` / `.delete_queue` properties (see §4.1)
- Tests: ~5 unit tests for filtering correctness

**Phase A.2 — Generalize `_rel_to_vault` for multi-root (Deepseek Probe 4):**
- Refactor `kdb_scan._rel_to_vault(abs_path, root_abs, vault_root)` to handle different root-to-vault relationships
- Backward-compat for existing single-root callers

**Phase A.3 — `kdb_scan.py` multi-root extension:**
- Scan-roots config loader (`load_scan_roots_config` reading `state/scan_roots.json`) with validation (duplicate root_ids, missing paths, overlapping roots)
- Walker extended to iterate roots (per-root pruning of `.*/` prefix dirs via walker-time `dirnames[:] = [d for d in dirnames if not d.startswith('.')]`)
- Per-root scope-config applied (mandatory excludes, file-type allowlist `.md` only per D-91-2)
- `_RawFile` gains `root_id`; classify() partitions by root, runs Phase B/C/D independently per root (D-91-9)
- `last_scan.json` schema extended with `root_id` per entry (provenance only — manifest identity stays `path` per §5.5)
- Multi-root collision invariant test: overlapping roots emitting same vault-relative path → config error
- Tests: ~15-25 unit tests for multi-root walker

### Phase B — `kdb-orchestrate` CLI skeleton
- CLI entry point + arg parsing (`--feeders`, `--dry-run`, `--verbose`)
- Workflow algorithm (§4 pseudocode → Python)
- Exit code handling per §3.3
- Tests: integration test against synthetic vault (no LLM cost)

### Phase C — Source-retraction step (D-91-14 Shape A)
- Implement `emit_source_retraction_run(deleted_entries, run_id)` — emits compile-event journal with empty `compiled_sources` + DELETED `to_reconcile` (Shape A per D-91-14)
- Crash-consistent write order (per Task #68 §6.1): sidecar → `last_scan.json` → manifest removal → journal write
- Verify existing `ObsidianRunsAdapter.apply_compile_result()` correctly routes empty-compile + DELETED-to_reconcile through `_handle_source_deleted()` on replay (should be no-op since the path already exists; just adding a deletion-only test)
- Tests: DELETED source → source-retraction sidecar emitted + manifest removal + Source node + SUPPORTS edges removed from GraphDB + replay-from-rebuild matches live state

### Phase D — Feeder triggering
- Feeder registry loader (`load_feeders_config`)
- Feeder invocation + error handling
- Test feeder for plumbing verification
- Tests: ~5-8 unit tests + integration test

### Phase E — Live smoke (Joseph fires per `[[feedback_user_fires_api_cost_runs]]`)
- E.1: Synthetic vault → `kdb-orchestrate --dry-run` reports correct diff (no LLM cost)
- E.2: Real vault `kdb-orchestrate` against ~5-10 enriched sources (~$0.05-0.20 cost)
- E.3: Re-run after no changes → no-op (idempotency)

### Closure
- TASKS.md #91 row flip + Milestone Changelog entry per `[[feedback_milestone_closure_rule]]`

---

## 11. v2+ roadmap (deferred from v1)

Documented here per D-91-7 so we don't forget when triggers materialize:

- **Real-time / scheduled triggering** — `kdb-orchestrate` runs on filesystem-watcher events or cron schedule. Requires elaborate Component #3 design (event-emission, batching, debounce, watcher process lifecycle). Trigger: user wants near-real-time graph updates without manual fire.
- **Parallel source processing** — `--parallel=N` flag. Trigger: vault grows past ~500 changed sources per run AND wall-clock cost becomes annoying.
- **Resume-from-failure / partial-run journal** — recover from mid-run aborts without re-processing already-committed sources. Trigger: D-91-8 fail-fast empirically hurts throughput (see D-91-8 trade-off note).
- **Multi-user / concurrent-trigger locking** — lock-file or DB-level lock. Trigger: project ever supports multiple operators.
- **Feeder parallelism** — feeders run concurrently rather than sequentially. Trigger: feeder list grows + individual feeders are network-bound.
- **Feeder framework formalization** — typed feeder interface + plugin discovery + per-feeder telemetry. Trigger: feeder count > 5 or user wants to write feeders in a non-shell language with shared utilities.
- **GraphDB utilization beyond ingest** (Task #88 v0.2 §5.6 b/c) — query interfaces, analysis ops, M2/M3 from Round 6, REST/GraphQL API. Trigger: Round 6 Learn implementation lands (Tasks #83/#84/#85/#86 family).

---

## 12. Things to consult during continued design

- `docs/task88-ingestion-pipeline-blueprint.md` v0.2 — parent blueprint; §5.2 (Component #3) and §5.6 (Component #6) are the predecessors being subsumed
- `docs/task89-component1-enrichment-blueprint.md` v0.2.2 — Pass-1 producer contract this orchestrator consumes
- `docs/task90-context-loader-t2-rewrite-blueprint.md` v0.2 — Pass-2 context-loader behavior orchestrator triggers
- `docs/task66-compile-trigger-model-blueprint.md` — the `last_compiled_hash` invariant in current `kdb_scan.py`
- `docs/task68-cleanup-retraction-event-blueprint.md` — replayable cleanup-event pattern (relevant to OQ-91-1)
- `docs/task73-manifest-ontology-removal-blueprint.md` — manifest v3.0 source-state-only ledger contract
- `kdb_compiler/kdb_scan.py` — current single-root implementation being extended
- `kdb_compiler/source_state_update.py` — manifest writer (renamed from `manifest_update.py` per Task #73 Phase D)
- `kdb_compiler/kdb_clean.py` — `kdb-clean orphans` implementation (referenced by D-91-4)
- `docs/external-review-panel.md` — reviewer panel composition + flow; β = Codex + Deepseek

---

## 13. v0.1 → v0.2 amendment table

| ID | Source | Severity | Status | Where in v0.2 |
|---|---|---|---|---|
| A1 (CR-1) | Deepseek F-1 + Codex F-3 (2/2) | critical | Adopted | §4.2 pseudocode rewritten with `apply_source_enrich_and_compile` per-source atomic API (Phase A.0 prereq); §10 Phase A.0 added |
| A2 (CR-2) | Codex F-4 (unique) | critical | Adopted | §7 fully rewritten as two-phase failure model (D-91-13); §7.1 taxonomy table updated with pre-commit (a) vs post-manifest (b) phases |
| A3 (H-1) | Codex F-1+F-2+F-3 + Deepseek Probe 1 (2/2) | high | Adopted | §4.2 pseudocode uses direct Python API (`enrich_one`, in-process compile pipeline) with one-source synthetic scans; D-91-12 locked |
| A4 (H-2) | Codex F-5 + Deepseek OQ-91-1 take (shape divergence) | high | Joseph-ratified Shape A | OQ-91-1 resolved (D-91-14): existing compile-event sidecar with empty `compiled_sources` + DELETED `to_reconcile`; §4.2 Step 6 + §10 Phase C updated |
| A5 (H-3) | Deepseek F-2 (Source-node leak) | high | Adopted (subsumed by A4) | Resolved by D-91-14 Shape A — `_handle_source_deleted()` (ingestor.py:224-246) already removes Source nodes + SUPPORTS edges on replay; verified in §10 Phase C tests |
| A6 (M-1) | Codex F-7 (multi-root collision) | medium | Adopted | §5.5 new section: multi-root identity collision invariant; mandatory `KDB/` exclude in vault-in-place root when both configured |
| A7 (M-2) | Deepseek F-3 + Codex Probe 4 (2/2, hidden-dir excludes) | medium | Adopted | §6.1 rewritten with `.*/` glob walker-time skip; resolves Codex Probe 3 (apply excludes before stat/hash) |
| A8 (M-3) | Deepseek Probe 3 (dry-run + feeders interaction) | medium | Adopted | D-91-11 locked; §4.2 Step 1 + §8.3 updated to skip feeders under `--dry-run` |
| A9 | Codex F-6 + Deepseek F-4 (2/2, ScanResult shape) | medium | Adopted | §4.1 new sub-section: filtered accessor properties (`compile_queue`, `move_queue`, `delete_queue`) added during Phase A.1 |
| A10 | Deepseek F-5 (feeder no-output observability) | low | Adopted | §8.3 amended: `--verbose` surfaces `"feeder X: 0 new files"`; non-verbose silent |
| A11 | Codex Probe 1 / Deepseek Probe 1 (subprocess vs Python API) | high | Adopted (subsumed by A3) | D-91-12 locked |
| A12 | Codex Probe 3 (excludes before stat/hash) | medium | Adopted (subsumed by A7) | §6.1 walker-time prefix skip resolves |
| A13 | Codex Probe 4 / Deepseek F-3 specific dirs (`.git`, `.venv`, `Templates`) | medium | Adopted (subsumed by A7) | `.*/` glob catches `.git/`, `.cursor/`, `.vscode/`, `.venv/`; `Templates/` documented as default-optional |
| A14 | Deepseek Probe 4 (`_rel_to_vault` hardcoded) | medium | Adopted | §10 Phase A.2 added |
| A15 | Deepseek OQ-91-4 payload spec | medium | Adopted | D-91-10 expanded with field-level spec |
| A16 | Codex F-6 ancillary (MOVED+CHANGED edge case) | low | Deferred | OQ-91-8 filed (defer, revisit if empirical) |
| A17 | Codex OQ-91-7 ancillary (`last_orchestrate.json` running marker) | low | Deferred | OQ-91-9 filed (defer to implementation-time) |

**Summary:** 17 amendments. 2 critical, 6 high, 7 medium, 2 low. 2 deferred to post-v0.2 OQs (OQ-91-8 + OQ-91-9). Zero Joseph vetoes on panel findings; one architectural fork (OQ-91-1 Shape A vs B) resolved by Joseph.

---

## 14. v0.1 reviewer-convergence summary

**Panel:** Codex + Deepseek (panel β per D-91 panel scope decision)
**Dispatched:** 2026-05-27 evening (Joseph fires)
**Returned:** 2026-05-27 evening (~minutes after dispatch)
**Guardrail compliance:** 2/2 clean — both reviewers produced exactly one output file at the assigned path; no other repo modifications detected (`git status --short` post-return showed only `??` for the two assigned files).

### 14.1 Convergence pattern (n=2)

- **2/2 unanimous on 5 OQ resolutions** (OQ-91-2 / OQ-91-3 / OQ-91-4 / OQ-91-5 / OQ-91-7) — all confirmed v0.1 leans
- **2/2 convergent on 3 substantive findings** (CR-1 manifest atomicity / H-1 execution unit / H-3+A9 ScanResult shape) — different framings, same root cause
- **1/2 unique catches with critical/high stakes:**
  - Codex F-4 (critical, unique) — graph-sync failure breaks blanket §7.2 invariant → drove D-91-13 two-phase model
  - Deepseek F-3 + Probe 3 (medium-stakes unique) — hidden-directory excludes incomplete; `--dry-run` + feeders interaction
- **1 genuine architectural fork** (OQ-91-1 Shape A vs Shape B) — both reviewers chose option (a) replayable journal but diverged on implementation shape; Joseph picked Shape A per v1 simplification spirit

### 14.2 Per-reviewer track-record signals

**Codex:**
- 7 findings, 4 OQ takes, 4 probes
- Severity distribution: 1 critical (F-4) / 3 high (F-1/F-2/F-3 pass-1/pass-2 execution unit, F-5 OQ-91-1 implementation shape) / 2 medium (F-6 ScanResult / F-7 multi-root identity) / 1 high (F-8 not present — counted from §10 actions)
- Code-grounded: all 7 findings cite specific file:line references in current codebase
- Unique critical catch (F-4 graph-sync invariant) — the type of architectural lens Codex consistently brings

**Deepseek:**
- 5 findings, 7 OQ takes, 4 probes
- Severity distribution: 1 critical (F-1 manifest atomicity) / 2 high (F-2 Source-node leak, OQ-91-1 implementation shape) / 2 medium (F-3 hidden-dir, F-4 ScanResult) / 1 low (F-5 feeder no-output observability)
- Code-grounded: 5/5 findings cite specific file:line + line counts in current codebase
- Self-aware convergence prediction (F-1: "I suspect Codex will flag this too") — high signal-to-noise

### 14.3 Panel composition assessment

Panel β (Codex + Deepseek) was the right scope for this task:
- 2 reviewers caught all the load-bearing issues (no clear gap that a 3rd reviewer would have caught)
- Both clean guardrail compliance + code-grounded findings
- Fast turnaround (response files landed within minutes of dispatch)
- Architectural fork (OQ-91-1 shape) was a 1-vs-1 split — adding a tiebreaker reviewer would have helped, but Joseph's ratification resolved it cleanly per the established workflow

**Recommendation for next blueprint of similar scope:** panel β again. For larger architectural pieces (#88, #89, #90 scale), revert to full 5-CLI panel.

---

**Next steps:**
1. ✅ Joseph reviewed v0.1 → ratified D-91-1..D-91-8 + dispatched panel β
2. ✅ Panel β responses landed → 2/2 guardrail-clean
3. ✅ Synthesized panel feedback → v0.2 fold (17 amendments, 2 deferred to post-v0.2 OQs)
4. ✅ Joseph ratified v0.2 (D-91-9..D-91-14 locked)
5. **NEXT:** Write TDD implementation plan at `docs/superpowers/plans/2026-05-27-task91-kdb-orchestrate-implementation.md` mirroring Task #90 plan precedent (Phase A.0 → A.1 → A.2 → A.3 → B → C → D → E sequence with checkbox tracking)
6. Plan review (lighter — single-reviewer Codex pass) → ratified
7. Phase A-E execution per implementation-plan precedent
