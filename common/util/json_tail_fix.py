"""Root-preserving boundary-decode (#114): decode the ROOT JSON value of a
text, tolerating carrier noise before/after it.

Selection only — the accepted value is decoded exactly as written; no byte
is altered, and a nested value is NEVER carved out of its root (an array
root that fails to decode yields None, not its first element).

Rule: when the first non-whitespace character begins a JSON value
('{', '[', '"', digit, '-', or a letter-run matching a 'true'/'false'/
'null' literal in EITHER direction — prefix-of-literal ('nul' = attempted
root) or literal-led ('nulljunk' = root + noise tail); 'note:' is
prose), decode exactly there; on failure return None, never scan into a
nested '{'. Only when the text leads with prose does the search fall
back to the first '{' — first-'{' only, no scanning.
"""
from __future__ import annotations

import json


def _is_value_start(text: str, i: int) -> bool:
    c = text[i]
    if c in '{["-0123456789':
        return True
    if not c.isalpha():
        return False
    # A leading letter-run counts as a root candidate in BOTH directions:
    # it is a prefix of a literal ('nul' → attempted root) or starts with
    # one ('nulljunk' → root 'null' + adjacent-noise tail). Anything else
    # ('note:', 'nonsense') is prose → first-'{' fallback.
    j = i
    while j < len(text) and text[j].isalpha():
        j += 1
    tok = text[i:j]
    return any(
        text.startswith(lit, i) or lit.startswith(tok)
        for lit in ("true", "false", "null")
    )


def _decode_at(text: str, start: int) -> tuple[object, int, int] | None:
    try:
        value, end = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return value, start, len(text) - end


def parse_document_prefix(text: str) -> tuple[object, int, int] | None:
    """Return (value, prefix_chars, tail_chars) or None."""
    i = 0
    while i < len(text) and text[i].isspace():
        i += 1
    if i == len(text):
        return None
    if _is_value_start(text, i):
        # Root candidate at the first non-whitespace char — decode there or
        # fail. Never scan into a nested '{' on failure.
        return _decode_at(text, i)
    # Leading prose: the document is expected to start at the first '{'.
    start = text.find("{")
    if start == -1:
        return None
    return _decode_at(text, start)
