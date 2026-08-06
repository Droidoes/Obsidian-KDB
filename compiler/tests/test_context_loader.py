"""Tests for context_loader — real Kuzu, no mocks (#123 P3a.2b contract).

T2 is the adapter's validated selector hits (`t2_selection`), in SELECTOR
ORDER — semantic selection is the sole T2 seeding path (R-P3a-2; the
regex/resolver family is deleted, §7). Within-tier sort key:
`(-tier, rank_index, -pagerank, slug)` with `rank_index` the fat-stage rank
for T2 members and a constant for T1/T3 (§4.3) — under a binding cap,
selector rank decides which T2 pages survive. T3 is always a 1-hop expansion
of T1∪T2 seeds; the cold-start 2-hop widening is gone (§7).
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from kdb_graph.graphdb import GraphDB
from common.source_io import SourceFrontmatter
from common.types import ContextSnapshot

from compiler import context_loader


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


def _fm(keys, domain: str | None = "value-investing") -> SourceFrontmatter:
    return SourceFrontmatter(
        kdb_signal="signal", domain=domain, source_type="essay",
        author="Test", summary="A summary.", key_themes=["a"],
        entity_search_keys=keys,
    )


class TestTierRanking:
    def test_t1_source_supported_entities_ranked_highest(self, gdb):
        """Entities supported by the source appear first (tier 3 score)."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        # src-alpha supports hub, spoke-1, spoke-2 — all must be present
        assert "hub" in slugs
        assert "spoke-1" in slugs
        assert "spoke-2" in slugs
        # They should be the first 3 (highest tier)
        assert set(slugs[:3]) == {"hub", "spoke-1", "spoke-2"}

    def test_t2_selection_ranked_below_t1(self, gdb):
        """Selector hits rank below source-supported entities."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b"],
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        assert "leaf-b" in slugs
        leaf_b_idx = slugs.index("leaf-b")
        for s in ("hub", "spoke-1", "spoke-2"):
            assert slugs.index(s) < leaf_b_idx

    def test_t3_neighbors_ranked_below_t2(self, gdb):
        """1-hop neighbors of seeds rank below selector hits."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-beta",
            t2_selection=["spoke-2"],
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        # src-beta T1 = {leaf-a}; T2 = {spoke-2}. T3 = 1-hop of {leaf-a, spoke-2}
        # → hub, spoke-1 (via hub)… all below T2.
        assert slugs.index("leaf-a") < slugs.index("spoke-2")
        assert "hub" in slugs
        assert slugs.index("spoke-2") < slugs.index("hub")

    def test_pagerank_breaks_ties_within_t1(self, gdb):
        """Within T1 (constant rank_index), higher PageRank sorts first."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        # Within T1: hub has highest PageRank (most inbound).
        assert slugs[0] == "hub"

    def test_selector_rank_beats_pagerank_within_t2(self, gdb):
        """§4.3's explicit sort key: rank_index (fat-stage rank) sorts before
        -pagerank — a lower-PageRank hit selected EARLIER by the selector
        ranks first. leaf-a has more inbound links (hub, spoke-2) than
        leaf-b (none) yet is ranked second by the selector here."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "leaf-a"],   # selector order, not PageRank
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        assert slugs.index("leaf-b") < slugs.index("leaf-a")

    def test_page_cap_governs_t2_t3_only(self, gdb):
        """#131: page_cap is t2/t3 flood control — t1 is must-see, cap-EXEMPT.
        cap=3 with 3 T1 + 2 T2 + 1 T3 candidates: all 3 T1 delivered in full;
        the t2∪t3 tail is capped at 3."""
        result = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "orphan-x"],
            page_cap=3,
        )
        snapshot, t = result.snapshot, result.telemetry
        assert len(snapshot.t1) == 3                        # exempt — full delivery
        assert t.t1.delivered == t.t1.candidates == 3
        # The cap's real scope: exactly 3 of the t2∪t3 tail survive —
        # both T2 hits (selector order), then the T3 neighbor.
        assert t.t2.slugs == ["leaf-b", "orphan-x"]
        assert t.t3.slugs == ["leaf-a"]
        assert len(snapshot.pages) == 6                     # 3 T1 + 3 capped rest

    def test_binding_cap_selector_rank_decides_t2_survivors(self, gdb):
        """§3.2's ratified behavior change: under a binding cap, selector
        rank — not PageRank — decides which T2 pages survive. Cap=1 leaves
        exactly one t2/t3 slot (t1 is cap-exempt, #131); the FIRST selector
        hit wins it even though the second has the higher PageRank."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "leaf-a"],
            page_cap=1,                          # exactly 1 t2/t3 slot
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        assert len(slugs) == 4                   # 3 T1 (exempt) + 1 survivor
        assert "leaf-b" in slugs                 # selector rank 1 survives
        assert "leaf-a" not in slugs             # higher PageRank, cut anyway

    def test_outgoing_links_populated(self, gdb):
        """Each ContextPage carries its outgoing_links from the graph."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        ).snapshot
        hub_page = next(p for p in snapshot.pages if p.slug == "hub")
        assert set(hub_page.outgoing_links) == {"spoke-1", "spoke-2", "leaf-a"}

    def test_source_id_set_on_snapshot(self, gdb):
        """ContextSnapshot carries source_id."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        ).snapshot
        assert snapshot.source_id == "src-alpha"


class TestT1CapExemption:
    """#131: t1 is must-see — delivered in full even when it alone exceeds
    page_cap; the cap governs only the t2∪t3 tail."""

    def test_t1_exceeding_cap_is_fully_delivered(self, gdb):
        """The run-7 defect in miniature (Pabrai: 65 t1 candidates, 50
        delivered → 15 silently amputated, 14 retracted): a source owning MORE
        than page_cap of its own pages still has every one delivered."""
        conn = gdb.conn
        conn.execute(
            "CREATE (s:Source {source_id: 'src-gamma', source_type: 'raw', "
            "canonical_path: 'src-gamma', status: 'active', "
            "file_type: 'markdown', hash: 'sha256:aaa', size_bytes: 100, "
            "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
            "last_ingested_at: '2026-01-01', ingest_state: 'compiled', "
            "ingest_count: 1, last_run_id: 'r1', moved_to: ''})")
        for i in range(8):
            slug = f"gamma-{i}"
            conn.execute(
                "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                "status: 'active', confidence: 'medium', "
                "created_at: '2026-01-01', updated_at: '2026-01-01', "
                "first_run_id: 'r1', last_run_id: 'r1'})", {"s": slug})
            conn.execute(
                "MATCH (s:Source {source_id: 'src-gamma'}), "
                "(e:Entity {slug: $slug}) "
                "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)", {"slug": slug})
        result = context_loader.build_context_snapshot(
            conn, source_id="src-gamma", page_cap=3)
        t = result.telemetry
        assert t.t1.candidates == 8
        assert t.t1.delivered == 8                     # cap=3 never touches t1
        assert len(result.snapshot.t1) == 8
        assert t.t2.delivered + t.t3.delivered <= 3


class TestSnapshotTierShape:
    """#129: the snapshot is tier-structured — t1/t2/t3 lists, pairwise
    disjoint, each in global rank order; `pages` is the derived flat view
    (t1+t2+t3). Selection is untouched, so these shape tests double as the
    parity net: tier membership + order pin the pre-#129 slug sequence."""

    def test_to_dict_shape(self, gdb):
        d = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-a"],
            page_cap=50,
        ).snapshot.to_dict()
        assert set(d.keys()) == {"source_id", "t1", "t2", "t3"}
        assert "pages" not in d
        for tier in ("t1", "t2", "t3"):
            assert isinstance(d[tier], list)
            for page in d[tier]:
                assert set(page.keys()) == {
                    "slug", "title", "page_type", "outgoing_links"}

    def test_tiers_disjoint_union_is_rank_order(self, gdb):
        snap = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-a"],
            page_cap=50,
        ).snapshot
        t1 = [p.slug for p in snap.t1]
        t2 = [p.slug for p in snap.t2]
        t3 = [p.slug for p in snap.t3]
        # Topology: T1 = src-alpha SUPPORTS; T2 = the selector hit; T3 =
        # 1-hop of seeds minus seeds → leaf-b (via hub); orphan-x excluded.
        assert set(t1) == {"hub", "spoke-1", "spoke-2"}
        assert t2 == ["leaf-a"]
        assert t3 == ["leaf-b"]
        # Disjoint, and the flat view is the strict tier concatenation.
        assert len(t1 + t2 + t3) == len(set(t1 + t2 + t3))
        assert [p.slug for p in snap.pages] == t1 + t2 + t3

    def test_t1_carries_exactly_source_supported(self, gdb):
        """The anti-churn precondition: the model is always shown exactly
        the pages this source currently SUPPORTS, in its own tier."""
        snap = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        ).snapshot
        assert {p.slug for p in snap.t1} == {"hub", "spoke-1", "spoke-2"}

    def test_tier_lists_match_telemetry(self, gdb):
        """The snapshot tiers and the telemetry TierRecords are the same
        partition — under a binding cap the t2/t3 tiers are the cap-truncated
        prefixes (selector-rank order, §3.2; t1 is cap-exempt, #131), at full
        delivery they are the tier sets."""
        # Binding cap: exactly 1 t2/t3 slot — selector rank 1 survives.
        capped = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "leaf-a"],
            page_cap=1,
        )
        for tier_pages, record in (
            (capped.snapshot.t1, capped.telemetry.t1),
            (capped.snapshot.t2, capped.telemetry.t2),
            (capped.snapshot.t3, capped.telemetry.t3),
        ):
            assert [p.slug for p in tier_pages] == record.slugs
        assert capped.telemetry.t2.slugs == ["leaf-b"]   # cap-truncated
        # Full delivery.
        full = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "leaf-a"],
            page_cap=50,
        )
        for tier_pages, record in (
            (full.snapshot.t1, full.telemetry.t1),
            (full.snapshot.t2, full.telemetry.t2),
            (full.snapshot.t3, full.telemetry.t3),
        ):
            assert [p.slug for p in tier_pages] == record.slugs
        assert full.telemetry.t2.slugs == ["leaf-b", "leaf-a"]

    def test_empty_tiers_serialize_empty(self, gdb):
        """No search ⇒ t2 is [] in the dict; empty tiers are valid (R-P3a-3)."""
        d = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        ).snapshot.to_dict()
        assert d["t1"] != []
        assert d["t2"] == []

    def test_empty_graph_all_tiers_empty(self, tmp_path):
        with GraphDB(tmp_path / "empty-tier-graph") as g:
            result = context_loader.build_context_snapshot(
                g.conn, source_id="nonexistent", page_cap=50)
        snap = result.snapshot
        assert snap.t1 == [] and snap.t2 == [] and snap.t3 == []
        assert snap.pages == []
        assert snap.to_dict() == {
            "source_id": "nonexistent", "t1": [], "t2": [], "t3": []}


