# Runs Journal V2 — Consolidated Spec for Opus

This document consolidates my feedback on the proposed `runs/<run_id>.json` restructuring and the follow-up implementation spec into one shareable note.

It is grounded in the current code paths:

- `kdb_compiler/kdb_compile.py`
- `kdb_compiler/compiler.py`
- `kdb_compiler/manifest_update.py`
- `kdb_compiler/resp_stats_writer.py`
- `kdb_compiler/run_context.py`

## Executive Summary

The proposed direction is correct overall:

- Always write a run journal, including failure runs.
- Move final journal assembly to the orchestrator in `kdb_compile.py`.
- Preserve per-source deep artifacts in `state/llm_resp/<run_id>/...json`.
- Expand the run journal into a queryable, stage-aware diagnostic record.

The main corrections I recommend are:

- Split manifest schema versioning from journal schema versioning.
- Treat end-to-end run success separately from compile-stage success.
- Make replay-mode fields nullable or absent where live model-call data does not exist.
- Keep full prompt/response payloads out of the run journal; store references only.
- Let `manifest_update.py` return a compact manifest-stage payload, not the final journal.

## Current State

### What the code does today

- `kdb_compile.compile()` is the real 7-stage orchestrator.
- Early failure paths return before any journal file is written.
- `manifest_update.build_manifest_update()` currently returns `(next_manifest, journal)`.
- `manifest_update.build_journal()` produces a flat journal shape.
- `compiler.run_compile()` emits `job_start` / `job_done` progress events, but does not currently expose a rich per-source stats sink to the orchestrator.
- `resp_stats_writer.write_resp_stats()` already writes one per-source artifact under `state/llm_resp/<run_id>/...json`.
- Dry-run currently skips journal persistence, even though per-source resp-stats are still written.

### Important implications

- Failed runs currently lose the highest-value diagnostic context.
- Journal schema is currently coupled too loosely to manifest-related versioning.
- The orchestrator is the only place that can see true end-to-end timings across all 7 stages.

## Decisions

### Decision A — Always write the journal

Recommended: **yes**.

Rationale:

- This is the single biggest gain for workflow optimization.
- Early validation failures, stale fixture issues, manifest read errors, and apply failures are exactly the cases where the journal is most useful.
- A missing journal on failure creates blind spots in later diagnosis.

Implementation rule:

- The run journal should be finalized and written for both success and failure runs.
- If journal write itself fails, that is a separate failure condition and should surface explicitly.

### Decision B — Orchestrator owns the final journal

Recommended: **yes**.

Rationale:

- `manifest_update.py` cannot see end-to-end stage timings.
- The compile stage spans replay/live branching, per-source work, and validation outcomes that manifest code should not own.
- The orchestrator already defines the canonical stage structure.

Implementation rule:

- `kdb_compile.py` assembles the final journal.
- `manifest_update.py` returns manifest-stage payload only.

## Corrections to the Proposed Plan

### 1. Split schema versioning

Do not reuse the current `SCHEMA_VERSION` for both manifest and journal shapes.

Recommended:

- `MANIFEST_SCHEMA_VERSION = "1.0"`
- `JOURNAL_SCHEMA_VERSION = "2.0"`

Why:

- Manifest shape and run-journal shape are now separate contracts.
- Tying them together creates accidental migrations and confusing test coupling.

### 2. Clarify success semantics

Top-level `success` in the new journal should mean **end-to-end orchestrator success**, not just `compile_result.success`.

Recommended top-level fields:

- `success`: end-to-end outcome
- `compile_success`: mirrors compile stage success when available
- `journal_written`
- `manifest_written`

Why:

- A compile can succeed while manifest write fails.
- A run can fail before compile ever produces a valid `compile_result`.

### 3. Replay mode needs nullable fields

When stage 3 reuses a pre-staged `compile_result.json`, the current run may not have live values for:

- `provider`
- `model`
- `attempts`
- `input_tokens`
- `output_tokens`
- `prompt_hash`
- `response_hash`
- `resp_stats_ref`

Recommended:

- allow these fields to be `null` or absent in replay mode
- record `mode: "replay"` explicitly at the compile stage

### 4. Keep prompt/response bodies out of the run journal

Recommended:

- keep hashes, parsed summaries, gate outcomes, and `resp_stats_ref`
- do not inline `system_prompt`, `user_prompt`, `raw_response_text`, or full parsed JSON into the run journal

Why:

- the journal should be a durable query index
- `state/llm_resp/<run_id>/...json` is already the deep artifact store
- duplicating deep payloads increases size and maintenance cost with little gain

### 5. Move journal code out of `manifest_update.py`

If the orchestrator owns the final journal, `build_journal()` no longer belongs in `manifest_update.py`.

Recommended:

- create `kdb_compiler/run_journal.py`
- put `RunJournalBuilder` and `JOURNAL_SCHEMA_VERSION` there

## Recommended Journal V2 Shape

