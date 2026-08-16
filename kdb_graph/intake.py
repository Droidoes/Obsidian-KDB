"""apply_compile_result + private helpers — atomic per-run graph intake.

Algorithm per docs/task-graphdb-kdb-blueprint.md §5. Two-phase Source mutation
(Phase 1 scan-refresh + Phase 3 compile-state — Codex v2 NEW M1); atomic
SUPPORTS replacement per source (Codex v2 C2); MOVED transfers SUPPORTS to
destination (Codex v2 M3) and writes only Source-schema-defined fields
(Codex v2 NEW C2 — no `updated_at` on Source; use `last_seen_at`).

#136 (drain-as-you-go): LINKS_TO wiring + deprecation marking are per-run,
in-txn — the Task #91 end-of-run batch passes (standalone `wire_links` /
`detect_deprecations` + the deferral flags) are deleted. Unresolved link
targets pend durably in the PendingLink ledger (schema v2.5) and drain when
the target arrives; pages losing their last SUPPORTS flip `deprecated` via a
per-source diff. Blueprint:
docs/superpowers/archive/specs/2026-08-06-task136-per-source-wiring-blueprint-v0.1.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import kuzu

from kdb_graph.types import IntakeResult

_DEFAULT_SOURCE_TYPE = "obsidian-kdb-raw"
_DEFAULT_ROLE = "primary"
_DEFAULT_ENTITY_STATUS = "active"
# #115 Phase 3 (D-115-12): _DEFAULT_CONFIDENCE deleted — Entity.confidence is
# logically deprecated (never written; dead Kuzu column remains).


# --- body wikilink extraction (#115 T2.4 — graph-owned edge derivation) ---
# Mirrored from compiler.validate_source_response.body_wikilink_slugs:
# kdb_graph imports NO sibling package (B.3), so the extractor is mirrored
# here. Keep the regexes byte-identical to the compiler's.

import re as _re

_SLUG_RE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_WIKILINK_RE = _re.compile(
    rf"(?<!\\)\[\[({_SLUG_RE})(?:#[^|\]]*)?(?:\|[^\]]*)?\]\]"
)
_FENCED_CODE_RE = _re.compile(r"```.*?```", _re.DOTALL)
_INLINE_CODE_RE = _re.compile(r"`[^`\n]*`")


def _strip_code(text: str) -> str:
    return _INLINE_CODE_RE.sub("", _FENCED_CODE_RE.sub("", text))


def body_wikilink_slugs(body: str) -> set[str]:
    """Slug set extracted from [[slug]] / [[slug|alias]] / [[slug#h]] tokens
    in `body`, after stripping code spans. Mirror of the compiler's
    body_wikilink_slugs — the two must not drift."""
    return set(_WIKILINK_RE.findall(_strip_code(body)))


def apply_compile_result(
    cr: dict,
    scan_dict: dict,
    run_id: str,
    *,
    conn: kuzu.Connection,
    now: str | None = None,
) -> IntakeResult:
    """Apply one compile run's deltas to the Kuzu graph (atomic per run).

    #136 (drain-as-you-go): LINKS_TO wiring and deprecation marking happen
    INSIDE this per-run txn — there is no end-of-run batch pass anymore.
    Links whose targets don't exist yet are upserted into the durable
    PendingLink ledger (same txn ⇒ crash-safe); each newly upserted page
    drains the pendings keyed on its slug. Pages losing their last SUPPORTS
    in this commit flip `deprecated` via a per-source set-diff (revive
    symmetric on re-support). The Task #91 deferral flags
    (wire_links/detect_deprecations) and the standalone finalize passes are
    deleted — see blueprint
    docs/superpowers/archive/specs/2026-08-06-task136-per-source-wiring-blueprint-v0.1.md.

    Args:
        cr: compile_result dict (already validated by Stage 4).
        scan_dict: last_scan dict (already validated by Stage 2).
        run_id: run id string.
        conn: open kuzu.Connection.
        now: ISO timestamp; defaults to datetime.now().astimezone().isoformat().

    Returns:
        IntakeResult with counts + newly-deprecated page slugs.

    Raises:
        Any exception from Kuzu during execution; transaction is rolled back first.
    """
    if now is None:
        now = datetime.now().astimezone().isoformat()

    result = IntakeResult(run_id=run_id)

    conn.execute("BEGIN TRANSACTION")
    try:
        # Phase 1: refresh Source nodes from scan (scan-derived fields only)
        for entry in scan_dict.get("files", []):
            _upsert_source_from_scan(conn, entry, run_id, now, result)

        # Phase 2: reconcile MOVED + DELETED sources. DELETED also erases the
        # pages whose only SUPPORTS came from the deleted source (#130 R-130-4).
        for op in scan_dict.get("to_reconcile", []):
            t = op.get("type")
            if t == "MOVED":
                _handle_source_moved(conn, op, run_id, now)
            elif t == "DELETED":
                erased, dead_links = _handle_source_deleted(conn, op, run_id, now)
                result.erased_pages.extend(erased)
                result.erased_dead_links.extend(dead_links)

        # Phase 3: ingest compiled_sources. Two passes within the phase so that
        # cross-entity (and cross-source) references resolve correctly: pass 1
        # upserts every Entity node across all sources first (draining
        # pendings keyed on each slug); pass 2 wires/pends LINKS_TO,
        # SUPPORTS, and the ingest-state update.
        for cs in cr.get("compiled_sources", []):
            for page in cs.get("pages", []):
                _upsert_entity(conn, page, run_id, now, result)
        pre_sets: dict[str, list[str]] = {}
        for cs in cr.get("compiled_sources", []):
            for page in cs.get("pages", []):
                _replace_outgoing_links(conn, page, run_id, now, result)
            pre_sets[cs.get("source_id") or ""] = _replace_supports_for_source(
                conn, cs, run_id, now, result)
            _update_source_ingest_state(conn, cs, run_id, now)
            _write_source_meta(conn, cs)

        # Phase 3.6 (D1-A): derive Domain + BELONGS_TO from Source.domain + SUPPORTS.
        # Runs after SUPPORTS (pass 2) + Source.domain (_write_source_meta) are written.
        rederive_domains(conn, run_id, now, result)

        # Phase 3.5 (#74.5): materialize alias Entity rows + ALIAS_OF edges
        # from canonical_meta.aliases_emitted. Runs after Phase 3 so the
        # canonical entities exist for the ALIAS_OF endpoints to MATCH.
        _upsert_alias_entities_and_edges(conn, cr, run_id, now, result)

        # Phase 4 (#136): per-source deprecation diff — pages that lost their
        # last SUPPORTS in this commit flip deprecated in-txn; emitted pages
        # still marked deprecated revive. Runs after ALL pass-2 SUPPORTS are
        # final, so a cross-source drop+re-support inside one call never
        # produces a transient flip.
        for cs in cr.get("compiled_sources", []):
            _deprecations_for_source(
                conn, cs, pre_sets.get(cs.get("source_id") or "", []),
                run_id, now, result)

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
    result: IntakeResult,
) -> None:
    """Phase 1: scan-refresh only. Does NOT touch ingest-state fields
    (last_ingested_at, ingest_state, ingest_count, last_run_id) — those
    are Phase 3's job per Codex v2 NEW M1. `ON CREATE` seeds ingest-state
    defaults (including last_run_id='') so later Phase 3 increments work
    cleanly.

    Naming note: producer's manifest uses 'run_state/compile_count/last_compiled_at';
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
) -> tuple[list[dict], list[dict]]:
    """Phase 2 DELETED: mark Source as deleted + erase its orphaned pages
    (#130 R-130-4 — source deletion is total erasure, not deprecation).

    A canonical page whose ONLY SUPPORTS came from the deleted source is
    DETACH DELETEd along with its alias rows; pages with another supporting
    source survive untouched. Returns (erased, dead_links):
      erased     — [{slug, page_type}] so the caller can delete the wiki files
                   (graph layer does no I/O);
      dead_links — [{from_slug, to_slug}] surviving pages whose LINKS_TO pointed
                   at erased slugs (their edges die with the node; their wiki
                   bodies keep a dangling [[link]] — reported, never rewritten).
    """
    sid = op.get("source_id") or op.get("from") or op.get("path")
    if not sid:
        return [], []
    # 1. Pages whose only SUPPORTS is this source (canonical only) — captured
    # BEFORE the edge drop.
    erased: list[dict] = []
    r = conn.execute(
        """
        MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(p:Entity)
        WHERE p.canonical_id IS NULL
          AND NOT EXISTS {
              MATCH (s2:Source)-[:SUPPORTS]->(p) WHERE s2.source_id <> $sid
          }
        RETURN p.slug, p.page_type
        """,
        {"sid": sid},
    )
    while r.has_next():
        row = r.get_next()
        erased.append({"slug": row[0], "page_type": row[1]})
    # 2. Drop the source's SUPPORTS edges + mark it deleted.
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
    # 3. Erase: alias rows pointing at the erased canonicals, then the canonicals
    # (DETACH DELETE takes LINKS_TO/BELONGS_TO with the node). Surviving pages'
    # inbound links to the erased slugs are captured first (report-only).
    dead_links: list[dict] = []
    if erased:
        slugs = [e["slug"] for e in erased]
        r3 = conn.execute(
            """
            MATCH (p:Entity)-[:LINKS_TO]->(t:Entity)
            WHERE t.slug IN $slugs AND NOT p.slug IN $slugs
            RETURN DISTINCT p.slug, t.slug
            """,
            {"slugs": slugs},
        )
        while r3.has_next():
            row = r3.get_next()
            dead_links.append({"from_slug": row[0], "to_slug": row[1]})
        conn.execute(
            "MATCH (a:Entity) WHERE a.canonical_id IN $slugs DETACH DELETE a",
            {"slugs": slugs},
        )
        conn.execute(
            """
            MATCH (p:Entity)
            WHERE p.slug IN $slugs AND p.canonical_id IS NULL
            DETACH DELETE p
            """,
            {"slugs": slugs},
        )
        # #136 §3.3: GC pendings SOURCED at the erased pages (their carrier is
        # gone). Pendings keyed on the erased slugs as TARGET stay — a later
        # source may legitimately re-emit that slug (the re-emit revival path,
        # now for links too).
        conn.execute(
            "MATCH (p:PendingLink) WHERE p.source_slug IN $slugs DELETE p",
            {"slugs": slugs},
        )
    return erased, dead_links


# ---------- Phase 3: page + edges + SUPPORTS + compile-state ----------

def _upsert_entity(
    conn: kuzu.Connection,
    page: dict,
    run_id: str,
    now: str,
    result: IntakeResult,
) -> None:
    """Phase 3: upsert an Entity node. `created_at` and `first_run_id` set on first
    INSERT and never overwritten (per §4 design note).

    #74.5 additions for the alias-promoted-to-canonical re-classification case
    (a slug that was an alias is now being declared canonical by appearing in
    pages[]):
      - `canonical_id` is explicitly reset to NULL.
      - Any stale outgoing ALIAS_OF edges are dropped.
    Without these, C1 (`canonical_id IS NOT NULL` ⇔ ALIAS_OF edge exists) and
    C3 (no chains/cycles) would be violated by the lingering alias state.

    Naming note: parameter `page` is a producer-side dict (kdb-compile's term);
    graph-side stores it as an Entity node per D-A1.
    """
    slug = page.get("slug")
    if not slug:
        return
    # #115 Phase 3 (D-115-12): Entity.confidence is logically deprecated —
    # never written (the dead Kuzu column stays until the next destructive
    # schema change). The deprecated page key is ignored, not read.
    conn.execute(
        """
        MERGE (p:Entity {slug: $slug})
        ON CREATE SET p.created_at=$ts, p.first_run_id=$run_id
        SET p.title=$title, p.page_type=$ptype, p.status=$status,
            p.updated_at=$ts, p.last_run_id=$run_id,
            p.canonical_id=NULL
        """,
        {
            "slug": slug,
            "ts": now,
            "run_id": run_id,
            "title": page.get("title", ""),
            "ptype": page.get("page_type", ""),
            "status": page.get("status", _DEFAULT_ENTITY_STATUS),
        },
    )
    # Promotion safety: drop any outgoing ALIAS_OF — this slug is canonical now.
    conn.execute(
        "MATCH (p:Entity {slug: $slug})-[r:ALIAS_OF]->() DELETE r",
        {"slug": slug},
    )
    result.entities_upserted += 1
    _drain_pending_links(conn, slug, run_id, now, result)


def _drain_pending_links(
    conn: kuzu.Connection,
    slug: str,
    run_id: str,
    now: str,
    result: IntakeResult,
) -> None:
    """#136 drain-as-you-go: resolve every PendingLink keyed on `slug` — the
    target now exists, so the pended LINKS_TO edges land in the same txn and
    the ledger rows are deleted (a drain fires once per pending row).

    Invariant (§4.3 of the blueprint): pendings on slug X exist only while no
    Entity X exists, so for an already-existing page this is a no-op. The
    NOT EXISTS guard keeps it duplicate-safe even if that invariant is ever
    violated. Drain lookups are full PendingLink scans (no secondary index
    assumed — R1); the ledger is bounded by outstanding forward references,
    and production commits are per-source, so scans stay small.
    """
    r = conn.execute(
        "MATCH (p:PendingLink {target_slug: $slug}) "
        "RETURN p.link_id, p.source_slug",
        {"slug": slug},
    )
    rows: list[tuple[str, str]] = []
    while r.has_next():
        row = r.get_next()
        rows.append((row[0], row[1]))
    for link_id, source_slug in rows:
        conn.execute(
            """
            MATCH (a:Entity {slug: $a}), (b:Entity {slug: $b})
            WHERE NOT EXISTS { MATCH (a)-[:LINKS_TO]->(b) }
            CREATE (a)-[:LINKS_TO {run_id: $run_id, created_at: $ts}]->(b)
            """,
            {"a": source_slug, "b": slug, "run_id": run_id, "ts": now},
        )
        # The row is resolved (or its carrier is gone — GC-by-drain): delete
        # either way so a drain never fires twice.
        conn.execute(
            "MATCH (p:PendingLink {link_id: $lid}) DELETE p",
            {"lid": link_id},
        )
        result.links_drained += 1


def _replace_outgoing_links(
    conn: kuzu.Connection,
    page: dict,
    run_id: str,
    now: str,
    result: IntakeResult,
) -> None:
    """Phase 3: drop+recreate LINKS_TO edges from this page (current-state
    replacement), extended #136-style to the pending ledger:

    - Target EXISTS as an Entity → CREATE the edge (as before).
    - Target ABSENT → MERGE a durable PendingLink row (same txn ⇒ crash-safe);
      a later commit that upserts the target drains it into an edge. Today's
      silent-skip dangling link becomes durable and queryable.

    Current-state replacement covers the ledger too: pendings SOURCED at this
    page whose target is no longer linked are deleted at rewire — a recompiled
    page that dropped a link must not leave a stale pend that would wire it
    later (batch-equivalence: the deleted batch never wired a link the final
    body lacks)."""
    slug = page.get("slug")
    if not slug:
        return
    # 1. Drop existing outgoing edges.
    conn.execute(
        "MATCH (a:Entity {slug: $slug})-[r:LINKS_TO]->() DELETE r",
        {"slug": slug},
    )
    # 2. Recreate per link target. #115 T2.4: the legacy `outgoing_links`
    # key is preferred when present (historical payloads); new-shape pages
    # derive the target set from body wikilinks.
    targets = page.get("outgoing_links")
    if targets is None:
        body = page.get("body")
        targets = sorted(body_wikilink_slugs(body)) if isinstance(body, str) else []
    # 3. Selective ledger GC: drop this page's pendings whose target fell out
    # of the current target set (stale-pend removal; current targets MERGE
    # below and keep their first_run_id).
    conn.execute(
        "MATCH (p:PendingLink {source_slug: $slug}) "
        "WHERE NOT p.target_slug IN $targets DELETE p",
        {"slug": slug, "targets": list(targets)},
    )
    # 4. Wire what resolves; pend what doesn't (MERGE on link_id — idempotent
    # re-pend: first_run_id preserved, last_run_id bumped).
    for target in targets:
        rb = conn.execute(
            "MATCH (b:Entity {slug: $b}) RETURN COUNT(b)", {"b": target}
        )
        target_exists = rb.has_next() and int(rb.get_next()[0]) > 0
        if target_exists:
            conn.execute(
                """
                MATCH (a:Entity {slug: $a}), (b:Entity {slug: $b})
                CREATE (a)-[:LINKS_TO {run_id: $run_id, created_at: $ts}]->(b)
                """,
                {"a": slug, "b": target, "run_id": run_id, "ts": now},
            )
        else:
            link_id = f"{slug}|{target}"
            rp = conn.execute(
                "MATCH (p:PendingLink {link_id: $lid}) RETURN COUNT(p)",
                {"lid": link_id},
            )
            already_pended = rp.has_next() and int(rp.get_next()[0]) > 0
            conn.execute(
                """
                MERGE (p:PendingLink {link_id: $lid})
                ON CREATE SET p.source_slug=$a, p.target_slug=$b,
                              p.first_run_id=$run_id, p.created_at=$ts
                SET p.last_run_id=$run_id, p.updated_at=$ts
                """,
                {"lid": link_id, "a": slug, "b": target,
                 "run_id": run_id, "ts": now},
            )
            if not already_pended:
                result.links_pended += 1
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
    result: IntakeResult,
) -> list[str]:
    """Phase 3: atomic per-source SUPPORTS replacement (Codex review CRITICAL #2).
    Symmetric to `_replace_outgoing_links` — pages the source no longer
    supports lose their edge; if no other source supports them, Phase 4's
    per-source diff (#136 `_deprecations_for_source`) flags them deprecated.

    Returns the pre-replacement SUPPORTS slug set (captured BEFORE the drop)
    for that Phase-4 diff."""
    source_id = cs.get("source_id")
    if not source_id:
        return []
    # 0. Capture the current SUPPORTS slug set (the Phase-4 diff's pre_set).
    r0 = conn.execute(
        "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(p:Entity) RETURN p.slug",
        {"sid": source_id},
    )
    pre_slugs: list[str] = []
    while r0.has_next():
        pre_slugs.append(r0.get_next()[0])
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
    return pre_slugs


