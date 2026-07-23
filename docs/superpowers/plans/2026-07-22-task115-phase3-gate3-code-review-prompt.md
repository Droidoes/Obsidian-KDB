# Task #115 — Phase 3 (confidence deprecation + snapshot v7) — Gate-3 CODE Review Prompt (Codex)

> Sent **verbatim** to Codex CLI. Repo root: `/home/ftu/Droidoes/Obsidian-KDB`, branch `feat/115-pass2-contract`, base commit `610ef77` (Gate 2). The change under review is the **uncommitted working-tree diff** on top of `610ef77` — 11 modified files (+67/−34) plus 3 new paths. Write your review to `docs/superpowers/plans/2026-07-22-task115-phase3-gate3-code-review-codex.md`.

---

You are a senior staff engineer doing a **pre-commit CODE review** at a phase gate. The design is ratified; Phases 1–2 (the Pass-2 contract revision) are already reviewed and committed at Gate 2. Your job: verify the **Phase-3 implementation** — the Entity-confidence logical deprecation (D-115-12) + snapshot format v7 (Task 3.2) — matches the design, is complete, and has no regressions or scope creep. Be skeptical and specific; cite `file:line`.

## HARD GUARDRAIL — read first, non-negotiable
- **Read-only.** Do NOT modify, create, rename, or delete ANY file **except** the single output file named above. Write your entire review there and nowhere else.
- No state-changing git (`add`/`commit`/`checkout`/etc.), no `pip install`, no formatters.
- You MAY run tests: `.venv/bin/python -m pytest` (use the venv python — bare `pytest` resolves to a broken system install). Full suite currently claimed green: **1380 passed / 1 live-skip / 1 deselected**.

## Ground truth (ratified design — the diff must match THIS)
- Spec v1.6, **D-115-12** and **D-115-14**: `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md` (§D-115-12: stop accepting/writing/querying/verifying/snapshotting/returning Entity confidence; the dead Kuzu column stays; Claim tier untouched. §D-115-14: read-compat = journal rebuild + `kdb-validate`, optional-deprecated fields).
- Blueprint v1.10, **Phase 3** (Tasks 3.1–3.2 + Gate 3): `docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md` §329–358. Task 3.1 enumerates the exact write/read inventory; Task 3.2 is the snapshot bump; Gate 3 requires the executable pre/post comparison.

## What the change is (intended behavior)
Entity/page confidence is **logically deprecated**: no intake writes (page upsert AND alias-Entity creation), no dataclass field, no query row-mapping, no verifier comparison, no snapshot emission, no MCP surface, no parked-promotion write, no test-factory emission. The Kuzu column is NOT dropped (stays until the next destructive schema change). Snapshot `entities.jsonl` drops the key (format v6→v7 — the first non-additive bump; write-only by design, NO v6 loader). **Claim/Evidence computed confidence** (`Claim.confidence` DOUBLE, `confidence_spread`, `core/belief_classifier.py`, EVIDENCES score, the o1 scenario YAMLs) is **protected and must be untouched**.

## How to see the diff
- Modified files: `git diff HEAD` — `kdb_graph/{intake,types,queries,graphdb,verifier,snapshot,testing}.py`, `kdb_graph/ops/op_1_promote.py`, `kdb_graph/tests/test_snapshot.py`, `kdb_mcp/{models,adapters}.py`.
- New paths (untracked; review them too): `kdb_graph/tests/gate3_dump.py`, `kdb_graph/tests/test_gate3_confidence_deprecation.py`, `kdb_graph/tests/fixtures/gate3_mixed_corpus/` (corpus journals + committed pre-artifact).

