"""resp_stats_writer — build + atomically write one RespStatsRecord per compile call.

Writes to `<state_root>/llm_resp/<run_id>/<safe_source_id>.json`.
Directory creation is handled by atomic_io.atomic_write_bytes (mkdir
parents=True, exist_ok=True on the target's parent).

These are call-telemetry records, NOT quality evaluations. They capture
mechanical run stats (tokens, latency, attempts) and well-formedness
gates (extract/parse/schema/semantic). A response can score 4/4 on the
gates and still be a poor answer — judging response quality is a
separate feature (see M2 E3 deferred).

Always-on fields: metadata, hashes, four classification flags,
schema_errors, semantic_errors, parsed_summary (when parse_ok=True).
Env-gated by KDB_RESP_STATS_CAPTURE_FULL=='1': parsed_json,
system_prompt, user_prompt, raw_response_text.

Hash sentinels distinguish missing data from empty data:
  prompt_hash   = 'sha256:none'  -> prompt could not be built
  response_hash = 'sha256:none'  -> no response captured (pre-response fail)
"""
from __future__ import annotations

import hashlib
import os
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from kdb_compiler.atomic_io import atomic_write_json
from kdb_compiler.call_model import ModelResponse
from kdb_compiler.run_context import RunContext
from kdb_compiler.types import ParsedSummary, RespStatsRecord

if TYPE_CHECKING:
    # BuiltPrompt is defined in prompt_builder (Step F). Runtime uses duck
    # typing — any object with .system and .user str attrs works.
    from kdb_compiler.prompt_builder import BuiltPrompt

_NONE_HASH = "sha256:none"
_CAPTURE_FULL_ENV = "KDB_RESP_STATS_CAPTURE_FULL"


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _capture_full() -> bool:
    """True iff env var is exactly '1'. Any other value (including 'true',
    'yes', unset) -> False. Strict so operators don't get surprised."""
    return os.environ.get(_CAPTURE_FULL_ENV) == "1"


def safe_source_id(source_id: str) -> str:
    """Filesystem-safe filename key derived from a source_id.

    'KDB/raw/foo/bar.md' -> 'KDB__raw__foo__bar.md.<8-hex>'

    The 8-hex suffix is sha256(source_id)[:8] and disambiguates collisions
    that would otherwise map two distinct ids to the same name (e.g.
    'a/b.md' vs 'a__b.md'). Not round-trippable — the filename is a key,
    not a path recovery.
    """
    slashed = source_id.replace("/", "__")
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:8]
    return f"{slashed}.{digest}"


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


def build_resp_stats(
    *,
    ctx: RunContext,
    source_id: str,
    prompt: BuiltPrompt | None,
    raw_response_text: str,
    model_response: ModelResponse | None,
    extract_ok: bool,
    parse_ok: bool,
    parsed_json: dict | None,
    schema_ok: bool,
    schema_errors: list[str],
    semantic_ok: bool,
    semantic_errors: list[str],
) -> RespStatsRecord:
    """Assemble one RespStatsRecord. Hashes always computed. See module
    docstring for the always-on vs env-gated field split."""
    capture_full = _capture_full()

    if model_response is not None:
        provider = model_response.provider
        model = model_response.model
        attempts = model_response.attempts
        latency_ms = model_response.latency_ms
        input_tokens = model_response.input_tokens
        output_tokens = model_response.output_tokens
        response_hash = _sha256(raw_response_text) if raw_response_text else _sha256("")
    else:
        provider = ""
        model = ""
        attempts = 0
        latency_ms = 0
        input_tokens = 0
        output_tokens = 0
        response_hash = _NONE_HASH

    if prompt is not None:
        prompt_text = prompt.system + "\n\n" + prompt.user
        prompt_hash = _sha256(prompt_text)
    else:
        prompt_hash = _NONE_HASH

    summary = build_parsed_summary(parsed_json) if (parse_ok and isinstance(parsed_json, dict)) else None

    return RespStatsRecord(
        run_id=ctx.run_id,
        source_id=source_id,
        provider=provider,
        model=model,
        attempts=attempts,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        prompt_hash=prompt_hash,
        response_hash=response_hash,
        extract_ok=extract_ok,
        parse_ok=parse_ok,
        schema_ok=schema_ok,
        semantic_ok=semantic_ok,
        schema_errors=list(schema_errors),
        semantic_errors=list(semantic_errors),
        parsed_summary=summary,
        parsed_json=(parsed_json if capture_full else None),
        system_prompt=(prompt.system if capture_full and prompt is not None else None),
        user_prompt=(prompt.user if capture_full and prompt is not None else None),
        raw_response_text=(raw_response_text if capture_full else None),
    )


def write_resp_stats(record: RespStatsRecord, state_root: Path) -> Path:
    """Atomic write to <state_root>/llm_resp/<run_id>/<safe_source_id>.json.

    Returns the written path. atomic_write_json creates the parent dirs
    (parents=True, exist_ok=True) so no explicit mkdir is needed here.
    """
    target = state_root / "llm_resp" / record.run_id / f"{safe_source_id(record.source_id)}.json"
    atomic_write_json(target, record.to_dict())
    return target
