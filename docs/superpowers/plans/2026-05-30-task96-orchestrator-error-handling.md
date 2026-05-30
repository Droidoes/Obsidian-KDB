# Task #96 Implementation Plan — Orchestrator Error Handling

**Goal:** implement the ratified B → C path:

1. **B:** structured observability foundation — event log, severity taxonomy,
   invariant checks, CLI log controls, richer run summary, raw failure artifacts.
2. **C:** quarantine-and-continue — source-local failures quarantine and the run
   continues; run-fatal and invariant failures still abort; finalize runs over
   the committed set.

**Architecture:** `docs/archive/tasks/task96-orchestrator-error-handling-blueprint.md`.

**Scope discipline:** B must land first without changing fail-fast behavior. C
then changes policy using the B severity model. Do not mix the behavior change
into the observability patch.

**Run tests with:**

```bash
python3 -m pytest -q -m "not live" kdb_compiler/tests/test_kdb_orchestrate.py
python3 -m pytest -q -m "not live" kdb_compiler/
```

---

## Phase B1 — Event Model and Recorder

**Files:**
- Create `kdb_compiler/orchestrator_events.py`
- Create `kdb_compiler/tests/test_orchestrator_events.py`

**Tasks:**
- [x] Define `OrchestratorSeverity` as a `Literal` or `StrEnum`:
  `debug`, `info`, `warning`, `source_quarantine`, `run_fatal`,
  `invariant_violation`.
- [x] Define `OrchestratorEvent` dataclass:
  `schema_version`, `ts`, `run_id`, `source_id`, `stage`, `event_type`,
  `severity`, `message`, `exception_type`, `error`, `context`, `artifacts`.
- [x] Define `EventRecorder`:
  - owns `run_id`, `events_path`, and `log_level`;
  - appends JSONL rows;
  - filters optional low-level `debug`/`info` events according to log level;
  - always records `warning`, `source_quarantine`, `run_fatal`,
    `invariant_violation`;
  - tracks `event_log_failed`.
- [x] Ensure the recorder creates `state/runs/<run_id>/`.
- [x] Unit tests:
  - serializes stable JSON keys;
  - appends multiple JSONL rows;
  - `warning` log level drops `info`/`debug`;
  - `info` log level keeps `info` but drops `debug`;
  - `debug` log level keeps all;
  - high-severity events are always recorded;
  - event-write failure sets `event_log_failed`.

**Pass criteria:** event tests green; no orchestrator behavior changed.

---

## Phase B2 — Production Invariant Helper

**Files:**
- Modify `kdb_compiler/orchestrator_events.py`
- Extend `kdb_compiler/tests/test_orchestrator_events.py`

**Tasks:**
- [x] Add `OrchestratorInvariantError`.
- [x] Add `check_orchestrator_invariant(condition, *, recorder, code, stage,
      message, source_id=None, context=None)`.
- [x] On failure:
  - emit `severity="invariant_violation"`;
  - raise `OrchestratorInvariantError(code, stage, message)`.
- [x] Do not use bare Python `assert` for production orchestrator invariants.
- [x] Unit tests:
  - passing condition emits nothing and returns;
  - failing condition emits one invariant event;
  - failing condition raises typed error with code/stage/message;
  - failure behavior is independent of recorder log level.

**Pass criteria:** invariant helper is always-on and independently tested.

---

## Phase B3 — Wire Logging Controls Into CLI

**Files:**
- Modify `kdb_compiler/kdb_orchestrate.py`
- Extend `kdb_compiler/tests/test_kdb_orchestrate.py`

**Tasks:**
- [x] Add CLI flag `--log-level {warning,info,debug}` defaulting to `warning`.
- [x] Keep `--verbose` as sugar for `--log-level info`.
- [x] Keep/add `--debug` as sugar for `--log-level debug`.
- [x] Resolve conflicts deterministically:
  - explicit `--log-level` wins over aliases, or
  - aliases set the value before calling `run()`.
  Pick one and test it.
- [x] Add `log_level` parameter to `run(...)`.
- [x] Construct an `EventRecorder` at run start.
- [x] Add `event_log_path` and `event_log_failed` to `OrchestrateResult`.
- [x] CLI prints the event-log path in the final summary.

**Tests:**
- [x] `test_cli_log_level_warning_default`.
- [x] `test_cli_verbose_sets_info`.
- [x] `test_cli_debug_sets_debug`.
- [x] `test_run_writes_event_log_path_to_summary`.

**Pass criteria:** existing CLI tests stay green; no policy change yet.

