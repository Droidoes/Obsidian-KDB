"""Tests for the Task #90 v0.2 alias-aware resolvers.

Covers BOTH implementations (simple 2-query default per D-90-9 + Codex-tested
batch escape hatch). Per Grok F-4 / D-90-9 contract: both MUST return functionally
identical {raw_slug → canonical_slug} mappings on the shared fixture graph
spanning all §3.1 reachability paths + B-2 inactive-target + Qwen Probe-2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kdb_graph.graphdb import GraphDB
from compiler.context_loader import (
    _resolve_to_canonical_slugs,
    _resolve_to_canonical_slugs_batch,
)


# ---------- Fixture: graph spanning all §3.1 reachability paths ----------

@pytest.fixture
def resolver_graph(tmp_path: Path):
    """Fixture graph covering:
    - Path 1 direct PK hit (active, no canonical_id)
    - Path 2 canonical_id with ACTIVE target (B-2 fix verification)
    - Path 2 canonical_id with INACTIVE target (B-2 regression — must return absent)
    - Path 3 ALIAS_OF with active canonical
    - Path 3 ALIAS_OF with inactive canonical
    - Qwen Probe-2: entity with BOTH canonical_id and divergent ALIAS_OF
    - Inactive entity (Path 1 inactive)
    - Nonexistent slug (handled by absent-from-dict)
    """
    with GraphDB(tmp_path / "resolver-graph") as g:
        conn = g.conn

        def add_entity(slug: str, status: str = "active", canonical_id: str | None = None):
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: $st, confidence: 'medium', canonical_id: $ci, "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug, "st": status, "ci": canonical_id},
            )

        def add_alias_of(alias: str, canonical: str):
            conn.execute(
                """
                MATCH (a:Entity {slug: $alias}), (c:Entity {slug: $canonical})
                CREATE (a)-[:ALIAS_OF {run_id: 'r1', created_at: '2026-01-01',
                                       algorithm: 'manual'}]->(c)
                """,
                {"alias": alias, "canonical": canonical},
            )

        # Path 1 direct PK hits
        add_entity("value-investing")
        add_entity("warren-buffett")

        # Path 2 — canonical_id with active target
        add_entity("wb", canonical_id="warren-buffett")

        # Path 3 — ALIAS_OF with active canonical (no canonical_id on alias row)
        add_entity("buffett")
        add_alias_of("buffett", "warren-buffett")

        # B-2 — canonical_id with INACTIVE target
        add_entity("deprecated", status="inactive")
        add_entity("old-name", canonical_id="deprecated")

        # Qwen Probe-2 — entity with both canonical_id AND outgoing ALIAS_OF
        add_entity("target-a")
        add_entity("target-b")
        add_entity("ambiguous", canonical_id="target-a")
        add_alias_of("ambiguous", "target-b")

        # Path 1 inactive (entity exists but inactive — no canonical_id, no alias)
        add_entity("inactive-only", status="inactive")

        # Path 3 inactive — alias has ALIAS_OF to an inactive canonical
        add_entity("alias-to-dead")
        add_entity("dead-target", status="inactive")
        add_alias_of("alias-to-dead", "dead-target")

        yield conn


# ---------- Parity test: simple ≡ batch on every probe (D-90-9 + Grok F-4) ----------

PARITY_PROBES = [
    # (raw_slugs_input, expected_resolved_mapping, label)
    (["value-investing"], {"value-investing": "value-investing"}, "Path 1 direct PK"),
    (["wb"], {"wb": "warren-buffett"}, "Path 2 canonical_id active target"),
    (["buffett"], {"buffett": "warren-buffett"}, "Path 3 ALIAS_OF"),
    (["old-name"], {}, "B-2: canonical_id target inactive — must NOT leak"),
    (["ambiguous"], {"ambiguous": "target-a"}, "Qwen Probe-2: canonical_id wins, ALIAS_OF unreached"),
    (["inactive-only"], {}, "Path 1 inactive entity"),
    (["alias-to-dead"], {}, "Path 3 with inactive canonical"),
    (["nonexistent-slug"], {}, "Nonexistent slug"),
    ([], {}, "Empty input"),
    (
        ["", "  ", "value-investing"],
        {"value-investing": "value-investing"},
        "Defensive strip + drop-empty (Qwen O-2)",
    ),
    (
        ["value-investing", "value-investing"],
        {"value-investing": "value-investing"},
        "Duplicate raw keys",
    ),
    (
        ["value-investing", "buffett", "wb", "old-name", "nonexistent-slug"],
        {
            "value-investing": "value-investing",
            "buffett": "warren-buffett",
            "wb": "warren-buffett",
            # old-name absent (B-2 inactive target)
            # nonexistent-slug absent
        },
        "Mixed valid + invalid + alias-paths in one batch",
    ),
]


@pytest.mark.parametrize(
    "raw_slugs,expected,label",
    PARITY_PROBES,
    ids=[probe[2] for probe in PARITY_PROBES],
)
def test_resolver_parity_simple_vs_batch(resolver_graph, raw_slugs, expected, label):
    """Both resolvers MUST produce identical mappings (D-90-9 contract)."""
    simple_result = _resolve_to_canonical_slugs(resolver_graph, raw_slugs)
    batch_result = _resolve_to_canonical_slugs_batch(resolver_graph, raw_slugs)
    assert simple_result == expected, f"simple resolver wrong for {label!r}"
    assert batch_result == expected, f"batch resolver wrong for {label!r}"
    assert simple_result == batch_result, f"parity violated for {label!r}"


# ---------- Direct resolver unit tests (extra coverage beyond parity) ----------


def test_simple_resolver_b2_inactive_canonical_target(resolver_graph):
    """B-2 regression: canonical_id target.status='inactive' must NOT resolve."""
    result = _resolve_to_canonical_slugs(resolver_graph, ["old-name"])
    assert result == {}


def test_simple_resolver_alias_of_inactive_target(resolver_graph):
    """Path 3 with inactive canonical entity — must NOT resolve."""
    result = _resolve_to_canonical_slugs(resolver_graph, ["alias-to-dead"])
    assert result == {}


def test_simple_resolver_qwen_probe_2_canonical_id_wins(resolver_graph):
    """Qwen Probe-2: entity with both canonical_id AND outgoing ALIAS_OF.

    Per §3.1 order: direct PK fails (entity exists but canonical_id IS NOT NULL),
    canonical_id check succeeds first → returns target-a. ALIAS_OF (→target-b) is
    never traversed.
    """
    result = _resolve_to_canonical_slugs(resolver_graph, ["ambiguous"])
    assert result == {"ambiguous": "target-a"}


def test_simple_resolver_empty_and_whitespace_drop(resolver_graph):
    """Qwen O-2: strip whitespace; drop empty/whitespace-only entries."""
    assert _resolve_to_canonical_slugs(resolver_graph, []) == {}
    assert _resolve_to_canonical_slugs(resolver_graph, ["", "  ", "\t"]) == {}
    # Trimmed-and-valid entry preserved
    assert _resolve_to_canonical_slugs(
        resolver_graph, ["  value-investing  "]
    ) == {"value-investing": "value-investing"}


def test_simple_resolver_duplicate_inputs_dedup(resolver_graph):
    """Duplicate raw keys → dict semantics dedup naturally."""
    result = _resolve_to_canonical_slugs(
        resolver_graph,
        ["value-investing", "value-investing", "value-investing"],
    )
    assert result == {"value-investing": "value-investing"}


def test_batch_resolver_b2_inactive_canonical_target(resolver_graph):
    """B-2 regression on batch resolver."""
    result = _resolve_to_canonical_slugs_batch(resolver_graph, ["old-name"])
    assert result == {}


def test_batch_resolver_qwen_probe_2(resolver_graph):
    """Qwen Probe-2 on batch resolver."""
    result = _resolve_to_canonical_slugs_batch(resolver_graph, ["ambiguous"])
    assert result == {"ambiguous": "target-a"}
