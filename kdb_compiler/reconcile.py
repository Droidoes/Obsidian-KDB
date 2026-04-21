"""reconcile — post-validate repair of reconcilable defects in compile_result.

Consumes the measure_findings from validate_compile_result and mutates the
compile_result dict in place so downstream stages see a "clean" payload, as
if the LLM had emitted it correctly. Everything observable about what went
wrong lives in the validator findings + the returned ReconcileAction list
(captured in the run journal for quality scoring) — the compile_result
itself is made indistinguishable from a perfect response.

Architecture:
    * Registry of rules keyed by ValidationFinding.type.
    * reconcile(cr, findings) dispatches each finding to its rule.
    * Rules mutate the matching compiled_source entry in place.
    * Adding a new reconcilable finding type = adding one @register_rule
      function. Core dispatch never changes.

Invariants:
    * Only consumes findings with severity="measure". Passing gate findings
      is a programmer error (the run should have aborted before reconcile).
    * After reconcile returns, re-validating cr produces no measure findings
      of the reconciled types.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .validate_compile_result import ValidationFinding


class ReconcileError(Exception):
    """Raised when a finding can't be dispatched (unknown type, missing source)."""


@dataclass
class ReconcileAction:
    finding_type: str
    source_id: str | None
    detail: str              # human-readable one-liner for logs/journal


RuleFn = Callable[[dict, ValidationFinding], ReconcileAction]

_RULES: dict[str, RuleFn] = {}


def register_rule(finding_type: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator: registers a rule function for a given ValidationFinding.type."""
    def wrap(fn: RuleFn) -> RuleFn:
        if finding_type in _RULES:
            raise ReconcileError(f"Rule for {finding_type!r} already registered")
        _RULES[finding_type] = fn
        return fn
    return wrap


def registered_types() -> list[str]:
    """Introspection: what finding types does the reconciler handle today?"""
    return sorted(_RULES.keys())


# -------------------------------------------------------------------------
# Rules
# -------------------------------------------------------------------------

def _slug_field_for(page_type: str | None) -> str:
    if page_type == "concept":
        return "concept_slugs"
    if page_type == "article":
        return "article_slugs"
    raise ReconcileError(f"Pairing rule expected page_type concept|article, got {page_type!r}")


@register_rule("pairing_commission")
def _fix_pairing_commission(src: dict, finding: ValidationFinding) -> ReconcileAction:
    """Slug in concept_slugs/article_slugs with no matching page — remove it."""
    field = _slug_field_for(finding.page_type)
    current = src.get(field) or []
    if finding.slug in current:
        src[field] = [s for s in current if s != finding.slug]
        detail = f"removed {finding.slug!r} from {field}"
    else:
        detail = f"{finding.slug!r} already absent from {field} (idempotent)"
    return ReconcileAction(
        finding_type="pairing_commission",
        source_id=finding.source_id,
        detail=detail,
    )


@register_rule("pairing_omission")
def _fix_pairing_omission(src: dict, finding: ValidationFinding) -> ReconcileAction:
    """Page in pages[] whose slug is missing from concept_slugs/article_slugs — add it."""
    field = _slug_field_for(finding.page_type)
    current = src.get(field) or []
    if finding.slug not in current:
        src[field] = list(current) + [finding.slug]
        detail = f"added {finding.slug!r} to {field}"
    else:
        detail = f"{finding.slug!r} already present in {field} (idempotent)"
    return ReconcileAction(
        finding_type="pairing_omission",
        source_id=finding.source_id,
        detail=detail,
    )


# -------------------------------------------------------------------------
# Dispatch
# -------------------------------------------------------------------------

def reconcile(cr: dict, findings: list[ValidationFinding]) -> list[ReconcileAction]:
    """Apply registered rules for each finding. Mutates cr in place."""
    sources_by_id = {
        s.get("source_id"): s
        for s in cr.get("compiled_sources", [])
        if isinstance(s, dict) and isinstance(s.get("source_id"), str)
    }
    actions: list[ReconcileAction] = []
    for f in findings:
        rule = _RULES.get(f.type)
        if rule is None:
            raise ReconcileError(
                f"No reconcile rule for finding type {f.type!r} "
                f"(registered: {registered_types()})"
            )
        src = sources_by_id.get(f.source_id)
        if src is None:
            raise ReconcileError(
                f"Finding of type {f.type!r} references unknown source_id {f.source_id!r}"
            )
        actions.append(rule(src, f))
    return actions
