"""#143 — feeder conversion journal tests."""
from ingestion.feeder.journal import (
    append_journal, load_journal, seen_message_ids, seen_urls)


def test_load_missing_returns_empty(tmp_path):
    assert load_journal(tmp_path / "gmail.jsonl") == []


def test_append_then_load_roundtrip(tmp_path):
    p = tmp_path / "gmail.jsonl"
    append_journal(p, {"message_id": "m1", "source_url": "https://a.substack.com/p/x",
                       "filename": "x.md", "outcome": "converted"})
    append_journal(p, {"message_id": "m2", "source_url": None, "filename": None,
                       "outcome": "dedup", "dedup_of": "x.md"})
    records = load_journal(p)
    assert len(records) == 2
    assert records[0]["message_id"] == "m1"
    assert records[1]["dedup_of"] == "x.md"


def test_append_preserves_prior_lines(tmp_path):
    p = tmp_path / "gmail.jsonl"
    append_journal(p, {"message_id": "m1"})
    append_journal(p, {"message_id": "m2"})
    assert [r["message_id"] for r in load_journal(p)] == ["m1", "m2"]


def test_seen_message_ids(tmp_path):
    records = [{"message_id": "m1"}, {"message_id": "m2"}]
    assert seen_message_ids(records) == {"m1", "m2"}


def test_seen_urls_skips_incomplete_records():
    records = [
        {"source_url": "https://a.substack.com/p/x", "filename": "x.md"},
        {"source_url": None, "filename": None},
        {"source_url": "https://a.substack.com/p/y"},
    ]
    assert seen_urls(records) == {"https://a.substack.com/p/x": "x.md"}
