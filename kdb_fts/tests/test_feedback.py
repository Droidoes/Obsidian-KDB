import json

import pytest

from kdb_fts import feedback, ledger


def test_append_and_load_roundtrip(tmp_path):
    ledger.connect(tmp_path)  # creates feedback/ subdir
    e1 = feedback.append_event(tmp_path, action="strong", target_type="article",
                               target_id="a1", reason_text="great thesis",
                               batch_id="calibration-p1", position_shown=0,
                               score_shown=0.8)
    e2 = feedback.append_event(tmp_path, action="noise", target_type="article",
                               target_id="a2", batch_id="calibration-p1",
                               position_shown=1)
    assert e1["ts"] and e1["action"] == "strong"
    events = feedback.load_events(tmp_path)
    assert [e["target_id"] for e in events] == ["a1", "a2"]
    assert feedback.load_events(tmp_path, batch_id="calibration-p1") == events
    assert feedback.load_events(tmp_path, batch_id="nope") == []
    # file is real JSONL, one event per line
    lines = (tmp_path / "feedback" / "events.jsonl").read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["action"] == "strong"


def test_closed_sets_enforced(tmp_path):
    ledger.connect(tmp_path)
    with pytest.raises(ValueError):
        feedback.append_event(tmp_path, action="amazing", target_type="article",
                              target_id="a1")
    with pytest.raises(ValueError):
        feedback.append_event(tmp_path, action="strong", target_type="page",
                              target_id="a1")


def test_no_mutation_api_and_append_only_file(tmp_path):
    ledger.connect(tmp_path)
    feedback.append_event(tmp_path, action="weak", target_type="article",
                          target_id="a1")
    assert not hasattr(feedback, "update_event")
    assert not hasattr(feedback, "delete_event")
    first = (tmp_path / "feedback" / "events.jsonl").read_text()
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id="a1")  # same target re-labeled = new event
    second = (tmp_path / "feedback" / "events.jsonl").read_text()
    assert second.startswith(first)  # prior bytes untouched


def test_cli_feedback_appends(tmp_path, capsys):
    from kdb_fts import cli

    rc = cli.main(["feedback", "article", "a9", "interesting",
                   "--reason", "solid", "--state", str(tmp_path)])
    assert rc == 0
    events = feedback.load_events(tmp_path)
    assert len(events) == 1 and events[0]["reason_text"] == "solid"
