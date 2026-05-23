# Task #87 Blueprint v1 — Qwen Review

**Reviewer:** Qwen
**Date:** 2026-05-22
**Blueprint reviewed:** `docs/task87-promotion-belief-revision-eval-criteria-blueprint.md` (v1)

---

## 1. Convergence

The blueprint cleanly adapts the Task #75 predeclared-eval spine to the mutation-eval frame. The glossary (§2) is the load-bearing piece — by front-loading "mutation eval ≠ retrieval eval" and defining the pre/post-state assertion shape, it prevents reviewers (and future implementers) from sliding back into the retrieval frame. The operations roster (§3) is well-justified: O1 absorbs sequential sub-steps into one eval unit, O2 is separated for its distinct provenance-reconstruction logic, and O3 isolates the read-mostly path with its side-effect contract. The probe-set framework (§7) coverage axes are thorough — action-table cells, upgrade tiers, drift matrix, state transitions, and aliasing — and the YAML template gives #87.1 a concrete scaffold.

---

## 2. Findings

### Finding 1 — O3 is not a mutation op, and that's a frame risk

> §3.1 O3: "Belief-sensitive read" — Eval shape: "Query → expected resolution path + result. Side-effect: lazy `subject_slug` rewrite"

O3 is primarily a **read** operation with a conditional side-effect (lazy rewrite). The side-effect is secondary — it only fires when stale denormalized keys are encountered. This makes O3 structurally different from O1 and O2, which are pure mutations. The risk: by bundling O3 under the mutation-eval umbrella, the per-op criteria may inadvertently treat the side-effect as equally important as the read correctness, or vice versa.

More importantly, O3's eval shape is closer to retrieval-eval than mutation-eval. The primary assertion is "did the read return the right thing?" — the same frame as Task #75. The lazy rewrite is a minor mutation tacked onto a read. This doesn't mean O3 shouldn't exist; it means its criteria should be framed as **retrieval-eval with a mutation invariant** (the side-effect must not corrupt state), not as a full mutation-eval.

### Finding 2 — Demotion/retraction omission is structurally fine for v1 but the probe-set has a ghost entry

> §3.3: "Explicit retraction is **deferred** — it needs a UX surface (or a programmatic trigger contract) that v1 doesn't define."
> §7.1 state-machine transitions: `active → retracted` (via explicit retraction; deferred to V2 but probe scenario specified)

§3.3 says retraction is deferred. §7.1 asks for a probe scenario for `active → retracted`. This is a contradiction: you can't specify a probe scenario for an operation whose trigger contract doesn't exist yet. Either:
- (a) Remove the retraction probe scenario from §7.1 v1 coverage (defer fully to v2), or
- (b) Define a minimal programmatic trigger contract in this blueprint (e.g., "an operator flag or API call marks a Claim `retracted`") so the probe scenario has a defined input.

The same issue applies to `superseded → active` (revival), which is also deferred.

### Finding 3 — HW-6 (SUPERSEDES chain depth) has no Round 6 hedge mapping

> §6.1 HW-6: "SUPERSEDES chain depth > D for any Claim family"
> Review prompt §5 asks: "are the hedges from the Round 6 ontology-purpose discussion reflected?"

The three Round 6 hedges (§9.4.7) are: vanity-graph failure mode, stranded-summary failure mode, under-counted-Learn-surface failure mode. The review prompt's §5 lists three *different* Round 6 hedges (HW-a: productivity bottleneck, HW-b: audit-trail growth, HW-c: taxonomy fragmentation). These don't match §9.4.7's hedges.

Mapping the review prompt's HW-a/b/c against §6.1's HW-1..7:
- **HW-a (latency/throughput)** → No direct HW rule. HW-1/HW-2 are about drift rates, not latency. This is a **miss**.
- **HW-b (audit-trail growth)** → HW-6 (chain depth) is the closest proxy, but chain depth ≠ audit-trail size. Audit-trail growth is about `promotion_audit` record volume and `EVIDENCES` edge count, not SUPERSEDES depth. This is a **mis-shaping**.
- **HW-c (taxonomy fragmentation)** → No direct HW rule. Predicate-class canonicalization (D-83/84-5) is explicitly out of scope (§3.3), so HW-c has no owner in this blueprint. This is a **miss**, but arguably correct since canonicalization eval belongs elsewhere.

