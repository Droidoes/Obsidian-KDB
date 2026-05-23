# Task #87 Blueprint v1 Review - Codex

## 1. Convergence

The main architectural move holds: #87 correctly treats #83/#84 as **mutation eval**, not retrieval eval. The pre-state + input -> expected post-state + verifier-clean invariant shape is the right spine for Promotion Contract / Belief Revision testing, and the O1/O2/O3 roster is mostly a useful compression of the upstream design.

The strongest parts are:

- O1 as an end-to-end candidate boundary. Testing classify/fingerprint/action/mutate separately would miss the actual correctness contract.
- O2 as a separate upgrade surface. The precondition "legacy LINKS_TO exists but no Claim family exists" is different enough from ordinary O1 promotion that it deserves its own probe family.
- The invariants-by-reference approach. #83/#84 §6 should remain canonical; #87 should not fork that contract.

The review issues below are mostly about making the eval criteria exact enough that a scenario can fail mechanically.

## 2. Findings

### F1 - O1 does not distinguish auto-promotion from human-review disposition

§4.1 says O1 applies the D-83/84-2 action and mutates state. But D-83/84-8 Part D explicitly has drift cells where the default action is **investigate before promotion** or **human review**. §7.1 also requires probe coverage for all four drift action-matrix cells.

That creates an eval ambiguity: for `fingerprint_drift=false, classification_drift=true` and `true,true`, is the expected post-state a graph mutation, a review-queue/audit record with no graph mutation, or both?

> P-O1-2 | D-83/84-2 action correctness | For each cell ... the expected mutation is applied.

For human-review cells, "expected mutation is applied" may be wrong. The Promotion Contract should probably classify, record audit/disposition, and stop before Claim/LINKS_TO mutation unless explicitly operator-approved.

**Recommendation:** Add an explicit O1 criterion for **promotion disposition correctness**: each drift matrix cell must produce the expected disposition (`auto_promote`, `auto_promote_with_note`, `investigate`, `human_review`) and only auto-promote dispositions may mutate the graph in default mode. Add a negative criterion: human-review dispositions create no Claim/LINKS_TO/SUPPORTS writes unless an approval input is present.

### F2 - O1 under-specifies topology-only actions for `no_counterpart` / `orthogonal`

The O1 output contract emphasizes Claim-space mutation:

> expected post-state (new/updated Claim nodes, EVIDENCES edges, Claim-Claim edges)

But D-83/84-2 says `no_counterpart` and `orthogonal` write ordinary topology (`LINKS_TO` + `SUPPORTS`) and create no Claim. A probe could pass "no Claim created" while failing to assert that the topology write actually happened.

**Recommendation:** Amend O1's output contract and P-O1-2 to include topology-only post-states: expected `LINKS_TO` / `SUPPORTS` writes for `no_counterpart`, `orthogonal`, and `qualifies_or_extends/refines_truth_conditions=false`; expected absence of Claim/EVIDENCES writes for those cells.

### F3 - O2 Tier 3 is allowed upstream but not positively evaluated here

D-83/84-7 Part B allows Tier 3:

> If neither Tier 1 nor Tier 2 yields a source, create the OLD Claim with no `EVIDENCES` edges; record attempted-and-failed reconstruction in operational metadata.

§4.2 covers Tier 1 and Tier 2 provenance labels, and F-O2-2 partially mentions Tier 3 only as a failure escape:

> OLD-Claim has zero EVIDENCES | Tier 3 was reached when Tier 1 or 2 was actually available

That leaves no positive pass criterion for a legitimate Tier 3 scenario, despite §7.1 requiring one scenario per tier.

**Recommendation:** Add P-O2-7: when Tier 1 and Tier 2 are both unavailable, O2 creates the OLD Claim with zero EVIDENCES **and** writes the required attempted-reconstruction metadata. Add F-O2-4: zero OLD-Claim EVIDENCES without Tier 3 metadata is a failure.

### F4 - Retraction is half in scope and half deferred

§3.3 says:

> Explicit retraction is deferred - it needs a UX surface (or a programmatic trigger contract) that v1 doesn't define.

But §7.1 requires a state-machine transition scenario:

> `active -> retracted` (via explicit retraction; deferred to V2 but probe scenario specified)

O3 also depends on retracted-Claim filtering, and D-83/84-11 defines edge cleanup once retraction occurs. The current blueprint can test reads over a pre-seeded retracted Claim, but it cannot test the mutation that turns `active` into `retracted` because no operation owns that transition.

This is the main operations-roster question. I would not leave it implicit.

**Recommendation:** Pick one of two clean shapes:

- Add **O4 Explicit retraction** with pre-state active Claim + retraction input -> post-state `state=retracted`, edges preserved, default reads filtered, no cascade.
- Or explicitly defer active->retracted mutation eval out of #87 v1 and narrow O3 to "fixtures may contain preexisting retracted Claims for read-filter testing."

If the probe set keeps an active->retracted transition, O4 is the cleaner contract.

