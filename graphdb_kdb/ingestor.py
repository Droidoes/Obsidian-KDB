"""apply_compile_result + private helpers — atomic per-run graph ingestion.

Algorithm per docs/task-graphdb-kdb-blueprint.md §5. Two-phase Source mutation
(Phase 1 scan-refresh + Phase 3 compile-state — Codex v2 NEW M1); atomic
SUPPORTS replacement per source (Codex v2 C2); MOVED transfers SUPPORTS to
destination (Codex v2 M3) and writes only Source-schema-defined fields
(Codex v2 NEW C2 — no `updated_at` on Source; use `last_seen_at`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import kuzu

from graphdb_kdb.types import SyncResult

_DEFAULT_SOURCE_TYPE = "obsidian-kdb-raw"
_DEFAULT_ROLE = "primary"
_DEFAULT_ENTITY_STATUS = "active"
_DEFAULT_CONFIDENCE = "medium"


def apply_compile_result(
    cr: dict,
    scan_dict: dict,
    run_id: str,
    *,
    conn: kuzu.Connection,
    now: str | None = None,
) -> SyncResult:
    """Apply one compile run's deltas to the Kuzu graph (atomic per run).

    Args:
        cr: compile_result dict (already validated by Stage 4).
        scan_dict: last_scan dict (already validated by Stage 2).
        run_id: run id string.
        conn: open kuzu.Connection.
        now: ISO timestamp; defaults to datetime.now().astimezone().isoformat().

    Returns:
        SyncResult with counts + newly-orphaned page slugs.

    Raises:
        Any exception from Kuzu during execution; transaction is rolled back first.
    """
    if now is None:
        now = datetime.now().astimezone().isoformat()

    result = SyncResult(run_id=run_id)

    conn.execute("BEGIN TRANSACTION")
    try:
        # Phase 1: refresh Source nodes from scan (scan-derived fields only)
        for entry in scan_dict.get("files", []):
            _upsert_source_from_scan(conn, entry, run_id, now, result)

        # Phase 2: reconcile MOVED + DELETED sources
        for op in scan_dict.get("to_reconcile", []):
            t = op.get("type")
            if t == "MOVED":
                _handle_source_moved(conn, op, run_id, now)
            elif t == "DELETED":
                _handle_source_deleted(conn, op, run_id, now)

        # Phase 3: ingest compiled_sources. Two passes within the phase so that
        # cross-entity (and cross-source) references resolve correctly: pass 1
        # upserts every Entity node across all sources first; pass 2 wires LINKS_TO,
        # SUPPORTS, and the ingest-state update.
        for cs in cr.get("compiled_sources", []):
            for page in cs.get("pages", []):
                _upsert_entity(conn, page, run_id, now, result)
        for cs in cr.get("compiled_sources", []):
            for page in cs.get("pages", []):
                _replace_outgoing_links(conn, page, run_id, now, result)
            _replace_supports_for_source(conn, cs, run_id, now, result)
            _update_source_ingest_state(conn, cs, run_id, now)

        # Phase 4: orphan detection (mark orphans + revive previously-orphaned pages
        # that have regained SUPPORTS)
        result.orphans_detected = _detect_and_mark_orphans(conn, run_id, now)

        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            # Best-effort rollback; surface the original exception either way.
            pass
        raise

    return result


# ---------- Phase 1: Source scan refresh ----------

def _upsert_source_from_scan(
    conn: kuzu.Connection,
    entry: dict,
    run_id: str,
    now: str,
    result: SyncResult,
) -> None:
    """Phase 1: scan-refresh only. Does NOT touch ingest-state fields
    (last_ingested_at, ingest_state, ingest_count, last_run_id) — those
    are Phase 3's job per Codex v2 NEW M1. `ON CREATE` seeds ingest-state
    defaults (including last_run_id='') so later Phase 3 increments work
    cleanly.

    Naming note: producer's payload uses 'compile_state/count/last_compiled_at';
    graph-side renames to 'ingest_*' per D-A2. Reads stay producer-side; writes
    use graph-side names.

    last_run_id invariant (#63.7 fix 2026-05-14): graph's `last_run_id`
    must mirror manifest's `last_run_id`, which is bumped only on
    Phase-3-equivalent compile events — NOT on every scan. Bumping it
    here would cause spurious `attribute_mismatch` divergences for any
    run that scans a source without compiling it (verified empirically
    in #63.7-A1).
    """
    source_id = entry.get("path") or entry.get("source_id")
    if not source_id:
        return
    conn.execute(
        """
        MERGE (s:Source {source_id: $sid})
        ON CREATE SET s.first_seen_at=$ts, s.source_type=$stype,
                      s.ingest_count=0, s.last_ingested_at='',
                      s.ingest_state='', s.last_run_id='', s.moved_to=''
        SET s.canonical_path=$path, s.hash=$hash, s.size_bytes=$size,
            s.file_type=$ftype, s.status='active',
            s.last_seen_at=$ts
        """,
        {
            "sid": source_id,
            "ts": now,
            "stype": _DEFAULT_SOURCE_TYPE,
            "path": entry.get("path", source_id),
            "hash": entry.get("current_hash", entry.get("hash", "")),
            "size": int(entry.get("size_bytes", 0)),
            "ftype": entry.get("file_type", "markdown"),
        },
    )
    result.sources_upserted += 1


# ---------- Phase 2: MOVED + DELETED reconciliation ----------

def _handle_source_moved(
    conn: kuzu.Connection,
    op: dict,
    run_id: str,
    now: str,
) -> None:
    """Phase 2 MOVED: transfer SUPPORTS edges from old to new Source;
    mark old as moved (historical breadcrumb). Writes only fields defined
    in the Source schema (no `updated_at` — uses `last_seen_at`).
    """
    old_sid = op.get("from_source_id") or op.get("from") or op.get("old_source_id")
    new_sid = op.get("to_source_id") or op.get("to") or op.get("new_source_id")
    if not old_sid or not new_sid:
        return

    # Transfer SUPPORTS edges from old to new Source. Done in three queries to
    # work around Kuzu's strict WITH-scope semantics (`r` cannot be carried
    # past a DELETE r in the same MATCH...WITH chain):
    #   1. Read the old source's SUPPORTS edges into Python.
    #   2. Drop them.
    #   3. Recreate them on the new source with the original edge attributes.
    r = conn.execute(
        """
        MATCH (old:Source {source_id: $old})-[r:SUPPORTS]->(p:Entity)
        RETURN p.slug, r.role, r.hash_at_time, r.run_id, r.created_at
        """,
        {"old": old_sid},
    )
    transfers: list[tuple[str, str, str, str, str]] = []
    while r.has_next():
        row = r.get_next()
        transfers.append((row[0], row[1] or "", row[2] or "", row[3] or "", row[4] or ""))

    conn.execute(
        "MATCH (old:Source {source_id: $old})-[r:SUPPORTS]->() DELETE r",
        {"old": old_sid},
    )

    for slug, role, hash_, rid, cts in transfers:
        conn.execute(
            """
            MATCH (new:Source {source_id: $new}), (p:Entity {slug: $slug})
            CREATE (new)-[:SUPPORTS {role: $role, hash_at_time: $hash, run_id: $rid, created_at: $cts}]->(p)
            """,
            {"new": new_sid, "slug": slug, "role": role, "hash": hash_, "rid": rid, "cts": cts},
        )

    # Mark old as moved — only schema-defined fields.
    conn.execute(
        """
        MATCH (old:Source {source_id: $old})
        SET old.status='moved', old.moved_to=$new,
            old.last_run_id=$run_id, old.last_seen_at=$ts
        """,
        {"old": old_sid, "new": new_sid, "run_id": run_id, "ts": now},
    )


def _handle_source_deleted(
    conn: kuzu.Connection,
    op: dict,
    run_id: str,
    now: str,
) -> None:
    """Phase 2 DELETED: mark Source as deleted. Existing SUPPORTS edges
    remain (left for orphan detection to flag dependent pages)."""
    sid = op.get("source_id") or op.get("from") or op.get("path")
    if not sid:
        return
    # Drop the source's SUPPORTS edges (page state is reflected in orphan detection).
    conn.execute(
        "MATCH (s:Source {source_id: $sid})-[r:SUPPORTS]->() DELETE r",
        {"sid": sid},
    )
    conn.execute(
        """
        MATCH (s:Source {source_id: $sid})
        SET s.status='deleted', s.last_run_id=$run_id, s.last_seen_at=$ts
        """,
        {"sid": sid, "run_id": run_id, "ts": now},
    )


# ---------- Phase 3: page + edges + SUPPORTS + compile-state ----------

def _upsert_entity(
    conn: kuzu.Connection,
    page: dict,
    run_id: str,
    now: str,
    result: SyncResult,
) -> None:
    """Phase 3: upsert an Entity node. `created_at` and `first_run_id` set on first
    INSERT and never overwritten (per §4 design note).

    Naming note: parameter `page` is a producer-side dict (kdb-compile's term);
    graph-side stores it as an Entity node per D-A1.
    """
    slug = page.get("slug")
    if not slug:
        return
    conn.execute(
        """
        MERGE (p:Entity {slug: $slug})
        ON CREATE SET p.created_at=$ts, p.first_run_id=$run_id
        SET p.title=$title, p.page_type=$ptype, p.status=$status,
            p.confidence=$conf, p.updated_at=$ts, p.last_run_id=$run_id
        """,
        {
            "slug": slug,
            "ts": now,
            "run_id": run_id,
            "title": page.get("title", ""),
            "ptype": page.get("page_type", ""),
            "status": page.get("status", _DEFAULT_ENTITY_STATUS),
            "conf": page.get("confidence", _DEFAULT_CONFIDENCE),
        },
    )
    result.entities_upserted += 1


def _replace_outgoing_links(
    conn: kuzu.Connection,
    page: dict,
    run_id: str,
    now: str,
    result: SyncResult,
) -> None:
    """Phase 3: drop+recreate LINKS_TO edges from this page (current-state
    replacement). If a target slug doesn't yet exist as an Entity node, the
    CREATE is silently skipped — dangling outgoing_links are a validator
    catch upstream, not the ingestor's job."""
    slug = page.get("slug")
    if not slug:
        return
    # 1. Drop existing outgoing edges.
    conn.execute(
        "MATCH (a:Entity {slug: $slug})-[r:LINKS_TO]->() DELETE r",
        {"slug": slug},
    )
    # 2. Recreate per outgoing_links entry. The MATCH-with-two-patterns
    # form silently skips when target doesn't exist.
    for target in page.get("outgoing_links", []):
        conn.execute(
            """
            MATCH (a:Entity {slug: $a}), (b:Entity {slug: $b})
            CREATE (a)-[:LINKS_TO {run_id: $run_id, created_at: $ts}]->(b)
            """,
            {"a": slug, "b": target, "run_id": run_id, "ts": now},
        )
    # Count edges actually created from this page (truth from the graph).
    r = conn.execute(
        "MATCH (a:Entity {slug: $slug})-[r:LINKS_TO]->() RETURN COUNT(r)",
        {"slug": slug},
    )
    if r.has_next():
        result.edges_upserted += int(r.get_next()[0])


def _replace_supports_for_source(
    conn: kuzu.Connection,
    cs: dict,
    run_id: str,
    now: str,
    result: SyncResult,
) -> None:
    """Phase 3: atomic per-source SUPPORTS replacement (Codex review CRITICAL #2).
    Symmetric to `_replace_outgoing_links` — pages the source no longer
    supports lose their edge; if no other source supports them, Phase 4
    flags them orphan_candidate."""
    source_id = cs.get("source_id")
    if not source_id:
        return
    # 1. Drop all existing SUPPORTS edges from this source.
    conn.execute(
        "MATCH (s:Source {source_id: $sid})-[r:SUPPORTS]->() DELETE r",
        {"sid": source_id},
    )
    # 2. Recreate one SUPPORTS edge per page in the current compiled_source entry.
    compile_meta = cs.get("compile_meta", {}) or {}
    hash_at_time = compile_meta.get("hash", compile_meta.get("source_hash", ""))
    for page in cs.get("pages", []):
        slug = page.get("slug")
        if not slug:
            continue
        conn.execute(
            """
            MATCH (s:Source {source_id: $sid}), (p:Entity {slug: $slug})
            CREATE (s)-[:SUPPORTS {role: $role, hash_at_time: $hash, run_id: $run_id, created_at: $ts}]->(p)
            """,
            {
                "sid": source_id,
                "slug": slug,
                "role": _DEFAULT_ROLE,
                "hash": hash_at_time,
                "run_id": run_id,
                "ts": now,
            },
        )
    # Count edges actually created from this source (truth from the graph).
    r = conn.execute(
        "MATCH (s:Source {source_id: $sid})-[r:SUPPORTS]->() RETURN COUNT(r)",
        {"sid": source_id},
    )
    if r.has_next():
        result.supports_upserted += int(r.get_next()[0])


def _update_source_ingest_state(
    conn: kuzu.Connection,
    cs: dict,
    run_id: str,
    now: str,
) -> None:
    """Phase 3: ingest-state-only update; fires only for sources in
    `cr.compiled_sources`. Increments `ingest_count` and stamps ingest
    metadata. Phase 1 left these fields untouched (Codex v2 NEW M1).

    Naming note: reads producer-side 'compile_state' (from compile_meta /
    compiled_source dicts); writes graph-side 'ingest_state' per D-A2.
    """
    source_id = cs.get("source_id")
    if not source_id:
        return
    compile_meta = cs.get("compile_meta", {}) or {}
    state = compile_meta.get("compile_state") or cs.get("compile_state") or "compiled"
    conn.execute(
        """
        MATCH (s:Source {source_id: $sid})
        SET s.last_ingested_at=$ts, s.ingest_state=$state,
            s.ingest_count = s.ingest_count + 1, s.last_run_id=$run_id
        """,
        {"sid": source_id, "ts": now, "state": state, "run_id": run_id},
    )


# ---------- Phase 4: orphan detection + revival ----------

def _detect_and_mark_orphans(
    conn: kuzu.Connection,
    run_id: str,
    now: str,
) -> list[str]:
    """Phase 4: mark Entities with zero SUPPORTS as orphan_candidate; revive
    previously-orphaned entities that have regained SUPPORTS. Returns the
    list of NEWLY orphan_candidate slugs (not revivals)."""
    # Find newly-orphaned pages (no SUPPORTS, not already marked).
    r = conn.execute(
        """
        MATCH (p:Entity)
        WHERE NOT EXISTS { MATCH (:Source)-[:SUPPORTS]->(p) }
          AND p.status <> 'orphan_candidate'
        RETURN p.slug
        """
    )
    new_orphans: list[str] = []
    while r.has_next():
        new_orphans.append(r.get_next()[0])
    for slug in new_orphans:
        conn.execute(
            """
            MATCH (p:Entity {slug: $slug})
            SET p.status='orphan_candidate', p.last_run_id=$run_id, p.updated_at=$ts
            """,
            {"slug": slug, "run_id": run_id, "ts": now},
        )

    # Revive previously-orphaned pages that now have SUPPORTS.
    r2 = conn.execute(
        """
        MATCH (p:Entity)
        WHERE p.status = 'orphan_candidate'
          AND EXISTS { MATCH (:Source)-[:SUPPORTS]->(p) }
        RETURN p.slug
        """
    )
    revivals: list[str] = []
    while r2.has_next():
        revivals.append(r2.get_next()[0])
    for slug in revivals:
        conn.execute(
            """
            MATCH (p:Entity {slug: $slug})
            SET p.status='active', p.last_run_id=$run_id, p.updated_at=$ts
            """,
            {"slug": slug, "run_id": run_id, "ts": now},
        )

    return new_orphans
