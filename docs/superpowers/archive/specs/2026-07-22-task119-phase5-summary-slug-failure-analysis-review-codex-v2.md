# Task #119 Phase-5 failure analysis — Codex review v2

**Date:** 2026-07-23  
**Reviewer:** Codex  
**Reviewed document:** `docs/superpowers/archive/specs/2026-07-22-task119-phase5-summary-slug-failure-analysis.md`  
**Review basis:** Finding-by-finding absorption check against
`docs/superpowers/archive/specs/2026-07-22-task119-phase5-summary-slug-failure-analysis-review-codex.md`

**Verdict:** **GO-WITH-ONE-CHANGE.** The revised analysis substantively
absorbs all six blocking findings and all three accuracy corrections from
Codex R1. No architectural blocker remains.

## Finding

### F1 [Medium] — The #119 acceptance gate is ambiguous

Section 5 item 9 says:

> new clean comparison anchor + re-fire BOTH complete cohorts
> (deepseek-v4-flash + gpt-5.4-mini); #119 closes only when
> quarantine/retry/recovery KPIs are stable vs the new baseline

This does not define an executable comparison:

1. `deepseek-v4-flash` and `gpt-5.4-mini` are two members of one cohort, not
   two cohorts.
2. The document calls for a new comparison anchor but does not define how or
   when the “new baseline” is produced.
3. If the new baseline means the current pre-#119 behavior, undirected KPI
   stability would preserve the observed retry and quarantine rather than
   prove that #119 fixed them.

This ambiguity came from Codex R1 itself: its phrase “re-fire both complete
cohorts” was imprecise, and v1.1 inherited that wording.

Before #119 design ratification, choose and state one comparison strategy:

- **Strategy A — inherited Phase-0 baseline.** Reuse the original clean,
  zero-quarantine Phase-0 cohort as the baseline. From a clean post-#119
  comparison anchor, run one complete comparison cohort containing both
  models. Require quarantine/retry/recovery KPIs to satisfy the original
  stability gate.
- **Strategy B — paired pre/post #119 cohorts.** Run one clean pre-change
  baseline cohort and one clean post-change comparison cohort, each containing
  both models. In this design, the success criterion must be directional:
  the two observed sources compile without retry or quarantine, normalization
  telemetry records the deterministic resolution, and the remainder of the
  corpus introduces no new quarantine/retry/recovery regressions.

Under either strategy:

- pin the same corpus and corpus fingerprint;
- pin model/provider configuration and relevant prompt/version stamps;
- enumerate graph-KPI changes rather than hiding them; and
- distinguish failures fixed by #119 from unrelated stochastic or provider
  failures.

## R1 absorption verification

| R1 finding | v1.1 disposition | Result |
|---|---|---|
| F1 — Phase-5 gate failed | Failure stated plainly; Joseph's explicit temporary-production waiver recorded; original gate carried to #119 | **Absorbed**, subject to the acceptance-gate precision finding above |
| F2 — field symptom vs system defect | Root cause restated as canonical representation enforced before deterministic normalization | **Absorbed** |
| F3 — proposal and canonical contracts | Two logical contracts and the required processing order defined | **Absorbed** |
| F4 — deterministic authority, never fuzzy similarity | Role/provenance/registry/context authority required; ambiguity/collision/loss reject | **Absorbed** |
| F5 — strict equality moves after normalization | Exact normalized-summary invariant and post-canonicalization re-validation retained; alias behavior remains an explicit design decision | **Absorbed** |
| F6 — deterministic body-link resolution | Parsed wikilink targets only; aliases/headings preserved; prose/code unchanged; 1:1 mapping and collision rejection required | **Absorbed** |
| Accuracy 1 — quarantine is not deletion | Candidate commit is skipped; prior committed content survives | **Corrected** |
| Accuracy 2 — slug is operationally load-bearing | Wiki, graph, wikilink, manifest, and replay identity roles recorded | **Corrected** |
| Accuracy 3 — prevalence is unestimated | Observation limited to 1/36 per run; general prevalence explicitly unestimated | **Corrected** |

## Additional verification

- The three normalization-boundary options remain architecturally distinct and
  preserve their implementation-cost, compounding-risk, and reversibility
  differences.
- The contract-wide field audit, normalization telemetry, positive regression
  fixtures, and ambiguity/collision negatives are all included.
- The North Star update is correctly required before implementation; the
  #119 design itself remains explicitly unratified.
- The renamed `task119` artifact references are internally consistent.
- `git diff --check` reports no whitespace errors.

## Final disposition

Revise only the acceptance-gate wording before using v1.1 as the ratified #119
design seed. With that correction, Codex R1 is fully absorbed and the analysis
is ready to enter the #119 architecture-options cycle.