### F5 - O3 is partly retrieval eval and partly mutation eval; the side-effect needs exact write-set assertions

O3 is mostly a read operation, with one mutation: lazy denormalized-key rewrite. That is acceptable as an observable consumer contract, but the eval criteria should separate "returned result" from "state changed."

Today P-O3-1 through P-O3-4 are retrieval-shaped. P-O3-5 is mutation-shaped. What is missing is write-set exactness:

- If stale denormalized keys exist, the read rewrites only the stale keys it touches.
- If no stale keys exist, the read performs zero writes.
- A LINKS_TO fallback read does not create a Claim family as a side effect.

**Recommendation:** Add O3 pass/fail criteria for lazy-rewrite exactness and no-op reads. This prevents O3 from becoming a hidden mutation surface beyond the D-83/84-9 incremental rewrite.

### F6 - Several criteria depend on config/time but do not require scenarios to declare them

P-O1-6 requires bounded-mean-with-recency-decay confidence correctness. F-O1-2 references corroboration threshold N. P-O3-4 references confidence threshold T. These are falsifiable only if the scenario declares the values and freezes time.

Otherwise, a failing implementation can claim a different N/T/tau/now basis.

**Recommendation:** Extend §7.2 scenario format with an `eval_config` block:

```yaml
eval_config:
  now: <fixed timestamp>
  corroboration_threshold_n: <int>
  confidence_decay_tau_days: <number>
  default_read_confidence_threshold_t: <number>
  confidence_map_version: <id>
```

This keeps thresholds tunable while making each probe mechanically checkable.

### F7 - Hedge-watch rules do not cover the Round 6 hedges named by the prompt

The prompt asks reviewers to map HW-1..HW-7 against:

- HW-a: Promotion gate becomes a productivity bottleneck
- HW-b: Belief Revision audit trail grows unwieldy
- HW-c: Predicate-class taxonomy fragments

The current HW list mostly monitors drift, confidence distribution, idempotency, supersession depth, and claim-id collisions. Those are useful, but they do not directly cover the three named hedges.

There is also a source mismatch: `docs/what-is-the-ontology-for.md` §9.4.7 currently names the Round 6 hedges as vanity-graph, stranded-summary, and under-counted-Learn-surface. The review prompt's HW-a/HW-b/HW-c wording is not the same source text.

**Recommendation:** Reconcile the hedge source before v2. Either update the prompt/blueprint to the actual §9.4.7 hedge names, or record that HW-a/HW-b/HW-c are derived operationalizations. Then add explicit HW rules:

- Promotion throughput: Analysis candidates surfaced vs Promotion candidates accepted, plus queue age / manual-review backlog.
- Audit growth: Claims, EVIDENCES, Claim-Claim edges, and audit records per promoted candidate over rolling windows.
- Predicate taxonomy fragmentation: raw predicate classes per canonical predicate, new canonical predicate rate, alias/canonicalization merge rate, and unresolved predicate-class clusters.

### F8 - Probe coverage misses intra-batch duplicate/conflict behavior

O1 idempotency covers retrying the same candidate against post-state. It does not cover two candidates in the same Analysis emission that engage the same family or are near-duplicates. D-83/84-10 explicitly leaves multi-candidate dedup as OQ-28, but #87's probe framework could still require at least one "sequential candidates touching same family" scenario so v1 behavior is observable.

**Recommendation:** Add a §7.1 coverage axis for sequential multi-candidate behavior: same family, same source/different quote, different source/same assertion, and conflicting candidates ordered A->B. The gate can assert v1's sequential semantics without solving future parallelism.

## 3. Recommendations

**Recommendation:** Add O1 disposition criteria so drift human-review cells assert "no graph mutation unless approved."

**Recommendation:** Add topology-only expected post-states to O1 for non-Claim action-table cells.

**Recommendation:** Add positive Tier 3 O2 criteria and make Tier 3 metadata machine-checkable.

**Recommendation:** Either add O4 explicit retraction or remove active->retracted mutation coverage from #87 v1.

**Recommendation:** Add O3 write-set exactness criteria for lazy rewrite and no-op reads.

**Recommendation:** Add scenario-level `eval_config` for N/T/tau/now/confidence-map values.

**Recommendation:** Reconcile HW hedge lineage and add explicit throughput, audit-growth, and predicate-fragmentation watch rules.

**Recommendation:** Add at least one sequential multi-candidate probe axis for OQ-28-adjacent behavior.

## 4. Open Questions

1. For human-review drift cells, is the eval expected to stop at a review artifact, or should #87 define a second input shape for "operator approved, now apply mutation"?
2. Is explicit retraction intended to ship with #83/#84 v1 behavior or only be represented as pre-seeded fixture state for read filtering?
3. Which Round 6 hedge vocabulary is authoritative for #87: the prompt's HW-a/HW-b/HW-c, or `what-is-the-ontology-for.md` §9.4.7 as currently written?
4. Should #87.1 include invalid pre-state scenarios, or should all verifier-invalid fixtures be excluded from eval by construction?
