"""Rung-1 of the #106 repair ladder: targeted, content-preserving escaping of
stray backslashes that are not valid JSON escapes (e.g. unescaped LaTeX `\\(`).

This is NOT a general JSON-repair tool. It only doubles a `\\` that JSON would
reject, so the backslash survives in the parsed string exactly as emitted —
preserving body content (math/markdown). Anything else stays broken and falls
to retry/quarantine. See spec section 3."""
from __future__ import annotations

import re

# A backslash that is NOT the start of a valid JSON escape:
#   valid escapes are \" \\ \/ \b \f \n \r \t  and  \uXXXX (4 hex)
# Negative lookahead for those; match the lone backslash so we can double it.
_STRAY_BACKSLASH = re.compile(r'\\(?![\"\\/bfnrt]|u[0-9a-fA-F]{4})')


def escape_stray_backslashes(text: str) -> str:
    """Double every backslash in `text` that is not a valid JSON escape lead.

    Content-preserving: valid escapes (`\\n`, `\\\\`, `\\"`, `\\uXXXX`, …) are
    left untouched; a stray `\\(` becomes `\\\\(` so `json.loads` decodes it
    back to a literal backslash. Idempotent on already-valid JSON text.
    """
    return _STRAY_BACKSLASH.sub(r"\\\\", text)
