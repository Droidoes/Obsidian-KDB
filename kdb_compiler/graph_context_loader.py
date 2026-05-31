"""graph_context_loader — GraphDB-backed context snapshot for one compile job.

Selected by planner.py via KDB_CONTEXT_SOURCE=graphdb. Does NOT read env vars
itself (Codex F-5 purity invariant) — planner owns env-var parsing and threads
T2Mode/resolver as explicit params. Fails explicitly if graph state is
insufficient.

Ranking tiers (strict ordering — no cross-tier promotion):
    T1 (score=3): entities supported by this source (SUPPORTS edges)
    T2 (score=2): entities seeded into context per T2Mode (Task #90 v0.2):
                  - STRUCTURED (default, D-90-1): Pass-1 enriched sources use
                    `entity_search_keys` (D-89-20); pre-Pass-1 sources fall
                    back to legacy regex; explicit `[]` honored as empty T2
                    (State C, D-90-8).
                  - LAYERED (benchmark-only): union of structured + legacy.
                  - LEGACY (benchmark-only / pre-Pass-1 fallback): whole-word
                    regex + cold-start title-phrase widening (D48 / Task #71).
    T3 (score=1): 1-hop neighbors (in+out) of T1∪T2 seeds, excluding seeds
                  Cold-start widening: expands to 2-hop when T1 empty and
                  |T2| < _MIN_SEED_THRESHOLD.
    Tie-break:    PageRank (desc), then slug (asc) — within same tier only
"""
from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

import kuzu

from kdb_compiler.types import ContextPage, ContextSnapshot

if TYPE_CHECKING:
    from kdb_compiler.source_io import SourceFrontmatter

_VALID_PAGE_TYPES = frozenset({"summary", "concept", "article"})


_MIN_SEED_THRESHOLD = 5


class T2Mode(str, Enum):
    """T2 production strategy (Task #90 D-90-2).

    STRUCTURED is the v1 production default per D-90-1. LAYERED and LEGACY
    exist for the NW-9 benchmark (D-90-4) — they are not expected to be
    selected in normal compile runs.
    """
    STRUCTURED = "structured"
    LAYERED = "layered"
    LEGACY = "legacy"


def build_context_snapshot(
    conn: kuzu.Connection,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = 50,
    frontmatter: "SourceFrontmatter | None" = None,
    mode: T2Mode = T2Mode.STRUCTURED,
    resolver: str = "simple",
) -> ContextSnapshot:
    """Build a tier-ranked, source-specific context snapshot from GraphDB.

    Pure graph reads — no manifest access, no env var reads.
    Empty/missing source or empty graph → empty snapshot (never raises).

    Task #90 v0.2 params:
        frontmatter: Pass-1 SourceFrontmatter or None for pre-Pass-1 sources.
            Drives T2 branch under STRUCTURED/LAYERED modes.
        mode: T2 production strategy (default STRUCTURED per D-90-1).
        resolver: "simple" (2-query default per D-90-9) or "batch" (Codex-tested
            escape hatch via KDB_T2_RESOLVER=batch).
    """
    active_entities = _load_active_entities(conn)
    if not active_entities:
        return ContextSnapshot(source_id=source_id, pages=[])

    slug_set = set(active_entities.keys())

    # Same-domain gate (D3 override): T2/T3 pull only from the source's Pass-1
    # domain (entity anti-entropy). T1 stays on the full set — it is the source's
    # own SUPPORTS, same-domain by construction. A source with no Pass-1 domain
    # (pre-Pass-1 / un-enriched) cannot be scoped, so it falls back to the full graph.
    domain = frontmatter.domain if frontmatter is not None else None
    pool = (_domain_pool(conn, domain) & slug_set) if domain else slug_set

    # --- Tier assignment ---
    t1_slugs = _t1_source_supported(conn, source_id, slug_set)
    cold_start = len(t1_slugs) == 0

    t2_slugs = _build_t2(
        conn,
        source_text=source_text,
        candidate_slugs=pool - t1_slugs,
        active_entities=active_entities,
        cold_start=cold_start,
        frontmatter=frontmatter,
        mode=mode,
        resolver=resolver,
    )

    seeds = t1_slugs | t2_slugs
    max_hops = 1
    if cold_start and len(t2_slugs) < _MIN_SEED_THRESHOLD:
        max_hops = 2
    t3_slugs = _t3_neighbors(conn, seeds, pool - seeds, max_hops=max_hops)

    # --- Scoring + ranking ---
    pagerank_scores = _pagerank_scores(conn)

    scored: list[tuple[str, int, float]] = []
    for slug in t1_slugs:
        scored.append((slug, 3, pagerank_scores.get(slug, 0.0)))
    for slug in t2_slugs:
        scored.append((slug, 2, pagerank_scores.get(slug, 0.0)))
    for slug in t3_slugs:
        scored.append((slug, 1, pagerank_scores.get(slug, 0.0)))

    # Strict tier ordering: tier desc, pagerank desc, slug asc
    scored.sort(key=lambda x: (-x[1], -x[2], x[0]))
    selected_slugs = [s[0] for s in scored[:page_cap]]

    # --- Projection ---
    outgoing_map = _batch_outgoing_links(conn, selected_slugs)
    pages = []
    for slug in selected_slugs:
        ent = active_entities[slug]
        page_type = ent["page_type"]
        if page_type not in _VALID_PAGE_TYPES:
            continue
        pages.append(ContextPage(
            slug=slug,
            title=ent["title"],
            page_type=page_type,
            outgoing_links=outgoing_map.get(slug, []),
        ))

    return ContextSnapshot(source_id=source_id, pages=pages)


