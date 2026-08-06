"""Tests for `kdb-clean` — the KDB maintenance CLI (orphans mode retired in #130).

The `orphans` mode is RETIRED (#130 — deprecated page lifecycle): the
orphan_candidate status no longer exists. Model-dropped pages are marked
`deprecated` in place (graph + frontmatter at finalize), and pages of a
deleted source are erased at reconcile time — there is nothing to reap. The
command now prints a retirement notice and exits 0; that notice is covered
here.

The legacy `reap_orphans()` / `build_cleanup_artifacts()` helpers were deleted
in #133 (their only consumers — the fired one-shot backfill script and
replay-era fixture math — are gone). Historical `cleanup` journals remain
replayable through `kdb_graph.intake.apply_cleanup`; that path is covered in
`kdb_graph/tests/test_rebuilder.py`.
"""
from __future__ import annotations

import pytest

from tools.cleanup import main


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
