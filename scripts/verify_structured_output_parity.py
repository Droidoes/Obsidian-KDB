"""verify_structured_output_parity — fire a minimal Pass-1-shaped JSON envelope
request at each candidate provider; record pass/fail.

Usage:
    python scripts/verify_structured_output_parity.py

Output:
    Per-provider pass/fail printed to stdout; manually transcribed by Task A.2
    into docs/task89-pass1-provider-parity-2026-05-26.md
"""
from __future__ import annotations

import json
import sys

from common.call_model import ModelRequest, call_model, ModelConfigError

# Candidate models for Pass-1 (subset of common/models.json that advertises
# structured-output support). Per-entry knobs handle provider-specific quirks:
#   extra_body: deepseek needs thinking disabled to prevent <think> tag pollution
#   use_completion_tokens: GPT-5+ family requires max_completion_tokens not max_tokens
CANDIDATES = [
    {"provider": "deepseek", "model": "deepseek-v4-flash",
     "extra_body": {"thinking": {"type": "disabled"}}, "use_completion_tokens": False},
    {"provider": "gemini", "model": "gemini-3.1-flash-lite",
     "extra_body": None, "use_completion_tokens": False},
    {"provider": "anthropic", "model": "claude-haiku-4-5-20251001",
     "extra_body": None, "use_completion_tokens": False},
    {"provider": "openai", "model": "gpt-5.4-mini",
     "extra_body": None, "use_completion_tokens": True},
    {"provider": "xai", "model": "grok-4.20-0309-non-reasoning",
     "extra_body": None, "use_completion_tokens": False},
]

PROMPT = """Given this source content, return a JSON envelope matching the
schema below.

SOURCE:
This is a test source about value investing principles, focusing on margin
of safety and circle of competence. Written by Joseph (2026-05-26).

Return ONLY a valid JSON object with these fields:
{
  "kdb_signal": "signal" or "noise",
  "domain": one of ["value-investing", "ai-ml", "other"],
  "source_type": one of ["blog", "post", "article", "other"],
  "author": string or null,
  "summary": string (1-3 sentences),
  "key_entities": list of strings,
  "key_themes": list of strings,
  "confidence": number 0.0 to 1.0
}
"""

def smoke(
    *,
    provider: str,
    model: str,
    extra_body: dict | None,
    use_completion_tokens: bool,
) -> tuple[bool, str]:
    req = ModelRequest(
        provider=provider,
        model=model,
        prompt=PROMPT,
        json_mode=True,
        temperature=0.0,
        max_tokens=1024,
        extra_body=extra_body,
        use_completion_tokens=use_completion_tokens,
    )
    try:
        resp = call_model(req)
        parsed = json.loads(resp.text)
        required = {
            "kdb_signal", "domain", "source_type", "author",
            "summary", "key_entities", "key_themes", "confidence",
        }
        missing = required - set(parsed.keys())
        if missing:
            return False, f"missing fields: {missing}"
        return True, f"ok ({resp.latency_ms}ms, {resp.input_tokens}/{resp.output_tokens} tok)"
    except json.JSONDecodeError as e:
        return False, f"non-JSON output: {e}"
    except ModelConfigError as e:
        return False, f"config error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main():
    results = []
    for c in CANDIDATES:
        ok, msg = smoke(**c)
        verdict = "PASS" if ok else "FAIL"
        print(f"{verdict}  {c['provider']:12s} {c['model']:30s}  {msg}")
        results.append((c["provider"], c["model"], ok, msg))
    fail_count = sum(1 for _, _, ok, _ in results if not ok)
    sys.exit(fail_count)


if __name__ == "__main__":
    main()
