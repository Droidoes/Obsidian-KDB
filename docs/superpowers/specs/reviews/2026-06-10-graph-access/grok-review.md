# Design Review — Graph-Access Package + MCP Server

**Reviewer:** Grok (independent panel)
**Brief:** `docs/superpowers/specs/2026-06-10-graph-access-package-design.md`
**Date:** 2026-06-10

---

## 1. Producer / consumer / durable-asset framing

**Verdict: SOUND — extract the access contract; keep compile-specific composition in the compiler.**

The brief correctly reframes "The Gate" from a hypothetical external query to an observed internal one: `context_loader` already reads the graph on every Pass-2 compile. The durable asset is the GraphDB (schema + on-disk Kuzu store + the code that understands both), not the compiler binary. Grounding is accurate: `kdb_graph/` has no `common/` dependency, owns schema/migrations/types/queries/intake, and `ObsidianRunsAdapter` already bridges producer JSON without importing compiler modules.

There is no strong reason to keep the access contract coupled to the compiler. Coupling made sense historically (single consumer, co-evolving schema), but Phase B already moved `kdb_graph` to a peer package in the monorepo — the conceptual extraction is largely done; what remains is formalizing the boundary (packaging, MCP transport, operational contracts). The compiler should remain the exclusive in-process writer and owner of Pass-2 composition (`T1/T2/T3`, domain gate, PageRank tie-breaks) — that is legitimately compile-specific, not graph-contract.

The one coupling worth naming explicitly (brief omits it): `kdb_graph/adapters/obsidian_runs.py` is a producer-shape adapter tied to Obsidian-KDB run-journal layout. It belongs in the graph package as long as Obsidian-KDB is the sole producer; if a second producer appears, adapters should fan out from the package edge, not pull producer logic inward.

---

## 2. Open forks F1–F5

### F1 — Extraction scope (whole `kdb_graph` vs read-subset)

**AGREE.**

Schema, migrations, intake, and read primitives are one contract. Splitting write-path (intake) into the compiler while readers live in a separate package reintroduces the drift the brief targets — readers and writers would version independently, and MCP/orchestrator/cleanup would disagree on node shapes. The whole package is already extractable (zero `common/` deps); there is no untangling cost argument for a read-subset.

### F2 — Packaging / repo boundary (in-repo package first vs separate repo now)

**AGREE.**

Phase B (`docs/superpowers/plans/2026-06-02-phase-b-package-split.md`) already `git mv`'d `graphdb_kdb` → `kdb_graph` as a peer top-level package with its own tests. The MCP server is the second consumer proving the boundary works across process lines; a third external consumer (or a distinct release cadence) is the right trigger for a physical repo split. Premature separate-repo extraction adds release/CI overhead with no current beneficiary. **Recommendation:** add a dedicated `pyproject.toml` (or workspace member) for `kdb_graph` when MCP lands — formalize what Phase B structurally achieved.

### F3 — `get_body` / content-store ownership

**AGREE.**

The three-store model (graph = ontology metadata, wiki/ = rendered bodies, manifest = file lifecycle) is load-bearing. `get_body` needs `page_type` from the graph (`get_entity`) plus path resolution (`common/paths.slug_to_abspath`) plus filesystem read — a classic assembly-layer concern. Putting wiki I/O inside `kdb_graph` would couple the graph package to vault layout and Obsidian path conventions. **Nuance:** the thin content accessor should depend on `common/paths` (pure path logic), not re-derive `KDB/wiki/{subdirs}/{slug}.md` rules.

### F4 — Graph-view generator placement

**AGREE with lean** (co-locate now; do not MCP-ify yet).

`tools/viewer/kdb_graph_viewer.py` is already a pure reader (`GraphDB(..., read_only=True)`, no compiler imports). Co-locating it with the graph-access package makes the "reader outputs" family explicit (MCP tools, HTML export, future analytics views). Deferring `export_graph_view` as an MCP tool is correct — it emits a large file artifact, not a chat-sized answer. **Minor follow-up:** the viewer currently issues raw `CALL show_tables()` / `MATCH (n:\`{tbl}\`)` Cypher rather than `queries.py` primitives; co-location is the moment to decide whether a `export_full_graph()` query primitive belongs in the package or the viewer stays intentionally schema-introspective.

### F5 — MCP transport + concurrency posture

**PARTIALLY AGREE — stdio yes; concurrency is understated.**

**Transport:** stdio local-first is correct for single-user, same-machine agent/chat integration. HTTP/SSE can wait.

**Concurrency: DISAGREE that persistent read-only attach is a non-blocker.** Empirical Kuzu 0.11.3 probing (documented in `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md`) shows a separate read-only `Database` held open is **snapshot-pinned at open time** and does not see later commits until reopened. That directly affects MCP freshness during an orchestrator compile run. The brief's "open-per-query or back off" is the right mitigation but should be elevated from optional footnote to **required MCP server policy**: open (or reopen) the database per tool invocation, or explicitly document staleness. Persistent connection is a performance optimization only safe when no writer is active.

