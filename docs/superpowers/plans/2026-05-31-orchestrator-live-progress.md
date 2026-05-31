# Orchestrator Live Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream a real-time, per-source, per-stage progress narrative to stdout (default-on) during a `kdb-orchestrate` run, with elapsed times, running counts, and inline errors.

**Architecture:** The `EventRecorder` already sees every orchestrator event. We (1) decouple its console tee from the JSONL severity filter so progress renders regardless of file verbosity, (2) rewrite the renderer to emit per-stage lines with elapsed time + a `[n/total]` header + running counts, (3) add two stage-start events to the orchestrator and a `set_progress_plan` call, and (4) wire the CLI to attach `sys.stdout` by default with a `--quiet` opt-out. The event JSONL and `last_orchestrate.json` are unchanged.

**Tech Stack:** Python 3 stdlib, pytest. Files: `kdb_compiler/orchestrator_events.py`, `kdb_compiler/kdb_orchestrate.py`, `kdb_compiler/tests/test_orchestrator_events.py`, `kdb_compiler/tests/test_kdb_orchestrate.py`.

**Spec:** `docs/superpowers/specs/2026-05-31-orchestrator-live-progress-design.md`

**Note:** This supersedes #101's console approach (stderr, gated at `--log-level info/debug`). The #101 renderer tests (old snapshot format, info-gated streaming) are **replaced** by the new-format tests below — that is expected, not a regression.

---

### Task 1: Rewrite the EventRecorder console renderer (decouple + per-stage format)

