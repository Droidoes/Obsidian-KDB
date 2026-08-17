"""CLI smoke: intake → status → search round-trip over the fixture tree."""
from __future__ import annotations

from pathlib import Path

from kdb_fts import cli

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fts_tree"


def test_intake_status_search_roundtrip(tmp_path, capsys):
    state = tmp_path / "fts"
    assert cli.main(["intake", "--raw-root", str(FIXTURE), "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "seen=5" in out and "deleted=0" in out

    assert cli.main(["status", "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "ok: 1" in out and "digest-stub: 1" in out and "media: 1" in out
    assert "short: 1" in out and "bleed: 1" in out

    assert cli.main(["search", "Barrick", "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "g-fixture-001" in out and "Barrick" in out


def test_search_no_hits_exit_0(tmp_path, capsys):
    state = tmp_path / "fts"
    cli.main(["intake", "--raw-root", str(FIXTURE), "--state", str(state)])
    capsys.readouterr()
    assert cli.main(["search", "zzzznope", "--state", str(state)]) == 0
    assert "no hits" in capsys.readouterr().out


def test_status_unknown_model_no_crash(tmp_path, capsys):
    """A verdict left by a model that has since left the active pool must not
    crash status — cost prints as n/a."""
    from kdb_fts import ledger
    from kdb_fts.tests.test_gate import _seed_articles

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=1)
    ledger.insert_gate_verdict(
        conn, article_id="gid0", run_id="r1", topic="investment",
        signal=0.5, extract_ideas=True, extract_lessons=False,
        exploration=False, confidence=0.5, rationale="t", model="ghost-model",
        prompt_version="gate_v1", input_tokens=10, output_tokens=5)
    conn.close()
    assert cli.main(["status", "--state", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "ghost-model" in out and "n/a" in out
