"""Task #91 Plan 3 — pipeline registry tests."""
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


# ---------- Task 1: load_pipelines ----------

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


# ---------- Task 2: list_pipelines + get_pipeline ----------

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
