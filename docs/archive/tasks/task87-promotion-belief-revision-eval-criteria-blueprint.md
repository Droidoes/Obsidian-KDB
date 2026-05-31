# Task #87 — Predeclared Eval Criteria for #83/#84 (Promotion Contract + Belief Revision) — Blueprint v2

**Status:** v2 — drafted 2026-05-22 after holistic panel review
**Lineage:** Filed 2026-05-22 from #83/#84 blueprint v2 closeout (commit `01c6373`). Analog of Task #75 for step-3 ops, adapted for the **mutation-eval** shape of the Promotion Contract + Belief Revision. v2 synthesizes Codex + Deepseek + Qwen v1 holistic reviews (16 findings; convergence on O3 hybrid framing, P-O1-6 determinism, hedge-source reconciliation).
**Reviewer panel:** Codex + Deepseek + Qwen (per `docs/external-review-panel.md`)
**Anchors:**
- `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v2 — the design this blueprint evaluates)
- `docs/task75-predeclared-eval-criteria-blueprint.md` (precedent for the predeclared-eval discipline; this blueprint adapts the spine)
- `docs/TASKS.md` #87 + planned #87.1 (probe-set curation)

---

## 0. TL;DR

The #83/#84 v2 blueprint is structurally complete (12 decisions ratified). This blueprint defines **what "working correctly" means** for the Promotion Contract + Belief Revision **before implementation begins** — the same predeclared-eval discipline Task #75 established for step-3 ops. Without it, implementation can't be objectively verified.

**Critical adaptation:** Task #75 was retrieval-eval ("did the op return the right thing?"). #87 is **mutation-eval** ("did the op make the right state change?"). The frame is **integration-test-shaped** — pre-state + input → expected post-state + invariants preserved — not benchmark-shaped.

**Three v1 operations** (O1 mutation / O2 mutation / O3 *hybrid* — retrieval + 1 mutation invariant), per-op predeclared criteria, **eleven hedge-watch rules** (HW-1..HW-11; values calibrated empirically — HW-8 maps the §9.4.7 vanity-graph hedge to #87 territory; HW-9/10/11 added on their own merits, not Round-6 lineage). Probe-set curation deferred to sub-task **#87.1**.

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
| **O3** | **Belief-sensitive read** *(hybrid)* | Tuple `(subject, predicate_class, scope)` → Claim-space resolution if Claim family exists; LINKS_TO fallback otherwise (per D-83/84-7 Part A amended) | **Hybrid eval shape:** primarily *retrieval-eval* (query → expected resolution path + result, Task #75 frame) plus *one mutation invariant* for the lazy `subject_slug` rewrite side-effect per D-83/84-9 (when stale denormalized keys are encountered). Per-op criteria split accordingly — see §4.3. |

### 3.2 Rationale for this cut

- **O1 absorbs four sub-stages** (classify, fingerprint, action-matrix, mutate) into one eval-able unit because their contract is sequential and atomic at the candidate level. Testing them independently fragments the contract — the post-state of the whole pipeline is the meaningful thing to assert.
- **O2 is separated** because its precondition (existing `LINKS_TO` with no prior Claim family) is structurally different from O1 (which may or may not have an existing Claim family). The provenance-reconstruction logic (Tier 1 / 2 / 3) is distinct enough to deserve its own eval surface.
- **O3 is separated** because belief-sensitive reads are read-mostly with a side-effect (lazy rewrite per D-83/84-9). The read-path correctness rule (tuple-granularity per D-83/84-7 Part A amended) is the load-bearing contract, separate from mutation. O3's eval shape is therefore **hybrid** — retrieval-eval for the read-correctness contract, plus a single mutation-invariant for the lazy-rewrite side-effect (the rewrite must not corrupt state). This is per 3-reviewer convergence in the v1 holistic review; v2 retains O3 as one op but acknowledges the hybrid shape explicitly. Whether O3 should split into two ops in a later version is OQ-12.

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
- Scenario-declared `eval_config` (see §7.2) — `eval_clock`, threshold values, confidence-map version — pinned to make expected post-state deterministically computable.

**Output contract:**

- One of two outcomes determined by promotion-time classification + the drift-cell disposition:
  - **Mutate-disposition cells** (default): graph mutation per D-83/84-2 action (Claim-creating *or* topology-only — see P-O1-2).
  - **Human-review disposition cells:** zero graph mutation; only a `promotion_audit` record with `disposition=human_review` plus a review-queue/audit artifact. Mutation only fires under an explicit approval input (out of #87 v1 scope; see OQ-10).
- `promotion_audit` record (per D-83/84-8 Part D) including `fingerprint_drift`, `classification_drift`, `drift_explanation`, **`disposition`**.
- Idempotency: re-running O1 with the same candidate against the post-state is a no-op (per D-83/84-10).

**Pass criteria:**

| P-O1-1 | Action-matrix determinism | Given identical (pre-state, candidate, `eval_config`), promotion-time classification produces the same `analysis_classification` (counterpart_status + relation_kind + sub-flag). |
| P-O1-2 | D-83/84-2 action correctness | For each cell of the D-83/84-2 action table, the expected mutation is applied. **Claim-creating cells** (`reinforces` over threshold, `contradicts`, `qualifies_or_extends` with `refines_truth_conditions=true`, `supersedes`): Claim + EVIDENCES + Claim-Claim edges created per the table. **Topology-only cells** (`no_counterpart`, `orthogonal`, `qualifies_or_extends` with `refines_truth_conditions=false`, `reinforces` under threshold): `LINKS_TO` + `SUPPORTS` writes occur per D-83/84-2; **zero Claim/EVIDENCES/Claim-Claim writes** for these cells. |
| P-O1-3 | Idempotency on retry | Re-running O1 with the same candidate against the post-state produces zero new writes (verified by uniqueness-constraint checks per D-83/84-10). |
| P-O1-4 | Drift signals correct | For probe scenarios with graph mutations between analysis-time and promotion-time, `fingerprint_drift` and `classification_drift` match the expected truth values per the D-83/84-8 Part D 4-cell matrix. |
| P-O1-5 | Evidence cardinality | Each **unique** `evidence[]` entry in the input candidate (uniqueness key per D-83/84-10: `(source_id, claim_id, quoted_text_hash, provenance_type)`) becomes exactly one `Source—EVIDENCES→Claim` edge on promotion; duplicate entries are idempotently deduplicated. Empty `evidence[]` is permitted by the contract — the resulting Claim may have zero EVIDENCES edges (verifier behavior on zero-EVIDENCES Claims: see OQ-16). |
| P-O1-6 | Aggregate confidence correctness | Post-mutation `Claim.confidence` equals the deterministic aggregation of all current `EVIDENCES.score` values per the aggregation contract resolved in **#83/#84 OQ-26**; `Claim.confidence_spread` is computed per the same contract. **Determinism requires `eval_clock` from `eval_config`** — if the aggregation formula contains a time-decay term, the eval harness MUST use `eval_clock` (NOT system wall-clock) for any `now()` reference. Equality tolerance: see OQ-15. |
| P-O1-7 | Disposition correctness | For each (D-83/84-2 action × D-83/84-8 Part D drift cell) combination, `promotion_audit.disposition` matches the expected value (`auto_promote` / `auto_promote_with_note` / `investigate` / `human_review`). Only `auto_promote` / `auto_promote_with_note` dispositions mutate the graph in default mode (no approval input). |
| P-O1-8 | Retracted-counterpart resolution | When the candidate's counterpart is a `state=retracted` Claim, O1 resolves per the rule pending in OQ-18 (forward-pointer to #83/#84 — current default: treat as no_counterpart against the retracted member; if an active member exists in the same Claim family, classify against that). The `promotion_audit` records `counterpart_resolution_path` for diagnostic clarity. |

**Fail criteria:**

| F-O1-1 | Classification non-determinism | Same (pre-state, candidate, `eval_config`) yields different classifications across runs (without graph state change). |
| F-O1-2 | Action-table violation | A `contradicts` candidate skips Claim creation; `reinforces` triggers Claim creation below threshold N; topology-only cell writes a Claim; Claim-creating cell skips Claim writes. |
| F-O1-3 | Idempotency violation | Retry produces duplicate writes (new Claim with same `claim_id`, or duplicate EVIDENCES rows on the same uniqueness key). |
| F-O1-4 | Invariant break post-mutation | Any of the §5 invariants (referenced from #83/#84 §6) fails verifier check after O1 completes. **Eval-failure output MUST include the violated-invariants list from verifier output** for diagnostic clarity (i.e., a bare "F-O1-4 fired" without naming the broken invariant is itself a probe-set defect). |
| F-O1-5 | Unauthorized mutation under human-review disposition | A scenario producing `disposition=human_review` (or `investigate`) writes to Claim / EVIDENCES / LINKS_TO / SUPPORTS without an approval input. Default-mode O1 must short-circuit before mutation on these cells. |

**Gate threshold:**

- P-O1-1 through P-O1-8 must hold on **100% of probe scenarios** for #87 ratification.
- F-O1-1 through F-O1-5 must produce **zero failures** on the probe set.

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
| P-O2-7 | Positive Tier-3 reconstruction | When Tier 1 (run-payload) and Tier 2 (SUPPORTS-overlap) are both unavailable, O2 creates the OLD Claim with **zero EVIDENCES edges** AND writes the required attempted-reconstruction metadata to operational logs / `promotion_audit` (per D-83/84-7 Part B): `provenance_attempt_tier1=failed`, `provenance_attempt_tier2=failed`, `provenance_synthesized_marker=true`. This is the correct positive behavior for the Tier-3 cell, not a failure escape. |

**Fail criteria:**

| F-O2-1 | LINKS_TO mutation | The original LINKS_TO edge is deleted or modified by the upgrade (violates D-83/84-7 Part A). |
| F-O2-2 | OLD-Claim has zero EVIDENCES with Tier-1 or Tier-2 available | The upgrade gave up too quickly — Tier 3 was reached when Tier 1 or 2 was actually available (distinct from P-O2-7's legitimate Tier-3 case). |
| F-O2-3 | Provenance-type mislabeled | An OLD-Claim EVIDENCES row has `provenance_type=analysis_emitted` (reserved for NEW-Claim evidence). |
| F-O2-4 | Tier-3 metadata missing | OLD Claim has zero EVIDENCES AND the attempted-reconstruction metadata (per P-O2-7) is missing — failure to record the synthesized-marker provenance is itself a contract violation, even when zero-EVIDENCES is otherwise legitimate. |

**Gate threshold:**

- P-O2-1 through P-O2-7: 100% of probe scenarios.
- F-O2-1 through F-O2-4: zero failures.

### 4.3 O3 — Belief-sensitive read *(hybrid op)*

**Frame:** O3 is a **hybrid eval op** — predominantly retrieval-eval (Task #75 frame), with one mutation invariant for the lazy-rewrite side-effect. The pass/fail criteria below are split into two classes accordingly:

- **Retrieval-eval class** (P-O3-1..4, F-O3-1..3): query → expected resolution path + result. Pre-state = post-state for these criteria unless the lazy-rewrite side-effect fires.
- **Mutation-invariant class** (P-O3-5, F-O3-4): if the lazy-rewrite fires, it must preserve all §5 invariants and produce no malformed denormalized keys.

**Input contract:**

- A read tuple `(subject_slug, predicate_class_canonical, predicate_scope_slugs)`.
- A read mode (`default` filters retracted + below-threshold; `audit` does not).
- Scenario-declared `eval_config` (see §7.2) — `default_read_confidence_threshold_t` (used by P-O3-4); `eval_clock` (if the threshold derivation involves decay weights).

**Output contract:**

- If a Claim family exists for the tuple: return Claim-space resolution (set of active Claims, with polarity/modality/confidence).
- If no Claim family exists for the tuple: return LINKS_TO topology resolution.
- **Conditional side-effect:** lazy `subject_slug` rewrite per D-83/84-9 if (and only if) the read encounters a Claim with a stale denormalized `subject_slug` relative to its `Claim—ABOUT→Entity` target. Reads with no stale keys produce **zero writes**.

**Pass criteria (retrieval-eval class):**

| P-O3-1 | Tuple-granularity correctness | For a subject with mixed Claim/LINKS_TO state (Claim family for one predicate, LINKS_TO only for another), the read returns Claim-space for the former tuple and LINKS_TO for the latter — NOT Claim-space for all subject-touching tuples. |
| P-O3-2 | Aliased-subject resolution | A read with a non-canonical subject slug resolves through `ALIAS_OF` to the canonical entity's Claims (per D-83/84-9). |
| P-O3-3 | Retracted-Claim filtering | Default-mode reads exclude `state=retracted` Claims (per D-83/84-6 F2); audit-mode reads include them. |
| P-O3-4 | Decayed-below-threshold filtering | Default-mode reads exclude Claims with `confidence < T_scenario`, where `T_scenario` is `default_read_confidence_threshold_t` declared in the scenario's `eval_config` block (§7.2). Audit-mode reads include below-threshold Claims. The threshold value used MUST be recorded in the scenario output for machine-checkability. |

**Pass criteria (mutation-invariant class):**

| P-O3-5 | Lazy-rewrite triggered iff stale | When the read encounters a Claim with stale denormalized `subject_slug` (post-canonicalization), the side-effect rewrite happens (per D-83/84-9 incremental path). When no stale keys exist among reachable Claims, the read performs **zero writes**. The rewrite touches only the stale keys encountered (not subject-wide). |

**Fail criteria (retrieval-eval class):**

| F-O3-1 | Subject-granularity contamination | A read for a tuple with no Claim family is routed through Claim-space because some *other* tuple on the same subject has Claims (violates D-83/84-7 Part A amended). |
| F-O3-2 | Aliased miss | A read with non-canonical subject slug fails to resolve through `ALIAS_OF` (returns no results despite Claims existing for the canonical form). |
| F-O3-3 | Retracted-Claim leak | Default-mode read returns `state=retracted` Claims. |

**Fail criteria (mutation-invariant class):**

| F-O3-4 | Lazy-rewrite corruption | The side-effect rewrite produces a `claim_family_id` violating D-83/84-6 F1 delimiter/parseability guard; a `subject_slug` that doesn't match `Claim—ABOUT→Entity.canonical_id` (violating D-83/84-9 denormalized-key coherence); or a `claim_id` that breaks uniqueness. The rewrite also fires when no stale keys exist (a no-op read produces writes) — that's an F-O3-4 fail too. Verifier-output capture per F-O1-4 applies. See OQ-17 for verifier-flush timing. |

**Gate threshold:**

- P-O3-1 through P-O3-5: 100% of probe scenarios.
- F-O3-1 through F-O3-4: zero failures.

---

## 5. Invariants reference

This blueprint **does not restate** the GraphDB contract invariants. They live in `docs/task83-84-promotion-contract-belief-revision-blueprint.md` §6 "GraphDB contract delta" and are the canonical source.

Each per-op criterion above implicitly includes: **after the op completes, all §6 invariants must hold**. The verifier (`graphdb-kdb verify` with the §6 contract-delta extensions) is the mechanism for invariant checking. Eval scenarios assert (a) the expected post-state matches, AND (b) the verifier reports no new violations.

If a v1 review reveals invariants the §6 delta missed, those go back to the #83/#84 blueprint as a §6 amendment — NOT here.

---

## 6. Hedge-watch rules

HW rules instrument the system in production. Each rule has a **shape** (the symptom and the suspected cause); the **value** of the threshold is calibrated empirically and tracked in the OQ that owns it.

### 6.0 Hedge-source provenance

Two distinct hedge inputs feed the HW roster:

1. **Round 6 hedges** (the architectural watch-for-at-implementation hedges from `docs/what-is-ontology-for-V1.md` §9.4.7, ratified at Round 6 closure):
   - **Vanity-graph failure mode** — Analysis surfaces N candidates; Promotion accepts M ≪ N over a sustained window. **In #87's territory** — mapped to **HW-8** below.
   - **Stranded-summary failure mode** — Task #86 GraphRAG-style summaries indexed but never become graph elements. **Owned by Task #86 eval surface, not #87.**
   - **Under-counted-Learn-surface failure mode** — Task #74 canonicalization hosts genuine epistemic decisions in practice. **Owned by Task #74 canonicalization audit, not #87.**

2. **#87-territory implementation-risk hedges** (added on their own merits during v2 synthesis from reviewer findings — NOT Round-6 lineage):
   - Drift-rate, fingerprint-scope, corroboration-rate, confidence-bucket-distribution, idempotency, supersession-depth, claim_id-collision — **HW-1..HW-7** below.
   - Promotion latency / throughput — **HW-9** (Deepseek F3).
   - Audit-trail growth — **HW-10** (3-reviewer convergence).
   - LINKS_TO ↔ Claim layer divergence — **HW-11** (Qwen F8).

The v1 review prompt conflated #87-territory hedges with Round-6 hedges (the prompt invented HW-a/b/c labels matching neither source). v2 reconciles: §9.4.7's three hedges are named explicitly, and HW-8 carries vanity-graph; everything else stands on its own merits.

### 6.1 The HW rules (HW-1..HW-11)

| HW # | Symptom | Suspected cause | Owning OQ |
|---|---|---|---|
| **HW-1** | `classification_drift` rate > **X%** across **N** consecutive promotion-time classifications | Coupling-as-invariant violation: the classifier reads data the fingerprint scope doesn't cover (D-83/84-8 Part B) | #83/#84 OQ-25 (enforcement mechanism); values: this blueprint OQ-2 |
| **HW-2** | `fingerprint_drift` rate ≫ `classification_drift` rate (e.g., **>3×**) | Fingerprint scope too broad: fingerprint includes data the classifier doesn't actually consult, generating false drift signals | #83/#84 OQ-25-adjacent; values: this blueprint OQ-2 |
| **HW-3** | `reinforces`-triggered Claim upgrades fire on **>Y%** of candidates (too eager) OR **<Z%** (too lazy) | Corroboration threshold N off | #83/#84 OQ-6; values: this blueprint OQ-2 |
| **HW-4** | Confidence-bucket emission distribution is **>P%** in one bucket (e.g., >80% `medium`) | LLM emission contract failing: model not differentiating confidence levels | #83/#84 OQ-20 + OQ-26 (mapping calibration); values: this blueprint OQ-2 |
| **HW-5** | Idempotency violations detected on retry (≥1 occurrence) | Uniqueness-constraint logic broken; D-83/84-10 violated | #83/#84 OQ-28 (multi-candidate dedup); zero-tolerance threshold |
| **HW-6** | SUPERSEDES chain depth > **D** for any Claim family | Policy gap on supersession lifecycle (when to retire old versions; lifecycle compaction) | NEW OQ filed below (this blueprint OQ-3) |
| **HW-7** | `claim_id` collision rate non-zero (any duplicate primary-key write attempts) | Version-allocation broken or `claim_family_id` deduplication failing | D-83/84-6 F1 amendment defensive check; zero-tolerance threshold |
| **HW-8** | Over rolling window W of promotion attempts: Analysis surfaces N candidates, Promotion accepts M, **M/N < R** | Gate thresholds too strict — the **vanity-graph failure mode** (§9.4.7 hedge 1): Analysis output never enters graph state. Audit gate thresholds. | NEW OQ (this blueprint OQ-6) — empirical R; rolling window W |
| **HW-9** | Per-candidate promotion latency > **L** ms (p50 or p95 across a compile run) | Classifier cost / fingerprint recomputation scope creep / graph-walk depth under-estimated. Productivity-bottleneck implementation hedge. | NEW OQ (this blueprint OQ-7) — empirical L per percentile |
| **HW-10** | Per-compile audit-trail growth (Claims + EVIDENCES + Claim-Claim edges + `promotion_audit` rows per candidate) > **G** over rolling window | Audit-trail-bloat implementation hedge — unbounded provenance accumulation degrades graph query cost + storage. | NEW OQ (this blueprint OQ-8) — empirical G; storage-policy decision pending |
| **HW-11** | Fraction of entity-pairs with active Claim family for predicate P that **also** have LINKS_TO edges for the same predicate exceeds **F** over a rolling sample | Hybrid-model accumulation: O2 upgrade-from-LINKS_TO firing too rarely; the two layers diverging semantically without retroactive promotion. Distinct from HW-3 (which watches *rate*) — this watches *standing divergence*. | NEW OQ (this blueprint OQ-9) — empirical F |

### 6.2 HW rule trigger consequences

When an HW rule fires:

1. **Log + audit trail.** The triggering candidates/promotions are captured with full context for human review.
2. **Surface to operator.** A flag is raised in operator-visible dashboards / CLI status.
3. **Conditional auto-throttle.** For HW-5 and HW-7 (zero-tolerance), the Promotion Contract may auto-halt pending operator review. For other HW rules, throttling is policy-level (not architectural-blocker). HW-8 (vanity-graph attrition) is a sustained-window signal — auto-throttle is inappropriate; the right response is gate-threshold audit.
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

**By drift action-matrix cell** (minimum 1 per cell, **with expected disposition recorded in `expected_post_state.promotion_audit.disposition`**):

- `fingerprint_drift=false, classification_drift=false` → expected disposition recorded
- `fingerprint_drift=true, classification_drift=false` → expected disposition recorded
- `fingerprint_drift=false, classification_drift=true` → expected disposition recorded
- `fingerprint_drift=true, classification_drift=true` → expected disposition recorded

A scenario that has the right drift bools but the wrong disposition is a probe-set defect (P-O1-7 would fail downstream against a real implementation). The four boolean combinations exercise the input axis; recording the expected disposition exercises the output axis.

**By state-machine transition** (minimum 1 per transition that has a defined trigger contract in v1):

- `active → superseded` (via SUPERSEDES — defined by D-83/84-11; testable in v1)
- ~~`active → retracted`~~ — **deferred to #87 v2**, blocked on explicit-retraction trigger contract (UX surface or programmatic API; not defined in #83/#84 v1).
- ~~`superseded → active`~~ — **deferred to #87 v2**, blocked on revival trigger contract (D-83/84-11 specifies the cascade but not the operator-trigger boundary).

A pre-existing `retracted` Claim **may appear in pre-state fixtures** for testing read-filter behavior (P-O3-3) or retracted-counterpart resolution (P-O1-8) without requiring an `active → retracted` mutation scenario.

**By retracted-counterpart scenario** (minimum 1, per P-O1-8):

- Candidate counterpart is a `state=retracted` Claim with an `active` sibling in the same Claim family → expected resolution: classify against the active sibling per OQ-18's pending rule.
- Candidate counterpart is a `state=retracted` Claim with no active sibling → expected resolution: treat as `no_counterpart` per OQ-18 default.

**By aliasing scenario** (minimum 1):

- Subject canonicalization between analysis-time and promotion-time (D-83/84-9 lazy-rewrite case)
- Aliased-subject belief-sensitive read (P-O3-2)

**By sequential multi-candidate interaction** (minimum 1, per D-83/84-10 sequential semantics):

- Two candidates emitted in one Analysis batch where candidate N's promotion-time classification differs from what it would have been against the pre-batch state, because candidate N-1's promotion altered the Claim space. This exercises the sequential-processing commitment of D-83/84-10 (multi-candidate parallelism deferred to OQ-28 remains out of scope).

### 7.2 Scenario format (template)

Each probe scenario follows this template:

```yaml
scenario_id: <unique slug, e.g. "buffett-tech-contradiction-2020">
description: <one-line summary>
covers:
  - <action-table cell>
  - <upgrade-tier or N/A>
  - <state-transition or N/A>
  - <retracted-counterpart axis or N/A>
  - <sequential-interaction axis or N/A>
  - <HW-rule or N/A>

