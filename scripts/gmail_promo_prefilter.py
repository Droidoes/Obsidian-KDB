#!/usr/bin/env python3
"""ONE-OFF (2026-08-15, #143 follow-up): promo pre-filter for the gmail-substack raw corpus.

Scans KDB/raw/joseph-ft-public-gmail/*.md and classifies each file as
promo (paywalled teaser / subscribe-to-read-more) or article, using a
deterministic marker battery. Default mode is REPORT-ONLY (no writes) so
the marker logic can be tuned iteratively with Joseph via bucket samples.

    python scripts/gmail_promo_prefilter.py                 # report
    python scripts/gmail_promo_prefilter.py --sample 20     # more samples
    python scripts/gmail_promo_prefilter.py --apply         # move promos -> _promo/

When the markers stabilize, the same battery is ported into
ingestion/feeder (kdb-gmail-fetch) so future promo emails are journaled as
`promo` and label-moved without writing an md source.

Buckets:
  STRONG        — definite paywall/promo signals -> promo
  TRANSACTIONAL — account/notification mails -> promo (reported separately)
  COMPUTED #152 — link_dense_teaser (body) + 6 title patterns -> promo
  WATCH         — reported for tuning, NOT classified (footer CTAs etc.)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path

RAW_DIR = Path(
    "/mnt/c/Users/fangq/Documents/Obsidian Vault/KDB/raw/joseph-ft-public-gmail"
)
PROMO_DIR = RAW_DIR / "_promo"
MOVELOG = PROMO_DIR / "_movelog.jsonl"


def _rx(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE)


# (name, pattern) — case-insensitive substring/regex
STRONG: list[tuple[str, re.Pattern]] = [
    ("paywall_checkout_link", _rx(r"utm_source=paywall")),
    ("unlock_offer", _rx(r"launch_post_unlock_offer=true")),
    ("claim_free_post", _rx(r"Claim my free post")),
    ("free_preview", _rx(r"free preview")),
    ("subscriber_only_block", _rx(r"Subscriber-only posts")),
    ("get_full_access", _rx(r"Get full access")),
    ("paid_subscribers_only", _rx(r"This post is for paid subscribers")),
    # free-but-truncated: "[Continue reading( for free)](https://substack.com/redirect/...)"
    # mid-body jump link; benign footer/app-button and prose mentions don't match
    ("truncated_continue_reading", _rx(
        r"\[Continue reading(?: for free)?\]\(https://substack\.com/redirect/")),
    # truncated with ellipsis cue: "… [Read more](https://substack.com/redirect/...)"
    # (bare [Read more] without … is the AI-news roundup per-item format — not truncation)
    ("truncated_read_more", _rx(
        r"(?:…|\.{3})\s*\[Read more\]\(https://substack\.com/redirect/")),
]

TRANSACTIONAL: list[tuple[str, re.Pattern]] = [
    ("confirm_email", _rx(r"Confirm your email")),
    ("verify_email", _rx(r"Verify your email")),
    ("welcome_substack", _rx(r"Welcome to Substack")),
]

# #152 battery B — title-scoped (frontmatter `title:` line), case-insensitive
TITLE_MARKERS: list[tuple[str, re.Pattern]] = [
    ("title_live_video", _rx(r"^(live video with|🗓️.*going live|watch (it )?live)")),
    ("title_new_thread", _rx(r"^💬?\s*new thread from")),
    ("title_welcome", _rx(r"^(welcome[ ! to]|you'?re on the list)")),
    ("title_promo_offer", _rx(
        r"(special offer|% off|ends tonight|closes at midnight"
        r"|best (time|week) to (join|subscribe)|final hours)")),
    ("title_portfolio_update", _rx(r"^📈\s*live portfolio update")),
    ("title_new_follower", _rx(r"^new follower on substack")),
]

# #152 battery A — link footers outweigh the prose (video/promo teasers);
# measured against 150 human labels: 40/71 noise caught, 0 false positives
_URL_RX = re.compile(r"https?://[^\s)\]]+")
COMPUTED_NAMES = ["link_dense_teaser"] + [n for n, _ in TITLE_MARKERS]

_FM_RX = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
_FM_TITLE_RX = re.compile(r"^title:\s*(.+)$", re.MULTILINE)


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (title, body) — leading --- block excluded from the body."""
    m = _FM_RX.match(text)
    if not m:
        return None, text
    t = _FM_TITLE_RX.search(m.group(0))
    title = t.group(1).strip().strip('"').strip("'") if t else None
    return title, text[m.end():]


def computed_markers(body: str, title: str | None) -> list[str]:
    """#152 batteries: link_dense_teaser (body) + title patterns (title)."""
    hits: list[str] = []
    url_chars = sum(len(m.group()) for m in _URL_RX.finditer(body))
    if url_chars > len(body) - url_chars and len(body.split()) < 800:
        hits.append("link_dense_teaser")
    if title:
        hits += [name for name, rx in TITLE_MARKERS if rx.search(title)]
    return hits