def _deprecations_for_source(
    conn: kuzu.Connection,
    cs: dict,
    pre_slugs: list[str],
    run_id: str,
    now: str,
    result: IntakeResult,
) -> None:
    """Phase 4 (#136): per-source deprecation diff — replaces the deleted
    whole-graph end-of-run scan (`_detect_and_mark_deprecations`).

    lost = pre_set − emitted: pages this source supported before the drop and
    no longer emits. Each lost slug that is canonical AND now has zero
    SUPPORTS (checked against the graph AFTER all of this call's pass-2
    SUPPORTS are final — a cross-source drop+re-support within one call never
    flips) transitions to 'deprecated' (#130 vocabulary; node stays,
    revivable). Emitted slugs still marked 'deprecated' revive (symmetric:
    the re-supporter's commit heals the transient window).

    Alias entities are never eligible: they carry no SUPPORTS by design, so
    they can never appear in either set.
    """
    emitted = {p.get("slug") for p in cs.get("pages", []) if p.get("slug")}
    for slug in pre_slugs:
        if slug in emitted:
            continue
        r = conn.execute(
            """
            MATCH (p:Entity {slug: $slug})
            WHERE p.canonical_id IS NULL
              AND NOT EXISTS { MATCH (:Source)-[:SUPPORTS]->(p) }
              AND p.status <> 'deprecated'
            RETURN p.slug, p.page_type
            """,
            {"slug": slug},
        )
        if not r.has_next():
            continue
        row = r.get_next()
        conn.execute(
            """
            MATCH (p:Entity {slug: $slug})
            SET p.status='deprecated', p.last_run_id=$run_id, p.updated_at=$ts
            """,
            {"slug": slug, "run_id": run_id, "ts": now},
        )
        result.deprecations_detected.append(
            {"slug": row[0], "page_type": row[1]})
    for slug in emitted:
        conn.execute(
            """
            MATCH (p:Entity {slug: $slug})
            WHERE p.status = 'deprecated'
            SET p.status='active', p.last_run_id=$run_id, p.updated_at=$ts
            """,
            {"slug": slug, "run_id": run_id, "ts": now},
        )


