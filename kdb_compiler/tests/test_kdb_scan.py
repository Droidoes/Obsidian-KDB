"""Tests for kdb_scan — walker, classifier, rename pass, CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ingestion import kdb_scan
from ingestion.kdb_scan import classify, load_manifest_sources, main, scan, walk_raw


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


def test_load_manifest_returns_pipeline_id(tmp_path: Path) -> None:
    # Task #91 (M1): pipeline_id must round-trip so scan_scope's per-pipeline
    # prior filter can match committed rows; legacy records (no field) -> None.
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"sources": {
        "AIML/a.md": {"hash": "sha256:" + "a" * 64, "mtime": 1.0, "size_bytes": 3,
                      "file_type": "markdown", "is_binary": False,
                      "pipeline_id": "vault-test"},
        "legacy/b.md": {"hash": "sha256:" + "b" * 64, "mtime": 1.0, "size_bytes": 3,
                        "file_type": "markdown", "is_binary": False},
    }}))
    out = load_manifest_sources(p)
    assert out["AIML/a.md"]["pipeline_id"] == "vault-test"
    assert out["legacy/b.md"]["pipeline_id"] is None


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
        # last_compiled_hash == current hash -> skip (content already compiled)
        "KDB/raw/unchanged.md": {"hash": h("stable content"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False,
                                 "last_compiled_hash": h("stable content")},
        # last_compiled_hash == old hash; current content differs -> compile
        "KDB/raw/changed.md":   {"hash": h("original content"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False,
                                 "last_compiled_hash": h("original content")},
        # moved: last_compiled_hash == renamed body hash -> skip after move
        "KDB/raw/moved-old.md": {"hash": h("renamed body"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False,
                                 "last_compiled_hash": h("renamed body")},
        "KDB/raw/gone.md":      {"hash": h("tombstoned"), "mtime": 1.0, "size_bytes": 1,
                                 "file_type": "markdown", "is_binary": False,
                                 "last_compiled_hash": h("tombstoned")},
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
    assert sorted(result.to_skip) == ["KDB/raw/moved-new.md", "KDB/raw/unchanged.md"]

    s = result.summary
    assert (s.new, s.changed, s.unchanged, s.moved, s.deleted) == (1, 1, 1, 1, 1)


def test_scan_entry_to_dict_always_includes_compiled_hash():
    from common.types import ScanEntry
    # never-compiled source: compiled_hash is null, still present
    e = ScanEntry(
        path="KDB/raw/a.md", action="NEW",
        current_hash="sha256:" + "a" * 64, current_mtime=1.0,
        size_bytes=10, file_type="markdown", is_binary=False,
        compiled_hash=None,
    )
    assert "compiled_hash" in e.to_dict()
    assert e.to_dict()["compiled_hash"] is None
    # previously-compiled source: carries the prior hash
    e2 = ScanEntry(
        path="KDB/raw/b.md", action="UNCHANGED",
        current_hash="sha256:" + "b" * 64, current_mtime=1.0,
        size_bytes=10, file_type="markdown", is_binary=False,
        compiled_hash="sha256:" + "c" * 64,
        previous_hash="sha256:" + "b" * 64, previous_mtime=0.5,
    )
    assert e2.to_dict()["compiled_hash"] == "sha256:" + "c" * 64


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


# ---------- Task #66: hash-based compile eligibility ----------

def _sha256_text(text: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _src_rec(*, hash, last_compiled_hash, run_state="in_graph_db"):
    return {
        "hash": hash, "mtime": 0.0, "size_bytes": 1,
        "file_type": "markdown", "is_binary": False,
        "run_state": run_state, "last_compiled_hash": last_compiled_hash,
    }


def test_unchanged_already_compiled_is_skipped(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "hello")
    h = _sha256_text("hello")
    _write_manifest(state, {"KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=h)})
    res = scan(vault, write=False)
    assert res.to_skip == ["KDB/raw/a.md"]
    assert res.to_compile == []


def test_unchanged_not_yet_compiled_is_compiled(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "hello")
    h = _sha256_text("hello")
    _write_manifest(state, {"KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=None)})
    res = scan(vault, write=False)
    assert res.to_compile == ["KDB/raw/a.md"]
    assert res.to_skip == []


def test_changed_with_a_prior_compiled_hash_is_compiled(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "new content")
    old = _sha256_text("old content")
    _write_manifest(state, {"KDB/raw/a.md": _src_rec(hash=old, last_compiled_hash=old)})
    res = scan(vault, write=False)
    assert res.to_compile == ["KDB/raw/a.md"]
    entry = next(e for e in res.files if e.path == "KDB/raw/a.md")
    assert entry.action == "CHANGED"
    assert entry.compiled_hash == old


def test_new_file_is_compiled(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "hello")
    _write_manifest(state, {})
    res = scan(vault, write=False)
    assert res.to_compile == ["KDB/raw/a.md"]
    entry = next(e for e in res.files if e.path == "KDB/raw/a.md")
    assert entry.compiled_hash is None


def test_error_state_does_not_force_recompile(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    _write(raw / "a.md", "hello")
    h = _sha256_text("hello")
    _write_manifest(state, {
        "KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=h, run_state="error_compile"),
    })
    res = scan(vault, write=False)
    assert res.to_skip == ["KDB/raw/a.md"]
    assert res.to_compile == []


def test_moved_with_compiled_content_is_skipped(tmp_path: Path) -> None:
    vault, raw, state = _make_vault(tmp_path)
    sub = raw / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    _write(sub / "b.md", "hello")
    h = _sha256_text("hello")
    _write_manifest(state, {"KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=h)})
    res = scan(vault, write=False)
    moved = next(e for e in res.files if e.action == "MOVED")
    assert moved.compiled_hash == h
    assert res.to_skip == ["KDB/raw/sub/b.md"]
    assert res.to_compile == []


# ---------- Task #91 Plan 4: generalized scope walk ----------

def test_walk_scope_arbitrary_root_vault_relative(tmp_path):
    vault = tmp_path
    root = vault / "Vault-test" / "AIML"
    (root / "Claude").mkdir(parents=True)
    (root / "Claude" / "a.md").write_text("x", encoding="utf-8")
    (root / "b.txt").write_text("y", encoding="utf-8")             # non-.md: filtered
    (root / ".hidden").mkdir()
    (root / ".hidden" / "c.md").write_text("z", encoding="utf-8")  # hidden dir: pruned
    (root / "Daily Notes").mkdir()
    (root / "Daily Notes" / "d.md").write_text("w", encoding="utf-8")  # excluded

    files, _sym, _err = kdb_scan.walk_scope(
        root, vault, file_types={".md"}, excludes=["Daily Notes/"])
    paths = sorted(f.rel_path for f in files)
    assert paths == ["Vault-test/AIML/Claude/a.md"]   # vault-relative; rest filtered


def test_scan_entry_pipeline_id_field():
    from common.types import ScanEntry
    e = ScanEntry(path="P/a.md", action="NEW", current_hash="sha256:x",
                  current_mtime=1.0, size_bytes=3, file_type="markdown",
                  is_binary=False, compiled_hash=None, pipeline_id="test-pipe")
    assert e.pipeline_id == "test-pipe"
    assert e.to_dict()["pipeline_id"] == "test-pipe"


def test_seed_source_record_carries_pipeline_id():
    from kdb_compiler.manifest_writer import _seed_source_record
    from common.run_context import RunContext
    ctx = RunContext.new(dry_run=True, vault_root=Path("/tmp/x"))
    rec = _seed_source_record(
        {"path": "P/a.md", "file_type": "markdown", "current_hash": "sha256:x",
         "current_mtime": 1.0, "size_bytes": 3, "is_binary": False,
         "pipeline_id": "test-pipe"}, ctx)
    assert rec["pipeline_id"] == "test-pipe"


def test_scan_scope_stamps_pipeline_id(tmp_path):
    from common.run_context import RunContext
    vault = tmp_path
    root = vault / "P"; root.mkdir()
    (root / "a.md").write_text("x", encoding="utf-8")
    res = kdb_scan.scan_scope(
        root, vault, pipeline_id="test-pipe", prior={},
        run_ctx=RunContext.new(vault_root=vault), excludes=[], file_types={".md"})
    e = next(f for f in res.files if f.path == "P/a.md")
    assert e.pipeline_id == "test-pipe"
    assert e.to_dict()["pipeline_id"] == "test-pipe"


def test_scan_scope_deleted_scoped_to_pipeline(tmp_path):
    """DELETED pass only flags THIS pipeline's absent sources (D-91 scanner)."""
    from common.run_context import RunContext
    vault = tmp_path
    root_a = vault / "A"; root_a.mkdir()   # empty on disk → A/gone.md deleted
    prior = {
        "A/gone.md": {"hash": "sha256:1", "mtime": 1.0, "pipeline_id": "A"},
        "B/keep.md": {"hash": "sha256:2", "mtime": 1.0, "pipeline_id": "B"},
    }
    res = kdb_scan.scan_scope(
        root_a, vault, pipeline_id="A", prior=prior,
        run_ctx=RunContext.new(vault_root=vault), excludes=[], file_types={".md"})
    deleted = sorted(op.path for op in res.to_reconcile if op.type == "DELETED")
    assert deleted == ["A/gone.md"]        # B/keep.md (other pipeline) untouched


def test_scan_scope_no_cross_pipeline_move(tmp_path):
    """A same-hash file in another pipeline is NOT matched as MOVED (D-91-9)."""
    from common.run_context import RunContext
    vault = tmp_path
    root_a = vault / "A"; root_a.mkdir()
    (root_a / "x.md").write_text("same", encoding="utf-8")
    h = _sha256_text("same")
    prior = {"B/y.md": {"hash": h, "mtime": 1.0, "pipeline_id": "B"}}
    res = kdb_scan.scan_scope(
        root_a, vault, pipeline_id="A", prior=prior,
        run_ctx=RunContext.new(vault_root=vault), excludes=[], file_types={".md"})
    x = next(f for f in res.files if f.path == "A/x.md")
    assert x.action == "NEW"               # not MOVED-from-B
    assert not [op for op in res.to_reconcile if op.type == "MOVED"]
