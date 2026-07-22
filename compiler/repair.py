"""repair — rung-2 slug coercion for the per-source response (post-#115).

The #65 Repair stage is DELETED whole (#115): the list-pairing fixers and
the finding-driven dispatch died with the fields they repaired
(concept_slugs / article_slugs / summary_slug no longer exist in the LLM
contract, so the pairing defect class is structurally impossible).

What survives:

    * `coerce_slugs_and_propagate(parsed_json)` — rung-2 of the #106
      robustness ladder: collision-free rename of malformed slugs across
      page `slug` fields and body [[wikilinks]], gated by re-validation
      in compile_one. Body-only now: the top-level slug fields it used
      to propagate into are gone from the contract.

    * The pure body-wikilink extractor lives in
      `compiler.validate_source_response.body_wikilink_slugs`.
"""
from __future__ import annotations

import re

from common.paths import collapse_slug

# Whole-token wikilink matcher for the coercion rewrite. PERMISSIVE target group
# (must see malformed slugs like `Foo---Bar` that the strict extractor ignores),
# capturing #anchor and |display separately so they survive the rewrite.
_COERCE_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")


def _all_slug_values(pj: dict) -> set[str]:
    """Every distinct slug string present across the slug-bearing fields
    (post-#115: page `slug` + body [[wikilinks]] — nothing else exists)."""
    vals: set[str] = set()
    for pg in (pj.get("pages") or []):
        if not isinstance(pg, dict):
            continue
        if isinstance(pg.get("slug"), str):
            vals.add(pg["slug"])
        body = pg.get("body")
        if isinstance(body, str):
            vals.update(m.group(1) for m in _COERCE_WIKILINK_RE.finditer(body))
    return vals


def coerce_slugs_and_propagate(parsed_json: dict) -> bool:
    """Rung-2 (#106 spec section 4): build a collision-free rename map from
    `collapse_slug` over ALL present slug values, then apply it across page
    `slug` fields and body [[wikilinks]] (whole-token rewrite preserving
    |display / #anchor). Mutates `parsed_json` in place. Returns True iff
    anything changed.

    Refuses (no mutation, returns False) if any present slug is un-coercible
    (collapse_slug -> None for a value that is itself invalid) or if two
    distinct slugs would collapse to the same value / a collapse collides with
    an already-valid slug. The re-validation gate in compile_one is the final
    arbiter; this just keeps the payload internally consistent or untouched.
    """
    values = _all_slug_values(parsed_json)
    rename: dict[str, str] = {}
    for v in values:
        c = collapse_slug(v)
        if c is None:
            return False
        if c != v:
            rename[v] = c
    if not rename:
        return False
    targets = list(rename.values())
    unchanged = values - set(rename.keys())
    if len(set(targets)) != len(targets) or (set(targets) & unchanged):
        return False

    def _swap(s: object) -> object:
        return rename.get(s, s) if isinstance(s, str) else s  # type: ignore[arg-type]

    def _rw(m: re.Match) -> str:
        tgt, anchor, disp = m.group(1), m.group(2) or "", m.group(3) or ""
        return f"[[{rename.get(tgt, tgt)}{anchor}{disp}]]"

    for pg in (parsed_json.get("pages") or []):
        if not isinstance(pg, dict):
            continue
        pg["slug"] = _swap(pg.get("slug"))
        body = pg.get("body")
        if isinstance(body, str):
            pg["body"] = _COERCE_WIKILINK_RE.sub(_rw, body)
    return True
