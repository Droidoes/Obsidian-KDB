"""call_model_retry — minimal retry wrapper over call_model.

Uses the provider SDKs' native typed exceptions — no string matching,
no custom retryable-status taxonomies. 3 attempts, exponential backoff
with ±20% jitter, honors Retry-After headers when present.

Non-retryable errors (auth, 400, context length, etc.) bubble up
immediately; retrying them would never help.
"""
from __future__ import annotations

import random
import time

import anthropic
import openai

from kdb_compiler.call_model import ModelRequest, ModelResponse, call_model

_RETRYABLE: tuple[type[BaseException], ...] = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


def _parse_retry_after(exc: BaseException) -> float | None:
    """Return the Retry-After header (seconds) if present on the SDK exception."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def call_model_with_retry(
    req: ModelRequest,
    *,
    max_attempts: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 30.0,
) -> ModelResponse:
    """Call call_model with simple exponential backoff on retryable SDK errors."""
    for attempt in range(1, max_attempts + 1):
        try:
            return call_model(req)
        except _RETRYABLE as e:
            if attempt >= max_attempts:
                raise
            retry_after = _parse_retry_after(e)
            if retry_after is not None:
                sleep_s = min(max_backoff, retry_after)
            else:
                sleep_s = min(max_backoff, initial_backoff * (2 ** (attempt - 1)))
            sleep_s += random.uniform(0, 0.2 * sleep_s)
            time.sleep(sleep_s)
    raise RuntimeError("call_model_with_retry: unreachable")
