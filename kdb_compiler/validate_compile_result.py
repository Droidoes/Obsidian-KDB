"""validate_compile_result — schema-validates compile_result.json before any writes.

Fail-fast gate between the LLM output and the filesystem (D8, D18). If the
payload is malformed, nothing downstream runs; patch_applier only accepts
validated payloads.

Two validation layers, both accumulating (no short-circuit):
    1. JSON-Schema (jsonschema.Draft202012Validator) against
       schemas/compile_result.schema.json.
    2. Semantic checks — duplicate slugs within a source, summary/concept/
       article slug resolution, reserved-slug policy via paths.validate_slug.

Public API:
    validate(payload) -> list[str]   # empty = valid
    main() -> None                   # CLI entry point

CLI:
    kdb-validate [path.json]         # stdin if path omitted
    exit 0 — valid; exit 1 — invalid; exit 2 — runtime/config error
"""
from __future__ import annotations

import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from kdb_compiler import paths
from kdb_compiler.paths import PathError

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "compile_result.schema.json"


@cache
def _validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> list[str]:
    """Return list of human-readable errors. Empty list means valid."""
    errors: list[str] = []

    for err in _validator().iter_errors(payload):
        errors.append(f"[{err.json_path}] {err.message}")

    if not isinstance(payload, dict):
        return errors
    compiled_sources = payload.get("compiled_sources")
    if not isinstance(compiled_sources, list):
        return errors

    for idx, src in enumerate(compiled_sources):
        if isinstance(src, dict):
            _check_source(src, idx, errors)

    return errors


def _check_source(src: dict, idx: int, errors: list[str]) -> None:
    loc = f"$.compiled_sources[{idx}]"
    pages = src.get("pages") or []

    page_types: dict[str, str] = {}
    slug_counts: dict[str, int] = {}
    for p in pages:
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        pt = p.get("page_type")
        if isinstance(slug, str):
            slug_counts[slug] = slug_counts.get(slug, 0) + 1
            if isinstance(pt, str) and slug not in page_types:
                page_types[slug] = pt

    for slug, count in slug_counts.items():
        if count > 1:
            errors.append(f"[{loc}.pages] duplicate slug {slug!r} ({count} occurrences)")

    summary_slug = src.get("summary_slug")
    if isinstance(summary_slug, str):
        pt = page_types.get(summary_slug)
        if pt is None:
            errors.append(f"[{loc}.summary_slug] {summary_slug!r} not found in pages[]")
        elif pt != "summary":
            errors.append(
                f"[{loc}.summary_slug] {summary_slug!r} is page_type={pt!r}, expected 'summary'"
            )

    for field, expected in (("concept_slugs", "concept"), ("article_slugs", "article")):
        items = src.get(field) or []
        if not isinstance(items, list):
            continue
        for j, slug in enumerate(items):
            if not isinstance(slug, str):
                continue
            pt = page_types.get(slug)
            if pt is None:
                errors.append(f"[{loc}.{field}[{j}]] {slug!r} not found in pages[]")
            elif pt != expected:
                errors.append(
                    f"[{loc}.{field}[{j}]] {slug!r} is page_type={pt!r}, expected {expected!r}"
                )

    # Reserved slug policy — only surface the Reserved case here; pattern/length
    # violations are already covered by JSON-Schema, so we skip those to avoid
    # double-reporting.
    def _reserved_check(slug_value: Any, where: str) -> None:
        if not isinstance(slug_value, str):
            return
        try:
            paths.validate_slug(slug_value)
        except PathError as e:
            if "Reserved" in str(e):
                errors.append(f"[{where}] {e}")

    _reserved_check(summary_slug, f"{loc}.summary_slug")
    for field in ("concept_slugs", "article_slugs"):
        items = src.get(field) or []
        if isinstance(items, list):
            for j, slug in enumerate(items):
                _reserved_check(slug, f"{loc}.{field}[{j}]")
    for j, p in enumerate(pages):
        if isinstance(p, dict):
            _reserved_check(p.get("slug"), f"{loc}.pages[{j}].slug")


def main() -> None:
    """CLI. argv[1] = path, else stdin. Exit 0 (valid) / 1 (invalid) / 2 (runtime)."""
    try:
        if len(sys.argv) >= 2:
            raw = Path(sys.argv[1]).read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    errors = validate(payload)
    if errors:
        for msg in errors:
            print(msg)
        sys.exit(1)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
