"""Tests for kdb_benchmark.registry — loads and shape-checks models.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_benchmark import registry
from kdb_benchmark.registry import ModelEntry, load_registry


def test_default_registry_loads_and_has_unique_ids() -> None:
    entries = load_registry()
    assert len(entries) >= 1
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        assert isinstance(e, ModelEntry)
        assert e.id and e.provider and e.model


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_registry(tmp_path / "nope.json")


def test_top_level_must_be_list(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        load_registry(p)


def test_entry_missing_required_field_raises(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(json.dumps([{"id": "x", "provider": "anthropic"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing/empty string field 'model'"):
        load_registry(p)


def test_empty_field_raises(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([{"id": "x", "provider": "", "model": "m"}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="provider"):
        load_registry(p)


def test_duplicate_id_raises(tmp_path: Path) -> None:
    p = tmp_path / "models.json"
    p.write_text(
        json.dumps([
            {"id": "dup", "provider": "anthropic", "model": "a"},
            {"id": "dup", "provider": "openai",    "model": "b"},
        ]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate id"):
        load_registry(p)
