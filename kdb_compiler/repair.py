"""repair — post-validate repair of reconcilable defects in compile_result.

Consumes the measure_findings from validate_compile_result and mutates the
compile_result dict in place so downstream stages see a "clean" payload, as
if the LLM had emitted it correctly. Everything observable about what went
wrong lives in the validator findings + the returned ReconcileAction list
(captured in the run journal for quality scoring) — the compile_result
itself is made indistinguishable from a perfect response.

Architecture:
    * Registry of rules keyed by ValidationFinding.type.
    * repair(cr, findings) dispatches each finding to its rule.
    * Rules mutate the matching compiled_source entry in place.
    * Adding a new reconcilable finding type = adding one @register_rule
      function. Core dispatch never changes.

    * `reconcile_body_links(parsed_json)` is unconditional normalization,
      not finding-driven. Sits in this module because it's the same
      "post-validate, pre-persist repair" purpose; called per-source
      after semantic_check passes and before downstream stages read
      parsed_json. See Task #57.

Invariants:
    * Only consumes findings with severity="measure". Passing gate findings
      is a programmer error (the run should have aborted before repair).
    * After repair returns, re-validating cr produces no measure findings
      of the repaired types.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .validate_compile_result import ValidationFinding
from .validate_compiled_source_response import body_wikilink_slugs


class RepairError(Exception):
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
            raise RepairError(f"Rule for {finding_type!r} already registered")
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
    raise RepairError(f"Pairing rule expected page_type concept|article, got {page_type!r}")


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


@register_rule("pairing_type_mismatch")
def _fix_pairing_type_mismatch(src: dict, finding: ValidationFinding) -> ReconcileAction:
    """Slug filed in concept_slugs/article_slugs whose page has a different
    page_type. The page object is authoritative (Task #65 / D45) — remove
    the slug from the list(s) it does not belong in. The matching
    pairing_omission finding (if present) adds it to the correct list.

    `reconcile_slug_lists()` is the primary, compile-time fix; this
    finding-driven rule is the validation-stage safety net for any payload
    that reached the validator un-reconciled (and satisfies the contract
    that every measure-severity finding type has a reconcile rule)."""
    correct_field = {"concept": "concept_slugs", "article": "article_slugs"}.get(
        finding.page_type
    )
    removed_from: list[str] = []
    for field in ("concept_slugs", "article_slugs"):
        if field == correct_field:
            continue
        current = src.get(field) or []
        if finding.slug in current:
            src[field] = [s for s in current if s != finding.slug]
            removed_from.append(field)
    if removed_from:
        detail = (f"removed {finding.slug!r} from {', '.join(removed_from)} "
                  f"(page is {finding.page_type})")
    else:
        detail = f"{finding.slug!r} already absent from mis-filed list(s) (idempotent)"
    return ReconcileAction(
        finding_type="pairing_type_mismatch",
        source_id=finding.source_id,
        detail=detail,
    )


# -------------------------------------------------------------------------
# Dispatch
# -------------------------------------------------------------------------

def reconcile_body_links(parsed_json: dict) -> int:
    """Body-wins normalization: each page's `outgoing_links` is replaced by
    the sorted set of slugs found as `[[slug]]` in its body. Enforces the
    bidirectional invariant by construction — after this, body and
    outgoing_links are guaranteed to agree exactly. Returns the number of
    pages whose `outgoing_links` field was modified.

    Mutates parsed_json in place. Tolerant: missing/non-list pages → 0;
    non-dict page entry → skipped; non-string body → empty link set."""
    pages = parsed_json.get("pages") or []
    if not isinstance(pages, list):
        return 0
    n_changed = 0
    for p in pages:
        if not isinstance(p, dict):
            continue
        body = p.get("body")
        new_links = sorted(body_wikilink_slugs(body)) if isinstance(body, str) else []
        prior = p.get("outgoing_links") or []
        prior_list = list(prior) if isinstance(prior, list) else []
        if prior_list != new_links:
            n_changed += 1
        p["outgoing_links"] = new_links
    return n_changed


def reconcile_slug_lists(parsed_json: dict) -> int:
    """Pages-win normalization: `concept_slugs` and `article_slugs` are
    rebuilt from the slugs of `pages[]` entries whose `page_type` is
    'concept' / 'article' respectively (sorted, deduplicated). Makes the
    slug lists consistent with `pages[]` by construction — after this,
    pairing_commission / pairing_omission / pairing_type_mismatch cannot
    arise: the page object is authoritative (Task #65 / D45, extending
    Task #57's body-wins doctrine from `outgoing_links` to the slug lists).
    Returns the count of slug-list fields actually changed (0, 1, or 2).

    Mutates parsed_json in place. Tolerant: missing/non-list `pages` → 0
    (no mutation); non-dict page entry → skipped; non-string slug → skipped.
    """
    pages = parsed_json.get("pages")
    if not isinstance(pages, list):
        return 0
    concepts: set[str] = set()
    articles: set[str] = set()
    for p in pages:
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        if not isinstance(slug, str):
            continue
        pt = p.get("page_type")
        if pt == "concept":
            concepts.add(slug)
        elif pt == "article":
            articles.add(slug)
    new_concepts = sorted(concepts)
    new_articles = sorted(articles)
    n_changed = 0
    if (parsed_json.get("concept_slugs") or []) != new_concepts:
        n_changed += 1
    if (parsed_json.get("article_slugs") or []) != new_articles:
        n_changed += 1
    parsed_json["concept_slugs"] = new_concepts
    parsed_json["article_slugs"] = new_articles
    return n_changed


def repair(cr: dict, findings: list[ValidationFinding]) -> list[ReconcileAction]:
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
            raise RepairError(
                f"No reconcile rule for finding type {f.type!r} "
                f"(registered: {registered_types()})"
            )
        src = sources_by_id.get(f.source_id)
        if src is None:
            raise RepairError(
                f"Finding of type {f.type!r} references unknown source_id {f.source_id!r}"
            )
        actions.append(rule(src, f))
    return actions
