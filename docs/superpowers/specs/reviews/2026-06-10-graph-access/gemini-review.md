# Design Review — Graph-Access Package + MCP Server

**Reviewer:** Gemini (independent panel)
**Brief:** `docs/superpowers/specs/2026-06-10-graph-access-package-design.md`
**Date:** 2026-06-10

---

## 1. Producer / consumer / durable-asset framing

**Verdict: SOUND — Bounding the GraphDB as a shared, durable asset is the correct architectural direction, and compiler-specific context composition must remain in the compiler.**

The framing is operationally and theoretically correct. The compilation pipeline is a producer that updates the GraphDB, while many other components—including the compiler's own Pass-2 context loader, the KPI suite, the cleanup tools, and the proposed MCP server—are consumers. Coupling the access interface (`kdb_graph/`) to the compiler repository creates unnecessary dependency friction for non-compiler consumers. Extracting the access contract ensures that compiler-specific heuristics (e.g., T1/T2/T3 logic, page-cap heuristics, and PageRank tie-breakers) do not pollute the core database interface. Non-compiler readers can query the clean core API directly without pulling in compilation-specific logic.

---

## 2. Open forks F1–F5

### F1 — Extraction scope (whole `kdb_graph` vs read-subset)

**AGREE.**

Splitting read and write paths into separate packages introduces significant schema drift risks and doubles the maintenance surface. The schema is the unified source of truth for the database; therefore, table definitions, migrations, and basic read/write operations must belong to a single package boundary. Since `kdb_graph/` currently has zero dependencies on `common/` and is fully self-contained, there is no technical untangling penalty to extracting the package in its entirety.

### F2 — Packaging / repo boundary (in-repo package first vs separate repo now)

**AGREE.**

An in-repo package (with its own namespace, tests, and configuration) achieves the necessary logical boundary without the friction of multi-repo maintenance. It avoids the overhead of managing separate Git repositories, credentials, CI/CD pipelines, and synchronized dependency versions. Proving the package boundary with the MCP server as a second consumer is sufficient; a physical repository split should only be triggered if a third consumer outside the monorepo context requires independent integration.

### F3 — `get_body` / content-store ownership

**AGREE.**

The three-store architecture (GraphDB, wiki content store, and file manifest) must remain decoupled. Storing body content in the GraphDB violates the thin-node decision, and pulling wiki filesystem access into the graph package would couple it to vault paths and Markdown parsing dependencies. The graph-access package should only return node metadata, while a thin content accessor handles the filesystem reads. The MCP server serves as the assembly layer that coordinates both stores to construct complete responses.

### F4 — Graph-view generator placement

**AGREE.**

The graph-view generator (`tools/viewer/kdb_graph_viewer.py`) is a pure reader of the GraphDB. Co-locating it with the graph-access package makes the suite of reader outputs explicit. Deferring the MCP tool for exporting graph views is correct because the generator produces interactive HTML files, which are unfit for direct injection into a chat model's message-based context.

### F5 — MCP transport + concurrency posture

**PARTIALLY AGREE — Transport stdio is correct, but the concurrency posture is underestimated.**

While stdio is the correct choice for a local, single-user developer workflow, the brief treats concurrency too lightly. Because Kuzu is an embedded in-process database, a long-lived database connection is pinned to the snapshot state at open time. If the MCP server maintains a persistent connection, it will not see any compiler updates until the connection is recycled. Thus, a **reopen-on-query** connection policy is a functional requirement, not a performance fallback. Additionally, to avoid file lock contention, read-only consumers must open Kuzu with `read_only=True`—a capability currently blocked by the implementation's handling of `read_only` flags.

---

## 3. Gaps — consumers, failure modes, risks

| Gap | Severity | Analysis & Recommendation |
|:---|:---|:---|
| **Inactive `read_only` parameter** | **Blocker** | In `GraphDB._open`, Kuzu's `Database` constructor is called without `read_only=self._read_only`. This causes read-only readers to attempt to acquire write locks. Bypassing schema checks and passing `read_only=True` to Kuzu is a hard prerequisite for concurrent read-only access. |
| **DDL execute on read-only open** | **Blocker** | `GraphDB._open` currently calls `_ensure_schema()`, which runs DDL statements (`CREATE TABLE`, etc.). A Kuzu instance opened in read-only mode will crash when executing DDL. Bypassing `_ensure_schema` on read-only opens is mandatory. |
| **Kuzu snapshot pinning** | High | Since Kuzu does not automatically refresh read-only snapshots when writes commit, the MCP server must discard and reopen the connection per query, or implement a version-based invalidation mechanism. |
| **Schema migration responsibility** | Medium | With multiple packages pointing to the same Kuzu database directory, only the writer (compiler/orchestrator or the `graphdb-kdb` CLI tool) should perform migrations. The MCP server must only inspect `_SchemaMeta` and fail-fast if it detects a schema version mismatch. |
| **Unrestricted Cypher execution** | Medium | Exposing a raw `cypher` tool via the MCP server violates safety boundaries and tightly couples agent prompts to internal schema layouts. Exclude raw Cypher from the day-one MCP toolset. |
| **Multi-writer contention** | Medium | The brief assumes the orchestrator is the only writer. However, `tools/cleanup.py` executes retract operations (`apply_cleanup`). The system must define lock-acquisition timeouts or error-handling when two processes attempt to write concurrently. |
| **Test fixture coupling** | Low | Post-extraction, test suites in `tools/tests/` that import `kdb_graph.tests.conftest` will cross package boundaries. Test helpers and database fixtures should be clearly exposed under a shared testing utility inside the `kdb_graph` package. |

---

## 4. Timing — "extract now, second-consumer timing"

**Verdict: RIGHT TIMING — Extracting the package interface now is correct to prevent compiler coupling, but it should not be a physical repository split.**

The second consumer (the MCP server) is the correct trigger to formalize the package boundary in-repo. Doing so forces the system to solve the read-only concurrency, connection lifecycle, and schema mismatch challenges immediately. Delaying this extraction would result in compiler dependencies leaking into the MCP server or duplicating database access code. However, moving the code to a separate repository at this stage would be premature and introduce unnecessary release and version management overhead.

---

## Summary verdict

| Aspect | Verdict | Key Architectural Rationale |
|:---|:---|:---|
| **Framing sound?** | **YES** | The GraphDB is a shared, durable asset. Compiler-specific T1/T2/T3 composition must remain in the compiler, while access primitives live in the graph package. |
| **F1: Scope** | **AGREE** | Schema and read/write contract must stay unified in one package to prevent drift. |
| **F2: Packaging** | **AGREE** | An in-repo package is sufficient. Defer physical repo separation. |
| **F3: Content-store** | **AGREE** | Decoupling GraphDB from wiki filesystem operations maintains a clean metadata layer. |
| **F4: Viewer placement** | **AGREE** | Viewer is a graph reader; co-locating it with the package is logical. |
| **F5: Concurrency** | **DISAGREE (Lean)**| Concurrency is a blocker. Reopen-per-query is required to prevent stale snapshot reads, and `read_only` handles must be fixed. |
| **Timing** | **RIGHT** | Formalize the package boundary in-repo now to support the MCP server deployment. |
