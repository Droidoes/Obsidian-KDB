# ingestion/enrich/pass1_prompt.py
"""Pass-1 prompt construction (Jinja2 template rendering)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ingestion.enrich.config_loader import load_domains, load_source_types
from ingestion.enrich.pass1_schema import PASS1_SCHEMA_VERSION

PASS1_PROMPT_VERSION = "1.2.0"  # Task #95: drop 4 code-owned fields; full JSON template; arrow→prose boundaries (2026-05-30)

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
)


# Hardcoded boundary rule strings from NW-4 v0.4 §4 + NW-7 v0.2 §3.
# These are NOT in the config files (per D-NW7-6: scope texts in config are
# purely content-descriptive; boundary rules live in the prompt as a sibling
# block). Adjust here when boundary docs are amended.
# Boundary labels use "vs" between the candidate IDs (DeepSeek #4, Task #95):
# the earlier arrow notation (↑ ↔ ⇄) was undefined shorthand the LLM could not
# reliably interpret. The prose after the colon carries all directional meaning.
_DOMAIN_BOUNDARIES: tuple[str, ...] = (
    "ai-ml vs software vs hardware: compute stack — AI algorithms/models → ai-ml; OS/dev tools/programming → software; chips/silicon/electronics → hardware. Content classifies at the layer it primarily operates on.",
    "ai-ml vs software (AI tooling override): if content reads as software/dev-tooling BUT its subject is an AI/LLM model or product (Claude, ChatGPT, Codex, DeepSeek, Qwen, Gemini, Grok, Copilot, etc.) — classify as ai-ml, not software. Reserve software for general programming/OS/dev tooling with no AI/LLM subject.",
    "neuroscience-cognition vs biology: brain mechanisms, cognition (the former) vs cellular/genetic/evolutionary (the latter).",
    "psychology vs neuroscience-cognition: behavior/self-improvement/applied (the former) vs mechanism-level empirical brain science (the latter).",
    "health-wellbeing vs biology: applied personal-health decisions (the former) vs biological mechanisms without personal application (the latter).",
    "personal-finance vs value-investing: applied/situational (sector analysis, portfolio, tax) is personal-finance vs investment philosophy/methods/models is value-investing.",
    "value-investing vs economy-markets: investment-decision lens (what to buy/sell, valuation) vs market-mechanism lens (how markets/economies function).",
    "literature vs philosophy: narrative form (fiction, poetry) vs argumentative form (systematic thought).",
    "lifestyle vs personal-finance: experiential/personal-living (travel, hobbies, retirement activities) vs resource-management (retirement planning, tax, portfolio).",
    "lifestyle vs health-wellbeing: living-experiential focus vs health-focused (nutrition for longevity, fitness protocols).",
    "geopolitics vs history: current/recent → geopolitics; completed historical period → history.",
    "science-technology (catch-all): use ONLY when no specific S&T domain (#1-7) fits AND you can articulate why.",
)

_SOURCE_TYPE_BOUNDARIES: tuple[str, ...] = (
    "blog vs post: blog = own publication (personal blog, Substack on own subdomain); post = community/forum/aggregator. When venue cannot be inferred, classify by authorial stance: self-contained piece → blog; community-participation → post.",
    "article vs news: article = analysis/argument/extended take; news = event reporting. Hybrid: classify by dominant mode.",
    "Transcript family: Q&A dominates → interview regardless of medium; one-direction educational delivery → transcript-lecture regardless of medium; otherwise medium-based (transcript-podcast vs transcript-video).",
    "book-chapter vs book-summary: chapter = verbatim book text; summary = ABOUT the book. Annotated excerpts classified by volume: verbatim majority → book-chapter; user-authored majority → book-summary.",
    "letter vs email: letter = curated public-facing addressed correspondence; email = informal individual/small-group.",
    "speech vs transcript-lecture: speech = prepared text form of address; transcript-lecture = transcribed-from-delivery.",
    "wiki vs article: wiki = encyclopedic register (third-person, neutral, multi-source citations); article = editorial (author voice, argument).",
    "social-thread vs post: social-thread = platform-native substantive authored content (multi-tweet thread, LinkedIn long-form post, substantive single-post platform essay); post = community comment or short casual share.",
    "interview vs meeting-notes: interview = verbatim Q&A (transcribed or text-native); meeting-notes = user-summarized.",
    "daily-note vs meeting-notes: daily-note = date-stamped omnibus log; meeting-notes = single-meeting dedicated artifact.",
    "documentation vs wiki: documentation = product/instructional reference (READMEs, runbooks, tutorials — reader does); wiki = descriptive encyclopedic entry (reader learns about).",
    "chat-log vs interview: chat-log = informal multi-party / human-to-AI exchange (no curated questioner/subject roles); interview = curated Q&A (clear interlocutor + subject).",
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
