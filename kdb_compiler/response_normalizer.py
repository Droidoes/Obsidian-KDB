"""response_normalizer — strict JSON extraction. No semantic repair.

Accepts only two shapes:
    1. bare JSON object text (starts with '{', ends with '}')
    2. single fenced block: ```json\\n{...}\\n``` or ```\\n{...}\\n```

Leading/trailing whitespace is stripped before checking. Any other shape
(prose before/after, multiple objects, regex-found substrings, etc.)
raises ValueError and is caught as extract_ok=False by compile_one.

Explicitly NOT handled here:
    - prose stripping / "find the first JSON-looking substring"
    - key renaming
    - enum coercion
    - field invention / defaulting
    - slug normalization
    - multi-object recovery

All of the above belong elsewhere: schema + semantic validation fail
honestly so the eval record captures the model's failure mode, rather
than masking it with Python cleanup.
"""
from __future__ import annotations

import json


def extract_json_text(raw_text: str) -> str:
    """Return the JSON text payload from the model response.

    Accepts a bare object or a single fenced block. Raises ValueError for
    every other shape (with a terse message suitable for eval records and
    error logs).
    """
    text = raw_text.strip()

    if text.startswith("```"):
        # Single fenced block. Strip opening fence (with optional lang tag),
        # then the trailing fence.
        first_newline = text.find("\n")
        if first_newline == -1:
            raise ValueError("response is a fence opener with no body")
        opening_fence = text[:first_newline]
        # Accept ``` or ```json or ```JSON; reject anything else after the
        # backticks (e.g. ```python).
        lang = opening_fence[3:].strip().lower()
        if lang not in ("", "json"):
            raise ValueError(f"unsupported fence language {lang!r}; expected 'json' or unlabelled")

        body_and_rest = text[first_newline + 1:]
        if not body_and_rest.endswith("```"):
            raise ValueError("response has opening fence but no closing fence at end")
        body = body_and_rest[:-3].rstrip()

        if "```" in body:
            raise ValueError("response contains multiple fenced blocks; expected exactly one")
        text = body.strip()

    if not (text.startswith("{") and text.endswith("}")):
        raise ValueError("response is not a bare JSON object or single fenced block")

    return text


def parse_json_object(raw_text: str) -> dict:
    """extract_json_text + json.loads. Raises ValueError on either failure.

    A non-dict top-level value (list, string, number) is rejected — the
    per-source contract is always an object.
    """
    json_text = extract_json_text(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e.msg} at line {e.lineno} col {e.colno}") from e
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object at top level, got {type(parsed).__name__}")
    return parsed
