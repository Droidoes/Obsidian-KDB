"""author_map — raw author string → canonical author/publication (yaml).

author_map.yaml lives under the state root and is Joseph-editable config.
Unmapped strings never block intake: they default to their normalized form
and are listed by unmapped() for Joseph to curate (§6 blueprint).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml


def _normalize(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def load_map(root: Path) -> dict[str, dict[str, str]]:
    path = Path(root) / "author_map.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): dict(v) for k, v in data.items()}


def resolve(conn: sqlite3.Connection, raw: str, mapping: dict[str, dict[str, str]]) -> int:
    """Get-or-create canonical author + alias for one raw string."""
    entry = mapping.get(raw, {})
    canonical = entry.get("canonical") or _normalize(raw)
    publication = entry.get("publication")
    row = conn.execute(
        "SELECT author_id FROM author_aliases WHERE raw_string = ?", (raw,)
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT author_id FROM authors WHERE canonical_name = ?", (canonical,)
    ).fetchone()
    if row:
        author_id = row[0]
        if publication:  # enrich existing row if we now know the publication
            conn.execute(
                "UPDATE authors SET publication = COALESCE(publication, ?) WHERE author_id = ?",
                (publication, author_id),
            )
    else:
        cur = conn.execute(
            "INSERT INTO authors(canonical_name, publication) VALUES (?,?)",
            (canonical, publication),
        )
        author_id = cur.lastrowid
    conn.execute(
        "INSERT INTO author_aliases(raw_string, author_id) VALUES (?,?)",
        (raw, author_id),
    )
    conn.commit()
    return author_id


def unmapped(conn: sqlite3.Connection) -> list[str]:
    """Raw strings with no yaml override (canonical == normalized raw).

    Post-filtered in Python (not SQL): SQLite TRIM strips only leading/trailing
    whitespace, while _normalize also collapses internal runs — a SQL-only
    comparison would silently drop exactly the messy strings this list exists
    to surface.
    """
    rows = conn.execute(
        """SELECT al.raw_string, a.canonical_name FROM author_aliases al
           JOIN authors a ON a.author_id = al.author_id
           ORDER BY al.raw_string"""
    ).fetchall()
    return [raw for raw, canonical in rows if canonical == _normalize(raw)]
