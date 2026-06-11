# Graph-Access Package — Phase 1: Boundary Formalization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalize `kdb_graph` as a standalone graph-access package boundary by publishing its test-support helpers and public API, so the forthcoming read-only MCP server (Phase 3) lands on a stable, importable surface without reaching into test internals.

**Architecture:** `kdb_graph` already has zero `common` dependency and a `__init__` public surface. This phase does NOT move files or split `pyproject` — it (a) extracts the test factories from `kdb_graph/tests/conftest.py` into a shippable `kdb_graph/testing.py` module so cross-package importers stop reaching into `kdb_graph.tests.conftest`, and (b) completes the public API surface (`GraphDBReadOnlyError`, query/analytics access) with a test that pins it. Source spec: `docs/superpowers/specs/2026-06-10-graph-access-package-design.md` §4.5 (`kdb_graph.testing`), §3 (public surface). Builds on #112 (read-only correctness, landed `8d63019`).

**Tech Stack:** Python 3.12, pytest, Kuzu (embedded). Test runner: `venv/bin/python -m pytest -m "not live"`.

**Out of scope (later phases):** dedicated `pyproject` workspace member, viewer co-location (entangled with package-data + sandbox-run.sh — own micro-decision), content-store accessor (Phase 2), the MCP server (Phase 3, gated on MCP-SDK doc verification).

---

## File Structure

