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


# --- runner half (Task 5): DB + call_model + spans + journal ------------------

from datetime import datetime

from common.atomic_io import atomic_write_text
from common.call_model import ModelRequest, call_model
from common.model_pool import resolve_models_json

from kdb_fts import ledger, spans

_EXTRACT_MAX_OUTPUT_TOKENS = 8192


def chunk_paragraphs(paragraphs: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Greedy paragraph-atomic grouping ≤ CHUNK_TARGET_WORDS; a single paragraph
    longer than the target is its own chunk (never split). 0-based chunks."""
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_words = 0
    for pid, body in paragraphs:
        words = len(body.split())
        if current and current_words + words > CHUNK_TARGET_WORDS:
            chunks.append(current)
            current = []
            current_words = 0
        current.append((pid, body))
        current_words += words
    if current:
        chunks.append(current)
    return chunks


def _call_once(spec, prompt: str, call_fn):
    return call_fn(ModelRequest(
        provider=spec.provider, model=spec.model, prompt=prompt,
        json_mode=True, max_tokens=_EXTRACT_MAX_OUTPUT_TOKENS,
        temperature=spec.temperature, extra_body=spec.extra_body,
        use_completion_tokens=spec.use_completion_tokens, route=spec.route,
    ))


def _already_extracted(conn, article_id: str, schema_version: str,
                       model: str, prompt_version: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM extraction_runs WHERE article_id = ? AND schema_version = ?"
        " AND model = ? AND prompt_version = ? LIMIT 1",
        (article_id, schema_version, model, prompt_version),
    ).fetchone() is not None


def _slice_evidence(para_map: dict[str, str], evidence: dict | None) -> dict | None:
    """Slice the source span for one record's evidence (article-global map).
    Returns {"paragraph_id", "quote"} or None (→ the runner drops/nulls)."""
    if not evidence:
        return None
    body = para_map.get(evidence["paragraph_id"])
    if body is None:
        return None
    quote = spans.slice_span(body, evidence["head_anchor"], evidence["tail_anchor"])
    if quote is None:
        return None
    return {"paragraph_id": evidence["paragraph_id"], "quote": quote}


def run_extract(conn, *, state_root, run_id: str, model_id: str = "deepseek-v4-flash",
                max_n: int | None = None, dry_run: bool = False, call_fn=call_model) -> dict:
    """Extract every triggered article (accept rule ∪ exploration); one structured
    call per chunk; atomic per-article commit; resumable at article granularity."""
    spec = resolve_models_json(model_id)
    todo = ledger.triggered_articles(conn)
    if max_n is not None:
        todo = todo[:max_n]

    stats = {"extracted": 0, "empty": 0, "failed": 0, "skipped": 0,
             "mentions": 0, "cards": 0, "input_tokens": 0, "output_tokens": 0,
             "cost_usd": 0.0, "dropped_records": 0, "dropped_fields": 0}
    journal: list[dict] = []
    raw_outputs: dict[str, list[tuple[int, str]]] = {}

    for row in todo:
        article_id = row["article_id"]
        if _already_extracted(conn, article_id, EXTRACT_PROMPT_VERSION,
                              spec.model, EXTRACT_PROMPT_VERSION):
            stats["skipped"] += 1
            continue

        paragraphs = ledger.article_paragraphs(conn, article_id)
        para_map = dict(paragraphs)
        total_words = sum(len(b.split()) for _, b in paragraphs)
        chunks = [paragraphs] if total_words <= MAX_BODY_WORDS else chunk_paragraphs(paragraphs)

        statuses, mentions, cards = [], [], []
        article_failed = False

        for ci, chunk in enumerate(chunks):
            prompt = build_prompt(title=row["title"], author=row["author"],
                                  published_date=row["published_date"], paragraphs=chunk)
            result = None
            resp = None
            for _attempt in range(2):  # initial + one retry
                resp = _call_once(spec, prompt, call_fn)
                stats["input_tokens"] += resp.input_tokens
                stats["output_tokens"] += resp.output_tokens
                try:
                    result = parse_extraction(resp.text)
                    break
                except ExtractParseError:
                    continue
            raw_outputs.setdefault(article_id, []).append((ci, resp.text if resp else ""))
            if result is None:
                article_failed = True
                stats["failed"] += 1
                continue

            for m in result.mentions:
                span = _slice_evidence(para_map, m.evidence)
                if span is None:  # required-core span fail → drop the record (D-P2-5)
                    stats["dropped_records"] += 1
                    continue
                mentions.append({
                    "company": m.company, "stance": m.stance, "thesis": m.thesis,
                    "ticker": m.ticker, "valuation_premise": m.valuation_premise,
                    "catalyst": m.catalyst, "risks": m.risks, "horizon": m.horizon,
                    "expires_on": m.expires_on, "extraction_uncertainty": m.extraction_uncertainty,
                    "spans": [{"field": "thesis", "paragraph_id": span["paragraph_id"],
                               "exact_quote": span["quote"]}],
                })
            for c in result.cards:
                span = _slice_evidence(para_map, c.evidence)
                if span is None:
                    stats["dropped_records"] += 1
                    continue
                cards.append({
                    "principle": c.principle, "context": c.context,
                    "reusable_application": c.reusable_application,
                    "failure_mode": c.failure_mode, "lesson_type": c.lesson_type,
                    "spans": [{"field": "principle", "paragraph_id": span["paragraph_id"],
                               "exact_quote": span["quote"]}],
                })
            statuses.append({
                "status": "ok" if (result.mentions or result.cards) else "empty",
                "chunk_index": ci, "n_chunks": len(chunks),
                "n_mentions": len(result.mentions), "n_cards": len(result.cards),
                "expect_ideas": row["expect_ideas"], "expect_lessons": row["expect_lessons"],
                "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
            })

        if article_failed:
            journal.append({"article_id": article_id, "status": "failed"})
            continue

        n_mentions = len(mentions)
        n_cards = len(cards)
        if not dry_run:
            ledger.commit_extraction_article(
                conn, article_id=article_id, run_id=run_id,
                schema_version=EXTRACT_PROMPT_VERSION, model=spec.model,
                prompt_version=EXTRACT_PROMPT_VERSION,
                statuses=statuses, mentions=mentions, cards=cards)

        stats["extracted"] += 1
        stats["mentions"] += n_mentions
        stats["cards"] += n_cards
        if n_mentions == 0 and n_cards == 0:
            stats["empty"] += 1
        journal.append({"article_id": article_id, "status": "ok",
                        "n_mentions": n_mentions, "n_cards": n_cards})

    stats["cost_usd"] = (spec.price_in / 1e6 * stats["input_tokens"]
                         + spec.price_out / 1e6 * stats["output_tokens"])
    if not dry_run:
        if raw_outputs:
            edir = ledger.extractions_dir_for(state_root, run_id)
            for article_id, outs in raw_outputs.items():
                atomic_write_text(
                    edir / f"{article_id}.json",
                    json.dumps(outs, ensure_ascii=False, indent=2),
                )
        journal.append({"summary": True, **stats, "model": spec.model,
                        "prompt_version": EXTRACT_PROMPT_VERSION,
                        "finished": datetime.now().astimezone().isoformat(timespec="seconds")})
        run_dir = ledger.run_dir_for(state_root, run_id)
        atomic_write_text(
            run_dir / "journal.jsonl",
            "".join(json.dumps(line, sort_keys=True) + "\n" for line in journal),
        )
    return stats
