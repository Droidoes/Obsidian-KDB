"""validate_compiled_source_response — per-source model output gate (M2).

Applied to ONE parsed response object from a single compile call, BEFORE
it is enriched with runner-injected source-id-space fields and folded
into compile_result.json. Complements validate_compile_result (which
validates the aggregate file) by enforcing the stricter per-call
contract: all 7 LLM-emitted pageIntent fields required, schema-only
checks that compile_result can't express because compile_result is
lenient at aggregate level.

Two independent layers:
    1. validate(payload)               — JSON-Schema, accumulating
    2. semantic_check(payload, ...)    — post-schema, semantic rules

CLI:
    kdb-validate-response [path.json] [--source-name <name>]
    exit 0 — valid; exit 1 — invalid; exit 2 — runtime/config error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "compiled_source_response.schema.json"


@cache
def _validator() -> Draft202012Validator:
    """Build the response-schema validator. The schema constrains only
    LLM-emitted fields (slug-space + a path-free source_name). Source-id-
    space fields are runner-injected post-parse and validated at the
    persistence layer (compile_result.schema.json), not here."""
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> list[str]:
    """JSON-Schema validation. Returns [] if valid.

    Errors formatted as '[<json_path>] <message>' matching
    validate_compile_result's convention.
    """
    return [
        f"[{err.json_path}] {err.message}"
        for err in _validator().iter_errors(payload)
    ]


def semantic_check(payload: dict, *, source_name: str) -> list[str]:
    """Run AFTER schema validation passes. Returns [] if valid.

    Rules (in evaluation order, accumulating):
      1. payload['source_name'] == source_name             (echoed verbatim)
      2. summary_slug appears in [p['slug'] for p in pages]
      3. exactly one page has page_type='summary' AND slug == summary_slug
    """
    errors: list[str] = []

    echoed = payload.get("source_name")
    if echoed != source_name:
        errors.append(
            f"[$.source_name] expected {source_name!r}, got {echoed!r} "
            "(model must echo the provided source_name verbatim)"
        )

    pages = payload.get("pages") or []
    page_slugs = [p.get("slug") for p in pages if isinstance(p, dict)]

    summary_slug = payload.get("summary_slug")
    if summary_slug not in page_slugs:
        errors.append(
            f"[$.summary_slug] {summary_slug!r} does not appear in pages[].slug"
        )

    summary_page_matches = [
        p for p in pages
        if isinstance(p, dict)
        and p.get("slug") == summary_slug
        and p.get("page_type") == "summary"
    ]
    if len(summary_page_matches) != 1:
        errors.append(
            f"[$.pages] expected exactly one page with "
            f"page_type='summary' and slug={summary_slug!r}, "
            f"got {len(summary_page_matches)}"
        )

    return errors


# ---------- M5 body-link counts (Task #28) ----------
#
# The schema description for `outgoing_links` already states "Must appear
# in body as [[slug]]". M5 turns that contract from documentation into
# measurable telemetry by emitting per-source intersection / union counts
# of (declared outgoing_links) vs (slugs found in body wikilinks).
# The benchmark scorer divides at score time for symmetric Jaccard;
# this validator does not compute the ratio.

_SLUG_RE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_WIKILINK_RE = re.compile(
    rf"(?<!\\)\[\[({_SLUG_RE})(?:#[^|\]]*)?(?:\|[^\]]*)?\]\]"
)
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_code(text: str) -> str:
    """Remove fenced and inline code spans before scanning for wikilinks.
    Avoids false positives from documentation that demonstrates [[slug]]
    syntax inside code blocks."""
    return _INLINE_CODE_RE.sub("", _FENCED_CODE_RE.sub("", text))


def _body_wikilink_slugs(body: str) -> set[str]:
    """Slug set extracted from [[slug]] / [[slug|alias]] / [[slug#h]]
    tokens in `body`, after stripping code spans. Strict kebab-case
    match — out-of-pattern brackets (e.g. [[Foo Bar]]) are silently
    ignored."""
    return set(_WIKILINK_RE.findall(_strip_code(body)))


def body_link_check(payload: dict) -> tuple[int, int]:
    """Symmetric body-vs-declared link check (Task #19 M5).

    For each page, declared = set(page.outgoing_links), body = slugs in
    [[…]] tokens (code-stripped). Returns (Σ|D_p ∩ B_p|, Σ|D_p ∪ B_p|)
    across all pages — the scorer divides at score time for symmetric
    Jaccard.

    Tolerant — never raises. Malformed payload (missing/non-dict pages,
    non-list outgoing_links, non-string body) contributes (0, 0)."""
    pages = payload.get("pages") or []
    if not isinstance(pages, list):
        return (0, 0)
    intersection = 0
    union = 0
    for p in pages:
        if not isinstance(p, dict):
            continue
        declared_raw = p.get("outgoing_links") or []
        if isinstance(declared_raw, list):
            declared = {s for s in declared_raw if isinstance(s, str)}
        else:
            declared = set()
        body = p.get("body")
        body_links = _body_wikilink_slugs(body) if isinstance(body, str) else set()
        intersection += len(declared & body_links)
        union += len(declared | body_links)
    return (intersection, union)


def body_link_per_page_asymmetry(payload: dict) -> list[dict]:
    """Per-page asymmetry detail for M5 verbose trace (Task #39).

    Returns one dict per page where `declared != body`, in `pages[]` order,
    with keys: `page_slug`, `declared_only` (slugs in outgoing_links missing
    from body), `body_only` (slugs in body missing from outgoing_links).
    `declared_only` / `body_only` are sorted lists for stable output.
    Aligned pages (declared == body) are omitted. Pages without a string
    slug are reported as `page_slug=None`.

    Same payload-tolerance contract as body_link_check — never raises."""
    pages = payload.get("pages") or []
    if not isinstance(pages, list):
        return []
    out: list[dict] = []
    for p in pages:
        if not isinstance(p, dict):
            continue
        declared_raw = p.get("outgoing_links") or []
        if isinstance(declared_raw, list):
            declared = {s for s in declared_raw if isinstance(s, str)}
        else:
            declared = set()
        body = p.get("body")
        body_links = _body_wikilink_slugs(body) if isinstance(body, str) else set()
        if declared == body_links:
            continue
        slug = p.get("slug")
        out.append({
            "page_slug": slug if isinstance(slug, str) else None,
            "declared_only": sorted(declared - body_links),
            "body_only": sorted(body_links - declared),
        })
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-validate-response",
        description="Validate a single per-source compile response JSON "
                    "against compiled_source_response.schema.json + semantic rules.",
    )
    p.add_argument("path", nargs="?", help="Path to JSON file; reads stdin if omitted")
    p.add_argument(
        "--source-name",
        help="If provided, run semantic_check against this source_name too",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        raw = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    errors = validate(payload)
    if not errors and args.source_name and isinstance(payload, dict):
        errors.extend(semantic_check(payload, source_name=args.source_name))

    if errors:
        for msg in errors:
            print(msg)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