class TestT2SelectionContract:
    def test_t2_selection_intersected_with_pool_minus_t1(self, gdb):
        """T2 = t2_selection ∩ (active pool − T1), order preserved — the
        minus-T1 is a no-op safeguard under §4.1's pre-selector exclusion;
        unknown slugs drop out too."""
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "hub", "no-such-slug", "leaf-a"],
            page_cap=50,
        ).snapshot
        telemetry_t2 = [p.slug for p in snapshot.pages
                        if p.slug in ("leaf-a", "leaf-b")]
        assert telemetry_t2 == ["leaf-b", "leaf-a"]  # order preserved
        # hub is T1 — it appears exactly once, in the T1 band
        slugs = [p.slug for p in snapshot.pages]
        assert slugs.index("hub") < slugs.index("leaf-b")

    def test_none_and_empty_selection_both_empty_t2(self, gdb):
        """None (no search ran — replay/tooling) and [] (searched, nothing
        selected) both produce an empty T2; T1/T3 proceed (R-P3a-3)."""
        for selection in (None, []):
            result = context_loader.build_context_snapshot(
                gdb.conn,
                source_id="src-alpha",
                t2_selection=selection,
                page_cap=50,
            )
            assert result.telemetry.t2.candidates == 0
            assert result.telemetry.t1.candidates == 3

    def test_duplicate_selection_entries_deduped_first_rank_wins(self, gdb):
        snapshot = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "leaf-a", "leaf-b"],
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        assert slugs.count("leaf-b") == 1
        assert slugs.index("leaf-b") < slugs.index("leaf-a")


