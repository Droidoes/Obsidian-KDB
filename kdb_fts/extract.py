"""extract — idea/lesson extraction (blueprint §5.2): one structured LLM call.

Split in two layers, mirroring gate.py:
  - pure: build_prompt / parse_extraction (this file, top) — no I/O, no LLM
  - runner: run_extract (Task 5) — DB + call_model + spans + journal

Fail-closed: JSON-object envelope required; field-level salvage is per-record
(required-core span fail → drop record; optional field → null; D-P2-5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EXTRACT_PROMPT_VERSION = "extract_v1"
MAX_BODY_WORDS = 8000    # D-P2-4: whole body below this; chunk above
CHUNK_TARGET_WORDS = 6000
STANCES = ("long", "short", "pass", "watch", "unclear")
LESSON_TYPES = ("framework", "mental-model", "mistake-postmortem", "process", "risk", "behavioral")

_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{EXTRACT_PROMPT_VERSION}.j2"


class ExtractParseError(ValueError):
    """Response text is not a usable extraction JSON object."""


@dataclass
class RawMention:
    company: str
    stance: str
    thesis: str
    ticker: str | None
    valuation_premise: str | None
    catalyst: str | None
    risks: str | None
    horizon: str | None
    expires_on: str | None
    extraction_uncertainty: float | None
    evidence: dict | None   # {"paragraph_id", "head_anchor", "tail_anchor"}


@dataclass
class RawCard:
    principle: str
    context: str | None
    reusable_application: str | None
    failure_mode: str | None
    lesson_type: str | None
    evidence: dict | None


@dataclass
class ExtractionResult:
    mentions: list[RawMention]
    cards: list[RawCard]
    downgraded: bool


def _opt_str(value) -> str | None:
    return value if isinstance(value, str) and value else None


def _evidence(ev) -> dict | None:
    if not isinstance(ev, dict):
        return None
    pid, head, tail = ev.get("paragraph_id"), ev.get("head_anchor"), ev.get("tail_anchor")
    if not (isinstance(pid, str) and isinstance(head, str) and isinstance(tail, str)):
        return None
    return {"paragraph_id": pid, "head_anchor": head, "tail_anchor": tail}


def _clamp01(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def build_prompt(*, title: str | None, author: str | None,
                 published_date: str | None, paragraphs: list[tuple[str, str]]) -> str:
    """Render the versioned prompt; body = numbered paragraphs. NO word truncation
    — chunking is the caller's job (D-P2-4: never silently truncate). Single-pass
    sequential str.replace (the #123 P10 rule)."""
    body = "\n\n".join(f"[{pid}]\n{text}" for pid, text in paragraphs)
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    for token, value in (
        ("{{TITLE}}", title or "(untitled)"),
        ("{{AUTHOR}}", author or "(unknown)"),
        ("{{PUBLISHED}}", published_date or "(unknown)"),
        ("{{BODY}}", body),
    ):
        template = template.replace(token, value)
    return template


def parse_extraction(text: str) -> ExtractionResult:
    """Parse + salvage one extraction response. Raises ExtractParseError when the
    envelope itself is unusable; per-record salvage drops bad records but keeps
    siblings (the #123 R1 posture)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractParseError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ExtractParseError("response is not a JSON object")

    mentions: list[RawMention] = []
    for idea in data.get("ideas") or []:
        if not isinstance(idea, dict):
            continue
        company = idea.get("company")
        stance = idea.get("stance")
        thesis = idea.get("thesis")
        ev = _evidence(idea.get("evidence"))
        # required core = company + valid stance + thesis + evidence (D-P2-5)
        if (not (isinstance(company, str) and company)
                or stance not in STANCES
                or not (isinstance(thesis, str) and thesis)
                or ev is None):
            continue
        mentions.append(RawMention(
            company=company, stance=stance, thesis=thesis,
            ticker=_opt_str(idea.get("ticker")),
            valuation_premise=_opt_str(idea.get("valuation_premise")),
            catalyst=_opt_str(idea.get("catalyst")),
            risks=_opt_str(idea.get("risks")),
            horizon=_opt_str(idea.get("horizon")),
            expires_on=_opt_str(idea.get("expires_on")),
            extraction_uncertainty=_clamp01(idea.get("extraction_uncertainty")),
            evidence=ev,
        ))

    cards: list[RawCard] = []
    for lesson in data.get("lessons") or []:
        if not isinstance(lesson, dict):
            continue
        principle = lesson.get("principle")
        ev = _evidence(lesson.get("evidence"))
        if (not (isinstance(principle, str) and principle)) or ev is None:
            continue
        lt = lesson.get("lesson_type")
        cards.append(RawCard(
            principle=principle,
            context=_opt_str(lesson.get("context")),
            reusable_application=_opt_str(lesson.get("reusable_application")),
            failure_mode=_opt_str(lesson.get("failure_mode")),
            lesson_type=lt if lt in LESSON_TYPES else None,  # unknown → null the field
            evidence=ev,
        ))

    return ExtractionResult(mentions=mentions, cards=cards,
                            downgraded=data.get("downgraded") is True)
