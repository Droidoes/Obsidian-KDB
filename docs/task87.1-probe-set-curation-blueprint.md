# Task #87.1 — Probe-set curation — v1 spike phase

**Status:** v1 spike — 4 illustrative scenarios drafted 2026-05-22
**Parent task:** #87 (eval criteria blueprint v2 — commit `0d68688`)
**Workflow:** **(A) Spike-then-expand** — ratified 2026-05-22.
**Coverage target on expansion:** ~18 scenarios per #87 §7.1 v2 (#87 OQ-4 lean).
**Storage:** single blueprint doc with inline YAML scenarios; materialization to `tests/eval/promotion/scenarios/*.yaml` deferred to #83/#84 implementation start.
**External review:** none — scenarios are mechanical applications of #87 v2 criteria; if criteria-ambiguity surfaces, re-fire #87 v2 → v3, not #87.1 review.

---

## 0. TL;DR

#87 v2's §7.2 probe template is dense and hasn't faced real content. **Spike phase** writes 4 diverse scenarios to pressure-test the template before scaling to ~18. Each spike scenario is a self-contained YAML document covering one op + one axis. The spike surfaces:

- **Template gaps** (fields the v2 template didn't anticipate)
- **Per-op contract ambiguities** (where #87 v2 §4 criteria are mechanically under-specified)
- **Cross-criteria conflicts** (where two criteria step on each other under one scenario)
- **OQ resolution dependencies** (criteria that can't be made mechanical until an OQ resolves)

The deliverables of spike phase are:

1. **4 scenarios** (§3) — exercising O1 Claim-creating, O1 topology-only, O2 Tier-1, O3 aliased read.
2. **Template-stress observations** (§4) — what worked, what didn't, what was ambiguous.
3. **OQs surfaced from spike** (§5) — new questions not anticipated in #87 v2.
4. **Decisions needed before expansion** (§6) — gates that must close before writing scenarios 5–18.

Expansion phase (~14 more scenarios) is gated on the §6 decisions.

---

## 1. Spike-phase goal

The blueprint review pattern is: criteria first → probe set tests criteria → implementation tests probe set. The spike is a forcing function for the **middle step**: writing concrete pre-state + input + expected-post-state under real content reveals whether the criteria are actually mechanically checkable.

### What spike tests (not the full set):

- **§7.2 YAML template shape.** Are all the fields the template requires actually fillable for diverse scenario shapes? Are any required fields missing?
- **Per-op output contracts.** Can `expected_post_state` be specified deterministically for each op under the v2 criteria, given `eval_config` pinned?
- **Cross-axis interaction.** Does covering one axis (e.g., `disposition`) interact awkwardly with another axis (e.g., `retracted-counterpart`)?
- **OQ-leak.** Are there criteria that turn out to require an OQ resolution before a scenario can be written?

### What spike does NOT test (deferred to expansion):

- Full coverage of the 7 D-83/84-2 action cells (spike covers 2 of 7).
- Full coverage of the 3 upgrade tiers (spike covers 1 of 3).
- Full coverage of the 4 drift action-matrix cells (spike covers 1 of 4).
- Sequential-interaction axis (deferred — needs ≥2 scenarios in spike phase v2 if surfacing matters).
- Edge-case adversarial scenarios (deferred to a v2 probe-set expansion per #87 OQ-4 default lean).

---

## 2. Scenario selection rationale

Four scenarios chosen to maximize template stress and coverage diversity:

| # | Op | D-83/84-2 cell / axis | Stress purpose |
|---|---|---|---|
| **S1** | O1 | `contradicts` (Buffett 2020 tech-pivot from #83/#84 §2 worked example) | Claim-creating mutation; full Claim/EVIDENCES/CONTRADICTS post-state shape; `promotion_audit` envelope with non-trivial disposition |
| **S2** | O1 | `no_counterpart` (brand-new entity) | Topology-only post-state — exercises P-O1-2 "Claim-creating cells *vs* topology-only cells" split; **zero** Claim/EVIDENCES writes; LINKS_TO+SUPPORTS only |
| **S3** | O2 | Upgrade-from-LINKS_TO, **Tier-1** (run-payload reconstruction) | Two-Claim creation (OLD reconstructed + NEW analysis-emitted); `provenance_type` variation across EVIDENCES rows; D-83/84-9 ABOUT-authoritative binding |
| **S4** | O3 | Aliased-subject read + lazy rewrite | **Hybrid eval shape** — retrieval-eval class (P-O3-2 ALIAS_OF traversal) + mutation-invariant class (P-O3-5 lazy rewrite); exercises the §4.3 v2 split |

**Coverage matrix:**

- **All 3 ops** exercised.
- **O1 mutation-disposition split** (Claim-creating + topology-only).
- **O2 highest-information tier** (Tier 1; Tier 2/3 deferred to expansion).
- **O3 architectural hybrid frame** (the contentious framing question from v1 review).
- **Pre-state diversity:** populated-with-Claims (S1), minimal-graph (S2), populated-LINKS_TO-no-Claims (S3), populated-Claims-with-aliasing (S4).
- **`eval_config` fields:** every field used by at least one spike scenario.
- **`promotion_audit`:** disposition + counterpart_resolution_path exercised across S1/S2/S3.

---

## 3. Spike scenarios

> **Notation conventions:**
> - All ISO timestamps include explicit local offset (per `feedback_local_time_everywhere`).
> - `claim_id` follows `<claim_family_id>__v<N>` per #83/#84 D-83/84-6 F1 v2.
> - `claim_family_id` is `<subject_slug>__<predicate_class_canonical>__<predicate_scope_slugs_joined>` (delimiter guard: components are kebab-case, no `__` substring).
> - `Claim.confidence` placeholder values appear where OQ-26 aggregation formula isn't resolved yet (flagged inline as `# OQ-26-dependent`).
> - Floating-point equality uses `abs_diff < 1e-9` per #87 OQ-15 lean.

### 3.1 S1 — O1 `contradicts` (Buffett 2020 tech-pivot)

**Worked example anchor:** #83/#84 §2 — Buffett's 1995 avoid-tech stance is the prior Claim; the 2020 Apple investment is the contradicting candidate.

```yaml
scenario_id: s1-buffett-tech-contradicts-2020
description: |
  Existing active Claim "buffett_avoids_tech_investments" (from 1995 letter, 2
  evidences, high confidence). New candidate emitted from 2020 article
  reporting Buffett's Apple investment, classified as `contradicts`.
  Expected: NEW Claim created, CONTRADICTS edge to OLD Claim, EVIDENCES
  on NEW Claim, no mutation of LINKS_TO topology.
covers:
  - "action-cell: contradicts"
  - "drift-cell: fingerprint_drift=false, classification_drift=false"
  - "upgrade-tier: N/A (pre-existing Claim family)"
  - "state-transition: N/A (both Claims remain active)"
  - "aliasing: N/A"
  - "retracted-counterpart: N/A"
  - "sequential-interaction: N/A"
  - "HW-rule: N/A (single-candidate)"

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365.0
  default_read_confidence_threshold_t: 0.30
  confidence_map_version: "confidence_map_v1"
  read_mode: default  # unused by O1; included for template uniformity

pre_state:
  entities:
    - slug: warren-buffett
      canonical_id: warren-buffett
      domain: investing
    - slug: berkshire-hathaway
      canonical_id: berkshire-hathaway
      domain: investing
    - slug: apple-inc
      canonical_id: apple-inc
      domain: technology
  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
      state_hash: "links_to_state_v1"
      type: subject_mentions
  supports:
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: tech-industry
      role: object
  claims:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      claim_family_id: "warren-buffett__avoids_tech_investments__global"
      subject_slug: warren-buffett
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      modality: declarative
      confidence: 0.80  # OQ-26-dependent placeholder
      confidence_spread: 0.05  # OQ-26-dependent placeholder
      created_at: "1995-03-15T00:00:00+09:00"
  evidences:
    - source_id: KDB/raw/1995-buffett-letter.md
      claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      quoted_text: "I don't invest in technology businesses I don't understand."
      score: 0.80
      provenance_type: analysis_emitted
      created_at: "1995-03-15T00:00:00+09:00"
    - source_id: KDB/raw/1996-buffett-shareholder-meeting.md
      claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      quoted_text: "We stay away from tech because circle-of-competence."
      score: 0.80
      provenance_type: analysis_emitted
      created_at: "1996-05-04T00:00:00+09:00"
  edges: []  # no Claim-Claim edges yet
  about_edges:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      entity_slug: warren-buffett

input:
  candidate:
    candidate_id: cand-2020-buffett-apple
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: avoids_tech_investments  # canonicalized to existing family
    predicate_scope_slugs: ["global"]
    polarity: denies   # this is what makes it a contradiction
    modality: declarative
    counterpart_status: present  # has counterpart Claim
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: "warren-buffett__avoids_tech_investments__global__v1"
    doxastic_fingerprint:
      state_hash: "sha256:abc123def456..."  # placeholder
      classifier_input_scope:
        - "buffett_avoids_tech_investments_global_family"
        - "candidate_polarity"
    confidence:
      bucket: high
      score: 0.80
      score_source: config_map
      map_version: confidence_map_v1
    evidence:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  entities: unchanged
  links_to: unchanged
  supports:
    add:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        entity_slug: warren-buffett
        role: subject
  claims:
    add:
      - claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        claim_family_id: "warren-buffett__avoids_tech_investments__global"
        subject_slug: warren-buffett
        predicate_class_canonical: avoids_tech_investments
        predicate_scope_slugs: ["global"]
        version: 2
        state: active
        polarity: denies
        modality: declarative
        confidence: 0.80  # OQ-26-dependent placeholder
        confidence_spread: 0.00  # OQ-26-dependent placeholder
        created_at: "2026-06-01T00:00:00+09:00"
  evidences:
    add:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        score: 0.80
        provenance_type: analysis_emitted
        created_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        to_claim_id: "warren-buffett__avoids_tech_investments__global__v1"
        edge_type: CONTRADICTS
        created_at: "2026-06-01T00:00:00+09:00"
  about_edges:
    add:
      - claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        entity_slug: warren-buffett
  promotion_audit:
    candidate_id: cand-2020-buffett-apple
    fingerprint_drift: false
    classification_drift: false
    drift_explanation: null
    disposition: auto_promote
    counterpart_resolution_path: null  # counterpart is active, no resolution traversal needed
    classified_at: "2026-06-01T00:00:00+09:00"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - P-O1-1  # determinism: re-running this scenario should yield same classification
  - P-O1-2  # Claim-creating path: contradicts cell
  - P-O1-3  # idempotency (verified by retry pass)
  - P-O1-4  # drift signals false
  - P-O1-5  # evidence cardinality (1 entry → 1 EVIDENCES edge)
  - P-O1-6  # aggregate confidence (placeholder; OQ-26-blocked)
  - P-O1-7  # disposition auto_promote
  - F-O1-4  # invariant preservation (verifier clean post-mutation)
```

### 3.2 S2 — O1 `no_counterpart` (new entity)

**Stress purpose:** Topology-only post-state — exercises P-O1-2 split (Claim-creating *vs* topology-only). Verifies that O1 produces **zero** Claim/EVIDENCES writes for this cell while writing LINKS_TO + SUPPORTS.

```yaml
scenario_id: s2-new-entity-no-counterpart
description: |
  Brand-new entity ("nvidia-corp") never seen by the system before. Candidate
  has counterpart_status=no_counterpart. Expected: LINKS_TO + SUPPORTS
  writes only; ZERO Claim/EVIDENCES/Claim-Claim writes.
covers:
  - "action-cell: no_counterpart"
  - "drift-cell: fingerprint_drift=false, classification_drift=false"
  - "topology-only post-state (P-O1-2)"
  - "HW-rule: N/A"

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365.0
  default_read_confidence_threshold_t: 0.30
  confidence_map_version: "confidence_map_v1"
  read_mode: default

pre_state:
  entities: []   # empty — new-entity scenario
  links_to: []
  supports: []
  claims: []
  evidences: []
  edges: []
  about_edges: []

input:
  candidate:
    candidate_id: cand-nvidia-founded
    subject_slug: nvidia-corp
    predicate_class_raw: "founded_in"
    predicate_class_canonical: founded_in
    predicate_scope_slugs: ["temporal"]
    polarity: affirms
    modality: declarative
    counterpart_status: no_counterpart
    relation_kind: null   # no relation when no_counterpart
    refines_truth_conditions: false
    counterpart_claim_id: null
    doxastic_fingerprint:
      state_hash: "sha256:none000..."
      classifier_input_scope:
        - "subject_existence_check"
        - "context_key: founded_in__temporal"  # per #83/#84 D-83/84-8 Part A v2 null-counterpart distinguisher
    confidence:
      bucket: high
      score: 0.80
      score_source: config_map
      map_version: confidence_map_v1
    evidence:
      - source_id: KDB/raw/nvidia-founding-1993.md
        quoted_text: "NVIDIA Corporation was founded on April 5, 1993."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  entities:
    add:
      - slug: nvidia-corp
        canonical_id: nvidia-corp
        domain: technology  # inferred from source/context (impl-detail per OQ-26-adjacent)
  links_to:
    add:
      - from_slug: nvidia-corp
        to_slug: "1993"  # temporal-scope target (impl-detail: how scopes become topology)
        run_id: <runtime-assigned>
        state_hash: <runtime-computed>
        type: subject_temporal_assertion
  supports:
    add:
      - source_id: KDB/raw/nvidia-founding-1993.md
        entity_slug: nvidia-corp
        role: subject
  claims: unchanged  # zero Claim writes per topology-only contract
  evidences: unchanged
  edges: unchanged
  about_edges: unchanged
  promotion_audit:
    candidate_id: cand-nvidia-founded
    fingerprint_drift: false
    classification_drift: false
    drift_explanation: null
    disposition: auto_promote
    counterpart_resolution_path: null
    classified_at: "2026-06-01T00:00:00+09:00"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - P-O1-2  # topology-only path (zero Claim writes asserted explicitly)
  - P-O1-3  # idempotency
  - P-O1-4  # drift signals false
  - P-O1-7  # disposition auto_promote
  - F-O1-2  # negative: would fail if Claim were written
  - F-O1-4  # invariant preservation
```

### 3.3 S3 — O2 upgrade-from-LINKS_TO, Tier-1

**Stress purpose:** Two-Claim creation (OLD reconstructed + NEW analysis-emitted); D-83/84-7 Part B Tier-1 provenance via run-payload reconstruction; D-83/84-9 ABOUT-authoritative binding for both Claims.

```yaml
scenario_id: s3-buffett-tech-upgrade-tier1
description: |
  Existing LINKS_TO from a 1995 run (warren-buffett -> tech-industry, type
  subject_mentions). No Claim family exists yet. New candidate contradicts
  the implied topology. Expected: O2 fires. OLD Claim reconstructed from
  run-1995-buffett-letter's run-payload (Tier 1). NEW Claim created from
  the contradicting candidate. CONTRADICTS edge between them. Original
  LINKS_TO preserved (additive upgrade per D-83/84-7 Part A).
covers:
  - "action-cell: contradicts (under O2 upgrade)"
  - "upgrade-tier: Tier 1 (run-payload reconstruction)"
  - "two-Claim creation"

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365.0
  default_read_confidence_threshold_t: 0.30
  confidence_map_version: "confidence_map_v1"
  read_mode: default

pre_state:
  entities:
    - slug: warren-buffett
      canonical_id: warren-buffett
      domain: investing
    - slug: tech-industry
      canonical_id: tech-industry
      domain: technology
  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
      state_hash: "links_to_state_v1"
      type: subject_mentions
  supports:
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: tech-industry
      role: object
  claims: []   # no Claim family yet — this is the O2 precondition
  evidences: []
  edges: []
  about_edges: []
  # Auxiliary: run-payload available for Tier-1 reconstruction
  run_payloads:
    - run_id: run-1995-buffett-letter
      compile_result_path: KDB/runs/run-1995-buffett-letter/compile_result.json
      # Tier-1 reconstruction can extract: source_paths = [KDB/raw/1995-buffett-letter.md],
      # quoted_text = the original page text that produced the LINKS_TO edge.
      reconstructible_quote: "I don't invest in technology businesses I don't understand."

input:
  candidate:
    candidate_id: cand-2020-buffett-apple-upgrade
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: invests_in_technology  # NEW canonical predicate, no prior family
    predicate_scope_slugs: ["global"]
    polarity: affirms
    modality: declarative
    # O2 dispatch is DERIVED, not enum-named (per D-87.1-5 ratification 2026-05-22):
    # counterpart_status == candidate_counterpart_found
    # AND counterpart_claim_id == null  (no Claim family yet)
    # AND counterpart_links_to_ref != null  (LINKS_TO counterpart exists)
    counterpart_status: candidate_counterpart_found
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: null   # no Claim exists yet — dispatches to O2
    counterpart_links_to_ref:
      from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
    doxastic_fingerprint:
      state_hash: "sha256:xyz789..."
      classifier_input_scope:
        - "links_to_subject_mentions(buffett, tech-industry)"
        - "candidate_polarity"
    confidence:
      bucket: high
      score: 0.80
      score_source: config_map
      map_version: confidence_map_v1
    evidence:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  entities: unchanged
  links_to: unchanged   # additive upgrade per D-83/84-7 Part A
  supports:
    add:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        entity_slug: warren-buffett
        role: subject
  claims:
    add:
      # OLD Claim — reconstructed from run-payload (Tier 1)
      - claim_id: "warren-buffett__invests_in_technology__global__v1"
        claim_family_id: "warren-buffett__invests_in_technology__global"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in_technology
        predicate_scope_slugs: ["global"]
        version: 1
        state: active
        polarity: denies   # OLD Claim denies tech-investing per 1995 letter
        modality: declarative
        confidence: 0.70   # OQ-26-dependent placeholder (Tier-1 reconstructed → lower than analysis_emitted)
        confidence_spread: 0.00
        created_at: "2026-06-01T00:00:00+09:00"  # creation time is upgrade time, not source time
      # NEW Claim — analysis-emitted from candidate
      - claim_id: "warren-buffett__invests_in_technology__global__v2"
        claim_family_id: "warren-buffett__invests_in_technology__global"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in_technology
        predicate_scope_slugs: ["global"]
        version: 2
        state: active
        polarity: affirms
        modality: declarative
        confidence: 0.80   # OQ-26-dependent placeholder
        confidence_spread: 0.00
        created_at: "2026-06-01T00:00:00+09:00"
  evidences:
    add:
      # OLD-Claim EVIDENCES — provenance_type=reconstructed_from_run_payload
      - source_id: KDB/raw/1995-buffett-letter.md
        claim_id: "warren-buffett__invests_in_technology__global__v1"
        quoted_text: "I don't invest in technology businesses I don't understand."
        score: null   # MAY be null per P-O2-3 (Tier-1 reconstruction does not assign analysis-time score)
        provenance_type: reconstructed_from_run_payload
        created_at: "2026-06-01T00:00:00+09:00"
      # NEW-Claim EVIDENCES — analysis_emitted
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        claim_id: "warren-buffett__invests_in_technology__global__v2"
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        score: 0.80
        provenance_type: analysis_emitted
        created_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__invests_in_technology__global__v2"
        to_claim_id: "warren-buffett__invests_in_technology__global__v1"
        edge_type: CONTRADICTS
        created_at: "2026-06-01T00:00:00+09:00"
  about_edges:
    add:
      - claim_id: "warren-buffett__invests_in_technology__global__v1"
        entity_slug: warren-buffett
      - claim_id: "warren-buffett__invests_in_technology__global__v2"
        entity_slug: warren-buffett
  promotion_audit:
    candidate_id: cand-2020-buffett-apple-upgrade
    fingerprint_drift: false
    classification_drift: false
    drift_explanation: null
    disposition: auto_promote
    counterpart_resolution_path: "via_links_to(run-1995-buffett-letter)→tier1_reconstruct"
    classified_at: "2026-06-01T00:00:00+09:00"
    provenance_attempt_tier1: succeeded
    provenance_attempt_tier2: not_attempted
    provenance_synthesized_marker: false

expected_invariants_hold: true
expected_op_to_invoke: O2
exercised_criteria:
  - P-O2-1  # both Claims created
  - P-O2-2  # OLD-Claim EVIDENCES provenance_type=reconstructed_from_run_payload
  - P-O2-3  # NULL-fields permitted on Tier-1 EVIDENCES
  - P-O2-4  # ABOUT edges on both Claims
  - P-O2-5  # LINKS_TO unchanged (additive)
  - P-O2-6  # idempotency
  - F-O2-1  # negative: would fail if LINKS_TO mutated
  - F-O2-3  # negative: would fail if OLD-Claim EVIDENCES were analysis_emitted
  - F-O1-4  # invariant preservation
```

### 3.4 S4 — O3 aliased-subject read + lazy rewrite

**Stress purpose:** Hybrid eval shape — retrieval-eval class (returning the right Claims through ALIAS_OF) + mutation-invariant class (lazy rewrite of stale denormalized `subject_slug`). Exercises §4.3 v2 split.

```yaml
scenario_id: s4-aliased-read-lazy-rewrite
description: |
  Two entities: "warren-buffett" (canonical) and "buffett" (alias via
  ALIAS_OF). A Claim exists with subject_slug="buffett" (denormalized key
  is stale — set before canonicalization merged the alias). Read tuple
  uses canonical "warren-buffett". Expected: read resolves through
  ALIAS_OF to the Claim, returns it, AND triggers lazy rewrite of the
  stale subject_slug to "warren-buffett".
covers:
  - "action-cell: N/A (O3 is read)"
  - "aliasing: ALIAS_OF traversal + lazy rewrite (D-83/84-9)"
  - "O3 hybrid eval shape (retrieval + mutation invariant)"

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365.0
  default_read_confidence_threshold_t: 0.30
  confidence_map_version: "confidence_map_v1"
  read_mode: default

pre_state:
  entities:
    - slug: warren-buffett
      canonical_id: warren-buffett
      domain: investing
    - slug: buffett
      canonical_id: warren-buffett   # alias resolves to canonical
      domain: investing
  alias_of_edges:
    - from_slug: buffett
      to_slug: warren-buffett
  links_to: []
  supports:
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: buffett   # stale: SUPPORTS row predates canonicalization
      role: subject
  claims:
    - claim_id: "buffett__avoids_tech_investments__global__v1"   # NOTE: claim_id uses stale slug
      claim_family_id: "buffett__avoids_tech_investments__global"
      subject_slug: buffett   # STALE denormalized key — should be "warren-buffett" post-canonicalization
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      modality: declarative
      confidence: 0.80
      confidence_spread: 0.05
      created_at: "1995-03-15T00:00:00+09:00"
  evidences:
    - source_id: KDB/raw/1995-buffett-letter.md
      claim_id: "buffett__avoids_tech_investments__global__v1"
      quoted_text: "I don't invest in technology businesses I don't understand."
      score: 0.80
      provenance_type: analysis_emitted
      created_at: "1995-03-15T00:00:00+09:00"
  edges: []
  about_edges:
    - claim_id: "buffett__avoids_tech_investments__global__v1"
      entity_slug: warren-buffett   # ABOUT is authoritative — points to canonical even when subject_slug is stale

input:
  read_tuple:
    subject_slug: warren-buffett   # canonical query
    predicate_class_canonical: avoids_tech_investments
    predicate_scope_slugs: ["global"]

expected_post_state:
  entities: unchanged
  alias_of_edges: unchanged
  links_to: unchanged
  supports: unchanged   # lazy rewrite scope is Claims only per D-83/84-9
  claims:
    update:
      # Lazy rewrite: subject_slug + claim_family_id + claim_id rewritten to canonical
      - selector: { previous_claim_id: "buffett__avoids_tech_investments__global__v1" }
        new_values:
          claim_id: "warren-buffett__avoids_tech_investments__global__v1"
          claim_family_id: "warren-buffett__avoids_tech_investments__global"
          subject_slug: warren-buffett
        # All other Claim fields unchanged
  evidences:
    update:
      - selector: { previous_claim_id: "buffett__avoids_tech_investments__global__v1" }
        new_values:
          claim_id: "warren-buffett__avoids_tech_investments__global__v1"
        # Other EVIDENCES fields unchanged
  edges: unchanged
  about_edges:
    update:
      - selector: { previous_claim_id: "buffett__avoids_tech_investments__global__v1" }
        new_values:
          claim_id: "warren-buffett__avoids_tech_investments__global__v1"

expected_read_result:
  claims_returned:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"   # post-rewrite ID
      polarity: affirms
      modality: declarative
      confidence: 0.80
  resolution_path: "via_alias_of(warren-buffett ← buffett)→claim_family__avoids_tech_investments__global"

expected_invariants_hold: true
expected_op_to_invoke: O3
exercised_criteria:
  - P-O3-1  # tuple-granularity (Claim returned, not LINKS_TO fallback)
  - P-O3-2  # aliased-subject resolution through ALIAS_OF
  - P-O3-3  # default-mode read; no retracted Claims in fixture
  - P-O3-4  # decayed-below-threshold filtering (Claim is above T_scenario)
  - P-O3-5  # lazy rewrite triggered iff stale (stale present → rewrite fires; touches only the stale Claim)
  - F-O3-1  # negative: would fail if subject-granularity contamination
  - F-O3-2  # negative: would fail if alias miss
  - F-O3-4  # negative: would fail if lazy rewrite produces malformed claim_family_id
```

---

## 4. Template-stress observations

### 4.1 What worked

| Field / shape | Observation |
|---|---|
| `eval_config` block | Clean fit. Every field is used at least once across S1–S4; no field is dead weight. |
| `pre_state` ↔ `expected_post_state` shape parity | YAML structure mirrors well — easy to spot diffs. |
| `exercised_criteria` enumeration per scenario | Useful traceability artifact. Lets a runner verify each scenario actually tests what it claims. Recommend keeping as required field. |
| `expected_op_to_invoke` | Acts as a sanity check — if O1 is dispatched but the scenario expected O2, that's itself a fail. |
| `disposition` + `counterpart_resolution_path` in promotion_audit | Each is small but load-bearing. The diagnostic value showed up immediately when writing S3 (where Tier-1 reconstruction *is* the resolution path). |

### 4.2 What didn't work cleanly — surfaced template gaps

| Gap | Surfaced in | Discussion |
|---|---|---|
| **`expected_post_state.claims` shape: `unchanged` / `add` / `update` semantics** | S1 (add), S2 (unchanged), S4 (update) | The v2 template (#87 §7.2) uses flat `claims: ...` syntax that doesn't distinguish "specify the new full state" vs "specify the delta from pre-state." Spike scenarios needed explicit `add` / `update` / `unchanged` keys to be unambiguous. **Decision needed: D-87.1-1 — adopt explicit-delta YAML shape.** |
| **`run_payloads` block under `pre_state`** | S3 | Tier-1 reconstruction needs access to historical run sidecars, but the v2 §7.2 template has no field for representing run-payload availability in pre-state. Spike invented `run_payloads:` block; needs ratifying as a template extension. **Decision needed: D-87.1-2.** |
| **`alias_of_edges` block under `pre_state`** | S4 | ALIAS_OF is a separate edge type per D-83/84-9 but isn't in the v2 §7.2 pre-state list (which has `entities`, `links_to`, `supports`, `claims`, `edges`). Spike added `alias_of_edges:` as its own block (parallel to `about_edges`). **Decision needed: D-87.1-3.** |
| **`about_edges` block** | All scenarios | v2 §7.2 lumps `edges` as a single bucket but D-83/84-9 makes ABOUT a distinct edge type with its own integrity contract. Spike separated `about_edges:` from `edges:` (Claim-Claim edges). **Decision needed: D-87.1-3.** |
| **Runtime-assigned fields** (`run_id`, `state_hash`, `classified_at`) | S2 (LINKS_TO write), S3 | Some post-state fields are runtime-assigned (the implementation generates them, not the scenario author). v2 §7.2 doesn't specify how to mark these. Spike uses `<runtime-assigned>` / `<runtime-computed>` placeholders. **Decision needed: D-87.1-4 — formal marker syntax.** |
| **`counterpart_status` extensions** | S3 | D-83/84-7 specifies upgrade-from-LINKS_TO but doesn't formally enumerate the `counterpart_status` value that triggers O2 dispatch. Spike used `implied_by_links_to`. **Decision needed: D-87.1-5 — confirm or rename to match #83/#84 envelope.** |
| **O3 input shape — `read_tuple` not `candidate`** | S4 | v2 §7.2 template assumes `input.candidate` for the input section, but O3's input is a read tuple, not a candidate envelope. Spike used `input.read_tuple`. **Decision needed: D-87.1-6 — accept divergent input shape per op.** |
| **`expected_read_result` block (O3 only)** | S4 | O3's retrieval-eval class needs a "what does the read return" assertion separate from post-state. Spike added `expected_read_result:` for O3 scenarios. **Decision needed: D-87.1-7 — adopt as O3-specific block.** |

### 4.3 OQ-resolution dependencies surfaced

- **OQ-26 (aggregation formula)** is the most blocking. Every Claim-creating scenario has `confidence` and `confidence_spread` placeholders that can't be computed mechanically until the formula resolves. Spike uses inline `# OQ-26-dependent placeholder` comments; expansion can stay this way until OQ-26 closes.
- **OQ-15 (floating-point tolerance)** — spike adopts `abs_diff < 1e-9` (the OQ-15 lean) inline in the runner contract; doesn't affect YAML.
- **OQ-26 (aggregation formula) + OQ-29 (`tau`) interaction** — confidence values in S1's post-state are placeholders because the OLD Claim has 2 evidences pre-mutation and the new aggregate after a third evidence appears depends on both. Spike writes the values forward and tags them; expansion will need a final pass once OQs resolve.

### 4.4 Cross-criteria conflict check

No conflicts observed in the 4-scenario spike. Specifically tested:

- P-O1-2 (action correctness) vs P-O1-5 (evidence cardinality): consistent in S1.
- P-O1-2 (topology-only) vs F-O1-2 (action violation): S2 expected post-state asserts both positively (Claim absence) and negatively (no_counterpart cell did write LINKS_TO).
- P-O2-2 (provenance tier) vs P-O2-3 (NULL fields): S3 demonstrates the legitimate interaction (Tier-1 → reconstructed_from_run_payload → NULL score permitted).
- P-O3-2 (aliased resolution) vs P-O3-5 (lazy rewrite): S4 demonstrates they fire together cleanly.

---

## 5. OQs surfaced from spike (new — not anticipated in #87 v2)

### OQ-S1 — Pre-state representation: full-state vs delta-from-base?

Each spike scenario specifies `pre_state` as a complete fixture. For ~18 scenarios with overlapping setups (e.g., Buffett-investing context appears across S1, S3, possibly others), this duplicates content. Should `pre_state` support `extends: <base_fixture_id>` inheritance, or stay self-contained per scenario?

**Lean:** keep self-contained for v1 — DRY-via-base-fixture adds complexity, and 18 scenarios is not yet at the cost-of-duplication threshold. Revisit at probe-set v2 expansion.

### OQ-S2 — Probe-set runner: dynamic vs static post-state matching?

`expected_post_state` with `unchanged` / `add` / `update` keys (per D-87.1-1) implies the runner computes the post-state diff dynamically. Alternatively, scenarios specify the full post-state and the runner does a full graph snapshot diff. Trade-off: dynamic diff is more readable in YAML but requires diff machinery; static full-state is simpler runner-side but bloats YAML.

**Lean:** dynamic diff for readability — the runner machinery is one-time cost; per-scenario readability is reproductive cost.

### OQ-S3 — Should scenarios specify the runtime-assigned field values, or assert "any non-null"?

For `run_id` / `state_hash` / `classified_at`, the scenario author can't deterministically predict the values (they depend on runtime UUID generation, current clock, etc.). Options: (a) scenario asserts `<runtime-assigned>` placeholder = "any non-null value satisfies"; (b) scenario specifies expected values and runner injects them; (c) scenario asserts only structural presence, not value.

**Lean:** (a) for runtime-UUID-like fields, (c) for time-stamps when `eval_clock` is in effect (the runner uses `eval_clock` for `classified_at`, so it IS predictable).

### OQ-S4 — How does O3 specify "read mode" — top-level field or eval_config?

S4 uses `eval_config.read_mode: default`, but for O3 specifically the read mode is per-call (the same Claim graph can be read in default or audit mode by different consumers). Should O3 scenarios specify `read_mode` in `input` (parallel to the read tuple) rather than `eval_config`?

**Lean:** move `read_mode` from `eval_config` to `input.read_mode` for O3 scenarios. `eval_config.read_mode` was a placeholder unused by O1/O2; making it O3-input-only matches the contract.

### OQ-S5 — How to encode "negative" criteria (F-On-N) explicitly?

S1's `exercised_criteria` lists `F-O1-4` (invariant preservation), but the scenario is a *positive* case where F-O1-4 should NOT fire. S2 lists `F-O1-2` similarly. Should there be a separate `would_fail_if` block (or a per-criterion expected truth value) to make positive vs negative explicit?

**Lean:** add `expected_to_pass` / `expected_to_fire` annotation to `exercised_criteria` entries. Default: P-* expected_to_pass; F-* expected_to_not_fire. Scenarios that *should* fire an F-* criterion (adversarial test) flip the flag.

### OQ-S6 — Probe-set storage location once materialized

#87 §7.3 noted `tests/eval/promotion/scenarios/*.yaml` as likely. Spike confirms YAML is the right format. Open: does each scenario become one file (e.g., `s1-buffett-tech-contradicts-2020.yaml`), or are they grouped by op (`o1.yaml`, `o2.yaml`, `o3.yaml`)?

**Lean:** one file per scenario — easier review-per-scenario, easier diff, easier addition of new scenarios. Group by op via directory: `tests/eval/promotion/scenarios/o1/*.yaml` etc. Defer to #83/#84 implementation start.

### OQ-S7 — Should O1-vs-O2 dispatch be an explicit field on the candidate, or stay derived?

Surfaced by D-87.1-5 ratification 2026-05-22. The current contract derives O2 dispatch from three fields jointly: `counterpart_status == candidate_counterpart_found` AND `counterpart_claim_id == null` AND `counterpart_links_to_ref != null`. This is correct per #83/#84 but means the dispatch logic is **implicit** — a reader scanning a scenario must reconstruct the dispatch from three fields rather than read one.

**Tradeoff:**
- **Stay derived (current):** No new vocabulary in #83/#84; single source of truth (the three fields the Promotion Contract already needs anyway); no risk of a `dispatch_path` field disagreeing with the underlying fields.
- **Add explicit `op_dispatch_path: O1 | O2`:** More readable in scenarios; lets the probe runner assert dispatch correctness directly (does the dispatcher route to the right handler?). Cost: new field that must be kept consistent with the three derived inputs.

**Lean:** stay derived in #87.1 scenarios; revisit if #83/#84 implementation introduces a `dispatch_path` field at the dispatcher level (in which case scenarios can mirror it). Defer to #83/#84 implementation start.

---

## 6. Decisions needed before expansion (D-87.1-*)

**Status: ratified 2026-05-22.** All 10 decisions adopted as their lean (D-87.1-5 with vocabulary correction — see "Ratification outcome" column).

These gate the expansion from 4 spike scenarios to ~18 full coverage. Each is small, but writing 14 more without these decisions risks mass rework.

| # | Decision | Spike-surface basis | Ratification outcome (2026-05-22) |
|---|---|---|---|
| **D-87.1-1** | Adopt `unchanged` / `add` / `update` explicit-delta shape for `expected_post_state.*` | All four scenarios | **Ratified.** Self-documenting. v2 §7.2 template superseded by this spike-doc's shape; v2 §7.2 to be amended in a follow-up patch. |
| **D-87.1-2** | Add `pre_state.run_payloads:` block for Tier-1 fixtures | S3 | **Ratified.** Tier-2 and Tier-3 also need run/SUPPORTS-graph awareness in pre-state; field is canonical. |
| **D-87.1-3** | Split `edges:` into `about_edges:` + `alias_of_edges:` + `edges:` (Claim-Claim only) | S3, S4 | **Ratified.** Each edge type has different integrity contract; bucketing prevents ambiguity. |
| **D-87.1-4** | Marker syntax for runtime-assigned fields: `<runtime-assigned>` for UUID-like; `<eval_clock>` for time | S2, S3 | **Ratified.** Marker is explicit; runner has unambiguous matching rules. |
| **D-87.1-5** | Confirm `counterpart_status: implied_by_links_to` triggers O2 dispatch | S3 | **Ratified with correction.** Verify result: `implied_by_links_to` is **not** in the #83/#84 `counterpart_status` enum. Canonical enum (per D-83/84-2 §94 + §696) is `no_counterpart` \| `candidate_counterpart_found` \| `orthogonal`. **O2 dispatch is derived, not enum-named:** `counterpart_status == candidate_counterpart_found` AND `counterpart_claim_id == null` AND `counterpart_links_to_ref != null`. S3 input field corrected. See OQ-S7 for follow-up. |
| **D-87.1-6** | Allow input shape divergence per op: `input.candidate` for O1/O2; `input.read_tuple` for O3 | S4 | **Ratified.** Forcing O3 reads through `candidate` shape was awkward in S4. |
| **D-87.1-7** | Add `expected_read_result:` block for O3 scenarios | S4 | **Ratified.** O3's retrieval-eval class needs an output-assertion field distinct from `expected_post_state`. |
| **D-87.1-8** | Move `read_mode` from `eval_config` to `input.read_mode` (O3 only) | OQ-S4 | **Ratified.** `eval_config.read_mode` is unused for O1/O2; it belongs with the read tuple semantically. |
| **D-87.1-9** | Add `expected_to_pass` / `expected_to_fire` annotation to `exercised_criteria` entries | OQ-S5 | **Ratified.** Makes positive-vs-adversarial intent machine-readable. |
| **D-87.1-10** | Confidence placeholders stay until OQ-26 resolves | All Claim-creating scenarios | **Ratified.** Block expansion only on D-87.1-1..9; confidence values are amendable in-place when OQ-26 closes. |

---

## 7. Expansion plan (post-ratification of §6 decisions)

Remaining ~14 scenarios to write:

| Axis | Spike covers | Expansion adds |
|---|---|---|
| Action-table cells (7) | `contradicts`, `no_counterpart` (2) | `reinforces`, `qualifies-with-truth`, `qualifies-without-truth`, `supersedes`, `orthogonal` (5) |
| Upgrade tiers (3) | Tier 1 (1) | Tier 2, Tier 3 (2) |
| Drift cells (4) | `(false, false)` only — implicit in all spike (1) | `(true, false)`, `(false, true)`, `(true, true)` (3) |
| State transitions (1 — `active → superseded`) | Not covered | 1 dedicated scenario |
| Aliasing (1) | S4 (1) | Subject-canonicalized-between-runs variant (1) |
| Retracted-counterpart (2) | Not covered | 2 (sibling-active and no-active-sibling) |
| Sequential-interaction (1) | Not covered | 1 dedicated scenario |
| **Total expansion** | **4 spike** | **~14 expansion** = ~18 full coverage |

Expansion ratification gate: §6 decisions ratified → 14 scenarios written → spot-check pass → #87.1 v1 ratified → unblocks #83/#84 implementation start.

---

## 8. Change log

- **2026-05-22** — v1 spike-phase draft. 4 scenarios (S1 O1 contradicts, S2 O1 no_counterpart, S3 O2 Tier-1 upgrade, S4 O3 aliased read). Template-stress observations + 6 OQs (OQ-S1..S6) + 10 decision gates (D-87.1-1..10) surfaced. Expansion to ~18 scenarios blocked on D-87.1-1..9 ratification.
- **2026-05-22** — §6 decisions D-87.1-1..10 **ratified**. D-87.1-5 ratified with vocabulary correction: `implied_by_links_to` is not a valid `counterpart_status` enum value per #83/#84 D-83/84-2; canonical enum is `no_counterpart` | `candidate_counterpart_found` | `orthogonal`. O2 dispatch is derived (not enum-named): `counterpart_status == candidate_counterpart_found` AND `counterpart_claim_id == null` AND `counterpart_links_to_ref != null`. S3 input field corrected accordingly. **OQ-S7 added** (should dispatch path be explicit or stay derived — current lean: stay derived). Expansion to 14 more scenarios now unblocked.