class TestT3OneHopAlways:
    """The cold-start 2-hop widening is deleted (§7) — T3 is a deterministic
    1-hop expansion of T1∪T2 seeds, even for a cold-start source with a
    single T2 seed."""

    @pytest.fixture
    def cold_start_gdb(self, tmp_path: Path):
        """legalism -> hub-node -> deep-leaf chain; src-new has NO supports."""
        with GraphDB(tmp_path / "cold-start-graph") as g:
            conn = g.conn
            for slug, title, ptype in [
                ("margin-of-safety", "Margin of Safety", "concept"),
                ("legalism", "Legalism", "concept"),
                ("hub-node", "Hub Node", "concept"),
                ("deep-leaf", "Deep Leaf", "article"),
            ]:
                conn.execute(
                    "CREATE (e:Entity {slug: $s, title: $t, page_type: $pt, "
                    "status: 'active', confidence: 'medium', "
                    "created_at: '2026-01-01', updated_at: '2026-01-01', "
                    "first_run_id: 'r1', last_run_id: 'r1'})",
                    {"s": slug, "t": title, "pt": ptype},
                )
            conn.execute(
                "CREATE (s:Source {source_id: 'src-new', source_type: 'raw', "
                "canonical_path: 'src-new', status: 'active', file_type: 'markdown', "
                "hash: 'sha256:bbb', size_bytes: 200, "
                "first_seen_at: '2026-01-01', last_seen_at: '2026-01-01', "
                "last_ingested_at: '', ingest_state: 'pending', "
                "ingest_count: 0, last_run_id: '', moved_to: ''})"
            )
            for f, t in [
                ("margin-of-safety", "legalism"),
                ("legalism", "hub-node"),
                ("hub-node", "deep-leaf"),
                ("hub-node", "margin-of-safety"),
            ]:
                conn.execute(
                    "MATCH (a:Entity {slug: $f}), (b:Entity {slug: $t}) "
                    "CREATE (a)-[:LINKS_TO {run_id: 'r1'}]->(b)",
                    {"f": f, "t": t},
                )
            yield g

    def test_cold_start_sparse_t2_stays_one_hop(self, cold_start_gdb):
        """Cold-start + one T2 seed ⇒ still 1-hop: legalism's 1-hop neighbors
        (hub-node, margin-of-safety) are T3; deep-leaf is 2-hop — EXCLUDED
        (the widening is gone)."""
        snapshot = context_loader.build_context_snapshot(
            cold_start_gdb.conn,
            source_id="src-new",
            t2_selection=["legalism"],
            page_cap=50,
        ).snapshot
        slugs = [p.slug for p in snapshot.pages]
        assert "legalism" in slugs               # T2
        assert "hub-node" in slugs               # T3, 1-hop
        assert "margin-of-safety" in slugs       # T3, 1-hop (incoming)
        assert "deep-leaf" not in slugs          # 2-hop — widening deleted

    def test_empty_seeds_empty_t3_is_valid(self, cold_start_gdb):
        """R-P3a-3: empty T1/T2 ⇒ empty T3, and that is a valid answer."""
        result = context_loader.build_context_snapshot(
            cold_start_gdb.conn,
            source_id="src-new",
            t2_selection=[],
            page_cap=50,
        )
        assert result.snapshot.pages == []
        assert result.telemetry.t3.candidates == 0
        assert result.telemetry.cold_start is True


