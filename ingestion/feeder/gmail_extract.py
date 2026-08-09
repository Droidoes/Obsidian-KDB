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
_FOOTER_MARKERS = ("unsubscribe", "manage your subscription",
                   "you're receiving this", "you are receiving this",
                   "view in browser", "read in browser")
_VIDEO_MARKERS = ("substack.com/api/video", "/api/v1/video",
                  "video-player", "watch on substack")
_PODCAST_MARKERS = ("substack podcast", "audio-player",
                    "listen on substack", "podcast.apple.com",
                    "open.spotify.com/episode")


def headers_of(payload: dict) -> dict[str, str]:
    raw = payload.get("payload", {}).get("headers", []) or []
    return {h.get("name", "").lower(): h.get("value", "") for h in raw}


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def html_body(payload: dict) -> str:
    """Prefer the first text/html part; fall back to text/plain; walk nested
    mime parts."""
    best_html, best_text = "", ""
    stack = [payload.get("payload", {})]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        if mime == "text/html" and not best_html:
            best_html = _decode_part(part)
        elif mime == "text/plain" and not best_text:
            best_text = _decode_part(part)
        stack.extend(part.get("parts", []) or [])
    return best_html or best_text


def canonical_url(html: str) -> str | None:
    """First substack /p/ link, tracking query stripped (regex never matches
    the query string)."""
    m = _SUBSTACK_POST_RE.search(html)
    return m.group(0) if m else None


def content_kind(html: str) -> str:
    low = html.lower()
    if any(m in low for m in _VIDEO_MARKERS):
        return "video"
    if any(m in low for m in _PODCAST_MARKERS):
        return "podcast"
    return "article"


def html_to_markdown(html: str) -> str:
    """markdownify, drop images (tracking pixels/button chrome), drop footer
    lines, collapse blank runs."""
    md = markdownify(html, strip=["img"])
    kept = [ln.rstrip() for ln in md.splitlines()
            if not any(m in ln.lower() for m in _FOOTER_MARKERS)]
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
        source_url=canonical_url(html),
        content_kind=content_kind(html),
        body_markdown=html_to_markdown(html),
    )
