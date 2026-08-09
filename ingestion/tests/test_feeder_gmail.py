"""#143 — feeder fetch() flow tests (fake client; tmp dirs)."""
import base64

import pytest
import yaml

from ingestion.feeder.gmail import DEFAULT_LABEL, fetch
from ingestion.feeder.gmail_client import GmailClientError


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _payload(mid: str, url: str, *, subject: str | None = None) -> dict:
    html = f'<p>Body for {mid} <a href="{url}">web</a></p>'
    return {"id": mid, "payload": {
        "headers": [
            {"name": "Subject", "value": subject or f"Post {mid}"},
            {"name": "From", "value": "Jane Doe <jane@x.substack.com>"},
            {"name": "Date", "value": "Sat, 09 Aug 2026 10:30:00 -0400"},
        ],
        "parts": [{"mimeType": "text/html", "body": {"data": _b64(html)}}],
    }}


class FakeClient:
    def __init__(self, payloads: dict, fail_on: set = ()):  # mid -> payload
        self.payloads = payloads
        self.fail_on = fail_on
        self.moved: list[tuple[str, list, list]] = []

    def resolve_label_ids(self):
        return {DEFAULT_LABEL: "LR", "Substack_ai_processed": "LP"}

    def list_message_ids(self, label, *, max_messages=None):
        ids = list(self.payloads)
        return ids[:max_messages] if max_messages else ids

    def get_message(self, mid):
        if mid in self.fail_on:
            raise GmailClientError(f"boom {mid}")
        return self.payloads[mid]

    def modify_labels(self, mid, *, add, remove):
        self.moved.append((mid, add, remove))


def _run(client, tmp_path, **kwargs):
    return fetch(client=client, raw_dir=tmp_path / "raw",
                 journal_path=tmp_path / "state" / "feeders" / "gmail.jsonl",
                 **kwargs)


def test_converts_writes_source_moves_label_journals(tmp_path):
    c = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x")})
    s = _run(c, tmp_path)
    assert (s.converted, s.failed) == (1, 0)
    files = list((tmp_path / "raw").glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---\n")[1])
    assert fm["gmail_message_id"] == "m1"
    assert fm["source_url"] == "https://a.substack.com/p/x"
    assert fm["feeder"] == "gmail-substack"
    assert fm["content_kind"] == "article"
    assert "domain" not in fm and "source_type" not in fm   # D2
    assert c.moved == [("m1", ["LP"], ["LR"])]
    assert (tmp_path / "state" / "feeders" / "gmail.jsonl").exists()


def test_rerun_skips_journaled_messages(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x")}
    _run(FakeClient(payloads), tmp_path)
    c2 = FakeClient(payloads)
    s = _run(c2, tmp_path)
    assert (s.converted, s.skipped) == (0, 1)
    assert c2.moved == []


def test_dedup_by_canonical_url_no_second_file_but_labels_move(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x"),
                "m2": _payload("m2", "https://a.substack.com/p/x")}
    c = FakeClient(payloads)
    s = _run(c, tmp_path)
    assert (s.converted, s.dedup) == (1, 1)
    assert len(list((tmp_path / "raw").glob("*.md"))) == 1
    assert sorted(m[0] for m in c.moved) == ["m1", "m2"]


def test_per_message_failure_isolated_and_stays_unlabeled(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x"),
                "m2": _payload("m2", "https://a.substack.com/p/y")}
    c = FakeClient(payloads, fail_on={"m2"})
    s = _run(c, tmp_path)
    assert (s.converted, s.failed) == (1, 1)
    assert s.failures[0][0] == "m2"
    assert [m[0] for m in c.moved] == ["m1"]


def test_dry_run_zero_side_effects(tmp_path):
    c = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x")})
    _run(c, tmp_path, dry_run=True)
    assert not (tmp_path / "raw").exists() or not list((tmp_path / "raw").glob("*.md"))
    assert not (tmp_path / "state").exists()
    assert c.moved == []


def test_max_messages_caps(tmp_path):
    payloads = {f"m{i}": _payload(f"m{i}", f"https://a.substack.com/p/{i}")
                for i in range(5)}
    s = _run(FakeClient(payloads), tmp_path, max_messages=2)
    assert s.converted == 2


def test_missing_label_raises(tmp_path):
    class NoLabels(FakeClient):
        def resolve_label_ids(self):
            return {}
    with pytest.raises(GmailClientError, match="label not found"):
        _run(NoLabels({}), tmp_path)


def test_cli_dry_run_smoke(tmp_path, capsys, monkeypatch):
    from ingestion.feeder import gmail as feeder

    class StubClient:
        def resolve_label_ids(self):
            return {DEFAULT_LABEL: "LR", "Substack_ai_processed": "LP"}

        def list_message_ids(self, label, *, max_messages=None):
            return []

        def get_message(self, mid):
            raise AssertionError("no messages expected")

        def modify_labels(self, mid, *, add, remove):
            raise AssertionError("no writes expected")

    monkeypatch.setattr(feeder, "GmailClient", lambda: StubClient())
    rc = feeder.main(["--dry-run", "--raw-dir", str(tmp_path / "raw"),
                      "--journal", str(tmp_path / "j" / "gmail.jsonl")])
    assert rc == 0
    assert "converted 0" in capsys.readouterr().out
