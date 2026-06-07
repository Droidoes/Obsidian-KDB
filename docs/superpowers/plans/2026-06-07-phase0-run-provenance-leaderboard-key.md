# #111 Phase 0 — Run Provenance + Leaderboard Key Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a `release_version` on every benchmark run and key the `kdb-benchmark` leaderboard on `(provider, model, release_version)` — so the upcoming clean-slate baselines (`v0.5.5` → `v0.5.6` → `v0.5.7`) accumulate as distinct, per-model-comparable rows.

**Architecture:** Three small, additive changes to the existing #109 benchmark machinery: (1) add `release_version` (captured via `git describe --tags --dirty`) to `RunMeasurementHeader`, which already flows into `measurements.json`; (2) accumulate the orchestrate stdout progress in the `EventRecorder` and write it to the benchmark per-run dir as `console.log`; (3) change the leaderboard's dedup/replace key in `tools/benchmark/cli.py` from `model` to the `(provider, model, release_version)` triple.

**Tech Stack:** Python 3, stdlib `subprocess`/`dataclasses`/`json`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md` §3a (#111 Phase 0). Branch `feat/111-structured-output-upgrade` (currently at `v0.5.4`/`d41da4a`).

**Conventions:** run tests with `.venv/bin/pytest -m "not live"` (plain `pytest`/`python` aren't on PATH; `.env` auto-loads keys so always pass `-m "not live"`). Baseline test count at branch start: **1209 passed**.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `common/version.py` | Create | `release_version()` — `git describe --tags --dirty --always`, best-effort |
| `common/measurement.py` | Modify | add `release_version: str = ""` to `RunMeasurementHeader` |
| `orchestrator/kdb_orchestrate.py` | Modify | set `release_version=release_version()` in the header (`~:953`); write `console.log` via emit |
| `kdb_compiler`/orchestrator event recorder | Modify | `EventRecorder` accumulates rendered console lines + exposes `console_text()` |
| `orchestrator/emit_kpis.py` | Modify | `maybe_emit_kpis` gains `console_text` → writes `<benchmark-run-dir>/console.log` |
| `tools/benchmark/cli.py` | Modify | leaderboard keyed on `(provider, model, release_version)` |

---

## Task 1: `release_version` provenance helper + header field

**Files:**
- Create: `common/version.py`
- Modify: `common/measurement.py` (`RunMeasurementHeader`)
- Test: `common/tests/test_version.py` (create), `common/tests/test_measurement.py` (existing — find with `grep -rl RunMeasurementHeader common/tests/`)

- [ ] **Step 1: Write the failing test for the helper.** In `common/tests/test_version.py`:

```python
import re
from common.version import release_version

def test_release_version_returns_git_describe_string():
    # In this repo HEAD is on/near a v0.5.x tag → starts with "v0." (or is a sha/"unknown" in odd CI).
    v = release_version()
    assert isinstance(v, str) and v
    # Tolerant: a real describe like v0.5.4 / v0.5.4-3-gabc123 / v0.5.4-dirty, OR the "unknown" fallback.
    assert v == "unknown" or re.match(r"^v\d|^[0-9a-f]{7,}", v)

def test_release_version_unknown_on_failure(monkeypatch):
    import common.version as ver
    def boom(*a, **k):
        raise OSError("no git")
    monkeypatch.setattr(ver.subprocess, "run", boom)
    assert release_version() == "unknown"
