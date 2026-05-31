# T2/T3 Domain-Scoped Retrieval — Design Spec

**Date:** 2026-05-31
**Status:** Approved (design); pending spec review → implementation plan
**Scope:** the 0.5.0 "consumer (T2/T3)" item implementing domain-scoping for the
Pass-2 context snapshot. **Target file:** `kdb_compiler/graph_context_loader.py`.
**Decision lineage:** implements **D3** from `docs/ontology-blueprint-V1.md`, but
**overrides** the ratified C ("coordinate, not gate") to a **hard same-domain gate**
(see "Decision override" below).

---

## Goal

Scope the Pass-2 context snapshot to the source's **Pass-1 domain only** — T2 and T3
pull existing entities exclusively from that domain — so the compiler is shown a clean,
same-domain set of entities to reuse, not an off-domain-diluted one.

## Why (the problem)

The context snapshot exists for **entity anti-entropy**: it shows the Pass-2 LLM the
relevant *existing* graph entities so it links to / reuses them instead of spawning
near-duplicates. Tiers: **T1** = entities the source `SUPPORTS`; **T2** = entities matched
from the source's Pass-1 `entity_search_keys`; **T3** = graph neighbors of T1∪T2; capped
at `page_cap` (50). As the graph grows across domains, T3's open neighbor expansion drags
in off-domain entities (a hub bridges value-investing → AI/ML), diluting the limited
context and inviting concept blur / mis-merges. Off-domain entities are **noise for the
disambiguation job**, so the context should be same-domain by design.

This is **not** about forbidding cross-domain *links*: Pass-2 remains free to emit whatever
links it judges right. And cross-domain **Discover** (finding connections across domains)
is a separate, future, query-time concern over the whole graph — not a compile-context
concern. Scoping the context changes only **what existing entities the compiler is shown**.

## Decision override (recorded against blueprint D3)

Blueprint `ontology-blueprint-V1.md` §7 ratified **D3 → C (coordinate, not gate)** with a
~70/30 same/cross budget; the 5-model panel unanimously rejected the hard gate, fearing it
suppresses cross-domain Discover. **Joseph overrides to a hard same-domain gate** on the
grounds the panel conflated three things: (1) **context-scoping** (anti-entropy — should be
same-domain), (2) **link-creation** (unconstrained — the LLM's call), (3) **Discover**
(future, query-time). Separating them, the gate touches only (1); (2) and (3) are
untouched, so the panel's objection does not bite. The ~70/30 budget, cross-domain
weighting, and "exact-T2-global" nuance from variant D are **dropped** in favor of the
simpler hard gate. The blueprint's D3 Ratification entry is updated to record this.

## Design

A **positive pull**, not a filter: the candidate universe for T2/T3 becomes "the entities
that `BELONGS_TO` this source's domain." Off-domain and domain-less entities are simply never
in the pool — no per-entity branch.

In `build_context_snapshot(conn, *, source_id, source_text, page_cap, frontmatter, mode, resolver)`:

1. **Domain** = `frontmatter.domain` (Pass-1's single coordinate).
2. **Domain pool** — load the active entities that `BELONGS_TO` the domain, via a Domain-join
   query (`MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: $domain}) WHERE e.status='active'`,
   where `Domain.name` is the primary key and `frontmatter.domain` is the exact string used as
   that name). This pool replaces `slug_set` as the candidate universe for T2 and T3.
3. **T1** — unchanged: the source's `SUPPORTS` entities (same-domain by construction via D1-A;
   they are the source's own and always relevant, so not intersected).
4. **T2** — `_t2_from_search_keys` resolves `entity_search_keys` → canonical slugs, then the
   result is **intersected with the domain pool**. A key resolving to an off-domain entity
   (a same-slug cross-domain false match) is dropped. STRUCTURED/LAYERED/LEGACY all scope to
   the pool.
5. **T3** — `_t3_neighbors` runs over the **domain pool** as its candidate universe
   (`domain_pool - seeds`), so only same-domain neighbors are admitted. Cold-start widening
   (#71, `_t2_title_in_text`) searches within the domain pool only.
6. **No padding** — ranking (tier desc → pagerank desc → slug asc) and `page_cap` truncation
   are unchanged; with a domain-scoped pool the snapshot is naturally as long as the domain
   supports — short or empty is acceptable, never topped up from other domains. (Priority:
   full same-domain list > short/empty same-domain list > off-domain-padded list.)
7. **Fallback** — a source with **no Pass-1 domain** (`frontmatter is None`, or domain empty:
   pre-Pass-1 / un-enriched source) cannot be domain-scoped, so the pool falls back to all
   active entities (today's un-scoped behavior) for that source only. The existing State-A
   legacy T2 path already covers `frontmatter is None`.

## Dilution check / observability

Because the pool is a positive domain pull, the produced context is same-domain by
construction. The "dilution check" is therefore a cheap guard + observability, not a filter:
the snapshot records the scoped `domain` and the page count, and a 0-cost assertion that no
selected page is off-domain (catches a derivation/query bug). The per-source count can feed
the #102 progress line (e.g. `context: 12 pages`). No separate metrics store.

## Out of scope

- Cross-domain link **creation** by Pass-2 (unchanged — not constrained here).
- Cross-domain **Discover** (future, query-time, whole-graph; not a compile concern).
- The ~70/30 budget, cross-domain down-weighting, exact-T2-global (dropped with the override).
- Hub-suppression (deferred companion per the blueprint).
- Multi-domain weighting — a multi-domain entity that includes the source's domain is in the
  pool (membership); no weighting beyond that.

## Testing

Unit tests in `kdb_compiler/tests/` (graph fixtures, no live API):
- **T2 off-domain drop:** an `entity_search_key` resolving to an entity in a *different*
  domain is excluded from the snapshot.
- **Same-slug cross-domain false match** is excluded (the disambiguation win).
- **T3 same-domain only:** a cross-domain neighbor of a seed is not admitted; a same-domain
  neighbor is.
- **No padding:** when the domain pool is smaller than `page_cap`, the snapshot is short and
  contains no off-domain page (not topped up).
- **Composition guard:** every page in the snapshot belongs to the scoped domain.
- **Cold-start within domain:** title-phrase widening admits only same-domain titles.
- **No-domain source fallback:** `frontmatter=None` yields the prior un-scoped behavior
  (regression-safe).
