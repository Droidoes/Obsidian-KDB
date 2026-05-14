# Codex Review Request v2 — GraphDB-KDB Layer (Task #63, post-feedback)

**Purpose:** Second-pass architectural review of the GraphDB-KDB blueprint *after* your prior round of feedback has been incorporated. We want you to (a) verify each of your prior findings was addressed faithfully, (b) catch anything the fixes introduced or surfaced, and (c) flag anything load-bearing the first pass missed now that the design is sharper.

**Date:** 2026-05-13 (same day as v1; second pass).
**Prior review:** Appendix B contains your full v1 review verbatim.

---

## 1. Your role (unchanged from v1)

You are a Senior Staff Engineer & Architect external peer reviewer. The proposal under review is the same project — single-developer team building an embedded graph DB subsystem for a single-user Python toolchain. No code has landed yet. Your output will be read by both the human developer and the AI assistant; it should help them decide what to change before implementation begins.

You have continuity from your prior review. This pass is **targeted re-verification**, not a fresh start. Don't re-explain context the v1 prompt already established — focus on what changed and what (if anything) the changes broke or missed.

## 2. What this review needs to deliver

Three things, in this order:

1. **Verification of your prior findings** — for each CRITICAL and MATERIAL item you raised, confirm whether the v2 blueprint addresses it faithfully. Flag any items where the fix is partial, wrong, or introduces a new concern.
2. **New issues introduced by the changes** — the fixes were non-trivial (delete-then-create SUPPORTS, MOVED edge transfer, STRING timestamps, Stage 9 ordering, #63.0 pre-task). Look for second-order bugs the edits could have created.
3. **Anything still missing** — now that the surface is cleaner, what should have been flagged in v1 but wasn't? (e.g., concurrency, observability, error propagation, edge cases in the Cypher.)

## 3. Change log — your prior findings → blueprint resolutions

| # | Severity | Your finding | Resolution | Blueprint location to verify |
|---|---|---|---|---|
| C1 | CRITICAL | Replay contract unverified (D34/D39 vs Q3) | Promoted Q3 to new pre-implementation sub-task **#63.0** (gates all others); §13.2 renamed "Owned by sub-task #63.0"; §16 step 3 = run #63.0 first | §11 #63.0 row; §13.2; §15 first checkbox; §16 step 3 |
| C2 | CRITICAL | Stale SUPPORTS on source recompile (orphan detection broken) | Replaced `_upsert_supports_edges` with `_replace_supports_for_source` (delete-then-create per source) | §5 phase 3 code; §5 "Replace SUPPORTS for a source" Cypher block |
| C3 | CRITICAL | `TIMESTAMP` vs local-ISO-with-offset rule | All 7 timestamp fields switched to `STRING`; design note added explaining the rationale + Kuzu UTC-normalization issue | §4 schema DDL (all `STRING` now); §4 design-note bullet about timestamps |
| C4 | CRITICAL | 3× retry/backoff for Kuzu locks contradicts "no imaginary risk" rule | Removed retry; fail clearly on first contention; L1 tightened | §7.2 lock-contention row; §14 L1 |
| M1 | MATERIAL | compile_result schema is Obsidian-flavored; multi-source is aspirational at ingestion layer | **Partially accepted:** D32 wording tempered to "multi-source at storage layer; ingestion API is Obsidian-flavored for v1." **Rejected:** introducing GraphRun/GraphSource normalization layer now (YAGNI; will build when source #2 lands) | §1 paragraph 2; D32 rewritten |
| M2 | MATERIAL | Stage 9 journal persistence ordering | Explicit ordering paragraph added: Stage 9 runs before `_finalize_and_write`; final run-success stays `true` even on Stage 9 `ok=false` | §7.1 "Ordering with `_finalize_and_write`" paragraph |
| M3 | MATERIAL | Source move semantics — SUPPORTS edge fate underspecified | Specified: MOVED reconciliation transfers SUPPORTS edges from old to new Source; old Source becomes historical-only with zero active SUPPORTS | §5 "MOVED reconciliation" Cypher block |
| M4 | MATERIAL | Tests miss high-risk cases | Added 7 tests across `test_ingestion.py`, `test_rebuilder.py`, new `tests/integration/test_stage9.py`. Total ~51 → ~58 | §10 test table (test_ingestion ~15, test_rebuilder ~6, new test_stage9 row ~3, Total ~58) |
| — | Cosmetic | §7.2 still mentioned OneDrive after D35 moved Kuzu off OneDrive | OneDrive corruption row deleted from §7.2 failure-modes table | §7.2 — should have 4 rows now, not 5 |
| — | Cosmetic | `communities --algorithm leiden` listed but python-louvain doesn't ship Leiden | `--algorithm` flag dropped; CLI is now `communities [--json]` with comment "(Louvain via python-louvain)" | §6.2 communities row |
| — | Cosmetic | Docs (#63.8) should come before #63.1 per North Star | **Rejected.** See §4 below for reasoning. | §11 #63.8 row unchanged |

## 4. What we pushed back on (and why)

Two items where we did not implement your recommendation. If you still feel strongly about either after re-reading the rationale, flag it as a new finding in the v2 output — but please surface the specific concern, not a restatement of the v1 position.

### 4.1 GraphRun/GraphSource normalization layer (M1 partial reject)

You recommended introducing a normalized ingestion contract now to make the multi-source claim real at the API level, not just the storage level.

We accepted the spirit by tempering D32 wording: storage layer is multi-source-ready; ingestion API is Obsidian-flavored for v1 and explicitly deferred. We did not accept the abstraction because:

- v1 has exactly one producer (`kdb-compile`). Building a normalization layer without a second consumer to validate it would be speculative.
- The schema's `Source.source_type` discriminator carries the forward-compat hook at a cost of one field.
- The team's `feedback_no_imaginary_risk` constraint explicitly drops complexity aimed at future-tenancy concerns. A normalization layer for a future second source-type that may never arrive falls under that rule.
- When source #2 actually lands, the normalization shape will be informed by what source #2 actually needs, not by what we guessed today.

### 4.2 Documentation-first ordering (cosmetic reject)

You suggested moving `CODEBASE_OVERVIEW.md` updates earlier — before or alongside #63.1 — citing the team's "North Star (Documentation)" principle.

We disagree on the read of the principle:

- "North Star = Documentation" in the team's system prompt refers to the **design-doc-first** workflow: no work begins without a blueprint locked. This blueprint (`task-graphdb-kdb-blueprint.md`) IS the North Star for this work — it's been drafted, reviewed twice, and pending the Proceed gate.
- `CODEBASE_OVERVIEW.md` §8 is the **post-implementation summary** — it captures D32–D40 in their as-built form, with anchors to the actual files/classes/CLIs that landed. Writing it before implementation would produce speculative descriptions that drift from reality.
- The blueprint already carries the design-time decisions; CODEBASE_OVERVIEW.md captures them post-hoc as project-level architectural state.

## 5. Review priorities for v2 (in order)

1. **Verification of CRITICAL and MATERIAL fixes** (per §3 table). For each, either confirm the fix is well-formed or flag a specific problem with the v2 attempt.

2. **Cypher correctness in the new Edit blocks** — the SUPPORTS replacement and MOVED reconciliation Cypher (§5) are new. Particular concerns:
   - Does the MOVED Cypher's `WITH old, p, role, hash, rid, cts` chain work under Kuzu's actual semantics? (Kuzu's Cypher dialect is mostly Neo4j-compatible but has some divergences.)
   - Is there a risk that "delete then create" inside a single transaction leaves a window where orphan detection runs against an empty SUPPORTS set?
   - The orphan detection query (`WHERE NOT EXISTS { MATCH (:Source)-[:SUPPORTS]->(p) }`) — does it correctly account for the case where Phase 3 just deleted a source's SUPPORTS but is about to recreate them in the same transaction? (We believe Cypher's MATCH inside the same transaction sees post-DELETE state, so orphan detection in Phase 4 sees the correct final state — but please verify.)

3. **STRING timestamp implications** — switching from native `TIMESTAMP` to `STRING` is the right call for the local-offset preservation, but does it lose anything we should preserve?
   - Range queries: `WHERE p.created_at > '2026-05-01T00:00:00'` works on lexicographic STRING comparison and ISO-8601 strings sort correctly *if* the offset is identical across rows. Different offsets (e.g., DST transition) would break ordering. Is this a real concern for a single-user single-machine setup?
   - Should we recommend storing both a sort-stable UTC variant + the local-offset string, or is this overengineering?

4. **#63.0 scoping** — is the three-outcome decision tree (confirm / embed-going-forward / sidecar archive / downgrade-D39 + backfill) complete? Any fourth outcome we missed?

5. **Anything new that the cleaner v2 surface exposes** — second-order issues, missing observability, error-propagation gaps, edge cases in the schema we didn't think about.

## 6. Constraint notes (brief — full text in v1 prompt)

The 9 load-bearing constraint notes from the v1 prompt all still apply. Most relevant for this pass:

- **No complexity for imaginary risk** — particularly relevant to whether to add concurrency/retry/backoff machinery beyond what's there.
- **Graph over vector** — particularly relevant to whether any of your new findings push toward embedding-style solutions.
- **Local time everywhere** — particularly relevant to the C3 timestamp fix; you can verify it landed correctly.

## 7. Output format

Same structure as v1:

```
## Top-line verdict on v2
GREEN | YELLOW | RED — one sentence on whether the blueprint is now Proceed-ready.

## Verification of prior findings
Table mapping each prior finding to a verdict:
- ✓ FIXED — fix is correct and complete
- ⚠ PARTIAL — fix addresses the symptom but misses something
- ✗ NOT FIXED — finding still stands
- ◯ REJECTED-OK — push-back rationale is sound

For ⚠ or ✗, include severity + evidence + recommendation.

## New CRITICAL findings (introduced or surfaced by v2)
Same structure as v1 CRITICAL section. Only items that are genuinely new — not restatements of v1.

## New MATERIAL concerns
Same structure as v1.

## Cosmetic notes (v2 only)
Bulleted. No more than 8.

## What looks right in v2
3–6 bullets on what improved. Keep signal high.

## Final recommendation
PROCEED | ITERATE-AGAIN | HOLD — with one paragraph on the gating concern (if any).
```

**Critical instructions:**
- For each prior finding, **explicitly check the cited blueprint location** (§3 table column 5) and verify the fix is there. Don't take our word for it.
- If you find a NEW issue, mark it clearly as "NEW IN V2" or "MISSED IN V1" — don't fold it into prior-finding verification.
- Push back on push-backs only with new evidence. If our §4 rationale is sound, mark ◯ REJECTED-OK and move on.
- Cite specifically (§X / D## / line range) so the team can navigate quickly.

---

# Appendix A — Updated Blueprint (`docs/task-graphdb-kdb-blueprint.md`)

This is the current state after all v1-feedback edits. Compare against the change log in §3 to verify each fix landed at the cited location.

```markdown
# Task #63 — GraphDB-KDB Layer (Blueprint)

**Status:** Design — reviewed 2026-05-13 (Codex external review incorporated); awaiting explicit Proceed on implementation (see §16).
**Date:** 2026-05-11 (drafted), 2026-05-13 (reviewed + Codex feedback applied).

---

## 1. Why this exists

The investigation of #26 + #27 surfaced a deeper architectural truth: the current KDB is shaped as a *raw text → wiki page compiler*, with the graph emerging as an accidental byproduct stored half-and-half in `manifest.json` alongside file metadata. The user's reframe is that KDB is — and should be architected as — a *raw text → knowledge graph compiler*. Wiki pages are one rendering of the graph (the Obsidian-readable view); the graph itself is the durable, queryable system that downstream tooling is meant to consume.

**Scope at the right layer.** **GraphDB-KDB** is a *multi-source* knowledge-graph ontology system. The Obsidian-KDB compile pipeline (`kdb-compile`) is the first — and currently only — contributing producer; the architecture admits future source-types (arxiv papers, YouTube transcripts, other corpora) without re-architecting. The narrower name `kdb-graph` is reserved for future Obsidian-specific graph-view utilities (consumers of GraphDB-KDB), not for the ontology layer itself.

Three load-bearing properties:
1. Independent of Obsidian KDB. Other applications (any language with Kuzu bindings) can open and query the graph.
2. Built parallel to `manifest.json`, not on top of it.
3. Full-scaled v1, not scaffold-MVP.

---

## 2. Locked decisions

| ID  | Decision | Rationale |
|---|---|---|
| **D32** | GraphDB-KDB is a *multi-source* raw-text → knowledge-graph compiler at the **storage layer** — the schema admits `Source.source_type` as a discriminator and is source-agnostic. The **ingestion API contract** (`apply_compile_result`) is currently Obsidian-flavored — it consumes the existing `compile_result` shape, which encodes Obsidian-KDB conventions (source_id pattern `^KDB/raw/.+`, page-types `summary\|concept\|article`). A normalized `GraphRun/GraphSource` ingestion contract is deferred until a second source-type actually arrives (YAGNI for v1). The graph is the architectural primitive; `manifest.json`, wiki markdown files, and any future visualization are *renderings* of the graph, not the system itself. | The differentiating bet of the project is "explicit edges beat implicit similarity." Storage-layer multi-source readiness is cheap to bake in now; ingestion-layer abstraction without a second producer would be speculative complexity. |
| **D33** | Storage = Kuzu (embedded graph database, Cypher dialect, multi-language bindings). | Purpose-built for the embedded-graph use case. File-based, portable, Cypher-standard, MIT-licensed. Latest stable: 0.11.3. |
| **D34** | Independence-by-shared-upstream: `manifest_update.py` and `graphdb_kdb.ingestor` each consume `compile_result + last_scan + run_id` independently. Neither reads or writes the other's store. | Real independence (per the ablation test). Both regenerable from `state/runs/<run_id>.json` history. |
| **D35** | GraphDB physical location: `~/Droidoes/GraphDB-KDB/` — sibling to the `Obsidian-KDB` project. Cross-project read/write access is the design intent; default path overridable via `KDB_GRAPH_PATH` env var. | Physical separation mirrors logical separation. Avoids OneDrive sync corruption (Droidoes is not OneDrive-synced). Backup story: derived state is *recoverable*, not backed up directly — `graphdb-kdb rebuild` regenerates from OneDrive-backed `state/runs/*.json`. Belt-and-suspenders via `graphdb-kdb snapshot` (#63.9). |
| **D36** | Naming triad: Python module `graphdb_kdb`, Kuzu directory `GraphDB-KDB/`, CLI command `graphdb-kdb`. The name `kdb-graph` is **reserved** for a future Obsidian-graph-view utility (out of #63 scope). | CLI name matches the brand and the ontology-layer scope. |
| **D37** | Schema includes `Page` and `Source` as node types; `LINKS_TO` (Page→Page) and `SUPPORTS` (Source→Page) as relationship types. Provenance is first-class graph data, not a sidecar. | Source-attribution queries become natural graph traversals. |
| **D38** | Pipeline integration: new **Stage 9 (`graph_sync`)** in `kdb_compile.py`, runs AFTER Stage 8 (manifest write) succeeds. Failure is **non-fatal**: graph_sync errors emit a warning + journal entry, but the overall compile run still returns success. | Honors D34 independence. Recovery is via `graphdb-kdb rebuild`. |
| **D39** | Rebuild path: `graphdb-kdb rebuild` drops all Kuzu tables and replays every `state/runs/<run_id>.json` (which carries its `compile_result` snapshot — pending #63.0 verification) in chronological order. | If GraphDB drifts from compile-history truth, regenerate from compile-history truth. |
| **D40** | Advanced analytics (PageRank, community detection) use a **hybrid** strategy: Kuzu Cypher fetches topology; NetworkX/python-louvain computes the algorithm. | Kuzu doesn't ship native PageRank or Louvain. |

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
       (JSON ledger)                  (Kuzu directory; sibling to
                                        Obsidian-KDB project)
              │                                │
              ▼                                ▼
       context_loader.py                 OTHER APPS:
       (today's consumer)                graphdb-kdb CLI, kuzu bindings, etc.
```

---

## 4. Schema (Kuzu DDL)

```cypher
CREATE NODE TABLE Page (
    slug          STRING PRIMARY KEY,
    title         STRING,
    page_type     STRING,        -- summary | concept | article
    status        STRING,        -- active | stale | archived | orphan_candidate
    confidence    STRING,        -- low | medium | high
    created_at    STRING,
    updated_at    STRING,
    first_run_id  STRING,
    last_run_id   STRING
);

CREATE NODE TABLE Source (
    source_id          STRING PRIMARY KEY,
    source_type        STRING,                -- obsidian-kdb-raw | (future) arxiv | youtube-transcript | ...
    canonical_path     STRING,
    status             STRING,
    file_type          STRING,
    hash               STRING,
    size_bytes         INT64,
    first_seen_at      STRING,
    last_seen_at       STRING,
    last_compiled_at   STRING,                -- empty string if never compiled
    compile_state      STRING,
    compile_count      INT64,
    last_run_id        STRING,
    moved_to           STRING
);

CREATE REL TABLE LINKS_TO (
    FROM Page TO Page,
    run_id      STRING,
    created_at  STRING
);

CREATE REL TABLE SUPPORTS (
    FROM Source TO Page,
    role          STRING,      -- primary | supporting | historical
    hash_at_time  STRING,
    run_id        STRING,
    created_at    STRING
);
```

**Design notes:**

- `LINKS_TO` stored uni-directionally (Page→Page). Backward traversal via Cypher MATCH pattern; no materialized inverse.
- `Page.created_at` / `Page.first_run_id` set on first INSERT, never overwritten.
- `Source.status='moved'` keeps the original `source_id` as PK; `moved_to` points at the new id; a separate `Source` row exists for the destination.
- `Source.source_type` is the multi-source discriminator. v1 emits only `"obsidian-kdb-raw"`. Future source-types plug in without schema change.
- `Page.body` intentionally absent — bodies live in markdown files (D8 boundary).
- **Timestamps are `STRING`, not Kuzu native `TIMESTAMP`.** Stored as `datetime.now().astimezone().isoformat()` (e.g., `2026-05-13T20:30:00-04:00`). Preserves the system-local offset per project rule `feedback_local_time_everywhere`. Kuzu's native `TIMESTAMP` type normalizes to UTC internally and would lose the offset on round-trip. Round-trip preservation verified in `test_ingestion.py`.

---

## 5. Ingestion algorithm

```python
def apply_compile_result(cr, scan_dict, run_id, *, conn) -> SyncResult:
    """Apply one compile run's deltas to the Kuzu graph. Atomic per run."""

    now = datetime.now().astimezone()  # local time w/ offset

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
            _replace_supports_for_source(conn, cs, run_id, now)  # atomic per-source: drop prior SUPPORTS, then recreate
            _update_source_compile_state(conn, cs, run_id, now)

        # --- Phase 4: orphan-candidate detection ---
        orphans = _detect_and_mark_orphans(conn, run_id, now)

    return SyncResult(...)
```

**Per-step Cypher:**

- **Upsert page:**
  ```cypher
  MERGE (p:Page {slug: $slug})
  ON CREATE SET p.created_at=$ts, p.first_run_id=$run_id
  SET p.title=$title, p.page_type=$type, p.status=$status,
      p.confidence=$conf, p.updated_at=$ts, p.last_run_id=$run_id
  ```

- **Replace outgoing edges (per-page):**
  ```cypher
  MATCH (a:Page {slug: $slug})-[r:LINKS_TO]->()
  DELETE r;

  MATCH (a:Page {slug: $slug})
  MATCH (b:Page {slug: $target})
  CREATE (a)-[:LINKS_TO {run_id: $run_id, created_at: $ts}]->(b)
  ```

- **Upsert source:**
  ```cypher
  MERGE (s:Source {source_id: $sid})
  ON CREATE SET s.first_seen_at=$ts
  SET s.hash=$hash, s.last_seen_at=$ts, s.last_compiled_at=$ts,
      s.compile_state=$state, s.last_run_id=$run_id, s.status='active'
  ```

- **Replace SUPPORTS for a source** (atomic per-source; symmetric to `_replace_outgoing_links`):
  ```cypher
  -- 1. Drop all existing SUPPORTS edges from this source
  MATCH (s:Source {source_id: $sid})-[r:SUPPORTS]->()
  DELETE r;

  -- 2. Recreate one SUPPORTS edge per page in the current compiled_source entry:
  MATCH (s:Source {source_id: $sid})
  MATCH (p:Page {slug: $slug})
  CREATE (s)-[:SUPPORTS {role: $role, hash_at_time: $hash, run_id: $run_id, created_at: $ts}]->(p)
  ```
  Pages the source no longer supports lose their SUPPORTS edge in step 1; if no other source supports them, Phase 4 orphan detection correctly flags them. Fixes Codex CRITICAL #2.

- **MOVED reconciliation** — transfer active SUPPORTS to destination, mark old source as historical:
  ```cypher
  -- 1. Transfer SUPPORTS edges from old source to new source
  MATCH (old:Source {source_id: $old_sid})-[r:SUPPORTS]->(p:Page)
  WITH old, p, r.role AS role, r.hash_at_time AS hash, r.run_id AS rid, r.created_at AS cts
  DELETE r
  WITH old, p, role, hash, rid, cts
  MATCH (new:Source {source_id: $new_sid})
  CREATE (new)-[:SUPPORTS {role: role, hash_at_time: hash, run_id: rid, created_at: cts}]->(p);

  -- 2. Mark old source as moved (historical breadcrumb)
  MATCH (old:Source {source_id: $old_sid})
  SET old.status='moved', old.moved_to=$new_sid, old.last_run_id=$run_id, old.updated_at=$ts
  ```

- **Orphan detection:**
  ```cypher
  MATCH (p:Page)
  WHERE NOT EXISTS { MATCH (:Source)-[:SUPPORTS]->(p) }
    AND p.status <> 'orphan_candidate'
  SET p.status='orphan_candidate', p.last_run_id=$run_id, p.updated_at=$ts
  RETURN p.slug
  ```

**Failure semantics:** transaction rolls back on any Kuzu raise. Stage 9 logs to journal but does not fail the overall run (D38).

---

## 6. Query API

### 6.1 Python surface

Methods: `__init__`, `apply_compile_result`, `get_page`, `get_source`, `neighbors` (direction, depth), `incoming_links`, `outgoing_links`, `shortest_path`, `pages_for_source`, `sources_for_page`, `subgraph_by_source`, `orphan_pages`, `pagerank` (NetworkX-backed), `communities` (Louvain via python-louvain), `structural_holes`, `cypher` (escape hatch), `stats`, `verify_against_manifest`, `rebuild_from_runs`.

### 6.2 CLI surface (`graphdb-kdb`)

| Subcommand | What it does |
|---|---|
| `graphdb-kdb init` | Creates the Kuzu directory + schema. Idempotent. |
| `graphdb-kdb sync --vault-root <path>` | Manually trigger ingest from `state/compile_result.json` + `state/last_scan.json`. |
| `graphdb-kdb verify --vault-root <path>` | Compare GraphDB to `manifest.json`. |
| `graphdb-kdb rebuild --vault-root <path>` | Drop tables; replay `state/runs/*.json` in chronological order. |
| `graphdb-kdb stats` | Print node/edge counts. |
| `graphdb-kdb neighbors <slug> [--depth N] [--direction out\|in\|both] [--json]` | List neighbors. |
| `graphdb-kdb incoming <slug>` | Sugar for neighbors --direction in --depth 1. |
| `graphdb-kdb path <from_slug> <to_slug>` | Print shortest-path chain. |
| `graphdb-kdb pagerank [--top N] [--json]` | Print PageRank-ranked pages. |
| `graphdb-kdb communities [--json]` | Print community assignments (Louvain via python-louvain). |
| `graphdb-kdb orphans` | List orphan-candidate pages. |
| `graphdb-kdb subgraph-by-source <source_id> [--json]` | Export subgraph. |
| `graphdb-kdb cypher "<query>" [--params <json>] [--json]` | Run ad-hoc Cypher. |

---

## 7. Pipeline integration

### 7.1 Stage 9 — `graph_sync`

```python
# ----- [9] graph_sync -----
_stage_open(9)
try:
    from graphdb_kdb import GraphDB, default_graph_path
    graph_dir = default_graph_path()  # ~/Droidoes/GraphDB-KDB/ unless KDB_GRAPH_PATH overrides
    with GraphDB(graph_dir) as graph:
        sync_result = graph.apply_compile_result(cr, scan_dict, run_id)
    _stage_close(9, ok=True, pages_upserted=..., edges_upserted=..., sources_upserted=..., orphans_detected=...)
except Exception as exc:
    note = f"{type(exc).__name__}: {exc}"
    _stage_close(9, ok=False, note=note, recovery_hint="run: graphdb-kdb rebuild")
    # NO call to _fail(); the overall run remains successful.
```

**Stage names list updated:** `STAGE_NAMES` gains `"graph_sync"` as element 9. `_STAGE_TOTAL` becomes 9.

**Ordering with `_finalize_and_write`:** Stage 9 runs **before** `_finalize_and_write` so its journal entry is captured. Final run-success status remains `true` even when Stage 9 closes with `ok=false` — this is what makes graph_sync non-fatal at the run-outcome level while still recording the failure in the journal.

### 7.2 Failure modes

| Failure | Effect on run | Recovery |
|---|---|---|
| `kuzu` not installed | Stage 9 fails non-fatally; journal flags it; compile run returns success | `pip install kuzu>=0.11` |
| Kuzu file lock contention | Stage 9 fails non-fatally on first contention; clear error message in journal | Identify other holder; rerun `graphdb-kdb sync`. Concurrent `kdb-compile` invocations not expected (L1); no retry/backoff per `feedback_no_imaginary_risk` |
| Schema drift | `_ensure_schema` detects, logs incompatibility, fails Stage 9 non-fatally | `graphdb-kdb rebuild` |
| Transaction violation | Single-run ingestion fails; transaction rolls back | Next run will retry; or `graphdb-kdb rebuild` |

---

## 8. Validation + rebuild paths

### 8.1 `graphdb-kdb verify`

Walks `manifest.json`; confirms every (page, edge, source) is in Kuzu with matching attributes. Reports missing-in-kuzu / missing-in-manifest / attribute-mismatch. Exit 0 if perfect agreement.

### 8.2 `graphdb-kdb rebuild`

Drops Kuzu tables; iterates `state/runs/<run_id>.json` in chronological order; extracts each run's `compile_result` + `last_scan` (embedded inline in v2 run journal — verified during #63.0; falls back to per-run `compile_result.json` sidecar if not embedded); applies via `apply_compile_result`. Migration entry point: first run backfills the 4 already-compiled sources.

---

## 9. File structure

```
graphdb_kdb/
├── __init__.py, __main__.py
├── schema.py, graphdb.py, ingestor.py, queries.py
├── verifier.py, rebuilder.py, cli.py, types.py
└── tests/
    ├── conftest.py, test_schema.py, test_ingestion.py,
    │   test_queries.py, test_verifier.py, test_rebuilder.py, test_cli.py
    └── fixtures/
```

`pyproject.toml`: adds `kuzu>=0.11`, `networkx>=3.0`, `python-louvain>=0.16`; adds `graphdb-kdb = "graphdb_kdb.cli:main"`.

---

## 10. Test surface (~58 total)

| File | Tests | Coverage |
|---|---|---|
| `test_schema.py` | ~4 | Table creation idempotent; schema version stored; reopen preserves schema. |
| `test_ingestion.py` | ~15 | Single-page upsert; multi-page upsert; outgoing edges replace (add, remove, change); SUPPORTS upsert; **SUPPORTS replacement (stale support cleared when a source recompile drops a page)**; **MOVED source transfers active SUPPORTS to destination**; source upsert; MOVED reconcile; DELETED reconcile; orphan detection; orphan revival on re-support; transaction rollback on bad input; idempotent re-apply of same run; multiple sources in one run; **timestamp offset round-trip (local ISO string preserved through write+read)**. |
| `test_queries.py` | ~14 | get_page; get_source; neighbors at depths/directions; incoming_links; shortest_path; pages_for_source; sources_for_page; subgraph_by_source; orphan_pages; pagerank; communities; structural_holes; cypher escape hatch; stats. |
| `test_verifier.py` | ~6 | Perfect agreement; missing-in-kuzu; missing-in-manifest; attribute mismatch; sources too; exit codes + JSON output. |
| `test_rebuilder.py` | ~6 | Empty + 0 runs; replay 1 run; replay N runs; orphan transitions over time; replay matches live ingest; **rebuild fails clearly when journal lacks replay payload**. |
| `test_cli.py` | ~10 | Each subcommand: argparse, JSON output, error paths. |
| `tests/integration/test_stage9.py` | ~3 | Stage 9 outcome persists in journal on `ok=true`; on `ok=false`; final run-success stays `true` even when Stage 9 closes with `ok=false`. |
| **Total** | **~58** | |

---

## 11. Sub-task breakdown

| Sub | Title | Deliverable | Dependencies |
|---|---|---|---|
| **#63.0** | **Replay-contract verification** | Inspect `run_journal.py` v2 schema. Three outcomes: (a) confirmed embedded → no code change; (b) not embedded → write-side embed OR per-run sidecar archive; (c) historical unrecoverable → downgrade D39 to "prospective from #63.0 forward" + one-off backfill. Outcome in D39 rationale. | None (pre-implementation blocker; gates all others). |
| **#63.1** | Schema + skeleton | `graphdb_kdb/{schema,graphdb,types}.py` + `test_schema.py` green. `graphdb-kdb init` works. `default_graph_path()` + `SCHEMA_VERSION` + empty migration registry. | **#63.0**. |
| **#63.2** | Ingestion algorithm | `ingestor.py` + `test_ingestion.py` green. | #63.1. |
| **#63.3** | Read query API | `queries.py` + `test_queries.py` green. CLI: neighbors, incoming, path, stats, cypher. | #63.1, #63.2. |
| **#63.4** | Analytics (hybrid) | PageRank + Louvain + structural_holes via NetworkX. | #63.3. |
| **#63.5** | Verifier | `verifier.py` + CLI `verify`. | #63.2. |
| **#63.6** | Rebuilder | `rebuilder.py` + CLI `rebuild`. Backfill canonical-corpus runs. | #63.2. |
| **#63.7** | Pipeline Stage 9 wiring | Edit `kdb_compile.py`; update `run_journal.py`. Integration tests. | All preceding. |
| **#63.8** | Documentation | CODEBASE_OVERVIEW.md §8 added. | All preceding. |
| **#63.9** | Snapshot/export | `graphdb-kdb snapshot` to JSONL. Belt-and-suspenders backup. | #63.3. |

**#63.0 gates all others**; no other sub-task lands until its outcome is in D39's rationale.

---

## 12. Dependencies

```bash
pip install kuzu>=0.11 networkx>=3.0 python-louvain>=0.16
```

---

## 13. Open questions

### 13.1 Resolved

| ID | Question | Resolution |
|---|---|---|
| **Q1** | OneDrive corruption risk | Move to `~/Droidoes/GraphDB-KDB/`. Recovery-via-D39 + #63.9 snapshot. |
| **Q2** | `knowledge_graph/` legacy collision | README note. |
| **Q4** | Transaction scope | Per-run atomic. |
| **Q5** | CLI name | `graphdb-kdb`. `kdb-graph` reserved. |
| **Q6** | Schema evolution | Scaffold `SCHEMA_VERSION` + migration registry in #63.1. |

### 13.2 Owned by sub-task #63.0

| ID | Question | Resolution path |
|---|---|---|
| **Q3** | Run-journal `compile_result` embedding | Owned by #63.0. Three outcomes: confirm / embed-going-forward / sidecar archive / downgrade-D39 + backfill. Outcome recorded in D39 rationale. |

---

## 14. Known limitations (v1)

| # | Limitation | Severity |
|---|---|---|
| L1 | Kuzu single-writer; concurrent kdb-compile fails Stage 9 on second invocation (no retry/backoff per `feedback_no_imaginary_risk`). | Trivial |
| L2 | NetworkX analytics in Python; noticeable at 10⁵+ nodes (current scale: 62 pages). | Low for v1 |
| L3 | Rebuild always succeeds (well-formed compile_results); can't simulate mid-history graph_sync failures. | Trivial |
| L4 | Verifier compares overlap only; `manifest.json` system-state fields not mirrored. | None (by design) |
| L5 | `Source.canonical_path` currently equals `source_id` (forward-compat placeholder). | None |
| L6 | Schema locked at first connection; migration framework scaffolded but minimal in v1. | Low |
| L7 | Stage 9 gated on Stage 8 success (sequential pipeline order); no data dependency on Stage 8 output but execution-level coupling. | Low |

---

## 15. Verification criteria for closure

- [ ] **Sub-task #63.0 outcome recorded in D39 rationale.**
- [ ] All sub-tasks #63.1–#63.9 closed with commits.
- [ ] `pip install -e .` succeeds; `python -c "import graphdb_kdb"` works.
- [ ] `graphdb-kdb init` creates Kuzu directory + schema; idempotent on second run.
- [ ] All ~58 tests across `graphdb_kdb/tests/` + `tests/integration/` green.
- [ ] `graphdb-kdb rebuild --vault-root ~/Obsidian` populates Kuzu from 4 historical runs; produces 62-page graph matching manifest.
- [ ] `graphdb-kdb verify --vault-root ~/Obsidian` reports perfect agreement after rebuild.
- [ ] Independence ablation tests pass (delete-manifest, delete-graph + rebuild).
- [ ] Live compile end-to-end: Stage 9 success; subsequent verify reports zero divergence.
- [ ] No regression in existing pipeline.
- [ ] `graphdb-kdb snapshot` round-trips correctly.
- [ ] CODEBASE_OVERVIEW.md §8 added with D32–D40.

---

## 16. What "Proceed" looks like

1. **Lock the blueprint** by committing this file to `docs/`.
2. **Open Task #63** in `docs/TASKS.md` (status `in-progress`).
3. **Run sub-task #63.0 (replay-contract verification) FIRST** — pre-implementation blocker:
   - Inspect `kdb_compiler/run_journal.py` schema.
   - Apply the decision tree from §11 / §13.2.
   - Record outcome in D39's rationale before any other sub-task lands.
4. **Start sub-task #63.1** (schema + skeleton) via TDD:
   - Add deps to `pyproject.toml`.
   - Write `test_schema.py` first (failing); implement minimal `schema.py` + `graphdb.py` + `types.py` + `default_graph_path()` helper + `SCHEMA_VERSION` + migration registry.
   - Add `graphdb-kdb init` skeleton to `cli.py`.
   - Verify with `pip install -e .` + `graphdb-kdb init` smoke test.
```

---

# Appendix B — Your prior review (verbatim)

This is the response you produced from the v1 prompt. Use it to cross-reference your prior findings against the v2 fixes.

```
## Top-line verdict
YELLOW — the direction is sound, but the proposal overclaims independence and multi-source readiness until replay inputs, timestamp persistence, and edge replacement semantics are tightened.

## Critical findings (must-fix before code lands)

- Severity: CRITICAL
- Location: D34/D39; §8.2; Q3; kdb_compiler/run_journal.py:263; docs/compile_result.md:57; docs/last_scan.md:34
- Evidence: D34/D39 state that state/runs/<run_id>.json carries replayable compile_result; §8.2/Q3 admits this is unverified. Current journal stores only paths to overwritten baton files, and docs say compile_result.json / last_scan.json have no history.
- Claim: Rebuild is not currently a real historical independence proof. At best it is prospective after a journal format change.
- Recommendation: Add a pre-implementation #63.0 replay-contract task: prove every required historical run contains compile_result + last_scan, or change the journal writer to embed compact snapshots going forward and explicitly downgrade historical rebuild/backfill claims.

- Severity: CRITICAL
- Location: §5 SUPPORTS upsert/orphan detection; docs/task-graphdb-kdb-blueprint.md:218
- Evidence: SUPPORTS uses MERGE (s)-[r:SUPPORTS]->(p) but never deletes support edges for pages no longer emitted by a recompiled source. Orphan detection only checks for zero SUPPORTS.
- Claim: A page dropped by a source recompile can retain stale SUPPORTS forever, so orphan detection is wrong and rebuild will reproduce the wrong graph.
- Recommendation: Replace SUPPORTS per source atomically: delete current non-historical (s)-[:SUPPORTS]->() for that source, then recreate edges from the current compiled source. If historical support is needed, model it separately and exclude it from orphan detection.

- Severity: CRITICAL
- Location: Constraint note "local time everywhere"; §4 timestamp fields; §5 now; docs/task-graphdb-kdb-blueprint.md:90
- Evidence: The schema uses Kuzu TIMESTAMP, while the project rule says persisted datetimes should be system-local ISO with offset. Kuzu docs state TIMESTAMP accepts offsets and stores based on offset relative to UTC: https://docs.kuzudb.com/cypher/data-types
- Claim: The proposal is ambiguous at best, and likely loses the exact local ISO-with-offset representation.
- Recommendation: Store persisted datetimes as STRING containing datetime.now().astimezone().isoformat(), or explicitly document and test Kuzu round-tripping with local offset if keeping TIMESTAMP.

- Severity: CRITICAL
- Location: Constraint note "No complexity for imaginary risk"; §7.2 lock contention; L1; docs/task-graphdb-kdb-blueprint.md:322
- Evidence: §7.2 adds 3 retries with 100ms backoff for Kuzu file locks, while the review constraints explicitly say to drop lock/retry ceremony for the single-user setup.
- Claim: This contradicts a load-bearing prior decision.
- Recommendation: Remove retry/backoff from v1 or document it as a minimal Kuzu-open behavior only if the team explicitly revises the constraint.

## Material concerns (worth addressing during implementation)

- Severity: MATERIAL
- Location: D32; §5 entrypoint; compile_result schema; kdb_compiler/schemas/compile_result.schema.json:49
- Evidence: The ingest API consumes compile_result + last_scan; current schema hardcodes source_id as ^KDB/raw/.+, summary slugs, and page types summary|concept|article.
- Claim: Multi-source is an aspiration, not yet a source-agnostic contract. Arxiv/YouTube producers will need adapters or schema changes.
- Recommendation: Introduce a small GraphRun/GraphSource normalized ingestion contract, with Obsidian compile output as the first adapter.

- Severity: MATERIAL
- Location: §7.1 Stage 9 journal persistence; current orchestrator finalization; kdb_compiler/kdb_compile.py:467
- Evidence: Current kdb_compile.py writes the final journal immediately after Stage 8. The proposal says Stage 9 logs a journal entry but does not explicitly move finalization after Stage 9.
- Claim: If implemented by simple append, Stage 9 may not persist in the run journal.
- Recommendation: State explicitly: Stage 9 runs before _finalize_and_write; final success remains true even when stage 9 has ok=false.

- Severity: MATERIAL
- Location: §4 moved Source semantics; §5 phase 2; existing manifest move behavior; kdb_compiler/manifest_update.py:287
- Evidence: Manifest move handling rekeys source references on pages. The GraphDB proposal keeps old and new Source rows but does not specify whether SUPPORTS edges move to the destination.
- Claim: Source move queries can double-count or keep current support on the moved-from source.
- Recommendation: Define move semantics precisely: active SUPPORTS edges should point to the destination Source; old Source should either have no SUPPORTS or only explicitly historical relationships.

- Severity: MATERIAL
- Location: §10 tests; §15 verification criteria
- Evidence: Tests cover ingestion broadly, but the target list misses timestamp offset round-trip, stale SUPPORTS replacement, Stage 9 journal persistence, and rebuild failure when journals lack replay payload.
- Claim: The highest-risk independence and temporal semantics are under-tested.
- Recommendation: Add focused tests for those four cases before analytics tests.

## Cosmetic notes

- §7.2 still mentions OneDrive corruption despite D35 moving Kuzu outside OneDrive; remove or mark "obsolete after D35."
- §11 puts documentation at #63.8, but the North Star update should happen before or alongside #63.1 per your own system prompt.
- §6.2 lists communities --algorithm leiden, but dependencies only include python-louvain.

## What looks right

- D34's shared-upstream independence model is the right shape.
- Keeping GraphDB parallel to manifest avoids a bad migration cliff.
- Kuzu + NetworkX hybrid is appropriately scoped for current scale.
- The CLI split between graphdb-kdb and future kdb-graph is now clean.
- The ablation tests in §15 are exactly the right closure criteria.

## Questions for the team

- Should GraphDB preserve historical source support, or only current support?
- Is GraphDB meant to be source-agnostic at the storage layer only, or at the ingestion contract too?
- Should graphdb-kdb rebuild include dry-run journals, failed journals, or only successful non-dry-run compiles?
```

---

End of review request v2. Produce your structured re-verification per §7 above.
