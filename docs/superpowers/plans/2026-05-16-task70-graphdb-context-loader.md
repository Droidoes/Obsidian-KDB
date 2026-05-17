# Task #70 — GraphDB-Backed Context Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `context_loader.py`'s manifest-based `EXISTING CONTEXT` construction with graph queries from GraphDB-KDB, selectable via env var `KDB_CONTEXT_SOURCE`.

**Architecture:** Option B — parallel `graph_context_loader.py` module alongside the untouched `context_loader.py`. Planner owns the branch: reads `KDB_CONTEXT_SOURCE` env var, opens GraphDB once via context manager, passes `gdb.conn` to the graph loader for all sources in a planning run. Fail-loud if graphdb requested but unavailable/empty.

**Tech Stack:** Python 3.11+, Kuzu (embedded graph DB), existing `graphdb_kdb` query/analytics primitives, pytest with real temp Kuzu fixtures.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `kdb_compiler/graph_context_loader.py` | **Create** | Graph-backed context snapshot builder: tier-ranked entity selection + ContextPage projection |
| `kdb_compiler/planner.py` | **Modify** (lines 27-35 imports, 89-115 `build_jobs`) | Add env-switch, open GraphDB once, delegate to graph loader when `KDB_CONTEXT_SOURCE=graphdb` |
| `kdb_compiler/tests/test_graph_context_loader.py` | **Create** | Unit tests against real temp Kuzu DB with known topology |

---

## Task 1: Graph context loader — tier logic + ranking

**Files:**
- Create: `kdb_compiler/tests/test_graph_context_loader.py`
- Create: `kdb_compiler/graph_context_loader.py`

### Test topology (used across all Task 1 tests)

A temp Kuzu graph with this known structure:

```
Sources: src-alpha (supports: hub, spoke-1, spoke-2)
         src-beta  (supports: leaf-a)

Entities (all active, concept type):
  hub       → outgoing: [spoke-1, spoke-2, leaf-a]
  spoke-1   → outgoing: [hub]
  spoke-2   → outgoing: [leaf-a]
  leaf-a    → outgoing: []
  leaf-b    → outgoing: [hub]
  orphan-x  → outgoing: []
```

This gives us:
- T1 (source-supported): hub, spoke-1, spoke-2 for src-alpha
- T2 (slug-in-text): depends on source_text content
- T3 (1-hop neighbors of seeds): depends on seed set
- PageRank: hub has highest (most inbound edges)

- [ ] **Step 1: Write the test fixture**

Create `kdb_compiler/tests/test_graph_context_loader.py`:

```python
"""Tests for graph_context_loader — real Kuzu, no mocks."""
from __future__ import annotations

from pathlib import Path

import kuzu
import pytest

from graphdb_kdb.graphdb import GraphDB
from kdb_compiler.types import ContextSnapshot


@pytest.fixture
def gdb(tmp_path: Path):
    """Temp GraphDB with the reference topology."""
    with GraphDB(tmp_path / "test-graph") as g:
        conn = g.conn
        # Entities
        for slug, title, ptype in [
            ("hub", "Hub Concept", "concept"),
            ("spoke-1", "Spoke One", "concept"),
            ("spoke-2", "Spoke Two", "concept"),
            ("leaf-a", "Leaf Alpha", "article"),
            ("leaf-b", "Leaf Beta", "concept"),
            ("orphan-x", "Orphan X", "concept"),
        ]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $t, page_type: $pt, "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug, "t": title, "pt": ptype},
            )

        # Sources
        for sid in ["src-alpha", "src-beta"]:
            conn.execute(
                "CREATE (s:Source {source_id: $sid, source_type: 'raw', "
                "canonical_path: $sid, status: 'active', file_type: 'markdown', "
                "hash: 'sha256:aaa', size_bytes: 100, "
                "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
                "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
                "ingest_count: 1, last_run_id: 'r1', moved_to: ''})",
                {"sid": sid},
            )

        # SUPPORTS edges (src-alpha → hub, spoke-1, spoke-2; src-beta → leaf-a)
        for src, slug in [
            ("src-alpha", "hub"),
            ("src-alpha", "spoke-1"),
            ("src-alpha", "spoke-2"),
            ("src-beta", "leaf-a"),
        ]:
            conn.execute(
                "MATCH (s:Source {source_id: $src}), (e:Entity {slug: $slug}) "
                "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)",
                {"src": src, "slug": slug},
            )

        # LINKS_TO edges
        for from_slug, to_slug in [
            ("hub", "spoke-1"),
            ("hub", "spoke-2"),
            ("hub", "leaf-a"),
            ("spoke-1", "hub"),
            ("spoke-2", "leaf-a"),
            ("leaf-b", "hub"),
        ]:
            conn.execute(
                "MATCH (a:Entity {slug: $f}), (b:Entity {slug: $t}) "
                "CREATE (a)-[:LINKS_TO {run_id: 'r1'}]->(b)",
                {"f": from_slug, "t": to_slug},
            )

        yield g
```

