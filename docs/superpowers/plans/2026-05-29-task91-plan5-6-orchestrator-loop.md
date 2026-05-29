# Plan 5+6 — `kdb-orchestrate` loop (Pass-1 egress wiring + the E2E conductor)

> **For agentic workers:** Use superpowers:subagent-driven-development or executing-plans. **Capstone integration** — high effort. Goes through advisor + 5-model panel review BEFORE execution (per the agreed path). The final task is the **live run Joseph fires**.

**Goal:** Build `kdb-orchestrate` — the end-to-end conductor that wires the four shipped foundations (`compile_source`, `detect_orphans`, pipeline registry, `scan_scope`) into a per-source loop on a single shared read-write GraphDB connection, ending in the first live `feeder→Pass-1→Pass-2→GraphDB` run on the test sandbox.

**Architecture:** New module `kdb_compiler/kdb_orchestrate.py`. Entry: registry → select pipeline → load scope → open ONE read-write `GraphDB` → `scan_scope` → per-source loop → finalize. The loop reuses existing machinery per-source (`enrich_one`, `compile_source`, `build_source_state_update`, `patch_applier.apply`, `apply_compile_result(detect_orphans=False)`); finalize runs `detect_orphans()` once → `kdb-clean orphans` → `last_orchestrate.json`. Produce-don't-write + embed-during-enrich + deferred-orphan-marking + fail-fast (D-91-8/13) all per the spec.

**Spec:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Orchestrator loop + Pass-2 ingress + Pass-1 egress). **Decisions:** D-91-1..14; embed-during-enrich + post-embed-hash (2026-05-29); produce-don't-write + accept cross-source-wiki trade-off (panel forks). Plans 5+6 of 6.

**Run tests with `-m "not live"`.** The final live run is Joseph-fired on `~/Obsidian/Vault-in-place-test-run/` with an isolated `.kdb-state/` + `GraphDB_Test`.

---

## Panel-review status (5-model panel, 2026-05-29 — synthesis: `docs/task91-plan5-6-review-synthesis.md`)

**Convergent fixes — FOLDED into the tasks below:**
- **M1 (Critical, 3/5):** `load_manifest_sources` must return `pipeline_id` (else `scan_scope` filters all prior out → whole-vault recompile every run). **Task 0** below: add it + stamp legacy records (no `pipeline_id`) with a default at startup + regression test.
- **M2 (High, 2/5):** noise commit sets `last_compiled_hash = post_embed_hash` (else re-enriched every run). **Task 3** noise branch.
- **Journaling — RESOLVED → per-source sidecar:** each committed source's `cr` → `state/sidecars/<run_id>/` right after its manifest commit; finalize concatenates into the batch `compile_result.json` + run journal. **Tasks 2 + 4.**
- **m1:** finalize cleanup writes its cleanup journal + `retraction.json` via `build_cleanup_artifacts` (else rebuild resurrects reaped entities). **Task 4.**
- **m2 (2/5):** `enrich_one` also returns `post_embed_mtime` (+ size); `_commit_source` overrides `current_mtime` in `single_scan`. **Tasks 1 + 2.**
- **m3:** wrap `reconcile.reconcile` in `compile_source` → `failure_stage="reconcile"` (a shipped Plan-1 gap). **Task 0.**
- **m4:** load the alias ledger ONCE before the loop (shared config), thread into each `compile_source`. **Task 3.**
- **m5 REFUTED (Qwen):** MOVED+CHANGED decomposes to NEW+DELETED in `classify()` and is handled correctly — the deferred comment is removed from Task 3.
- **m6 (Low):** `to_compile` is alphabetical, not dependency-ordered — accept v1, document in the loop.

## RESOLVED (5-model panel + Joseph, 2026-05-29 — `docs/task91-c1-ford-synthesis.md`)

**C1 (cross-source `LINKS_TO`) → defer link-wiring to finalize batch-wire, NO stubs** (panel 4/5; stubs rejected — break live≡replay, "ghost links", mask dangling-link signal). Per-source `apply_compile_result(wire_links=False)` skips only `_replace_outgoing_links` (keeps SUPPORTS/ingest-state/meta → read-after-write for T1/T2). A standalone `wire_links(cr, conn, run_id, now)` (extracted from `_replace_outgoing_links`) runs once at finalize over the accumulated `cr`s with all entities present → **live≡replay by construction**. Mid-run T3 degradation accepted (monolith had no intra-batch T3 either). *Optional later enhancement: Codex's incremental-prefix-rewire after each source for mid-run T3 — default OFF.*

