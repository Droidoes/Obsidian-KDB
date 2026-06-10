# Verdict

GO WITH FIXES. The producer/consumer/durable-asset framing is sound, and the access contract should not remain coupled to the compiler. The code already supports that direction: `compiler/context_loader.py` composes graph primitives from `kdb_graph.queries`, while `kdb_graph` production code has an existing no-producer-import invariant. The second consumer timing is also legitimate: an MCP reader is a materially different access path from Pass-2 context loading, not just another compiler helper.

The brief should not proceed unchanged. It understates three boundary risks: the current `GraphDB(read_only=True)` flag is not applied to `kuzu.Database`, the "whole package" extraction includes Obsidian-run adapter/rebuild semantics that are producer-shaped, and the first MCP body tool crosses from graph access into content-store access without a defined content package contract.

# Load-Bearing Findings

1. `read_only=True` is currently a no-op in `kdb_graph/graphdb.py`. `GraphDB.__init__` stores `_read_only`, but `_open()` calls `kuzu.Database(str(self._graph_dir))` without passing `read_only=self._read_only`. Local Kuzu 0.11.3 exposes `kuzu.Database(..., read_only: bool = False)`, so this is not just a documentation gap. Any MCP design that relies on read-only attach must first make the wrapper actually open read-only and add a regression test that write methods fail or are blocked when `_read_only` is true.

2. F1's "whole package" lean is directionally correct for schema/read/write consistency, but too coarse as written. `kdb_graph` contains the generic graph core, but it also contains `adapters/obsidian_runs.py`, `rebuilder.py` replay semantics, CLI commands, snapshot/verifier surfaces, and tests that know about producer run-journal shape. Those can live in the extracted repo/package, but the brief should name them as adapter/plugin surfaces, not imply the entire tree is equally producer-neutral.

3. `get_body` is the first cross-store operation and deserves a contract before it becomes an MCP primitive. Bodies live in wiki files and paths are currently compiler/common-owned. If the graph-access package stays pure, the MCP assembly layer needs a small content accessor with explicit path root, slug-to-path policy, page-type routing, missing-body behavior, and stale graph-to-wiki mismatch behavior. Without that, the MCP layer quietly re-couples graph access to compiler path utilities.

4. Schema/package versioning is under-specified. `SCHEMA_VERSION` and `MIGRATIONS` live in `kdb_graph.schema`; once MCP or viewer are installable clients, they need a predictable compatibility contract: supported schema range, error shape for newer/older graph stores, and a "read-only clients never migrate" rule. Today `GraphDB._ensure_schema()` runs migrations on open, which is wrong for an MCP read-only process unless guarded.

# Fork Recommendations

F1 - AGREE WITH QUALIFICATION: extract the whole contract, not a read subset. Schema, migrations, write intake, read queries, verifier/snapshot, and analytics need one owner. But split the extracted package internally into `core` (schema, connection, types, queries), `writers` or `intake`, `adapters/obsidian`, and `ops/cli`. That preserves one package while preventing the Obsidian adapter from masquerading as generic core.

F2 - AGREE: in-repo clean package first. A separate repo now adds release/version overhead before the API has real usage. Make it separable in place: own package namespace, package-data, tests, public API, boundary tests, and no imports from compiler/common except through explicitly approved adapter or content-access packages. Split physically only after an external third consumer or after MCP stabilizes.

F3 - AGREE: keep stores separate. The graph package should not own wiki body reads. Add a separate content-store reader package/module and let MCP join graph results to body text in an assembly layer. The key is not just purity; it avoids dragging compiler path and vault assumptions into a graph package that should remain reusable for future producers.

F4 - AGREE, but defer the move until F2 structure exists. The viewer is a clean reader and belongs near the query-core eventually. Do not MCP-ify it now. First extract a reusable graph export function that returns neutral JSON; the CLI/file-writing HTML renderer can remain an output adapter.

F5 - AGREE WITH MUST-FIX: stdio local-first is right. Open-per-query is safer than a persistent read connection until Kuzu multi-process behavior is empirically verified on the installed version and workload. But the read-only wrapper bug must be fixed first, and read-only MCP must refuse startup or degrade cleanly if the compiler holds a write lock.

# Missing Risks / Consumers

- Read-only clients must not run migrations. Current open path always calls `_ensure_schema()`, which can mutate. A read-only `GraphDB` should verify schema only and fail with a structured incompatible-schema error.
- Write methods on a read-only `GraphDB` should be blocked at the wrapper boundary, not merely left to Kuzu to fail. That includes `apply_compile_result`, `apply_cleanup`, `detect_orphans`, and `wire_links`.
- The package boundary must define public dataclass/JSON response shapes for MCP. Returning raw dataclasses directly is fine in-process, but MCP needs stable serialized shapes and error envelopes.
- Alias/canonical resolution should be a first-class MCP behavior, not an incidental tool. Most interactive users will ask for surface names, aliases, or titles, not exact slugs.
- The brief omits claim-layer consumers. `Claim` tables already exist in schema v2.2. Even if day-one MCP skips Claim tools, extraction should not make Entity-only assumptions that block later `claims_about(slug)` / evidence retrieval.
- Test fixtures are a real coupling surface. `kdb_graph/tests` currently provide useful graph factories used by other packages. If packaging is separated, fixture ownership should be explicit: either exported test utilities or duplicated local fixtures.
- The default graph path belongs in configuration policy, not core logic long-term. `default_graph_path()` currently bakes in `~/Droidoes/GraphDB-KDB`; acceptable for in-repo phase, but an installable package should accept explicit paths and let applications own defaults.
- Raw Cypher escape hatches should not be exposed through MCP day one. They are useful for local CLI diagnostics, but an agent-facing protocol should expose bounded read tools only.

# Timing Recommendation

Extract now, but do it as an in-repo package boundary with a narrow milestone, not a repo split. The trigger is real: the compiler, viewer/KPI readers, and planned MCP server are distinct consumers of the same durable graph asset. Keeping the contract embedded inside compiler mental-model territory will compound confusion.

The first milestone should be "make the boundary true" rather than "build all MCP features":

1. Fix and test real read-only open semantics.
2. Split read-only schema verification from migration-on-write open.
3. Define the public query/result/error shapes for in-process and MCP consumers.
4. Add the content-store reader as a separate contract before `get_body`.
5. Move or wrap the viewer only after the graph package has a stable export API.
6. Ship a minimal MCP stdio server with bounded read tools: `get_entity`, `graph_neighborhood`, `find_path`, `entities_for_source`, `sources_for_entity`, and `resolve_search_keys`. Add `get_body` only once the content accessor exists.

Do not build FTS or assembled GraphRAG answers yet. The brief is right to let usage pull those in later.
