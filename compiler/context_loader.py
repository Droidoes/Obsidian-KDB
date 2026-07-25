"""context_loader — GraphDB-backed context snapshot for one compile job.

Called directly by the orchestrator (`kdb_orchestrate.py`). Does NOT read env
vars itself (Codex F-5 purity invariant) — the caller threads T2Mode/resolver
as explicit params. Fails explicitly if graph state is insufficient.

Note: `KDB_CONTEXT_SOURCE`, `KDB_T2_MODE`, and `KDB_T2_RESOLVER` env vars no
longer have any effect; selection and mode are wired directly by the
orchestrator.

Task #122: build_context_snapshot returns a ContextBuildResult — TWO products:
the prompt-facing ContextSnapshot (byte-identical) + the persistence-facing
ContextTelemetry (event-time capture: per-key dispositions with resolution
provenance, pre/post-cap tier records, effective strategy). The telemetry is
NEVER serialized into the prompt.

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

from kdb_graph import queries
from common.types import (
    ContextBuildResult,
    ContextPage,
    ContextSnapshot,
    ContextTelemetry,
    EffectiveT2Strategy,
    KeyOutcome,
    TierRecord,
)

if TYPE_CHECKING:
    from common.source_io import SourceFrontmatter

_VALID_PAGE_TYPES = frozenset({"summary", "concept", "article"})


_MIN_SEED_THRESHOLD = 5
_DEFAULT_PAGE_CAP = 50


class T2Mode(str, Enum):
    """T2 production strategy (Task #90 D-90-2).

    STRUCTURED is the v1 production default per D-90-1. LAYERED and LEGACY
    exist for the NW-9 benchmark (D-90-4) — they are not expected to be
    selected in normal compile runs.
    """
    STRUCTURED = "structured"
    LAYERED = "layered"
    LEGACY = "legacy"


def _effective_strategy(
    mode: "T2Mode",
    frontmatter: "SourceFrontmatter | None",
) -> tuple[list[str], EffectiveT2Strategy]:
    """(keys_emitted, effective_t2_strategy) from the configured mode +
    frontmatter presence — pre-graph-read, so the same derivation is valid on
    the context_failed path (Task #122 §3). keys_emitted is the key list the
    strategy actually consumes: State B / LAYERED-with-keys → the frontmatter
    keys; State A / LEGACY (frontmatter ignored) → []; State C → [] (the
    explicit empty emission itself)."""
    if mode == T2Mode.LAYERED:
        keys = (list(frontmatter.entity_search_keys)
                if frontmatter is not None and frontmatter.entity_search_keys
                else [])
        return keys, "layered_union"
    if mode == T2Mode.LEGACY:
        return [], "legacy_regex"
    # STRUCTURED three-state (D-90-8)
    if frontmatter is None:
        return [], "legacy_regex"                       # State A
    if frontmatter.entity_search_keys:
        return list(frontmatter.entity_search_keys), "structured_keys"  # State B
    return [], "explicit_empty"                         # State C


def _resolve_key_outcomes(
    resolved_prov: dict[str, tuple[str, str | None]],
    keys: list[str],
    *,
    t1_slugs: set[str],
    pool: set[str],
) -> tuple[list[KeyOutcome], set[str]]:
    """Disposition per emitted key, in emission order (Task #122 §3 precedence):
    absent from the resolution map → unresolved; canonical ∈ t1 → already_t1;
    canonical ∉ (pool − t1) → out_of_scope; already seeded by an earlier key →
    duplicate_seed; else → t2_seed (and seed it). Returns (outcomes, t2_seeds)
    — the seeds set equals the slug-only structured T2 set by construction."""
    outcomes: list[KeyOutcome] = []
    seeded: set[str] = set()
    scope = pool - t1_slugs
    for key in keys:
        hit = resolved_prov.get(key)
        if hit is None:
            outcomes.append(KeyOutcome(key=key, disposition="unresolved",
                                       resolved=None, target_first_run_id=None))
            continue
        canonical, stamp = hit
        if canonical in t1_slugs:
            disposition = "resolved_already_t1"
        elif canonical not in scope:
            disposition = "resolved_out_of_scope"
        elif canonical in seeded:
            disposition = "resolved_duplicate_seed"
        else:
            disposition = "resolved_t2_seed"
            seeded.add(canonical)
        outcomes.append(KeyOutcome(key=key, disposition=disposition,
                                   resolved=canonical, target_first_run_id=stamp))
    return outcomes, seeded


def build_context_snapshot(
    conn: Any,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = _DEFAULT_PAGE_CAP,
    frontmatter: "SourceFrontmatter | None" = None,
    mode: T2Mode = T2Mode.STRUCTURED,
    resolver: str = "simple",
) -> ContextBuildResult:
    """Build a tier-ranked, source-specific context snapshot from GraphDB —
    returning BOTH products (Task #122): the prompt-facing ContextSnapshot
    (byte-identical to pre-#122) and the persistence-facing ContextTelemetry
    (event-time capture; never serialized into the prompt).

    Pure graph reads — no manifest access, no env var reads.
    Empty/missing source or empty graph → empty snapshot (never raises).

    Task #90 v0.2 params:
        frontmatter: Pass-1 SourceFrontmatter or None for pre-Pass-1 sources.
            Drives T2 branch under STRUCTURED/LAYERED modes.
        mode: T2 production strategy (default STRUCTURED per D-90-1).
        resolver: "simple" (2-query default per D-90-9) or "batch" (Codex-tested
            escape hatch; pass resolver="batch" explicitly).
    """
    keys_emitted, strategy = _effective_strategy(mode, frontmatter)
    domain = frontmatter.domain if frontmatter is not None else None

    active_entities = _load_active_entities(conn)
    if not active_entities:
        # Empty-graph early return: FULL telemetry — every emitted key
        # unresolved (outcomes present), zero tiers, cold_start=True, max_hops
        # per the cold-start widening policy (T1 empty + |T2| < threshold → 2).
        zero = TierRecord(candidates=0, delivered=0, slugs=[])
        return ContextBuildResult(
            snapshot=ContextSnapshot(source_id=source_id, pages=[]),
            telemetry=ContextTelemetry(
                source_id=source_id,
                configured_t2_mode=mode.value,  # type: ignore[arg-type]
                effective_t2_strategy=strategy,
                keys_emitted=keys_emitted,
                key_outcomes=[KeyOutcome(key=k, disposition="unresolved",
                                         resolved=None, target_first_run_id=None)
                              for k in keys_emitted],
                t1=zero,
                t2=zero,
                t3=zero,
                candidate_universe_size=0,
                domain_scope=domain,
                cold_start=True,
                max_hops=2,
                page_cap=page_cap,
            ),
        )

    slug_set = set(active_entities.keys())

    # Same-domain gate (D3 override): T2/T3 pull only from the source's Pass-1
    # domain (entity anti-entropy). T1 stays on the full set — it is the source's
    # own SUPPORTS, same-domain by construction. A source with no Pass-1 domain
    # (pre-Pass-1 / un-enriched) cannot be scoped, so it falls back to the full graph.
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

    # --- Key dispositions (event-time; prompt-facing T2 unchanged above) ---
    key_outcomes: list[KeyOutcome] = []
    if keys_emitted:
        resolved_prov = (
            _resolve_to_canonical_slugs_with_provenance_batch(conn, keys_emitted)
            if resolver == "batch"
            else _resolve_to_canonical_slugs_with_provenance(conn, keys_emitted)
        )
        key_outcomes, _t2_seeds = _resolve_key_outcomes(
            resolved_prov, keys_emitted, t1_slugs=t1_slugs, pool=pool,
        )

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

    # --- TierRecords: candidates = pre-cap tier sets; delivered/slugs =
    # post-cap, post-projection prompt pages per tier, in rank order. The
    # tiers are disjoint by construction (t2 ⊆ pool−t1, t3 ⊆ pool−seeds), so
    # sum(delivered) == len(pages) ≤ page_cap.
    tier_of: dict[str, int] = {}
    for slug in t1_slugs:
        tier_of[slug] = 1
    for slug in t2_slugs:
        tier_of[slug] = 2
    for slug in t3_slugs:
        tier_of[slug] = 3
    tier_slugs: dict[int, list[str]] = {1: [], 2: [], 3: []}
    for page in pages:
        tier_slugs[tier_of[page.slug]].append(page.slug)

    return ContextBuildResult(
        snapshot=ContextSnapshot(source_id=source_id, pages=pages),
        telemetry=ContextTelemetry(
            source_id=source_id,
            configured_t2_mode=mode.value,  # type: ignore[arg-type]
            effective_t2_strategy=strategy,
            keys_emitted=keys_emitted,
            key_outcomes=key_outcomes,
            t1=TierRecord(len(t1_slugs), len(tier_slugs[1]), tier_slugs[1]),
            t2=TierRecord(len(t2_slugs), len(tier_slugs[2]), tier_slugs[2]),
            t3=TierRecord(len(t3_slugs), len(tier_slugs[3]), tier_slugs[3]),
            candidate_universe_size=len(pool),
            domain_scope=domain,
            cold_start=cold_start,
            max_hops=max_hops,
            page_cap=page_cap,
        ),
    )


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

    Thin wrapper over kdb_graph.queries.resolve_to_canonical_slugs — the
    Cypher + path-precedence logic now lives behind the single Kuzu door.
    Retained as a module-level symbol so existing importers (e.g.
    test_t2_resolver_parity.py) only repoint their import path.
    """
    return queries.resolve_to_canonical_slugs(conn, raw_slugs)


def _resolve_to_canonical_slugs_batch(
    conn: Any,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Codex-tested batch resolver (D-90-9 escape hatch; pass resolver="batch").

    Thin wrapper over kdb_graph.queries.resolve_to_canonical_slugs_batch.
    """
    return queries.resolve_to_canonical_slugs_batch(conn, raw_slugs)


def _resolve_to_canonical_slugs_with_provenance(
    conn: Any,
    raw_slugs: list[str],
) -> dict[str, tuple[str, str | None]]:
    """Provenance twin (#122): {raw: (canonical, target_first_run_id)} — the
    disposition pass reads stamps from here; the slug-only wrapper above is a
    projection of the same classification."""
    return queries.resolve_to_canonical_slugs_with_provenance(conn, raw_slugs)


def _resolve_to_canonical_slugs_with_provenance_batch(
    conn: Any,
    raw_slugs: list[str],
) -> dict[str, tuple[str, str | None]]:
    """Batch provenance twin (#122)."""
    return queries.resolve_to_canonical_slugs_with_provenance_batch(conn, raw_slugs)
