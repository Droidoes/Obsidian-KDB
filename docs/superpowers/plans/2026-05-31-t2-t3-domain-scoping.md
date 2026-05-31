# T2/T3 Domain-Scoped Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scope the Pass-2 context snapshot (T2 + T3) to the source's Pass-1 domain only — a hard same-domain gate for entity anti-entropy.

**Architecture:** `build_context_snapshot` computes a **domain pool** = active entities that `BELONGS_TO` the source's `frontmatter.domain` (joined on `Domain.name`), then uses that pool as the candidate universe for T2 and T3 instead of all active entities. T1 (the source's own `SUPPORTS`) is unchanged. No padding — a smaller pool naturally yields a shorter snapshot. A source with no Pass-1 domain falls back to the full graph. Both `_t2_from_search_keys` and `_t3_neighbors` already filter by their `candidate_slugs` argument, so passing the pool through is all that's needed.

**Tech Stack:** Python 3 stdlib, Kuzu (embedded graph), pytest. File: `kdb_compiler/graph_context_loader.py`; tests `kdb_compiler/tests/test_graph_context_loader.py`.

**Spec:** `docs/superpowers/specs/2026-05-31-t2-t3-domain-scoping-design.md` (D3 override → hard same-domain gate).

---

### Task 1: Domain-scope the T2/T3 candidate universe

**Files:**
- Modify: `kdb_compiler/graph_context_loader.py` (add `_domain_pool`; scope `build_context_snapshot`)
- Test: `kdb_compiler/tests/test_graph_context_loader.py` (add a domain fixture + tests)

- [ ] **Step 1: Write the failing tests**

Append to `kdb_compiler/tests/test_graph_context_loader.py`. This adds a self-contained domain fixture (value-investing entities + one ai-ml entity, with a cross-domain `LINKS_TO`) and the gate tests:

```python
from kdb_compiler.source_io import SourceFrontmatter


@pytest.fixture
def gdb_dom(tmp_path: Path):
    """Temp GraphDB: 3 value-investing entities + 1 ai-ml, a cross-domain link."""
    with GraphDB(tmp_path / "dom-graph") as g:
        conn = g.conn
        for slug, title, ptype in [
            ("vi-hub", "VI Hub", "concept"),
            ("vi-spoke", "VI Spoke", "concept"),
            ("vi-leaf", "VI Leaf", "article"),
            ("ai-node", "AI Node", "concept"),
        ]:
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $t, page_type: $pt, "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})",
                {"s": slug, "t": title, "pt": ptype},
            )
        conn.execute(
            "CREATE (s:Source {source_id: 'src-vi', source_type: 'raw', "
            "canonical_path: 'src-vi', status: 'active', file_type: 'markdown', "
            "hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r1', moved_to: ''})"
        )
        for slug in ["vi-hub", "vi-spoke"]:        # T1: src-vi SUPPORTS vi-hub, vi-spoke
            conn.execute(
                "MATCH (s:Source {source_id: 'src-vi'}), (e:Entity {slug: $slug}) "
                "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)", {"slug": slug})
        for a, b in [("vi-hub", "ai-node"), ("vi-hub", "vi-leaf"), ("vi-spoke", "ai-node")]:
            conn.execute(
                "MATCH (a:Entity {slug: $a}), (b:Entity {slug: $b}) "
                "CREATE (a)-[:LINKS_TO {run_id: 'r1'}]->(b)", {"a": a, "b": b})
        for name in ["value-investing", "ai-ml"]:
            conn.execute("CREATE (d:Domain {name: $n, created_at: '2026-01-01', "
                         "first_run_id: 'r1'})", {"n": name})
        for slug, dom in [("vi-hub", "value-investing"), ("vi-spoke", "value-investing"),
                          ("vi-leaf", "value-investing"), ("ai-node", "ai-ml")]:
            conn.execute(
                "MATCH (e:Entity {slug: $s}), (d:Domain {name: $d}) "
                "CREATE (e)-[:BELONGS_TO {run_id: 'r1'}]->(d)", {"s": slug, "d": dom})
        yield g


def _vi_fm(keys):
    return SourceFrontmatter.from_dict({
        "kdb_signal": "signal", "domain": "value-investing",
        "source_type": "raw", "summary": "s", "entity_search_keys": keys})


def test_t2_off_domain_key_is_dropped(gdb_dom):
    snap = graph_context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", source_text="", page_cap=50,
        frontmatter=_vi_fm(["ai-node"]))
    slugs = [p.slug for p in snap.pages]
    assert "ai-node" not in slugs            # off-domain key resolution dropped


def test_t2_same_domain_key_is_kept(gdb_dom):
    snap = graph_context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", source_text="", page_cap=50,
        frontmatter=_vi_fm(["vi-leaf"]))
    assert "vi-leaf" in [p.slug for p in snap.pages]


def test_t3_excludes_cross_domain_neighbor(gdb_dom):
    # vi-hub LINKS_TO ai-node (cross-domain) and vi-leaf (same-domain).
    snap = graph_context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", source_text="", page_cap=50,
        frontmatter=_vi_fm([]))
    slugs = [p.slug for p in snap.pages]
    assert "ai-node" not in slugs            # cross-domain neighbor excluded
    assert "vi-leaf" in slugs                # same-domain neighbor admitted


def test_no_padding_and_all_same_domain(gdb_dom):
    snap = graph_context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", source_text="", page_cap=50,
        frontmatter=_vi_fm([]))
    slugs = {p.slug for p in snap.pages}
    assert slugs <= {"vi-hub", "vi-spoke", "vi-leaf"}   # no off-domain top-up
    assert "ai-node" not in slugs


def test_no_domain_source_falls_back_to_full_graph(gdb_dom):
    # frontmatter=None → un-scoped; ai-node is reachable via T3 (vi-hub→ai-node).
    snap = graph_context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", source_text="", page_cap=50,
        frontmatter=None)
    assert "ai-node" in [p.slug for p in snap.pages]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest kdb_compiler/tests/test_graph_context_loader.py -m "not live" -q -W ignore -k "domain or same_domain or padding or off_domain or cross_domain"`
