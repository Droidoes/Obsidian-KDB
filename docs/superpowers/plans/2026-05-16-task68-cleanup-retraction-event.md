# Task #68 — Replayable Cleanup/Retraction Event — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `kdb-clean orphans --apply` emit a typed, replayable cleanup event so `graphdb-kdb rebuild` converges instead of re-introducing reaped pages.

**Architecture:** `kdb-clean orphans --apply` writes a `cleanup` run journal + `retraction.json` sidecar into the same `state/runs/` stream the compiler uses. The journal carries `event_type: "cleanup"`; the retraction payload carries `retracted_slugs` (reaped slugs with no surviving active page). A new `ingestor.apply_cleanup` `DETACH DELETE`s those `Entity` nodes; the `ObsidianRunsAdapter` routes on `event_type` for both replay (`rebuild`) and live sync. A one-shot backfill synthesizes a cleanup journal for the pre-#68 16-orphan reap.

**Tech Stack:** Python 3.12, Kuzu 0.11 (graph store), pytest. Test runner: `.venv/bin/python -m pytest`.

**Source of truth:** `docs/task68-cleanup-retraction-event-blueprint.md` (Codex-approved). This plan implements that blueprint.

---

## Background an implementer needs

- **`kdb-clean`** is a maintenance CLI (`kdb_compiler/kdb_clean.py`). `kdb-clean orphans` archives `orphan_candidate` pages and removes them from `manifest.json`. `reap_orphans(manifest)` is its pure manifest-mutation core. "reap" is internal vocabulary; the user-facing command is always `kdb-clean orphans`.
- **GraphDB-KDB** is an independently-derived Kuzu graph. `graphdb-kdb rebuild` drops all tables and replays eligible run journals from `state/runs/*.json` chronologically. `Entity` nodes are **slug-keyed**.
- **The bug:** `kdb-clean` mutates `manifest.json` only. `rebuild` replays the *compile* journals, whose old runs still emit the reaped pages — `ingestor._upsert_entity` (`MERGE`) re-creates them. The cleanup is invisible to replay.
- **Why DELETE, not a flag:** the orphan entity is *already* flagged in the graph; replay re-`MERGE`s it back to `active`. Only an actual `DELETE`, positioned chronologically after the compile events, converges the graph to the manifest. See blueprint §2.
- **slug vs page_id:** `kdb-clean` reaps `page_id`s; the graph is slug-keyed. A reaped slug must NOT be deleted if a surviving (non-reaped) page still carries it. The retraction event carries `reaped` (full page records, audit) AND `retracted_slugs` (only fully-removed slugs); the graph deletes by `retracted_slugs` only.
- **Vault vs graph location:** the Kuzu graph is at `~/Droidoes/GraphDB-KDB` (not the vault). `state/runs/` is under the vault at `<vault-root>/KDB/state/runs/`. `kdb-clean --vault-root` takes the vault root; the CLI appends `KDB/`.
- **Write order is crash-consistency-critical:** archive → retraction sidecar → manifest → journal → live-sync. The journal must never commit before the manifest (blueprint §6.1).

**Baseline:** before starting, run the full suite and confirm it is green:

```
.venv/bin/python -m pytest
```
Expected: all pass, 0 failures (1 skip is acceptable).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `kdb_compiler/kdb_clean.py` | `reap_orphans` gains `retracted_slugs`; `build_cleanup_artifacts` builds journal+retraction; `_cmd_orphans --apply` emits them + live-syncs | Modify |
| `kdb_compiler/tests/test_kdb_clean.py` | unit tests for the above | Modify |
| `graphdb_kdb/types.py` | `SyncResult` gains `entities_deleted` | Modify |
| `graphdb_kdb/ingestor.py` | new `apply_cleanup` (`DETACH DELETE` by `retracted_slugs`) | Modify |
| `graphdb_kdb/graphdb.py` | `GraphDB.apply_cleanup` thin wrapper | Modify |
| `graphdb_kdb/tests/test_cleanup_ingestion.py` | `apply_cleanup` tests incl. slug-safe graph test | Create |
| `graphdb_kdb/adapters/base.py` | `SkipReason` gains `unsupported_event_type` | Modify |
| `graphdb_kdb/adapters/obsidian_runs.py` | `event_type` routing in `is_eligible`/`load_payload`/`apply`; `sync_cleanup_run`; `supported_journal_versions` | Modify |
| `graphdb_kdb/tests/test_rebuilder.py` | adapter routing + end-to-end cleanup replay tests | Modify |
| `scripts/backfill_cleanup_journal.py` | one-shot backfill for the pre-#68 16-orphan reap | Create |
| `kdb_compiler/tests/test_backfill_cleanup_journal.py` | backfill pure-function tests | Create |
| `docs/graphdb-kdb-producer-contract.md` | §3.3/§3.4/§4 amendment | Modify |
| `docs/CODEBASE_OVERVIEW.md` | drop the #68 maintenance caveat | Modify |
| `docs/TASKS.md` | #68 → done | Modify |

---

## Task 1: `reap_orphans()` emits `retracted_slugs`

**Files:**
- Modify: `kdb_compiler/kdb_clean.py:55-99` (`reap_orphans`)
- Test: `kdb_compiler/tests/test_kdb_clean.py`

- [ ] **Step 1: Write the failing tests**

Add to `kdb_compiler/tests/test_kdb_clean.py` (after `test_reap_no_orphans_is_noop`):

```python
def test_reap_retracted_slugs_lists_fully_removed_slugs():
    o1 = "KDB/wiki/concepts/o1.md"
    o2 = "KDB/wiki/concepts/o2.md"
    manifest = _manifest(
        pages={
            o1: _page("orphan_candidate", "o1"),
            o2: _page("orphan_candidate", "o2"),
        },
        orphans={o1: {}, o2: {}},
    )
    report = reap_orphans(manifest)
    assert report["retracted_slugs"] == ["o1", "o2"]


def test_reap_retracted_slugs_excludes_slug_surviving_under_another_type():
    # slug-safe (manifest side): 'foo' survives as an active article, so
    # reaping the orphaned 'foo' concept must NOT retract slug 'foo'.
    art = "KDB/wiki/articles/foo.md"
    con = "KDB/wiki/concepts/foo.md"
    solo = "KDB/wiki/concepts/solo.md"
    manifest = _manifest(
        pages={
            art: _page("active", "foo", page_type="article"),
            con: _page("orphan_candidate", "foo", page_type="concept"),
            solo: _page("orphan_candidate", "solo"),
        },
        orphans={con: {}, solo: {}},
    )
    report = reap_orphans(manifest)
    assert report["retracted_slugs"] == ["solo"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_clean.py -k retracted -v`
Expected: FAIL — `KeyError: 'retracted_slugs'` (the key is not in the return dict yet).

- [ ] **Step 3: Implement `retracted_slugs`**

In `kdb_compiler/kdb_clean.py`, in `reap_orphans()`, after the `dead_links` list comprehension and before the `for pid in reaped_ids:` loop, add:

```python
    # retracted_slugs: reaped slugs that NO surviving page provides — the
    # slug-safe deletion key set for the graph (a slug still carried by a
    # surviving active page must not be retracted). #68.
    retracted_slugs = sorted(reaped_slugs - surviving_slugs)
```

