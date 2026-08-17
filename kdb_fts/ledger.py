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


def ungated_articles(conn: sqlite3.Connection, model: str,
                     prompt_version: str) -> list[dict]:
    """ok-cleanliness articles lacking a verdict at (model, prompt_version).

    author = canonical name when mapped, else raw string. Deterministic
    order (article_id ASC) so --max N slicing is stable across runs.
    """
    rows = conn.execute(
        """SELECT a.article_id, a.title,
                  COALESCE(au.canonical_name, a.raw_author) AS author,
                  a.published_date,
                  (SELECT GROUP_CONCAT(p.body, char(10)||char(10))
                   FROM paragraphs p WHERE p.article_id = a.article_id) AS body
           FROM articles a
           LEFT JOIN authors au ON au.author_id = a.author_id
           WHERE a.cleanliness = 'ok'
             AND NOT EXISTS (
                 SELECT 1 FROM gate_verdicts gv
                 WHERE gv.article_id = a.article_id
                   AND gv.model = ? AND gv.prompt_version = ?)
           ORDER BY a.article_id""",
        (model, prompt_version),
    ).fetchall()
    return [
        {"article_id": r[0], "title": r[1], "author": r[2],
         "published_date": r[3], "body": r[4] or ""}
        for r in rows
    ]


def insert_gate_verdict(
    conn: sqlite3.Connection, *, article_id: str, run_id: str, topic: str,
    signal: float, extract_ideas: bool, extract_lessons: bool,
    exploration: bool, confidence: float | None, rationale: str,
    model: str, prompt_version: str, input_tokens: int, output_tokens: int,
) -> None:
    """One verdict row per (article, run); commits immediately (resume-safe)."""
    conn.execute(
        """INSERT OR REPLACE INTO gate_verdicts
           (article_id, run_id, topic, signal, extract_ideas, extract_lessons,
            exploration, confidence, rationale, model, prompt_version,
            input_tokens, output_tokens)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (article_id, run_id, topic, signal, int(extract_ideas),
         int(extract_lessons), int(exploration), confidence, rationale,
         model, prompt_version, input_tokens, output_tokens),
    )
    conn.commit()


def latest_verdicts(conn: sqlite3.Connection) -> list[dict]:
    """The routing view: each article's verdict from its latest run."""
    rows = conn.execute(
        """SELECT gv.article_id, gv.run_id, gv.topic, gv.signal,
                  gv.extract_ideas, gv.extract_lessons, gv.exploration,
                  gv.confidence, gv.rationale, gv.model, gv.prompt_version,
                  gv.input_tokens, gv.output_tokens
           FROM gate_verdicts gv
           JOIN (SELECT article_id, MAX(run_id) AS mr FROM gate_verdicts
                 GROUP BY article_id) t
             ON t.article_id = gv.article_id AND t.mr = gv.run_id
           ORDER BY gv.article_id"""
    ).fetchall()
    cols = ("article_id", "run_id", "topic", "signal", "extract_ideas",
            "extract_lessons", "exploration", "confidence", "rationale",
            "model", "prompt_version", "input_tokens", "output_tokens")
    return [dict(zip(cols, r)) for r in rows]


def mark_exploration(conn: sqlite3.Connection, run_id: str,
                     article_ids: list[str]) -> None:
    conn.executemany(
        "UPDATE gate_verdicts SET exploration = 1 WHERE article_id = ? AND run_id = ?",
        [(a, run_id) for a in article_ids],
    )
    conn.commit()


def run_dir_for(root: Path, run_id: str) -> Path:
    """Create (idempotently) and return runs/<run_id> — mkdir lives only here
    (write-guard R3)."""
    path = Path(root) / "runs" / run_id
    path.mkdir(exist_ok=True)
    return path
