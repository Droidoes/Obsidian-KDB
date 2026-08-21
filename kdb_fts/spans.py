"""spans — evidence-span proof (D10): anchor slice + fallback ladder. PURE (no I/O).

The controller philosophy (D-P2-3): the model POINTS (paragraph_id + head/tail
anchors), Python CUTS. Every returned text is a verbatim substring of the source,
so the substring proof holds by construction — the fallback ladder relaxes the
ANCHOR, never the PROOF.
"""
from __future__ import annotations

import re
import unicodedata


def validate_anchor(paragraph: str, anchor: str) -> int:
    """Occurrence count of anchor in paragraph (exact match)."""
    return paragraph.count(anchor)


def slice_span(paragraph: str, head: str, tail: str) -> str | None:
    """Slice the source span between two anchors; None if either anchor is not
    unique or the head does not precede the tail. Anchor-inclusive."""
    if not head or not tail:
        return None
    if paragraph.count(head) != 1 or paragraph.count(tail) != 1:
        return None
    hi = paragraph.index(head)
    ti = paragraph.index(tail)
    if ti < hi + len(head):  # tail must start at/after head ends
        return None
    return paragraph[hi:ti + len(tail)]


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _fold_with_offsets(text: str) -> tuple[str, list[int]]:
    """NFKC-fold char-by-char, recording each folded char's source offset.
    Whitespace runs collapse to a single space (offset = run start). NFKC is not
    length-preserving, so the offset map is the only sound way back to source."""
    folded: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(text):
        for nch in unicodedata.normalize("NFKC", ch) or "":
            if nch.isspace():
                if folded and folded[-1] == " ":
                    continue
                folded.append(" ")
                offsets.append(i)
            else:
                folded.append(nch)
                offsets.append(i)
    return "".join(folded), offsets


def _slice_by_offsets(paragraph: str, offsets: list[int], idx: int, length: int) -> str:
    return paragraph[offsets[idx]:offsets[idx + length - 1] + 1]


def _fuzzy_snap(paragraph: str, quote: str) -> str | None:
    """Tolerant token-gap match over the ASCII-alnum signature. Returns a verbatim
    source substring (the source range spanning the matched signature) or None."""

    def keep(ch: str) -> bool:
        return ch.isascii() and ch.isalnum()

    sig_chars: list[str] = []
    src_idx: list[int] = []
    for i, ch in enumerate(paragraph):
        if keep(ch):
            sig_chars.append(ch.lower())
            src_idx.append(i)
    p_sig = "".join(sig_chars)
    q_sig = "".join(ch.lower() for ch in quote if keep(ch))
    if not q_sig:
        return None
    idx = p_sig.find(q_sig)
    if idx == -1:
        return None
    start = src_idx[idx]
    end = src_idx[idx + len(q_sig) - 1] + 1
    return paragraph[start:end]


def locate_quote(paragraph: str, quote: str) -> str | None:
    """Fallback ladder (D-P2-3): exact → folded → fuzzy. Every rung returns a
    verbatim source substring or None. Rungs 2–3 take the first match without a
    uniqueness check (the LOCATION may bind to a different occurrence — accepted;
    the verbatim invariant is what matters)."""
    if paragraph.count(quote) == 1:
        return quote
    folded_p, offsets = _fold_with_offsets(paragraph)
    folded_q = _fold(quote)
    idx = folded_p.find(folded_q)
    if idx != -1:
        candidate = _slice_by_offsets(paragraph, offsets, idx, len(folded_q))
        if _fold(candidate) == folded_q:  # re-verify after unmapping
            return candidate
    return _fuzzy_snap(paragraph, quote)
