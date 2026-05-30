# kdb_compiler/ingestion/pass1_caller.py
"""Pass-1 LLM call: fire the prompt at the configured provider/model;
parse the JSON envelope; raise on parse / schema failure.

Single retry on transient failures per Task #89 §5.1. The LLM call goes
through call_model.py; structured-output is requested via json_mode=True.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from kdb_compiler.call_model import ModelRequest, call_model, ModelResponse
from kdb_compiler.ingestion.pass1_prompt import build_pass1_prompt, PASS1_PROMPT_VERSION
from kdb_compiler.ingestion.pass1_schema import validate_llm_content, PASS1_SCHEMA_VERSION

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


class Pass1CallError(Exception):
    """Pass-1 call failed after all retries."""


def call_pass1(
    *, source_text: str, source_path: str, provider: str, model: str,
    max_retries: int = 1,
) -> Pass1CallResult:
    """Fire one Pass-1 LLM call. Returns parsed + validated envelope.

    Per Task #89 §5.1: retry once on schema validation failure; on second
    failure raise Pass1CallError. Caller (enrich.py) emits enrich_failed
    lifecycle event.
    """
    prompt = build_pass1_prompt(source_text=source_text, source_path=source_path)

    last_err: Exception | None = None
    raw_text = ""
    last_resp: ModelResponse | None = None
    for attempt in range(1, max_retries + 2):  # initial + retries
        req = ModelRequest(
            provider=provider, model=model, prompt=prompt,
            json_mode=True, temperature=0.0, max_tokens=4096,
        )
        try:
            resp = call_model(req)
            last_resp = resp
            raw_text = resp.text
            parsed = json.loads(raw_text)
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
            )
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            log.warning(f"Pass-1 attempt {attempt}/{max_retries+1} failed: {e}")
            continue

    raise Pass1CallError(
        f"Pass-1 call failed after {max_retries + 1} attempts: {last_err}"
    )
