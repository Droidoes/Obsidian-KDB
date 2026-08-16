# Task #132 Blueprint v0.1 — Replay/journal hardening (orchestrator-era journals)

**Status:** SHIPPED 2026-08-06 — sandbox cold run `2026-08-05T22-55-58_EDT` verified `live ≡ replay` (0 divergences, all layers)
**Date:** 2026-08-06
**Task ledger:** `docs/TASKS.md` #132
**Architecture decision:** Option A (producer retrofit — the orchestrator writes the D39 journal layout again), ratified by Joseph 2026-08-06. Panel review deliberately skipped — success is machine-checkable (`live ≡ replay` graph diff); the verifier is the review.

---

## 1. Problem statement

`graphdb-kdb rebuild` replays per-run journals (`state/runs/<run_id>.json` + sidecars
`compile_result.json` / `last_scan.json`). The last writer of those journals was deleted with
`kdb-compile` in the 0.5.1 realignment (2026-06-01). Since then:

- The orchestrator builds the exact replay payload in memory (`_combine_crs`,
  `orchestrator/kdb_orchestrate.py:167-194`) and hands it to `apply_compile_result`, then
  persists only the flat baton `state/compile_result.json`, **overwritten every run**.
- No `<run_id>.json` journal, no per-run sidecars, no `state/last_scan.json` (so even the
  `--backfill-baton` escape hatch is unsatisfiable).
- `graphdb-kdb rebuild` discovers **zero eligible journals** on a modern state tree;
  D39's independence proof is unfalsifiable.

Post-#130 there are also no cleanup journals; deprecation is a finalize-time fixpoint
derivation, and source deletion is total erasure applied via reconcile ops. Any fix must
reproduce those graph effects under replay.

## 2. What the live path actually ingests (the fidelity contract)

Per run, the graph receives inputs through exactly these intake calls
(`kdb_graph/intake.py`):

| Live call site | Payload | Flags |
|---|---|---|
| `_commit_source` (`kdb_orchestrate.py:142-144`) | per-source `cr` + `single_scan = {files: [entry w/ POST-embed hash], to_compile: [sid], to_reconcile: []}` | `detect_deprecations=False, wire_links=False` |
| `_commit_reconcile_op` (`:415-417`) | `{compiled_sources: []}` + `{files: [moved_entry] or [], to_compile: [], to_reconcile: [op]}` — **applied ops only**; MOVED+CHANGED ops are skipped at `:931` | same |
| `_finalize` (`:219-220`) | `wire_links(combined, conn, run_id)` then `detect_deprecations(conn, run_id)` — only when ≥1 source committed (`:949`) | — |
| `_commit_noise_source` / `_commit_source_failure` | **manifest only — no graph call** | — |

`finalize` internals: `wire_links` commits its own txn; `detect_deprecations` commits its
own txn (`intake.py:807-859`). A crash between them leaves "wired but not deprecated" —
a state the journal must be able to represent.

**Edge case that shapes the design:** on `manifest_post_graph` failure
(`_commit_source` `:152-158`) the graph commit DID happen but the loop does not append
`commit.cr` to `accumulated_crs`. The archive must include that cr anyway — it was
ingested graph-side, and replay rebuilds the graph, not the manifest.

**Ordering fact that shapes the design:** `apply_compile_result` runs reconcile (Phase 2)
*before* compiled sources (Phase 3), but the live orchestrator runs all source commits
*before* reconcile ops. Exotic-corner consequence (a changed source re-emits, in the same
run, a page whose sole supporter was just deleted): a single unioned call would erase the
page before re-adding it (DETACH DELETE kills inbound LINKS_TO and created_at), while the
live order preserves them. The archive must replay in **live order**: commits phase, then
reconcile phase.

## 3. Design

### 3.1 Journal — `state/runs/<run_id>.json` (schema `"2.3"`)

Written once per run, in `run()`'s `finally` block (outcome known there), next to the
existing `measurement_header.json` write (`kdb_orchestrate.py:1045-1047`). Slim:

```json
{
  "schema_version": "2.3",
  "producer": "kdb-orchestrate",
  "run_id": "2026-08-06T…",
  "started_at": "<ctx.started_at — ISO; the adapter's sort key>",
  "finished_at": "<now_iso()>",
  "dry_run": false,
  "success": true,
  "replayable_payload": true,
  "finalize_progress": "none | wired | deprecated",
  "counts": {"sources_scanned": 0, "sources_compiled": 0, "sources_noise": 0,
             "sources_failed": 0, "sources_moved": 0, "sources_deleted": 0},
  "quarantined_sources": ["<source_id>", "…"]
}
```

- `success` = `exit_code == 0`. `replayable_payload` = sidecars archived successfully
  (D50 amendment leg: an aborted/crashed run has `success=false` yet a faithful partial
  payload → `replayable_payload=true`).
- `finalize_progress` (new, the derive gate): `"none"` (finalize never ran — aborted run,
  reconcile-only run — or `wire_links` rolled back), `"wired"` (wire_links committed,
  deprecations not), `"deprecated"` (finalize completed).
- `event_type` absent ⇒ compile (adapter default).
- Dry runs: journal + sidecars written with `dry_run: true` (audit; adapter skips — the
  existing `dry_run` skip reason).

### 3.2 Sidecars — `state/runs/<run_id>/`

Archived in the same `finally` site, from accumulated state (partial on abort — faithful
by construction):

**`compile_result.json`** = `_combine_crs(accumulated_crs, run_id)` — byte-identical to
the flat baton `_finalize` writes. Plus the `manifest_post_graph` cr (§2 edge case):
on `failure_stage == "manifest_post_graph"` the loop appends the cr (and its scan entry)
to the archive accumulators even though the commit "failed".

**`last_scan.json`** = the union of actual intake scan inputs, keeping the two phases
separate (§2 ordering fact):

```json
{
  "files": ["<post-embed ScanEntry dict per committed source>"],
  "to_compile": ["<committed source_ids>"],
  "moved_files": ["<moved_entry dict per APPLIED MOVED op>"],
  "to_reconcile": ["<applied op dicts only — MOVED+CHANGED skips excluded>"]
}
```

- Noise sources, failed sources, and unchanged sources are **excluded** (they never
  reached intake — unlike the monolith era, whose full-scan archive was correct for a
  single-call live path).
- `moved_files` is new for 2.3 (legacy sidecars have no such key; legacy path untouched).
- An empty run (nothing committed, no reconcile ops) still archives both files with empty
  collections — truthful, replayable no-op, keeps eligibility uniform.

**Archival is warn-only**: wrapped in try/except; on failure set
`replayable_payload=false`, still attempt the journal, never mask a propagating
exception, never abort a run (the `maybe_emit_kpis` philosophy).

### 3.3 Adapter replay — `kdb_graph/adapters/obsidian_runs.py`

Three changes, all adapter-local; `rebuilder.py`, `verifier.py`, `intake.py` **untouched**:

1. `supported_journal_versions += ["2.3"]` (D-S3 gate).
2. `load_payload`: for 2.3 journals, read `finalize_progress` from the journal and stuff
   it into the returned mutation under reserved key `_finalize_progress` (**in-memory
   only** — the on-disk sidecar stays pristine; `apply` pops it before routing). Legacy
   journals: key absent.
3. `apply`: pop `_finalize_progress`.
   - **Key present (2.3)** — two-phase live-order replay with deferred derive:
     ```python
     apply_compile_result(mutation, {**scan, "to_reconcile": []}, run_id,
                          conn=conn, detect_deprecations=False, wire_links=False)
     if scan.get("to_reconcile") or scan.get("moved_files"):
         apply_compile_result({"compiled_sources": []},
                              {"files": scan.get("moved_files", []),
                               "to_reconcile": scan.get("to_reconcile", [])},
                              run_id, conn=conn,
                              detect_deprecations=False, wire_links=False)
     if progress in ("wired", "deprecated"):
         wire_links(mutation, conn, run_id)
     if progress == "deprecated":
         detect_deprecations(conn, run_id)
     ```
   - **Key absent (legacy 2.0–2.2)**: unchanged — single
     `apply_compile_result(mutation, scan, run_id, conn=conn)` with defaults
     (`True/True`), exactly as the monolith ingested.

`graphdb-kdb verify` inherits 2.3 coverage automatically (it replays through the same
adapter). The pre-existing Claim-layer replay gap (verifier scope-limits its Claim diff)
is untouched — parked 2.0 tier, out of scope.

