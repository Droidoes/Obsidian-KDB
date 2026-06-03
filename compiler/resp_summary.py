"""resp_summary — compiler-specific parsed-response summary extraction.

Reduces a full LLM-parsed response dict to a body-free ParsedSummary
aggregate (counts + slug list + page_type histogram). Used by compiler.py
to populate the parsed_summary field on RespStatsRecord before calling
common.llm_telemetry.build_resp_stats.
"""
from __future__ import annotations

from collections import Counter

from common.types import ParsedSummary


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
    for p in pages:
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        if isinstance(slug, str):
            page_slugs.append(slug)
        pt = p.get("page_type")
        if isinstance(pt, str):
            page_types[pt] += 1
        links = p.get("outgoing_links") or []
        if isinstance(links, list):
            outgoing_link_count += len(links)

    log_entries = parsed_json.get("log_entries") or []
    warnings = parsed_json.get("warnings") or []

    return ParsedSummary(
        summary_slug=parsed_json.get("summary_slug") if isinstance(parsed_json.get("summary_slug"), str) else None,
        page_count=len(page_slugs),
        page_types=dict(page_types),
        slugs=page_slugs,
        outgoing_link_count=outgoing_link_count,
        log_entry_count=len(log_entries) if isinstance(log_entries, list) else 0,
        warning_count=len(warnings) if isinstance(warnings, list) else 0,
        source_id_echoed=parsed_json.get("source_id") if isinstance(parsed_json.get("source_id"), str) else None,
    )