# ---------- Tier helpers ----------


def _load_active_entities(conn: kuzu.Connection) -> dict[str, dict]:
    """Load all active entities as {slug: {title, page_type}}."""
    result = conn.execute(
        "MATCH (e:Entity) WHERE e.status = 'active' "
        "RETURN e.slug, e.title, e.page_type"
    )
    entities: dict[str, dict] = {}
    while result.has_next():
        row = result.get_next()
        entities[row[0]] = {"title": row[1], "page_type": row[2]}
    return entities


def _domain_pool(conn: kuzu.Connection, domain: str) -> set[str]:
    """Slugs of active entities that BELONGS_TO `domain` (the same-domain gate).

    The Pass-2 context is pulled only from the source's Pass-1 domain (D3
    override → hard same-domain gate). Domain nodes are keyed by `Domain.name`,
    which is exactly the string Pass-1 emits as `frontmatter.domain`.
    """
    result = conn.execute(
        "MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: $name}) "
        "WHERE e.status = 'active' RETURN e.slug",
        {"name": domain},
    )
    slugs: set[str] = set()
    while result.has_next():
        slugs.add(result.get_next()[0])
    return slugs


def _t1_source_supported(
    conn: kuzu.Connection, source_id: str, active_slugs: set[str]
) -> set[str]:
    """Entities the source currently SUPPORTS."""
    result = conn.execute(
        "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(e:Entity) "
        "RETURN e.slug",
        {"sid": source_id},
    )
    slugs: set[str] = set()
    while result.has_next():
        slug = result.get_next()[0]
        if slug in active_slugs:
            slugs.add(slug)
    return slugs


def _t2_slug_in_text(source_text: str, candidate_slugs: set[str]) -> set[str]:
    """Slugs that appear as whole-word tokens in source_text."""
    if not candidate_slugs or not source_text:
        return set()
    pattern = _whole_word_alternation(sorted(candidate_slugs))
    return {m.group(0).lower() for m in pattern.finditer(source_text)}


def _title_eligible(title: str) -> bool:
    """Check if a title passes the cold-start matching guardrail.

    Eligible iff:
      - normalized length > 3, AND
      - either has 2+ alphanumeric tokens, OR is a single token with length >= 6
    """
    normalized = title.strip().lower()
    if len(normalized) <= 3:
        return False
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if len(tokens) >= 2:
        return True
    if len(tokens) == 1 and len(tokens[0]) >= 6:
        return True
    return False


