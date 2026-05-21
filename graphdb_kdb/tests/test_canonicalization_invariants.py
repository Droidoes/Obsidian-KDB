"""Tests for #74.6 — Layer 3 canonicalization invariants (C1–C4).

Per docs/task74-canonicalization-blueprint.md §9.1, the four invariants are
pure live-graph properties — no replay, no sidecar reads required. These
tests stand up small graphs by hand (no apply_compile_result), violate
each invariant deliberately, and verify the detector catches it.

Happy paths go through `apply_compile_result` to confirm that the
ingestion-produced graph state actually satisfies C1–C4.
"""
from __future__ import annotations

from graphdb_kdb import verifier
from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


# ---------- helpers ----------


def _seed_two_canonicals(gdb: GraphDB) -> None:
    """Plant two canonical entities + a SUPPORTS edge each, via the ingest
    path so all entity fields are populated normally."""
    cs = make_compiled_source(
        "KDB/raw/x.md",
        [make_page("apple-inc"), make_page("microsoft")],
    )
    cr = make_compile_result([cs])
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    gdb.apply_compile_result(cr, scan, "seed-run")


def _alias_entry(alias: str, canonical: str, algorithm: str = "ledger") -> dict:
    return {"alias_slug": alias, "canonical_slug": canonical, "algorithm": algorithm}


def _canonical_meta(aliases: list[dict] | None = None) -> dict:
    return {
        "algorithm_version": "1.0",
        "ledger_snapshot_sha256": "deadbeef",
        "aliases_emitted": aliases or [],
        "outgoing_link_remaps": [],
        "merged_pages": [],
    }


def _by_field(divs, field_code):
    return [d for d in divs if d.field == field_code]


# ---------- C1 — alias without ALIAS_OF ----------


def test_c1_violation_alias_entity_without_alias_of_edge(graph_dir):
    """Hand-roll: an Entity with canonical_id set but no ALIAS_OF edge to
    the canonical → C1 violation."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_canonicals(gdb)
        # Directly insert an alias entity without the edge — simulates a
        # corruption scenario the verifier should catch.
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'aapl', canonical_id: 'apple-inc', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    c1 = _by_field(divs, "C1")
    assert len(c1) == 1
    assert c1[0].kind == "invariant_violation"
    assert c1[0].category == "entity"
    assert c1[0].key == "aapl"
    assert c1[0].source == "canonicalization_invariants"


def test_c1_happy_alias_with_alias_of_edge_passes(graph_dir):
    """A properly-ingested alias (via Phase 3.5) has the matching
    ALIAS_OF edge → C1 holds."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([_alias_entry("aapl", "apple-inc")]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    assert _by_field(divs, "C1") == []


# ---------- C2 — ALIAS_OF source's canonical_id mismatches destination ----------


def test_c2_violation_alias_of_canonical_id_mismatch(graph_dir):
    """Hand-roll: an ALIAS_OF edge alias→canonical where alias.canonical_id
    points elsewhere → C2 violation."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_canonicals(gdb)
        # alias points (via canonical_id) at 'microsoft' but its ALIAS_OF
        # edge goes to 'apple-inc'.
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'mismatch-alias', canonical_id: 'microsoft', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        gdb.conn.execute(
            "MATCH (a:Entity {slug: 'mismatch-alias'}), (c:Entity {slug: 'apple-inc'}) "
            "CREATE (a)-[:ALIAS_OF {run_id: 'manual', created_at: '2026-05-20', "
            "algorithm: 'ledger'}]->(c)"
        )
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    c2 = _by_field(divs, "C2")
    assert len(c2) == 1
    assert c2[0].category == "alias_of"
    assert c2[0].key == "mismatch-alias→apple-inc"
    assert c2[0].expected_value == "apple-inc"   # destination slug
    assert c2[0].actual_value == "microsoft"     # source's canonical_id


def test_c2_violation_alias_of_source_has_null_canonical_id(graph_dir):
    """Hand-roll: an Entity with an ALIAS_OF edge to a canonical but no
    canonical_id set on itself → C2 violation (NULL branch). This is a
    distinct corruption from the slug-mismatch branch above."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_canonicals(gdb)
        # Edge present, but canonical_id deliberately NULL.
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'null-canon-alias', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        gdb.conn.execute(
            "MATCH (a:Entity {slug: 'null-canon-alias'}), (c:Entity {slug: 'apple-inc'}) "
            "CREATE (a)-[:ALIAS_OF {run_id: 'manual', created_at: '2026-05-20', "
            "algorithm: 'ledger'}]->(c)"
        )
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    c2 = _by_field(divs, "C2")
    assert len(c2) == 1
    assert c2[0].key == "null-canon-alias→apple-inc"
    assert c2[0].expected_value == "apple-inc"
    assert c2[0].actual_value is None  # canonical_id is NULL


# ---------- C3 — flat invariant (no chains) ----------


