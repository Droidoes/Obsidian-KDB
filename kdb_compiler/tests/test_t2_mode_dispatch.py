"""Tests for the Task #90 v0.2 T2Mode dispatcher + branch selector.

Covers:
- T2Mode.STRUCTURED three-state branch (D-90-8 headline): State A pre-Pass-1
  fallback to legacy / State B non-empty signal / State C explicit empty → ∅
- T2Mode.LAYERED: structured ∪ legacy; honors State C with legacy fallback
- T2Mode.LEGACY: ignores frontmatter entirely
- Default mode = STRUCTURED (D-90-1)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kdb_graph.graphdb import GraphDB
from kdb_compiler.context_loader import (
    T2Mode,
    build_context_snapshot,
)
from common.source_io import SourceFrontmatter


# ---------- Fixture: minimal graph with two entities ----------

@pytest.fixture
def t2_graph(tmp_path: Path):
    """Two active entities + one source. Body contains 'value-investing' as
    a whole word so legacy regex catches it; LLM-emitted entity_search_keys
    drive the structured branch."""
    with GraphDB(tmp_path / "t2-graph") as g:
        conn = g.conn
        for slug in ["value-investing", "compound-interest"]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: 'active', confidence: 'medium', canonical_id: NULL, "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug},
            )
        conn.execute(
            "CREATE (s:Source {source_id: 'src-1', source_type: 'raw', "
            "canonical_path: 'src-1', status: 'active', file_type: 'markdown', "
            "hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r1', moved_to: ''})"
        )
        # Both entities BELONGS_TO 'ai-ml' (the _fm() domain) so the same-domain
        # gate (D3) admits them; these tests exercise T2 mode dispatch, not the gate.
        conn.execute(
            "CREATE (d:Domain {name: 'ai-ml', created_at: '2026-01-01', "
            "first_run_id: 'r1'})"
        )
        for slug in ["value-investing", "compound-interest"]:
            conn.execute(
                "MATCH (e:Entity {slug: $s}), (d:Domain {name: 'ai-ml'}) "
                "CREATE (e)-[:BELONGS_TO {run_id: 'r1'}]->(d)", {"s": slug})
        yield conn


def _fm(entity_search_keys: list[str]) -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal",
        domain="ai-ml",
        source_type="blog",
        author=None,
        summary="Test.",
        key_themes=[],
        entity_search_keys=entity_search_keys,
    )


def _t2_slugs(snapshot):
    """Extract slugs from snapshot.pages (T2 entities live in pages — T1 would
    have score 3, T2 score 2 — without SUPPORTS edges in fixture, T1 is empty
    so all returned pages came from T2)."""
    return {p.slug for p in snapshot.pages}


# ---------- T2Mode.STRUCTURED three-state branch (D-90-8) ----------


def test_structured_state_a_no_frontmatter_falls_back_to_legacy(t2_graph):
    """State A: frontmatter=None (pre-Pass-1 source) → legacy regex catches
    `value-investing` in body."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="Long-form essay on value-investing as a discipline.",
        frontmatter=None,
        mode=T2Mode.STRUCTURED,
    )
    assert "value-investing" in _t2_slugs(snap)


def test_structured_state_b_non_empty_uses_structured_lookup(t2_graph):
    """State B: frontmatter.entity_search_keys non-empty → structured lookup.

    Body has no slug-mention but entity_search_keys explicitly seeds the slug."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="A diary entry with no concept slugs in it.",
        frontmatter=_fm(["compound-interest"]),
        mode=T2Mode.STRUCTURED,
    )
    assert "compound-interest" in _t2_slugs(snap)
    # The body slug should NOT be picked up — structured signal only
    assert "value-investing" not in _t2_slugs(snap)


def test_structured_state_c_empty_entity_search_keys_emits_empty_t2(t2_graph):
    """State C (D-90-8 HEADLINE): explicit `entity_search_keys=[]` honored as
    empty T2. Body contains `value-investing` but legacy regex is NOT invoked."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="Long-form essay on value-investing as a discipline.",
        frontmatter=_fm([]),
        mode=T2Mode.STRUCTURED,
    )
    assert _t2_slugs(snap) == set(), \
        "State C should honor LLM's empty signal; legacy fallback would " \
        "have produced {'value-investing'}"


# ---------- T2Mode.LAYERED ----------


def test_layered_state_c_still_runs_legacy_regex(t2_graph):
    """LAYERED deliberately diverges from STRUCTURED on State C — runs legacy
    regex even with explicit `entity_search_keys=[]` (NW-9 comparison axis)."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="Long-form essay on value-investing as a discipline.",
        frontmatter=_fm([]),
        mode=T2Mode.LAYERED,
    )
    assert "value-investing" in _t2_slugs(snap)


def test_layered_state_b_unions_structured_and_legacy(t2_graph):
    """LAYERED with State B + body containing different slug → both T2 hits."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="Long-form essay on value-investing.",
        frontmatter=_fm(["compound-interest"]),
        mode=T2Mode.LAYERED,
    )
    slugs = _t2_slugs(snap)
    assert "value-investing" in slugs  # from legacy regex on body
    assert "compound-interest" in slugs  # from entity_search_keys


# ---------- T2Mode.LEGACY ----------


def test_legacy_ignores_frontmatter_entirely(t2_graph):
    """LEGACY mode: behaves identically to pre-rewrite code; frontmatter unused."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="Long-form essay on value-investing.",
        frontmatter=_fm(["compound-interest"]),  # ignored
        mode=T2Mode.LEGACY,
    )
    slugs = _t2_slugs(snap)
    assert "value-investing" in slugs
    assert "compound-interest" not in slugs


# ---------- Default mode (D-90-1: STRUCTURED) ----------


def test_default_mode_is_structured(t2_graph):
    """Caller omitting `mode` gets STRUCTURED by default."""
    snap = build_context_snapshot(
        t2_graph,
        source_id="src-1",
        source_text="Long-form essay on value-investing.",
        frontmatter=_fm([]),  # State C
    )
    # Default STRUCTURED honors empty signal — should be empty T2.
    assert _t2_slugs(snap) == set()