**Files:**
- Modify: `kdb_compiler/orchestrator_events.py` (`EventRecorder`: `__init__` state, `record_event`, `_render_console`, drop `_snapshot_line`, add `set_progress_plan`)
- Test: `kdb_compiler/tests/test_orchestrator_events.py` (replace the #101 console tests)

- [ ] **Step 1: Write the failing tests**

Replace the existing #101 console tests in `test_orchestrator_events.py` (anything asserting the old `⏱ MM:SS [N] enriched · …` snapshot or info-gated streaming) with these. Add a controllable clock helper at module scope:

```python
import io

class _Clock:
    """Controllable monotonic stand-in: tests set .now before each event."""
    def __init__(self) -> None:
        self.now = 0.0
    def __call__(self) -> float:
        return self.now


def _rec(tmp_path, *, log_level="warning", console=None, clock=None):
    return EventRecorder(
        run_id="RUN1",
        events_path=tmp_path / "runs" / "RUN1" / "orchestrator_events.jsonl",
        log_level=log_level,
        console=console,
        clock=clock or _Clock(),
    )


def test_progress_renders_at_warning_but_not_written_to_jsonl(tmp_path):
    # Decoupling: an info progress event prints to console even at the default
    # 'warning' level, yet is NOT recorded to the JSONL (file verbosity unchanged).
    out = io.StringIO()
    rec = _rec(tmp_path, log_level="warning", console=out)
    rec.set_progress_plan(total=2, skipped=5)
    rec.record(stage="source", event_type="source_started", severity="info",
               message="", source_id="a.md")
    assert "[  1/2] ▸ a.md" in out.getvalue()
    assert "2 to process, 5 unchanged (skipped)" in out.getvalue()
    # info event not in the JSONL filter at warning level
    assert rec.recorded_events == []


def test_per_stage_elapsed_and_counts(tmp_path):
    clk = _Clock()
    out = io.StringIO()
    rec = _rec(tmp_path, console=out, clock=clk)
    rec.set_progress_plan(total=1, skipped=0)
    rec.record(stage="source", event_type="source_started", severity="info",
               message="", source_id="a.md")
    clk.now = 10.0
    rec.record(stage="pass1_enrich", event_type="pass1_enrich_started",
               severity="info", message="", source_id="a.md")
    clk.now = 14.2
    rec.record(stage="pass1_enrich", event_type="pass1_enrich_completed",
               severity="info", message="", source_id="a.md")
    clk.now = 20.0
    rec.record(stage="pass2_compile", event_type="pass2_compile_started",
               severity="info", message="", source_id="a.md")
    clk.now = 31.8
    rec.record(stage="pass2_compile", event_type="pass2_compile_completed",
               severity="info", message="", source_id="a.md")
    rec.record(stage="commit", event_type="source_commit_completed",
               severity="info", message="", source_id="a.md")
    text = out.getvalue()
    assert "pass-1 enrich…" in text
    assert "pass-1 ✓ 4.2s" in text
    assert "pass-2 compile…" in text
    assert "pass-2 ✓ 11.8s" in text
    assert "committed ✓" in text
    assert "done 1 · skipped 0 · noise 0 · quarantined 0" in text


def test_noise_path_and_quarantine_alarm(tmp_path):
    out = io.StringIO()
    rec = _rec(tmp_path, console=out)
    rec.set_progress_plan(total=2, skipped=0)
    rec.record(stage="source", event_type="source_started", severity="info",
               message="", source_id="n.md")
    rec.record(stage="pass1_gate", event_type="pass1_gate_noise", severity="info",
               message="", source_id="n.md")
    rec.record(stage="source", event_type="source_started", severity="info",
               message="", source_id="bad.md")
    rec.record(stage="pass2_compile", event_type="source_quarantined",
               severity="source_quarantine", message="Pass-2 compile failed",
               source_id="bad.md", error="error_compile")
    text = out.getvalue()
    assert "noise — skipping pass-2" in text
    assert "⚠ source_quarantine: bad.md" in text


def test_no_console_still_tallies(tmp_path):
    rec = _rec(tmp_path, console=None)
    rec.record(stage="commit", event_type="source_commit_completed",
               severity="info", message="", source_id="a.md")
    assert rec._tallies["committed"] == 1  # counters update without a console
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest kdb_compiler/tests/test_orchestrator_events.py -m "not live" -q`
Expected: FAIL — `set_progress_plan` missing / new lines absent.

- [ ] **Step 3: Add renderer state to `__init__`**

In `EventRecorder.__init__`, replace the Task #101 state block:

```python
        # Task #101 — live progress tee (None = file-only, no console output).
        self._console = console
        self._clock = clock
        self._start = clock()
        self._source_n = 0
        self._current_source: str | None = None
        self._tallies = {
            "enriched": 0, "compiled": 0, "committed": 0,
            "noise": 0, "quarantined": 0,
        }
```

with:

```python
        # Live progress tee (None = file-only). The console renderer is
        # independent of the JSONL severity filter (see record_event).
        self._console = console
        self._clock = clock
        self._start = clock()
        self._stage_t0 = self._start
        self._source_n = 0
        self._total = 0
        self._skipped = 0
        self._current_source: str | None = None
        self._tallies = {
            "enriched": 0, "compiled": 0, "committed": 0,
            "noise": 0, "quarantined": 0,
        }
```

- [ ] **Step 4: Decouple console rendering from the JSONL filter in `record_event`**

Replace the current `record_event`:

```python
    def record_event(self, event: OrchestratorEvent) -> OrchestratorEvent | None:
        if not self.should_record(event.severity):
            return None
        self.recorded_events.append(event)
        try:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as f:
                json.dump(event.to_dict(), f, ensure_ascii=False, sort_keys=False)
                f.write("\n")
        except OSError:
            self.event_log_failed = True
        self._render_console(event)
        return event
```

with (console + counters fire ALWAYS; only the JSONL write is gated):

```python
    def record_event(self, event: OrchestratorEvent) -> OrchestratorEvent | None:
        # Console progress + counters are independent of file verbosity: the
        # live narrative shows every milestone regardless of --log-level.
        self._render_console(event)
        if not self.should_record(event.severity):
            return None
        self.recorded_events.append(event)
        try:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as f:
                json.dump(event.to_dict(), f, ensure_ascii=False, sort_keys=False)
                f.write("\n")
        except OSError:
            self.event_log_failed = True
        return event
```

- [ ] **Step 5: Add `set_progress_plan` + rewrite the renderer; drop `_snapshot_line`**

Replace the entire Task #101 block (`_snapshot_line` and `_render_console`) with:

```python
    # -- live progress tee (best-effort, never raises) --

    def set_progress_plan(self, *, total: int, skipped: int) -> None:
        """Record the run's denominator/skip counts and print the run header."""
        self._total = total
        self._skipped = skipped
        if self._console is None:
            return
        try:
            self._console.write(
                f"kdb-orchestrate · run {self.run_id} · "
                f"{total} to process, {skipped} unchanged (skipped)\n\n")
            self._console.flush()
        except (OSError, ValueError):
            pass

    def _elapsed(self, since: float) -> str:
        return f"{max(0.0, self._clock() - since):.1f}s"

    def _mmss(self) -> str:
        elapsed = int(max(0.0, self._clock() - self._start))
        mm, ss = divmod(elapsed, 60)
        return f"{mm:02d}:{ss:02d}"

    def _counts_tail(self) -> str:
        t = self._tallies
        return (f"done {t['committed']} · skipped {self._skipped} · "
                f"noise {t['noise']} · quarantined {t['quarantined']}")

    def _render_console(self, event: OrchestratorEvent) -> None:
        """Tally counters (always) and, when a console is attached, print the
        live per-stage progress narrative. Best-effort: never a second failure
        path."""
        et = event.event_type
        if et == "source_started":
            self._source_n += 1
            self._current_source = event.source_id
        elif et in ("pass1_enrich_started", "pass2_compile_started"):
            self._stage_t0 = self._clock()
        tally = _TALLY_BY_EVENT.get(et)
        if tally:
            self._tallies[tally] += 1

        if self._console is None:
            return
        try:
            self._write_progress(event, et)
            self._console.flush()
        except (OSError, ValueError):
            pass  # console is best-effort

    def _write_progress(self, event: OrchestratorEvent, et: str) -> None:
        w = self._console.write
        src = (self._current_source or "")[-48:]
        den = self._total if self._total else "?"
        if et == "source_started":
            w(f"[{self._source_n:>3}/{den}] ▸ {src}\n")
        elif et == "pass1_enrich_started":
            w("         pass-1 enrich…\n")
        elif et == "pass1_enrich_completed":
            w(f"         pass-1 ✓ {self._elapsed(self._stage_t0)}\n")
        elif et == "pass1_gate_noise":
            w(f"         noise — skipping pass-2  · {self._counts_tail()}\n")
        elif et == "pass2_compile_started":
            w("         pass-2 compile…\n")
        elif et == "pass2_compile_completed":
            w(f"         pass-2 ✓ {self._elapsed(self._stage_t0)}\n")
        elif et == "source_commit_completed":
            w(f"         committed ✓  · {self._counts_tail()}\n")
        elif event.severity in _ALARM_SEVERITIES:
            w(f"         ⚠ {event.severity}: "
              f"{event.source_id or event.stage} — {event.message}\n")
        elif et in ("reconcile_completed", "finalize_completed", "finalize_skipped"):
            w(f"⏱ {self._mmss()}  {et.replace('_', ' ')}\n")
```

Also delete the now-unused `_SOURCE_TERMINAL_EVENTS` constant near the top of the file (it was only read by the old `_snapshot_line` path).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest kdb_compiler/tests/test_orchestrator_events.py -m "not live" -q`
Expected: PASS (all, including the existing non-console event/invariant tests).

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/orchestrator_events.py kdb_compiler/tests/test_orchestrator_events.py
git commit -m "feat(orchestrator): per-stage live progress renderer, decoupled from JSONL filter"
```

---

### Task 2: Wire the orchestrator + CLI (stage-start events, plan, stdout default, --quiet)

**Files:**
- Modify: `kdb_compiler/kdb_orchestrate.py` (two `*_started` events, `set_progress_plan` call, `run()` `quiet` param + console wiring, `--quiet` arg, `main`)
- Test: `kdb_compiler/tests/test_kdb_orchestrate.py` (replace the #101 info-streams/warning-quiet integration tests)

- [ ] **Step 1: Write the failing integration tests**

Find the existing #101 integration tests in `test_kdb_orchestrate.py` (the ones asserting stderr streaming at `--log-level info` and silence at `warning`) and replace them with the new contract. Use the file's existing run fixture/harness (the same one those #101 tests used — reuse its pipeline/vault/graph setup and its monkeypatched enrich/compile). The assertions:

```python
def test_default_run_streams_progress_to_stdout(orchestrate_env, capsys):
    # orchestrate_env = the existing fixture used by the prior #101 tests:
    # a built pipeline + vault + graph with enrich/compile monkeypatched to
    # produce >=1 signal source. Adjust the call to match the fixture's helper.
    run(**orchestrate_env.run_kwargs())  # default: quiet=False, log_level="warning"
    out = capsys.readouterr().out
    assert "kdb-orchestrate · run " in out          # header
    assert "to process" in out
    assert "▸ " in out                               # a per-source line
    assert "pass-1 enrich…" in out                   # stage-start marker
    assert "pass-2 compile…" in out


def test_quiet_suppresses_progress_but_keeps_jsonl(orchestrate_env, capsys):
    res = run(**orchestrate_env.run_kwargs(quiet=True))
    out = capsys.readouterr().out
    assert "pass-1 enrich…" not in out
    assert "▸ " not in out
    # the event log is still written
    assert res.event_log_path.exists()
```

If the prior #101 tests targeted stderr, switch their capture to `capsys.readouterr().out` (stdout) and drop `--log-level info`. Keep whatever fixture-construction those tests already had; only the invocation (`quiet=`) and assertions change.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest kdb_compiler/tests/test_kdb_orchestrate.py -m "not live" -q -k "stream or quiet"`
Expected: FAIL — `run()` has no `quiet` kwarg / `pass-1 enrich…` absent from stdout.

- [ ] **Step 3: Add the `quiet` param and stdout console wiring to `run()`**

In `kdb_compiler/kdb_orchestrate.py`, change the `run()` signature line:

```python
def run(
    *, pipeline_id: str, vault_root: Path, state_root: Path, graph_path: Path,
    provider: str, model: str, max_tokens: int = 32768, dry_run: bool = False,
    limit: int | None = None, log_level: OrchestratorLogLevel = "warning",
) -> OrchestrateResult:
```

to add `quiet`:

```python
def run(
    *, pipeline_id: str, vault_root: Path, state_root: Path, graph_path: Path,
    provider: str, model: str, max_tokens: int = 32768, dry_run: bool = False,
    limit: int | None = None, log_level: OrchestratorLogLevel = "warning",
    quiet: bool = False,
) -> OrchestrateResult:
```

Then replace the Task #101 console-wiring block:

```python
    # Task #101: stream a live per-source progress snapshot to stderr at
    # info/debug (the default 'warning' level stays quiet for scripted runs).
    progress_console = sys.stderr if log_level in ("info", "debug") else None
    recorder = EventRecorder.for_state_root(
        state_root=state_root, run_id=ctx.run_id, log_level=log_level,
        console=progress_console)
```

with (live progress on stdout by default; `--quiet` silences; log_level only governs the JSONL):

```python
    # Live progress streams to stdout by default; --quiet silences it. The
    # JSONL verbosity is governed independently by log_level.
    progress_console = None if quiet else sys.stdout
    recorder = EventRecorder.for_state_root(
        state_root=state_root, run_id=ctx.run_id, log_level=log_level,
        console=progress_console)
```

- [ ] **Step 4: Announce the plan to the recorder after scan**

Immediately after the `scan_completed` event is recorded (the `recorder.record(stage="scan", event_type="scan_completed", …)` block ends around line 536), add:

```python
    recorder.set_progress_plan(
        total=len(scan.to_compile),
        skipped=max(0, len(scan.files) - len(scan.to_compile)),
    )
```

- [ ] **Step 5: Emit the two stage-start events**

In the source loop, add `pass1_enrich_started` right before the `enrich = enrich_one(` call (currently ~line 585):

```python
                recorder.record(
                    stage="pass1_enrich", event_type="pass1_enrich_started",
                    severity="info", message="Pass-1 enrich started",
                    source_id=source_id)
                enrich = enrich_one(
```

And `pass2_compile_started` right before the `result = compile_source(` call (currently ~line 665):

```python
                recorder.record(
                    stage="pass2_compile", event_type="pass2_compile_started",
                    severity="info", message="Pass-2 compile started",
                    source_id=source_id)
                result = compile_source(
```

- [ ] **Step 6: Add the `--quiet` CLI flag and pass it through**

In `_build_parser()`, add after the `--debug` argument:

```python
    p.add_argument("--quiet", action="store_true",
                   help="suppress the live stdout progress narrative "
                        "(the final report and event log are unaffected)")
```

In `main()`, pass `quiet` into the `run(...)` call — change:

```python
    res = run(
        pipeline_id=args.pipeline, vault_root=vault_root, state_root=state_root,
        graph_path=graph_path, provider=args.provider, model=args.model,
        max_tokens=args.max_tokens, dry_run=args.dry_run, limit=args.limit,
        log_level=_resolve_log_level(args))
```

to:

```python
    res = run(
        pipeline_id=args.pipeline, vault_root=vault_root, state_root=state_root,
        graph_path=graph_path, provider=args.provider, model=args.model,
        max_tokens=args.max_tokens, dry_run=args.dry_run, limit=args.limit,
        log_level=_resolve_log_level(args), quiet=args.quiet)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m pytest kdb_compiler/tests/test_kdb_orchestrate.py -m "not live" -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add kdb_compiler/kdb_orchestrate.py kdb_compiler/tests/test_kdb_orchestrate.py
git commit -m "feat(orchestrator): stream live progress to stdout by default + --quiet; stage-start events"
```

---

### Task 3: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full non-live suite**

Run: `python3 -m pytest -m "not live" -q`
Expected: PASS (matching the project's standing green baseline; live smoke tests skipped).

- [ ] **Step 2: Smoke-render the narrative without the network**

Confirm the renderer output by replaying a scripted event sequence (no API): in a Python REPL or a scratch test, build an `EventRecorder` with `console=sys.stdout`, call `set_progress_plan(total=3, skipped=7)`, and feed `source_started → pass1_enrich_started → pass1_enrich_completed → pass2_compile_started → pass2_compile_completed → source_commit_completed`, then a noise source and a quarantined source. Eyeball that it reads like the spec's mock.

- [ ] **Step 3: Commit (if Step 2 prompted any tweak)**

```bash
git add -A
git commit -m "test(orchestrator): full non-live suite green for live-progress"
```

---

## Self-Review

**Spec coverage:**
- Stream & default (stdout default-on, `--quiet`, log-level→JSONL only) → Task 2 Steps 3, 6 ✓
- Output format (header, per-stage started→completed elapsed, counts, noise/skip, alarms) → Task 1 Step 5 ✓
- Mechanism: two stage-start events → Task 2 Step 5; decouple console from filter → Task 1 Step 4; elapsed via clock → Task 1 Step 5; `[n/total]` + skipped → Task 1 Step 5 + Task 2 Step 4 ✓
- Errors inline + final report unchanged → Task 1 Step 5 (alarm branch); final report untouched ✓
- JSONL unchanged → `should_record`/`recorded_events` path untouched; only render moved ahead of the gate ✓
- Testing (unit + integration) → Task 1 Step 1, Task 2 Step 1, Task 3 ✓

**Placeholder scan:** none. The one soft spot — `orchestrate_env` in Task 2's tests — is explicitly "reuse the existing #101 integration fixture/harness in this file"; the implementer adapts the call to that fixture's helper rather than inventing one.

**Type consistency:** `set_progress_plan(*, total, skipped)` defined (Task 1) and called with those kwargs (Task 2). `quiet: bool` added to `run()` signature (Task 2 Step 3) and passed from `main` (Step 6) and tests (Step 1). `_elapsed`/`_mmss`/`_counts_tail`/`_write_progress` all defined and referenced within Task 1 Step 5. Event types `pass1_enrich_started`/`pass2_compile_started` emitted (Task 2 Step 5) match the renderer's branches (Task 1 Step 5).
