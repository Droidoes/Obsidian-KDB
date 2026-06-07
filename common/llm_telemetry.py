"""llm_telemetry — build + atomically write one RespStatsRecord per LLM call.

Stage-agnostic (common leaf). Contains only the generic telemetry machinery:
hashing, safe filename derivation, record assembly, and atomic write.

By default, writes to `<state_root>/llm_resp/<run_id>/<safe_source_id>.json`.
Callers that own a run-specific artifact directory may pass `artifact_dir`
to place the record there instead. Directory creation is handled by
atomic_io.atomic_write_json (mkdir parents=True, exist_ok=True on the
target's parent).

These are call-telemetry records, NOT quality evaluations. They capture
mechanical run stats (tokens, latency, attempts) and well-formedness
gates (extract/parse/schema/semantic). A response can score 4/4 on the
gates and still be a poor answer — judging response quality is a
separate feature (see M2 E3 deferred).

Always-on fields: metadata, hashes, four classification flags,
schema_errors, semantic_errors, parsed_summary (caller-supplied, when
parse_ok=True). Env-gated by KDB_RESP_STATS_CAPTURE_FULL=='1':
parsed_json, system_prompt, user_prompt, raw_response_text.

Hash sentinels distinguish missing data from empty data:
  prompt_hash   = 'sha256:none'  -> prompt could not be built
  response_hash = 'sha256:none'  -> no response captured (pre-response fail)

Compiler-specific logic (build_parsed_summary) lives in compiler.resp_summary;
callers must compute the ParsedSummary and pass it via `parsed_summary`.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from common.atomic_io import atomic_write_json
from common.call_model import ModelResponse
from common.run_context import RunContext
from common.types import ParsedSummary, RespStatsRecord

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


def build_resp_stats(
    *,
    ctx: RunContext,
    source_id: str,
    provider: str = "",
    model: str = "",
    prompt,
    raw_response_text: str,
    model_response: ModelResponse | None,
    extract_ok: bool,
    parse_ok: bool,
    parsed_json: dict | None,
    schema_ok: bool,
    schema_errors: list[str],
    semantic_ok: bool,
    semantic_errors: list[str],
    parsed_summary: ParsedSummary | None = None,
    source_words: int = 0,
    failure=None,
    compile_attempts: int | None = None,
    syntax_repaired: bool = False,
    slug_coerced: bool = False,
    final_status: str | None = None,
    total_input_tokens: int | None = None,
    total_output_tokens: int | None = None,
    total_latency_ms: int | None = None,
    call_count: int = 1,
    final_attempt_index: int = 1,
    price_in: float = 0.0,
    price_out: float = 0.0,
) -> RespStatsRecord:
    """Assemble one RespStatsRecord. Hashes always computed. See module
    docstring for the always-on vs env-gated field split.

    `provider` and `model` are the **requested** provider/model from the
    runner's call site. They are persisted on every record (success or
    pre-response failure) so the benchmark scorer's filter contract holds
    for parse-failed and source-read-failed records too — see Task #19
    Phase 3 / Round 4 (MF2). When `model_response` is present, its
    provider/model echoes the request and is used directly; when
    `model_response is None` (pre-response failure), the requested values
    are persisted as fallback.

    `source_words` is the whitespace-split count of the source text the
    caller read (or 0 on source-read failure). Persisted on the record so
    the benchmark scorer can derive cost/latency-per-1k-source-words
    without re-reading the corpus.

    `parsed_summary` is caller-supplied (computed via
    compiler.resp_summary.build_parsed_summary when parse_ok=True).
    `prompt` is duck-typed — any object with .system and .user str attrs.
    `failure` is duck-typed — any object with .stage, .exception_type,
    .message str attrs (or None).
    """
    capture_full = _capture_full()

    if model_response is not None:
        persisted_provider = model_response.provider
        persisted_model = model_response.model
        attempts = model_response.attempts
        latency_ms = model_response.latency_ms
        input_tokens = model_response.input_tokens
        output_tokens = model_response.output_tokens
        response_hash = _sha256(raw_response_text) if raw_response_text else _sha256("")
        stop_reason = model_response.stop_reason
    else:
        persisted_provider = provider
        persisted_model = model
        attempts = 0
        latency_ms = 0
        input_tokens = 0
        output_tokens = 0
        response_hash = _NONE_HASH
        stop_reason = None

    token_overrun = stop_reason in ("max_tokens", "length")

    if prompt is not None:
        prompt_text = prompt.system + "\n\n" + prompt.user
        prompt_hash = _sha256(prompt_text)
    else:
        prompt_hash = _NONE_HASH

    failed_after_response = bool(raw_response_text) and not (
        extract_ok and parse_ok and schema_ok and semantic_ok
    )

    # Discarded-attempt aggregation (#109 Task 2).
    # When the caller supplies explicit totals (multi-attempt path), use them.
    # Otherwise, fall back to the single-attempt values so 1-attempt runs are
    # always back-compat (totals == per-call values, call_count=1, final_attempt_index=1).
    agg_input_tokens = total_input_tokens if total_input_tokens is not None else input_tokens
    agg_output_tokens = total_output_tokens if total_output_tokens is not None else output_tokens
    agg_latency_ms = total_latency_ms if total_latency_ms is not None else latency_ms

    # #110 Task 2.1: per-call cost from pool pricing × AGGREGATED tokens.
    # price_in/price_out are USD per 1,000,000 tokens; you pay for every retry
    # attempt, so bill the aggregated totals (not the final-attempt values).
    # Defaults to 0.0 when prices are unset (unpriced run).
    cost_usd = price_in / 1e6 * agg_input_tokens + price_out / 1e6 * agg_output_tokens

    return RespStatsRecord(
        run_id=ctx.run_id,
        source_id=source_id,
        provider=persisted_provider,
        model=persisted_model,
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
        parsed_summary=parsed_summary,
        parsed_json=(parsed_json if capture_full else None),
        system_prompt=(prompt.system if capture_full and prompt is not None else None),
        user_prompt=(prompt.user if capture_full and prompt is not None else None),
        raw_response_text=(
            raw_response_text if (capture_full or failed_after_response) else None
        ),
        stop_reason=stop_reason,
        token_overrun=token_overrun,
        cost_usd=cost_usd,
        source_words=source_words,
        failure_stage=failure.stage if failure is not None else None,
        failure_exception_type=failure.exception_type if failure is not None else None,
        failure_exception_message=failure.message if failure is not None else None,
        compile_attempts=compile_attempts,
        syntax_repaired=syntax_repaired,
        slug_coerced=slug_coerced,
        final_status=final_status,
        total_input_tokens=agg_input_tokens,
        total_output_tokens=agg_output_tokens,
        total_latency_ms=agg_latency_ms,
        call_count=call_count,
        final_attempt_index=final_attempt_index,
    )


def write_resp_stats(
    record: RespStatsRecord,
    state_root: Path,
    *,
    artifact_dir: Path | None = None,
) -> Path:
    """Atomic write one response-stats record.

    Default target:
        <state_root>/llm_resp/<run_id>/<safe_source_id>.json

    Run-owned target:
        <artifact_dir>/<safe_source_id>.json

    Returns the written path. atomic_write_json creates the parent dirs
    (parents=True, exist_ok=True) so no explicit mkdir is needed here.
    """
    base = artifact_dir if artifact_dir is not None else state_root / "llm_resp" / record.run_id
    target = base / f"{safe_source_id(record.source_id)}.json"
    atomic_write_json(target, record.to_dict())
    return target
