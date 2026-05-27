# kdb_compiler/ingestion/pass1_prompt.py
"""Pass-1 prompt construction (Jinja2 template rendering)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kdb_compiler.ingestion.config_loader import load_domains, load_source_types
from kdb_compiler.ingestion.pass1_schema import PASS1_SCHEMA_VERSION

PASS1_PROMPT_VERSION = "1.1.0"  # Task #90 v0.2 §4 entity_search_keys amendments (2026-05-27)

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
)


# Hardcoded boundary rule strings from NW-4 v0.4 §4 + NW-7 v0.2 §3.
# These are NOT in the config files (per D-NW7-6: scope texts in config are
# purely content-descriptive; boundary rules live in the prompt as a sibling
# block). Adjust here when boundary docs are amended.
_DOMAIN_BOUNDARIES: tuple[str, ...] = (
    "ai-ml ↑ software ↑ hardware: compute stack — AI algorithms/models → ai-ml; OS/dev tools/programming → software; chips/silicon/electronics → hardware. Content classifies at the layer it primarily operates on.",
    "neuroscience-cognition ↑ biology: brain mechanisms, cognition (above) vs cellular/genetic/evolutionary (below).",
    "psychology ↑ neuroscience-cognition: behavior/self-improvement/applied (above) vs mechanism-level empirical brain science (below).",
    "health-wellbeing ↑ biology: applied personal-health decisions (above) vs biological mechanisms without personal application (below).",
    "personal-finance ↑ value-investing: applied/situational (sector analysis, portfolio, tax) above vs investment philosophy/methods/models (below).",
    "value-investing ↔ economy-markets: investment-decision lens (what to buy/sell, valuation) vs market-mechanism lens (how markets/economies function).",
    "literature ↔ philosophy: narrative form (fiction, poetry) vs argumentative form (systematic thought).",
    "lifestyle ↔ personal-finance: experiential/personal-living (travel, hobbies, retirement activities) vs resource-management (retirement planning, tax, portfolio).",
    "lifestyle ↔ health-wellbeing: living-experiential focus vs health-focused (nutrition for longevity, fitness protocols).",
    "geopolitics ⇄ history: current/recent → geopolitics; completed historical period → history.",
    "science-technology (catch-all): use ONLY when no specific S&T domain (#1-7) fits AND you can articulate why.",
)

_SOURCE_TYPE_BOUNDARIES: tuple[str, ...] = (
    "blog ↔ post: blog = own publication (personal blog, Substack on own subdomain); post = community/forum/aggregator. When venue cannot be inferred, classify by authorial stance: self-contained piece → blog; community-participation → post.",
    "article ↔ news: article = analysis/argument/extended take; news = event reporting. Hybrid: classify by dominant mode.",
    "Transcript family: Q&A dominates → interview regardless of medium; one-direction educational delivery → transcript-lecture regardless of medium; otherwise medium-based (transcript-podcast vs transcript-video).",
    "book-chapter ↔ book-summary: chapter = verbatim book text; summary = ABOUT the book. Annotated excerpts classified by volume: verbatim majority → book-chapter; user-authored majority → book-summary.",
    "letter ↔ email: letter = curated public-facing addressed correspondence; email = informal individual/small-group.",
    "speech ↔ transcript-lecture: speech = prepared text form of address; transcript-lecture = transcribed-from-delivery.",
    "wiki ↔ article: wiki = encyclopedic register (third-person, neutral, multi-source citations); article = editorial (author voice, argument).",
    "social-thread ↔ post: social-thread = platform-native substantive authored content (multi-tweet thread, LinkedIn long-form post, substantive single-post platform essay); post = community comment or short casual share.",
    "interview ↔ meeting-notes: interview = verbatim Q&A (transcribed or text-native); meeting-notes = user-summarized.",
    "daily-note ↔ meeting-notes: daily-note = date-stamped omnibus log; meeting-notes = single-meeting dedicated artifact.",
    "documentation ↔ wiki: documentation = product/instructional reference (READMEs, runbooks, tutorials — reader does); wiki = descriptive encyclopedic entry (reader learns about).",
    "chat-log ↔ interview: chat-log = informal multi-party / human↔AI exchange (no curated questioner/subject roles); interview = curated Q&A (clear interlocutor + subject).",
)


def build_pass1_prompt(*, source_text: str, source_path: str) -> str:
    template = _env.get_template("pass1_prompt.j2")
    return template.render(
        source_text=source_text,
        source_path=source_path,
        domains=load_domains(),
        source_types=load_source_types(),
        domain_boundaries=_DOMAIN_BOUNDARIES,
        source_type_boundaries=_SOURCE_TYPE_BOUNDARIES,
        prompt_version=PASS1_PROMPT_VERSION,
        schema_version=PASS1_SCHEMA_VERSION,
    )