def _t2_title_in_text(
    source_text: str,
    candidate_slugs: set[str],
    active_entities: dict[str, dict],
) -> set[str]:
    """Title-phrase matching for cold-start widening (D48, Task #71).

    Matches eligible entity titles as exact phrases in source_text.
    Returns the set of slugs whose titles matched.
    """
    if not candidate_slugs or not source_text:
        return set()

    title_to_slug: dict[str, str] = {}
    for slug in candidate_slugs:
        ent = active_entities.get(slug)
        if ent is None:
            continue
        title = ent.get("title", "")
        if not title or not _title_eligible(title):
            continue
        title_to_slug[title.strip().lower()] = slug

    if not title_to_slug:
        return set()

    escaped_titles = [re.escape(t) for t in sorted(title_to_slug.keys(), key=len, reverse=True)]
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(escaped_titles) + r")(?!\w)",
        re.IGNORECASE,
    )
    matched_slugs: set[str] = set()
    for m in pattern.finditer(source_text):
        matched_title = m.group(0).lower()
        slug = title_to_slug.get(matched_title)
        if slug:
            matched_slugs.add(slug)
    return matched_slugs


def _t3_neighbors(
    conn: kuzu.Connection,
    seeds: set[str],
    candidate_slugs: set[str],
    *,
    max_hops: int = 1,
) -> set[str]:
    """Multi-hop in+out neighbors of seeds that are active and not already a seed."""
    if not seeds or not candidate_slugs:
        return set()
    current_frontier = set(seeds)
    all_neighbors: set[str] = set()
    visited = set(seeds)

    for _ in range(max_hops):
        next_frontier: set[str] = set()
        for slug in current_frontier:
            # outgoing
            result = conn.execute(
                "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug",
                {"s": slug},
            )
            while result.has_next():
                n = result.get_next()[0]
                if n in candidate_slugs and n not in visited:
                    all_neighbors.add(n)
                    next_frontier.add(n)
            # incoming
            result = conn.execute(
                "MATCH (a:Entity {slug: $s})<-[:LINKS_TO]-(b:Entity) RETURN b.slug",
                {"s": slug},
            )
            while result.has_next():
                n = result.get_next()[0]
                if n in candidate_slugs and n not in visited:
                    all_neighbors.add(n)
                    next_frontier.add(n)
        visited |= next_frontier
        current_frontier = next_frontier
    return all_neighbors


def _pagerank_scores(conn: kuzu.Connection) -> dict[str, float]:
    """Compute PageRank over LINKS_TO topology. Returns {slug: score}."""
    try:
        import networkx as nx
    except ImportError:
        return {}

    result = conn.execute(
        "MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug"
    )
    g = nx.DiGraph()
    while result.has_next():
        row = result.get_next()
        g.add_edge(row[0], row[1])

    if not g.nodes:
        return {}

    # Add isolated active entities so they get a base score
    result2 = conn.execute("MATCH (e:Entity) WHERE e.status = 'active' RETURN e.slug")
    while result2.has_next():
        g.add_node(result2.get_next()[0])

    return nx.pagerank(g)


# ---------- Projection helpers ----------


def _batch_outgoing_links(
    conn: kuzu.Connection, slugs: list[str]
) -> dict[str, list[str]]:
    """For each slug, fetch its outgoing LINKS_TO target slugs."""
    out: dict[str, list[str]] = {}
    for slug in slugs:
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug ORDER BY b.slug",
            {"s": slug},
        )
        links = []
        while result.has_next():
            links.append(result.get_next()[0])
        out[slug] = links
    return out


# ---------- Regex helper ----------


def _whole_word_alternation(slugs: list[str]) -> re.Pattern[str]:
    """Case-insensitive whole-word pattern. Hyphens are intra-token."""
    escaped = [re.escape(s) for s in slugs]
    return re.compile(
        r"(?<![\w-])(" + "|".join(escaped) + r")(?![\w-])",
        re.IGNORECASE,
    )


# ---------- T2 dispatcher (Task #90 v0.2 — D-90-2) ----------


