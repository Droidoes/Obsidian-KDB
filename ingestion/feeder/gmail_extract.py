"""gmail_extract — Gmail format=full payload -> source-doc parts (#143).

Deterministic: headers, HTML->markdown, canonical Substack URL, content_kind.
No LLM, no network. D2: nothing classificatory beyond best-effort
`content_kind` (article | video | podcast) — pass-1 enrich remains the single
classification authority.
"""
from __future__ import annotations

import base64
import email.utils
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from markdownify import markdownify


@dataclass(frozen=True)
class SourceParts:
    title: str
    author: str
    published_date: str          # ISO YYYY-MM-DD
    source_url: str | None       # canonical Substack post URL, else None
    content_kind: str            # "article" | "video" | "podcast"
    body_markdown: str


_SUBSTACK_POST_RE = re.compile(
    r"https://[a-z0-9][a-z0-9-]*\.substack\.com/p/[a-z0-9][a-z0-9-]*", re.I)
_SUBSTACK_OPEN_RE = re.compile(
    r"https://open\.substack\.com/pub/[a-z0-9][a-z0-9-]*"
    r"/p/[a-z0-9][a-z0-9-]*", re.I)
# Template chrome: real Substack emails hide podcast/video CSS+JS markers in
# <style>/<script> blocks — strip them before marker scans and markdownify.
_CHROME_BLOCK_RE = re.compile(
    r"<style\b[^>]*>.*?</style\s*>|<script\b[^>]*>.*?</script\s*>",
    re.I | re.S)
_FOOTER_MARKERS = ("unsubscribe", "manage your subscription",
                   "you're receiving this", "you are receiving this",
                   "view in browser", "read in browser")
_VIDEO_MARKERS = ("substack.com/api/video", "/api/v1/video",
                  "video-player", "watch on substack")
_PODCAST_MARKERS = ("substack podcast", "audio-player",
                    "listen on substack", "podcast.apple.com",
                    "open.spotify.com/episode")


def _dechrome(html: str) -> str:
    return _CHROME_BLOCK_RE.sub("", html)


def headers_of(payload: dict) -> dict[str, str]:
    raw = payload.get("payload", {}).get("headers", []) or []
    return {h.get("name", "").lower(): h.get("value", "") for h in raw}


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _first_part_text(payload: dict, mime: str) -> str:
    """First non-empty decoded part of `mime`, walking nested mime parts."""
    stack = [payload.get("payload", {})]
    while stack:
        part = stack.pop()
        if part.get("mimeType", "") == mime:
            text = _decode_part(part)
            if text:
                return text
        stack.extend(part.get("parts", []) or [])
    return ""


def text_body(payload: dict) -> str:
    """First text/plain part ('' when absent); walks nested mime parts."""
    return _first_part_text(payload, "text/plain")


def html_body(payload: dict) -> str:
    """Prefer the first text/html part; fall back to text/plain; walk nested
    mime parts."""
    return _first_part_text(payload, "text/html") or text_body(payload)


def canonical_url(html: str, plain: str = "") -> str | None:
    """First substack post URL, tracking query stripped (regexes never match
    the query string). Candidates, first hit wins: (a) old-format
    <pub>.substack.com/p/ link in the HTML; (b) old-format in the text/plain
    part (real newsletters carry the direct URL on the plain part's first
    line); (c) modern open.substack.com/pub/<pub>/p/<slug> redirect in the
    HTML."""
    m = _SUBSTACK_POST_RE.search(html) or _SUBSTACK_POST_RE.search(plain)
    if m:
        return m.group(0)
    m = _SUBSTACK_OPEN_RE.search(html)
    return m.group(0) if m else None


def content_kind(html: str) -> str:
    low = _dechrome(html).lower()
    if any(m in low for m in _VIDEO_MARKERS):
        return "video"
    if any(m in low for m in _PODCAST_MARKERS):
        return "podcast"
    return "article"


def html_to_markdown(html: str) -> str:
    """De-chrome, markdownify, drop images (tracking pixels/button chrome),
    cut footer chrome, collapse blank runs.

    Real Substack bodies markdownify to a handful of very long lines whose
    final line carries the footer links — so instead of dropping whole
    marker lines (which guts the article), truncate at the FIRST footer
    marker: keep everything before it, drop the tail and all following
    lines (footer chrome is terminal)."""
    md = markdownify(_dechrome(html), strip=["img"])
    kept: list[str] = []
    for ln in md.splitlines():
        low = ln.lower()
        cut = min((low.find(m) for m in _FOOTER_MARKERS if m in low),
                  default=None)
        if cut is None:
            kept.append(ln.rstrip())
            continue
        # truncation can land mid-markdown-link ([Unsubscribe](...)), leaving
        # a dangling "[" — that stub is chrome tail, not content
        head = ln[:cut].rstrip().removesuffix("[").rstrip()
        if head:
            kept.append(head)
        break
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def author_of(headers: dict[str, str]) -> str:
    name, addr = email.utils.parseaddr(headers.get("from", ""))
    return name.strip() or addr


def published_date_of(headers: dict[str, str]) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(headers.get("date", ""))
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        return datetime.now(timezone.utc).date().isoformat()
    return dt.date().isoformat()


def title_of(headers: dict[str, str]) -> str:
    return re.sub(r"^(?:(?:re|fwd?):\s*)+", "",
                  headers.get("subject", "").strip(), flags=re.I)


def extract(payload: dict) -> SourceParts:
    headers = headers_of(payload)
    html = html_body(payload)
    return SourceParts(
        title=title_of(headers),
        author=author_of(headers),
        published_date=published_date_of(headers),
        source_url=canonical_url(html, text_body(payload)),
        content_kind=content_kind(html),
        body_markdown=html_to_markdown(html),
    )
