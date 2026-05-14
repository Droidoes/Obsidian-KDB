"""Kuzu DDL + schema version + migration registry for GraphDB-KDB.

Schema is documented at docs/task-graphdb-kdb-blueprint.md §4. Tables:
- Node: Page (slug-keyed), Source (source_id-keyed, source_type-discriminated)
- Rel:  LINKS_TO (Page->Page), SUPPORTS (Source->Page)
- Internal: _SchemaMeta (key/value for schema_version pinning)

Timestamps are STRING (per D-note in §4) holding `datetime.now().astimezone().isoformat()`.
"""
from __future__ import annotations

from typing import Callable

SCHEMA_VERSION = "1.0"

# Node tables — one CREATE per element (Kuzu requires one statement per execute).
NODE_TABLE_DDL: list[str] = [
    """
    CREATE NODE TABLE Page (
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
    """,
    """
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
        last_compiled_at   STRING,
        compile_state      STRING,
        compile_count      INT64,
        last_run_id        STRING,
        moved_to           STRING
    )
    """,
]

# Relationship tables
REL_TABLE_DDL: list[str] = [
    """
    CREATE REL TABLE LINKS_TO (
        FROM Page TO Page,
        run_id      STRING,
        created_at  STRING
    )
    """,
    """
    CREATE REL TABLE SUPPORTS (
        FROM Source TO Page,
        role          STRING,
        hash_at_time  STRING,
        run_id        STRING,
        created_at    STRING
    )
    """,
]

# Internal metadata table — single-row `(key='schema_version', value=SCHEMA_VERSION)`.
SCHEMA_META_DDL = """
    CREATE NODE TABLE _SchemaMeta (
        key   STRING PRIMARY KEY,
        value STRING
    )
"""

# Q6 scaffold: migration registry keyed by (from_version, to_version).
# Empty for v1; populated when schema evolves.
MIGRATIONS: dict[tuple[str, str], Callable] = {}
