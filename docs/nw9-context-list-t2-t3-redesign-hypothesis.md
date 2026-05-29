# NW-9 — EXISTING CONTEXT list: T2/T3 redesign hypothesis

> **Status:** Design hypothesis (2026-05-29), surfaced during the `kdb-orchestrate` E2E walk. **Proposed as a new task** reviving Task #26's parked "effectiveness measurement" scope and **revising Task #90's shipped T2** (`STRUCTURED` exact-match `entity_search_keys`). Pending ledger ID + Joseph's go. NOT in `#91` scope — `build_context_snapshot` is already `mode`-pluggable, so the orchestrator consumes whatever T2/T3 strategy wins this measurement.

## Problem (Joseph, 2026-05-29)

The EXISTING CONTEXT list (T1/T2/T3, cap 50) exists to anchor Pass-2 to **entities that already exist in the GraphDB**, so the compiler reuses canonical concepts instead of minting variants (`Apple Inc.` next to `apple-inc`).

- **T1** (source already `SUPPORTS` entity) and **T3** (graph neighbors of seeds) are pulled *from the graph* — naturally aligned to the objective.
- **T2** is the outlier. Today (shipped #90 `STRUCTURED`) T2 = `entity_search_keys` (Pass-1, open-vocab, blind to the graph) **exact-matched** against entity slugs (`WHERE e.slug IN $keys`, `graph_context_loader._resolve_to_canonical_slugs`). A key hits only if it *exactly equals* an existing slug or recorded alias surface. On non-obvious names it silently misses. Joseph: as built, T2 is "more noise than signal."

## Grounding (verified in code, 2026-05-29)

- `domain` and `source_type` are **controlled vocabularies**, not free generation: `domain` ∈ 23 IDs (`domains.json`, NW-4 v0.4), `source_type` ∈ 21 IDs (`source_types.json`, NW-7 v0.2), enforced as JSON-schema enums (`pass1_schema.py:37-38,76-77`).
- `BELONGS_TO (Entity→Domain)` edge exists (schema v2.1). → entities **can** be scoped by domain: `MATCH (e:Entity)-[:BELONGS_TO]->(:Domain {…})`.
- `source_type` is a property of `Source` **only** — entities carry no `source_type` (`schema.py:73`). → source_type **cannot** scope an entity sub-cluster; it is *form/genre*, orthogonal to *topic*. Stays as Pass-2 prompt metadata.
- T2 resolution is exact-match + `canonical_id`/`ALIAS_OF` traversal — **no fuzzy/semantic bridge**.
- Variant defense is two-layer: **prevention** (read-time T2 anchoring) + **cure** (write-time Stage 6 `canonicalize`, alias ledger → `aliases_emitted` → ingestor Phase 3.5 materializes `ALIAS_OF` edges → strengthens future T2). T2 need not be airtight (cure is the backstop) but prevention is cheaper/less lossy than cure.

## Hypothesis A — domain-scoped, key-driven T2

Replace whole-graph exact-match with **scope-then-fuzzy-match**:

1. **Scope** — candidate pool = entities `BELONGS_TO` the source's `domain` (the sub-cluster). (`source_type` plays no scoping role.)
2. **Match** — use `entity_search_keys` as **regex / whole-token patterns** against the scoped entities' `slug` + `title` (fuzzy, e.g. key `buffett` → `warren-buffett`), not exact slug equality.
3. **Result** → T2.

**Why it should beat shipped `STRUCTURED`:** scope supplies precision (only same-domain entities), fuzzy match supplies recall (keys no longer need to be byte-exact), and the scope is guaranteed graph-aligned because `domain` is controlled-vocab. Keys retain their unique value — surfacing entities the source discusses *without naming* (regex-over-source-text can't) — now matched forgivingly inside a safe scope.

### Open sub-questions (pin during the task, not now)
- **Match predicate** — whole-token vs substring vs normalized; guard short keys (`ai`, `value`) against false positives.
- **Scope = hard filter vs boost** — cross-domain / multi-domain sources may legitimately reference adjacent-domain entities. Lean: *boost* or *domain+adjacent*, not hard-filter; T1/T3 still catch supported/neighbor entities outside the domain. TBD by measurement.
- **Domain-coverage precondition** — if a large fraction of active entities lack `BELONGS_TO` edges, scoping *starves* T2. **First validation step: measure domain-edge coverage on the real graph.**

## Hypothesis B — T3 strictly 1-hop (coupled to A)

Cap T3 at **n=1 neighbors** of the seeds; **remove #71's cold-start 2-hop widening** (`if cold_start and |T2| < _MIN_SEED_THRESHOLD(5): max_hops = 2`).

- **Rationale:** 2-hop neighbors are weakly related (noise); the widening was a crutch for thin cold-start T2.
- **Coupling (the crux):** #71 added the widening *because* cold-start + thin T2 starved context (new sources got 3 pages vs 8). Removing it **re-opens that starvation risk** unless Hypothesis A makes T2 reliably non-thin on cold-start. **B is only safe if A delivers — they must be measured together.**

## Confirmed, no change needed
- Tier priority T1 → T2 → T3, then truncate at `page_cap=50` (tier-desc, then pagerank-desc).
- T3 is **never random**: it is neighbors-*of-seeds*; empty T1+T2 → empty seeds → empty T3 by construction.

## Measurement (NW-9 harness — already exists)
- T2 strategy is dispatched via `T2Mode` (`STRUCTURED` / `LEGACY` / `LAYERED`) in `graph_context_loader`. Add a new mode (e.g. `DOMAIN_SCOPED`) + a benchmark run.
- Metrics: **cold-start density** (does 1-hop T3 + domain-T2 starve?), **precision** (are T2 hits actually relevant to the source?), **variant-rate** (does it reduce downstream variant creation / canonicalize workload?).
- D-90-12 already defines the sunset gate ("cold-start ≥ + precision ≥"); extend it to rank `DOMAIN_SCOPED` vs `STRUCTURED` vs `LEGACY` vs `LAYERED`.

## Lineage
- Revives Task #26's parked **effectiveness-measurement** scope (superseded into #63; deferred as post-#63 follow-up).
- Revises Task #90 (`STRUCTURED` shipped as v1 default; `LEGACY` retained behind dispatch pending D-90-12).
- Carries NW-9 forward from a measurement gate into a concrete redesign+measurement task.
