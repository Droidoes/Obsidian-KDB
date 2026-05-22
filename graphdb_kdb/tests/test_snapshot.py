"""Tests for graphdb_kdb.snapshot — #63.9.

Test scope (per Codex review + Phase 2 design lock):
1. JSONL parseability — every line in every file parses as JSON
2. Manifest count + sha256 — recorded values match what's on disk
3. Stable ordering — two snapshots of an unchanged graph are byte-identical
4. D34 grep invariant — snapshot.py has no kdb_compiler imports
5. Atomic-failure cleanup — failed mid-snapshot leaves no `<out>/`
6. latest.json pointer — points at the most recent snapshot dir
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.ingestor import apply_compile_result
from graphdb_kdb.snapshot import (
    SNAPSHOT_FORMAT_VERSION,
    default_snapshot_dirname,
    snapshot,
    update_latest_pointer,
)


# ---------- fixtures ----------


def _seed_graph(graph_dir: Path) -> None:
    """Populate a graph with a small synthetic state."""
    cr = {
        "run_id": "2026-04-19T10-00-00Z",
        "compiled_sources": [
            {
                "source_id": "KDB/raw/paper.md",
                "compile_meta": {"compile_state": "compiled"},
                "pages": [
                    {
                        "slug": "summary-paper",
                        "page_type": "summary",
                        "title": "Paper",
                        "status": "active",
                        "confidence": "high",
                        "outgoing_links": ["concept-a"],
                        "supports_page_existence": ["KDB/raw/paper.md"],
                    },
                    {
                        "slug": "concept-a",
                        "page_type": "concept",
                        "title": "Concept A",
                        "status": "active",
                        "confidence": "high",
                        "outgoing_links": [],
                        "supports_page_existence": ["KDB/raw/paper.md"],
                    },
                ],
            },
        ],
    }
    scan = {
        "run_id": "2026-04-19T10-00-00Z",
        "files": [
            {
                "path": "KDB/raw/paper.md",
                "current_hash": "sha256:abc123",
                "size_bytes": 1024,
                "file_type": "markdown",
            },
        ],
    }
    with GraphDB(graph_dir) as gdb:
        apply_compile_result(cr, scan, "2026-04-19T10-00-00Z", conn=gdb.conn)


# ---------- 1. JSONL parseability ----------


def test_snapshot_jsonl_files_parse(graph_dir, tmp_path):
    _seed_graph(graph_dir)
    out = tmp_path / "snap"
    result = snapshot(graph_dir, out)
    assert out.is_dir()
    for name in (
        "entities.jsonl", "sources.jsonl", "links_to.jsonl",
        "supports.jsonl", "alias_of.jsonl",
        "domain.jsonl", "belongs_to.jsonl",
    ):
        path = out / name
        assert path.is_file()
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
    # Manifest is JSON (not JSONL)
    json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert (out / "schema.cypher").is_file()


# ---------- 2. Manifest count + sha256 ----------


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_manifest_counts_and_hashes_match_disk(graph_dir, tmp_path):
    _seed_graph(graph_dir)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    # Top-level counts mirror per-file rows
    assert manifest["counts"]["entities"] == manifest["files"]["entities.jsonl"]["rows"]
    assert manifest["counts"]["sources"] == manifest["files"]["sources.jsonl"]["rows"]
    assert manifest["counts"]["links_to"] == manifest["files"]["links_to.jsonl"]["rows"]
    assert manifest["counts"]["supports"] == manifest["files"]["supports.jsonl"]["rows"]
    # #74.7 (format v2): alias_of count is recorded too
    assert manifest["counts"]["alias_of"] == manifest["files"]["alias_of.jsonl"]["rows"]
    # #80 (format v3): domain + belongs_to counts
    assert manifest["counts"]["domain"] == manifest["files"]["domain.jsonl"]["rows"]
    assert manifest["counts"]["belongs_to"] == manifest["files"]["belongs_to.jsonl"]["rows"]

    # Recorded sha256 matches what's actually on disk
    for name in (
        "entities.jsonl", "sources.jsonl", "links_to.jsonl",
        "supports.jsonl", "alias_of.jsonl",
        "domain.jsonl", "belongs_to.jsonl", "schema.cypher",
    ):
        recorded = manifest["files"][name]["sha256"]
        actual = _file_sha256(out / name)
        assert recorded == actual, f"{name}: manifest sha {recorded} != disk sha {actual}"

    # schema_ddl_sha256 at top level matches schema.cypher's sha
    assert manifest["schema_ddl_sha256"] == _file_sha256(out / "schema.cypher")

    # Recorded row counts match actual line counts
    for name in (
        "entities.jsonl", "sources.jsonl", "links_to.jsonl",
        "supports.jsonl", "alias_of.jsonl",
        "domain.jsonl", "belongs_to.jsonl",
    ):
        recorded = manifest["files"][name]["rows"]
        actual = sum(1 for _ in (out / name).read_text(encoding="utf-8").splitlines() if _)
        assert recorded == actual


def test_snapshot_manifest_has_required_top_level_keys(graph_dir, tmp_path):
    _seed_graph(graph_dir)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for key in (
        "schema_version", "schema_ddl_sha256", "snapshot_format_version",
        "emitted_at", "graph_dir", "counts", "files",
    ):
        assert key in m, f"manifest missing key: {key}"
    assert m["snapshot_format_version"] == SNAPSHOT_FORMAT_VERSION


# ---------- 3. Stable ordering — two snapshots are byte-identical ----------


def test_two_snapshots_of_unchanged_graph_are_byte_identical(graph_dir, tmp_path):
    _seed_graph(graph_dir)
    out_a = tmp_path / "snap-a"
    out_b = tmp_path / "snap-b"
    snapshot(graph_dir, out_a)
    snapshot(graph_dir, out_b)
    for name in (
        "entities.jsonl", "sources.jsonl", "links_to.jsonl",
        "supports.jsonl", "alias_of.jsonl",
        "domain.jsonl", "belongs_to.jsonl", "schema.cypher",
    ):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), \
            f"{name} differs between snapshots of unchanged graph"


# ---------- 4. D34 grep invariant ----------


def test_snapshot_module_has_no_kdb_compiler_imports():
    """D34: parse import nodes via ast (not text grep — docstrings can
    mention `kdb_compiler` legitimately)."""
    import ast

    path = Path(__file__).resolve().parent.parent / "snapshot.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("kdb_compiler"), \
                    f"D34 violation: import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("kdb_compiler"), \
                f"D34 violation: from {node.module} import ..."


# ---------- 5. Atomic-failure cleanup ----------


def test_snapshot_refuses_existing_out_dir(graph_dir, tmp_path):
    _seed_graph(graph_dir)
    out = tmp_path / "snap"
    out.mkdir()
    with pytest.raises(FileExistsError):
        snapshot(graph_dir, out)


def test_snapshot_failure_leaves_no_partial_out_dir(graph_dir, tmp_path, monkeypatch):
    """Simulate a mid-snapshot crash; final out_dir should not exist."""
    _seed_graph(graph_dir)
    out = tmp_path / "snap"

    # Monkeypatch one of the writers to raise mid-flight
    from graphdb_kdb import snapshot as snap_mod
    def boom(*a, **kw):
        raise RuntimeError("simulated mid-snapshot failure")
    monkeypatch.setattr(snap_mod, "_write_supports", boom)

    with pytest.raises(RuntimeError, match="simulated mid-snapshot failure"):
        snapshot(graph_dir, out)
    assert not out.exists(), "failed snapshot left a partial out_dir"
    # No leftover tmp dirs either
    assert not any(p.name.startswith("snap.tmp.") for p in tmp_path.iterdir())


# ---------- 6. latest.json pointer ----------


def test_latest_pointer_names_most_recent(graph_dir, tmp_path):
    _seed_graph(graph_dir)
    snapshots_root = tmp_path / "graph-snapshots"
    snapshots_root.mkdir()

    snap_a = snapshots_root / "2026-05-14T20-00-00_EDT"
    snap_b = snapshots_root / "2026-05-14T21-00-00_EDT"

    snapshot(graph_dir, snap_a)
    update_latest_pointer(snapshots_root, snap_a.name, "1.0")
    latest = json.loads((snapshots_root / "latest.json").read_text(encoding="utf-8"))
    assert latest["snapshot_dir"] == snap_a.name

    snapshot(graph_dir, snap_b)
    update_latest_pointer(snapshots_root, snap_b.name, "1.0")
    latest = json.loads((snapshots_root / "latest.json").read_text(encoding="utf-8"))
    assert latest["snapshot_dir"] == snap_b.name
    assert latest["snapshot_format_version"] == SNAPSHOT_FORMAT_VERSION


# ---------- 7. Snapshot id format ----------


def test_default_snapshot_dirname_format():
    name = default_snapshot_dirname()
    # YYYY-MM-DDTHH-MM-SS_<TZ>
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_\S+$", name), name


# ---------- 8. CLI smoke test ----------


def test_cli_snapshot_writes_files(graph_dir, tmp_path, monkeypatch):
    _seed_graph(graph_dir)
    monkeypatch.setenv("KDB_GRAPH_PATH", str(graph_dir))

    out_dir = tmp_path / "snap-cli"
    result = subprocess.run(
        [
            sys.executable, "-m", "graphdb_kdb.cli", "snapshot",
            "--out", str(out_dir), "--json",
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert out_dir.is_dir()
    assert (out_dir / "manifest.json").is_file()
    payload = json.loads(result.stdout)
    assert payload["counts"]["entities"] >= 1


# ---------- 9. #74.7 — alias state serialization (format v2) ----------


def _seed_graph_with_aliases(graph_dir: Path) -> None:
    """Seed a graph that exercises every alias-state surface area: a
    canonical entity, an alias entity, an ALIAS_OF edge, and a LINKS_TO
    edge to the canonical. Goes through the full Phase 3 + 3.5 ingest
    path so the data is shaped exactly as production would produce it."""
    cr = {
        "run_id": "alias-seed-run",
        "compiled_sources": [
            {
                "source_id": "KDB/raw/equities.md",
                "compile_meta": {"compile_state": "compiled"},
                "pages": [
                    {
                        "slug": "apple-inc",
                        "page_type": "concept",
                        "title": "Apple Inc.",
                        "status": "active",
                        "confidence": "high",
                        "outgoing_links": [],
                    },
                ],
            },
        ],
        "canonical_meta": {
            "algorithm_version": "1.0",
            "ledger_snapshot_sha256": "deadbeef",
            "aliases_emitted": [
                {"alias_slug": "aapl",
                 "canonical_slug": "apple-inc",
                 "algorithm": "ledger"},
            ],
            "outgoing_link_remaps": [],
            "merged_pages": [],
        },
    }
    scan = {
        "run_id": "alias-seed-run",
        "files": [
            {"path": "KDB/raw/equities.md", "current_hash": "sha256:eq",
             "size_bytes": 1024, "file_type": "markdown"},
        ],
    }
    with GraphDB(graph_dir) as gdb:
        apply_compile_result(cr, scan, "alias-seed-run", conn=gdb.conn)


def test_snapshot_serializes_canonical_id_on_alias_entity(
    graph_dir, tmp_path,
):
    """#74.7 format v2: entities.jsonl rows carry canonical_id (None for
    canonicals, str for aliases). Tier-2 recovery from snapshot alone
    needs this column or alias identity is lost."""
    _seed_graph_with_aliases(graph_dir)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    rows = {
        json.loads(line)["slug"]: json.loads(line)
        for line in (out / "entities.jsonl").read_text("utf-8").splitlines()
    }
    assert rows["apple-inc"]["canonical_id"] is None
    assert rows["aapl"]["canonical_id"] == "apple-inc"


def test_snapshot_alias_of_jsonl_records_edge_with_provenance(
    graph_dir, tmp_path,
):
    """#74.7 format v2: alias_of.jsonl carries one row per ALIAS_OF edge
    with run_id + algorithm + created_at provenance. Pre-#74 graphs
    produce an empty file with rows=0 (test below)."""
    _seed_graph_with_aliases(graph_dir)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    rows = [
        json.loads(line)
        for line in (out / "alias_of.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    e = rows[0]
    assert e["alias_slug"] == "aapl"
    assert e["canonical_slug"] == "apple-inc"
    assert e["algorithm"] == "ledger"
    assert e["run_id"] == "alias-seed-run"
    assert e["created_at"]  # non-empty timestamp string

    # Manifest counts reflect it
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert manifest["counts"]["alias_of"] == 1
    assert manifest["files"]["alias_of.jsonl"]["rows"] == 1
    # Format-version assertion lives in test_snapshot_format_version_is_v3
    # so this test's intent ("alias_of edge content + provenance") stays
    # focused on the alias surface introduced in #74.7 (format v2).


def test_snapshot_alias_of_empty_for_pre_74_graph(graph_dir, tmp_path):
    """A graph with no aliases produces alias_of.jsonl with zero rows —
    back-compat: pre-#74 ingest paths produce an empty file, not no file."""
    _seed_graph(graph_dir)  # canonical-only seed (no canonical_meta)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    content = (out / "alias_of.jsonl").read_text("utf-8")
    assert content == ""
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert manifest["counts"]["alias_of"] == 0
    # And every canonical entity has canonical_id=None in the snapshot
    rows = [
        json.loads(line)
        for line in (out / "entities.jsonl").read_text("utf-8").splitlines()
    ]
    assert all(r["canonical_id"] is None for r in rows)