def _update_source_ingest_state(
    conn: kuzu.Connection,
    cs: dict,
    run_id: str,
    now: str,
) -> None:
    """Phase 3: ingest-state-only update; fires only for sources in
    `cr.compiled_sources`. Increments `ingest_count` and stamps ingest
    metadata. Phase 1 left these fields untouched (Codex v2 NEW M1).

    Naming note: reads producer-side 'run_state' when present; accepts legacy
    'compile_state' from older replay payloads; writes graph-side 'ingest_state'
    per D-A2.
    """
    source_id = cs.get("source_id")
    if not source_id:
        return
    compile_meta = cs.get("compile_meta", {}) or {}
    state = _normalize_source_run_state(
        compile_meta.get("run_state")
        or cs.get("run_state")
        or compile_meta.get("compile_state")
        or cs.get("compile_state")
        or "in_graph_db"
    )
    conn.execute(
        """
        MATCH (s:Source {source_id: $sid})
        SET s.last_ingested_at=$ts, s.ingest_state=$state,
            s.ingest_count = s.ingest_count + 1, s.last_run_id=$run_id
        """,
        {"sid": source_id, "ts": now, "state": state, "run_id": run_id},
    )


def _normalize_source_run_state(value: object) -> str:
    """Normalize producer lifecycle state before writing Source.ingest_state."""
    aliases = {
        "metadata_only": "no_graph_db",
        "compiled": "in_graph_db",
        "recompiled": "in_graph_db",
        "error": "error_compile",
    }
    text = str(value)
    return aliases.get(text, text)


