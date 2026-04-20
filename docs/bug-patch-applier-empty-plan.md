# Bug — `patch_applier.apply` crashes on empty / all-failed compile plans

**Status**: open · **Opened**: 2026-04-20 · **Discovered by**: Task #1 CLI smoke runs

---

## Symptom

Two reproducible crash paths in `patch_applier.apply()` (`kdb_compiler/patch_applier.py:361`) when the compile stage produces no usable per-source intents.

### Case A — empty `KDB/raw/`

```
FileNotFoundError: [Errno 2] No such file or directory: '…/state/compile_result.json'
  at _load_json(state_root / "compile_result.json")   # patch_applier.py:334
  called from apply()                                 # patch_applier.py:369
```

When `raw/` is empty the scanner has nothing to compile, `compiler.run_compile` is skipped (or produces an in-memory result that is never written to disk), and `apply()` then blindly reads `state/compile_result.json` from disk and blows up on first access.

### Case B — all sources fail to compile (e.g. missing `CLAUDE.md`)

```
PagePatchError: Compiled intent 'paper' has no PageRecord
  at build_page_patches(compile_result, next_manifest, run_ctx)
```

When every per-source compile errors out, `compile_result.compiled_sources` is empty but stale page intents still flow through `build_page_patches`, which cannot reconcile them against the fresh manifest and raises.

---

## Root cause (hypothesis)

`apply()` has two implicit preconditions that are not enforced:

1. **`state/compile_result.json` exists on disk** — it's read via `_load_json` at the top of the function. The orchestrator already holds `cr` in-memory at that point (`kdb_compile.py:151`), so the on-disk read is a redundant round-trip that fails when live-compile path skipped the write (dry-run, empty plan).
2. **`cr.compiled_sources` is non-empty** — `build_page_patches` assumes every intent has a manifest anchor. It has no "nothing to apply" fast-path.

---

## Repro

```bash
# Case A
rm -rf /tmp/empty-vault && mkdir -p /tmp/empty-vault/KDB/raw
python3 -m kdb_compiler.kdb_compile --vault-root /tmp/empty-vault

# Case B — vault with sources but no CLAUDE.md (so compile fails)
# (any vault where every source errors will reproduce)
```

Expected under Case A: orchestrator should print the seven stage banners and exit cleanly with "nothing to apply" rather than crash.

Expected under Case B: same — stage 6 should be a clean no-op when zero pages were compiled successfully; orchestrator already reports `sources_failed` count.

---

## Proposed fix (sketch — needs design gate)

Two independent changes, either of which closes the crash:

**Option 1 — pass `cr` in-memory, stop re-reading from disk.**
`apply()` already receives `next_manifest`; extend its signature to take `compile_result: dict` and drop `_load_json(state_root / "compile_result.json")`. Closes Case A. No behavior change in happy path because the orchestrator already has `cr` on hand.

**Option 2 — add an early-return in `apply()` when there is nothing to write.**
If `cr.compiled_sources` is empty and no manifest page was rekeyed/orphaned this run, return an `ApplyResult` with empty lists and `success=True`. Closes Case B.

Both are small; they address different preconditions. Recommended to land Option 1 first (removes redundant I/O, fixes Case A), then Option 2 as a separate change (semantic fast-path for zero-output runs).

---

## Out of scope

- The root cause of "missing `CLAUDE.md` → every compile errors" is a separate user-facing issue (better error messaging at the compile seam). Not tracked here.
- Scanner behavior when `raw/` is empty is correct — `to_compile` is empty, so no LLM call. The bug is purely downstream in `apply()`.

## Links

- Discovered while smoke-testing commit `b377bfc` (Task #1 — progress banners).
- Related code: `kdb_compiler/patch_applier.py:334, 361-369`; `kdb_compiler/kdb_compile.py:183-190`.
