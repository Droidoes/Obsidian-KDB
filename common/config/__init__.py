"""config — .env loading + late-bound env helpers for LLM calls (Task #121).

Loads .env at import time (python-dotenv, override=False). The frozen
Settings dataclass + `settings` singleton were deleted in #121: secrets are
resolved LATE at the call boundary via resolve_required_env() (plain
os.getenv function calls — monkeypatch.setenv-friendly), and the two D7
timeout knobs via llm_timeout_seconds() (connect/write/pool, default 120) and
llm_inactivity_timeout_seconds() (read-silence watchdog, default 900).

Usage:
    from common.config import (
        llm_inactivity_timeout_seconds, llm_timeout_seconds, resolve_required_env,
    )

    api_key = resolve_required_env(route.api_key_env, model=req.model, provider=provider)
    timeout = llm_timeout_seconds()

    # in tests:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from common.model_route import ModelConfigError


def _find_dotenv() -> Path | None:
    start = Path(__file__).resolve()
    for parent in [start, *start.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


_dotenv_path = _find_dotenv()
if _dotenv_path is not None:
    load_dotenv(dotenv_path=_dotenv_path, override=False)


def resolve_required_env(name: str, *, model: str, provider: str) -> str:
    """Return the value of env var `name`; missing/empty → ModelConfigError
    naming the env var + model + provider — NEVER the value."""
    value = os.getenv(name, "")
    if not value:
        raise ModelConfigError(
            f"{name} is not set (or is empty) — required for model={model!r} provider={provider!r}"
        )
    return value


def _positive_int_seconds_env(var: str, default: int) -> int:
    """Shared validation for the two timeout getters (D7): unset → default;
    non-integer or non-positive → ModelConfigError naming the variable."""
    raw = os.getenv(var)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ModelConfigError(
            f"{var} must be an integer, got {raw!r}"
        ) from None
    if value <= 0:
        raise ModelConfigError(
            f"{var} must be positive, got {value}"
        )
    return value


def llm_timeout_seconds() -> int:
    """LLM_TIMEOUT_SECONDS, default 120 — the connect/write/pool phases
    (getting the request out the door). Fails hard on a non-integer or
    non-positive value, naming the variable."""
    return _positive_int_seconds_env("LLM_TIMEOUT_SECONDS", 120)


def llm_inactivity_timeout_seconds() -> int:
    """LLM_INACTIVITY_TIMEOUT_SECONDS, default 900 — the read-silence watchdog:
    max seconds of socket silence on any single read before the call fails.
    NOT a total wall-clock deadline (a peer dripping bytes resets the clock).
    Fails hard on a non-integer or non-positive value, naming the variable."""
    return _positive_int_seconds_env("LLM_INACTIVITY_TIMEOUT_SECONDS", 900)
