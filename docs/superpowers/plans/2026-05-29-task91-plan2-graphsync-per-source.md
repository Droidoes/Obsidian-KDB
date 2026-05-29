# Plan 2 — Graph-sync per-source (`detect_orphans` flag + standalone pass)

> **For agentic workers:** Use superpowers:executing-plans. Checkbox steps.

**Goal:** Let the orchestrator run `apply_compile_result` **per source without orphan-marking**, and run orphan-marking **once at finalize** via a standalone `detect_orphans()` — implementing the spec's "orphan-marking deferred to end-of-run" decision (avoids transient-orphan context pollution / variant creation).

**Architecture:** `apply_compile_result` gains `detect_orphans: bool = True` (default preserves the monolith/legacy batch behavior). Per-source orchestrator calls pass `False` (Phases 1–3.5 only). A new module-level `detect_orphans(conn, run_id)` wraps the existing `_detect_and_mark_orphans` in its own transaction; the orchestrator calls it once before `kdb-clean orphans` at finalize.

**Spec:** `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md` — "Orphan-marking is deferred to end-of-run". Plan 2 of 6. Leaves the app green (default `True` = unchanged behavior; existing orphan tests still pass).

**Run tests:** `python -m pytest graphdb_kdb/tests/test_ingestion.py -m "not live"`.

---

## File Structure
- **Modify** `graphdb_kdb/ingestor.py` — `apply_compile_result` `detect_orphans` flag; new `detect_orphans()` function.
- **Modify** `graphdb_kdb/graphdb.py` — `apply_compile_result` passthrough; new `detect_orphans()` method.
- **Modify** `graphdb_kdb/tests/test_ingestion.py` — new tests.

---

## Task 1: `apply_compile_result(detect_orphans=True)` flag

**Files:** `graphdb_kdb/ingestor.py:25` (signature) + `:98` (Phase 4); `graphdb_kdb/graphdb.py:165`; Test `test_ingestion.py`.

- [ ] **Step 1: Write the failing test**

```python
# append to graphdb_kdb/tests/test_ingestion.py
def test_apply_skips_orphan_marking_when_disabled(graph_dir):
    src = "KDB/raw/s.md"
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r1")
        # Source drops 'b' but with detect_orphans=False — 'b' must NOT be flagged.
        res = gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a")])]),
            scan, "r2", detect_orphans=False)
        b = gdb.get_entity("b")
    assert res.orphans_detected == []
    assert b.status == "active"  # still active — marking deferred to finalize
```

- [ ] **Step 2: Run** → FAIL (`apply_compile_result() got an unexpected keyword argument 'detect_orphans'`).

- [ ] **Step 3: Implement** — `graphdb_kdb/ingestor.py`, add the param to `apply_compile_result` (line 25-32) and gate Phase 4 (line 96-98):

```python
def apply_compile_result(
    cr: dict,
    scan_dict: dict,
    run_id: str,
    *,
    conn: kuzu.Connection,
    now: str | None = None,
    detect_orphans: bool = True,
) -> SyncResult:
```

```python
        # Phase 4: orphan detection (mark orphans + revive). Task #91: skipped
        # when detect_orphans=False — the orchestrator runs a single end-of-run
        # detect_orphans() pass instead (deferred-marking decision).
        if detect_orphans:
            result.orphans_detected = _detect_and_mark_orphans(conn, run_id, now)
```

And `graphdb_kdb/graphdb.py` `apply_compile_result` (line 165) — add passthrough:

```python
    def apply_compile_result(
        self,
        cr: dict,
        scan_dict: dict,
        run_id: str,
        *,
        now: str | None = None,
        detect_orphans: bool = True,
    ) -> SyncResult:
        """Apply one compile run's deltas. Atomic per run. Delegates to ingestor."""
        from graphdb_kdb.ingestor import apply_compile_result as _apply
        return _apply(cr, scan_dict, run_id, conn=self.conn, now=now,
                      detect_orphans=detect_orphans)
```