class TestT3NeighborsRegression:
    """#81: lock the `_t3_neighbors` primitive's contract (unchanged by
    P3a.2b — the builder now always calls it with max_hops=1)."""

    @pytest.fixture
    def chain_gdb(self, tmp_path: Path):
        with GraphDB(tmp_path / "chain-graph") as g:
            conn = g.conn
            for slug in ["margin-of-safety", "legalism", "hub-node", "deep-leaf"]:
                conn.execute(
                    "CREATE (e:Entity {slug: $s, title: $s, page_type: 'concept', "
                    "status: 'active', confidence: 'medium', "
                    "created_at: '2026-01-01', updated_at: '2026-01-01', "
                    "first_run_id: 'r1', last_run_id: 'r1'})",
                    {"s": slug},
                )
            for f, t in [
                ("margin-of-safety", "legalism"),
                ("legalism", "hub-node"),
                ("hub-node", "deep-leaf"),
            ]:
                conn.execute(
                    "MATCH (a:Entity {slug: $f}), (b:Entity {slug: $t}) "
                    "CREATE (a)-[:LINKS_TO {run_id: 'r1'}]->(b)",
                    {"f": f, "t": t},
                )
            yield g

    def test_t3_neighbors_is_deterministic(self, chain_gdb):
        from compiler.context_loader import _t3_neighbors

        seeds = {"margin-of-safety"}
        candidates = {"margin-of-safety", "legalism", "hub-node", "deep-leaf"}
        a = _t3_neighbors(chain_gdb.conn, seeds, candidates, max_hops=1)
        b = _t3_neighbors(chain_gdb.conn, seeds, candidates, max_hops=1)
        assert a == b

    def test_t3_neighbors_expands_outgoing_and_incoming(self, chain_gdb):
        from compiler.context_loader import _t3_neighbors

        seeds = {"legalism"}
        candidates = {"margin-of-safety", "hub-node"}
        result = _t3_neighbors(chain_gdb.conn, seeds, candidates, max_hops=1)
        assert "hub-node" in result, "outgoing neighbor dropped"
        assert "margin-of-safety" in result, "incoming neighbor dropped"

    def test_t3_neighbors_respects_candidate_filter(self, chain_gdb):
        from compiler.context_loader import _t3_neighbors

        seeds = {"legalism"}
        candidates = {"hub-node"}
        result = _t3_neighbors(chain_gdb.conn, seeds, candidates, max_hops=1)
        assert result == {"hub-node"}

    def test_t3_neighbors_excludes_seeds_from_output(self, chain_gdb):
        from compiler.context_loader import _t3_neighbors

        seeds = {"legalism", "hub-node"}
        candidates = {"margin-of-safety", "legalism", "hub-node", "deep-leaf"}
        result = _t3_neighbors(chain_gdb.conn, seeds, candidates, max_hops=1)
        assert "legalism" not in result
        assert "hub-node" not in result


