# #123 Round 1 Synthesis — Codex Review and Vote

**Date:** 2026-07-25
**Reviewer:** GPT-5.6 / Codex
**Artifact reviewed:** [`2026-07-25-task123-round1-synthesis.md`](2026-07-25-task123-round1-synthesis.md)

## Vote

**APPROVE.**

I concur with D1–D8 as the basis for the vision document. The synthesis
accurately represents my Round-1 position. Joseph's final domain ruling is
architecturally coherent when treated as an explicit context-build constraint.

## Feedback to carry forward

1. **Keep the capability general.**

   `graph_search(query) -> ordered graph entities` is the general capability.
   Pass-1.5 is its first integration adapter, not its defining interface.
   Pass-1 summaries, keys, and mandatory context-build domain scope belong to
   that adapter rather than the consumer-neutral search contract.

2. **Preserve both domain-scope denominators.**

   Domain-empty requests should not count as selector failures under D3.
   However, the all-request domain-empty rate must remain visible as an
   end-to-end system outcome. Otherwise the accepted approximately 35% context
   starvation disappears from reporting.

3. **Make replay decisions auditable.**

   D6 should persist the selector model, route, prompt version/hash, query, and
   candidate-snapshot hash alongside the ordered selected slugs. Persisting
   slugs alone can reproduce the output but cannot audit the decision or prove
   what candidate population the selector saw.

4. **Separate identity validation from relevance evaluation.**

   Refine D7's wording: Kuzu is the runtime identity authority; the held-out
   truth set validates relevance. Candidate membership plus live-graph
   verification proves that a returned identity is eligible, active, and
   canonical. It does not prove that the identity is semantically relevant.

5. **Clarify FTS's T2 relationship.**

   FTS is never relevance authority or T3 machinery. It may later generate
   bounded T2 candidates through graph search when scale requires
   prefiltering. This reconciles “never the T2/T3 mechanism” with D4's
   at-scale candidate-generation role.

6. **Define the authority and snapshot for fat candidate text.**

   The vision must state whether fat text comes solely from graph-resident
   `Source.summary` or also from wiki bodies. If filesystem bodies participate,
   GraphDB is no longer the function's only implicit data input. Their
   authority, deterministic projection, bounds, and snapshot identity must
   therefore be explicit.

## Approval assessment

These points are requirements for precision in the vision, spec, and
blueprint—not blockers to accepting the Round-1 synthesis. The load-bearing
decisions are sufficiently coherent to proceed.

