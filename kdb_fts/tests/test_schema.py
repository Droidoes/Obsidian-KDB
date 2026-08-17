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


import sqlite3

import pytest

from kdb_fts import ledger, schema


def test_migration_2_creates_gate_verdicts(tmp_path):
    conn = ledger.connect(tmp_path)
    assert schema.current_version(conn) == 2
    cols = {r[1] for r in conn.execute("PRAGMA table_info(gate_verdicts)")}
    assert cols == {
        "article_id", "run_id", "topic", "signal",
        "extract_ideas", "extract_lessons", "exploration",
        "confidence", "rationale", "model", "prompt_version",
        "input_tokens", "output_tokens",
    }


def test_migrate_failure_rolls_back_and_keeps_version(tmp_path, monkeypatch):
    """A broken migration must not advance schema_version or leave the DB
    wedged (executescript txn-wrapping, migration-2-era hardening)."""
    conn = ledger.connect(tmp_path)
    broken = "CREATE TABLE boom(x); CREATE TABLE boom(x);"  # dup → error mid-script
    monkeypatch.setitem(schema.MIGRATIONS, 3, broken)
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 3)
    with pytest.raises(sqlite3.OperationalError):
        schema.migrate(conn)
    assert schema.current_version(conn) == 2  # unchanged
    # DB still usable: a well-known table answers a query.
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0


def test_connect_creates_state_subdirs(tmp_path):
    ledger.connect(tmp_path)
    for sub in ("runs", "feedback", "review", "exports"):
        assert (tmp_path / sub).is_dir(), sub