### 3.4 live ≡ replay argument

- **Pages/SUPPORTS/aliases**: union payload ≡ per-source sequential applies — supersession
  is per-source, entity upserts idempotent, alias phase unions. Already pinned at the
  production boundary (`test_rebuilder.py:1106-1220`).
- **Source scan-refresh rows**: union `files[]` has each source at most once (a source
  commits ≤ once per run; a MOVED+CHANGED source appears only via its committed
  post-embed entry) ⇒ MERGE idempotent, same end state.
- **Reconcile**: applied ops only, in live order after commits (§3.3 two-phase split).
- **LINKS_TO**: `wire_links(combined)` — identical payload, idempotent per-page
  drop+recreate.
- **Deprecations**: global fixpoint with revive; `finalize_progress` replays exactly the
  derives that ran live — including the abort-before-finalize case (`"none"` ⇒ page stays
  deprecated in both stores) and the crash-between-finalize-stages case (`"wired"`).
- **manifest_post_graph**: cr archived ⇒ replayed graph includes what live committed.
- **Out of scope (never was in scope)**: replay rebuilds graph state only — not wiki
  files, not the manifest (D51 layer model).

### 3.5 What does NOT change

- Flat baton `state/compile_result.json` — kept (consumed by the `--emit-kpis` gate,
  `kdb_orchestrate.py:1049-1050`).
- `--backfill-baton` — unchanged (pre-#63 history only; still requires a flat
  `state/last_scan.json` nobody writes — noted, not fixed here).
- Rebuilder core, verifier, intake, schema — no changes.
- Legacy 2.0–2.2 journal support — retained (none exist on modern state trees, but the
  code path stays pinned).

## 4. Implementation plan

**132.1 — Adapter 2.3 replay (kdb_graph).** TDD red → green. `obsidian_runs.py` per §3.3.

**132.2 — Orchestrator journal/sidecar writer.** TDD red → green. New small module
`orchestrator/journal_writer.py` (archive sidecars + write journal; warn-only); wire
accumulators in `run()` (committed scan entries, applied reconcile ops, moved entries);
append cr on `manifest_post_graph`; call from the `finally` block; re-scope the stale
absence pin (`orchestrator/tests/test_kdb_orchestrate.py:237-238` — journals are a
`run()`-level artifact, `_finalize` still writes none; `retraction.json` stays absent).

**132.3 — E2E proof + docs.** Graph-equality test (below); sandbox warm run on
`Vault-in-place-test-run` → `graphdb-kdb verify` (temp replay + diff) → zero divergence;
doc batch: TASKS #132 resolution, CBO §8.4 + D39 row (2.3 amendment), adapter module
docstring (`:1-7` still says "kdb-compile's run-journal artifacts"),
`intake.py:682` stale sidecar comment, producer-contract doc §3.3/3.4 (2.3 layout),
`RunContext`/`page_writer` journal docstrings.

## 5. Test plan (TDD-first)

**132.1 — `kdb_graph/tests/test_rebuilder.py`:**
1. 2.3 journal, `finalize_progress="deprecated"` ⇒ replay equals a deferred-commit live
   sequence (edges wired, dropped pages deprecated).
2. `"none"` ⇒ no LINKS_TO wired, no deprecations marked after replay.
3. `"wired"` ⇒ edges wired, zero deprecations.
4. Two-phase ordering pin: deleted sole-supported page re-emitted by a compiled source in
   the same run ⇒ page survives with inbound edges + `created_at` intact.
5. Reconcile-only archive (empty `compiled_sources`, ops + `moved_files`) replays clean.
6. `"2.4"` journal ⇒ `unsupported_version` skip; 2.3 dry-run journal ⇒ `dry_run` skip.
7. Reserved-key hygiene: `load_payload` returns mutation WITH `_finalize_progress`; the
   on-disk sidecar does NOT contain it.
8. Legacy 2.0–2.2 suite = unchanged existing pins.

**132.2 — `orchestrator/tests/test_kdb_orchestrate.py` (+ new journal-writer tests):**
1. Happy-path `run()`: journal exists with 2.3 fields (`success`, `replayable_payload`,
   `finalize_progress`, `started_at`); archived `compile_result.json` byte-equals the flat
   baton; `last_scan.json` union = committed post-embed entries only (noise/failed/unchanged
   excluded).
