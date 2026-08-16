# #130 — Deprecated Page Lifecycle: Blueprint v0.1

Date: 2026-08-05 · Task: **#130 page lifecycle on SUPPORTS-loss (`deprecated` status, source-delete erasure)** · Status: **v0.1 — for ratification**

Ledger row: `docs/TASKS.md` #130 (open). Sequenced **after** #129 (closed): #129 reduced
spurious drops at the source; #130 changes what a drop means. Name ratified by owner:
**`deprecated`** (supersedes the ledger's working name "dormant").

---

## 1. What #130 is

The zombie fix, at the lifecycle layer.

**Verified problem statement.** A page that loses its last SUPPORTS edge — the model
declined to re-emit it on a warm recompile — is today flagged `orphan_candidate` and
**DETACH DELETEd from the graph in the same finalize pass**
(`kdb_graph/intake.py:682-740` mark; `orchestrator/kdb_orchestrate.py:212-226` reap via
`reap_orphans_from_graph` → `apply_cleanup` at `kdb_graph/intake.py:800-809`). The file
on disk is never touched by that path. Result: **zombie pages** — files claiming
`status: active` with no graph node. Measured: 85 after baseline run
`2026-08-04T13-10-43_EDT`; 38 after qwen warm `2026-08-04T23-45-24_EDT`; **15 live right
now** after deepseek warm `2026-08-05T00-25-04_EDT` (305 files vs 290 entities).

**Root cause.** The graph has a status lifecycle (`active` / `orphan_candidate` /
deleted); the wiki file has none (`page_writer.py:174` writes `status: active` and no
code path ever writes anything else). Deletion is the only end-state, and it is
graph-only. Every drop therefore diverges the two stores.

**Fix.** Replace the transient `orphan_candidate` turnstile with a **resting
`deprecated` status**, written atomically to **both** the graph node and the file's
frontmatter in the same finalize pass. Deletion is removed from the model-drop path
entirely. The only remaining deletion is **source deletion**, which the owner has ruled
is **total erasure** — node deleted, file deleted, no archive.

**Success measure (the zombie invariant).** After any run, for every wiki file:
frontmatter `status` == its graph node's `status`, and every canonical graph node has
exactly one file. No file without a node, no node without a file. §13 audits this.

## 2. Scope and non-goals

**In scope:**

- Graph layer: rename `orphan_candidate` → `deprecated`; removal of the model-drop reap;
  source-deletion erasure fork (§5, §6).
- File layer: `page_writer` gains deprecation-marking and page-file deletion (§7).
- Orchestrator: finalize rewiring; reconcile-op erasure capture; summary keys (§8).
- Consumers: `queries.py` rename, `graphdb-kdb orphans` CLI rename, KPI watched-metric
  input (§9).
- `kdb-clean orphans` retirement notice (§10).
- Tests per §12; sandbox verification per §13.

**Non-goals (explicitly deferred):**

- **No backfill** of historical drops (run-2's 85, the live 15). Owner ruling: cold runs
  erase sandbox history; the next cold run re-derives a clean world.
- **No GC/retention policy** for deprecated pages. They accumulate until revived or the
  vault is cold-run. A `kdb-clean deprecated --older-than` reaper is a possible future
  task, deliberately not built now.
- **Replay/journal hardening.** Orchestrator-era runs write no replayable compile
  journals today (sidecar layout drift — pre-existing gap, verified §11). #130 adds no
  journal types and neither fixes nor worsens this; reconvergence path is a cold run.
- **#131** (t1 page_cap exemption) — separate task, no dependency.
- Person-entity modeling (parked in the #123 residue note).
- `kdb_graph/ops/` (parked 2.0 tier) and `scripts/migrate_task64_supersession.py`
  (HISTORICAL) reference old statuses; both unwired — untouched.

## 3. Binding rulings (owner, 2026-08-04 → 2026-08-05 discussion)

- **R-130-1 — Option C:** on SUPPORTS-loss, transition to `deprecated` instead of
  deleting. "So Option C is the way to go."
- **R-130-2 — The name is `deprecated`.** "I have changed my mind on dormant, let's call
  it deprecated."
- **R-130-3 — Both stores, atomically.** The status flip lands on the graph node and the
  file's frontmatter in the same finalize pass — the zombie condition becomes
  structurally impossible.
- **R-130-4 — Source deletion is total erasure.** "If a source is deleted, no wiki
  pages related to that source should exist... not in KDB/wiki not archived." Node
  DETACH DELETEd, file deleted from disk, **no archive copy** (today's
  `orphan-archive/` move is removed from this path).
- **R-130-5 — No backfill.** Cold runs erase everything soon enough.
- **R-130-6 — No GC.** Deprecated pages persist until revival; no automated expiry.

## 4. Design — the lifecycle

Entity (canonical pages only — aliases remain exempt from all of this):

```
                 model drops page on recompile
            ┌──────────────────────────────────┐
            ▼                                  │
        ┌────────┐   re-emitted by a      ┌────────────┐
        │ active │ ◄── later compile ──── │ deprecated │
        └───┬────┘   (revival)            └────────────┘
            │
            │ source deleted AND its SUPPORTS
            ▼ was the page's last
         ERASED (node + file, no archive)
```

- `deprecated` pages keep every edge except SUPPORTS (which is already gone):
  LINKS_TO in/out and BELONGS_TO stay. Revival therefore restores the page with its
  neighborhood intact — no re-wiring.
- Readers already filter `status = 'active'` (`kdb_graph/queries.py:250,264,324,340,
  372`); `deprecated` is invisible to graph queries, Pass-1.5 search space
  materialization, Pass-2 context (`compiler/context_loader.py` reads via
  `queries.py`), and MCP tools. No reader changes needed.
- A `deprecated` page has zero SUPPORTS by construction, so source deletion can never
  reach it — its only exits are revival or a cold run.

## 5. Design — graph layer: rename + revive generalization

`kdb_graph/intake.py` `_detect_and_mark_orphans` (682-740) → `_detect_and_mark_deprecations`:

- Mark query: status literal `'orphan_candidate'` → `'deprecated'`; otherwise identical
  (canonical-only, zero-SUPPORTS, not already marked).
- Revive query: `p.status = 'deprecated'` with SUPPORTS → `'active'` (was
  `'orphan_candidate'` → `'active'`). Mechanism already exists (723-735); this is a
  literal change, not new logic.
- Return shape: newly-deprecated as `(slug, page_type)` pairs (was `list[str]` of
  slugs) — the finalize file-sync needs `page_type` for path derivation
  (`common.paths.slug_to_relpath`).
- Public wrapper `detect_orphans` (743-760) → `detect_deprecations`, same return-shape
  change. Callers updated: orchestrator finalize, tests.
- `kdb_graph/types.py:27` `IntakeResult.orphans_detected` → `deprecations_detected`
  (comment + name; populated at `intake.py:135` for the monolith/replay path).

`kdb_graph/queries.py:210-215` `orphan_entities()` → `deprecated_entities()`, status
literal → `'deprecated'`. Callers: `kdb_graph/cli.py` (§9), `tools/cleanup.py` (§10).

## 6. Design — graph layer: source-deletion erasure fork

`_handle_source_deleted` (`kdb_graph/intake.py:259-278`) currently drops the source's
SUPPORTS edges and marks the Source `deleted`, leaving pages for orphan detection —
which under #130 would wrongly send them to `deprecated`. New behavior, all inside the
existing Phase-2 transaction:

```python
# 1. BEFORE dropping edges: pages whose ONLY SUPPORTS is this source (canonical only)
erased = query("""
    MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(p:Entity)
    WHERE p.canonical_id IS NULL AND COUNT { ()-[:SUPPORTS]->(p) } = 1
    RETURN p.slug, p.page_type
""")
# 2. existing: drop this source's SUPPORTS edges; mark Source status='deleted'
# 3. erase: alias rows pointing at the erased canonicals, then the canonicals
exec("MATCH (a:Entity) WHERE a.canonical_id IN $slugs DETACH DELETE a")
exec("MATCH (p:Entity) WHERE p.slug IN $slugs AND p.canonical_id IS NULL DETACH DELETE p")
```

- Alias rows (step 3a) are identity assertions about a node that ceases to exist;
  leaving them would dangle. One extra query, correct regardless of whether aliasing
  has ever fired in production (`alias_of = 0` live today).
- DETACH DELETE removes LINKS_TO/BELONGS_TO with the node — no dead graph edges.
  Other pages' wiki bodies may hold `[[links]]` to the erased slug; those dangle in
  Obsidian. Posture identical to today's cleanup: **report, never rewrite** — erased
  slugs + affected linking pages go to the run event log (§8).
- `IntakeResult` gains `erased_pages: list[dict]` (`{slug, page_type}`), aggregated by
  `apply_compile_result` from each `_handle_source_deleted` call.
- A page supported by **two** sources keeps its remaining edge (`COUNT = 1` predicate)
  and stays `active` — only true orphans-of-deletion are erased.
- Placement in the graph layer (not the orchestrator) is deliberate: any future replay
  of a reconcile op reproduces the erasure through the same code path.

## 7. Design — file layer (`compiler/page_writer.py`)

Two new public helpers; `page_writer` remains the sole owner of wiki writes.

- `mark_deprecated(vault_root, pages) -> list[Path]` — for each `{slug, page_type}`:
  locate via `slug_to_relpath`, read, replace the frontmatter `status: active` line
  with `status: deprecated` (frontmatter block only; format is machine-emitted and
  stable, `page_writer.py:174`), atomic write (`atomic_write_text`, D14). Missing file
  → skip + note (never fail). Idempotent on already-deprecated files.
- `delete_page_files(vault_root, pages) -> list[Path]` — `unlink(missing_ok=True)` per
  page. No archive, no move (R-130-4).

Revival needs **no new file code**: a re-emitted page is rewritten wholesale by the
existing compile path, whose frontmatter defaults to `status: active`.

## 8. Design — orchestrator

**Finalize** (`kdb_orchestrate.py:195-237`) becomes:

```
5. wire_links(combined)
6. deprecations = detect_deprecations(conn, run_id)        # graph flip (§5)
7. page_writer.mark_deprecated(vault_root, deprecations)   # file sync (§7) — NEW
8. write compile_result.json (unchanged)
```

**Removed from finalize:** `reap_orphans_from_graph`, `build_cleanup_artifacts`,
`retraction.json` + `runs/<run_id>.json` cleanup-journal write, `apply_cleanup`
(the `apply_cleanup` **function stays** in `kdb_graph/intake.py` — historical
`event_type: cleanup` journals must remain replayable, adapter route untouched).

**Reconcile commit** (`_commit_reconcile_op`, `kdb_orchestrate.py:402-418`): capture
the `IntakeResult` from `apply_compile_result`; for each `erased_pages` entry call
`page_writer.delete_page_files`; log erased slugs + dead-link report to the event log.

**Run summary** (`write_last_orchestrate_json` finalize dict):
`{"links_wired", "orphans_marked", "reaped"}` → `{"links_wired", "deprecated": N,
"erased": M}`. Consumers swept at implementation (`last_orchestrate.json`, viewer).

dry-run parity: today's dry-run still mutates the graph (wire_links + detect) and gates
only artifacts/files; #130 keeps that semantic — graph flips happen, `mark_deprecated`
and file deletions are gated.

## 9. Design — consumers

- `kdb_graph/cli.py`: `orphans` subcommand → `deprecated` (cmd + help + command map;
  reads `deprecated_entities()`). Dev-facing CLI; clean rename, no alias kept.
- `compiler/kpi/graph.py:280-290`: watched `orphan_rate` input was
  `finalize_artifacts["reaped"]` → now the finalize `deprecated` list; metric renamed
  `deprecation_rate` (same formula, newly-deprecated ÷ total entities). Watched-only,
  never scored; history break accepted and noted. `emit_kpis` + tests updated.
- `kdb_search`, `kdb_mcp`, `context_loader`: **no changes** — all read through
  `queries.py` active filters (verified §4).
- `kdb_graph/verifier.py`, `snapshot.py`: no status references (verified) — untouched.

## 10. Design — `kdb-clean orphans` retirement

The command's precondition (`orphan_candidate` exists) can never hold post-#130.
Pointing it at `deprecated` is **wrong** (it would archive pages R-130-1 says stay).
Decision: `_cmd_orphans` prints a retirement notice ("status removed in #130; pages are
deprecated in place, never reaped; source deletion erases") and exits 0. `reap_orphans`,
`reap_orphans_from_graph`, `build_cleanup_artifacts` become dead code — flagged in
docstrings, **not deleted** in this task (historical-journal tooling
`scripts/backfill_cleanup_journal.py` still imports `build_cleanup_artifacts`).

## 11. Rebuild/replay posture (verified facts)

- `graphdb-kdb rebuild` replays `compile` and `cleanup` events from
  `state/runs/<run_id>.json` + sidecars (`kdb_graph/adapters/obsidian_runs.py`).
- Orchestrator-era runs write **no compile journals** (only finalize's cleanup journal
  when reaped > 0, and `compile_result.json` lands at `state/` top level, not the
  documented sidecar path). Replay-from-journals for this era is a pre-existing gap —
  #130 does not depend on it and does not expand scope to fix it.
- `deprecated` is **derived state**: recomputed from SUPPORTS topology at every
  finalize. Any cold run re-derives active/deprecated correctly by construction.
- Historical `cleanup` journals remain replayable (`apply_cleanup` preserved, §8).

## 12. TDD test plan

**P1 — graph core (`kdb_graph/tests/`), written first, red until implemented:**

- `test_intake.py`: model-drop → node PRESENT with `status='deprecated'`, LINKS_TO
  intact, file untouched (graph layer does no I/O). Re-emit → revive to `'active'`.
  Alias entities never deprecated (existing exclusion, renamed literal).
- `test_intake.py` erasure: DELETED op → sole-supported page's node GONE (incl. its
  edges); alias rows for erased canonicals GONE; dual-supported page stays `'active'`;
  `IntakeResult.erased_pages` carries `{slug, page_type}`.
- `test_queries.py`: `deprecated_entities()` enumerates; all five active filters
  exclude deprecated.
- `test_rebuilder.py`: historical cleanup-journal replay unchanged (existing tests
  guard — must stay green).
- `test_alias_intake.py`: literal rename updates.

**P2 — file layer (`compiler/tests/test_page_writer.py`):**

- `mark_deprecated` flips exactly the frontmatter status line, body byte-identical;
  idempotent; missing file tolerated; atomic write.
- `delete_page_files` unlinks; missing_ok.

**P3 — orchestrator + KPI (`orchestrator/tests/`, `compiler/tests/test_kpi_graph.py`):**

- Finalize: no `retraction.json`, no cleanup journal written; `mark_deprecated` invoked
  with the newly-deprecated set; summary keys `deprecated`/`erased`.
- Reconcile DELETED op end-to-end (tmp vault): file deleted from disk, node absent,
  event log records erasure.
- KPI `deprecation_rate` derivation from finalize artifacts.

**P4 — tools (`tools/tests/test_kdb_clean*.py`):** retirement notice, exit 0.

Boundary guard (`tools/tests/test_package_boundaries.py`) untouched; full suite green
at every phase gate (current baseline: 3112 passed).

## 13. Verification (sandbox, post-implementation)

Vault `~/Obsidian/Vault-in-place-test-run`, deepseek-v4-flash, full stats capture.

1. **Cold run** → audit: zombie invariant (§1) holds; `deprecated` count = 0 expected
   (cold emits everything); suite green.
2. **Warm run** (unedited sources) → dropped slugs land in `deprecated` (graph AND
   frontmatter agree); zero zombies; residual drop count vs. the 15-page deepseek
   baseline.
3. **Revival probe** (recompile after restoring/forcing re-emit of a deprecated slug —
   method fixed at implementation) → `active` on both sides.
4. **Erasure probe**: delete one source from the vault, run → its sole-supported pages
   gone from graph AND disk (no `orphan-archive/` entry); dual-supported page (if any)
   survives active.
5. Audit script (ad-hoc, not committed): cross-walk every wiki file's frontmatter
   status vs. graph node status — must be 1:1.

## 14. Closure checklist (Phase 3 discipline)

- [ ] All P1–P4 tests green; full suite ≥ 3112 baseline
- [ ] Sandbox §13 probes 1–4 pass; zombie audit clean
- [ ] `docs/TASKS.md` #130 → closed with outcome narrative
- [ ] North Star `docs/CODEBASE_OVERVIEW.md` milestone entry (lifecycle section rewrite:
      `orphan_candidate` vocabulary is gone)
- [ ] `AGENTS.md` architecture paragraph: orphan-reap language → deprecated lifecycle
- [ ] Follow-ups filed: replay/journal hardening (pre-existing gap, §11);
      `kdb-clean orphans` dead-code removal (deferred from §10); deprecated-GC candidate
      (only if accumulation ever matters, R-130-6)
