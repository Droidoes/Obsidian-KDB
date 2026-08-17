"""gate — relevance/topic gate (blueprint §7.2): one cheap LLM call per article.

This module is split in two layers:
  - pure: build_prompt / parse_verdict (this file, top) — no I/O, no LLM
  - runner: run_gate (bottom, Task 4) — DB + call_model + journal

Fail-closed contract: unknown topic → 'other' + both extract flags False;
invalid JSON → GateParseError (the runner retries once, then journals
'failed' and writes NO verdict row).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TOPICS: tuple[str, ...] = (
    "investment", "finance-econ", "geopolitics", "china-econ", "ai-tech", "other",
)
GATE_PROMPT_VERSION = "gate_v1"
MAX_BODY_WORDS = 4000  # §7.2 truncation (~p95 body length is 4,245 words)

_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{GATE_PROMPT_VERSION}.md"


class GateParseError(ValueError):
    """Response text is not a usable verdict JSON object."""


@dataclass
class GateVerdict:
    topic: str
    signal: float
    extract_ideas: bool
    extract_lessons: bool
    confidence: float | None
    rationale: str
    raw_topic: str | None  # model's verbatim topic (== topic when known)


def build_prompt(*, title: str | None, author: str | None,
                 published_date: str | None, body: str) -> str:
    """Render the versioned prompt template; body truncated to MAX_BODY_WORDS.

    Single-pass sequential str.replace (the #123 P10 rule: substituted
    content is never re-scanned for further placeholders).
    """
    truncated = " ".join(body.split()[:MAX_BODY_WORDS])
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    for token, value in (
        ("{{TITLE}}", title or "(untitled)"),
        ("{{AUTHOR}}", author or "(unknown)"),
        ("{{PUBLISHED}}", published_date or "(unknown)"),
        ("{{BODY}}", truncated),
    ):
        template = template.replace(token, value)
    return template


def _clamp01(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def parse_verdict(text: str) -> GateVerdict:
    """Parse + salvage one gate response. Raises GateParseError when the
    envelope itself is unusable; field-level problems fail closed."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GateParseError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise GateParseError("response is not a JSON object")
    raw_topic = data.get("topic") if isinstance(data.get("topic"), str) else None
    if raw_topic in TOPICS:
        topic = raw_topic
        extract_ideas = data.get("extract_ideas") is True
        extract_lessons = data.get("extract_lessons") is True
    else:  # unknown/missing label fails closed (§7.2)
        topic = "other"
        extract_ideas = False
        extract_lessons = False
    signal = _clamp01(data.get("signal"))
    rationale = data.get("rationale")
    return GateVerdict(
        topic=topic,
        signal=signal if signal is not None else 0.0,
        extract_ideas=extract_ideas,
        extract_lessons=extract_lessons,
        confidence=_clamp01(data.get("confidence")),
        rationale=str(rationale)[:280] if rationale is not None else "",
        raw_topic=raw_topic,
    )