def _write_source_meta(
    conn: kuzu.Connection,
    cs: dict,
) -> None:
    """Phase 3 (D-89-17): write Pass-1 frontmatter fields to Source node.

    Fires only when `source_meta` is present in the compiled_source entry.
    Writes summary, author, domain unconditionally; writes source_type only
    when present in source_meta (Bug #1 fix 2026-05-26 night per D-89-17 +
    v0.2.2 amendment — Pass-1's source_type classification flows through to
    the Source node, replacing the first-time-create default).

    When source_meta is absent the SET is skipped entirely; existing NULL
    columns remain NULL (backward-compat: compile_results without source_meta
    stay valid; source_type stays at the first-create default).
    """
    source_id = cs.get("source_id")
    source_meta = cs.get("source_meta")
    if not source_id or not source_meta:
        return
    conn.execute(
        """
        MATCH (s:Source {source_id: $sid})
        SET s.summary=$summary, s.author=$author, s.domain=$domain
        """,
        {
            "sid": source_id,
            "summary": source_meta.get("summary"),
            "author": source_meta.get("author"),
            "domain": source_meta.get("domain"),
        },
    )
    source_type = source_meta.get("source_type")
    if source_type is not None:
        conn.execute(
            """
            MATCH (s:Source {source_id: $sid})
            SET s.source_type=$source_type
            """,
            {"sid": source_id, "source_type": source_type},
        )