## Pressure-test these (the load-bearing decisions)
1. **Inventory completeness.** Blueprint Task 3.1 lists every write/read site: `intake.py` page upsert AND alias creation; `ops/op_1_promote.py` Entity write (NOT the Claim-tier confidence at `op_1_promote.py:373+`); `types.py` Entity; `queries.py` + `graphdb.py` row mapping; `verifier.py` comparison; `snapshot.py`; `kdb_mcp/models.py` + `adapters.py`; `testing.py` factory. Grep the whole repo for `confidence` and confirm: no remaining Entity-scope write/read outside the inventory; `tools/diagnostics/dump_run_passes.py`'s `confidence` is Pass-1 *source* frontmatter (different field, correctly untouched); viewer bakeoff HTMLs are static artifacts (correctly untouched).
2. **Claim-tier protection.** `kdb_graph/schema.py` Claim DDL (`confidence DOUBLE`, `confidence_spread`), `core/belief_classifier.py`, `op_1_promote.py`'s Claim confidence writes, the snapshot Claim writers (`snapshot.py:497+`), and the o1 eval YAML/probe files must be byte-identical to Gate 2. Verify the diff did not touch them.
3. **Gate-3 pre/post comparison soundness.** This is the gate's core evidence. Check: (a) the pinned corpus (`fixtures/gate3_mixed_corpus/runs/`) is a *mixed* pair — one LEGACY-shape journal (explicit `confidence: high/low/medium` + `summary_slug` + stored `outgoing_links` + an `aliases_emitted` entry) and one NEW-shape journal (4-field pages, body wikilinks); (b) `gate3_dump.py`'s normalization excludes ONLY volatile timestamps — every other node/edge/property is compared; (c) the committed `pre_confidence_removal_artifact.json` was generated at the Gate-2 HEAD (confidence values present and varied — the anti-regeneration guard pins this); (d) the test asserts post-rebuild confidence is uniformly NULL (dead column never written) AND the full graph is otherwise identical; (e) is there any other property the deprecation could plausibly perturb that the corpus FAILS to exercise (e.g., SUPPORTS hash_at_time, BELONGS_TO support_count, alias page_type/status)?
4. **Snapshot v7 correctness.** `SNAPSHOT_FORMAT_VERSION == 7`; `_write_entities` emits no `confidence` key even when the dead column holds values (test pins this with a seeded legacy-shape graph); the version-history comment documents v7 as the first non-additive bump with no v6 loader; manifest tests still pass; Claim snapshot files still emit their confidence columns.
5. **Dead-column safety.** Intake's MERGE no longer sets `p.confidence` — on CREATE, the column is NULL. Any code path that reads `e.confidence` and would break on NULL (the removed dataclass field, the MCP adapter, analytics, `cli.py` printers)? Confirm no surviving reader exists.
6. **Dual-mode read-compat preserved.** The LEGACY corpus journal (WITH confidence + summary_slug + outgoing_links) still rebuilds cleanly — intake IGNORES the deprecated page key rather than rejecting it (the aggregate schema retains it optional-deprecated). Confirm no new rejection path for historical payloads.
7. **Scope discipline.** Phase 3 ONLY: no Phase-4 parity corpus, no #116 reservation machinery, no changes to compiler/ Gate-2 code beyond what Phase 3 requires. The verifier's entity diff dropping the confidence pair is the ONLY verifier change.

## Output — write ONLY to `docs/superpowers/plans/2026-07-22-task115-phase3-gate3-code-review-codex.md`
1. **Verdict:** `GO` (commit Gate 3 as-is) / `GO-WITH-CHANGES` (commit after specific fixes) / `REWORK`.
2. **Findings**, each: `[Severity: Critical | High | Medium | Low]` · `file:line` · the flaw · why it matters · concrete suggested change.
3. Group under: **(a) inventory completeness & Claim-tier protection**, **(b) Gate-3 pre/post comparison soundness**, **(c) snapshot v7 & dead-column safety**, **(d) read-compat & scope**. If a group is empty, say "none".
4. **One-paragraph bottom line:** is this diff safe to commit as Gate 3, and what (if anything) must change first.
