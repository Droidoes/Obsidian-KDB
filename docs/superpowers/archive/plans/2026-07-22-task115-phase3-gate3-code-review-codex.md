# Task #115 Phase 3 — Gate-3 Code Review (Codex)

**Reviewed:** 2026-07-22  
**Branch/base:** `feat/115-pass2-contract` at `610ef77` plus the uncommitted Phase-3 diff  
**Scope:** Entity-confidence logical deprecation (D-115-12), snapshot format v7, and the executable Gate-3 pre/post proof

## Verdict: GO-WITH-CHANGES

The core graph, query, MCP, verifier, promotion, and snapshot edits implement the intended Entity-confidence removal without touching Claim-tier confidence. However, one real production reader still returns the deprecated property, and the load-bearing Gate-3 artifact is not actually a full-graph comparison. Fix those before the Gate-3 commit. Two smaller test-contract gaps should be closed in the same pass.

## (a) Inventory completeness & Claim-tier protection

### F1 — The viewer still reads and returns `Entity.confidence`

**[Severity: Medium]** · `tools/viewer/kdb_graph_viewer.py:68` and `tools/viewer/bakeoff/export_graph.py:62` · Both executable viewer exporters use `MATCH (n:Entity) RETURN n` through their all-node-table loops, then copy every non-internal property into `props` (`kdb_graph_viewer.py:73-81`; bake-off fallback `export_graph.py:67-72`). On a legacy-populated graph, the official viewer currently emits `{"confidence": "high"}`; even a new graph emits the dead column as `null`. This violates D-115-12's stop-querying/stop-returning contract and the blueprint's required viewer/CLI consumer sweep. The static bake-off HTML artifacts can remain untouched, but the two executable exporters are readers, not static artifacts. **Suggested change:** for `Entity` rows, omit `confidence` from `props` (preferably via an explicit Entity projection, or at minimum `props.pop("confidence", None)`), do the same in the executable bake-off fallback, and add an export test seeded with a non-null legacy value that asserts the key is absent.

### F2 — Verifier and MCP deprecation behavior is not explicitly pinned

**[Severity: Low]** · `kdb_graph/tests/test_verifier.py:139` and `kdb_mcp/tests/test_server.py:49` · The production edits are correct, but the ratified validation matrix calls for logical-deprecation tests across intake, verifier, snapshot, and MCP. The verifier suite tests a `page_type` mismatch but never proves a confidence-only difference is ignored; the MCP round-trip asserts only `slug` and `title`, so it would not catch the deprecated field reappearing in the public response. The Gate-3 rebuild test covers intake/alias null writes, not these two outward contracts. **Suggested change:** seed a live graph with legacy non-null Entity confidence and assert replay verification has no confidence divergence; assert `confidence` is absent from adapter `model_dump()` and MCP `structuredContent` for both single-entity and neighborhood/source-provenance surfaces.

Claim-tier protection itself is clean: `kdb_graph/schema.py`, `kdb_graph/core/belief_classifier.py`, and the O1 scenario corpus are byte-identical to Gate 2. The only `op_1_promote.py` change removes the Entity write; its Claim `confidence`/`confidence_spread` writes remain unchanged. The Claim snapshot writer still emits both computed-confidence columns and its existing content assertion passes.

## (b) Gate-3 pre/post comparison soundness

### F3 — The “full-graph” dump omits the Claim subgraph and schema metadata

**[Severity: Medium]** · `kdb_graph/tests/gate3_dump.py:50` and `kdb_graph/tests/gate3_dump.py:124` · The helper says it compares every node, edge, and nonvolatile property, but the returned artifact includes only Entity, Source, Domain, LINKS_TO, SUPPORTS, ALIAS_OF, and BELONGS_TO. It entirely omits `_SchemaMeta`, `Claim`, `EVIDENCES`, `ABOUT`, `SUPERSEDES`, `CONTRADICTS`, and `QUALIFIES`. Consequently, the Gate-3 equality at `test_gate3_confidence_deprecation.py:56` cannot detect unexpected rows or property changes in those tables, even though Claim-tier non-interference is an explicit scope guard. The current corpus is expected to leave the Claim tables empty, but encoding those empty sections is precisely what would catch accidental creation. **Suggested change:** normalize every schema table and every nonvolatile property, including empty Claim-tier arrays and `_SchemaMeta`; regenerate/extend the pinned Gate-2 artifact using Gate-2 production code; retain the anti-regeneration confidence guard. The existing corpus already does a good job exercising the legacy/new split, alias page type/status/canonical target, `SUPPORTS.hash_at_time`, `BELONGS_TO.support_count`, legacy stored link lists, and new body-derived links.

## (c) Snapshot v7 & dead-column safety

### F4 — The snapshot test does not actually seed a populated dead column

**[Severity: Low]** · `kdb_graph/tests/test_snapshot.py:565` · The test claims to prove that v7 omits the key even when the Kuzu column contains legacy values, but `_seed_graph()` routes its historical page keys through the new intake, which deliberately ignores them. A direct query immediately before snapshot returns `None` for both seeded entities. The writer is correctly implemented today, but the stated regression proof is weaker than the Gate-3 requirement. **Suggested change:** directly set/seed `Entity.confidence` to a non-null legacy value after intake, assert that precondition from Kuzu, then snapshot and assert the JSONL key is absent.

No production snapshot defect was found: `SNAPSHOT_FORMAT_VERSION == 7`, the history comment identifies the first non-additive bump and no-v6-loader policy, `_write_entities` omits the column, manifest/latest-pointer paths consume the v7 constant, and Claim snapshot confidence remains intact.

## (d) Read-compat & scope

None.

The legacy Gate-3 journal rebuilds successfully and its deprecated `confidence`, `summary_slug`, and `outgoing_links` keys are ignored/consumed in the intended legacy paths; the new journal derives links from body wikilinks. The aggregate schema still retains removed fields as optional, deprecated, read-only properties, and the existing mixed-mode validator/rebuilder tests pass. The new Gate-3 sidecars use a deliberately minimal synthetic `compile_meta`, so they are rebuild fixtures rather than standalone `kdb-validate` fixtures; D-115-14's validator proof remains in the existing fixture-backed tests. No Phase-4 parity corpus, #116 lifecycle machinery, physical Kuzu-column removal, compiler changes, or other scope leakage is present. `tools/diagnostics/dump_run_passes.py` remains correctly scoped to Pass-1 source confidence.

## Verification performed

- Focused Gate-3 + snapshot tests: **23 passed**.
- Broader focused graph/MCP/viewer/promotion regression bundle: green.
- Package-boundary guard: **9 passed**.
- Deterministic suite (`-m 'not bench and not live'`): **1379 passed, 1 environment-gated skip, 2 deselected** (1380 selected; exit 0).
- Default suite additionally selected the DeepSeek live smoke because this environment exposes `DEEPSEEK_API_KEY`; that one external call failed with `Connection error` under sandboxed network access. This is not a Gate-3 regression and was excluded from the deterministic result above.
- `git diff --check HEAD`: clean.
- Manual probes confirmed both F1 (official viewer returned legacy `confidence: high`) and F4 (the snapshot test's seeded graph held only `NULL` confidence values).

## Bottom line

The central deprecation implementation is mechanically sound and Claim confidence is protected, but the diff is not ready to commit as Gate 3: the official/fallback viewer exporters still expose the deprecated Entity property, and the advertised full-graph pre/post proof omits the complete Claim tier and schema metadata. Close F1 and F3, add the focused contract assertions in F2/F4, rerun the deterministic suite, and the phase should be safe to commit.