Then change the `return` statement to include it:

```python
    return {
        "reaped": sorted(reaped, key=lambda r: r["page_id"]),
        "dead_links": sorted(dead_links, key=lambda d: (d["from_page"], d["to_slug"])),
        "retracted_slugs": retracted_slugs,
    }
```

Update the `reap_orphans` docstring `report` block to list the new key:

```python
    report = {
      "reaped":          [{"page_id", "slug", "page_type"}, ...],  # sorted by page_id
      "dead_links":      [{"from_page", "to_slug"}, ...],          # active -> reaped
      "retracted_slugs": [slug, ...],  # reaped slugs no surviving page provides
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_clean.py -v`
Expected: PASS — all tests (the 8 existing + 2 new) green.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/kdb_clean.py kdb_compiler/tests/test_kdb_clean.py
git commit -m "feat(task68.1): reap_orphans emits retracted_slugs (slug-safe deletion key set)"
```

---

## Task 2: `apply_cleanup` ingestor function + `GraphDB.apply_cleanup` wrapper

**Files:**
- Modify: `graphdb_kdb/types.py:13-21` (`SyncResult`)
- Modify: `graphdb_kdb/ingestor.py` (add `apply_cleanup` at end of Phase functions, after `_detect_and_mark_orphans`)
- Modify: `graphdb_kdb/graphdb.py:139` (add wrapper after `apply_compile_result`)
- Test: `graphdb_kdb/tests/test_cleanup_ingestion.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `graphdb_kdb/tests/test_cleanup_ingestion.py`:

```python
"""Tests for graphdb_kdb.ingestor.apply_cleanup (#68).

apply_cleanup DETACH DELETEs Entity nodes by retraction['retracted_slugs'].
It is the graph-side counterpart of `kdb-clean orphans`.
"""
from __future__ import annotations

from graphdb_kdb.graphdb import GraphDB
from graphdb_kdb.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


def _seed(gdb, slugs, *, source_id="KDB/raw/s.md"):
    """Ingest one compile run with the given page slugs as one source."""
    cr = make_compile_result([
        make_compiled_source(source_id, [make_page(s) for s in slugs])
    ])
    scan = make_scan([make_scan_entry(source_id)])
    gdb.apply_compile_result(cr, scan, "seed-run")


def test_apply_cleanup_deletes_retracted_entity(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb, ["alpha"])
        assert gdb.get_entity("alpha") is not None
        res = gdb.apply_cleanup({"retracted_slugs": ["alpha"]}, "clean-1")
        assert gdb.get_entity("alpha") is None
        assert res.entities_deleted == 1


def test_apply_cleanup_deletes_only_listed_slugs(graph_dir):
    # slug-safe (graph side): retract 'solo' only — 'foo' must survive.
    with GraphDB(graph_dir) as gdb:
        _seed(gdb, ["foo", "solo"])
        res = gdb.apply_cleanup({"retracted_slugs": ["solo"]}, "clean-1")
        assert gdb.get_entity("solo") is None
        assert gdb.get_entity("foo") is not None
        assert res.entities_deleted == 1


def test_apply_cleanup_removes_supports_and_links_edges(graph_dir):
    with GraphDB(graph_dir) as gdb:
        # 'a' links to 'b'; both supported by the source.
        cr = make_compile_result([
            make_compiled_source("KDB/raw/s.md", [
                make_page("a", outgoing_links=["b"]),
                make_page("b"),
            ])
        ])
        scan = make_scan([make_scan_entry("KDB/raw/s.md")])
        gdb.apply_compile_result(cr, scan, "seed-run")
        assert gdb.stats()["links_to"] == 1
        gdb.apply_cleanup({"retracted_slugs": ["b"]}, "clean-1")
        s = gdb.stats()
        assert s["entities"] == 1          # only 'a' remains
        assert s["links_to"] == 0          # a->b edge gone with b
        assert s["supports"] == 1          # source still SUPPORTS 'a'


def test_apply_cleanup_absent_slug_is_noop(graph_dir):
    with GraphDB(graph_dir) as gdb:
        _seed(gdb, ["alpha"])
        res = gdb.apply_cleanup({"retracted_slugs": ["never-existed"]}, "clean-1")
        assert res.entities_deleted == 0
        assert gdb.get_entity("alpha") is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_cleanup_ingestion.py -v`
Expected: FAIL — `AttributeError: 'GraphDB' object has no attribute 'apply_cleanup'`.

- [ ] **Step 3: Add `entities_deleted` to `SyncResult`**

In `graphdb_kdb/types.py`, in the `SyncResult` dataclass, add a field after `supports_upserted`:

```python
    supports_upserted: int = 0    # SUPPORTS edges present after replacement (Phase 3)
    entities_deleted: int = 0     # Entity DETACH DELETE ops in apply_cleanup (#68)
    orphans_detected: list[str] = field(default_factory=list)  # newly orphan_candidate slugs
```

- [ ] **Step 4: Implement `apply_cleanup` in the ingestor**

In `graphdb_kdb/ingestor.py`, append at the end of the file (after `_detect_and_mark_orphans`):

```python
# ---------- Cleanup retraction (#68) ----------

def apply_cleanup(
    retraction: dict,
    run_id: str,
    *,
    conn: kuzu.Connection,
) -> SyncResult:
    """Retract entities a `kdb-clean orphans` run removed (#68).

    DETACH DELETEs the Entity node — and its LINKS_TO + SUPPORTS edges — for
    every slug in `retraction['retracted_slugs']`, and ONLY those slugs.
    `retracted_slugs` is the slug-safe key set computed by `reap_orphans`
    (reaped slugs no surviving active page provides); the full `reaped` page
    list in the retraction payload is audit-only and is NOT used for deletion.

    Atomic per run, mirroring apply_compile_result's transaction handling.

    Args:
        retraction: retraction payload dict (`retracted_slugs`, `reaped`, ...).
        run_id: cleanup run id string.
        conn: open kuzu.Connection.

    Returns:
        SyncResult with `entities_deleted` set to the count of nodes actually
        removed (a retracted slug already absent from the graph is a no-op).
    """
    result = SyncResult(run_id=run_id)

    conn.execute("BEGIN TRANSACTION")
    try:
        for slug in retraction.get("retracted_slugs", []):
            r = conn.execute(
                "MATCH (e:Entity {slug: $slug}) RETURN COUNT(e)", {"slug": slug}
            )
            existed = r.has_next() and int(r.get_next()[0]) > 0
            if existed:
                conn.execute(
                    "MATCH (e:Entity {slug: $slug}) DETACH DELETE e",
                    {"slug": slug},
                )
                result.entities_deleted += 1
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise

    return result
```

**`DETACH DELETE` note:** verified supported in Kuzu 0.11 (the pinned version) — it removes the node and all incident `LINKS_TO`/`SUPPORTS` edges in one statement. If a future Kuzu rejects it, the fallback is explicit edge deletion before the node delete — the tests stay identical:

```python
                conn.execute(
                    "MATCH (e:Entity {slug: $slug})-[r:LINKS_TO]->() DELETE r",
                    {"slug": slug})
                conn.execute(
                    "MATCH ()-[r:LINKS_TO]->(e:Entity {slug: $slug}) DELETE r",
                    {"slug": slug})
                conn.execute(
                    "MATCH ()-[r:SUPPORTS]->(e:Entity {slug: $slug}) DELETE r",
                    {"slug": slug})
                conn.execute(
                    "MATCH (e:Entity {slug: $slug}) DELETE e", {"slug": slug})
```

- [ ] **Step 5: Add the `GraphDB.apply_cleanup` wrapper**

In `graphdb_kdb/graphdb.py`, immediately after the `apply_compile_result` method (ends line 139), add:

```python
    def apply_cleanup(self, retraction: dict, run_id: str) -> SyncResult:
        """Retract entities a cleanup run removed. Delegates to ingestor (#68)."""
        from graphdb_kdb.ingestor import apply_cleanup as _apply
        return _apply(retraction, run_id, conn=self.conn)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_cleanup_ingestion.py graphdb_kdb/tests/test_ingestion.py -v`
Expected: PASS — the 4 new cleanup tests + all existing ingestion tests green.

- [ ] **Step 7: Commit**

```bash
git add graphdb_kdb/types.py graphdb_kdb/ingestor.py graphdb_kdb/graphdb.py graphdb_kdb/tests/test_cleanup_ingestion.py
git commit -m "feat(task68.2): apply_cleanup — DETACH DELETE entities by retracted_slugs"
```

---

## Task 3: Adapter event-type routing

**Files:**
- Modify: `graphdb_kdb/adapters/base.py:22-28` (`SkipReason`)
- Modify: `graphdb_kdb/adapters/obsidian_runs.py` (`supported_journal_versions`, `is_eligible`, `load_payload`, `apply`)
- Test: `graphdb_kdb/tests/test_rebuilder.py`

- [ ] **Step 1: Write the failing tests**

In `graphdb_kdb/tests/test_rebuilder.py`, after the `_write_run` helper (ends line 93), add a cleanup-run builder:

```python
def _write_cleanup_run(
    journals_dir: Path,
    run_id: str,
    retracted_slugs: list[str],
    *,
    started_at: str,
    reaped: list[dict] | None = None,
    success: bool = True,
    dry_run: bool = False,
    schema_version: str = "2.1",
    skip_sidecar: bool = False,
) -> Path:
    """Write a synthetic kdb-clean cleanup run tree:
        <journals_dir>/<run_id>.json          — cleanup journal
        <journals_dir>/<run_id>/retraction.json — retraction sidecar
    """
    journals_dir.mkdir(parents=True, exist_ok=True)
    journal = {
        "schema_version": schema_version,
        "event_type": "cleanup",
        "run_id": run_id,
        "started_at": started_at,
        "success": success,
        "dry_run": dry_run,
    }
    journal_path = journals_dir / f"{run_id}.json"
    journal_path.write_text(json.dumps(journal))
    if skip_sidecar:
        return journal_path
    sidecar = journals_dir / run_id
    sidecar.mkdir(parents=True, exist_ok=True)
    retraction = {
        "event_type": "cleanup",
        "run_id": run_id,
        "reaped": reaped or [],
        "retracted_slugs": retracted_slugs,
        "dead_links": [],
    }
    (sidecar / "retraction.json").write_text(json.dumps(retraction))
    return journal_path
```

Then add these tests at the end of the file:

```python
# ============================================================================
# Cleanup event routing (#68)
# ============================================================================

def test_obsidian_adapter_cleanup_run_is_eligible(tmp_path):
    journals = tmp_path / "runs"
    _write_cleanup_run(journals, "clean-orphans-2026-02-01T00-00-00",
                       ["drop"], started_at="2026-02-01T00:00:00")
    adapter = ObsidianRunsAdapter()
    [desc] = adapter.discover_runs(journals)
    # schema_version 2.1 must be accepted (not skipped unsupported_version).
    assert adapter.is_eligible(desc).eligible is True


def test_obsidian_adapter_cleanup_missing_retraction_payload_skipped(tmp_path):
    journals = tmp_path / "runs"
    _write_cleanup_run(journals, "clean-orphans-2026-02-01T00-00-00",
                       ["drop"], started_at="2026-02-01T00:00:00",
                       skip_sidecar=True)
    adapter = ObsidianRunsAdapter()
    [desc] = adapter.discover_runs(journals)
    elig = adapter.is_eligible(desc)
    assert elig.eligible is False
    assert elig.skip_reason == "payload_missing"


def test_obsidian_adapter_unknown_event_type_skipped(tmp_path):
    journals = tmp_path / "runs"
    journals.mkdir()
    (journals / "weird.json").write_text(json.dumps({
        "schema_version": "2.1", "event_type": "bogus", "run_id": "weird",
        "started_at": "2026-01-01T00:00:00", "success": True, "dry_run": False,
    }))
    adapter = ObsidianRunsAdapter()
    [desc] = adapter.discover_runs(journals)
    elig = adapter.is_eligible(desc)
    assert elig.eligible is False
    assert elig.skip_reason == "unsupported_event_type"


def test_obsidian_adapter_cleanup_load_payload(tmp_path):
    journals = tmp_path / "runs"
    _write_cleanup_run(journals, "clean-orphans-2026-02-01T00-00-00",
                       ["drop"], started_at="2026-02-01T00:00:00")
    adapter = ObsidianRunsAdapter()
    [desc] = adapter.discover_runs(journals)
    mutation, scan, run_id = adapter.load_payload(desc)
    assert mutation["event_type"] == "cleanup"
    assert mutation["retracted_slugs"] == ["drop"]
    assert scan == {}
    assert run_id == "clean-orphans-2026-02-01T00-00-00"


def test_obsidian_adapter_apply_routes_cleanup_to_apply_cleanup(graph_dir):
    cr = make_compile_result([
        make_compiled_source("KDB/raw/s.md", [make_page("gone")])
    ])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    adapter = ObsidianRunsAdapter()
    with GraphDB(graph_dir) as gdb:
        adapter.apply(cr, scan, "run-1", gdb.conn)
        assert gdb.get_entity("gone") is not None
        retraction = {"event_type": "cleanup", "retracted_slugs": ["gone"]}
        res = adapter.apply(retraction, {}, "clean-1", gdb.conn)
        assert gdb.get_entity("gone") is None
        assert res.entities_deleted == 1


def test_obsidian_adapter_apply_raises_on_unknown_event_type(graph_dir):
    adapter = ObsidianRunsAdapter()
    with GraphDB(graph_dir) as gdb:
        with pytest.raises(ValueError, match="unsupported event_type"):
            adapter.apply({"event_type": "bogus"}, {}, "run-x", gdb.conn)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_rebuilder.py -k "cleanup or unknown_event" -v`
Expected: FAIL — cleanup journals are skipped `unsupported_version` (adapter only knows `["2.0"]`), and `unsupported_event_type` is not a valid `SkipReason`.

- [ ] **Step 3: Add `unsupported_event_type` to `SkipReason`**

In `graphdb_kdb/adapters/base.py`, extend the `SkipReason` literal:

```python
SkipReason = Literal[
    "failed",                  # producer reported run failure (success != true)
    "dry_run",                 # producer reported dry-run (excluded by D39 filter)
    "payload_missing",         # sidecar archive absent or incomplete
    "invalid_journal",         # journal JSON malformed or missing required fields
    "unsupported_version",     # journal schema_version not in supported_journal_versions
    "unsupported_event_type",  # journal event_type is neither 'compile' nor 'cleanup' (#68)
]
```

- [ ] **Step 4: Implement event routing in the adapter**

In `graphdb_kdb/adapters/obsidian_runs.py`:

(a) Update the `supported_journal_versions` ClassVar:

```python
    supported_journal_versions: ClassVar[list[str]]  = ["2.0", "2.1"]  # +cleanup #68
```

(b) Replace the body of `is_eligible` from the version-gate line onward (the block from `version = str(...)` to the final `return EligibilityResult(True, None)`) with:

```python
        # Version gate (D-S3) — runs before success/dry_run since unsupported
        # journal shapes can't be trusted to populate those fields correctly.
        version = str(journal.get("schema_version", ""))
        if version not in self.supported_journal_versions:
            return EligibilityResult(False, "unsupported_version")

        if not journal.get("success"):
            return EligibilityResult(False, "failed")
        if journal.get("dry_run"):
            return EligibilityResult(False, "dry_run")

        # Event-type routing (#68): absent ⇒ 'compile' (back-compat with 2.0
        # compile journals). 'cleanup' uses a retraction.json sidecar instead of
        # compile_result.json + last_scan.json. Anything else is a hard skip —
        # it must not fall through to 'compile'.
        event_type = journal.get("event_type", "compile")
        sidecar_dir = descriptor.journal_path.parent / descriptor.run_id
        if event_type == "compile":
            if not (sidecar_dir / "compile_result.json").is_file():
                return EligibilityResult(False, "payload_missing")
            if not (sidecar_dir / "last_scan.json").is_file():
                return EligibilityResult(False, "payload_missing")
        elif event_type == "cleanup":
            if not (sidecar_dir / "retraction.json").is_file():
                return EligibilityResult(False, "payload_missing")
        else:
            return EligibilityResult(False, "unsupported_event_type")

        return EligibilityResult(True, None)
```

(c) Replace the standard-descriptor branch of `load_payload` (everything after the `assert descriptor.journal_path is not None, ...` statement) with:

```python
        sidecar_dir = descriptor.journal_path.parent / descriptor.run_id
        # event_type lives in the journal; re-read to route payload loading (#68).
        with descriptor.journal_path.open() as f:
            event_type = json.load(f).get("event_type", "compile")
        if event_type == "cleanup":
            with (sidecar_dir / "retraction.json").open() as f:
                retraction = json.load(f)
            return retraction, {}, descriptor.run_id
        with (sidecar_dir / "compile_result.json").open() as f:
            mutation = json.load(f)
        with (sidecar_dir / "last_scan.json").open() as f:
            scan = json.load(f)
        return mutation, scan, descriptor.run_id
```

(d) Replace the `apply` method body with `event_type` routing:

```python
    def apply(
        self,
        mutation: dict,
        scan: dict,
        run_id: str,
        conn: kuzu.Connection,
    ) -> SyncResult:
        """Route to the core ingestor by event_type (#68). A 'cleanup' payload
        carries `event_type` + `retracted_slugs`; a compile payload has no
        `event_type` key (absent ⇒ compile). An unrecognized `event_type`
        raises ValueError — `is_eligible` screens these out on the replay path,
        but `apply` is also reachable directly (live sync), so it guards too."""
        event_type = mutation.get("event_type", "compile")
        if event_type == "cleanup":
            from graphdb_kdb.ingestor import apply_cleanup
            return apply_cleanup(mutation, run_id, conn=conn)
        if event_type == "compile":
            from graphdb_kdb.ingestor import apply_compile_result
            return apply_compile_result(mutation, scan, run_id, conn=conn)
        raise ValueError(f"unsupported event_type: {event_type!r}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_rebuilder.py -v`
Expected: PASS — the 5 new routing tests + all existing rebuilder tests green.

- [ ] **Step 6: Commit**

```bash
git add graphdb_kdb/adapters/base.py graphdb_kdb/adapters/obsidian_runs.py graphdb_kdb/tests/test_rebuilder.py
git commit -m "feat(task68.3): ObsidianRunsAdapter routes cleanup events by event_type"
```

---

## Task 4: `sync_cleanup_run` live-sync entry point

**Files:**
- Modify: `graphdb_kdb/adapters/obsidian_runs.py` (add `sync_cleanup_run` after `sync_current_run`)
- Test: `graphdb_kdb/tests/test_rebuilder.py`

- [ ] **Step 1: Write the failing test**

Add to `graphdb_kdb/tests/test_rebuilder.py` (end of file):

```python
def test_sync_cleanup_run_deletes_entity_in_graph(graph_dir):
    # seed an entity via the compile path, then retract it via the cleanup
    # live-sync entry point — both must hit the same graph_dir.
    cr = make_compile_result([
        make_compiled_source("KDB/raw/s.md", [make_page("alpha")])
    ])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    adapter = ObsidianRunsAdapter()
    adapter.sync_current_run(cr, scan, "run-1", graph_dir)
    retraction = {"event_type": "cleanup", "retracted_slugs": ["alpha"]}
    res = adapter.sync_cleanup_run(retraction, "clean-1", graph_dir)
    assert res.entities_deleted == 1
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("alpha") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_rebuilder.py::test_sync_cleanup_run_deletes_entity_in_graph -v`
Expected: FAIL — `AttributeError: 'ObsidianRunsAdapter' object has no attribute 'sync_cleanup_run'`.

- [ ] **Step 3: Implement `sync_cleanup_run`**

In `graphdb_kdb/adapters/obsidian_runs.py`, add after `sync_current_run` (end of class):

```python
    def sync_cleanup_run(
        self,
        retraction: dict,
        run_id: str,
        graph_dir: Path | None = None,
    ) -> SyncResult:
        """Live-sync a cleanup run into the graph (#68).

        `sync_current_run`'s signature is locked by Stage 9 (D-S0) and has no
        slot for a scan-less retraction payload — cleanup gets its own entry
        point. `kdb-clean orphans --apply` calls this; `apply()` routes the
        retraction (event_type='cleanup') to `apply_cleanup`."""
        from graphdb_kdb import default_graph_path
        from graphdb_kdb.graphdb import GraphDB

        resolved = graph_dir if graph_dir is not None else default_graph_path()
        with GraphDB(resolved) as gdb:
            return self.apply(retraction, {}, run_id, gdb.conn)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_rebuilder.py -v`
Expected: PASS — all rebuilder tests green.

- [ ] **Step 5: Commit**

```bash
git add graphdb_kdb/adapters/obsidian_runs.py graphdb_kdb/tests/test_rebuilder.py
git commit -m "feat(task68.4): sync_cleanup_run — adapter live-sync entry point for cleanup"
```

---

## Task 5: `kdb-clean orphans --apply` emits the cleanup journal + sidecar + live-sync

