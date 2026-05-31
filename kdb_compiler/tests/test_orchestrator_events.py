"""Tests for Task #96 orchestrator structured events + invariants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler.orchestrator_events import (
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
# Task #101 — console progress display (per-source count snapshot to stderr)
# ---------------------------------------------------------------------------

class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _emit_source(rec: EventRecorder, sid: str, *, outcome: str = "committed") -> None:
    rec.record(stage="source", event_type="source_started", severity="info",
               message="started", source_id=sid)
    rec.record(stage="pass1_enrich", event_type="pass1_enrich_completed",
               severity="info", message="enriched", source_id=sid)
    if outcome == "noise":
        rec.record(stage="pass1_gate", event_type="pass1_gate_noise",
                   severity="info", message="noise", source_id=sid)
        return
    rec.record(stage="pass2_compile", event_type="pass2_compile_completed",
               severity="info", message="compiled", source_id=sid)
    if outcome == "quarantined":
        rec.record(stage="pass2_compile", event_type="source_quarantined",
                   severity="source_quarantine", message="compile failed",
                   source_id=sid)
        return
    rec.record(stage="commit", event_type="source_commit_completed",
               severity="info", message="committed", source_id=sid)


def _recorder(tmp_path: Path, console, clock=None, log_level="info") -> EventRecorder:
    return EventRecorder(
        run_id="r1", events_path=tmp_path / "runs" / "r1" / "events.jsonl",
        log_level=log_level, console=console, clock=clock or _FakeClock(),
    )


def test_console_snapshot_after_commit(tmp_path: Path) -> None:
    import io
    out = io.StringIO()
    rec = _recorder(tmp_path, out)
    _emit_source(rec, "AIML/Obsidian/Callouts.md")

    text = out.getvalue()
    snap = [ln for ln in text.splitlines() if ln.startswith("⏱")]
    assert len(snap) == 1
    line = snap[0]
    assert "[1]" in line
    assert "enriched 1" in line
    assert "compiled 1" in line
    assert "committed 1" in line
    assert "quarantined 0" in line
    assert "Callouts.md" in line


def test_console_counts_accumulate_across_sources(tmp_path: Path) -> None:
    import io
    out = io.StringIO()
    rec = _recorder(tmp_path, out)
    _emit_source(rec, "a.md")
    _emit_source(rec, "b.md")

    snaps = [ln for ln in out.getvalue().splitlines() if ln.startswith("⏱")]
    assert len(snaps) == 2
    assert "[2]" in snaps[-1]
    assert "committed 2" in snaps[-1]


def test_console_noise_increments_noise(tmp_path: Path) -> None:
    import io
    out = io.StringIO()
    rec = _recorder(tmp_path, out)
    _emit_source(rec, "Daily Notes/2026-05-28.md", outcome="noise")

    snap = [ln for ln in out.getvalue().splitlines() if ln.startswith("⏱")][-1]
    assert "noise 1" in snap
    assert "committed 0" in snap


def test_console_quarantine_prints_alarm_and_snapshot(tmp_path: Path) -> None:
    import io
    out = io.StringIO()
    rec = _recorder(tmp_path, out)
    _emit_source(rec, "Big Source.md", outcome="quarantined")

    text = out.getvalue()
    assert "⚠" in text
    assert "Big Source.md" in text
    snap = [ln for ln in text.splitlines() if ln.startswith("⏱")][-1]
    assert "quarantined 1" in snap


def test_console_elapsed_from_clock(tmp_path: Path) -> None:
    import io
    out = io.StringIO()
    clk = _FakeClock()
    rec = _recorder(tmp_path, out, clock=clk)
    clk.t = 75.0
    _emit_source(rec, "x.md")

    snap = [ln for ln in out.getvalue().splitlines() if ln.startswith("⏱")][-1]
    assert "01:15" in snap


def test_console_none_is_silent_and_file_unchanged(tmp_path: Path) -> None:
    rec = EventRecorder(
        run_id="r1", events_path=tmp_path / "runs" / "r1" / "events.jsonl",
        log_level="info",
    )
    _emit_source(rec, "a.md")
    assert rec.events_path.exists()
    assert not rec.event_log_failed