- [ ] **Step 4: Run** → PASS. Also run the existing orphan tests to confirm default-True unchanged: `python -m pytest graphdb_kdb/tests/test_ingestion.py -k orphan -m "not live"`.

- [ ] **Step 5: Commit**

```bash
git add graphdb_kdb/ingestor.py graphdb_kdb/graphdb.py graphdb_kdb/tests/test_ingestion.py
git commit -m "feat(task91): apply_compile_result detect_orphans flag (default True)"
```

---

## Task 2: standalone `detect_orphans()` end-of-run pass

**Files:** `graphdb_kdb/ingestor.py` (new function near `_detect_and_mark_orphans`, ~line 650); `graphdb_kdb/graphdb.py` (new method); Test `test_ingestion.py`.

- [ ] **Step 1: Write the failing test**

```python
# append to test_ingestion.py
def test_standalone_detect_orphans_marks_after_deferred_apply(graph_dir):
    """The deferred model: per-source apply with detect_orphans=False leaves the
    orphan unmarked; the end-of-run detect_orphans() pass then marks it."""
    src = "KDB/raw/s.md"
    scan = make_scan([make_scan_entry(src)])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a"), make_page("b")])]),
            scan, "r1")
        gdb.apply_compile_result(
            make_compile_result([make_compiled_source(src, [make_page("a")])]),
            scan, "r2", detect_orphans=False)
        assert gdb.get_entity("b").status == "active"   # not yet marked

        orphans = gdb.detect_orphans("r2")              # finalize pass
        b = gdb.get_entity("b")
    assert "b" in orphans
    assert b.status == "orphan_candidate"
```

- [ ] **Step 2: Run** → FAIL (`'GraphDB' object has no attribute 'detect_orphans'`).

- [ ] **Step 3: Implement** — `graphdb_kdb/ingestor.py`, add a public function (it owns its own transaction since the orchestrator calls it standalone; `datetime` is already imported at line 12):

```python
def detect_orphans(
    conn: kuzu.Connection, run_id: str, *, now: str | None = None
) -> list[str]:
    """Task #91: standalone end-of-run orphan-marking pass. The orchestrator
    calls this ONCE at finalize — after all per-source apply_compile_result
    calls (which run with detect_orphans=False) — so orphan status is computed
    once over the final graph, not per-source. Own transaction. Returns the
    newly orphan_candidate slugs."""
    if now is None:
        now = datetime.now().astimezone().isoformat()
    conn.execute("BEGIN TRANSACTION")
    try:
        orphans = _detect_and_mark_orphans(conn, run_id, now)
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    return orphans
```

And `graphdb_kdb/graphdb.py`, add a method (near `apply_cleanup`):

```python
    def detect_orphans(self, run_id: str, *, now: str | None = None) -> list[str]:
        """End-of-run orphan-marking pass (Task #91). Delegates to ingestor."""
        from graphdb_kdb.ingestor import detect_orphans as _detect
        return _detect(self.conn, run_id, now=now)
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Full regression** — `python -m pytest graphdb_kdb/ kdb_compiler/ -m "not live" -q -p no:warnings` → all pass.

- [ ] **Step 6: Commit**

```bash
git add graphdb_kdb/ingestor.py graphdb_kdb/graphdb.py graphdb_kdb/tests/test_ingestion.py
git commit -m "feat(task91): standalone detect_orphans() end-of-run pass"
```

---

## Self-Review
1. **Spec coverage:** deferred orphan-marking = `detect_orphans=False` per-source (Task 1) + standalone `detect_orphans()` finalize pass (Task 2). Matches the spec decision.
2. **Backward-compat:** `detect_orphans=True` default preserves the monolith/legacy batch behavior; existing orphan tests untouched and green.
3. **Type consistency:** `detect_orphans` param on both `ingestor.apply_compile_result` and `GraphDB.apply_compile_result`; `detect_orphans()` function + `GraphDB.detect_orphans()` method return `list[str]`.