Expected: the four scoping tests FAIL (ai-node still present / vi-leaf logic) because no scoping exists yet; `test_no_domain_source_falls_back_to_full_graph` may already pass (status quo).

- [ ] **Step 3: Add the `_domain_pool` helper**

In `kdb_compiler/graph_context_loader.py`, add this function immediately after `_load_active_entities` (around line 150):

```python
def _domain_pool(conn: kuzu.Connection, domain: str) -> set[str]:
    """Slugs of active entities that BELONGS_TO `domain` (the same-domain gate).

    The Pass-2 context is pulled only from the source's Pass-1 domain (D3
    override → hard same-domain gate). Domain nodes are keyed by `Domain.name`,
    which is exactly the string Pass-1 emits as `frontmatter.domain`.
    """
    result = conn.execute(
        "MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: $name}) "
        "WHERE e.status = 'active' RETURN e.slug",
        {"name": domain},
    )
    slugs: set[str] = set()
    while result.has_next():
        slugs.add(result.get_next()[0])
    return slugs
```

- [ ] **Step 4: Scope T2/T3 to the domain pool in `build_context_snapshot`**

Find this block (around lines 80–101):

```python
    slug_set = set(active_entities.keys())

    # --- Tier assignment ---
    t1_slugs = _t1_source_supported(conn, source_id, slug_set)
    cold_start = len(t1_slugs) == 0

    t2_slugs = _build_t2(
        conn,
        source_text=source_text,
        candidate_slugs=slug_set - t1_slugs,
        active_entities=active_entities,
        cold_start=cold_start,
        frontmatter=frontmatter,
        mode=mode,
        resolver=resolver,
    )

    seeds = t1_slugs | t2_slugs
    max_hops = 1
    if cold_start and len(t2_slugs) < _MIN_SEED_THRESHOLD:
        max_hops = 2
    t3_slugs = _t3_neighbors(conn, seeds, slug_set - seeds, max_hops=max_hops)
```

Replace it with (adds the domain pool; T2/T3 candidate universe becomes the pool):

