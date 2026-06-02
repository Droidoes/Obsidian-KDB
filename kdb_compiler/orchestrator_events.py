"""Structured event logging for kdb-orchestrate.

Task #96 B1-B2 foundation: the orchestrator needs machine-readable run events
and production invariant checks before quarantine-and-continue can safely land.
This module intentionally stays independent of kdb_orchestrate.py so it can be
unit-tested without graph/vault fixtures.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, TextIO

from common.run_context import now_iso

ORCHESTRATOR_EVENT_SCHEMA_VERSION = "1.0"

# Live progress: which event_types feed which running counter, and which
# severities are alarms (printed as a distinct ⚠ line).
_TALLY_BY_EVENT = {
    "pass1_enrich_completed": "enriched",
    "pass2_compile_completed": "compiled",
    "source_commit_completed": "committed",
    "pass1_gate_noise": "noise",
    "source_quarantined": "quarantined",
}
_ALARM_SEVERITIES = {"source_quarantine", "run_fatal", "invariant_violation"}

OrchestratorSeverity = Literal[
    "debug",
    "info",
    "warning",
    "source_quarantine",
    "run_fatal",
    "invariant_violation",
]
OrchestratorLogLevel = Literal["warning", "info", "debug"]

HIGH_VISIBILITY_SEVERITIES = {
    "warning",
    "source_quarantine",
    "run_fatal",
    "invariant_violation",
}
LOG_LEVELS = {"warning", "info", "debug"}


@dataclass
class OrchestratorEvent:
    run_id: str
    stage: str
    event_type: str
    severity: OrchestratorSeverity
    message: str
    source_id: str | None = None
    exception_type: str | None = None
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    ts: str = field(default_factory=now_iso)
    schema_version: str = ORCHESTRATOR_EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ts": self.ts,
            "run_id": self.run_id,
            "source_id": self.source_id,
            "stage": self.stage,
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "exception_type": self.exception_type,
            "error": self.error,
            "context": dict(self.context),
            "artifacts": dict(self.artifacts),
        }


class EventRecorder:
    """Append-only JSONL event recorder.

    Event writes are best-effort: observability failure must be surfaced but
    must not become a second failure path that obscures the original error.
    """

    def __init__(
        self,
        *,
        run_id: str,
        events_path: Path | str,
        log_level: OrchestratorLogLevel = "warning",
        console: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if log_level not in LOG_LEVELS:
            raise ValueError(f"unknown orchestrator log level: {log_level}")
        self.run_id = run_id
        self.events_path = Path(events_path)
        self.log_level = log_level
        self.event_log_failed = False
        self.recorded_events: list[OrchestratorEvent] = []
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

    @classmethod
    def for_state_root(
        cls,
        *,
        state_root: Path | str,
        run_id: str,
        log_level: OrchestratorLogLevel = "warning",
        console: TextIO | None = None,
    ) -> "EventRecorder":
        events_path = Path(state_root) / "runs" / run_id / "orchestrator_events.jsonl"
        return cls(run_id=run_id, events_path=events_path, log_level=log_level,
                   console=console)

    def should_record(self, severity: OrchestratorSeverity) -> bool:
        if severity in HIGH_VISIBILITY_SEVERITIES:
            return True
        if self.log_level == "debug":
            return True
        if self.log_level == "info":
            return severity == "info"
        return False

    def record(
        self,
        *,
        stage: str,
        event_type: str,
        severity: OrchestratorSeverity,
        message: str,
        source_id: str | None = None,
        exception_type: str | None = None,
        error: str | None = None,
        context: dict[str, Any] | None = None,
        artifacts: dict[str, str] | None = None,
    ) -> OrchestratorEvent | None:
        event = OrchestratorEvent(
            run_id=self.run_id,
            source_id=source_id,
            stage=stage,
            event_type=event_type,
            severity=severity,
            message=message,
            exception_type=exception_type,
            error=error,
            context=context or {},
            artifacts=artifacts or {},
        )
        return self.record_event(event)

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

    def count(self, severity: OrchestratorSeverity) -> int:
        return sum(1 for event in self.recorded_events if event.severity == severity)

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


class OrchestratorInvariantError(RuntimeError):
    def __init__(self, *, code: str, stage: str, message: str) -> None:
        self.code = code
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}:{code}: {message}")


def check_orchestrator_invariant(
    condition: bool,
    *,
    recorder: EventRecorder,
    code: str,
    stage: str,
    message: str,
    source_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Always-on production invariant check for orchestrator contracts."""
    if condition:
        return
    recorder.record(
        stage=stage,
        event_type="invariant_violation",
        severity="invariant_violation",
        message=message,
        source_id=source_id,
        exception_type="OrchestratorInvariantError",
        error=code,
        context=context,
    )
    raise OrchestratorInvariantError(code=code, stage=stage, message=message)
