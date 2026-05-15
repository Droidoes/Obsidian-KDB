# Task #64 — Recompile Page Supersession Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a source's recompile remove that source's support from prior pages the new run no longer emits, so pre-#37 summaries (and any model-volume-variance casualties) get flagged `orphan_candidate` instead of lingering as stale duplicates.

**Architecture:** Add a per-source supersession step to `manifest_update.apply_compile_result()`, mirroring the graph ingestor's already-correct `_replace_supports_for_source`. The existing orphan pass then flags newly-unsupported pages. A one-shot no-API migration script repairs the 3 already-crossed sources. See `docs/task64-recompile-supersession-blueprint.md` for the design and decisions D41–D44.

**Tech Stack:** Python 3, pytest, the `kdb_compiler` package. No new dependencies.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `kdb_compiler/manifest_update.py` | Manifest core — page upsert, supersession, invariants | Modify: add `_supersede_omitted_pages()`, call it in `apply_compile_result()`, make `assert_manifest_invariants()` status-aware |
| `kdb_compiler/tests/test_manifest_update.py` | Manifest unit tests | Modify: add supersession + invariant tests |
| `scripts/migrate_task64_supersession.py` | One-shot data repair for the 3 crossed sources | Create |
| `docs/CODEBASE_OVERVIEW.md` | Decision ledger | Modify: append D41–D44 |

**Key shared helper signature** (defined in Task 1, used by Tasks 2 + 6):

```python
def _supersede_omitted_pages(
    manifest: dict, source_id: str, emitted_keys: set[str],
    *, started_at: str, run_id: str,
) -> list[str]:
    """Drop source_id from supports_page_existence + source_refs of every
    page the source previously supported but did NOT emit this run. When a
    removal empties a page's support, seed its orphans[] entry (preserving
    previous_supporting_sources). Returns the list of affected page_keys.
    Plain str params (not RunContext) so the migration script can call it."""
```

---

## Task 1: `_supersede_omitted_pages()` helper

**Files:**
- Modify: `kdb_compiler/manifest_update.py` (add helper near `_purge_source_from_pages`, ~line 233)
- Test: `kdb_compiler/tests/test_manifest_update.py`

- [ ] **Step 1: Write the failing test**

Add to `kdb_compiler/tests/test_manifest_update.py` (end of file):

