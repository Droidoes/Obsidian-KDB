"""ledger — typed DB access; the ONLY module that opens ledger.sqlite (D3/D4).

Every sqlite3.connect in kdb_fts lives here (write-boundary guard R1).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from kdb_fts import schema, state

_DB_NAME = "ledger.sqlite"


@dataclass
class ArticleRecord:
    article_id: str
    path: str
    content_sha256: str
    title: str | None
    raw_author: str | None
    author_id: int | None
    published_date: str | None
    source_url: str | None
    content_kind: str | None
    word_count: int
    cleanliness: str
    paragraphs: list[str] = field(default_factory=list)


def connect(root: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the ledger under the state root; migrate.

    Also guarantees the §5 state layout subdirs exist — ledger.py is the
    write-guard's mkdir allowlist, so all directory creation lives here.
    """
    root = (root or state.state_root())
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("runs", "feedback", "review", "exports"):
        (root / sub).mkdir(exist_ok=True)
    conn = sqlite3.connect(root / _DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    schema.migrate(conn)
    return conn


def upsert_article(conn: sqlite3.Connection, rec: ArticleRecord, run_id: str) -> None:
    """Insert or refresh one article. Paragraphs are replaced only when the
    content hash changed; first_seen_run is sticky, last_seen_run advances."""
    existing = conn.execute(
        "SELECT content_sha256 FROM articles WHERE article_id = ?",
        (rec.article_id,),
    ).fetchone()
    if existing is None:
        conn.execute(
            """INSERT INTO articles
               (article_id, path, content_sha256, title, raw_author, author_id,
                published_date, source_url, content_kind, word_count, cleanliness,
                first_seen_run, last_seen_run)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rec.article_id, rec.path, rec.content_sha256, rec.title, rec.raw_author,
             rec.author_id, rec.published_date, rec.source_url, rec.content_kind,
             rec.word_count, rec.cleanliness, run_id, run_id),
        )
        _replace_paragraphs(conn, rec)
    else:
        conn.execute(
            """UPDATE articles SET path=?, content_sha256=?, title=?, raw_author=?,
               author_id=?, published_date=?, source_url=?, content_kind=?,
               word_count=?, cleanliness=?, last_seen_run=?
               WHERE article_id=?""",
            (rec.path, rec.content_sha256, rec.title, rec.raw_author, rec.author_id,
             rec.published_date, rec.source_url, rec.content_kind, rec.word_count,
             rec.cleanliness, run_id, rec.article_id),
        )
        if existing[0] != rec.content_sha256:
            _replace_paragraphs(conn, rec)
    conn.commit()


def _replace_paragraphs(conn: sqlite3.Connection, rec: ArticleRecord) -> None:
    conn.execute("DELETE FROM paragraphs WHERE article_id = ?", (rec.article_id,))
    conn.executemany(
        "INSERT INTO paragraphs(article_id, paragraph_id, body) VALUES (?,?,?)",
        [(rec.article_id, f"p{i:04d}", body) for i, body in enumerate(rec.paragraphs, 1)],
    )


def delete_absent(conn: sqlite3.Connection, present_ids: set[str]) -> int:
    """Delete articles (and cascaded paragraphs) whose ids are not present."""
    rows = conn.execute("SELECT article_id FROM articles").fetchall()
    stale = [r[0] for r in rows if r[0] not in present_ids]
    conn.executemany("DELETE FROM articles WHERE article_id = ?", [(a,) for a in stale])
    conn.commit()
    return len(stale)


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Full FTS5 repopulation (cheap at 4.2M words; keeps index logic trivial).

    The author column is the CANONICAL name when the alias is mapped
    (falling back to raw_author) — searching a curated name must work.
    """
    conn.execute("DELETE FROM articles_fts")
    conn.execute(
        """INSERT INTO articles_fts(article_id, title, author, body)
           SELECT a.article_id, COALESCE(a.title, ''),
                  COALESCE((SELECT au.canonical_name FROM authors au
                            WHERE au.author_id = a.author_id),
                           a.raw_author, ''),
                  COALESCE((SELECT GROUP_CONCAT(p.body, char(10)||char(10))
                            FROM paragraphs p WHERE p.article_id = a.article_id), '')
           FROM articles a"""
    )
    conn.commit()


def search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """FTS5 MATCH over title/author/body; bm25 order; snippet from body."""
    try:
        rows = conn.execute(
            """SELECT article_id, title, author,
                      snippet(articles_fts, 3, '**', '**', '…', 12) AS snip
               FROM articles_fts WHERE articles_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        raise ValueError(f"malformed FTS5 query {query!r}: {e}") from e
    return [
        {"article_id": r[0], "title": r[1], "author": r[2], "snippet": r[3]}
        for r in rows
    ]
