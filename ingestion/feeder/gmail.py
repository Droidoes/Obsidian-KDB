"""gmail — the gmail-substack feeder: Gmail label -> KDB raw sources (#143).

Flow (spec §3.2): list -> journal-skip -> get -> extract -> promo-filter ->
dedup -> write -> label move -> journal append. Deterministic (D1): no LLM
anywhere. Promo/teaser messages (paywalled or truncated — see
`promo_filter`) are journaled `promo` and label-moved WITHOUT writing an md
source. Per-message failures are isolated: the message stays in the raw
label and lands in the summary, the batch continues.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import yaml

from common.atomic_io import atomic_write_text
from common.paths import kdb_root, slugify

from ingestion.feeder import journal as jrnl
from ingestion.feeder.gmail_client import GmailClient, GmailClientError
from ingestion.feeder.gmail_extract import extract
from ingestion.feeder.promo_filter import promo_markers

DEFAULT_LABEL = "Substack_raw"
PROCESSED_LABEL = "Substack_ai_processed"
RAW_SUBDIR = Path("raw") / "joseph-ft-public-gmail"
JOURNAL_REL = Path("state") / "feeders" / "gmail.jsonl"


@dataclass
class FetchSummary:
    converted: int = 0
    skipped: int = 0
    dedup: int = 0
    promo: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def _render_source(parts, *, message_id: str, ingested_at: str) -> str:
    """D2 frontmatter contract + extracted body."""
    fm = yaml.safe_dump(
        {"title": parts.title,
         "author": parts.author,
         "published_date": parts.published_date,
         "source_url": parts.source_url,
         "gmail_message_id": message_id,
         "content_kind": parts.content_kind,
         "feeder": "gmail-substack",
         "ingested_at": ingested_at},
        sort_keys=False, allow_unicode=True)
    return f"---\n{fm}---\n\n{parts.body_markdown}\n"


def _target_path(raw_dir: Path, title: str, message_id: str) -> Path:
    base = slugify(title)
    path = raw_dir / f"{base}.md"
    if path.exists():
        path = raw_dir / f"{base}-{message_id[:8]}.md"
    return path


def fetch(*, client: GmailClient, raw_dir: Path, journal_path: Path,
          label: str = DEFAULT_LABEL, processed_label: str = PROCESSED_LABEL,
          max_messages: int | None = None, dry_run: bool = False,
          out: TextIO = sys.stdout) -> FetchSummary:
    summary = FetchSummary()
    records = jrnl.load_journal(journal_path)
    seen_ids = jrnl.seen_message_ids(records)
    seen_urls = jrnl.seen_urls(records)

    label_ids = client.resolve_label_ids()
    for name in (label, processed_label):
        if name not in label_ids:
            raise GmailClientError(f"Gmail label not found: {name!r}")

    for mid in client.list_message_ids(label, max_messages=max_messages):
        if mid in seen_ids:
            summary.skipped += 1
            continue
        try:
            parts = extract(client.get_message(mid))
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            markers = promo_markers(parts.body_markdown, title=parts.title)
            # promo wins over dedup (more informative outcome) and never
            # populates seen_urls — a teaser must not block a later clean
            # email carrying the same canonical URL.
            dedup_of = (None if markers else
                        (seen_urls.get(parts.source_url)
                         if parts.source_url else None))
            if dry_run:
                tag = ("promo" if markers
                       else "dedup" if dedup_of else "convert")
                print(f"[dry-run] {tag}: {parts.title!r} "
                      f"<{parts.source_url}> ({parts.content_kind})", file=out)
                continue
            if markers:
                record = {"message_id": mid, "source_url": parts.source_url,
                          "filename": None, "markers": markers,
                          "ingested_at": now, "outcome": "promo"}
                summary.promo += 1
            elif dedup_of:
                record = {"message_id": mid, "source_url": parts.source_url,
                          "filename": None, "dedup_of": dedup_of,
                          "ingested_at": now, "outcome": "dedup"}
                summary.dedup += 1
            else:
                target = _target_path(raw_dir, parts.title, mid)
                atomic_write_text(target, _render_source(
                    parts, message_id=mid, ingested_at=now))
                record = {"message_id": mid, "source_url": parts.source_url,
                          "filename": target.name, "ingested_at": now,
                          "outcome": "converted"}
                if parts.source_url:
                    seen_urls[parts.source_url] = target.name
                summary.converted += 1
            # D3: the feeder's only Gmail write — move out of the raw queue.
            client.modify_labels(mid, add=[label_ids[processed_label]],
                                 remove=[label_ids[label]])
            jrnl.append_journal(journal_path, record)
        except Exception as e:      # per-message isolation; stays in raw label
            summary.failed += 1
            summary.failures.append((mid, str(e)))
            print(f"failed: {mid}: {e}", file=out)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="kdb-gmail-fetch",
        description="#143 gmail-substack feeder: convert Substack_raw emails "
                    "to KDB raw sources, move them to Substack_ai_processed.")
    p.add_argument("--max", type=int, default=None, dest="max_messages",
                   help="cap messages processed (slice-first backlog, D8)")
    p.add_argument("--dry-run", action="store_true",
                   help="print planned conversions; no writes/labels/journal")
    p.add_argument("--label", default=DEFAULT_LABEL)
    p.add_argument("--processed-label", default=PROCESSED_LABEL)
    p.add_argument("--raw-dir", type=Path, default=kdb_root() / RAW_SUBDIR)
    p.add_argument("--journal", type=Path, default=kdb_root() / JOURNAL_REL)
    args = p.parse_args(argv)
    try:
        summary = fetch(client=GmailClient(), raw_dir=args.raw_dir,
                        journal_path=args.journal, label=args.label,
                        processed_label=args.processed_label,
                        max_messages=args.max_messages, dry_run=args.dry_run)
    except GmailClientError as e:
        print(f"kdb-gmail-fetch: {e}", file=sys.stderr)
        return 2
    print(f"converted {summary.converted} · dedup {summary.dedup} · "
          f"promo {summary.promo} · skipped {summary.skipped} · "
          f"failed {summary.failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