```python
# ---------- Task #64: supersession ----------

def test_supersede_omitted_pages_removes_source_and_seeds_orphan() -> None:
    from kdb_compiler.manifest_update import _supersede_omitted_pages
    m = manifest_update.ensure_manifest_shape({}, ctx=_ctx())
    # Page solely supported by source X, which the new run no longer emits.
    m["pages"]["KDB/wiki/summaries/old.md"] = {
        "page_id": "KDB/wiki/summaries/old.md", "slug": "old",
        "page_type": "summary", "status": "active", "title": "Old",
        "source_refs": [{"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"}],
        "supports_page_existence": ["KDB/raw/x.md"],
        "outgoing_links": [], "incoming_links_known": [],
        "confidence": "medium", "orphan_candidate": False,
    }
    affected = _supersede_omitted_pages(
        m, "KDB/raw/x.md", emitted_keys={"KDB/wiki/summaries/summary-x.md"},
        started_at="2026-05-15T09:00:00-04:00", run_id="r-test",
    )
    page = m["pages"]["KDB/wiki/summaries/old.md"]
    assert affected == ["KDB/wiki/summaries/old.md"]
    assert page["supports_page_existence"] == []
    assert page["source_refs"] == []
    orphan = m["orphans"]["KDB/wiki/summaries/old.md"]
    assert orphan["previous_supporting_sources"] == ["KDB/raw/x.md"]
    assert orphan["reason"].startswith("superseded")


def test_supersede_skips_emitted_and_unrelated_pages() -> None:
    from kdb_compiler.manifest_update import _supersede_omitted_pages
    m = manifest_update.ensure_manifest_shape({}, ctx=_ctx())
    # Emitted page — must be left alone even though X supports it.
    m["pages"]["KDB/wiki/summaries/summary-x.md"] = {
        "page_id": "KDB/wiki/summaries/summary-x.md", "slug": "summary-x",
        "page_type": "summary", "status": "active", "title": "X",
        "source_refs": [{"source_id": "KDB/raw/x.md", "hash": H1, "role": "primary"}],
        "supports_page_existence": ["KDB/raw/x.md"],
        "outgoing_links": [], "incoming_links_known": [],
        "confidence": "medium", "orphan_candidate": False,
    }
    # Unrelated page — supported by Y, not X.
    m["pages"]["KDB/wiki/concepts/y.md"] = {
        "page_id": "KDB/wiki/concepts/y.md", "slug": "y",
        "page_type": "concept", "status": "active", "title": "Y",
        "source_refs": [{"source_id": "KDB/raw/y.md", "hash": H2, "role": "supporting"}],
        "supports_page_existence": ["KDB/raw/y.md"],
        "outgoing_links": [], "incoming_links_known": [],
        "confidence": "medium", "orphan_candidate": False,
    }
    affected = _supersede_omitted_pages(
        m, "KDB/raw/x.md", emitted_keys={"KDB/wiki/summaries/summary-x.md"},
        started_at="2026-05-15T09:00:00-04:00", run_id="r-test",
    )
    assert affected == []
    assert m["pages"]["KDB/wiki/summaries/summary-x.md"]["supports_page_existence"] == ["KDB/raw/x.md"]
    assert m["pages"]["KDB/wiki/concepts/y.md"]["supports_page_existence"] == ["KDB/raw/y.md"]
    assert m["orphans"] == {}


def test_supersede_shared_page_keeps_other_source() -> None:
    from kdb_compiler.manifest_update import _supersede_omitted_pages
    m = manifest_update.ensure_manifest_shape({}, ctx=_ctx())
    # Concept supported by BOTH X and Y; X no longer emits it, Y still does.
    m["pages"]["KDB/wiki/concepts/shared.md"] = {
        "page_id": "KDB/wiki/concepts/shared.md", "slug": "shared",
        "page_type": "concept", "status": "active", "title": "Shared",
        "source_refs": [
            {"source_id": "KDB/raw/x.md", "hash": H1, "role": "supporting"},
            {"source_id": "KDB/raw/y.md", "hash": H2, "role": "supporting"},
        ],
        "supports_page_existence": ["KDB/raw/x.md", "KDB/raw/y.md"],
        "outgoing_links": [], "incoming_links_known": [],
        "confidence": "medium", "orphan_candidate": False,
    }
    affected = _supersede_omitted_pages(
        m, "KDB/raw/x.md", emitted_keys=set(),
        started_at="2026-05-15T09:00:00-04:00", run_id="r-test",
    )
    page = m["pages"]["KDB/wiki/concepts/shared.md"]
    assert affected == ["KDB/wiki/concepts/shared.md"]
    assert page["supports_page_existence"] == ["KDB/raw/y.md"]
    assert [r["source_id"] for r in page["source_refs"]] == ["KDB/raw/y.md"]
    # Support is non-empty → no orphan entry seeded.
    assert m["orphans"] == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -k supersede -v`
Expected: FAIL — `ImportError: cannot import name '_supersede_omitted_pages'`

- [ ] **Step 3: Write the helper**

In `kdb_compiler/manifest_update.py`, add immediately after `_rekey_source_in_pages()` (after line ~243, before `apply_scan_reconciliation`):

