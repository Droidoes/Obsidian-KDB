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
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"author_map.yaml is not valid YAML: {path}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"author_map.yaml must be a mapping of raw string → entry: {path}")
    return {str(k): dict(v or {}) for k, v in data.items()}


def resolve(conn: sqlite3.Connection, raw: str, mapping: dict[str, dict[str, str]]) -> int:
    """Get-or-create canonical author + alias for one raw string.

    yaml overrides win even after an alias exists (Joseph edits the map between
    runs): the alias row is upserted to the override's canonical author.
    """
    entry = mapping.get(raw, {})
    canonical = entry.get("canonical") or _normalize(raw)
    publication = entry.get("publication")
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
        """INSERT INTO author_aliases(raw_string, author_id) VALUES (?,?)
           ON CONFLICT(raw_string) DO UPDATE SET author_id = excluded.author_id""",
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
