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


def test_freeze_batch_carries_exploration_flag(tmp_path):
    """The frozen JSON is the D13 exposure record — the §7.2 exploration
    mark must survive the freezer (server stamps events from it)."""
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=12)
    _gate_all(conn, tmp_path)
    ledger.mark_exploration(conn, "r1", ["gid0"])
    path = review.freeze_batch(conn, tmp_path, batch_id="calibration-p1", n=9)
    items = {it["article_id"]: it
             for it in json.loads(path.read_text())["items"]}
    assert "gid0" in items  # sorts first in its topic stratum
    assert items["gid0"]["exploration"] is True
    assert all(it["exploration"] is False
               for aid, it in items.items() if aid != "gid0")


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


import http.client
import threading

from kdb_fts import feedback


def _serve(tmp_path, batch_id):
    server = review.make_server(tmp_path, batch_id)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _req(server, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    body = json.dumps(payload) if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_server_roundtrip_event_writeback(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=3)
    conn.close()
    server = _serve(tmp_path, "b1")
    try:
        status, html = _req(server, "GET", "/")
        assert status == 200 and b'id="title"' in html
        status, batch = _req(server, "GET", "/batch")
        assert status == 200
        item = json.loads(batch)["items"][0]
        status, out = _req(server, "POST", "/event",
                           {"article_id": item["article_id"], "action": "strong",
                            "reason_text": "compelling"})
        assert status == 200 and json.loads(out)["ok"] is True
    finally:
        server.shutdown()
    events = feedback.load_events(tmp_path, batch_id="b1")
    assert len(events) == 1
    e = events[0]
    # exposure context stamped server-side from the frozen batch (D13)
    assert e["target_id"] == item["article_id"]
    assert e["position_shown"] == item["position"]
    assert e["score_shown"] == item["signal"]
    assert e["ranker_version"] is None
    assert e["reason_text"] == "compelling"
    assert e["exploration"] is False


def test_server_rejects_unknown_article_and_action(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)
    conn.close()
    server = _serve(tmp_path, "b1")
    try:
        status, _ = _req(server, "POST", "/event",
                         {"article_id": "ghost", "action": "strong"})
        assert status == 400
        batch = json.loads(_req(server, "GET", "/batch")[1])
        status, _ = _req(server, "POST", "/event",
                         {"article_id": batch["items"][0]["article_id"],
                          "action": "bogus"})
        assert status == 400
        assert _req(server, "GET", "/nope")[0] == 404
    finally:
        server.shutdown()
    assert feedback.load_events(tmp_path) == []  # nothing written


def test_server_rejects_negative_content_length(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)
    conn.close()
    server = _serve(tmp_path, "b1")
    try:
        raw = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
        raw.putrequest("POST", "/event")
        raw.putheader("Content-Length", "-5")
        raw.endheaders(b"")
        resp = raw.getresponse()
        assert resp.status == 400
        resp.read()
        raw.close()
    finally:
        server.shutdown()
    assert feedback.load_events(tmp_path) == []  # nothing written
