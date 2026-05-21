"""Tests for graphdb_kdb.schema + GraphDB schema bootstrap (#63.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

import graphdb_kdb
from graphdb_kdb import schema
from graphdb_kdb.graphdb import GraphDB


def test_schema_constants_exist():
    """Schema module exposes SCHEMA_VERSION + DDL lists + MIGRATIONS registry."""
    assert isinstance(schema.SCHEMA_VERSION, str)
    assert schema.SCHEMA_VERSION == "2.0"  # #74.1 bump
    assert isinstance(schema.NODE_TABLE_DDL, list) and len(schema.NODE_TABLE_DDL) == 2
    assert isinstance(schema.REL_TABLE_DDL, list) and len(schema.REL_TABLE_DDL) == 3
    node_text = " ".join(schema.NODE_TABLE_DDL)
    assert "CREATE NODE TABLE Entity" in node_text
    assert "CREATE NODE TABLE Source" in node_text
    # #74.1: Entity gains canonical_id property (D-R5-5).
    assert "canonical_id" in node_text
    rel_text = " ".join(schema.REL_TABLE_DDL)
    assert "CREATE REL TABLE LINKS_TO" in rel_text
    assert "CREATE REL TABLE SUPPORTS" in rel_text
    # #74.1: ALIAS_OF rel table with `algorithm` provenance (D-R5-6).
    assert "CREATE REL TABLE ALIAS_OF" in rel_text
    assert "algorithm" in rel_text
    # #74.1: 1 migration registered (1.0 → 2.0).
    assert isinstance(schema.MIGRATIONS, dict)
    assert set(schema.MIGRATIONS.keys()) == {("1.0", "2.0")}
    assert callable(schema.MIGRATIONS[("1.0", "2.0")])


def test_graphdb_init_creates_schema(graph_dir):
    """First open of a fresh path creates tables + persists schema version."""
    with GraphDB(graph_dir) as gdb:
        v = gdb.schema_version()
        stats = gdb.stats()
    assert graph_dir.exists()
    assert v == schema.SCHEMA_VERSION
    assert v == "2.0"
    # #74.1: alias_of counter joins the stats dict.
    assert stats == {
        "entities": 0, "sources": 0, "links_to": 0, "supports": 0, "alias_of": 0
    }


def test_graphdb_init_is_idempotent(graph_dir):
    """Re-opening preserves schema version and adds no duplicate state."""
    with GraphDB(graph_dir) as gdb:
        v1 = gdb.schema_version()
    with GraphDB(graph_dir) as gdb:
        v2 = gdb.schema_version()
        stats = gdb.stats()
    assert v1 == v2 == schema.SCHEMA_VERSION
    assert stats == {
        "entities": 0, "sources": 0, "links_to": 0, "supports": 0, "alias_of": 0
    }


def test_alias_of_table_exists_on_fresh_db(graph_dir):
    """#74.1 D-R5-6: a fresh v2.0 DB has the ALIAS_OF rel table."""
    with GraphDB(graph_dir) as gdb:
        # The presence of the relation is observable via a Cypher count of 0.
        result = gdb.conn.execute(
            "MATCH ()-[r:ALIAS_OF]->() RETURN COUNT(*)"
        )
        assert result.has_next()
        assert int(result.get_next()[0]) == 0


def test_entity_canonical_id_column_present(graph_dir):
    """#74.1 D-R5-5: Entity has the canonical_id column on a fresh v2.0 DB."""
    with GraphDB(graph_dir) as gdb:
        # Reading the column from an empty table returns no rows but should
        # not raise — proves the column exists.
        result = gdb.conn.execute(
            "MATCH (e:Entity) RETURN e.canonical_id LIMIT 1"
        )
        # Successfully executed = column exists.
        assert result is not None


