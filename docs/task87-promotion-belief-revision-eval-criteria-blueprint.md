# Task #87 — Predeclared Eval Criteria for #83/#84 (Promotion Contract + Belief Revision) — Blueprint v1

**Status:** v1 — drafted 2026-05-22, pending external review
**Lineage:** Filed 2026-05-22 from #83/#84 blueprint v2 closeout (commit `01c6373`). Analog of Task #75 for step-3 ops, adapted for the **mutation-eval** shape of the Promotion Contract + Belief Revision.
**Reviewer panel:** Codex + Deepseek + Qwen (per `docs/external-review-panel.md`)
**Anchors:**
- `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v2 — the design this blueprint evaluates)
- `docs/task75-predeclared-eval-criteria-blueprint.md` (precedent for the predeclared-eval discipline; this blueprint adapts the spine)
- `docs/TASKS.md` #87 + planned #87.1 (probe-set curation)

---

## 0. TL;DR

The #83/#84 v2 blueprint is structurally complete (12 decisions ratified). This blueprint defines **what "working correctly" means** for the Promotion Contract + Belief Revision **before implementation begins** — the same predeclared-eval discipline Task #75 established for step-3 ops. Without it, implementation can't be objectively verified.

**Critical adaptation:** Task #75 was retrieval-eval ("did the op return the right thing?"). #87 is **mutation-eval** ("did the op make the right state change?"). The frame is **integration-test-shaped** — pre-state + input → expected post-state + invariants preserved — not benchmark-shaped.

**Three v1 operations**, three per-op predeclared criteria, seven hedge-watch rules with shaped thresholds (values TBD, calibrated empirically). Probe-set curation deferred to sub-task **#87.1**.

---

## 1. Context — why #87 exists, and what it does not do

### 1.1 The predeclared-eval discipline

Task #75 established that **success criteria for an architectural component ship before the component itself**. Reasoning: without predeclared criteria, implementation produces code without an objective measure of correctness, and "did this work?" becomes a post-hoc judgment call. Task #75's pattern is mirrored here for the Promotion Contract + Belief Revision.

The discipline is binding:

- #83/#84 implementation **MUST NOT** begin until #87 v2 is ratified.
- Implementation work that lands without satisfying #87's predeclared criteria is **regression-prone by definition** — no baseline to measure against.
- HW (hedge-watch) rules are the *operational* layer of the eval discipline; they fire during normal use and trigger architectural review.

### 1.2 What #87 covers

| Concern | Where it lives |
|---|---|
| What the system *does* (architecture) | `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v2) |
| What "working correctly" means (eval) | **This blueprint** |
| What scenarios test it (probe set) | **Sub-task #87.1** (deferred from this blueprint) |
| What invariants must hold post-mutation | **Reference** to #83/#84 §6 GraphDB contract delta (no re-litigation) |
| How to implement the architecture (impl) | Future implementation tasks (post-#87 ratification) |

### 1.3 What #87 explicitly does NOT do

- **Re-design the architecture.** Decisions D-83/84-1 through D-83/84-12 are ratified; this blueprint evaluates them, not re-opens them.
- **Re-litigate invariants.** §6 of the #83/#84 blueprint already lists the schema migration / snapshot / rebuild / verifier obligations. This blueprint references those; it doesn't restate them.
- **Solve probe-set curation.** Probe-set design is a separate-task effort (#87.1) of similar scope to #87 itself. This blueprint sets the *framework* for probe sets but defers the actual curation.
- **Specify implementation form.** Polymorphism / Python types / Cypher query patterns are implementation-task work, post-#87 ratification.

---

## 2. Glossary

### 2.1 "Mutation eval" vs "retrieval eval"

- **Retrieval eval** (Task #75 frame): the op consumes a query and returns a result. Eval asks "did the op return the right thing?" The shape is benchmark-with-known-correct-answers. Examples: PPR retrieval, community routing, typed traversal.
- **Mutation eval** (this blueprint's frame): the op consumes a request and **changes graph state**. Eval asks "did the op make the right state change?" The shape is integration-test-with-pre-and-post-state-assertions. Examples: promote candidate, upgrade-from-LINKS_TO, belief-sensitive read with side-effects.

The shift matters because the per-op contract is different: retrieval ops have an output contract; mutation ops have a **state-transition contract** (pre-state + input → expected post-state).

### 2.2 "Pre/post state assertion"

A test scenario specifies:

- **Pre-state:** the graph state before the op (entities, LINKS_TO, Claims, EVIDENCES, etc.)
- **Input:** what the op receives (candidate, query tuple, etc.)
- **Expected post-state:** what the graph should look like after the op
- **Invariants preserved:** which of the #83/#84 §6 invariants must hold post-mutation

A pass = post-state matches expected AND all invariants hold. A fail = post-state diverges OR an invariant breaks.

### 2.3 "Invariant preservation"

Drawn from #83/#84 §6 GraphDB contract delta:

- Every `Claim` has an `ABOUT` edge (no orphans).
- `Claim—ABOUT→Entity` targets exist (no dangling).
- `Source—EVIDENCES→Claim` sources exist (no dangling).
- `analysis_emitted` EVIDENCES rows have non-NULL `quoted_text` + `score`.
- Claim-Claim edges target existing Claims.
- Terminal `retracted` Claims have no `retracted → active` history; `SUPERSEDES` chains are acyclic.
- `claim_id` parseability per D-83/84-6 F1.
- Denormalized-key coherence per D-83/84-9 (`Claim.subject_slug` matches `Claim—ABOUT→Entity.canonical_id` or via `ALIAS_OF`).
- `claim_family_id` consistency (shared family → shared subject + predicate-class + scope).

Eval criteria reference this list rather than re-enumerate. The verifier (per the §6 delta) is the canonical mechanism for invariant checking; eval scenarios validate that *the op being tested* preserves them.

### 2.4 "Probe set"

A **curated collection of pre-state + input + expected-post-state scenarios** that exercises an op across its action-table cells, edge cases, and HW-rule trigger conditions. Probe-set curation for #87 is sub-task #87.1; this blueprint sets the *framework* for probe sets (what cells must be covered, what scenario shapes are required) but defers the actual scenario writing.

### 2.5 "Hedge-watch rule"

A predeclared **symptom → action** rule: if a measurable system property crosses a shaped threshold, suspect a specific architectural issue and trigger review. HW rules fire **during normal operation**, not just during eval — they make the system self-instrumenting. Threshold *shapes* are predeclared here; *values* are calibrated empirically post-implementation (some live in #83/#84's existing OQs — OQ-6, OQ-9, OQ-20, OQ-26, OQ-27, OQ-29).

### 2.6 "Gate threshold"

Predeclared pass/fail value for an op. Examples: "promotion idempotency rate must be 100% across the probe set" (gate-style), "fingerprint coverage of classifier inputs must be 100% by construction" (gate-style). Gate failure = op cannot ship.

---

## 3. Operations roster

Three operations, derived by **compressing the 11-step pipeline of #83/#84 into integration-test-sized ops** per advisor input. Each is an *evaluable mutation* — a unit with a clear pre-state + input + expected post-state contract.

### 3.1 The three operations

| # | Operation | What it does | Eval shape |
|---|---|---|---|
| **O1** | **Promotion pipeline** | Candidate → classify (D-83/84-3) → fingerprint (D-83/84-8) → action-matrix (D-83/84-8 Part D) → mutate (D-83/84-2 action via D-83/84-10 idempotency contract) | Pre-state + candidate envelope → expected post-state (new/updated Claim nodes, EVIDENCES edges, Claim-Claim edges); `promotion_audit` fields populated correctly. |
| **O2** | **Upgrade-from-LINKS_TO** | `LINKS_TO` + first contradiction (or other promotion trigger) → Claim creation with three-tier provenance reconstruction per D-83/84-7 Part B + ABOUT-authoritative binding per D-83/84-9 | LINKS_TO pre-state + contradiction-candidate → expected Claim post-state with `provenance_type` correctly set per tier (`analysis_emitted` for new evidence; `reconstructed_from_run_payload` or `reconstructed_from_supports_overlap` for OLD claim evidence); denormalized keys correct. |
| **O3** | **Belief-sensitive read** | Tuple `(subject, predicate_class, scope)` → Claim-space resolution if Claim family exists; LINKS_TO fallback otherwise (per D-83/84-7 Part A amended) | Query → expected resolution path + result. Side-effect: lazy `subject_slug` rewrite per D-83/84-9 (when stale denormalized keys are encountered). |

### 3.2 Rationale for this cut

- **O1 absorbs four sub-stages** (classify, fingerprint, action-matrix, mutate) into one eval-able unit because their contract is sequential and atomic at the candidate level. Testing them independently fragments the contract — the post-state of the whole pipeline is the meaningful thing to assert.
- **O2 is separated** because its precondition (existing `LINKS_TO` with no prior Claim family) is structurally different from O1 (which may or may not have an existing Claim family). The provenance-reconstruction logic (Tier 1 / 2 / 3) is distinct enough to deserve its own eval surface.
- **O3 is separated** because belief-sensitive reads are read-mostly with a side-effect (lazy rewrite per D-83/84-9). The read-path correctness rule (tuple-granularity per D-83/84-7 Part A amended) is the load-bearing contract, separate from mutation.

### 3.3 What this roster does NOT commit to

- **Predicate-class canonicalization** (D-83/84-5) is **not** in this roster. It belongs in the shared-canonicalization-infra test discipline analogous to Task #74. The Promotion pipeline depends on it being correct, but its eval surface is separate from #87.
- **Aggregate-confidence** (D-83/84-12) is a *checked invariant* on O1's output, not a separate op. It runs as a post-step in O1 (when EVIDENCES lands or is updated) and its correctness is asserted as part of O1's expected post-state.
- **Decay** (D-83/84-12) is **deferred** — it needs a scheduler/tick mechanism that's out of scope for v1 #83/#84.
- **Explicit retraction** is **deferred** — it needs a UX surface (or a programmatic trigger contract) that v1 doesn't define.
- **SUPERSEDES revival cascade** (D-83/84-11) is **deferred** — it's an opt-in operator that only fires under specific conditions; not v1 eval-blocking.

---

## 4. Per-op predeclared criteria

### 4.1 O1 — Promotion pipeline

**Input contract:**

- A candidate envelope conforming to D-83/84-8 + #83/#84 §4 schema (post-restructure to `evidence[]` objects).
- Current graph state (read-only at classify/fingerprint stages; written at mutate stage).

**Output contract:**

- Post-state graph mutation per the D-83/84-2 action determined by promotion-time classification.
- `promotion_audit` record (per D-83/84-8 Part D) including `fingerprint_drift`, `classification_drift`, `drift_explanation`.
- Idempotency: re-running O1 with the same candidate against the post-state is a no-op (per D-83/84-10).

**Pass criteria:**

| P-O1-1 | Action-matrix determinism | Given identical (pre-state, candidate), promotion-time classification produces the same `analysis_classification` (counterpart_status + relation_kind + sub-flag). |
| P-O1-2 | D-83/84-2 action correctness | For each cell of the D-83/84-2 action table (no_counterpart / reinforces / contradicts / qualifies-with-truth / qualifies-without-truth / supersedes / orthogonal), the expected mutation is applied. |
| P-O1-3 | Idempotency on retry | Re-running O1 with the same candidate against the post-state produces zero new writes (verified by uniqueness-constraint checks per D-83/84-10). |
| P-O1-4 | Drift signals correct | For probe scenarios with graph mutations between analysis-time and promotion-time, `fingerprint_drift` and `classification_drift` match the expected truth values per the 4-cell matrix. |
| P-O1-5 | Evidence cardinality | Each `evidence[]` entry in the input candidate becomes exactly one `Source—EVIDENCES→Claim` edge on promotion. |
| P-O1-6 | Aggregate confidence correctness | Post-mutation `Claim.confidence` equals the bounded-mean-with-recency-decay aggregation per D-83/84-12 of all current EVIDENCES.score values; `Claim.confidence_spread` equals the unweighted stdev. |

**Fail criteria:**

| F-O1-1 | Classification non-determinism | Same (pre-state, candidate) yields different classifications across runs (without graph state change). |
| F-O1-2 | Action-table violation | A `contradicts` candidate skips Claim creation (or `reinforces` triggers Claim creation below threshold N). |
| F-O1-3 | Idempotency violation | Retry produces duplicate writes (new Claim with same `claim_id`, or duplicate EVIDENCES rows on the same (source_id, claim_id, quoted_text_hash, provenance_type) key). |
| F-O1-4 | Invariant break post-mutation | Any of the §5 invariants (referenced from #83/#84 §6) fails verifier check after O1 completes. |

**Gate threshold:**

- P-O1-1 through P-O1-6 must hold on **100% of probe scenarios** for #87 ratification.
- F-O1-1 through F-O1-4 must produce **zero failures** on the probe set.

### 4.2 O2 — Upgrade-from-LINKS_TO

**Input contract:**

- An existing `LINKS_TO` edge with no corresponding Claim family.
- A candidate envelope (typically `contradicts` polarity) that triggers upgrade per D-83/84-2.
- Optional: access to run-payload history (for Tier 1 reconstruction) and SUPPORTS graph (for Tier 2 fallback).

**Output contract:**

- Two Claim nodes created: the NEW Claim from the candidate, and the OLD Claim reconstructed from the pre-existing LINKS_TO.
- A `CONTRADICTS` edge (or `SUPERSEDES`, `QUALIFIES` per the relation kind) between them.
- `Source—EVIDENCES→Claim` edges populated per the three-tier provenance per D-83/84-7 Part B.
- `Claim—ABOUT→Entity` edges per D-83/84-9 (authoritative binding to the canonical Entity).

**Pass criteria:**

| P-O2-1 | Both Claims created | OLD + NEW Claims exist post-upgrade. |
| P-O2-2 | Provenance tier correctness | OLD-Claim EVIDENCES.provenance_type is `reconstructed_from_run_payload` when run sidecar is available; `reconstructed_from_supports_overlap` otherwise; never `analysis_emitted` (that's reserved for the NEW Claim). |
| P-O2-3 | NULL-fields per tier | OLD-Claim EVIDENCES with `reconstructed_from_*` provenance MAY have NULL `quoted_text` / `score`; verifier accepts. |
| P-O2-4 | Authoritative ABOUT binding | OLD-Claim and NEW-Claim each have a `Claim—ABOUT→Entity` edge pointing at the canonical Entity (via `ALIAS_OF` traversal if subject was canonicalized). |
| P-O2-5 | LINKS_TO unchanged | The original `LINKS_TO` edge between the two entities is still present post-upgrade per D-83/84-7 Part A (upgrade is additive). |
| P-O2-6 | Idempotency | Re-running O2 with the same input produces no new writes (uniqueness constraints from D-83/84-10 apply). |

**Fail criteria:**

| F-O2-1 | LINKS_TO mutation | The original LINKS_TO edge is deleted or modified by the upgrade (violates D-83/84-7 Part A). |
| F-O2-2 | OLD-Claim has zero EVIDENCES | Tier 3 was reached when Tier 1 or 2 was actually available (the upgrade gave up too quickly). |
| F-O2-3 | Provenance-type mislabeled | An OLD-Claim EVIDENCES row has `provenance_type=analysis_emitted` (reserved for NEW-Claim evidence). |

**Gate threshold:**

- P-O2-1 through P-O2-6: 100% of probe scenarios.
- F-O2-1 through F-O2-3: zero failures.

### 4.3 O3 — Belief-sensitive read

**Input contract:**

- A read tuple `(subject_slug, predicate_class_canonical, predicate_scope_slugs)`.

**Output contract:**

- If a Claim family exists for the tuple: return Claim-space resolution (set of active Claims, with polarity/modality/confidence). Side-effect: lazy `subject_slug` rewrite per D-83/84-9 if the Claim's subject_slug is stale relative to the canonical entity.
- If no Claim family exists: return LINKS_TO topology resolution.

**Pass criteria:**

| P-O3-1 | Tuple-granularity correctness | For a subject with mixed Claim/LINKS_TO state (Claim family for one predicate, LINKS_TO only for another), the read returns Claim-space for the former tuple and LINKS_TO for the latter — NOT Claim-space for all subject-touching tuples. |
| P-O3-2 | Aliased-subject resolution | A read with a non-canonical subject slug resolves through `ALIAS_OF` to the canonical entity's Claims (per D-83/84-9). |
| P-O3-3 | Retracted-Claim filtering | Default reads exclude `state=retracted` Claims (per D-83/84-6 F2); audit-mode reads include them. |
| P-O3-4 | Decayed-below-threshold filtering | Default reads exclude Claims with `confidence < T` (per D-83/84-6 F2 decay threshold note); audit-mode reads include them. |
| P-O3-5 | Lazy-rewrite side effect | When the read encounters a Claim with stale denormalized `subject_slug` (post-canonicalization), the side-effect rewrite happens (per D-83/84-9 incremental path). |

**Fail criteria:**

| F-O3-1 | Subject-granularity contamination | A read for a tuple with no Claim family is routed through Claim-space because some *other* tuple on the same subject has Claims (violates D-83/84-7 Part A amended). |
| F-O3-2 | Aliased miss | A read with non-canonical subject slug fails to resolve through `ALIAS_OF` (returns no results despite Claims existing for the canonical form). |
| F-O3-3 | Retracted-Claim leak | Default-mode read returns `state=retracted` Claims. |

**Gate threshold:**

- P-O3-1 through P-O3-5: 100% of probe scenarios.
- F-O3-1 through F-O3-3: zero failures.

---

## 5. Invariants reference

This blueprint **does not restate** the GraphDB contract invariants. They live in `docs/task83-84-promotion-contract-belief-revision-blueprint.md` §6 "GraphDB contract delta" and are the canonical source.

Each per-op criterion above implicitly includes: **after the op completes, all §6 invariants must hold**. The verifier (`graphdb-kdb verify` with the §6 contract-delta extensions) is the mechanism for invariant checking. Eval scenarios assert (a) the expected post-state matches, AND (b) the verifier reports no new violations.

If a v1 review reveals invariants the §6 delta missed, those go back to the #83/#84 blueprint as a §6 amendment — NOT here.

---

## 6. Hedge-watch rules

HW rules instrument the system in production. Each rule has a **shape** (the symptom and the suspected cause); the **value** of the threshold is calibrated empirically and tracked in the OQ that owns it.

### 6.1 The seven HW rules

| HW # | Symptom | Suspected cause | Owning OQ |
|---|---|---|---|
| **HW-1** | `classification_drift` rate > **X%** across **N** consecutive promotion-time classifications | Coupling-as-invariant violation: the classifier reads data the fingerprint scope doesn't cover (D-83/84-8 Part B) | #83/#84 OQ-25 (enforcement mechanism); values: this blueprint OQ-2 |
| **HW-2** | `fingerprint_drift` rate ≫ `classification_drift` rate (e.g., **>3×**) | Fingerprint scope too broad: fingerprint includes data the classifier doesn't actually consult, generating false drift signals | #83/#84 OQ-25-adjacent; values: this blueprint OQ-2 |
| **HW-3** | `reinforces`-triggered Claim upgrades fire on **>Y%** of candidates (too eager) OR **<Z%** (too lazy) | Corroboration threshold N off | #83/#84 OQ-6; values: this blueprint OQ-2 |
| **HW-4** | Confidence-bucket emission distribution is **>P%** in one bucket (e.g., >80% `medium`) | LLM emission contract failing: model not differentiating confidence levels | #83/#84 OQ-20 + OQ-26 (mapping calibration); values: this blueprint OQ-2 |
| **HW-5** | Idempotency violations detected on retry (≥1 occurrence) | Uniqueness-constraint logic broken; D-83/84-10 violated | #83/#84 OQ-28 (multi-candidate dedup); zero-tolerance threshold |
| **HW-6** | SUPERSEDES chain depth > **D** for any Claim family | Policy gap on supersession lifecycle (when to retire old versions; lifecycle compaction) | NEW OQ filed below (this blueprint OQ-3) |
| **HW-7** | `claim_id` collision rate non-zero (any duplicate primary-key write attempts) | Version-allocation broken or `claim_family_id` deduplication failing | D-83/84-6 F1 amendment defensive check; zero-tolerance threshold |

### 6.2 HW rule trigger consequences

When an HW rule fires:

1. **Log + audit trail.** The triggering candidates/promotions are captured with full context for human review.
2. **Surface to operator.** A flag is raised in operator-visible dashboards / CLI status.
3. **Conditional auto-throttle.** For HW-5 and HW-7 (zero-tolerance), the Promotion Contract may auto-halt pending operator review. For other HW rules, throttling is policy-level (not architectural-blocker).
4. **OQ feedback.** The HW data feeds the owning OQ's empirical calibration loop.

### 6.3 What HW rules don't do

- They don't auto-redesign the system. A firing HW rule is *signal*, not *prescription*.
- They don't enforce zero-noise. Some false-positive rate is expected; calibration tunes the signal-to-noise.
- They don't replace probe-based eval (§4 above). HW rules monitor runtime; probe-based eval validates pre-implementation correctness.

---

## 7. Probe-set framework (curation deferred to #87.1)

A probe set is a curated collection of pre-state + input + expected-post-state scenarios. For #87, the probe set must exercise:

### 7.1 Coverage requirements

**By D-83/84-2 action-table cell** (minimum 1 scenario per cell):

| Cell | Scenario seed |
|---|---|
| `no_counterpart` | New entity with no prior LINKS_TO or Claim history |
| `orthogonal` | Buffett's insurance stance (touches Buffett but not the tech-investing claim family) |
| `reinforces` | A third source restating the 1995 Buffett-avoids-tech stance |
| `contradicts` | The 2020 Buffett-tech-pivot article (the original Buffett scenario from #83/#84 §2) |
| `qualifies_or_extends` with `refines_truth_conditions=true` | "Buffett invests in tech *iff* circle-of-competence" |
| `qualifies_or_extends` with `refines_truth_conditions=false` | "Buffett also discusses insurance float in the 1995 letter" |
| `supersedes` | Buffett's 2020 stance temporally replacing 1995 (vs contradicting — preserve both) |

**By upgrade-mechanism tier** (minimum 1 per tier):

- Tier 1 (run-payload reconstruction available)
- Tier 2 (SUPPORTS-overlap only)
- Tier 3 (synthesized marker; both Tier 1 and Tier 2 unavailable)

**By drift action-matrix cell** (minimum 1 per cell):

- `fingerprint_drift=false, classification_drift=false`
- `fingerprint_drift=true, classification_drift=false`
- `fingerprint_drift=false, classification_drift=true`
- `fingerprint_drift=true, classification_drift=true`

**By state-machine transition** (minimum 1 per transition):

- `active → superseded` (via SUPERSEDES)
- `active → retracted` (via explicit retraction; deferred to V2 but probe scenario specified)
- `superseded → active` (revival; deferred to V2)

**By aliasing scenario** (minimum 1):

- Subject canonicalization between analysis-time and promotion-time (D-83/84-9 lazy-rewrite case)
- Aliased-subject belief-sensitive read (P-O3-2)

### 7.2 Scenario format (template)

Each probe scenario follows this template:

```yaml
scenario_id: <unique slug, e.g. "buffett-tech-contradiction-2020">
description: <one-line summary>
covers:
  - <action-table cell>
  - <upgrade-tier or N/A>
  - <state-transition or N/A>
  - <HW-rule or N/A>

pre_state:
  entities:
    - { slug, canonical_id, attributes... }
  links_to:
    - { from_slug, to_slug, run_id, ... }
  supports:
    - { source_id, entity_slug, role, ... }
  claims:
    - { claim_id, ... full Claim node }
  edges:
    - { from_claim, to_claim, edge_type, attrs... }

input:
  candidate:
    <full candidate envelope per #83/#84 §4>

expected_post_state:
  entities: ...
  claims: ...
  evidences: ...
  edges: ...
  promotion_audit:
    fingerprint_drift: <bool>
    classification_drift: <bool>

expected_invariants_hold: true
expected_op_to_invoke: O1 | O2 | O3
```

### 7.3 What #87.1 owns

- Author the ~10–15 scenarios needed for coverage above.
- Validate that each scenario's expected post-state is internally consistent (no invariant pre-violations).
- Maintain the probe set as #83/#84 implementation lands — when D-83/84-N is amended, audit probe scenarios for breakage.
- Define the storage location and execution mechanism (likely `tests/eval/promotion/scenarios/*.yaml` or similar; impl-task work).

#87.1 is **blocked on** #87 v1 ratification (this blueprint) and **blocks** #83/#84 implementation start.

---

## 8. Open Questions

### OQ-1 — Per-op invariant assertion mechanism

Eval scenarios assert that all §5 invariants hold post-mutation. The mechanism options:

- (a) Run `graphdb-kdb verify` after each op execution in eval mode — slow but authoritative.
- (b) Subset verifier check (skip schema-migration invariants; check only Claim-layer invariants) — faster but risks gaps.
- (c) Eval-specific lightweight invariant set (curated subset) — fastest but adds a new contract surface.

Resolution belongs in #87 v2 ratification; defaults to (a) unless eval execution time becomes blocking.

### OQ-2 — HW threshold values

This blueprint specifies HW rule **shapes**; values are calibrated empirically and tracked in the owning OQs:

- HW-1 / HW-2 thresholds → #83/#84 OQ-25 (coupling-as-invariant enforcement) for the diagnostic; values empirical.
- HW-3 → #83/#84 OQ-6 (corroboration threshold N).
- HW-4 → #83/#84 OQ-20 + OQ-26 (confidence map + aggregation tuning).
- HW-5 / HW-7 → zero-tolerance, no calibration needed.
- HW-6 → this blueprint OQ-3 below.

OQ-2 itself owns the **shape-to-value mapping** — when each owning OQ is resolved, the HW threshold inherits the value. This blueprint's job is to make sure the shape is right and the mapping to owning OQ is explicit; value resolution is the owning OQ's job.

### OQ-3 — SUPERSEDES chain depth threshold

NEW open question filed by this blueprint (not in #83/#84). What's the maximum reasonable chain depth before policy gap is suspected? Initial guess: D=10. Belongs in the empirical-tuning track alongside the threshold OQs.

### OQ-4 — Probe-set curation scope (#87.1 scoping)

What's the minimum probe set for v1 implementation start? Coverage requirements in §7.1 suggest ~15 scenarios; could go as low as ~8 (one per action-table cell + 3 upgrade-tiers + 4 drift-cells) or as high as ~25 (with adversarial-case coverage). Trade-off: more scenarios = higher confidence but slower #87.1 turnaround.

Default lean: target **15 scenarios** for v1 (action-table + tiers + drift + 1 aliasing + 1 retraction). Adversarial/edge-case scenarios deferred to a v2 probe-set expansion.

### OQ-5 — Eval execution surface

Where do eval scenarios run? Options:

- (a) Standalone test suite (`tests/eval/promotion/...`) invoked via `pytest -m promotion-eval` or similar.
- (b) Integrated into `graphdb-kdb verify` as a new check mode.
- (c) Dedicated CLI (`graphdb-kdb promotion-eval` or `kdb-eval promotion`).

Default lean: (a) — pytest-based, follows project test discipline. Option (c) may emerge later as a separate UX surface.

---

## 9. References

- `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v2) — the design this blueprint evaluates
- `docs/task75-predeclared-eval-criteria-blueprint.md` — precedent for predeclared-eval discipline (retrieval-eval shape)
- `docs/task19-kpi-design.md` — earlier precedent (compile-side KPI predeclaration → CODEBASE_OVERVIEW §7)
- `docs/external-review-panel.md` — active reviewer panel (Codex + Deepseek + Qwen)
- `docs/CODEBASE_OVERVIEW.md` — architecture context
- `docs/what-is-the-ontology-for.md` §9.4 — Round 6 closure that mandated #83/#84

---

## 10. Change log

- **2026-05-22** — v1 drafted. Pre-external-review. Operations roster compressed to 3 (per advisor input on mutation-eval-vs-retrieval-eval frame mismatch); probe-set curation filed as #87.1; HW rules with shaped thresholds; 5 new OQs filed.
