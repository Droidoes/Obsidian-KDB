"""Snapshot/export — read-only JSONL dump of the graph for backup safety net.

#63.9 — belt-and-suspenders backup per D35. Writes plain-text JSONL files
into the OneDrive-synced vault, complementing the primary recovery path
(`graphdb-kdb rebuild` from per-run sidecars). Diffable, human-readable,
self-verifying via per-file sha256 + row counts in manifest.json.

v1 is write-only. A future `graphdb-kdb load-snapshot` would close the
recovery loop (Tier 2: journals AND Kuzu dir lost → restore from
snapshot). Out of scope for #63.9.

D34 invariant: this module reads ONLY from the Kuzu graph. No imports
from kdb_compiler.* — snapshot represents graph state, not producer state.

Atomicity: write into `<out_dir>.tmp.<uuid>/`, write data files first,
manifest.json last, then `os.rename` to `<out_dir>/`. If `<out_dir>`
already exists, fail loudly (don't overwrite).

Stable ordering within each file (lexical key sort inside each JSON line
+ total-ordering tuples on the SQL side) yields byte-diffable snapshots
across runs of an unchanged graph — the property that makes them useful
in OneDrive / git diffs.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import kuzu

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.schema import (
    NODE_TABLE_DDL,
    REL_TABLE_DDL,
    SCHEMA_META_DDL,
    SCHEMA_VERSION,
)

SNAPSHOT_FORMAT_VERSION = 4
# v1: original (entities/sources/links_to/supports + schema.cypher)
# v2 (#74.7): adds Entity.canonical_id + alias_of.jsonl
# v3 (#80): adds domain.jsonl + belongs_to.jsonl (Domain nodes + BELONGS_TO
#           edges from schema v2.1 / #76). Writer-only: snapshot.py has no
#           reader today, so format-version dispatch is a future load-snapshot
#           concern; v3 is purely additive (all v2 files still emitted).


@dataclass(frozen=True)
class SnapshotResult:
    out_dir: Path
    emitted_at: str
    schema_version: str
    counts: dict


def snapshot(graph_dir: Path, out_dir: Path) -> SnapshotResult:
    """Export the graph at `graph_dir` to `out_dir` as JSONL + manifest.

    Atomic: writes into a temp sibling dir, then renames. Raises
    `FileExistsError` if `out_dir` already exists (we never overwrite
    a prior snapshot).
    """
    graph_dir = Path(graph_dir)
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"snapshot dir already exists: {out_dir}")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir.parent / f"{out_dir.name}.tmp.{uuid.uuid4().hex[:12]}"
    tmp_dir.mkdir(parents=True, exist_ok=False)

    try:
        emitted_at = datetime.now().astimezone().isoformat()

        with GraphDB(graph_dir) as gdb:
            files_meta: dict[str, dict] = {}

            entities_path = tmp_dir / "entities.jsonl"
            files_meta["entities.jsonl"] = {
                "rows": _write_entities(gdb.conn, entities_path),
                "sha256": _sha256(entities_path),
            }

            sources_path = tmp_dir / "sources.jsonl"
            files_meta["sources.jsonl"] = {
                "rows": _write_sources(gdb.conn, sources_path),
                "sha256": _sha256(sources_path),
            }

            links_path = tmp_dir / "links_to.jsonl"
            files_meta["links_to.jsonl"] = {
                "rows": _write_links_to(gdb.conn, links_path),
                "sha256": _sha256(links_path),
            }

            supports_path = tmp_dir / "supports.jsonl"
            files_meta["supports.jsonl"] = {
                "rows": _write_supports(gdb.conn, supports_path),
                "sha256": _sha256(supports_path),
            }

            # #74.7 (format v2): ALIAS_OF edges serialized into their own
            # JSONL file. Pre-#74 graphs produce an empty file with rows=0
            # — back-compatible with existing snapshot consumers that
            # didn't know about aliases.
            alias_of_path = tmp_dir / "alias_of.jsonl"
            files_meta["alias_of.jsonl"] = {
                "rows": _write_alias_of(gdb.conn, alias_of_path),
                "sha256": _sha256(alias_of_path),
            }

            # #80 (format v3): Domain nodes + BELONGS_TO edges from schema
            # v2.1 (#76). Pre-#76 graphs produce empty files with rows=0
            # — additive bump, no breaking change to v2 file layout.
            domain_path = tmp_dir / "domain.jsonl"
            files_meta["domain.jsonl"] = {
                "rows": _write_domains(gdb.conn, domain_path),
                "sha256": _sha256(domain_path),
            }

            belongs_to_path = tmp_dir / "belongs_to.jsonl"
            files_meta["belongs_to.jsonl"] = {
                "rows": _write_belongs_to(gdb.conn, belongs_to_path),
                "sha256": _sha256(belongs_to_path),
            }

            # #83/#84 (format v4): Claim node + 5 Claim-layer rel tables.
            # Pre-#83/#84 graphs produce empty files with rows=0 — additive
            # bump, no breaking change to v3 file layout.
            claims_path = tmp_dir / "claims.jsonl"
            files_meta["claims.jsonl"] = {
                "rows": _write_claims(gdb.conn, claims_path),
                "sha256": _sha256(claims_path),
            }

            evidences_path = tmp_dir / "evidences.jsonl"
            files_meta["evidences.jsonl"] = {
                "rows": _write_evidences(gdb.conn, evidences_path),
                "sha256": _sha256(evidences_path),
            }

            about_path = tmp_dir / "about.jsonl"
            files_meta["about.jsonl"] = {
                "rows": _write_about(gdb.conn, about_path),
                "sha256": _sha256(about_path),
            }

            supersedes_path = tmp_dir / "supersedes.jsonl"
            files_meta["supersedes.jsonl"] = {
                "rows": _write_supersedes(gdb.conn, supersedes_path),
                "sha256": _sha256(supersedes_path),
            }

            contradicts_path = tmp_dir / "contradicts.jsonl"
            files_meta["contradicts.jsonl"] = {
                "rows": _write_contradicts(gdb.conn, contradicts_path),
                "sha256": _sha256(contradicts_path),
            }

            qualifies_path = tmp_dir / "qualifies.jsonl"
            files_meta["qualifies.jsonl"] = {
                "rows": _write_qualifies(gdb.conn, qualifies_path),
                "sha256": _sha256(qualifies_path),
            }

            schema_path = tmp_dir / "schema.cypher"
            schema_ddl_sha256 = _write_schema(schema_path)
            files_meta["schema.cypher"] = {"sha256": schema_ddl_sha256}

            counts = {
                "entities": files_meta["entities.jsonl"]["rows"],
                "sources": files_meta["sources.jsonl"]["rows"],
                "links_to": files_meta["links_to.jsonl"]["rows"],
                "supports": files_meta["supports.jsonl"]["rows"],
                "alias_of": files_meta["alias_of.jsonl"]["rows"],
                "domain": files_meta["domain.jsonl"]["rows"],
                "belongs_to": files_meta["belongs_to.jsonl"]["rows"],
                "claims": files_meta["claims.jsonl"]["rows"],
                "evidences": files_meta["evidences.jsonl"]["rows"],
                "about": files_meta["about.jsonl"]["rows"],
                "supersedes": files_meta["supersedes.jsonl"]["rows"],
                "contradicts": files_meta["contradicts.jsonl"]["rows"],
                "qualifies": files_meta["qualifies.jsonl"]["rows"],
            }

            manifest = {
                "schema_version": SCHEMA_VERSION,
                "schema_ddl_sha256": schema_ddl_sha256,
                "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
                "emitted_at": emitted_at,
                "graph_dir": str(graph_dir.resolve()),
                "counts": counts,
                "files": files_meta,
            }
            (tmp_dir / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

        os.rename(tmp_dir, out_dir)
    except BaseException:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    return SnapshotResult(
        out_dir=out_dir,
        emitted_at=emitted_at,
        schema_version=SCHEMA_VERSION,
        counts=counts,
    )


def update_latest_pointer(
    snapshots_root: Path,
    snapshot_dir_name: str,
    schema_version: str,
) -> Path:
    """Write/replace `<snapshots_root>/latest.json` pointing at the
    just-finished snapshot. Atomic via temp-file + `os.replace`. Stores
    a relative directory name, not a symlink (Windows/OneDrive-safe)."""
    snapshots_root = Path(snapshots_root)
    latest_path = snapshots_root / "latest.json"
    tmp_path = snapshots_root / f"latest.json.tmp.{uuid.uuid4().hex[:12]}"
    payload = {
        "snapshot_dir": snapshot_dir_name,
        "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
        "snapshot_id": snapshot_dir_name,
        "schema_version": schema_version,
    }
    tmp_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, latest_path)
    return latest_path


def default_snapshot_dirname() -> str:
    """Filename-safe snapshot id: `YYYY-MM-DDTHH-MM-SS_<TZ>`.

    Mirrors `kdb_compiler.run_context.run_id_from_timestamp` format
    without importing it (D34: no kdb_compiler imports inside
    graphdb_kdb/).
    """
    dt = datetime.now().astimezone()
    tz = dt.tzname() or "LOCAL"
    return dt.strftime("%Y-%m-%dT%H-%M-%S") + f"_{tz}"


# ---------- per-table writers ----------


def _write_entities(conn: kuzu.Connection, path: Path) -> int:
    """#74.7 (format v2): adds canonical_id (NULL ⇒ canonical, str ⇒ alias).

    Serialized as JSON null vs string. Pre-#74 snapshots always wrote
    every entity without this field; future load-snapshot consumers
    should default missing keys to None for format v1 compatibility.
    """
    query = """
    MATCH (e:Entity)
    RETURN e.slug, e.title, e.page_type, e.status, e.confidence,
           e.created_at, e.updated_at, e.first_run_id, e.last_run_id,
           e.canonical_id
    ORDER BY e.slug
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "slug": row[0],
                "title": row[1],
                "page_type": row[2],
                "status": row[3],
                "confidence": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "first_run_id": row[7],
                "last_run_id": row[8],
                "canonical_id": row[9],   # None ⇒ canonical; str ⇒ alias
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_sources(conn: kuzu.Connection, path: Path) -> int:
    query = """
    MATCH (s:Source)
    RETURN s.source_id, s.source_type, s.canonical_path, s.status,
           s.file_type, s.hash, s.size_bytes,
           s.first_seen_at, s.last_seen_at, s.last_ingested_at,
           s.ingest_state, s.ingest_count, s.last_run_id, s.moved_to
    ORDER BY s.source_id
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "source_id": row[0],
                "source_type": row[1],
                "canonical_path": row[2],
                "status": row[3],
                "file_type": row[4],
                "hash": row[5],
                "size_bytes": int(row[6]) if row[6] is not None else 0,
                "first_seen_at": row[7],
                "last_seen_at": row[8],
                "last_ingested_at": row[9],
                "ingest_state": row[10],
                "ingest_count": int(row[11]) if row[11] is not None else 0,
                "last_run_id": row[12],
                "moved_to": row[13],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_links_to(conn: kuzu.Connection, path: Path) -> int:
    query = """
    MATCH (a:Entity)-[r:LINKS_TO]->(b:Entity)
    RETURN a.slug, b.slug, r.run_id, r.created_at
    ORDER BY a.slug, b.slug, r.run_id, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "from_slug": row[0],
                "to_slug": row[1],
                "run_id": row[2],
                "created_at": row[3],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_supports(conn: kuzu.Connection, path: Path) -> int:
    query = """
    MATCH (s:Source)-[r:SUPPORTS]->(e:Entity)
    RETURN s.source_id, e.slug, r.run_id, r.role, r.hash_at_time, r.created_at
    ORDER BY s.source_id, e.slug, r.run_id, r.role, r.hash_at_time, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "source_id": row[0],
                "entity_slug": row[1],
                "run_id": row[2],
                "role": row[3],
                "hash_at_time": row[4],
                "created_at": row[5],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_alias_of(conn: kuzu.Connection, path: Path) -> int:
    """#74.7 (format v2): ALIAS_OF edges (Entity → Entity) with provenance.

    Pre-#74 graphs have no aliases ⇒ emit an empty file (rows=0). Future
    `load-snapshot` recreates aliases by upserting alias Entity rows with
    `canonical_id` (from entities.jsonl) plus an ALIAS_OF edge per row
    here — restores the full graph-side canonicalization state.
    """
    query = """
    MATCH (a:Entity)-[r:ALIAS_OF]->(c:Entity)
    RETURN a.slug, c.slug, r.run_id, r.algorithm, r.created_at
    ORDER BY a.slug, c.slug, r.run_id, r.algorithm, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "alias_slug": row[0],
                "canonical_slug": row[1],
                "run_id": row[2],
                "algorithm": row[3],
                "created_at": row[4],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_domains(conn: kuzu.Connection, path: Path) -> int:
    """#80 (format v3): Domain nodes (name-keyed) with creation provenance.

    Pre-#76 graphs have no Domain rows ⇒ emit an empty file (rows=0).
    Stable ordering: lexical by `name` (the primary key).
    """
    query = """
    MATCH (d:Domain)
    RETURN d.name, d.created_at, d.first_run_id
    ORDER BY d.name
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "name": row[0],
                "created_at": row[1],
                "first_run_id": row[2],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_belongs_to(conn: kuzu.Connection, path: Path) -> int:
    """#80 (format v3): BELONGS_TO edges (Entity → Domain) with sub_domain
    (nullable) + run_id + created_at provenance.

    Pre-#76 graphs have no edges ⇒ emit an empty file (rows=0). Total-order
    by `(entity_slug, domain_name, run_id, created_at)` so two snapshots
    of an unchanged graph are byte-identical.
    """
    query = """
    MATCH (e:Entity)-[r:BELONGS_TO]->(d:Domain)
    RETURN e.slug, d.name, r.sub_domain, r.run_id, r.created_at
    ORDER BY e.slug, d.name, r.run_id, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "entity_slug": row[0],
                "domain_name": row[1],
                "sub_domain": row[2],
                "run_id": row[3],
                "created_at": row[4],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_claims(conn: kuzu.Connection, path: Path) -> int:
    """#83/#84 (format v4): Claim nodes with full D-83/84-6 attribute set.

    Pre-#83/#84 graphs have no Claim rows ⇒ emit an empty file (rows=0).
    Stable ordering: lexical by `claim_id` (the primary key).
    """
    query = """
    MATCH (c:Claim)
    RETURN c.claim_id, c.claim_family_id, c.subject_slug,
           c.predicate_class_canonical, c.predicate_class_raw,
           c.predicate_scope_slugs, c.object_slugs,
           c.polarity, c.modality, c.condition_text, c.assertion_text,
           c.confidence, c.confidence_spread, c.state, c.version,
           c.created_at, c.last_revised_at
    ORDER BY c.claim_id
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "claim_id": row[0],
                "claim_family_id": row[1],
                "subject_slug": row[2],
                "predicate_class_canonical": row[3],
                "predicate_class_raw": row[4],
                "predicate_scope_slugs": list(row[5]) if row[5] is not None else [],
                "object_slugs": list(row[6]) if row[6] is not None else [],
                "polarity": row[7],
                "modality": row[8],
                "condition_text": row[9],
                "assertion_text": row[10],
                "confidence": row[11],
                "confidence_spread": row[12],
                "state": row[13],
                "version": row[14],
                "created_at": row[15],
                "last_revised_at": row[16],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_evidences(conn: kuzu.Connection, path: Path) -> int:
    """#83/#84 (format v4): EVIDENCES edges (Source → Claim) with
    quoted_text + score + provenance_type + run_id + created_at.

    Pre-#83/#84 graphs have no edges ⇒ empty file. Total-order by
    `(source_id, claim_id, run_id, created_at)` for byte-identical reruns.
    """
    query = """
    MATCH (s:Source)-[r:EVIDENCES]->(c:Claim)
    RETURN s.source_id, c.claim_id, r.quoted_text, r.score,
           r.provenance_type, r.run_id, r.created_at
    ORDER BY s.source_id, c.claim_id, r.run_id, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "source_id": row[0],
                "claim_id": row[1],
                "quoted_text": row[2],
                "score": row[3],
                "provenance_type": row[4],
                "run_id": row[5],
                "created_at": row[6],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_about(conn: kuzu.Connection, path: Path) -> int:
    """#83/#84 (format v4): ABOUT edges (Claim → Entity). Authoritative
    Claim-to-Entity binding per D-83/84-9.

    Pre-#83/#84 graphs have no edges ⇒ empty file. Total-order by
    `(claim_id, entity_slug, run_id, created_at)`.
    """
    query = """
    MATCH (c:Claim)-[r:ABOUT]->(e:Entity)
    RETURN c.claim_id, e.slug, r.run_id, r.created_at
    ORDER BY c.claim_id, e.slug, r.run_id, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "claim_id": row[0],
                "entity_slug": row[1],
                "run_id": row[2],
                "created_at": row[3],
            }
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_supersedes(conn: kuzu.Connection, path: Path) -> int:
    """#83/#84 (format v4): SUPERSEDES edges (Claim → Claim, newer → older).
    Per D-83/84-6 F2 state machine.
    """
    return _write_claim_claim_edge(conn, path, "SUPERSEDES", extra_attrs=())


def _write_contradicts(conn: kuzu.Connection, path: Path) -> int:
    """#83/#84 (format v4): CONTRADICTS edges (Claim → Claim) with
    `contradiction_kind` attribute. Semantically symmetric; queries traverse
    both directions per D-83/84-6 F2.
    """
    return _write_claim_claim_edge(conn, path, "CONTRADICTS", extra_attrs=("contradiction_kind",))


def _write_qualifies(conn: kuzu.Connection, path: Path) -> int:
    """#83/#84 (format v4): QUALIFIES edges (Claim → Claim) for
    `qualifies_or_extends` with `refines_truth_conditions=true` per D-83/84-2.
    """
    return _write_claim_claim_edge(conn, path, "QUALIFIES", extra_attrs=())


def _write_claim_claim_edge(
    conn: kuzu.Connection, path: Path, edge_name: str, *, extra_attrs: tuple[str, ...]
) -> int:
    """Shared serializer for SUPERSEDES / CONTRADICTS / QUALIFIES.

    All three are Claim→Claim with common (run_id, created_at) provenance;
    CONTRADICTS adds `contradiction_kind`. Stable order:
    `(from_claim_id, to_claim_id, run_id, created_at)`.
    """
    extra_proj = "".join(f", r.{a}" for a in extra_attrs)
    query = f"""
    MATCH (a:Claim)-[r:{edge_name}]->(b:Claim)
    RETURN a.claim_id, b.claim_id, r.run_id, r.created_at{extra_proj}
    ORDER BY a.claim_id, b.claim_id, r.run_id, r.created_at
    """
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        r = conn.execute(query)
        while r.has_next():
            row = r.get_next()
            obj = {
                "from_claim_id": row[0],
                "to_claim_id": row[1],
                "run_id": row[2],
                "created_at": row[3],
            }
            for i, attr in enumerate(extra_attrs):
                obj[attr] = row[4 + i]
            f.write(json.dumps(obj, sort_keys=True) + "\n")
            n += 1
    return n


def _write_schema(path: Path) -> str:
    """Emit DDL constants from schema.py as a single .cypher file (evidence,
    not authority). Returns the sha256 of the written content so callers
    can record it in manifest.json."""
    parts: list[str] = [
        "-- GraphDB-KDB schema DDL (evidence — authoritative DDL lives in graphdb_kdb/schema.py)",
        f"-- SCHEMA_VERSION = {SCHEMA_VERSION}",
        "",
    ]
    for ddl in NODE_TABLE_DDL:
        parts.append(ddl.strip() + ";")
        parts.append("")
    for ddl in REL_TABLE_DDL:
        parts.append(ddl.strip() + ";")
        parts.append("")
    parts.append(SCHEMA_META_DDL.strip() + ";")
    parts.append("")
    content = "\n".join(parts)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
