# Codex Review Request — GraphDB-KDB Layer (Task #63)

**Purpose:** External architectural review of an uncommitted design proposal before code lands.
**Date:** 2026-05-13.
**Reviewer:** Codex (or any senior-engineer-grade LLM with a 128K+ context window).

Paste the entire content of this file as a single user message into a fresh chat. The first block establishes role and review framing; the three appendices are the source documents.

---

## 1. Your role

You are a **Senior Staff Engineer & Architect** acting as an external peer reviewer. You have not seen this codebase before. Your job is to produce a rigorous, prioritized review of an architectural design proposal that is about to commit a single-developer team (one human, one AI assistant) to ~1500–3000 LOC of new subsystem work spread across ~51 tests and 9 sub-tasks.

You are reviewing **design intent**, not code. No code exists yet. Your output will be read by both the human developer and the AI assistant; it should help them decide what to change before implementation begins.

## 2. Project context (read this first)

- **What it is:** "KDB" / "Obsidian-KDB" is a Python toolchain that compiles raw text (currently Obsidian markdown sources from a single subdirectory `KDB/raw/`) into wiki pages + a knowledge graph. Single user, single machine, ~3 months old, ~62 compiled wiki pages from 4 source files today. Active development.
- **The proposal under review:** A new subsystem called **GraphDB-KDB** built on the Kuzu embedded graph database. It is positioned as a *multi-source* knowledge-graph ontology system; today only the Obsidian-KDB compile pipeline feeds it, but the architecture is meant to admit future source-types (arxiv papers, YouTube transcripts, other corpora) without rework.
- **Existing pipeline (relevant background):** `kdb-compile` runs an 8-stage pipeline that produces a `compile_result` JSON object → writes wiki markdown files → writes `manifest.json` (a kitchen-sink JSON ledger holding file metadata, page metadata, edges, and system state). Run journals are persisted to `state/runs/<run_id>.json`. The proposal adds **Stage 9 (`graph_sync`)** that ingests the same `compile_result` into a Kuzu graph, in parallel with the existing manifest write — neither store depends on the other.
- **Why now:** Investigation of two prior tasks (#26 EXISTING CONTEXT design review, #27 manifest scalability) surfaced that the project has been treating the graph as an accidental byproduct of compilation. Reframe: the **graph is the architectural primitive**; wiki pages and manifest.json are renderings of it. #26 and #27 are superseded by this larger refoundation (Task #63).

## 3. Constraint notes — load-bearing prior decisions (don't re-litigate)

These are durable team norms captured from prior sessions. Treat them as given; don't propose alternatives unless you spot an actual contradiction with the proposal.

- **No complexity for imaginary risk.** Single-user, infrequent workload. Drop locking/retry ceremony aimed at multi-tenant concerns.
- **Measurability over defensive complexity.** Invest in latency/tokens/metadata, not elaborate retry/streaming machinery.
- **Local time everywhere for persisted datetimes.** Use system-local ISO with offset, not UTC/Z.
- **Graph over vector.** Don't propose VectorDB/embeddings as solutions to graph-query problems in this project. The architectural bet is "explicit edges beat implicit similarity."
- **Apples-to-apples within session.** When attributing benchmark deltas, fire both states (with/without change) within the current session, not cross-day n=1.
- **CLI scope distinction (locked):** `graphdb-kdb` is the CLI for the multi-source ontology layer. `kdb-graph` is reserved for a *future* Obsidian-graph-view utility (out of #63 scope). Don't conflate these.
- **Storage locked:** Kuzu 0.11.3 (embedded graph DB, Cypher dialect, multi-language bindings). Don't argue for Neo4j/SQLite/DuckDB/NetworkX-as-DB.
- **Analytics hybrid locked:** Cypher fetches topology; NetworkX/python-louvain computes PageRank + Louvain + structural-holes.
- **Physical location locked:** `~/Droidoes/GraphDB-KDB/` (sibling to the Obsidian-KDB project, not OneDrive-synced). Recovery is via `graphdb-kdb rebuild` replaying `state/runs/*.json` (which IS OneDrive-backed).

## 4. Review priorities (in order)

1. **Architectural soundness.** Do the locked decisions D32–D40 hold together? Does the diagram in §3 match the prose in §1–2? Any internal contradiction (e.g., a "non-fatal" claim that the code path doesn't actually realize)?
2. **Independence claims (D34 + D39).** The proposal asserts "delete either store; the other still works" and "rebuild reconstructs graph from compile-history without reading manifest." Is this actually achievable given the data flow described? What would break the property in practice?
3. **Failure-mode honesty (§7.2 + L1–L7).** When things go wrong, are the recovery paths real or aspirational? Is the Stage 8 → Stage 9 temporal coupling (L7) a real issue or a non-problem?
4. **Forward compatibility — multi-source claim.** The proposal frames GraphDB-KDB as multi-source-ready (D32, `Source.source_type` field added in schema). Is the schema actually source-agnostic, or does it carry Obsidian-specific baggage (e.g., `Page.page_type ∈ {summary, concept, article}` — would arxiv papers map cleanly?)? Where would a future arxiv-compile producer hit friction?
5. **Test surface adequacy (§10).** Is the ~51-test target right-sized? Blind spots? Any test category that's over-specified for v1?
6. **Sequencing & sizing (§11).** The sub-task chain is #63.1 → #63.9. Are dependencies right? Any sub-task that should be split or merged? Is "schema + skeleton" really the right first step or should the run-journal verification (Q3) come earlier?
7. **Schema details (§4).** Specific concerns: LINKS_TO uni-directional storage with no materialized inverse — is the Cypher pattern actually performant at scale? `Source.status='moved'` with separate row at destination — does this leak the manifest's move-tombstone semantics into the graph correctly? Are timestamps in TIMESTAMP type or strings (proposal is ambiguous)?

## 5. What NOT to review (out of scope)

- Whether Kuzu is the right DB choice — D33 is locked.
- Whether NetworkX is the right analytics layer — D40 is locked.
- Whether `kdb-graph` (the future Obsidian-view utility) should be in scope — explicitly out by design.
- Existing pipeline architecture (Stages 1–8) unless the proposal mis-describes it.
- Style/formatting of the docs themselves (this is a design review, not a doc review).

## 6. Output format

Produce a single markdown response with these sections, in order. Use the headers verbatim. Cite section numbers / decision IDs / table rows when making claims about the docs.

```
## Top-line verdict
GREEN | YELLOW | RED — one sentence.

## Critical findings (must-fix before code lands)
For each finding:
- **Severity:** CRITICAL
- **Location:** §X / D## / table row
- **Evidence:** what you see in the doc
- **Claim:** what's wrong / what breaks
- **Recommendation:** specific, actionable

## Material concerns (worth addressing during implementation)
Same structure as above. Severity: MATERIAL.

## Cosmetic notes
Brief bulleted list. No more than 10. Only if genuinely useful.

## What looks right
3–6 bullets acknowledging well-designed parts. Keep signal-to-noise high.

## Questions for the team
Genuine ambiguities only. If none, skip the section.
```

**Do not pad.** **Do not summarize what you read** unless required to substantiate a claim. **Cite specifically** — "§7.1 line N" or "D38" or "table row L7" — so the team can navigate quickly.

If you find a contradiction with the constraint notes (§3), surface it as a CRITICAL finding — don't silently re-litigate the locked decision.

---

# Appendix A — Blueprint (`docs/task-graphdb-kdb-blueprint.md`)

The primary document. 16 sections, ~535 lines. Locks decisions D32–D40, defines schema, ingestion, query API, CLI, pipeline integration, validation/rebuild, file structure, tests, sub-tasks, open questions, limitations, verification criteria.

```markdown
# Task #63 — GraphDB-KDB Layer (Blueprint)

**Status:** Design — reviewed 2026-05-13; awaiting explicit Proceed on implementation (see §16).
**Date:** 2026-05-11 (drafted), 2026-05-13 (reviewed).
**Reference:** `docs/TASKS.md` → Task #63 (`open`). Supersedes the originally-scoped #26 (EXISTING CONTEXT design review) and #27 (manifest scalability) — both fold into this larger refoundation.

---

## 1. Why this exists

The investigation of #26 + #27 surfaced a deeper architectural truth: the current KDB is shaped as a *raw text → wiki page compiler*, with the graph emerging as an accidental byproduct stored half-and-half in `manifest.json` alongside file metadata. The user's reframe is that KDB is — and should be architected as — a *raw text → knowledge graph compiler*. Wiki pages are one rendering of the graph (the Obsidian-readable view); the graph itself is the durable, queryable system that downstream tooling (search, knowledge-hole detection, adaptive learning paths, EXISTING CONTEXT for next-compile) is meant to consume.

**Scope at the right layer.** **GraphDB-KDB** is a *multi-source* knowledge-graph ontology system. The Obsidian-KDB compile pipeline (`kdb-compile`) is the first — and currently only — contributing producer; the architecture admits future source-types (arxiv papers, YouTube transcripts, other corpora) without re-architecting. The narrower name `kdb-graph` is reserved for future Obsidian-specific graph-view utilities (consumers of GraphDB-KDB), not for the ontology layer itself.

This task builds the GraphDB as a first-class data subsystem with three load-bearing properties:

1. **Independent of Obsidian KDB.** Other applications (any language with Kuzu bindings) can open and query the graph without going through any KDB-specific code path.
2. **Built parallel to `manifest.json`, not on top of it.** Both consume `compile_result` independently. Either store can be deleted and regenerated from `compile_result` history; neither depends on the other.
3. **Full-scaled v1, not scaffold-MVP.** Complete schema, full ingestion, full query API, validation, rebuild — all on day one, populated from the canonical corpus of compiled sources.

---

## 2. Locked decisions

| ID  | Decision | Rationale |
|---|---|---|
| **D32** | GraphDB-KDB is a *multi-source* raw-text → knowledge-graph compiler. The graph is the architectural primitive; `manifest.json`, wiki markdown files, and any future visualization are *renderings* of the graph, not the system itself. Obsidian KDB/raw (via `kdb-compile`) is the first contributing source-type; others may follow without re-architecting. | The differentiating bet of the project is "explicit edges beat implicit similarity." Vector RAG flattens ontology into cosine distance; the graph preserves what we paid to build. Scoping the ontology system independently of any single source keeps the architecture extensible. |
| **D33** | Storage = Kuzu (embedded graph database, Cypher dialect, multi-language bindings). | Purpose-built for the embedded-graph use case. SQLite-with-graph-schema would force consumers to reimplement traversal; NetworkX+JSONL is Python-only. Kuzu is the right primitive: file-based (no daemon), portable (any language with bindings opens the same directory), Cypher (industry-standard), MIT-licensed, production-grade. Latest stable: 0.11.3. |
| **D34** | Independence-by-shared-upstream: `manifest_update.py` and `graphdb_kdb.ingestor` each consume `compile_result + last_scan + run_id` independently. Neither reads or writes the other's store. | Real independence (per the ablation test): delete `manifest.json` → GraphDB still works; delete `GraphDB-KDB/` → manifest still works. Both regenerable from `state/runs/<run_id>.json` history (which carries the compile_results). |
| **D35** | GraphDB physical location: `~/Droidoes/GraphDB-KDB/` — sibling to the `Obsidian-KDB` project under the active projects root. Cross-project read/write access is the design intent; default path overridable via `KDB_GRAPH_PATH` env var. | Physical separation mirrors the logical separation — GraphDB-KDB is a peer subsystem, not a child of Obsidian-KDB. Avoids OneDrive sync corruption on Kuzu binary files entirely (Droidoes is not OneDrive-synced). Backup story: derived state is *recoverable*, not backed up directly — `graphdb-kdb rebuild` regenerates from `~/Obsidian/KDB/state/runs/*.json` (which IS OneDrive-backed). Belt-and-suspenders via `graphdb-kdb snapshot` (#63.9) exports JSONL to the vault. |
| **D36** | Naming triad: Python module `graphdb_kdb`, Kuzu directory `GraphDB-KDB/`, CLI command `graphdb-kdb`. The name `kdb-graph` is **reserved** for a future Obsidian-graph-view utility (downstream consumer of GraphDB-KDB; out of #63 scope). | CLI name matches the brand and the ontology-layer scope, not the narrower Obsidian-KDB project family. `graphdb-kdb` operates on the cross-source ontology; `kdb-graph` (future) would produce Obsidian-specific outputs from it. Python module uses underscores because identifiers can't contain hyphens. |
| **D37** | Schema includes `Page` and `Source` as node types; `LINKS_TO` (Page→Page) and `SUPPORTS` (Source→Page) as relationship types. Provenance is first-class graph data, not a sidecar. | Source-attribution queries ("show me everything compiled from Karpathy's attention paper", "which sources support concept X?") become natural graph traversals. Splitting sources into a separate store would mean re-introducing the manifest-style "two files that must agree." |
| **D38** | Pipeline integration: new **Stage 9 (`graph_sync`)** in `kdb_compile.py`, runs AFTER Stage 8 (manifest write) succeeds. Failure is **non-fatal**: graph_sync errors emit a warning + journal entry, but the overall compile run still returns success. | Honors D34 independence: a failed graph write must not roll back a successful manifest write. Recovery is via `graphdb-kdb rebuild`. |
| **D39** | Rebuild path: `graphdb-kdb rebuild` drops all Kuzu tables and replays every `state/runs/<run_id>.json` (which carries its `compile_result` snapshot) in chronological order. This **proves** independence — Kuzu can be regenerated without ever reading `manifest.json`. | If GraphDB drifts from compile-history truth, regenerate from compile-history truth. If `manifest.json` and Kuzu disagree, the answer is "neither is authoritative — both are derived; pick the one with the better track record this incident." |
| **D40** | Advanced analytics (PageRank, community detection, betweenness centrality) use a **hybrid** strategy: Kuzu Cypher fetches topology (edge lists, node attributes); NetworkX/python-louvain computes the algorithm; results materialized back into Kuzu as node properties when desired. | Kuzu doesn't ship native PageRank or Louvain. Implementing these in Cypher (iterative random walks) is awkward; calling out to mature Python libs is cleaner. At our scale (10⁴ nodes ceiling), the hybrid cost is sub-second per algorithm. |

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
CREATE NODE TABLE Page (
    slug          STRING PRIMARY KEY,
    title         STRING,
    page_type     STRING,        -- summary | concept | article
    status        STRING,        -- active | stale | archived | orphan_candidate
    confidence    STRING,        -- low | medium | high
    created_at    TIMESTAMP,
    updated_at    TIMESTAMP,
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
    first_seen_at      TIMESTAMP,
    last_seen_at       TIMESTAMP,
    last_compiled_at   TIMESTAMP,             -- null-equivalent: epoch 0
    compile_state      STRING,                -- compiled | recompiled | moved_source | error | metadata_only
    compile_count      INT64,
    last_run_id        STRING,
    moved_to           STRING                 -- only meaningful when status=moved
);

-- Relationship tables
CREATE REL TABLE LINKS_TO (
    FROM Page TO Page,
    run_id      STRING,        -- run that emitted this edge
    created_at  TIMESTAMP
);

CREATE REL TABLE SUPPORTS (
    FROM Source TO Page,
    role          STRING,      -- primary | supporting | historical
    hash_at_time  STRING,      -- source hash when this support was emitted
    run_id        STRING,
    created_at    TIMESTAMP
);
```

**Design notes:**

- `LINKS_TO` is **stored uni-directionally** (Page→Page following `outgoing_links`). Backward traversal ("who links to me?") is a Cypher pattern `MATCH (s)-[:LINKS_TO]->(t {slug: $slug})` — no materialized inverse index needed.
- `Page.created_at` / `Page.first_run_id` are set on first INSERT and **never overwritten** on subsequent updates. `updated_at` / `last_run_id` bump every run that touches the page.
- `Source.status='moved'` keeps the original `source_id` as PK; `moved_to` points at the new id; a separate `Source` row exists for the destination. (Kuzu doesn't permit changing a primary key in place.)
- `Source.source_type` is the multi-source discriminator. v1 emits only `"obsidian-kdb-raw"`. Future source-types (`"arxiv"`, `"youtube-transcript"`, etc.) plug in without schema change; query patterns like `MATCH (s:Source) WHERE s.source_type='arxiv' RETURN ...` work uniformly across source kinds.
- `Page.body` is intentionally absent — bodies live in the markdown files (D8 boundary). The GraphDB stores semantic graph state, not file content.

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
                _upsert_page(conn, page, run_id, now)
                _replace_outgoing_links(conn, page, run_id, now)
            _upsert_supports_edges(conn, cs, run_id, now)
            _update_source_compile_state(conn, cs, run_id, now)

        # --- Phase 4: orphan-candidate detection ---
        # A Page has zero remaining SUPPORTS edges → mark orphan_candidate
        orphans = _detect_and_mark_orphans(conn, run_id, now)

    return SyncResult(
        pages_upserted=...,
        edges_upserted=...,
        sources_upserted=...,
        orphans_detected=orphans,
        run_id=run_id,
    )
```

**Per-step Cypher (representative — full text in `graphdb_kdb/ingestor.py`):**

- **Upsert page**:
  ```cypher
  MERGE (p:Page {slug: $slug})
  ON CREATE SET p.created_at=$ts, p.first_run_id=$run_id
  SET p.title=$title, p.page_type=$type, p.status=$status,
      p.confidence=$conf, p.updated_at=$ts, p.last_run_id=$run_id
  ```

- **Replace outgoing edges (idempotent per-page)**:
  ```cypher
  MATCH (a:Page {slug: $slug})-[r:LINKS_TO]->()
  DELETE r;

  -- Then for each target_slug in outgoing_links:
  MATCH (a:Page {slug: $slug})
  MATCH (b:Page {slug: $target})
  CREATE (a)-[:LINKS_TO {run_id: $run_id, created_at: $ts}]->(b)
  ```
  (If `target_slug` doesn't yet exist as a Page node, the `CREATE` is skipped — a dangling outgoing_link is a validator-catch upstream, not the ingestor's job.)

- **Upsert source**:
  ```cypher
  MERGE (s:Source {source_id: $sid})
  ON CREATE SET s.first_seen_at=$ts
  SET s.hash=$hash, s.last_seen_at=$ts, s.last_compiled_at=$ts,
      s.compile_state=$state, s.last_run_id=$run_id, s.status='active'
  ```

- **Upsert SUPPORTS** (one per page in this source):
  ```cypher
  MATCH (s:Source {source_id: $sid})
  MATCH (p:Page {slug: $slug})
  MERGE (s)-[r:SUPPORTS]->(p)
  ON CREATE SET r.created_at=$ts
  SET r.role=$role, r.hash_at_time=$hash, r.run_id=$run_id
  ```

- **Orphan detection**:
  ```cypher
  MATCH (p:Page)
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
| `get_page(slug)` | `Page \| None` | Lookup one node. |
| `get_source(source_id)` | `Source \| None` | Lookup one source. |
| `neighbors(slug, *, direction='out', depth=1)` | `list[Page]` | BFS expansion; `direction ∈ {out, in, both}`. |
| `incoming_links(slug)` | `list[Page]` | Sugar for `neighbors(slug, direction='in', depth=1)`. |
| `outgoing_links(slug)` | `list[Page]` | Sugar for `neighbors(slug, direction='out', depth=1)`. |
| `shortest_path(from_slug, to_slug, *, max_hops=10)` | `list[str] \| None` | Path of slugs, or `None` if unreachable. |
| `pages_for_source(source_id)` | `list[Page]` | All pages a source supports. |
| `sources_for_page(slug)` | `list[Source]` | All sources supporting a page. |
| `subgraph_by_source(source_id)` | `dict {nodes, edges}` | Subgraph induced by one source's supported pages. |
| `orphan_pages()` | `list[Page]` | Pages with `status='orphan_candidate'`. |
| `pagerank(*, top_n=None)` | `list[(slug, score)]` | NetworkX-backed (hybrid per D40). |
| `communities(*, algorithm='louvain')` | `dict[slug, community_id]` | NetworkX/python-louvain backed. |
| `structural_holes()` | `list[(comm_a, comm_b, n_bridges)]` | Pairs of communities with few inter-edges; surfaces "knowledge-hole" candidates. |
| `cypher(query, params=None)` | `list[dict]` | Ad-hoc Cypher escape hatch. |
| `stats()` | `dict` | Node/edge counts by type. |
| `verify_against_manifest(manifest_path)` | `VerifyResult` | Diff Kuzu vs manifest.json; report divergences. |
| `rebuild_from_runs(runs_dir)` | `RebuildResult` | Drop and replay all compile_results in chronological order. |

### 6.2 CLI surface (`graphdb-kdb`)

| Subcommand | What it does |
|---|---|
| `graphdb-kdb init` | Creates the Kuzu directory + schema. Idempotent. |
| `graphdb-kdb sync --vault-root <path>` | Manually trigger ingest from the current `state/compile_result.json` + `state/last_scan.json`. Mirrors what Stage 9 does automatically. |
| `graphdb-kdb verify --vault-root <path>` | Compare GraphDB to `manifest.json`. Exit 0 if perfect agreement; nonzero with diff report otherwise. |
| `graphdb-kdb rebuild --vault-root <path>` | Drop Kuzu tables; replay all `state/runs/*.json` in chronological order. Independence proof — does not read `manifest.json`. |
| `graphdb-kdb stats` | Print node/edge counts. |
| `graphdb-kdb neighbors <slug> [--depth N] [--direction out\|in\|both] [--json]` | List neighbors. |
| `graphdb-kdb incoming <slug>` | Sugar; equivalent to `neighbors <slug> --direction in --depth 1`. |
| `graphdb-kdb path <from_slug> <to_slug>` | Print shortest-path chain. |
| `graphdb-kdb pagerank [--top N] [--json]` | Print PageRank-ranked pages. |
| `graphdb-kdb communities [--algorithm louvain\|leiden] [--json]` | Print community assignments. |
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
        pages_upserted=sync_result.pages_upserted,
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

### 7.2 Failure modes

| Failure | Effect on run | Recovery |
|---|---|---|
| `kuzu` not installed | Stage 9 fails non-fatally; journal flags it; compile run returns success | `pip install kuzu>=0.11` |
| Kuzu file lock contention | Stage 9 retries 3× with 100ms backoff (built into `GraphDB.__init__`); if still locked, fails non-fatally | Identify other holder; rerun `graphdb-kdb sync` |
| Schema drift (existing DB has older schema) | `GraphDB._ensure_schema` detects via stored version row, logs incompatibility, fails Stage 9 non-fatally | `graphdb-kdb rebuild` |
| Transaction violation (e.g., LLM-emitted slug duplicate) | Single-run ingestion fails; transaction rolls back; Kuzu state unchanged | Reduces to "next run will retry"; or `graphdb-kdb rebuild` |
| OneDrive sync corruption of Kuzu file mid-write | `GraphDB.__init__` may fail to open (corrupted catalog); reported clearly | `graphdb-kdb rebuild`; long-term fix: OneDrive ignore rule (Open Q1) |

---

## 8. Validation + rebuild paths

### 8.1 `graphdb-kdb verify`

Walks `manifest.json` and confirms every (page, edge, source) is present in Kuzu with matching attributes. Three classes of divergence:

- **Missing in Kuzu**: present in manifest, absent in graph. Most common cause: graph_sync failed on a prior run.
- **Missing in manifest**: present in graph, absent in manifest. Most common cause: manifest write succeeded but a subsequent partial restore lost it.
- **Attribute mismatch**: both present but differ on a tracked field (title, page_type, last_run_id, ...).

Exit code: `0` if perfect agreement, `1` otherwise. Stdout: aligned diff report. `--json` flag for machine consumption.

### 8.2 `graphdb-kdb rebuild`

**The independence proof.** Drops all Kuzu tables; iterates `state/runs/<run_id>.json` in chronological order; extracts each run's `compile_result` and `last_scan` (both should be embedded in the v2 run journal — verified during #63.1 setup per Q3; if not, the rebuild falls back to per-run `compile_result.json` snapshots from disk, OR the run journal gets a small write-side change to embed them inline); applies via `apply_compile_result`. Result: the Kuzu state at the end of replay equals what live ingestion would have produced.

This subcommand is also the migration entry point for the canonical corpus: the first time we run it, the 4 already-compiled sources from `state/runs/` get backfilled into Kuzu.

---

## 9. File structure

```
graphdb_kdb/
├── __init__.py              # exports GraphDB, SyncResult, Page, Source
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
├── types.py                 # Page, Source dataclasses; SyncResult, VerifyResult
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
| `test_ingestion.py` | ~12 | Single-page upsert; multi-page upsert; outgoing edges replace (add, remove, change); SUPPORTS upsert; source upsert; MOVED reconcile; DELETED reconcile; orphan detection; orphan revival on re-support; transaction rollback on bad input; idempotent re-apply of same run; multiple sources in one run. |
| `test_queries.py` | ~14 | get_page (hit/miss); get_source; neighbors at depths 1/2/3, directions out/in/both; incoming_links convenience; shortest_path success + unreachable; pages_for_source; sources_for_page; subgraph_by_source structure; orphan_pages; pagerank correctness on a known small graph; communities correctness on a known small graph; structural_holes; cypher escape hatch; stats. |
| `test_verifier.py` | ~6 | Perfect agreement; missing-in-kuzu detected; missing-in-manifest detected; attribute mismatch detected; verifies sources too, not just pages; exit codes + JSON output. |
| `test_rebuilder.py` | ~5 | Empty Kuzu + 0 runs → no-op; replay of 1 run; replay of N runs; replay preserves orphan transitions over time; replay output matches live-ingestion output for identical inputs. |
| `test_cli.py` | ~10 | Each subcommand: argparse routing; JSON output; non-zero exit on missing args. Mocked Kuzu in unit tests; integration tests in `tests/integration/` with real Kuzu. |
| **Total** | **~51** | |

Test discipline: TDD. Write failing test first; minimal implementation; refactor. Real Kuzu DB created at `tests/tmp/<test_id>.kuzu` and cleaned up via pytest fixtures.

---

## 11. Sequencing — sub-task breakdown

| Sub | Title | Deliverable | Dependencies |
|---|---|---|---|
| **#63.1** | Schema + skeleton | `graphdb_kdb/{schema,graphdb,types}.py` + `test_schema.py` green. `graphdb-kdb init` works. | None (foundation). |
| **#63.2** | Ingestion algorithm | `ingestor.py` + `test_ingestion.py` green on synthetic fixtures. | #63.1. |
| **#63.3** | Read query API | `queries.py` + `test_queries.py` green. CLI `neighbors`, `incoming`, `path`, `stats`, `cypher` working. | #63.1, #63.2. |
| **#63.4** | Analytics (hybrid) | PageRank + Louvain + structural_holes via NetworkX. CLI `pagerank`, `communities`, `orphans`. | #63.3. |
| **#63.5** | Verifier | `verifier.py` + CLI `graphdb-kdb verify`. | #63.2. |
| **#63.6** | Rebuilder | `rebuilder.py` + CLI `graphdb-kdb rebuild`. Backfill canonical-corpus runs as the first proof. | #63.2. |
| **#63.7** | Pipeline Stage 9 wiring | Edit `kdb_compile.py` to add Stage 9; update `run_journal.py` STAGE_NAMES; add stage-9 progress emit. New integration tests. | All preceding. |
| **#63.8** | Documentation | CODEBASE_OVERVIEW.md gains §8 "GraphDB-KDB Layer" with D32–D40 ledger entries. README mention. | All preceding. |
| **#63.9** | Snapshot/export | `graphdb-kdb snapshot` exports `pages.jsonl` + `edges.jsonl` + `sources.jsonl` to `~/Obsidian/KDB/state/graph-snapshots/<ts>/`. Belt-and-suspenders backup at the JSONL-text level. | #63.3. |

---

## 12. Dependencies + setup

```bash
pip install kuzu>=0.11 networkx>=3.0 python-louvain>=0.16
```

- **kuzu (0.11.3)**: ~30 MB wheel; Linux x86_64 prebuilt available. No native build required.
- **networkx (3.x)**: pure Python; depends on `numpy` and `scipy` for some algorithms.
- **python-louvain (0.16)**: pure Python; thin wrapper over networkx.

All three are MIT or BSD-licensed.

---

## 13. Open questions

### 13.1 Resolved during 2026-05-13 review

| ID | Question | Resolution |
|---|---|---|
| **Q1** | OneDrive sync corruption risk on Kuzu binary files | Move location to `~/Droidoes/GraphDB-KDB/` (sibling to Obsidian-KDB; not OneDrive-synced). Backup is recovery-via-D39. Belt-and-suspenders via `graphdb-kdb snapshot` (#63.9). |
| **Q2** | `knowledge_graph/` legacy directory naming collision | README note clarifying the distinction. No rename. |
| **Q4** | Transaction scope: per-run vs per-source | Per-run atomic. |
| **Q5** | CLI command name | `graphdb-kdb`. `kdb-graph` reserved for future Obsidian-view utility. |
| **Q6** | Schema evolution scaffolding | Scaffold `SCHEMA_VERSION` + migration registry in #63.1. |

### 13.2 Open — verify during implementation

| ID | Question | Verification window | Recommendation |
|---|---|---|---|
| **Q3** | Run-journal embedding of `compile_result` — does v2 run journal embed `compile_result` inline, or only deltas/log? Determines whether `graphdb-kdb rebuild` can replay history retroactively. | #63.1 setup | If `compile_result` not embedded inline: add small write-side change OR add per-run `compile_result.json` archive. Without this, D39 only works prospectively. |

---

## 14. Known limitations (v1)

| # | Limitation | Severity | Notes |
|---|---|---|---|
| L1 | Kuzu is single-writer at the OS level. Concurrent `kdb-compile` invocations would serialize at Stage 9. | Low | Not a real-world scenario for single-user setup. |
| L2 | PageRank/community detection are NetworkX-based, computed in Python. At 10⁵+ nodes this becomes noticeable. | Low for v1 | Current scale is 62 pages. |
| L3 | `graphdb-kdb rebuild` rebuilds in chronological order, doesn't replay graph_sync errors. | Trivial | Audit value, not operational. |
| L4 | The verifier compares Kuzu to `manifest.json` overlap (sources + pages + edges) only. `manifest.json` fields (`stats`, `runs`, `settings`) are not mirrored. | None | By design. |
| L5 | `Source.canonical_path` currently equals `source_id` (v1 invariant). Reserved for future v2. | None | Forward-compat placeholder. |
| L6 | Kuzu schema is locked at first connection. Changing schema mid-corpus requires migration. | Low | Q6 resolved — scaffolds migration path. |
| L7 | Stage 9 currently gated on Stage 8 success (sequential pipeline order). Stage 9 reads `compile_result`/`last_scan`/`run_id` from memory — no data dependency on Stage 8's output — but a fatal Stage 8 failure prevents Stage 9 from running. | Low | True execution-level independence deferred to v2. |

---

## 15. Verification criteria for closure

- [ ] All sub-tasks #63.1–#63.9 closed with commits.
- [ ] `pip install -e .` succeeds; `python -c "import graphdb_kdb"` works.
- [ ] `graphdb-kdb init` creates Kuzu directory + schema; idempotent on second run.
- [ ] All ~51 tests across `graphdb_kdb/tests/` green.
- [ ] `graphdb-kdb rebuild --vault-root ~/Obsidian` populates Kuzu from the 4 historical runs in `state/runs/`; produces 62-page graph matching current manifest.
- [ ] `graphdb-kdb verify --vault-root ~/Obsidian` reports perfect agreement after rebuild.
- [ ] **Independence ablation tests pass:**
  - [ ] Delete `manifest.json`. `graphdb-kdb neighbors <slug>`, `graphdb-kdb pagerank`, `graphdb-kdb stats` all still work.
  - [ ] Delete `GraphDB-KDB/` directory. Run `kdb-compile`. Manifest writes correctly. `graphdb-kdb rebuild` reconstructs Kuzu from the new state/runs entry.
- [ ] Live compile end-to-end: one fresh `kdb-compile` on the live vault produces Stage 9 success in the journal; subsequent `graphdb-kdb verify` reports zero divergence.
- [ ] No regression in existing pipeline.

---

## 16. What "Proceed" looks like

1. Lock the blueprint by committing this file to `docs/`.
2. Open Task #63 in `docs/TASKS.md` (status `in-progress`).
3. Start sub-task #63.1 (schema + skeleton) via TDD.
4. Front-load Q3 verification during #63.1 setup.
```

---

# Appendix B — Paradigm record (`docs/New-GraphDB-Paradigm.md`)

The conversation that produced the design. Verbatim Q&A; `❯` lines are the user (human developer), `●` lines are the AI assistant. The original session was 2026-05-10 evening; a 2026-05-13 appendix captures the post-blueprint review.

```markdown
❯ ❯ im not sure if im ready to settle on track 1 and track 2 yet....
    [1] it seems that the biggest architecture issue we are facing which also what kaparthy KDB is facing is "why"... kaparthy has proposed a workflow to build an obsidian graph...
    but "why", why we spend time to build obsidian graph..beside showing it off on reddit?  I think the answer to the why is that we are essentially building a GraphDB.... we can visualize it to show off, but we can also use it for searching and maybe potentially identify knowledge holes and create opportunities for adaptive learning... so as a major objective and s/w architecture, we MUST build a graphDB based on results of compiled sources... the slugs are the materials for building graphDB...  once we have built a graphDB, identifying top 50 links for the source-to-be-compile will be very easy... so again we MUST first build a graphDB, finding existing links is just one of the many applications of that graphDB... with the graphDB, the scalability issue is automatically resolved... at least for the searching piece
    [2] we still have the scalability of file meta that has yet to be resolved... but let's don't conflate that with the need for a GraphDB... right now both file meta and the hint of GraphDB are randomly put into one place that's called manifest.json
    [3] once we have our GraphDB, and we can properly query the GraphDB to get the depth=1 links and feed that into the model for compiling a source, we can then evaluate the links that the model generates using ontology... that's "how" we are going the measure M2

    that's my high level proposal of addressing #26 and #27

● You're right. This is the re-frame.

  KDB isn't a "raw text → wiki page compiler." It's a raw text → knowledge graph compiler. The wiki pages are one rendering of the graph (the human-readable, Obsidian-native rendering — useful, but a view, not the system). The graph is the durable, queryable artifact. The differentiating bet here is: the graph is a data system, not a screenshot.

  manifest.json today is an accident. It exists because the prototype needed a place to dump four different concerns (file metadata, page metadata, graph edges, system state) and JSON was the path of least resistance. There's nothing principled about housing all four together.

  Three layers worth being explicit about:
  - Layer 1 — Logical model: Nodes = pages, slug-keyed, typed (summary | concept | article). Edges = directed wikilinks. The reverse-index is materialized, not authored.
  - Layer 2 — Storage. Live options: (a) NetworkX+JSONL, (b) embedded graph DB like Kuzu, (c) server graph DB. At our scale, my initial lean was (a).
  - Layer 3 — Query API: depth-N expansion, PageRank, community detection, orphan detection, structural-hole detection, subgraph extraction.

  The bridge problem doesn't disappear: seed identification (given a new raw source S, which existing graph nodes does it touch?) is still an entity-linking problem the graph alone doesn't solve. Three options (none involve vector embeddings): LLM-as-entity-linker, community-summary matching, regex+LLM hybrid.

  Honestly: this proposal supersedes #26 and #27 as currently scoped. The actual work is bigger and probably wants new task IDs.

  Two things to lock before going further:
  1. Storage choice for Layer 2 — NetworkX+JSONL vs embedded DB?
  2. Manifest.json's fate — derived export vs split-and-retire?

---

❯ agree with all of the above...
  [1] I want the graphDB that we build to be independent of Obsidian KDB... it should be accessible by other applications, projects outside Obsidian KDB...
  [2] make before break... so Manifest.json will stay as if nothing has happened.. we'll build a GraphDB in parallel...
  [3] please continue to record this conversation until we have consensus on how to proceed

● The independence constraint changes Layer 2.

  NetworkX is a Python in-memory library, not a database. JSONL is a file format with no query semantics. If "accessible by other applications" means any project — Python or otherwise — should be able to open the GraphDB and run graph queries without reimplementing traversal, then NetworkX+JSONL fails.

  Revised: Kuzu. Embedded graph database — think SQLite, but for graphs. Single directory on disk, opened by any process with the bindings. Bindings exist for Python, Node.js, Rust, C++, Go, Java. Cypher query language. ACID transactions. MIT-licensed.

  No server needed for v1. Single user, single machine.

  What "make before break" looks like mechanically: new top-level package `kdb_graph/`. GraphDB physical location proposal: `~/Obsidian/KDB/state/graph/`. Pipeline wiring: after manifest_update writes, new step calls graph ingester. Validation: `kdb-graph verify`. Rebuild path: `kdb-graph rebuild`. context_loader.py unchanged for now.

  Five questions: storage choice locked at Kuzu? Physical location? Sync source (manifest vs compile_result)? Package naming? Initial scope?

---

❯ [1] I think im fine with kuzu if that's your preferred choice... the logical separation is most important to me
  [2] im fine with that as well
  [3] compile results directly... manifest.json should be maintained as if GraphDB doesn't exist... GraphDB should be created and maintained as if manifest.json doesnt exist
  [4] GraphDB-KDB
  [5] we can build a mvp but we need to build a full scaled GraphDB using compiled result of sources from /raw... and all the query/response capability of a fully functioning graphDB

● Consensus locked across all five.

  [1] Kuzu, with your framing as the durable insight: the logical separation is the asset.

  [2] Co-located (initially proposed at `~/Obsidian/KDB/state/graph/`; later moved to `~/Droidoes/GraphDB-KDB/` after OneDrive corruption concerns).

  [3] **This is the gem of the conversation.** Compile_result is the canonical upstream truth; manifest_update.py and the new graph builder each consume it independently with no knowledge of each other. The ablation test cuts both ways: delete manifest.json and Kuzu still works; delete Kuzu and manifest still works. Either can be regenerated from state/runs/<run_id>.json history. Real independence.

  This also resolves a subtle thing: where manifest_update.py materializes incoming_links_known by walking everyone's outgoing_links (bookkeeping overhead), Kuzu doesn't — Cypher answers "who links to me?" by graph traversal. Manifest serializes the graph; Kuzu IS the graph.

  [4] Naming: Python `graphdb_kdb` / Kuzu dir `GraphDB-KDB/` / CLI `graphdb-kdb` (post-2026-05-13 review).

  [5] Full-scaled v1: full schema, complete ingestion, full query API, CLI, validation + rebuild, full test coverage. Rough sizing: ~1500-3000 LOC, ~30-50 tests, 2-3 focused sessions.

---

❯ proceed pls

● Blueprint drafted at docs/task-graphdb-kdb-blueprint.md, locks D32–D40.

  Six open questions in Section 13: OneDrive corruption, knowledge_graph/ collision, run-journal embedding, transaction scope, CLI name, schema evolution.

  Awaiting user review + answers to Q1 and Q5 minimum.

---

## 2026-05-13 review — scope distinction (GraphDB-KDB vs kdb-graph)

Reviewed the blueprint cold. Q5's "which CLI name?" framing surfaced a deeper conceptual confusion that needed locking down before implementation. Captured verbatim because the distinction is durable and load-bearing.

### The clarification

❯ Option A works, snapshot as #63.9... but we need to clarify one thing... which is, too me, extremely important.. kdb-graph is NOT GraphDB-KDB... kdb-graph.. is to produce the obsidian connectivity for the purpose of generating obsidian graph... GraphDB-KDB is to generate ontology of sources... one of the sources, also the only one available so far is Obsidian KDB/raw.... kdb-graph is just special case of GraphDB-KDB.... to say kdb-graph snapshot... is effectively getting things backwards

● Restated to confirm understanding:

- **GraphDB-KDB** = the multi-source knowledge-graph ontology system. Currently ingests from one source-type (Obsidian KDB/raw via the `kdb-compile` pipeline); the architecture is designed for many source-types over time.
- **kdb-graph** = a downstream, Obsidian-specific utility — produces Obsidian connectivity for graph-view rendering. Reads from GraphDB-KDB, doesn't manage it. **Not in Task #63 scope.**
- The Kuzu directory + the operator CLI for the ontology layer belong to **GraphDB-KDB**, not kdb-graph.

The blueprint had these conflated under `kdb-graph` as the CLI name. That was exactly backwards — using a special-case name for the general-case tool.

### The three layers

| Tool | Layer | Scope | Status |
|---|---|---|---|
| `kdb-compile` | Producer | Obsidian-KDB compile pipeline (KDB/raw → wiki pages → Stage 9 push into GraphDB-KDB) | Exists |
| `graphdb-kdb` | Ontology operator | Init, ingest, verify, rebuild, query, analytics, snapshot — source-agnostic | **Task #63 scope** |
| `kdb-graph` | Obsidian-specific consumer | Emit Obsidian-shaped output | Future — name reserved |

### Why this distinction matters durably

Conflating these would degrade decisions over time:
1. **Schema decisions** would creep toward Obsidian-flavored only.
2. **CLI semantics** would accumulate Obsidian-specific behavior in the ontology tool.
3. **Future producers** (arxiv-compile, youtube-compile) need a target system that doesn't presume Obsidian.

### Resolutions from the same review

| ID | Resolution |
|---|---|
| **Q1** | Move location to `~/Droidoes/GraphDB-KDB/`. Backup story: derived state is recoverable via `graphdb-kdb rebuild` from OneDrive-backed `state/runs/*.json`. |
| **Q2** | README note clarifying the distinction. |
| **Q4** | Per-run atomic. |
| **Q5** | `graphdb-kdb`. `kdb-graph` reserved. |
| **Q6** | Scaffold `SCHEMA_VERSION` + migration registry in #63.1. |
| **Q3** | Still open — front-loaded to #63.1 setup. |

Sub-task `#63.9` (snapshot/export) added. `L7` (Stage 8/9 temporal coupling) added to Section 14 limitations.
```

---

# Appendix C — Session handoff (`docs/session-handoff-2026-05-10-graphdb-paradigm.md`)

Supplementary continuity record. The "next-action checklist" at the top of this doc was the implementation roadmap before the 2026-05-13 review absorbed Q1 and Q5 into resolutions.

```markdown
# Session Handoff — 2026-05-10 → 2026-05-11 (GraphDB Paradigm)

**Theme:** Architectural pivot — KDB reframed as a knowledge-graph compiler with the GraphDB as a first-class data subsystem
**Status (at handoff):** Blueprint complete; awaiting user "Proceed" gate before any code changes

## Decisions locked

- **D32**: KDB is a knowledge-graph compiler. Manifest is one rendering, not the system.
- **D33**: Storage = Kuzu 0.11.3 (embedded graph DB, Cypher, multi-language bindings).
- **D34**: Independence-by-shared-upstream — both consumers read `compile_result` directly.
- **D35**: GraphDB at `~/Droidoes/GraphDB-KDB/` (post-2026-05-13 review; original proposal was `~/Obsidian/KDB/state/graph/`).
- **D36**: Naming triad: `graphdb_kdb` module / `GraphDB-KDB` dir / `graphdb-kdb` CLI (post-2026-05-13 review).
- **D37**: Page + Source nodes; LINKS_TO + SUPPORTS rels. Provenance is first-class graph data.
- **D38**: Pipeline integration as new Stage 9 (`graph_sync`); failure is non-fatal.
- **D39**: `graphdb-kdb rebuild` replays `state/runs/*.json` — proves manifest-free regeneration.
- **D40**: PageRank/community detection hybrid (Cypher fetches topology; NetworkX/python-louvain computes).

## What didn't happen yet (gating on Proceed)

- No code written
- No Task #63 opened in TASKS.md
- No `pip install kuzu`
- No commits

## Recovery / context for next session

Three-step warm-up:
1. Re-read `docs/New-GraphDB-Paradigm.md` (full conversation)
2. Re-read Sections 2 (decisions) + 13 (open questions) of `docs/task-graphdb-kdb-blueprint.md`
3. Answer Q3 (run-journal embedding) → "Proceed" → start #63.1

## Closing principle

This session's defining moment was the user's reframe of "why" — the architectural identity of the project itself. When the conversation feels stuck on the *how*, check whether the *why* has been articulated.
```

---

End of review request. Produce your structured review per §6 above.