# Pinned values that make the expected post-state deterministically computable.
# Required for P-O1-1 (action-matrix determinism), P-O1-6 (aggregate confidence
# correctness), P-O3-4 (decayed-below-threshold filtering), and any criterion
# whose evaluation depends on `now()`, a threshold, or a versioned config.
eval_config:
  eval_clock: <fixed ISO timestamp, e.g. "2026-06-01T00:00:00+09:00">  # used by aggregation decay + threshold derivations
  corroboration_threshold_n: <int>                                     # used by P-O1-2 reinforces gate
  confidence_decay_tau_days: <number>                                  # used by P-O1-6 aggregation
  default_read_confidence_threshold_t: <number>                        # used by P-O3-4
  confidence_map_version: <id, e.g. "confidence_map_v1">               # used by P-O1-5 + P-O1-6
  read_mode: default | audit                                           # used by P-O3-3 + P-O3-4 (O3 scenarios only)

pre_state:
  entities:
    - { slug, canonical_id, attributes... }
  links_to:
    - { from_slug, to_slug, run_id, ... }
  supports:
    - { source_id, entity_slug, role, ... }
  claims:
    - { claim_id, ... full Claim node }              # may include state=retracted for P-O1-8 / P-O3-3 fixtures
  edges:
    - { from_claim, to_claim, edge_type, attrs... }