**Files:**
- Modify: `kdb_compiler/kdb_clean.py` (add `build_cleanup_artifacts`; rewrite the `--apply` block of `_cmd_orphans`; update module docstring)
- Test: `kdb_compiler/tests/test_kdb_clean.py`

- [ ] **Step 1: Write the failing tests**

Add to `kdb_compiler/tests/test_kdb_clean.py`. First extend the imports — **replace** the existing line `from kdb_compiler.kdb_clean import main, reap_orphans` (currently at line 13) with:

```python
from kdb_compiler.kdb_clean import build_cleanup_artifacts, main, reap_orphans
```

Add a helper near the top (after `_manifest`):

```python
def _stub_sync(monkeypatch):
    """Stub the graph live-sync so --apply tests don't spin up Kuzu."""
    import types as _types
    monkeypatch.setattr(
        "graphdb_kdb.adapters.obsidian_runs.ObsidianRunsAdapter.sync_cleanup_run",
        lambda self, retraction, run_id, graph_dir=None: _types.SimpleNamespace(
            entities_deleted=0, run_id=run_id),
    )
```

Then the tests:

```python
def test_build_cleanup_artifacts_shapes_journal_and_retraction():
    report = {
        "reaped": [{"page_id": "p", "slug": "s", "page_type": "concept"}],
        "dead_links": [],
        "retracted_slugs": ["s"],
    }
    journal, retraction = build_cleanup_artifacts(
        report, "clean-orphans-2026-05-16T10-16-00",
        "2026-05-16T10:16:00-04:00", "2026-05-16T10:16:01-04:00")
    assert journal["schema_version"] == "2.1"
    assert journal["event_type"] == "cleanup"
    assert journal["success"] is True
    assert journal["dry_run"] is False
    assert journal["summary"]["reaped_count"] == 1
    assert journal["summary"]["retracted_slug_count"] == 1
    assert journal["artifacts"]["retraction_path"].endswith("retraction.json")
    assert retraction["event_type"] == "cleanup"
    assert retraction["retracted_slugs"] == ["s"]
    assert retraction["reaped"] == report["reaped"]


def test_main_orphans_apply_writes_cleanup_journal_and_retraction(tmp_path, monkeypatch):
    _stub_sync(monkeypatch)
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)
    pid = "KDB/wiki/concepts/gone.md"
    md = tmp_path / pid
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# gone", encoding="utf-8")
    manifest = _manifest(
        pages={pid: _page("orphan_candidate", "gone")},
        orphans={pid: {}},
    )
    (state / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    rc = main(["orphans", "--vault-root", str(tmp_path), "--apply"])
    assert rc == 0

    runs = state / "runs"
    journals = list(runs.glob("clean-orphans-*.json"))
    assert len(journals) == 1
    journal = json.loads(journals[0].read_text(encoding="utf-8"))
    assert journal["event_type"] == "cleanup"
    assert journal["schema_version"] == "2.1"

    run_id = journal["run_id"]
    retraction = json.loads(
        (runs / run_id / "retraction.json").read_text(encoding="utf-8"))
    assert retraction["event_type"] == "cleanup"
    assert retraction["retracted_slugs"] == ["gone"]


def test_main_orphans_apply_writes_manifest_before_journal(tmp_path, monkeypatch):
    # crash-consistency invariant (blueprint §6.1): the replay-state journal
    # must never be committed before the live-state manifest.
    _stub_sync(monkeypatch)
    from kdb_compiler import atomic_io
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)
    pid = "KDB/wiki/concepts/gone.md"
    md = tmp_path / pid
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# gone", encoding="utf-8")
    manifest = _manifest(
        pages={pid: _page("orphan_candidate", "gone")},
        orphans={pid: {}},
    )
    (state / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    calls: list[str] = []
    real = atomic_io.atomic_write_json

    def spy(path, obj, **kw):
        from pathlib import Path
        calls.append(Path(path).name)
        return real(path, obj, **kw)

    monkeypatch.setattr("kdb_compiler.kdb_clean.atomic_io.atomic_write_json", spy)
    main(["orphans", "--vault-root", str(tmp_path), "--apply"])

    journal_idx = next(i for i, n in enumerate(calls)
                       if n.startswith("clean-orphans"))
    assert calls.index("retraction.json") < calls.index("manifest.json")
    assert calls.index("manifest.json") < journal_idx
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_clean.py -k "cleanup_artifacts or apply_writes or before_journal" -v`
Expected: FAIL — `ImportError: cannot import name 'build_cleanup_artifacts'`.

- [ ] **Step 3: Add `build_cleanup_artifacts`**

In `kdb_compiler/kdb_clean.py`, add this function after `reap_orphans` (before `_cmd_orphans`):

```python
def build_cleanup_artifacts(
    report: dict,
    run_id: str,
    started_at: str,
    finished_at: str,
) -> tuple[dict, dict]:
    """Build the (journal, retraction) pair for a cleanup run (#68).

    journal     -> state/runs/<run_id>.json    (audit record; replay eligibility)
    retraction  -> state/runs/<run_id>/retraction.json  (the replay payload)

    `report` is a `reap_orphans()` return dict. Pure — also used by the
    one-shot backfill (scripts/backfill_cleanup_journal.py).
    """
    retraction = {
        "event_type": "cleanup",
        "run_id": run_id,
        "reaped": report["reaped"],
        "retracted_slugs": report["retracted_slugs"],
        "dead_links": report["dead_links"],
    }
    journal = {
        "schema_version": "2.1",
        "event_type": "cleanup",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "success": True,
        "dry_run": False,
        "summary": {
            "reaped_count": len(report["reaped"]),
            "retracted_slug_count": len(report["retracted_slugs"]),
            "dead_link_count": len(report["dead_links"]),
        },
        "artifacts": {"retraction_path": f"state/runs/{run_id}/retraction.json"},
    }
    return journal, retraction
```

- [ ] **Step 4: Rewrite the `--apply` block of `_cmd_orphans`**

In `kdb_compiler/kdb_clean.py`, in `_cmd_orphans`, replace everything from `run_id = f"clean-orphans-...` through the end of the function (the archival loop, `assert_manifest_invariants`, `atomic_write_json` of the manifest, the audit-file write, and the closing `NOTE` prints) with:

```python
    # Capture the clock ONCE (aware) so run_id and started_at can never disagree.
    now_dt = datetime.now().astimezone()
    run_id = f"clean-orphans-{now_dt.strftime('%Y-%m-%dT%H-%M-%S')}"
    started_at = now_dt.isoformat(timespec="seconds")
    runs_root = state_root / "runs"
    archive_root = state_root / "orphan-archive" / run_id

    # Write order is crash-consistency-critical (blueprint §6.1):
    #   archive -> retraction sidecar -> manifest -> journal -> live-sync.
    # The journal (replay state) must never be committed before the manifest
    # (live state); the sidecar is inert until the journal references it.

    # 1. archive the .md files
    for r in report["reaped"]:
        src = vault_root / r["page_id"]
        dst = archive_root / r["page_id"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.move(str(src), str(dst))
        else:
            print(f"note    {r['page_id']} — file already absent, manifest-only reap")

    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    journal, retraction = build_cleanup_artifacts(
        report, run_id, started_at, finished_at)

    # 2. retraction sidecar — inert until the journal references it
    sidecar_dir = runs_root / run_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    atomic_io.atomic_write_json(sidecar_dir / "retraction.json", retraction,
                                sort_keys=True)

    # 3. atomic manifest write — commits live state
    assert_manifest_invariants(manifest)
    atomic_io.atomic_write_json(manifest_path, manifest, sort_keys=True)

    # 4. atomic journal write — commits replay state (MUST follow the manifest)
    atomic_io.atomic_write_json(runs_root / f"{run_id}.json", journal,
                                sort_keys=True)

    print(f"\nAPPLIED — {len(report['reaped'])} page(s) archived to {archive_root}")
    print(f"          manifest updated; cleanup journal at "
          f"{runs_root / (run_id + '.json')}")

    # 5. live-sync the retraction into the graph (best-effort — blueprint §6.4).
    # On failure the manifest is still the source of truth and the journal from
    # step 4 makes the next `graphdb-kdb rebuild` reconverge.
    try:
        from graphdb_kdb.adapters.obsidian_runs import ObsidianRunsAdapter
        sync = ObsidianRunsAdapter().sync_cleanup_run(retraction, run_id)
        print(f"          graph live-sync: {sync.entities_deleted} "
              f"entity(ies) retracted")
    except Exception as exc:  # noqa: BLE001 — best-effort, never fails the reap
        print(f"WARN    graph live-sync failed ({type(exc).__name__}: {exc}); "
              f"run `graphdb-kdb rebuild` to reconverge.")
    return 0
```

Note: the `if not report["reaped"]: ... return 0` guard and the `if not args.apply: ... return 0` dry-run block stay exactly as they are, before this block.

- [ ] **Step 5: Update the module docstring**

In `kdb_compiler/kdb_clean.py`, replace the `GraphDB-KDB caveat (Task #68): ...` paragraph in the module docstring with:

```
GraphDB-KDB sync (Task #68): `orphans --apply` writes a replayable `cleanup`
run journal + `retraction.json` sidecar into `state/runs/` and live-syncs the
retraction into the graph through the Obsidian adapter. `graphdb-kdb rebuild`
replays the cleanup event chronologically, so the reaped pages stay retracted
instead of being re-introduced.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_kdb_clean.py -v`
Expected: PASS — all tests green (existing + 3 new).

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/kdb_clean.py kdb_compiler/tests/test_kdb_clean.py
git commit -m "feat(task68.5): kdb-clean orphans --apply emits replayable cleanup journal"
```

---

## Task 6: End-to-end cleanup replay through `rebuild`

**Files:**
- Test: `graphdb_kdb/tests/test_rebuilder.py` (the `_write_cleanup_run` helper from Task 3 is reused)

This task is test-only — it proves the D39 independence property for the cleanup event (replay of eligible runs ≡ live state). No production code changes; if a test fails, the bug is in Task 2–5 code.

- [ ] **Step 1: Write the tests**

Add to `graphdb_kdb/tests/test_rebuilder.py` (end of file):

```python
def test_rebuild_replays_cleanup_event_deletes_entity(tmp_path, graph_dir):
    journals = tmp_path / "runs"
    _write_run(journals, "2026-01-01T00-00-00",
               started_at="2026-01-01T00:00:00",
               sources=[("KDB/raw/s.md", ["keep", "drop"])])
    _write_cleanup_run(journals, "clean-orphans-2026-02-01T00-00-00",
                       ["drop"], started_at="2026-02-01T00:00:00")
    result = rebuild(graph_dir, ObsidianRunsAdapter(),
                     journals_dir=journals, confirm=False)
    assert result.ok
    assert result.replayed == 2
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("drop") is None    # retracted by the cleanup event
        assert gdb.get_entity("keep") is not None


def test_rebuild_cleanup_then_later_compile_re_emits_slug(tmp_path, graph_dir):
    # A compile run AFTER the cleanup that re-emits a retracted slug correctly
    # re-creates it — the cleanup is positional, not permanent.
    journals = tmp_path / "runs"
    _write_run(journals, "2026-01-01T00-00-00",
               started_at="2026-01-01T00:00:00",
               sources=[("KDB/raw/s.md", ["x"])])
    _write_cleanup_run(journals, "clean-orphans-2026-02-01T00-00-00",
                       ["x"], started_at="2026-02-01T00:00:00")
    _write_run(journals, "2026-03-01T00-00-00",
               started_at="2026-03-01T00:00:00",
               sources=[("KDB/raw/s.md", ["x"])])
    result = rebuild(graph_dir, ObsidianRunsAdapter(),
                     journals_dir=journals, confirm=False)
    assert result.ok
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("x") is not None   # re-emitted after retraction


