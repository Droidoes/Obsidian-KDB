# Task #63 — GraphDB-KDB Layer (Blueprint)

**Status:** Design — reviewed 2026-05-13 (Codex external review v1 + v2 incorporated); awaiting explicit Proceed on implementation (see §16).
**Date:** 2026-05-11 (drafted), 2026-05-13 (reviewed; Codex v1 + v2 feedback applied).
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #63 (`open`). Supersedes the originally-scoped #26 (EXISTING CONTEXT design review) and #27 (manifest scalability) — both fold into this larger refoundation.
**Companion docs:**
- [`docs/reference/New-GraphDB-Paradigm.md`](reference/New-GraphDB-Paradigm.md) — the conversation that produced this design (verbatim Q&A record)
- [`docs/CODEBASE_OVERVIEW.md`](CODEBASE_OVERVIEW.md) §5 (data flow), §3 (D8 boundary)
- [`docs/reference/compile_result.md`](reference/compile_result.md), [`docs/reference/last_scan.md`](reference/last_scan.md), [`docs/reference/manifest.md`](reference/manifest.md)
- [`kdb_compiler/schemas/compile_result.schema.json`](../kdb_compiler/schemas/compile_result.schema.json) — input contract
**Memory:** `feedback_no_imaginary_risk.md`, `feedback_apples_to_apples_within_session.md`, `feedback_measurability_over_defensive_complexity.md`.

---

## 1. Why this exists

The investigation of #26 + #27 surfaced a deeper architectural truth: the current KDB is shaped as a *raw text → wiki page compiler*, with the graph emerging as an accidental byproduct stored half-and-half in `manifest.json` alongside file metadata. The user's reframe is that KDB is — and should be architected as — a *raw text → knowledge graph compiler*. Wiki pages are one rendering of the graph (the Obsidian-readable view); the graph itself is the durable, queryable system that downstream tooling (search, knowledge-hole detection, adaptive learning paths, EXISTING CONTEXT for next-compile) is meant to consume.

**Scope at the right layer.** **GraphDB-KDB** is a *multi-source* knowledge-graph ontology system. The Obsidian-KDB compile pipeline (`kdb-compile`) is the first — and currently only — contributing producer; the architecture admits future source-types (arxiv papers, YouTube transcripts, other corpora) without re-architecting. The narrower name `kdb-graph` is reserved for future Obsidian-specific graph-view utilities (consumers of GraphDB-KDB), not for the ontology layer itself. See memory note `project_graphdb_kdb_vs_kdb_graph_distinction`.

This task builds the GraphDB as a first-class data subsystem with three load-bearing properties:

1. **Independent of Obsidian KDB.** Other applications (any language with Kuzu bindings) can open and query the graph without going through any KDB-specific code path.
2. **Built parallel to `manifest.json`, not on top of it.** Both consume `compile_result` independently. Either store can be deleted and regenerated from `compile_result` history; neither depends on the other.
3. **Full-scaled v1, not scaffold-MVP.** Complete schema, full ingestion, full query API, validation, rebuild — all on day one, populated from the canonical corpus of compiled sources.

---

## 2. Locked decisions

