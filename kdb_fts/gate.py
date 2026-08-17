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


# --- runner half (Task 4): DB + call_model + journal ------------------------

import math
from datetime import datetime

from common.atomic_io import atomic_write_text
from common.call_model import ModelRequest, ModelResponse, call_model
from common.model_pool import resolve_models_json

from kdb_fts import ledger

_GATE_MAX_OUTPUT_TOKENS = 1024
_EXPLORATION_FRACTION = 0.05  # §7.2: of the ineligible set
_EXPLORATION_MIN = 10


def _exploration_sample(ineligible: list[dict]) -> list[str]:
    """5% (min 10, capped at population) of ineligible articles, stratified
    by author. Deterministic: groups sorted by (-size, author), ids sorted,
    round-robin."""
    k = min(len(ineligible),
            max(_EXPLORATION_MIN, math.ceil(_EXPLORATION_FRACTION * len(ineligible))))
    by_author: dict[str, list[str]] = {}
    for row in ineligible:
        by_author.setdefault(row["author"] or "(unknown)", []).append(row["article_id"])
    groups = [sorted(ids) for _, ids in
              sorted(by_author.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    picked: list[str] = []
    idx = 0
    while len(picked) < k and any(groups):
        group = groups[idx % len(groups)]
        if group:
            picked.append(group.pop(0))
        idx += 1
    return picked


def _call_once(spec, prompt: str, call_fn) -> ModelResponse:
    return call_fn(ModelRequest(
        provider=spec.provider, model=spec.model, prompt=prompt,
        json_mode=True, max_tokens=_GATE_MAX_OUTPUT_TOKENS,
        temperature=spec.temperature, extra_body=spec.extra_body,
        use_completion_tokens=spec.use_completion_tokens, route=spec.route,
    ))


def run_gate(conn, *, state_root: Path, run_id: str,
             model_id: str = "deepseek-v4-flash", max_n: int | None = None,
             dry_run: bool = False, call_fn=call_model) -> dict:
    """Gate every ungated ok article; one verdict row per call; resumable.

    dry_run: LLM calls happen, NOTHING is committed (D20) — no verdict
    rows, no exploration marks, no journal.
    """
    spec = resolve_models_json(model_id)
    todo = ledger.ungated_articles(conn, spec.model, GATE_PROMPT_VERSION)
    skipped = conn.execute(
        "SELECT COUNT(*) FROM gate_verdicts WHERE model = ? AND prompt_version = ?",
        (spec.model, GATE_PROMPT_VERSION),
    ).fetchone()[0]
    if max_n is not None:
        todo = todo[:max_n]

    stats = {"gated": 0, "failed": 0, "skipped": skipped, "by_topic": {},
             "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
             "exploration_marked": 0}
    journal: list[dict] = []
    ineligible: list[dict] = []
    gated_ids: list[str] = []

    for row in todo:
        prompt = build_prompt(title=row["title"], author=row["author"],
                              published_date=row["published_date"],
                              body=row["body"])
        verdict = None
        resp = None
        for _attempt in range(2):  # initial + one retry
            resp = _call_once(spec, prompt, call_fn)
            stats["input_tokens"] += resp.input_tokens
            stats["output_tokens"] += resp.output_tokens
            try:
                verdict = parse_verdict(resp.text)
                break
            except GateParseError:
                continue
        if verdict is None:
            stats["failed"] += 1
            journal.append({"article_id": row["article_id"], "status": "failed"})
            continue
        stats["gated"] += 1
        stats["by_topic"][verdict.topic] = stats["by_topic"].get(verdict.topic, 0) + 1
        journal.append({"article_id": row["article_id"], "status": "gated",
                        "topic": verdict.topic, "signal": verdict.signal,
                        "raw_topic": verdict.raw_topic})
        gated_ids.append(row["article_id"])
        if not (verdict.extract_ideas or verdict.extract_lessons):
            ineligible.append(row)
        if not dry_run:
            ledger.insert_gate_verdict(
                conn, article_id=row["article_id"], run_id=run_id,
                topic=verdict.topic, signal=verdict.signal,
                extract_ideas=verdict.extract_ideas,
                extract_lessons=verdict.extract_lessons, exploration=False,
                confidence=verdict.confidence, rationale=verdict.rationale,
                model=spec.model, prompt_version=GATE_PROMPT_VERSION,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens)

    marks = _exploration_sample(ineligible) if ineligible else []
    stats["exploration_marked"] = len(marks)
    stats["cost_usd"] = (spec.price_in / 1e6 * stats["input_tokens"]
                         + spec.price_out / 1e6 * stats["output_tokens"])
    if not dry_run:
        if marks:
            ledger.mark_exploration(conn, run_id, marks)
        journal.append({"summary": True, **stats,
                        "model": spec.model,
                        "prompt_version": GATE_PROMPT_VERSION,
                        "finished": datetime.now().astimezone().isoformat(timespec="seconds")})
        run_dir = ledger.run_dir_for(Path(state_root), run_id)
        atomic_write_text(
            run_dir / "journal.jsonl",
            "".join(json.dumps(line, sort_keys=True) + "\n" for line in journal),
        )
    return stats