```

- [ ] **Step 2: Run it — expect failure.**

Run: `.venv/bin/pytest common/tests/test_version.py -v -m "not live"`
Expected: FAIL — `ModuleNotFoundError: common.version`.

- [ ] **Step 3: Implement `common/version.py`.**

```python
"""version — best-effort git release identifier for run provenance.

`git describe --tags --dirty --always` yields the nearest semver tag (e.g.
`v0.5.4`), `v0.5.4-3-g<sha>` off-tag, a `-dirty` suffix when the working tree
has uncommitted changes (so a benchmark run is never silently mislabeled as a
clean release), or a bare short-sha / "unknown" when git is unavailable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def release_version() -> str:
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--dirty", "--always"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        v = out.stdout.strip()
        return v or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
```

- [ ] **Step 4: Run — expect pass.**

Run: `.venv/bin/pytest common/tests/test_version.py -v -m "not live"`
Expected: PASS (2).

- [ ] **Step 5: Add the failing header-field test.** In the existing `RunMeasurementHeader` test module:

```python
def test_header_carries_release_version():
    from common.measurement import RunMeasurementHeader
    import dataclasses
    h = RunMeasurementHeader(
        run_id="r", corpus_fingerprint="cf", pass1_prompt_version="1",
        pass2_prompt_version="", scanned=1, to_compile=1, signal=1, noise=0,
        p1_attempted=1, p2_attempted=1, release_version="v0.5.5",
    )
    assert dataclasses.asdict(h)["release_version"] == "v0.5.5"

def test_header_release_version_defaults_empty():
    from common.measurement import RunMeasurementHeader
    h = RunMeasurementHeader(
        run_id="r", corpus_fingerprint="cf", pass1_prompt_version="1",
        pass2_prompt_version="", scanned=1, to_compile=1, signal=1, noise=0,
        p1_attempted=1, p2_attempted=1,
    )
    assert h.release_version == ""   # back-compat for headers written pre-#111
```

- [ ] **Step 6: Run — expect failure** (`unexpected keyword 'release_version'`).

Run: `.venv/bin/pytest common/tests/ -k release_version -v -m "not live"`

- [ ] **Step 7: Add the field.** In `common/measurement.py`, `RunMeasurementHeader`, add as the LAST field (default preserves back-compat with existing `measurement_header.json` that lack it — `load_run_measurements` builds `RunMeasurementHeader(**header_data)`, so a missing key must default):

```python
    release_version: str = ""
```

- [ ] **Step 8: Run — expect pass; then full suite.**

Run: `.venv/bin/pytest common/tests/ -k release_version -v -m "not live"` → PASS
Run: `.venv/bin/pytest -m "not live" -q` → green (report count; baseline 1209 + 4 new).

- [ ] **Step 9: Commit.**

```bash
git add common/version.py common/measurement.py common/tests/test_version.py common/tests/test_measurement.py
git commit -m "feat(provenance): release_version helper + RunMeasurementHeader field (#111 Phase 0)"
```

---

## Task 2: Wire `release_version` into the run + write `console.log`

**Files:**
- Modify: `orchestrator/kdb_orchestrate.py` (header construction `~:953`; pass console text to emit)
- Modify: the `EventRecorder` module (find: `grep -rl "class EventRecorder" --include="*.py"` — it lives in the orchestrator/compiler event module) — accumulate rendered console lines
- Modify: `orchestrator/emit_kpis.py` (`maybe_emit_kpis` writes `console.log`)
- Test: `orchestrator/tests/test_kdb_orchestrate.py`, the EventRecorder test module, `orchestrator/tests/` for emit

- [ ] **Step 1: Failing test — header gets a real release_version.** In `orchestrator/tests/test_kdb_orchestrate.py` (reuse the existing run harness/fixture that drives `run(...)` with fakes — match how other tests construct it):

```python
def test_run_header_records_release_version(<existing run fixtures>):
    # After a fake run, the written measurement_header.json carries a non-empty release_version.
    ...  # drive run(...), read <state runs>/<run_id>/measurement_header.json
    assert header_json["release_version"]  # non-empty (real git describe, or "unknown")
```

- [ ] **Step 2: Run — expect failure** (field present but empty / KeyError). `.venv/bin/pytest orchestrator/tests/test_kdb_orchestrate.py -k release_version -v -m "not live"`

- [ ] **Step 3: Set it in the header.** In `orchestrator/kdb_orchestrate.py`, add the import (top, with the other `common.*`):

```python
from common.version import release_version
```

and in the `RunMeasurementHeader(...)` construction (`~:953`) add:

```python
            release_version=release_version(),
```

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest orchestrator/tests/test_kdb_orchestrate.py -k release_version -v -m "not live"`

- [ ] **Step 5: Failing test — EventRecorder accumulates console text.** In the EventRecorder test module:

```python
def test_recorder_accumulates_console_text():
    # A recorder with a console sink records the rendered progress lines for later capture.
    import io
    rec = <construct EventRecorder with console=io.StringIO(), clock=<fake>>
    rec.set_progress_plan(total=1, skipped=0)   # or the real plan method
    # ... record a couple of per-source events that render to console ...
    text = rec.console_text()
    assert "▸" in text or text.strip()   # the rendered narrative is captured
```

(Read the recorder first: it has a `_render_console`/console sink already — Task #101/#102. Add a `list[str]` buffer that every rendered line is appended to, and a `console_text() -> "\n".join(buffer)` accessor. Best-effort — never raise.)

- [ ] **Step 6: Run — expect failure** (`console_text` not defined). 

- [ ] **Step 7: Implement the accumulation.** In `EventRecorder`: add `self._console_lines: list[str] = []` in `__init__`; everywhere `_render_console` writes a line to the console sink, also `self._console_lines.append(line)`; add:

```python
    def console_text(self) -> str:
        return "\n".join(self._console_lines)
```

- [ ] **Step 8: Run — expect pass.**

- [ ] **Step 9: Failing test — `console.log` written to the benchmark run dir.** In the emit-kpis test module (find: `grep -rl maybe_emit_kpis orchestrator/tests/`), with `get_benchmark_runs_dir` monkeypatched to `tmp_path`:

```python
def test_emit_writes_console_log(tmp_path, monkeypatch, <emit fixtures>):
    import orchestrator.emit_kpis as ek
    monkeypatch.setattr(ek, "get_benchmark_runs_dir", lambda: tmp_path)
    ek.maybe_emit_kpis(emit_kpis=True, run_id="r1", ..., console_text="hello\nprogress")
    assert (tmp_path / "r1" / "console.log").read_text() == "hello\nprogress"

def test_emit_skips_console_log_when_no_text(tmp_path, monkeypatch, <emit fixtures>):
    import orchestrator.emit_kpis as ek
    monkeypatch.setattr(ek, "get_benchmark_runs_dir", lambda: tmp_path)
    ek.maybe_emit_kpis(emit_kpis=True, run_id="r1", ..., console_text=None)
    assert not (tmp_path / "r1" / "console.log").exists()
```

- [ ] **Step 10: Run — expect failure** (`unexpected keyword 'console_text'`).

- [ ] **Step 11: Implement.** `maybe_emit_kpis` gains `console_text: str | None = None`. After it computes the benchmark run dir (`get_benchmark_runs_dir() / run_id`, which it already creates), add — best-effort, never abort the run:

```python
    if console_text:
        try:
            (bench_run_dir).mkdir(parents=True, exist_ok=True)
            (bench_run_dir / "console.log").write_text(console_text, encoding="utf-8")
        except OSError:
            log.warning("could not write console.log for run %s", run_id)
```

Then in `kdb_orchestrate.run()`, pass `console_text=recorder.console_text() if not quiet else None` into the `maybe_emit_kpis(...)` call (`~:968`).

- [ ] **Step 12: Run targeted + full suite.**

Run: `.venv/bin/pytest orchestrator/tests/ -k "release_version or console" -v -m "not live"` → PASS
Run: `.venv/bin/pytest -m "not live" -q` → green (report count).

- [ ] **Step 13: Commit.**

```bash
git add orchestrator/kdb_orchestrate.py orchestrator/emit_kpis.py <event_recorder.py> orchestrator/tests/
git commit -m "feat(provenance): record release_version + save orchestrate stdout to console.log (#111 Phase 0)"
```

---

## Task 3: Leaderboard keyed on `(provider, model, release_version)`

**Files:**
- Modify: `tools/benchmark/cli.py` (`_score_command` — the `models_to_rundir` keying + the Borda `model` identifier)
- Modify: `orchestrator/emit_kpis.py` (ensure `measurements.json` `header` carries `provider`, `model`, `release_version` — provider/model are added at emit time; release_version flows from Task 1)
- Test: `tools/benchmark/tests/` (the score-command test module)

- [ ] **Step 1: Confirm the emitted header carries the triple.** Read `maybe_emit_kpis` — it already merges `provider`/`model` into the emitted `measurements.json` `header` (cli.py reads `header.model`). Confirm `release_version` is included too (it's a field on `RunMeasurementHeader` → in `dataclasses.asdict(header)` → already in the emitted header dict). If provider isn't in the header dict, add it where model is added.

- [ ] **Step 2: Failing test — same model, two release_versions → two rows.** In the score-command test module (reuse its measurements.json fixture builder):

```python
def test_leaderboard_keys_on_model_and_release_version(tmp_path, ...):
    # Two run dirs: same model "deepseek-v4-flash", provider "deepseek",
    # release_version "v0.5.5" and "v0.5.6". Both must appear as DISTINCT rows.
    write_measurements(tmp_path/"runA", model="deepseek-v4-flash", provider="deepseek", release="v0.5.5", scored={...})
    write_measurements(tmp_path/"runB", model="deepseek-v4-flash", provider="deepseek", release="v0.5.6", scored={...})
    rc = main(["score", "runA", "runB", "--runs-root", str(tmp_path), "--leaderboard", str(tmp_path/"lb.json")])
    lb = json.loads((tmp_path/"lb.json").read_text())
    keys = set(lb["models"].keys())
    assert len(keys) == 2                       # NOT collapsed to one model row
    assert any("v0.5.5" in k for k in keys) and any("v0.5.6" in k for k in keys)

def test_leaderboard_same_triple_replaces(tmp_path, ...):
    # Same model+provider+release re-run → the later run dir replaces (one row).
    write_measurements(tmp_path/"run1", model="m", provider="p", release="v0.5.5", scored={...})
    write_measurements(tmp_path/"run2", model="m", provider="p", release="v0.5.5", scored={...})
    main(["score", "run1", "run2", "--runs-root", str(tmp_path), "--leaderboard", str(tmp_path/"lb.json")])
    lb = json.loads((tmp_path/"lb.json").read_text())
    assert len(lb["models"]) == 1
    assert list(lb["models"].values())[0] == "run2"   # latest replaces
```

(Read the existing score tests to reuse their `write_measurements` helper / measurements.json shape; if none exists, build a minimal one inline.)

- [ ] **Step 3: Run — expect failure** (current keying collapses to one model row).

Run: `.venv/bin/pytest tools/benchmark/tests/ -k "release_version or triple" -v -m "not live"`

- [ ] **Step 4: Change the key.** In `tools/benchmark/cli.py` `_score_command`, replace the `model`-only key with a composite. Add a helper near the top of the function:

```python
    def _row_key(header: dict) -> str:
        # Unique leaderboard line item: provider/model@release_version.
        prov = header.get("provider", "")
        model = header.get("model", "")
        rel = header.get("release_version", "") or "unversioned"
        return f"{prov}/{model}@{rel}"
```

Then everywhere the loop currently does `model_slug = header.get("model")` and `models_to_rundir[model_slug] = run_dir`, use `key = _row_key(header)` instead (keep the missing-`model` error check). Downstream, the dict is now `{row_key: run_dir}`; pass `row_key` as the Borda `"model"` identifier (`models.append({"model": row_key, "scored": scored})`) so the ranking and `leaderboard.md` display `provider/model@release`. The prior-leaderboard load (`prior.get("models", {})`) needs no shape change — it was already `{key: run_dir}`, the key is just richer now. (Reset/migration: a pre-#111 leaderboard keyed on bare model is incompatible — document that `score` users delete the leaderboard file once, per the existing reset convention.)

- [ ] **Step 5: Run targeted — expect pass.** `.venv/bin/pytest tools/benchmark/tests/ -k "release_version or triple" -v -m "not live"`

- [ ] **Step 6: Full suite + render check.**

Run: `.venv/bin/pytest -m "not live" -q` → green (report count).
Confirm the leaderboard table/`leaderboard.md` renders the composite key sensibly (the ranking rows now read `provider/model@vX.Y.Z`); adjust the `_render_leaderboard_md` / terminal-table header label if it still says just "Model".

- [ ] **Step 7: Commit.**

```bash
git add tools/benchmark/cli.py orchestrator/emit_kpis.py tools/benchmark/tests/
git commit -m "feat(benchmark): leaderboard keyed on (provider, model, release_version) (#111 Phase 0)"
```

---

## Final verification (before tagging baseline-0 = v0.5.5)

- [ ] `.venv/bin/pytest -m "not live" -q` fully green.
- [ ] **Live smoke (Joseph fires — API cost):** one `kdb-orchestrate --model deepseek-v4-flash --emit-kpis` run on the sandbox → confirm `benchmark/runs/<id>/measurements.json` `header.release_version` reads `v0.5.4-…` (or the then-current describe), `benchmark/runs/<id>/console.log` exists and contains the progress narrative, and `kdb-benchmark score <id>` produces a `provider/model@version` leaderboard row.
- [ ] Update `docs/TASKS.md` (#111 progress) on phase completion.
- [ ] Then: tag/release **`v0.5.5`** (RELEASES.md entry) and fire the **baseline-0** clean-slate 4-model benchmark (Checkpoint per spec §3a).

---

## Self-Review

- **Spec coverage:** §3a [1a] release_version → Task 1 + Task 2 Steps 1-4; [1b] saved stdout → Task 2 Steps 5-12; [2] leaderboard key → Task 3. All §3a requirements covered.
- **Placeholders:** the EventRecorder construction in tests and the `write_measurements` fixture are deliberately referenced (not spelled out) because the exact recorder ctor + score-test helper must be read from the modules at execution time; the *behavior* each test pins (console text captured; two release_versions → two rows; same triple replaces) is unambiguous. All production-code steps carry complete code.
- **Type consistency:** `release_version()` (function) vs `RunMeasurementHeader.release_version` (field) vs `header.get("release_version")` (dict key) are used consistently; `console_text()`/`console_text=` match; `_row_key(header)` returns the same composite used as both the dict key and the Borda `"model"` id.
