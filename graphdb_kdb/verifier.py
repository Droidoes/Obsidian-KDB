"""Replay-to-temp structural equality verifier (D50 Phase G).

Proves graph integrity by replaying journals into a temp Kuzu, then
structurally diffing temp (expected) vs live (actual). Three layers:

  Layer 1 — source-state preflight: cheap manifest.sources{} vs graph
            Source nodes check. Catches obvious drift without a full rebuild.

  Layer 2 — replay structural diff: rebuild() into a temp Kuzu, then
            diff ALL graph state (entities, sources, links, supports) between
            the replay graph (expected) and the live graph (actual).

  Layer 3 — canonicalization invariants (#74.6): pure live-graph Cypher
            checks for C1–C4 from docs/task74-canonicalization-blueprint.md
            §9.1. No sidecar reads, no rebuild — cheapest of the three
            layers and runs first so it gives feedback even when replay
            cannot complete.

Divergence classes:
  - missing_in_live      — present in replay, absent in live graph
  - missing_in_replay    — present in live, absent in replay
  - attribute_mismatch   — both present but tracked fields differ
  - invariant_violation  — live graph violates a canonicalization invariant
                           (#74.6); field carries the constraint code
                           ('C1'|'C2'|'C3'|'C4')

Each divergence carries a `source` tag: 'source_state_preflight',
'replay_structural_diff', or 'canonicalization_invariants', so consumers
can separate cheap-check results from the authoritative replay proof.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import kuzu

from graphdb_kdb.graphdb import GraphDB


# ---------- result types ----------

@dataclass(frozen=True)
class Divergence:
    kind: str       # 'missing_in_live' | 'missing_in_replay' | 'attribute_mismatch'
    category: str   # 'entity' | 'source' | 'links_to' | 'supports' | 'domain' | 'belongs_to'
    key: str        # slug | source_id | 'a→b' | 'sid→slug' | domain name | 'slug→domain'
    source: str     # 'source_state_preflight' | 'replay_structural_diff'
    field: str | None = None
    expected_value: Any = None
    actual_value: Any = None


@dataclass
class VerifyResult:
    ok: bool
    rebuild_failed: bool = False
    rebuild_error: str | None = None
    divergences: list[Divergence] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


# ---------- attribute maps ----------

_SOURCE_DIRECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("status", "status"),
    ("run_state", "ingest_state"),
    ("compile_count", "ingest_count"),
    ("hash", "hash"),
    ("file_type", "file_type"),
    ("size_bytes", "size_bytes"),
    ("last_run_id", "last_run_id"),
)

_ENTITY_DIRECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("page_type", "page_type"),
    ("status", "status"),
    ("confidence", "confidence"),
    ("last_run_id", "last_run_id"),
)


# ---------- graph state loaders ----------

def _graph_entities(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    r = conn.execute(
        "MATCH (e:Entity) "
        "RETURN e.slug, e.page_type, e.status, e.confidence, e.last_run_id"
    )
    out: dict[str, dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[row[0]] = {
            "slug": row[0],
            "page_type": row[1],
            "status": row[2],
            "confidence": row[3],
            "last_run_id": row[4],
        }
    return out


def _graph_sources(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    r = conn.execute(
        "MATCH (s:Source) "
        "RETURN s.source_id, s.status, s.ingest_state, s.ingest_count, "
        "       s.hash, s.file_type, s.size_bytes, s.last_run_id, "
        "       s.summary, s.author, s.domain"
    )
    out: dict[str, dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[row[0]] = {
            "source_id": row[0],
            "status": row[1],
            "ingest_state": row[2],
            "ingest_count": int(row[3]) if row[3] is not None else 0,
            "hash": row[4],
            "file_type": row[5],
            "size_bytes": int(row[6]) if row[6] is not None else 0,
            "last_run_id": row[7],
            # #89 D-89-17: Pass-1 frontmatter fields — NULL until Pass-1 runs.
            "summary": row[8],
            "author": row[9],
            "domain": row[10],
        }
    return out


def _graph_links(conn: kuzu.Connection) -> set[tuple[str, str]]:
    r = conn.execute("MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug")
    out: set[tuple[str, str]] = set()
    while r.has_next():
        row = r.get_next()
        out.add((row[0], row[1]))
    return out


def _graph_supports(conn: kuzu.Connection) -> set[tuple[str, str]]:
    r = conn.execute(
        "MATCH (s:Source)-[:SUPPORTS]->(e:Entity) RETURN s.source_id, e.slug"
    )
    out: set[tuple[str, str]] = set()
    while r.has_next():
        row = r.get_next()
        out.add((row[0], row[1]))
    return out


# #79: schema v2.1 — Domain nodes + BELONGS_TO edges (#76 follow-up).
# Domain is existence-only (created_at/first_run_id are provenance, skipped
# per the same pattern that skips Entity.created_at/Source.first_seen_at).
# BELONGS_TO tracks sub_domain as a real data field; run_id is provenance
# (set ON MATCH on every re-write) and follows the SUPPORTS pattern of not
# being tracked in attribute diffs.

def _graph_domains(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    r = conn.execute("MATCH (d:Domain) RETURN d.name")
    out: dict[str, dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[row[0]] = {"name": row[0]}
    return out


def _graph_belongs_to(
    conn: kuzu.Connection,
) -> dict[tuple[str, str], dict[str, Any]]:
    r = conn.execute(
        "MATCH (e:Entity)-[r:BELONGS_TO]->(d:Domain) "
        "RETURN e.slug, d.name, r.sub_domain"
    )
    out: dict[tuple[str, str], dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[(row[0], row[1])] = {
            "entity_slug": row[0],
            "domain_name": row[1],
            "sub_domain": row[2],
        }
    return out


# --- #83/#84 Claim-layer collectors (schema v2.2) -------------------------
#
# Claim-layer state isn't yet recreated by the rebuilder (rebuild is supposed
# to "re-run the Promotion Contract against the restored compilation state"
# per blueprint §6, but that requires the O1 pipeline replay-side, deferred).
# So the structural diff for Claim-layer tables would always show
# `missing_in_replay` for any live Claims (replay starts empty).
#
# Pragmatic v1: collectors run on both replay + live, but the diff is
# **scope-limited to keys present in BOTH** sides. Live-only Claims aren't
# flagged as drift — they're just acknowledged as "not yet replay-derivable".
# When the rebuild's promotion-replay lands, this diff tightens to strict
# equality (parallel to how Domain/BELONGS_TO became strict in #79).

def _graph_claims(conn: kuzu.Connection) -> dict[str, dict[str, Any]]:
    r = conn.execute(
        "MATCH (c:Claim) RETURN c.claim_id, c.claim_family_id, c.state, c.version"
    )
    out: dict[str, dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[row[0]] = {
            "claim_id": row[0],
            "claim_family_id": row[1],
            "state": row[2],
            "version": row[3],
        }
    return out


def _graph_evidences(conn: kuzu.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    r = conn.execute(
        "MATCH (s:Source)-[r:EVIDENCES]->(c:Claim) "
        "RETURN s.source_id, c.claim_id, r.provenance_type"
    )
    out: dict[tuple[str, str], dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[(row[0], row[1])] = {
            "source_id": row[0], "claim_id": row[1], "provenance_type": row[2],
        }
    return out


def _graph_about(conn: kuzu.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    r = conn.execute(
        "MATCH (c:Claim)-[r:ABOUT]->(e:Entity) RETURN c.claim_id, e.slug"
    )
    out: dict[tuple[str, str], dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[(row[0], row[1])] = {"claim_id": row[0], "entity_slug": row[1]}
    return out


def _graph_claim_claim_edges(
    conn: kuzu.Connection, edge_name: str
) -> dict[tuple[str, str], dict[str, Any]]:
    r = conn.execute(
        f"MATCH (a:Claim)-[r:{edge_name}]->(b:Claim) RETURN a.claim_id, b.claim_id"
    )
    out: dict[tuple[str, str], dict[str, Any]] = {}
    while r.has_next():
        row = r.get_next()
        out[(row[0], row[1])] = {"from_claim_id": row[0], "to_claim_id": row[1]}
    return out


# ---------- manifest projection (source-state preflight only) ----------

def _manifest_sources(manifest: dict) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for sid, src in (manifest.get("sources") or {}).items():
        out[sid] = {
            "source_id": sid,
            "status": src.get("status"),
            "run_state": src.get("run_state"),
            "compile_count": int(src.get("compile_count") or 0),
            "hash": src.get("hash"),
            "file_type": src.get("file_type"),
            "size_bytes": int(src.get("size_bytes") or 0),
            "last_run_id": src.get("last_run_id"),
        }
    return out


# ---------- diff helpers ----------

def _diff_attrs(
    *,
    category: str,
    key: str,
    source: str,
    expected_row: dict[str, Any],
    actual_row: dict[str, Any],
    fields: tuple[tuple[str, str], ...],
) -> list[Divergence]:
    out: list[Divergence] = []
    for efield, afield in fields:
        ev = expected_row.get(efield)
        av = actual_row.get(afield)
        if ev != av:
            out.append(Divergence(
                kind="attribute_mismatch",
                category=category,
                key=key,
                source=source,
                field=efield,
                expected_value=ev,
                actual_value=av,
            ))
    return out


def _diff_sources_preflight(
    manifest_sources: dict[str, dict],
    live_sources: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "source_state_preflight"
    for sid in sorted(manifest_sources.keys() - live_sources.keys()):
        divs.append(Divergence(kind="missing_in_live", category="source", key=sid, source=src))
    for sid in sorted(live_sources.keys() - manifest_sources.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="source", key=sid, source=src))
    for sid in sorted(manifest_sources.keys() & live_sources.keys()):
        divs.extend(_diff_attrs(
            category="source",
            key=sid,
            source=src,
            expected_row=manifest_sources[sid],
            actual_row=live_sources[sid],
            fields=_SOURCE_DIRECT_FIELDS,
        ))
    return divs


def _diff_entities(
    expected: dict[str, dict],
    actual: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for slug in sorted(expected.keys() - actual.keys()):
        divs.append(Divergence(kind="missing_in_live", category="entity", key=slug, source=src))
    for slug in sorted(actual.keys() - expected.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="entity", key=slug, source=src))
    for slug in sorted(expected.keys() & actual.keys()):
        divs.extend(_diff_attrs(
            category="entity",
            key=slug,
            source=src,
            expected_row=expected[slug],
            actual_row=actual[slug],
            fields=_ENTITY_DIRECT_FIELDS,
        ))
    return divs


def _diff_sources_replay(
    expected: dict[str, dict],
    actual: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for sid in sorted(expected.keys() - actual.keys()):
        divs.append(Divergence(kind="missing_in_live", category="source", key=sid, source=src))
    for sid in sorted(actual.keys() - expected.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="source", key=sid, source=src))
    for sid in sorted(expected.keys() & actual.keys()):
        divs.extend(_diff_attrs(
            category="source",
            key=sid,
            source=src,
            expected_row=expected[sid],
            actual_row=actual[sid],
            fields=(("ingest_state", "ingest_state"),
                    ("ingest_count", "ingest_count"),
                    ("hash", "hash"),
                    ("file_type", "file_type"),
                    ("size_bytes", "size_bytes"),
                    ("status", "status"),
                    ("last_run_id", "last_run_id"),
                    # #89 D-89-17: Pass-1 frontmatter fields — included in
                    # replay diff so drift is detected once rebuild's Pass-1
                    # replay lands. Pre-Pass-1 rows compare NULL==NULL (no
                    # spurious divergences); post-Pass-1 drift is flagged.
                    ("summary", "summary"),
                    ("author", "author"),
                    ("domain", "domain")),
        ))
    return divs


def _diff_edge_set(
    *,
    category: str,
    expected_set: set[tuple[str, str]],
    actual_set: set[tuple[str, str]],
    arrow: str = "→",
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for a, b in sorted(expected_set - actual_set):
        divs.append(Divergence(kind="missing_in_live", category=category, key=f"{a}{arrow}{b}", source=src))
    for a, b in sorted(actual_set - expected_set):
        divs.append(Divergence(kind="missing_in_replay", category=category, key=f"{a}{arrow}{b}", source=src))
    return divs


def _diff_domains(
    expected: dict[str, dict],
    actual: dict[str, dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for name in sorted(expected.keys() - actual.keys()):
        divs.append(Divergence(kind="missing_in_live", category="domain", key=name, source=src))
    for name in sorted(actual.keys() - expected.keys()):
        divs.append(Divergence(kind="missing_in_replay", category="domain", key=name, source=src))
    return divs


def _diff_belongs_to(
    expected: dict[tuple[str, str], dict],
    actual: dict[tuple[str, str], dict],
) -> list[Divergence]:
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    for slug, name in sorted(expected.keys() - actual.keys()):
        divs.append(Divergence(
            kind="missing_in_live", category="belongs_to",
            key=f"{slug}→{name}", source=src,
        ))
    for slug, name in sorted(actual.keys() - expected.keys()):
        divs.append(Divergence(
            kind="missing_in_replay", category="belongs_to",
            key=f"{slug}→{name}", source=src,
        ))
    for k in sorted(expected.keys() & actual.keys()):
        slug, name = k
        divs.extend(_diff_attrs(
            category="belongs_to",
            key=f"{slug}→{name}",
            source=src,
            expected_row=expected[k],
            actual_row=actual[k],
            fields=(("sub_domain", "sub_domain"),),
        ))
    return divs


def _diff_claim_layer_scoped(
    *, category: str, expected: dict, actual: dict, key_to_str
) -> list[Divergence]:
    """Scope-limited diff for #83/#84 Claim-layer tables.

    Per the note on the collectors above: rebuild doesn't yet write
    Claim-layer state, so a strict equality diff would always flag live
    Claims as `missing_in_replay`. v1 reports divergences ONLY for keys
    present in BOTH replay and live (the strict diff is unlocked when
    rebuild's promotion-replay lands). Live-only rows are silently
    accepted as "not yet replay-derivable" — counted but not flagged.
    """
    divs: list[Divergence] = []
    src = "replay_structural_diff"
    # Only flag missing-in-live for keys present in BOTH (so we catch
    # attribute drift when replay does begin producing Claims; today,
    # this loop is empty since replay carries no Claims).
    shared = expected.keys() & actual.keys()
    for k in sorted(shared):
        if expected[k] != actual[k]:
            divs.append(Divergence(
                kind="attribute_mismatch", category=category,
                key=key_to_str(k), source=src,
            ))
    return divs


# ---------- public entry points ----------

def verify_source_state(
    live_conn: kuzu.Connection,
    manifest: dict,
) -> list[Divergence]:
    """Layer 1: source-state preflight. Cheap comparison of manifest sources{}
    against live graph Source nodes. Returns divergences tagged with
    source='source_state_preflight'."""
    m_sources = _manifest_sources(manifest)
    l_sources = _graph_sources(live_conn)
    return _diff_sources_preflight(m_sources, l_sources)


def verify_canonicalization_invariants(
    live_conn: kuzu.Connection,
) -> list[Divergence]:
    """Layer 3 (#74.6): canonicalization invariants on the live graph.

    Four invariants from docs/task74-canonicalization-blueprint.md §9.1.
    All checks are pure Cypher against the live graph — no sidecar reads,
    no replay. Divergences tagged source='canonicalization_invariants',
    kind='invariant_violation', field={'C1'|'C2'|'C3'|'C4'}.

    - **C1** — every `Entity` with `canonical_id IS NOT NULL` has a
      matching `ALIAS_OF` edge to that canonical_id.
    - **C2** — every `ALIAS_OF` edge's source has `canonical_id` equal
      to the edge's destination slug.
    - **C3** — `ALIAS_OF` is flat (D-R5-13): every `Entity.canonical_id`
      points at an `Entity` with `canonical_id IS NULL` (no chains).
    - **C4** — every `LINKS_TO` edge's destination has `canonical_id IS
      NULL` (D-R5-12: LINKS_TO targets are always canonical).

    Pre-#74 graphs (no aliases at all) trivially satisfy all four.
    """
    divs: list[Divergence] = []
    src = "canonicalization_invariants"

    # C1: alias entity (canonical_id set) without a matching ALIAS_OF edge.
    r = live_conn.execute(
        """
        MATCH (a:Entity)
        WHERE a.canonical_id IS NOT NULL
          AND NOT EXISTS {
              MATCH (a)-[:ALIAS_OF]->(c:Entity)
              WHERE c.slug = a.canonical_id
          }
        RETURN a.slug, a.canonical_id
        """
    )
    while r.has_next():
        row = r.get_next()
        divs.append(Divergence(
            kind="invariant_violation",
            category="entity",
            key=row[0],
            source=src,
            field="C1",
            expected_value=f"ALIAS_OF edge to {row[1]!r}",
            actual_value="no matching ALIAS_OF edge",
        ))

    # C2: ALIAS_OF edge whose source's canonical_id != destination slug.
    r = live_conn.execute(
        """
        MATCH (a:Entity)-[:ALIAS_OF]->(c:Entity)
        WHERE a.canonical_id IS NULL OR a.canonical_id <> c.slug
        RETURN a.slug, a.canonical_id, c.slug
        """
    )
    while r.has_next():
        row = r.get_next()
        divs.append(Divergence(
            kind="invariant_violation",
            category="alias_of",
            key=f"{row[0]}→{row[2]}",
            source=src,
            field="C2",
            expected_value=row[2],   # destination slug
            actual_value=row[1],     # source's canonical_id (may be None)
        ))

    # C3: chain — canonical_id points at an Entity that is itself an alias.
    r = live_conn.execute(
        """
        MATCH (a:Entity), (target:Entity)
        WHERE a.canonical_id IS NOT NULL
          AND target.slug = a.canonical_id
          AND target.canonical_id IS NOT NULL
        RETURN a.slug, a.canonical_id, target.canonical_id
        """
    )
    while r.has_next():
        row = r.get_next()
        divs.append(Divergence(
            kind="invariant_violation",
            category="entity",
            key=row[0],
            source=src,
            field="C3",
            expected_value=f"flat: {row[1]!r} should have canonical_id IS NULL",
            actual_value=f"{row[1]!r} chains to {row[2]!r}",
        ))

    # C4: LINKS_TO destination is an alias (has canonical_id set).
    r = live_conn.execute(
        """
        MATCH (a:Entity)-[:LINKS_TO]->(b:Entity)
        WHERE b.canonical_id IS NOT NULL
        RETURN a.slug, b.slug, b.canonical_id
        """
    )
    while r.has_next():
        row = r.get_next()
        divs.append(Divergence(
            kind="invariant_violation",
            category="links_to",
            key=f"{row[0]}→{row[1]}",
            source=src,
            field="C4",
            expected_value=f"canonical target (canonical_id IS NULL)",
            actual_value=f"alias for {row[2]!r}",
        ))

    return divs


def verify(
    live_conn: kuzu.Connection,
    *,
    journals_dir: Path,
    manifest: dict | None = None,
) -> VerifyResult:
    """Full replay verification: rebuild temp graph from journals, diff against live.

    Args:
        live_conn: Connection to the live Kuzu graph.
        journals_dir: Directory containing run journals (state/runs/).
        manifest: Optional manifest dict for source-state preflight.
            If None, preflight is skipped.

    Returns:
        VerifyResult. If rebuild fails, ok=False + rebuild_failed=True + no
        divergences (partial replay is not compared).
    """
    from graphdb_kdb.adapters.obsidian_runs import ObsidianRunsAdapter
    from graphdb_kdb.rebuilder import rebuild

    all_divs: list[Divergence] = []

    # Layer 1: source-state preflight (if manifest provided)
    if manifest is not None:
        all_divs.extend(verify_source_state(live_conn, manifest))

    # Layer 3 (#74.6): canonicalization invariants on the live graph.
    # Runs before Layer 2 so even if rebuild fails downstream we still
    # surface alias-state violations (the cheapest and most localized
    # signal). Pre-#74 graphs trivially satisfy C1–C4 — zero divergences.
    all_divs.extend(verify_canonicalization_invariants(live_conn))

    # Layer 2: replay structural diff
    adapter = ObsidianRunsAdapter()

    with tempfile.TemporaryDirectory() as td:
        temp_graph_dir = Path(td) / "graph"

        rebuild_result = rebuild(
            graph_dir=temp_graph_dir,
            adapter=adapter,
            journals_dir=journals_dir,
            confirm=False,
        )

        if not rebuild_result.ok:
            failed_runs = [
                o for o in rebuild_result.outcomes if o.state == "failed"
            ]
            error_msg = "; ".join(
                f"{o.run_id}: {o.error}" for o in failed_runs
            )
            return VerifyResult(
                ok=False,
                rebuild_failed=True,
                rebuild_error=error_msg,
                divergences=all_divs,
                counts={"rebuild_replayed": rebuild_result.replayed,
                        "rebuild_skipped": rebuild_result.skipped,
                        "rebuild_failed": rebuild_result.failed},
            )

        with GraphDB(temp_graph_dir) as replay_gdb:
            r_entities = _graph_entities(replay_gdb.conn)
            r_sources = _graph_sources(replay_gdb.conn)
            r_links = _graph_links(replay_gdb.conn)
            r_supports = _graph_supports(replay_gdb.conn)
            r_domains = _graph_domains(replay_gdb.conn)
            r_belongs_to = _graph_belongs_to(replay_gdb.conn)
            # #83/#84 Claim layer — empty under v1 (no promotion-replay yet).
            r_claims = _graph_claims(replay_gdb.conn)
            r_evidences = _graph_evidences(replay_gdb.conn)
            r_about = _graph_about(replay_gdb.conn)
            r_supersedes = _graph_claim_claim_edges(replay_gdb.conn, "SUPERSEDES")
            r_contradicts = _graph_claim_claim_edges(replay_gdb.conn, "CONTRADICTS")
            r_qualifies = _graph_claim_claim_edges(replay_gdb.conn, "QUALIFIES")

    l_entities = _graph_entities(live_conn)
    l_sources = _graph_sources(live_conn)
    l_links = _graph_links(live_conn)
    l_supports = _graph_supports(live_conn)
    l_domains = _graph_domains(live_conn)
    l_belongs_to = _graph_belongs_to(live_conn)
    l_claims = _graph_claims(live_conn)
    l_evidences = _graph_evidences(live_conn)
    l_about = _graph_about(live_conn)
    l_supersedes = _graph_claim_claim_edges(live_conn, "SUPERSEDES")
    l_contradicts = _graph_claim_claim_edges(live_conn, "CONTRADICTS")
    l_qualifies = _graph_claim_claim_edges(live_conn, "QUALIFIES")

    all_divs.extend(_diff_entities(r_entities, l_entities))
    all_divs.extend(_diff_sources_replay(r_sources, l_sources))
    all_divs.extend(_diff_edge_set(
        category="links_to", expected_set=r_links, actual_set=l_links,
    ))
    all_divs.extend(_diff_edge_set(
        category="supports", expected_set=r_supports, actual_set=l_supports,
    ))
    all_divs.extend(_diff_domains(r_domains, l_domains))
    all_divs.extend(_diff_belongs_to(r_belongs_to, l_belongs_to))
    # Claim-layer scoped diff (v1: shared-keys-only — see collector note above).
    all_divs.extend(_diff_claim_layer_scoped(
        category="claim", expected=r_claims, actual=l_claims,
        key_to_str=lambda k: str(k),
    ))
    all_divs.extend(_diff_claim_layer_scoped(
        category="evidences", expected=r_evidences, actual=l_evidences,
        key_to_str=lambda k: f"{k[0]}→{k[1]}",
    ))
    all_divs.extend(_diff_claim_layer_scoped(
        category="about", expected=r_about, actual=l_about,
        key_to_str=lambda k: f"{k[0]}→{k[1]}",
    ))
    for cat, r_set, l_set in (
        ("supersedes", r_supersedes, l_supersedes),
        ("contradicts", r_contradicts, l_contradicts),
        ("qualifies", r_qualifies, l_qualifies),
    ):
        all_divs.extend(_diff_claim_layer_scoped(
            category=cat, expected=r_set, actual=l_set,
            key_to_str=lambda k: f"{k[0]}→{k[1]}",
        ))

    counts = {
        "entities_checked": len(r_entities.keys() | l_entities.keys()),
        "sources_checked": len(r_sources.keys() | l_sources.keys()),
        "links_checked": len(r_links | l_links),
        "supports_checked": len(r_supports | l_supports),
        "domains_checked": len(r_domains.keys() | l_domains.keys()),
        "belongs_to_checked": len(r_belongs_to.keys() | l_belongs_to.keys()),
        # #83/#84 Claim layer
        "claims_checked": len(r_claims.keys() | l_claims.keys()),
        "evidences_checked": len(r_evidences.keys() | l_evidences.keys()),
        "about_checked": len(r_about.keys() | l_about.keys()),
        "supersedes_checked": len(r_supersedes.keys() | l_supersedes.keys()),
        "contradicts_checked": len(r_contradicts.keys() | l_contradicts.keys()),
        "qualifies_checked": len(r_qualifies.keys() | l_qualifies.keys()),
        "missing_in_live": sum(1 for d in all_divs if d.kind == "missing_in_live"),
        "missing_in_replay": sum(1 for d in all_divs if d.kind == "missing_in_replay"),
        "attribute_mismatch": sum(1 for d in all_divs if d.kind == "attribute_mismatch"),
        "invariant_violation": sum(1 for d in all_divs if d.kind == "invariant_violation"),
        "replay_replayed": rebuild_result.replayed,
        "replay_skipped": rebuild_result.skipped,
    }

    return VerifyResult(ok=not all_divs, divergences=all_divs, counts=counts)