```python
def _supersede_omitted_pages(
    manifest: dict, source_id: str, emitted_keys: set[str],
    *, started_at: str, run_id: str,
) -> list[str]:
    """Drop source_id from supports_page_existence + source_refs of every
    page the source previously supported but did NOT emit this run.

    The diff-form of graphdb_kdb's _replace_supports_for_source (drop-all-
    then-recreate). When a removal empties a page's support, seed its
    orphans[] entry so the orphan pass that runs next preserves the
    previous_supporting_sources provenance via setdefault.

    Returns the sorted list of affected page_keys.
    """
    affected: list[str] = []
    for page_key, page in manifest["pages"].items():
        if page_key in emitted_keys:
            continue
        support = page.get("supports_page_existence", [])
        if source_id not in support:
            continue
        prior_support = list(support)
        page["supports_page_existence"] = [s for s in support if s != source_id]
        page["source_refs"] = [
            r for r in page.get("source_refs", [])
            if r.get("source_id") != source_id
        ]
        affected.append(page_key)
        if not page["supports_page_existence"]:
            manifest.setdefault("orphans", {}).setdefault(page_key, {
                "page_id": page_key,
                "flagged_at": started_at,
                "reason": "superseded — source no longer emits this page",
                "previous_supporting_sources": prior_support,
                "recommended_action": "review_manually",
                "last_run_id": run_id,
            })
    return sorted(affected)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -k supersede -v`
Expected: PASS — 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/manifest_update.py kdb_compiler/tests/test_manifest_update.py
git commit -m "feat(task64): _supersede_omitted_pages helper (D41)"
```

---

## Task 2: Wire supersession into `apply_compile_result()`

**Files:**
- Modify: `kdb_compiler/manifest_update.py` — `apply_compile_result()`, inside the `for cs` loop after the source-record block (after line ~478, before the loop ends)
- Test: `kdb_compiler/tests/test_manifest_update.py`

- [ ] **Step 1: Write the failing test**

Add to `kdb_compiler/tests/test_manifest_update.py` (end of file):

```python
def test_recompile_supersedes_pre37_summary_slug() -> None:
    # Run 1: pre-#37 — summary slug WITHOUT the `summary-` prefix.
    ctx1 = _ctx(run_id="r1", started_at="2026-04-19T01:00:00Z")
    m = manifest_update.ensure_manifest_shape({}, ctx=ctx1)
    scan1 = _scan(run_id="r1", files=[_file("KDB/raw/p.md", "NEW")],
                  to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan1, ctx1)
    cr1 = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/p.md", "buffett-interview",
        pages=[_page("buffett-interview", "summary", "Buffett")],
    )])
    apply_compile_result(m, cr1, scan1, ctx1)
    assert m["pages"]["KDB/wiki/summaries/buffett-interview.md"]["status"] == "active"

    # Run 2: post-#37 — same source, summary slug WITH the prefix.
    ctx2 = _ctx(run_id="r2", started_at="2026-05-15T02:00:00Z")
    scan2 = _scan(run_id="r2",
                  files=[_file("KDB/raw/p.md", "CHANGED", h=H2, prev_hash=H1, prev_mtime=1.0)],
                  to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan2, ctx2)
    cr2 = _compile("r2", compiled_sources=[_cs(
        "KDB/raw/p.md", "summary-buffett-interview",
        pages=[_page("summary-buffett-interview", "summary", "Buffett")],
    )])
    apply_compile_result(m, cr2, scan2, ctx2)

    old = m["pages"]["KDB/wiki/summaries/buffett-interview.md"]
    new = m["pages"]["KDB/wiki/summaries/summary-buffett-interview.md"]
    assert old["status"] == "orphan_candidate"
    assert old["orphan_candidate"] is True
    assert old["supports_page_existence"] == []
    assert "KDB/wiki/summaries/buffett-interview.md" in m["orphans"]
    assert m["orphans"]["KDB/wiki/summaries/buffett-interview.md"][
        "previous_supporting_sources"] == ["KDB/raw/p.md"]
    assert new["status"] == "active"


