"""Tests for kdb_graph.schema + GraphDB schema bootstrap (#63.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

import kdb_graph
from kdb_graph import schema
from kdb_graph.graphdb import GraphDB


def test_schema_constants_exist():
    """Schema module exposes SCHEMA_VERSION + DDL lists + MIGRATIONS registry."""
    assert isinstance(schema.SCHEMA_VERSION, str)
    assert schema.SCHEMA_VERSION == "2.5"  # #136: PendingLink node table (durable link ledger)
    assert isinstance(schema.NODE_TABLE_DDL, list) and len(schema.NODE_TABLE_DDL) == 5
    assert isinstance(schema.REL_TABLE_DDL, list) and len(schema.REL_TABLE_DDL) == 9
    node_text = " ".join(schema.NODE_TABLE_DDL)
    assert "CREATE NODE TABLE Entity" in node_text
    assert "CREATE NODE TABLE Source" in node_text
    # #74.1: Entity gains canonical_id property (D-R5-5).
    assert "canonical_id" in node_text
    # #76.2: Domain node table.
    assert "CREATE NODE TABLE Domain" in node_text
    # #83/#84: Claim node table.
    assert "CREATE NODE TABLE Claim" in node_text
    # #89 D-89-17: Source gains summary/author/domain columns.
    assert "summary" in node_text
    assert "author" in node_text
    # #136: PendingLink durable ledger (link_id = source_slug + "|" + target_slug).
    assert "CREATE NODE TABLE PendingLink" in node_text
    assert "link_id" in node_text
    assert "target_slug" in node_text
    rel_text = " ".join(schema.REL_TABLE_DDL)
    assert "CREATE REL TABLE LINKS_TO" in rel_text
    assert "CREATE REL TABLE SUPPORTS" in rel_text
    # #74.1: ALIAS_OF rel table with `algorithm` provenance (D-R5-6).
    assert "CREATE REL TABLE ALIAS_OF" in rel_text
    assert "algorithm" in rel_text
    # D1-A: BELONGS_TO rel table with support_count (derived projection; sub_domain dropped).
    assert "CREATE REL TABLE BELONGS_TO" in rel_text
    assert "support_count" in rel_text
    # #83/#84: 5 new Claim-layer rel tables.
    for name in ("EVIDENCES", "ABOUT", "SUPERSEDES", "CONTRADICTS", "QUALIFIES"):
        assert f"CREATE REL TABLE {name}" in rel_text
    # 5 migrations registered: 1.0→2.0, 2.0→2.1, 2.1→2.2, 2.2→2.3, 2.4→2.5.
    assert isinstance(schema.MIGRATIONS, dict)
    assert set(schema.MIGRATIONS.keys()) == {
        ("1.0", "2.0"), ("2.0", "2.1"), ("2.1", "2.2"), ("2.2", "2.3"),
        ("2.4", "2.5"),
    }
    assert callable(schema.MIGRATIONS[("1.0", "2.0")])
    assert callable(schema.MIGRATIONS[("2.0", "2.1")])
    assert callable(schema.MIGRATIONS[("2.1", "2.2")])
    assert callable(schema.MIGRATIONS[("2.2", "2.3")])
    assert callable(schema.MIGRATIONS[("2.4", "2.5")])


def test_graphdb_init_creates_schema(graph_dir):
    """First open of a fresh path creates tables + persists schema version."""
    with GraphDB(graph_dir) as gdb:
        v = gdb.schema_version()
        stats = gdb.stats()
    assert graph_dir.exists()
    assert v == schema.SCHEMA_VERSION
    assert v == "2.5"
    # #76.2: domains + belongs_to counters join the stats dict.
    assert stats == {
        "entities": 0, "sources": 0, "links_to": 0, "supports": 0,
        "alias_of": 0, "domains": 0, "belongs_to": 0,
        # #83/#84 v2.2 — Claim layer counters all zero on fresh DB.
        "claims": 0, "evidences": 0, "about": 0,
        "supersedes": 0, "contradicts": 0, "qualifies": 0,
        # #136 v2.5 — PendingLink ledger counter.
        "pending_links": 0,
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
        "entities": 0, "sources": 0, "links_to": 0, "supports": 0,
        "alias_of": 0, "domains": 0, "belongs_to": 0,
        # #83/#84 v2.2 — Claim layer counters all zero on fresh DB.
        "claims": 0, "evidences": 0, "about": 0,
        "supersedes": 0, "contradicts": 0, "qualifies": 0,
        # #136 v2.5 — PendingLink ledger counter.
        "pending_links": 0,
    }
    # v2.5: schema version now "2.5" (#136 PendingLink node table).
    assert v1 == "2.5"


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


def test_migration_v1_to_v2_4_requires_rebuild(graph_dir):
    """Opening a v1.0 DB with v2.4 code chains 1.0→2.0→2.1→2.2→2.3, then
    hits 2.3→2.4 which has no registered migration (destructive BELONGS_TO
    change requires `graphdb-kdb rebuild`). GraphDBSchemaError is raised."""
    from kdb_graph.graphdb import GraphDBSchemaError

    _create_v1_db(graph_dir)

    with pytest.raises(GraphDBSchemaError) as excinfo:
        with GraphDB(graph_dir):
            pass
    assert "no migration registered" in str(excinfo.value)
    assert "rebuild" in str(excinfo.value)


def test_migrate_2_2_to_2_3_adds_source_columns(graph_dir):
    """Per Task #89 D-89-17: _migrate_2_2_to_2_3 adds summary, author, domain
    columns to Source. Mirrors the _create_v1_db pattern — manually builds
    a v2.2 DB so we can target the specific migration step."""
    from kdb_graph.schema import _migrate_2_2_to_2_3
    import kuzu

    # Build a minimal v2.2 DB in-place (Entity + Source + basic rels + meta).
    db = kuzu.Database(str(graph_dir))
    conn = kuzu.Connection(db)
    # Source table in v2.2 shape (no summary/author/domain columns).
    conn.execute("""
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
    """)
    conn.execute("""
    CREATE NODE TABLE _SchemaMeta (
        key   STRING PRIMARY KEY,
        value STRING
    )
    """)
    conn.execute("CREATE (:_SchemaMeta {key: 'schema_version', value: '2.2'})")
    # Seed one Source row to prove migration is non-destructive.
    conn.execute(
        "CREATE (:Source {source_id: 'KDB/raw/seed.md', source_type: 'md', "
        "canonical_path: 'KDB/raw/seed.md', status: 'active', file_type: 'markdown', "
        "hash: 'sha256:abc', size_bytes: 100, first_seen_at: '2026-01-01', "
        "last_seen_at: '2026-01-01', last_ingested_at: '2026-01-01', "
        "ingest_state: 'compiled', ingest_count: 1, last_run_id: 'r1', moved_to: ''})"
    )
    del conn
    del db

    # Now run the specific migration step.
    db2 = kuzu.Database(str(graph_dir))
    conn2 = kuzu.Connection(db2)
    _migrate_2_2_to_2_3(conn2)

    # Verify columns exist (query would raise if columns are absent).
    r = conn2.execute(
        "MATCH (s:Source {source_id: 'KDB/raw/seed.md'}) "
        "RETURN s.summary, s.author, s.domain"
    )
    assert r.has_next()
    row = r.get_next()
    # Existing rows get NULL (not yet populated by Pass-1).
    assert row[0] is None  # summary
    assert row[1] is None  # author
    assert row[2] is None  # domain

    # Schema version bumped.
    mv = conn2.execute(
        "MATCH (m:_SchemaMeta {key: 'schema_version'}) RETURN m.value"
    )
    assert mv.get_next()[0] == "2.3"
    del conn2
    del db2


def test_fresh_db_current_version_has_source_columns(graph_dir):
    """Fresh DB created with current SCHEMA_VERSION has summary/author/domain
    on Source (no migration needed — DDL creates them directly)."""
    with GraphDB(graph_dir) as gdb:
        assert gdb.schema_version() == schema.SCHEMA_VERSION
        # Column existence: INSERT with explicit values, then read back.
        gdb.conn.execute(
            "CREATE (:Source {source_id: 'KDB/raw/test.md', source_type: 'md', "
            "canonical_path: 'KDB/raw/test.md', status: 'active', file_type: 'markdown', "
            "hash: 'sha256:xyz', size_bytes: 50, first_seen_at: '2026-01-01', "
            "last_seen_at: '2026-01-01', last_ingested_at: '2026-01-01', "
            "ingest_state: 'compiled', ingest_count: 1, last_run_id: 'r1', "
            "moved_to: '', summary: 'A test source', author: 'Jane Doe', "
            "domain: 'Testing'})"
        )
        r = gdb.conn.execute(
            "MATCH (s:Source {source_id: 'KDB/raw/test.md'}) "
            "RETURN s.summary, s.author, s.domain"
        )
        assert r.has_next()
        row = r.get_next()
        assert row[0] == "A test source"
        assert row[1] == "Jane Doe"
        assert row[2] == "Testing"


def test_migration_unknown_version_raises(graph_dir, monkeypatch):
    """If a DB reports a stored version with no migration registered,
    _ensure_schema raises GraphDBSchemaError pointing the user at rebuild."""
    from kdb_graph.graphdb import GraphDBSchemaError

    # Create a v1.0 DB, then make MIGRATIONS empty to simulate "no migration
    # registered for this pair."
    _create_v1_db(graph_dir)
    monkeypatch.setattr(schema, "MIGRATIONS", {})
    # Patch the imported reference in graphdb.py too (the import is `from
    # kdb_graph.schema import MIGRATIONS`, so we need to patch there too).
    from kdb_graph import graphdb as graphdb_mod
    monkeypatch.setattr(graphdb_mod, "MIGRATIONS", {})

    with pytest.raises(GraphDBSchemaError) as excinfo:
        with GraphDB(graph_dir):
            pass
    assert "no migration registered" in str(excinfo.value)
    assert "rebuild" in str(excinfo.value)


def test_default_graph_path_default(monkeypatch):
    """default_graph_path derives <vault>/KDB/graph from the default vault root."""
    monkeypatch.delenv("KDB_GRAPH_PATH", raising=False)
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    p = kdb_graph.default_graph_path()
    assert isinstance(p, Path)
    assert p == (Path.home() / "Obsidian").resolve() / "KDB" / "graph"


def test_default_graph_path_vault_env(monkeypatch, tmp_path):
    """OBSIDIAN_VAULT_PATH drives the derived default when KDB_GRAPH_PATH is unset."""
    monkeypatch.delenv("KDB_GRAPH_PATH", raising=False)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    assert kdb_graph.default_graph_path() == tmp_path.resolve() / "KDB" / "graph"


def test_default_graph_path_env_override(tmp_path, monkeypatch):
    """KDB_GRAPH_PATH env var overrides the default."""
    custom = tmp_path / "custom-graph-location"
    monkeypatch.setenv("KDB_GRAPH_PATH", str(custom))
    p = kdb_graph.default_graph_path()
    assert p == custom


def test_belongs_to_ddl_has_support_count_not_sub_domain():
    from kdb_graph import schema
    belongs_to_ddl = next(d for d in schema.REL_TABLE_DDL if "BELONGS_TO" in d)
    assert "support_count" in belongs_to_ddl
    assert "INT64" in belongs_to_ddl
    assert "sub_domain" not in belongs_to_ddl


def test_schema_version_is_2_5():
    from kdb_graph import schema
    assert schema.SCHEMA_VERSION == "2.5"


def test_pending_link_table_exists_on_fresh_db(graph_dir):
    """#136: a fresh v2.5 DB has the PendingLink node table (observable via a
    zero-count Cypher query; first_run_id/last_run_id columns present)."""
    with GraphDB(graph_dir) as gdb:
        result = gdb.conn.execute(
            "MATCH (p:PendingLink) RETURN COUNT(p)"
        )
        assert result.has_next()
        assert int(result.get_next()[0]) == 0
        # Column existence — would raise if absent.
        assert gdb.conn.execute(
            "MATCH (p:PendingLink) RETURN p.first_run_id, p.last_run_id LIMIT 1"
        ) is not None


def test_migrate_2_4_to_2_5_adds_pending_link_table(graph_dir):
    """#136: _migrate_2_4_to_2_5 adds the PendingLink node table in place
    (non-destructive). Mirrors the _create_v1_db pattern — manually builds a
    v2.4 DB (current DDL minus PendingLink) so we can target the specific step."""
    from kdb_graph.schema import _migrate_2_4_to_2_5
    import kuzu

    db = kuzu.Database(str(graph_dir))
    conn = kuzu.Connection(db)
    for ddl in schema.NODE_TABLE_DDL[:4]:       # v2.4 shape: no PendingLink
        conn.execute(ddl)
    for ddl in schema.REL_TABLE_DDL:
        conn.execute(ddl)
    conn.execute(schema.SCHEMA_META_DDL)
    conn.execute("CREATE (:_SchemaMeta {key: 'schema_version', value: '2.4'})")
    # Seed one Entity to prove the migration is non-destructive.
    conn.execute(
        "CREATE (:Entity {slug: 'pre-migration', title: 'Pre', page_type: 'concept', "
        "status: 'active', created_at: '2026-08-06', updated_at: '2026-08-06', "
        "first_run_id: 'r0', last_run_id: 'r0'})"
    )
    del conn
    del db

    db2 = kuzu.Database(str(graph_dir))
    conn2 = kuzu.Connection(db2)
    _migrate_2_4_to_2_5(conn2)

    # PendingLink queryable; seeded entity intact; version bumped.
    r = conn2.execute("MATCH (p:PendingLink) RETURN COUNT(p)")
    assert int(r.get_next()[0]) == 0
    r = conn2.execute("MATCH (e:Entity {slug: 'pre-migration'}) RETURN COUNT(e)")
    assert int(r.get_next()[0]) == 1
    mv = conn2.execute(
        "MATCH (m:_SchemaMeta {key: 'schema_version'}) RETURN m.value"
    )
    assert mv.get_next()[0] == "2.5"
    del conn2
    del db2


def test_open_existing_2_4_db_migrates_via_ensure_schema(graph_dir):
    """#136 end-to-end migration path: a writable GraphDB open of a v2.4 store
    walks the registered 2.4→2.5 step automatically (existing graphs get the
    ledger without a rebuild)."""
    import kuzu

    db = kuzu.Database(str(graph_dir))
    conn = kuzu.Connection(db)
    for ddl in schema.NODE_TABLE_DDL[:4]:
        conn.execute(ddl)
    for ddl in schema.REL_TABLE_DDL:
        conn.execute(ddl)
    conn.execute(schema.SCHEMA_META_DDL)
    conn.execute("CREATE (:_SchemaMeta {key: 'schema_version', value: '2.4'})")
    del conn
    del db

    with GraphDB(graph_dir) as gdb:
        assert gdb.schema_version() == "2.5"
        r = gdb.conn.execute("MATCH (p:PendingLink) RETURN COUNT(p)")
        assert int(r.get_next()[0]) == 0
