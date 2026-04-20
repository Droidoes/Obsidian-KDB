"""Tests for validate_last_scan — JSON-Schema + semantic gate."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from kdb_compiler import validate_last_scan as vls

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64
H4 = "sha256:" + "4" * 64


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------- fixture-based cases ----------

def test_valid_fixture_produces_no_errors() -> None:
    assert vls.validate(_load("last_scan.minimal.valid.json")) == []


def test_invalid_fixture_surfaces_multiple_violations() -> None:
    errors = vls.validate(_load("last_scan.minimal.invalid.json"))
    # Duplicate path, missing previous_hash (schema), to_compile/to_skip overlap,
    # ghost.md not in files[], DELETED reconcile overlapping files[], summary mismatches.
    assert len(errors) >= 5, f"expected >=5 errors, got {len(errors)}: {errors}"


# ---------- helpers for constructed payloads ----------

def _entry(path: str, action: str, **overrides) -> dict:
    base = {
        "path": path,
        "action": action,
        "current_hash": overrides.pop("current_hash", H1),
        "current_mtime": 1700000000.0,
        "size_bytes": 100,
        "file_type": "markdown",
        "is_binary": False,
    }
    if action in ("CHANGED", "UNCHANGED"):
        base["previous_hash"] = overrides.pop("previous_hash", H2)
        base["previous_mtime"] = overrides.pop("previous_mtime", 1699000000.0)
    if action == "MOVED":
        base["previous_hash"] = overrides.pop("previous_hash", base["current_hash"])
        base["previous_mtime"] = overrides.pop("previous_mtime", 1699000000.0)
        base["previous_path"] = overrides.pop("previous_path", "KDB/raw/old.md")
    base.update(overrides)
    return base


def _summary(**kwargs) -> dict:
    base = {"new": 0, "changed": 0, "unchanged": 0, "moved": 0,
            "deleted": 0, "error": 0, "skipped_symlink": 0}
    base.update(kwargs)
    return base


def _payload(
    files: list[dict] | None = None,
    to_compile: list[str] | None = None,
    to_skip: list[str] | None = None,
    to_reconcile: list[dict] | None = None,
    summary: dict | None = None,
    errors: list[dict] | None = None,
    skipped_symlinks: list[dict] | None = None,
) -> dict:
    files = files or []
    counts = {"NEW": 0, "CHANGED": 0, "UNCHANGED": 0, "MOVED": 0}
    for e in files:
        counts[e["action"]] = counts.get(e["action"], 0) + 1
    deleted_n = sum(1 for op in (to_reconcile or []) if op.get("type") == "DELETED")
    if summary is None:
        summary = _summary(
            new=counts["NEW"], changed=counts["CHANGED"],
            unchanged=counts["UNCHANGED"], moved=counts["MOVED"],
            deleted=deleted_n,
            error=len(errors or []),
            skipped_symlink=len(skipped_symlinks or []),
        )
    if to_compile is None:
        to_compile = sorted(e["path"] for e in files if e["action"] in ("NEW", "CHANGED"))
    if to_skip is None:
        to_skip = sorted(e["path"] for e in files if e["action"] == "UNCHANGED")
    return {
        "schema_version": "1.0",
        "run_id": "2026-04-19T00-00-00Z",
        "scanned_at": "2026-04-19T00:00:00Z",
        "vault_root": "/tmp/vault",
        "raw_root": "KDB/raw",
        "settings_snapshot": {
            "rename_detection": True, "symlink_policy": "skip",
            "scan_binary_files": True, "binary_compile_mode": "metadata_only",
        },
        "summary": summary,
        "files": files,
        "to_compile": to_compile,
        "to_reconcile": to_reconcile or [],
        "to_skip": to_skip,
        "errors": errors or [],
        "skipped_symlinks": skipped_symlinks or [],
    }


# ---------- happy path ----------

def test_empty_payload_validates() -> None:
    assert vls.validate(_payload()) == []


def test_minimal_new_only_validates() -> None:
    p = _payload(files=[_entry("KDB/raw/new.md", "NEW")])
    assert vls.validate(p) == []


def test_all_actions_validate() -> None:
    p = _payload(
        files=[
            _entry("KDB/raw/n.md", "NEW"),
            _entry("KDB/raw/c.md", "CHANGED"),
            _entry("KDB/raw/u.md", "UNCHANGED"),
            _entry("KDB/raw/m.md", "MOVED", previous_path="KDB/raw/m-old.md"),
        ],
        to_reconcile=[
            {"type": "MOVED", "from": "KDB/raw/m-old.md", "to": "KDB/raw/m.md", "hash": H1},
            {"type": "DELETED", "path": "KDB/raw/gone.md", "hash": H4},
        ],
    )
    assert vls.validate(p) == []


# ---------- schema-layer violations ----------

def test_missing_required_top_level_field() -> None:
    p = _payload()
    del p["schema_version"]
    errors = vls.validate(p)
    assert any("schema_version" in e for e in errors)


def test_scan_entry_missing_previous_hash_for_changed() -> None:
    entry = _entry("KDB/raw/c.md", "CHANGED")
    del entry["previous_hash"]
    p = _payload(files=[entry])
    errors = vls.validate(p)
    assert any("previous_hash" in e for e in errors)


def test_scan_entry_missing_previous_path_for_moved() -> None:
    entry = _entry("KDB/raw/m.md", "MOVED")
    del entry["previous_path"]
    p = _payload(
        files=[entry],
        to_reconcile=[{"type": "MOVED", "from": "KDB/raw/old.md", "to": "KDB/raw/m.md"}],
    )
    errors = vls.validate(p)
    assert any("previous_path" in e for e in errors)


def test_hash_format_rejected() -> None:
    entry = _entry("KDB/raw/n.md", "NEW", current_hash="md5:deadbeef")
    p = _payload(files=[entry])
    errors = vls.validate(p)
    assert any("current_hash" in e or "pattern" in e for e in errors)


def test_unknown_action_rejected() -> None:
    bad = _entry("KDB/raw/x.md", "NEW")
    bad["action"] = "RECOMPILE"
    p = _payload(files=[bad])
    errors = vls.validate(p)
    assert errors  # schema enum rejects this


# ---------- semantic-layer violations ----------

def test_duplicate_path_in_files() -> None:
    p = _payload(files=[
        _entry("KDB/raw/dup.md", "NEW"),
        _entry("KDB/raw/dup.md", "NEW"),
    ])
    errors = vls.validate(p)
    assert any("duplicate path" in e and "dup.md" in e for e in errors)


def test_to_compile_path_missing_from_files() -> None:
    p = _payload(
        files=[_entry("KDB/raw/a.md", "NEW")],
        to_compile=["KDB/raw/a.md", "KDB/raw/ghost.md"],
    )
    errors = vls.validate(p)
    assert any("ghost.md" in e and "to_compile" in e for e in errors)


def test_to_compile_action_mismatch() -> None:
    # MOVED in to_compile is illegal — to_compile allows only
    # NEW/CHANGED/UNCHANGED (UNCHANGED permitted for error-retry).
    p = _payload(
        files=[_entry("KDB/raw/m.md", "MOVED", previous_path="KDB/raw/old.md")],
        to_compile=["KDB/raw/m.md"],
        to_skip=[],
        to_reconcile=[{"type": "MOVED", "from": "KDB/raw/old.md", "to": "KDB/raw/m.md"}],
    )
    errors = vls.validate(p)
    assert any("to_compile" in e and "MOVED" in e for e in errors)


def test_to_compile_unchanged_permitted_for_error_retry() -> None:
    # UNCHANGED is legal in to_compile — it's how the scanner retries
    # sources whose previous compile errored. Validator can't see the
    # manifest, so it trusts the scanner's decision.
    p = _payload(
        files=[_entry("KDB/raw/u.md", "UNCHANGED")],
        to_compile=["KDB/raw/u.md"],
        to_skip=[],
    )
    assert vls.validate(p) == []


def test_to_skip_action_mismatch() -> None:
    p = _payload(
        files=[_entry("KDB/raw/n.md", "NEW")],
        to_compile=[],
        to_skip=["KDB/raw/n.md"],
    )
    errors = vls.validate(p)
    assert any("to_skip" in e and "NEW" in e for e in errors)


def test_to_compile_and_to_skip_overlap() -> None:
    p = _payload(
        files=[_entry("KDB/raw/x.md", "NEW")],
        to_compile=["KDB/raw/x.md"],
        to_skip=["KDB/raw/x.md"],
    )
    errors = vls.validate(p)
    assert any("both to_compile and to_skip" in e for e in errors)


def test_to_compile_missing_expected_entry() -> None:
    p = _payload(
        files=[_entry("KDB/raw/n.md", "NEW")],
        to_compile=[],  # should contain n.md
        to_skip=[],
    )
    errors = vls.validate(p)
    assert any(
        "to_compile" in e and "missing NEW" in e and "KDB/raw/n.md" in e
        for e in errors
    )


def test_to_skip_missing_expected_entry() -> None:
    # UNCHANGED file missing from BOTH to_compile and to_skip is illegal —
    # the scanner must classify every UNCHANGED file as either retry
    # (to_compile) or skip (to_skip).
    p = _payload(
        files=[_entry("KDB/raw/u.md", "UNCHANGED")],
        to_compile=[],
        to_skip=[],  # should contain u.md
    )
    errors = vls.validate(p)
    assert any(
        "UNCHANGED" in e and "KDB/raw/u.md" in e and "missing" in e
        for e in errors
    )


def test_moved_reconcile_to_not_in_files() -> None:
    p = _payload(
        files=[],
        to_reconcile=[{"type": "MOVED", "from": "KDB/raw/a.md", "to": "KDB/raw/b.md"}],
    )
    errors = vls.validate(p)
    assert any("MOVED 'to'" in e and "b.md" in e and "not found" in e for e in errors)


def test_moved_reconcile_from_present_in_files() -> None:
    # both old & new exist in files[] — 'from' should NOT be in files[]
    p = _payload(
        files=[
            _entry("KDB/raw/old.md", "NEW"),
            _entry("KDB/raw/new.md", "MOVED", previous_path="KDB/raw/old.md"),
        ],
        to_reconcile=[{"type": "MOVED", "from": "KDB/raw/old.md", "to": "KDB/raw/new.md", "hash": H1}],
    )
    errors = vls.validate(p)
    assert any("MOVED 'from'" in e and "old.md" in e for e in errors)


def test_moved_entry_without_reconcile_op() -> None:
    p = _payload(
        files=[_entry("KDB/raw/m.md", "MOVED", previous_path="KDB/raw/m-old.md")],
        to_reconcile=[],
    )
    errors = vls.validate(p)
    assert any("MOVED entry" in e and "m.md" in e and "no matching" in e for e in errors)


def test_deleted_reconcile_path_in_files() -> None:
    p = _payload(
        files=[_entry("KDB/raw/d.md", "NEW")],
        to_reconcile=[{"type": "DELETED", "path": "KDB/raw/d.md"}],
    )
    errors = vls.validate(p)
    assert any("DELETED" in e and "d.md" in e and "unexpectedly" in e for e in errors)


def test_summary_count_mismatch() -> None:
    p = _payload(
        files=[_entry("KDB/raw/n.md", "NEW")],
        summary=_summary(new=9),  # actual is 1
    )
    errors = vls.validate(p)
    assert any("summary.new" in e and "9" in e for e in errors)


def test_summary_deleted_count_mismatch() -> None:
    p = _payload(
        files=[],
        to_reconcile=[{"type": "DELETED", "path": "KDB/raw/gone.md"}],
        summary=_summary(deleted=0),  # should be 1
    )
    errors = vls.validate(p)
    assert any("summary.deleted" in e for e in errors)


# ---------- CLI smoke ----------

def _run_cli(args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "kdb_compiler.validate_last_scan", *args],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_exit_zero_on_valid_fixture() -> None:
    r = _run_cli([str(FIXTURES / "last_scan.minimal.valid.json")])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_cli_exit_one_on_invalid_fixture() -> None:
    r = _run_cli([str(FIXTURES / "last_scan.minimal.invalid.json")])
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.strip(), "expected error lines on stdout"


def test_cli_exit_two_on_bad_path(tmp_path: Path) -> None:
    r = _run_cli([str(tmp_path / "nonexistent.json")])
    assert r.returncode == 2


def test_cli_reads_stdin_when_no_argv() -> None:
    raw = (FIXTURES / "last_scan.minimal.valid.json").read_text(encoding="utf-8")
    r = _run_cli([], stdin=raw)
    assert r.returncode == 0
    assert "OK" in r.stdout
