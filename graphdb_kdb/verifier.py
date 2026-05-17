"""Replay-to-temp structural equality verifier (D50 Phase G).

Proves graph integrity by replaying journals into a temp Kuzu, then
structurally diffing temp (expected) vs live (actual). Two layers:

  Layer 1 — source-state preflight: cheap manifest.sources{} vs graph
            Source nodes check. Catches obvious drift without a full rebuild.

  Layer 2 — replay structural diff: rebuild() into a temp Kuzu, then
            diff ALL graph state (entities, sources, links, supports) between
            the replay graph (expected) and the live graph (actual).

Divergence classes:
  - missing_in_live   — present in replay, absent in live graph
  - missing_in_replay — present in live, absent in replay
  - attribute_mismatch — both present but tracked fields differ

Each divergence carries a `source` tag: 'source_state_preflight' or
'replay_structural_diff', so consumers can separate cheap-check results
from the authoritative replay proof.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import kuzu

from graphdb_kdb.graphdb import GraphDB


# ---------- result types ----------

@dataclass(frozen=True)
class Divergence:
    kind: str       # 'missing_in_live' | 'missing_in_replay' | 'attribute_mismatch'
    category: str   # 'entity' | 'source' | 'links_to' | 'supports'
    key: str        # slug | source_id | 'a→b' | 'sid→slug'
    source: str     # 'source_state_preflight' | 'replay_structural_diff'
    field: str | None = None
    expected_value: Any = None
    actual_value: Any = None


@dataclass
class VerifyResult:
    ok: bool
    rebuild_failed: bool = False
    rebuild_error: str | None = None
    divergences: list[Divergence] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


# ---------- attribute maps ----------

_SOURCE_DIRECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("status", "status"),
    ("compile_state", "ingest_state"),
    ("compile_count", "ingest_count"),
    ("hash", "hash"),
    ("file_type", "file_type"),
    ("size_bytes", "size_bytes"),
    ("last_run_id", "last_run_id"),
)

_ENTITY_DIRECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("page_type", "page_type"),
    ("status", "status"),
    ("confidence", "confidence"),
    ("last_run_id", "last_run_id"),
)


# ---------- graph state loaders ----------

def _graph_entities(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    r = conn.execute(
        "MATCH (e:Entity) "
        "RETURN e.slug, e.page_type, e.status, e.confidence, e.last_run_id"
    )
    out: dict[str, dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[row[0]] = {
            "slug": row[0],
            "page_type": row[1],
            "status": row[2],
            "confidence": row[3],
            "last_run_id": row[4],
        }
    return out


def _graph_sources(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    r = conn.execute(
        "MATCH (s:Source) "
        "RETURN s.source_id, s.status, s.ingest_state, s.ingest_count, "
        "       s.hash, s.file_type, s.size_bytes, s.last_run_id"
    )
    out: dict[str, dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[row[0]] = {
            "source_id": row[0],
            "status": row[1],
            "ingest_state": row[2],
            "ingest_count": int(row[3]) if row[3] is not None else 0,
            "hash": row[4],
            "file_type": row[5],
            "size_bytes": int(row[6]) if row[6] is not None else 0,
            "last_run_id": row[7],
        }
    return out


def _graph_links(conn: kuzu.Connection) -> set[tuple[str, str]]:
    r = conn.execute("MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug")
    out: set[tuple[str, str]] = set()
    while r.has_next():
        row = r.get_next()
        out.add((row[0], row[1]))
    return out


def _graph_supports(conn: kuzu.Connection) -> set[tuple[str, str]]:
    r = conn.execute(
        "MATCH (s:Source)-[:SUPPORTS]->(e:Entity) RETURN s.source_id, e.slug"
    )
    out: set[tuple[str, str]] = set()
    while r.has_next():
        row = r.get_next()
        out.add((row[0], row[1]))
    return out


# ---------- manifest projection (source-state preflight only) ----------

def _manifest_sources(manifest: dict) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for sid, src in (manifest.get("sources") or {}).items():
        out[sid] = {
            "source_id": sid,
            "status": src.get("status"),
            "compile_state": src.get("compile_state"),
            "compile_count": int(src.get("compile_count") or 0),
            "hash": src.get("hash"),
            "file_type": src.get("file_type"),
            "size_bytes": int(src.get("size_bytes") or 0),
            "last_run_id": src.get("last_run_id"),
        }
    return out


# ---------- diff helpers ----------

def _diff_attrs(
    *,
    category: str,
    key: str,
    source: str,
    expected_row: dict[str, Any],
    actual_row: dict[str, Any],
    fields: tuple[tuple[str, str], ...],
) -> list[Divergence]:
    out: list[Divergence] = []
    for efield, afield in fields:
        ev = expected_row.get(efield)
        av = actual_row.get(afield)
        if ev != av:
            out.append(Divergence(
                kind="attribute_mismatch",
                category=category,
                key=key,
                source=source,
                field=efield,
                expected_value=ev,
                actual_value=av,
            ))
    return out


def _diff_sources_preflight(
    manifest_sources: dict[str, dict],
    live_sources: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "source_state_preflight"
    for sid in sorted(manifest_sources.keys() - live_sources.keys()):
        divs.append(Divergence(kind="missing_in_live", category="source", key=sid, source=src))
    for sid in sorted(live_sources.keys() - manifest_sources.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="source", key=sid, source=src))
    for sid in sorted(manifest_sources.keys() & live_sources.keys()):
        divs.extend(_diff_attrs(
            category="source",
            key=sid,
            source=src,
            expected_row=manifest_sources[sid],
            actual_row=live_sources[sid],
            fields=_SOURCE_DIRECT_FIELDS,
        ))
    return divs


def _diff_entities(
    expected: dict[str, dict],
    actual: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for slug in sorted(expected.keys() - actual.keys()):
        divs.append(Divergence(kind="missing_in_live", category="entity", key=slug, source=src))
    for slug in sorted(actual.keys() - expected.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="entity", key=slug, source=src))
    for slug in sorted(expected.keys() & actual.keys()):
        divs.extend(_diff_attrs(
            category="entity",
            key=slug,
            source=src,
            expected_row=expected[slug],
            actual_row=actual[slug],
            fields=_ENTITY_DIRECT_FIELDS,
        ))
    return divs


def _diff_sources_replay(
    expected: dict[str, dict],
    actual: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for sid in sorted(expected.keys() - actual.keys()):
        divs.append(Divergence(kind="missing_in_live", category="source", key=sid, source=src))
    for sid in sorted(actual.keys() - expected.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="source", key=sid, source=src))
    for sid in sorted(expected.keys() & actual.keys()):
        divs.extend(_diff_attrs(
            category="source",
            key=sid,
            source=src,
            expected_row=expected[sid],
            actual_row=actual[sid],
            fields=(("ingest_state", "ingest_state"),
                    ("ingest_count", "ingest_count"),
                    ("hash", "hash"),
                    ("file_type", "file_type"),
                    ("size_bytes", "size_bytes"),
                    ("status", "status"),
                    ("last_run_id", "last_run_id")),
        ))
    return divs


def _diff_edge_set(
    *,
    category: str,
    expected_set: set[tuple[str, str]],
    actual_set: set[tuple[str, str]],
    arrow: str = "→",
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for a, b in sorted(expected_set - actual_set):
        divs.append(Divergence(kind="missing_in_live", category=category, key=f"{a}{arrow}{b}", source=src))
    for a, b in sorted(actual_set - expected_set):
        divs.append(Divergence(kind="missing_in_replay", category=category, key=f"{a}{arrow}{b}", source=src))
    return divs


# ---------- public entry points ----------

def verify_source_state(
    live_conn: kuzu.Connection,
    manifest: dict,
) -> list[Divergence]:
    """Layer 1: source-state preflight. Cheap comparison of manifest sources{}
    against live graph Source nodes. Returns divergences tagged with
    source='source_state_preflight'."""
    m_sources = _manifest_sources(manifest)
    l_sources = _graph_sources(live_conn)
    return _diff_sources_preflight(m_sources, l_sources)


def verify(
    live_conn: kuzu.Connection,
    *,
    journals_dir: Path,
    manifest: dict | None = None,
) -> VerifyResult:
    """Full replay verification: rebuild temp graph from journals, diff against live.

    Args:
        live_conn: Connection to the live Kuzu graph.
        journals_dir: Directory containing run journals (state/runs/).
        manifest: Optional manifest dict for source-state preflight.
            If None, preflight is skipped.

    Returns:
        VerifyResult. If rebuild fails, ok=False + rebuild_failed=True + no
        divergences (partial replay is not compared).
    """
    from graphdb_kdb.adapters.obsidian_runs import ObsidianRunsAdapter
    from graphdb_kdb.rebuilder import rebuild

    all_divs: list[Divergence] = []

    # Layer 1: source-state preflight (if manifest provided)
    if manifest is not None:
        all_divs.extend(verify_source_state(live_conn, manifest))

    # Layer 2: replay structural diff
    adapter = ObsidianRunsAdapter()

    with tempfile.TemporaryDirectory() as td:
        temp_graph_dir = Path(td) / "graph"

        rebuild_result = rebuild(
            graph_dir=temp_graph_dir,
            adapter=adapter,
            journals_dir=journals_dir,
            confirm=False,
        )

        if not rebuild_result.ok:
            failed_runs = [
                o for o in rebuild_result.outcomes if o.state == "failed"
            ]
            error_msg = "; ".join(
                f"{o.run_id}: {o.error}" for o in failed_runs
            )
            return VerifyResult(
                ok=False,
                rebuild_failed=True,
                rebuild_error=error_msg,
                divergences=all_divs,
                counts={"rebuild_replayed": rebuild_result.replayed,
                        "rebuild_skipped": rebuild_result.skipped,
                        "rebuild_failed": rebuild_result.failed},
            )

        with GraphDB(temp_graph_dir) as replay_gdb:
            r_entities = _graph_entities(replay_gdb.conn)
            r_sources = _graph_sources(replay_gdb.conn)
            r_links = _graph_links(replay_gdb.conn)
            r_supports = _graph_supports(replay_gdb.conn)

    l_entities = _graph_entities(live_conn)
    l_sources = _graph_sources(live_conn)
    l_links = _graph_links(live_conn)
    l_supports = _graph_supports(live_conn)

    all_divs.extend(_diff_entities(r_entities, l_entities))
    all_divs.extend(_diff_sources_replay(r_sources, l_sources))
    all_divs.extend(_diff_edge_set(
        category="links_to", expected_set=r_links, actual_set=l_links,
    ))
    all_divs.extend(_diff_edge_set(
        category="supports", expected_set=r_supports, actual_set=l_supports,
    ))

    counts = {
        "entities_checked": len(r_entities.keys() | l_entities.keys()),
        "sources_checked": len(r_sources.keys() | l_sources.keys()),
        "links_checked": len(r_links | l_links),
        "supports_checked": len(r_supports | l_supports),
        "missing_in_live": sum(1 for d in all_divs if d.kind == "missing_in_live"),
        "missing_in_replay": sum(1 for d in all_divs if d.kind == "missing_in_replay"),
        "attribute_mismatch": sum(1 for d in all_divs if d.kind == "attribute_mismatch"),
        "replay_replayed": rebuild_result.replayed,
        "replay_skipped": rebuild_result.skipped,
    }

    return VerifyResult(ok=not all_divs, divergences=all_divs, counts=counts)
