# Panel Review — deepseek-v4-pro (2026-06-10)

## 1. Producer / consumer / durable-asset framing

**Sound.** `kdb_graph` is already a de facto shared contract: 9 non-test files across 4 packages (`compiler`, `orchestrator`, `tools`, `kdb_graph` itself) import it. All of them go through `kdb_graph.queries` (reads) or `kdb_graph.intake` (writes) — the single-door discipline is already enforced in production code (`compiler/kpi/graph.py` line 7: "every graph read goes through kdb_graph.queries"). The package boundary test at `tools/tests/test_package_boundaries.py` already encodes the dependency contract (`compiler` depends on `kdb_graph`; `kdb_graph` may depend on `common`). Extraction names what exists.

The brief's claim of **zero dependency on `common/`** is confirmed: a grep finds no `from common` or `import common` in non-test `kdb_graph/` code. The boundary test allows the import but it's unused — extraction is clean.

There is no reason to keep the access contract coupled to the compiler. The compiler is one of several consumers and the sole producer. Coupling the schema to the producer forces every reader to carry a transitive dependency on compiler code it doesn't need. The current separation is already clean enough to extract mechanically; delaying it only deepens that coupling as more consumers (MCP server) land.

---

## 2. Fork-by-fork

**F1 — Extraction scope: whole package.** **AGREE.** The schema, migrations, types, queries, and intake all need to agree on the schema version. Splitting read-primitives from write-intake across a package boundary means schema changes must be coordinated across two packages instead of one — exactly the drift problem extraction is meant to prevent. The migration chain (`schema.py` MIGRATIONS dict) already treats the DB as a single versioned artifact; splitting it would require the read-side to know what schema version it's reading and the write-side to know what it's writing, with no single `SCHEMA_VERSION` constant to reconcile them. Whole-package extraction keeps `SCHEMA_VERSION` as the single source of truth.

The brief's concern about "drift" is not theoretical: the codebase already shows it in miniature with the 2.3→2.4 migration being destructive (BELONGS_TO changed from editable to derived, requiring `graphdb-kdb rebuild`). If read and write lived in separate packages, a 2.3 reader talking to a 2.4 writer would silently produce wrong BELONGS_TO results.

**F2 — In-repo package first.** **AGREE.** The MCP server is the second consumer; extracting to a separate repo before a third external consumer needs it is premature ceremony. The boundary test already gatekeeps the dependency graph; an in-repo `pyproject.toml` + own namespace + own tests is sufficient to prove the contract.

**Caveat:** test-fixture coupling needs attention during extraction. Currently `compiler/tests/test_context_loader.py` and `compiler/tests/test_kpi_graph.py` import from `kdb_graph` and construct `GraphDB` instances directly in fixtures. If the extracted package gets its own `conftest.py` with `graph_dir` fixtures, compiler tests that need them must either (a) import the extracted package's conftest fixtures (pytest跨-package fixture sharing is fragile), or (b) duplicate minimal fixtures. Neither is hard, but the brief doesn't mention it.

**F3 — `get_body` / content-store separation.** **AGREE.** The graph store (Kuzu) and the content store (wiki/ filesystem) are different storage backends with different access patterns, different failure modes, and different lifecycle. Bundling content-store access into the graph package would give it a dependency on `common/paths.py` (which resolves wiki/ paths) — breaking the zero-dependency property the brief correctly celebrates. The MCP assembly layer joining two thin readers is the right separation; it also means the content-store reader can be reused independently (e.g., by a future search tool that wants bodies without the graph).

**F4 — Graph-view generator placement.** **AGREE** with co-location as a reader output. But note a subtlety: the current viewer (`tools/viewer/kdb_graph_viewer.py`) bypasses `queries.py` entirely — it does raw Cypher table-dumps (`SHOW_TABLES()` → per-table `MATCH` → `nodes()`). This is a different access pattern than the semantic primitives (`neighbors`, `shortest_path`, `entities_for_source`). If the viewer moves into the extracted package, it should use the same `queries.py` primitives rather than raw Cypher — otherwise the "single door" discipline has a hole. The brief's decision to not MCP-ify it yet is correct: the export produces a file artifact with a very different contract (batch HTML generation vs. interactive query-response).

**F5 — stdio MCP, concurrency posture.** **AGREE.** stdio local-first matches the single-user, same-machine reality. The "open-per-query vs. persistent connection" question is correctly deferred: Kuzu's Python bindings create `Database` + `Connection` objects that can be opened read-only, and for a single user who isn't compiling (write-locked) and chatting (read-only) simultaneously, there is no contention. If it bites later, the fix is `open()` + query + `close()` per request, which is trivially correct.

One thing the brief doesn't mention: stdio MCP means the server process must know where the graph DB lives. The `default_graph_path()` in `kdb_graph/__init__.py` resolves `~/Droidoes/GraphDB-KDB`. The MCP server should accept this as a CLI argument or env var rather than baking it in — this is likely obvious but worth stating.