# ---------- Phase 3.6: Domain nodes + BELONGS_TO edges (D1-A, derived) ----------

def rederive_domains(
    conn: kuzu.Connection,
    run_id: str,
    now: str,
    result: IntakeResult,
) -> None:
    """D1-A: derive Domain nodes + BELONGS_TO edges from Source.domain + SUPPORTS.

    Replaces the per-page LLM domain (removed in 0.5.0). Domain is a coordinate
    inherited from provenance: an Entity BELONGS_TO every Domain D such that some
    Source with `Source.domain == D` SUPPORTS it. `support_count` = number of
    distinct such sources (a filterable strength signal — high = strong anchor,
    1 = incidental). Canonical-only: alias entities (canonical_id non-null) are
    skipped. Fully recomputable: the projection is DELETED and rebuilt from
    authority on every call, so it can never go stale (and `graphdb-kdb rebuild`
    gets it for free by replaying compile_result.json).
    """
    # 1. Clear the derived projection (recomputed from authority each call).
    conn.execute("MATCH (:Entity)-[r:BELONGS_TO]->(:Domain) DELETE r")
    conn.execute("MATCH (d:Domain) DELETE d")

    # 2. Pull (entity_slug, source_domain, source_id) for canonical entities
    #    supported by a domain-classified source. Source.domain values are the
    #    Pass-1 controlled vocabulary (already kebab-case ids) — no normalization.
    r = conn.execute(
        """
        MATCH (s:Source)-[:SUPPORTS]->(e:Entity)
        WHERE s.domain IS NOT NULL AND s.domain <> '' AND e.canonical_id IS NULL
        RETURN e.slug, s.domain, s.source_id
        """
    )
    agg: dict[tuple[str, str], set[str]] = {}
    while r.has_next():
        slug, dom, sid = r.get_next()
        agg.setdefault((slug, dom), set()).add(sid)

    # 3. Materialize Domain nodes + BELONGS_TO edges with support_count.
    domains_seen: set[str] = set()
    for (slug, dom), sids in agg.items():
        if dom not in domains_seen:
            # NOTE: because the projection is deleted and rebuilt on every call,
            # first_run_id/created_at reflect the latest rederive, not true
            # first-seen. Acceptable: the verifier treats Domain as existence-only.
            conn.execute(
                "MERGE (d:Domain {name: $name}) "
                "ON CREATE SET d.created_at=$ts, d.first_run_id=$run_id",
                {"name": dom, "ts": now, "run_id": run_id},
            )
            domains_seen.add(dom)
        conn.execute(
            "MATCH (e:Entity {slug: $slug}), (d:Domain {name: $name}) "
            "MERGE (e)-[r:BELONGS_TO]->(d) "
            "SET r.run_id=$run_id, r.created_at=$ts, r.support_count=$cnt",
            {"slug": slug, "name": dom, "run_id": run_id, "ts": now, "cnt": len(sids)},
        )
    result.domains_upserted = len(domains_seen)
    result.belongs_to_upserted = len(agg)


