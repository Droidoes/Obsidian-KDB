# Task #82 - Learn Architectural Options: Codex Feedback

**Date:** 2026-05-22  
**Status:** Codex recommendation for Round 6 Fork-A resolution  
**Context:** `docs/what-is-the-ontology-for.md` section 9.3.6 candidate selection

## Recommendation

Choose **candidate (a), but with candidate (b)'s engineering discipline**.

Do **not** make Hypothesis Promotion a fourth Learn mechanism. Conceptually,
that muddies the taxonomy: the three real Learn categories are the three kinds
of graph state that change:

1. **Belief revision** - what the graph believes.
2. **Identity refinement** - what the graph thinks entities are, excluding
   Task #74 canonicalization hygiene.
3. **Abstraction / principle induction** - what higher-order concepts, rules,
   or summaries the graph commits to.

But also do **not** let Promotion become "just an implementation detail." That
is the real danger. The right framing is:

> Hypothesis Promotion is not a Learn slot. It is a mandatory cross-cutting
> boundary contract that every Learn operation must pass through before graph
> state changes.

So I would proceed with an **(a+) resolution**:

```text
Round 6 adopts a 3-slot Learn taxonomy:
Belief Revision, Identity Refinement, Abstraction / Principle Induction.

Hypothesis Promotion is adopted as a first-class architectural boundary operator,
not as a fourth Learn mechanism. It owns the commit-back contract, provenance,
confidence gates, conflict checks, review thresholds, and predeclared evals.
No Analysis output may mutate graph state except through this operator.
```

That gives the project the clean ontology of candidate (a) and the anti-vanity
safeguard of candidate (b).

## Why Not Pure Candidate (b)

Reject pure candidate (b) because it mixes "type of state changed" with "gate
that authorizes change." Once that move is accepted, Forgetting has an equally
strong claim to become its own slot, then review, decay, retraction, and
provenance start wanting slot status too. That path bloats the taxonomy.

## Why Not Candidate (c)

Reject candidate (c) as the primary architecture. Gemini's version is useful as
implementation vocabulary, but not as the top-level taxonomy. "Logical Rule
Mining" and "Hierarchical Consolidation" are methods or committed forms; they
belong under **Abstraction / Principle Induction**, not beside Belief Revision
as peer categories.

## Suggested Next Step

1. Update section 9.4 to ratify **3 Learn mechanisms + first-class Promotion boundary
   operator**.
2. Add a dedicated follow-up task: **Hypothesis Promotion Contract**.
3. Make that task define:
   - input candidate shape from Analysis ops;
   - output mutation types: belief edge, identity split, abstraction node/rule;
   - confidence/provenance/supporting-path requirements;
   - conflict checks;
   - human-review thresholds;
   - predeclared eval criteria, mirroring Task #75's pattern.
4. Only after that, design the individual Learn mechanisms.

## Short Form

**Taxonomy = candidate (a). Governance = candidate (b). Implementation examples
from candidate (c) get folded under Abstraction.**
