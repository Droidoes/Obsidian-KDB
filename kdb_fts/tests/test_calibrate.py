from kdb_fts import calibrate, feedback, ledger
from kdb_fts.tests.test_gate import _seed_articles
from kdb_fts.tests.test_review import _gate_all


def test_report_confusion_matrix(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=6)
    _gate_all(conn, tmp_path)  # topics cycle: investment, finance-econ, geopolitics, ...
    ids = [r[0] for r in conn.execute(
        "SELECT article_id FROM articles ORDER BY article_id")]
    # gid0 investment, gid1 finance-econ, gid2 geopolitics,
    # gid3 china-econ, gid4 ai-tech, gid5 other
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id=ids[0], batch_id="b1")   # gate+ label+ → tp
    feedback.append_event(tmp_path, action="noise", target_type="article",
                          target_id=ids[1], batch_id="b1")   # gate+ label- → fp
    feedback.append_event(tmp_path, action="interesting", target_type="article",
                          target_id=ids[2], batch_id="b1")   # gate- label+ → fn
    feedback.append_event(tmp_path, action="weak", target_type="article",
                          target_id=ids[3], batch_id="b1")   # gate- label- → tn
    # ids[4], ids[5] unlabeled → excluded from the matrix
    # re-label: ids[3] upgraded → becomes fn
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id=ids[3], batch_id="b1")
    rep = calibrate.report(conn, tmp_path, "b1")
    assert rep["labeled"] == 4
    assert rep["confusion"] == {"tp": 1, "fp": 1, "fn": 2, "tn": 0}
    assert abs(rep["precision"] - 0.5) < 1e-9
    assert abs(rep["recall"] - 1 / 3) < 1e-9
    assert rep["by_topic"]["china-econ"] == {"pos": 1, "neg": 0}


def test_report_empty_batch(tmp_path):
    conn = ledger.connect(tmp_path)
    rep = calibrate.report(conn, tmp_path, "nobody-labeled")
    assert rep["labeled"] == 0 and rep["precision"] is None


def test_signal_clause_rescues_non_relevant_topic(tmp_path):
    """Ratified hybrid rule (2026-08-19): topic outside investment/finance-econ
    with signal >= 0.75 counts gate-positive; just below stays negative."""
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    ids = [r[0] for r in conn.execute(
        "SELECT article_id FROM articles ORDER BY article_id")]
    for aid, sig in ((ids[0], 0.8), (ids[1], 0.74)):
        ledger.insert_gate_verdict(
            conn, article_id=aid, run_id="r1", topic="geopolitics",
            signal=sig, extract_ideas=False, extract_lessons=False,
            exploration=False, confidence=0.5, rationale="t", model="m",
            prompt_version="gate_v1", input_tokens=1, output_tokens=1)
    for aid in ids:
        feedback.append_event(tmp_path, action="strong", target_type="article",
                              target_id=aid, batch_id="b1")
    rep = calibrate.report(conn, tmp_path, "b1")
    assert rep["confusion"] == {"tp": 1, "fp": 0, "fn": 1, "tn": 0}


def test_cli_calibration(tmp_path, capsys):
    from kdb_fts import cli

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    _gate_all(conn, tmp_path)
    conn.close()
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id="gid0", batch_id="calibration-p1")
    rc = cli.main(["calibration", "--batch", "calibration-p1", "--state", str(tmp_path)])
    assert rc == 0
    assert "precision" in capsys.readouterr().out


def test_cli_calibration_precision_zero_recall_none(tmp_path, capsys):
    """Regression: tp=0,fn=0,fp>0 → precision=0.0 but recall=None; the CLI
    must not crash formatting a None metric."""
    from kdb_fts import cli

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=1)
    ledger.insert_gate_verdict(
        conn, article_id="gid0", run_id="r1", topic="investment",
        signal=0.9, extract_ideas=True, extract_lessons=False,
        exploration=False, confidence=0.5, rationale="t", model="m",
        prompt_version="gate_v1", input_tokens=1, output_tokens=1)
    conn.close()
    feedback.append_event(tmp_path, action="noise", target_type="article",
                          target_id="gid0", batch_id="b1")  # gate+ label- → fp
    rc = cli.main(["calibration", "--batch", "b1", "--state", str(tmp_path)])
    assert rc == 0
    assert "precision=0.000" in capsys.readouterr().out