---

## 3. What the brief misses

**Schema versioning across the package boundary.** The brief says the extracted package "owns" the schema, but doesn't address what happens when the package bumps `SCHEMA_VERSION` and the compiler (or MCP server) is still on an older commit. The migration chain in `schema.py` handles forward migration on DB open, but there's no discussion of a compatibility matrix: can a v2.4 reader safely read a v2.3 database? (Yes, because migrations are non-destructive — except the 2.3→2.4 jump, which is destructive per the comment at line 50 of schema.py: "requires `graphdb-kdb rebuild` (no in-place migration).") If the extracted package introduces a new destructive migration, every consumer must rebuild. This needs to be documented as part of the extraction.

**`default_graph_path()` ownership.** The `__init__.py` exports `default_graph_path()` which resolves `~/Droidoes/GraphDB-KDB` or `$KDB_GRAPH_PATH`. This function lives in the graph package but serves CLI consumers. After extraction, the MCP server, compiler, and tools will each need to locate the graph — the package should provide the resolution logic, but the brief should document this as a shared entry point rather than letting each consumer reinvent it.

**Multi-process Kuzu lock semantics.** The brief says "Kuzu is embedded + single-writer... SQLite-like" and "other processes attach read-only." This framing is correct in theory, but the Kuzu Python bindings behavior under concurrent read-only attachment should be verified against the installed version (0.11.x). Specifically: does opening a second `kuzu.Database(path, read_only=True)` while a writer holds the DB handle block, fail, or silently share? And does Kuzu's WAL grow unboundedly when a long-lived read-only connection prevents checkpointing? This isn't a blocker for extraction — it's a testing/verification item for the MCP server implementation.

**CLI ownership (`kdb_graph/cli.py`).** The `graphdb-kdb` entry point currently lives inside `kdb_graph`. If the package is extracted (even in-repo), does the CLI stay with it or move to the compiler/orchestrator? The CLI includes `ingest`, `verify`, `rebuild`, `snapshot`, `stats` — operations that span both read and write. If the CLI stays with the graph package, the package owns its own tooling; if it moves, consumers must bring their own. This is a fork that should be listed (call it F6) or explicitly deferred.

**`kdb_graph/adapters/` layer.** The adapter (`adapters/obsidian_runs.py`) translates the producer's `compile_result.json` format into graph-intake format. If extracted, this adapter becomes a permanent interface contract between producer and graph — it can't evolve independently on either side without coordination. The brief mentions the intake stays in the package (F1), but doesn't discuss the adapter as a versioned interface. This is worth a note: the adapter is where producer/consumer coupling actually lives, and it should be treated as an API with its own backward-compatibility promise.

**Test-fixture coupling (concrete).** As noted under F2, compiler tests that construct `GraphDB` directly (e.g., `compiler/tests/test_context_loader.py`, `compiler/tests/test_kpi_graph.py`) will need their fixtures updated. The brief should call this out so extraction doesn't accidentally break the test suite in ways the author didn't anticipate.

---

## 4. Timing: extract now vs. later

**Extract now is correct.** The MCP server is the second consumer. Building the MCP server on the current import path (`from kdb_graph import GraphDB, queries`) and then extracting later would mean:
1. Writing the MCP server's imports once.
2. Changing them all when the package moves.
3. Updating tests, fixtures, and pyproject.toml dependencies.

That's pure rework. Extracting first means the MCP server lands on the stable boundary and never needs to change its import paths. The extraction is also low-risk: `kdb_graph` already has zero dependency on `common/`, own tests, and a contract enforced by `test_package_boundaries.py`. The cost of delaying is higher than the cost of extracting now.

The "concrete-first" argument would apply if we didn't already know the shape of the second consumer — but we do. The MCP server's read tools (§3.5) map 1:1 onto existing `queries.py` functions. There's no discovery left; the boundary is proven. Extract it, write the MCP server against the extracted package, and the third consumer (if it ever arrives) gets a clean repo-split on a proven boundary.

---

## Verdict summary

| Question | Verdict |
|----------|---------|
| Producer/consumer framing | Sound — confirmed by code inspection |
| F1 (whole package) | AGREE |
| F2 (in-repo package first) | AGREE, with test-fixture callout |
| F3 (separate stores) | AGREE |
| F4 (viewer co-location) | AGREE, note raw-Cypher divergence from queries.py |
| F5 (stdio MCP) | AGREE |
| Missing: schema versioning contract | Needs explicit compatibility documentation |
| Missing: test-fixture coupling | Needs extraction plan |
| Missing: Kuzu concurrent-read verification | Pre-MCP-implementation smoke test |
| Timing | Extract now — proven boundary, low risk |
