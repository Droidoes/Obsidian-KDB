# ingestion/enrich/pass1_caller.py
"""Pass-1 LLM call: fire the prompt at the configured provider/model;
parse the JSON envelope; raise on parse / schema failure.

Single retry on transient failures per Task #89 §5.1. The LLM call goes
through call_model.py; structured-output is requested via json_mode=True.

Task #108: Rung-1 of the #106-style repair ladder is wired here —
escape_stray_backslashes is applied on json.JSONDecodeError before falling
to retry. final_status / syntax_repaired / per-attempt aggregation fields
are emitted for sidecar telemetry.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from common.call_model import ModelRequest, call_model, ModelResponse
from common.util.json_escape_fix import escape_stray_backslashes
from ingestion.enrich.pass1_prompt import build_pass1_prompt, PASS1_PROMPT_VERSION
from ingestion.enrich.pass1_schema import (
    normalize_llm_content, validate_llm_content, PASS1_SCHEMA_VERSION,
)

log = logging.getLogger(__name__)


@dataclass
class Pass1CallResult:
    parsed: dict  # the validated envelope dict
    raw_response_text: str  # the raw LLM text response
    request_prompt: str  # the rendered prompt sent
    request_model: str
    request_provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int
    # Task #108: repair-ladder telemetry — parallel to Pass-2's fields.
    # Defaults keep callers that construct Pass1CallResult directly (tests,
    # enrich.py stubs) working without modification.
    final_status: str = "clean"      # clean | repaired | retried-and-repaired | quarantined
    syntax_repaired: bool = False    # True iff escape_stray_backslashes fired on winning attempt
    total_input_tokens: int = 0      # summed across all attempts that reached the model
    total_output_tokens: int = 0
    total_latency_ms: int = 0
    call_count: int = 0              # number of attempts that returned a ModelResponse
    final_attempt_index: int = 1     # 1-based index of the winning attempt


class Pass1CallError(Exception):
    """Pass-1 call failed after all retries."""

    def __init__(
        self,
        message: str,
        *,
        raw_response_text: str = "",
        request_prompt: str | None = None,
        request_model: str | None = None,
        request_provider: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        attempts: int = 0,
        # Task #108: aggregation fields for sidecar telemetry on the quarantine path.
        final_status: str = "quarantined",
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        total_latency_ms: int = 0,
        call_count: int = 0,
        final_attempt_index: int = 0,
    ) -> None:
        super().__init__(message)
        self.raw_response_text = raw_response_text
        self.request_prompt = request_prompt
        self.request_model = request_model
        self.request_provider = request_provider
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.attempts = attempts
        self.final_status = final_status
        self.total_input_tokens = total_input_tokens
        self.total_output_tokens = total_output_tokens
        self.total_latency_ms = total_latency_ms
        self.call_count = call_count
        self.final_attempt_index = final_attempt_index


def call_pass1(
    *, source_text: str, source_path: str, provider: str, model: str,
    max_retries: int = 1,
) -> Pass1CallResult:
    """Fire one Pass-1 LLM call. Returns parsed + validated envelope.

    Per Task #89 §5.1: retry once on schema validation failure; on second
    failure raise Pass1CallError. Caller (enrich.py) emits enrich_failed
    lifecycle event.

    Task #108: Rung-1 repair ladder — on json.JSONDecodeError, attempt
    escape_stray_backslashes before consuming a retry. final_status /
    syntax_repaired / per-attempt aggregation are emitted on both success
    and failure paths.
    """
    prompt = build_pass1_prompt(source_text=source_text, source_path=source_path)

    last_err: Exception | None = None
    raw_text = ""
    last_resp: ModelResponse | None = None

    # Task #108: per-loop accumulators (reached-model scope).
    total_input_tokens = 0
    total_output_tokens = 0
    total_latency_ms = 0
    call_count = 0            # attempts that returned a ModelResponse

    for attempt in range(1, max_retries + 2):  # initial + retries
        req = ModelRequest(
            provider=provider, model=model, prompt=prompt,
            json_mode=True, temperature=0.0, max_tokens=4096,
        )
        try:
            resp = call_model(req)
            last_resp = resp
            raw_text = resp.text

            # Accumulate tokens/latency for every attempt that reached the model.
            total_input_tokens += resp.input_tokens
            total_output_tokens += resp.output_tokens
            total_latency_ms += resp.latency_ms
            call_count += 1

            # Task #108 Rung-1: try raw parse; on JSONDecodeError apply
            # escape_stray_backslashes before falling through to retry.
            syntax_repaired = False
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                escaped = escape_stray_backslashes(raw_text)
                try:
                    parsed = json.loads(escaped)
                    syntax_repaired = True
                except json.JSONDecodeError as inner_e:
                    # Repair failed — let outer except handle retry/quarantine.
                    raise inner_e

            # Coerce benign shape deviations (e.g. >10 entity_search_keys) BEFORE
            # validation — don't burn a retry over a lossless, mechanical fix.
            normalize_llm_content(parsed)
            # STAGE 1 (Task #95): validate the LLM-owned content fields ONLY,
            # BEFORE stamping. This is the retry gate — bad content (off-enum
            # domain, >10 keys, missing other_reason) triggers another attempt.
            validate_llm_content(parsed)
            # Code-stamp the 3 code-owned scalar fields the LLM no longer emits.
            # The `override` block is constructed downstream by apply_overrides
            # (overrides.py), which is its sole producer.
            parsed["prompt_version"] = PASS1_PROMPT_VERSION
            parsed["model"] = model
            parsed["schema_version"] = PASS1_SCHEMA_VERSION

            # Derive final_status: winning attempt index is the decision point.
            # attempt==1 → clean or repaired; attempt>=2 → retried-and-repaired.
            if attempt == 1:
                final_status = "repaired" if syntax_repaired else "clean"
            else:
                final_status = "retried-and-repaired"

            return Pass1CallResult(
                parsed=parsed,
                raw_response_text=raw_text,
                request_prompt=prompt,
                request_model=model,
                request_provider=provider,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                latency_ms=resp.latency_ms,
                attempts=attempt,
                final_status=final_status,
                syntax_repaired=syntax_repaired,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_latency_ms=total_latency_ms,
                call_count=call_count,
                final_attempt_index=attempt,
            )
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            log.warning(f"Pass-1 attempt {attempt}/{max_retries+1} failed: {e}")
            continue
        except Exception as e:
            last_err = e
            log.warning(f"Pass-1 attempt {attempt}/{max_retries+1} failed: {e}")
            continue

    raise Pass1CallError(
        f"Pass-1 call failed after {max_retries + 1} attempts: {last_err}",
        raw_response_text=raw_text,
        request_prompt=prompt,
        request_model=model,
        request_provider=provider,
        input_tokens=(last_resp.input_tokens if last_resp is not None else 0),
        output_tokens=(last_resp.output_tokens if last_resp is not None else 0),
        latency_ms=(last_resp.latency_ms if last_resp is not None else 0),
        attempts=max_retries + 1,
        final_status="quarantined",
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_latency_ms=total_latency_ms,
        call_count=call_count,
        final_attempt_index=max_retries + 1,
    )