def _build_t2(
    conn: kuzu.Connection,
    *,
    source_text: str,
    candidate_slugs: set[str],
    active_entities: dict[str, dict],
    cold_start: bool,
    frontmatter: "SourceFrontmatter | None",
    mode: T2Mode,
    resolver: str,
) -> set[str]:
    """Dispatch T2 construction by mode. STRUCTURED is the v1 default."""
    if mode == T2Mode.STRUCTURED:
        return _t2_structured(
            conn, frontmatter, source_text, candidate_slugs, cold_start,
            active_entities, resolver,
        )
    if mode == T2Mode.LAYERED:
        return _t2_layered(
            conn, frontmatter, source_text, candidate_slugs, cold_start,
            active_entities, resolver,
        )
    if mode == T2Mode.LEGACY:
        return _t2_legacy(source_text, candidate_slugs, cold_start, active_entities)
    raise ValueError(f"unknown T2Mode: {mode!r}")


def _t2_structured(
    conn: kuzu.Connection,
    frontmatter: "SourceFrontmatter | None",
    source_text: str,
    candidate_slugs: set[str],
    cold_start: bool,
    active_entities: dict[str, dict],
    resolver: str,
) -> set[str]:
    """STRUCTURED mode (Option A, D-90-1). Three-state branch per D-90-8.

    State A — frontmatter is None: pre-Pass-1 source → legacy regex + cold-start
        title-phrase widening.
    State B — frontmatter.entity_search_keys non-empty: use structured lookup.
    State C — frontmatter present but entity_search_keys explicitly []: honor
        the LLM's "no graph anchors" judgment; emit empty T2.
    """
    if frontmatter is None:
        return _t2_legacy(source_text, candidate_slugs, cold_start, active_entities)
    if frontmatter.entity_search_keys:
        return _t2_from_search_keys(
            conn, frontmatter.entity_search_keys, candidate_slugs, resolver,
        )
    # State C — explicit empty signal honored.
    return set()


def _t2_layered(
    conn: kuzu.Connection,
    frontmatter: "SourceFrontmatter | None",
    source_text: str,
    candidate_slugs: set[str],
    cold_start: bool,
    active_entities: dict[str, dict],
    resolver: str,
) -> set[str]:
    """LAYERED mode (Option B, benchmark-only). structured ∪ legacy.

    Deliberately diverges from STRUCTURED on State C — when entity_search_keys
    is explicitly [], LAYERED still runs the legacy regex over the full candidate
    pool. Lets NW-9 measure the cost of honoring State C vs. always-regex.
    """
    structured: set[str] = set()
    if frontmatter is not None and frontmatter.entity_search_keys:
        structured = _t2_from_search_keys(
            conn, frontmatter.entity_search_keys, candidate_slugs, resolver,
        )
    regex_pool = candidate_slugs - structured
    legacy = _t2_legacy(source_text, regex_pool, cold_start, active_entities)
    return structured | legacy


def _t2_legacy(
    source_text: str,
    candidate_slugs: set[str],
    cold_start: bool,
    active_entities: dict[str, dict],
) -> set[str]:
    """LEGACY mode (pre-Pass-1 fallback or benchmark baseline). Whole-word
    slug regex + cold-start title-phrase widening (D48 / Task #71).

    Transitional behavior — sunsets under D-90-12 once vault is 100% enriched
    and NW-9 confirms STRUCTURED ≥ LEGACY on cold-start density + precision.
    """
    t2 = _t2_slug_in_text(source_text, candidate_slugs)
    if cold_start:
        t2 = t2 | _t2_title_in_text(
            source_text, candidate_slugs - t2, active_entities,
        )
    return t2


# ---------- Structured-key lookup (Task #90 v0.2 — D-90-9) ----------


def _t2_from_search_keys(
    conn: kuzu.Connection,
    raw_keys: list[str],
    candidate_slugs: set[str],
    resolver: str,
) -> set[str]:
    """Batched resolution of Pass-1 entity_search_keys → canonical T2 slugs.

    Set semantics naturally deduplicate when multiple raw keys resolve to the
    same canonical entity.
    """
    if not raw_keys:
        return set()
    if resolver == "batch":
        resolved_map = _resolve_to_canonical_slugs_batch(conn, raw_keys)
    else:
        resolved_map = _resolve_to_canonical_slugs(conn, raw_keys)
    return {canonical for canonical in resolved_map.values()
            if canonical in candidate_slugs}


