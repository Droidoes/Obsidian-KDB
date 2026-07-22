"""resp_summary — compiler-specific parsed-response summary extraction.

Reduces a full LLM-parsed response dict to a body-free ParsedSummary
aggregate (counts + slug list + page_type histogram). Used by compiler.py
to populate the parsed_summary field on RespStatsRecord before calling
common.llm_telemetry.build_resp_stats.

#115 (D-115-15): runs from compile_one's `finally` on EVERY parsed dict,
including schema/semantic-rejected responses. `summary_slug` is emitted
ONLY when exactly one well-formed summary page is observable (else None);
`outgoing_link_count` derives from body wikilinks via the pure extractor.
"""
from __future__ import annotations

from collections import Counter

from common.types import ParsedSummary
from compiler.validate_source_response import body_wikilink_slugs


def build_parsed_summary(parsed_json: dict) -> ParsedSummary:
    """Reduce a parsed per-source response to a body-free shape digest.

    Never raises — missing / wrong-typed fields produce None / 0 / [].
    Intended to be lightweight aggregate-analytics bait: counts + slug
    list + page_type histogram, no bodies.
    """
    pages = parsed_json.get("pages") or []
    if not isinstance(pages, list):
        pages = []

    page_slugs: list[str] = []
    page_types: Counter[str] = Counter()
    outgoing_link_count = 0
    summary_slugs: list[str] = []
    for p in pages:
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        if isinstance(slug, str):
            page_slugs.append(slug)
        pt = p.get("page_type")
        if isinstance(pt, str):
            page_types[pt] += 1
            if pt == "summary" and isinstance(slug, str):
                summary_slugs.append(slug)
        body = p.get("body")
        if isinstance(body, str):
            outgoing_link_count += len(body_wikilink_slugs(body))

    notes = parsed_json.get("compilation_notes") or []

    return ParsedSummary(
        # emitted ONLY when exactly one well-formed summary page is observable
        summary_slug=summary_slugs[0] if len(summary_slugs) == 1 else None,
        page_count=len(page_slugs),
        page_types=dict(page_types),
        slugs=page_slugs,
        outgoing_link_count=outgoing_link_count,
        compilation_note_count=len(notes) if isinstance(notes, list) else 0,
    )