# ---------------------------------------------------------------------------
# Same-domain gate (D3 override): T2/T3 pull only from the source's Pass-1 domain
# ---------------------------------------------------------------------------


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


def test_t2_off_domain_selection_is_dropped(gdb_dom):
    snap = context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", page_cap=50,
        frontmatter=_fm(["ai-node"]),
        t2_selection=["ai-node"]).snapshot
    assert "ai-node" not in [p.slug for p in snap.pages]


def test_t2_same_domain_selection_is_kept(gdb_dom):
    snap = context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", page_cap=50,
        frontmatter=_fm(["vi-leaf"]),
        t2_selection=["vi-leaf"]).snapshot
    assert "vi-leaf" in [p.slug for p in snap.pages]


def test_t3_excludes_cross_domain_neighbor(gdb_dom):
    # vi-hub LINKS_TO ai-node (cross-domain) and vi-leaf (same-domain).
    snap = context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", page_cap=50,
        frontmatter=_fm([])).snapshot
    slugs = [p.slug for p in snap.pages]
    assert "ai-node" not in slugs            # cross-domain neighbor excluded
    assert "vi-leaf" in slugs                # same-domain neighbor admitted


def test_no_padding_and_all_same_domain(gdb_dom):
    snap = context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", page_cap=50,
        frontmatter=_fm([])).snapshot
    slugs = {p.slug for p in snap.pages}
    assert slugs <= {"vi-hub", "vi-spoke", "vi-leaf"}   # no off-domain top-up
    assert "ai-node" not in slugs