---

## Phase B4 — Emit Stage and Source Events

**Files:**
- Modify `kdb_compiler/kdb_orchestrate.py`
- Extend `kdb_compiler/tests/test_kdb_orchestrate.py`

**Events to emit:**
- [x] `run_started` (`info`)
- [x] `scan_completed` (`info`)
- [x] `dry_run_planned` (`info`)
- [x] `source_started` (`info`, source_id)
- [x] `pass1_enrich_completed` (`info`, source_id)
- [x] `pass1_gate_noise` (`info`, source_id)
- [x] `pass1_gate_signal` (`debug`, source_id)
- [x] `pass2_compile_completed` (`info`, source_id)
- [x] `source_commit_completed` (`info`, source_id)
- [x] `reconcile_completed` (`info`, source_id/op)
- [x] `finalize_completed` (`info`)
- [x] `run_finished` (`info`)

**Failure events under existing fail-fast behavior:**
- [x] enrich failure emits `source_quarantine` severity even though B still
      aborts the run; this labels the failure correctly before C changes policy.
- [x] compile failure emits `source_quarantine` severity even though B still
      aborts the run.
- [x] commit failure emits either `source_quarantine` or `run_fatal` per the
      blueprint's stage inventory.
- [x] unexpected exception emits `run_fatal`.

**Tests:**
- [x] successful run writes start/scan/source/finalize/finish events.
- [x] dry-run writes event log and summary pointer.
- [x] compile failure writes a `source_quarantine` event and still fail-fasts
      before C.
- [x] unexpected exception writes `run_fatal` if it reaches the summary path.

**Pass criteria:** B labels failures but does not yet continue after them.

---

## Phase B5 — Summary and Alarm Surface

**Files:**
- Modify `kdb_compiler/kdb_orchestrate.py`
- Extend `kdb_compiler/tests/test_kdb_orchestrate.py`

**Tasks:**
- [x] Extend `write_last_orchestrate_json(...)` with:
  - `event_log_path`;
  - `event_log_failed`;
  - `warnings`;
  - `sources_quarantined`;
  - `invariant_violations`;
  - `quarantined_sources` list.
- [x] Keep summary slim: source lists only for quarantines; full event stream is
      JSONL.
- [x] CLI final line must make quarantines visible when count > 0.

**Tests:**
- [x] summary includes event fields on success.
- [x] summary includes quarantine count/source on compile failure.
- [x] event log failure is surfaced in summary.

**Pass criteria:** no hidden failure; summary points to event evidence.

**B5 verification:** 2026-05-30 targeted event/orchestrator tests green
(`34 passed`); broader non-live `kdb_compiler/` suite green (`1 skipped` live
smoke).

---

## Phase B6 — Raw Failure Artifact Persistence

**Files:**
- Inspect and modify as needed:
  - `kdb_compiler/ingestion/pass1_caller.py`
  - `kdb_compiler/ingestion/enrich.py`
  - `kdb_compiler/compiler.py`
  - `kdb_compiler/kdb_orchestrate.py`
- Tests in existing pass1/compiler/orchestrator test files.

**Tasks:**
- [x] For Pass-1 parse/schema/model failures, persist raw response when present.
- [x] For Pass-2 parse/schema/model failures, ensure resp-stats or a sidecar
      contains raw response when present.
- [x] If a layer cannot expose raw response yet, emit an event with
      `event_type="raw_response_unavailable"` and context explaining why.
- [x] Add artifact paths to failure events.

**Tests:**
- [x] Pass-1 invalid JSON writes or references a raw-response artifact.
- [x] Pass-2 invalid response writes or references a raw-response artifact.
- [x] Missing raw response emits explicit `raw_response_unavailable`.

**Pass criteria:** real-run-1's "cannot inspect source #21" class is closed or
explicitly surfaced as a remaining gap.

**B6 verification:** 2026-05-30 focused Pass-1/Pass-2/orchestrator tests green
(`117 passed`); broader non-live `kdb_compiler/` suite green (`1 skipped` live
smoke).

---

## Phase B7 — Run-Directory Artifact Consolidation + Invariant Wiring

**Files:**
- Modify `kdb_compiler/resp_stats_writer.py`
- Modify `kdb_compiler/compiler.py`
- Modify `kdb_compiler/kdb_orchestrate.py`
- Extend focused tests.

**Tasks:**
- [x] Keep legacy `state/llm_resp/<run_id>/` as the default response-stats path
      for existing `kdb-compile` / benchmark surfaces.
