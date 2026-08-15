"""#143 — promo-filter unit tests + fetch() promo-path integration.

The battery is ported from scripts/gmail_promo_prefilter.py (tuned 2026-08-15
over the 4,189-file corpus): paywalled teasers, truncated-free excerpts, and
transactional mails are promo; footer CTAs ("Upgrade to paid") and bare
per-item "[Read more]" roundup links are NOT.
"""
import base64

import pytest

from ingestion.feeder.promo_filter import promo_markers


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


# ---------- unit: marker battery ----------

@pytest.mark.parametrize("body,marker", [
    ('<a href="https://x.substack.com/p/a?utm_source=paywall">up</a>',
     "paywall_checkout_link"),
    ('<a href="https://substack.com/redirect/x?launch_post_unlock_offer=true">c</a>',
     "unlock_offer"),
    ("Claim my free post", "claim_free_post"),
    ("You are reading a free preview of this post", "free_preview"),
    ("Subscriber-only posts and full archive", "subscriber_only_block"),
    ("Get full access to the archive", "get_full_access"),
    ("This post is for paid subscribers", "paid_subscribers_only"),
    ('[Continue reading](https://substack.com/redirect/abc)',
     "truncated_continue_reading"),
    ('[Continue reading for free](https://substack.com/redirect/abc)',
     "truncated_continue_reading"),
    ('the argument falls apart…\n\n[Read more](https://substack.com/redirect/abc)',
     "truncated_read_more"),
    ("Confirm your email on Substack", "confirm_email"),
])
def test_promo_markers_hit(body, marker):
    assert marker in promo_markers(body)


@pytest.mark.parametrize("body", [
    # footer CTA on a full free article — NOT promo (tuning finding)
    'A complete essay. [Upgrade to paid](https://x.substack.com/subscribe)',
    # bare per-item "[Read more]" without ellipsis — AI-news roundup format
    ('Story summary ends here. '
     '[Read more](https://substack.com/redirect/abc)'),
    # ordinary substantive body
    "This essay argues that liquidity drives the cycle, with data.",
])
def test_benign_bodies_not_flagged(body):
    assert promo_markers(body) == []


# ---------- integration: fetch() promo path ----------

def _payload(mid: str, url: str, html: str, *, subject: str | None = None) -> dict:
    return {"id": mid, "payload": {
        "headers": [
            {"name": "Subject", "value": subject or f"Post {mid}"},
            {"name": "From", "value": "Jane Doe <jane@x.substack.com>"},
            {"name": "Date", "value": "Sat, 09 Aug 2026 10:30:00 -0400"},
        ],
        "parts": [{"mimeType": "text/html", "body": {"data": _b64(html)}}],
    }}


class FakeClient:  # mirrors test_feeder_gmail.FakeClient (kept local: no
    def __init__(self, payloads: dict, fail_on: set = ()):  # cross-test imports)
        self.payloads = payloads
        self.fail_on = fail_on
        self.moved: list[tuple[str, list, list]] = []

    def resolve_label_ids(self):
        return {"Substack_raw": "LR", "Substack_ai_processed": "LP"}

    def list_message_ids(self, label, *, max_messages=None):
        ids = list(self.payloads)
        return ids[:max_messages] if max_messages else ids

    def get_message(self, mid):
        return self.payloads[mid]

    def modify_labels(self, mid, *, add, remove):
        self.moved.append((mid, add, remove))


def _run(client, tmp_path, **kwargs):
    from ingestion.feeder.gmail import fetch
    return fetch(client=client, raw_dir=tmp_path / "raw",
                 journal_path=tmp_path / "state" / "feeders" / "gmail.jsonl",
                 **kwargs)


PAYWALLED_HTML = (
    '<p>A tempting first paragraph about book value...</p>'
    '<a href="https://x.substack.com/p/a?utm_source=paywall">Upgrade to paid</a>'
)


def test_promo_message_no_file_but_label_moves_and_journals(tmp_path):
    from ingestion.feeder.journal import load_journal

    c = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x",
                                   PAYWALLED_HTML)})
    s = _run(c, tmp_path)
    assert (s.promo, s.converted, s.failed) == (1, 0, 0)
    assert not list((tmp_path / "raw").glob("*.md"))      # no md written
    assert c.moved == [("m1", ["LP"], ["LR"])]            # still drains queue
    records = load_journal(tmp_path / "state" / "feeders" / "gmail.jsonl")
    assert records[0]["outcome"] == "promo"
    assert records[0]["filename"] is None
    assert "paywall_checkout_link" in records[0]["markers"]


def test_promo_journaled_messages_skip_on_rerun(tmp_path):
    payloads = {"m1": _payload("m1", "https://a.substack.com/p/x",
                               PAYWALLED_HTML)}
    _run(FakeClient(payloads), tmp_path)
    c2 = FakeClient(payloads)
    s2 = _run(c2, tmp_path)
    assert (s2.promo, s2.skipped) == (0, 1)
    assert c2.moved == []


def test_promo_does_not_block_later_clean_version_of_same_url(tmp_path):
    """A promo teaser must not poison URL dedup: a later NON-promo email with
    the same canonical URL still converts."""
    _run(FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x",
                                    PAYWALLED_HTML)}), tmp_path)
    clean_html = ('<p>The full article body with real substance and no '
                  'paywall markers at all.</p>')
    c2 = FakeClient({"m2": _payload("m2", "https://a.substack.com/p/x",
                                    clean_html)})
    s2 = _run(c2, tmp_path)
    assert (s2.converted, s2.dedup) == (1, 0)


def test_dry_run_tags_promo(tmp_path, capsys):
    import sys
    # fetch()'s `out` default binds sys.stdout at import time (before capsys),
    # so pass the current stream explicitly to test the printed tag.
    c = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x",
                                   PAYWALLED_HTML)})
    s = _run(c, tmp_path, dry_run=True, out=sys.stdout)
    assert (s.promo, s.converted) == (0, 0)   # dry-run counts nothing
    assert "[dry-run] promo:" in capsys.readouterr().out
    assert not (tmp_path / "state").exists()
    assert c.moved == []


def test_cli_summary_line_includes_promo(tmp_path, capsys, monkeypatch):
    from ingestion.feeder import gmail as feeder

    client = FakeClient({"m1": _payload("m1", "https://a.substack.com/p/x",
                                        PAYWALLED_HTML)})
    monkeypatch.setattr(feeder, "GmailClient", lambda: client)
    rc = feeder.main(["--raw-dir", str(tmp_path / "raw"),
                      "--journal", str(tmp_path / "j" / "gmail.jsonl")])
    assert rc == 0
    assert "promo 1" in capsys.readouterr().out