# ---------- 10. #80 — Domain + BELONGS_TO serialization (format v3) ----------


def _seed_graph_with_domains(graph_dir: Path) -> None:
    """Seed a graph that exercises the domain pipeline: one page with a
    single-string domain + sub_domain, one page with an array domain.
    Mirrors the production ingest path so post-normalize state is what
    snapshot reads back."""
    cr = {
        "run_id": "domain-seed-run",
        "compiled_sources": [
            {
                "source_id": "KDB/raw/markets.md",
                "compile_meta": {"compile_state": "compiled"},
                "pages": [
                    {
                        "slug": "alpha",
                        "page_type": "concept",
                        "title": "Alpha",
                        "status": "active",
                        "confidence": "high",
                        "outgoing_links": [],
                        "domain": "Investing",
                        "sub_domain": "Value Investing",
                    },
                    {
                        "slug": "beta",
                        "page_type": "concept",
                        "title": "Beta",
                        "status": "active",
                        "confidence": "high",
                        "outgoing_links": [],
                        "domain": ["Investing", "Macro"],
                    },
                ],
            },
        ],
    }
    scan = {
        "run_id": "domain-seed-run",
        "files": [
            {"path": "KDB/raw/markets.md", "current_hash": "sha256:mk",
             "size_bytes": 256, "file_type": "markdown"},
        ],
    }
    with GraphDB(graph_dir) as gdb:
        apply_compile_result(cr, scan, "domain-seed-run", conn=gdb.conn)


