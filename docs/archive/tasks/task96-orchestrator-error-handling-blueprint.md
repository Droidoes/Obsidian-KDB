# Task #96 — Orchestrator Error-Handling Architecture

**Status:** v0.1 architecture path ratified by Joseph 2026-05-30: **B then C**.
Build the structured observability/severity foundation first, then revise the
orchestrator into quarantine-and-continue using that foundation.

**Parent context:** Task #91 (`kdb-orchestrate`) and the real-run-1 gate list in
`docs/orchestrate-real-run-1-to-2-tasklist.md`.

**Immediate problem:** real-run-1 processed 20/36 sandbox sources and then
fail-fasted on source #21. The run proved the E2E tunnel works, but also proved
the conductor is not operable enough: failures are too quiet, raw failure
evidence can be lost, and `failure_stage` strings are not a policy-grade error
model.

---

## 1. Decision

Adopt **Option B → Option C**:

1. **B — Structured observability foundation.** Add a first-class event log,
   severity taxonomy, and explicit invariant checks without changing the
   skip/abort policy yet.
2. **C — Quarantine-and-continue.** Replace fail-fast only after severities
   exist. Source-level failures become logged quarantine events; run-level
   failures still abort. Finalize runs over the committed set.

Rejected for now:

- **A — thin logging patch.** Too local. It would add messages but not create the
  policy substrate #94 needs.
- **C first.** Too risky. A circuit-breaker/quarantine policy without a severity
  model would hard-code today's guesses.

---

## 2. Severity Taxonomy

Severity answers: *what should the conductor do with this event?*

| Severity | Meaning | Default policy |
|---|---|---|
| `debug` | Developer trace; useful for reproducing control flow | Record only when debug logging is enabled |
| `info` | Normal stage/source progress | Record and optionally print concise progress |
| `warning` | Non-fatal anomaly; run continues without quarantine | Record; summarize at end |
| `source_quarantine` | This source cannot proceed safely, but the run can continue | Quarantine source; continue loop |
| `run_fatal` | The run cannot continue safely | Abort after writing summary/event log |
| `invariant_violation` | A code/system contract was broken; continuing would hide corruption | Abort; always high-visibility |

`source_quarantine` is intentionally separate from `warning`: it is a real
source failure and must be visible in summaries, but it is not a whole-run
failure once #94 lands.

---

## 3. Event Schema

Write append-only JSONL at:

```text
<state_root>/runs/<run_id>/orchestrator_events.jsonl
```

Each row:

```json
{
  "schema_version": "1.0",
  "ts": "2026-05-30T12:00:00Z",
  "run_id": "2026-05-30T12-00-00",
  "source_id": "AIML/example.md",
  "stage": "pass1_enrich",
  "event_type": "source_quarantined",
  "severity": "source_quarantine",
  "message": "Pass-1 response failed content schema validation",
  "exception_type": "Pass1SchemaError",
  "error": "override is not an LLM-owned field",
  "context": {
    "pipeline_id": "vault-test",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "attempts": 2
  },
  "artifacts": {
    "raw_response": "runs/<run_id>/pass1/<source_id>.raw.json",
    "sidecar": "runs/<run_id>/pass1/<source_id>.json"
  }
}
```

Rules:

- `source_id` is nullable for run-level events.
- `context` is small structured metadata, not arbitrary blob dumping.
- `artifacts` points to files; large text does not belong inline.
- Event writing must be best-effort but not silent: if event logging fails, the
  run summary records `event_log_failed=true`.

---

## 4. Failure-Point Inventory

| Stage | Example failure | Severity default | Required evidence |
|---|---|---|---|
| `startup` | missing pipeline config, invalid graph path | `run_fatal` | config path, exception |
| `scan` | unreadable root, scan invariant violation | `run_fatal` | root, errors list |
| `pass1_enrich` | model call failure, parse/schema failure | `source_quarantine` | raw response if any, prompt/version metadata |
| `pass1_envelope` | Stage-2 assembled envelope invalid | `invariant_violation` unless proven source-local | envelope sidecar, validation error |
| `pass1_embed` | frontmatter write failure | `source_quarantine` if isolated file I/O; `run_fatal` if state root/config issue | path, exception |
| `pass2_context` | graph context read failure | `run_fatal` by default | graph path, query context |
| `pass2_compile` | model call/parse/schema/gate failure | `source_quarantine` | raw response if any, resp-stats, failure_stage |
| `commit_wiki` | page apply failure | `source_quarantine` before graph/manifest commit | pages attempted/written |
| `graph_sync` | Kuzu mutation failure | `source_quarantine` if txn rolled back clean; `run_fatal` if connection unusable | txn outcome, exception |
| `manifest_commit` | manifest write failure after graph commit | `run_fatal` until recovery semantics are implemented | manifest path, graph_committed flag |
| `reconcile_deleted_moved` | source tombstone/path update failure | `run_fatal` | op payload |
| `finalize_wire_links` | deferred LINKS_TO batch wire failure | `run_fatal` | accumulated source count, exception |
| `finalize_orphans_cleanup` | orphan detect/reap failure | `run_fatal` | cleanup report or exception |
| `summary_write` | `last_orchestrate.json` write failure | `run_fatal` | path, exception |

These are defaults. Implementation can refine a stage only by adding a test that
proves the narrower severity is safe.

---

## 5. Invariant Contract

Do **not** use bare Python `assert` for production checks. `assert` can be
disabled by `python -O`. Use explicit checks:

```python
check_orchestrator_invariant(
    condition,
    code="manifest_requires_post_embed_hash",
    stage="commit_manifest",
    severity="invariant_violation",
    message="Committed source hash must equal post-embed hash",
    context={...},
)
```

On failure:

1. Emit an `invariant_violation` event.
2. Raise `OrchestratorInvariantError`.
3. Write `last_orchestrate.json` with `exit_reason="invariant:<code>"`.
4. Abort the run.

Initial invariant set:

- Every source in `scan.to_compile` has a matching `ScanEntry`.
- `enrich_one` success returns non-empty `body`, `parsed_envelope`,
  `post_embed_hash`, and `post_embed_mtime`.
- Noise commit sets `compile_state="metadata_only"` and
  `last_compiled_hash == post_embed_hash`.
- Signal commit uses `current_hash == post_embed_hash` in the synthetic
  single-source scan.
- `compile_source.ok` implies `cr` is present and has exactly one
  `compiled_sources[]` entry for the source.
- Failed `compile_source` has `failure_stage`, `exception_type`, and `error`
  populated.
- `_commit_source.ok` implies `graph_committed=True`, `next_manifest` present,
  and `cr` present.
- `_commit_source` failure with `failure_stage="graph_sync"` implies manifest
  was not written for that source in this attempt.
- Finalize must run whenever at least one source was committed and the run is
  not `run_fatal` before graph connection open.
- `last_orchestrate.json` must include an `event_log_path` and quarantine counts.

---

## 6. Summary and Alarm Surface

`last_orchestrate.json` remains slim but gains:

```json
{
  "event_log_path": "runs/<run_id>/orchestrator_events.jsonl",
  "counts": {
    "sources_quarantined": 1,
    "warnings": 2,
    "invariant_violations": 0
  },
  "quarantined_sources": [
    {"source_id": "Life-Health-Wellbeing/How Not to Age.md", "stage": "pass1_enrich"}
  ],
  "event_log_failed": false
}
```

CLI behavior:

- default: concise progress + final summary;
- `--log-level {warning,info,debug}` controls operator-visible messages;
- `--verbose` is sugar for `--log-level info`;
- `--debug` is sugar for `--log-level debug`;
- errors and quarantines also print to stderr.

Logging level controls what is displayed and which optional low-level events are
emitted. It does **not** control invariant enforcement: production invariant
checks are always on, regardless of `--log-level`, `--verbose`, or `--debug`.

No hidden failures: if any source is quarantined, the final CLI line must say so
even when exit code remains 0 under #94.

---

## 7. C: Quarantine-and-Continue Policy

After B lands, #94 revises D-91-8:

- `source_quarantine` events do not abort the run.
- The source gets a manifest/quarantine marker sufficient to avoid pretending it
  succeeded.
- The loop continues to the next source.
- Finalize always runs over the committed set, which dissolves the #94 stranded
  `LINKS_TO` class.
- `run_fatal` and `invariant_violation` still abort.

Open design points for #94:

- Where the quarantine ledger lives: manifest source record vs.
  `state/quarantine/<source_id>.json` vs. both.
- Whether quarantined sources retry automatically next run or require content
  change / explicit clear.
- Whether a high quarantine rate triggers a derived `run_fatal` circuit breaker.

---

## 8. Implementation Plan

### Phase B1 — Event model and writer

- Add `kdb_compiler/orchestrator_events.py`.
- Define `OrchestratorSeverity`, `OrchestratorEvent`, `EventRecorder`.
- JSONL append helper using existing atomic/durable patterns where practical.
- Unit tests for serialization, append, disabled debug filtering, and
  best-effort failure reporting.

### Phase B2 — Invariant helper

- Add `OrchestratorInvariantError`.
- Add `check_orchestrator_invariant`.
- Tests prove it emits one event and raises a typed exception.

### Phase B3 — Wire B into `kdb_orchestrate`

- Emit run start, scan complete, source start, enrich result, gate decision,
  compile result, commit result, reconcile result, finalize result, run finish.
- Add CLI logging controls: `--log-level {warning,info,debug}`, with
  `--verbose` and `--debug` aliases.
- Preserve existing behavior: fail-fast remains until C.
- Persist raw model response on failure where the lower layer exposes it; if it
  does not, log the missing-artifact gap explicitly.
- Extend `last_orchestrate.json`.

### Phase C1 — Quarantine result surface

- Introduce quarantine event/result shape.
- Extend run counts and summaries.
- Add tests for source-level Pass-1 and Pass-2 failure continuing the loop.

### Phase C2 — Finalize-always-over-committed-set

- Ensure finalize runs after quarantines when at least one source committed.
- Add regression for #94: first source commits with deferred links, second
  source quarantines, finalize still wires links for committed sources.

### Phase C3 — Circuit breaker

- Add derived run-fatal thresholds only after basic quarantine is green.
- Candidate rules: max consecutive quarantines, max quarantine percentage, or
  zero successful signal compiles.

---

## 9. Test Plan

Run non-live tests only unless Joseph explicitly fires live API tests.

Required tests:

- Event JSON schema/serialization.
- Event JSONL append path.
- `last_orchestrate.json` includes `event_log_path` and quarantine counters.
- Each failure point in §4 emits the expected severity.
- Invariant helper raises typed error and logs `invariant_violation`.
- Raw-response artifact is persisted or an explicit missing-artifact event is
  emitted.
- Existing fail-fast behavior stays unchanged after B.
- After C, Pass-1 source failure quarantines and next source continues.
- After C, Pass-2 source failure quarantines and next source continues.
- After C, finalize runs with quarantined sources and wires links for committed
  sources.
- Run-fatal still aborts and writes summary/event log.

Verification command:

```bash
python3 -m pytest -q -m "not live" kdb_compiler/tests/test_kdb_orchestrate.py
```

Broader gate before closure:

```bash
python3 -m pytest -q -m "not live" kdb_compiler/
```

---

## 10. Ratification Gate

This blueprint captures Joseph's selected path (**B then C**). Implementation
still requires an explicit **Proceed** after review, per project workflow.