def test_no_domain_source_tiering_pool_is_whole_active_graph(gdb_dom):
    """§4.3's stated absent-domain rule: a source with no domain tiers over
    the WHOLE ACTIVE GRAPH (frontmatter=None → un-scoped; ai-node reachable
    via T3 from vi-hub)."""
    snap = context_loader.build_context_snapshot(
        gdb_dom.conn, source_id="src-vi", page_cap=50,
        frontmatter=None).snapshot
    assert "ai-node" in [p.slug for p in snap.pages]


# ---------------------------------------------------------------------------
# T1 pass-through (§4.3, [v0.3] scoped adapter read)
# ---------------------------------------------------------------------------


class TestT1SlugsPassThrough:
    def test_t1_slugs_param_is_authoritative(self, gdb):
        """The adapter's single scoped T1 read is passed through — the builder
        does NOT re-read SUPPORTS when t1_slugs is given (src-beta's real T1
        is {leaf-a}; the passed subset stands)."""
        result = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-beta",
            t1_slugs=frozenset(),
            page_cap=50,
        )
        assert result.telemetry.t1.candidates == 0
        assert result.telemetry.cold_start is True
        assert "leaf-a" not in [p.slug for p in result.snapshot.pages]

    def test_t1_slugs_none_builder_reads_and_scopes_itself(self, gdb):
        """None (replay/tooling path) ⇒ the builder reads + scopes T1 itself,
        as today — including the inactive-SUPPORTS KeyError guard (§4.1 B1)."""
        gdb.conn.execute(
            "MATCH (s:Source {source_id: 'src-alpha'}), (e:Entity {slug: 'orphan-x'}) "
            "CREATE (s)-[:SUPPORTS {run_id: 'r1'}]->(e)")
        gdb.conn.execute(
            "MATCH (e:Entity {slug: 'orphan-x'}) SET e.status = 'inactive'")
        result = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            page_cap=50,
        )
        assert result.telemetry.t1.candidates == 3   # retracted entity scoped out
        assert "orphan-x" not in [p.slug for p in result.snapshot.pages]


# ---------------------------------------------------------------------------
# Telemetry (the persistence-facing product, #122's two-product split)
# ---------------------------------------------------------------------------