WATCH: list[tuple[str, re.Pattern]] = [
    ("upgrade_to_paid_anywhere", _rx(r"Upgrade to paid")),
    ("pledge", _rx(r"pledge")),
    ("subscribe_now", _rx(r"Subscribe now")),
    ("become_paid_subscriber", _rx(r"Become a paid subscriber")),
    ("continue_reading", _rx(r"Continue reading")),
]


def classify(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (strong_hits, transactional_hits, watch_hits, computed_hits).

    Computed hits (#152 batteries A+B) are classified as promo alongside
    STRONG/TRANSACTIONAL; battery A runs on the body only (frontmatter
    excluded), battery B on the frontmatter title only."""
    strong = [name for name, rx in STRONG if rx.search(text)]
    txn = [name for name, rx in TRANSACTIONAL if rx.search(text)]
    watch = [name for name, rx in WATCH if rx.search(text)]
    title, body = split_frontmatter(text)
    computed = computed_markers(body, title)
    return strong, txn, watch, computed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", type=int, default=10,
                    help="random samples printed per bucket (default 10)")
    ap.add_argument("--apply", action="store_true",
                    help="move promo files into _promo/ (default: report only)")
    ap.add_argument("--seed", type=int, default=42, help="sample RNG seed")
    args = ap.parse_args()

    files = sorted(p for p in RAW_DIR.glob("*.md") if p.is_file())
    if not files:
        print(f"no .md files under {RAW_DIR}", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    marker_counts: dict[str, int] = {}
    promo: list[tuple[Path, list[str]]] = []      # (path, matched markers)
    articles: list[Path] = []
    article_watch: dict[Path, list[str]] = {}     # watch hits on non-promo files

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"WARN unreadable: {p.name}: {e}", file=sys.stderr)
            continue
        strong, txn, watch, computed = classify(text)
        for name in strong + txn + watch + computed:
            marker_counts[name] = marker_counts.get(name, 0) + 1
        hits = strong + txn + computed
        if hits:
            promo.append((p, hits))
        else:
            articles.append(p)
            if watch:
                article_watch[p] = watch

    # ---- report ----
    def _sample(bucket: list, n: int) -> list:
        return rng.sample(bucket, min(n, len(bucket)))

    print(f"corpus: {len(files)} files  (promo {len(promo)} = "
          f"{len(promo) / len(files):.1%} · article {len(articles)} = "
          f"{len(articles) / len(files):.1%})")
    print("\nper-marker hit counts:")
    for group, label in ((STRONG, "STRONG"),
                         (TRANSACTIONAL, "TRANSACTIONAL"),
                         (WATCH, "WATCH (not classified)")):
        print(f"  [{label}]")
        for name, _ in group:
            print(f"    {marker_counts.get(name, 0):>6}  {name}")
    print("  [COMPUTED #152 (classified as promo)]")
    for name in COMPUTED_NAMES:
        print(f"    {marker_counts.get(name, 0):>6}  {name}")

    # watchlist cross-tab: 'Upgrade to paid' files with NO strong/txn marker
    upgrade_only = [p.name for p, w in article_watch.items()
                    if "upgrade_to_paid_anywhere" in w]
    print(f"\nwatchlist: 'Upgrade to paid' but NOT classified promo: "
          f"{len(upgrade_only)} (eyeball for misses)")
    for name in _sample(upgrade_only, min(args.sample, 5)):
        print(f"    {name}")

    print(f"\n--- sample PROMO ({args.sample}) ---")
    for p, hits in _sample(promo, args.sample):
        print(f"  {p.stat().st_size:>7}  {p.name}  [{', '.join(hits)}]")
    print(f"\n--- sample ARTICLE ({args.sample}) ---")
    for p in _sample(articles, args.sample):
        print(f"  {p.stat().st_size:>7}  {p.name}")

    if not args.apply:
        print("\n(report only — rerun with --apply to move promos into _promo/)")
        return 0

    # ---- apply ----
    PROMO_DIR.mkdir(exist_ok=True)
    moved = 0
    with MOVELOG.open("a", encoding="utf-8") as log:
        for p, hits in promo:
            dest = PROMO_DIR / p.name
            if dest.exists():
                stem, suffix = p.stem, p.suffix
                i = 2
                while dest.exists():
                    dest = PROMO_DIR / f"{stem}--{i}{suffix}"
                    i += 1
            shutil.move(str(p), str(dest))
            log.write(json.dumps({
                "file": p.name, "dest": dest.name, "markers": hits,
            }) + "\n")
            moved += 1
    print(f"\nmoved {moved} files -> {PROMO_DIR}")
    print(f"movelog: {MOVELOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
