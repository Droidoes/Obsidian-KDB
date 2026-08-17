"""schema — SQLite DDL + numbered migrations for the kdb_fts ledger.

Phase 0 (migration 1): articles / paragraphs / authors / author_aliases /
articles_fts. Phase 1 (migration 2): gate_verdicts (§7.2; additive cols
exploration/rationale/tokens beyond §6's list — plan deviation 1).
Extraction, feedback-mirror, and ranker tables arrive as later migrations
in their own phases (D14: re-extraction never rewrites identity).
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

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
    2: """
    CREATE TABLE gate_verdicts (
        article_id      TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
        run_id          TEXT NOT NULL,
        topic           TEXT NOT NULL,       -- 6 closed labels; unknown fails closed to 'other'
        signal          REAL NOT NULL,       -- 0..1
        extract_ideas   INTEGER NOT NULL,    -- bool
        extract_lessons INTEGER NOT NULL,    -- bool
        exploration     INTEGER NOT NULL DEFAULT 0,  -- §7.2: 5%-of-ineligible sample for Phase 2
        confidence      REAL,                -- nullable, model-reported 0..1
        rationale       TEXT,                -- §7.2 one-liner
        model           TEXT NOT NULL,
        prompt_version  TEXT NOT NULL,
        input_tokens    INTEGER NOT NULL DEFAULT 0,
        output_tokens   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (article_id, run_id)
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
    """Apply all pending migrations in order. Idempotent.

    Each migration's DDL runs inside an explicit transaction (a failing
    migration rolls back and never advances schema_version). executescript
    commits any already-open transaction first, so the BEGIN must live
    inside the script text.
    """
    for version in range(current_version(conn) + 1, SCHEMA_VERSION + 1):
        try:
            conn.executescript(f"BEGIN;\n{MIGRATIONS[version]}\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
