# Plan 3 — Pipeline registry (`pipelines.json` + loader)

> **For agentic workers:** Use superpowers:executing-plans. Checkbox steps.

**Goal:** A standalone, per-vault pipeline registry: `<state_root>/pipelines.json` (hand-authored config) + `kdb_compiler/pipeline_registry.py` loader (`load_pipelines` / `list_pipelines` / `get_pipeline`) with validation. The orchestrator reads it at startup to present the selection list and to scope the scan.

**Architecture:** New additive module. A `Pipeline` dataclass per entry. `load_pipelines(state_root)` parses + validates (unique ids; roots exist). It does NOT replace the existing global `load_scope_config()` — migrating force_noise/force_signal from global to per-pipeline is the orchestrator-integration step (Plan 5/6); Plan 3 just defines the registry. Per-vault config (roots are vault-specific), so `state_root`-parameterized like `planner.plan`.

**Spec:** "Component: Pipeline registry (global config)". Schema: `id / type / root / excludes / force_noise / force_signal / file_types / feeder`. Unifies the v0.2 blueprint's `scan_roots.json` + `feeders.json`. Plan 3 of 6; standalone + independently testable; leaves the app green (new module, no existing code touched).

**Run tests:** `python -m pytest kdb_compiler/tests/test_pipeline_registry.py -m "not live"`.

> **v1 validation scope:** unique `id`s + `root` exists. The full scope-collision invariant (no two pipelines producing the same vault-relative path) needs scope evaluation and is deferred to Plan 4 (scanner), where scope logic lives.

---

## File Structure
- **Create** `kdb_compiler/pipeline_registry.py` — `Pipeline` dataclass, `PipelineRegistryError`, `load_pipelines` / `list_pipelines` / `get_pipeline`.
- **Create** `kdb_compiler/tests/test_pipeline_registry.py` — all tests.

---

## Task 1: `Pipeline` dataclass + `load_pipelines` (parse + validate)

**Files:** Create `kdb_compiler/pipeline_registry.py`; Test `kdb_compiler/tests/test_pipeline_registry.py`.

- [ ] **Step 1: Write the failing tests**

```python
# kdb_compiler/tests/test_pipeline_registry.py
import json
from pathlib import Path

import pytest

from kdb_compiler import pipeline_registry as pr


def _write(state_root: Path, pipelines: list[dict]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "pipelines.json").write_text(
        json.dumps({"pipelines": pipelines}), encoding="utf-8")


def _entry(tmp_path: Path, pid: str, sub: str = "src") -> dict:
    root = tmp_path / sub
    root.mkdir(parents=True, exist_ok=True)
    return {"id": pid, "type": "in-place", "root": str(root),
            "force_noise": ["Daily Notes/"]}


def test_load_pipelines_parses_entry(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "vault-in-place")])
    pipes = pr.load_pipelines(state)
    assert len(pipes) == 1
    p = pipes[0]
    assert p.id == "vault-in-place"
    assert p.type == "in-place"
    assert p.force_noise == ["Daily Notes/"]
    assert p.file_types == [".md"]          # default
    assert p.excludes == [] and p.force_signal == [] and p.feeder is None


def test_load_pipelines_rejects_duplicate_id(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "dup", "a"), _entry(tmp_path, "dup", "b")])
    with pytest.raises(pr.PipelineRegistryError, match="duplicate"):
        pr.load_pipelines(state)


def test_load_pipelines_rejects_missing_root(tmp_path):
    state = tmp_path / "state"
    _write(state, [{"id": "x", "type": "raw", "root": str(tmp_path / "nope")}])
    with pytest.raises(pr.PipelineRegistryError, match="root"):
        pr.load_pipelines(state)


def test_load_pipelines_missing_file_raises(tmp_path):
    with pytest.raises(pr.PipelineRegistryError, match="not found"):
        pr.load_pipelines(tmp_path / "state")
```

- [ ] **Step 2: Run** → FAIL (`No module named 'kdb_compiler.pipeline_registry'`).

