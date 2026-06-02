"""Tests for kdb_graph.rebuilder + adapters.obsidian_runs (#63.6).

The generic core (rebuilder.rebuild) is tested via a synthetic adapter built
inline; the Obsidian adapter is tested against synthetic state/runs/ trees in
tmp_path. Both share the same rebuild driver.

D39 filter semantics + D-S3 version support exercised via the
SkipReason eligibility cases.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pytest

from kdb_graph.adapters.base import (
    EligibilityResult,
    RunDescriptor,
)
from kdb_graph.adapters.obsidian_runs import ObsidianRunsAdapter
from kdb_graph.graphdb import GraphDB
from kdb_graph.rebuilder import RebuildResult, rebuild
from kdb_graph.tests.conftest import (
    make_compile_result,
    make_compiled_source,
    make_page,
    make_scan,
    make_scan_entry,
)


# ============================================================================
# 1. Helpers — synthetic kdb-compile run tree builder
# ============================================================================

def _write_run(
    journals_dir: Path,
    run_id: str,
    *,
    success: bool = True,
    dry_run: bool = False,
    schema_version: str = "2.0",
    started_at: str | None = None,
    sources: list[tuple[str, list[str]]] | None = None,
    skip_sidecar: bool = False,
    invalid_journal: bool = False,
    canonical_meta: dict | None = None,
) -> Path:
    """Write a synthetic kdb-compile run tree:
        <journals_dir>/<run_id>.json          — the run journal
        <journals_dir>/<run_id>/compile_result.json  — sidecar (unless skip_sidecar)
        <journals_dir>/<run_id>/last_scan.json        — sidecar (unless skip_sidecar)

    `sources` is a list of (source_id, [page_slugs]); each becomes a
    compiled_source entry. Defaults: one source 's' with two pages a, b.

    `canonical_meta` (#74.7): when provided, embedded verbatim into the
    sidecar's compile_result.json (post-#74 journals). Default None is
    the pre-#74 shape — no canonical_meta key in the cr.
    """
    journals_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journals_dir / f"{run_id}.json"

    sources = sources if sources is not None else [("KDB/raw/s.md", ["a", "b"])]

    if invalid_journal:
        # Malformed JSON content — exercises is_eligible's 'invalid_journal' path.
        journal_path.write_text("{ this is not valid json")
        return journal_path

    journal = {
        "schema_version": schema_version,
        "run_id": run_id,
        "started_at": started_at or run_id,
        "success": success,
        "dry_run": dry_run,
    }
    journal_path.write_text(json.dumps(journal))

    if skip_sidecar:
        return journal_path

    sidecar_dir = journals_dir / run_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    compiled_sources = [
        make_compiled_source(sid, [make_page(s) for s in slugs])
        for sid, slugs in sources
    ]
    mutation = make_compile_result(
        compiled_sources, run_id=run_id, canonical_meta=canonical_meta,
    )
    scan = make_scan([make_scan_entry(sid) for sid, _ in sources])

    (sidecar_dir / "compile_result.json").write_text(json.dumps(mutation))
    (sidecar_dir / "last_scan.json").write_text(json.dumps(scan))
    return journal_path


# ============================================================================
# 2. Generic rebuilder — tested with synthetic adapter
# ============================================================================

@dataclass
class FakeAdapter:
    """Minimal in-memory adapter for testing rebuild() in isolation."""
    source_type: ClassVar[str] = "fake"
    entity_id_namespace: ClassVar[str | None] = None
    supported_journal_versions: ClassVar[list[str]] = ["fake-v1"]

    runs: list[tuple[RunDescriptor, EligibilityResult, dict, dict]] = field(
        default_factory=list
    )

    def discover_runs(self, journals_dir: Path) -> list[RunDescriptor]:
        return [d for d, *_ in self.runs]

    def is_eligible(self, descriptor: RunDescriptor) -> EligibilityResult:
        for d, elig, _, _ in self.runs:
            if d.run_id == descriptor.run_id:
                return elig
        return EligibilityResult(False, "invalid_journal")

    def load_payload(self, descriptor: RunDescriptor):
        for d, _, mutation, scan in self.runs:
            if d.run_id == descriptor.run_id:
                return mutation, scan, descriptor.run_id
        raise KeyError(descriptor.run_id)

    def apply(self, mutation, scan, run_id, conn):
        from kdb_graph.ingestor import apply_compile_result
        return apply_compile_result(mutation, scan, run_id, conn=conn)

    def sync_current_run(self, mutation, scan, run_id, graph_dir=None):
        raise NotImplementedError  # not exercised here

    def add(
        self,
        run_id: str,
        sort_key: str,
        *,
        eligible: bool = True,
        skip_reason=None,
        mutation: dict | None = None,
        scan: dict | None = None,
    ) -> None:
        desc = RunDescriptor(run_id=run_id, sort_key=sort_key)
        self.runs.append((
            desc,
            EligibilityResult(eligible, skip_reason),
            mutation or {"compiled_sources": []},
            scan or {"files": []},
        ))


def test_rebuilder_empty(graph_dir, tmp_path):
    """Empty journals dir + empty extras → no-op."""
    adapter = FakeAdapter()
    result = rebuild(
        graph_dir=graph_dir,
        adapter=adapter,
        journals_dir=tmp_path,
        confirm=False,
    )
    assert result == RebuildResult(replayed=0, skipped=0, failed=0, outcomes=[])


def test_rebuilder_one_run(graph_dir, tmp_path):
    """Single eligible run → 1 replayed; graph has the entity it produced."""
    adapter = FakeAdapter()
    adapter.add(
        run_id="r1",
        sort_key="2026-04-21T00:00:00",
        mutation=make_compile_result(
            [make_compiled_source("KDB/raw/s.md", [make_page("alpha")])],
            run_id="r1",
        ),
        scan=make_scan([make_scan_entry("KDB/raw/s.md")]),
    )
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)
    assert result.replayed == 1
    assert result.failed == 0
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("alpha") is not None


def test_rebuilder_chronological_order(graph_dir, tmp_path):
    """Out-of-filesystem-order descriptors → replay in sort_key order.

    Verify by exercising MOVED-style time dependency: run 'r2' drops page 'b'
    introduced by run 'r1'; only the correct (r1 then r2) order yields b
    orphan_candidate. If replayed r2-first then r1-last, b would be active.
    """
    adapter = FakeAdapter()
    # Add in reverse-chronological order — sort_key should re-order them.
    adapter.add(
        run_id="r2",
        sort_key="2026-04-21T02:00:00",
        mutation=make_compile_result(
            [make_compiled_source("KDB/raw/s.md", [make_page("a")])],
            run_id="r2",
        ),
        scan=make_scan([make_scan_entry("KDB/raw/s.md")]),
    )
    adapter.add(
        run_id="r1",
        sort_key="2026-04-21T01:00:00",
        mutation=make_compile_result(
            [make_compiled_source("KDB/raw/s.md", [make_page("a"), make_page("b")])],
            run_id="r1",
        ),
        scan=make_scan([make_scan_entry("KDB/raw/s.md")]),
    )
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)
    assert result.replayed == 2
    with GraphDB(graph_dir) as gdb:
        b = gdb.get_entity("b")
    assert b is not None
    assert b.status == "orphan_candidate"  # r2 dropped b, so b is orphan


def test_rebuilder_skip_reasons_preserved(graph_dir, tmp_path):
    """Ineligible runs reported with structured skip reasons (D-S3 audit)."""
    adapter = FakeAdapter()
    adapter.add("r-failed",   "ts1", eligible=False, skip_reason="failed")
    adapter.add("r-dry",      "ts2", eligible=False, skip_reason="dry_run")
    adapter.add("r-nopayload", "ts3", eligible=False, skip_reason="payload_missing")
    adapter.add("r-badver",   "ts4", eligible=False, skip_reason="unsupported_version")
    adapter.add("r-bad",      "ts5", eligible=False, skip_reason="invalid_journal")
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)
    assert result.replayed == 0
    assert result.skipped == 5
    reasons = {o.skip_reason for o in result.outcomes if o.state == "skipped"}
    assert reasons == {"failed", "dry_run", "payload_missing", "unsupported_version", "invalid_journal"}


def test_rebuilder_whole_db_drop(graph_dir, tmp_path):
    """Pre-populated graph → rebuild wipes existing data before replay."""
    # Pre-seed graph with 'omega' via direct ingestion.
    cr = make_compile_result(
        [make_compiled_source("KDB/raw/pre.md", [make_page("omega")])],
        run_id="pre",
    )
    scan = make_scan([make_scan_entry("KDB/raw/pre.md")])
    with GraphDB(graph_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "pre")
        assert gdb.get_entity("omega") is not None

    # Rebuild with a different adapter that only replays 'alpha'.
    adapter = FakeAdapter()
    adapter.add(
        "r1", "ts",
        mutation=make_compile_result(
            [make_compiled_source("KDB/raw/s.md", [make_page("alpha")])],
            run_id="r1",
        ),
        scan=make_scan([make_scan_entry("KDB/raw/s.md")]),
    )
    rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)

    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("omega") is None     # wiped
        assert gdb.get_entity("alpha") is not None  # replayed


def test_rebuilder_idempotent(graph_dir, tmp_path):
    """Two consecutive rebuilds → identical final state."""
    adapter = FakeAdapter()
    adapter.add(
        "r1", "ts",
        mutation=make_compile_result(
            [make_compiled_source("KDB/raw/s.md", [make_page("alpha"), make_page("beta")])],
            run_id="r1",
        ),
        scan=make_scan([make_scan_entry("KDB/raw/s.md")]),
    )
    rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)
    with GraphDB(graph_dir) as gdb:
        s1 = gdb.stats()
    rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)
    with GraphDB(graph_dir) as gdb:
        s2 = gdb.stats()
    assert s1 == s2


def test_rebuilder_replay_equals_live(tmp_path):
    """Same inputs to live ingestion vs rebuild → graph states equal."""
    cr = make_compile_result(
        [make_compiled_source("KDB/raw/s.md", [
            make_page("a", outgoing_links=["b"]),
            make_page("b"),
        ])],
        run_id="r1",
    )
    scan = make_scan([make_scan_entry("KDB/raw/s.md")])

    # Path A: live ingestion.
    live_dir = tmp_path / "live"
    with GraphDB(live_dir) as gdb:
        gdb.apply_compile_result(cr, scan, "r1")
        live_stats = gdb.stats()
        live_a = gdb.get_entity("a")
        live_b = gdb.get_entity("b")

    # Path B: replay via rebuild.
    replay_dir = tmp_path / "replay"
    adapter = FakeAdapter()
    adapter.add("r1", "ts", mutation=cr, scan=scan)
    rebuild(graph_dir=replay_dir, adapter=adapter, journals_dir=tmp_path, confirm=False)
    with GraphDB(replay_dir) as gdb:
        replay_stats = gdb.stats()
        replay_a = gdb.get_entity("a")
        replay_b = gdb.get_entity("b")

    assert live_stats == replay_stats
    assert live_a.slug == replay_a.slug == "a"
    assert live_b.slug == replay_b.slug == "b"


# ============================================================================
# 3. Obsidian adapter — synthetic state/runs tree under tmp_path
# ============================================================================

def test_obsidian_adapter_discover_and_replay(graph_dir, tmp_path):
    """End-to-end: synthetic state/runs/ tree → adapter discovers → rebuild replays."""
    journals = tmp_path / "runs"
    _write_run(journals, "2026-04-21T01-00-00Z", started_at="2026-04-21T01:00:00",
               sources=[("KDB/raw/s.md", ["alpha", "beta"])])
    _write_run(journals, "2026-04-21T02-00-00Z", started_at="2026-04-21T02:00:00",
               sources=[("KDB/raw/s.md", ["alpha"])])  # drops beta

    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.replayed == 2
    assert result.failed == 0
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("alpha") is not None
        beta = gdb.get_entity("beta")
    assert beta is not None
    assert beta.status == "orphan_candidate"  # ordered replay made beta orphan


def test_obsidian_adapter_skip_dry_run(graph_dir, tmp_path):
    """dry_run=True journal → skipped with skip_reason='dry_run'."""
    journals = tmp_path / "runs"
    _write_run(journals, "r-dry", dry_run=True)
    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.replayed == 0
    assert result.skipped == 1
    assert result.outcomes[0].skip_reason == "dry_run"


def test_obsidian_adapter_skip_failed(graph_dir, tmp_path):
    """success=False journal → skipped with skip_reason='failed'."""
    journals = tmp_path / "runs"
    _write_run(journals, "r-fail", success=False)
    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.skipped == 1
    assert result.outcomes[0].skip_reason == "failed"


def test_obsidian_adapter_skip_payload_missing(graph_dir, tmp_path):
    """Eligible-looking journal but no sidecar → skipped with payload_missing."""
    journals = tmp_path / "runs"
    _write_run(journals, "r-nopayload", skip_sidecar=True)
    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.skipped == 1
    assert result.outcomes[0].skip_reason == "payload_missing"


def test_obsidian_adapter_skip_unsupported_version(graph_dir, tmp_path):
    """schema_version not in supported_journal_versions → skipped (D-S3)."""
    journals = tmp_path / "runs"
    _write_run(journals, "r-v99", schema_version="99.0")
    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.skipped == 1
    assert result.outcomes[0].skip_reason == "unsupported_version"


def test_obsidian_adapter_replayable_payload_eligible_despite_failure(graph_dir, tmp_path):
    """D50 amended D39: success=False + replayable_payload=True is eligible.
    Graph-sync-failed runs with valid sidecars must be replayable by rebuild."""
    journals = tmp_path / "runs"
    journal_path = _write_run(journals, "r-graphsync-fail", success=False)
    # Patch the journal to include replayable_payload=True
    import json
    journal = json.loads(journal_path.read_text())
    journal["replayable_payload"] = True
    journal_path.write_text(json.dumps(journal))

    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.replayed == 1
    assert result.skipped == 0


def test_obsidian_adapter_failed_without_replayable_payload_skipped(graph_dir, tmp_path):
    """D50: success=False + replayable_payload=False → still skipped."""
    journals = tmp_path / "runs"
    journal_path = _write_run(journals, "r-compile-fail", success=False)
    import json
    journal = json.loads(journal_path.read_text())
    journal["replayable_payload"] = False
    journal_path.write_text(json.dumps(journal))

    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.skipped == 1
    assert result.outcomes[0].skip_reason == "failed"


def test_obsidian_adapter_skip_invalid_journal(graph_dir, tmp_path):
    """Malformed JSON journal → skipped with invalid_journal."""
    journals = tmp_path / "runs"
    _write_run(journals, "r-bad", invalid_journal=True)
    adapter = ObsidianRunsAdapter()
    result = rebuild(graph_dir=graph_dir, adapter=adapter, journals_dir=journals, confirm=False)
    assert result.skipped == 1
    assert result.outcomes[0].skip_reason == "invalid_journal"


# ============================================================================
# 4. Baton-backfill (Shape B per blueprint §13.1 Q3 outcome (d))
# ============================================================================

def test_rebuilder_backfill_baton(graph_dir, tmp_path):
    """Direct descriptor with payload_paths is replayed implicitly-eligibly."""
    # No journals on disk — only the baton paths.
    cr_path = tmp_path / "compile_result.json"
    scan_path = tmp_path / "last_scan.json"
    cr_path.write_text(json.dumps(make_compile_result(
        [make_compiled_source("KDB/raw/baton.md", [make_page("baton-page")])],
        run_id="baton-run",
    )))
    scan_path.write_text(json.dumps(make_scan([make_scan_entry("KDB/raw/baton.md")])))

    descriptor = RunDescriptor(
        run_id="baton-run",
        sort_key="0000-pre-63-backfill",
        journal_path=None,
        payload_paths=(cr_path, scan_path),
    )
    adapter = ObsidianRunsAdapter()
    journals_dir = tmp_path / "runs"  # nonexistent — adapter returns []
    result = rebuild(
        graph_dir=graph_dir,
        adapter=adapter,
        journals_dir=journals_dir,
        confirm=False,
        extra_descriptors=[descriptor],
    )
    assert result.replayed == 1
    with GraphDB(graph_dir) as gdb:
        assert gdb.get_entity("baton-page") is not None


def test_rebuilder_backfill_sorts_first(graph_dir, tmp_path):
    """Baton descriptor sort_key '0000-…' sorts before real ISO-8601 keys.

    Both runs are replayed; the baton goes first (its outcome is listed first).
    Both producers' entities coexist because the two runs touch different
    Source IDs — neither run's Phase 3 replacement clears the other's
    SUPPORTS edges. (The chronological-order-matters semantics are already
    covered by test_rebuilder_chronological_order, which exercises a single
    source across multiple runs.)
    """
    journals = tmp_path / "runs"
    _write_run(
        journals, "2026-05-01T00-00-00Z", started_at="2026-05-01T00:00:00",
        sources=[("KDB/raw/s.md", ["kept"])],
    )
    cr_path = tmp_path / "compile_result.json"
    scan_path = tmp_path / "last_scan.json"
    cr_path.write_text(json.dumps(make_compile_result(
        [make_compiled_source("KDB/raw/baton.md", [make_page("baton-page")])],
        run_id="baton-run",
    )))
    scan_path.write_text(json.dumps(make_scan([make_scan_entry("KDB/raw/baton.md")])))
    descriptor = RunDescriptor(
        run_id="baton-run",
        sort_key="0000-pre-63-backfill",
        journal_path=None,
        payload_paths=(cr_path, scan_path),
    )
    adapter = ObsidianRunsAdapter()
    result = rebuild(
        graph_dir=graph_dir,
        adapter=adapter,
        journals_dir=journals,
        confirm=False,
        extra_descriptors=[descriptor],
    )
    assert result.replayed == 2
    # Order of outcomes: baton first, then real run.
    assert result.outcomes[0].run_id == "baton-run"
    assert result.outcomes[1].run_id == "2026-05-01T00-00-00Z"
    with GraphDB(graph_dir) as gdb:
        baton_page = gdb.get_entity("baton-page")
        kept = gdb.get_entity("kept")
    assert baton_page is not None
    assert baton_page.status == "active"   # baton's source still supports it
    assert kept is not None
    assert kept.status == "active"


# ============================================================================
# Cleanup event routing (#68)
# ============================================================================

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

    journals = tmp_path / "runs"
    _write_run(journals, "2026-01-01T00-00-00",
               started_at="2026-01-01T00:00:00",
               sources=[("KDB/raw/s.md", ["foo", "solo"])])

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


# ============================================================================
# 7. #74.7 — canonical_meta replay (D-R5-7 / D-R5-10 / blueprint §8.4)
# ============================================================================
#
# Rebuild's correctness guarantee for post-#74 journals: a journal whose
# sidecar carries `canonical_meta` replays into a graph with the exact
# alias Entity rows + ALIAS_OF edges the original compile produced. Pre-#74
# journals replay untouched (canonical_id NULL throughout). Mixed journal
# sequences are the realistic scenario for any vault that pre-dated #74.

def _canonical_meta_with(aliases: list[tuple[str, str, str]]) -> dict:
    return {
        "algorithm_version": "1.0",
        "ledger_snapshot_sha256": "deadbeef",
        "aliases_emitted": [
            {"alias_slug": a, "canonical_slug": c, "algorithm": algo}
            for (a, c, algo) in aliases
        ],
        "outgoing_link_remaps": [],
        "merged_pages": [],
    }


def test_rebuild_post_74_journal_reproduces_alias_state(graph_dir, tmp_path):
    """A v2.2 journal whose sidecar carries canonical_meta.aliases_emitted
    rebuilds into a graph with the alias Entity rows + ALIAS_OF edges
    (D-R5-10 + blueprint §8.4)."""
    journals = tmp_path / "runs"
    _write_run(
        journals,
        "2026-05-20T01-00-00Z",
        started_at="2026-05-20T01:00:00",
        schema_version="2.2",
        sources=[("KDB/raw/equities.md", ["apple-inc"])],
        canonical_meta=_canonical_meta_with([
            ("aapl", "apple-inc", "ledger"),
        ]),
    )
    result = rebuild(
        graph_dir=graph_dir, adapter=ObsidianRunsAdapter(),
        journals_dir=journals, confirm=False,
    )
    assert result.replayed == 1
    assert result.failed == 0
    with GraphDB(graph_dir) as gdb:
        canonical = gdb.get_entity("apple-inc")
        alias = gdb.get_entity("aapl")
        stats = gdb.stats()
    assert canonical is not None and canonical.canonical_id is None
    assert alias is not None and alias.canonical_id == "apple-inc"
    assert stats["alias_of"] == 1


def test_rebuild_pre_74_journal_leaves_no_alias_state(graph_dir, tmp_path):
    """A v2.0 journal (pre-#74, no canonical_meta) rebuilds with every
    entity at canonical_id IS NULL and zero ALIAS_OF edges. Back-compat
    for the existing #63 corpus per blueprint §8.3."""
    journals = tmp_path / "runs"
    _write_run(
        journals,
        "2026-04-10T00-00-00Z",
        started_at="2026-04-10T00:00:00",
        schema_version="2.0",
        sources=[("KDB/raw/paper.md", ["alpha", "beta"])],
        # canonical_meta intentionally None — pre-#74 shape
    )
    result = rebuild(
        graph_dir=graph_dir, adapter=ObsidianRunsAdapter(),
        journals_dir=journals, confirm=False,
    )
    assert result.replayed == 1
    with GraphDB(graph_dir) as gdb:
        alpha = gdb.get_entity("alpha")
        beta = gdb.get_entity("beta")
        stats = gdb.stats()
    assert alpha.canonical_id is None
    assert beta.canonical_id is None
    assert stats["alias_of"] == 0


def test_rebuild_mixed_pre_74_and_post_74_journal_sequence(graph_dir, tmp_path):
    """The realistic upgrade scenario: a pre-#74 v2.0 journal followed by
    a post-#74 v2.2 journal that introduces aliases. The pre-#74 entity
    remains canonical; the post-#74 alias state attaches correctly.
    Verify by chronological replay order (#74.7 must not regress
    chronological semantics)."""
    journals = tmp_path / "runs"
    # Pre-#74 journal — establishes apple-inc as a canonical
    _write_run(
        journals,
        "2026-04-10T00-00-00Z",
        started_at="2026-04-10T00:00:00",
        schema_version="2.0",
        sources=[("KDB/raw/equities.md", ["apple-inc"])],
    )
    # Post-#74 journal — adds the aapl alias for the same canonical.
    # The compile_result includes apple-inc in pages[] (because Stage 6
    # merged the alias page intent into the canonical), so the alias
    # Entity gets created with canonical_id pointing at apple-inc.
    _write_run(
        journals,
        "2026-05-20T01-00-00Z",
        started_at="2026-05-20T01:00:00",
        schema_version="2.2",
        sources=[("KDB/raw/equities.md", ["apple-inc"])],
        canonical_meta=_canonical_meta_with([
            ("aapl", "apple-inc", "ledger"),
        ]),
    )
    result = rebuild(
        graph_dir=graph_dir, adapter=ObsidianRunsAdapter(),
        journals_dir=journals, confirm=False,
    )
    assert result.replayed == 2
    with GraphDB(graph_dir) as gdb:
        canonical = gdb.get_entity("apple-inc")
        alias = gdb.get_entity("aapl")
        stats = gdb.stats()
    # Canonical survives through both journals — first_run_id pins the
    # pre-#74 chronology, last_run_id reflects the most recent touch.
    assert canonical is not None and canonical.canonical_id is None
    assert canonical.first_run_id == "2026-04-10T00-00-00Z"
    assert canonical.last_run_id == "2026-05-20T01-00-00Z"
    # Alias attached by the second journal
    assert alias is not None and alias.canonical_id == "apple-inc"
    assert alias.first_run_id == "2026-05-20T01-00-00Z"
    assert stats["alias_of"] == 1
