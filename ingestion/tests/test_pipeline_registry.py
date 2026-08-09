"""Task #91 Plan 3 — pipeline registry tests; #143 pipelines.d layout."""
import json
from pathlib import Path

import pytest

from ingestion.config import pipeline_registry as pr


def _write(state_root: Path, pipelines: list[dict]) -> None:
    """One file per pipeline under pipelines.d/<id>.json (#143)."""
    ddir = state_root / "pipelines.d"
    ddir.mkdir(parents=True, exist_ok=True)
    for entry in pipelines:
        (ddir / f"{entry['id']}.json").write_text(
            json.dumps(entry), encoding="utf-8")


def _entry(tmp_path: Path, pid: str, sub: str = "src") -> dict:
    root = tmp_path / sub
    root.mkdir(parents=True, exist_ok=True)
    return {"id": pid, "type": "in-place", "root": str(root),
            "force_noise": ["Daily Notes/"]}


# ---------- load_pipelines (#143 pipelines.d) ----------

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


def test_load_pipelines_aggregates_sorted(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "vault-in-place", "a"),
                   _entry(tmp_path, "gmail-substack", "b")])
    assert [p.id for p in pr.load_pipelines(state)] == [
        "gmail-substack", "vault-in-place"]     # sorted by filename


def test_load_pipelines_rejects_filename_id_mismatch(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "real-id")])
    bad = state / "pipelines.d" / "real-id.json"
    bad.rename(state / "pipelines.d" / "other-name.json")
    with pytest.raises(pr.PipelineRegistryError, match="does not match filename"):
        pr.load_pipelines(state)


def test_load_pipelines_rejects_missing_root(tmp_path):
    state = tmp_path / "state"
    _write(state, [{"id": "x", "type": "raw", "root": str(tmp_path / "nope")}])
    with pytest.raises(pr.PipelineRegistryError, match="root"):
        pr.load_pipelines(state)


def test_load_pipelines_missing_dir_raises(tmp_path):
    with pytest.raises(pr.PipelineRegistryError, match="not found"):
        pr.load_pipelines(tmp_path / "state")


def test_load_pipelines_legacy_only_raises_migration_error(tmp_path):
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "pipelines.json").write_text(
        json.dumps({"pipelines": [_entry(tmp_path, "vault-in-place")]}),
        encoding="utf-8")
    with pytest.raises(pr.PipelineRegistryError, match="migrate"):
        pr.load_pipelines(state)


def test_load_pipelines_both_layouts_fail_closed(tmp_path):
    state = tmp_path / "state"
    _write(state, [_entry(tmp_path, "vault-in-place")])
    (state / "pipelines.json").write_text(
        json.dumps({"pipelines": [_entry(tmp_path, "vault-in-place")]}),
        encoding="utf-8")
    with pytest.raises(pr.PipelineRegistryError, match="remove pipelines.json"):
        pr.load_pipelines(state)


def test_load_pipelines_rejects_bundle_shape(tmp_path):
    state = tmp_path / "state"
    ddir = state / "pipelines.d"
    ddir.mkdir(parents=True)
    (ddir / "x.json").write_text(
        json.dumps({"pipelines": [_entry(tmp_path, "x")]}), encoding="utf-8")
    with pytest.raises(pr.PipelineRegistryError, match="single pipeline object"):
        pr.load_pipelines(state)


# ---------- list_pipelines + get_pipeline ----------

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