- [ ] **Step 2: Write the T1 (source-supported) test**

Append to `test_graph_context_loader.py`:

```python
from kdb_compiler import graph_context_loader


class TestTierRanking:
    def test_t1_source_supported_entities_ranked_highest(self, gdb):
        """Entities supported by the source appear first (tier 3 score)."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="unrelated text with no slug mentions",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # src-alpha supports hub, spoke-1, spoke-2 — all must be present
        assert "hub" in slugs
        assert "spoke-1" in slugs
        assert "spoke-2" in slugs
        # They should be the first 3 (highest tier)
        assert set(slugs[:3]) == {"hub", "spoke-1", "spoke-2"}

    def test_t2_slug_in_text_ranked_below_t1(self, gdb):
        """Slugs mentioned in source_text rank below source-supported."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="See also leaf-b for more context.",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # leaf-b is T2 (slug in text), should appear after T1 seeds
        assert "leaf-b" in slugs
        t1_slugs = {"hub", "spoke-1", "spoke-2"}
        leaf_b_idx = slugs.index("leaf-b")
        for s in t1_slugs:
            assert slugs.index(s) < leaf_b_idx

    def test_t3_neighbors_ranked_below_t2(self, gdb):
        """1-hop neighbors of seeds rank below text-mention seeds."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-beta",
            source_text="no slug mentions here",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # src-beta supports leaf-a (T1). leaf-a has no outgoing links,
        # but spoke-2 links TO leaf-a (incoming). spoke-2 is T3.
        assert "leaf-a" in slugs
        if "spoke-2" in slugs:
            assert slugs.index("leaf-a") < slugs.index("spoke-2")

    def test_pagerank_breaks_ties_within_tier(self, gdb):
        """Within same tier, higher PageRank sorts first."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        # Within T1: hub has highest PageRank (most inbound).
        # hub should sort before spoke-1, spoke-2 within the T1 band.
        assert slugs[0] == "hub"
```

- [ ] **Step 3: Write the page_cap and outgoing_links tests**

Append to `test_graph_context_loader.py`:

```python
    def test_page_cap_truncates(self, gdb):
        """page_cap limits total output."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="leaf-b orphan-x",
            page_cap=3,
        )
        assert len(snapshot.pages) == 3

    def test_outgoing_links_populated(self, gdb):
        """Each ContextPage carries its outgoing_links from the graph."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="",
            page_cap=50,
        )
        hub_page = next(p for p in snapshot.pages if p.slug == "hub")
        assert set(hub_page.outgoing_links) == {"spoke-1", "spoke-2", "leaf-a"}

    def test_source_id_set_on_snapshot(self, gdb):
        """ContextSnapshot carries source_id."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="",
            page_cap=50,
        )
        assert snapshot.source_id == "src-alpha"


class TestEdgeCases:
    def test_empty_graph_returns_empty_snapshot(self, tmp_path):
        """Empty graph → empty pages, no crash."""
        with GraphDB(tmp_path / "empty-graph") as g:
            snapshot = graph_context_loader.build_context_snapshot(
                g.conn,
                source_id="nonexistent",
                source_text="anything",
                page_cap=50,
            )
        assert snapshot.pages == []
        assert snapshot.source_id == "nonexistent"

    def test_unknown_source_returns_text_matches_and_neighbors(self, gdb):
        """Source not in graph → no T1 seeds, but T2/T3 still work."""
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="unknown-source",
            source_text="hub is mentioned here",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        assert "hub" in slugs

    def test_only_active_entities_included(self, gdb):
        """Entities with status != 'active' are excluded."""
        # Mark orphan-x as inactive
        gdb.conn.execute(
            "MATCH (e:Entity {slug: 'orphan-x'}) SET e.status = 'inactive'"
        )
        snapshot = graph_context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            source_text="orphan-x is mentioned",
            page_cap=50,
        )
        slugs = [p.slug for p in snapshot.pages]
        assert "orphan-x" not in slugs
```

