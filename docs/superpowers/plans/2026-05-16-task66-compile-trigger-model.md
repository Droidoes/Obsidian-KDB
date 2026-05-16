# Task #66 — Compile-Trigger Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `error_retry` side-channel from `kdb_scan.py` and replace compile eligibility with the honest invariant `compile iff current_hash != last_compiled_hash`.

**Architecture:** A raw source carries two independent facts — its current content hash, and the hash last *successfully* processed (`last_compiled_hash`). The scan carries the prior `last_compiled_hash` onto every `ScanEntry` as `compiled_hash`; `to_compile`/`to_skip` partition purely on `current_hash != compiled_hash`, never on `action`. `last_compiled_hash` advances only on successful processing: `apply_compile_result` for LLM-compiled text sources, `apply_scan_reconciliation` for metadata-only binaries. `compile_state` becomes informational — no code path reads it for a decision. A one-shot migration backfills the field on the existing manifest.

**Tech Stack:** Python 3, `dataclasses`, `jsonschema` (Draft 2020-12), `pytest`. Run tests with `.venv/bin/python -m pytest` — bare `python3` lacks `kuzu` and produces spurious failures.

**Authoritative spec:** `docs/task66-compile-trigger-model-blueprint.md` (D46, Q1–Q6). This plan implements it; do not re-litigate the design.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `kdb_compiler/types.py` | `ScanEntry` dataclass | Add required `compiled_hash` field |
| `kdb_compiler/schemas/last_scan.schema.json` | `last_scan.json` shape | Add `compiled_hash` to `scanEntry` (required, nullable) |
| `kdb_compiler/kdb_scan.py` | Scan + eligibility | Carry `compiled_hash`; rewrite `to_compile`/`to_skip`; delete `error_retry` |
| `kdb_compiler/manifest_update.py` | Manifest writes | Seed + advance `last_compiled_hash` |
| `kdb_compiler/validate_last_scan.py` | `last_scan.json` validation | Rewrite `to_compile`/`to_skip` rules around the hash comparison |
| `docs/CODEBASE_OVERVIEW.md` | Decision ledger | D46 entry |
| `docs/TASKS.md` | Task ledger | Mark #66 done at end |
| `scripts/migrate_task66_compiled_hash.py` (new) | One-shot migration | Q2 backfill + Q4 EP1 repair |

Tests live in `kdb_compiler/tests/test_kdb_scan.py`, `test_manifest_update.py`, `test_validate_last_scan.py`.

---

## Task 1: `ScanEntry.compiled_hash` field + schema

**Files:**
- Modify: `kdb_compiler/types.py:28-60` (`ScanEntry`)
- Modify: `kdb_compiler/schemas/last_scan.schema.json` (`scanEntry` def, `$defs`)
- Test: `kdb_compiler/tests/test_kdb_scan.py`, `kdb_compiler/tests/test_validate_last_scan.py`

`compiled_hash` is **required-but-nullable** (Q3): present on every entry, value is the prior `last_compiled_hash` string or `null`, never absent. In the dataclass it is a field with **no default** (positionally required), placed before the defaulted `previous_*` fields. In `to_dict()` it is emitted unconditionally.

- [ ] **Step 1: Write the failing test (dataclass)**

Add to `kdb_compiler/tests/test_kdb_scan.py`:

```python
def test_scan_entry_to_dict_always_includes_compiled_hash():
    from kdb_compiler.types import ScanEntry
    # never-compiled source: compiled_hash is null, still present
    e = ScanEntry(
        path="KDB/raw/a.md", action="NEW",
        current_hash="sha256:" + "a" * 64, current_mtime=1.0,
        size_bytes=10, file_type="markdown", is_binary=False,
        compiled_hash=None,
    )
    assert "compiled_hash" in e.to_dict()
    assert e.to_dict()["compiled_hash"] is None
    # previously-compiled source: carries the prior hash
    e2 = ScanEntry(
        path="KDB/raw/b.md", action="UNCHANGED",
        current_hash="sha256:" + "b" * 64, current_mtime=1.0,
        size_bytes=10, file_type="markdown", is_binary=False,
        compiled_hash="sha256:" + "c" * 64,
        previous_hash="sha256:" + "b" * 64, previous_mtime=0.5,
    )
    assert e2.to_dict()["compiled_hash"] == "sha256:" + "c" * 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_scan.py::test_scan_entry_to_dict_always_includes_compiled_hash -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'compiled_hash'`.

- [ ] **Step 3: Add the field to `ScanEntry`**

In `kdb_compiler/types.py`, change the `ScanEntry` field block (currently `is_binary` then `previous_hash`) to insert `compiled_hash` between them with no default:

```python
    path: str                              # POSIX relative to vault: "KDB/raw/foo.md"
    action: ScanAction
    current_hash: str                      # "sha256:<64-hex>"
    current_mtime: float                   # unix seconds; advisory
    size_bytes: int
    file_type: FileType
    is_binary: bool
    compiled_hash: Optional[str]           # prior last_compiled_hash, or None — required-but-nullable (Q3)
    previous_hash: Optional[str] = None    # CHANGED/UNCHANGED/MOVED
    previous_mtime: Optional[float] = None # CHANGED/UNCHANGED/MOVED
    previous_path: Optional[str] = None    # MOVED only
```

In `ScanEntry.to_dict()`, add `compiled_hash` to the always-present block (it is emitted even when `None`):

