"""Tests for graphdb_kdb.verifier (#63.5)."""
from __future__ import annotations

import json

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


# ---------- seed helpers ----------

SRC_ID = "KDB/raw/s.md"


def _seed_two_pages_one_edge(gdb: GraphDB) -> None:
    """alpha -> beta, both supported by SRC_ID."""
    pages = [
        make_page("alpha", outgoing_links=["beta"]),
        make_page("beta"),
    ]
    cr = make_compile_result([make_compiled_source(SRC_ID, pages)])
    scan = make_scan([make_scan_entry(SRC_ID)])
    gdb.apply_compile_result(cr, scan, "run-1")


def _matching_manifest() -> dict:
    """Hand-crafted manifest mirroring what _seed_two_pages_one_edge produces.

    Tracked fields only. Timestamps and other manifest-only fields can be
    anything — the verifier ignores them per L4.
    """
    return {
        "schema_version": "1.0",
        "stats": {"ignored": True},
        "runs": [],
        "settings": {},
        "tombstones": {},
        "pages": {
            "KDB/wiki/concepts/alpha.md": {
                "slug": "alpha",
                "page_type": "concept",
                "confidence": "medium",
                "last_run_id": "run-1",
                "orphan_candidate": False,
                "outgoing_links": ["beta"],
                "source_refs": [{"source_id": SRC_ID, "role": "primary"}],
            },
            "KDB/wiki/concepts/beta.md": {
                "slug": "beta",
                "page_type": "concept",
                "confidence": "medium",
                "last_run_id": "run-1",
                "orphan_candidate": False,
                "outgoing_links": [],
                "source_refs": [{"source_id": SRC_ID, "role": "primary"}],
            },
        },
        "sources": {
            SRC_ID: {
                "source_id": SRC_ID,
                "status": "active",
                "compile_state": "compiled",
                "compile_count": 1,
                "hash": "sha256:abc",
                "file_type": "markdown",
                "size_bytes": 100,
                "last_run_id": "run-1",
            },
        },
    }


# ---------- 1. perfect agreement ----------

def test_perfect_agreement_returns_ok(graph_dir):
    from graphdb_kdb import verifier
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, _matching_manifest())
    assert result.ok
    assert result.divergences == []
    assert result.counts["pages_checked"] == 2
    assert result.counts["sources_checked"] == 1
    assert result.counts["links_checked"] == 1
    assert result.counts["supports_checked"] == 2
    assert result.counts["missing_in_kuzu"] == 0
    assert result.counts["missing_in_manifest"] == 0
    assert result.counts["attribute_mismatch"] == 0


# ---------- 2. missing in Kuzu ----------

def test_page_missing_in_kuzu_detected(graph_dir):
    """Manifest lists a page the graph never ingested."""
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    manifest["pages"]["KDB/wiki/concepts/gamma.md"] = {
        "slug": "gamma",
        "page_type": "concept",
        "confidence": "medium",
        "last_run_id": "run-1",
        "orphan_candidate": False,
        "outgoing_links": [],
        "source_refs": [],
    }
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    kinds = [(d.kind, d.entity, d.key) for d in result.divergences]
    assert ("missing_in_kuzu", "page", "gamma") in kinds


def test_source_missing_in_kuzu_detected(graph_dir):
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    manifest["sources"]["KDB/raw/extra.md"] = {
        "source_id": "KDB/raw/extra.md",
        "status": "active",
        "compile_state": "compiled",
        "compile_count": 1,
        "hash": "sha256:xyz",
        "file_type": "markdown",
        "size_bytes": 50,
        "last_run_id": "run-1",
    }
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    assert any(
        d.kind == "missing_in_kuzu" and d.entity == "source" and d.key == "KDB/raw/extra.md"
        for d in result.divergences
    )


def test_links_to_missing_in_kuzu_detected(graph_dir):
    """Manifest claims beta->alpha edge but graph has only alpha->beta."""
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    manifest["pages"]["KDB/wiki/concepts/beta.md"]["outgoing_links"] = ["alpha"]
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    assert any(
        d.kind == "missing_in_kuzu" and d.entity == "links_to" and d.key == "beta→alpha"
        for d in result.divergences
    )


def test_supports_missing_in_kuzu_detected(graph_dir):
    """Manifest claims an extra Source supports alpha, but graph doesn't have it."""
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    manifest["sources"]["KDB/raw/ghost.md"] = {
        "source_id": "KDB/raw/ghost.md",
        "status": "active",
        "compile_state": "compiled",
        "compile_count": 1,
        "hash": "sha256:ghost",
        "file_type": "markdown",
        "size_bytes": 0,
        "last_run_id": "run-1",
    }
    manifest["pages"]["KDB/wiki/concepts/alpha.md"]["source_refs"].append({
        "source_id": "KDB/raw/ghost.md", "role": "supporting"
    })
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    assert any(
        d.kind == "missing_in_kuzu" and d.entity == "supports"
        and d.key == "KDB/raw/ghost.md→alpha"
        for d in result.divergences
    )


