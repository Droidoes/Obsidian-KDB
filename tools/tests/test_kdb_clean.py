"""Tests for `kdb-clean` — the KDB maintenance CLI.

`reap_orphans()` is the pure manifest-mutation core of the `orphans` mode
(internal vocabulary: "reap"; user-facing command: `kdb-clean orphans`). File
archival is a main()-level side effect and is not covered by the unit tests.
"""
from __future__ import annotations

import json

import pytest

from tools.cleanup import build_cleanup_artifacts, main, reap_orphans


def _page(status, slug, *, page_type="concept", outgoing_links=None):
    return {
        "status": status,
        "slug": slug,
        "page_type": page_type,
        "page_id": f"KDB/wiki/{page_type}s/{slug}.md",
        "outgoing_links": list(outgoing_links or []),
    }


def _manifest(pages, orphans=None):
    return {"schema_version": "1.0", "pages": pages, "orphans": orphans or {}}


def _stub_sync(monkeypatch):
    """Stub the graph live-sync so --apply tests don't spin up Kuzu."""
    import types as _types
    monkeypatch.setattr(
        "kdb_graph.adapters.obsidian_runs.ObsidianRunsAdapter.sync_cleanup_run",
        lambda self, retraction, run_id, graph_dir=None: _types.SimpleNamespace(
            entities_deleted=0, run_id=run_id),
    )


def _seed_graph_with_orphan(tmp_path, monkeypatch, slug="gone"):
    """Create an in-memory GraphDB with one orphan_candidate entity."""
    from kdb_graph.graphdb import GraphDB
    from kdb_graph.tests.conftest import (
        make_compile_result, make_compiled_source, make_page,
        make_scan, make_scan_entry,
    )
    graph_dir = tmp_path / "GraphDB-KDB"
    with GraphDB(graph_dir) as gdb:
        pages = [make_page(slug)]
        cr1 = make_compile_result([
            make_compiled_source("KDB/raw/a.md", pages),
        ], run_id="run-1")
        scan1 = make_scan([make_scan_entry("KDB/raw/a.md")])
        gdb.apply_compile_result(cr1, scan1, "run-1")
        # Delete source to orphan the entity
        cr2 = make_compile_result([], run_id="run-2")
        scan2 = make_scan(
            [],
            to_reconcile=[{"type": "DELETED", "path": "KDB/raw/a.md"}],
        )
        gdb.apply_compile_result(cr2, scan2, "run-2")
    monkeypatch.setattr("tools.cleanup.default_graph_path", lambda: graph_dir)


def test_reap_removes_orphan_from_pages_and_orphans():
    pid = "KDB/wiki/concepts/zheng-he-voyages.md"
    manifest = _manifest(
        pages={pid: _page("orphan_candidate", "zheng-he-voyages")},
        orphans={pid: {"reason": "superseded"}},
    )
    report = reap_orphans(manifest)
    assert pid not in manifest["pages"]
    assert pid not in manifest["orphans"]
    assert [r["page_id"] for r in report["reaped"]] == [pid]


def test_reap_leaves_active_pages_untouched():
    active = "KDB/wiki/concepts/capital-light.md"
    orphan = "KDB/wiki/concepts/dead.md"
    manifest = _manifest(
        pages={
            active: _page("active", "capital-light"),
            orphan: _page("orphan_candidate", "dead"),
        },
        orphans={orphan: {"reason": "superseded"}},
    )
    reap_orphans(manifest)
    assert active in manifest["pages"]
    assert orphan not in manifest["pages"]


def test_reap_reports_dead_links_from_active_pages():
    active = "KDB/wiki/concepts/live.md"
    orphan = "KDB/wiki/concepts/gone.md"
    manifest = _manifest(
        pages={
            active: _page("active", "live", outgoing_links=["gone", "still-here"]),
            orphan: _page("orphan_candidate", "gone"),
        },
        orphans={orphan: {}},
    )
    report = reap_orphans(manifest)
    assert report["dead_links"] == [{"from_page": active, "to_slug": "gone"}]


def test_reap_ignores_links_between_two_orphans():
    # an orphan linking to another orphan is not a "dead link" in an active page
    o1 = "KDB/wiki/concepts/o1.md"
    o2 = "KDB/wiki/concepts/o2.md"
    manifest = _manifest(
        pages={
            o1: _page("orphan_candidate", "o1", outgoing_links=["o2"]),
            o2: _page("orphan_candidate", "o2"),
        },
        orphans={o1: {}, o2: {}},
    )
    report = reap_orphans(manifest)
    assert report["dead_links"] == []
    assert manifest["pages"] == {}


def test_reap_link_to_slug_surviving_under_another_type_is_not_dead():
    # 'foo' exists as both an active article and an orphaned concept. A link to
    # 'foo' still resolves after the concept is reaped — not a dead link.
    art = "KDB/wiki/articles/foo.md"
    con = "KDB/wiki/concepts/foo.md"
    linker = "KDB/wiki/concepts/bar.md"
    manifest = _manifest(
        pages={
            art: _page("active", "foo", page_type="article"),
            con: _page("orphan_candidate", "foo", page_type="concept"),
            linker: _page("active", "bar", outgoing_links=["foo"]),
        },
        orphans={con: {}},
    )
    report = reap_orphans(manifest)
    assert report["dead_links"] == []
    assert con not in manifest["pages"]
    assert art in manifest["pages"]


def test_reap_no_orphans_is_noop():
    active = "KDB/wiki/concepts/a.md"
    manifest = _manifest(pages={active: _page("active", "a")})
    report = reap_orphans(manifest)
    assert report["reaped"] == []
    assert report["dead_links"] == []
    assert active in manifest["pages"]


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


def test_main_orphans_dry_run_reads_graph_without_mutating(tmp_path, monkeypatch):
    _seed_graph_with_orphan(tmp_path, monkeypatch, slug="gone")
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)
    rc = main(["orphans", "--vault-root", str(tmp_path)])
    assert rc == 0
    # dry-run is the default — no files written
    assert not list(state.glob("runs/clean-orphans-*"))


def test_main_requires_a_subcommand():
    with pytest.raises(SystemExit):
        main([])


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
    _seed_graph_with_orphan(tmp_path, monkeypatch, slug="gone")
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)
    pid = "KDB/wiki/concepts/gone.md"
    md = tmp_path / pid
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# gone", encoding="utf-8")

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


def test_main_orphans_apply_writes_retraction_before_journal(tmp_path, monkeypatch):
    _stub_sync(monkeypatch)
    _seed_graph_with_orphan(tmp_path, monkeypatch, slug="gone")
    from common import atomic_io
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)
    pid = "KDB/wiki/concepts/gone.md"
    md = tmp_path / pid
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# gone", encoding="utf-8")

    calls: list[str] = []
    real = atomic_io.atomic_write_json

    def spy(path, obj, **kw):
        from pathlib import Path
        calls.append(Path(path).name)
        return real(path, obj, **kw)

    monkeypatch.setattr("tools.cleanup.atomic_io.atomic_write_json", spy)
    main(["orphans", "--vault-root", str(tmp_path), "--apply"])

    journal_idx = next(i for i, n in enumerate(calls)
                       if n.startswith("clean-orphans"))
    assert calls.index("retraction.json") < journal_idx
