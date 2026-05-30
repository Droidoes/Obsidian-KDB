"""Structured event logging for kdb-orchestrate.

Task #96 B1-B2 foundation: the orchestrator needs machine-readable run events
and production invariant checks before quarantine-and-continue can safely land.
This module intentionally stays independent of kdb_orchestrate.py so it can be
unit-tested without graph/vault fixtures.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from kdb_compiler.run_context import now_iso

ORCHESTRATOR_EVENT_SCHEMA_VERSION = "1.0"

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
    ) -> None:
        if log_level not in LOG_LEVELS:
            raise ValueError(f"unknown orchestrator log level: {log_level}")
        self.run_id = run_id
        self.events_path = Path(events_path)
        self.log_level = log_level
        self.event_log_failed = False
        self.recorded_events: list[OrchestratorEvent] = []

    @classmethod
    def for_state_root(
        cls,
        *,
        state_root: Path | str,
        run_id: str,
        log_level: OrchestratorLogLevel = "warning",
    ) -> "EventRecorder":
        events_path = Path(state_root) / "runs" / run_id / "orchestrator_events.jsonl"
        return cls(run_id=run_id, events_path=events_path, log_level=log_level)

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
