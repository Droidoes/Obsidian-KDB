"""Manifest ↔ Kuzu cross-check (#63.5).

Per blueprint §8.1: walks `manifest.json` and confirms every (page, edge,
source, support) is present in Kuzu with matching attributes. Reports
three classes of divergence:

  - missing_in_kuzu      — present in manifest, absent in graph
  - missing_in_manifest  — present in graph, absent in manifest
  - attribute_mismatch   — both present but differ on a tracked field

Per L4 (blueprint §13.2): the verifier reports on **overlap only**.
Manifest-only fields (`stats`, `runs`, `settings`, top-level `orphans`,
`tombstones`) are intentionally not mirrored in the graph and are
skipped. Timestamps are also skipped: manifest pages carry mixed
UTC-`Z` and local-offset strings; the graph uses local-offset only
(per `feedback_local_time_everywhere`). Comparing as strings would
produce false positives on format drift, not real state divergence.

Tracked attribute set:
  - Entity: page_type, last_run_id, confidence, status (mapped from
            manifest's `orphan_candidate` bool)
  - Source: status, ingest_state, ingest_count, hash, file_type,
            size_bytes, last_run_id

Naming bridge (D-A1 + D-A2, 2026-05-14): the graph side renamed
`Page → Entity` and `compile_state/count/last_compiled_at →
ingest_state/count/last_ingested_at`. The manifest side retains
producer-side names (`pages.*`, `compile_state`, etc.) because
`manifest_update.py` is the producer's writer. The field-alias
tuples below (_PAGE_DIRECT_FIELDS, _SOURCE_DIRECT_FIELDS) map
(manifest_field_name, graph_field_name) explicitly so the verifier
bridges the two name spaces without false-positive divergences.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import kuzu


# ---------- result types ----------

@dataclass(frozen=True)
class Divergence:
    kind: str       # 'missing_in_kuzu' | 'missing_in_manifest' | 'attribute_mismatch'
    entity: str     # 'page' | 'source' | 'links_to' | 'supports'
    key: str        # slug | source_id | 'a→b' | 'sid→slug'
    field: str | None = None
    manifest_value: Any = None
    kuzu_value: Any = None


@dataclass
class VerifyResult:
    ok: bool
    divergences: list[Divergence] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


# ---------- attribute maps ----------

# (manifest_field_name, graph_field_name) pairs. Identical names = no rename;
# divergent names bridge producer-side terminology to graph-side terminology
# (D-A1 + D-A2 — see module docstring).
_PAGE_DIRECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("page_type", "page_type"),
    ("last_run_id", "last_run_id"),
    ("confidence", "confidence"),
)

_SOURCE_DIRECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("status", "status"),
    ("compile_state", "ingest_state"),       # D-A2: graph-side renamed
    ("compile_count", "ingest_count"),       # D-A2: graph-side renamed
    ("hash", "hash"),
    ("file_type", "file_type"),
    ("size_bytes", "size_bytes"),
    ("last_run_id", "last_run_id"),
)


# ---------- graph state loaders ----------

def _graph_entities(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    """Return entities keyed by slug, with graph-side field names."""
    r = conn.execute(
        """
        MATCH (e:Entity)
        RETURN e.slug, e.page_type, e.status, e.confidence,
               e.last_run_id
        """
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
    """Return sources keyed by source_id, with graph-side field names (ingest_*)."""
    r = conn.execute(
        """
        MATCH (s:Source)
        RETURN s.source_id, s.status, s.ingest_state, s.ingest_count,
               s.hash, s.file_type, s.size_bytes, s.last_run_id
        """
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


# ---------- manifest projection ----------

def _manifest_pages(manifest: dict) -> dict[str, dict[str, Any]]:
    """Project manifest pages dict to {slug: tracked-attrs-dict}.

    Keys here use manifest's producer-side names (page_type, status from
    orphan_candidate bool, etc.) — _diff_attrs() bridges to graph-side
    via the (manifest_field, graph_field) tuples.
    """
    out: dict[str, dict[str, Any]] = {}
    for page in (manifest.get("pages") or {}).values():
        slug = page.get("slug")
        if not slug:
            continue
        status = "orphan_candidate" if page.get("orphan_candidate") else "active"
        out[slug] = {
            "slug": slug,
            "page_type": page.get("page_type"),
            "status": status,
            "confidence": page.get("confidence"),
            "last_run_id": page.get("last_run_id"),
        }
    return out


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


def _manifest_links(manifest: dict) -> set[tuple[str, str]]:
    """Derive expected LINKS_TO edges from each page's outgoing_links."""
    out: set[tuple[str, str]] = set()
    for page in (manifest.get("pages") or {}).values():
        slug = page.get("slug")
        if not slug:
            continue
        for tgt in page.get("outgoing_links") or []:
            out.add((slug, tgt))
    return out


