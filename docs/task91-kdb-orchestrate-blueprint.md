# Task #91 — `kdb-orchestrate`: End-to-end Ingestion Orchestrator + Extended `kdb_scan.py`

**Status:** v0.1 draft (2026-05-27 evening) — Joseph-ratified D-91-1..D-91-8; pending external panel β review (Codex + Deepseek) before v0.2 ratification.

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
| **D-91-8** | **Fail-fast at first source failure.** If any source fails Pass-1 enrich OR Pass-2 compile, abort the whole `kdb-orchestrate` run immediately. No skip-and-continue; no partial commit. Manifest stays in known-good pre-failure state | 2026-05-27 | Joseph call (overrode assistant's skip-and-continue lean) |

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

```python
def kdb_orchestrate(feeders: list[str] | None = None,
                   dry_run: bool = False,
                   verbose: bool = False) -> int:
    """End-to-end ingestion orchestrator (D-91-1..D-91-8)."""

    # Step 1 (optional): trigger feeders
    if feeders:
        for feeder in feeders:
            try:
                run_feeder(feeder)
            except Exception as e:
                log_error(f"feeder {feeder} failed", e)
                return 1  # fail-fast (D-91-8)

    # Step 2: scan all configured roots, diff against manifest
    try:
        scan_result = kdb_scan(
            roots=load_scan_roots_config(),  # e.g., [KDB_RAW, vault-in-place dirs]
            file_type_allowlist={".md"},     # D-91-2
        )
    except Exception as e:
        log_error("scan failed", e)
        return 2

    # Step 3: dry-run short-circuit
    if dry_run:
        report(scan_result)
        return 0

    # Step 4: process NEW + CHANGED sources sequentially with fail-fast (D-91-8)
    for source in scan_result.new + scan_result.changed:
        try:
            enrich_result = kdb_enrich(source)       # Pass-1
        except Exception as e:
            log_error(f"enrich failed: {source.path}", e)
            return 3

        try:
            compile_result = kdb_compile(source)     # Pass-2 + graph sync
        except Exception as e:
            log_error(f"compile failed: {source.path}", e)
            return 4

        try:
            source_state_update(source, enrich_result, compile_result)  # manifest update
        except Exception as e:
            log_error(f"manifest update failed: {source.path}", e)
            return 5

    # Step 5: process MOVED entries (path update, no recompile)
    for source in scan_result.moved:
        try:
            source_state_update_path_only(source)
        except Exception as e:
            log_error(f"manifest path-update failed: {source.path}", e)
            return 5

    # Step 6: process DELETED entries (manifest removal; entity cleanup deferred to Step 7)
    for source in scan_result.deleted:
        try:
            source_state_remove(source)  # OQ-91-1: source-retraction journal?
        except Exception as e:
            log_error(f"manifest source-remove failed: {source.path}", e)
            return 5

    # Step 7: final cleanup (D-91-4) — kdb-clean orphans handles entity orphan-pruning
    try:
        kdb_clean_orphans(apply=True)
    except Exception as e:
        log_error("cleanup failed", e)
        return 6

    return 0
```

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

### 5.4 Multi-root reconciliation wrinkle

A file at `~/Obsidian/KDB/raw/foo.md` could match (by content-hash) a file at `~/Obsidian/AIML/foo.md` and be mis-reported as MOVED across roots. **D-91-9 candidate:** MOVED detection scoped per-root (matches must share the same `root_id`); cross-root same-hash files treated as independent NEW entries. Open for v0.2 review.

### 5.5 Manifest reader/writer

Unchanged — already path-keyed per D-88-1. No schema migration needed.

### 5.6 Output `last_scan.json`

Schema extended with `root_id` per entry; otherwise unchanged.

### 5.7 Backward compat

Existing KDB/raw-only behavior preserved when only `kdb-raw` root is configured. Make-before-break refactor (Task #73 precedent).

---

## 6. Per-root scope-config details

### 6.1 Default excludes (vault-in-place root)

Required:
- `KDB/` — would create circular ingestion (the machine side ingesting itself)
- `.obsidian/` — Obsidian config (defense-in-depth per D-88-11; `.md` rule already excludes most plugin output)
- `.trash/` — Obsidian's trash

Optional (user-configurable):
- `Templates/` — common Obsidian template folder, usually meta-content
- Any user-specified excludes

### 6.2 Default excludes (KDB/raw root)

None — everything in KDB/raw is in-scope by definition.

### 6.3 File-type hard rule

`.md` only (D-91-2). Non-`.md` files silently skipped at walker layer; not even logged as errors (would be noise on a 1663-file vault).

### 6.4 Daily Notes handling (cross-reference D-89-14)

`Daily Notes/` is IN scope but routed to `force_noise` post-LLM per D-89-14. Joseph's intent (D-88-11): "I would like daily notes enhanced by the LLM" — Pass-1 still runs against them; path-based override routes them to noise unless content judgment overrides.

---

## 7. Error handling (D-91-8 fail-fast)

### 7.1 Failure-mode taxonomy

| Stage | Failure | D-91-8 action | Exit code |
|---|---|---|---|
| Feeder | Feeder script returns non-zero | Abort run | 1 |
| Scan | I/O error, permission denied, unreadable file | Abort run | 2 |
| Enrich | Pass-1 LLM error, schema validation fail, network timeout | Abort run AT failing source | 3 |
| Compile | Pass-2 LLM error, validator gate fail, graph-sync error | Abort run AT failing source | 4 |
| Manifest update | Atomic-write fail, schema validation fail | Abort run AT failing source | 5 |
| Cleanup | `kdb-clean orphans` failure | Abort run | 6 |

### 7.2 Manifest consistency invariant

On abort, the manifest reflects all sources processed BEFORE the failing source (those are already committed in their atomic updates). The failing source is NOT committed. Re-running `kdb-orchestrate` after the user fixes the root cause picks up where it left off (the previously-committed sources are now UNCHANGED on the next scan; the failing source is still NEW or CHANGED).

### 7.3 No partial-run journal

D-91-8 implies no resume-from / checkpoint / replay-failed-only logic. The orchestrator is restartable as a fresh run because the manifest absorbs partial progress as a side effect of per-source atomic commits.

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

### 8.4 No v1 feeder implementations included

This task does NOT ship any actual feeders. v1 ships:
- The `kdb-orchestrate` `--feeders=...` flag
- The feeder contract + registry schema
- A test feeder for plumbing verification

Real feeders (RSS, podcasts, gmail) are filed as separate tasks per `[[feedback_concrete_first_extract_later]]` — first concrete feeder is filed when there's a real source the user wants to ingest from.

---

## 9. Open questions (post-v0.1, for panel review + Joseph)

| ID | Question | Notes |
|---|---|---|
| **OQ-91-1** | Source-retraction journal? When a source is DELETED, do we write a journal event (Task #68 cleanup-event pattern) so the deletion is replayable, or just remove from manifest and let `kdb-clean orphans` handle entity cleanup? | Task #68 set precedent for replayability. Current `kdb-clean orphans` reads from GraphDB authority. The Source-node-removal step needs explicit specification — currently undefined. |
| **OQ-91-2** | Scan-roots config location: separate `scan_roots.json` or nested in `manifest.json` config block? | Separate file: cleaner separation, easier to version-control config separately from state. Nested: one fewer file. Lean: separate. |
| **OQ-91-3** | MOVED detection scoped per-root or cross-root? | D-91-9 candidate: per-root. See §5.4. |
| **OQ-91-4** | Should `kdb-orchestrate` emit a per-run summary (`state/last_orchestrate.json`)? | Lean: yes (small file, useful for observability). |
| **OQ-91-5** | Feeder failure on `--feeders=NAME` where NAME isn't registered: error or skip with warning? | Lean: error (D-91-8 fail-fast spirit). |
| **OQ-91-6** | What happens if `kdb-clean orphans` final step finds nothing to clean? | Lean: success (exit 0), report `0 orphans cleaned`. Currently `kdb-clean orphans` already handles this. Verify before ship. |
| **OQ-91-7** | Re-entry safety: if `kdb-orchestrate` is fired twice concurrently? | Lean: don't add lock-file ceremony (single-user, manual trigger per `[[feedback_no_imaginary_risk]]`). Document as user discipline. |

---

## 10. Implementation plan (post-blueprint-ratification)

Phases mirror Task #89 / #90 precedent. Estimates assume blueprint v0.2 ratified.

### Phase A — `kdb_scan.py` multi-root extension
- Scan-roots config loader (`load_scan_roots_config`)
- Walker extended to iterate roots
- Per-root scope-config applied (excludes, file-type allowlist)
- `last_scan.json` schema extended with `root_id`
- MOVED detection scoped per OQ-91-3 resolution
- Tests: ~15-25 unit tests for multi-root walker

### Phase B — `kdb-orchestrate` CLI skeleton
- CLI entry point + arg parsing (`--feeders`, `--dry-run`, `--verbose`)
- Workflow algorithm (§4 pseudocode → Python)
- Exit code handling per §3.3
- Tests: integration test against synthetic vault (no LLM cost)

### Phase C — Source-retraction step
- OQ-91-1 resolution implemented (journal event or direct manifest removal)
- Tests: DELETED source → manifest removal + graph cleanup verified

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

## 13. v0.1 → v0.2 amendment table (to be populated post-panel-β review)

| ID | Source | Status | Where in v0.2 |
|---|---|---|---|
| _Pending Codex + Deepseek review_ | | | |

---

## 14. v0.1 reviewer-convergence summary (to be populated post-panel-β review)

_Pending Codex + Deepseek review._

---

**Next steps:**
1. Joseph reviews v0.1 → notes / corrections / additional locked decisions
2. Dispatch to panel β (Codex + Deepseek) per D-91 panel scope decision
3. Synthesize panel feedback into v0.2 fold
4. Joseph ratifies v0.2 → unblocks TDD implementation plan write
5. Implementation plan → external review (lighter) → ratified → Phase A-E execution per [`docs/superpowers/plans/`] precedent
