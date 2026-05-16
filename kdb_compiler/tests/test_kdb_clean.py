"""Tests for `kdb-clean` — the KDB maintenance CLI.

`reap_orphans()` is the pure manifest-mutation core of the `orphans` mode
(internal vocabulary: "reap"; user-facing command: `kdb-clean orphans`). File
archival is a main()-level side effect and is not covered by the unit tests.
"""
from __future__ import annotations

import json

import pytest

from kdb_compiler.kdb_clean import main, reap_orphans


def _page(status, slug, *, page_type="concept", outgoing_links=None):
    return {
        "status": status,
        "slug": slug,
        "page_type": page_type,
        "page_id": f"KDB/wiki/{page_type}s/{slug}.md",
        "outgoing_links": list(outgoing_links or []),
    }


def _manifest(pages, orphans=None):
    return {"pages": pages, "orphans": orphans or {}}


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


def test_main_orphans_dry_run_reads_manifest_without_mutating(tmp_path):
    state = tmp_path / "KDB" / "state"
    state.mkdir(parents=True)
    pid = "KDB/wiki/concepts/gone.md"
    manifest = _manifest(
        pages={pid: _page("orphan_candidate", "gone")},
        orphans={pid: {}},
    )
    mpath = state / "manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    rc = main(["orphans", "--vault-root", str(tmp_path)])
    assert rc == 0
    # dry-run is the default — the manifest file must be byte-identical
    assert json.loads(mpath.read_text(encoding="utf-8")) == manifest


def test_main_requires_a_subcommand():
    with pytest.raises(SystemExit):
        main([])