def _manifest_supports(manifest: dict) -> set[tuple[str, str]]:
    """Derive expected SUPPORTS edges from each page's source_refs."""
    out: set[tuple[str, str]] = set()
    for page in (manifest.get("pages") or {}).values():
        slug = page.get("slug")
        if not slug:
            continue
        for ref in page.get("source_refs") or []:
            sid = ref.get("source_id")
            if sid:
                out.add((sid, slug))
    return out


# ---------- diff helpers ----------

def _diff_attrs(
    *,
    entity: str,
    key: str,
    manifest_row: dict[str, Any],
    kuzu_row: dict[str, Any],
    fields: tuple[tuple[str, str], ...],
) -> list[Divergence]:
    out: list[Divergence] = []
    for mfield, kfield in fields:
        mv = manifest_row.get(mfield)
        kv = kuzu_row.get(kfield)
        if mv != kv:
            out.append(Divergence(
                kind="attribute_mismatch",
                entity=entity,
                key=key,
                field=mfield,
                manifest_value=mv,
                kuzu_value=kv,
            ))
    return out


def _diff_pages(
    manifest_pages: dict[str, dict],
    kuzu_pages: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    for slug in sorted(manifest_pages.keys() - kuzu_pages.keys()):
        divs.append(Divergence(kind="missing_in_kuzu", entity="page", key=slug))
    for slug in sorted(kuzu_pages.keys() - manifest_pages.keys()):
        divs.append(Divergence(kind="missing_in_manifest", entity="page", key=slug))
    # status is its own field; bundle into the same direct-fields sweep.
    fields = _PAGE_DIRECT_FIELDS + (("status", "status"),)
    for slug in sorted(manifest_pages.keys() & kuzu_pages.keys()):
        divs.extend(_diff_attrs(
            entity="page",
            key=slug,
            manifest_row=manifest_pages[slug],
            kuzu_row=kuzu_pages[slug],
            fields=fields,
        ))
    return divs


def _diff_sources(
    manifest_sources: dict[str, dict],
    kuzu_sources: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    for sid in sorted(manifest_sources.keys() - kuzu_sources.keys()):
        divs.append(Divergence(kind="missing_in_kuzu", entity="source", key=sid))
    for sid in sorted(kuzu_sources.keys() - manifest_sources.keys()):
        divs.append(Divergence(kind="missing_in_manifest", entity="source", key=sid))
    for sid in sorted(manifest_sources.keys() & kuzu_sources.keys()):
        divs.extend(_diff_attrs(
            entity="source",
            key=sid,
            manifest_row=manifest_sources[sid],
            kuzu_row=kuzu_sources[sid],
            fields=_SOURCE_DIRECT_FIELDS,
        ))
    return divs


def _diff_edge_set(
    *,
    entity: str,
    manifest_set: set[tuple[str, str]],
    kuzu_set: set[tuple[str, str]],
    arrow: str = "→",
) -> list[Divergence]:
    divs: list[Divergence] = []
    for a, b in sorted(manifest_set - kuzu_set):
        divs.append(Divergence(kind="missing_in_kuzu", entity=entity, key=f"{a}{arrow}{b}"))
    for a, b in sorted(kuzu_set - manifest_set):
        divs.append(Divergence(kind="missing_in_manifest", entity=entity, key=f"{a}{arrow}{b}"))
    return divs


# ---------- public entry points ----------

def verify(conn: kuzu.Connection, manifest: dict) -> VerifyResult:
    """Diff in-memory manifest dict against the Kuzu state behind `conn`."""
    m_pages = _manifest_pages(manifest)
    m_sources = _manifest_sources(manifest)
    m_links = _manifest_links(manifest)
    m_supports = _manifest_supports(manifest)

    k_pages = _graph_entities(conn)
    k_sources = _graph_sources(conn)
    k_links = _graph_links(conn)
    k_supports = _graph_supports(conn)

    divs: list[Divergence] = []
    divs.extend(_diff_pages(m_pages, k_pages))
    divs.extend(_diff_sources(m_sources, k_sources))
    divs.extend(_diff_edge_set(
        entity="links_to", manifest_set=m_links, kuzu_set=k_links,
    ))
    divs.extend(_diff_edge_set(
        entity="supports", manifest_set=m_supports, kuzu_set=k_supports,
    ))

    counts = {
        "pages_checked": len(m_pages | k_pages.keys()),
        "sources_checked": len(m_sources.keys() | k_sources.keys()),
        "links_checked": len(m_links | k_links),
        "supports_checked": len(m_supports | k_supports),
        "missing_in_kuzu": sum(1 for d in divs if d.kind == "missing_in_kuzu"),
        "missing_in_manifest": sum(1 for d in divs if d.kind == "missing_in_manifest"),
        "attribute_mismatch": sum(1 for d in divs if d.kind == "attribute_mismatch"),
    }
    return VerifyResult(ok=not divs, divergences=divs, counts=counts)


def verify_against_manifest(
    conn: kuzu.Connection,
    manifest_path: Path | str,
) -> VerifyResult:
    """Load manifest JSON from disk + delegate to `verify`."""
    path = Path(manifest_path)
    with path.open() as f:
        manifest = json.load(f)
    return verify(conn, manifest)
