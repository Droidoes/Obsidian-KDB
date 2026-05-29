# Plan 4 — Generalized scanner + `pipeline_id` manifest field

> **For agentic workers:** Use superpowers:executing-plans. Checkbox steps. **Largest regression surface of the six plans (29 `test_kdb_scan.py` tests) — run the full kdb_scan suite after every task.**

**Goal:** Generalize `kdb_scan` from hardcoded `KDB/raw/` to **any pipeline scope** (root + excludes + file_types), stamp each source with its `pipeline_id`, and scope the DELETED/MOVED passes per-pipeline (D-91-9). Backward-compatible: the existing raw behavior is preserved exactly.

**Key de-risking finding:** source_ids are **already vault-relative** — `_rel_to_vault` (kdb_scan.py:164-167) computes `abs_path.relative_to(raw_abs.parent.parent)` = relative to the vault root; `"KDB/raw/…"` is just what that yields when the root is `KDB/raw`. So generalizing to other roots is **swapping the relpath base to an explicit `vault_root`, NOT a source_id-scheme migration.** No production data migration needed; the orchestrator runs in the isolated sandbox (separate state + `GraphDB_Test`).

**Architecture:** A new scope-driven entry `scan_scope(root_abs, vault_root, *, pipeline_id, excludes, file_types)` that the orchestrator calls per selected pipeline. `walk_raw` generalizes to `walk_scope`; `classify` takes a `prior` already **filtered to the pipeline's sources** (by `pipeline_id`) so the DELETED pass only considers this pipeline (and MOVED only matches within it → D-91-9 per-root). `ScanEntry` + the manifest source record gain `pipeline_id`.

**Spec:** "Component: Scanner" (`pipeline_id` tag; DELETED pass = entries where `pipeline_id == selected` & absent on disk) + D-91-2 (`.md` only) + D-91-9 (per-root MOVED). Plan 4 of 6.

> **Deferred (flagged):** the scope-collision invariant from Plan 3 (no two pipelines producing the same vault-relative path) — validate it here once scope evaluation exists, OR keep deferred to Plan 6 wiring; decide at execution.

**Run tests:** `python -m pytest kdb_compiler/tests/test_kdb_scan.py -m "not live"` after EVERY task.

---

## File Structure
- **Modify** `kdb_compiler/types.py` — `ScanEntry` gains `pipeline_id: Optional[str] = None`.
- **Modify** `kdb_compiler/kdb_scan.py` — `walk_scope` (generalized walk + excludes + file_types), `_rel_to_vault(abs, vault_root)`, `pipeline_id` stamping, `scan_scope` entry point. Keep `walk_raw`/existing CLI as a back-compat wrapper.
- **Modify** `kdb_compiler/source_state_update.py` — manifest record gains `pipeline_id`.
- **Modify** `kdb_compiler/tests/test_kdb_scan.py` + `test_source_state_update.py` — new tests; verify existing stay green.

---

## Task 1: generalize walk + relpath base (backward-compatible)

**Files:** `kdb_compiler/kdb_scan.py:107,164`; Test `test_kdb_scan.py`.

- [ ] **Step 1: failing test** — walk an arbitrary root, source_ids vault-relative, `.md`-only, excludes + hidden dirs pruned.

```python
# append to test_kdb_scan.py
def test_walk_scope_arbitrary_root_vault_relative(tmp_path):
    from kdb_compiler import kdb_scan
    vault = tmp_path
    root = vault / "Vault-test" / "AIML"
    (root / "Claude").mkdir(parents=True)
    (root / "Claude" / "a.md").write_text("x", encoding="utf-8")
    (root / "b.txt").write_text("y", encoding="utf-8")          # non-.md: excluded
    (root / ".hidden").mkdir()
    (root / ".hidden" / "c.md").write_text("z", encoding="utf-8")  # hidden dir: pruned
    (root / "Daily Notes").mkdir()
    (root / "Daily Notes" / "d.md").write_text("w", encoding="utf-8")

    files, _sym, _err = kdb_scan.walk_scope(
        root, vault, file_types={".md"}, excludes=["Daily Notes/"])
    paths = sorted(f.rel_path for f in files)
    assert paths == ["Vault-test/AIML/Claude/a.md"]   # vault-relative; .txt/hidden/excluded gone
```

- [ ] **Step 2: run** → FAIL (`walk_scope` missing).
- [ ] **Step 3: implement** — in `kdb_scan.py`:
  - Add `_rel_to_vault(abs_path, vault_root)` overload (relative to `vault_root` directly). Keep the old 2-arg form working for `walk_raw` (or update `walk_raw` to pass `raw_abs.parent.parent` as `vault_root`).
  - Add `walk_scope(root_abs, vault_root, *, file_types, excludes)` modeled on `walk_raw` but: prune hidden dirs (`d.startswith('.')`) + excluded dirs (match against `excludes`); only keep files whose suffix ∈ `file_types`; compute rel via `_rel_to_vault(p, vault_root)`.
  - Refactor `walk_raw(raw_abs)` to delegate: `walk_scope(raw_abs, raw_abs.parent.parent, file_types=_MARKDOWN_EXTS, excludes=[])` (preserves today's behavior incl. `.markdown`/`.txt` for the legacy path — the `.md`-only restriction is applied via the pipeline's `file_types` in `scan_scope`, D-91-2).
