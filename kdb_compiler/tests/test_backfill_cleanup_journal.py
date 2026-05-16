"""Tests for the one-shot #68 cleanup-journal backfill (pure functions)."""
from __future__ import annotations

from scripts.backfill_cleanup_journal import (
    compute_retracted_slugs,
    started_at_from_run_id,
)


def test_compute_retracted_slugs_excludes_slugs_still_in_manifest():
    reaped = [
        {"slug": "gone", "page_id": "KDB/wiki/concepts/gone.md", "page_type": "concept"},
        {"slug": "kept", "page_id": "KDB/wiki/articles/kept.md", "page_type": "article"},
    ]
    # 'kept' still has a live page in the manifest; 'gone' does not.
    manifest = {"pages": {"KDB/wiki/articles/kept.md": {"slug": "kept"}}}
    assert compute_retracted_slugs(reaped, manifest) == ["gone"]


def test_compute_retracted_slugs_all_removed():
    reaped = [
        {"slug": "a", "page_id": "p1", "page_type": "concept"},
        {"slug": "b", "page_id": "p2", "page_type": "concept"},
    ]
    manifest = {"pages": {}}
    assert compute_retracted_slugs(reaped, manifest) == ["a", "b"]


def test_started_at_from_run_id_attaches_local_offset():
    out = started_at_from_run_id("clean-orphans-2026-05-16T10-16-00")
    # naive timestamp stem -> local-ISO-with-offset (date + time preserved)
    assert out.startswith("2026-05-16T10:16:00")
    assert ("+" in out[19:]) or ("-" in out[19:])  # an offset is present
