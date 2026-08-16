"""Schema: fresh DB migrates to latest; migrate is idempotent; env override wins."""
from __future__ import annotations

import sqlite3

from kdb_fts import schema, state


def test_state_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("KDB_FTS_PATH", str(tmp_path / "custom"))
    assert state.state_root() == (tmp_path / "custom").resolve()


def test_state_root_default(monkeypatch, tmp_path):
    monkeypatch.delenv("KDB_FTS_PATH", raising=False)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))
    assert state.state_root() == (tmp_path / "vault" / "KDB" / "fts").resolve()


def test_fresh_db_migrates_to_latest():
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    assert schema.current_version(conn) == schema.SCHEMA_VERSION
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
            # sqlite_master records FTS5 shadow tables as type 'table'
        )
    }
    for expected in ("meta", "articles", "paragraphs", "authors", "author_aliases"):
        assert expected in tables, f"missing table {expected}"
    fts = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'articles_fts'"
    ).fetchone()
    assert fts is not None and "fts5" in fts[0].lower()


def test_migrate_is_idempotent():
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    schema.migrate(conn)  # second run: no-op, no error
    assert schema.current_version(conn) == schema.SCHEMA_VERSION
