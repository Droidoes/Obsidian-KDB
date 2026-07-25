# Task #119 options v1.2 — Codex review

**Date:** 2026-07-23  
**Reviewer:** Codex  
**Reviewed artifacts:**

- `2026-07-23-task119-options-r3-absorption-response-kimi.md`
- `2026-07-23-task119-normalization-boundary-architecture-options.md` v1.2

## Verdict

**GO WITH MINOR DOCUMENTATION CORRECTIONS.**

No architectural blocker remains. v1.2 is ready for Joseph's confirmation of:

> **Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling**

## Findings

### F1 — Medium: body wikilink targets are still described as “gated”

The architecture options document §4 says:

> Concept/article slugs and body wikilink targets are **not** Python-derivable — they stay model-authored and gated.

That wording contradicts both the verified current behavior and the new reference policy. Body target existence is not gated: an unresolvable model-authored target is preserved, KPI-visible, and nonfatal when no normalization authority exists.

Suggested replacement:

> Concept/article slugs remain model-authored and proposal-schema-gated. Body wikilink targets remain model-authored references governed by the reference policy above: preserve without normalization authority; rewrite only with unique authority; reject attempted-rewrite ambiguity.

This is a contract-wording correction, not an architecture change.

### F2 — Low: the absorption response still presents v1.1 as current

Although the opening erratum points to v1.2, the response metadata and `State of play` section still:

- identify v1.1 as the current artifact of record;
- describe the full form (a/b) plus option (1/2/3) choice as still open;
- retain wording from the superseded, contradictory reference-policy discussion.

The response should either:

1. be explicitly labeled as the historical v1.1 absorption response, with v1.2 identified as the current artifact; or
2. be refreshed to state that the architecture has converged and now awaits confirmation of the single recommended package.

## Prior-findings resolution

All four findings from the preceding Codex review are substantively resolved:

1. **Form (a) contradiction resolved.** The summary slug is optional and unconstrained in the proposal contract, so a missing or malformed raw value cannot reject the proposal. Form (b) remains the recommended design.
2. **Reference-policy contradiction resolved.** The policy now distinguishes preservation without authority from rejection when an attempted rewrite has multiple plausible referents.
3. **Structural taxonomy resolved.** Structural insufficiency is defined by the proposal schema, avoiding an incomplete hand-maintained error inventory.
4. **Schema-role wording resolved.** The v1.2 options document distinguishes the new prompt-facing proposal schema from the existing canonical validation shape.

## Disposition

The two remaining findings are minor documentation corrections and do not justify another architecture round.

After correction, Joseph can explicitly confirm:

> **Option 2 + form (b) + no links-to-current-summary + fail-closed alias handling**

That confirmation can close the Phase-1 decision gate, after which the decision should be captured in the task ledger and North Star before moving into the blueprint phase.
