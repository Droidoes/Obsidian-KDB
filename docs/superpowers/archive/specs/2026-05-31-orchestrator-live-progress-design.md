# Orchestrator Live Progress — Design Spec

**Date:** 2026-05-31
**Status:** Approved (design); pending spec review → implementation plan
**Scope:** the 0.5.0 "stdout / progress messaging" item; **supersedes the console
approach of #101** (per-source snapshot to stderr, gated at `--log-level info/debug`).
**Target files:** `kdb_compiler/orchestrator_events.py` (console renderer),
`kdb_compiler/kdb_orchestrate.py` (CLI wiring + two new stage-start events).

---

## Goal

Give an attended `kdb-orchestrate` run a **blow-by-blow, real-time progress report on
stdout, on by default** — what source is being processed, its Pass-1 / Pass-2 stages
with elapsed time, running processed/skipped/quarantined counts, and errors as they
happen. Keep it lean (no dashboard); the event JSONL stays the exhaustive record.

## Context

- **#96** writes a structured `orchestrator_events.jsonl` (severity taxonomy) and a slim
  `last_orchestrate.json`; the CLI prints only a terse final report to stdout.
- **#101** teed a per-source *snapshot* line to **stderr**, but only at `--log-level
  info/debug`; the default `warning` is silent. A ~30-min attended run therefore shows
  **zero output until the end** ("felt like a hang") unless you opt into info.
- The orchestrator already emits per-stage **completion** events: `source_started`,
  `pass1_enrich_completed`, `pass1_gate_signal` / `pass1_gate_noise`,
  `pass2_compile_completed`, `source_commit_completed`, `source_quarantined`. There are
  **no stage-start events** for the two long LLM stages.

## Console contract

**Stream & default.** Live progress → **stdout, on by default.** A new **`--quiet`** flag
silences it (unattended/scripted runs). **`--log-level {warning,info,debug}` now controls
only the JSONL verbosity** — it no longer gates the console. The final report still prints
to stdout; the run is launched attended, and machine consumers read the JSON files, not
stdout, so default-on progress breaks nothing.

**Output format** (illustrative; exact glyphs/spacing settle at implementation):
```
kdb-orchestrate · run <run_id> · 29 to process, 7 unchanged (skipped)

[ 1/29] ▸ Buffett Munger/1979-letter.md
         pass-1 enrich…  ✓ 4.2s  (signal)
         pass-2 compile… ✓ 11.8s (7 entities)
         committed ✓    · done 1 · skipped 0 · noise 0 · quarantined 0
[ 2/29] ▸ note-x.md
         pass-1 enrich…  ✓ 3.1s  (noise — skipped pass-2)
[ 3/29] ▸ broken.md
         pass-2 compile… ⚠ quarantined (error_compile) — see event_log
…
⏱ 18:42  reconcile ✓ · finalize ✓
```
The `pass-1 enrich…` / `pass-2 compile…` lines print **when the stage starts**, then are
completed with `✓ <elapsed>` (or `⚠ <reason>`) — so the long LLM call is visibly
in-progress, not a blank wait. Running counters trail each source. Plain scrolling
`print` — **no `\r`/`isatty`/spinner** (consistent with #101's deliberate choice).

## Mechanism

1. **Two new stage-start events** in `kdb_orchestrate.py`: `pass1_enrich_started` and
   `pass2_compile_started` (severity `info`), emitted immediately before each LLM call.
   These let the console show "…in progress" before the wait, and also enrich the JSONL.
2. **Decouple the console renderer from the JSONL severity filter** in `EventRecorder`.
   Today the console tee lives inside the `should_record(severity)` branch, so at default
   `warning` it prints nothing. Change: when a console is attached, the renderer reacts to
   a **curated set of progress `event_type`s** (started/completed/gate/commit/quarantine/
   reconcile/finalize) **regardless** of whether the event passes the file's severity gate.
   The JSONL filter is unchanged and independent.
3. **Elapsed** is computed in the renderer by deltaing consecutive stage events with the
   recorder's existing injectable `clock` (start stamped on each `*_started`; printed on
   the matching `*_completed`/quarantine).
4. **Counts.** `[n/total]` denominator = the plan's to-compile count; `skipped` = the plan
   diff (unchanged sources); `done`/`noise`/`quarantined` tallied as today. This reinstates
   a denominator (#101 deliberately omitted it; the user now wants it).
5. **CLI wiring.** Replace `progress_console = sys.stderr if log_level in (info,debug)`
   with `progress_console = None if args.quiet else sys.stdout`. Add `--quiet`.

## Errors

`source_quarantine` / `run_fatal` / `invariant_violation` print an inline `⚠` line in the
stream as they happen, and still land in the event log + the final alarm/summary
(unchanged). The final report block is unchanged except it now follows the live stream.

## Out of scope

- No in-place dashboard, spinner, progress bar, or TTY/`isatty` machinery.
- No change to the event JSONL schema/verbosity semantics or `last_orchestrate.json`.
- No change to the final report's content (it already covers exit/counts/paths/alarm).

## Testing

- **Unit** (`test_orchestrator_events.py`): drive the renderer with a scripted event
  sequence + a fake clock + `StringIO`; assert (a) the per-source header with `[n/total]`,
  (b) `pass-1`/`pass-2` started→completed lines with elapsed, (c) trailing counts,
  (d) the `noise → skipped pass-2` path, (e) an inline `⚠` quarantine line, (f) the
  `--quiet`/no-console path prints nothing while the JSONL is still written.
- **Integration** (`test_kdb_orchestrate.py`): a default run streams progress to stdout;
  `--quiet` stdout is empty; the event JSONL is identical in both.