# ---------- Phase 3.5: alias Entity + ALIAS_OF writes (#74.5) ----------

def _upsert_alias_entities_and_edges(
    conn: kuzu.Connection,
    cr: dict,
    run_id: str,
    now: str,
    result: IntakeResult,
) -> None:
    """Phase 3.5 (#74.5): materialize alias Entity rows + ALIAS_OF edges from
    canonical_meta.aliases_emitted.

    For each entry:
      1. MERGE an Entity row for the alias slug with `canonical_id` set to
         the (chain-flattened, D-R5-13) canonical slug. `status` and
         `page_type` are 'alias' so canonical-taxonomy queries naturally
         skip these rows.
      2. Drop any existing outgoing ALIAS_OF (D-R5-13 flat invariant: at
         most one ALIAS_OF per alias).
      3. CREATE one fresh ALIAS_OF edge carrying run_id + algorithm
         provenance from canonical_meta.

    Self-loops (alias_slug == canonical_slug) are skipped defensively —
    Stage 6 should never emit them but the adapter is a graph-invariant
    guardian, not a Stage 6 client.

    Missing-canonical case (canonical not in the graph): the MATCH-then-CREATE
    pattern silently no-ops the edge; the alias Entity still carries
    `canonical_id` so #74.6's C1 verifier will catch the inconsistency.
    Mirrors how `_replace_outgoing_links` handles dangling targets.

    Idempotency: re-applying the same `canonical_meta` produces the same
    graph state — one ALIAS_OF per alias, with the most recent run's
    `run_id`/`created_at`. Older provenance lives in the per-run sidecar
    `state/runs/<run_id>/compile_result.json` (archived by the orchestrator's
    journal writer, #132).
    """
    canonical_meta = cr.get("canonical_meta") or {}
    aliases = canonical_meta.get("aliases_emitted") or []
    for entry in aliases:
        alias_slug = entry.get("alias_slug")
        canonical_slug = entry.get("canonical_slug")
        algorithm = entry.get("algorithm") or "ledger"
        if not alias_slug or not canonical_slug:
            continue
        if alias_slug == canonical_slug:
            # Self-loop defense — Stage 6 shouldn't emit these.
            continue

        # 1. Upsert alias Entity with canonical_id pointing at root canonical.
        # #115 Phase 3 (D-115-12): no confidence write (logically deprecated).
        conn.execute(
            """
            MERGE (a:Entity {slug: $alias})
            ON CREATE SET a.created_at=$ts, a.first_run_id=$run_id,
                          a.title='', a.page_type='alias'
            SET a.canonical_id=$canonical, a.status='alias',
                a.updated_at=$ts, a.last_run_id=$run_id
            """,
            {
                "alias": alias_slug, "canonical": canonical_slug,
                "ts": now, "run_id": run_id,
            },
        )
        result.entities_upserted += 1

        # 2. Drop any existing outgoing ALIAS_OF — flat invariant (D-R5-13).
        conn.execute(
            "MATCH (a:Entity {slug: $alias})-[r:ALIAS_OF]->() DELETE r",
            {"alias": alias_slug},
        )

        # 3. Fresh ALIAS_OF with run_id + algorithm provenance. Count from
        # the graph (mirrors _replace_outgoing_links / _replace_supports_for_source
        # convention: report the count of edges this pass actually created).
        # MATCH-then-CREATE silently no-ops if the canonical is absent, so
        # we query post-CREATE for the truth.
        conn.execute(
            """
            MATCH (a:Entity {slug: $alias}), (c:Entity {slug: $canonical})
            CREATE (a)-[:ALIAS_OF {run_id: $run_id, created_at: $ts,
                                   algorithm: $algo}]->(c)
            """,
            {
                "alias": alias_slug, "canonical": canonical_slug,
                "run_id": run_id, "ts": now, "algo": algorithm,
            },
        )
        r = conn.execute(
            "MATCH (a:Entity {slug: $alias})-[r:ALIAS_OF]->() RETURN COUNT(r)",
            {"alias": alias_slug},
        )
        if r.has_next():
            result.alias_of_upserted += int(r.get_next()[0])


