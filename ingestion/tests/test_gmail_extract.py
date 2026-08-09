"""#143 — gmail_extract tests (synthetic format=full payloads)."""
import base64

from ingestion.feeder.gmail_extract import (
    author_of, canonical_url, content_kind, extract, headers_of,
    html_body, html_to_markdown, published_date_of, title_of)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _payload(html: str | None, *, plain="plain", subject="Test Post",
             sender="Jane Doe <jane@x.substack.com>",
             date="Sat, 09 Aug 2026 10:30:00 -0400") -> dict:
    parts = [{"mimeType": "text/plain", "body": {"data": _b64(plain)}}]
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    return {
        "id": "m1",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
            ],
            "parts": parts,
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

# Real-shape fixtures (all invented text):
# (i) real bodies markdownify to ONE very long line with the footer chrome
# appended on that same line
LONG_LINE_SENTENCE = "The quarterly compounding thesis restated at length. "
LONG_LINE_HTML = (
    "<div><p>" + LONG_LINE_SENTENCE * 120 +
    '<a href="https://janedoe.substack.com/unsubscribe">Unsubscribe</a>'
    "</p></div>")

# (ii) modern emails link the post via an open.substack.com redirect in the
# HTML; the direct old-format URL sits on the plain part's first line
REDIRECT_HTML = (
    '<div><p>Short note body.</p>'
    '<p><a href="https://open.substack.com/pub/janedoe/p/redirected-post?'
    'utm_source=email&utm_medium=email">Open in Substack</a></p></div>')
REDIRECT_PLAIN = (
    "View this post on the web at "
    "https://janedoe.substack.com/p/redirected-post\n\nShort note body.\n")

# (iii) podcast/video markers hide in <style>/<script> template chrome of
# every email, including plain-text articles
STYLE_CHROME_HTML = (
    "<html><head><style>.audio-player { display: none; }</style>"
    "<script>var player = 'video-player';</script></head>"
    "<body><p>Plain text article body.</p></body></html>")


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


def test_extract_keeps_long_single_line_body():
    """Real shape (i): one ~KB-long line carries the whole article AND the
    trailing unsubscribe chrome — truncation must keep the article head."""
    parts = extract(_payload(LONG_LINE_HTML))
    body = parts.body_markdown
    assert LONG_LINE_SENTENCE.strip() in body
    assert len(body) >= 0.9 * len(LONG_LINE_SENTENCE * 120)
    assert "unsubscribe" not in body.lower()


def test_extract_drops_lines_after_footer_marker():
    """Footer chrome is terminal: the marker line's tail and everything
    below it is dropped."""
    html = ('<p>Body text.</p>'
            '<p><a href="https://janedoe.substack.com/unsubscribe">'
            'Unsubscribe</a></p>'
            '<p>123 Sender St, City legalese.</p><p>More chrome.</p>')
    body = extract(_payload(html)).body_markdown
    assert "Body text." in body
    assert "legalese" not in body and "More chrome" not in body


def test_extract_canonical_url_prefers_plain_direct_url():
    """Real shape (ii): direct old-format URL on the plain part's first line
    beats the open.substack.com redirect in the HTML."""
    parts = extract(_payload(REDIRECT_HTML, plain=REDIRECT_PLAIN))
    assert parts.source_url == "https://janedoe.substack.com/p/redirected-post"


def test_extract_canonical_url_falls_back_to_open_redirect():
    """Without an old-format URL anywhere, the open.substack.com redirect is
    the canonical URL (tracking query never matched)."""
    parts = extract(_payload(REDIRECT_HTML, plain="Short note body.\n"))
    assert parts.source_url == (
        "https://open.substack.com/pub/janedoe/p/redirected-post")


def test_extract_content_kind_ignores_style_script_chrome():
    """Real shape (iii): audio/video markers inside <style>/<script> blocks
    are template chrome, not content."""
    parts = extract(_payload(STYLE_CHROME_HTML))
    assert parts.content_kind == "article"
    assert "Plain text article body." in parts.body_markdown


def test_extract_plain_text_fallback():
    """No text/html part: the text/plain part is the body (and carries the
    canonical URL)."""
    plain = ("Body text https://janedoe.substack.com/p/plain-post\n"
             "more text\nunsubscribe here\n")
    parts = extract(_payload(None, plain=plain))
    assert parts.source_url == "https://janedoe.substack.com/p/plain-post"
    assert "Body text" in parts.body_markdown
    assert "unsubscribe" not in parts.body_markdown.lower()


def test_extract_walks_nested_multipart():
    """multipart/mixed wrapping multipart/alternative: html and plain parts
    are found at depth."""
    p = _payload(ARTICLE_HTML, plain=REDIRECT_PLAIN)
    p["payload"]["mimeType"] = "multipart/mixed"
    p["payload"]["parts"] = [
        {"mimeType": "multipart/alternative", "body": {},
         "parts": [
             {"mimeType": "text/plain", "body": {"data": _b64(REDIRECT_PLAIN)}},
             {"mimeType": "text/html", "body": {"data": _b64(ARTICLE_HTML)}},
         ]},
        {"mimeType": "application/octet-stream",
         "body": {"data": _b64("blob")}},
    ]
    parts = extract(p)
    assert "Thesis body" in parts.body_markdown
    # old-format URL exists in both html and plain; html wins (candidate a)
    assert parts.source_url == "https://janedoe.substack.com/p/my-big-thesis"