- [ ] **Step 4: Run tests — verify they fail (module doesn't exist yet)**

Run: `cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_compiler/tests/test_graph_context_loader.py -v 2>&1 | head -30`

Expected: `ModuleNotFoundError: No module named 'kdb_compiler.graph_context_loader'`

- [ ] **Step 5: Implement `graph_context_loader.py`**

Create `kdb_compiler/graph_context_loader.py`:

```python
"""graph_context_loader — GraphDB-backed context snapshot for one compile job.

Parallel to context_loader.py (manifest-backed). Selected by planner.py via
KDB_CONTEXT_SOURCE=graphdb. Does NOT read env vars itself — planner owns the
branch. Fails explicitly if graph state is insufficient.

Ranking tiers (strict ordering — no cross-tier promotion):
    T1 (score=3): entities supported by this source (SUPPORTS edges)
    T2 (score=2): entities whose slug appears as whole-word in source_text
    T3 (score=1): 1-hop neighbors (in+out) of T1∪T2 seeds, excluding seeds
    Tie-break:    PageRank (desc), then slug (asc) — within same tier only
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import kuzu

from kdb_compiler.types import ContextPage, ContextSnapshot

if TYPE_CHECKING:
    pass

_VALID_PAGE_TYPES = frozenset({"summary", "concept", "article"})


def build_context_snapshot(
    conn: kuzu.Connection,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = 50,
) -> ContextSnapshot:
    """Build a tier-ranked, source-specific context snapshot from GraphDB.

    Pure graph reads — no manifest access, no env var reads.
    Empty/missing source or empty graph → empty snapshot (never raises).
    """
    active_entities = _load_active_entities(conn)
    if not active_entities:
        return ContextSnapshot(source_id=source_id, pages=[])

    slug_set = set(active_entities.keys())

    # --- Tier assignment ---
    t1_slugs = _t1_source_supported(conn, source_id, slug_set)
    t2_slugs = _t2_slug_in_text(source_text, slug_set - t1_slugs)
    seeds = t1_slugs | t2_slugs
    t3_slugs = _t3_neighbors(conn, seeds, slug_set - seeds)

    # --- Scoring + ranking ---
    pagerank_scores = _pagerank_scores(conn)

    scored: list[tuple[str, int, float]] = []
    for slug in t1_slugs:
        scored.append((slug, 3, pagerank_scores.get(slug, 0.0)))
    for slug in t2_slugs:
        scored.append((slug, 2, pagerank_scores.get(slug, 0.0)))
    for slug in t3_slugs:
        scored.append((slug, 1, pagerank_scores.get(slug, 0.0)))

    # Strict tier ordering: tier desc, pagerank desc, slug asc
    scored.sort(key=lambda x: (-x[1], -x[2], x[0]))
    selected_slugs = [s[0] for s in scored[:page_cap]]

    # --- Projection ---
    outgoing_map = _batch_outgoing_links(conn, selected_slugs)
    pages = []
    for slug in selected_slugs:
        ent = active_entities[slug]
        page_type = ent["page_type"]
        if page_type not in _VALID_PAGE_TYPES:
            continue
        pages.append(ContextPage(
            slug=slug,
            title=ent["title"],
            page_type=page_type,
            outgoing_links=outgoing_map.get(slug, []),
        ))

    return ContextSnapshot(source_id=source_id, pages=pages)


# ---------- Tier helpers ----------


def _load_active_entities(conn: kuzu.Connection) -> dict[str, dict]:
    """Load all active entities as {slug: {title, page_type}}."""
    result = conn.execute(
        "MATCH (e:Entity) WHERE e.status = 'active' "
        "RETURN e.slug, e.title, e.page_type"
    )
    entities: dict[str, dict] = {}
    while result.has_next():
        row = result.get_next()
        entities[row[0]] = {"title": row[1], "page_type": row[2]}
    return entities


def _t1_source_supported(
    conn: kuzu.Connection, source_id: str, active_slugs: set[str]
) -> set[str]:
    """Entities the source currently SUPPORTS."""
    result = conn.execute(
        "MATCH (s:Source {source_id: $sid})-[:SUPPORTS]->(e:Entity) "
        "RETURN e.slug",
        {"sid": source_id},
    )
    slugs: set[str] = set()
    while result.has_next():
        slug = result.get_next()[0]
        if slug in active_slugs:
            slugs.add(slug)
    return slugs


def _t2_slug_in_text(source_text: str, candidate_slugs: set[str]) -> set[str]:
    """Slugs that appear as whole-word tokens in source_text."""
    if not candidate_slugs or not source_text:
        return set()
    pattern = _whole_word_alternation(sorted(candidate_slugs))
    return {m.group(0).lower() for m in pattern.finditer(source_text)}


def _t3_neighbors(
    conn: kuzu.Connection, seeds: set[str], candidate_slugs: set[str]
) -> set[str]:
    """1-hop in+out neighbors of seeds that are active and not already a seed."""
    if not seeds:
        return set()
    neighbors: set[str] = set()
    for slug in seeds:
        # outgoing
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug",
            {"s": slug},
        )
        while result.has_next():
            n = result.get_next()[0]
            if n in candidate_slugs:
                neighbors.add(n)
        # incoming
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})<-[:LINKS_TO]-(b:Entity) RETURN b.slug",
            {"s": slug},
        )
        while result.has_next():
            n = result.get_next()[0]
            if n in candidate_slugs:
                neighbors.add(n)
    return neighbors


def _pagerank_scores(conn: kuzu.Connection) -> dict[str, float]:
    """Compute PageRank over LINKS_TO topology. Returns {slug: score}."""
    try:
        import networkx as nx
    except ImportError:
        return {}

    result = conn.execute(
        "MATCH (a:Entity)-[:LINKS_TO]->(b:Entity) RETURN a.slug, b.slug"
    )
    g = nx.DiGraph()
    while result.has_next():
        row = result.get_next()
        g.add_edge(row[0], row[1])

    if not g.nodes:
        return {}

    # Add isolated active entities so they get a base score
    result2 = conn.execute("MATCH (e:Entity) WHERE e.status = 'active' RETURN e.slug")
    while result2.has_next():
        g.add_node(result2.get_next()[0])

    return nx.pagerank(g)


# ---------- Projection helpers ----------


def _batch_outgoing_links(
    conn: kuzu.Connection, slugs: list[str]
) -> dict[str, list[str]]:
    """For each slug, fetch its outgoing LINKS_TO target slugs."""
    out: dict[str, list[str]] = {}
    for slug in slugs:
        result = conn.execute(
            "MATCH (a:Entity {slug: $s})-[:LINKS_TO]->(b:Entity) RETURN b.slug ORDER BY b.slug",
            {"s": slug},
        )
        links = []
        while result.has_next():
            links.append(result.get_next()[0])
        out[slug] = links
    return out


# ---------- Regex helper (duplicated from context_loader — sunset-bound) ----------


def _whole_word_alternation(slugs: list[str]) -> re.Pattern[str]:
    """Case-insensitive whole-word pattern. Hyphens are intra-token."""
    escaped = [re.escape(s) for s in slugs]
    return re.compile(
        r"(?<![\w-])(" + "|".join(escaped) + r")(?![\w-])",
        re.IGNORECASE,
    )
```

- [ ] **Step 6: Run tests — verify they pass**

Run: `cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_compiler/tests/test_graph_context_loader.py -v`

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add kdb_compiler/graph_context_loader.py kdb_compiler/tests/test_graph_context_loader.py
git commit -m "feat(task70.1): graph_context_loader — tier-ranked GraphDB context builder"
```

---

## Task 2: Planner wiring — env-switch + fail-loud

**Files:**
- Modify: `kdb_compiler/planner.py` (imports ~line 27-35, `build_jobs` ~line 89-115)
- Create: `kdb_compiler/tests/test_planner_graph_context.py`

- [ ] **Step 1: Write failing test for planner graph-context integration**

Create `kdb_compiler/tests/test_planner_graph_context.py`:

```python
"""Tests for planner.py graph-context wiring (#70.2)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from graphdb_kdb.graphdb import GraphDB
from kdb_compiler.planner import build_jobs


@pytest.fixture
def graph_path_with_source(tmp_path: Path) -> Path:
    """Seed a temp GraphDB with one source + one entity, close it, return path.

    Closed before returning so build_jobs() can open it via KDB_GRAPH_PATH
    without conflicting with an already-open handle.
    """
    gpath = tmp_path / "test-graph"
    with GraphDB(gpath) as g:
        conn = g.conn
        conn.execute(
            "CREATE (e:Entity {slug: 'alpha', title: 'Alpha', page_type: 'concept', "
            "status: 'active', confidence: 'medium', "
            "created_at: '2026-01-01', updated_at: '2026-01-01', "
            "first_run_id: 'r1', last_run_id: 'r1'})"
        )
        conn.execute(
            "CREATE (s:Source {source_id: 'raw/test.md', source_type: 'raw', "
            "canonical_path: 'raw/test.md', status: 'active', file_type: 'markdown', "
            "hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r1', moved_to: ''})"
        )
        conn.execute(
            "MATCH (s:Source {source_id: 'raw/test.md'}), (e:Entity {slug: 'alpha'}) "
            "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)"
        )
    return gpath


@pytest.fixture
def vault_with_source(tmp_path: Path):
    """Vault root with a raw source file."""
    vault = tmp_path / "vault"
    raw_dir = vault / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "test.md").write_text("This is alpha content.")
    return vault


@pytest.fixture
def scan_one_source():
    return {
        "to_compile": ["raw/test.md"],
        "files": [
            {
                "path": "raw/test.md",
                "current_hash": "sha256:bbb",
                "size_bytes": 100,
                "file_type": "markdown",
                "is_binary": False,
            }
        ],
        "to_skip": [],
        "to_reconcile": [],
    }


@pytest.fixture
def manifest_minimal():
    return {"pages": {}, "sources": {}}


class TestPlannerGraphContext:
    def test_graphdb_context_source_uses_graph_loader(
        self, graph_path_with_source, vault_with_source, scan_one_source, manifest_minimal
    ):
        """KDB_CONTEXT_SOURCE=graphdb routes through graph_context_loader."""
        with patch.dict(os.environ, {
            "KDB_CONTEXT_SOURCE": "graphdb",
            "KDB_GRAPH_PATH": str(graph_path_with_source),
        }):
            jobs = build_jobs(
                scan_one_source,
                manifest_minimal,
                vault_with_source,
            )
        assert len(jobs) == 1
        # alpha is supported by this source → must appear
        slugs = [p.slug for p in jobs[0].context_snapshot.pages]
        assert "alpha" in slugs

    def test_manifest_context_source_uses_manifest_loader(
        self, vault_with_source, scan_one_source, manifest_minimal
    ):
        """KDB_CONTEXT_SOURCE=manifest (default) uses context_loader."""
        with patch.dict(os.environ, {"KDB_CONTEXT_SOURCE": "manifest"}):
            jobs = build_jobs(
                scan_one_source,
                manifest_minimal,
                vault_with_source,
            )
        assert len(jobs) == 1
        # manifest has no pages → empty context
        assert jobs[0].context_snapshot.pages == []

    def test_graphdb_missing_path_raises(
        self, vault_with_source, scan_one_source, manifest_minimal, tmp_path
    ):
        """If graphdb requested but path doesn't exist → RuntimeError."""
        bogus_path = tmp_path / "nonexistent" / "graph"
        with patch.dict(os.environ, {
            "KDB_CONTEXT_SOURCE": "graphdb",
            "KDB_GRAPH_PATH": str(bogus_path),
        }):
            with pytest.raises(RuntimeError, match="GraphDB unavailable"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)

    def test_graphdb_empty_graph_raises(
        self, vault_with_source, scan_one_source, manifest_minimal, tmp_path
    ):
        """If graphdb requested but graph has 0 entities → RuntimeError."""
        empty_graph_path = tmp_path / "empty-graph"
        with GraphDB(empty_graph_path) as g:
            pass  # creates schema but no data — closes on exit
        with patch.dict(os.environ, {
            "KDB_CONTEXT_SOURCE": "graphdb",
            "KDB_GRAPH_PATH": str(empty_graph_path),
        }):
            with pytest.raises(RuntimeError, match="GraphDB unavailable"):
                build_jobs(scan_one_source, manifest_minimal, vault_with_source)
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_compiler/tests/test_planner_graph_context.py -v 2>&1 | head -30`

Expected: FAIL (planner doesn't read `KDB_CONTEXT_SOURCE` yet).

- [ ] **Step 3: Implement planner wiring**

Modify `kdb_compiler/planner.py`:

Add import at top (after existing imports, ~line 34):

```python
from kdb_compiler import graph_context_loader
```

Replace `build_jobs` function (lines 89-115) with:

```python
import os
from contextlib import contextmanager


def build_jobs(
    scan: dict,
    manifest: dict,
    vault_root: Path,
    *,
    context_page_cap: int = 50,
) -> list[CompileJob]:
    """Pure-ish (reads source files). One job per eligible source_id.

    Context source is selected by KDB_CONTEXT_SOURCE env var:
      - 'manifest' (default): manifest-backed context_loader
      - 'graphdb': GraphDB-backed graph_context_loader (fail-loud if unavailable)
    """
    vault_root = Path(vault_root)
    context_source = os.environ.get("KDB_CONTEXT_SOURCE", "manifest")

    if context_source == "graphdb":
        return _build_jobs_graphdb(scan, vault_root, context_page_cap)
    return _build_jobs_manifest(scan, manifest, vault_root, context_page_cap)


def _build_jobs_manifest(
    scan: dict, manifest: dict, vault_root: Path, page_cap: int
) -> list[CompileJob]:
    jobs: list[CompileJob] = []
    for source_id in eligible_source_ids(scan):
        abs_path = vault_root / source_id
        source_text = _read_source_text(abs_path)
        snapshot = context_loader.build_context_snapshot(
            manifest,
            source_id=source_id,
            source_text=source_text,
            page_cap=page_cap,
        )
        jobs.append(CompileJob(
            source_id=source_id,
            abs_path=str(abs_path),
            context_snapshot=snapshot,
        ))
    return jobs


def _build_jobs_graphdb(
    scan: dict, vault_root: Path, page_cap: int
) -> list[CompileJob]:
    with _graph_conn_or_raise() as conn:
        jobs: list[CompileJob] = []
        for source_id in eligible_source_ids(scan):
            abs_path = vault_root / source_id
            source_text = _read_source_text(abs_path)
            snapshot = graph_context_loader.build_context_snapshot(
                conn,
                source_id=source_id,
                source_text=source_text,
                page_cap=page_cap,
            )
            jobs.append(CompileJob(
                source_id=source_id,
                abs_path=str(abs_path),
                context_snapshot=snapshot,
            ))
        return jobs


@contextmanager
def _graph_conn_or_raise():
    """Open GraphDB via context manager or raise RuntimeError with guidance.

    Validates: (1) graph path exists, (2) graph has >0 entities.
    Yields: kuzu.Connection for the duration of the block.
    """
    from graphdb_kdb import default_graph_path
    from graphdb_kdb.graphdb import GraphDB

    graph_path = default_graph_path()

    if not graph_path.exists():
        raise RuntimeError(
            f"GraphDB unavailable at {graph_path}. "
            "Run `graphdb-kdb rebuild` or set KDB_CONTEXT_SOURCE=manifest."
        )

    with GraphDB(graph_path, read_only=True) as gdb:
        if gdb.stats()["entities"] == 0:
            raise RuntimeError(
                f"GraphDB at {graph_path} has 0 entities. "
                "Run `graphdb-kdb rebuild` or set KDB_CONTEXT_SOURCE=manifest."
            )
        yield gdb.conn
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_compiler/tests/test_planner_graph_context.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Run full existing planner tests to verify no regression**

Run: `cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest kdb_compiler/tests/ -v -k "planner or context_loader" 2>&1 | tail -20`

Expected: All existing tests still PASS (default is `manifest`).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/planner.py kdb_compiler/tests/test_planner_graph_context.py
git commit -m "feat(task70.2): planner env-switch — KDB_CONTEXT_SOURCE=graphdb wiring"
```

---

## Task 3: Full suite green + integration sanity

**Files:**
- No new files — validation only.

- [ ] **Step 1: Run full test suite**

Run: `cd /home/ftu/Droidoes/Obsidian-KDB && python -m pytest --tb=short 2>&1 | tail -20`

Expected: All tests PASS (no regressions).

- [ ] **Step 2: Manual live-graph smoke (not automated)**

This is a manual verification step. Run against the real vault graph:

```bash
cd /home/ftu/Droidoes/Obsidian-KDB
KDB_CONTEXT_SOURCE=graphdb python -c "
from pathlib import Path
from kdb_compiler.planner import plan

jobs = plan(
    Path.home() / 'Obsidian',
    scan={'to_compile': ['KDB/raw/EP1 - The Journey of China.md'], 'files': [], 'to_skip': [], 'to_reconcile': []},
    context_page_cap=40,
)
for j in jobs:
    print(f'{j.source_id}: {len(j.context_snapshot.pages)} pages')
    for p in j.context_snapshot.pages[:5]:
        print(f'  {p.slug} ({p.page_type}) links={len(p.outgoing_links)}')
    if len(j.context_snapshot.pages) > 5:
        print(f'  ... and {len(j.context_snapshot.pages) - 5} more')
"
```

Verify: output shows pages ranked by tier, hub concepts first, reasonable count.

- [ ] **Step 3: Commit plan doc (ledger already updated earlier this session)**

```bash
git add docs/superpowers/plans/2026-05-16-task70-graphdb-context-loader.md
git commit -m "docs(task70): implementation plan — graphdb-backed context loader"
```

---

## Post-Plan Notes

**Not in scope for v1 (future enhancements):**
- Title matching (noisy — slug-only for now)
- Depth-2 expansion (54-node graph makes this nearly "everything")
- Side-by-side benchmark harness (separate task after #70 lands)
- Flipping default to `graphdb` (requires benchmark proof)
