"""schema — SQLite DDL + numbered migrations for the kdb_fts ledger.

Phase 0 (migration 1): articles / paragraphs / authors / author_aliases /
articles_fts. Gate, extraction, feedback, and ranker tables arrive as later
migrations in their own phases (D14: re-extraction never rewrites identity).
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE articles (
        article_id     TEXT PRIMARY KEY,  -- gmail_message_id else 'sha256:'+hash (D17)
        path           TEXT NOT NULL,      -- mutable attribute, never identity
        content_sha256 TEXT NOT NULL,
        title          TEXT,
        raw_author     TEXT,
        author_id      INTEGER REFERENCES authors(author_id),
        published_date TEXT,
        source_url     TEXT,
        content_kind   TEXT,
        word_count     INTEGER NOT NULL,
        cleanliness    TEXT NOT NULL,      -- ok|short|media|digest-stub|bleed|repaired
        first_seen_run TEXT NOT NULL,
        last_seen_run  TEXT NOT NULL
    );
    CREATE TABLE paragraphs (
        article_id   TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
        paragraph_id TEXT NOT NULL,          -- p0001… stable within one content hash
        body         TEXT NOT NULL,
        PRIMARY KEY (article_id, paragraph_id)
    );
    CREATE TABLE authors (
        author_id       INTEGER PRIMARY KEY,
        canonical_name  TEXT NOT NULL UNIQUE,
        publication     TEXT,
        explicit_rating REAL,              -- nullable; wins when set (D9a)
        derived_score   REAL
    );
    CREATE TABLE author_aliases (
        raw_string TEXT PRIMARY KEY,
        author_id  INTEGER NOT NULL REFERENCES authors(author_id)
    );
    CREATE VIRTUAL TABLE articles_fts USING fts5(
        article_id UNINDEXED,
        title,
        author,
        body
    );
    """,
}


def current_version(conn: sqlite3.Connection) -> int:
    """Schema version of an open connection; 0 for a brand-new database."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:  # meta table does not exist yet
        return 0
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations in order. Idempotent."""
    for version in range(current_version(conn) + 1, SCHEMA_VERSION + 1):
        conn.executescript(MIGRATIONS[version])
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