**F-ord (commit ordering) → β, graph-sync-first** (panel UNANIMOUS 5/5; **Joseph approved revising ratified D-91-13 → see D-91-15**). Graph-sync (Kuzu txn) runs *before* manifest-write; manifest + sidecar are written only on graph-sync success. A graph-sync failure rolls back cleanly → manifest never written → case-(a) self-heal. **Case-(b) is eliminated.** Invariant strengthened: `sidecar exists ⇒ manifest written ⇒ graph consistent`.

**The convergent combined commit sequence** (drives Tasks 2 + 4):
```
per-source (_commit_source):
  1. patch_applier.apply(write=True)                                  # wiki (stage 8)
  2. apply_compile_result(cr, single_scan, conn,                      # Kuzu txn: Source+Entities+SUPPORTS+aliases+meta
        detect_orphans=False, wire_links=False)                       #   rollback-clean on failure (case-a)
  3. [on success] atomic_write_json(manifest)                         # ← COMMIT BOUNDARY (post-graph-sync, β)
  4. write per-source sidecar state/runs/<run_id>/<source_id>.json    # best-effort replay payload; accumulate cr
finalize:
  5. wire_links(accumulated_crs, conn)                                # C1 batch link-wire, all entities present (own txn, idempotent)
  6. detect_orphans(conn, run_id)                                     # single deferred pass
  7. reap_orphans_from_graph + apply_cleanup + build_cleanup_artifacts # kdb-clean (+ cleanup journal/retraction = m1)
  8. compact sidecars → combined compile_result.json + run journal + last_orchestrate.json
noise: no graph step → manifest metadata_only, last_compiled_hash=post_embed_hash (M2)
```
`last_orchestrate.json` distinguishes `manifest_failed_after_graph_commit` (Codex). Finalize-crash resume via a `state/runs/<run_id>_state.json` phase marker (v1-optional).

**Scope-collision check** — still deferred; validate cross-pipeline path overlap at orchestrator startup in a later pass (not gating the sandbox run).

---

## File Structure
- **Modify** `kdb_compiler/ingestion/enrich.py` — `EnrichResult` gains `body` + `post_embed_hash`; `enrich_one` returns them (recompute whole-file hash right after embed).
- **Create** `kdb_compiler/kdb_orchestrate.py` — the conductor (`run()`, per-source `_commit_source`, `_finalize`, CLI `main`).
- **Modify** `pyproject.toml` — `kdb-orchestrate` console script.
- **Create** `kdb_compiler/tests/test_kdb_orchestrate.py` — routing, fail-fast, finalize, summary (all non-live, model faked).

---

## Task 0 (prerequisite fixes — independent of the C1/F-ord deliberation)

**T0a — M1: `load_manifest_sources` returns `pipeline_id` + legacy-record migration.**
- `kdb_scan.load_manifest_sources` (kdb_scan.py:215-241): add `"pipeline_id": rec.get("pipeline_id")` to the returned dict; update docstring. **Without this, `scan_scope`'s `r.get("pipeline_id") == pipeline_id` filter drops every prior row → whole-vault recompile every run.**
- Orchestrator startup: load the full manifest; any source record lacking `pipeline_id` → stamp the selected (or a configured default) `pipeline_id` and rewrite, so legacy records are visible to `scan_scope`. (For the fresh sandbox this is a no-op; matters for real vaults later.)
- Test: a source committed under pipeline `p1` scans `UNCHANGED`/`to_skip` on the next `p1` run (the resume regression M1 would break).

**T0b — m3: wrap `reconcile.reconcile` in `compile_source` (shipped Plan-1 gap).**
- `kdb_compiler/compiler.py` `compile_source` (the shipped function): `reconcile.reconcile(cr, vres.measure_findings)` is unwrapped → `ReconcileError` escapes the `CompileSourceResult` contract. Wrap it:
  ```python
  try:
      reconcile.reconcile(cr, vres.measure_findings)
  except reconcile.ReconcileError as e:
      return CompileSourceResult(cr=None, failure_stage="reconcile",
                                 exception_type=type(e).__name__, error=str(e))
  ```
- Test: a `ReconcileError`-triggering cr → `result.failure_stage == "reconcile"` (not a raised exception).

