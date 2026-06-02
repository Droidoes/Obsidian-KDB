"""Tests for Task #96 orchestrator structured events + invariants."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from orchestrator.orchestrator_events import (
    EventRecorder,
    OrchestratorEvent,
    OrchestratorInvariantError,
    check_orchestrator_invariant,
)


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_event_serializes_stable_json_shape() -> None:
    event = OrchestratorEvent(
        run_id="r1",
        source_id="AIML/a.md",
        stage="pass1_enrich",
        event_type="source_quarantined",
        severity="source_quarantine",
        message="bad source",
        exception_type="Pass1SchemaError",
        error="boom",
        context={"model": "m"},
        artifacts={"raw_response": "runs/r1/raw.json"},
        ts="2026-05-30T12:00:00-04:00",
    )

    d = event.to_dict()

    assert list(d) == [
        "schema_version",
        "ts",
        "run_id",
        "source_id",
        "stage",
        "event_type",
        "severity",
        "message",
        "exception_type",
        "error",
        "context",
        "artifacts",
    ]
    assert d["schema_version"] == "1.0"
    assert d["severity"] == "source_quarantine"
    assert d["context"] == {"model": "m"}


def test_recorder_appends_multiple_jsonl_rows(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "r1" / "orchestrator_events.jsonl"
    recorder = EventRecorder(run_id="r1", events_path=path, log_level="info")

    recorder.record(stage="run", event_type="run_started", severity="info", message="start")
    recorder.record(stage="run", event_type="run_finished", severity="warning", message="warn")

    rows = _lines(path)
    assert [r["event_type"] for r in rows] == ["run_started", "run_finished"]
    assert [r["severity"] for r in rows] == ["info", "warning"]
    assert len(recorder.recorded_events) == 2
    assert not recorder.event_log_failed


def test_recorder_warning_level_drops_info_and_debug(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    recorder = EventRecorder(run_id="r1", events_path=path, log_level="warning")

    assert recorder.record(stage="s", event_type="i", severity="info", message="i") is None
    assert recorder.record(stage="s", event_type="d", severity="debug", message="d") is None

    assert not path.exists()
    assert recorder.recorded_events == []


def test_recorder_info_level_keeps_info_but_drops_debug(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    recorder = EventRecorder(run_id="r1", events_path=path, log_level="info")

    recorder.record(stage="s", event_type="i", severity="info", message="i")
    recorder.record(stage="s", event_type="d", severity="debug", message="d")

    rows = _lines(path)
    assert [r["event_type"] for r in rows] == ["i"]


def test_recorder_debug_level_keeps_all_low_level_events(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    recorder = EventRecorder(run_id="r1", events_path=path, log_level="debug")

    recorder.record(stage="s", event_type="i", severity="info", message="i")
    recorder.record(stage="s", event_type="d", severity="debug", message="d")

    rows = _lines(path)
    assert [r["event_type"] for r in rows] == ["i", "d"]


@pytest.mark.parametrize(
    "severity",
    ["warning", "source_quarantine", "run_fatal", "invariant_violation"],
)
def test_high_visibility_events_are_always_recorded(tmp_path: Path, severity: str) -> None:
    path = tmp_path / f"{severity}.jsonl"
    recorder = EventRecorder(run_id="r1", events_path=path, log_level="warning")

    recorder.record(stage="s", event_type=severity, severity=severity, message="m")

    rows = _lines(path)
    assert rows[0]["severity"] == severity


def test_event_write_failure_sets_flag_without_raising(tmp_path: Path) -> None:
    # A directory path cannot be opened for append; recorder should surface the
    # observability failure via its flag and keep the original path non-throwing.
    recorder = EventRecorder(run_id="r1", events_path=tmp_path, log_level="info")

    event = recorder.record(stage="run", event_type="run_started", severity="info", message="x")

    assert event is not None
    assert recorder.event_log_failed
    assert len(recorder.recorded_events) == 1


def test_for_state_root_uses_standard_run_path(tmp_path: Path) -> None:
    recorder = EventRecorder.for_state_root(state_root=tmp_path, run_id="r1", log_level="info")

    recorder.record(stage="run", event_type="run_started", severity="info", message="start")

    assert recorder.events_path == tmp_path / "runs" / "r1" / "orchestrator_events.jsonl"
    assert recorder.events_path.exists()


def test_unknown_log_level_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown orchestrator log level"):
        EventRecorder(run_id="r1", events_path=tmp_path / "events.jsonl", log_level="trace")  # type: ignore[arg-type]


def test_invariant_check_passes_without_event(tmp_path: Path) -> None:
    recorder = EventRecorder(run_id="r1", events_path=tmp_path / "events.jsonl", log_level="debug")

    check_orchestrator_invariant(
        True,
        recorder=recorder,
        code="ok",
        stage="commit_manifest",
        message="fine",
    )

    assert recorder.recorded_events == []
    assert not recorder.events_path.exists()


def test_invariant_check_logs_and_raises_typed_error(tmp_path: Path) -> None:
    recorder = EventRecorder(run_id="r1", events_path=tmp_path / "events.jsonl", log_level="warning")

    with pytest.raises(OrchestratorInvariantError) as exc:
        check_orchestrator_invariant(
            False,
            recorder=recorder,
            code="missing_scan_entry",
            stage="scan",
            message="to_compile source has no ScanEntry",
            source_id="AIML/a.md",
            context={"pipeline_id": "vt"},
        )

    assert exc.value.code == "missing_scan_entry"
    assert exc.value.stage == "scan"
    rows = _lines(recorder.events_path)
    assert len(rows) == 1
    assert rows[0]["severity"] == "invariant_violation"
    assert rows[0]["event_type"] == "invariant_violation"
    assert rows[0]["exception_type"] == "OrchestratorInvariantError"
    assert rows[0]["error"] == "missing_scan_entry"
    assert rows[0]["source_id"] == "AIML/a.md"
    assert rows[0]["context"] == {"pipeline_id": "vt"}


def test_invariant_failure_ignores_log_level_filter(tmp_path: Path) -> None:
    recorder = EventRecorder(run_id="r1", events_path=tmp_path / "events.jsonl", log_level="warning")

    with pytest.raises(OrchestratorInvariantError):
        check_orchestrator_invariant(
            False,
            recorder=recorder,
            code="bad",
            stage="commit",
            message="bad",
        )

    assert _lines(recorder.events_path)[0]["severity"] == "invariant_violation"


# ---------------------------------------------------------------------------
# Live progress console (per-stage narrative on stdout, default-on)
# ---------------------------------------------------------------------------

class _Clock:
    """Controllable monotonic stand-in: tests set .now before each event."""
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _rec(tmp_path: Path, *, log_level="warning", console=None, clock=None) -> EventRecorder:
    return EventRecorder(
        run_id="RUN1",
        events_path=tmp_path / "runs" / "RUN1" / "orchestrator_events.jsonl",
        log_level=log_level,
        console=console,
        clock=clock or _Clock(),
    )


def test_progress_renders_at_warning_but_not_written_to_jsonl(tmp_path: Path) -> None:
    # Decoupling: an info progress event prints to console even at the default
    # 'warning' level, yet is NOT recorded to the JSONL (file verbosity unchanged).
    out = io.StringIO()
    rec = _rec(tmp_path, log_level="warning", console=out)
    rec.set_progress_plan(total=2, skipped=5)
    rec.record(stage="source", event_type="source_started", severity="info",
               message="", source_id="a.md")
    assert "[  1/2] ▸ a.md" in out.getvalue()
    assert "2 to process, 5 unchanged (skipped)" in out.getvalue()
    assert rec.recorded_events == []


def test_per_stage_elapsed_and_counts(tmp_path: Path) -> None:
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


def test_noise_path_and_quarantine_alarm(tmp_path: Path) -> None:
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


def test_no_console_still_tallies(tmp_path: Path) -> None:
    rec = _rec(tmp_path, console=None)
    rec.record(stage="commit", event_type="source_commit_completed",
               severity="info", message="", source_id="a.md")
    assert rec._tallies["committed"] == 1  # counters update without a console