def _create_v1_db(graph_dir):
    """Helper: create a DB in the pre-#74.1 v1.0 shape (no canonical_id,
    no ALIAS_OF) so we can exercise the migration. Mirrors the historical
    schema documented in schema.py's version history note."""
    import kuzu  # local import to keep test isolation

    db = kuzu.Database(str(graph_dir))
    conn = kuzu.Connection(db)
    v1_entity = """
    CREATE NODE TABLE Entity (
        slug          STRING PRIMARY KEY,
        title         STRING,
        page_type     STRING,
        status        STRING,
        confidence    STRING,
        created_at    STRING,
        updated_at    STRING,
        first_run_id  STRING,
        last_run_id   STRING
    )
    """
    v1_source = """
    CREATE NODE TABLE Source (
        source_id          STRING PRIMARY KEY,
        source_type        STRING,
        canonical_path     STRING,
        status             STRING,
        file_type          STRING,
        hash               STRING,
        size_bytes         INT64,
        first_seen_at      STRING,
        last_seen_at       STRING,
        last_ingested_at   STRING,
        ingest_state       STRING,
        ingest_count       INT64,
        last_run_id        STRING,
        moved_to           STRING
    )
    """
    v1_links_to = """
    CREATE REL TABLE LINKS_TO (
        FROM Entity TO Entity,
        run_id      STRING,
        created_at  STRING
    )
    """
    v1_supports = """
    CREATE REL TABLE SUPPORTS (
        FROM Source TO Entity,
        role          STRING,
        hash_at_time  STRING,
        run_id        STRING,
        created_at    STRING
    )
    """
    v1_schema_meta = """
    CREATE NODE TABLE _SchemaMeta (
        key   STRING PRIMARY KEY,
        value STRING
    )
    """
    conn.execute(v1_entity)
    conn.execute(v1_source)
    conn.execute(v1_links_to)
    conn.execute(v1_supports)
    conn.execute(v1_schema_meta)
    conn.execute(
        "CREATE (m:_SchemaMeta {key: 'schema_version', value: '1.0'})"
    )
    # Seed one entity to prove the migration is non-destructive.
    conn.execute(
        "CREATE (e:Entity {slug: 'pre-migration-entity', title: 'Pre-migration', "
        "page_type: 'concept', status: 'active', confidence: 'high', "
        "created_at: '2026-05-20', updated_at: '2026-05-20', "
        "first_run_id: 'pre-r1', last_run_id: 'pre-r1'})"
    )
    # Close connection so GraphDB can reopen cleanly.
    del conn
    del db


def test_migration_v1_to_v2_applies(graph_dir):
    """#74.1: opening a v1.0 DB with v2.0 code applies the registered
    migration in place. Existing entity survives; canonical_id column +
    ALIAS_OF rel table become available."""
    _create_v1_db(graph_dir)

    with GraphDB(graph_dir) as gdb:
        # Schema version now reports v2.0 (migration ran).
        assert gdb.schema_version() == "2.0"
        # The pre-migration entity survived.
        stats = gdb.stats()
        assert stats["entities"] == 1
        # canonical_id is queryable on existing rows (returns NULL).
        result = gdb.conn.execute(
            "MATCH (e:Entity {slug: 'pre-migration-entity'}) RETURN e.canonical_id"
        )
        assert result.has_next()
        row = result.get_next()
        # Existing entities default to canonical_id = NULL (i.e. they are
        # canonical by construction per blueprint §8.3).
        assert row[0] is None
        # ALIAS_OF table is queryable (empty).
        ar = gdb.conn.execute("MATCH ()-[r:ALIAS_OF]->() RETURN COUNT(*)")
        assert int(ar.get_next()[0]) == 0


def test_migration_unknown_version_raises(graph_dir, monkeypatch):
    """If a DB reports a stored version with no migration registered,
    _ensure_schema raises GraphDBSchemaError pointing the user at rebuild."""
    from graphdb_kdb.graphdb import GraphDBSchemaError

    # Create a v1.0 DB, then make MIGRATIONS empty to simulate "no migration
    # registered for this pair."
    _create_v1_db(graph_dir)
    monkeypatch.setattr(schema, "MIGRATIONS", {})
    # Patch the imported reference in graphdb.py too (the import is `from
    # graphdb_kdb.schema import MIGRATIONS`, so we need to patch there too).
    from graphdb_kdb import graphdb as graphdb_mod
    monkeypatch.setattr(graphdb_mod, "MIGRATIONS", {})

    with pytest.raises(GraphDBSchemaError) as excinfo:
        with GraphDB(graph_dir):
            pass
    assert "no migration registered" in str(excinfo.value)
    assert "rebuild" in str(excinfo.value)


def test_default_graph_path_default(monkeypatch):
    """default_graph_path returns ~/Droidoes/GraphDB-KDB when env var unset."""
    monkeypatch.delenv("KDB_GRAPH_PATH", raising=False)
    p = graphdb_kdb.default_graph_path()
    assert isinstance(p, Path)
    assert p == Path.home() / "Droidoes" / "GraphDB-KDB"


def test_default_graph_path_env_override(tmp_path, monkeypatch):
    """KDB_GRAPH_PATH env var overrides the default."""
    custom = tmp_path / "custom-graph-location"
    monkeypatch.setenv("KDB_GRAPH_PATH", str(custom))
    p = graphdb_kdb.default_graph_path()
    assert p == custom
