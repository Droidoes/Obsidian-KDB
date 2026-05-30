# kdb_compiler/ingestion/overrides.py
"""Post-LLM deterministic override layer (Task #89 §4).

Per D-89-3 §4.4: blacklist (force_noise) wins ties.
Per D-89-3 §4.5: LLM never sees the path lists.
Per D-89-3 §4.6 + Grok OQ-3: override block always emitted (null when no
  override fired) + reject_reason survival rule across overrides.
Per D-89-15: LLM runs on every in-scope source; this layer applies AFTER.
"""
from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath
from typing import Iterable


def build_override_block(
    llm_original: str, *,
    applied: str | None = None, rule: str | None = None,
    match: str | None = None, reject_reason_cleared: str | None = None,
) -> dict:
    """Single producer of the `override` audit block (Task #95).

    Every override block in the system is constructed here — apply_overrides
    (success path) + enrich.py's empty/failed paths — so there is one source of
    truth for the block's structure. `llm_original` is the model's pre-override
    kdb_signal; the other fields default to null (no override fired)."""
    return {
        "applied": applied,
        "rule": rule,
        "match": match,
        "llm_original": llm_original,
        "reject_reason_cleared": reject_reason_cleared,
    }


def _match_any(source_path: str, globs: Iterable[str]) -> str | None:
    """Return the first matching glob, or None. Match against POSIX-style
    vault-relative path (forward slashes only)."""
    path = str(PurePosixPath(source_path))
    for glob in globs:
        if fnmatch.fnmatch(path, glob):
            return glob
    return None


def apply_overrides(
    envelope: dict, *, source_path: str,
    force_signal: Iterable[str], force_noise: Iterable[str],
) -> dict:
    """Apply force_signal / force_noise overrides to a parsed envelope.

    Returns a new envelope dict with override applied (mutates `override`
    sub-dict and possibly `kdb_signal` + `reject_reason`).
    """
    llm_original = envelope["kdb_signal"]

    # Blacklist wins ties: check force_noise first.
    noise_match = _match_any(source_path, force_noise)
    signal_match = _match_any(source_path, force_signal) if not noise_match else None

    if noise_match is not None:
        envelope["kdb_signal"] = "noise"
        envelope["override"] = build_override_block(
            llm_original, applied="noise", rule="force_noise", match=noise_match,
        )
        # reject_reason survival: if LLM had emitted signal, synthesize a reject_reason
        if llm_original == "signal":
            envelope["reject_reason"] = (
                f"deterministic override via force_noise: {noise_match}"
            )
    elif signal_match is not None:
        envelope["kdb_signal"] = "signal"
        cleared = envelope["reject_reason"]
        envelope["override"] = build_override_block(
            llm_original, applied="signal", rule="force_signal", match=signal_match,
            reject_reason_cleared=cleared,
        )
        # reject_reason survival: if LLM had emitted noise + reject_reason, clear it.
        if llm_original == "noise":
            envelope["reject_reason"] = None
    else:
        envelope["override"] = build_override_block(llm_original)

    return envelope