**T0c — C1 mechanism: `wire_links` flag + standalone `wire_links()` (ingestor).**
- `apply_compile_result` gains `wire_links: bool = True`; when `False`, Phase-3 pass-2 **skips only `_replace_outgoing_links`** (keeps `_replace_supports_for_source` / `_update_source_ingest_state` / `_write_source_meta` → SUPPORTS + meta still per-source for read-after-write). Default `True` preserves the monolith/batch path.
- Extract a public `wire_links(cr, conn, run_id, now) -> int` that runs `_replace_outgoing_links` over every page in `cr["compiled_sources"]` (idempotent drop+recreate). The orchestrator calls it once at finalize over the accumulated batch `cr`.
- Tests: (a) `apply_compile_result(wire_links=False)` upserts entities+SUPPORTS but creates **zero** `LINKS_TO`; (b) a later `wire_links(batch_cr)` with both entities present creates the cross-source edge that per-source sync skipped; (c) default `wire_links=True` unchanged (existing ingestion tests green).

> T0a + T0b are independent of C1/F-ord (could run first). T0c is the C1 fix mechanism (panel-resolved); it + the β commit ordering now drive Tasks 2 + 4 (see the RESOLVED combined sequence above).

---

## Task 1 (Plan 5): `enrich_one` egress — return body + post-embed hash + mtime

**Files:** `kdb_compiler/ingestion/enrich.py`; Test `tests/test_enrich*.py` (mirror existing enrich tests).

- [ ] **Step 1: failing test** — `enrich_one` result carries `body` and a `post_embed_hash` equal to the on-disk file hash AFTER embedding.

```python
def test_enrich_returns_body_and_post_embed_hash(tmp_path, monkeypatch):
    # ... set up a source + monkeypatch call_pass1 to return a known envelope ...
    res = enrich_one(source_path=src, source_id=sid, runs_root=runs, run_id="r1",
                     provider="p", model="m")
    assert res.body  # the stripped body
    import hashlib
    on_disk = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()
    assert res.post_embed_hash == on_disk   # whole-file hash AFTER embed
```

- [ ] **Step 2: run** → FAIL (`EnrichResult` has no `body`/`post_embed_hash`).
- [ ] **Step 3: implement** — `enrich.py`:
  - `EnrichResult`: add `body: str | None = None`, `post_embed_hash: str | None = None`.
  - In `enrich_one`, after `embed_frontmatter(source_path, envelope)` (line 63), recompute the whole-file hash and thread body + hash into the returned `EnrichResult` on the success path:
    ```python
    embed_frontmatter(source_path, envelope)
    post_embed_hash = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
    ...
    return EnrichResult(source_id, outcome, envelope, sidecar, None,
                        body=body, post_embed_hash=post_embed_hash)
    ```
  - Skipped/failed paths leave `body`/`post_embed_hash` as their available values (body known for skipped; None for failed pre-embed).
- [ ] **Step 4: run** → PASS + existing enrich suite green.
- [ ] **Step 5: commit** `feat(task91): Plan5 — enrich_one egress (body + post-embed whole-file hash)`

---

## Task 2 (Plan 6): per-source commit helper

The load-bearing unit: given a compiled source, commit it atomically-enough per D-91-13.

**Files:** `kdb_compiler/kdb_orchestrate.py`; Test `test_kdb_orchestrate.py`.

- [ ] **Step 1: failing test** — `_commit_source` writes wiki pages, updates the manifest (post-embed hash + pipeline_id), and graph-syncs with `detect_orphans=False` (orphan not marked mid-loop).
- [ ] **Step 2: run** → FAIL.
> **Verified (advisor A, 2026-05-29):** `build_source_state_update` → `apply_scan_reconciliation` (source_state_update.py:146) iterates **only `last_scan`'s files** + `to_reconcile` ops; it does NOT diff against the full `prior` keyset, so a single-source `last_scan` updates only that source and leaves all others untouched. Per-source commit via the full builder is safe (no mass-tombstoning).

- [ ] **Step 3: implement** `_commit_source(*, cr, source_id, pipeline_id, post_embed_hash, scan_entry, prior_manifest, vault_root, state_root, conn, ctx) -> dict`:
  ```
  single_scan = {"files": [scan_entry_dict_with_pipeline_id_and_post_embed_hash], "to_compile": [source_id], "to_reconcile": []}
  next_manifest, _ = source_state_update.build_source_state_update(prior_manifest, single_scan, cr, ctx)
  patch_applier.apply(vault_root, compile_result=cr, last_scan=single_scan, run_ctx=ctx, write=True)   # stage 8
  atomic_write_json(manifest_path, next_manifest)                                                       # ← COMMIT BOUNDARY
  # (journaling: accumulate cr for finalize per Design Point 1)
  conn graph-sync: apply_compile_result(cr, single_scan, ctx.run_id, conn=conn, detect_orphans=False)   # case-b if this throws
  return {"next_manifest": next_manifest, "pages_written": [...]}
  ```
  The scan_entry carries `current_hash = post_embed_hash` so the manifest stores the post-embed hash (breaks the re-enrich loop).
