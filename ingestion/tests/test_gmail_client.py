"""#143 — GmailClient seam tests (fake runner; no network)."""
import json
import subprocess

import pytest

from ingestion.feeder.gmail_client import GmailClient, GmailClientError


def _proc(payload: dict, rc: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gws"], returncode=rc, stdout=json.dumps(payload), stderr=stderr)


def _client(handler) -> GmailClient:
    def runner(cmd, **kwargs):
        return handler(cmd)
    return GmailClient(runner=runner)


def test_resolve_label_ids_maps_names():
    c = _client(lambda cmd: _proc({"labels": [
        {"id": "Label_1", "name": "Substack_raw", "type": "user"},
        {"id": "Label_2", "name": "Substack_ai_processed", "type": "user"}]}))
    assert c.resolve_label_ids() == {
        "Substack_raw": "Label_1", "Substack_ai_processed": "Label_2"}


def test_list_message_ids_paginates_until_no_token():
    pages = iter([
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t2"},
        {"messages": [{"id": "c"}]},
    ])
    c = _client(lambda cmd: _proc(next(pages)))
    assert c.list_message_ids("Substack_raw") == ["a", "b", "c"]


def test_list_message_ids_caps_at_max():
    pages = iter([
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t2"},
        {"messages": [{"id": "c"}]},
    ])
    c = _client(lambda cmd: _proc(next(pages)))
    assert c.list_message_ids("Substack_raw", max_messages=2) == ["a", "b"]


def test_list_message_ids_empty_label():
    c = _client(lambda cmd: _proc({"resultSizeEstimate": 0}))
    assert c.list_message_ids("Substack_raw") == []


def test_get_message_returns_payload():
    c = _client(lambda cmd: _proc({"id": "m1", "payload": {"headers": []}}))
    assert c.get_message("m1")["id"] == "m1"


def test_modify_labels_sends_add_and_remove():
    seen = {}

    def handler(cmd):
        seen["cmd"] = cmd
        return _proc({"id": "m1", "labelIds": ["Label_2"]})

    c = _client(handler)
    c.modify_labels("m1", add=["Label_2"], remove=["Label_1"])
    body = json.loads(seen["cmd"][seen["cmd"].index("--json") + 1])
    assert body == {"addLabelIds": ["Label_2"], "removeLabelIds": ["Label_1"]}


def test_nonzero_rc_raises():
    c = _client(lambda cmd: _proc({}, rc=1, stderr="auth expired"))
    with pytest.raises(GmailClientError, match="auth expired"):
        c.resolve_label_ids()


def test_unparseable_output_raises():
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0,
                                           stdout="not json", stderr="")
    with pytest.raises(GmailClientError, match="unparseable"):
        GmailClient(runner=runner).resolve_label_ids()
