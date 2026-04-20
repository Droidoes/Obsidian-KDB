"""call_model — provider-routing proxy for LLM calls.

Single sync entry point: sends a ModelRequest to one of
{anthropic, openai, gemini, ollama} and returns a ModelResponse with
the text, usage counts, wall-clock latency, and provider/model echo
(eval-ready metadata per project memory).

Providers:
    anthropic → native anthropic SDK (client.messages.create)
    openai    → openai SDK, standard endpoint
    gemini    → openai SDK, base_url=generativelanguage.googleapis.com/v1beta/openai/
    ollama    → openai SDK, base_url=http://localhost:11434/v1

No streaming; batch-compile workload. SDK httpx timeout handles pre-first-byte
hangs. Retry/backoff lives in call_model_retry.py, not here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

import anthropic
from openai import OpenAI

from kdb_compiler.config import settings

Provider = Literal["anthropic", "openai", "gemini", "ollama"]


@dataclass
class ModelRequest:
    provider: Provider
    model: str
    prompt: str = ""
    system: str | None = None
    json_mode: bool = False
    temperature: float = 0.0
    max_tokens: int = 4096
    extra: dict = field(default_factory=dict)


@dataclass
class ModelResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    provider: str
    attempts: int = 1
    stop_reason: str | None = None
    raw: Any = None


class ModelConfigError(ValueError):
    """Raised when provider config is missing (e.g. no API key) or unknown."""


def call_model(req: ModelRequest) -> ModelResponse:
    """Dispatch to the right provider. Sync/block. SDK errors propagate."""
    t0 = time.monotonic()

    if req.provider == "anthropic":
        text, input_tokens, output_tokens, stop_reason, raw = _call_anthropic(req)
    elif req.provider == "openai":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req, base_url=None, api_key=settings.openai_api_key
        )
    elif req.provider == "gemini":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.gemini_api_key,
        )
    elif req.provider == "ollama":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req, base_url=settings.ollama_base_url, api_key="ollama"
        )
    else:
        raise ModelConfigError(f"Unknown provider: {req.provider!r}")

    return ModelResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=int((time.monotonic() - t0) * 1000),
        model=req.model,
        provider=req.provider,
        stop_reason=stop_reason,
        raw=raw,
    )


def _call_anthropic(req: ModelRequest) -> tuple[str, int, int, str | None, Any]:
    if not settings.anthropic_api_key:
        raise ModelConfigError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.llm_timeout_seconds,
    )
    kwargs: dict[str, Any] = {
        "model": req.model,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "messages": [{"role": "user", "content": req.prompt}],
    }
    if req.system is not None:
        kwargs["system"] = req.system
    kwargs.update(req.extra)

    resp = client.messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    stop_reason = getattr(resp, "stop_reason", None)
    return text, resp.usage.input_tokens, resp.usage.output_tokens, stop_reason, resp


def _call_openai_compat(
    req: ModelRequest, *, base_url: str | None, api_key: str
) -> tuple[str, int, int, str | None, Any]:
    if not api_key:
        raise ModelConfigError(f"No API key configured for provider={req.provider!r}")
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=settings.llm_timeout_seconds,
    )

    messages: list[dict] = []
    if req.system is not None:
        messages.append({"role": "system", "content": req.system})
    messages.append({"role": "user", "content": req.prompt})

    # Gemini's OpenAI-compat endpoint requires a "models/" prefix on the model ID.
    if req.provider == "gemini" and not req.model.startswith("models/"):
        model = f"models/{req.model}"
    else:
        model = req.model

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }
    if req.json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    kwargs.update(req.extra)

    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    finish_reason = getattr(resp.choices[0], "finish_reason", None)
    return text, resp.usage.prompt_tokens, resp.usage.completion_tokens, finish_reason, resp