2. Mixed run (committed + noise + failure + MOVED + DELETED + MOVED+CHANGED): union
   exactly right; skipped op excluded; `moved_files` carries only applied MOVED entries.
3. Abort (`run_fatal`): `success=false`, `replayable_payload=true`,
   `finalize_progress="none"`, partial payload archived.
4. `manifest_post_graph`: cr + scan entry included in the archive despite failure exit.
5. Dry run: journal written, `dry_run=true`, sidecars archived, adapter would skip
   (asserted via 132.1.6's skip reason, not re-wired here).
6. Archival failure injected ⇒ journal still written with `replayable_payload=false`;
   run outcome unaffected.

**132.3 — E2E + live:**
1. E2E graph-equality: fixture-vault orchestrator run (existing stubbed-LLM harness),
   then a second warm run exercising drop + re-emit + a deletion ⇒ `rebuild` from
   journals into a fresh dir ⇒ full graph diff equal (entities + statuses, SUPPORTS,
   LINKS_TO, Source rows incl. post-embed hashes, domains).
2. Sandbox: warm run on `Vault-in-place-test-run`, then `graphdb-kdb verify` ⇒ zero
   divergence reported.
3. Pass criteria: full `pytest` suite green; verify clean; live ≡ replay on the E2E test.

## 6. Blast radius

- `kdb_graph/adapters/obsidian_runs.py` (version + flag channel + derive)
- `orchestrator/kdb_orchestrate.py` (accumulators, manifest_post_graph append, finally hook)
- new `orchestrator/journal_writer.py`
- tests: `kdb_graph/tests/test_rebuilder.py`, `orchestrator/tests/`
- docs: TASKS, CBO (§8.4 + D39 row), adapter docstring, `intake.py:682` comment,
  `docs/reference/graphdb-kdb-producer-contract.md`, `common/run_context.py` /
  `compiler/page_writer.py` journal docstrings
- **Untouched:** rebuilder, verifier, intake, schema, prompts, search, manifest writer.

## 7. Open questions / non-goals

- Claim-layer replay (parked 2.0 tier) — pre-existing verifier scope limit; not this task.
- Baton backfill's flat `state/last_scan.json` requirement — pre-#63 only; documented, not
  fixed.
- Journal is deliberately slim (eligibility + audit counts); run-log entries stay in-memory
  (`RunContext.append_log`) — richness can grow later if audit needs it.

## 8. Deviation log

1. **Dry-run journals carry empty payloads, not would-be payloads** (§3.1/§5).
   The conductor's dry-run early-returns before the graph opens (plan preview
   only — no enrich/compile fires), so no would-be payload exists. The journal
   is archived with `dry_run=true` + empty sidecars; the adapter skips it via
   the existing `dry_run` gate. The "every run leaves a journal" invariant is
   preserved.
2. **Sandbox proof is a cold run, not warm** (§5, 132.3.2). Rebuild replays
   only journaled runs, and the sandbox graph was built by unjournaled ones —
   a warm-run journal alone cannot reproduce it. The meaningful
   `graphdb-kdb verify` requires a cold run (fresh graph built entirely by
   journaled runs).
3. **MOVED+CHANGED skip pinned by construction, not a dedicated run()-level
   test** (§5, 132.2.2). Driving a MOVED+CHANGED classification through the
   real scanner proved impractical in the harness. The exclusion is
   structural — the archive append sits after the skip `continue` in the
   reconcile loop — and is covered by the MOVED-only run test plus 132.1's
   two-phase replay pins.
4. **Verifier Layer-1 preflight gained a run_state filter** (out of §3's
   "rebuilder/verifier/intake untouched" scope — verifier-side only, read
   path). The sandbox gate exposed a pre-existing false positive:
   `_diff_sources_preflight` expected EVERY manifest source in the graph, so
   the 7 noise sources (`run_state="no_graph_db"`, `compile_count=0`) were
   flagged `missing_in_live` on an otherwise-perfect verification. The fix
   expects graph presence only for `run_state="in_graph_db"` (missing
   run_state keeps the conservative legacy default); noise/pending/error-*
   records are correctly-absent by design. Pinned by
   `test_source_state_preflight_skips_non_graph_run_states`; sandbox verify
   went from 7 false positives to fully clean.

