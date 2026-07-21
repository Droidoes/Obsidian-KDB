"""response_recovery — the Pass-2 recovery contract (#114).

One shared operation for the whole raw-response surface: loose unwrap,
strict-shape evaluation, and the 5-step selection-first ladder. Used by
both compile_one and tools/replay.py so a captured response yields ONE
verdict.

The principle: the LLM response is a carrier; the JSON document is the
payload. Recover the payload with maximum tolerance for carrier noise;
select, never edit (the one sanctioned byte normalization is
escape_stray_backslashes — content-preserving through decode). Failure is
declared only when no complete decodable document exists. ANY decoded
value is returned — including JSON null (recovered=True, parsed=None);
the schema gate judges content (spec v0.3.2/0.3.3). Callers branch on
`result.recovered`, never on `parsed is None`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from common.util.json_escape_fix import escape_stray_backslashes
from common.util.json_tail_fix import parse_document_prefix
from compiler import response_normalizer


@dataclass(frozen=True)
class RecoveryResult:
    recovered: bool
    extract_ok: bool
    parsed: object | None = None
    syntax_repaired: bool = False
    boundary_recovered: bool = False
    prefix_discarded_chars: int = 0
    tail_discarded_chars: int = 0
    error: str | None = None


def recover_json_response(raw_text: str) -> RecoveryResult:
    # Strict-shape verdict first — telemetry only, never gates.
    try:
        response_normalizer.extract_json_text(raw_text)
        extract_ok = True
    except ValueError:
        extract_ok = False

    candidate = response_normalizer.unwrap_response(raw_text)

    # 1. clean-decode original
    try:
        return RecoveryResult(recovered=True, extract_ok=extract_ok,
                              parsed=json.loads(candidate))
    except json.JSONDecodeError:
        pass

    # 2. boundary-decode original (root-preserving)
    hit = parse_document_prefix(candidate)
    if hit is not None:
        return RecoveryResult(
            recovered=True, extract_ok=extract_ok, parsed=hit[0],
            boundary_recovered=True,
            prefix_discarded_chars=hit[1], tail_discarded_chars=hit[2])

    # 3-5. escape-normalize, then clean-decode / boundary-decode normalized
    escaped = escape_stray_backslashes(candidate)
    if escaped != candidate:
        try:
            return RecoveryResult(recovered=True, extract_ok=extract_ok,
                                  parsed=json.loads(escaped),
                                  syntax_repaired=True)
        except json.JSONDecodeError:
            pass
        hit = parse_document_prefix(escaped)
        if hit is not None:
            return RecoveryResult(
                recovered=True, extract_ok=extract_ok, parsed=hit[0],
                syntax_repaired=True, boundary_recovered=True,
                prefix_discarded_chars=hit[1], tail_discarded_chars=hit[2])

    return RecoveryResult(
        recovered=False, extract_ok=extract_ok,
        error="no complete JSON document recoverable from response")
