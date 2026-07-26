"""build_task123_snapshot_fixture — export the frozen 2026-07-25 gemini cold-run
end state as the tracked, minimized, checksummed SearchSnapshot fixture (#123
spec §8.1, D7 work item 1).

Source (READ-ONLY, gitignored): benchmark/runs/gemini-3.6-flash-2026-07-25T09-41-46_EDT/
Target (tracked):                 benchmark/truth/task123_search_snapshot_v1/

Deterministic, re-runnable, idempotent: the same bundle yields a byte-identical
fixture (manifest.generated_at is read FROM the bundle — the pages' compiled_at
stamp — never from the wall clock). Standalone: stdlib only, no project imports
— the bundle is data, not a live system.

Fields per identity (identities.json, ordered by slug ascending):
  slug, title, page_type   — from the wiki page's frontmatter
  domain                   — compile_result.json, LAST compiled_sources[] entry
                             (array order) emitting the slug (supersede rule)
  hub_rank                 — PageRank over the wikilink graph parsed from the
                             frozen bodies (1 = highest)
Excerpts (excerpt policy v1) are the exact projected bytes per identity.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

BUNDLE = Path("benchmark/runs/gemini-3.6-flash-2026-07-25T09-41-46_EDT")
OUT_DIR = Path("benchmark/truth/task123_search_snapshot_v1")
SOURCE_RUN_ID = "gemini-3.6-flash-2026-07-25T09-41-46_EDT"
EXCERPT_POLICY_VERSION = "1"

_PAGE_TYPE_DIRS = {"concepts": "concept", "articles": "article", "summaries": "summary"}

_EXCERPT_WORD_LIMIT = 250
_EXCERPT_EXTENSION_WORD_LIMIT = 25

EXCERPT_POLICY = (
    "Take the page body (verbatim bytes after the closing frontmatter '---'). "
    "If it is <=250 whitespace-separated words, the excerpt is the body "
    "verbatim. Otherwise cut at the end of the 250th word, then extend to the "
    "end of the current sentence (the next '.', '!' or '?' followed by "
    "whitespace or end-of-text) if that lands within 25 more words; if no "
    "sentence end falls inside that window, hard-cut at the 250th word "
    "boundary."
)
HUB_RANK_METHOD = (
    "PageRank over the directed link graph parsed from the frozen wiki bodies "
    "('[[slug]]' and '[[slug|display]]'; self-links dropped; links to slugs "
    "outside the 163 dropped; duplicate edges collapsed). Power iteration, "
    "damping 0.85, convergence when the L1 rank delta < 1e-12, max 100 "
    "iterations, dangling nodes redistribute uniformly, no external graph "
    "library. hub_rank = 1-based integer rank by score descending, ties "
    "broken by slug ascending."
)

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_WORD_RE = re.compile(r"\S+")
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")
_FM_SCALAR_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")


# ---------- wiki page parsing ----------

def _parse_page(path: Path) -> tuple[dict, str]:
    """(frontmatter scalars, body). Minimal scalar parser — nested blocks
    (source_refs lists) never match the anchored scalar pattern."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: missing frontmatter opening '---'")
    fm: dict[str, str] = {}
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            return fm, "".join(lines[i + 1:])
        m = _FM_SCALAR_RE.match(line.rstrip("\n"))
        if m:
            value = m.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            fm[m.group(1)] = value
    raise ValueError(f"{path}: missing frontmatter closing '---'")


def _load_pages() -> dict[str, dict]:
    """All 163 wiki pages keyed by slug: frontmatter fields + body."""
    pages: dict[str, dict] = {}
    for dirname, page_type in _PAGE_TYPE_DIRS.items():
        for path in sorted((BUNDLE / "wiki" / dirname).glob("*.md")):
            fm, body = _parse_page(path)
            if fm.get("slug") != path.stem:
                raise ValueError(f"{path}: slug {fm.get('slug')!r} != filename stem")
            if fm.get("page_type") != page_type:
                raise ValueError(f"{path}: page_type {fm.get('page_type')!r} != {page_type!r}")
            if not fm.get("title"):
                raise ValueError(f"{path}: empty title")
            pages[path.stem] = {
                "slug": path.stem,
                "title": fm["title"],
                "page_type": page_type,
                "body": body,
                "compiled_at": fm.get("compiled_at", ""),
            }
    return pages


# ---------- domain mapping (last emission wins) ----------

def _last_emission_domains() -> tuple[dict[str, str], dict[str, list[tuple[str, str]]]]:
    """slug -> domain of the LAST compiled_sources[] entry emitting it (array
    order); also the full emitter list per slug for the supersede report."""
    cr = json.loads((BUNDLE / "compile_result.json").read_text(encoding="utf-8"))
    domain_of: dict[str, str] = {}
    emitters: dict[str, list[tuple[str, str]]] = {}
    for source in cr["compiled_sources"]:
        domain = (source.get("source_meta") or {}).get("domain")
        for page in source.get("pages", []):
            emitters.setdefault(page["slug"], []).append((source["source_id"], domain))
            domain_of[page["slug"]] = domain
    return domain_of, emitters


# ---------- hub rank (PageRank over the frozen bodies' wikilinks) ----------

def _link_targets(body: str) -> list[str]:
    """Raw [[wikilink]] targets: [[slug]] and [[slug|display]] → slug."""
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(body)]


