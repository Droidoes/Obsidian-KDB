# Task #87 Eval Criteria Blueprint v1 — Holistic Review (Deepseek)

**Date:** 2026-05-22
**Reviewer:** Deepseek (per `docs/external-review-panel.md`)
**Blueprint reviewed:** `docs/task87-promotion-belief-revision-eval-criteria-blueprint.md` (v1)
**Format:** Standard review-prompt structure per `docs/task87-v1-review-prompt.md`

---

## 1. Convergence

The blueprint gets the structural bones right. The mutation-eval shape (§2.1–2.2) — pre-state + input → post-state + invariants — is the correct frame for evaluating #83/#84. The three-op compression of the 11-step pipeline (§3) is well-argued: O1 absorbs sequential stages that would be meaningless tested in isolation; O2 separates on structurally distinct preconditions; O3 captures the consumer-side observable behavior. The per-op criteria are falsifiable and the gate thresholds (100% pass, zero failures) are appropriately exacting for a predeclared eval contract.

The probe-set framework (§7) covers the right axes and the YAML template is machine-actionable. The invariant-reference strategy (§5) — pointer to #83/#84 §6, no duplication — is clean and avoids the classic two-source-of-truth drift problem.

---

## 2. Findings

### F1 — O3 is 80% retrieval-eval, not mutation-eval (Axis 1)

The blueprint frames all three ops as mutation-eval (§2.1, §3.1), but O3 (Belief-sensitive read) has only **one** mutation criterion (P-O3-5, the lazy-rewrite side-effect) against **four** retrieval criteria (P-O3-1 through P-O3-4). F-O3-1 through F-O3-3 are all retrieval-style failures — wrong resolution path, aliased miss, retracted-Claim leak.

This isn't necessarily *wrong* — O3 genuinely is a read operation with one side-effect. But the §2.1 framing:

> *"mutation ops have a state-transition contract (pre-state + input → expected post-state)"*

is misleading for O3. Under this framing, O3's expected post-state is identical to its pre-state *except* when a stale `subject_slug` rewrite fires. The retrieval contracts (P-O3-1–4) don't fit the state-transition shape; they fit the retrieval shape the blueprint explicitly says it's adapting away from.

**Recommendation:** Add an explicit note in §3.1 acknowledging that O3 is a **hybrid** op — its evaluable surface is predominantly retrieval, with a single mutation side-effect (lazy rewrite). The per-op table cell for O3 should label the eval shape as "Query → expected resolution path + result; side-effect eval on lazy rewrite" rather than implying it's fully mutation-shaped. This is cosmetic but prevents a reader from pattern-matching O3 as "the same kind of thing as O1/O2."

---

### F2 — Wall-clock dependency in P-O1-6 makes it unfalsifiable without clock injection (Axis 3)

P-O1-6 requires:

> *"Post-mutation Claim.confidence equals the bounded-mean-with-recency-decay aggregation per D-83/84-12 of all current EVIDENCES.score values."*

D-83/84-12 defines `w_i = exp(-t / tau)` where `t = now() - evidence_i.created_at`. In a real run, `now()` is wall-clock time at mutation. In an eval harness, `now()` is… the eval harness's wall-clock time, which drifts. A probe scenario written on Tuesday will produce a different expected `confidence` on Wednesday because the decay weights shift. The criterion is mathematically precise but **operationally unfalsifiable** without controlling the clock.

This isn't just a threshold-tuning concern (out of scope per the review prompt); it's a **contract-shape** concern. The expected post-state for O1 can't be statically precomputed if it depends on `now()`. The eval harness must either (a) inject a synthetic clock, (b) fix `now()` to the `created_at` timestamp of the most recent EVIDENCES edge, or (c) accept a tolerance window. None are specified.

**Recommendation:** Add an OQ or a §4.1 note that the eval harness for O1 **must control time** — either by fixing `now()` to a known reference timestamp embedded in the probe scenario, or by injecting a clock stub. This is a structural requirement on the #87.1 probe-set format, not a tuning detail. Suggested addition to the probe scenario template (§7.2):

```yaml
eval_clock: "2026-06-01T00:00:00Z"  # fixed reference time for decay-weighted computations
```

---

### F3 — Round 6 hedges (HW-a, HW-b, HW-c) have incomplete coverage in HW-1..HW-7 (Axis 5)

The prompt explicitly asks: are the three Round 6 hedges from `docs/what-is-the-ontology-for.md` §9.4.7 reflected in HW-1..HW-7? The mapping:

| Round 6 hedge | Nearest HW rule | Coverage |
|---|---|---|
| **HW-a:** Promotion gate becomes productivity bottleneck (latency/throughput) | None directly. HW-1 captures `classification_drift` rate, which is correctness, not throughput. | **Missing.** No HW rule monitors promotion latency or per-compile candidate throughput. |
| **HW-b:** Belief Revision audit-trail grows unwieldy (graph size growth) | HW-6 (SUPERSEDES chain depth) partially. No rule for total Claim count, EVIDENCES edge count, or graph-size growth rate. | **Partial.** Chain depth is a specific symptom of audit-trail bloat, not the general case. |
| **HW-c:** Predicate-class taxonomy fragments under real corpus stress (canonicalization watch) | None. §3.3 defers canonicalization eval to the Task #74 discipline. | **Missing, but explicitly out of scope.** Defensible if the Task #74 eval surface owns this. |

HW-a is the most concerning gap. The legacy OQs (§8 OQ-2) track threshold values for HW-1–HW-4, but none track latency. If the Promotion Contract adds 500ms of classifier + fingerprint recomputation per candidate and a compile run surfaces 20 candidates, the 10-second regression is invisible to HW-1..HW-7. The system would be "correct" (all P-O*N criteria pass) but operationally degraded.

**Recommendation:** Add **HW-8 — Promotion latency watch**:

| HW # | Symptom | Suspected cause | Owning OQ |
|---|---|---|---|
| **HW-8** | Per-candidate promotion latency > **L** ms (p50 or p95 across a compile run) | Classifier cost, fingerprint recomputation scope creep, or graph-walk depth under-estimated | New OQ (this blueprint) |

The threshold value can be calibrated empirically (out of scope for this review), but the *shape* — per-candidate latency with percentile aggregation — should be in the HW roster.

For HW-b: HW-6 covers chain depth but not total graph growth. Consider adding an HW rule for **total Claim + EVIDENCES edge count growth rate** over N compilations. This directly monitors the "audit-trail grows unwieldy" hedge.

---

### F4 — No coverage for "candidate engages a retracted Claim" scenario (Axis 3, §4.1)

O1's Pass/Fail criteria are indexed to the D-83/84-2 action table cells (§4.1 P-O1-2). But the action table has no row for: *counterpart is a Claim in `state=retracted`*. D-83/84-11 specifies that retracted Claims' edges are preserved and retracted Claims are filtered from default retrieval — but what does the Promotion Contract *do* when a new candidate's counterpart is retracted?

This is not a speculative edge case. The concrete scenario: Claim v1 (`active`) CONTRADICTS Claim v2 (`retracted`). New candidate arrives with `reinforces` polarity targeting the same predicate tuple. The counterpart it engages could be v2 (retracted) rather than v1 (active). What's the expected behavior? Promote against v1? Treat as `no_counterpart`? Skip because the counterpart is terminal?