**Prerequisite blocker the brief does not mention:** `GraphDB._open()` currently **ignores** the `read_only=True` constructor flag — it always opens read-write and runs `_ensure_schema()` (which can execute DDL migrations). Every caller passing `read_only=True` (viewer, `emit_kpis`, future MCP) gets a silent read-write handle. Fixing this is a hard prerequisite before shipping the MCP read server; otherwise "read-only by construction" is false.

---

## 3. Gaps — consumers, failure modes, risks

| Gap | Severity | Recommendation |
|-----|----------|----------------|
| **`read_only` flag not wired** | Blocker | Implement `kuzu.Database(path, read_only=True)` + skip `_ensure_schema()` DDL on read-only open before MCP ships. |
| **Kuzu snapshot semantics** | High | Document MCP staleness model; mandate per-query reopen or version/token in tool responses ("graph as of schema v2.3, opened 14:32:01"). |
| **Multi-writer contention** | Medium | Brief assumes single writer (orchestrator). `tools/cleanup.py` also calls `apply_cleanup` (write). Two write paths can contend on Kuzu's single-writer lock — brief should acknowledge cleanup-as-second-writer and state expected failure mode (block/retry/queue). |
| **Schema version across boundary** | Medium | MCP startup should read `SCHEMA_VERSION` / `gdb.schema_version()` and fail fast on mismatch with a actionable message (`pip install -e .` / rebuild). Pin `kdb_graph` version in MCP assembly metadata. |
| **Test-fixture coupling** | Medium | `tools/tests/test_kdb_clean.py` imports `kdb_graph.tests.conftest` factories. Post-extraction, either publish test helpers under `kdb_graph.testing` or duplicate minimal fixtures at the tools boundary. |
| **Operational consumers unlisted** | Low | `cli.py` (`graphdb-kdb`), `rebuilder`, `verifier`, `snapshot` are graph-package operators, not compiler modules. Brief table should include them — they justify F1 "whole package" and inform who runs migrations. |
| **`cypher()` escape hatch** | Medium | `queries.cypher()` exists. Day-one MCP tools are thin adapters — good. Explicitly **exclude** raw Cypher from MCP v1 to prevent unbounded reads and schema-coupled agent prompts. |
| **Claim layer (schema v2.2+)** | Low | Day-one tools cover Entity/Source/LINKS_TO/SUPPORTS. Claim nodes and five claim rels are invisible to MCP — fine if intentional; note in deferred-tools list. |
| **Config discovery** | Low | `default_graph_path()` / `KDB_GRAPH_PATH` and `OBSIDIAN_VAULT_PATH` (for `get_body`) must be threaded through MCP server config with clear precedence docs. |
| **Analytics surface** | Low | `analytics.pagerank` / `communities` are package-owned but not in day-one MCP — aligned with brief; graph-view may want them later without MCP. |
| **Phase B status ambiguity** | Low | Brief reads as greenfield extraction; repo state is post-Phase-B peer package. Clarify "extract" = boundary formalization + MCP assembly, not another `git mv`. |

---

## 4. Timing — "extract now, second-consumer trigger"

**Verdict: RIGHT TIMING for boundary formalization; WRONG if interpreted as another structural move.**

The second consumer (MCP read server) is the correct forcing function for:
- wiring true read-only opens,
- defining the assembly layer (graph + wiki content),
- locking day-one tool surface,
- and optionally a `kdb_graph`-scoped `pyproject.toml`.

It would be **premature** to split to a separate git repo now (F2 lean is correct) or to build FTS/GraphRAG answer tools before primitives prove insufficient (brief correctly defers these).

It would be **late** to defer read-only correctness and Kuzu concurrency semantics — those are prerequisites, not follow-ons.

**Concrete sequencing recommendation:**
1. Fix `GraphDB` read-only open (no DDL on read path).
2. Stand up MCP assembly layer with six thin tools + per-query (or explicit stale) open policy.
3. Add `kdb_graph` package metadata / version contract test.
4. Co-locate graph-viewer under graph-access package tree.
5. Defer separate repo, FTS, GraphRAG answer tool, and `export_graph_view` MCP tool.

---

## Summary verdict

| Question | Answer |
|----------|--------|
| Framing sound? | **Yes** — durable asset + shared contract; compiler stays producer + compose client. |
| F1 | Agree (whole package) |
| F2 | Agree (in-repo first) |
| F3 | Agree (separate stores, MCP assembly) |
| F4 | Agree (co-locate viewer; defer MCP export) |
| F5 | Partial (stdio yes; elevate per-query reopen; fix `read_only` first) |
| Timing | Right for MCP + contracts; structural extract largely done |

**Top three actions before implementation:** (1) implement real read-only `GraphDB` open, (2) codify Kuzu snapshot/reopen policy for MCP, (3) exclude raw `cypher()` from MCP v1 and document schema-version fail-fast.