```python
        d: dict[str, Any] = {
            "path": self.path,
            "action": self.action,
            "current_hash": self.current_hash,
            "current_mtime": self.current_mtime,
            "size_bytes": self.size_bytes,
            "file_type": self.file_type,
            "is_binary": self.is_binary,
            "compiled_hash": self.compiled_hash,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_scan.py::test_scan_entry_to_dict_always_includes_compiled_hash -v`
Expected: PASS.

- [ ] **Step 5: Update the schema**

In `kdb_compiler/schemas/last_scan.schema.json`, add a `$defs` entry after `hashString`:

```json
    "hashOrNull": { "type": ["string", "null"], "pattern": "^sha256:[a-fA-F0-9]{64}$" },
```

In the `scanEntry` def: add `"compiled_hash"` to the `required` array, and add the property:

```json
        "compiled_hash":  { "$ref": "#/$defs/hashOrNull" },
```

(Place it after `"is_binary"` in `properties`. JSON-Schema `pattern` applies only to string instances, so `null` passes.)

- [ ] **Step 6: Write the failing schema test**

Add to `kdb_compiler/tests/test_validate_last_scan.py` (use the file's existing valid-payload helper/fixture; if the helper builds a `files[]` entry, this test asserts the new requirement):

```python
def test_scan_entry_without_compiled_hash_is_rejected():
    from kdb_compiler.validate_last_scan import validate
    payload = _minimal_valid_scan()          # existing test helper
    del payload["files"][0]["compiled_hash"]  # required-but-nullable: absence is invalid
    errors = validate(payload)
    assert any("compiled_hash" in e for e in errors)
```

If `test_validate_last_scan.py` has no `_minimal_valid_scan` helper, add one that returns a schema-valid single-file payload including `"compiled_hash": None`.

- [ ] **Step 7: Run it, verify fail-then-pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_validate_last_scan.py -v`
Expected: the new test FAILs first if the helper omits `compiled_hash`; once the helper/fixtures include `compiled_hash`, the deletion-test PASSes. Update every fixture/helper in `test_validate_last_scan.py` so each `files[]` entry carries `compiled_hash` (string or `null`).

- [ ] **Step 8: Commit**

```bash
git add kdb_compiler/types.py kdb_compiler/schemas/last_scan.schema.json kdb_compiler/tests/test_kdb_scan.py kdb_compiler/tests/test_validate_last_scan.py
git commit -m "feat(task66): ScanEntry.compiled_hash — required-but-nullable field + schema"
```

---

## Task 2: `kdb_scan.py` — carry `compiled_hash`, rewrite eligibility, delete `error_retry`

**Files:**
- Modify: `kdb_compiler/kdb_scan.py` — `load_manifest_sources` (197-204), `classify` (210-283), `_entry_from` (286-305), `build_scan_result` (316-374), `scan` (404-413)
- Test: `kdb_compiler/tests/test_kdb_scan.py`

Eligibility becomes a pure two-field comparison. The scan sources each entry's `compiled_hash` from the prior manifest source record: for UNCHANGED/CHANGED from `prior[path]`, for MOVED from `prior[previous_path]`, for NEW it is `None`.

- [ ] **Step 1: Write the failing tests**

Add to `kdb_compiler/tests/test_kdb_scan.py`. These cover the four §2 cases plus `error_retry` removal and the MOVED rule. Use the file's existing scan-harness helpers (a temp vault with `KDB/raw/` + `KDB/state/manifest.json`); if helpers differ, adapt the construction but keep the assertions.

```python
def test_unchanged_already_compiled_is_skipped(tmp_path):
    # case 1: current hash == last_compiled_hash -> skip
    vault = _make_vault(tmp_path, raw={"a.md": "hello"})
    h = _sha256_text("hello")
    _write_manifest(vault, sources={"KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=h)})
    res = scan(vault, write=False)
    assert res.to_skip == ["KDB/raw/a.md"]
    assert res.to_compile == []


def test_unchanged_not_yet_compiled_is_compiled(tmp_path):
    # case 2: hash unchanged but never successfully compiled -> compile
    vault = _make_vault(tmp_path, raw={"a.md": "hello"})
    h = _sha256_text("hello")
    _write_manifest(vault, sources={"KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=None)})
    res = scan(vault, write=False)
    assert res.to_compile == ["KDB/raw/a.md"]
    assert res.to_skip == []


def test_changed_with_a_prior_compiled_hash_is_compiled(tmp_path):
    # case 3: content changed; an older hash was compiled -> compile
    vault = _make_vault(tmp_path, raw={"a.md": "new content"})
    old = _sha256_text("old content")
    _write_manifest(vault, sources={"KDB/raw/a.md": _src_rec(hash=old, last_compiled_hash=old)})
    res = scan(vault, write=False)
    assert res.to_compile == ["KDB/raw/a.md"]
    entry = next(e for e in res.files if e.path == "KDB/raw/a.md")
    assert entry.action == "CHANGED"
    assert entry.compiled_hash == old


def test_new_file_is_compiled(tmp_path):
    # case 4: never seen -> compiled_hash None -> compile
    vault = _make_vault(tmp_path, raw={"a.md": "hello"})
    _write_manifest(vault, sources={})
    res = scan(vault, write=False)
    assert res.to_compile == ["KDB/raw/a.md"]
    entry = next(e for e in res.files if e.path == "KDB/raw/a.md")
    assert entry.compiled_hash is None


def test_error_state_does_not_force_recompile(tmp_path):
    # error_retry is GONE: compile_state=="error" but hash already compiled -> skip
    vault = _make_vault(tmp_path, raw={"a.md": "hello"})
    h = _sha256_text("hello")
    _write_manifest(vault, sources={
        "KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=h, compile_state="error"),
    })
    res = scan(vault, write=False)
    assert res.to_skip == ["KDB/raw/a.md"]
    assert res.to_compile == []


def test_moved_with_compiled_content_is_skipped(tmp_path):
    # Q5: pure rename of already-compiled content -> to_skip; record still rekeys
    vault = _make_vault(tmp_path, raw={"sub/b.md": "hello"})
    h = _sha256_text("hello")
    _write_manifest(vault, sources={"KDB/raw/a.md": _src_rec(hash=h, last_compiled_hash=h)})
    res = scan(vault, write=False)
    moved = next(e for e in res.files if e.action == "MOVED")
    assert moved.compiled_hash == h          # sourced from prior record at previous_path
    assert res.to_skip == ["KDB/raw/sub/b.md"]
    assert res.to_compile == []
```

Add `_src_rec` / `_sha256_text` helpers if absent:

```python
def _sha256_text(text: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _src_rec(*, hash, last_compiled_hash, compile_state="compiled"):
    return {
        "hash": hash, "mtime": 0.0, "size_bytes": 1,
        "file_type": "markdown", "is_binary": False,
        "compile_state": compile_state, "last_compiled_hash": last_compiled_hash,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_scan.py -k "compiled or error_state or moved_with" -v`
Expected: FAIL — `to_compile`/`to_skip` still computed from `action`; `compiled_hash` not yet populated.

- [ ] **Step 3: Carry `last_compiled_hash` in the manifest projection**

In `kdb_compiler/kdb_scan.py`, `load_manifest_sources`, change the projection dict — replace the `compile_state` line with `last_compiled_hash`:

```python
        out[sid] = {
            "hash": rec.get("hash"),
            "mtime": rec.get("mtime"),
            "size_bytes": rec.get("size_bytes"),
            "file_type": rec.get("file_type"),
            "is_binary": rec.get("is_binary"),
            "last_compiled_hash": rec.get("last_compiled_hash"),
        }
```

- [ ] **Step 4: Thread `compiled_hash` through `_entry_from` and `classify`**

Change `_entry_from` to take a required `compiled_hash` argument:

```python
def _entry_from(
    cur: _RawFile,
    action: str,
    prev_hash: Any,
    prev_mtime: Any,
    compiled_hash: str | None,
    *,
    previous_path: str | None = None,
) -> ScanEntry:
    return ScanEntry(
        path=cur.rel_path,
        action=action,  # type: ignore[arg-type]
        current_hash=cur.hash,
        current_mtime=cur.mtime,
        size_bytes=cur.size_bytes,
        file_type=cur.file_type,
        is_binary=cur.is_binary,
        compiled_hash=compiled_hash if isinstance(compiled_hash, str) else None,
        previous_hash=prev_hash if isinstance(prev_hash, str) else None,
        previous_mtime=float(prev_mtime) if isinstance(prev_mtime, (int, float)) else None,
        previous_path=previous_path,
    )
```

In `classify`, update the three `_entry_from` call sites:

Phase B (both branches) — pass `prev.get("last_compiled_hash")`:
```python
        if prev_hash == cur.hash:
            files.append(_entry_from(cur, "UNCHANGED", prev_hash, prev_mtime,
                                     prev.get("last_compiled_hash")))
        else:
            files.append(_entry_from(cur, "CHANGED", prev_hash, prev_mtime,
                                     prev.get("last_compiled_hash")))
```

Phase C (MOVED) — source from the prior record at `old_path`:
```python
        files.append(_entry_from(
            cur, "MOVED",
            prev.get("hash"), prev.get("mtime"),
            prev.get("last_compiled_hash"),
            previous_path=old_path,
        ))
```

Phase D (NEW) — never compiled, `None`:
```python
        files.append(_entry_from(cur, "NEW", None, None, None))
```

- [ ] **Step 5: Rewrite `build_scan_result` — delete `error_retry`**

Replace the `error_retry` / `to_compile` / `to_skip` block (lines 327-343) with the hash rule, and **remove the `prior_sources` parameter** (it is now dead):

```python
def build_scan_result(
    *,
    run_ctx: RunContext,
    raw_root_rel: str,
    files: list[ScanEntry],
    reconcile_ops: list[ReconcileOp],
    errors: list[ErrorEntry],
    skipped_symlinks: list[SkippedSymlinkEntry],
    settings: SettingsSnapshot,
) -> ScanResult:
    # Task #66 (D46): compile eligibility is one honest comparison.
    # A file compiles iff its current content hash differs from the hash
    # last successfully compiled. compile_state plays no part.
    to_compile = sorted(e.path for e in files if e.current_hash != e.compiled_hash)
    to_skip = sorted(e.path for e in files if e.current_hash == e.compiled_hash)
```

(Keep the `counts` / `summary` / `ScanResult(...)` body below unchanged.)

In `scan`, drop the `prior_sources=prior` kwarg from the `build_scan_result(...)` call.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_scan.py -v`
Expected: PASS. Update any pre-existing test that constructed `ScanEntry` directly or called `build_scan_result(prior_sources=...)` — add `compiled_hash`, drop `prior_sources`.

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/kdb_scan.py kdb_compiler/tests/test_kdb_scan.py
git commit -m "feat(task66): hash-based compile eligibility — delete error_retry kludge"
```

---

## Task 3: `manifest_update.py` — seed + advance `last_compiled_hash`

**Files:**
- Modify: `kdb_compiler/manifest_update.py` — `_seed_source_record` (177-199), `apply_scan_reconciliation` (286-340 CHANGED branch), `apply_compile_result` (483-526 + stub 486-496)
- Test: `kdb_compiler/tests/test_manifest_update.py`

`last_compiled_hash` advances **only on successful processing of the current content** (D46): `apply_compile_result` for LLM-compiled text sources; `apply_scan_reconciliation` for `is_binary` sources (whose metadata recording *is* their processing — Q6). It is never advanced by the scan for a text source, and never advanced for an error-marked / missing source.

- [ ] **Step 1: Write the failing tests**

Add to `kdb_compiler/tests/test_manifest_update.py` (adapt to the file's existing fixture helpers):

```python
def test_seed_record_has_last_compiled_hash_none_for_markdown():
    from kdb_compiler.manifest_update import _seed_source_record
    fe = {"path": "KDB/raw/a.md", "current_hash": "sha256:" + "a" * 64,
          "current_mtime": 1.0, "size_bytes": 5, "file_type": "markdown",
          "is_binary": False}
    rec = _seed_source_record(fe, _ctx())
    assert rec["last_compiled_hash"] is None


def test_seed_record_sets_last_compiled_hash_for_binary():
    from kdb_compiler.manifest_update import _seed_source_record
    h = "sha256:" + "b" * 64
    fe = {"path": "KDB/raw/x.png", "current_hash": h, "current_mtime": 1.0,
          "size_bytes": 5, "file_type": "binary", "is_binary": True}
    rec = _seed_source_record(fe, _ctx())
    # Q6: metadata recording IS the binary's successful processing
    assert rec["last_compiled_hash"] == h


def test_apply_compile_result_advances_last_compiled_hash():
    # a successful compile sets last_compiled_hash to the compiled source hash
    manifest = _manifest_with_source("KDB/raw/a.md", hash="sha256:" + "a" * 64,
                                     last_compiled_hash=None)
    last_scan = _last_scan(to_compile=["KDB/raw/a.md"],
                           current_hash="sha256:" + "a" * 64)
    cr = _compile_result_for("KDB/raw/a.md")
    apply_compile_result(manifest, cr, last_scan, _ctx())
    assert manifest["sources"]["KDB/raw/a.md"]["last_compiled_hash"] == "sha256:" + "a" * 64


def test_error_marked_source_does_not_advance_last_compiled_hash():
    # source expected to compile but missing from compile_result -> stays eligible
    manifest = _manifest_with_source("KDB/raw/a.md", hash="sha256:" + "a" * 64,
                                     last_compiled_hash=None)
    last_scan = _last_scan(to_compile=["KDB/raw/a.md"],
                           current_hash="sha256:" + "a" * 64)
    cr = _compile_result_empty()                      # no compiled_sources
    apply_compile_result(manifest, cr, last_scan, _ctx())
    rec = manifest["sources"]["KDB/raw/a.md"]
    assert rec["compile_state"] == "error"
    assert rec["last_compiled_hash"] is None          # not advanced -> eligible next scan


def test_changed_binary_advances_last_compiled_hash_in_scan_reconciliation():
    # Q6: a binary whose content changed gets its hash advanced by the scan
    h_old, h_new = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    manifest = _manifest_with_source("KDB/raw/x.png", hash=h_old,
                                     last_compiled_hash=h_old, is_binary=True)
    last_scan = {"files": [{"path": "KDB/raw/x.png", "action": "CHANGED",
                            "current_hash": h_new, "current_mtime": 2.0,
                            "size_bytes": 9, "file_type": "binary",
                            "is_binary": True, "compiled_hash": h_old,
                            "previous_hash": h_old, "previous_mtime": 1.0}],
                 "to_reconcile": []}
    apply_scan_reconciliation(manifest, last_scan, _ctx())
    assert manifest["sources"]["KDB/raw/x.png"]["last_compiled_hash"] == h_new
```

If the test file lacks `_manifest_with_source` / `_last_scan` / `_compile_result_*` helpers, add minimal ones, or adapt to the existing harness. The behavioural assertions are the contract — keep them.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_manifest_update.py -k "last_compiled_hash" -v`
Expected: FAIL — `KeyError: 'last_compiled_hash'`.

- [ ] **Step 3: Seed `last_compiled_hash` in `_seed_source_record`**

In `_seed_source_record`, add the field after `compile_count` (binary → current hash per Q6, markdown → `None`):

```python
        "compile_state": "metadata_only" if file_entry.get("is_binary") else "compiled",
        "compile_count": 0,
        "last_compiled_hash": (
            file_entry["current_hash"] if file_entry.get("is_binary") else None
        ),
```

- [ ] **Step 4: Advance it for changed binaries in `apply_scan_reconciliation`**

In the `CHANGED` branch, after `rec["last_run_id"] = ctx.run_id`, add the Q6 binary advance:

```python
            rec["last_seen_at"] = ctx.started_at
            rec["last_run_id"] = ctx.run_id
            # Task #66 (Q6): a binary has no LLM compile step — recording its
            # changed metadata IS its successful processing.
            if fe.get("is_binary"):
                rec["last_compiled_hash"] = fe["current_hash"]
```

(MOVED needs nothing: a MOVED match is hash-identical content, so the popped record's `last_compiled_hash` is already correct. UNCHANGED needs nothing.)

- [ ] **Step 5: Advance it on successful compile in `apply_compile_result`**

In the per-source loop, after `rec["last_run_id"] = ctx.run_id` (line 502), add:

```python
        rec["last_compiled_at"] = ctx.started_at
        rec["last_run_id"] = ctx.run_id
        # Task #66 (D46): record the hash that was just successfully compiled.
        rec["last_compiled_hash"] = source_hash
```

In the stub-record dict (the `if rec is None:` branch, lines 486-496), add the field:

```python
                "last_run_id": ctx.run_id, "compile_state": "compiled",
                "compile_count": 0, "last_compiled_hash": source_hash,
                "summary_page": None, "outputs_created": [],
```

(The error-mark block at lines 528-535 is left untouched — it must **not** advance `last_compiled_hash`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_manifest_update.py -v`
Expected: PASS. Update any pre-existing test asserting an exact `_seed_source_record` / stub dict shape to include `last_compiled_hash`.

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/manifest_update.py kdb_compiler/tests/test_manifest_update.py
git commit -m "feat(task66): seed + advance last_compiled_hash on successful processing"
```

---

## Task 4: `validate_last_scan.py` — rewrite `to_compile`/`to_skip` rules

**Files:**
- Modify: `kdb_compiler/validate_last_scan.py` — module docstring (1-30), `_check_semantics` (67-233)
- Test: `kdb_compiler/tests/test_validate_last_scan.py`

`to_compile`/`to_skip` are validated purely against `current_hash != compiled_hash`, never against `action`. An UNCHANGED *or* MOVED file may legitimately sit in either set. Keep duplicate detection, disjointness, reconcile-op checks, and summary counts unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `kdb_compiler/tests/test_validate_last_scan.py`:

```python
def test_unchanged_file_in_to_compile_is_valid_when_hashes_differ():
    # case 2: UNCHANGED action, never compiled -> belongs in to_compile
    payload = _minimal_valid_scan()
    f = payload["files"][0]
    f["action"] = "UNCHANGED"
    f["previous_hash"] = f["current_hash"]
    f["previous_mtime"] = 0.5
    f["compiled_hash"] = None                     # current_hash != compiled_hash
    payload["to_compile"] = [f["path"]]
    payload["to_skip"] = []
    payload["summary"]["unchanged"] = 1
    payload["summary"]["new"] = 0
    assert validate(payload) == []


def test_file_misclassified_into_to_skip_is_rejected():
    # current_hash != compiled_hash but listed in to_skip -> error
    payload = _minimal_valid_scan()
    f = payload["files"][0]
    f["compiled_hash"] = None                     # never compiled
    payload["to_compile"] = []
    payload["to_skip"] = [f["path"]]
    errors = validate(payload)
    assert any("to_skip" in e for e in errors)


def test_file_misclassified_into_to_compile_is_rejected():
    # current_hash == compiled_hash but listed in to_compile -> error
    payload = _minimal_valid_scan()
    f = payload["files"][0]
    f["action"] = "UNCHANGED"
    f["previous_hash"] = f["current_hash"]
    f["previous_mtime"] = 0.5
    f["compiled_hash"] = f["current_hash"]        # already compiled
    payload["to_compile"] = [f["path"]]
    payload["to_skip"] = []
    payload["summary"]["unchanged"] = 1
    payload["summary"]["new"] = 0
    errors = validate(payload)
    assert any("to_compile" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_validate_last_scan.py -k "to_compile or to_skip or misclassified" -v`
Expected: FAIL — current code rejects UNCHANGED-in-to_compile only by action heuristic and does not check the hash rule.

- [ ] **Step 3: Rewrite the semantic checks**

In `_check_semantics`, build a per-path hash index alongside `status_by_path`, and replace the action-based `to_compile`/`to_skip` membership + completeness blocks (lines 98-152) with the hash rule. Replace this region:

```python
    # --- files[] indexing + duplicate detection ---
    status_by_path: dict[str, str] = {}
    action_counter: Counter[str] = Counter()
    dup_paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        action = entry.get("action")
        if not isinstance(path, str) or not isinstance(action, str):
            continue
        if path in status_by_path:
            dup_paths.append(path)
        status_by_path[path] = action
        action_counter[action] += 1
```

with (adds a `hashes_by_path` index — current vs compiled):

```python
    # --- files[] indexing + duplicate detection ---
    status_by_path: dict[str, str] = {}
    hashes_by_path: dict[str, tuple[Any, Any]] = {}   # path -> (current_hash, compiled_hash)
    action_counter: Counter[str] = Counter()
    dup_paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        action = entry.get("action")
        if not isinstance(path, str) or not isinstance(action, str):
            continue
        if path in status_by_path:
            dup_paths.append(path)
        status_by_path[path] = action
        hashes_by_path[path] = (entry.get("current_hash"), entry.get("compiled_hash"))
        action_counter[action] += 1
```

Then replace the to_compile membership loop (the `elif s not in ("NEW", "CHANGED", "UNCHANGED")` block) so it checks the hash rule:

```python
    if isinstance(to_compile, list):
        if len(to_compile) != len(set(to_compile)):
            errors.append("[$.to_compile] contains duplicate paths")
        for p in to_compile:
            if not isinstance(p, str):
                continue
            if p not in status_by_path:
                errors.append(f"[$.to_compile] path not found in files[]: {p!r}")
                continue
            cur, comp = hashes_by_path.get(p, (None, None))
            if cur == comp:
                errors.append(
                    f"[$.to_compile] {p!r} has current_hash == compiled_hash "
                    "(already compiled — belongs in to_skip)"
                )
```

Replace the to_skip membership loop (the `elif s != "UNCHANGED"` block) similarly:

```python
    if isinstance(to_skip, list):
        if len(to_skip) != len(set(to_skip)):
            errors.append("[$.to_skip] contains duplicate paths")
        for p in to_skip:
            if not isinstance(p, str):
                continue
            if p not in status_by_path:
                errors.append(f"[$.to_skip] path not found in files[]: {p!r}")
                continue
            cur, comp = hashes_by_path.get(p, (None, None))
            if cur != comp:
                errors.append(
                    f"[$.to_skip] {p!r} has current_hash != compiled_hash "
                    "(not yet compiled — belongs in to_compile)"
                )
```

Replace the completeness block (the `for p, s in sorted(status_by_path.items())` loop) with a hash-partition completeness check:

```python
    # --- completeness: every file is in exactly one of to_compile / to_skip,
    # partitioned purely by current_hash != compiled_hash (Task #66 D46). ---
    if isinstance(to_compile, list) and isinstance(to_skip, list):
        to_compile_set = {p for p in to_compile if isinstance(p, str)}
        to_skip_set = {p for p in to_skip if isinstance(p, str)}
        for p in sorted(status_by_path):
            cur, comp = hashes_by_path.get(p, (None, None))
            should_compile = cur != comp
            in_compile = p in to_compile_set
            in_skip = p in to_skip_set
            if should_compile and not in_compile:
                errors.append(f"[$.to_compile] missing eligible file {p!r}")
            if not should_compile and not in_skip:
                errors.append(f"[$.to_skip] missing skippable file {p!r}")
```

(The disjointness check, the duplicate-path loop, the reconcile-ops block, and the summary-count block all stay unchanged.)

- [ ] **Step 4: Update the module docstring**

In `validate_last_scan.py` lines 8-21, replace the `to_compile`/`to_skip` bullet group describing the action-based rules with:

```
    2. Semantic — cross-field invariants JSON-Schema can't express cleanly:
         * to_compile == { f : current_hash != compiled_hash }  (Task #66 D46)
         * to_skip    == { f : current_hash == compiled_hash }, the complement
         * to_compile / to_skip are disjoint; their union is files[]
         * action (NEW/CHANGED/UNCHANGED/MOVED) describes content-vs-last-seen
           ONLY — it never decides eligibility
         * Every MOVED in files[] has a matching MOVED reconcile op (and inverse)
         * DELETED paths in to_reconcile must NOT appear in files[]
         * summary counts equal actual array counts
         * No duplicate paths in files[], to_compile, to_skip
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_validate_last_scan.py -v`
Expected: PASS. Update any pre-existing test that relied on the action-based rejection messages (e.g. `"expected UNCHANGED"`).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/validate_last_scan.py kdb_compiler/tests/test_validate_last_scan.py
git commit -m "feat(task66): validate_last_scan partitions to_compile/to_skip by hash, not action"
```

---

## Task 5: Decision ledger + task ledger

**Files:**
- Modify: `docs/CODEBASE_OVERVIEW.md` — decision ledger (after D45, line ~444)
- Modify: `docs/TASKS.md` — #66 row

- [ ] **Step 1: Add the D46 ledger entry**

Append after the D45 row in `docs/CODEBASE_OVERVIEW.md`:

```markdown
| D46 | 2026-05-16 (Task #66) | **Compile eligibility is `current_hash != last_compiled_hash`.** A new source field `last_compiled_hash` records the hash last *successfully processed*; it advances **only on successful processing of the current content** — `apply_compile_result` for LLM-compiled text sources, `apply_scan_reconciliation` for metadata-only binaries (Q6) — never by the scan merely *seeing* a changed text source, never for an error-marked / missing source. The scan carries the prior value onto every `ScanEntry` as `compiled_hash` (required-but-nullable); `to_compile`/`to_skip` partition purely on the hash comparison, never on `action`. The `error_retry` side-channel is removed; `compile_state` stays informational but no longer affects eligibility. Force-recompile = a real source-content change; no manifest flag, no `--force`; content hash only, never mtime. See `docs/task66-compile-trigger-model-blueprint.md`. | `manifest.hash` advances during the *scan* (it means "last hash seen"), so reading it back as "last hash compiled" conflated two facts: a failed compile left `hash` already advanced, so the file read UNCHANGED next scan despite never compiling. `error_retry` was a patch over that conflation — and it made force-recompile possible by hand-editing `compile_state: "error"` into the manifest. Splitting the two hashes makes the trigger one honest comparison and removes the manifest-editable force path. |
```

- [ ] **Step 2: Check for an `error_retry` description in the scan-pipeline section**

Run: `grep -n "error_retry\|to_compile\|compile_state" docs/CODEBASE_OVERVIEW.md`
If any prose section (not the D46 row, not the graphdb `ingest_state` rename note) describes eligibility via `error_retry` or `compile_state`, amend it to the D46 rule. If none exists, no further edit.

- [ ] **Step 3: Commit**

```bash
git add docs/CODEBASE_OVERVIEW.md
git commit -m "docs(task66): D46 decision ledger entry — hash-based compile trigger"
```

(`docs/TASKS.md` #66 row flips to `done` in the final wrap-up commit after the live migration, Task 7 — matching the #64/#65 pattern.)

---

## Task 6: One-shot migration script

**Files:**
- Create: `scripts/migrate_task66_compiled_hash.py`
- Test: `kdb_compiler/tests/test_migrate_task66.py` (new)

Backfills `last_compiled_hash` on the existing manifest (Q2) and performs the EP1 `compile_state` repair as a distinct labeled one-off step (Q4). `--dry-run` is the default; `--apply` mutates. Models `scripts/migrate_task64_supersession.py`.

- [ ] **Step 1: Write the failing tests**

Create `kdb_compiler/tests/test_migrate_task66.py`:

```python
"""Tests for the Task #66 one-shot last_compiled_hash migration."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.migrate_task66_compiled_hash import backfill_manifest

_ABSENT = object()


def _src(*, hash, compile_state, last_compiled_hash=_ABSENT):
    rec = {"hash": hash, "compile_state": compile_state}
    if last_compiled_hash is not _ABSENT:
        rec["last_compiled_hash"] = last_compiled_hash
    return rec


def test_backfill_sets_hash_for_compiled_state():
    h = "sha256:" + "a" * 64
    manifest = {"sources": {"KDB/raw/a.md": _src(hash=h, compile_state="compiled")}}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert manifest["sources"]["KDB/raw/a.md"]["last_compiled_hash"] == h
    assert "KDB/raw/a.md" in report["backfilled"]


def test_backfill_sets_hash_for_recompiled_and_metadata_only():
    h = "sha256:" + "b" * 64
    manifest = {"sources": {
        "KDB/raw/r.md": _src(hash=h, compile_state="recompiled"),
        "KDB/raw/x.png": _src(hash=h, compile_state="metadata_only"),
    }}
    backfill_manifest(manifest, repair_error_sources=[])
    assert manifest["sources"]["KDB/raw/r.md"]["last_compiled_hash"] == h
    assert manifest["sources"]["KDB/raw/x.png"]["last_compiled_hash"] == h


def test_backfill_leaves_error_state_absent():
    h = "sha256:" + "c" * 64
    manifest = {"sources": {"KDB/raw/e.md": _src(hash=h, compile_state="error")}}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert "last_compiled_hash" not in manifest["sources"]["KDB/raw/e.md"]
    assert "KDB/raw/e.md" in report["left_eligible"]


def test_backfill_is_idempotent():
    h = "sha256:" + "d" * 64
    manifest = {"sources": {
        "KDB/raw/a.md": _src(hash=h, compile_state="compiled", last_compiled_hash=h),
    }}
    report = backfill_manifest(manifest, repair_error_sources=[])
    assert report["backfilled"] == []        # already present -> untouched


def test_repair_reverts_error_then_backfill_sets_hash():
    # Q4: EP1 repair runs first, so the uniform Q2 rule then backfills it
    h = "sha256:" + "e" * 64
    manifest = {"sources": {"KDB/raw/EP1.md": _src(hash=h, compile_state="error")}}
    report = backfill_manifest(manifest, repair_error_sources=["KDB/raw/EP1.md"])
    rec = manifest["sources"]["KDB/raw/EP1.md"]
    assert rec["compile_state"] == "recompiled"
    assert rec["last_compiled_hash"] == h
    assert "KDB/raw/EP1.md" in report["repaired"]


def test_repair_skips_source_not_in_error_state():
    h = "sha256:" + "f" * 64
    manifest = {"sources": {"KDB/raw/EP1.md": _src(hash=h, compile_state="recompiled")}}
    report = backfill_manifest(manifest, repair_error_sources=["KDB/raw/EP1.md"])
    assert "KDB/raw/EP1.md" in report["repair_skipped"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_migrate_task66.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_task66_compiled_hash'`.

- [ ] **Step 3: Write the migration script**

Create `scripts/migrate_task66_compiled_hash.py`:

```python
#!/usr/bin/env python3
"""Task #66 one-shot migration — backfill last_compiled_hash on the live manifest.

Existing source records predate Task #66 and have no `last_compiled_hash`. Without
a backfill every source would read as "never compiled" and recompile spuriously on
the first post-#66 run. This script writes the field once (Q2), and performs the
EP1 `compile_state` repair as a distinct labeled local data repair (Q4).

Q2 backfill rule:
    compile_state in {compiled, recompiled, metadata_only} -> last_compiled_hash = hash
    compile_state == "error" (or anything else)            -> leave absent (eligible)

Q4 EP1 repair (--repair-error-source, repeatable): a source hand-edited to
`compile_state: "error"` that was in fact successfully compiled at its recorded
`hash`. The repair sets compile_state error -> recompiled BEFORE the Q2 loop, so the
uniform rule then backfills it. This is a specific local data repair, not
compile-state logic — no code path reads compile_state for a decision.

--dry-run is the DEFAULT. Pass --apply to mutate state/manifest.json.

last_compiled_hash is a manifest-only field — no graphdb-kdb resync is needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from kdb_compiler import atomic_io
from kdb_compiler.manifest_update import assert_manifest_invariants

_COMPILED_STATES = {"compiled", "recompiled", "metadata_only"}


def backfill_manifest(manifest: dict, *, repair_error_sources: list[str]) -> dict:
    """Mutate manifest in place. Returns a report dict of what changed."""
    sources = manifest.get("sources", {})
    report: dict = {"repaired": [], "repair_skipped": [],
                    "backfilled": [], "left_eligible": []}

    # --- EP1 kludge revert (one-time local repair, Q4) ---
    for sid in repair_error_sources:
        rec = sources.get(sid)
        if rec is None:
            raise SystemExit(f"ERROR  --repair-error-source {sid}: not in manifest")
        if rec.get("compile_state") != "error":
            report["repair_skipped"].append(sid)
            continue
        rec["compile_state"] = "recompiled"
        report["repaired"].append(sid)

    # --- uniform Q2 backfill ---
    for sid, rec in sorted(sources.items()):
        if rec.get("last_compiled_hash") is not None:
            continue                                  # idempotent
        if rec.get("compile_state") in _COMPILED_STATES:
            rec["last_compiled_hash"] = rec.get("hash")
            report["backfilled"].append(sid)
        else:
            report["left_eligible"].append(sid)        # error/other -> absent
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="migrate_task66_compiled_hash")
    ap.add_argument("--vault-root", required=True,
                    help="Absolute path to the Obsidian vault root")
    ap.add_argument("--apply", action="store_true",
                    help="Mutate state/manifest.json (default is dry-run)")
    ap.add_argument("--repair-error-source", action="append", default=[],
                    metavar="SOURCE_ID",
                    help="Source whose 'error' compile_state is a known-bad "
                         "hand-edit to revert to 'recompiled' (repeatable)")
    args = ap.parse_args(argv)

    state_root = Path(args.vault_root).resolve() / "KDB" / "state"
    manifest_path = state_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR  cannot read manifest {manifest_path}: {exc}")
        return 1

    report = backfill_manifest(
        manifest, repair_error_sources=args.repair_error_source,
    )

    for sid in report["repaired"]:
        print(f"repair  {sid} — compile_state error -> recompiled (local data repair)")
    for sid in report["repair_skipped"]:
        print(f"skip    {sid} — not in 'error' state; repair not applied")
    for sid in report["backfilled"]:
        print(f"backfill {sid} — last_compiled_hash <- hash")
    for sid in report["left_eligible"]:
        print(f"eligible {sid} — left without last_compiled_hash (will compile)")

    print(f"\nsummary: {len(report['repaired'])} repaired, "
          f"{len(report['backfilled'])} backfilled, "
          f"{len(report['left_eligible'])} left eligible")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    assert_manifest_invariants(manifest)
    run_id = f"task66-migration-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    atomic_io.atomic_write_json(manifest_path, manifest, sort_keys=True)
    audit_path = state_root / f"task66-migration-audit-{run_id}.json"
    atomic_io.atomic_write_json(audit_path, {"run_id": run_id, **report},
                                sort_keys=True)
    print(f"\nAPPLIED — manifest updated; audit at {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_migrate_task66.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full compiler suite**

Run: `.venv/bin/python -m pytest kdb_compiler/ -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_task66_compiled_hash.py kdb_compiler/tests/test_migrate_task66.py
git commit -m "feat(task66): one-shot last_compiled_hash backfill migration"
```

---

## Task 7: Live migration + verification (HUMAN-GATED — not for subagents)

This task mutates the live vault. The subagent executor stops after Task 6 and hands back. The operator runs these steps.

- [ ] **Step 1: Dry-run the migration**

The operator first finds EP1's source_id (`grep -o '"KDB/raw/[^"]*EP1[^"]*"' KDB/state/manifest.json` in the vault), then:

```
.venv/bin/python -m scripts.migrate_task66_compiled_hash \
  --vault-root /home/ftu/Obsidian \
  --repair-error-source "<EP1 source_id>"
```

Review: EP1 reported `repair`; all 4 sources reported `backfill`; nothing `left eligible` unexpectedly.

- [ ] **Step 2: Apply**

Re-run with `--apply`. Confirm the audit file is written.

- [ ] **Step 3: Verify a no-op scan recompiles nothing**

Run a `kdb-compile` scan-only / no-op pass against `/home/ftu/Obsidian` and confirm all 4 sources classify `to_skip` — none spuriously recompile (blueprint §5.2 step 4).

- [ ] **Step 4: Final wrap-up commit**

Flip the `docs/TASKS.md` #66 row to `done` (record the migration commit/audit), then commit:

```bash
git add docs/TASKS.md
git commit -m "docs(task66): mark #66 done — error_retry kludge removed, migration applied"
```

---

## Acceptance

- `error_retry` and every `compile_state` *read for eligibility* are gone from `kdb_scan.py`.
- `to_compile`/`to_skip` derive purely from `current_hash != compiled_hash`.
- Post-migration, a no-op scan recompiles nothing.
- Full `kdb_compiler` suite green under `.venv/bin/python -m pytest`.
