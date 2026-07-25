"""call_model — provider-routing proxy for LLM calls.

Single sync entry point: sends a ModelRequest to a provider and returns a
ModelResponse with the text, usage counts, wall-clock latency, and
provider/model echo (resp-stats metadata per project memory).

Routing (Task #121): a request either carries an explicit ModelRoute
(authoritative — its api_call_type alone selects the handler, even when it
differs from the provider's registry row) or resolves one from the Class-B
registry below via provider_default(). api_call_type is the ONLY closed set
(openai_compat / anthropic / gemini); endpoint=None means the SDK's built-in
URL; api_key_env NAMES the env var whose value is resolved late at the call
boundary (never at import; the value never appears in errors). ollama-local
is the only no-auth row (dummy key "ollama"); no-auth is never
caller-declared.

Class-B registry (route-less calls):
    anthropic    → native anthropic SDK (client.messages.create)
    openai       → openai SDK, standard endpoint
    gemini       → native google-genai SDK (json-mode only, minimal thinking)
    xai          → openai SDK, base_url=https://api.x.ai/v1
    alibaba      → openai SDK, base_url=https://dashscope-us.aliyuncs.com/compatible-mode/v1
    deepseek     → openai SDK, base_url=https://api.deepseek.com
    ollama-local → openai SDK, base_url=http://localhost:11434/v1 (or OLLAMA_BASE_URL, late)
    ollama-cloud → openai SDK, base_url=https://ollama.com/v1 (Ollama Cloud)
    zai          → openai SDK, base_url=https://api.z.ai/api/paas/v4 (Zhipu GLM)

No streaming; batch-compile workload. The scalar SDK timeout
(LLM_TIMEOUT_SECONDS, default 120) still covers all httpx phases in P1 — the
connect/write/pool vs read-silence split lands in P3. Retry/backoff lives in
call_model_retry.py, not here; the OpenAI/Anthropic constructors pass
max_retries=2 explicitly (D8 — identical to today's SDK default, pinned
against upstream drift).
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

from common.config import llm_timeout_seconds, resolve_required_env
# ModelConfigError lives in common.model_route (so common.config can raise it
# without an import cycle) and is re-exported here — existing
# `from common.call_model import ModelConfigError` importers keep working.
from common.model_route import (
    ModelConfigError,
    ModelRoute,
    validate_provider_identity,
    validate_route,
)


@dataclass
class ModelRequest:
    # Free-form informational identity (D5) — validated canonical at dispatch;
    # the closed Literal was deleted in #121.
    provider: str
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
    # Explicit route (Class A) — authoritative when present, even if its
    # api_call_type differs from the provider's registry row. None → the
    # Class-B registry resolves the route from `provider` (the escape hatch
    # every current caller takes).
    route: ModelRoute | None = None


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


# Class-B registry — a FACTORY (per-request lambda invocation), not static
# data, so OLLAMA_BASE_URL resolves late (monkeypatch.setenv-friendly).
_PROVIDER_DEFAULTS: dict[str, Callable[[], ModelRoute]] = {
    "anthropic":    lambda: ModelRoute("anthropic", None, "ANTHROPIC_API_KEY"),
    "openai":       lambda: ModelRoute("openai_compat", None, "OPENAI_API_KEY"),
    "gemini":       lambda: ModelRoute("gemini", None, "GEMINI_API_KEY"),
    "xai":          lambda: ModelRoute("openai_compat", "https://api.x.ai/v1", "XAI_GROK_API_KEY"),
    "alibaba":      lambda: ModelRoute("openai_compat", "https://dashscope-us.aliyuncs.com/compatible-mode/v1", "QWEN_US_API_KEY"),
    "deepseek":     lambda: ModelRoute("openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "ollama-local": lambda: ModelRoute("openai_compat",
                                       os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                                       None),   # no-auth; dummy key below
    "ollama-cloud": lambda: ModelRoute("openai_compat", "https://ollama.com/v1", "OLLAMA_API_KEY"),
    "zai":          lambda: ModelRoute("openai_compat", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY"),
}


def provider_default(provider: str) -> ModelRoute:
    """The registry row for a route-less call. Unknown provider →
    ModelConfigError (before secret lookup or SDK construction)."""
    factory = _PROVIDER_DEFAULTS.get(provider)
    if factory is None:
        raise ModelConfigError(f"Unknown provider: {provider!r}")
    return factory()


def call_model(req: ModelRequest) -> ModelResponse:
    """Dispatch on the resolved route's api_call_type. Sync/block. SDK errors propagate."""
    t0 = time.monotonic()

    provider = validate_provider_identity(req.provider)  # first, always
    if req.route is not None:
        route = validate_route(req.route, provider=provider, allow_no_auth=False)
        allow_no_auth = False
    else:
        allow_no_auth = provider == "ollama-local"
        route = validate_route(
            provider_default(provider), provider=provider, allow_no_auth=allow_no_auth
        )
    # ollama-local needs no key, but the OpenAI SDK still requires a non-empty
    # string. Otherwise validate_route check 5 guarantees api_key_env is a str.
    api_key = "ollama" if allow_no_auth else resolve_required_env(
        route.api_key_env, model=req.model, provider=provider)

    if route.api_call_type == "openai_compat":
        text, input_tokens, output_tokens, stop_reason, raw = _call_openai_compat(
            req, base_url=route.endpoint, api_key=api_key
        )
    elif route.api_call_type == "gemini":
        text, input_tokens, output_tokens, stop_reason, raw = _call_gemini(req, api_key=api_key)
    elif route.api_call_type == "anthropic":
        text, input_tokens, output_tokens, stop_reason, raw = _call_anthropic(req, api_key=api_key)
    else:  # unreachable — validate_route closed the set
        raise ModelConfigError(
            f"provider {provider!r}: unknown api_call_type {route.api_call_type!r}"
        )

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


def _call_anthropic(req: ModelRequest, *, api_key: str) -> tuple[str, int, int, str | None, Any]:
    client = anthropic.Anthropic(
        api_key=api_key,
        timeout=llm_timeout_seconds(),
        # Explicit = today's SDK default (one logical call may issue up to 3
        # HTTP requests on retryable failures); pinned against upstream drift (D8).
        max_retries=2,
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


def _call_gemini(req: ModelRequest, *, api_key: str) -> tuple[str, int, int, str | None, Any]:
    # No max_retries here: google-genai has no such constructor kwarg — its
    # retry knob is HttpOptions.retry_options (default None = no SDK-internal
    # retries). D8 preserves exactly that.
    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=llm_timeout_seconds() * 1000),
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
        timeout=llm_timeout_seconds(),
        max_retries=2,  # explicit = today's SDK default; pinned against upstream drift (D8)
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