- [ ] **Step 4: run** `test_kdb_scan.py` — new test PASS + all 29 existing PASS.
- [ ] **Step 5: commit** `feat(task91): Plan4 T1 — walk_scope generalized walk + vault-relative base`

---

## Task 2: `pipeline_id` on `ScanEntry` + manifest record

**Files:** `types.py` (`ScanEntry`), `kdb_scan.py` (`_entry_from` stamps it), `source_state_update.py` (record field); Tests.

- [ ] **Step 1: failing test** — a scanned entry carries `pipeline_id`; the manifest record persists it.

```python
def test_scan_entry_carries_pipeline_id(tmp_path):
    from kdb_compiler import kdb_scan
    vault = tmp_path
    root = vault / "P"; root.mkdir()
    (root / "a.md").write_text("x", encoding="utf-8")
    res = kdb_scan.scan_scope(root, vault, pipeline_id="test-pipe",
                              excludes=[], file_types={".md"}, prior={}, run_ctx=_run_ctx(vault))
    e = next(f for f in res.files if f.path == "P/a.md")
    assert e.pipeline_id == "test-pipe"
```
(Reuse/define a `_run_ctx` helper mirroring existing `test_kdb_scan.py` RunContext usage.)

- [ ] **Step 2: run** → FAIL.
- [ ] **Step 3: implement**
  - `types.py` `ScanEntry`: add `pipeline_id: Optional[str] = None` (defaulted → existing constructions unaffected).
  - `kdb_scan.py` `_entry_from(...)`: accept + set `pipeline_id`.
  - `source_state_update.py`: add `"pipeline_id"` to `_RECORD_FIELDS` (line ~40) and to `_build_record` (`"pipeline_id": file_entry.get("pipeline_id")`, ~line 76). Manifest schema note: additive nullable field; bump `SOURCE_STATE_SCHEMA_VERSION` only if the existing migration framework requires it (check — additive-nullable may not need a bump; mirror the #76 domain-field precedent).
- [ ] **Step 4: run** `test_kdb_scan.py` + `test_source_state_update.py` — new PASS, existing green.
- [ ] **Step 5: commit** `feat(task91): Plan4 T2 — pipeline_id on ScanEntry + manifest record`

---

## Task 3: pipeline-scoped classify + `scan_scope` entry point (D-91-9)

**Files:** `kdb_scan.py` (`classify` prior already filtered; `scan_scope` wrapper); Tests.

- [ ] **Step 1: failing tests** — (a) DELETED pass only flags THIS pipeline's absent sources; (b) a same-hash file in a different pipeline is NOT matched as MOVED (D-91-9).

```python
def test_scan_scope_deleted_scoped_to_pipeline(tmp_path):
    # prior has pipeline-A source 'A/gone.md' and pipeline-B 'B/keep.md';
    # scanning pipeline-A (root A/, prior filtered to pipeline_id=='A') must emit
    # DELETED only for A/gone.md, never B/keep.md.
    ...
def test_scan_scope_no_cross_pipeline_move(tmp_path):
    # current A/x.md (hash H) + prior B/y.md (hash H, pipeline B). Scanning A with
    # prior filtered to A must classify A/x.md as NEW, not MOVED-from-B.
    ...
```
(Fill in with the `scan_scope` API + `make`-style fixtures mirroring existing `test_kdb_scan.py`.)

- [ ] **Step 2: run** → FAIL.
- [ ] **Step 3: implement** `scan_scope(root_abs, vault_root, *, pipeline_id, excludes, file_types, prior, run_ctx) -> ScanResult`:
  1. `files, sym, err = walk_scope(root_abs, vault_root, file_types=file_types, excludes=excludes)`
  2. **filter `prior` to this pipeline:** `prior_scoped = {p: r for p, r in prior.items() if r.get("pipeline_id") == pipeline_id}` — so Phase-C MOVED only matches within the pipeline (D-91-9) and Phase-D DELETED only flags this pipeline's absent sources.
  3. `entries, ops = classify(files, prior_scoped)`; stamp `pipeline_id` on each entry (in `_entry_from` via Task 2, threading `pipeline_id` through `classify`/`scan_scope`).
  4. `build_scan_result(...)` → `ScanResult`.
- [ ] **Step 4: run** full `test_kdb_scan.py` — all green.
- [ ] **Step 5: commit** `feat(task91): Plan4 T3 — pipeline-scoped classify + scan_scope (D-91-9)`

---

## Task 4: full regression + scope-collision decision

- [ ] **Step 1:** `python -m pytest kdb_compiler/ graphdb_kdb/ -m "not live" -q -p no:warnings` → all green.
- [ ] **Step 2:** decide the deferred scope-collision check (Plan 3): implement here (cross-pipeline path overlap → `PipelineRegistryError`/scan error) OR keep deferred to Plan 6 with a one-line note. Record the call.
- [ ] **Step 3: commit** any cleanup.

---

## Self-Review
1. **Spec coverage:** generalized scope walk (D-91-2 file_types) + `pipeline_id` tag + scoped DELETED + per-root MOVED (D-91-9). source_id scheme unchanged (vault-relative — de-risked).
2. **Backward-compat:** `walk_raw` delegates to `walk_scope`; `ScanEntry.pipeline_id` defaulted; manifest field additive-nullable → existing 29 kdb_scan tests + source_state tests stay green (the gate at each task).
3. **Type consistency:** `pipeline_id` threads ScanEntry → manifest record → (Plan 6) DELETED scoping; `scan_scope` signature stable across Tasks 2-3.
