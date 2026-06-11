"""Tests for GraphDB read-only correctness (Task #112).

The `read_only=True` flag on GraphDB was a dead parameter: `_open()` ignored it,
always opening read-write and always running `_ensure_schema()` (DDL/migrations).
These tests pin the intended contract:

  1. A read-only handle is genuinely read-only at the Kuzu level (writes raise).
  2. Write methods are blocked at the wrapper boundary (GraphDBReadOnlyError).
  3. A read-only open NEVER migrates — on a schema mismatch it fails fast and
     leaves the on-disk schema version untouched.
  4. A read-only open against a schema-matched DB reads normally.
"""
from __future__ import annotations

import kuzu
import pytest

from kdb_graph import schema
from kdb_graph.graphdb import GraphDB, GraphDBReadOnlyError, GraphDBSchemaError

from kdb_graph.tests.test_schema import _create_v1_db


def _init_current_db(graph_dir) -> None:
    """Create a fresh DB at the current SCHEMA_VERSION, then close it."""
    with GraphDB(graph_dir):
        pass


def test_read_only_kuzu_handle_rejects_write(graph_dir):
    """read_only=True must pass through to kuzu.Database — a raw write raises."""
    _init_current_db(graph_dir)
    with GraphDB(graph_dir, read_only=True) as gdb:
        with pytest.raises(Exception):
            gdb.conn.execute(
                "CREATE (:Domain {name: 'x', created_at: 't', first_run_id: 'r'})"
            )


def test_read_only_blocks_write_methods(graph_dir):
    """Write methods on a read-only handle raise GraphDBReadOnlyError at the
    wrapper boundary (not left to Kuzu to fail)."""
    _init_current_db(graph_dir)
    with GraphDB(graph_dir, read_only=True) as gdb:
        with pytest.raises(GraphDBReadOnlyError):
            gdb.detect_orphans(run_id="r")
        with pytest.raises(GraphDBReadOnlyError):
            gdb.apply_cleanup({"retracted_slugs": []}, run_id="r")


def test_read_only_open_does_not_migrate(graph_dir):
    """A read-only open of a schema-mismatched DB fails fast and NEVER migrates —
    the on-disk schema version is left untouched (the bug ran migrations because
    read_only was ignored)."""
    _create_v1_db(graph_dir)  # on-disk schema_version == "1.0"

    with pytest.raises(GraphDBSchemaError):
        with GraphDB(graph_dir, read_only=True):
            pass

    # No migration ran: on-disk version is still 1.0 (the bug would have walked
    # it forward to 2.3 before failing at 2.3->2.4).
    db = kuzu.Database(str(graph_dir), read_only=True)
    conn = kuzu.Connection(db)
    r = conn.execute(
        "MATCH (m:_SchemaMeta {key: 'schema_version'}) RETURN m.value"
    )
    assert r.get_next()[0] == "1.0"
    del conn
    del db


def test_read_only_mismatch_error_is_actionable(graph_dir):
    """The read-only schema-mismatch error names the version gap + rebuild."""
    _create_v1_db(graph_dir)
    with pytest.raises(GraphDBSchemaError) as excinfo:
        with GraphDB(graph_dir, read_only=True):
            pass
    msg = str(excinfo.value)
    assert "1.0" in msg and schema.SCHEMA_VERSION in msg
    assert "rebuild" in msg


def test_read_only_matched_db_reads(graph_dir):
    """A read-only open of a schema-matched DB opens and reads normally."""
    _init_current_db(graph_dir)
    with GraphDB(graph_dir, read_only=True) as gdb:
        assert gdb.schema_version() == schema.SCHEMA_VERSION
        assert gdb.stats()["entities"] == 0
