"""#115 Phase 3, Gate 3 — executable pre/post comparison for the Entity
confidence logical deprecation (D-115-12).

The pinned mixed-journal corpus (`fixtures/gate3_mixed_corpus/runs/`) was
rebuilt AT THE GATE-2 HEAD and the normalized full-graph artifact committed
as `pre_confidence_removal_artifact.json`. This test rebuilds the SAME
corpus post-deprecation and diffs with ONLY Entity.confidence excluded —
every node, edge, and other property must be identical (blueprint Phase 3,
Gate 3).

Artifact regeneration (Gate-2 code ONLY — never regenerate post-deprecation):
    .venv/bin/python -m kdb_graph.tests.gate3_dump
"""
from __future__ import annotations

import json
from pathlib import Path

from kdb_graph.graphdb import GraphDB
from kdb_graph.tests.gate3_dump import (
    ARTIFACT_PATH,
    dump_normalized,
    rebuild_corpus,
)


def _without_entity_confidence(artifact: dict) -> dict:
    """Strip ONLY the Entity.confidence key; everything else is compared."""
    out = dict(artifact)
    out["entities"] = [
        {k: v for k, v in e.items() if k != "confidence"}
        for e in artifact["entities"]
    ]
    return out


def test_gate3_rebuild_matches_gate2_artifact_except_confidence(graph_dir):
    pre = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))

    result = rebuild_corpus(graph_dir)
    assert result.failed == 0 and result.replayed == 2, result.outcomes
    with GraphDB(graph_dir) as gdb:
        post = dump_normalized(gdb.conn)

    # Sanity: the pre-artifact really pins the OLD behavior (confidence
    # present and varied), and the new rebuild really omits it (dead column
    # never written → NULL on every row).
    pre_confs = {e["slug"]: e["confidence"] for e in pre["entities"]}
    assert pre_confs["summary-legacy"] == "high"
    assert pre_confs["alpha"] == "low"
    assert pre_confs["alpha-alias"] == ""
    post_confs = {e["slug"]: e["confidence"] for e in post["entities"]}
    assert set(post_confs.values()) == {None}

    # THE Gate-3 invariant: identical modulo Entity.confidence.
    assert _without_entity_confidence(post) == _without_entity_confidence(pre)


def test_gate3_pre_artifact_is_from_gate2_corpus():
    """Guard against accidental artifact regeneration post-deprecation:
    the committed artifact MUST contain non-null confidence values (the
    Gate-2 writer still emitted them)."""
    pre = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    confs = [e["confidence"] for e in pre["entities"]]
    assert any(c not in (None, "") for c in confs), (
        "pre-artifact lost its confidence values — was it regenerated "
        "with post-deprecation code?"
    )


def test_dump_normalized_includes_contradiction_kind(graph_dir):
    """Codex Gate-3 round-2 R2-F1: the full-graph normalizer must retain
    the nonvolatile CONTRADICTS.contradiction_kind property (Claim tier is
    compared property-for-property, not just endpoints)."""
    with GraphDB(graph_dir) as gdb:
        gdb.conn.execute("CREATE (c:Claim {claim_id: 'c1'})")
        gdb.conn.execute("CREATE (c:Claim {claim_id: 'c2'})")
        gdb.conn.execute(
            "MATCH (a:Claim {claim_id: 'c1'}), (b:Claim {claim_id: 'c2'}) "
            "CREATE (a)-[r:CONTRADICTS {contradiction_kind: 'polarity_flip', "
            "run_id: 'r', created_at: 't'}]->(b)"
        )
        dump = dump_normalized(gdb.conn)
    assert dump["contradicts"] == [
        {"from": "c1", "to": "c2", "run_id": "r",
         "contradiction_kind": "polarity_flip"}
    ]
    # And the populated Claims themselves appear in the claims section.
    assert {c["claim_id"] for c in dump["claims"]} == {"c1", "c2"}
