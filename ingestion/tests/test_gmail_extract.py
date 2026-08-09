"""#143 — gmail_extract tests (synthetic format=full payloads)."""
import base64

from ingestion.feeder.gmail_extract import (
    author_of, canonical_url, content_kind, extract, headers_of,
    html_body, html_to_markdown, published_date_of, title_of)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _payload(html: str, *, subject="Test Post", sender="Jane Doe <jane@x.substack.com>",
             date="Sat, 09 Aug 2026 10:30:00 -0400") -> dict:
    return {
        "id": "m1",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("plain")}},
                {"mimeType": "text/html", "body": {"data": _b64(html)}},
            ],
        },
    }


ARTICLE_HTML = (
    '<div><p>Hello <a href="https://janedoe.substack.com/p/my-big-thesis?'
    'utm_source=email&token=abc">read on the web</a></p>'
    '<p>Thesis body.</p>'
    '<p><a href="https://janedoe.substack.com/unsubscribe">Unsubscribe</a></p>'
    '<img src="https://track.example.com/pixel.gif"></div>')

VIDEO_HTML = (
    '<div><p>New episode</p>'
    '<a href="https://janedoe.substack.com/p/market-video">'
    '<img src="https://substackcdn.com/api/video/thumb.jpg"></a>'
    '<span>Watch on Substack</span></div>')


def test_headers_of_lowercases_names():
    h = headers_of(_payload(ARTICLE_HTML))
    assert h["subject"] == "Test Post" and "from" in h and "date" in h


def test_html_body_prefers_html_part():
    assert "Thesis body" in html_body(_payload(ARTICLE_HTML))


def test_canonical_url_strips_tracking():
    assert canonical_url(ARTICLE_HTML) == "https://janedoe.substack.com/p/my-big-thesis"


def test_canonical_url_none_when_absent():
    assert canonical_url("<p>no links here</p>") is None


def test_content_kind_video_detected():
    assert content_kind(VIDEO_HTML) == "video"


def test_content_kind_article_default():
    assert content_kind(ARTICLE_HTML) == "article"


def test_html_to_markdown_strips_footer_and_images():
    md = html_to_markdown(ARTICLE_HTML)
    assert "Thesis body" in md
    assert "unsubscribe" not in md.lower()
    assert "pixel.gif" not in md


def test_author_prefers_display_name():
    assert author_of(headers_of(_payload(ARTICLE_HTML))) == "Jane Doe"


def test_published_date_iso():
    assert published_date_of(headers_of(_payload(ARTICLE_HTML))) == "2026-08-09"


def test_title_strips_re_fwd():
    h = headers_of(_payload(ARTICLE_HTML, subject="Fwd: Re: Real Title"))
    assert title_of(h) == "Real Title"


def test_extract_full_article():
    parts = extract(_payload(ARTICLE_HTML))
    assert parts.title == "Test Post"
    assert parts.author == "Jane Doe"
    assert parts.published_date == "2026-08-09"
    assert parts.source_url == "https://janedoe.substack.com/p/my-big-thesis"
    assert parts.content_kind == "article"
    assert "Thesis body" in parts.body_markdown
