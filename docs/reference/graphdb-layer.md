# GraphDB-KDB Layer — Schema & CLI Reference

Moved verbatim from `docs/CODEBASE_OVERVIEW.md` §8.2 and §8.6 on 2026-08-19 (Task #146 housekeeping): the overview stays the living map; this static reference lives here. Section numbers are the original overview numbering. §8.1/§8.3–§8.5/§8.7 remain in the overview.

### 8.2 Schema (Kuzu DDL)

```cypher
CREATE NODE TABLE Entity (
    slug          STRING PRIMARY KEY,    -- producer-emitted identifier; bare per D-S1 grandfather for Obsidian
    title         STRING,
    page_type     STRING,                -- summary | concept | article | alias  (values still Obsidian-flavored, per D-A2 deferred)
    status        STRING,                -- active | deprecated (#130 lifecycle, canonical pages only — aliases exempt)
    confidence    STRING,                -- low | medium | high — LOGICALLY DEPRECATED (D-115-12, post-#115): no writes/reads/queries/snapshots; dead column stays until the next destructive schema change
    canonical_id  STRING,                -- Task #74: NULL ⇒ self is canonical; otherwise root canonical slug (chain-flattened, D-R5-13)
    created_at    STRING,                -- ISO with local offset (no UTC normalization per feedback_local_time_everywhere)
    updated_at    STRING,
    first_run_id  STRING,
    last_run_id   STRING
);

CREATE NODE TABLE Source (
    source_id          STRING PRIMARY KEY,
    source_type        STRING,           -- discriminator (multi-source-ready per D32-tempered); "obsidian-kdb-raw" for v1
    canonical_path     STRING,
    status             STRING,           -- active | moved | deleted | error
    file_type          STRING,
    hash               STRING,
    size_bytes         INT64,
    first_seen_at      STRING,
    last_seen_at       STRING,
    last_ingested_at   STRING,           -- renamed from last_compiled_at per D-A2 (graph-side ingestion concept)
    ingest_state       STRING,           -- graph-side name for producer run_state
    ingest_count       INT64,            -- renamed from compile_count per D-A2
    last_run_id        STRING,
    moved_to           STRING
);

CREATE REL TABLE LINKS_TO ( FROM Entity TO Entity, run_id STRING, created_at STRING );
CREATE REL TABLE SUPPORTS ( FROM Source TO Entity, role STRING, hash_at_time STRING, run_id STRING, created_at STRING );
CREATE REL TABLE ALIAS_OF ( FROM Entity TO Entity, run_id STRING, created_at STRING, algorithm STRING );  -- Task #74
```

**Canonicalization invariants** (Task #74, enforced by `graphdb-kdb verify` Layer 3 / C1–C4):

- **C1** — every `Entity` with `canonical_id IS NOT NULL` has a matching `ALIAS_OF` edge to that canonical_id.
- **C2** — every `ALIAS_OF` edge's source `Entity` has `canonical_id` equal to the edge's destination.
- **C3** — `ALIAS_OF` is acyclic AND **flat** (D-R5-13): every `Entity.canonical_id` points at an `Entity` with `canonical_id IS NULL` — no chains, no cycles.
- **C4** — every `LINKS_TO` edge's destination has `canonical_id IS NULL`: LINKS_TO never points at an alias (D-R5-12; alias→canonical remap happens at the canonicalize stage — Stage 5 post-#115 — before graph_sync).

Aliases are exempt from deprecation detection (no `SUPPORTS` edges by OQ-E; canonical-only routing); `_detect_and_mark_deprecations` is scoped to `canonical_id IS NULL`.

**Naming history**: `Entity` was originally `Page` (renamed per D-A1 2026-05-14); graph-side `ingest_*` fields were originally `compile_*` (renamed per D-A2). The producer source-state ledger now uses `run_state` for source lifecycle status (Task #96 C1 prep, schema v3.1); deprecated `compile_state` is accepted only as a migration/replay fallback. The verifier's `_SOURCE_DIRECT_FIELDS` tuples are the alias bridge: `("run_state", "ingest_state")` etc.

---

### 8.6 CLI surface (current)

```
graphdb-kdb init                                        # create Kuzu dir + schema
graphdb-kdb stats [--json]                              # node/edge counts by type
graphdb-kdb neighbors <slug> [--depth N] [--direction]  # BFS expansion
graphdb-kdb incoming <slug>                             # sugar for neighbors --direction in
graphdb-kdb path <from> <to> [--max-hops N]             # shortest directed path
graphdb-kdb cypher "<query>" [--params <json>]          # ad-hoc Cypher escape hatch
graphdb-kdb pagerank [--top N]                          # NetworkX-backed PageRank
graphdb-kdb communities                                 # Louvain community assignments
graphdb-kdb structural-holes                            # inter-community bridge counts
graphdb-kdb deprecated                                  # list deprecated entities (#130 — was `orphans`)
graphdb-kdb subgraph-by-source <source_id>              # source's induced subgraph
graphdb-kdb verify --vault-root <P>                     # diff Kuzu vs manifest.json
graphdb-kdb rebuild --vault-root <P> [--backfill-baton] # drop + replay (D-S2 whole-DB)
                  [--yes] [--json]
graphdb-kdb domains [--json]                            # Domain nodes sorted by entity count
graphdb-kdb snapshot [--vault-root <P>] [--out <dir>]   # JSONL+manifest+schema export (#63.9)
```

`--graph-dir <path>` overrides the Kuzu data directory (default: `$KDB_GRAPH_PATH`, else `<vault>/KDB/graph` derived from `OBSIDIAN_VAULT_PATH`).
