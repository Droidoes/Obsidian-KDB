"""Gate-3 (Task #115 Phase 3) pre/post comparison helper.

Rebuilds the PINNED mixed-journal corpus (fixtures/gate3_mixed_corpus/) and
dumps a normalized, deterministic full-graph artifact: every node, every
edge, every property EXCEPT volatile wall-clock timestamps (created_at /
updated_at / *_seen_at / last_ingested_at), which differ on every rebuild.

Used twice:
  1. At the Gate-2 HEAD (pre-deprecation) to generate
     `pre_confidence_removal_artifact.json` — via `python -m
     kdb_graph.tests.gate3_dump` (the exact rebuild command is
     `rebuild_corpus()` below; the Gate-3 test pins both).
  2. By the Gate-3 test, which rebuilds the SAME corpus and diffs with ONLY
     Entity.confidence excluded — every other node/edge/property must be
     identical (blueprint Phase 3, Gate 3).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import kuzu

from kdb_graph.adapters.obsidian_runs import ObsidianRunsAdapter
from kdb_graph.rebuilder import rebuild

CORPUS_DIR = Path(__file__).parent / "fixtures" / "gate3_mixed_corpus"
ARTIFACT_PATH = CORPUS_DIR / "pre_confidence_removal_artifact.json"


def rebuild_corpus(graph_dir: Path):
    """The exact pinned Gate-3 rebuild command."""
    return rebuild(
        graph_dir=graph_dir,
        adapter=ObsidianRunsAdapter(),
        journals_dir=CORPUS_DIR / "runs",
        confirm=False,
    )


def _rows(conn: kuzu.Connection, query: str) -> list[list]:
    r = conn.execute(query)
    out = []
    while r.has_next():
        out.append(list(r.get_next()))
    return out


def dump_normalized(conn: kuzu.Connection) -> dict:
    """Full-graph dump, deterministic modulo wall-clock timestamps (excluded)."""
    entities = [
        {
            "slug": row[0], "title": row[1], "page_type": row[2],
            "status": row[3], "confidence": row[4],
            "canonical_id": row[5],
            "first_run_id": row[6], "last_run_id": row[7],
        }
        for row in _rows(
            conn,
            "MATCH (e:Entity) RETURN e.slug, e.title, e.page_type, e.status, "
            "e.confidence, e.canonical_id, e.first_run_id, e.last_run_id "
            "ORDER BY e.slug",
        )
    ]
    sources = [
        {
            "source_id": row[0], "source_type": row[1],
            "canonical_path": row[2], "status": row[3], "file_type": row[4],
            "hash": row[5], "size_bytes": row[6],
            "ingest_state": row[7], "ingest_count": row[8],
            "last_run_id": row[9], "moved_to": row[10],
            "summary": row[11], "author": row[12], "domain": row[13],
        }
        for row in _rows(
            conn,
            "MATCH (s:Source) RETURN s.source_id, s.source_type, "
            "s.canonical_path, s.status, s.file_type, s.hash, s.size_bytes, "
            "s.ingest_state, s.ingest_count, s.last_run_id, s.moved_to, "
            "s.summary, s.author, s.domain ORDER BY s.source_id",
        )
    ]
    domains = [
        {"name": row[0], "first_run_id": row[1]}
        for row in _rows(
            conn, "MATCH (d:Domain) RETURN d.name, d.first_run_id ORDER BY d.name"
        )
    ]
    links_to = [
        {"from": row[0], "to": row[1], "run_id": row[2]}
        for row in _rows(
            conn,
            "MATCH (a:Entity)-[r:LINKS_TO]->(b:Entity) "
            "RETURN a.slug, b.slug, r.run_id ORDER BY a.slug, b.slug",
        )
    ]
    supports = [
        {"from": row[0], "to": row[1], "role": row[2],
         "hash_at_time": row[3], "run_id": row[4]}
        for row in _rows(
            conn,
            "MATCH (s:Source)-[r:SUPPORTS]->(e:Entity) "
            "RETURN s.source_id, e.slug, r.role, r.hash_at_time, r.run_id "
            "ORDER BY s.source_id, e.slug",
        )
    ]
    alias_of = [
        {"from": row[0], "to": row[1], "run_id": row[2], "algorithm": row[3]}
        for row in _rows(
            conn,
            "MATCH (a:Entity)-[r:ALIAS_OF]->(b:Entity) "
            "RETURN a.slug, b.slug, r.run_id, r.algorithm ORDER BY a.slug",
        )
    ]
    belongs_to = [
        {"from": row[0], "to": row[1], "run_id": row[2], "support_count": row[3]}
        for row in _rows(
            conn,
            "MATCH (e:Entity)-[r:BELONGS_TO]->(d:Domain) "
            "RETURN e.slug, d.name, r.run_id, r.support_count "
            "ORDER BY e.slug, d.name",
        )
    ]
    # --- Claim tier + schema metadata (Codex Gate-3 F3) ---
    # The corpus leaves these EMPTY by design — encoding the empty sections
    # is precisely what catches accidental Claim-tier creation/mutation by
    # the deprecation diff (Claim confidence is PROTECTED, never excluded).
    schema_meta = [
        {"key": row[0], "value": row[1]}
        for row in _rows(
            conn, "MATCH (m:_SchemaMeta) RETURN m.key, m.value ORDER BY m.key"
        )
    ]
    claims = [
        {
            "claim_id": row[0], "claim_family_id": row[1],
            "subject_slug": row[2], "predicate_class_canonical": row[3],
            "predicate_class_raw": row[4], "predicate_scope_slugs": row[5],
            "object_slugs": row[6], "polarity": row[7], "modality": row[8],
            "condition_text": row[9], "assertion_text": row[10],
            "confidence": row[11], "confidence_spread": row[12],
            "state": row[13], "version": row[14],
        }
        for row in _rows(
            conn,
            "MATCH (c:Claim) RETURN c.claim_id, c.claim_family_id, "
            "c.subject_slug, c.predicate_class_canonical, "
            "c.predicate_class_raw, c.predicate_scope_slugs, c.object_slugs, "
            "c.polarity, c.modality, c.condition_text, c.assertion_text, "
            "c.confidence, c.confidence_spread, c.state, c.version "
            "ORDER BY c.claim_id",
        )
    ]
    evidences = [
        {"from": row[0], "to": row[1], "quoted_text": row[2],
         "score": row[3], "provenance_type": row[4], "run_id": row[5]}
        for row in _rows(
            conn,
            "MATCH (s:Source)-[r:EVIDENCES]->(c:Claim) "
            "RETURN s.source_id, c.claim_id, r.quoted_text, r.score, "
            "r.provenance_type, r.run_id ORDER BY s.source_id, c.claim_id",
        )
    ]
    about = [
        {"from": row[0], "to": row[1], "run_id": row[2]}
        for row in _rows(
            conn,
            "MATCH (c:Claim)-[r:ABOUT]->(e:Entity) "
            "RETURN c.claim_id, e.slug, r.run_id ORDER BY c.claim_id, e.slug",
        )
    ]
    claim_rels: dict[str, list] = {}
    for rel, extra_prop in (("SUPERSEDES", None), ("CONTRADICTS", "contradiction_kind"),
                            ("QUALIFIES", None)):
        extra_col = f", r.{extra_prop}" if extra_prop else ""
        rows = _rows(
            conn,
            f"MATCH (a:Claim)-[r:{rel}]->(b:Claim) "
            f"RETURN a.claim_id, b.claim_id, r.run_id{extra_col} "
            f"ORDER BY a.claim_id, b.claim_id",
        )
        entries = []
        for row in rows:
            entry = {"from": row[0], "to": row[1], "run_id": row[2]}
            if extra_prop:
                entry[extra_prop] = row[3]
            entries.append(entry)
        claim_rels[rel.lower()] = entries
    return {
        "schema_meta": schema_meta,
        "entities": entities,
        "sources": sources,
        "domains": domains,
        "claims": claims,
        "links_to": links_to,
        "supports": supports,
        "alias_of": alias_of,
        "belongs_to": belongs_to,
        "evidences": evidences,
        "about": about,
        **claim_rels,
    }


def main() -> None:
    from kdb_graph.graphdb import GraphDB

    with tempfile.TemporaryDirectory() as tmp:
        graph_dir = Path(tmp) / "graph"
        result = rebuild_corpus(graph_dir)
        assert result.failed == 0 and result.replayed == 2, result.outcomes
        with GraphDB(graph_dir) as gdb:
            artifact = dump_normalized(gdb.conn)
    ARTIFACT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