- **Create** `kdb_graph/testing.py` — public, shippable test-support factories (`make_page`, `make_compiled_source`, `make_compile_result`, `make_scan_entry`, `make_scan`). One responsibility: synthetic compile-result/scan fixtures for any consumer's tests.
- **Modify** `kdb_graph/tests/conftest.py` — re-export the factories from `kdb_graph.testing` (keep the `graph_dir` fixture local; it's pytest-only). Existing `from .conftest import make_*` call sites keep working unchanged.
- **Modify** `tools/tests/test_kdb_clean.py`, `tools/tests/test_kdb_clean_graphdb.py` — repoint factory imports from `kdb_graph.tests.conftest` → `kdb_graph.testing`.
- **Modify** `kdb_graph/__init__.py` — add `GraphDBReadOnlyError` to imports + `__all__`.
- **Create** `kdb_graph/tests/test_public_api.py` — pin the public surface (the package exports the contract consumers depend on).

---

## Task 1: Publish test-support factories as `kdb_graph.testing`

**Files:**
- Create: `kdb_graph/testing.py`
- Test: `kdb_graph/tests/test_testing_module.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_graph/tests/test_testing_module.py
"""kdb_graph.testing is the public, shippable test-support surface (Phase 1).

Cross-package consumers import factories from here, NOT from kdb_graph.tests.conftest.
"""
from __future__ import annotations

from kdb_graph import testing


def test_make_page_defaults():
    p = testing.make_page("alpha-beta")
    assert p["slug"] == "alpha-beta"
    assert p["page_type"] == "concept"
    assert p["title"] == "Title for alpha-beta"
    assert p["outgoing_links"] == []


def test_make_compile_result_shape():
    src = testing.make_compiled_source(
        "KDB/raw/x.md", [testing.make_page("alpha")]
    )
    cr = testing.make_compile_result([src], run_id="r1")
    assert cr["run_id"] == "r1"
    assert cr["success"] is True
    assert cr["compiled_sources"][0]["source_id"] == "KDB/raw/x.md"


def test_make_scan_pairs_with_source():
    scan = testing.make_scan([testing.make_scan_entry("KDB/raw/x.md")])
    assert scan["files"][0]["path"] == "KDB/raw/x.md"
    assert scan["files"][0]["action"] == "CHANGED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest kdb_graph/tests/test_testing_module.py -m "not live" -q`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'kdb_graph.testing'` (or ImportError on `testing`).

- [ ] **Step 3: Write minimal implementation**

Create `kdb_graph/testing.py` with the five factories moved verbatim from `kdb_graph/tests/conftest.py` (the bodies are unchanged — this is a move, not a redesign):

```python
# kdb_graph/testing.py
"""Public, shippable test-support factories for kdb_graph consumers.

Synthetic compile_result / scan dicts for exercising graph intake/read code
without a live producer. Lives in the package (not tests/) so cross-package
test suites import a stable surface instead of reaching into kdb_graph.tests.conftest.
"""
from __future__ import annotations


def make_page(
    slug: str,
    *,
    page_type: str = "concept",
    title: str | None = None,
    status: str = "active",
    confidence: str = "medium",
    outgoing_links: list[str] | None = None,
    body: str = "",
) -> dict:
    """Construct a minimal compile_result page dict."""
    return {
        "slug": slug,
        "page_type": page_type,
        "title": title if title is not None else f"Title for {slug}",
        "status": status,
        "confidence": confidence,
        "outgoing_links": outgoing_links or [],
        "body": body,
    }


def make_compiled_source(
    source_id: str,
    pages: list[dict],
    *,
    run_state: str = "in_graph_db",
    source_hash: str = "sha256:abc",
    source_meta: dict | None = None,
) -> dict:
    """Construct a minimal compile_result.compiled_sources[i] dict."""
    d: dict = {
        "source_id": source_id,
        "pages": pages,
        "compile_meta": {
            "run_state": run_state,
            "hash": source_hash,
        },
    }
    if source_meta is not None:
        d["source_meta"] = source_meta
    return d


def make_compile_result(
    compiled_sources: list[dict],
    *,
    run_id: str = "test-run",
    canonical_meta: dict | None = None,
) -> dict:
    """Construct a minimal compile_result dict."""
    cr = {
        "run_id": run_id,
        "success": True,
        "compiled_sources": compiled_sources,
        "errors": [],
        "warnings": [],
    }
    if canonical_meta is not None:
        cr["canonical_meta"] = canonical_meta
    return cr


def make_scan_entry(
    source_id: str,
    *,
    hash_: str = "sha256:abc",
    size_bytes: int = 100,
    file_type: str = "markdown",
) -> dict:
    """Construct a minimal last_scan.files[i] dict."""
    return {
        "path": source_id,
        "action": "CHANGED",
        "current_hash": hash_,
        "size_bytes": size_bytes,
        "file_type": file_type,
        "is_binary": False,
    }


def make_scan(files: list[dict], *, to_reconcile: list[dict] | None = None) -> dict:
    """Construct a minimal last_scan dict."""
    return {
        "files": files,
        "to_reconcile": to_reconcile or [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest kdb_graph/tests/test_testing_module.py -m "not live" -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_graph/testing.py kdb_graph/tests/test_testing_module.py
git commit -m "feat(kdb_graph): publish test-support factories as kdb_graph.testing (#113 ph1)"
```

---

## Task 2: Re-export factories from conftest (keep existing call sites working)

**Files:**
- Modify: `kdb_graph/tests/conftest.py`

- [ ] **Step 1: Run the existing kdb_graph suite to capture the green baseline**

Run: `venv/bin/python -m pytest kdb_graph/tests/ -m "not live" -q`
Expected: PASS (current green; the factories still live in conftest).

- [ ] **Step 2: Replace the factory bodies in conftest with a re-export**

In `kdb_graph/tests/conftest.py`, delete the five factory function definitions (`make_page` … `make_scan`) and replace them with a re-export below the `graph_dir` fixture. Keep the `graph_dir` fixture and the imports it needs.

```python
# kdb_graph/tests/conftest.py  (replace the "# ---------- synthetic factories ----------"
# section and everything below it with this re-export)

# Synthetic factories now live in the shippable kdb_graph.testing module so
# cross-package consumers import a stable surface. Re-exported here so existing
# `from kdb_graph.tests.conftest import make_*` call sites keep working.
from kdb_graph.testing import (  # noqa: E402,F401
    make_page,
    make_compiled_source,
    make_compile_result,
    make_scan_entry,
    make_scan,
)
```

- [ ] **Step 3: Run the kdb_graph suite to verify nothing broke**

Run: `venv/bin/python -m pytest kdb_graph/tests/ -m "not live" -q`
Expected: PASS — same count as the Step 1 baseline. Every test importing `make_*` from conftest now resolves via the re-export.

- [ ] **Step 4: Commit**

```bash
git add kdb_graph/tests/conftest.py
git commit -m "refactor(kdb_graph): conftest re-exports factories from kdb_graph.testing (#113 ph1)"
```

---

## Task 3: Repoint cross-package importers off `kdb_graph.tests.conftest`

**Files:**
- Modify: `tools/tests/test_kdb_clean_graphdb.py:15`
- Modify: `tools/tests/test_kdb_clean.py:43`

- [ ] **Step 1: Run the two tools tests to capture the green baseline**

Run: `venv/bin/python -m pytest tools/tests/test_kdb_clean.py tools/tests/test_kdb_clean_graphdb.py -m "not live" -q`
Expected: PASS (current green; they import from `kdb_graph.tests.conftest`).

- [ ] **Step 2: Repoint the imports**

In `tools/tests/test_kdb_clean_graphdb.py` (around line 15), change:

```python
from kdb_graph.tests.conftest import (
```
to:
```python
from kdb_graph.testing import (
```

In `tools/tests/test_kdb_clean.py` (around line 43, inside whatever scope it sits), change the same import path:

```python
    from kdb_graph.tests.conftest import (
```
to:
```python
    from kdb_graph.testing import (
```

(Only the module path changes; the imported names are identical and already provided by `kdb_graph.testing`.)

- [ ] **Step 3: Run the two tools tests to verify they still pass**

Run: `venv/bin/python -m pytest tools/tests/test_kdb_clean.py tools/tests/test_kdb_clean_graphdb.py -m "not live" -q`
Expected: PASS — same count as Step 1. No cross-package test now reaches into `kdb_graph.tests`.

- [ ] **Step 4: Commit**

```bash
git add tools/tests/test_kdb_clean.py tools/tests/test_kdb_clean_graphdb.py
git commit -m "refactor(tools): import graph test factories from kdb_graph.testing, not tests.conftest (#113 ph1)"
```

---

## Task 4: Complete the public API surface

**Files:**
- Modify: `kdb_graph/__init__.py`
- Test: `kdb_graph/tests/test_public_api.py`

- [ ] **Step 1: Write the failing test**

```python
# kdb_graph/tests/test_public_api.py
"""Pin the kdb_graph public API surface (Phase 1).

Consumers (MCP server, compiler, tools) import from this surface; it must carry
the read-only contract added in #112.
"""
from __future__ import annotations

import kdb_graph


def test_read_only_error_is_public():
    assert hasattr(kdb_graph, "GraphDBReadOnlyError")
    assert "GraphDBReadOnlyError" in kdb_graph.__all__
    # It is the same class the wrapper raises.
    from kdb_graph.graphdb import GraphDBReadOnlyError as _E
    assert kdb_graph.GraphDBReadOnlyError is _E


def test_core_surface_present():
    for name in (
        "GraphDB", "GraphDBSchemaError", "GraphDBReadOnlyError",
        "Entity", "Source", "SCHEMA_VERSION", "default_graph_path",
    ):
        assert name in kdb_graph.__all__, f"{name} missing from public __all__"
        assert hasattr(kdb_graph, name), f"{name} not importable from kdb_graph"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest kdb_graph/tests/test_public_api.py -m "not live" -q`
Expected: FAIL — `GraphDBReadOnlyError` is not in `kdb_graph.__all__` (it was added to `graphdb.py` in #112 but never exported).

- [ ] **Step 3: Write minimal implementation**

In `kdb_graph/__init__.py`, update the `graphdb` import line and `__all__`:

```python
from kdb_graph.graphdb import GraphDB, GraphDBReadOnlyError, GraphDBSchemaError
```

And add `"GraphDBReadOnlyError",` to the `__all__` list (next to `"GraphDBSchemaError"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest kdb_graph/tests/test_public_api.py -m "not live" -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full kdb_graph + tools suites for regression**

Run: `venv/bin/python -m pytest kdb_graph/tests/ tools/tests/ -m "not live" -q`
Expected: PASS (all green — no regressions from the conftest re-export or import repoints).

- [ ] **Step 6: Commit**

```bash
git add kdb_graph/__init__.py kdb_graph/tests/test_public_api.py
git commit -m "feat(kdb_graph): export GraphDBReadOnlyError on the public surface (#113 ph1)"
```

---

## Phase 1 done — verification checklist

- [ ] `kdb_graph.testing` exists and is imported by `kdb_graph.tests.conftest` + both `tools/tests/test_kdb_clean*` (no consumer imports `kdb_graph.tests.conftest`).
- [ ] `kdb_graph.__all__` carries `GraphDBReadOnlyError` + the core surface.
- [ ] `venv/bin/python -m pytest kdb_graph/tests/ tools/tests/ -m "not live" -q` green.
- [ ] `tools/tests/test_package_boundaries.py` still green (no new illegal edges).

## Next phases (separate plans)

- **Phase 2 — Content-store accessor:** a `slug` + `page_type` → wiki/ body reader (pure function over `common/paths`), independently testable; enables `get_body`. Spec §4.5 F3.
- **Phase 3 — Read-only MCP stdio server:** assembly layer + thin `queries.py` adapters + `get_body` + the `stress_test` analytics composite (the §1.5 Gate) + per-query reopen + stable response/error shapes. **First task = verify the MCP Python SDK API via Context7/official docs** before any server code — do not write SDK call shapes from memory.