- [ ] **Step 4: run** → PASS.
- [ ] **Step 5: commit** `feat(task91): Plan6 — per-source commit helper (apply→manifest→graph-sync)`

---

## Task 3 (Plan 6): the orchestrator loop + routing + fail-fast

**Files:** `kdb_compiler/kdb_orchestrate.py` (`run()`); Test `test_kdb_orchestrate.py`.

- [ ] **Step 1: failing tests** — the three branches + fail-fast:
  - NEW/MOD signal → enrich → compile → commit (graph has the source's SUPPORTS).
  - NEW/MOD noise (force_noise dir) → enriched, manifest `metadata_only`, NOT in graph.
  - DELETE → `apply_compile_result(empty cr, to_reconcile=[DELETED])` → SUPPORTS severed, Source tombstoned.
  - Pass-2 failure → run aborts (fail-fast), `failure_stage` recorded, prior sources stay committed.
- [ ] **Step 2: run** → FAIL.
- [ ] **Step 3: implement** `run(*, pipeline_id, vault_root, state_root, graph_path, provider, model, max_tokens, dry_run=False) -> OrchestrateResult`:
  ```
  pipeline = pipeline_registry.get_pipeline(state_root, pipeline_id)
  prior = load_manifest_sources(state_root / "manifest.json")
  ctx = RunContext.new(vault_root=vault_root)
  with GraphDB(graph_path) as g:                        # ONE shared read-write connection
      scan = scan_scope(pipeline.root, vault_root, pipeline_id=pipeline_id, prior=prior,
                        run_ctx=ctx, excludes=pipeline.excludes, file_types=set(pipeline.file_types))
      # Route off the partitions the scanner ALREADY computes (advisor C):
      #   scan.to_compile  = source_ids where current_hash != compiled_hash (NEW/CHANGED needing compile)
      #   scan.to_reconcile = DELETED + MOVED ops
      #   UNCHANGED + pure-MOVED (content same, hash unchanged) are NOT in to_compile → no recompile.
      for source_id in scan.to_compile:                  # compile queue first
          enrich = enrich_one(...)                        # embeds + post_embed_hash
          if enrich failed: return fail-fast(stage="enrich")
          if gate(enrich.envelope["kdb_signal"]) == "noise":   # incl. force_noise override
              prior = commit metadata_only (manifest, no compile/graph); continue
          result = compile_source(source_id, enrich.body,
                                  SourceFrontmatter.from_dict(enrich.envelope),   # from_dict projects; no keep_fm wrapper
                                  g.conn, ..., ctx=ctx, ledger=load_or_empty(...))
          if not result.ok: return fail-fast(stage=result.failure_stage)   # D-91-8
          prior = _commit_source(cr=result.cr, post_embed_hash=enrich.post_embed_hash, ...)["next_manifest"]
      for op in scan.to_reconcile:                        # DELETED + (pure-)MOVED
          apply_compile_result({"compiled_sources": []}, {"to_reconcile": [op], "files": []},
                               ctx.run_id, conn=g.conn, detect_orphans=False)  # _handle_source_deleted / _handle_source_moved
          prior = manifest tombstone/path-update commit
      # MOVED+CHANGED (a file both moved AND edited) appears in BOTH to_compile and to_reconcile —
      # the OQ-91-8 deferred edge. Plan v1: dedupe to the compile path (recompile at new path);
      # confirm/route explicitly during execution (or keep deferred with a logged skip).
      _finalize(g.conn, ...)                              # Task 4
  ```
- [ ] **Step 4: run** → PASS (branches + fail-fast).
- [ ] **Step 5: commit** `feat(task91): Plan6 — orchestrator loop (3-branch routing + fail-fast)`

---

## Task 4 (Plan 6): finalize — detect_orphans → cleanup → summary

- [ ] **Step 1: failing test** — after the loop, `_finalize` runs the single `detect_orphans()` pass, reaps via `kdb-clean orphans`, and writes `last_orchestrate.json`. (A source whose only supporter was deleted in the run ends up reaped.)
- [ ] **Step 2: run** → FAIL.
- [ ] **Step 3: implement** `_finalize(conn, *, state_root, ctx, counts, manifest_delta)`:
  ```
  detect_orphans(conn, ctx.run_id)                       # the single end-of-run marking pass (Plan 2)
  report = reap_orphans_from_graph(conn); apply_cleanup(report_retraction, ctx.run_id, conn=conn)  # kdb-clean orphans (D-91-4)
  write_last_orchestrate_json(state_root, summary)       # Task 5
  ```
  Skipped under `--dry-run` (no writes).
- [ ] **Step 4: run** → PASS.
- [ ] **Step 5: commit** `feat(task91): Plan6 — finalize (detect_orphans + kdb-clean + summary)`

---

## Task 5 (Plan 6): `last_orchestrate.json` (D-91-10)

- [ ] **Step 1: failing test** — slim summary with the D-91-10 fields.
- [ ] **Step 2: run** → FAIL.
- [ ] **Step 3: implement** `write_last_orchestrate_json(state_root, summary)` → `state/last_orchestrate.json`:
  ```json
  {"run_id","started_at","finished_at","exit_code","exit_reason",
   "counts":{"sources_scanned","sources_enriched","sources_compiled","sources_moved","sources_deleted","sources_failed"},
   "manifest_delta":{"added","removed","changed"}}
  ```
  On abort, `exit_code`/`exit_reason` record the failing source + D-91-13 case-(a)/(b). Written always (success + abort).
- [ ] **Step 4: run** → PASS.
- [ ] **Step 5: commit** `feat(task91): Plan6 — last_orchestrate.json run summary (D-91-10)`

---

## Task 6 (Plan 6): CLI + LIVE RUN gate

- [ ] **Step 1:** `main(argv)` — `kdb-orchestrate --pipeline ID --vault-root PATH [--state-root PATH] [--graph-path PATH] [--dry-run] [--model ID]`. Registry-driven pipeline selection (list if `--pipeline` omitted). Add `kdb-orchestrate` to `pyproject.toml` scripts; `pip install -e . --break-system-packages`.
- [ ] **Step 2:** non-live CLI smoke (`--dry-run` on a tmp vault) → exit 0, plan printed.
- [ ] **Step 3: scaffold the FULLY-ISOLATED sandbox** (assistant). **Isolation fix (advisor B):** `patch_applier` writes wiki under `vault_root/KDB/wiki/`, so the sandbox dir itself must be `vault_root` — otherwise compiled pages pollute the real `~/Obsidian/KDB/wiki/` and survive `rm -rf` of the sandbox. Treat `~/Obsidian/Vault-in-place-test-run/` as its own vault root (still "inside ~/Obsidian" per Joseph, just self-contained):
  ```
  ~/Obsidian/Vault-in-place-test-run/           ← vault_root
    KDB/
      KDB-Compiler-System-Prompt.md             ← copied from ~/Obsidian/KDB/
      state/   (manifest.json + pipelines.json written here)
      wiki/    (compiled pages land here — isolated)
      graph/   (GraphDB_Test — KDB_GRAPH_PATH)
    AIML/ , Value Investing/ , Daily Notes/ , …  ← Joseph's source content
  ```
  `pipelines.json`: one pipeline `id=vault-test`, `type=in-place`, `root=<sandbox abs>`, `excludes=["KDB/"]` (don't scan its own output), `force_noise=["Daily Notes/"]`, `file_types=[".md"]`. source_ids are sandbox-relative (e.g. `AIML/Claude/foo.md`). **Cleanup = `rm -rf ~/Obsidian/Vault-in-place-test-run/`** — everything (sources, wiki, state, graph) under one dir; production `~/Obsidian/KDB/` untouched.
- [ ] **Step 4: THE LIVE RUN (Joseph fires):**
  ```
  KDB_GRAPH_PATH=~/Obsidian/Vault-in-place-test-run/KDB/graph \
    kdb-orchestrate --pipeline vault-test \
    --vault-root ~/Obsidian/Vault-in-place-test-run \
    --model deepseek-v4-flash
  ```
  (`--state-root` defaults to `<vault_root>/KDB/state`.) **Observe:** sources enriched (frontmatter embedded in the sandbox files), signal→compiled→wiki pages under the sandbox's `KDB/wiki/`, `GraphDB_Test` has Entities + SUPPORTS, `Daily Notes/` enriched but `metadata_only` (not graphed), `last_orchestrate.json` summary. **Then pause + reassess** (per Joseph's [5]).

---

## Self-Review (run before advisor/panel)
1. **Spec coverage:** entry/registry · single rw conn · 3-branch routing · embed-during-enrich + post-embed-hash · produce-don't-write commit (apply→manifest→graph-sync) · deferred orphan-marking → finalize · fail-fast D-91-8/13 · `last_orchestrate.json` D-91-10. Reuses all four shipped foundations + monolith commit machinery.
2. **Open design points** (§ above) flagged for the panel: journaling granularity, scope-collision check.
3. **Live run is the gate** — Joseph fires; isolated sandbox keeps production pristine.
