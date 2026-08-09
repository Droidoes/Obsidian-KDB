"""pipeline_registry — per-vault ingestion-pipeline registry (Tasks #91, #143).

#143: config moved from a single `<state_root>/pipelines.json` to one file
per pipeline under `<state_root>/pipelines.d/<id>.json` — pipelines become
plugins: a new feeder ships its own file, nothing else changes. The filename
stem must equal the entry's `id`. The orchestrator reads this at startup to
present the pipeline-selection list and to scope the scan.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class PipelineRegistryError(RuntimeError):
    """Raised when pipelines.d/ is missing, malformed, or fails validation."""


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


def _load_entry_file(path: Path) -> Pipeline:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PipelineRegistryError(
            f"malformed pipeline file at {path}: {e}") from e
    if not isinstance(payload, dict) or "pipelines" in payload:
        raise PipelineRegistryError(
            f"{path} must be a single pipeline object, "
            f"not a {{'pipelines': [...]}} bundle")
    entry = _parse_entry(payload)
    if entry.id != path.stem:
        raise PipelineRegistryError(
            f"pipeline id {entry.id!r} does not match filename {path.name!r} "
            f"(expected pipelines.d/{entry.id}.json)")
    return entry


def load_pipelines(state_root: Path | str) -> list[Pipeline]:
    """Load + validate `<state_root>/pipelines.d/*.json` (#143). Validates:
    single-object files, filename==id, unique ids, roots exist.
    Raises PipelineRegistryError on any failure."""
    state_root = Path(state_root)
    ddir = state_root / "pipelines.d"
    legacy = state_root / "pipelines.json"
    if ddir.is_dir() and legacy.exists():
        raise PipelineRegistryError(
            f"both {ddir} and legacy {legacy} exist — remove pipelines.json "
            f"after migrating to pipelines.d/<id>.json (#143)")
    if legacy.exists():
        raise PipelineRegistryError(
            f"legacy {legacy} found — migrate to one file per pipeline under "
            f"{ddir}/<id>.json, then delete pipelines.json (#143)")
    if not ddir.is_dir():
        raise PipelineRegistryError(f"pipeline registry not found at {ddir}")

    pipelines = [_load_entry_file(p) for p in sorted(ddir.glob("*.json"))]
    if not pipelines:
        raise PipelineRegistryError(f"no pipeline files under {ddir}")

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
