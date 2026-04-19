"""Tests for atomic_io — temp+fsync+os.replace atomic write primitives."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler import atomic_io


def test_atomic_write_bytes_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    atomic_io.atomic_write_bytes(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_atomic_write_bytes_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")
    atomic_io.atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"new"


def test_atomic_write_bytes_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deep" / "out.bin"
    atomic_io.atomic_write_bytes(target, b"hi")
    assert target.read_bytes() == b"hi"


def test_atomic_write_bytes_leaves_no_temp_on_success(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    atomic_io.atomic_write_bytes(target, b"x")
    stragglers = [p for p in tmp_path.iterdir() if p.name.startswith(".out.bin.tmp")]
    assert stragglers == []


def test_atomic_write_text_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    atomic_io.atomic_write_text(target, "héllo\n")
    assert target.read_text(encoding="utf-8") == "héllo\n"


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    payload = {"b": 2, "a": 1, "nested": {"x": [1, 2, 3]}}
    atomic_io.atomic_write_json(target, payload)
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == payload


def test_atomic_write_json_sort_keys(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    atomic_io.atomic_write_json(target, {"b": 1, "a": 2}, sort_keys=True)
    text = target.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')


def test_atomic_write_bytes_cleans_temp_on_failure(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "out.bin"

    def boom(*_a, **_kw):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(atomic_io.os, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        atomic_io.atomic_write_bytes(target, b"x")
    stragglers = [p for p in tmp_path.iterdir() if p.name.startswith(".out.bin.tmp")]
    assert stragglers == []
    assert not target.exists()
