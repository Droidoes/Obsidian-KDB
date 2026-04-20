"""Tests for kdb_scan — walker, classifier, rename pass, CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from kdb_compiler import kdb_scan
from kdb_compiler.kdb_scan import classify, load_manifest_sources, main, scan, walk_raw


# ---------- helpers ----------

def _make_vault(tmp: Path) -> tuple[Path, Path, Path]:
    """Create vault/KDB/{raw,state}. Return (vault_root, raw_abs, state_abs)."""
    vault = tmp / "vault"
    raw = vault / "KDB" / "raw"
    state = vault / "KDB" / "state"
    raw.mkdir(parents=True)
    state.mkdir(parents=True)
    return vault, raw, state


def _write(p: Path, content: str | bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


def _write_manifest(state: Path, sources: dict) -> Path:
    m = state / "manifest.json"
    m.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return m


# ---------- walk_raw ----------

def test_walk_empty_raw(tmp_path: Path) -> None:
    _, raw, _ = _make_vault(tmp_path)
    files, symlinks, errors = walk_raw(raw)
    assert files == [] and symlinks == [] and errors == []


def test_walk_missing_raw_is_safe(tmp_path: Path) -> None:
    files, symlinks, errors = walk_raw(tmp_path / "nope")
    assert files == [] and symlinks == [] and errors == []


def test_walk_basic_files_sorted(tmp_path: Path) -> None:
    _, raw, _ = _make_vault(tmp_path)
    _write(raw / "b.md", "B")
    _write(raw / "a.md", "A")
    _write(raw / "nested" / "c.md", "C")
    files, _, _ = walk_raw(raw)
    paths = [f.rel_path for f in files]
    assert paths == sorted(paths)
    assert "KDB/raw/a.md" in paths and "KDB/raw/nested/c.md" in paths


def test_walk_skips_file_symlink(tmp_path: Path) -> None:
    _, raw, _ = _make_vault(tmp_path)
    real = tmp_path / "elsewhere.md"
    real.write_text("X")
    link = raw / "link.md"
    os.symlink(real, link)
    files, symlinks, _ = walk_raw(raw)
    assert [s.path for s in symlinks] == ["KDB/raw/link.md"]
    assert not any(f.rel_path == "KDB/raw/link.md" for f in files)


def test_walk_skips_dir_symlink(tmp_path: Path) -> None:
    _, raw, _ = _make_vault(tmp_path)
    real_dir = tmp_path / "elsewhere"
    real_dir.mkdir()
    (real_dir / "inner.md").write_text("I")
    os.symlink(real_dir, raw / "linked-dir")
    files, symlinks, _ = walk_raw(raw)
    assert any(s.path == "KDB/raw/linked-dir" for s in symlinks)
    assert files == []


def test_walk_detects_binary_via_nul_byte(tmp_path: Path) -> None:
    _, raw, _ = _make_vault(tmp_path)
    _write(raw / "bin.md", b"hello\x00world")  # .md but NUL present
    _write(raw / "txt.md", "normal text")
    files, _, _ = walk_raw(raw)
    by_path = {f.rel_path: f for f in files}
    assert by_path["KDB/raw/bin.md"].is_binary is True
    assert by_path["KDB/raw/bin.md"].file_type == "binary"
    assert by_path["KDB/raw/txt.md"].is_binary is False
    assert by_path["KDB/raw/txt.md"].file_type == "markdown"


def test_walk_hash_is_content_based(tmp_path: Path) -> None:
    _, raw, _ = _make_vault(tmp_path)
    _write(raw / "a.md", "same content")
    _write(raw / "b.md", "same content")
    files, _, _ = walk_raw(raw)
    hashes = {f.rel_path: f.hash for f in files}
    assert hashes["KDB/raw/a.md"] == hashes["KDB/raw/b.md"]
    assert hashes["KDB/raw/a.md"].startswith("sha256:")


# ---------- load_manifest_sources ----------

def test_load_manifest_missing_returns_empty(tmp_path: Path) -> None:
    assert load_manifest_sources(tmp_path / "no-manifest.json") == {}


def test_load_manifest_malformed_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text("{not json")
    assert load_manifest_sources(p) == {}


def test_load_manifest_reads_sources(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"sources": {
        "KDB/raw/a.md": {"hash": "sha256:" + "a" * 64, "mtime": 1.0, "size_bytes": 3,
                         "file_type": "markdown", "is_binary": False},
    }}))
    out = load_manifest_sources(p)
    assert out["KDB/raw/a.md"]["hash"] == "sha256:" + "a" * 64


# ---------- classify ----------

def _raw(path: str, hash_: str, mtime: float = 1.0, size: int = 1,
         ftype: str = "markdown", is_binary: bool = False) -> kdb_scan._RawFile:
    return kdb_scan._RawFile(
        rel_path=path, hash=hash_, mtime=mtime, size_bytes=size,
        file_type=ftype, is_binary=is_binary,  # type: ignore[arg-type]
    )


def test_classify_first_run_all_new() -> None:
    cur = [_raw("KDB/raw/a.md", "sha256:" + "1" * 64),
           _raw("KDB/raw/b.md", "sha256:" + "2" * 64)]
    files, ops = classify(cur, {})
    assert {f.action for f in files} == {"NEW"}
    assert ops == []


def test_classify_unchanged_when_hash_eq() -> None:
    h = "sha256:" + "1" * 64
    cur = [_raw("KDB/raw/a.md", h, mtime=100.0)]
    prior = {"KDB/raw/a.md": {"hash": h, "mtime": 1.0, "size_bytes": 1,
                              "file_type": "markdown", "is_binary": False}}
    files, ops = classify(cur, prior)
    assert files[0].action == "UNCHANGED"
    assert files[0].previous_hash == h and files[0].previous_mtime == 1.0
    assert ops == []


def test_classify_changed_when_hash_diff() -> None:
    cur = [_raw("KDB/raw/a.md", "sha256:" + "2" * 64)]
    prior = {"KDB/raw/a.md": {"hash": "sha256:" + "1" * 64, "mtime": 1.0, "size_bytes": 1,
                              "file_type": "markdown", "is_binary": False}}
    files, ops = classify(cur, prior)
    assert files[0].action == "CHANGED"
    assert files[0].previous_hash == "sha256:" + "1" * 64


def test_classify_rename_pairs_by_hash() -> None:
    h = "sha256:" + "3" * 64
    cur = [_raw("KDB/raw/new-loc.md", h)]
    prior = {"KDB/raw/old-loc.md": {"hash": h, "mtime": 1.0, "size_bytes": 1,
                                    "file_type": "markdown", "is_binary": False}}
    files, ops = classify(cur, prior)
    assert files[0].action == "MOVED"
    assert files[0].previous_path == "KDB/raw/old-loc.md"
    assert ops == [] or ops[0].type == "MOVED"
    moved = [o for o in ops if o.type == "MOVED"]
    assert len(moved) == 1
    assert moved[0].from_path == "KDB/raw/old-loc.md"
    assert moved[0].to_path == "KDB/raw/new-loc.md"


def test_classify_copy_not_treated_as_move() -> None:
    """Same hash, both paths remain: old is UNCHANGED, new is NEW, no MOVED op."""
    h = "sha256:" + "4" * 64
    cur = [_raw("KDB/raw/orig.md", h), _raw("KDB/raw/copy.md", h)]
    prior = {"KDB/raw/orig.md": {"hash": h, "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False}}
    files, ops = classify(cur, prior)
    by_path = {f.path: f for f in files}
    assert by_path["KDB/raw/orig.md"].action == "UNCHANGED"
    assert by_path["KDB/raw/copy.md"].action == "NEW"
    assert [o.type for o in ops] == []


def test_classify_deleted_has_no_files_entry() -> None:
    h = "sha256:" + "5" * 64
    cur: list = []
    prior = {"KDB/raw/gone.md": {"hash": h, "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False}}
    files, ops = classify(cur, prior)
    assert files == []
    assert len(ops) == 1 and ops[0].type == "DELETED"
    assert ops[0].path == "KDB/raw/gone.md" and ops[0].hash == h


def test_classify_results_are_sorted() -> None:
    cur = [_raw("KDB/raw/z.md", "sha256:" + "1" * 64),
           _raw("KDB/raw/a.md", "sha256:" + "2" * 64)]
    files, _ = classify(cur, {})
    assert [f.path for f in files] == ["KDB/raw/a.md", "KDB/raw/z.md"]


# ---------- scan() orchestrator + atomic write ----------

def test_scan_writes_last_scan_json_atomically(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "alpha")
    result = scan(vault)
    out = state / "last_scan.json"
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["raw_root"] == "KDB/raw"
    assert payload["summary"]["new"] == 1
    assert payload["to_compile"] == ["KDB/raw/a.md"]
    assert result.summary.new == 1


def test_scan_first_run_no_manifest_treats_all_as_new(tmp_path: Path) -> None:
    vault, raw, _ = _make_vault(tmp_path)
    _write(raw / "a.md", "A")
    _write(raw / "b.md", "B")
    result = scan(vault, write=False)
    assert {f.action for f in result.files} == {"NEW"}
    assert sorted(result.to_compile) == ["KDB/raw/a.md", "KDB/raw/b.md"]
    assert result.to_reconcile == []


def test_scan_end_to_end_mix(tmp_path: Path) -> None:
    """New + Changed + Unchanged + Moved + Deleted all produced from one scan."""
    vault, raw, state = _make_vault(tmp_path)

    # Content on disk now
    _write(raw / "new.md", "brand new")
    _write(raw / "unchanged.md", "stable content")
    _write(raw / "changed.md", "edited content")  # new content
    _write(raw / "moved-new.md", "renamed body")  # same hash as old path in manifest

    import hashlib

    def h(s: str) -> str:
        return "sha256:" + hashlib.sha256(s.encode()).hexdigest()

    _write_manifest(state, {
        "KDB/raw/unchanged.md": {"hash": h("stable content"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False},
        "KDB/raw/changed.md":   {"hash": h("original content"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False},
        "KDB/raw/moved-old.md": {"hash": h("renamed body"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False},
        "KDB/raw/gone.md":      {"hash": h("tombstoned"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False},
    })

    result = scan(vault, write=False)
    by_path = {f.path: f for f in result.files}

    assert by_path["KDB/raw/new.md"].action == "NEW"
    assert by_path["KDB/raw/unchanged.md"].action == "UNCHANGED"
    assert by_path["KDB/raw/changed.md"].action == "CHANGED"
    assert by_path["KDB/raw/moved-new.md"].action == "MOVED"
    assert by_path["KDB/raw/moved-new.md"].previous_path == "KDB/raw/moved-old.md"
    assert "KDB/raw/gone.md" not in by_path  # DELETED not in files[]

    op_types = sorted(o.type for o in result.to_reconcile)
    assert op_types == ["DELETED", "MOVED"]

    assert sorted(result.to_compile) == ["KDB/raw/changed.md", "KDB/raw/new.md"]
    assert result.to_skip == ["KDB/raw/unchanged.md"]

    s = result.summary
    assert (s.new, s.changed, s.unchanged, s.moved, s.deleted) == (1, 1, 1, 1, 1)


def test_scan_retries_errored_sources_unchanged_hash(tmp_path: Path) -> None:
    """A source whose hash is unchanged but whose manifest entry records
    compile_state='error' must be re-included in to_compile so it gets
    another chance — otherwise it's stuck forever."""
    vault, raw, state = _make_vault(tmp_path)

    import hashlib
    def h(s: str) -> str:
        return "sha256:" + hashlib.sha256(s.encode()).hexdigest()

    _write(raw / "ok.md", "happy body")
    _write(raw / "errored.md", "truncated body")

    _write_manifest(state, {
        "KDB/raw/ok.md": {
            "hash": h("happy body"), "mtime": 1.0, "size_bytes": 1,
            "file_type": "markdown", "is_binary": False,
            "compile_state": "compiled",
        },
        "KDB/raw/errored.md": {
            "hash": h("truncated body"), "mtime": 1.0, "size_bytes": 1,
            "file_type": "markdown", "is_binary": False,
            "compile_state": "error",
        },
    })

    result = scan(vault, write=False)
    by_path = {f.path: f for f in result.files}

    # Both files are UNCHANGED on disk (hashes match).
    assert by_path["KDB/raw/ok.md"].action == "UNCHANGED"
    assert by_path["KDB/raw/errored.md"].action == "UNCHANGED"
    # But only the errored one is rescheduled for compile.
    assert result.to_compile == ["KDB/raw/errored.md"]
    assert result.to_skip == ["KDB/raw/ok.md"]


# ---------- CLI ----------

def test_cli_main_runs_and_writes(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "A")
    rc = main(["--vault-root", str(vault)])
    assert rc == 0
    assert (state / "last_scan.json").exists()
    out = capsys.readouterr().out
    assert "scanned 1 files" in out


def test_cli_requires_vault_root(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