**Recommendation:** Either (a) add a row to the D-83/84-2 action table for `retracted` counterpart status (goes back to #83/#84 blueprint), or (b) add a P-O1 criterion explicitly covering this case: *"candidate with retracted-Claim counterpart resolves to the nearest non-retracted Claim in the CONTRADICTS/SUPERSEDES chain, or treats as no_counterpart if no active member exists."* The probe-set framework (§7.1) should also add "retracted-Claim counterpart" as a coverage axis.

---

### F5 — No dedicated fail criterion for lazy-rewrite corruption (Axis 3, §4.3)

O3 has one pass criterion for the lazy-rewrite side-effect (P-O3-5) but no corresponding **fail** criterion. What happens if the rewrite:
- Produces a `claim_family_id` that doesn't parse (violates D-83/84-6 F1 delimiter guard)?
- Creates a `subject_slug` that doesn't match `Claim—ABOUT→Entity.canonical_id` (violates D-83/84-9 denormalized-key coherence)?
- Overwrites a `claim_id` in a way that breaks uniqueness?

These failures would be caught by the verifier (F-O1-4 covers invariant breaks for O1, but there's no equivalent for O3's side-effect). O3's fail criteria (F-O3-1 through F-O3-3) are all retrieval-path failures — none cover the mutation.

**Recommendation:** Add:

| F-O3-4 | Lazy-rewrite corruption | A read's side-effect rewrite produces a `claim_family_id`, `claim_id`, or `subject_slug` that violates D-83/84-6 F1 parseability, D-83/84-9 denormalized-key coherence, or Claim-node uniqueness. |

---

### F6 — Evidence cardinality edge cases not covered (Axis 3, §4.1)

P-O1-5 states: *"Each evidence[] entry in the input candidate becomes exactly one Source—EVIDENCES→Claim edge on promotion."* This is clear for the happy path, but the edge cases are silent:

- **Empty `evidence[]`:** Does promotion still create a Claim node with zero EVIDENCES edges? If so, the Claim has no sources — does the verifier accept this? (The verifier invariant says `analysis_emitted` EVIDENCES must have non-NULL `quoted_text` + `score`, but doesn't require at least one EVIDENCES edge.)
- **Duplicate `source_id` + `quoted_text`:** The idempotency contract (D-83/84-10) handles this via the uniqueness key `(source_id, claim_id, quoted_text_hash, provenance_type)`, but P-O1-5 should explicitly mention that duplicates are deduplicated rather than creating duplicate edges.

**Recommendation:** Extend P-O1-5 to: *"Each unique evidence[] entry (by the D-83/84-10 EVIDENCES uniqueness key) becomes exactly one Source—EVIDENCES→Claim edge. Duplicate entries are idempotently deduplicated. Promotion with empty evidence[] is permitted but the resulting Claim may have zero EVIDENCES edges — verifier behavior TBD."*

---

### F7 — Probe-set coverage missing multi-candidate sequential interaction (Axis 6, §7.1)

D-83/84-10 specifies that the Promotion Contract processes candidates **sequentially** — candidate N sees the state after candidate N-1's promotion. The probe-set framework (§7.1) has no coverage axis for this behavior. A probe set could have perfect per-cell coverage and still miss the case where candidate N's classification *changes* because candidate N-1's promotion created/updated a Claim that candidate N's classifier then reads.

This is the exact scenario that D-83/84-10's sequential-semantics commitment was designed to support. The eval should exercise it.

**Recommendation:** Add a coverage axis to §7.1:

> **By sequential-interaction scenario** (minimum 1): Two candidates in the same batch where candidate N's promotion-time classification differs from what it would have been against the pre-batch state, because candidate N-1's promotion changed the Claim space.

---

## 3. Recommendations (consolidated)

1. **Acknowledge O3 as hybrid** (§3.1) — mostly retrieval-eval with one mutation side-effect. Add a note to the ops table. (F1)

2. **Add clock-control mechanism** to the probe-set framework (§7.2) — a fixed `eval_clock` timestamp so P-O1-6's decay-weighted confidence is deterministically computable. (F2)

3. **Add HW-8 (promotion latency)** to the hedge-watch roster (§6.1) — covers the Round 6 HW-a hedge (productivity bottleneck) that HW-1..HW-7 currently miss. (F3)

4. **Add an O1 criterion or #83/#84 action-table row** for "candidate counterpart is a retracted Claim." (F4)

5. **Add F-O3-4** for lazy-rewrite corruption — the mutation side-effect of O3 needs a fail criterion. (F5)

6. **Tighten P-O1-5** to explicitly address empty `evidence[]` and duplicate deduplication. (F6)

7. **Add a sequential-interaction coverage axis** to §7.1 — two candidates where N-1's promotion changes N's classification. (F7)

---

## 4. Open Questions (raised by this review)

- **OQ-R1 — Retracted-Claim counterpart behavior.** What is the Promotion Contract's expected behavior when a new candidate's D-83/84-2 counterpart is a `retracted` Claim? Treat as no_counterpart? Walk to nearest active? Reject? This is currently unspecified in both #83/#84 and #87. (Filed from F4.)

- **OQ-R2 — Confidence eval precision.** With the clock-injection fix (F2), the decay-weighted confidence is deterministic. But floating-point equality across KuzuDB's C++ engine and Python's eval harness may produce off-by-ULP mismatches. Should P-O1-6 use a tolerance (e.g., `abs_diff < 1e-9`) rather than strict equality? Minor, but worth deciding before #87.1 writes probe scenarios with expected `confidence` values.

- **OQ-R3 — O3 lazy-rewrite vs verifier timing.** If the eval harness runs the verifier after O3 and the lazy rewrite hasn't been flushed (or is deferred), the verifier may report stale-`subject_slug` violations that are false positives. Should the eval harness force a flush before verifying, or should the verifier accept stale denormalized keys as `warning` not `error`?

---

**Summary:** The blueprint is structurally sound and the mutation-eval shape is the right adaptation of Task #75's pattern. The three findings that require v1 attention before ratification are: (1) the wall-clock dependency in P-O1-6, which breaks deterministic expected-post-state computation without clock injection; (2) the missing HW coverage for the Round 6 productivity-bottleneck hedge (HW-a); and (3) the unaddressed retracted-Claim counterpart scenario in O1. The remaining findings (O3 hybrid framing, lazy-rewrite fail criterion, evidence edge cases, sequential-interaction probe coverage) are specificity improvements that strengthen the contract but don't block ratification.
