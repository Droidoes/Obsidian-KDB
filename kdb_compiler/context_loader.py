"""context_loader — GraphDB-backed context snapshot for one compile job.

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
from typing import TYPE_CHECKING, Any

from graphdb_kdb import queries
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
    conn: Any,
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


def _load_active_entities(conn: Any) -> dict[str, dict]:
    """Load all active entities as {slug: {title, page_type}}."""
    return queries.active_entities(conn)


def _domain_pool(conn: Any, domain: str) -> set[str]:
    """Slugs of active entities that BELONGS_TO `domain` (the same-domain gate).

    The Pass-2 context is pulled only from the source's Pass-1 domain (D3
    override → hard same-domain gate). Domain nodes are keyed by `Domain.name`,
    which is exactly the string Pass-1 emits as `frontmatter.domain`.
    """
    return queries.domain_entity_slugs(conn, domain)


def _t1_source_supported(
    conn: Any, source_id: str, active_slugs: set[str]
) -> set[str]:
    """Entities the source currently SUPPORTS (restricted to active slugs)."""
    return queries.source_supported_slugs(conn, source_id) & active_slugs


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
    conn: Any,
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
            for n in queries.outgoing_neighbor_slugs(conn, slug):
                if n in candidate_slugs and n not in visited:
                    all_neighbors.add(n)
                    next_frontier.add(n)
            # incoming
            for n in queries.incoming_neighbor_slugs(conn, slug):
                if n in candidate_slugs and n not in visited:
                    all_neighbors.add(n)
                    next_frontier.add(n)
        visited |= next_frontier
        current_frontier = next_frontier
    return all_neighbors


def _pagerank_scores(conn: Any) -> dict[str, float]:
    """Compute PageRank over LINKS_TO topology. Returns {slug: score}."""
    try:
        import networkx as nx
    except ImportError:
        return {}

    g = nx.DiGraph()
    for from_slug, to_slug in queries.links_to_edges(conn):
        g.add_edge(from_slug, to_slug)

    if not g.nodes:
        return {}

    # Add isolated active entities so they get a base score
    for slug in queries.active_entity_slugs(conn):
        g.add_node(slug)

    return nx.pagerank(g)


# ---------- Projection helpers ----------


def _batch_outgoing_links(
    conn: Any, slugs: list[str]
) -> dict[str, list[str]]:
    """For each slug, fetch its outgoing LINKS_TO target slugs."""
    out: dict[str, list[str]] = {}
    for slug in slugs:
        out[slug] = queries.outgoing_links_ordered(conn, slug)
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
    conn: Any,
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
    conn: Any,
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
    conn: Any,
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
    conn: Any,
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
    conn: Any,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Simple 2-query alias-aware batch resolver (D-90-9 v1 default).

    Thin wrapper over graphdb_kdb.queries.resolve_to_canonical_slugs — the
    Cypher + path-precedence logic now lives behind the single Kuzu door.
    Retained as a module-level symbol so existing importers (e.g.
    test_t2_resolver_parity.py) only repoint their import path.
    """
    return queries.resolve_to_canonical_slugs(conn, raw_slugs)


def _resolve_to_canonical_slugs_batch(
    conn: Any,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Codex-tested batch resolver (D-90-9 escape hatch, KDB_T2_RESOLVER=batch).

    Thin wrapper over graphdb_kdb.queries.resolve_to_canonical_slugs_batch.
    """
    return queries.resolve_to_canonical_slugs_batch(conn, raw_slugs)