```python
    slug_set = set(active_entities.keys())

    # Same-domain gate (D3 override): T2/T3 pull only from the source's Pass-1
    # domain (entity anti-entropy). T1 stays on the full set — it is the source's
    # own SUPPORTS, same-domain by construction. A source with no Pass-1 domain
    # (pre-Pass-1 / un-enriched) cannot be scoped, so it falls back to the full graph.
    domain = frontmatter.domain if frontmatter is not None else None
    pool = (_domain_pool(conn, domain) & slug_set) if domain else slug_set

    # --- Tier assignment ---
    t1_slugs = _t1_source_supported(conn, source_id, slug_set)
    cold_start = len(t1_slugs) == 0

    t2_slugs = _build_t2(
        conn,
        source_text=source_text,
        candidate_slugs=pool - t1_slugs,
        active_entities=active_entities,
        cold_start=cold_start,
        frontmatter=frontmatter,
        mode=mode,
        resolver=resolver,
    )

    seeds = t1_slugs | t2_slugs
    max_hops = 1
    if cold_start and len(t2_slugs) < _MIN_SEED_THRESHOLD:
        max_hops = 2
    t3_slugs = _t3_neighbors(conn, seeds, pool - seeds, max_hops=max_hops)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest kdb_compiler/tests/test_graph_context_loader.py -m "not live" -q -W ignore`
Expected: PASS (the new domain tests + all existing tier-ranking tests — the existing tests use `frontmatter=None` or omit it, so they hit the full-graph fallback and are unaffected).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/graph_context_loader.py kdb_compiler/tests/test_graph_context_loader.py
git commit -m "feat(retrieval): same-domain gate for T2/T3 context (D3 override)"
```

---

### Task 2: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full non-live suite**

Run: `python3 -m pytest -m "not live" -W ignore --no-header`
Expected: PASS at the standing baseline (was 1209 passed, 1 live skip; this adds the new domain tests). In particular, `kdb_compiler/tests/test_planner_graph_context.py` and the compiler tests stay green — they call `build_context_snapshot` with the existing args, and the fallback preserves prior behavior for any call without a domain.

- [ ] **Step 2: Commit (only if a pre-existing test needed a touch-up)**

```bash
git add -A
git commit -m "test(retrieval): full non-live suite green for domain-scoped T2/T3"
```

---

## Self-Review

**Spec coverage:**
- Domain pool = entities `BELONGS_TO` source domain (positive pull, `Domain.name` join) → Task 1 Step 3 (`_domain_pool`) ✓
- T2 scoped to pool; off-domain key resolution dropped → Step 4 (`candidate_slugs=pool - t1_slugs`) + test `test_t2_off_domain_key_is_dropped` ✓
- T3 scoped to pool; cross-domain neighbor excluded → Step 4 (`_t3_neighbors(..., pool - seeds, ...)`) + test `test_t3_excludes_cross_domain_neighbor` ✓
- T1 unchanged → Step 4 leaves `_t1_source_supported(conn, source_id, slug_set)` ✓
- No padding (short/empty fine) → no ranking/cap change; test `test_no_padding_and_all_same_domain` ✓
- No-domain fallback → Step 4 `if domain else slug_set` + test `test_no_domain_source_falls_back_to_full_graph` ✓
- Dilution check = structural same-domain guarantee, asserted in tests (composition `slugs <= {…}`); per YAGNI no runtime `ContextSnapshot` field is added (build_context_snapshot stays a pure read) — a deliberate, lean reading of the spec's "record domain + count," which the existing `len(snapshot.pages)` already covers at the call site ✓
- Cold-start widening within domain → automatic: `_build_t2`/`_t2_title_in_text` operate on `candidate_slugs=pool - t1_slugs` ✓

**Placeholder scan:** none — every step has complete code and exact commands.

**Type consistency:** `_domain_pool(conn, domain) -> set[str]` defined (Step 3) and used as `_domain_pool(conn, domain) & slug_set` (Step 4). `pool` is a `set[str]`; `pool - t1_slugs` and `pool - seeds` match the `set[str]` `candidate_slugs` params of `_build_t2` and `_t3_neighbors`. `_vi_fm`/`gdb_dom` defined and used within Task 1's tests. `SourceFrontmatter.from_dict` required keys (`kdb_signal`, `domain`, `source_type`, `summary`) all supplied.
