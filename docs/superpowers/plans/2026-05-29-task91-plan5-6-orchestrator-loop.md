# Plan 5+6 — `kdb-orchestrate` loop (Pass-1 egress wiring + the E2E conductor)

> **For agentic workers:** Use superpowers:subagent-driven-development or executing-plans. **Capstone integration** — high effort. Goes through advisor + 5-model panel review BEFORE execution (per the agreed path). The final task is the **live run Joseph fires**.

**Goal:** Build `kdb-orchestrate` — the end-to-end conductor that wires the four shipped foundations (`compile_source`, `detect_orphans`, pipeline registry, `scan_scope`) into a per-source loop on a single shared read-write GraphDB connection, ending in the first live `feeder→Pass-1→Pass-2→GraphDB` run on the test sandbox.

**Architecture:** New module `kdb_compiler/kdb_orchestrate.py`. Entry: registry → select pipeline → load scope → open ONE read-write `GraphDB` → `scan_scope` → per-source loop → finalize. The loop reuses existing machinery per-source (`enrich_one`, `compile_source`, `build_source_state_update`, `patch_applier.apply`, `apply_compile_result(detect_orphans=False)`); finalize runs `detect_orphans()` once → `kdb-clean orphans` → `last_orchestrate.json`. Produce-don't-write + embed-during-enrich + deferred-orphan-marking + fail-fast (D-91-8/13) all per the spec.

**Spec:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` (Orchestrator loop + Pass-2 ingress + Pass-1 egress). **Decisions:** D-91-1..14; embed-during-enrich + post-embed-hash (2026-05-29); produce-don't-write + accept cross-source-wiki trade-off (panel forks). Plans 5+6 of 6.

**Run tests with `-m "not live"`.** The final live run is Joseph-fired on `~/Obsidian/Vault-in-place-test-run/` with an isolated `.kdb-state/` + `GraphDB_Test`.

---

## ⚠️ Design points for advisor + panel review (resolve before/at execution)

1. **Per-source journaling / replayability granularity.** The monolith writes ONE run journal (`state/runs/<run_id>.json`) + archives one batch `compile_result.json` sidecar; `graphdb-kdb rebuild` replays journals. The per-source loop graph-syncs + commits the manifest **per source** (for read-after-write + resume), but the rebuild safety net needs the per-source `cr`s to be replayable. **Lean:** accumulate per-source `cr`s into one run-level `compile_result` and write the journal + sidecar **once at finalize** (reuses the existing journal/rebuild machinery unchanged). **Trade-off the panel should weigh:** a crash *mid-loop, before finalize* leaves committed-but-not-yet-journaled sources — the live graph has them (per-source committed) so no rebuild is needed unless the graph is *also* lost; that double-fault is the residual gap. Alternative: append a per-source journal entry inside the loop (more machinery). **Decide with the panel.**
2. **`scan_scope` prior source** — the orchestrator loads the unified manifest (`load_manifest_sources`) as `prior`; `scan_scope` filters it by `pipeline_id`. Confirm the manifest record exposes `pipeline_id` for the filter (Plan 4 T2 added it to the seed record — verify older records degrade gracefully).
3. **Scope-collision check (deferred from Plans 3-4)** — validate at orchestrator startup once all pipelines are loaded (cross-pipeline path overlap → error), OR keep deferred. Decide.

---

## File Structure
- **Modify** `kdb_compiler/ingestion/enrich.py` — `EnrichResult` gains `body` + `post_embed_hash`; `enrich_one` returns them (recompute whole-file hash right after embed).
- **Create** `kdb_compiler/kdb_orchestrate.py` — the conductor (`run()`, per-source `_commit_source`, `_finalize`, CLI `main`).
- **Modify** `pyproject.toml` — `kdb-orchestrate` console script.
- **Create** `kdb_compiler/tests/test_kdb_orchestrate.py` — routing, fail-fast, finalize, summary (all non-live, model faked).

---

## Task 1 (Plan 5): `enrich_one` egress — return body + post-embed hash

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