Additionally, the Round 6 hedges from §9.4.7 (vanity-graph, stranded-summary, under-counted-Learn-surface) are also not reflected in HW-1..7. The vanity-graph hedge ("if Promotion accepts M ≪ N over a sustained window, audit gate thresholds") is closest to HW-3 (corroboration threshold eagerness/laziness) but HW-3 is about the `reinforces` trigger rate, not the Analysis→Promotion acceptance funnel.

### Finding 4 — P-O1-6 (aggregate confidence) references an impl detail that's still OQ-gated

> §4.1 P-O1-6: "`Claim.confidence` equals the bounded-mean-with-recency-decay aggregation per D-83/84-12"

D-83/84-12 (aggregate-confidence + decay) is listed in §3.3 as part of O1's output contract. But the actual aggregation formula ("bounded-mean-with-recency-decay") is still under OQ-26 in the #83/#84 blueprint. Specifying that the eval criterion uses this formula *before* the formula is ratified creates a dependency inversion: the eval criterion assumes a design decision that's still open. The criterion should either reference the OQ explicitly (e.g., "per the aggregation formula resolved in OQ-26") or specify the eval shape more abstractly ("confidence is a deterministic function of all EVIDENCES.score values per the aggregation contract").

### Finding 5 — F-O1-4 is a meta-criterion, not a falsifiable criterion

> §4.1 F-O1-4: "Any of the §5 invariants fails verifier check after O1 completes."

