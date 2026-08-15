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


def promo_markers(body_markdown: str) -> list[str]:
    """Return the names of all promo markers matching the converted body
    (empty list = treat as a real source)."""
    return [name for name, rx in PROMO_MARKERS if rx.search(body_markdown)]
