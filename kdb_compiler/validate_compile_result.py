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
    validate(payload) -> ValidationResult
    score_response(cr, result) -> ResponseScore | None   # stub, returns None
    main() -> None                                       # CLI entry point

CLI:
    kdb-validate [path.json]         # stdin if path omitted
    exit 0 — valid; exit 1 — invalid; exit 2 — runtime/config error

Gate vs measure split
---------------------
Findings carry a `severity`:
    * "gate"    — structurally broken or unreconcilable; must abort the run.
    * "measure" — reconcilable defect; surfaces as a finding for the quality
                  score and the reconcile stage, but does NOT abort.

All findings in this commit are "gate" (behavior preserved). Later commits
flip pairing-commission/omission to "measure" once reconcile.py is wired in.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from kdb_compiler import paths
from kdb_compiler.paths import PathError

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "compile_result.schema.json"


# -------------------------------------------------------------------------
# Dataclasses
# -------------------------------------------------------------------------

@dataclass
class ValidationFinding:
    type: str               # e.g. "pairing_commission", "duplicate_slug", "schema_violation"
    severity: str           # "gate" | "measure"
    detail: str             # human-readable one-liner including location path
    source_id: str | None = None
    page_type: str | None = None
    slug: str | None = None


@dataclass
class ValidationResult:
    gate_errors: list[ValidationFinding] = field(default_factory=list)
    measure_findings: list[ValidationFinding] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when there are no gate errors. Measure findings don't block."""
        return not self.gate_errors

    def detail_strings(self) -> list[str]:
        """All findings flattened to the legacy string list (gate first)."""
        return [f.detail for f in self.gate_errors] + [f.detail for f in self.measure_findings]


@dataclass
class ResponseScore:
    total: float                        # 0.0–1.0, higher = better
    dimensions: dict = field(default_factory=dict)
    penalties: list[dict] = field(default_factory=list)


def score_response(cr: dict, validation: ValidationResult) -> ResponseScore | None:
    """Score an LLM response on quality dimensions derived from validator findings.

    STUB — returns None. Real scoring lands with the M2 eval framework (see
    project_task5_eval_scoring_directions memory). When implemented, the score
    feeds per-call eval records so we can compare LLM models by pairing
    mismatch rate and other quality dimensions.
    """
    return None


# -------------------------------------------------------------------------
# Core validation
# -------------------------------------------------------------------------

@cache
def _validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(payload: Any) -> ValidationResult:
    """Return a ValidationResult. `.is_valid` is True iff no gate errors."""
    result = ValidationResult()

    for err in _validator().iter_errors(payload):
        result.gate_errors.append(ValidationFinding(
            type="schema_violation",
            severity="gate",
            detail=f"[{err.json_path}] {err.message}",
        ))

    if not isinstance(payload, dict):
        return result
    compiled_sources = payload.get("compiled_sources")
    if not isinstance(compiled_sources, list):
        return result

    for idx, src in enumerate(compiled_sources):
        if isinstance(src, dict):
            _check_source(src, idx, result)

    return result


def _check_source(src: dict, idx: int, result: ValidationResult) -> None:
    loc = f"$.compiled_sources[{idx}]"
    source_id = src.get("source_id") if isinstance(src.get("source_id"), str) else None
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
            result.gate_errors.append(ValidationFinding(
                type="duplicate_slug",
                severity="gate",
                detail=f"[{loc}.pages] duplicate slug {slug!r} ({count} occurrences)",
                source_id=source_id,
                slug=slug,
            ))

    summary_slug = src.get("summary_slug")
    if isinstance(summary_slug, str):
        pt = page_types.get(summary_slug)
        if pt is None:
            result.gate_errors.append(ValidationFinding(
                type="summary_slug_missing",
                severity="gate",
                detail=f"[{loc}.summary_slug] {summary_slug!r} not found in pages[]",
                source_id=source_id,
                slug=summary_slug,
            ))
        elif pt != "summary":
            result.gate_errors.append(ValidationFinding(
                type="summary_slug_wrong_type",
                severity="gate",
                detail=f"[{loc}.summary_slug] {summary_slug!r} is page_type={pt!r}, expected 'summary'",
                source_id=source_id,
                page_type=pt,
                slug=summary_slug,
            ))

    for field_name, expected in (("concept_slugs", "concept"), ("article_slugs", "article")):
        items = src.get(field_name) or []
        if not isinstance(items, list):
            continue
        for j, slug in enumerate(items):
            if not isinstance(slug, str):
                continue
            pt = page_types.get(slug)
            if pt is None:
                # Slug in list with no matching page of any type — reconcilable by deletion.
                # In this commit it remains gate; a later commit flips it to "measure".
                result.gate_errors.append(ValidationFinding(
                    type="pairing_commission",
                    severity="gate",
                    detail=f"[{loc}.{field_name}[{j}]] {slug!r} not found in pages[]",
                    source_id=source_id,
                    page_type=expected,
                    slug=slug,
                ))
            elif pt != expected:
                # Slug matches a page, but page's page_type is wrong — NOT reconcilable.
                # Stays gate permanently.
                result.gate_errors.append(ValidationFinding(
                    type="pairing_type_mismatch",
                    severity="gate",
                    detail=f"[{loc}.{field_name}[{j}]] {slug!r} is page_type={pt!r}, expected {expected!r}",
                    source_id=source_id,
                    page_type=pt,
                    slug=slug,
                ))

    def _reserved_check(slug_value: Any, where: str) -> None:
        if not isinstance(slug_value, str):
            return
        try:
            paths.validate_slug(slug_value)
        except PathError as e:
            if "Reserved" in str(e):
                result.gate_errors.append(ValidationFinding(
                    type="reserved_slug",
                    severity="gate",
                    detail=f"[{where}] {e}",
                    source_id=source_id,
                    slug=slug_value,
                ))

    _reserved_check(summary_slug, f"{loc}.summary_slug")
    for field_name in ("concept_slugs", "article_slugs"):
        items = src.get(field_name) or []
        if isinstance(items, list):
            for j, slug in enumerate(items):
                _reserved_check(slug, f"{loc}.{field_name}[{j}]")
    for j, p in enumerate(pages):
        if isinstance(p, dict):
            _reserved_check(p.get("slug"), f"{loc}.pages[{j}].slug")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

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

    result = validate(payload)
    if not result.is_valid:
        for f in result.gate_errors:
            print(f.detail)
        for f in result.measure_findings:
            print(f"[measure] {f.detail}")
        sys.exit(1)
    # Even on success, surface measure findings so operators can see them.
    for f in result.measure_findings:
        print(f"[measure] {f.detail}")
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