def test_recompile_omitted_article_orphaned_shared_concept_survives() -> None:
    # Run 1: source A emits summary + article + concept.
    ctx1 = _ctx(run_id="r1", started_at="2026-04-19T01:00:00Z")
    m = manifest_update.ensure_manifest_shape({}, ctx=ctx1)
    scan1 = _scan(run_id="r1", files=[_file("KDB/raw/a.md", "NEW")],
                  to_compile=["KDB/raw/a.md"])
    apply_scan_reconciliation(m, scan1, ctx1)
    cr1 = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/a.md", "summary-a",
        pages=[
            _page("summary-a", "summary"),
            _page("a-article", "article"),
            _page("shared-concept", "concept"),
        ],
        concept_slugs=["shared-concept"], article_slugs=["a-article"],
    )])
    apply_compile_result(m, cr1, scan1, ctx1)
    # Source B also emits shared-concept (second supporter).
    ctx1b = _ctx(run_id="r1b", started_at="2026-04-19T01:30:00Z")
    scan1b = _scan(run_id="r1b", files=[_file("KDB/raw/b.md", "NEW", h=H3)],
                   to_compile=["KDB/raw/b.md"])
    apply_scan_reconciliation(m, scan1b, ctx1b)
    cr1b = _compile("r1b", compiled_sources=[_cs(
        "KDB/raw/b.md", "summary-b",
        pages=[_page("summary-b", "summary"), _page("shared-concept", "concept")],
        concept_slugs=["shared-concept"],
    )])
    apply_compile_result(m, cr1b, scan1b, ctx1b)

    # Run 2: recompile A — summary only (drops article + concept).
    ctx2 = _ctx(run_id="r2", started_at="2026-05-15T02:00:00Z")
    scan2 = _scan(run_id="r2",
                  files=[_file("KDB/raw/a.md", "CHANGED", h=H2, prev_hash=H1, prev_mtime=1.0)],
                  to_compile=["KDB/raw/a.md"])
    apply_scan_reconciliation(m, scan2, ctx2)
    cr2 = _compile("r2", compiled_sources=[_cs(
        "KDB/raw/a.md", "summary-a",
        pages=[_page("summary-a", "summary")],
    )])
    apply_compile_result(m, cr2, scan2, ctx2)

    # Omitted article — solely supported by A → orphaned.
    assert m["pages"]["KDB/wiki/articles/a-article.md"]["status"] == "orphan_candidate"
    # Shared concept — still supported by B → stays active.
    shared = m["pages"]["KDB/wiki/concepts/shared-concept.md"]
    assert shared["status"] == "active"
    assert shared["supports_page_existence"] == ["KDB/raw/b.md"]


