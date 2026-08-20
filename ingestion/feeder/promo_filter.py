"""promo_filter — deterministic promo/teaser detector for the gmail feeder (#143).

Ported verbatim from the tuned battery in scripts/gmail_promo_prefilter.py
(2026-08-15, 3 report-only iterations over the 4,189-file converted corpus,
Joseph-eyeball-gated). A message whose converted body matches any marker is
journaled `promo` and label-moved to processed WITHOUT writing an md source.

Tuning findings encoded here:
- "Upgrade to paid" alone is NOT a marker — it appears as a footer/header
  funding-pitch CTA on full free articles (would over-match ~65% of corpus).
- Truncation jump links only count in their bracketed redirect form:
  "[Continue reading( for free)](https://substack.com/redirect/…)" and
  "… [Read more](https://substack.com/redirect/…)" (ellipsis cue required —
  bare "[Read more]" is the AI-news-roundup per-item format, not truncation).

#152 additions (measured against 150 human labels):
- Battery A `link_dense_teaser` (body-scoped): url_chars > text_chars AND
  words < 800 — catches video-announcement/promo-teaser emails whose link
  footers outweigh the prose; measured 40/71 noise caught, 0 false positives.
- Battery B (six `title_*` markers) is title-scoped, so body prose mentioning
  "special offer" never matches. Known accepted casualty: one
  interesting-labeled "New thread from Matt Warder" notification vs 150 junk
  thread-notification emails.
"""
from __future__ import annotations

import re


def _rx(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE)


# (name, pattern) — case-insensitive; order is cosmetic
PROMO_MARKERS: list[tuple[str, re.Pattern]] = [
    ("paywall_checkout_link", _rx(r"utm_source=paywall")),
    ("unlock_offer", _rx(r"launch_post_unlock_offer=true")),
    ("claim_free_post", _rx(r"Claim my free post")),
    ("free_preview", _rx(r"free preview")),
    ("subscriber_only_block", _rx(r"Subscriber-only posts")),
    ("get_full_access", _rx(r"Get full access")),
    ("paid_subscribers_only", _rx(r"This post is for paid subscribers")),
    ("truncated_continue_reading", _rx(
        r"\[Continue reading(?: for free)?\]\(https://substack\.com/redirect/")),
    ("truncated_read_more", _rx(
        r"(?:…|\.{3})\s*\[Read more\]\(https://substack\.com/redirect/")),
    ("confirm_email", _rx(r"Confirm your email")),
    ("verify_email", _rx(r"Verify your email")),
    ("welcome_substack", _rx(r"Welcome to Substack")),
]

# #152 battery B — title-scoped, case-insensitive; order is cosmetic
TITLE_PROMO_MARKERS: list[tuple[str, re.Pattern]] = [
    ("title_live_video", _rx(r"^(live video with|🗓️.*going live|watch (it )?live)")),
    ("title_new_thread", _rx(r"^💬?\s*new thread from")),
    ("title_welcome", _rx(r"^(welcome[ ! to]|you'?re on the list)")),
    ("title_promo_offer", _rx(
        r"(special offer|% off|ends tonight|closes at midnight"
        r"|best (time|week) to (join|subscribe)|final hours)")),
    ("title_portfolio_update", _rx(r"^📈\s*live portfolio update")),
    ("title_new_follower", _rx(r"^new follower on substack")),
]

# #152 battery A — link footers outweigh the prose (video/promo teasers)
_URL_RX = re.compile(r"https?://[^\s)\]]+")


def _link_dense_teaser(body_markdown: str) -> bool:
    url_chars = sum(len(m.group()) for m in _URL_RX.finditer(body_markdown))
    text_chars = len(body_markdown) - url_chars
    return url_chars > text_chars and len(body_markdown.split()) < 800


def promo_markers(body_markdown: str, title: str | None = None) -> list[str]:
    """Return the names of all promo markers matching the converted body
    (and title, when given) — empty list = treat as a real source.
    Battery B markers are title-scoped: title=None → they never fire."""
    hits = [name for name, rx in PROMO_MARKERS if rx.search(body_markdown)]
    if _link_dense_teaser(body_markdown):
        hits.append("link_dense_teaser")
    if title:
        hits += [name for name, rx in TITLE_PROMO_MARKERS if rx.search(title)]
    return hits
