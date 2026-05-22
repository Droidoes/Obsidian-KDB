# Task #83 + #84 - Codex Feedback on Relation Typology and Classifier Role

**Date:** 2026-05-22  
**Status:** Codex recommendation for the D-83/84-1 follow-up deliberation  
**Context:** `docs/task83-84-promotion-contract-belief-revision-blueprint.md`

## Recommendation

Redraw the typology slightly before going further.

The six proposed labels are the right raw materials, but they mix four
different things:

- **Novelty:** `asserts-new`
- **Logical relation:** `reinforces`, `contradicts`, `extends`
- **Temporal/version relation:** `supersedes`
- **Disposition/no-op:** `orthogonal`

That will get awkward because real cases can be both `extends` and
`contradicts`, or both `contradicts` and `supersedes`. Keep the language, but
model it as a two-step classifier:

```text
1. Counterpart status:
   no_counterpart | candidate_counterpart_found | orthogonal

2. Relation to counterpart:
   reinforces | contradicts | qualifies_or_extends | supersedes
```

Then derive the action:

| Case | Default action |
|---|---|
| `no_counterpart` | Write normal `LINKS_TO` + `SUPPORTS`; no Claim |
| `reinforces` | Add/aggregate support; no Claim in v1 unless threshold or explicit watch flag fires |
| `contradicts` | Upgrade to Claim |
| `qualifies_or_extends` | Upgrade only if it changes truth conditions of the prior claim |
| `supersedes` | Upgrade to Claim with temporal/version metadata |
| `orthogonal` | No belief-revision action; normal topology write may still happen |

The key change: **`extends` should not automatically mean "maybe Claim."** It
should mean: "does this merely add adjacent detail, or does it alter the prior
claim's truth conditions?" Only the second deserves Claim.

Examples:

- Adjacent detail: "Buffett also discusses insurance float" -> no Claim.
- Truth-condition refinement: "Buffett avoids tech unless it falls inside
  circle of competence" -> Claim-worthy.

## Classifier Role

Choose **(C) Mid - hints + confirmation**, with one hard rule:

> Analysis hints are advisory. Promotion-time classification is authoritative.

That preserves useful graph-walking work from Analysis ops, but keeps #83/#84
honest against current graph state. The shared-classifier implementation is the
right mitigation: same classifier module, two call sites, with promotion-time
revalidation required.

The candidate should carry both:

```text
analysis_time_relation_hint
promotion_time_confirmed_relation
```

If they differ, record `classification_drift: true` with the reason. That gives
the system auditability and a future eval surface.

## Short Form

**Typology:** keep the six terms, but split them into counterpart status +
semantic/temporal relation + derived action.

**Classifier role:** choose **C**, with promotion-time confirmation
authoritative and shared classifier code mandatory.