This is not a single falsifiable criterion — it's a pointer to an external list that may grow. If §6 of the #83/#84 blueprint adds three new invariants tomorrow, F-O1-4 silently absorbs them. This is architecturally correct (you want all invariants to hold) but evaluation-weak: a failing test for F-O1-4 won't tell you *which* invariant broke without running the full verifier and parsing its output. Consider either:
- (a) Enumerating the §6 invariants that are *mutation-sensitive* (i.e., most likely to break during O1's write phase) as explicit F-criteria, and keeping F-O1-4 as a catch-all ("+ any other §6 invariant"), or
- (b) Specifying that F-O1-4 failure includes the verifier's violated-invariant list as part of the test failure output.

### Finding 6 — P-O3-4 references an undefined threshold

> §4.3 P-O3-4: "Default reads exclude Claims with `confidence < T` (per D-83/84-6 F2 decay threshold note)"

T is not defined anywhere in this blueprint or the #83/#84 blueprint — it's a "configurable, analogous to OQ-6" note. For a gate criterion that must hold on 100% of probe scenarios, the threshold T needs to be specified per scenario (each probe scenario declares its expected T) or the criterion needs to be reframed as "default reads exclude Claims below the configured decay threshold, and the threshold used is recorded in the scenario." Without this, P-O3-4 is not machine-checkable — it depends on an external config value.

### Finding 7 — §7.1 drift action-matrix cell coverage is incomplete

> §7.1 drift cells: four combinations of (fingerprint_drift, classification_drift)

The four boolean combinations are covered. But §4.1 P-O1-4 says "drift signals match the expected truth values **per the 4-cell matrix**" — this refers to the D-83/84-8 Part B drift action-matrix, which maps (fingerprint_drift, classification_drift) to a promotion-time disposition. The probe set covers the input cells but doesn't explicitly require coverage of the *output dispositions* (what action the system takes for each drift cell). A probe scenario could have the right drift bools but wrong downstream action and still pass the "drift cell coverage" check. The coverage requirement should include the disposition (e.g., "re-classify", "audit flag", "proceed") as an expected post-state field.

### Finding 8 — No HW rule for LINKS_TO → Claim divergence over time

The hybrid model (D-83/84-7) maintains both LINKS_TO and Claim spaces. Over time, if LINKS_TO edges accumulate for entity pairs that already have Claim families, the two layers diverge semantically. There's no HW rule watching for "what fraction of entity-pairs with active Claim families also have LINKS_TO edges for the same predicate?" — a metric that would signal whether the hybrid model is accumulating redundancy or whether the upgrade-from-LINKS_TO (O2) is firing too rarely. This is related to HW-3 (upgrade eagerness) but is a distinct metric: HW-3 watches the *rate of upgrade firings*; this would watch the *accumulated divergence* between layers.

---

## 3. Recommendations

**Recommendation 1 — Reframe O3 criteria as retrieval-eval with mutation invariant.**
Split O3's criteria into two classes: (a) read-correctness criteria (P-O3-1, P-O3-2, P-O3-3, P-O3-4, F-O3-1, F-O3-2, F-O3-3) framed as retrieval-eval (query → expected result), and (b) a single mutation-invariant criterion (P-O3-5 → "lazy rewrite, if triggered, preserves all §5 invariants"). This prevents the frame contamination noted in Finding 1.

**Recommendation 2 — Remove deferred probe scenarios from §7.1 v1 coverage.**
Delete the `active → retracted` and `superseded → active` rows from §7.1's state-machine transition coverage. Add a note: "Retraction and revival probe scenarios deferred to #87.1 v2, blocked on retraction/revival trigger contract definition." This resolves the contradiction in Finding 2.

**Recommendation 3 — Add an explicit HW rule for Analysis→Promotion funnel attrition (Round 6 vanity-graph hedge).**
Add a new HW rule (HW-8 or renumber):

| HW-# | Symptom | Suspected cause | Owning OQ |
|---|---|---|---|
| **HW-8** | Analysis surfaces N candidates; Promotion accepts M where M/N < **R%** over a rolling window of W promotions | Gate thresholds too strict (vanity-graph failure mode per §9.4.7) | NEW OQ (this blueprint) |

This directly addresses the Round 6 vanity-graph hedge ("if Analysis surfaces N candidates and Promotion accepts M ≪ N over a sustained window, audit gate thresholds").

**Recommendation 4 — Reframe P-O1-6 to reference the OQ, not a formula.**
Change P-O1-6 wording to: "`Claim.confidence` equals the deterministic aggregation of all current `EVIDENCES.score` values per the aggregation contract resolved in #83/#84 OQ-26; `Claim.confidence_spread` is computed per the same contract." This removes the dependency inversion noted in Finding 4.

**Recommendation 5 — Strengthen F-O1-4 with invariant enumeration or output contract.**
Amend F-O1-4 to: "Any of the §5 invariants fails verifier check after O1 completes. Eval failure output MUST include the list of violated invariants (from verifier output) for diagnostic clarity." This addresses Finding 5 without duplicating §6.

**Recommendation 6 — Make P-O3-4 scenario-scenario-scoped.**
Amend P-O3-4 to: "Default reads exclude Claims with `confidence < T_scenario`, where `T_scenario` is the decay threshold specified in the probe scenario's expected_post_state. The threshold used MUST be recorded and machine-checkable." This addresses Finding 6.

**Recommendation 7 — Add disposition coverage to §7.1 drift cells.**
Amend §7.1 drift cell coverage to: "Minimum 1 per cell, **including the expected promotion-time disposition** (re-classify, audit-flag, proceed) as part of expected_post_state." This addresses Finding 7.

---

## 4. Open questions

**OQ-R1 (from this review) — Should O3 be split into two operations?** O3 bundles tuple-granularity correctness (pure read) with lazy-rewrite (conditional mutation). If the lazy-rewrite side-effect grows in v2 (e.g., additional denormalization repairs), O3 may need to split. Flag this as a v2 structural question rather than resolving now.

**OQ-R2 — What is the eval surface for predicate-class canonicalization correctness?** D-83/84-5 mandates shared canonicalization infrastructure, and D-83/84-4 makes same-predicate matching depend on canonical-form equality. The blueprint (§3.3) says this "belongs in the shared-canonicalization-infra test discipline analogous to Task #74." But if canonicalization is wrong, O1/O2/O3 all produce wrong results. Should #87 include at least one integration-level criterion that *assumes* canonicalization is correct and fails if it isn't (e.g., "a candidate with a non-canonical predicate_class_raw still promotes correctly after canonicalization")? Or is the canonicalization eval surface entirely separate?

**OQ-R3 — How does the probe set handle non-determinism from the LLM extraction layer?** The candidate envelope is LLM-emitted (from the Analysis op). The eval criteria assume deterministic behavior given a fixed candidate. But in the full pipeline, the candidate itself is non-deterministic. Should the probe set include scenarios where the *same raw source text* produces *slightly different candidate envelopes* across runs, and eval whether the Promotion Contract handles both correctly? This is a different non-determinism axis than F-O1-1 (which tests classification given the same candidate).
