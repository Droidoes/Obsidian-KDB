import json

import pytest

from kdb_fts import ledger, review
from kdb_fts.tests.test_gate import _seed_articles


def _gate_all(conn, tmp_path):
    """Give every seeded article a verdict without an LLM: 3 topics cycling."""
    topics = ["investment", "finance-econ", "geopolitics",
              "china-econ", "ai-tech", "other"]
    for i, row in enumerate(conn.execute(
            "SELECT article_id FROM articles ORDER BY article_id")):
        ledger.insert_gate_verdict(
            conn, article_id=row[0], run_id="r1", topic=topics[i % 6],
            signal=0.1 * (i % 10), extract_ideas=(i % 6 == 0),
            extract_lessons=False, exploration=False, confidence=0.5,
            rationale="t", model="m", prompt_version="gate_v1",
            input_tokens=1, output_tokens=1)


def test_freeze_batch_stratified_and_frozen(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=12)
    _gate_all(conn, tmp_path)
    path = review.freeze_batch(conn, tmp_path, batch_id="calibration-p1", n=9)
    batch = json.loads(path.read_text())
    assert batch["batch_id"] == "calibration-p1"
    assert batch["ranker_version"] is None
    assert len(batch["items"]) == 9
    topics = {it["topic"] for it in batch["items"]}
    assert len(topics) >= 4  # stratified across topic guesses, not top-N
    positions = [it["position"] for it in batch["items"]]
    assert positions == list(range(9))
    assert all(it["body"] for it in batch["items"])  # full body for labeling
    # determinism: same inputs → same article_ids
    ids1 = [it["article_id"] for it in batch["items"]]
    path2 = review.freeze_batch(conn, tmp_path, batch_id="calibration-p2", n=9)
    ids2 = [it["article_id"] for it in json.loads(path2.read_text())["items"]]
    assert ids1 == ids2


def test_freeze_refuses_overwrite(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)
    with pytest.raises(FileExistsError):
        review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)


def test_freeze_rejects_unknown_kind(tmp_path):
    conn = ledger.connect(tmp_path)
    with pytest.raises(ValueError):
        review.freeze_batch(conn, tmp_path, batch_id="b1", kind="research")