def _resolve_to_canonical_slugs(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Simple 2-query alias-aware batch resolver (D-90-9 v1 default).

    Reachability per §3.1: direct PK → canonical_id (with target.status='active'
    check — fixes B-2) → ALIAS_OF (canonical.status='active' check).

    Returns {raw_slug: canonical_slug} for every raw key that resolves to an
    active canonical entity. Unresolved raws are absent from the dict.

    Defensive: trims whitespace + drops empty/whitespace-only entries (Qwen O-2).
    """
    if not raw_slugs:
        return {}
    cleaned = [s.strip() for s in raw_slugs if s and s.strip()]
    if not cleaned:
        return {}

    resolved: dict[str, str] = {}

    # Single MATCH with two OPTIONAL chains: surface direct PK, canonical_id
    # target status, and ALIAS_OF canonical info in one round-trip. Path
    # precedence applied in Python: Path 2 (canonical_id) > Path 3 (ALIAS_OF)
    # > Path 1 (direct leaf). Path 3 before Path 1 is required so that an
    # entity with NO canonical_id but WITH an outgoing ALIAS_OF resolves via
    # the alias target — and so that an alias with a DEAD target stays
    # unresolved (does not fall back to self).
    q = conn.execute(
        """
        MATCH (e:Entity)
        WHERE e.slug IN $slugs
        OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
        OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
        RETURN e.slug, e.status, e.canonical_id,
               CASE WHEN target IS NULL THEN NULL ELSE target.status END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.slug END,
               CASE WHEN canon IS NULL THEN NULL ELSE canon.status END
        """,
        {"slugs": cleaned},
    )
    while q.has_next():
        slug, status, canonical_id, target_status, alias_canon, alias_canon_status = q.get_next()
        if canonical_id is not None:
            # Path 2 — canonical_id resolution (B-2 active check)
            if target_status == "active":
                resolved[slug] = canonical_id
            # else: dead canonical_id target — unresolved
        elif alias_canon is not None:
            # Path 3 — ALIAS_OF safety net (entity declared itself an alias)
            if alias_canon_status == "active":
                resolved[slug] = alias_canon
            # else: dead alias target — unresolved (NOT Path 1 fallback)
        elif status == "active":
            # Path 1 — direct leaf entity (no canonical_id, no outgoing ALIAS_OF)
            resolved[slug] = slug

    return resolved


def _resolve_to_canonical_slugs_batch(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Codex-tested batch resolver (D-90-9 escape hatch, KDB_T2_RESOLVER=batch).

    Single Cypher with UNWIND + chained OPTIONAL MATCH + CASE; empirically
    validated on Kuzu 0.11.3 in the v0.1 panel review. Functional parity with
    the simple resolver is enforced by test_t2_resolver_parity.py.
    """
    if not raw_slugs:
        return {}
    cleaned = [s.strip() for s in raw_slugs if s and s.strip()]
    if not cleaned:
        return {}

    # CASE precedence: Path 2 (canonical_id) > Path 3 (ALIAS_OF) > Path 1 (direct leaf).
    # An entity that has DECLARED itself an alias (either via canonical_id or
    # an outgoing ALIAS_OF edge) must NOT fall back to Path 1 if its declared
    # target is inactive — the explicit-null clauses suppress that fallback.
    # This keeps Path 1 reserved for true canonical leaves.
    q = conn.execute(
        """
        UNWIND $raw_slugs AS raw
        OPTIONAL MATCH (e:Entity {slug: raw})
        WITH raw, e
        OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
        OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
        RETURN raw,
               CASE
                 WHEN e IS NULL THEN NULL
                 WHEN e.canonical_id IS NOT NULL AND target IS NOT NULL AND target.status = 'active' THEN e.canonical_id
                 WHEN e.canonical_id IS NOT NULL THEN NULL
                 WHEN canon IS NOT NULL AND canon.status = 'active' THEN canon.slug
                 WHEN canon IS NOT NULL THEN NULL
                 WHEN e.status = 'active' THEN e.slug
                 ELSE NULL
               END AS canonical
        """,
        {"raw_slugs": cleaned},
    )
    resolved: dict[str, str] = {}
    while q.has_next():
        raw, canonical = q.get_next()
        if canonical is not None:
            resolved[raw] = canonical
    return resolved