# ---------- Cleanup retraction (#68) ----------

def apply_cleanup(
    retraction: dict,
    run_id: str,
    *,
    conn: kuzu.Connection,
) -> IntakeResult:
    """Retract entities a `kdb-clean orphans` run removed (#68).

    DETACH DELETEs the Entity node — and its LINKS_TO + SUPPORTS edges — for
    every slug in `retraction['retracted_slugs']`, and ONLY those slugs.
    `retracted_slugs` is the slug-safe key set the historical `kdb-clean
    orphans` reap computed (#68; the helper was deleted in #133 — reaped slugs
    no surviving active page provides); the full `reaped` page list in the
    retraction payload is audit-only and is NOT used for deletion.

    Atomic per run, mirroring apply_compile_result's transaction handling.

    Args:
        retraction: retraction payload dict (`retracted_slugs`, `reaped`, ...).
        run_id: cleanup run id string.
        conn: open kuzu.Connection.

    Returns:
        IntakeResult with `entities_deleted` set to the count of nodes actually
        removed (a retracted slug already absent from the graph is a no-op).
    """
    result = IntakeResult(run_id=run_id)

    conn.execute("BEGIN TRANSACTION")
    try:
        for slug in retraction.get("retracted_slugs", []):
            r = conn.execute(
                "MATCH (e:Entity {slug: $slug}) RETURN COUNT(e)", {"slug": slug}
            )
            existed = r.has_next() and int(r.get_next()[0]) > 0
            if existed:
                conn.execute(
                    "MATCH (e:Entity {slug: $slug}) DETACH DELETE e",
                    {"slug": slug},
                )
                result.entities_deleted += 1
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise

    return result
