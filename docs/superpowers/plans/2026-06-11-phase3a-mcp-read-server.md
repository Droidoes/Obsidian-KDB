# Phase 3a — read-only MCP stdio server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a working read-only MCP stdio server (`kdb_mcp/`) exposing the six thin graph adapters + `get_body`, each opening the GraphDB read-only per call and returning a stable Pydantic response shape.

**Architecture:** New in-repo sibling package `kdb_mcp/` (NOT inside `kdb_graph` — it imports both `kdb_graph` and `common.wiki_io`, so keeping it outside preserves `kdb_graph`'s zero-`common` invariant; F2 in-repo). Each tool is a thin `@mcp.tool()` wrapper over a pure adapter function that opens `GraphDB(graph_path, read_only=True)` as a context manager (per-query reopen — F5), queries, and maps the result into a Pydantic model. The `stress_test` analytics composite is **out of scope** — it is Phase 3b.

**Tech Stack:** Python 3, the official `mcp` SDK (FastMCP high-level API, v1.12.x), Pydantic, pytest (+ `anyio`, which ships with `mcp`). Kuzu via `kdb_graph.GraphDB`.

**Specs:** `docs/superpowers/specs/2026-06-10-graph-access-package-design.md` (v0.3 §3.5 tool surface, F5 reopen) + `docs/superpowers/specs/2026-06-11-phase3-mcp-sdk-verification.md` (verified SDK shapes).

---

## Verified ground truth (do not re-derive — confirmed against source this session)

`kdb_graph.GraphDB` — context manager, read methods (all sync, delegate to `queries.py`):
```python
GraphDB(graph_dir: Path | str, *, read_only: bool = False)        # __enter__/__exit__/close()
  .get_entity(slug) -> Entity | None
  .get_source(source_id) -> Source | None
  .neighbors(slug, *, direction="out", depth=1) -> list[Entity]   # direction: "out"|"in"|"both"
  .shortest_path(from_slug, to_slug, *, max_hops=10) -> list[str] | None
  .entities_for_source(source_id) -> list[Entity]
  .sources_for_entity(slug) -> list[Source]
  .conn -> kuzu.Connection                                        # public; for resolve below
```
`kdb_graph.queries.resolve_to_canonical_slugs(conn, raw_slugs: list[str]) -> dict[str, str]` (alias-aware; unresolved keys absent).

`Entity` (frozen dataclass) fields: `slug, title, page_type, status, confidence, created_at, updated_at, first_run_id, last_run_id, canonical_id`.
`Source` fields incl.: `source_id, source_type, canonical_path, status, file_type, domain, author, summary, …`.

`common.wiki_io.get_body(slug, page_type, *, root=None) -> str` raises `ContentNotFoundError` (missing file) / `PathError` (bad slug/page_type). `root` is the **vault** root (contains `KDB/wiki/`).

**Two distinct roots:** GraphDB dir (`KDB_GRAPH_PATH`, default `~/Droidoes/GraphDB-KDB`) ≠ vault root (`OBSIDIAN_VAULT_PATH`, default `~/Obsidian`, resolved by `common.paths.vault_root()`).

Test fixture idiom (build a populated tmp graph):
```python
from kdb_graph.graphdb import GraphDB
from kdb_graph.testing import make_page, make_compiled_source, make_compile_result, make_scan, make_scan_entry

def _seed(graph_dir):
    pages = [make_page("a", outgoing_links=["b"]), make_page("b")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:          # writable open to seed
        gdb.apply_compile_result(cr, scan, "run-1")
```

MCP in-memory test idiom (no subprocess; `anyio` ships with `mcp`):
```python
import pytest
from mcp import Client
from kdb_mcp.server import mcp as app

@pytest.fixture
def anyio_backend(): return "asyncio"

@pytest.mark.anyio
async def test_tool(...):
    async with Client(app, raise_exceptions=True) as c:
        result = await c.call_tool("get_entity", {"slug": "a"})
        # result.structuredContent -> dict ; result.isError -> bool
```

---

## File Structure

- `kdb_mcp/__init__.py` — package marker + docstring.
- `kdb_mcp/config.py` — `default_graph_path() -> Path` (`KDB_GRAPH_PATH` else `~/Droidoes/GraphDB-KDB`); `default_vault_root() -> Path` (delegates to `common.paths.vault_root()`). App-owned defaults; both overridable.
- `kdb_mcp/models.py` — Pydantic response models (one per tool): `EntityCard`, `SourceCard`, `Neighborhood`, `PathResult`, `BodyResult`, `SourceProvenance`, `EntityProvenance`, `SearchKeyResolution`.
- `kdb_mcp/adapters.py` — pure functions (the testable core): open `GraphDB` read-only per call, query, map to a model. One per tool. Raise `EntityNotFoundError`/propagate `ContentNotFoundError` on absence.
- `kdb_mcp/server.py` — the `FastMCP` instance + `@mcp.tool()` wrappers (thin: call the adapter with resolved config) + `main()` entry point.
- `kdb_mcp/tests/` — `test_config.py`, `test_adapters.py` (the bulk — sync, tmp GraphDB), `test_server.py` (in-memory `mcp.Client` integration).

`models.py` and `adapters.py` grow across tasks; each task appends its model + adapter + tests. The `@mcp.tool` wrappers are added once in the server task (Task 9).

---

### Task 1: Add the `mcp` dependency + `kdb_mcp` package skeleton + config

**Files:**
- Modify: `pyproject.toml` (the `dependencies = [...]` array) AND `requirements.txt` (it mirrors pyproject per its header comment)
- Create: `kdb_mcp/__init__.py`, `kdb_mcp/config.py`, `kdb_mcp/tests/__init__.py`, `kdb_mcp/tests/test_config.py`

- [ ] **Step 1: Install the SDK and record the dependency**

```bash
.venv/bin/python -m pip install "mcp>=1.12,<2"
.venv/bin/python -c "import mcp, anyio, pydantic; from mcp.server.fastmcp import FastMCP; from mcp import Client; print('mcp ok')"
```
The second line also confirms the **in-memory test API** (`from mcp import Client`) and `FastMCP` resolve — the one shape Tasks 9 depends on but Tasks 2–8 don't exercise. If `from mcp import Client` raises `ImportError` in this installed version (the plan verified it against the SDK's `testing.md`, but the symbol could be re-homed), **STOP and report NEEDS_CONTEXT — re-verify the in-memory client API via Context7/official docs; do NOT guess the import from memory.** (`mcp` pulls `anyio` + `pydantic` transitively.)

