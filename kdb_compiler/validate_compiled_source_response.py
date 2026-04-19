"""validate_compiled_source_response — per-source model output gate (M2).

Applied to ONE parsed response object from a single compile call, BEFORE
it is folded into compile_result.json. Complements validate_compile_result
(which validates the aggregate file) by enforcing the stricter per-call
contract: all 8 pageIntent fields required, non-empty
supports_page_existence, schema-only checks that compile_result can't
express because compile_result is lenient at aggregate level.

Two independent layers:
    1. validate(payload)               — JSON-Schema, accumulating
    2. semantic_check(payload, ...)    — post-schema, 4 semantic rules

CLI:
    kdb-validate-response [path.json] [--source-id <id>]
    exit 0 — valid; exit 1 — invalid; exit 2 — runtime/config error
"""
from __future__ import annotations

import argparse
import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "compiled_source_response.schema.json"


@cache
def _validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> list[str]:
    """JSON-Schema validation. Returns [] if valid.

    Errors formatted as '[<json_path>] <message>' matching
    validate_compile_result's convention.
    """
    return [f"[{err.json_path}] {err.message}" for err in _validator().iter_errors(payload)]


def semantic_check(payload: dict, *, source_id: str) -> list[str]:
    """Run AFTER schema validation passes. Returns [] if valid.

    Rules (in evaluation order, accumulating):
      1. payload['source_id'] == source_id                 (echoed verbatim)
      2. summary_slug appears in [p['slug'] for p in pages]
      3. exactly one page has page_type='summary' AND slug == summary_slug
      4. every page's supports_page_existence[] contains source_id
    """
    errors: list[str] = []

    echoed = payload.get("source_id")
    if echoed != source_id:
        errors.append(
            f"[$.source_id] expected {source_id!r}, got {echoed!r} "
            "(model must echo the provided source_id verbatim)"
        )

    pages = payload.get("pages") or []
    page_slugs = [p.get("slug") for p in pages if isinstance(p, dict)]

    summary_slug = payload.get("summary_slug")
    if summary_slug not in page_slugs:
        errors.append(
            f"[$.summary_slug] {summary_slug!r} does not appear in pages[].slug"
        )

    summary_page_matches = [
        p for p in pages
        if isinstance(p, dict)
        and p.get("slug") == summary_slug
        and p.get("page_type") == "summary"
    ]
    if len(summary_page_matches) != 1:
        errors.append(
            f"[$.pages] expected exactly one page with "
            f"page_type='summary' and slug={summary_slug!r}, "
            f"got {len(summary_page_matches)}"
        )

    for i, p in enumerate(pages):
        if not isinstance(p, dict):
            continue
        spe = p.get("supports_page_existence") or []
        if source_id not in spe:
            errors.append(
                f"[$.pages[{i}].supports_page_existence] must contain {source_id!r} "
                "(every page must attribute its existence to this source)"
            )

    return errors


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kdb-validate-response",
        description="Validate a single per-source compile response JSON "
                    "against compiled_source_response.schema.json + semantic rules.",
    )
    p.add_argument("path", nargs="?", help="Path to JSON file; reads stdin if omitted")
    p.add_argument(
        "--source-id",
        help="If provided, run semantic_check against this source_id too",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        raw = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    errors = validate(payload)
    if not errors and args.source_id and isinstance(payload, dict):
        errors.extend(semantic_check(payload, source_id=args.source_id))

    if errors:
        for msg in errors:
            print(msg)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