```json
{
  "schema_version": "2.0",
  "run_id": "2026-04-21T14-32-01_EDT",
  "compiler_version": "0.x.y",
  "dry_run": false,
  "vault_root": "/abs/path/to/vault",
  "started_at": "2026-04-21T14:32:01-04:00",
  "finished_at": "2026-04-21T14:34:17-04:00",
  "duration_ms": 136012,

  "success": true,
  "compile_success": true,
  "journal_written": true,
  "manifest_written": true,

  "terminated_at_stage": null,
  "failure_stage_name": null,
  "failure_type": null,
  "failure_message": null,

  "config": {
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 32768,
    "resp_stats_capture_full": false
  },

  "artifacts": {
    "last_scan_path": "state/last_scan.json",
    "compile_result_path": "state/compile_result.json",
    "manifest_path": "state/manifest.json",
    "journal_path": "state/runs/<run_id>.json",
    "resp_stats_dir": "state/llm_resp/<run_id>/"
  },

  "stages": [],
  "summary": {}
}
```

## Stage Model

Each stage entry should contain:

- `index`
- `name`
- `started_at`
- `finished_at`
- `duration_ms`
- `ok`
- `note`

Plus stage-specific payload.

Only include stages that actually started. Do not synthesize future stages after failure.

Use stage names already defined by the orchestrator:

- `scan`
- `validate scan`
- `compile`
- `validate compile_result`
- `build manifest update`
- `apply pages`
- `persist state`

## Stage-Specific Payloads

### Stage 1 — `scan`

Recommended fields:

- `scan_run_id`
- `files_total`
- `to_compile_count`
- `to_skip_count`
- `to_reconcile_count`
- `scan_summary`
- `reconcile_counts`
- `last_scan_path`

### Stage 2 — `validate scan`

Recommended fields:

- `error_count`
- `errors`

### Stage 3 — `compile`

Recommended fields:

- `mode`: `live` or `replay`
- `jobs_planned`
- `jobs_attempted`
- `jobs_succeeded`
- `jobs_failed`
- `aggregate`
- `sources`

Aggregate should include, where available:

- `total_input_tokens`
- `total_output_tokens`
- `total_latency_ms`
- `total_attempts`
- `providers`
- `models`

### Stage 4 — `validate compile_result`

Recommended fields:

- `error_count`
- `errors`

### Stage 5 — `build manifest update`

Recommended fields:

- `prior_manifest_loaded`
- `deltas`
- `counts`

Where:

- `deltas` includes `sources_added`, `sources_removed`, `sources_moved`, `sources_changed`, `pages_created`, `pages_updated`, `orphans_flagged`, `orphans_cleared`
- `counts` includes `sources_after`, `pages_after`, `orphans_after`, `tombstones_after`

### Stage 6 — `apply pages`

Recommended fields:

- `pages_written`
- `pages_written_count`
- `pages_created_count`
- `pages_updated_count`
- `bytes_written` if cheap to compute, otherwise omit initially

### Stage 7 — `persist state`

Recommended fields:

- `journal_written`
- `manifest_written`
- `journal_path`
- `manifest_path`
- `skipped_manifest_write_reason`

This is better than a single `skipped` flag because failure and dry-run are different reasons.

## Per-Source Compile Records

Stage 3 should include one entry per attempted source job.

Recommended shape:

```json
{
  "i": 1,
  "n": 3,
  "source_id": "KDB/raw/foo.md",
  "started_at": "...",
  "finished_at": "...",
  "duration_ms": 12345,
  "ok": true,
  "error": null,

  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "attempts": 1,
  "input_tokens": 12934,
  "output_tokens": 3127,
  "latency_ms": 12290,

  "prompt_hash": "sha256:...",
  "response_hash": "sha256:...",
  "resp_stats_ref": "state/llm_resp/<run_id>/KDB__raw__foo.md.json",

  "gates": {
    "extract_ok": true,
    "parse_ok": true,
    "schema_ok": true,
    "semantic_ok": true
  },

  "parsed_summary": {
    "summary_slug": "foo",
    "page_count": 4,
    "page_types": { "summary": 1, "concept": 3, "article": 0 },
    "slugs": ["foo", "a", "b", "c"],
    "outgoing_link_count": 9,
    "log_entry_count": 1,
    "warning_count": 0,
    "source_id_echoed": "KDB/raw/foo.md"
  }
}
```

Replay-mode rule:

- if the current run did not perform a live model call, fields that depend on a live response may be `null` or absent

## Summary Section

The top-level `summary` section should be optimized for quick inspection without having to traverse `stages`.

Recommended shape:

- `inputs`
- `counts`
- `deltas`
- `tokens`
- `log_entries`
- `warnings`
- `errors`

Recommended `summary.inputs`:

- `scan_run_id`
- `last_scan_path`
- `compile_result_path`
- `compile_sources_processed`

Recommended `summary.counts`:

- `sources_attempted`
- `sources_compiled`
- `sources_failed`
- `pages_created`
- `pages_updated`
- `pages_written`
- `orphans_flagged`
- `orphans_cleared`

Recommended `summary.tokens`:

- `input`
- `output`

`summary.deltas` may duplicate stage-5 deltas for convenience. That duplication is acceptable.

## Dry-Run Policy

Recommended: **write the journal on dry-run**.

Behavior:

- `dry_run: true`
- `journal_written: true`
- `manifest_written: false`
- stage 7 note indicates manifest write was skipped because of dry-run

Rationale:

- the project already treats per-source resp-stats as valid dry-run diagnostics
- suppressing the journal while still writing resp-stats is inconsistent
- dry-run exists partly to inspect behavior before committing durable state

No special dry-run filename prefix is needed. The journal itself already declares `dry_run: true`.

## Failure Policy

Recommended behavior:

- failure before stage 5 still produces a journal
- failure after stage 5 but before manifest write still produces a journal
- if manifest write fails, journal should already exist on disk

In a manifest-write failure case:

- `success = false`
- `journal_written = true`
- `manifest_written = false`
- `terminated_at_stage = 7`

This preserves the current journal-then-pointer discipline while making failure runs inspectable.

## Implementation Plan

### 1. Add a dedicated journal module

Create:

- `kdb_compiler/run_journal.py`

Responsibilities:

- `JOURNAL_SCHEMA_VERSION = "2.0"`
- `RunJournalBuilder`
- helper functions for stage timing and final assembly

### 2. Builder API

Recommended builder methods:

- `start_run(ctx, *, provider, model, max_tokens, state_root)`
- `start_stage(index, name)`
- `finish_stage(index, *, ok, note=None, **payload)`
- `record_source(record)`
- `set_manifest_stage_payload(payload)`
- `set_apply_stage_payload(payload)`
- `mark_failure(stage_index, stage_name, failure_type, failure_message)`
- `finalize(*, success, compile_success=None, compile_result=None, manifest_written=False, journal_written=False)`
- `to_dict()`

This does not need heavy dataclass modeling unless later reuse justifies it.

### 3. Refactor `kdb_compile.compile()`

`kdb_compile.py` should:

- instantiate the journal builder immediately after `RunContext`
- record stage start/finish timing in the builder
- on every failure branch:
  - mark failure
  - finalize journal
  - write journal
  - return `CompileRunResult`
- on success:
  - finalize journal
  - write journal
  - write manifest if not dry-run

Important:

- stage 7 should distinguish between journal write and manifest write
- top-level journal write should happen even on dry-run

### 4. Refactor `manifest_update.build_manifest_update()`

Change return value from:

```python
(next_manifest, journal)
```

to:

```python
(next_manifest, manifest_stage_payload)
```

Recommended `manifest_stage_payload` shape:

```json
{
  "prior_manifest_loaded": true,
  "deltas": {
    "sources_added": [],
    "sources_removed": [],
    "sources_moved": [],
    "sources_changed": [],
    "pages_created": [],
    "pages_updated": [],
    "orphans_flagged": [],
    "orphans_cleared": []
  },
  "counts": {
    "sources_after": 0,
    "pages_after": 0,
    "orphans_after": 0,
    "tombstones_after": 0
  }
}
```

Do not keep final journal assembly in `manifest_update.py`.

### 5. Extend `compiler.run_compile()`

Add an optional callback:

```python
source_stats_sink: Callable[[dict], None] | None = None
```

After each job finishes, emit a normalized per-source stats record to this sink.

The sink payload should derive from:

- `job.source_id`
- per-job latency
- `CompiledSource.compile_meta` when present
- error string when failed
- resp-stats file path when available

If needed, adjust `compile_one()` or `write_resp_stats()` so the written resp-stats path can be surfaced cleanly to the orchestrator.

## Test Migration

### Update existing tests

`test_manifest_update.py`

- stop asserting old flat journal shape
- assert manifest-stage payload shape instead
- split manifest schema version assertions from journal schema version assertions

`test_kdb_compile.py`

- dry-run expectations must change:
  - from `journal_written is False`
  - to `journal_written is True`
- allow `state/runs/<run_id>.json` to exist during dry-run
- failure-path tests should assert journal existence and `terminated_at_stage`

### Add new tests

Recommended new tests:

- `test_run_journal_builder_happy_path`
- `test_run_journal_builder_abort_stage_2`
- `test_run_journal_builder_replay_mode_nullables`
- `test_compile_writes_journal_on_stage_2_failure`
- `test_compile_writes_journal_on_stage_4_failure`
- `test_compile_writes_journal_on_dry_run`
- `test_compile_persist_state_records_manifest_skipped_on_dry_run`
- `test_compile_persist_state_records_manifest_not_written_on_failure`
- `test_run_journal_top_level_success_is_end_to_end_success`
- `test_run_journal_contains_resp_stats_refs_for_live_jobs`

## Rollout Recommendation

Implement in three patches:

1. Add `run_journal.py`, split schema versions, and builder unit tests.
2. Refactor orchestrator and manifest-update plumbing.
3. Extend compiler per-source telemetry and complete integration tests.

That sequencing keeps the change controlled and makes regressions easier to isolate.

## Final Recommendations

Recommended calls for Opus to proceed with:

1. Always write the run journal, including failures.
2. Write the run journal for dry-run too.
3. Move final journal assembly to `kdb_compile.py`.
4. Create a dedicated journal module.
5. Split manifest and journal schema versions.
6. Keep the run journal compact and queryable; use `resp_stats_ref` for deep artifacts.