Add the line `"mcp>=1.12,<2",` to the `dependencies = [...]` array in `pyproject.toml` (alongside `kuzu`/`networkx`), and add `mcp>=1.12,<2` to the runtime section of `requirements.txt` (above the `# dev` block), matching the existing one-per-line style.

- [ ] **Step 2: Write the failing config test**

Create `kdb_mcp/__init__.py`:
```python
"""kdb_mcp — read-only MCP stdio server over the kdb_graph + wiki content stores.

In-repo sibling to kdb_graph (NOT inside it): imports both kdb_graph (graph
reads) and common.wiki_io (content), so it stays outside the package to keep
kdb_graph's zero-`common` dependency intact. Read-only by construction.
"""
```
Create `kdb_mcp/tests/__init__.py` (empty). Create `kdb_mcp/tests/test_config.py`:
```python
from __future__ import annotations

from pathlib import Path

from kdb_mcp import config


def test_default_graph_path_uses_env(monkeypatch):
    monkeypatch.setenv("KDB_GRAPH_PATH", "/tmp/some/graph")
    assert config.default_graph_path() == Path("/tmp/some/graph")


def test_default_graph_path_falls_back(monkeypatch):
    monkeypatch.delenv("KDB_GRAPH_PATH", raising=False)
    assert config.default_graph_path() == (Path.home() / "Droidoes" / "GraphDB-KDB")


def test_default_vault_root_delegates(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/tmp/some/vault")
    assert config.default_vault_root() == Path("/tmp/some/vault").resolve()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_mcp.config'`.

