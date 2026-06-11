"""kdb_graph.testing is the public, shippable test-support surface (Phase 1).

Cross-package consumers import factories from here, NOT from kdb_graph.tests.conftest.
"""
from __future__ import annotations

from kdb_graph import testing


def test_make_page_defaults():
    p = testing.make_page("alpha-beta")
    assert p["slug"] == "alpha-beta"
    assert p["page_type"] == "concept"
    assert p["title"] == "Title for alpha-beta"
    assert p["outgoing_links"] == []


def test_make_compile_result_shape():
    src = testing.make_compiled_source(
        "KDB/raw/x.md", [testing.make_page("alpha")]
    )
    cr = testing.make_compile_result([src], run_id="r1")
    assert cr["run_id"] == "r1"
    assert cr["success"] is True
    assert cr["compiled_sources"][0]["source_id"] == "KDB/raw/x.md"


def test_make_scan_pairs_with_source():
    scan = testing.make_scan([testing.make_scan_entry("KDB/raw/x.md")])
    assert scan["files"][0]["path"] == "KDB/raw/x.md"
    assert scan["files"][0]["action"] == "CHANGED"