| ID  | Decision | Rationale |
|---|---|---|
| **D32** | GraphDB-KDB is a *multi-source* raw-text → knowledge-graph compiler at the **storage layer** — the schema admits `Source.source_type` as a discriminator and is source-agnostic. The **ingestion API contract** (`apply_compile_result`) is currently Obsidian-flavored — it consumes the existing `compile_result` shape, which encodes Obsidian-KDB conventions (source_id pattern `^KDB/raw/.+`, page-types `summary\|concept\|article`). A normalized `GraphRun/GraphSource` ingestion contract is deferred until a second source-type actually arrives (YAGNI for v1). The graph is the architectural primitive; `manifest.json`, wiki markdown files, and any future visualization are *renderings* of the graph, not the system itself. | The differentiating bet of the project is "explicit edges beat implicit similarity." Vector RAG flattens ontology into cosine distance; the graph preserves what we paid to build. Storage-layer multi-source readiness is cheap to bake in now; ingestion-layer abstraction without a second producer would be speculative complexity. |
| **D33** | Storage = Kuzu (embedded graph database, Cypher dialect, multi-language bindings). | Purpose-built for the embedded-graph use case. SQLite-with-graph-schema would force consumers to reimplement traversal; NetworkX+JSONL is Python-only. Kuzu is the right primitive: file-based (no daemon), portable (any language with bindings opens the same directory), Cypher (industry-standard), MIT-licensed, production-grade. Latest stable: 0.11.3. |
| **D34** | Independence-by-shared-upstream: `manifest_update.py` and `graphdb_kdb.ingestor` each consume `compile_result + last_scan + run_id` independently. Neither reads or writes the other's store. | Real independence (per the ablation test): delete `manifest.json` → GraphDB still works; delete `GraphDB-KDB/` → manifest still works. Both regenerable from `state/runs/<run_id>.json` history (which carries the compile_results). |
| **D35** | GraphDB physical location: `~/Droidoes/GraphDB-KDB/` — sibling to the `Obsidian-KDB` project under the active projects root. Cross-project read/write access is the design intent; default path overridable via `KDB_GRAPH_PATH` env var. | Physical separation mirrors the logical separation — GraphDB-KDB is a peer subsystem, not a child of Obsidian-KDB. Avoids OneDrive sync corruption on Kuzu binary files entirely (Droidoes is not OneDrive-synced). Backup story: derived state is *recoverable*, not backed up directly — `graphdb-kdb rebuild` regenerates from `~/Obsidian/KDB/state/runs/*.json` (which IS OneDrive-backed). Belt-and-suspenders via `graphdb-kdb snapshot` (#63.9) exports JSONL to the vault. |
| **D36** | Naming triad: Python module `graphdb_kdb`, Kuzu directory `GraphDB-KDB/`, CLI command `graphdb-kdb`. The name `kdb-graph` is **reserved** for a future Obsidian-graph-view utility (downstream consumer of GraphDB-KDB; out of #63 scope). | CLI name matches the brand and the ontology-layer scope, not the narrower Obsidian-KDB project family. `graphdb-kdb` operates on the cross-source ontology; `kdb-graph` (future) would produce Obsidian-specific outputs from it. Python module uses underscores because identifiers can't contain hyphens. |
| **D37** | Schema includes `Entity` and `Source` as node types; `LINKS_TO` (Entity→Entity) and `SUPPORTS` (Source→Entity) as relationship types. Provenance is first-class graph data, not a sidecar. *(Originally `Page` node-table; renamed to `Entity` per D-A1 2026-05-14.)* | Source-attribution queries ("show me everything compiled from Karpathy's attention paper", "which sources support concept X?") become natural graph traversals. Splitting sources into a separate store would mean re-introducing the manifest-style "two files that must agree." |
| **D38** | Pipeline integration: new **Stage 9 (`graph_sync`)** in `kdb_compile.py`, runs AFTER Stage 8 (manifest write) succeeds. Failure is **non-fatal**: graph_sync errors emit a warning + journal entry, but the overall compile run still returns success. | Honors D34 independence: a failed graph write must not roll back a successful manifest write. Recovery is via `graphdb-kdb rebuild`. |
| **D39** | Rebuild path: `graphdb-kdb rebuild` drops all Kuzu tables and replays the **eligible** subset of `state/runs/<run_id>.json` in chronological order. **Eligibility filter:** `success=true AND dry_run=false AND payload_present` (where payload = `compile_result` + `last_scan`, present as sidecar archive at `state/runs/<run_id>/compile_result.json` + `state/runs/<run_id>/last_scan.json` — per #63.0 outcome, not embedded inline in the journal). Dry-run journals are deliberate fictions; failed runs may carry partial/invalid payloads. This **proves** independence — Kuzu can be regenerated without ever reading `manifest.json`, **for all post-#63 runs**. Pre-#63 historical runs are unrecoverable except for the latest baton state — see §13.1 Q3 for the recorded #63.0 outcome. | If GraphDB drifts from compile-history truth, regenerate from compile-history truth. Filter excludes only deliberately-not-real runs (dry-run) and runs that didn't reach a valid compile_result (failed). In practice `success=true` already encompasses manifest-write success today (Stage 8 must complete for the journal to mark `success=true`), so the absence of an explicit `manifest_written` gate is **not** asking the rebuilder to replay manifest-failed runs — it avoids creating a hard dependency on a manifest-specific field name, preserving option-value if Stage 8/9 are later decoupled (per L7's deferred work). Sharpened per Codex v3 nuance. |
| **D40** | Advanced analytics (PageRank, community detection, betweenness centrality) use a **hybrid** strategy: Kuzu Cypher fetches topology (edge lists, node attributes); NetworkX/python-louvain computes the algorithm; results materialized back into Kuzu as node properties when desired. | Kuzu doesn't ship native PageRank or Louvain. Implementing these in Cypher (iterative random walks) is awkward; calling out to mature Python libs is cleaner. At our scale (10⁴ nodes ceiling), the hybrid cost is sub-second per algorithm. |
| **D-A1** *(2026-05-14, Round 1 Codex)* | Schema rename pass: `Page` node-table → `Entity`. Honest signaling that the node is an abstract graph entity, not a wiki-page rendering artifact. Free upgrade while schema is empty/small. | `Node` would collide with Kuzu's NODE keyword + universal graph-theory term. `Entity` signals abstract identity. Mechanical sweep across DDL, Cypher strings, dataclasses, tests, CLI labels. |
| **D-A2** *(2026-05-14, Round 1 Codex)* | Source field renames: `compile_state → ingest_state`, `compile_count → ingest_count`, `last_compiled_at → last_ingested_at`. `page_type/status/confidence` on Entity remain (their *values* are Obsidian-flavored; rename without revisiting values would be cosmetic). | Pipeline-specific *field names* become pipeline-neutral now; pipeline-specific *values* wait for producer #2 to inform the right abstraction. |
| **D-B1** *(2026-05-14, Round 1 Codex)* | Rebuilder is **B-lite (adapter split)**: thin generic replay core in `graphdb_kdb/rebuilder.py` (drop & recreate, chronological discovery, progress/error reporting) + producer-specific logic in `graphdb_kdb/adapters/obsidian_runs.py` (eligibility, journal parsing, sidecar loading, calls `apply_compile_result`). Rule: **`graphdb_kdb/` core MUST NOT `import kdb_compiler.*`** — adapter reads JSON by documented field names. Public function name `rebuild_from_obsidian_runs(...)`. | Pure C (core imports producer types) would silently weaken D34 independence. B-lite preserves it by structure, not by convention. Cost: ≤50 LOC of separation. |
| **D-S0** *(2026-05-14, Round 2 Codex)* | **Stage 9 wiring routes through the Obsidian adapter, not direct core call.** `kdb_compile.py` Stage 9 calls `graphdb_kdb.adapters.obsidian_runs.sync_current_run(cr, scan, run_id)`; the adapter opens the GraphDB connection and calls `apply_compile_result(...)` internally. Single Obsidian→graph entry point for both live sync (Stage 9) and replay (`graphdb-kdb rebuild`). | Makes Doc C's "producer never calls core directly" rule literal, not aspirational. Single code path = one place to debug/test/evolve. Closes OQ-E9 in extraction roadmap. |
| **D-S1** *(2026-05-14, Round 2 Codex)* | **Multi-producer entity-id namespacing**: Obsidian grandfathered as bare slugs (implicit `obsidian:` namespace); all future producers MUST use `<source_type>:<entity_id>` prefix. Adapter declares `entity_id_namespace: ClassVar[str \| None]`. | Full retroactive migration of 62+ Obsidian entities to `obsidian:concepts/...` is a destructive schema change with no operational benefit on the canonical corpus. Grandfathering is cheaper; future producers prefix to avoid collisions. Queries filter producers via `Source.source_type`, not slug prefix parsing. |
| **D-S2** *(2026-05-14, Round 2 Codex)* | **Rebuild blast radius v1**: `graphdb-kdb rebuild` always drops the **whole DB**, regardless of `--producer` flag. Producer-scoped rebuild is deferred until producer #2 ships AND the team agrees the scoped semantics. CLI prints a warning before executing whole-DB drop. | At v1 we have a single producer; whole-DB drop is the simple correct semantics. When producer #2 lands, deferring this decision until then lets the right semantics be informed by real co-tenancy needs (delete-by-source_type, isolation, etc.). Tracked as **L8**. |
| **D-S3** *(2026-05-14, Round 2 Codex)* | **Adapter version-support declaration**: each adapter declares `supported_journal_versions: ClassVar[list[str]]`. Adapter raises `UnsupportedJournalVersionError` on version mismatch rather than silently producing wrong graph state. | Producer journal `schema_version` evolves (Obsidian is at `2.0` today). Without explicit version-support declarations, an adapter built for `2.0` would silently mis-parse a `3.0` journal. Versioning discipline must be in place before Stage 1 of package extraction, not Stage 4. |

---

## 3. Architecture at a glance

```
                       compile_result.json
                            (per run)
                              │
              ┌───────────────┴────────────────┐
              │  (two independent consumers)   │
              ▼                                ▼
      manifest_update.py             graphdb_kdb.ingestor
              │                                │
              ▼                                ▼
       manifest.json                  ~/Droidoes/GraphDB-KDB/
       (JSON ledger:                  (Kuzu directory; sibling to
        sources + pages +              Obsidian-KDB project)
        edges + system state)         │
              │                       │
              ▼                       ▼
       context_loader.py       OTHER APPLICATIONS:
       (today's consumer;      - graphdb-kdb CLI (Cypher, neighbors, pagerank, ...)
        regex-over-slug-list   - Python apps (kuzu.Database / Connection)
        for EXISTING CONTEXT)  - Future Node/Go/Rust/Java consumers
                               - Future graph visualizers
                               - Future RAG/agent integrations
```

Two key properties of this picture:

- **No arrow runs between `manifest.json` and `GraphDB-KDB/`.** They both depend on `compile_result`; they do not depend on each other.
- **`context_loader.py` is not yet wired to GraphDB.** That's the originally-scoped Task C (graph-native seed selection) which becomes a follow-up task after this layer is live and trusted.

---

## 4. Schema (Kuzu DDL)

Lives in `graphdb_kdb/schema.py` as Python string constants; applied at first connection in `graphdb_kdb.graphdb.GraphDB._ensure_schema()`.

```cypher
-- Node tables
CREATE NODE TABLE Entity (
    slug          STRING PRIMARY KEY,
    title         STRING,
    page_type     STRING,        -- summary | concept | article
    status        STRING,        -- active | stale | archived | orphan_candidate
    confidence    STRING,        -- low | medium | high
    created_at    STRING,
    updated_at    STRING,
    first_run_id  STRING,        -- run that introduced this page
    last_run_id   STRING         -- most recent run that touched this page
);

CREATE NODE TABLE Source (
    source_id          STRING PRIMARY KEY,    -- e.g., KDB/raw/attention-paper.md
    source_type        STRING,                -- obsidian-kdb-raw | (future) arxiv | youtube-transcript | ...
    canonical_path     STRING,
    status             STRING,                -- active | moved | deleted | error
    file_type          STRING,                -- markdown | binary | unknown
    hash               STRING,                -- sha256:<64-hex> (current)
    size_bytes         INT64,
    first_seen_at      STRING,
    last_seen_at       STRING,
    last_ingested_at   STRING,             -- empty string if never ingested (per D-A2 rename of last_compiled_at)
    ingest_state       STRING,                -- compiled | recompiled | moved_source | error | metadata_only (per D-A2 rename of compile_state)
    ingest_count       INT64,                  -- per D-A2 rename of compile_count
    last_run_id        STRING,
    moved_to           STRING                 -- only meaningful when status=moved
);

-- Relationship tables
CREATE REL TABLE LINKS_TO (
    FROM Entity TO Entity,
    run_id      STRING,        -- run that emitted this edge
    created_at  STRING
);

CREATE REL TABLE SUPPORTS (
    FROM Source TO Entity,
    role          STRING,      -- primary | supporting (v1; historical-role deferred — history belongs in run_journal, not live graph)
    hash_at_time  STRING,      -- source hash when this support was emitted
    run_id        STRING,
    created_at    STRING
);
```

**Design notes:**

- `LINKS_TO` is **stored uni-directionally** (Entity→Entity following `outgoing_links`). Backward traversal ("who links to me?") is a Cypher pattern `MATCH (s)-[:LINKS_TO]->(t {slug: $slug})` — no materialized inverse index needed.
- `Entity.created_at` / `Entity.first_run_id` are set on first INSERT and **never overwritten** on subsequent updates. `updated_at` / `last_run_id` bump every run that touches the entity.
- `Source.status='moved'` keeps the original `source_id` as PK; `moved_to` points at the new id; a separate `Source` row exists for the destination. (Kuzu doesn't permit changing a primary key in place.)
- `Source.source_type` is the multi-source discriminator. v1 emits only `"obsidian-kdb-raw"`. Future source-types (`"arxiv"`, `"youtube-transcript"`, etc.) plug in without schema change; query patterns like `MATCH (s:Source) WHERE s.source_type='arxiv' RETURN ...` work uniformly across source kinds.
- `Entity.body` is intentionally absent — bodies live in the markdown files (D8 boundary). The GraphDB stores semantic graph state, not file content.
- **Timestamps are `STRING`, not Kuzu native `TIMESTAMP`.** Stored as `datetime.now().astimezone().isoformat()` (e.g., `2026-05-13T20:30:00-04:00`). Preserves the system-local offset per project rule `feedback_local_time_everywhere`. Kuzu's native `TIMESTAMP` type normalizes to UTC internally and would lose the offset on round-trip; the project's existing `manifest.json` and `run_journal` already use ISO-with-offset strings. Round-trip preservation is verified by a dedicated test in `test_ingestion.py`.

---

## 5. Ingestion algorithm

Entry point: `graphdb_kdb.ingestor.apply_compile_result(cr, scan_dict, run_id) -> SyncResult`. Pure function except for the Kuzu transaction. Atomic per run (all-or-nothing).

```python
def apply_compile_result(
    cr: dict,                      # compile_result dict (already validated by Stage 4)
    scan_dict: dict,               # last_scan dict (already validated by Stage 2)
    run_id: str,
    *,
    conn: kuzu.Connection,
) -> SyncResult:
    """Apply one compile run's deltas to the Kuzu graph. Atomic per run."""

    now = datetime.now().astimezone()  # local time w/ offset, per memory note

    with _transaction(conn):
        # --- Phase 1: refresh Source nodes from scan ---
        for entry in scan_dict["files"]:
            _upsert_source_from_scan(conn, entry, run_id, now)

        # --- Phase 2: reconcile MOVED + DELETED sources ---
        for op in scan_dict.get("to_reconcile", []):
            if op["type"] == "MOVED":
                _handle_source_moved(conn, op, run_id, now)
            elif op["type"] == "DELETED":
                _handle_source_deleted(conn, op, run_id, now)

        # --- Phase 3: ingest compiled_sources ---
        for cs in cr["compiled_sources"]:
            for page in cs["pages"]:
                _upsert_entity(conn, page, run_id, now)
                _replace_outgoing_links(conn, page, run_id, now)
            _replace_supports_for_source(conn, cs, run_id, now)  # atomic per-source: drop prior SUPPORTS, then recreate
            _update_source_ingest_state(conn, cs, run_id, now)

        # --- Phase 4: orphan-candidate detection ---
        # An Entity has zero remaining SUPPORTS edges → mark orphan_candidate
        orphans = _detect_and_mark_orphans(conn, run_id, now)

    return SyncResult(
        entities_upserted=...,
        edges_upserted=...,
        sources_upserted=...,
        orphans_detected=orphans,
        run_id=run_id,
    )
```

**Per-step Cypher (representative — full text in `graphdb_kdb/ingestor.py`):**

- **Upsert page**:
  ```cypher
  MERGE (p:Entity {slug: $slug})
  ON CREATE SET p.created_at=$ts, p.first_run_id=$run_id
  SET p.title=$title, p.page_type=$type, p.status=$status,
      p.confidence=$conf, p.updated_at=$ts, p.last_run_id=$run_id
  ```

- **Replace outgoing edges (idempotent per-page)**:
  ```cypher
  MATCH (a:Entity {slug: $slug})-[r:LINKS_TO]->()
  DELETE r;

  -- Then for each target_slug in outgoing_links:
  MATCH (a:Entity {slug: $slug})
  MATCH (b:Entity {slug: $target})
  CREATE (a)-[:LINKS_TO {run_id: $run_id, created_at: $ts}]->(b)
  ```
  (If `target_slug` doesn't yet exist as an Entity node, the `CREATE` is skipped — a dangling outgoing_link is a validator-catch upstream, not the ingestor's job.)

- **Upsert source — Phase 1 (scan refresh; does NOT touch compile-state fields)**:
  ```cypher
  MERGE (s:Source {source_id: $sid})
  ON CREATE SET s.first_seen_at=$ts, s.source_type=$source_type,
                s.ingest_count=0, s.last_ingested_at=''
  SET s.canonical_path=$path, s.hash=$hash, s.size_bytes=$size,
      s.file_type=$ftype, s.status='active',
      s.last_seen_at=$ts, s.last_run_id=$run_id
  ```
  Phase 1 refreshes scan-derived metadata only. `last_ingested_at`, `ingest_state`, `ingest_count` are intentionally **not** mutated here — they belong to Phase 3 and would otherwise misrepresent unchanged or metadata-only sources as freshly ingested (Codex v2 NEW MATERIAL #1). `ON CREATE` seeds them with neutral defaults.

- **Update source compile-state — Phase 3 (fires only for sources in `cr.compiled_sources`)**:
  ```cypher
  MATCH (s:Source {source_id: $sid})
  SET s.last_ingested_at=$ts, s.ingest_state=$state,
      s.ingest_count = s.ingest_count + 1, s.last_run_id=$run_id
  ```
  Increments `ingest_count` and writes ingest-state fields only for sources that produced a `compile_result` entry. Combined with Phase 1, this means every Source row has accurate scan-time `last_seen_at` AND a separate ingest-time `last_ingested_at`.

- **Replace SUPPORTS for a source** (atomic per-source; symmetric to `_replace_outgoing_links`):
  ```cypher
  -- 1. Drop all existing SUPPORTS edges from this source
  MATCH (s:Source {source_id: $sid})-[r:SUPPORTS]->()
  DELETE r;

  -- 2. Recreate one SUPPORTS edge per page in the current compiled_source entry:
  MATCH (s:Source {source_id: $sid})
  MATCH (p:Entity {slug: $slug})
  CREATE (s)-[:SUPPORTS {role: $role, hash_at_time: $hash, run_id: $run_id, created_at: $ts}]->(p)
  ```
  Pages the source no longer supports lose their SUPPORTS edge in step 1; if no other source supports them, Phase 4 orphan detection correctly flags them. This fixes a class of bug where stale SUPPORTS edges would persist after a source recompile drops a page (Codex review CRITICAL #2).

- **MOVED reconciliation** — transfer active SUPPORTS to destination, mark old source as historical:
  ```cypher
  -- 1. Transfer SUPPORTS edges from old source to new source
  MATCH (old:Source {source_id: $old_sid})-[r:SUPPORTS]->(p:Entity)
  WITH old, p, r.role AS role, r.hash_at_time AS hash, r.run_id AS rid, r.created_at AS cts
  DELETE r
  WITH old, p, role, hash, rid, cts
  MATCH (new:Source {source_id: $new_sid})
  CREATE (new)-[:SUPPORTS {role: role, hash_at_time: hash, run_id: rid, created_at: cts}]->(p);

  -- 2. Mark old source as moved (historical breadcrumb; no active SUPPORTS edges)
  -- Note: only fields defined in the Source schema are written. No `updated_at` field on Source — use `last_seen_at`.
  MATCH (old:Source {source_id: $old_sid})
  SET old.status='moved', old.moved_to=$new_sid, old.last_run_id=$run_id, old.last_seen_at=$ts
  ```
  Old Source row remains as historical record but holds zero active SUPPORTS edges; queries filtering on `status='active'` see only the destination Source. Consistent with `manifest_update.py`'s rekey-on-move semantics.

- **Orphan detection**:
  ```cypher
  MATCH (p:Entity)
  WHERE NOT EXISTS { MATCH (:Source)-[:SUPPORTS]->(p) }
    AND p.status <> 'orphan_candidate'
  SET p.status='orphan_candidate', p.last_run_id=$run_id, p.updated_at=$ts
  RETURN p.slug
  ```

**Failure semantics:** if Kuzu raises during any phase, the transaction rolls back. Caller (Stage 9 of `kdb_compile.py`) logs the error to the journal but **does not fail the overall run** (per D38). User can recover via `graphdb-kdb rebuild` or by re-running the compile (which will re-attempt ingestion).

---

## 6. Query API

### 6.1 Python surface (`graphdb_kdb.graphdb.GraphDB`)

| Method | Returns | Description |
|---|---|---|
| `__init__(graph_dir, *, read_only=False)` | — | Opens (or creates) the Kuzu database at `graph_dir`. |
| `apply_compile_result(cr, scan, run_id)` | `SyncResult` | Full ingest of one run (delegates to `ingestor`). |
| `get_entity(slug)` | `Entity \| None` | Lookup one node. |
| `get_source(source_id)` | `Source \| None` | Lookup one source. |
| `neighbors(slug, *, direction='out', depth=1)` | `list[Entity]` | BFS expansion; `direction ∈ {out, in, both}`. |
| `incoming_links(slug)` | `list[Entity]` | Sugar for `neighbors(slug, direction='in', depth=1)`. |
| `outgoing_links(slug)` | `list[Entity]` | Sugar for `neighbors(slug, direction='out', depth=1)`. |
| `shortest_path(from_slug, to_slug, *, max_hops=10)` | `list[str] \| None` | Path of slugs, or `None` if unreachable. |
| `entities_for_source(source_id)` | `list[Entity]` | All entities a source supports. |
| `sources_for_entity(slug)` | `list[Source]` | All sources supporting an entity. |
| `subgraph_by_source(source_id)` | `dict {nodes, edges}` | Subgraph induced by one source's supported pages. |
| `orphan_entities()` | `list[Entity]` | Entities with `status='orphan_candidate'`. |
| `pagerank(*, top_n=None)` | `list[(slug, score)]` | NetworkX-backed (hybrid per D40). |
| `communities(*, algorithm='louvain')` | `dict[slug, community_id]` | NetworkX/python-louvain backed. |
| `structural_holes()` | `list[(comm_a, comm_b, n_bridges)]` | Pairs of communities with few inter-edges; surfaces "knowledge-hole" candidates. |
| `cypher(query, params=None)` | `list[dict]` | Ad-hoc Cypher escape hatch. |
| `stats()` | `dict` | Node/edge counts by type. |
| `verify_against_manifest(manifest_path)` | `VerifyResult` | Diff Kuzu vs manifest.json; report divergences. |
| `rebuild_from_runs(runs_dir)` | `RebuildResult` | Drop and replay the **eligible** subset of compile_results (per D39 filter: `success=true AND dry_run=false AND payload_present`) in chronological order. |

### 6.2 CLI surface (`graphdb-kdb`)

| Subcommand | What it does |
|---|---|
| `graphdb-kdb init` | Creates the Kuzu directory + schema. Idempotent. |
| `graphdb-kdb sync --vault-root <path>` | Manually trigger ingest from the current `state/compile_result.json` + `state/last_scan.json`. Mirrors what Stage 9 does automatically. |
| `graphdb-kdb verify --vault-root <path>` | Compare GraphDB to `manifest.json`. Exit 0 if perfect agreement; nonzero with diff report otherwise. |
| `graphdb-kdb rebuild --vault-root <path>` | Drop Kuzu tables; replay the **eligible** subset of `state/runs/*.json` (filter: `success=true AND dry_run=false AND payload_present`) in chronological order. Independence proof — does not read `manifest.json`. |
| `graphdb-kdb stats` | Print node/edge counts. |
| `graphdb-kdb neighbors <slug> [--depth N] [--direction out\|in\|both] [--json]` | List neighbors. |
| `graphdb-kdb incoming <slug>` | Sugar; equivalent to `neighbors <slug> --direction in --depth 1`. |
| `graphdb-kdb path <from_slug> <to_slug>` | Print shortest-path chain. |
| `graphdb-kdb pagerank [--top N] [--json]` | Print PageRank-ranked pages. |
| `graphdb-kdb communities [--json]` | Print community assignments (Louvain via python-louvain). |
| `graphdb-kdb orphans` | List orphan-candidate pages. |
| `graphdb-kdb subgraph-by-source <source_id> [--json]` | Export a source's induced subgraph. |
| `graphdb-kdb cypher "<query>" [--params <json>] [--json]` | Run ad-hoc Cypher. |

Output format default: plain text (human-readable, aligned columns). `--json` flag returns structured JSON for any read subcommand.

---

## 7. Pipeline integration

### 7.1 Stage 9 — `graph_sync`

Added to `kdb_compile.py` after Stage 8 (`persist state`) completes successfully. Stage skeleton (mirrors the existing `_stage_open/_stage_close` pattern):

```python
# ----- [9] graph_sync -----
_stage_open(9)
try:
    from graphdb_kdb import GraphDB, default_graph_path
    graph_dir = default_graph_path()  # ~/Droidoes/GraphDB-KDB/ unless KDB_GRAPH_PATH overrides
    with GraphDB(graph_dir) as graph:
        sync_result = graph.apply_compile_result(cr, scan_dict, run_id)
    _stage_close(
        9, ok=True,
        entities_upserted=sync_result.entities_upserted,
        edges_upserted=sync_result.edges_upserted,
        sources_upserted=sync_result.sources_upserted,
        orphans_detected=len(sync_result.orphans_detected),
    )
except Exception as exc:
    # Per D38: graph_sync failure is non-fatal. Log + journal, continue.
    note = f"{type(exc).__name__}: {exc}"
    _stage_close(9, ok=False, note=note, recovery_hint="run: graphdb-kdb rebuild")
    # Note: NO call to _fail(); the overall run remains successful.
```

**Stage names list updated:** `STAGE_NAMES` in `run_journal.py` gains `"graph_sync"` as element 9 (1-indexed). `_STAGE_TOTAL` becomes 9.

**Ordering with `_finalize_and_write`:** Stage 9 runs **before** `_finalize_and_write` so its `_stage_open`/`_stage_close` journal entry is captured in the persisted run journal. Final run-success status remains `true` even when Stage 9 closes with `ok=false` — this is what makes graph_sync non-fatal at the run-outcome level while still recording the failure in the journal for later inspection or as a trigger for `graphdb-kdb rebuild`.

### 7.2 Failure modes

| Failure | Effect on run | Recovery |
|---|---|---|
| `kuzu` not installed | Stage 9 fails non-fatally; journal flags it; compile run returns success | `pip install kuzu>=0.11` |
| Kuzu file lock contention | Stage 9 fails non-fatally on first contention; clear error message in journal | Identify other holder (typically a stale Python REPL with an open kuzu connection); rerun `graphdb-kdb sync`. Concurrent `kdb-compile` invocations are not expected (L1); no retry/backoff per `feedback_no_imaginary_risk` |
| Schema drift (existing DB has older schema) | `GraphDB._ensure_schema` detects via stored version row, logs incompatibility, fails Stage 9 non-fatally | `graphdb-kdb rebuild` |
| Transaction violation (e.g., LLM-emitted slug duplicate) | Single-run ingestion fails; transaction rolls back; Kuzu state unchanged | Reduces to "next run will retry"; or `graphdb-kdb rebuild` |

---

## 8. Validation + rebuild paths

### 8.1 `graphdb-kdb verify`

Walks `manifest.json` and confirms every (page, edge, source) is present in Kuzu with matching attributes. Three classes of divergence:

- **Missing in Kuzu**: present in manifest, absent in graph. Most common cause: graph_sync failed on a prior run.
- **Missing in manifest**: present in graph, absent in manifest. Most common cause: manifest write succeeded but a subsequent partial restore lost it.
- **Attribute mismatch**: both present but differ on a tracked field (title, page_type, last_run_id, ...).

Exit code: `0` if perfect agreement, `1` otherwise. Stdout: aligned diff report. `--json` flag for machine consumption.

### 8.2 `graphdb-kdb rebuild`

**The independence proof.** Drops all Kuzu tables; iterates the **eligible** subset of `state/runs/<run_id>.json` in chronological order; extracts each run's `compile_result` and `last_scan`; applies via `apply_compile_result`. Eligibility per D39: `success=true AND dry_run=false AND payload_present` (embedded inline OR sidecar archive). Run-journal eligibility-field availability + payload shape are confirmed by sub-task **#63.0** before any other implementation work. Result: the Kuzu state at the end of replay equals what live ingestion of eligible runs would have produced.

This subcommand is also the migration entry point for the canonical corpus: the first time we run it, eligible already-compiled sources from `state/runs/` get backfilled into Kuzu.

---

## 9. File structure

```
graphdb_kdb/
├── __init__.py              # exports GraphDB, SyncResult, Entity, Source
├── __main__.py              # python -m graphdb_kdb dispatches to cli.main
├── schema.py                # NODE_TABLE_DDL, REL_TABLE_DDL, SCHEMA_VERSION
├── graphdb.py               # GraphDB class: connection mgmt, context manager,
│                            #   _ensure_schema, transaction helpers
├── ingestor.py              # apply_compile_result + private _upsert_* helpers
├── queries.py               # neighbors, pagerank, communities, structural_holes,
│                            #   shortest_path, sub-graph extraction
├── verifier.py              # verify_against_manifest + DiffReport
├── rebuilder.py             # rebuild_from_runs + run-journal iteration
├── cli.py                   # graphdb-kdb subcommands; argparse routing
├── types.py                 # Entity, Source dataclasses; SyncResult, VerifyResult
└── tests/
    ├── __init__.py
    ├── conftest.py          # shared fixtures: synthetic compile_result, scan
    ├── test_schema.py
    ├── test_ingestion.py    # upsert, edge replace, reconcile, orphan detection
    ├── test_queries.py      # all read primitives
    ├── test_verifier.py     # agreement + divergence cases
    ├── test_rebuilder.py    # replay produces same final state
    ├── test_cli.py          # subcommand routing + output formats
    └── fixtures/
        ├── synthetic_compile_result_basic.json
        ├── synthetic_last_scan_basic.json
        ├── synthetic_compile_result_with_reconcile.json
        └── synthetic_last_scan_with_reconcile.json
```

`pyproject.toml` updates:

```toml
[project]
dependencies = [
    # ... existing ...
    "kuzu>=0.11",
    "networkx>=3.0",
    "python-louvain>=0.16",
]

[project.scripts]
# ... existing ...
graphdb-kdb = "graphdb_kdb.cli:main"

[tool.setuptools.packages.find]
include = ["kdb_compiler*", "kdb_benchmark*", "graphdb_kdb*"]  # add graphdb_kdb*
exclude = ["knowledge_graph*", "docs*", "tests*", "benchmark*"]

[tool.setuptools.package-data]
graphdb_kdb = []  # no static assets (schema is Python constants)
```

`[tool.pytest.ini_options].testpaths` gains `graphdb_kdb/tests`.

---

## 10. Test surface (target counts)

| File | Tests | Coverage |
|---|---|---|
| `test_schema.py` | ~4 | Table creation idempotent; schema version stored; reopen preserves schema. |
| `test_ingestion.py` | ~17 | Single-entity upsert; multi-entity upsert; outgoing edges replace (add, remove, change); SUPPORTS upsert; **SUPPORTS replacement (stale support cleared when a source recompile drops an entity)**; **MOVED source transfers active SUPPORTS to destination**; source upsert; MOVED reconcile; DELETED reconcile; orphan detection; orphan revival on re-support; transaction rollback on bad input; idempotent re-apply of same run; multiple sources in one run; **timestamp offset round-trip (local ISO string preserved through write + read)**; **Phase 1 (scan refresh) does NOT mutate `last_ingested_at` / `ingest_state` / `ingest_count` — only Phase 3 does (Codex v2 NEW M1, per D-A2 rename)**; **MOVED reconciliation writes only fields defined on the Source schema (no `updated_at`; uses `last_seen_at`)**. |
| `test_queries.py` | ~14 | get_entity (hit/miss); get_source; neighbors at depths 1/2/3, directions out/in/both; incoming_links convenience; shortest_path success + unreachable; entities_for_source; sources_for_entity; subgraph_by_source structure; orphan_entities; pagerank correctness on a known small graph; communities correctness on a known small graph; structural_holes; cypher escape hatch; stats. |
| `test_verifier.py` | ~6 | Perfect agreement; missing-in-kuzu detected; missing-in-manifest detected; attribute mismatch detected; verifies sources too, not just pages; exit codes + JSON output. |
| `test_rebuilder.py` | ~7 | Empty Kuzu + 0 runs → no-op; replay of 1 run; replay of N runs; replay preserves orphan transitions over time; replay output matches live-ingestion output for identical inputs; **rebuild fails clearly when a journal lacks the replay payload (post-#63.0 fallback path)**; **replay-eligibility filter: dry-run journals and failed runs are excluded; only `success=true AND dry_run=false AND payload_present` runs are replayed (Codex v2 C1)**. |
| `test_cli.py` | ~10 | Each subcommand: argparse routing; JSON output; non-zero exit on missing args. Mocked Kuzu in unit tests; integration tests in `tests/integration/` with real Kuzu. |
| `tests/integration/test_stage9.py` | ~3 | Stage 9 outcome persists in run journal on `ok=true` path; Stage 9 outcome persists in run journal on `ok=false` (failure) path; final run-success stays `true` even when Stage 9 closes with `ok=false`. |
| **Total** | **~61** | |

Test discipline: **TDD per superpowers:test-driven-development**. Write failing test first; minimal implementation; refactor. Real Kuzu DB created at `tests/tmp/<test_id>.kuzu` and cleaned up via pytest fixtures.

---

## 11. Sequencing — sub-task breakdown

Task #63 is the parent. Sub-task IDs assigned as work begins (#64, #65, ...) per the project's "next free ID, don't backfill" rule. Suggested order:

| Sub | Title | Deliverable | Dependencies |
|---|---|---|---|
| **#63.0** | Replay-contract verification | Inspect `kdb_compiler/run_journal.py` v2 schema for **two** requirements: (i) **eligibility fields** (`success`, `dry_run`) present and reliably populated per run; (ii) **payload** (`compile_result` + `last_scan`) embedded inline OR available as sidecar. Decision matrix: (a) both present → no code change; proceed. (b) eligibility fields missing → add to run_journal write-side BEFORE #63.1 (these gate replay correctness). (c) payload missing → either add write-side inline embedding OR add per-run `compile_result.json` sidecar archive at `state/runs/<run_id>/`. (d) historical runs unrecoverable → downgrade D39 to "prospective from #63.0 forward" + one-off backfill from current on-disk `compile_result.json`. Outcome recorded in D39 rationale. | None (pre-implementation blocker; gates all others). |
| **#63.1** | Schema + skeleton | `graphdb_kdb/{schema,graphdb,types}.py` + `test_schema.py` green. `graphdb-kdb init` works. Includes `default_graph_path()` helper + `SCHEMA_VERSION` + empty migration registry (Q6). | **#63.0**. |
| **#63.2** | Ingestion algorithm | `ingestor.py` + `test_ingestion.py` green on synthetic fixtures. | #63.1. |
| **#63.3** | Read query API | `queries.py` + `test_queries.py` green. CLI `neighbors`, `incoming`, `path`, `stats`, `cypher` working. | #63.1, #63.2. |
| **#63.4** | Analytics (hybrid) | PageRank + Louvain + structural_holes via NetworkX. CLI `pagerank`, `communities`, `orphans`. | #63.3. |
| **#63.5** | Verifier | `verifier.py` + CLI `graphdb-kdb verify`. | #63.2. |
| **#63.6** | Rebuilder | `rebuilder.py` + CLI `graphdb-kdb rebuild`. Backfill canonical-corpus runs as the first proof. | #63.2. |
| **#63.7** | Pipeline Stage 9 wiring | Edit `kdb_compile.py` to add Stage 9; update `run_journal.py` STAGE_NAMES; add stage-9 progress emit. New integration tests. | All preceding. |
| **#63.8** | Documentation | CODEBASE_OVERVIEW.md gains §8 "GraphDB-KDB Layer" with D32–D40 ledger entries. README mention. | All preceding. |
| **#63.9** | Snapshot/export | `graphdb-kdb snapshot` exports `pages.jsonl` + `edges.jsonl` + `sources.jsonl` to `~/Obsidian/KDB/state/graph-snapshots/<ts>/`. Belt-and-suspenders backup at the JSONL-text level (diffable, OneDrive-friendly, regen target if rebuild ever broke). | #63.3. |

Each sub-task gets its own commit (or small set of commits). **#63.0 is a pre-implementation gate**; no other sub-task lands until its outcome is recorded in D39's rationale. Sub-tasks #63.1–#63.3 are the critical path to a usable GraphDB; #63.4–#63.6 add the analytics + safety nets; #63.7 enables automatic syncing; #63.8 closes the loop with documentation; #63.9 adds the snapshot/export safety net.

---

## 12. Dependencies + setup

```bash
pip install kuzu>=0.11 networkx>=3.0 python-louvain>=0.16
```

- **kuzu (0.11.3)**: ~30 MB wheel; Linux x86_64 prebuilt available. No native build required.
- **networkx (3.x)**: pure Python; depends on `numpy` and `scipy` for some algorithms.
- **python-louvain (0.16)**: pure Python; thin wrapper over networkx.

All three are MIT or BSD-licensed; no commercial licensing issues.

Verification step after install:
```bash
python -c "import kuzu; print(kuzu.__version__)"
# expected: 0.11.3
```

---

## 13. Open questions

Surfaced during this design pass; resolutions captured during the 2026-05-13 review.

### 13.1 Resolved

| ID | Question | Resolution |
|---|---|---|
| **Q1** | OneDrive sync corruption risk on Kuzu binary files | **Move location to `~/Droidoes/GraphDB-KDB/`** (sibling to Obsidian-KDB; not OneDrive-synced). Cross-project access is by design — see D35. Backup is recovery-via-D39: `graphdb-kdb rebuild` regenerates from OneDrive-backed `state/runs/*.json`. Belt-and-suspenders via `graphdb-kdb snapshot` (#63.9). |
| **Q2** | `knowledge_graph/` legacy directory naming collision (preexisting D3 viz, unrelated) | **README note** in `graphdb_kdb/` clarifying the distinction. No rename of the legacy file. |
| **Q3** | **Run-journal replay contract** — does the v2 run journal carry both (a) eligibility fields (`success`, `dry_run`) and (b) replay payload (`compile_result` + `last_scan`)? | **Resolved by #63.0 (2026-05-13).** Outcome **(c.ii) + (d)** per the four-outcome matrix.<br/><br/>**(a) Eligibility fields ARE present.** Inspection of `kdb_compiler/run_journal.py` (schema v2.0) confirms top-level fields `success: bool`, `dry_run: bool`, `journal_written: bool`, `manifest_written: bool`, `compile_success: bool \| None` — all reliably populated by `RunJournalBuilder.finalize()` (lines 207–302).<br/><br/>**(b) Payload is NOT embedded inline.** The journal's `artifacts` dict only stores PATHS to baton files (`compile_result_path` → `state/compile_result.json`, `last_scan_path` → `state/last_scan.json`) — both are OVERWRITTEN each run. The journal's `summary` block carries aggregate counts only (sources_attempted, pages_created, tokens), NOT the structural compile_result payload (compiled_sources with pages, outgoing_links, etc.). Verified via `python3 -c "import json; j=json.load(open(...))"` on a real journal: top-level keys do not include `compile_result`; summary keys are `counts, deltas, errors, inputs, log_entries, tokens, warnings`.<br/><br/>**Going forward (outcome c.ii):** sub-task #63.7 (Stage 9 pipeline wiring) adds per-run sidecar archive at `state/runs/<run_id>/{compile_result.json,last_scan.json}` so post-#63 runs retain their payloads. Eligibility filter applies normally.<br/><br/>**Historical runs (outcome d):** 10 pre-#63 historical run journals exist in `state/runs/` (2026-04-19 through 2026-04-21). Only the LATEST run's compile_result is recoverable from the current `state/compile_result.json` baton; the other 9 runs' compile_results are gone (overwritten). D39's full-history independence claim is therefore **prospective from #63 forward**; the LATEST pre-#63 run is one-off backfilled from current baton state during #63.6 rebuilder bring-up. Acceptable because (i) current corpus is small (~4 sources, 62 pages); (ii) re-running `kdb-compile` on the live vault re-derives baton state cheaply if needed; (iii) post-#63 runs preserve full payload and the D39 proof applies prospectively. |
| **Q4** | Transaction scope: per-run vs per-source | **Per-run atomic.** Reads are cheap; brief write-blocking is fine. Caller retries the entire run on failure. |
| **Q5** | CLI command name | **`graphdb-kdb`** — matches the user-facing brand and the ontology-layer scope. `kdb-graph` reserved for a future Obsidian-graph-view utility (out of #63 scope). See memory note `project_graphdb_kdb_vs_kdb_graph_distinction`. |
| **Q6** | Schema evolution scaffolding | **Scaffold in #63.1**: `SCHEMA_VERSION` constant + empty migration registry in `schema.py`. `_ensure_schema` runs missing migrations on open. Trivial at v1; expensive to retrofit at v3. |

### 13.2 Owned by sub-task #63.0

*(empty — Q3 resolved 2026-05-13; see §13.1 Q3 for the recorded outcome.)*

---

## 14. Known limitations (v1)

| # | Limitation | Severity | Notes |
|---|---|---|---|
| L1 | Kuzu is single-writer at the OS level. Concurrent `kdb-compile` invocations would fail Stage 9 on the second invocation (no retry/backoff per `feedback_no_imaginary_risk`). | Trivial | Not a real-world scenario for single-user setup. Manual rerun is the recovery; failure is logged in the journal with a clear error. |
| L2 | PageRank/community detection are NetworkX-based, computed in Python. At 10⁵+ nodes this becomes noticeable (seconds per call). | Low for v1 | Current scale is 62 pages. Threshold for native implementation is well beyond what we'll see soon. |
| L3 | `graphdb-kdb rebuild` rebuilds in chronological order, but doesn't replay graph_sync errors from journal entries — it always succeeds (because by definition the compile_results being replayed are well-formed). This is fine but means rebuild can't reproduce a "what would graph_sync have done if it had succeeded mid-history" simulation. | Trivial | Audit value, not operational. |
| L4 | The verifier compares Kuzu to `manifest.json`, but `manifest.json` has fields (`stats`, `runs`, `settings`) that aren't in the graph. Those fields are intentionally not mirrored. The verifier reports on overlap (sources + pages + edges) only. | None | By design — manifest carries system state that isn't graph state. |
| L5 | `Source.canonical_path` is stored but currently equals `source_id` (v1 invariant from manifest schema). Reserved for future v2 where moved files might track a separate canonical_path. | None | Forward-compat placeholder. |
| L6 | Kuzu schema is locked at first connection. Changing schema mid-corpus requires a migration. We have `SCHEMA_VERSION` but no automatic migration framework in v1. | Low | Q6 resolved — scaffolds the path but doesn't pre-build migrations we don't need yet. |
| L7 | Stage 9 currently gated on Stage 8 success (sequential pipeline order). Stage 9 reads `compile_result`/`last_scan`/`run_id` from memory — no data dependency on Stage 8's output — but a fatal Stage 8 failure prevents Stage 9 from running. | Low | True execution-level independence (both non-fatal, both run unconditionally given valid inputs) is deferred to v2. Acceptable because manifest writes rarely fail and `graphdb-kdb rebuild` is cheap recovery. |
| L8 *(per D-S2)* | `graphdb-kdb rebuild` always drops the whole DB regardless of `--producer` flag. In a multi-producer co-tenant Kuzu directory, this would wipe other producers' data. | None at v1 (single-producer); **load-bearing when producer #2 lands** | CLI prints a warning before whole-DB drop. Producer-scoped rebuild (delete-by-`source_type`, then replay only that producer's runs) is deferred until producer #2 ships AND the team agrees the right scoped semantics. Until then, document: "do not co-tenant multiple producers in the same Kuzu directory until L8 is resolved." |

---

## 14.1 Tracking items (post-#63 work)

Decisions made during #63 design that imply downstream work beyond the #63.1–#63.9 scope:

| ID | Item | Triggered by | When to address |
|---|---|---|---|
| **TR-1** | ~~Blueprint sweep after D-A1 rename pass executes.~~ **COMPLETED 2026-05-14 as part of #63.5b commit.** §4 DDL, §5 ingestion Cypher, §6 API surface, §7 Stage 9 skeleton, §10 test descriptions all updated to Entity/ingest_* naming. Historical "Page" mentions retained in D37 and D-A1 rationale rows (documenting the rename itself). | D-A1 | n/a |
| **TR-2** | Post-M3 (manifest succession arc, when manifest no longer carries `pages`/`orphans`/`stats`), `graphdb-kdb verify_against_manifest` becomes useless for the ontology dimension. Replacement audit path: **replay-to-temp-DB + structural equality compare**. New CLI subcommand or `--mode replay` flag on `graphdb-kdb verify`. | M3 of manifest succession arc | When M2/M3 work begins; details specified in `docs/reference/manifest-succession-arc.md` §6. |
| **TR-3** | Producer-scoped rebuild semantics (per L8) — when producer #2 actually arrives, design the scoped-delete + scoped-replay rules. Likely: `MATCH (s:Source {source_type:$producer}) DETACH DELETE s; MATCH (e:Entity) WHERE NOT EXISTS{(:Source)-[:SUPPORTS]->(e)} DELETE e; then replay only that producer's runs`. | Producer #2 | Producer #2 design phase. |

---

## 15. Verification criteria for closure

Task #63 is complete when:

- [ ] **Sub-task #63.0 (replay-contract verification) outcome recorded in D39 rationale.**
- [ ] All sub-tasks #63.1–#63.9 closed with commits.
- [ ] `pip install -e .` succeeds; `python -c "import graphdb_kdb"` works.
- [ ] `graphdb-kdb init` creates Kuzu directory + schema; idempotent on second run.
- [ ] All ~61 tests across `graphdb_kdb/tests/` + `tests/integration/` green.
- [ ] `graphdb-kdb rebuild --vault-root ~/Obsidian` populates Kuzu from the **eligible** historical runs in `state/runs/` (filter: `success=true AND dry_run=false AND payload_present`); produces 62-page graph matching current manifest.
- [ ] `graphdb-kdb verify --vault-root ~/Obsidian` reports perfect agreement after rebuild.
- [ ] **Independence ablation tests pass:**
  - [ ] Delete `manifest.json`. `graphdb-kdb neighbors <slug>`, `graphdb-kdb pagerank`, `graphdb-kdb stats` all still work.
  - [ ] Delete `GraphDB-KDB/` directory. Run `kdb-compile`. Manifest writes correctly. `graphdb-kdb rebuild` reconstructs Kuzu from the new state/runs entry.
- [ ] **Live compile end-to-end:** one fresh `kdb-compile` on the live vault produces Stage 9 success in the journal; subsequent `graphdb-kdb verify` reports zero divergence.
- [ ] **No regression in existing pipeline:** all pre-#63 tests (`kdb_compiler/tests/`, `kdb_benchmark/tests/`) still green.
- [ ] **#63.9 snapshot/export works:** `graphdb-kdb snapshot` produces `pages.jsonl` + `edges.jsonl` + `sources.jsonl` under `~/Obsidian/KDB/state/graph-snapshots/<ts>/`; round-trip-ingesting the snapshot reproduces the original graph state.
- [ ] CODEBASE_OVERVIEW.md gains §8 "GraphDB-KDB Layer" with D32–D40 ledger entries.
- [ ] `docs/TASKS.md` #63 entry moved to Closed; #26 and #27 closed with note "superseded by #63".
- [ ] `docs/reference/New-GraphDB-Paradigm.md` gets a closing entry noting the blueprint landed and was executed.

---

## 16. What "Proceed" looks like

Upon explicit user "Proceed" on this blueprint, the workflow is:

1. **Lock the blueprint** by committing this file to `docs/`.
2. **Open Task #63** in `docs/TASKS.md` (status `in-progress`, link to this blueprint).
3. **Run sub-task #63.0 (replay-contract verification) FIRST** — pre-implementation blocker:
   - Inspect `kdb_compiler/run_journal.py` schema for two requirements: (i) eligibility fields (`success`, `dry_run`) present per run; (ii) payload (`compile_result` + `last_scan`) embedded inline or available as sidecar.
   - Apply the four-outcome decision matrix from §11 / §13.2 (both present / eligibility missing / payload missing / historical unrecoverable).
   - Record the chosen outcome in D39's rationale before any other sub-task lands.
4. **Start sub-task #63.1** (schema + skeleton) via TDD per `superpowers:test-driven-development`:
   - Add `kuzu`, `networkx`, `python-louvain` to `pyproject.toml`.
   - Write `test_schema.py` first (failing); implement minimal `schema.py` + `graphdb.py` + `types.py` + `default_graph_path()` helper + `SCHEMA_VERSION` + empty migration registry (Q6) to make it pass.
   - Add `graphdb-kdb init` skeleton to `cli.py`.
   - Verify with `pip install -e .` + `graphdb-kdb init` smoke test.

Until "Proceed," no code changes land. This doc + the conversation record stand as the design surface.
