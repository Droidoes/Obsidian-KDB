"""Author map: yaml override, normalization default, unmapped listing."""
from __future__ import annotations

from kdb_fts import author_map, ledger


def test_default_canonical_is_normalized_raw(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    aid = author_map.resolve(conn, "  Aswath   Damodaran ", {})
    row = conn.execute(
        "SELECT canonical_name, publication FROM authors WHERE author_id = ?", (aid,)
    ).fetchone()
    assert row == ("Aswath Damodaran", None)
    # alias recorded; resolving again reuses the same author
    assert author_map.resolve(conn, "  Aswath   Damodaran ", {}) == aid


def test_yaml_override_maps_alias_to_canonical(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    mapping = {"Damodaran": {"canonical": "Aswath Damodaran",
                             "publication": "Musings on Markets"}}
    aid = author_map.resolve(conn, "Damodaran", mapping)
    row = conn.execute(
        "SELECT canonical_name, publication FROM authors WHERE author_id = ?", (aid,)
    ).fetchone()
    assert row == ("Aswath Damodaran", "Musings on Markets")
    # and the default-normalized form lands on the SAME author row
    assert author_map.resolve(conn, "Aswath Damodaran", mapping) == aid


def test_load_map_missing_file_returns_empty(tmp_path):
    assert author_map.load_map(tmp_path / "fts") == {}


def test_load_map_roundtrip(tmp_path):
    root = tmp_path / "fts"
    root.mkdir(parents=True)
    (root / "author_map.yaml").write_text(
        "Damodaran:\n  canonical: Aswath Damodaran\n  publication: Musings on Markets\n"
    )
    assert author_map.load_map(root) == {
        "Damodaran": {"canonical": "Aswath Damodaran", "publication": "Musings on Markets"}
    }


def test_unmapped_lists_only_non_overridden(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    author_map.resolve(conn, "Damodaran", {"Damodaran": {"canonical": "Aswath Damodaran"}})
    author_map.resolve(conn, "Mystery Writer", {})
    assert author_map.unmapped(conn) == ["Mystery Writer"]


def test_unmapped_includes_internal_whitespace_variant(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    author_map.resolve(conn, "Aswath  Damodaran", {})  # double internal space
    assert author_map.unmapped(conn) == ["Aswath  Damodaran"]