def test_rebuild_slug_safe_when_slug_survives_under_another_page(tmp_path, graph_dir):
    # Codex's named slug-safe integration test: the same slug 'foo' is emitted
    # by an active article AND an orphaned concept. The cleanup retracts only
    # the concept's page_id — but 'foo' still has a surviving article page, so
    # reap_orphans excludes 'foo' from retracted_slugs and the graph entity
    # 'foo' (one slug-keyed node) must survive.
    from kdb_compiler.kdb_clean import reap_orphans

    # graph: one source emits entity 'foo' (still active) + entity 'solo'.
    journals = tmp_path / "runs"
    _write_run(journals, "2026-01-01T00-00-00",
               started_at="2026-01-01T00:00:00",
               sources=[("KDB/raw/s.md", ["foo", "solo"])])

    # manifest: 'foo' as an active article + an orphaned concept; 'solo' orphan.
    manifest = {
        "pages": {
            "KDB/wiki/articles/foo.md": {
                "status": "active", "slug": "foo", "page_type": "article",
                "page_id": "KDB/wiki/articles/foo.md", "outgoing_links": [],
            },
            "KDB/wiki/concepts/foo.md": {
                "status": "orphan_candidate", "slug": "foo", "page_type": "concept",
                "page_id": "KDB/wiki/concepts/foo.md", "outgoing_links": [],
            },
            "KDB/wiki/concepts/solo.md": {
                "status": "orphan_candidate", "slug": "solo", "page_type": "concept",
                "page_id": "KDB/wiki/concepts/solo.md", "outgoing_links": [],
            },
        },
        "orphans": {"KDB/wiki/concepts/foo.md": {}, "KDB/wiki/concepts/solo.md": {}},
    }
    report = reap_orphans(manifest)
    assert "foo" not in report["retracted_slugs"]   # survives under the article
    assert report["retracted_slugs"] == ["solo"]

    _write_cleanup_run(journals, "clean-orphans-2026-02-01T00-00-00",
                       report["retracted_slugs"],
                       started_at="2026-02-01T00:00:00")
    result = rebuild(graph_dir, ObsidianRunsAdapter(),
                     journals_dir=journals, confirm=False)
    assert result.ok
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("foo") is not None    # slug-safe — must survive
        assert gdb.get_entity("solo") is None       # genuinely retracted
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest graphdb_kdb/tests/test_rebuilder.py -k "rebuild_replays_cleanup or re_emits or slug_safe" -v`
Expected: PASS — all three tests green. If they fail, fix the Task 2–5 code (do not weaken the tests).

- [ ] **Step 3: Run the full graphdb suite for regressions**

Run: `.venv/bin/python -m pytest graphdb_kdb/ -v`
Expected: PASS — all graphdb tests green.

- [ ] **Step 4: Commit**

```bash
git add graphdb_kdb/tests/test_rebuilder.py
git commit -m "test(task68.6): end-to-end cleanup-event replay through rebuild"
```

---

## Task 7: Producer-contract amendment + CODEBASE_OVERVIEW

**Files:**
- Modify: `docs/graphdb-kdb-producer-contract.md` (§3.3, §3.4, §4)
- Modify: `docs/CODEBASE_OVERVIEW.md` (drop the #68 maintenance caveat)

Docs-only task — no test (documentation is a TDD exception). Read each file before editing.

- [ ] **Step 1: Amend producer-contract §3.3 (run journal)**

In `docs/graphdb-kdb-producer-contract.md`, in §3.3, append a new row to the "Contract requirements" table:

```
| `event_type` (string, optional) | Discriminates run kinds in one journal stream — `"compile"` (or absent) vs `"cleanup"` (Task #68 retraction event) | Optional; **absent ⇒ `"compile"`** for back-compat with 2.0 journals. A `cleanup` journal is `schema_version: "2.1"`. |
```

- [ ] **Step 2: Amend producer-contract §3.4 (sidecar archive)**

In §3.4, after the "Today's reference" code block, add:

```
**Cleanup-event sidecar (Task #68):** a `cleanup` run's sidecar directory
contains `retraction.json` (the retraction payload — `reaped` audit records +
`retracted_slugs`) instead of `compile_result.json` + `last_scan.json`. The
adapter selects the sidecar contents to require by the journal's `event_type`.
```

- [ ] **Step 3: Amend producer-contract §4 (adapter interface)**

In §4, after "Critical adapter rules", add a new numbered rule:

```
8. **The adapter routes by `event_type`.** `is_eligible`, `load_payload`, and
   `apply` read the journal's `event_type` (absent ⇒ `compile`). A `cleanup`
   event loads `retraction.json` and `apply` dispatches to `apply_cleanup`
   (`DETACH DELETE` of `Entity` by `retracted_slugs`). An unrecognized
   `event_type` is skipped with `SkipReason='unsupported_event_type'` — it
   must never fall through to the compile path. `RunDescriptor` is unchanged;
   the discriminator lives in the journal JSON, not the descriptor.
```

- [ ] **Step 4: Update CODEBASE_OVERVIEW**

In `docs/CODEBASE_OVERVIEW.md`, find the "Maintenance caveat" paragraph added after §8.4 (it states `kdb-clean orphans` is not yet replay-covered, #68). Replace it with:

```
**Maintenance — `kdb-clean orphans`:** `--apply` archives orphan pages, removes
them from `manifest.json`, and emits a replayable `cleanup` run journal +
`retraction.json` sidecar into `state/runs/`. `graphdb-kdb rebuild` replays the
cleanup event chronologically, so reaped pages stay retracted (Task #68).
```

- [ ] **Step 5: Commit**

```bash
git add docs/graphdb-kdb-producer-contract.md docs/CODEBASE_OVERVIEW.md
git commit -m "docs(task68.7): producer-contract amendment for the cleanup event"
```

---

## Task 8: Backfill script for the pre-#68 16-orphan reap

**Files:**
- Create: `scripts/backfill_cleanup_journal.py`
- Test: `kdb_compiler/tests/test_backfill_cleanup_journal.py` (create)

**Why:** the 16-orphan reap in commit `f23c74b` ran before #68 and has no cleanup journal — `state/kdb-clean-orphans-audit-clean-orphans-2026-05-16T10-16-00.json`. Without a synthesized journal, `graphdb-kdb rebuild` still re-introduces those 16. This script reads that audit file, computes `retracted_slugs` against the current (post-reap) manifest, and writes the journal + sidecar.

- [ ] **Step 1: Write the failing tests**

Create `kdb_compiler/tests/test_backfill_cleanup_journal.py`:

```python
"""Tests for the one-shot #68 cleanup-journal backfill (pure functions)."""
from __future__ import annotations

from scripts.backfill_cleanup_journal import (
    compute_retracted_slugs,
    started_at_from_run_id,
)


def test_compute_retracted_slugs_excludes_slugs_still_in_manifest():
    reaped = [
        {"slug": "gone", "page_id": "KDB/wiki/concepts/gone.md", "page_type": "concept"},
        {"slug": "kept", "page_id": "KDB/wiki/articles/kept.md", "page_type": "article"},
    ]
    # 'kept' still has a live page in the manifest; 'gone' does not.
    manifest = {"pages": {"KDB/wiki/articles/kept.md": {"slug": "kept"}}}
    assert compute_retracted_slugs(reaped, manifest) == ["gone"]


def test_compute_retracted_slugs_all_removed():
    reaped = [
        {"slug": "a", "page_id": "p1", "page_type": "concept"},
        {"slug": "b", "page_id": "p2", "page_type": "concept"},
    ]
    manifest = {"pages": {}}
    assert compute_retracted_slugs(reaped, manifest) == ["a", "b"]


def test_started_at_from_run_id_attaches_local_offset():
    out = started_at_from_run_id("clean-orphans-2026-05-16T10-16-00")
    # naive timestamp stem -> local-ISO-with-offset (date + time preserved)
    assert out.startswith("2026-05-16T10:16:00")
    assert ("+" in out[19:]) or ("-" in out[19:])  # an offset is present
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_backfill_cleanup_journal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_cleanup_journal'`.

- [ ] **Step 3: Create the backfill script**

Create `scripts/backfill_cleanup_journal.py`:

```python
#!/usr/bin/env python3
"""One-shot #68 backfill — synthesize a cleanup journal for a pre-#68 reap.

`kdb-clean orphans --apply` runs before Task #68 wrote no cleanup journal, only
a standalone audit file (`state/kdb-clean-orphans-audit-<run-id>.json`). Without
a journal, `graphdb-kdb rebuild` re-introduces the reaped pages. This script
reads that audit file, computes `retracted_slugs` against the CURRENT manifest,
and writes the journal + retraction sidecar into `state/runs/` so rebuild
converges.

Dry-run by DEFAULT — pass `--apply` to write.

Usage:
    python -m scripts.backfill_cleanup_journal --vault-root <path> \\
        --audit <state/kdb-clean-orphans-audit-...json> [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from kdb_compiler import atomic_io
from kdb_compiler.kdb_clean import build_cleanup_artifacts


def compute_retracted_slugs(reaped: list[dict], manifest: dict) -> list[str]:
    """A reaped slug is retracted iff no page in the current manifest carries
    it. The manifest here is post-reap (and post-canonical-recompile), so a
    reaped slug absent from it is genuinely gone."""
    reaped_slugs = {r["slug"] for r in reaped if r.get("slug")}
    live_slugs = {p.get("slug") for p in manifest.get("pages", {}).values()}
    return sorted(reaped_slugs - live_slugs)


def started_at_from_run_id(run_id: str) -> str:
    """`clean-orphans-2026-05-16T10-16-00` -> local-ISO-with-offset.
    The run_id stem is a naive local timestamp; re-emit it with the offset."""
    stem = run_id.removeprefix("clean-orphans-")
    naive = datetime.strptime(stem, "%Y-%m-%dT%H-%M-%S")
    return naive.astimezone().isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="backfill_cleanup_journal")
    p.add_argument("--vault-root", required=True,
                   help="Absolute path to the Obsidian vault root")
    p.add_argument("--audit", required=True,
                   help="Path to the kdb-clean-orphans-audit-*.json file")
    p.add_argument("--apply", action="store_true",
                   help="Write the journal + sidecar (default is dry-run)")
    args = p.parse_args(argv)

    vault_root = Path(args.vault_root).resolve()
    state_root = vault_root / "KDB" / "state"
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    manifest = json.loads(
        (state_root / "manifest.json").read_text(encoding="utf-8"))

    run_id = audit["run_id"]
    reaped = audit["reaped"]
    retracted_slugs = compute_retracted_slugs(reaped, manifest)
    report = {
        "reaped": reaped,
        "dead_links": audit.get("dead_links", []),
        "retracted_slugs": retracted_slugs,
    }
    started = started_at_from_run_id(run_id)
    journal, retraction = build_cleanup_artifacts(report, run_id, started, started)

    print(f"run_id:           {run_id}")
    print(f"reaped pages:     {len(reaped)}")
    print(f"retracted slugs:  {len(retracted_slugs)}  {retracted_slugs}")
    print(f"journal -> state/runs/{run_id}.json")
    print(f"sidecar -> state/runs/{run_id}/retraction.json")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit.")
        return 0

    runs_root = state_root / "runs"
    sidecar_dir = runs_root / run_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    atomic_io.atomic_write_json(sidecar_dir / "retraction.json", retraction,
                                sort_keys=True)
    atomic_io.atomic_write_json(runs_root / f"{run_id}.json", journal,
                                sort_keys=True)
    print("\nAPPLIED — journal + retraction sidecar written. Next: "
          "`graphdb-kdb rebuild` then `graphdb-kdb verify`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Ensure `scripts/` is an importable package**

The test imports `scripts.backfill_cleanup_journal`, so `scripts/` must be a package. Run (idempotent — a no-op if the file already exists):

```bash
touch scripts/__init__.py
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_compiler/tests/test_backfill_cleanup_journal.py -v`
Expected: PASS — all 3 tests green.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_cleanup_journal.py kdb_compiler/tests/test_backfill_cleanup_journal.py
# also add scripts/__init__.py if it was created in Step 4
git commit -m "feat(task68.8): one-shot backfill — cleanup journal for the pre-#68 reap"
```

---

## Task 9: Live backfill + rebuild + verify (human-gated)

**Files:** none (operational task). Modify `docs/TASKS.md` at the end.

This task mutates live vault state (`state/runs/`) and the live graph. Per the project's migration discipline, the `--apply` step is **human-gated** — present the dry-run, get explicit "Proceed", then apply.

- [ ] **Step 1: Run the full suite — confirm green before touching live state**

Run: `.venv/bin/python -m pytest`
Expected: all pass, 0 failures (1 skip acceptable).

- [ ] **Step 2: Backfill dry-run**

Run:
```bash
.venv/bin/python -m scripts.backfill_cleanup_journal \
  --vault-root /home/ftu/Obsidian \
  --audit "/home/ftu/Obsidian/KDB/state/kdb-clean-orphans-audit-clean-orphans-2026-05-16T10-16-00.json"
```
Expected: prints `reaped pages: 16` and a `retracted slugs:` count — between 0 and 16, depending on how many reaped slugs survive under another active page (the dry-run prints the actual number; do not assume it). Confirm the retracted-slug list looks right with the human partner.

- [ ] **Step 3: Backfill apply (after human "Proceed")**

Run the same command with `--apply` appended.
Expected: `APPLIED — journal + retraction sidecar written.` Verify the files exist:
```bash
ls "/home/ftu/Obsidian/KDB/state/runs/clean-orphans-2026-05-16T10-16-00.json"
ls "/home/ftu/Obsidian/KDB/state/runs/clean-orphans-2026-05-16T10-16-00/retraction.json"
```

- [ ] **Step 4: Rebuild the graph**

Run:
```bash
graphdb-kdb rebuild --vault-root /home/ftu/Obsidian --yes
```
Expected: rebuild reports the cleanup run among `replayed` outcomes; `failed: 0`.

- [ ] **Step 5: Verify convergence**

Run:
```bash
graphdb-kdb verify --vault-root /home/ftu/Obsidian
```
Classify the `verify` output **by drift class** — do not report a vague "verify improved":
- **reap-residue** (entities re-introduced by replay) — MUST be **0**. This is the #68 acceptance criterion.
- **`compile_count` attribute drift** (≈8, uniform −1) — MAY remain; explicitly out of #68 scope (blueprint §9, possible #69).
- **dead link** (1–2) — MAY remain; a content fix, out of #68 scope (blueprint §9).

Acceptance: **reap-residue class = 0**. A non-empty `verify` is acceptable only if every remaining issue is in the two out-of-scope classes above; any residual reap-residue means #68 is not done.

- [ ] **Step 6: Mark #68 done in TASKS.md**

Read `docs/TASKS.md`, then change the #68 row's status from `open` to `done` and append a closure note: `closed 2026-05-16 — replayable cleanup/retraction event; backfill applied, rebuild+verify confirm reap-residue drift = 0.`

- [ ] **Step 7: Final commit**

```bash
git add docs/TASKS.md
git commit -m "docs(task68): close #68 — cleanup retraction event live + verified"
```

---

## Final review

After all 9 tasks: dispatch a final code-review subagent over the whole #68 change set (commits `task68.1`→`task68`), confirm the full suite is green, and report the `verify` reap-residue delta (should be −25, i.e. 0 remaining).

---

## Self-Review (plan author's check against the blueprint)

**Spec coverage** — every blueprint section maps to a task:
- §3 slug-vs-page_id (`retracted_slugs`) → Task 1
- §2 + §6.2 DELETE-pattern / `apply_cleanup` → Task 2
- §6.3 adapter routing + §6 unknown-event rule → Task 3
- §6.4 `sync_cleanup_run` → Task 4
- §5 data shapes + §6.1 write order + live-sync → Task 5
- §7 end-to-end replay + named slug-safe tests → Tasks 1, 2, 6
- §4 contract amendment → Task 7
- §6.5 backfill → Tasks 8, 9
- §7 acceptance = reap-residue → 0 → Task 9 Step 5

**Type consistency** — `build_cleanup_artifacts(report, run_id, started_at, finished_at) -> (journal, retraction)` is defined in Task 5 and consumed identically in Task 8. `SyncResult.entities_deleted` is added in Task 2 and asserted in Tasks 2, 3, 4. `retracted_slugs` key is produced in Task 1, consumed in Tasks 5, 8. `event_type` discriminator is consistent across journal + retraction payload in Tasks 3, 5.

**Placeholder scan** — no TBD/TODO; every code step has complete code; every test step has full test bodies.
