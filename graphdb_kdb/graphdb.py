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
            "pages":    count("MATCH (p:Page) RETURN COUNT(*)"),
            "sources":  count("MATCH (s:Source) RETURN COUNT(*)"),
            "links_to": count("MATCH ()-[r:LINKS_TO]->() RETURN COUNT(*)"),
            "supports": count("MATCH ()-[r:SUPPORTS]->() RETURN COUNT(*)"),
        }