def _pagerank(slugs: list[str], edges: dict[str, set[str]]) -> dict[str, float]:
    """Power iteration: damping 0.85, L1 convergence < 1e-12, max 100
    iterations, dangling nodes redistribute uniformly. Deterministic
    (uniform start, sorted-slug iteration order)."""
    n = len(slugs)
    damping = 0.85
    in_links: dict[str, list[str]] = {s: [] for s in slugs}
    for src in slugs:
        for dst in edges[src]:
            in_links[dst].append(src)
    dangling = [s for s in slugs if not edges[s]]

    rank = {s: 1.0 / n for s in slugs}
    for _iteration in range(100):
        dangling_mass = sum(rank[s] for s in dangling)
        new_rank = {}
        for s in slugs:
            inbound = sum(rank[u] / len(edges[u]) for u in in_links[s])
            new_rank[s] = ((1.0 - damping) + damping * dangling_mass) / n + damping * inbound
        delta = sum(abs(new_rank[s] - rank[s]) for s in slugs)
        rank = new_rank
        if delta < 1e-12:
            break
    return rank


def _hub_ranks(pages: dict[str, dict]) -> dict[str, int]:
    slugs = sorted(pages)
    slug_set = set(slugs)
    edges: dict[str, set[str]] = {}
    for slug in slugs:
        edges[slug] = {t for t in _link_targets(pages[slug]["body"])
                       if t in slug_set and t != slug}
    scores = _pagerank(slugs, edges)
    ordered = sorted(slugs, key=lambda s: (-scores[s], s))
    return {slug: rank for rank, slug in enumerate(ordered, start=1)}


# ---------- excerpt policy v1 ----------

def _excerpt(body: str) -> tuple[str, bool]:
    """(excerpt_text, was_capped) under excerpt policy v1 (module docstring +
    manifest.EXCERPT_POLICY carry the algorithm text)."""
    words = list(_WORD_RE.finditer(body))
    if len(words) <= _EXCERPT_WORD_LIMIT:
        return body, False
    cut = words[_EXCERPT_WORD_LIMIT - 1].end()
    if body[cut - 1] in ".!?":
        # the 250th word itself ends the sentence — zero-word extension
        return body[:cut], True
    tail = body[cut:]
    m = _SENTENCE_END_RE.search(tail)
    if m is not None:
        added = len(_WORD_RE.findall(tail[:m.end()]))
        if added <= _EXCERPT_EXTENSION_WORD_LIMIT:
            return body[:cut + m.end()], True
    return body[:cut], True


# ---------- output ----------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not BUNDLE.is_dir():
        print(f"error: source bundle not found at {BUNDLE}", file=sys.stderr)
        return 1

    pages = _load_pages()
    domain_of, emitters = _last_emission_domains()
    hub_rank_of = _hub_ranks(pages)

    # --- identities (ordered by slug ascending) + per-page excerpt ---
    identities: list[dict] = []
    capped: list[str] = []
    excerpts: dict[str, str] = {}
    unresolved: list[str] = []
    for slug in sorted(pages):
        page = pages[slug]
        domain = domain_of.get(slug)
        if not domain:
            unresolved.append(slug)
            continue
        identities.append({
            "slug": slug,
            "title": page["title"],
            "page_type": page["page_type"],
            "domain": domain,
            "hub_rank": hub_rank_of[slug],
        })
        text, was_capped = _excerpt(page["body"])
        if was_capped:
            capped.append(slug)
        excerpts[slug] = text
    if unresolved:
        raise SystemExit(f"error: {len(unresolved)} wiki slugs resolve to no "
                         f"domain: {unresolved}")

    # --- manifest ---
    by_page_type = Counter(p["page_type"] for p in pages.values())
    by_domain = Counter(i["domain"] for i in identities)
    generated_at = max(p["compiled_at"] for p in pages.values())
    manifest = {
        "source_run_id": SOURCE_RUN_ID,
        # read FROM the bundle (never the wall clock) — idempotent rebuilds
        "generated_at": generated_at,
        "excerpt_policy_version": EXCERPT_POLICY_VERSION,
        "excerpt_policy": EXCERPT_POLICY,
        "hub_rank_method": HUB_RANK_METHOD,
        "counts": {
            "total": len(identities),
            "by_page_type": {k: by_page_type[k] for k in sorted(by_page_type)},
            "by_domain": {k: by_domain[k] for k in sorted(by_domain)},
        },
        "capped": sorted(capped),
    }

    # --- write everything ---
    _write(OUT_DIR / "identities.json",
           json.dumps(identities, indent=2, ensure_ascii=False) + "\n")
    _write(OUT_DIR / "manifest.json",
           json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    for slug, text in excerpts.items():
        _write(OUT_DIR / "excerpts" / pages[slug]["page_type"] / f"{slug}.txt", text)

    # --- checksums (standard sha256sum format, paths relative to the fixture) ---
    tracked = [OUT_DIR / "manifest.json", OUT_DIR / "identities.json"]
    tracked += sorted((OUT_DIR / "excerpts").rglob("*.txt"))
    lines = [f"{_sha256(p)}  {p.relative_to(OUT_DIR)}" for p in tracked]
    _write(OUT_DIR / "checksums.sha256", "\n".join(lines) + "\n")

    # --- console report ---
    superseded = {s: v for s, v in emitters.items() if len(v) > 1}
    print(f"identities: {len(identities)} "
          f"(concepts {by_page_type['concept']}, articles {by_page_type['article']}, "
          f"summaries {by_page_type['summary']})")
    print(f"domains: {dict(sorted(by_domain.items()))}")
    print(f"superseded slugs ({len(superseded)}):")
    for slug in sorted(superseded):
        hops = " -> ".join(d for _src, d in superseded[slug])
        print(f"  {slug}: {hops} (final: {domain_of[slug]})")
    print(f"capped pages ({len(capped)}): {sorted(capped)}")
    print(f"checksums: {len(lines)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