- [x] Let orchestrator-owned Pass-2 calls write response stats into
      `state/runs/<run_id>/pass2/`.
- [x] Wire `check_orchestrator_invariant(...)` into the production run loop:
  - Pass-1 success payload completeness;
  - failed `compile_source` result payload completeness;
  - successful `compile_source` returns exactly one compiled source for the
    current `source_id`;
  - successful source commit exposes `graph_committed`, `next_manifest`, and
    `cr`.
- [x] Convert invariant failures into `exit_reason="invariant:<code>"`,
      `invariant_violation` events, and summary counts instead of generic
      unexpected crashes.

**Tests:**
- [x] `write_resp_stats(..., artifact_dir=...)` writes to a run-owned target.
- [x] `compile_source` failure artifacts point at
      `state/runs/<run_id>/pass2/`.
- [x] malformed successful compile result emits an `invariant_violation` event
      and writes `last_orchestrate.json` with `exit_reason="invariant:<code>"`.

**Pass criteria:** the run directory is the durable packet for orchestrator logs,
Pass-1 sidecars, Pass-2 response artifacts, and production invariant failures.

**B7 verification:** 2026-05-30 focused response-stats / compile-source /
orchestrator / event tests green (`80 passed`).

---

## Phase B8 — Source Lifecycle Naming Prep for C1

**Files:**
- Modify `kdb_compiler/source_state_update.py`
- Modify `kdb_compiler/run_context.py`
- Modify GraphDB verifier/ingestor source-state bridges.
- Extend focused tests.

**Tasks:**
- [x] Deprecate active source-state writes to `compile_state`.
- [x] Bump source-state schema to v3.1.
- [x] Add explicit `run_state` values:
      `pending`, `no_graph_db`, `in_graph_db`, `error_ingest`,
      `error_compile`, `error_commit`.
- [x] Migrate legacy `compile_state` values into `run_state`, including
      `metadata_only -> no_graph_db`, `error -> error_compile`, and
      `compiled`/`recompiled -> in_graph_db`.
- [x] Reject lingering `compile_state` and invalid `run_state` in source-state
      invariants.
- [x] Keep GraphDB's graph-side `ingest_state` name, but bridge it from
      producer `run_state`; accept legacy `compile_state` only for old replay
      payloads.

**Tests:**
- [x] source-state migration strips `compile_state` and writes valid
      `run_state`.
- [x] legacy error values map into the new error enum.
- [x] scan eligibility remains hash-only and ignores `run_state`.
- [x] GraphDB verifier compares producer `run_state` to graph
      `ingest_state`.

**Pass criteria:** C1 can write source-local failure classifications without
reusing the deprecated `compile_state` name.

**B8 verification:** 2026-05-30 focused source-state / scan / orchestrator /
GraphDB verifier, snapshot, and ingestion tests green; broader non-live
`kdb_compiler/` plus focused GraphDB suite green (`1 skipped` live smoke).

---

## Phase C1 — Quarantine Result Model

**Files:**
- Modify `kdb_compiler/kdb_orchestrate.py`
- Modify `kdb_compiler/source_state_update.py`
- Modify `kdb_compiler/ingestion/enrich.py`
- Extend `kdb_compiler/tests/test_kdb_orchestrate.py`

**Tasks:**
- [x] Add in-memory `quarantined_sources` list to the run loop.
- [x] Add helper `_commit_source_failure(...)` / `last_failure` payload that:
  - records source_id/stage/error/artifacts;
  - emits `source_quarantine`;
  - increments counts;
  - returns control to the loop.
- [x] Implement minimal persistent quarantine marker in source-state:
  - `run_state=error_ingest` for Pass-1 failures;
  - `run_state=error_compile` for Pass-2 failures;
  - `run_state=error_commit` for source-local commit failures;
  - structured `last_failure` with stage/run/error/exception/artifacts.
- [x] Preserve retry eligibility: failure writes source metadata but does **not**
      advance `last_compiled_hash`.
- [x] Treat Stage-2 Pass-1 assembled-envelope validation failures as
      `enrich_failed`, not unexpected crashes.
- [x] Keep `run_fatal` and `invariant_violation` as aborts.

**Tests:**
- [x] Pass-1 failure quarantines source and next source runs.
- [x] Pass-2 failure quarantines source and next source runs.
- [x] Quarantined source gets `error_*` state, structured `last_failure`, and
      no `last_compiled_hash` advancement.
- [x] Completed run with only source-local quarantines exits `0` with
      `exit_reason="completed_with_quarantines"`; alarm surface is summary,
      event log, and CLI stderr.