- [ ] **Step 4: Implement `config.py`**

Create `kdb_mcp/config.py`:
```python
"""Path resolution for the MCP server. Package-provided, app-owned defaults."""
from __future__ import annotations

import os
from pathlib import Path

from common import paths

_DEFAULT_GRAPH_DIR = Path.home() / "Droidoes" / "GraphDB-KDB"


def default_graph_path() -> Path:
    """GraphDB directory: KDB_GRAPH_PATH env, else ~/Droidoes/GraphDB-KDB."""
    env = os.environ.get("KDB_GRAPH_PATH")
    return Path(env) if env else _DEFAULT_GRAPH_DIR


def default_vault_root() -> Path:
    """Vault root (contains KDB/wiki/). Delegates to common.paths."""
    return paths.vault_root()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add kdb_mcp/ requirements.txt
git commit -m "feat(kdb_mcp): package skeleton + config path resolution + mcp dependency (#113 ph3a)"
```

---

### Task 2: `get_entity` adapter + `EntityCard` model

**Files:**
- Create: `kdb_mcp/models.py`, `kdb_mcp/adapters.py`, `kdb_mcp/tests/test_adapters.py`

- [ ] **Step 1: Write the failing test**

Create `kdb_mcp/tests/test_adapters.py`:
```python
from __future__ import annotations

import pytest

from kdb_graph.graphdb import GraphDB
from kdb_graph.testing import (
    make_compile_result, make_compiled_source, make_page, make_scan, make_scan_entry,
)
from kdb_mcp import adapters
from kdb_mcp.adapters import EntityNotFoundError


def _seed_chain(graph_dir):
    """a -> b (one source supports both)."""
    pages = [make_page("a", title="Alpha", outgoing_links=["b"]), make_page("b", title="Beta")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")


def test_get_entity_returns_card(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    card = adapters.get_entity(gdir, "a")
    assert card.slug == "a"
    assert card.title == "Alpha"
    assert card.page_type == "concept"
    assert card.status == "active"


def test_get_entity_missing_raises(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    with pytest.raises(EntityNotFoundError):
        adapters.get_entity(gdir, "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kdb_mcp.adapters'`.

- [ ] **Step 3: Implement `models.py` (EntityCard) and `adapters.py` (get_entity)**

Create `kdb_mcp/models.py`:
```python
"""Stable Pydantic response shapes for MCP tools (do not leak kdb_graph dataclasses)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EntityCard(BaseModel):
    """Public metadata for one graph entity (node)."""
    slug: str
    title: str
    page_type: str = Field(description="summary | concept | article")
    status: str
    confidence: str
    canonical_id: str | None = Field(default=None, description="non-null => this is an alias")
```

Create `kdb_mcp/adapters.py`:
```python
"""Pure adapter functions: open GraphDB read-only per call (F5 reopen), query,
map to a stable response model. Imported by the FastMCP tool wrappers."""
from __future__ import annotations

from pathlib import Path

from kdb_graph.graphdb import GraphDB
from kdb_graph.types import Entity

from kdb_mcp.models import EntityCard


class EntityNotFoundError(Exception):
    """No entity for the given slug (valid slug, absent node)."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"No entity for slug={slug!r}")


def _entity_card(e: Entity) -> EntityCard:
    return EntityCard(
        slug=e.slug, title=e.title, page_type=e.page_type, status=e.status,
        confidence=e.confidence, canonical_id=e.canonical_id,
    )


def get_entity(graph_path: Path, slug: str) -> EntityCard:
    """Return node metadata for a slug. Raises EntityNotFoundError if absent."""
    with GraphDB(graph_path, read_only=True) as g:
        e = g.get_entity(slug)
    if e is None:
        raise EntityNotFoundError(slug)
    return _entity_card(e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_mcp/models.py kdb_mcp/adapters.py kdb_mcp/tests/test_adapters.py
git commit -m "feat(kdb_mcp): get_entity adapter + EntityCard (#113 ph3a)"
```

---

### Task 3: `graph_neighborhood` adapter + `Neighborhood` model