def test_snapshot_domain_jsonl_records_domains(graph_dir, tmp_path):
    """#80 (format v3): domain.jsonl carries one row per Domain node with
    name + provenance (created_at, first_run_id)."""
    _seed_graph_with_domains(graph_dir)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    rows = {
        json.loads(line)["name"]: json.loads(line)
        for line in (out / "domain.jsonl").read_text("utf-8").splitlines()
    }
    # _normalize_domain: "Investing"→"investing", "Macro"→"macro"
    assert set(rows.keys()) == {"investing", "macro"}
    for r in rows.values():
        assert r["first_run_id"] == "domain-seed-run"
        assert r["created_at"]  # non-empty timestamp

    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert manifest["counts"]["domain"] == 2
    assert manifest["snapshot_format_version"] == 3


def test_snapshot_belongs_to_jsonl_records_edges(graph_dir, tmp_path):
    """#80 (format v3): belongs_to.jsonl carries one row per BELONGS_TO
    edge with entity_slug + domain_name + sub_domain (nullable) + run_id."""
    _seed_graph_with_domains(graph_dir)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    rows = [
        json.loads(line)
        for line in (out / "belongs_to.jsonl").read_text("utf-8").splitlines()
    ]
    by_key = {(r["entity_slug"], r["domain_name"]): r for r in rows}
    # alpha→investing carries sub_domain "value-investing" (R12 normalized);
    # beta's domain is plural so sub_domain is omitted (None) on both edges.
    assert by_key[("alpha", "investing")]["sub_domain"] == "value-investing"
    assert by_key[("beta", "investing")]["sub_domain"] is None
    assert by_key[("beta", "macro")]["sub_domain"] is None
    for r in rows:
        assert r["run_id"] == "domain-seed-run"
        assert r["created_at"]

    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert manifest["counts"]["belongs_to"] == 3
    assert manifest["files"]["belongs_to.jsonl"]["rows"] == 3


def test_snapshot_domain_files_empty_for_pre_76_graph(graph_dir, tmp_path):
    """A graph with no domains produces empty domain.jsonl + belongs_to.jsonl
    (parity with alias_of empty-for-pre-#74 test)."""
    _seed_graph(graph_dir)  # plain seed (no domain field on pages)
    out = tmp_path / "snap"
    snapshot(graph_dir, out)
    assert (out / "domain.jsonl").read_text("utf-8") == ""
    assert (out / "belongs_to.jsonl").read_text("utf-8") == ""
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert manifest["counts"]["domain"] == 0
    assert manifest["counts"]["belongs_to"] == 0
    assert manifest["snapshot_format_version"] == 3


def test_snapshot_format_version_is_v3():
    """#80: snapshot bumped from v2 (alias_of) to v3 (domain + belongs_to)."""
    assert SNAPSHOT_FORMAT_VERSION == 3
