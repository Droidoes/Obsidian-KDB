"""config — environment-driven settings for LLM calls.

Loads .env at import time (python-dotenv), then exposes a frozen Settings
singleton `settings`. No pydantic, no validation layer — plain os.getenv
reads with sensible defaults. Tests override by rebinding the singleton.

Usage:
    from kdb_compiler.config import settings
    settings.anthropic_api_key

    # in tests:
    monkeypatch.setattr("kdb_compiler.call_model.settings", Settings(...))
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    xai_api_key: str = ""
    qwen_us_api_key: str = ""
    ollama_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    deepseek_api_key: str = ""
    llm_timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            # The repo's .env uses XAI_GROK_API_KEY (vendor + product).
            xai_api_key=os.getenv("XAI_GROK_API_KEY", ""),
            # Alibaba DashScope intl/US endpoint — same env name as the
            # youtube-comment-chat project for consistency.
            qwen_us_api_key=os.getenv("QWEN_US_API_KEY", ""),
            # Ollama Cloud OpenAI-compat endpoint (provider=ollama-cloud).
            # Local Ollama (provider=ollama-local) does not require a key.
            ollama_api_key=os.getenv("OLLAMA_API_KEY", ""),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            # DeepSeek direct OpenAI-compat endpoint (provider=deepseek).
            # Replaces the Alibaba-routed access dropped 2026-05-15 for re-test.
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "300")),
        )


settings = Settings.from_env()