**Files:**
- Modify: `kdb_mcp/models.py`, `kdb_mcp/adapters.py`, `kdb_mcp/tests/test_adapters.py`

- [ ] **Step 1: Write the failing test** (append to `test_adapters.py`):
```python
def test_graph_neighborhood_out_depth1(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    nb = adapters.graph_neighborhood(gdir, "a", direction="out", depth=1)
    assert nb.center == "a"
    assert nb.direction == "out"
    assert nb.depth == 1
    assert [c.slug for c in nb.neighbors] == ["b"]


def test_graph_neighborhood_empty(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    nb = adapters.graph_neighborhood(gdir, "b", direction="out", depth=1)
    assert nb.neighbors == []
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py::test_graph_neighborhood_out_depth1 -v`
Expected: FAIL — `AttributeError: module 'kdb_mcp.adapters' has no attribute 'graph_neighborhood'`.

- [ ] **Step 3: Implement**

Append to `kdb_mcp/models.py`:
```python
class Neighborhood(BaseModel):
    """Entities reachable from a center slug within `depth` LINKS_TO hops."""
    center: str
    direction: str
    depth: int
    neighbors: list[EntityCard]
```

Append to `kdb_mcp/adapters.py` (add `Neighborhood` to the models import):
```python
def graph_neighborhood(
    graph_path: Path, slug: str, *, direction: str = "both", depth: int = 1
) -> Neighborhood:
    """BFS expansion from slug. direction: out|in|both; depth >= 1."""
    with GraphDB(graph_path, read_only=True) as g:
        ents = g.neighbors(slug, direction=direction, depth=depth)
    return Neighborhood(
        center=slug, direction=direction, depth=depth,
        neighbors=[_entity_card(e) for e in ents],
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_mcp/models.py kdb_mcp/adapters.py kdb_mcp/tests/test_adapters.py
git commit -m "feat(kdb_mcp): graph_neighborhood adapter + Neighborhood (#113 ph3a)"
```

---

### Task 4: `find_path` adapter + `PathResult` model

**Files:**
- Modify: `kdb_mcp/models.py`, `kdb_mcp/adapters.py`, `kdb_mcp/tests/test_adapters.py`

- [ ] **Step 1: Write the failing test** (append):
```python
def test_find_path_found(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    pr = adapters.find_path(gdir, "a", "b")
    assert pr.found is True
    assert pr.path == ["a", "b"]
    assert pr.hops == 1


def test_find_path_unreachable(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    pr = adapters.find_path(gdir, "b", "a")  # chain is a->b, no reverse edge
    assert pr.found is False
    assert pr.path is None
    assert pr.hops is None
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py::test_find_path_found -v`
Expected: FAIL — no attribute `find_path`.

- [ ] **Step 3: Implement**

Append to `kdb_mcp/models.py`:
```python
class PathResult(BaseModel):
    """Shortest directed LINKS_TO path between two slugs."""
    from_slug: str
    to_slug: str
    found: bool
    path: list[str] | None = None
    hops: int | None = None
```

Append to `kdb_mcp/adapters.py` (add `PathResult` to imports):
```python
def find_path(
    graph_path: Path, from_slug: str, to_slug: str, *, max_hops: int = 10
) -> PathResult:
    """Shortest directed path of slugs; found=False when unreachable."""
    with GraphDB(graph_path, read_only=True) as g:
        path = g.shortest_path(from_slug, to_slug, max_hops=max_hops)
    if path is None:
        return PathResult(from_slug=from_slug, to_slug=to_slug, found=False)
    return PathResult(
        from_slug=from_slug, to_slug=to_slug, found=True,
        path=path, hops=len(path) - 1,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_mcp/models.py kdb_mcp/adapters.py kdb_mcp/tests/test_adapters.py
git commit -m "feat(kdb_mcp): find_path adapter + PathResult (#113 ph3a)"
```

---

### Task 5: provenance adapters (`entities_for_source`, `sources_for_entity`) + `SourceCard`/provenance models

**Files:**
- Modify: `kdb_mcp/models.py`, `kdb_mcp/adapters.py`, `kdb_mcp/tests/test_adapters.py`

