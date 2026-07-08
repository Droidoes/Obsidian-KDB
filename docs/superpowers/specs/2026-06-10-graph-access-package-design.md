# Graph-Access Package + Read-Only MCP Server — Architecture Brief (v0.3)

> **⏸ STATUS UPDATE 2026-07-07 — Phase 3b (`stress_test`, the Named Gate) ABANDONED.**
> A precondition check on the live 248-entity sandbox graph showed the metacognitive
> analytics are **degenerate at personal scale**: grounding has no variance (214/218
> canonical entities have exactly 1 source) and only 2 of 486 LINKS_TO edges cross a
> community boundary (4 bridge entities). The stress test needs grounding-variance +
> real bridges to yield non-trivial output — the ratified *scale hedge* firing — and
> with no ground truth it would be correct-but-unvalidatable code against an untunable
> formula. **§1.5 (the Named Gate) and §3.5(c) (the analytics/composite tool) are
> superseded on that basis.** The rest of the brief STANDS: the `kdb_graph` package
> boundary + the 7-tool read-only MCP server (Phases 1/2/3a) shipped and are a
> **retained asset** — the intended front door for querying the graph — parked, to be
> re-prioritized after the vault-in-place ingestion produces a comprehensive graph.
> See `docs/2026-07-07-state-of-the-system.md` and `docs/TASKS.md` #113.

**Date:** 2026-06-10
**Status:** RATIFIED (Joseph, 2026-06-10) — design review 5/5 GO-WITH-FIXES folded; Named Gate chosen
**Author:** Joseph + Claude (brainstorm session 2026-06-10)
**Supersedes/extends:** `docs/reference/kdb-storage-architecture.md` ("The Gate"),
session-handoff-2026-06-09.md (MCP server direction)
**Reviews:** `docs/superpowers/specs/reviews/2026-06-10-graph-access/` (codex, deepseek-v4-pro, gemini, grok, qwen)
**Killer-app challenge:** `docs/superpowers/specs/2026-06-10-mcp-killer-app-challenge.md` + `reviews/2026-06-10-mcp-killer-app/` (6 proposals: codex, deepseek-v4-pro, gemini, gemini-pro, grok, qwen)

### v0.2 → v0.3 changelog
- **Named Gate RATIFIED (§1.5):** the MCP's load-bearing consumer is the **Epistemic Load-Bearing Stress Test** (1.0), with bridge-synthesis as its generative twin; Worldview Reconciliation is the 2.0 North Star. Resolves prerequisite P3.
- **Day-one tool surface CORRECTED (§3.5):** the Gate forces an **analytics/composite tool** over `analytics.py` (`pagerank`/`communities`/`structural_holes`) + 1–2 new primitives — the MCP server is NOT only thin adapters over `queries.py`.

### v0.1 → v0.2 changelog (panel fold-in)
- **NEW prerequisites (§7):** the `read_only` dead-flag fix + read-only-never-migrates; name the MCP's own Gate query.
- **F5 lean REVERSED:** concurrency is not a non-blocker — per-query reopen is *required* policy (snapshot-pinning). 4/5 refuted the v0.1 lean with empirical Kuzu evidence.
- **Consumer inventory (§2) expanded** from 6 → ~15, including the active O1 Promotion write-path.
- **F1 scope widened** to name `core/`, `ops/`, `verifier`, `rebuilder`, `snapshot`, `cli`, `adapters` explicitly.
- **New contracts (§4.5):** schema-version-as-package-contract, `kdb_graph.testing`, MCP response shapes, raw-`cypher()` exclusion, config/path threading.

---

## 1. Motivation — the realization

