"""intake — deterministic walk of a raw source tree (no LLM, D16/D17).

Reads KDB/raw trees read-only; produces ArticleRecords for the ledger.
Cleanliness precedence (one label per file):
    digest-stub > media > bleed > short > ok
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from common.source_io import parse_existing_frontmatter

from kdb_fts import author_map, ledger

DIGEST_TITLE_RE = re.compile(r"\band\s+\d+\s+more\b", re.IGNORECASE)
SHORT_WORD_FLOOR = 50
MEDIA_KINDS = frozenset({"video", "podcast"})
_EXCLUDE_DIRS = frozenset({"_promo"})
_BLEED_FENCE_SCAN_LIMIT = 200  # lines to scan for the closing fence


def _word_count(body: str) -> int:
    return len(re.findall(r"\S+", body))


def _split_paragraphs(body: str) -> list[str]:
    """Blank-line split; paragraph i becomes p000i in the ledger (stable per hash)."""
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _repair_bleed(text: str) -> str:
    """Repaired VIEW for frontmatter-bleed files: drop everything through the
    closing fence. Original bytes are never touched (D16)."""
    lines = text.splitlines()
    for i in range(1, min(len(lines), _BLEED_FENCE_SCAN_LIMIT)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :])
    return text  # no closing fence found: treat whole file as body


def _identity(fm: dict, text: str) -> str:
    gid = fm.get("gmail_message_id")
    if gid:
        return str(gid)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def scan_tree(raw_root: Path) -> list[ledger.ArticleRecord]:
    """Walk raw_root for *.md (excluding _EXCLUDE_DIRS), classify, and return
    one ArticleRecord per file. Pure: no DB, no writes."""
    records: list[ledger.ArticleRecord] = []
    for path in sorted(Path(raw_root).rglob("*.md")):
        if _EXCLUDE_DIRS & set(path.relative_to(raw_root).parts[:-1]):
            continue
        text = path.read_text(encoding="utf-8")
        fm, body = parse_existing_frontmatter(text)
        if not isinstance(fm, dict):
            fm = {}  # valid-YAML-but-non-mapping frontmatter: treat as unparseable (→ bleed)
        is_bleed = text.lstrip().startswith("---") and not fm
        view = _repair_bleed(text) if is_bleed else body
        title = fm.get("title")
        kind = fm.get("content_kind")
        words = _word_count(view)
        if isinstance(title, str) and DIGEST_TITLE_RE.search(title):
            cleanliness = "digest-stub"
        elif kind in MEDIA_KINDS:
            cleanliness = "media"
        elif is_bleed:
            cleanliness = "bleed"
        elif words < SHORT_WORD_FLOOR:
            cleanliness = "short"
        else:
            cleanliness = "ok"
        records.append(
            ledger.ArticleRecord(
                article_id=_identity(fm, text),
                path=str(path),
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                title=title if isinstance(title, str) else None,
                raw_author=fm.get("author") if isinstance(fm.get("author"), str) else None,
                author_id=None,  # resolved in run_intake via the author map
                published_date=(
                    str(fm["published_date"]) if fm.get("published_date") else None
                ),
                source_url=fm.get("source_url") if isinstance(fm.get("source_url"), str) else None,
                content_kind=kind if isinstance(kind, str) else None,
                word_count=words,
                cleanliness=cleanliness,
                paragraphs=_split_paragraphs(view),
            )
        )
    return records


def run_intake(conn, raw_root: Path, run_id: str, state_root: Path | None = None) -> dict:
    """Scan + upsert + prune + FTS rebuild. Idempotent on an unchanged tree.

    state_root: where author_map.yaml lives (None → no overrides applied).
    """
    records = scan_tree(raw_root)
    mapping = author_map.load_map(state_root) if state_root else {}
    for rec in records:
        if rec.raw_author:
            rec.author_id = author_map.resolve(conn, rec.raw_author, mapping)
        ledger.upsert_article(conn, rec, run_id)
    deleted = ledger.delete_absent(conn, {r.article_id for r in records})
    ledger.rebuild_fts(conn)
    by_cleanliness: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for r in records:
        by_cleanliness[r.cleanliness] = by_cleanliness.get(r.cleanliness, 0) + 1
        k = r.content_kind or "unknown"
        by_kind[k] = by_kind.get(k, 0) + 1
    return {
        "seen": len(records),
        "upserted": len(records),
        "deleted": deleted,
        "by_cleanliness": by_cleanliness,
        "by_content_kind": by_kind,
        "raw_author_strings": len({r.raw_author for r in records if r.raw_author}),
    }