**Pass criteria:** source-local failure no longer kills the batch.

**C1 verification:** 2026-05-30 focused source-state/orchestrator tests green
(`65 passed`); focused C1-adjacent suite green (`183 passed`).

---

## Phase C2 — Finalize Always Runs Over Committed Set

**Files:**
- Modify `kdb_compiler/kdb_orchestrate.py`
- Extend `kdb_compiler/tests/test_kdb_orchestrate.py`

**Tasks:**
- [x] Move finalize out of the source-local failure assumption.
- [x] Finalize runs when:
  - there is at least one accumulated committed `cr`;
  - graph connection is healthy;
  - no `run_fatal` / `invariant_violation` requires immediate abort.
- [x] Finalize skips only when zero committed sources or graph unavailable;
      all-quarantined runs emit `finalize_skipped` and still write summary/event log.
- [x] Summary distinguishes:
  - `ok`;
  - `completed_with_quarantines`;
  - `run_fatal`;
  - `invariant:<code>`.

**Tests:**
- [x] Regression for #94: source A commits with deferred links, source B
      quarantines, finalize still runs.
- [x] `wire_links` runs over committed set after quarantine.
- [x] `compile_result.json` is written for committed set after quarantine.
- [x] zero committed sources + all quarantined does not run link wiring but still
      writes summary/event log.

**Pass criteria:** #94 stranded deferred `LINKS_TO` class is dissolved.

**C2 verification:** 2026-05-30 orchestrator C2 regression tests green
(`26 passed`).

---

## Phase C3 — Circuit Breaker From Severities — DEFERRED (2026-05-30)

**Status: DEFERRED — not now.** Decision (Joseph + assistant, 2026-05-30):
runs are attended and `--limit N` (#99) already caps blast radius; C1/C2 already
surface all-quarantined runs loudly (exit_reason, counts, event log, stderr) with
no masking; thresholds (consecutive / ratio) are guesses with no measured baseline
("data before principle"). B's severity taxonomy makes the breaker a pure additive
policy layer, so deferral is architecturally free and fully reversible.

**Trigger to revisit:** a measured quarantine-rate baseline from the first real
multi-source run, OR any move to unattended/scheduled `kdb-orchestrate`. This also
resolves open ratification point #3 ("Circuit-breaker thresholds") = *none for
first C pass*.

**Files (when revisited):**
- Modify `kdb_compiler/kdb_orchestrate.py`
- Extend tests.

**Tasks:**
- [ ] Add a small circuit-breaker policy driven by severities, not a freeform
      toggle.
- [ ] Candidate defaults:
  - abort if N consecutive `source_quarantine` events exceeds threshold;
  - abort if quarantine ratio exceeds threshold after minimum sample;
  - abort if startup/scan/context/manifest/finalize emits `run_fatal`;
  - abort immediately on `invariant_violation`.
- [ ] Keep thresholds conservative and configurable only if a real use case
      exists. Avoid overbuilding.

**Tests:**
- [ ] consecutive quarantine threshold triggers `run_fatal`.
- [ ] isolated quarantine below threshold continues.
- [ ] invariant violation bypasses circuit breaker and aborts immediately.

**Pass criteria:** batch can continue through source-local failures without
masking systemic failure.

---

## Documentation Closure

- [x] Update `docs/archive/tasks/task96-orchestrator-error-handling-blueprint.md`
      with any drift from this plan. (No material drift — plan executed as written;
      C3 deferred, recorded here + in blueprint §7 open points.)
- [x] Update `docs/TASKS.md` #96 status/narrative. (status → closed; C3-deferred
      + D-96-1 + green-suite note appended.)
- [x] Update `docs/orchestrate-real-run-1-to-2-tasklist.md` B/C checkboxes.
- [x] Add `CODEBASE_OVERVIEW.md` milestone changelog entry on closure.
- [x] D-91-8 revision recorded as **D-96-1** (narrowed to run-fatal scope) in the
      tasklist C section + TASKS.md #96 + changelog.

---

## Open Ratification Points Before C

1. Exit code for completed run with quarantined sources:
   - option 1: `0` with alarm summary;
   - option 2: non-zero but finalize complete;
   - option 3: configurable.
2. Minimal persistent quarantine marker:
   - event log + summary only;
   - manifest source record;
   - separate `state/quarantine/` ledger.
3. Circuit-breaker thresholds:
   - none for first C pass;
   - fixed conservative defaults;
   - CLI-configurable.

Phase B can proceed without resolving these. Phase C cannot.