input:
  candidate:
    <full candidate envelope per #83/#84 §4>
  # For sequential-interaction scenarios, list multiple candidates in batch order:
  # batch:
  #   - <candidate N-1 envelope>
  #   - <candidate N envelope>
  # The expected_post_state then reflects the final state after sequential application.

expected_post_state:
  entities: ...
  claims: ...
  evidences: ...
  edges: ...
  promotion_audit:
    fingerprint_drift: <bool>
    classification_drift: <bool>
    disposition: auto_promote | auto_promote_with_note | investigate | human_review   # per P-O1-7
    counterpart_resolution_path: <string or null>                                     # per P-O1-8

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
- HW-6 → this blueprint OQ-3.
- HW-8 → this blueprint OQ-6.
- HW-9 → this blueprint OQ-7.
- HW-10 → this blueprint OQ-8.
- HW-11 → this blueprint OQ-9.

OQ-2 itself owns the **shape-to-value mapping** — when each owning OQ is resolved, the HW threshold inherits the value. This blueprint's job is to make sure the shape is right and the mapping to owning OQ is explicit; value resolution is the owning OQ's job.

### OQ-3 — SUPERSEDES chain depth threshold (HW-6)

NEW open question filed by this blueprint (not in #83/#84). What's the maximum reasonable chain depth before policy gap is suspected? Initial guess: D=10. Belongs in the empirical-tuning track alongside the threshold OQs.

### OQ-4 — Probe-set curation scope (#87.1 scoping)

What's the minimum probe set for v1 implementation start? Coverage requirements in §7.1 (now including retracted-counterpart + sequential-interaction axes) suggest **~18–20 scenarios**; could go as low as ~10 (one per action-table cell + 3 upgrade-tiers + 4 drift-cells) or as high as ~30 (with adversarial-case coverage). Trade-off: more scenarios = higher confidence but slower #87.1 turnaround.

Default lean: target **~18 scenarios** for v1 (action-table 7 + upgrade tiers 3 + drift cells 4 + 1 aliasing + 2 retracted-counterpart + 1 sequential-interaction). Adversarial/edge-case scenarios deferred to a v2 probe-set expansion.

### OQ-5 — Eval execution surface

Where do eval scenarios run? Options:

- (a) Standalone test suite (`tests/eval/promotion/...`) invoked via `pytest -m promotion-eval` or similar.
- (b) Integrated into `graphdb-kdb verify` as a new check mode.
- (c) Dedicated CLI (`graphdb-kdb promotion-eval` or `kdb-eval promotion`).

Default lean: (a) — pytest-based, follows project test discipline. Option (c) may emerge later as a separate UX surface.

### OQ-6 — HW-8 vanity-graph attrition threshold

What's the M/N acceptance ratio R below which HW-8 fires, and over what rolling window W? Resolution requires real-corpus baseline of Analysis-surfaced N vs Promotion-accepted M. Initial guess: R=0.10 (90% rejection sustained over W=200 promotions) → audit gate thresholds. This is the operationalization of the §9.4.7 vanity-graph hedge.

### OQ-7 — HW-9 promotion latency threshold

What's the per-candidate promotion latency L (p50 and p95) above which HW-9 fires? Initial guess: p50 > 300ms or p95 > 800ms. Calibrated against realistic corpus on the project's reference hardware; threshold may differ for compile-time vs interactive paths.

### OQ-8 — HW-10 audit-trail growth threshold

What's the audit-trail growth rate G per candidate (Claims + EVIDENCES + Claim-Claim edges + `promotion_audit` rows) above which HW-10 fires? Storage policy choice gates this — if `promotion_audit` rows are eventually compacted or rolled up, G can be higher. Initial guess pending storage-policy decision.

### OQ-9 — HW-11 LINKS_TO/Claim divergence threshold

What fraction F of entity-pairs with active Claim family for predicate P also have LINKS_TO edges for that predicate before HW-11 fires? Initial guess: F=0.25 sustained over rolling sample of 100 Claim families. Triggers re-evaluation of O2 upgrade firing rate (whether D-83/84-7 Part B is firing as often as it should).

### OQ-10 — Human-review approval-input shape *(from Codex v1 review)*

For drift cells with `disposition=human_review` or `disposition=investigate`, what's the input shape for "operator approved, now apply mutation"? Options:

- (a) Re-run O1 with an added `approval_token` field on the candidate envelope.
- (b) A separate operator-only op (O5: `apply_human_reviewed_promotion`) that takes a candidate-id and approval flag.
- (c) Defer entirely until UX surfaces emerge.

Lean: defer to (c) until a human-review UX is needed. v1 implementation can ship with `human_review` cells producing only audit records; the input-shape decision lives with the future UX task.

### OQ-11 — Invalid pre-state in probe scenarios *(from Codex v1 review)*

Should #87.1's probe set include scenarios with verifier-invalid pre-state (e.g., orphan Claims, dangling EVIDENCES) to test that ops detect and reject them, or should all fixtures be verifier-clean by construction? Lean: verifier-clean by construction for v1 — the ops contract assumes valid pre-state; pre-state-validation behavior is a separate op (verifier itself).

### OQ-12 — O3 split into two ops in a future version *(from Qwen v1 review)*

If O3's lazy-rewrite scope grows in v2 (additional denormalization repairs beyond `subject_slug`), should O3 split into a pure-retrieval op (O3a) and a denormalization-repair op (O3b)? Defer; v2 keeps O3 as one hybrid op with the explicit retrieval-eval / mutation-invariant split per §4.3.

### OQ-13 — Canonicalization integration eval surface boundary *(from Qwen v1 review)*

D-83/84-5 mandates shared canonicalization infra; D-83/84-4 makes same-predicate matching depend on canonical-form equality. If canonicalization is wrong, all of O1/O2/O3 produce wrong results — but §3.3 defers canonicalization eval to the Task #74 discipline. Does #87 need at least one *integration-level* criterion that fails when canonicalization is wrong (e.g., "a candidate with a non-canonical `predicate_class_raw` still promotes correctly after canonicalization"), or is the boundary clean? Lean: add one cross-cutting integration probe in #87.1 as a smoke test, but the canonicalization eval surface stays with Task #74.

### OQ-14 — LLM-extraction non-determinism in probe coverage *(from Qwen v1 review)*

The candidate envelope is LLM-emitted. The eval criteria assume deterministic behavior given a fixed candidate. But in the full pipeline, the candidate itself is non-deterministic. Should #87.1 include scenarios where the same raw source text produces slightly different candidate envelopes across runs, and eval whether the Promotion Contract handles both correctly? This is distinct from F-O1-1 (same-candidate classification determinism). Lean: out of scope for #87 v1 — frame this as Analysis-side eval, not Promotion-side; defer to a future Analysis-eval task.

### OQ-15 — Confidence floating-point tolerance *(from Deepseek v1 review)*

P-O1-6 asserts `Claim.confidence` equals the deterministic aggregation. With clock-control fixed (via `eval_config.eval_clock`), the computation is deterministic *in principle*, but floating-point equality across KuzuDB's C++ engine and Python's eval harness may produce off-by-ULP mismatches. Should P-O1-6 use a tolerance (e.g., `abs_diff < 1e-9`) rather than strict equality? Lean: yes — adopt `abs_diff < 1e-9` for `Claim.confidence` and `Claim.confidence_spread`. Belongs in #87.1 implementation when probe scenarios with expected confidence values are written.

### OQ-16 — Verifier behavior on zero-EVIDENCES Claims *(from Deepseek v1 review)*

P-O1-5 amended in v2 permits empty `evidence[]` (resulting in Claims with zero EVIDENCES). Does the verifier accept zero-EVIDENCES Claims (no `analysis_emitted` row required) or require at least one EVIDENCES edge for every Claim? Belongs in #83/#84 §6 invariant clarification — forward-pointer back to upstream. Lean: zero-EVIDENCES Claims are accepted *for OLD-Claim Tier-3 case* (per P-O2-7) but a new policy decision needed for empty-evidence Claims from O1 candidates.

### OQ-17 — O3 lazy-rewrite vs verifier flush timing *(from Deepseek v1 review)*

If the eval harness runs the verifier after O3 and the lazy rewrite hasn't been flushed (or is deferred), the verifier may report stale-`subject_slug` violations that are false positives. Options:

- (a) Eval harness forces a flush before verifying.
- (b) Verifier accepts stale denormalized keys as `warning`, not `error`.
- (c) Lazy-rewrite is synchronous (no flush issue).

Lean: (c) for v1 — make the rewrite synchronous on read-encounter; revisit only if performance forces deferral.

### OQ-18 — Retracted-Claim counterpart resolution *(forward-pointer to #83/#84, from Deepseek v1 review)*

D-83/84-2's action table has no row for the case where a candidate's counterpart is a `state=retracted` Claim. P-O1-8 in this blueprint records the current default ("classify against active sibling if present; else no_counterpart") but the upstream contract needs a proper amendment. **Forward-pointer:** file as a candidate D-83/84-13 amendment on the #83/#84 blueprint when implementation starts. #87 records the gap and works around it with a forward-pointer P-O1-8; this keeps #87 unblocked.

---

## 9. References

- `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v2) — the design this blueprint evaluates
- `docs/task75-predeclared-eval-criteria-blueprint.md` — precedent for predeclared-eval discipline (retrieval-eval shape)
- `docs/task19-kpi-design.md` — earlier precedent (compile-side KPI predeclaration → CODEBASE_OVERVIEW §7)
- `docs/external-review-panel.md` — active reviewer panel (Codex + Deepseek + Qwen)
- `docs/CODEBASE_OVERVIEW.md` — architecture context
- `docs/what-is-ontology-for-V1.md` §9.4 — Round 6 closure that mandated #83/#84

---

## 10. Change log

- **2026-05-22** — v1 drafted. Pre-external-review. Operations roster compressed to 3 (per advisor input on mutation-eval-vs-retrieval-eval frame mismatch); probe-set curation filed as #87.1; HW rules with shaped thresholds; 5 new OQs filed.
- **2026-05-22** — v2 synthesized from Codex + Deepseek + Qwen v1 holistic reviews (3 reviewers, 16 substantive findings). Tier-1 structural amendments: O3 reframed as **hybrid op** (retrieval-eval + mutation invariant) per 3-reviewer convergence; P-O1-6 refactored to remove unfalsifiability from wall-clock dependency + reference deterministic-aggregation contract (OQ-26) instead of unratified formula; §9.4.7 hedge-source reconciliation + HW roster expanded to HW-1..HW-11 (added HW-8 vanity-graph attrition mapping the only §9.4.7 hedge in #87's territory; HW-9 promotion latency + HW-10 audit-trail growth + HW-11 LINKS_TO ↔ Claim divergence as #87-territory rules, not Round-6 lineage). Tier-2 amendments: O1 disposition correctness (P-O1-7 + F-O1-5); sequential multi-candidate probe axis; deferred state-transition removal from §7.1; F-O3-4 lazy-rewrite corruption. Tier-3 amendments: topology-only post-states for non-Claim action cells; P-O2-7/F-O2-4 positive Tier-3 criterion; F-O1-4 verifier output capture; retracted-counterpart coverage with forward-pointer OQ; P-O1-5 evidence cardinality. §7.2 probe template extended with `eval_config` block (clock + thresholds). **13 new OQs registered:** OQ-6..OQ-9 (HW-8/9/10/11 threshold OQs) + OQ-10..OQ-18 (reviewer-raised — human-review approval-input shape, invalid-pre-state policy, O3 split deferral, canonicalization integration boundary, LLM extraction non-determinism, floating-point tolerance, zero-EVIDENCES verifier behavior, lazy-rewrite/verifier flush timing, retracted-counterpart forward-pointer to #83/#84).
