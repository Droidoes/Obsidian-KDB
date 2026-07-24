"""validate_proposal_response — proposal-schema gate (#119, D-119).

Structural sufficiency for the per-source PROPOSAL (prompt 4.0.0+), applied
to the recovered parse BEFORE the normalization bridge. A violation here is
`structural_insufficiency` (retriable once). Semantic classes (summary count,
collisions, coercibility) are the bridge's, not this module's.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "proposal_response.schema.json"


@cache
def _validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> list[str]:
    """Proposal-schema validation. Returns [] iff structurally sufficient.

    Errors formatted as '[<json_path>] <message>' matching
    validate_compile_result's convention.
    """
    return [
        f"[{err.json_path}] {err.message}"
        for err in _validator().iter_errors(payload)
    ]
