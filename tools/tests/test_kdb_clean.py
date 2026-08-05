"""Tests for `kdb-clean` — the KDB maintenance CLI (orphans mode retired in #130).

The `orphans` mode is RETIRED (#130 — deprecated page lifecycle): the
orphan_candidate status no longer exists. Model-dropped pages are marked
`deprecated` in place (graph + frontmatter at finalize), and pages of a
deleted source are erased at reconcile time — there is nothing to reap. The
command now prints a retirement notice and exits 0; that notice is covered
here.

`reap_orphans()` / `build_cleanup_artifacts()` are kept as LEGACY helpers for
historical-journal tooling (scripts/backfill_cleanup_journal.py, replay-era
tests); their pure manifest/artifact math is still covered by the unit tests
below.
"""
from __future__ import annotations

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


def test_main_requires_a_subcommand():
    with pytest.raises(SystemExit):
        main([])


def test_main_orphans_prints_retirement_notice(tmp_path, capsys):
    # Retired (#130): prints the notice, exits 0, writes nothing — even with
    # --apply (kept for argparse compat only).
    rc = main(["orphans", "--vault-root", str(tmp_path), "--apply"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RETIRED" in out
    assert not list(tmp_path.rglob("*"))


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