- [ ] **Step 3: Implement** `kdb_compiler/pipeline_registry.py`

```python
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
        raise PipelineRegistryError(f"pipeline entry must be an object, got {type(raw).__name__}")
    for key in ("id", "type", "root"):
        if not raw.get(key) or not isinstance(raw[key], str):
            raise PipelineRegistryError(f"pipeline entry missing required string '{key}': {raw!r}")
    if raw["type"] not in _VALID_TYPES:
        raise PipelineRegistryError(
            f"pipeline '{raw['id']}' has invalid type {raw['type']!r} (expected one of {sorted(_VALID_TYPES)})")
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
        raise PipelineRegistryError(f"pipelines.json at {path} must be {{'pipelines': [...]}}")

    pipelines = [_parse_entry(e) for e in payload["pipelines"]]

    seen: set[str] = set()
    for p in pipelines:
        if p.id in seen:
            raise PipelineRegistryError(f"duplicate pipeline id: {p.id!r}")
        seen.add(p.id)
        if not Path(p.root).exists():
            raise PipelineRegistryError(f"pipeline {p.id!r} root does not exist: {p.root}")
    return pipelines
```

- [ ] **Step 4: Run** → 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/pipeline_registry.py kdb_compiler/tests/test_pipeline_registry.py
git commit -m "feat(task91): Plan3 T1 — Pipeline dataclass + load_pipelines (parse + validate)"
```

---

## Task 2: `list_pipelines` + `get_pipeline` accessors

**Files:** Modify `kdb_compiler/pipeline_registry.py`; Test `test_pipeline_registry.py`.

- [ ] **Step 1: Write the failing tests**

```python
# append to test_pipeline_registry.py
def test_list_pipelines_returns_ids(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "a", "ra"), _entry(tmp_path, "b", "rb")])
    assert pr.list_pipelines(state) == ["a", "b"]


def test_get_pipeline_by_id(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "a", "ra"), _entry(tmp_path, "b", "rb")])
    p = pr.get_pipeline(state, "b")
    assert p.id == "b"


def test_get_pipeline_unknown_raises(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "a", "ra")])
    with pytest.raises(pr.PipelineRegistryError, match="unknown pipeline"):
        pr.get_pipeline(state, "missing")
```

- [ ] **Step 2: Run** → FAIL (`module 'kdb_compiler.pipeline_registry' has no attribute 'list_pipelines'`).

- [ ] **Step 3: Implement** — append to `pipeline_registry.py`

```python
def list_pipelines(state_root: Path | str) -> list[str]:
    """Pipeline ids in declaration order (the orchestrator's selection menu)."""
    return [p.id for p in load_pipelines(state_root)]


def get_pipeline(state_root: Path | str, pipeline_id: str) -> Pipeline:
    """Return the Pipeline with `pipeline_id`, or raise PipelineRegistryError."""
    for p in load_pipelines(state_root):
        if p.id == pipeline_id:
            return p
    raise PipelineRegistryError(f"unknown pipeline id: {pipeline_id!r}")
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Full regression** — `python -m pytest kdb_compiler/ graphdb_kdb/ -m "not live" -q -p no:warnings` → all pass.

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/pipeline_registry.py kdb_compiler/tests/test_pipeline_registry.py
git commit -m "feat(task91): Plan3 T2 — list_pipelines + get_pipeline accessors"
```

---

## Self-Review
1. **Spec coverage:** `pipelines.json` schema (id/type/root/excludes/force_noise/force_signal/file_types/feeder) + `load_pipelines`/`list_pipelines`/`get_pipeline` (Tasks 1-2). v1 validation = unique ids + roots exist; scope-collision deferred to Plan 4 (flagged).
2. **Additive:** new module only; `load_scope_config` untouched; full suite stays green.
3. **Type consistency:** `Pipeline` frozen dataclass; all three loaders take `state_root: Path | str`; `PipelineRegistryError` for all failures.
