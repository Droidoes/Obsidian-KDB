"""Tests for planner — CompileJob construction from last_scan + manifest.

Coverage per blueprint §10:
    - one job per to_compile entry (non-binary)
    - abs_path resolution (vault_root / source_id)
    - context_snapshot populated via context_loader
    - empty to_compile -> empty job list
    - manifest missing -> jobs still produced with empty context
    - binary filter: to_compile=[a.md, b.pdf with is_binary=True] -> only a.md
    - all-binary case -> empty job list

Plus CLI smoke and load_manifest behaviour.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdb_compiler import planner
from kdb_compiler.types import CompileJob


SOURCE_A = "KDB/raw/alpha.md"
SOURCE_B = "KDB/raw/beta.pdf"
SOURCE_C = "KDB/raw/gamma.md"


def _file(path: str, *, is_binary: bool = False, action: str = "NEW") -> dict:
    """Minimal scan file entry. Extra fields only when a test needs them."""
    return {
        "path": path,
        "action": action,
        "current_hash": "sha256:" + "a" * 64,
        "current_mtime": 0.0,
        "size_bytes": 1,
        "file_type": "binary" if is_binary else "markdown",
        "is_binary": is_binary,
    }


def _scan(*, to_compile: list[str], files: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "r1",
        "to_compile": to_compile,
        "files": files,
    }


def _write_vault_source(vault_root: Path, source_id: str, body: str) -> None:
    p = vault_root / source_id
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


# ---------- eligible_source_ids: binary filter ----------

def test_eligible_source_ids_passes_non_binary_through() -> None:
    scan = _scan(
        to_compile=[SOURCE_A, SOURCE_C],
        files=[_file(SOURCE_A), _file(SOURCE_C)],
    )
    assert planner.eligible_source_ids(scan) == [SOURCE_A, SOURCE_C]


def test_eligible_source_ids_drops_binaries() -> None:
    scan = _scan(
        to_compile=[SOURCE_A, SOURCE_B, SOURCE_C],
        files=[_file(SOURCE_A), _file(SOURCE_B, is_binary=True), _file(SOURCE_C)],
    )
    assert planner.eligible_source_ids(scan) == [SOURCE_A, SOURCE_C]


def test_eligible_source_ids_all_binary_yields_empty() -> None:
    scan = _scan(
        to_compile=[SOURCE_B],
        files=[_file(SOURCE_B, is_binary=True)],
    )
    assert planner.eligible_source_ids(scan) == []


def test_eligible_source_ids_empty_to_compile_yields_empty() -> None:
    scan = _scan(to_compile=[], files=[])
    assert planner.eligible_source_ids(scan) == []


def test_eligible_source_ids_preserves_scan_order() -> None:
    scan = _scan(
        to_compile=[SOURCE_C, SOURCE_A],
        files=[_file(SOURCE_A), _file(SOURCE_C)],
    )
    assert planner.eligible_source_ids(scan) == [SOURCE_C, SOURCE_A]


# ---------- build_jobs: core behaviour ----------

def test_build_jobs_one_per_eligible_source(tmp_path: Path) -> None:
    _write_vault_source(tmp_path, SOURCE_A, "alpha body")
    _write_vault_source(tmp_path, SOURCE_C, "gamma body")
    scan = _scan(
        to_compile=[SOURCE_A, SOURCE_C],
        files=[_file(SOURCE_A), _file(SOURCE_C)],
    )
    jobs = planner.build_jobs(scan, {}, tmp_path)
    assert len(jobs) == 2
    assert [j.source_id for j in jobs] == [SOURCE_A, SOURCE_C]


def test_build_jobs_abs_path_joins_vault_root(tmp_path: Path) -> None:
    _write_vault_source(tmp_path, SOURCE_A, "body")
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])
    jobs = planner.build_jobs(scan, {}, tmp_path)
    assert jobs[0].abs_path == str(tmp_path / SOURCE_A)


def test_build_jobs_binary_dropped(tmp_path: Path) -> None:
    _write_vault_source(tmp_path, SOURCE_A, "body")
    scan = _scan(
        to_compile=[SOURCE_A, SOURCE_B],
        files=[_file(SOURCE_A), _file(SOURCE_B, is_binary=True)],
    )
    jobs = planner.build_jobs(scan, {}, tmp_path)
    assert [j.source_id for j in jobs] == [SOURCE_A]


def test_build_jobs_all_binary_yields_empty(tmp_path: Path) -> None:
    scan = _scan(
        to_compile=[SOURCE_B],
        files=[_file(SOURCE_B, is_binary=True)],
    )
    jobs = planner.build_jobs(scan, {}, tmp_path)
    assert jobs == []


def test_build_jobs_empty_to_compile_yields_empty(tmp_path: Path) -> None:
    jobs = planner.build_jobs(_scan(to_compile=[], files=[]), {}, tmp_path)
    assert jobs == []


def test_build_jobs_missing_source_file_still_emits_job(tmp_path: Path) -> None:
    """Source text read failure is recoverable at plan time — the job is
    emitted with empty context and compile_one captures the read failure
    in its resp-stats record (blueprint §9)."""
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])
    jobs = planner.build_jobs(scan, {}, tmp_path)
    assert len(jobs) == 1
    assert jobs[0].source_id == SOURCE_A
    assert jobs[0].context_snapshot.pages == []


# ---------- build_jobs: context snapshot wired correctly ----------

def test_build_jobs_populates_context_snapshot(tmp_path: Path) -> None:
    """Manifest has a page citing SOURCE_A; the job's context_snapshot
    should include it."""
    _write_vault_source(tmp_path, SOURCE_A, "body")
    manifest = {
        "pages": {
            "KDB/wiki/summaries/alpha.md": {
                "slug": "alpha",
                "title": "Alpha",
                "page_type": "summary",
                "outgoing_links": [],
                "source_refs": [{"source_id": SOURCE_A, "hash": "x", "role": "primary"}],
            },
        }
    }
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])
    jobs = planner.build_jobs(scan, manifest, tmp_path)
    assert [p.slug for p in jobs[0].context_snapshot.pages] == ["alpha"]


def test_build_jobs_context_cap_forwarded(tmp_path: Path) -> None:
    _write_vault_source(tmp_path, SOURCE_A, "body")
    pages = {}
    for i in range(10):
        slug = f"c{i:02d}"
        pages[f"KDB/wiki/concepts/{slug}.md"] = {
            "slug": slug,
            "title": slug,
            "page_type": "concept",
            "outgoing_links": [],
            "source_refs": [{"source_id": SOURCE_A, "hash": "x", "role": "primary"}],
        }
    manifest = {"pages": pages}
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])

    jobs = planner.build_jobs(scan, manifest, tmp_path, context_page_cap=3)
    assert len(jobs[0].context_snapshot.pages) == 3


# ---------- load_manifest ----------

def test_load_manifest_missing_returns_empty(tmp_path: Path) -> None:
    assert planner.load_manifest(tmp_path) == {}


def test_load_manifest_empty_file_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("", encoding="utf-8")
    assert planner.load_manifest(tmp_path) == {}


def test_load_manifest_reads_json(tmp_path: Path) -> None:
    payload = {"schema_version": "1.0", "pages": {}}
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    assert planner.load_manifest(tmp_path) == payload


def test_load_manifest_corrupt_raises(tmp_path: Path) -> None:
    """Corrupt manifest should surface, not silently degrade to {}."""
    (tmp_path / "manifest.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        planner.load_manifest(tmp_path)


# ---------- plan() I/O shell ----------

def test_plan_uses_default_state_root(tmp_path: Path) -> None:
    vault = tmp_path
    state = vault / "KDB" / "state"
    state.mkdir(parents=True)
    _write_vault_source(vault, SOURCE_A, "body")
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])

    jobs = planner.plan(vault, scan=scan)
    assert [j.source_id for j in jobs] == [SOURCE_A]


def test_plan_respects_explicit_state_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_vault_source(vault, SOURCE_A, "body")
    explicit_state = tmp_path / "elsewhere"
    explicit_state.mkdir()
    manifest = {
        "pages": {
            "KDB/wiki/summaries/alpha.md": {
                "slug": "alpha", "title": "Alpha", "page_type": "summary",
                "outgoing_links": [],
                "source_refs": [{"source_id": SOURCE_A, "hash": "x", "role": "primary"}],
            },
        }
    }
    (explicit_state / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])
    jobs = planner.plan(vault, scan=scan, state_root=explicit_state)
    assert [p.slug for p in jobs[0].context_snapshot.pages] == ["alpha"]


# ---------- CLI ----------

def test_cli_human_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = tmp_path
    state = vault / "KDB" / "state"
    state.mkdir(parents=True)
    _write_vault_source(vault, SOURCE_A, "body")
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])
    scan.update({
        "scanned_at": "2026-04-19T00:00:00Z",
        "vault_root": str(vault),
        "raw_root": "KDB/raw",
    })
    (state / "last_scan.json").write_text(json.dumps(scan), encoding="utf-8")

    rc = planner.main(["--vault-root", str(vault)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 job(s)" in out
    assert SOURCE_A in out


def test_cli_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = tmp_path
    state = vault / "KDB" / "state"
    state.mkdir(parents=True)
    _write_vault_source(vault, SOURCE_A, "body")
    scan = _scan(to_compile=[SOURCE_A], files=[_file(SOURCE_A)])
    (state / "last_scan.json").write_text(json.dumps(scan), encoding="utf-8")

    rc = planner.main(["--vault-root", str(vault), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["source_id"] == SOURCE_A
    assert data[0]["context_page_count"] == 0


def test_cli_missing_scan_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "KDB" / "state").mkdir(parents=True)
    rc = planner.main(["--vault-root", str(tmp_path)])
    assert rc == 1
    assert "missing last_scan.json" in capsys.readouterr().err