# ---------- 3. missing in manifest ----------

def test_page_missing_in_manifest_detected(graph_dir):
    """Graph has gamma; manifest doesn't."""
    from graphdb_kdb import verifier
    with GraphDB(graph_dir) as gdb:
        # Seed an extra page gamma in addition to the two-page chain.
        pages = [
            make_page("alpha", outgoing_links=["beta"]),
            make_page("beta"),
            make_page("gamma"),
        ]
        cr = make_compile_result([make_compiled_source(SRC_ID, pages)])
        scan = make_scan([make_scan_entry(SRC_ID)])
        gdb.apply_compile_result(cr, scan, "run-1")
        manifest = _matching_manifest()  # doesn't mention gamma
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    assert any(
        d.kind == "missing_in_manifest" and d.entity == "page" and d.key == "gamma"
        for d in result.divergences
    )


# ---------- 4. attribute mismatch ----------

def test_page_attribute_mismatch_detected(graph_dir):
    """Manifest claims page_type=article but graph has page_type=concept."""
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    manifest["pages"]["KDB/wiki/concepts/alpha.md"]["page_type"] = "article"
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    mismatches = [
        d for d in result.divergences
        if d.kind == "attribute_mismatch" and d.entity == "page" and d.key == "alpha"
    ]
    assert len(mismatches) == 1
    assert mismatches[0].field == "page_type"
    assert mismatches[0].manifest_value == "article"
    assert mismatches[0].kuzu_value == "concept"


def test_source_attribute_mismatch_detected(graph_dir):
    """Manifest hash differs from graph hash."""
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    manifest["sources"][SRC_ID]["hash"] = "sha256:WRONG"
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert not result.ok
    hits = [d for d in result.divergences
            if d.kind == "attribute_mismatch" and d.entity == "source" and d.field == "hash"]
    assert len(hits) == 1


def test_orphan_candidate_bool_maps_to_status_enum(graph_dir):
    """Manifest's orphan_candidate=True ↔ graph status='orphan_candidate'."""
    from graphdb_kdb import verifier
    # Seed page b as orphan_candidate by dropping it from a second compile.
    src = SRC_ID
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r1",
        )
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a")])]),
            scan, "r2",
        )
        # Manifest matching the post-r2 state: b is orphan, a is active.
        manifest = {
            "pages": {
                "KDB/wiki/concepts/a.md": {
                    "slug": "a", "page_type": "concept", "confidence": "medium",
                    "last_run_id": "r2", "orphan_candidate": False,
                    "outgoing_links": [],
                    "source_refs": [{"source_id": src, "role": "primary"}],
                },
                "KDB/wiki/concepts/b.md": {
                    "slug": "b", "page_type": "concept", "confidence": "medium",
                    "last_run_id": "r2", "orphan_candidate": True,
                    "outgoing_links": [],
                    "source_refs": [],
                },
            },
            "sources": {
                src: {
                    "source_id": src, "status": "active",
                    "compile_state": "compiled", "compile_count": 2,
                    "hash": "sha256:abc", "file_type": "markdown",
                    "size_bytes": 100, "last_run_id": "r2",
                },
            },
        }
        result = verifier.verify(gdb.conn, manifest)
    # The status enum mapping makes this pass cleanly — no status mismatch.
    status_mismatches = [
        d for d in result.divergences
        if d.kind == "attribute_mismatch" and d.field == "status"
    ]
    assert status_mismatches == []
    # And the run also passes overall.
    assert result.ok


# ---------- 5. file-loading entry point ----------

def test_verify_against_manifest_loads_from_disk(graph_dir, tmp_path):
    """The file-loading entry point reads JSON and delegates to verify()."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_matching_manifest()))
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = gdb.verify_against_manifest(manifest_path)
    assert result.ok


def test_verify_skips_manifest_only_fields(graph_dir):
    """`stats`, `runs`, `settings`, `tombstones` in manifest are ignored (L4)."""
    from graphdb_kdb import verifier
    manifest = _matching_manifest()
    # Stuff manifest-only fields with junk; verifier should not care.
    manifest["stats"] = {"orphans": 99, "junk": "data"}
    manifest["runs"] = [{"unrelated": "noise"}]
    manifest["settings"] = {"feature_flag": True}
    manifest["tombstones"] = {"old-slug": {"deleted_at": "2026-01-01T00:00:00Z"}}
    with GraphDB(graph_dir) as gdb:
        _seed_two_pages_one_edge(gdb)
        result = verifier.verify(gdb.conn, manifest)
    assert result.ok