The 06-09 handoff framed "The Gate" as *name one external query to justify the
GraphDB*. This session found the Gate is **already passed by an internal
consumer**: the compile pipeline's Pass-2 context loader
(`compiler/context_loader.py`, Task #90) already queries the graph before each
Pass-2 to hand the LLM existing entities — so it links/reuses instead of minting
duplicates. The graph already earns its keep.

That reframed the real question. Joseph's instinct: build a **read-only MCP
server** so interactive/agent consumers (a chat app, GraphRAG retrieval, ad-hoc
entity lookups) can query the graph too. Pursuing it surfaced a deeper
architectural fact (see `memory/feedback_interrogate_anchored_premise.md`):

> The **GraphDB is a durable asset**. The compiler is **one producer** (writer).
> The MCP server, the graph-view generator, KPI/analytics, cleanup, the O1
> promotion pipeline, and the `graphdb-kdb` CLI are **consumers/operators**. The
> access contract (schema + read/write API) is shared by all and **owned by none
> individually**. Today that contract (`kdb_graph/`) lives *inside* the compiler
> repo — a premise that was never interrogated. It should be **extracted** so the
> compiler is just one client.

The data being outside the repo is a red herring: data is always outside (so is
the vault). What matters is where the **code that understands the data** lives.

**Scope note (panel):** Phase B already `git mv`'d the package to a top-level
peer (`kdb_graph/`) with its own tests + CLI. So "extract" here means
**formalize the boundary Phase B structurally created** (packaging, read-only
correctness, operational contracts, MCP assembly) — *not* a greenfield move or a
repo split.

## 1.5 The Named Gate — what the MCP server is FOR (ratified 2026-06-10)

The MCP server needs its own load-bearing consumer (panel prerequisite P3). A
6-model generative challenge (`2026-06-10-mcp-killer-app-challenge.md`) was run to
name one; 6/6 proposals beat the retrieval floor, and 4/6 converged on the same
idea. **Ratified Gate:**

- **PRIMARY (1.0, ships now) — the Epistemic Load-Bearing Stress Test.**
  *"Which of my most-relied-on ideas rest on the thinnest evidence — especially
  the ones bridging separate areas of my thinking?"* A 3-way structural
  intersection: **PageRank (influence) × structural-hole bridge-position ×
  SUPPORTS-degree (grounding)**. It is the convergent A-tier proposal
  (Qwen A+, Grok A), graph-native (no text approximation), **measured not
  speculated**, recurring (the topology shifts every compile), and its output is a
  *research agenda*, not a lookup. It exploits the property that makes a personal
  graph different from a public one: thin grounding is *signal*, not a data-quality
  defect.
- **GENERATIVE TWIN (1.0, same engine) — bridge synthesis.** Same
  communities/structural-holes/pagerank machinery, but the output is "write this
  note / read this next" — the sparsest bridge between two clusters becomes a
  synthesis prompt (Codex/Gemini-flash; Deepseek/Qwen runner-ups).
- **2.0 NORTH STAR — Worldview Reconciliation** (gemini-pro): active
  `CONTRADICTS`/`SUPERSEDES` Claims → forced belief revision. The named
  justification for building the Claim layer (O1, #83–86); parked behind 2.0.

**Why this matters to THIS design:** the Gate is what dictates the MCP tool
surface (§3.5). The stress test runs on `analytics.py` (already built), not the
six thin `queries.py` adapters — so the server's *reason to exist* requires
exposing analytics through MCP. That is now a day-one requirement, not deferred.

## 2. Grounding facts + consumer inventory (verified this session + panel)

- **`kdb_graph/` has ZERO dependency on `common/`.** Self-contained: own
  `types.py`, depends only on `kuzu` / `networkx` / `python-louvain`. Confirmed by
  three reviewers (172 imports checked). → **already cleanly extractable.**
- **Kuzu is embedded + single-writer.** In-process library, no daemon. One
  read-write handle; others attach read-only — but a read-only handle is
  **snapshot-pinned at open time** (does not see later commits until reopened).
- **Bodies are NOT in the graph** (thin-node decision). Bodies live in the
  **wiki/ content store**, written by `compiler/page_writer.py` via
  `common/paths.py`. `get_body` joins a *second* store.

**Consumer / operator inventory** (v0.1 listed 6; panel verified ~15 — the
write-path count is what matters for F1 scope):

| Consumer | R/W | In-process? | Notes |
|----------|-----|-------------|-------|
| `orchestrator` / `compiler` intake | **Write** | yes (write lock) | the producer |
| `tools/cleanup.py` (`apply_cleanup`) | **Write** | yes | 2nd write path |
| `tools/diagnostics/validate_domain_backfill.py` | **Write** (temp) | yes | 3rd write path |
| `kdb_graph/ops/op_1_promote.py` (O1) | **Write** | yes | **active #83–86 belief-revision write-path** — Claim nodes + 5 claim rels |
| `kdb_graph/rebuilder.py` | **Write** | yes | drop-and-replay; most destructive op |
| `kdb_graph/intake.py` | **Write** | yes | the write core |
| `kdb_graph/cli.py` (`graphdb-kdb`, 15 subcmds) | R+W | yes | admin/operational (`init`/`verify`/`rebuild`/`stats`/…) |
| `kdb_graph/verifier.py` | R+W (temp) | yes | layer-2 replay diff |
| `kdb_graph/snapshot.py` | Read | yes | JSONL export |
| `kdb_graph/core/belief_classifier.py` | compute | yes | stateless O1 classifier |
| `compiler/context_loader.py` (Pass-2) | Read | yes | compile-tuned T1/T2/T3 — **stays in compiler** |
| `compiler/kpi/graph.py` | Read | yes | graph KPIs |
| `orchestrator/emit_kpis.py` | Read | yes | passes dead `read_only=True` |
| `tools/viewer/kdb_graph_viewer.py` (+ bakeoff) | Read | yes | pure readers, raw Cypher, dead `read_only=True` |
| **NEW: MCP read server** | Read | no (protocol) | interactive/agent front door |

## 3. Settled architecture

1. **`kdb_graph` is the standalone graph-access package** — owner of the GraphDB
   read/write contract: schema + migrations + types + queries + intake + **ops/
   (O1 write-path) + rebuilder + verifier + snapshot + adapters + cli**. The
   compiler/orchestrator/tools depend on it.
2. **Read-only MCP server, co-located with the core.** Writes never go through it.
   "Read-only by construction" requires the §7 prerequisite fix to be *true*.
3. **One query-core, multiple transports** (parallel readers of the shared core,
   NOT client-and-server to each other):
   - **in-process** — compiler imports the core for Pass-2 (it's the writer).
   - **MCP** — read server for interactive/agent consumers.
   - **HTML** — graph-view generator (another reader output).
4. **`context_loader` stays in the compiler.** Its T1/T2/T3 + PageRank + page-cap
   is compile-specific tuning interactive consumers don't want verbatim. Becomes a
   client of the core; no refactor.
5. **Day-one MCP read tools** — three layers (NOT just thin adapters; the §1.5
   Gate forces the analytics layer):
   - **(a) thin adapters over `queries.py`:**
     - `graph_neighborhood(slug, depth=1, direction="both")` → `queries.neighbors`
     - `find_path(from_slug, to_slug)` → `queries.shortest_path`
     - `get_entity(slug)` → node metadata
     - `entities_for_source(source_id)` / `sources_for_entity(slug)` → provenance
     - `resolve_search_keys(keys)` → alias-aware canonical resolver (Codex: make
       this **first-class** — users ask names/aliases, not exact slugs)
   - **(b) content-store join (NEW):** `get_body(slug)` → reads wiki/ (not Kuzu).
   - **(c) analytics/composite (the Gate — NEW, over `analytics.py`):**
     `stress_test(top_n=5)` — composes `pagerank` × `structural_holes` ×
     `communities` × per-entity SUPPORTS-degree into the load-bearing-weak-points
     report (§1.5 PRIMARY). Implies two cheap new `queries.py` primitives:
     `indegree(slug)` (incoming `LINKS_TO` count) and `entity_list(page_type=,
     status=)` (bulk enumeration for the scoring loop). The generative twin
     (bridge-synthesis) reuses the same composite — a thin re-projection, not a
     second engine.
6. **Deferred until a real query demands them:** `fts_search` (gated SQLite FTS5),
   assembled-GraphRAG "answer" tool, `export_graph_view` MCP tool, raw `cypher()`,
   and the 2.0 Claim-layer tools (Worldview Reconciliation — §1.5 North Star).

## 4. Resolved forks (panel convergence)

- **F1 — Extraction scope: WHOLE package. (5/5 AGREE.)** Schema/migrations/intake/
  reads/ops are one contract; splitting reintroduces drift (the destructive
  2.3→2.4 migration shows a 2.3-reader/2.4-writer would silently produce wrong
  BELONGS_TO). *Scope is larger than v0.1 stated* — see §2 + §3.1. Codex:
  internally structure the package as `core` (schema/conn/types/queries) /
  `intake` (writers) / `adapters/obsidian` / `ops` / `cli` so the Obsidian
  adapter doesn't masquerade as generic core.

- **F2 — Packaging: in-repo clean package first. (5/5 AGREE.)** Own
  `pyproject.toml`/workspace member + namespace + tests when MCP lands. Physical
  repo split only on a third external consumer. **Add `kdb_graph.testing`** (or
  `kdb_graph[test]`) — `tools/tests` currently import `kdb_graph.tests.conftest`,
  which becomes a boundary violation post-extraction.

- **F3 — Stores stay separate. (5/5 AGREE.)** Graph package owns the graph; a thin
  content accessor owns wiki/; the MCP **assembly layer** joins them. Content
  accessor takes **`slug` + `page_type` as inputs** (does NOT re-query the graph —
  that's a hidden coupling); resolves path via a pure
  `slug_to_wiki_path(slug, page_type, vault_root)` over `common/paths`, then reads
  the file. Keeps both stores independently testable.

- **F4 — Viewer: co-locate as a reader output; do NOT MCP-ify. (5/5 AGREE.)**
  Open decision to record: the viewer uses raw introspective Cypher
  (`show_tables()` + per-table `MATCH`), not `queries.py`. Co-location is the
  moment to choose — export a `full_subgraph()` primitive in the package, or keep
  the viewer an intentional schema-introspective special case. **Lean: keep it a
  special case** (it needs *everything*, not a tuned subset); revisit if a second
  full-dump consumer appears.

- **F5 — Transport stdio: AGREE (5/5). Concurrency lean REVERSED (4/5).** v0.1
  called concurrency a non-blocker; the panel refuted it with empirical Kuzu
  evidence (snapshot-pinning, documented in
  `2026-05-28-orchestrate-e2e-design.md`). The real risk is **stale reads + a
  false read-only handle**, both correctness bugs. **Required policy:** the MCP
  server **opens (or reopens) the DB per tool invocation** read-only, or stamps
  every response with `graph_opened_at` so staleness is detectable. Persistent
  read connection is a perf optimization only safe when no writer is active.
  stdio local-first; HTTP/SSE later.

### 4.5 New contracts the panel requires

- **Schema version is a package contract.** `SCHEMA_VERSION` is versioned
  *independently* of the package version. **Every consumer checks it at startup.**
  Read-only consumers **never migrate** — they verify and **fail fast** on
  mismatch with an actionable message (e.g. *"Graph is v2.3, package expects v2.4;
  run `graphdb-kdb rebuild`"*). Only the writer/CLI triggers migration.
- **MCP response shapes are a stable public API.** Do not return raw in-process
  dataclasses over MCP — define serialized response shapes + an error envelope.
- **Exclude raw `cypher()` from MCP v1.** Unbounded reads + schema-coupled prompts;
  list in deferred/excluded tools.
- **Config/path discovery is package-provided, app-owned defaults.** The package
  exposes graph-path resolution (`default_graph_path()` / `KDB_GRAPH_PATH`); the
  MCP server + `get_body` also need the vault root threaded through config with
  documented precedence. `default_graph_path()` baking `~/Droidoes/GraphDB-KDB` is
  acceptable in-repo but the installable package should accept explicit paths.
- **Adapter is the producer extension point.** `adapters/obsidian_runs.py` is the
  reference `ProducerAdapter` impl and ships with the package; a second producer
  implements the protocol without touching core. Treat it as a versioned interface
  with a backward-compat promise.
- **Don't make Entity-only assumptions.** Claim tables (v2.2) already exist; the
  extraction must not block later `claims_about(slug)` / evidence-retrieval tools.

## 5. What explicitly does NOT change

- Writes stay in the producer/operators (in-process, exclusive handle).
- `context_loader` Pass-2 logic untouched.
- GraphDB data location (outside the repo) unchanged.
- No FTS index, no assembled-GraphRAG answer tool, no `export_graph_view` MCP tool,
  no raw-Cypher MCP tool until a concrete need proves the primitives insufficient.

## 6. Prerequisites — MUST land before any MCP code (§7 detail)

These are correctness gates, not follow-ons. The panel was unanimous (P1) /
strong (P2–P3).

- **P1 (5/5, blocker) — Make `read_only=True` real.** `GraphDB._open()` currently
  ignores the flag: always `kuzu.Database(path)` (read-write) + always
  `_ensure_schema()` (DDL). Fix: pass `read_only=self._read_only` to
  `kuzu.Database(...)` **and skip `_ensure_schema()` on read-only open**. Add a
  regression test that write methods (`apply_compile_result`, `apply_cleanup`,
  `detect_orphans`, `wire_links`) fail/are blocked when `_read_only`. ~10 LOC + test.
- **P2 (4/5) — Read-only schema verification + fail-fast.** A read-only open
  verifies `SCHEMA_VERSION` and raises a structured incompatible-schema error
  instead of migrating.
- **P3 (1/5, Qwen — strategic) — Name the MCP's own Gate query. ✅ RESOLVED v0.3.**
  See **§1.5**: the named Gate is the Epistemic Load-Bearing Stress Test (1.0),
  chosen via the 6-model killer-app challenge. The server now has a load-bearing
  consumer; it is not infra-without-a-user.

## 7. Recommended implementation sequencing (panel-converged)

1. **P1** — real read-only `GraphDB` open (no DDL on read path) + block writes on
   read-only handle. *(prerequisite)*
2. **P2** — schema-version fail-fast on read-only open.
3. **P3** — name the MCP Gate query; record it in this brief + JOURNEY.
4. Add `kdb_graph` package metadata (`pyproject.toml` workspace member) +
   `kdb_graph.testing` fixtures module; update `tools/tests` imports.
5. Thin **content-store accessor** (`slug`+`page_type` → wiki/ body) as its own
   module/contract.
6. **MCP stdio server**, assembly layer, six bounded read tools + per-query reopen
   policy + stable response/error shapes. Add `get_body` once the accessor exists.
7. Co-locate the graph-view generator under the package tree (keep it a
   schema-introspective special case for now).
8. **Defer:** separate repo, FTS, GraphRAG answer tool, `export_graph_view`,
   raw-Cypher MCP tool.

## 8. Panel verdict summary

| | Codex | Deepseek | Gemini | Grok | Qwen |
|--|--|--|--|--|--|
| Framing | sound | sound | sound | sound | sound (inventory incomplete) |
| F1 whole pkg | agree+ | agree | agree | agree | agree (bigger scope) |
| F2 in-repo | agree | agree | agree | agree | agree |
| F3 stores | agree | agree | agree | agree | agree |
| F4 viewer | agree (defer move) | agree | agree | agree | agree |
| F5 stdio | agree | agree | partial | partial | agree |
| F5 concurrency non-blocker | must-fix | (held) | disagree | disagree | disagree |
| `read_only` dead flag | ✔ | (schema) | blocker | blocker | blocker |
| Timing: extract now | yes | yes | yes | yes | yes (formalize) |

**Net:** unanimous GO-WITH-FIXES. The core design survives intact — every fix is
additive hardening; none challenges the producer/consumer/asset decision.
