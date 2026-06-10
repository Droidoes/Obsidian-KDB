# Design Review — Graph-Access Package + MCP Server

**Reviewer:** Qwen Code (independent panel)
**Brief:** `docs/superpowers/specs/2026-06-10-graph-access-package-design.md`
**Date:** 2026-06-10

---

## 1. Producer / Consumer / Durable-Asset Framing

**Verdict: SOUND in principle; INCOMPLETE in inventory.**

The reframing is architecturally correct. The graph *is* a durable asset; the compiler *is* one producer; the access contract *should* be shared. The zero-dependency finding (`kdb_graph/` has no imports from `common/`, `compiler/`, or `ingestion/`) is verified — 172 import statements checked, all resolve to stdlib, third-party (`kuzu`, `networkx`, `community`), or internal `kdb_graph.*`. The dependency arrow genuinely points inward.

**However, the consumer table in §2 is materially incomplete.** Verified consumers the brief omits:

| Consumer | R/W | Significance |
|----------|-----|-------------|
| `orchestrator/emit_kpis.py` | Read (convention) | Opens `GraphDB(read_only=True)` — flag is dead, gets silent RW handle |
| `tools/diagnostics/validate_domain_backfill.py` | **Write** | Calls `apply_compile_result` on a temp GraphDB — third write path after orchestrator and cleanup |
| `tools/viewer/bakeoff/export_graph.py` | Read (convention) | Second viewer, also uses dead `read_only=True` |
| `kdb_graph/cli.py` (15 subcommands) | Read + Write | `graphdb-kdb` CLI is a significant operational consumer — `init`, `verify`, `rebuild` are admin-grade operations |
| `kdb_graph/verifier.py` (723 lines) | Read + Write (temp) | Layer-2 replay creates a temp DB and diffs against live |
| `kdb_graph/rebuilder.py` | **Write** | Drop-and-replay is the most destructive operation in the system |
| `kdb_graph/snapshot.py` | Read | JSONL export with atomic writes and checksums |
| `kdb_graph/core/belief_classifier.py` | Pure compute | Stateless classifier for O1 Promotion Pipeline (Tasks #83–#86) |
| `kdb_graph/ops/op_1_promote.py` | **Write** | O1 Promotion Pipeline — creates Claim nodes, mutates graph topology |

The last two are particularly important: **`core/` and `ops/` are active write-path code for the belief-revision system** (Tasks #83–#86, currently being designed). They define their own type system (`CandidateEnvelope`, `ClassificationResult`, `PromotionAudit`, `DoxasticFingerprint`) and write Claim-layer mutations. The brief's §2 table lists six consumers and calls the inventory complete; it actually has at least fifteen, and the active belief-revision write path is the most architecturally significant omission.

**Implication for framing:** The framing is sound, but the brief undercounts the package's surface area by roughly half. Extraction scope (F1) must account for `core/`, `ops/`, `verifier`, `rebuilder`, `snapshot`, and the full CLI — not just `queries.py` + `intake.py`.

---

## 2. Open Forks F1–F5

### F1 — Extraction Scope

**AGREE with lean (whole package), but the scope is larger than the brief acknowledges.**

The reasoning is correct: schema, migrations, intake, and read primitives are one contract. Splitting creates drift. Verified: `kdb_graph/` is already a peer top-level package (post-Phase-B) with 14 test modules, own CLI, own adapter protocol.

**Addendum the brief misses:** The `core/` and `ops/` subdirectories (belief classifier + O1 promotion pipeline) are *already inside* `kdb_graph/`. They write Claim-layer mutations via the same schema. If extraction scope means "the whole package," these come along — and their type system (`CandidateEnvelope`, `Evidence`, `DoxasticFingerprint`, `AnalysisTimeClassification`) becomes part of the package's public API. This is fine (they're graph-schema-aware), but the brief should name them explicitly so reviewers and implementers know what "whole package" actually includes.

### F2 — Packaging / Repo Boundary

**AGREE.**

In-repo clean package first is the right sequencing. Phase B already did the structural move (`graphdb_kdb` → `kdb_graph`). Formalizing with a dedicated `pyproject.toml` workspace member when MCP lands is the right incremental step. Separate repo on the third external consumer.

**One concrete addition:** The package should publish a `kdb_graph.testing` module (or `kdb_graph[test]` extra). Currently, `tools/tests/test_kdb_clean.py` and `tools/tests/test_kdb_clean_graphdb.py` import directly from `kdb_graph.tests.conftest`. Post-extraction, cross-package test-factory imports become a boundary violation. Publishing test helpers is low-cost and prevents fixture drift.

### F3 — `get_body` / Content-Store Ownership

**AGREE.**

Graph package owns the graph; content-store accessor owns wiki/; MCP assembly layer joins them. The three-store model is load-bearing and should not be collapsed.

**Nuance on the content accessor:** `get_body` requires `page_type` from the graph (to resolve subdirectory: `wiki/concepts/slug.md` vs `wiki/sources/slug.md`) plus vault-path resolution (`KDB_VAULT_PATH` env or convention). The thin content accessor should:
1. Accept `slug` + `page_type` as inputs (not re-query the graph internally — that creates a hidden coupling back to the graph package).
2. Resolve path via a pure function (`slug_to_wiki_path(slug, page_type, vault_root)`).
3. Read the file.

The MCP assembly layer calls `get_entity(slug)` → extracts `page_type` → calls content accessor with both. This keeps the stores independently testable.

### F4 — Graph-View Generator Placement

**AGREE with lean; one refinement.**

Co-locate with the package; defer MCP export. The viewer is a pure reader output.

**Refinement:** The current viewer (`tools/viewer/kdb_graph_viewer.py`) issues raw schema-introspective Cypher (`CALL show_tables()`, dynamic `MATCH (n:\`{tbl}\`)`) rather than `queries.py` primitives. This is intentional (it needs *everything*, not a tuned subset), but it means the viewer is coupled to Kuzu's introspection API, not the graph package's query contract. Co-location is the right moment to decide: does the package export a `full_subgraph()` query primitive, or does the viewer stay as a schema-introspective special case? Either is defensible; the decision should be explicit.

### F5 — MCP Transport + Concurrency

**AGREE on transport (stdio local-first). PARTIALLY DISAGREE on concurrency posture — it is understated.**

The brief says: *"Concurrency is a non-blocker for a single user who isn't compiling and chatting in the same instant."* This is pragmatically true today but architecturally misleading for two reasons:

1. **Kuzu snapshot-pinning.** A read-only `Database` handle is snapshot-pinned at open time and does not see later commits until reopened. If the MCP server holds a persistent read connection while the orchestrator compiles, the MCP server returns stale data silently. The brief's "open-per-query or back off" is the right answer but should be a **required policy**, not an optional future consideration. Every MCP tool invocation should open-fresh or explicitly stamp its response with `graph_opened_at` so consumers can detect staleness.

2. **The `read_only` flag is dead.** `GraphDB.__init__` accepts `read_only=True` and stores it as `self._read_only`, but `_open()` ignores it entirely — always calls `kuzu.Database(path)` (read-write) and always runs `_ensure_schema()` (which can execute DDL migrations). Every current caller passing `read_only=True` (viewer, emit_kpis, bakeoff viewer) silently gets a read-write handle. **This is a hard prerequisite blocker for the MCP server.** "Read-only by construction" is currently false. Fix: pass `read_only=True` to `kuzu.Database()` and skip `_ensure_schema()` when read-only.

The brief treats concurrency as a non-issue by appeal to single-user workflow. The real issue is not concurrent writers — it is **stale reads and silent write-capability on allegedly read-only handles**. Both are correctness problems, not scale problems.

---

## 3. What the Brief Misses

### 3.1 The `read_only` Flag Is a Dead Parameter (Blocker)

Documented above and flagged independently by Grok. Elevating to blocker status because the entire MCP safety model ("read-only by construction") depends on it. The fix is ~10 lines in `graphdb.py` but must precede any MCP work.

### 3.2 Migration-on-Read Failure Mode

Schema version is at 2.4. Migration 2.3→2.4 is **destructive** (Kuzu cannot ALTER a REL table; requires `graphdb-kdb rebuild`). The brief assumes migration happens during compile (writer path). But post-extraction, what happens when:
- The MCP server opens read-only against a schema-2.3 database?
- It cannot migrate (read-only). It cannot serve (schema mismatch).

**Required policy:** Read-only open must check stored schema version vs package `SCHEMA_VERSION` and fail fast with an actionable message: *"Graph schema is v2.3, package expects v2.4. Run `graphdb-kdb rebuild` or `pip install kdb-graph==<matching-version>`."* The brief should specify who owns migration triggering (the writer, always) and what readers do on mismatch (fail, never auto-migrate).

### 3.3 Test-Fixture Coupling Across the Boundary

`tools/tests/test_kdb_clean.py` (line ~5) and `tools/tests/test_kdb_clean_graphdb.py` import from `kdb_graph.tests.conftest`:

```python
from kdb_graph.tests.conftest import ...
```

Post-extraction, this becomes a cross-package test dependency. Two options:
- **Publish test helpers:** `kdb_graph` ships a `kdb_graph.testing` module with graph-fixture factories.
- **Duplicate fixtures:** `tools/tests/` maintains its own minimal fixtures.

The brief does not mention this. It is low-severity but will cause immediate test breakage on extraction day if unaddressed.

### 3.4 Producer-Adapter Boundary

`kdb_graph/adapters/obsidian_runs.py` is tightly coupled to Obsidian-KDB's run-journal layout (journal versions 2.0/2.1/2.2, sidecar archive paths, compile vs cleanup event routing). The adapter protocol (`ProducerAdapter`) is generic, but the sole implementation is producer-specific.

The brief should state explicitly: **the adapter protocol is the package's extension point for additional producers.** The Obsidian-KDB adapter ships with the package as the reference implementation. If a second producer appears, it implements `ProducerAdapter` without modifying the package core. This is implicit in the current design but not stated — and it affects how the package's public API is documented.

### 3.5 O1 Promotion Pipeline as Active Write-Path

`kdb_graph/ops/op_1_promote.py` and `kdb_graph/core/belief_classifier.py` are not speculative — they are the active Tasks #83–#86 implementation. The promotion pipeline writes Claim nodes and five claim-layer relations (EVIDENCES, ABOUT, SUPERSEDES, CONTRADICTS, QUALIFIES) directly to the graph. This is a second write-path inside the package (alongside `intake.py`), with its own type system and its own correctness invariants (doxastic fingerprint, counterpart detection, disposition matrix).

The brief's extraction scope discussion should explicitly include these modules and acknowledge that the package's write surface is `intake.py` + `ops/` + `rebuilder.py`, not just `intake.py`.

### 3.6 CLI Ownership Post-Extraction

`kdb_graph/cli.py` provides 15 subcommands (`init`, `stats`, `neighbors`, `verify`, `rebuild`, etc.). These are operational/admin tools, not compile-pipeline tools. The brief does not address whether the CLI entry point (`graphdb-kdb`) ships with the extracted package or stays in the compiler repo's console_scripts.

**Recommendation:** The CLI ships with the package. It is pure graph-administration; none of its subcommands are compiler-specific. The package's `pyproject.toml` should declare `graphdb-kdb` as its own console_script.

### 3.7 `cypher()` Escape Hatch in MCP Context

`queries.cypher(conn, query, params)` is an ad-hoc Cypher execution function. It is useful for development and debugging but dangerous in an MCP context (unbounded reads, schema-coupled prompts, potential for accidental writes if `read_only` is not enforced).

**Recommendation:** Exclude `cypher()` from MCP v1 tool surface. Document it in a "deferred/excluded tools" section. If an escape hatch is needed later, add it as an opt-in admin-only tool with explicit confirmation.

### 3.8 Schema Version as Package Contract

The package's `SCHEMA_VERSION` (currently "2.4") is the single most important compatibility boundary. The brief should specify:
- The package version and schema version are **independently versioned** (package can release without schema change).
- Every consumer (MCP, CLI, compiler) must check schema version at startup.
- Schema version changes are breaking changes for all consumers — they require coordinated upgrade.

This is not a "nice to have" — it is the contract that makes extraction safe.

---

## 4. Timing — "Extract Now, Second-Consumer Trigger"

**Verdict: RIGHT timing for boundary formalization; the extraction is largely structural, not physical.**

The second consumer (MCP read server) is the correct forcing function. The Phase-B move already put `kdb_graph/` at the top level with its own tests and CLI. What remains is:
1. Wiring real read-only opens (prerequisite).
2. Defining the assembly layer.
3. Publishing test helpers.
4. Adding package metadata (`pyproject.toml` workspace member).

None of this requires a separate git repo. The brief's "extract now" language slightly overstates the work — it is closer to **"formalize the boundary that Phase B structurally created"** than to a greenfield extraction.

**What would make it premature:** If the MCP server has no concrete consumer in the next 30 days. The "Gate" from `kdb-storage-architecture.md` still applies: name one concrete question the MCP server answers. The brief references the 06-09 session's reframing ("context_loader already passes the Gate") but does not name the interactive query that justifies the MCP server itself. Without a named query, the MCP server risks being elegant infrastructure with no load-bearing user — the exact risk the Gate was designed to prevent.

**Recommended sequencing:**
1. Fix `read_only` flag in `GraphDB._open()` (10 lines, prerequisite).
2. Name one concrete interactive query the MCP server will answer (the Gate for the MCP).
3. Add schema-version fail-fast check to read-only opens.
4. Stand up MCP assembly layer with six thin tools + per-query open policy.
5. Publish `kdb_graph.testing` test helpers.
6. Add `kdb_graph` workspace member `pyproject.toml`.
7. Co-locate viewer under package tree.
8. Defer: separate repo, FTS, GraphRAG answer tool, `export_graph_view` MCP tool.

---

## Summary

| Question | Verdict |
|----------|---------|
| Framing sound? | **Yes** — but consumer inventory is incomplete by ~9 entries including active write-paths |
| F1 (scope) | Agree — whole package; scope larger than brief states (include `core/`, `ops/`, `verifier`, `rebuilder`, `snapshot`, CLI) |
| F2 (boundary) | Agree — in-repo first; add `kdb_graph.testing` module |
| F3 (content-store) | Agree — separate stores, assembly-layer join; content accessor takes `page_type` as input |
| F4 (viewer) | Agree — co-locate; decide on `full_subgraph()` primitive vs schema-introspective special case |
| F5 (transport/concurrency) | Partially agree — stdio yes; concurrency is understated (snapshot-pinning + dead `read_only` flag) |
| Timing | Right for formalization; name the MCP's Gate query first |

**Three prerequisites before implementation:**
1. Fix `GraphDB._open()` to honor `read_only=True` (skip DDL, pass to `kuzu.Database()`).
2. Add schema-version check on read-only open with actionable failure message.
3. Name the concrete interactive query that justifies the MCP server (pass the Gate).
