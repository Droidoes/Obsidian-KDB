"""pipeline_registry — per-vault ingestion-pipeline registry (Task #91).

`<state_root>/pipelines.json` is hand-authored config defining which
ingestion pipelines exist and how each is scoped. Unifies the v0.2
blueprint's scan_roots.json + feeders.json. The orchestrator reads this at
startup to present the pipeline-selection list and to scope the scan.

Per-vault (roots are vault-specific), so state_root-parameterized like
planner.plan. Does NOT replace the global load_scope_config() — per-pipeline
scope migration is the orchestrator-integration step.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class PipelineRegistryError(RuntimeError):
    """Raised when pipelines.json is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class Pipeline:
    id: str
    type: str                                  # "in-place" | "raw"
    root: str
    excludes: list[str] = field(default_factory=list)
    force_noise: list[str] = field(default_factory=list)
    force_signal: list[str] = field(default_factory=list)
    file_types: list[str] = field(default_factory=lambda: [".md"])
    feeder: Optional[Any] = None               # descriptive metadata only (v1)


_VALID_TYPES = {"in-place", "raw"}


def _parse_entry(raw: dict) -> Pipeline:
    if not isinstance(raw, dict):
        raise PipelineRegistryError(
            f"pipeline entry must be an object, got {type(raw).__name__}")
    for key in ("id", "type", "root"):
        if not raw.get(key) or not isinstance(raw[key], str):
            raise PipelineRegistryError(
                f"pipeline entry missing required string '{key}': {raw!r}")
    if raw["type"] not in _VALID_TYPES:
        raise PipelineRegistryError(
            f"pipeline '{raw['id']}' has invalid type {raw['type']!r} "
            f"(expected one of {sorted(_VALID_TYPES)})")
    return Pipeline(
        id=raw["id"], type=raw["type"], root=raw["root"],
        excludes=list(raw.get("excludes", []) or []),
        force_noise=list(raw.get("force_noise", []) or []),
        force_signal=list(raw.get("force_signal", []) or []),
        file_types=list(raw.get("file_types", []) or [".md"]),
        feeder=raw.get("feeder"),
    )


def load_pipelines(state_root: Path | str) -> list[Pipeline]:
    """Load + validate <state_root>/pipelines.json. Validates: unique ids,
    roots exist. Raises PipelineRegistryError on any failure."""
    path = Path(state_root) / "pipelines.json"
    if not path.exists():
        raise PipelineRegistryError(f"pipeline registry not found at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PipelineRegistryError(f"malformed pipelines.json at {path}: {e}") from e
    if not isinstance(payload, dict) or not isinstance(payload.get("pipelines"), list):
        raise PipelineRegistryError(
            f"pipelines.json at {path} must be {{'pipelines': [...]}}")

    pipelines = [_parse_entry(e) for e in payload["pipelines"]]

    seen: set[str] = set()
    for p in pipelines:
        if p.id in seen:
            raise PipelineRegistryError(f"duplicate pipeline id: {p.id!r}")
        seen.add(p.id)
        if not Path(p.root).exists():
            raise PipelineRegistryError(
                f"pipeline {p.id!r} root does not exist: {p.root}")
    return pipelines


def list_pipelines(state_root: Path | str) -> list[str]:
    """Pipeline ids in declaration order (the orchestrator's selection menu)."""
    return [p.id for p in load_pipelines(state_root)]


def get_pipeline(state_root: Path | str, pipeline_id: str) -> Pipeline:
    """Return the Pipeline with `pipeline_id`, or raise PipelineRegistryError."""
    for p in load_pipelines(state_root):
        if p.id == pipeline_id:
            return p
    raise PipelineRegistryError(f"unknown pipeline id: {pipeline_id!r}")
