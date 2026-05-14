"""GraphDB: Kuzu connection management + schema bootstrap.

Public API per docs/task-graphdb-kdb-blueprint.md §6.1. #63.1 implements
only the foundation (init, schema bootstrap, version check, stats); query
and analytics methods land in #63.3+.
"""
from __future__ import annotations

from pathlib import Path

import kuzu

from graphdb_kdb.schema import (
    NODE_TABLE_DDL,
    REL_TABLE_DDL,
    SCHEMA_META_DDL,
    SCHEMA_VERSION,
)
from graphdb_kdb.types import Entity, Source, SyncResult


class GraphDBSchemaError(RuntimeError):
    """Raised when on-disk schema version is incompatible with this code."""


class GraphDB:
    """Kuzu wrapper for the GraphDB-KDB store.

    Use as a context manager:

        with GraphDB(graph_dir) as gdb:
            stats = gdb.stats()
    """

    def __init__(self, graph_dir: Path | str, *, read_only: bool = False) -> None:
        self._graph_dir = Path(graph_dir)
        self._read_only = read_only
        # Kuzu creates the directory itself; ensure parent exists.
        self._graph_dir.parent.mkdir(parents=True, exist_ok=True)
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None

    # context manager

    def __enter__(self) -> "GraphDB":
        self._open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _open(self) -> None:
        self._db = kuzu.Database(str(self._graph_dir))
        self._conn = kuzu.Connection(self._db)
        self._ensure_schema()

    def close(self) -> None:
        # Kuzu bindings clean up on GC; dropping refs is sufficient.
        self._conn = None
        self._db = None

    @property
    def conn(self) -> kuzu.Connection:
        if self._conn is None:
            raise RuntimeError("GraphDB is not open. Use as a context manager.")
        return self._conn

    # schema bootstrap

    def _table_exists(self, name: str) -> bool:
        result = self.conn.execute("CALL show_tables() RETURN *")
        while result.has_next():
            row = result.get_next()
            if name in row:
                return True
        return False

    def _ensure_schema(self) -> None:
        """Idempotent: create schema on first open; verify version on re-open."""
        if self._table_exists("_SchemaMeta"):
            stored = self._read_schema_version()
            if stored != SCHEMA_VERSION:
                raise GraphDBSchemaError(
                    f"Schema version mismatch: stored={stored!r} expected={SCHEMA_VERSION!r}. "
                    "Run `graphdb-kdb rebuild` to regenerate."
                )
            return
        for ddl in NODE_TABLE_DDL:
            self.conn.execute(ddl)
        for ddl in REL_TABLE_DDL:
            self.conn.execute(ddl)
        self.conn.execute(SCHEMA_META_DDL)
        # Constant interpolation; SCHEMA_VERSION is module-controlled.
        self.conn.execute(
            f"CREATE (m:_SchemaMeta {{key: 'schema_version', value: '{SCHEMA_VERSION}'}})"
        )

    def _read_schema_version(self) -> str | None:
        result = self.conn.execute(
            "MATCH (m:_SchemaMeta {key: 'schema_version'}) RETURN m.value"
        )
        if result.has_next():
            row = result.get_next()
            return row[0] if row else None
        return None

    # public minimal API for #63.1

    def schema_version(self) -> str:
        """Schema version currently stored in this DB."""
        return self._read_schema_version() or ""

    def stats(self) -> dict[str, int]:
        """Basic node/edge counts."""
        def count(query: str) -> int:
            r = self.conn.execute(query)
            if r.has_next():
                return int(r.get_next()[0])
            return 0
        return {
            "entities": count("MATCH (e:Entity) RETURN COUNT(*)"),
            "sources":  count("MATCH (s:Source) RETURN COUNT(*)"),
            "links_to": count("MATCH ()-[r:LINKS_TO]->() RETURN COUNT(*)"),
            "supports": count("MATCH ()-[r:SUPPORTS]->() RETURN COUNT(*)"),
        }

    # ---- ingestion (#63.2) ----

    def apply_compile_result(
        self,
        cr: dict,
        scan_dict: dict,
        run_id: str,
        *,
        now: str | None = None,
    ) -> SyncResult:
        """Apply one compile run's deltas. Atomic per run. Delegates to ingestor."""
        from graphdb_kdb.ingestor import apply_compile_result as _apply
        return _apply(cr, scan_dict, run_id, conn=self.conn, now=now)

    # ---- minimal read API (full set lands in #63.3) ----

    def get_entity(self, slug: str) -> Entity | None:
        """Return the Entity node for a slug, or None if absent."""
        r = self.conn.execute(
            """
            MATCH (e:Entity {slug: $slug})
            RETURN e.slug, e.title, e.page_type, e.status, e.confidence,
                   e.created_at, e.updated_at, e.first_run_id, e.last_run_id
            """,
            {"slug": slug},
        )
        if not r.has_next():
            return None
        row = r.get_next()
        return Entity(
            slug=row[0], title=row[1], page_type=row[2], status=row[3],
            confidence=row[4], created_at=row[5], updated_at=row[6],
            first_run_id=row[7], last_run_id=row[8],
        )

    def get_source(self, source_id: str) -> Source | None:
        """Return the Source node for a source_id, or None if absent."""
        r = self.conn.execute(
            """
            MATCH (s:Source {source_id: $sid})
            RETURN s.source_id, s.source_type, s.canonical_path, s.status,
                   s.file_type, s.hash, s.size_bytes, s.first_seen_at,
                   s.last_seen_at, s.last_ingested_at, s.ingest_state,
                   s.ingest_count, s.last_run_id, s.moved_to
            """,
            {"sid": source_id},
        )
        if not r.has_next():
            return None
        row = r.get_next()
        return Source(
            source_id=row[0], source_type=row[1], canonical_path=row[2],
            status=row[3], file_type=row[4], hash=row[5],
            size_bytes=int(row[6]) if row[6] is not None else 0,
            first_seen_at=row[7], last_seen_at=row[8], last_ingested_at=row[9],
            ingest_state=row[10],
            ingest_count=int(row[11]) if row[11] is not None else 0,
            last_run_id=row[12], moved_to=row[13],
        )

    # ---- read API (#63.3) — delegates to queries module ----

    def neighbors(self, slug: str, *, direction: str = "out", depth: int = 1) -> list[Entity]:
        from graphdb_kdb import queries
        return queries.neighbors(self.conn, slug, direction=direction, depth=depth)

    def incoming_links(self, slug: str) -> list[Entity]:
        from graphdb_kdb import queries
        return queries.incoming_links(self.conn, slug)

    def outgoing_links(self, slug: str) -> list[Entity]:
        from graphdb_kdb import queries
        return queries.outgoing_links(self.conn, slug)

    def shortest_path(self, from_slug: str, to_slug: str, *, max_hops: int = 10) -> list[str] | None:
        from graphdb_kdb import queries
        return queries.shortest_path(self.conn, from_slug, to_slug, max_hops=max_hops)

    def entities_for_source(self, source_id: str) -> list[Entity]:
        from graphdb_kdb import queries
        return queries.entities_for_source(self.conn, source_id)

    def sources_for_entity(self, slug: str) -> list[Source]:
        from graphdb_kdb import queries
        return queries.sources_for_entity(self.conn, slug)

    def subgraph_by_source(self, source_id: str) -> dict:
        from graphdb_kdb import queries
        return queries.subgraph_by_source(self.conn, source_id)

    def orphan_entities(self) -> list[Entity]:
        from graphdb_kdb import queries
        return queries.orphan_entities(self.conn)

    def cypher(self, query: str, params: dict | None = None) -> list[dict]:
        from graphdb_kdb import queries
        return queries.cypher(self.conn, query, params)

    # ---- analytics API (#63.4) — hybrid via NetworkX/python-louvain ----

    def pagerank(self, *, top_n: int | None = None) -> list[tuple[str, float]]:
        from graphdb_kdb import analytics
        return analytics.pagerank(self.conn, top_n=top_n)

    def communities(self, *, algorithm: str = "louvain") -> dict[str, int]:
        from graphdb_kdb import analytics
        return analytics.communities(self.conn, algorithm=algorithm)

    def structural_holes(self) -> list[tuple[int, int, int]]:
        from graphdb_kdb import analytics
        return analytics.structural_holes(self.conn)

    # ---- verifier (#63.5) ----

    def verify_against_manifest(self, manifest_path):
        from graphdb_kdb import verifier
        return verifier.verify_against_manifest(self.conn, manifest_path)
