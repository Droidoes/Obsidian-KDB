"""Kuzu DDL + schema version + migration registry for GraphDB-KDB.

Schema is documented at docs/task-graphdb-kdb-blueprint.md §4 (#63 baseline)
and docs/task74-canonicalization-blueprint.md §5 (#74 canonicalization delta).

Tables:
- Node: Entity (slug-keyed; v2.0 adds canonical_id), Source (source_id-keyed)
- Rel:  LINKS_TO (Entity->Entity), SUPPORTS (Source->Entity), ALIAS_OF (Entity->Entity, v2.0)
- Internal: _SchemaMeta (key/value for schema_version pinning)

Timestamps are STRING (per D-note in §4) holding `datetime.now().astimezone().isoformat()`.

Naming history:
- `Page` → `Entity` per D-A1 (2026-05-14).
- Source's `compile_state/compile_count/last_compiled_at` → `ingest_state/
  ingest_count/last_ingested_at` per D-A2.
- Producer payloads (compile_result.json) retain the older names — adapters translate.

Schema version history:
- 1.0 — #63 baseline (Entity, Source, LINKS_TO, SUPPORTS).
- 2.0 — #74.1: Entity gains `canonical_id` property (nullable); new ALIAS_OF
        rel table with `algorithm` provenance (D-R5-5, D-R5-6, D-R5-13).
"""
from __future__ import annotations

from typing import Callable

SCHEMA_VERSION = "2.0"

# Node tables — one CREATE per element (Kuzu requires one statement per execute).
NODE_TABLE_DDL: list[str] = [
    """
    CREATE NODE TABLE Entity (
        slug          STRING PRIMARY KEY,
        title         STRING,
        page_type     STRING,
        status        STRING,
        confidence    STRING,
        canonical_id  STRING,
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
        last_ingested_at   STRING,
        ingest_state       STRING,
        ingest_count       INT64,
        last_run_id        STRING,
        moved_to           STRING
    )
    """,
]

# Relationship tables
REL_TABLE_DDL: list[str] = [
    """
    CREATE REL TABLE LINKS_TO (
        FROM Entity TO Entity,
        run_id      STRING,
        created_at  STRING
    )
    """,
    """
    CREATE REL TABLE SUPPORTS (
        FROM Source TO Entity,
        role          STRING,
        hash_at_time  STRING,
        run_id        STRING,
        created_at    STRING
    )
    """,
    """
    CREATE REL TABLE ALIAS_OF (
        FROM Entity TO Entity,
        run_id      STRING,
        created_at  STRING,
        algorithm   STRING
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


# ---- migrations ----------------------------------------------------------
#
# Each migration is a callable `(conn) -> None` that takes a Kuzu Connection
# and brings the DB from the registered `from_version` to `to_version` in
# place. Migrations are applied by `GraphDB._ensure_schema()` when a stored
# schema version doesn't match `SCHEMA_VERSION`.
#
# Migration rules:
# - Idempotency is the caller's job: each migration is applied at most once
#   per (from→to) version pair.
# - Migrations must not destroy existing data; they ADD columns / tables /
#   constraints. Destructive bumps go through `graphdb-kdb rebuild` instead.
# - After running, the migration updates the `_SchemaMeta.schema_version`
#   row to its `to_version` so the next `_ensure_schema()` sees the new
#   value.


def _migrate_1_0_to_2_0(conn) -> None:
    """Bring a v1.0 DB up to v2.0 in place (non-destructive).

    Changes:
      - Entity gains `canonical_id STRING` (nullable; existing rows default
        to NULL — which means "self is canonical" per D-R5-5).
      - New rel table ALIAS_OF (Entity → Entity) with run_id, created_at,
        algorithm columns — empty at migration time per blueprint §8.3.
      - `_SchemaMeta.schema_version` updated to "2.0".

    Anchor: docs/task74-canonicalization-blueprint.md §5 + §8.3 (#74.1).
    """
    # 1. ALTER Entity to add canonical_id.
    #    Kuzu syntax: ALTER TABLE <name> ADD <column> <type>
    conn.execute("ALTER TABLE Entity ADD canonical_id STRING")

    # 2. Create the ALIAS_OF rel table (the 3rd entry of REL_TABLE_DDL above).
    conn.execute(REL_TABLE_DDL[2])

    # 3. Bump _SchemaMeta to "2.0".
    conn.execute(
        "MATCH (m:_SchemaMeta {key: 'schema_version'}) SET m.value = '2.0'"
    )


# Migration registry keyed by (from_version, to_version).
MIGRATIONS: dict[tuple[str, str], Callable] = {
    ("1.0", "2.0"): _migrate_1_0_to_2_0,
}
