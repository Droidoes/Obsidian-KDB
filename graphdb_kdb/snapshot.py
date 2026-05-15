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

SNAPSHOT_FORMAT_VERSION = 1


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

            schema_path = tmp_dir / "schema.cypher"
            schema_ddl_sha256 = _write_schema(schema_path)
            files_meta["schema.cypher"] = {"sha256": schema_ddl_sha256}

            counts = {
                "entities": files_meta["entities.jsonl"]["rows"],
                "sources": files_meta["sources.jsonl"]["rows"],
                "links_to": files_meta["links_to.jsonl"]["rows"],
                "supports": files_meta["supports.jsonl"]["rows"],
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
    query = """
    MATCH (e:Entity)
    RETURN e.slug, e.title, e.page_type, e.status, e.confidence,
           e.created_at, e.updated_at, e.first_run_id, e.last_run_id
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
