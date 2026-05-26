"""verify_structured_output_parity — fire a minimal Pass-1-shaped JSON envelope
request at each candidate provider; record pass/fail.

Usage:
    python scripts/verify_structured_output_parity.py

Output:
    Per-provider pass/fail printed to stdout + recorded to
    docs/task89-pass1-provider-parity-2026-05-26.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from kdb_compiler.call_model import ModelRequest, call_model, ModelConfigError

# Candidate models for Pass-1 (subset of kdb_benchmark/models.json that advertises
# structured-output support). Adjust based on registry state.
CANDIDATES = [
    ("deepseek", "deepseek-v4-flash"),
    ("gemini", "gemini-3.1-flash-lite"),
    ("anthropic", "claude-haiku-4-5"),
    ("openai", "gpt-5.4-mini"),
    ("xai", "grok-4-1-fast-reasoning"),
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

def smoke(provider: str, model: str) -> tuple[bool, str]:
    req = ModelRequest(
        provider=provider,
        model=model,
        prompt=PROMPT,
        json_mode=True,
        temperature=0.0,
        max_tokens=1024,
    )
    try:
        resp = call_model(req)
        parsed = json.loads(resp.text)
        required = {"kdb_signal", "domain", "source_type", "summary", "key_entities"}
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
    for provider, model in CANDIDATES:
        ok, msg = smoke(provider, model)
        verdict = "PASS" if ok else "FAIL"
        print(f"{verdict}  {provider:12s} {model:30s}  {msg}")
        results.append((provider, model, ok, msg))
    fail_count = sum(1 for _, _, ok, _ in results if not ok)
    sys.exit(fail_count)


if __name__ == "__main__":
    main()
