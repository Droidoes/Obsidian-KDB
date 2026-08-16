"""Intake: classification precedence, identity, idempotency over the fixture tree."""
from __future__ import annotations

from pathlib import Path

from kdb_fts import intake, ledger

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fts_tree"


def _by_id(recs):
    return {r.article_id: r for r in recs}


def test_scan_classifies_each_fixture():
    recs = _by_id(intake.scan_tree(FIXTURE))
    assert "g-fixture-005" not in recs  # _promo/ excluded from the walk entirely
    assert recs["g-fixture-001"].cleanliness == "ok"
    assert recs["g-fixture-002"].cleanliness == "digest-stub"
    assert recs["g-fixture-003"].cleanliness == "media"
    assert recs["g-fixture-004"].cleanliness == "short"
    assert recs["g-fixture-001"].word_count == 52  # 27 words + 25 words, two paragraphs


def test_bleed_file_gets_repaired_view():
    recs = intake.scan_tree(FIXTURE)
    bleeds = [r for r in recs if r.cleanliness == "bleed"]
    assert len(bleeds) == 1
    assert bleeds[0].article_id.startswith("sha256:")  # no parseable gmail id → hash identity
    assert bleeds[0].paragraphs == ["Actual body text lives after the broken fence."]


def test_run_intake_is_idempotent(tmp_path):
    conn = ledger.connect(tmp_path / "fts")
    stats1 = intake.run_intake(conn, FIXTURE, "run1")
    stats2 = intake.run_intake(conn, FIXTURE, "run2")
    assert stats1["seen"] == 5  # 5 fixture files outside _promo/
    assert stats2["seen"] == 5 and stats2["deleted"] == 0
    # paragraphs are NOT rewritten on unchanged content:
    n_paras = conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]
    intake.run_intake(conn, FIXTURE, "run3")
    assert conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0] == n_paras


def test_identity_survives_move(tmp_path, monkeypatch):
    conn = ledger.connect(tmp_path / "fts")
    intake.run_intake(conn, FIXTURE, "run1")
    moved = tmp_path / "tree2"
    import shutil
    shutil.copytree(FIXTURE, moved)
    (moved / "plain-article.md").rename(moved / "renamed-article.md")
    intake.run_intake(conn, moved, "run2")
    row = conn.execute(
        "SELECT path FROM articles WHERE article_id = 'g-fixture-001'"
    ).fetchone()
    assert row[0].endswith("renamed-article.md")