def test_recompile_supersession_is_idempotent() -> None:
    ctx1 = _ctx(run_id="r1", started_at="2026-04-19T01:00:00Z")
    m = manifest_update.ensure_manifest_shape({}, ctx=ctx1)
    scan1 = _scan(run_id="r1", files=[_file("KDB/raw/p.md", "NEW")],
                  to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan1, ctx1)
    cr1 = _compile("r1", compiled_sources=[_cs(
        "KDB/raw/p.md", "summary-p", pages=[_page("summary-p", "summary")])])
    apply_compile_result(m, cr1, scan1, ctx1)

    # Re-apply the same emitted set — nothing should orphan or thrash.
    ctx2 = _ctx(run_id="r2", started_at="2026-05-15T02:00:00Z")
    scan2 = _scan(run_id="r2",
                  files=[_file("KDB/raw/p.md", "CHANGED", h=H2, prev_hash=H1, prev_mtime=1.0)],
                  to_compile=["KDB/raw/p.md"])
    apply_scan_reconciliation(m, scan2, ctx2)
    cr2 = _compile("r2", compiled_sources=[_cs(
        "KDB/raw/p.md", "summary-p", pages=[_page("summary-p", "summary")])])
    apply_compile_result(m, cr2, scan2, ctx2)

    assert m["pages"]["KDB/wiki/summaries/summary-p.md"]["status"] == "active"
    assert m["orphans"] == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -k "recompile_supersedes or omitted_article or supersession_is_idempotent" -v`
Expected: FAIL — `test_recompile_supersedes_pre37_summary_slug` asserts `old["status"] == "orphan_candidate"` but gets `"active"` (supersession not wired in yet).

- [ ] **Step 3: Wire the call into `apply_compile_result()`**

In `kdb_compiler/manifest_update.py`, inside `apply_compile_result()`, the `for cs in compile_result.get("compiled_sources", [])` loop ends after the `rec["provenance"] = {...}` block (line ~478). Add the supersession call as the last statement inside that loop, immediately after the `rec["provenance"] = {...}` assignment:

```python
        # Task #64 (D41): drop this source's support from prior pages the
        # current run no longer emits. touched_keys is the complete emitted
        # page set for this source. The orphan pass below flags any page
        # left with empty supports_page_existence.
        _supersede_omitted_pages(
            manifest, source_id, set(touched_keys),
            started_at=ctx.started_at, run_id=ctx.run_id,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -k "recompile_supersedes or omitted_article or supersession_is_idempotent" -v`
Expected: PASS — 3 tests pass.

- [ ] **Step 5: Run the full manifest_update suite for regressions**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -v`
Expected: PASS — all tests (pre-existing + 6 new) green.

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/manifest_update.py kdb_compiler/tests/test_manifest_update.py
git commit -m "feat(task64): recompile supersession in apply_compile_result (D41)"
```

---

## Task 3: Status-aware `source_refs` invariant

**Files:**
- Modify: `kdb_compiler/manifest_update.py` — `assert_manifest_invariants()`, lines 565-568
- Test: `kdb_compiler/tests/test_manifest_update.py`

- [ ] **Step 1: Write the failing test**

Add to `kdb_compiler/tests/test_manifest_update.py` (end of file):

```python
def test_invariant_allows_empty_source_refs_on_orphan_candidate() -> None:
    m = manifest_update.ensure_manifest_shape({}, ctx=_ctx())
    m["pages"]["KDB/wiki/summaries/orphaned.md"] = {
        "page_id": "KDB/wiki/summaries/orphaned.md", "slug": "orphaned",
        "page_type": "summary", "status": "orphan_candidate", "title": "O",
        "source_refs": [], "supports_page_existence": [],
        "outgoing_links": [], "incoming_links_known": [],
        "confidence": "medium", "orphan_candidate": True,
    }
    m["orphans"]["KDB/wiki/summaries/orphaned.md"] = {
        "page_id": "KDB/wiki/summaries/orphaned.md",
        "flagged_at": "t", "reason": "superseded", "previous_supporting_sources": [],
        "recommended_action": "review_manually", "last_run_id": "r",
    }
    # Must NOT raise.
    assert_manifest_invariants(m)


def test_invariant_still_rejects_empty_source_refs_on_active() -> None:
    m = manifest_update.ensure_manifest_shape({}, ctx=_ctx())
    m["pages"]["KDB/wiki/summaries/bad.md"] = {
        "page_id": "KDB/wiki/summaries/bad.md", "slug": "bad",
        "page_type": "summary", "status": "active", "title": "B",
        "source_refs": [], "supports_page_existence": [],
        "outgoing_links": [], "incoming_links_known": [],
        "confidence": "medium", "orphan_candidate": False,
    }
    with pytest.raises(ManifestInvariantError, match="empty source_refs"):
        assert_manifest_invariants(m)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -k "invariant_allows or invariant_still_rejects" -v`
Expected: FAIL — `test_invariant_allows_empty_source_refs_on_orphan_candidate` raises `ManifestInvariantError` (invariant not yet status-aware).

- [ ] **Step 3: Make the invariant status-aware**

In `kdb_compiler/manifest_update.py`, `assert_manifest_invariants()`, replace lines 566-568:

```python
        refs = page.get("source_refs", [])
        if len(refs) < 1:
            raise ManifestInvariantError(f"page {key} has empty source_refs")
```

with:

```python
        refs = page.get("source_refs", [])
        # Task #64 (D43): orphan_candidate pages may have empty source_refs —
        # supersession strips them; provenance is preserved in
        # orphans[].previous_supporting_sources. Active pages still require
        # a non-empty source_refs (this also covers the DELETED-source path).
        if len(refs) < 1 and page.get("status") != "orphan_candidate":
            raise ManifestInvariantError(
                f"page {key} (status={page.get('status')!r}) has empty source_refs"
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest kdb_compiler/tests/test_manifest_update.py -k "invariant_allows or invariant_still_rejects" -v`
Expected: PASS — 2 tests pass.

- [ ] **Step 5: Run the full kdb_compiler suite for regressions**

Run: `python -m pytest kdb_compiler/tests/ -v`
Expected: PASS — all tests green. (`apply_compile_result` calls `assert_manifest_invariants` downstream via `build_manifest_update`; a recompile that orphans a page now produces an orphan_candidate with empty source_refs — this change keeps that legal.)

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/manifest_update.py kdb_compiler/tests/test_manifest_update.py
git commit -m "fix(task64): status-aware source_refs invariant (D43)"
```

---

## Task 4: Decision ledger — D41–D44 in CODEBASE_OVERVIEW.md

**Files:**
- Modify: `docs/CODEBASE_OVERVIEW.md` — decision ledger section

- [ ] **Step 1: Append the ledger entries**

Open `docs/CODEBASE_OVERVIEW.md`, find the decision ledger (the section containing `D40`). Append four entries `D41`–`D44`, matching the exact formatting of the existing `D40` entry. Content for each is the corresponding row from `docs/task64-recompile-supersession-blueprint.md` §4:

- **D41** — Recompile supersession: a source's recompile removes that source's support from prior pages the new run no longer emits; the graph ingestor already implements this, D41 binds the manifest path to parity.
- **D42** — `source_refs` is current-state provenance, not an eternal log; stripped on supersession alongside `supports_page_existence`; history lives in run journals, `sources[].previous_versions`, `orphans[].previous_supporting_sources`.
- **D43** — Status-aware `source_refs` invariant: `active` page → non-empty; `orphan_candidate` page → may be empty; also fixes the pre-existing DELETED-path invariant crash.
- **D44** — D12 preserved: supersession flags pages `orphan_candidate`, never deletes; `delete_policy` stays `mark_orphan_candidate`.

- [ ] **Step 2: Commit**

```bash
git add docs/CODEBASE_OVERVIEW.md
git commit -m "docs(task64): D41-D44 decision ledger entries"
```

---

## Task 5: One-shot migration script

**Files:**
- Create: `scripts/migrate_task64_supersession.py`

This script repairs the 3 already-crossed sources without API cost. It is
idempotent and safe to run on a clean vault (produces zero changes).

- [ ] **Step 1: Write the script**

Create `scripts/migrate_task64_supersession.py`:

```python
#!/usr/bin/env python3
"""Task #64 one-shot migration — apply recompile supersession to the live
manifest for sources already recompiled before the Task #64 code fix landed.

For every source whose latest run archived a Stage 9 sidecar, the emitted
page set is read from state/runs/<run_id>/compile_result.json and asserted
equal to the manifest's sources[source_id].outputs_touched. Pages that still
list the source but were not emitted lose that source from
supports_page_existence + source_refs; pages left with empty support are
flagged orphan_candidate.

--dry-run is the DEFAULT. Pass --apply to mutate state/manifest.json.

After --apply, run:  graphdb-kdb rebuild --vault-root <root>
            then:    graphdb-kdb verify  --vault-root <root>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from kdb_compiler import atomic_io, paths
from kdb_compiler.manifest_update import (
    _supersede_omitted_pages,
    assert_manifest_invariants,
)


def _emitted_keys_from_sidecar(sidecar: dict, source_id: str) -> set[str] | None:
    """Page keys emitted for source_id per the archived compile_result.
    Returns None if the source is absent from the sidecar."""
    for cs in sidecar.get("compiled_sources", []):
        if cs.get("source_id") == source_id:
            return {
                paths.slug_to_relpath(p["slug"], p["page_type"])
                for p in cs.get("pages", [])
            }
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="migrate_task64_supersession")
    ap.add_argument("--vault-root", required=True,
                    help="Absolute path to the Obsidian vault root")
    ap.add_argument("--apply", action="store_true",
                    help="Mutate state/manifest.json (default is dry-run)")
    args = ap.parse_args(argv)

    state_root = Path(args.vault_root).resolve() / "KDB" / "state"
    manifest_path = state_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    now = datetime.now().astimezone().isoformat()
    run_id = f"task64-migration-{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"

    audit: dict = {"run_id": run_id, "started_at": now, "apply": args.apply,
                   "sources": []}
    total_affected = 0

    for source_id, rec in sorted(manifest.get("sources", {}).items()):
        last_run_id = rec.get("last_run_id")
        if not last_run_id:
            continue
        sidecar_path = state_root / "runs" / last_run_id / "compile_result.json"
        if not sidecar_path.exists():
            print(f"skip   {source_id} — no sidecar ({last_run_id})")
            continue

        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        emitted = _emitted_keys_from_sidecar(sidecar, source_id)
        if emitted is None:
            print(f"skip   {source_id} — not in sidecar {last_run_id}")
            continue

        # Q1 guard: sidecar emitted set must match the manifest bookkeeping.
        outputs_touched = set(rec.get("outputs_touched", []))
        if emitted != outputs_touched:
            print(f"ERROR  {source_id}: sidecar emitted set != outputs_touched")
            print(f"  only in sidecar : {sorted(emitted - outputs_touched)}")
            print(f"  only in manifest: {sorted(outputs_touched - emitted)}")
            return 1

        affected = _supersede_omitted_pages(
            manifest, source_id, emitted, started_at=now, run_id=run_id,
        )
        if affected:
            total_affected += len(affected)
            print(f"affect {source_id} — {len(affected)} page(s):")
            for k in affected:
                emptied = not manifest["pages"][k]["supports_page_existence"]
                tag = " → ORPHANED" if emptied else ""
                print(f"         {k}{tag}")
        audit["sources"].append({
            "source_id": source_id, "emitted_count": len(emitted),
            "affected_pages": affected,
        })

    # Flag status on any page left with empty support (orphans[] entries were
    # already seeded by _supersede_omitted_pages).
    newly_orphaned: list[str] = []
    for page_key, page in manifest["pages"].items():
        if not page.get("supports_page_existence", []):
            if page.get("status") != "orphan_candidate":
                newly_orphaned.append(page_key)
            page["status"] = "orphan_candidate"
            page["orphan_candidate"] = True
    audit["newly_orphaned"] = sorted(newly_orphaned)

    print(f"\nsummary: {total_affected} page-source link(s) superseded, "
          f"{len(newly_orphaned)} page(s) newly orphaned")

    if not args.apply:
        print("\nDRY RUN — no files written. Re-run with --apply to commit.")
        return 0

    assert_manifest_invariants(manifest)
    atomic_io.atomic_write_json(manifest_path, manifest, sort_keys=True)
    audit_path = state_root / f"task64-migration-audit-{run_id}.json"
    atomic_io.atomic_write_json(audit_path, audit, sort_keys=True)
    print(f"\nAPPLIED — manifest updated; audit at {audit_path}")
    print(f"Next: graphdb-kdb rebuild --vault-root {args.vault_root}")
    print(f"      graphdb-kdb verify  --vault-root {args.vault_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the script's import + arg parsing**

Run: `python scripts/migrate_task64_supersession.py --help`
Expected: prints the usage text, exit 0. (Confirms imports resolve — `_supersede_omitted_pages`, `paths.slug_to_relpath`, `atomic_io` all importable.)

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_task64_supersession.py
git commit -m "feat(task64): one-shot supersession migration script"
```

---

## Task 6: Run the migration against the live vault (operational)

This task mutates the live vault (`/home/ftu/Obsidian`) and GraphDB-KDB. It is
**operator-run, gated** — do not execute steps 2–4 without explicit human
go-ahead at the dry-run review.

- [ ] **Step 1: Dry-run and review**

Run: `python scripts/migrate_task64_supersession.py --vault-root /home/ftu/Obsidian`
Expected: lists affected pages per source — the 3 pre-#37 summaries
(`buffett-yahoo-interview-march-2020-covid`, `ep1-the-journey-of-china`,
`howard-marks-oil-rational-investor`) marked `→ ORPHANED`, plus any pre-#37
articles/concepts no longer emitted. No Q1-guard `ERROR` lines.
**STOP — human reviews the proposed diff before proceeding.**

- [ ] **Step 2: Apply**

Run: `python scripts/migrate_task64_supersession.py --vault-root /home/ftu/Obsidian --apply`
Expected: `APPLIED` line; audit JSON path printed; no invariant error.

- [ ] **Step 3: Rebuild + verify GraphDB-KDB**

Run: `graphdb-kdb rebuild --vault-root /home/ftu/Obsidian`
Then: `graphdb-kdb verify --vault-root /home/ftu/Obsidian`
Expected: `verify` reports no divergence between graph and the repaired manifest (exit 0).

- [ ] **Step 4: Commit the audit trail**

```bash
git add -A benchmark/ docs/ scripts/
git status   # confirm only the migration audit JSON is staged, if tracked
git commit -m "chore(task64): migration audit trail — 3 pre-#37 sources repaired"
```

(If the audit JSON lives under the vault rather than the repo, there is
nothing to commit here — note that in the closure and skip.)

---

## Self-Review

**Spec coverage** (against `docs/task64-recompile-supersession-blueprint.md`):
- §3 Part A code fix → Tasks 1–3. ✅
- §3 Part B1 migration → Task 5; Part B2 rebuild/verify → Task 6. ✅
- D41 → Task 2; D42 (strip source_refs) → Task 1 helper; D43 → Task 3; D44 (orphan, not delete) → verified by Task 2 assertions (`orphan_candidate`, page record retained). ✅
- §6 test surface — all six listed cases covered: pre-#37 slug replacement (Task 2), omitted article orphaned (Task 2), shared concept survives (Tasks 1 + 2), idempotency (Task 2), invariant active-vs-orphan (Task 3), `previous_supporting_sources` populated (Tasks 1 + 2). ✅
- §7 closure criteria → Task 6 step 3 (`verify`) + Task 3 step 5 (full suite). ✅

**Placeholder scan:** none — every code step carries complete code; the docs task (4) names exact content + format source.

**Type consistency:** `_supersede_omitted_pages(manifest, source_id, emitted_keys, *, started_at, run_id) -> list[str]` is defined identically in the File Structure header, Task 1 Step 3, and called with matching kwargs in Task 2 Step 3 and Task 5. `paths.slug_to_relpath(slug, page_type)` matches its use at `manifest_update.py:423`.

---

## Notes for the executor
- Run pytest from the repo root (`~/Droidoes/Obsidian-KDB`).
- Tasks 1–5 are pure code/docs, no API cost, fully reversible — execute straight through.
- Task 6 is operational and human-gated at the Step 1 dry-run review. Do not auto-proceed past it.