def test_c3_violation_chain_detected(graph_dir):
    """Hand-roll: A.canonical_id=B, B.canonical_id=C → A breaks C3
    (B is an alias, so A's canonical_id points at a non-canonical)."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_canonicals(gdb)
        # 'b-alias' is itself an alias for apple-inc; if 'a-alias' points
        # at 'b-alias' instead of 'apple-inc', that's a chain.
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'b-alias', canonical_id: 'apple-inc', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'a-alias', canonical_id: 'b-alias', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    c3 = _by_field(divs, "C3")
    # Only a-alias chains (b-alias points at the canonical apple-inc, OK).
    assert len(c3) == 1
    assert c3[0].key == "a-alias"
    assert "b-alias" in c3[0].expected_value


def test_c3_happy_d_r5_13_chain_flattening_no_chain_in_graph(graph_dir):
    """Sanity: a well-ingested graph (via Phase 3.5) has no chains —
    Stage 6's D-R5-13 flattening ensures every canonical_id points at
    a root."""
    cs = make_compiled_source("KDB/raw/x.md", [make_page("apple-inc")])
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([
            _alias_entry("aapl", "apple-inc"),
            _alias_entry("apple", "apple-inc"),
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    assert _by_field(divs, "C3") == []


# ---------- C4 — LINKS_TO targets are canonical ----------


def test_c4_violation_links_to_alias_target(graph_dir):
    """Hand-roll: a LINKS_TO edge whose destination has canonical_id set
    (i.e., the link points at an alias) → C4 violation."""
    with GraphDB(graph_dir) as gdb:
        _seed_two_canonicals(gdb)
        # Add an alias for apple-inc; then make microsoft LINKS_TO that alias.
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'aapl', canonical_id: 'apple-inc', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        gdb.conn.execute(
            "MATCH (a:Entity {slug: 'microsoft'}), (b:Entity {slug: 'aapl'}) "
            "CREATE (a)-[:LINKS_TO {run_id: 'manual', created_at: '2026-05-20'}]->(b)"
        )
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    c4 = _by_field(divs, "C4")
    assert len(c4) == 1
    assert c4[0].category == "links_to"
    assert c4[0].key == "microsoft→aapl"


def test_c4_happy_links_to_canonical_target_passes(graph_dir):
    """An ingested LINKS_TO from a page to a canonical target is fine."""
    cs = make_compiled_source(
        "KDB/raw/x.md",
        [
            make_page("apple-inc"),
            make_page("microsoft", outgoing_links=["apple-inc"]),
        ],
    )
    cr = make_compile_result([cs])
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    assert _by_field(divs, "C4") == []


# ---------- pre-#74 graph trivially passes ----------


def test_pre_74_graph_no_aliases_satisfies_all_invariants(graph_dir):
    """A graph with no aliases at all (the pre-#74 baseline) — every
    Entity has canonical_id IS NULL, no ALIAS_OF edges. All four
    invariants pass vacuously."""
    cs = make_compiled_source(
        "KDB/raw/x.md",
        [
            make_page("alpha", outgoing_links=["beta"]),
            make_page("beta"),
        ],
    )
    cr = make_compile_result([cs])  # no canonical_meta
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    assert divs == []


# ---------- aggregate: full happy graph ----------


def test_all_invariants_pass_on_fully_canonicalized_graph(graph_dir):
    """A graph ingested through the full Phase 3 + 3.5 path with
    canonical_meta from Stage 6 satisfies C1, C2, C3, and C4 together."""
    cs = make_compiled_source(
        "KDB/raw/x.md",
        [
            make_page("apple-inc"),
            make_page("microsoft", outgoing_links=["apple-inc"]),
        ],
    )
    cr = make_compile_result(
        [cs],
        canonical_meta=_canonical_meta([
            _alias_entry("aapl", "apple-inc"),
            _alias_entry("msft", "microsoft"),
        ]),
    )
    scan = make_scan([make_scan_entry("KDB/raw/x.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
        divs = verifier.verify_canonicalization_invariants(gdb.conn)
    assert divs == []


# ---------- integration into top-level verify() ----------


def test_verify_includes_layer_3_in_divergences_and_counts(graph_dir, tmp_path):
    """The top-level verifier.verify() runs Layer 3 alongside Layers 1+2.
    Violations show up tagged source='canonicalization_invariants' and
    are counted under counts['invariant_violation']."""
    import json
    from graphdb_kdb.adapters.obsidian_runs import ObsidianRunsAdapter  # noqa: F401

    journals_dir = tmp_path / "runs"
    journals_dir.mkdir(parents=True)
    # Empty journals dir → replay is empty graph; we deliberately taint
    # the live graph with a C1 violation so Layer 3 fires.
    with GraphDB(graph_dir) as gdb:
        gdb.conn.execute(
            "CREATE (e:Entity {slug: 'orphan-alias', canonical_id: 'no-such-canonical', "
            "title: '', page_type: 'alias', status: 'alias', confidence: '', "
            "created_at: '2026-05-20', updated_at: '2026-05-20', "
            "first_run_id: 'manual', last_run_id: 'manual'})"
        )
        result = verifier.verify(gdb.conn, journals_dir=journals_dir)
    assert not result.ok
    # Layer 3 divergence present and properly tagged
    layer3 = [
        d for d in result.divergences
        if d.source == "canonicalization_invariants"
    ]
    assert len(layer3) == 1
    assert layer3[0].field == "C1"
    assert layer3[0].key == "orphan-alias"
    # And the invariant_violation count reflects it
    assert result.counts["invariant_violation"] == 1