- [ ] **Step 1: Write the failing tests** (append):
```python
def test_sources_for_entity(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    prov = adapters.sources_for_entity(gdir, "a")
    assert prov.slug == "a"
    assert [s.source_id for s in prov.sources] == ["KDB/raw/s.md"]


def test_entities_for_source(tmp_path):
    gdir = tmp_path / "g"
    _seed_chain(gdir)
    prov = adapters.entities_for_source(gdir, "KDB/raw/s.md")
    assert prov.source_id == "KDB/raw/s.md"
    assert sorted(c.slug for c in prov.entities) == ["a", "b"]
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py::test_sources_for_entity -v`
Expected: FAIL — no attribute `sources_for_entity`.

- [ ] **Step 3: Implement**

Append to `kdb_mcp/models.py`:
```python
class SourceCard(BaseModel):
    """Public metadata for one source note."""
    source_id: str
    source_type: str
    status: str
    domain: str | None = None


class EntityProvenance(BaseModel):
    """Sources that currently support an entity."""
    slug: str
    sources: list[SourceCard]


class SourceProvenance(BaseModel):
    """Entities a source currently supports."""
    source_id: str
    entities: list[EntityCard]
```

Append to `kdb_mcp/adapters.py` (add `SourceCard, EntityProvenance, SourceProvenance` to imports and `Source` to the kdb_graph.types import):
```python
def _source_card(s: Source) -> SourceCard:
    return SourceCard(
        source_id=s.source_id, source_type=s.source_type, status=s.status,
        domain=s.domain,
    )


def sources_for_entity(graph_path: Path, slug: str) -> EntityProvenance:
    """Sources currently supporting an entity (empty list if none)."""
    with GraphDB(graph_path, read_only=True) as g:
        srcs = g.sources_for_entity(slug)
    return EntityProvenance(slug=slug, sources=[_source_card(s) for s in srcs])


def entities_for_source(graph_path: Path, source_id: str) -> SourceProvenance:
    """Entities a source currently supports (empty list if none)."""
    with GraphDB(graph_path, read_only=True) as g:
        ents = g.entities_for_source(source_id)
    return SourceProvenance(source_id=source_id, entities=[_entity_card(e) for e in ents])
```
(Update the `from kdb_graph.types import Entity` line to `from kdb_graph.types import Entity, Source`.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_mcp/models.py kdb_mcp/adapters.py kdb_mcp/tests/test_adapters.py
git commit -m "feat(kdb_mcp): provenance adapters + SourceCard/provenance models (#113 ph3a)"
```

---

### Task 6: `resolve_search_keys` adapter + `SearchKeyResolution` model

**Files:**
- Modify: `kdb_mcp/models.py`, `kdb_mcp/adapters.py`, `kdb_mcp/tests/test_adapters.py`

> **Why slugify-first (advisor finding):** the spec makes this tool first-class because *"users ask names/aliases, not exact slugs"*. But `queries.resolve_to_canonical_slugs` matches `WHERE e.slug IN $slugs` and only `.strip()`s — it does NOT lowercase or slugify. So a human-typed `"Amortization"` would never match the slug `amortization`. The adapter must `paths.slugify` each key first (turning `"Amortization"` → `"amortization"`), then alias-resolve, then map back to the original key. True synonyms still need `ALIAS_OF` entities (which the resolver already handles); this bridges the case/punctuation gap, which is the common case.

- [ ] **Step 1: Write the failing test** (append). It uses a **human-typed name** (`"Amortization"`), not a bare slug — this is the case the spec cares about:
```python
def test_resolve_search_keys_by_human_name(tmp_path):
    gdir = tmp_path / "g"
    pages = [make_page("amortization", title="Amortization")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(gdir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
    res = adapters.resolve_search_keys(gdir, ["Amortization", "ghost"])
    assert res.resolved == {"Amortization": "amortization"}  # name -> slugified -> resolved
    assert res.unresolved == ["ghost"]                       # absent after slugify
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py::test_resolve_search_keys_by_human_name -v`
Expected: FAIL — no attribute `resolve_search_keys`.

- [ ] **Step 3: Implement**

Append to `kdb_mcp/models.py`:
```python
class SearchKeyResolution(BaseModel):
    """Alias-aware mapping of input keys (human names) to canonical slugs."""
    resolved: dict[str, str]
    unresolved: list[str]
```

Append to `kdb_mcp/adapters.py` (add `from kdb_graph import queries`, `from common import paths`, and `SearchKeyResolution` to the models import):
```python
def resolve_search_keys(graph_path: Path, keys: list[str]) -> SearchKeyResolution:
    """Resolve human names/aliases to active canonical slugs. Each key is
    slugified first (so 'Amortization' -> 'amortization'), then alias-resolved.
    Keys that cannot be slugified or do not resolve land in `unresolved`
    (input order preserved). Returns the ORIGINAL key mapped to its canonical slug."""
    key_to_slug: dict[str, str] = {}
    for k in keys:
        try:
            key_to_slug[k] = paths.slugify(k)
        except paths.PathError:
            continue  # unslugifiable (empty / no ASCII) -> stays unresolved
    with GraphDB(graph_path, read_only=True) as g:
        slug_to_canon = queries.resolve_to_canonical_slugs(
            g.conn, sorted(set(key_to_slug.values()))
        )
    resolved = {k: slug_to_canon[s] for k, s in key_to_slug.items() if s in slug_to_canon}
    unresolved = [k for k in keys if k not in resolved]
    return SearchKeyResolution(resolved=resolved, unresolved=unresolved)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_mcp/models.py kdb_mcp/adapters.py kdb_mcp/tests/test_adapters.py
git commit -m "feat(kdb_mcp): resolve_search_keys adapter + SearchKeyResolution (#113 ph3a)"
```

---

### Task 7: `get_body` adapter + `BodyResult` model (content-store join)

**Files:**
- Modify: `kdb_mcp/models.py`, `kdb_mcp/adapters.py`, `kdb_mcp/tests/test_adapters.py`

- [ ] **Step 1: Write the failing test** (append). This one writes a wiki file under a tmp **vault** root (NOT the graph dir), using `paths.slug_to_abspath`:
```python
from pathlib import Path as _P

from common import paths as _paths


def _write_wiki_page(vault_root, slug, page_type, body):
    p = _paths.slug_to_abspath(slug, page_type, root=vault_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nslug: {slug}\npage_type: {page_type}\n---\n\n{body}", encoding="utf-8")


def test_get_body_returns_prose(tmp_path):
    vault = tmp_path / "vault"
    _write_wiki_page(vault, "a", "concept", "Alpha body text.\n")
    res = adapters.get_body(vault, "a", "concept")
    assert res.slug == "a"
    assert res.page_type == "concept"
    assert res.body == "Alpha body text.\n"


def test_get_body_missing_raises(tmp_path):
    from common.wiki_io import ContentNotFoundError
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ContentNotFoundError):
        adapters.get_body(vault, "ghost", "concept")
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py::test_get_body_returns_prose -v`
Expected: FAIL — no attribute `get_body`.

- [ ] **Step 3: Implement**

Append to `kdb_mcp/models.py`:
```python
class BodyResult(BaseModel):
    """The prose body of one wiki page."""
    slug: str
    page_type: str
    body: str
```

Append to `kdb_mcp/adapters.py` (add `from common.wiki_io import get_body as _read_body` and `BodyResult` to the models import). Note: `page_type` is `str` here because the value arrives over MCP as a plain string; `_read_body` validates it (raises `PathError` on an unknown value):
```python
def get_body(vault_root: Path, slug: str, page_type: str) -> BodyResult:
    """Return the wiki page body (frontmatter stripped). Reads files, not the
    graph. Raises ContentNotFoundError (absent file) / PathError (bad input)."""
    body = _read_body(slug, page_type, root=vault_root)  # type: ignore[arg-type]
    return BodyResult(slug=slug, page_type=page_type, body=body)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_adapters.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add kdb_mcp/models.py kdb_mcp/adapters.py kdb_mcp/tests/test_adapters.py
git commit -m "feat(kdb_mcp): get_body adapter + BodyResult (content-store join) (#113 ph3a)"
```

---

### Task 8: FastMCP server — tool wrappers + entry point

**Files:**
- Create: `kdb_mcp/server.py`

- [ ] **Step 1: Write the implementation** (the integration test in Task 9 is what drives this; here we assemble the wrappers). Create `kdb_mcp/server.py`:
```python
"""Read-only MCP stdio server over the KDB graph + wiki content stores.

Each tool opens the GraphDB read-only per call (F5 reopen). Writes never go
through this server. Run: `python -m kdb_mcp.server` (stdio).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.paths import PageType
from kdb_mcp import adapters, config
from kdb_mcp.models import (
    BodyResult, EntityCard, EntityProvenance, Neighborhood, PathResult,
    SearchKeyResolution, SourceProvenance,
)

mcp = FastMCP("kdb-graph")


@mcp.tool()
def get_entity(slug: str) -> EntityCard:
    """Return metadata for one graph entity by slug."""
    return adapters.get_entity(config.default_graph_path(), slug)


@mcp.tool()
def graph_neighborhood(slug: str, direction: str = "both", depth: int = 1) -> Neighborhood:
    """Entities reachable from `slug` within `depth` LINKS_TO hops. direction: out|in|both."""
    return adapters.graph_neighborhood(config.default_graph_path(), slug, direction=direction, depth=depth)


@mcp.tool()
def find_path(from_slug: str, to_slug: str, max_hops: int = 10) -> PathResult:
    """Shortest directed LINKS_TO path between two slugs."""
    return adapters.find_path(config.default_graph_path(), from_slug, to_slug, max_hops=max_hops)


@mcp.tool()
def sources_for_entity(slug: str) -> EntityProvenance:
    """Sources currently supporting an entity."""
    return adapters.sources_for_entity(config.default_graph_path(), slug)


@mcp.tool()
def entities_for_source(source_id: str) -> SourceProvenance:
    """Entities a source currently supports."""
    return adapters.entities_for_source(config.default_graph_path(), source_id)


@mcp.tool()
def resolve_search_keys(keys: list[str]) -> SearchKeyResolution:
    """Resolve names/aliases to active canonical slugs."""
    return adapters.resolve_search_keys(config.default_graph_path(), keys)


@mcp.tool()
def get_body(slug: str, page_type: PageType) -> BodyResult:
    """Return the prose body of a wiki page (frontmatter stripped). page_type is
    an enum (summary|concept|article) — invalid values are rejected by the SDK."""
    return adapters.get_body(config.default_vault_root(), slug, page_type)


def main() -> None:
    """Entry point — run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-import the module**

Run: `.venv/bin/python -c "from kdb_mcp.server import mcp, main; print('server imports ok')"`
Expected: prints `server imports ok` (no exceptions — confirms all tool signatures + model return types are valid for FastMCP schema generation).

- [ ] **Step 3: Commit**

```bash
git add kdb_mcp/server.py
git commit -m "feat(kdb_mcp): FastMCP server — 7 read tools + stdio entry point (#113 ph3a)"
```

---

### Task 9: In-memory MCP integration test (registration + round-trips + error envelope)

**Files:**
- Create: `kdb_mcp/tests/test_server.py`

- [ ] **Step 1: Write the integration tests**

Create `kdb_mcp/tests/test_server.py`. These point the server's config at a seeded tmp graph via `KDB_GRAPH_PATH`, drive it through the in-memory `mcp.Client`, and assert structured content + the error envelope:
```python
from __future__ import annotations

import pytest
from mcp import Client

from kdb_graph.graphdb import GraphDB
from kdb_graph.testing import (
    make_compile_result, make_compiled_source, make_page, make_scan, make_scan_entry,
)
from kdb_mcp.server import mcp as app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def seeded_graph(tmp_path, monkeypatch):
    gdir = tmp_path / "g"
    pages = [make_page("a", title="Alpha", outgoing_links=["b"]), make_page("b", title="Beta")]
    cr = make_compile_result([make_compiled_source("KDB/raw/s.md", pages)])
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])
    with GraphDB(gdir) as gdb:
        gdb.apply_compile_result(cr, scan, "run-1")
    monkeypatch.setenv("KDB_GRAPH_PATH", str(gdir))
    return gdir


@pytest.mark.anyio
async def test_server_lists_seven_read_tools(seeded_graph):
    async with Client(app, raise_exceptions=True) as c:
        tools = await c.list_tools()
    names = {t.name for t in tools.tools}
    assert names == {
        "get_entity", "graph_neighborhood", "find_path", "sources_for_entity",
        "entities_for_source", "resolve_search_keys", "get_body",
    }


@pytest.mark.anyio
async def test_get_entity_round_trip(seeded_graph):
    async with Client(app, raise_exceptions=True) as c:
        result = await c.call_tool("get_entity", {"slug": "a"})
    assert result.isError is False
    assert result.structuredContent["slug"] == "a"
    assert result.structuredContent["title"] == "Alpha"


@pytest.mark.anyio
async def test_graph_neighborhood_round_trip(seeded_graph):
    async with Client(app, raise_exceptions=True) as c:
        result = await c.call_tool("graph_neighborhood", {"slug": "a", "direction": "out", "depth": 1})
    nbrs = result.structuredContent["neighbors"]
    assert [n["slug"] for n in nbrs] == ["b"]


@pytest.mark.anyio
async def test_missing_entity_is_error_envelope(seeded_graph):
    # raise_exceptions=False so the error surfaces as an isError result, not a raise.
    async with Client(app) as c:
        result = await c.call_tool("get_entity", {"slug": "ghost"})
    assert result.isError is True
```

- [ ] **Step 2: Run the integration tests**

Run: `.venv/bin/python -m pytest kdb_mcp/tests/test_server.py -v`
Expected: PASS (4 tests). If `@pytest.mark.anyio` is unrecognized, confirm `anyio` is installed (it ships with `mcp`); no extra config needed — anyio registers its own pytest plugin.

- [ ] **Step 3: Commit**

```bash
git add kdb_mcp/tests/test_server.py
git commit -m "test(kdb_mcp): in-memory MCP integration — registration, round-trips, error envelope (#113 ph3a)"
```

---

### Task 10: Full-suite regression + live smoke against the real graph

**Files:** none (verification only).

- [ ] **Step 1: Run the kdb_mcp suite**

Run: `.venv/bin/python -m pytest kdb_mcp/ -v`
Expected: PASS (config 3 + adapters 11 + server 4 = 18 tests).

- [ ] **Step 2: Full offline suite**

Run: `.venv/bin/python -m pytest -m "not live" -p no:warnings -q`
Expected: PASS, no regressions vs the prior baseline (`1271 passed` + the new `kdb_mcp` tests). `-m "not live"` is mandatory (`.env` auto-loads API keys).

- [ ] **Step 3: Live smoke against the real GraphDB** (optional, requires the live graph to exist)

Run:
```bash
ls ~/Droidoes/GraphDB-KDB >/dev/null 2>&1 && .venv/bin/python -c "
from pathlib import Path
from kdb_mcp import adapters, config
g = config.default_graph_path()
print('graph:', g)
# pick any known slug from the live graph; adjust if needed
nb = adapters.graph_neighborhood(g, 'amortization', direction='both', depth=1)
print('neighbors of amortization:', [c.slug for c in nb.neighbors])
" || echo "live graph not present — skipping live smoke"
```
Expected: prints neighbors, OR the skip message. (Use a slug you know exists; the wiki listing earlier showed `amortization`.)

- [ ] **Step 4: Stop — Phase 3a complete**

A working read-only MCP stdio server exists with 7 tools, each per-query-reopen read-only, stable Pydantic responses, error envelope. **Out of scope (Phase 3b):** the `stress_test` analytics composite (the Named Gate) + its two new `queries.py` primitives. Report completion; update `docs/TASKS.md` (#113 Phase 3a done) + Milestone Changelog at the commit gate.
