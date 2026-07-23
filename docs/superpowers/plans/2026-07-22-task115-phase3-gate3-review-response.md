# Task #115 — Phase 3 Gate-3 code review: resolution of Codex findings (round 1 → round 2)

> Response to `docs/superpowers/plans/2026-07-22-task115-phase3-gate3-code-review-codex.md` (verdict: GO-WITH-CHANGES).
> All 4 findings folded into the same uncommitted Gate-3 diff on branch `feat/115-pass2-contract` (base `610ef77`, the Gate-2 commit).
> **Verification after fixes:** full suite **1385 passed / 1 live-skip / 1 deselected** via `.venv/bin/python -m pytest` (pre-review: 1380; +5 new tests, 1 modified).
>
> **For the round-2 reviewer:** re-review the working-tree diff (`git diff HEAD`) with focus on the files cited per finding. Confirm each resolution is correct and complete, and re-run the deterministic suite (`.venv/bin/python -m pytest -q -m 'not bench and not live'`). Write the round-2 verdict to `docs/superpowers/plans/2026-07-22-task115-phase3-gate3-code-review-codex-v2.md`.

---

## F1 [Medium] — viewer exporters no longer return `Entity.confidence`

**What was wrong:** `tools/viewer/kdb_graph_viewer.py` and `tools/viewer/bakeoff/export_graph.py` both copy every non-internal property of `MATCH (n:Entity) RETURN n` into `props`, so the deprecated dead column was exported (legacy value or `null`).

**Resolution:**
- `tools/viewer/kdb_graph_viewer.py` (~line 75): `props.pop("confidence", None)` for `Entity` rows, with a comment citing D-115-12. Static bake-off HTML artifacts remain untouched as ratified.
- `tools/viewer/bakeoff/export_graph.py` (~line 68): same pop + comment in the preserved fallback exporter.

**Tests (2 new, `tools/tests/test_kdb_graph_viewer.py`):** `test_export_omits_deprecated_entity_confidence` and `test_bakeoff_export_omits_deprecated_entity_confidence` — each creates an `Entity` row with `confidence: 'high'` directly via Cypher (the true legacy-populated case), runs the exporter, and asserts the key is absent from every exported Entity node's `props`.

## F3 [Medium] — Gate-3 dump is now genuinely full-graph

**What was wrong:** `gate3_dump.py` normalized only Entity/Source/Domain/LINKS_TO/SUPPORTS/ALIAS_OF/BELONGS_TO — omitting `_SchemaMeta`, `Claim`, `EVIDENCES`, `ABOUT`, `SUPERSEDES`, `CONTRADICTS`, `QUALIFIES` — so the pre/post equality could not detect unexpected Claim-tier rows or property changes (Claim-tier non-interference is an explicit scope guard).

**Resolution (`kdb_graph/tests/gate3_dump.py`):** `dump_normalized` now emits **all 13 sections** — the original seven plus `schema_meta`, `claims` (all nonvolatile properties, INCLUDING the protected computed `confidence`/`confidence_spread` — the comparison must catch any Claim-tier drift), `evidences`, `about`, `supersedes`, `contradicts`, `qualifies`. The corpus leaves the Claim tier empty by design; the encoded empty arrays are precisely the tripwire. Only volatile wall-clock timestamps remain excluded.

**Artifact regeneration — at the Gate-2 HEAD, with Gate-2 production code:** created a throwaway `git worktree` at `610ef77`, copied the untracked dump helper + corpus in, ran `.venv/bin/python -m kdb_graph.tests.gate3_dump` there, copied `pre_confidence_removal_artifact.json` back, removed the worktree. Verified: entity confidence values are the pre-deprecation ones (`summary-legacy=high`, `alpha=low`, `beta/gamma/summary-new=medium`, `alpha-alias=""`), `schema_meta` reports `2.4`, all Claim-tier sections are `[]`. The anti-regeneration guard test (`test_gate3_pre_artifact_is_from_gate2_corpus`) still passes, and both Gate-3 tests pass against the extended artifact.

## F2 [Low] — verifier + MCP deprecation behavior pinned

**Resolution:**
- `kdb_graph/tests/test_verifier.py::test_confidence_only_difference_ignored` — seeds live graph + journal via the normal path, then `SET e.confidence = 'high'` on one Entity (simulating a pre-deprecation live graph), runs `verifier.verify`, asserts `result.ok` and zero confidence-field divergences.
- `kdb_mcp/tests/test_adapters.py::test_entity_card_model_dump_has_no_confidence` — `get_entity` adapter card's `model_dump()` lacks the key.
- `kdb_mcp/tests/test_server.py::test_entity_surfaces_have_no_confidence` (anyio) — asserts the key is absent from `get_entity` structuredContent, every `graph_neighborhood` neighbor, and every `entities_for_source` entity (single-entity, neighborhood, and source-provenance surfaces).

## F4 [Low] — snapshot test now seeds a genuinely populated dead column

**What was wrong:** `test_entities_jsonl_has_no_confidence_key` claimed to prove v7 omits the key "even when the dead column holds values", but `_seed_graph()` routes through the new intake, which ignores the deprecated page key — the column was NULL for every row (verified with a direct query).

**Resolution (`kdb_graph/tests/test_snapshot.py`):** after `_seed_graph`, the test now executes `MATCH (e:Entity) SET e.confidence = 'high'` via Cypher, asserts the precondition (`COUNT` of entities with non-null confidence > 0) from Kuzu, then snapshots and asserts every `entities.jsonl` row lacks the key. The regression proof is now real: a populated dead column does not leak into v7 output.

---

## Suite evidence

- Full suite after all fixes: **1385 passed, 1 skipped (env-gated live smoke), 1 deselected (bench), 39 warnings** in ~62s — `.venv/bin/python -m pytest`.
- Claim-tier protection re-verified after the fixes: `kdb_graph/schema.py`, `core/belief_classifier.py`, o1 eval corpus untouched; Claim snapshot writers still emit both computed-confidence columns (existing content assertion `c1["confidence"] == 0.8` green).
- Scope: changes confined to the F1–F4 resolutions; no Phase-4 / #116 leakage; no production behavior change beyond the two viewer exporters' prop filtering.
