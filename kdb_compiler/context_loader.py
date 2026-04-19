"""context_loader — build a compact manifest snapshot for one compile job.

The model's only view of world state. Body-free by design (D8): we expose
{slug, title, page_type, outgoing_links} and nothing else — no bodies,
paths, timestamps, hashes, source_refs, or frontmatter.

Selection rule (per blueprint §5.3):

    1. Seeds = union of
        a. pages whose source_refs[].source_id == <source_id>
        b. pages whose slug appears as a whole-word token in <source_text>
    2. Depth-1 expansion = the targets of seeds' outgoing_links[], resolved
       against manifest.pages by slug.
    3. Concatenate seeds (sorted by slug) then depth-1 (sorted by slug,
       seeds excluded). First-seen wins on duplicates.
    4. Truncate to page_cap. Seeds are placed first, so an over-cap pass
       keeps as many seeds as possible and drops depth-1 overflow first.

Whole-word matching treats hyphens as connectors (not boundaries), using
negative lookarounds `(?<![\\w-])` ... `(?![\\w-])`. So `self-attention`
matches at word edges, but the slug `attention` does NOT match inside
`self-attention`. Without this, every hyphenated slug would noisy-match
its sub-terms (reinforcement-learning source pulling in `reinforcement`
and `learning`). Case-insensitive.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from kdb_compiler.types import ContextPage, ContextSnapshot

_VALID_PAGE_TYPES = {"summary", "concept", "article"}


def build_context_snapshot(
    manifest: dict,
    *,
    source_id: str,
    source_text: str,
    page_cap: int = 50,
) -> ContextSnapshot:
    """Pure. Given a manifest + source_id + source_text, return a capped
    snapshot of pages the LLM should consider.

    Missing / malformed manifest entries are skipped (never raise). An
    empty or missing manifest yields an empty snapshot.
    """
    pages_by_key = _pages_dict(manifest)
    if not pages_by_key:
        return ContextSnapshot(source_id=source_id, pages=[])

    # slug → page record (first occurrence wins if the manifest duplicates)
    slug_index: dict[str, dict] = {}
    for rec in pages_by_key.values():
        slug = rec.get("slug")
        if isinstance(slug, str) and slug and slug not in slug_index:
            slug_index[slug] = rec

    seed_slugs = _seed_slugs(
        slug_index=slug_index,
        source_id=source_id,
        source_text=source_text,
    )
    depth1_slugs = _depth1_slugs(slug_index=slug_index, seed_slugs=seed_slugs)

    ordered = sorted(seed_slugs) + sorted(depth1_slugs)
    selected = ordered[:page_cap]

    pages = [_to_context_page(slug_index[s]) for s in selected if s in slug_index]
    pages = [p for p in pages if p is not None]
    return ContextSnapshot(source_id=source_id, pages=pages)


# ---------- selection helpers ----------

def _seed_slugs(
    *,
    slug_index: dict[str, dict],
    source_id: str,
    source_text: str,
) -> set[str]:
    """Return slugs of seed pages: source_refs match ∪ slug-in-text match."""
    seeds: set[str] = set()

    for slug, rec in slug_index.items():
        if _page_cites_source(rec, source_id):
            seeds.add(slug)

    # Slug-in-text match. Compile a single alternation regex for speed on
    # long source_text.
    if slug_index:
        candidate_slugs = [s for s in slug_index if s not in seeds]
        if candidate_slugs:
            pattern = _whole_word_alternation([re.escape(s) for s in candidate_slugs])
            for m in pattern.finditer(source_text):
                seeds.add(m.group(0).lower())

    return seeds


def _depth1_slugs(
    *,
    slug_index: dict[str, dict],
    seed_slugs: Iterable[str],
) -> set[str]:
    """Targets of seeds' outgoing_links that resolve to a real page and
    aren't already a seed."""
    seed_set = set(seed_slugs)
    out: set[str] = set()
    for slug in seed_set:
        rec = slug_index.get(slug)
        if rec is None:
            continue
        links = rec.get("outgoing_links") or []
        if not isinstance(links, list):
            continue
        for link in links:
            if (
                isinstance(link, str)
                and link in slug_index
                and link not in seed_set
            ):
                out.add(link)
    return out


def _page_cites_source(page_record: dict, source_id: str) -> bool:
    """Page cites the source_id via its source_refs[].source_id."""
    refs = page_record.get("source_refs") or []
    if not isinstance(refs, list):
        return False
    for ref in refs:
        if isinstance(ref, dict) and ref.get("source_id") == source_id:
            return True
    return False


def _whole_word_alternation(escaped_slugs: list[str]) -> re.Pattern[str]:
    """Build a case-insensitive `(?<![\\w-])(a|b|c)(?![\\w-])` pattern.

    Hyphens are treated as part of a token, so `attention` does NOT match
    inside `self-attention`. Only edges of whitespace/punctuation count as
    word boundaries for slug matching.
    """
    return re.compile(
        r"(?<![\w-])(" + "|".join(escaped_slugs) + r")(?![\w-])",
        re.IGNORECASE,
    )


# ---------- projection helpers ----------

def _to_context_page(page_record: dict) -> ContextPage | None:
    """Reduce a manifest PageRecord to a ContextPage. Drops bodies, paths,
    timestamps, hashes, source_refs, confidence, status, etc. Returns None
    if the record is too malformed to project (missing slug/title/page_type
    or a page_type outside the locked enum)."""
    slug = page_record.get("slug")
    title = page_record.get("title")
    page_type = page_record.get("page_type")
    if not isinstance(slug, str) or not slug:
        return None
    if not isinstance(title, str):
        return None
    if page_type not in _VALID_PAGE_TYPES:
        return None

    links_raw = page_record.get("outgoing_links") or []
    outgoing_links = [x for x in links_raw if isinstance(x, str)] if isinstance(links_raw, list) else []

    return ContextPage(
        slug=slug,
        title=title,
        page_type=page_type,  # type: ignore[arg-type]  # checked against _VALID_PAGE_TYPES
        outgoing_links=outgoing_links,
    )


def _pages_dict(manifest: Any) -> dict[str, dict]:
    """Extract manifest['pages'] defensively. Returns {} if missing/wrong type."""
    if not isinstance(manifest, dict):
        return {}
    pages = manifest.get("pages")
    if not isinstance(pages, dict):
        return {}
    return {k: v for k, v in pages.items() if isinstance(v, dict)}


def main() -> None:  # pragma: no cover
    raise SystemExit("context_loader is a library module; not meant to be run directly.")


if __name__ == "__main__":
    main()
