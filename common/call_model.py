"""call_model — provider-routing proxy for LLM calls.

Single sync entry point: sends a ModelRequest to one of the supported
providers and returns a ModelResponse with the text, usage counts,
wall-clock latency, and provider/model echo (resp-stats metadata per
project memory).

Providers:
    anthropic    → native anthropic SDK (client.messages.create)
    openai       → openai SDK, standard endpoint
    gemini       → native google-genai SDK (json-mode only, minimal thinking)
    xai          → openai SDK, base_url=https://api.x.ai/v1
    alibaba      → openai SDK, base_url=https://dashscope-us.aliyuncs.com/compatible-mode/v1
    deepseek     → openai SDK, base_url=https://api.deepseek.com
    ollama-local → openai SDK, base_url=http://localhost:11434/v1 (or OLLAMA_BASE_URL)
    ollama-cloud → openai SDK, base_url=https://ollama.com/v1 (Ollama Cloud)
    zai          → openai SDK, base_url=https://api.z.ai/api/paas/v4 (Zhipu GLM)

No streaming; batch-compile workload. SDK httpx timeout handles pre-first-byte
hangs. Retry/backoff lives in call_model_retry.py, not here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

import anthropic
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

from common.config import settings

Provider = Literal[
    "anthropic", "openai", "gemini", "xai", "alibaba", "deepseek", "ollama-local", "ollama-cloud",
    "zai",
]


@dataclass
class ModelRequest:
    provider: Provider
    model: str
    prompt: str = ""
    system: str | None = None
    json_mode: bool = False
    # `temperature=None` OMITS the temperature kwarg entirely (the API applies
    # its own default), required by reasoning-family models like gpt-5.4-mini
    # that 400 on any non-default temperature. Threads from a nullable per-model
    # pool override (ModelSpec.temperature). Default 0.0 = deterministic.
    temperature: float | None = 0.0
    max_tokens: int = 4096
    # `use_completion_tokens=True` switches the openai-compat path from the
    # legacy `max_tokens` body field to `max_completion_tokens`, required by
    # GPT-5+ family models. No-op for the anthropic path.
    use_completion_tokens: bool = False
    # `extra_body` is forwarded to the openai-compat SDK as `extra_body=...`,
    # carrying provider-specific kwargs (e.g. Qwen's `{"think": false}`).
    # The gemini-native path reads `extra_body["thinking_level"]` specifically.
    extra_body: dict | None = None
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
        text, input_tokens, output_tokens, stop_reason, raw = _call_gemini(req)
    elif req.provider == "xai":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req, base_url="https://api.x.ai/v1", api_key=settings.xai_api_key,
        )
    elif req.provider == "alibaba":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req,
            base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
            api_key=settings.qwen_us_api_key,
        )
    elif req.provider == "deepseek":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req,
            base_url="https://api.deepseek.com",
            api_key=settings.deepseek_api_key,
        )
    elif req.provider == "ollama-local":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req, base_url=settings.ollama_base_url, api_key="ollama"
        )
    elif req.provider == "ollama-cloud":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req, base_url="https://ollama.com/v1", api_key=settings.ollama_api_key,
        )
    elif req.provider == "zai":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req,
            base_url="https://api.z.ai/api/paas/v4",
            api_key=settings.zai_api_key,
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
        "messages": [{"role": "user", "content": req.prompt}],
    }
    if req.temperature is not None:
        kwargs["temperature"] = req.temperature
    if req.system is not None:
        kwargs["system"] = req.system
    kwargs.update(req.extra)

    resp = client.messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    stop_reason = getattr(resp, "stop_reason", None)
    return text, resp.usage.input_tokens, resp.usage.output_tokens, stop_reason, resp


def _call_gemini(req: ModelRequest) -> tuple[str, int, int, str | None, Any]:
    if not settings.gemini_api_key:
        raise ModelConfigError("GEMINI_API_KEY not set")
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai_types.HttpOptions(timeout=settings.llm_timeout_seconds * 1000),
    )
    # Gemini 3.x uses thinking_level (NOT thinking_budget). flash-lite floor is
    # "minimal" (full-off unsupported) — the near-zero-reasoning value for our
    # extraction workload. Overridable via extra_body["thinking_level"].
    thinking_level = (req.extra_body or {}).get("thinking_level", "minimal")
    cfg_kwargs: dict[str, Any] = {
        "temperature": req.temperature,
        "max_output_tokens": req.max_tokens,
        "thinking_config": genai_types.ThinkingConfig(thinking_level=thinking_level),
    }
    if req.system is not None:
        cfg_kwargs["system_instruction"] = req.system
    if req.json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"
    # NB: req.extra (the openai-compat escape hatch) is intentionally NOT honored here —
    # GenerateContentConfig is a typed model with a different kwarg shape; gemini-native
    # knobs ride extra_body (e.g. thinking_level). Thread a typed gemini override here if needed.
    config = genai_types.GenerateContentConfig(**cfg_kwargs)

    resp = client.models.generate_content(
        model=req.model, contents=req.prompt, config=config,
    )
    text = resp.text or ""
    usage = resp.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
    # thinking tokens bill as output; include them (≈0 at minimal, but correct).
    output_tokens = (
        (getattr(usage, "candidates_token_count", 0) or 0)
        + (getattr(usage, "thoughts_token_count", 0) or 0)
    )
    stop_reason = None
    cands = getattr(resp, "candidates", None) or []
    if cands:
        fr = getattr(cands[0], "finish_reason", None)
        stop_reason = fr.value if fr is not None else None
    return text, input_tokens, output_tokens, stop_reason, resp


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

    model = req.model

    max_tokens_param = "max_completion_tokens" if req.use_completion_tokens else "max_tokens"
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        max_tokens_param: req.max_tokens,
    }
    if req.temperature is not None:
        kwargs["temperature"] = req.temperature
    if req.json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if req.extra_body:
        kwargs["extra_body"] = req.extra_body
    kwargs.update(req.extra)

    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    finish_reason = getattr(resp.choices[0], "finish_reason", None)
    return text, resp.usage.prompt_tokens, resp.usage.completion_tokens, finish_reason, resp