class TestTelemetry:
    def test_telemetry_fields_new_contract(self, gdb):
        """keys_emitted carries the ORIGINAL frontmatter expressions; tiers
        are pre-cap candidates + post-cap delivered; no V1 vocabulary."""
        search_sentinel = object()
        outcome_sentinel = object()
        result = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            frontmatter=_fm(["leaf-b", "leaf-a"], domain=None),
            t2_selection=["leaf-b", "leaf-a"],
            search_summary=search_sentinel,   # pass-through, never prompt-serialized
            key_outcomes=[outcome_sentinel, outcome_sentinel],
            page_cap=50,
        )
        t = result.telemetry
        assert t.source_id == "src-alpha"
        assert t.keys_emitted == ["leaf-b", "leaf-a"]   # originals, emission order
        assert t.key_outcomes == [outcome_sentinel, outcome_sentinel]
        assert t.t1.candidates == 3 and t.t1.delivered == 3
        assert t.t2.candidates == 2 and t.t2.slugs == ["leaf-b", "leaf-a"]
        assert t.candidate_universe_size == 6           # whole-graph pool (absent domain)
        assert t.cold_start is False
        assert t.page_cap == 50
        assert t.search is search_sentinel
        # The retired V1 vocabulary is gone from the telemetry shape.
        assert not hasattr(t, "configured_t2_mode")
        assert not hasattr(t, "effective_t2_strategy")
        assert not hasattr(t, "max_hops")

    def test_telemetry_pre_pass1_keys_empty(self, gdb):
        result = context_loader.build_context_snapshot(
            gdb.conn, source_id="src-alpha", frontmatter=None, page_cap=50)
        assert result.telemetry.keys_emitted == []
        assert result.telemetry.key_outcomes == []
        assert result.telemetry.search is None

    def test_telemetry_tier_records_pre_and_post_cap(self, gdb):
        """candidates = pre-cap tier sets; delivered/slugs = post-projection
        prompt pages — t1 in FULL (#131: cap-exempt), t2/t3 post-cap."""
        result = context_loader.build_context_snapshot(
            gdb.conn,
            source_id="src-alpha",
            t2_selection=["leaf-b", "leaf-a"],
            page_cap=1,
        )
        t = result.telemetry
        assert t.t1.delivered == t.t1.candidates == 3    # exempt — full delivery
        assert t.t2.candidates == 2
        assert t.t2.delivered == 1 and t.t2.slugs == ["leaf-b"]
        total = t.t1.delivered + t.t2.delivered + t.t3.delivered
        assert total == 4 <= t.t1.delivered + t.page_cap

    def test_empty_graph_full_telemetry(self, tmp_path):
        """Empty-graph early return: FULL telemetry — zero tiers,
        cold_start=True, candidate_universe_size=0, search passed through
        (§4.3: the adapter searched the empty space upstream — populated,
        not null)."""
        search_sentinel = object()
        with GraphDB(tmp_path / "empty-graph") as g:
            result = context_loader.build_context_snapshot(
                g.conn,
                source_id="nonexistent",
                frontmatter=_fm(["k1", "k2"]),
                key_outcomes=["o1", "o2"],
                search_summary=search_sentinel,
                page_cap=50,
            )
        assert result.snapshot.pages == []
        assert result.snapshot.source_id == "nonexistent"
        t = result.telemetry
        assert t.keys_emitted == ["k1", "k2"]
        assert t.key_outcomes == ["o1", "o2"]
        assert t.t1.candidates == t.t2.candidates == t.t3.candidates == 0
        assert t.candidate_universe_size == 0
        assert t.cold_start is True
        assert t.search is search_sentinel


# ---------------------------------------------------------------------------
# Deletion guards (§7 — the retiring surface is GONE, no compatibility shim)
# ---------------------------------------------------------------------------


class TestDeletionGuards:
    def test_deleted_symbols_are_gone(self):
        for name in (
            "T2Mode", "_build_t2", "_t2_structured", "_t2_layered", "_t2_legacy",
            "_t2_from_search_keys", "_t2_slug_in_text", "_t2_title_in_text",
            "_title_eligible", "_whole_word_alternation", "_MIN_SEED_THRESHOLD",
            "_effective_strategy",
            "_resolve_to_canonical_slugs", "_resolve_to_canonical_slugs_batch",
            "_resolve_to_canonical_slugs_with_provenance",
            "_resolve_to_canonical_slugs_with_provenance_batch",
        ):
            assert not hasattr(context_loader, name), f"{name} survived §7"

    def test_re_import_is_gone(self):
        assert "re" not in vars(context_loader)

    def test_signature_has_no_mode_resolver_source_text(self):
        params = set(inspect.signature(
            context_loader.build_context_snapshot).parameters)
        assert "mode" not in params
        assert "resolver" not in params
        assert "source_text" not in params
        # The new contract's inputs are present.
        assert {"t2_selection", "t1_slugs", "search_summary"} <= params
