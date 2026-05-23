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

## 3. Probe scenarios

> **Notation conventions:**
> - All ISO timestamps include explicit local offset (per `feedback_local_time_everywhere`).
> - `claim_id` follows `<claim_family_id>__v<N>` per #83/#84 D-83/84-6 F1 v2.
> - `claim_family_id` is `<subject_slug>__<predicate_class_canonical>__<predicate_scope_slugs_joined>` (delimiter guard: components are kebab-case, no `__` substring).
> - `Claim.confidence` placeholder values appear where OQ-26 aggregation formula isn't resolved yet (flagged inline as `# OQ-26-dependent`).
> - Floating-point equality uses `abs_diff < 1e-9` per #87 OQ-15 lean.

> **Origin:** §§3.1–3.4 (S1–S4) are the **spike** scenarios drafted 2026-05-22 before §6 ratification. §§3.5+ are **expansion** scenarios written against the ratified template shape (D-87.1-1..10). All scenarios are equally first-class probes; the spike/expansion distinction is historical, not functional.

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
  - {id: P-O1-1, expected: pass, note: "determinism: re-running this scenario should yield same classification"}
  - {id: P-O1-2, expected: pass, note: "Claim-creating path: contradicts cell"}
  - {id: P-O1-3, expected: pass, note: "idempotency (verified by retry pass)"}
  - {id: P-O1-4, expected: pass, note: "drift signals false"}
  - {id: P-O1-5, expected: pass, note: "evidence cardinality (1 entry → 1 EVIDENCES edge)"}
  - {id: P-O1-6, expected: pass, note: "aggregate confidence (placeholder; OQ-26-blocked)"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (verifier clean post-mutation)"}
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
  - {id: P-O1-2, expected: pass, note: "topology-only path (zero Claim writes asserted explicitly)"}
  - {id: P-O1-3, expected: pass, note: "idempotency"}
  - {id: P-O1-4, expected: pass, note: "drift signals false"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if Claim were written"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation"}
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
  - {id: P-O2-1, expected: pass, note: "both Claims created"}
  - {id: P-O2-2, expected: pass, note: "OLD-Claim EVIDENCES provenance_type=reconstructed_from_run_payload"}
  - {id: P-O2-3, expected: pass, note: "NULL-fields permitted on Tier-1 EVIDENCES"}
  - {id: P-O2-4, expected: pass, note: "ABOUT edges on both Claims"}
  - {id: P-O2-5, expected: pass, note: "LINKS_TO unchanged (additive)"}
  - {id: P-O2-6, expected: pass, note: "idempotency"}
  - {id: F-O2-1, expected: not_fire, note: "would fail if LINKS_TO mutated"}
  - {id: F-O2-3, expected: not_fire, note: "would fail if OLD-Claim EVIDENCES were analysis_emitted"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation"}
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
  - {id: P-O3-1, expected: pass, note: "tuple-granularity (Claim returned, not LINKS_TO fallback)"}
  - {id: P-O3-2, expected: pass, note: "aliased-subject resolution through ALIAS_OF"}
  - {id: P-O3-3, expected: pass, note: "default-mode read; no retracted Claims in fixture"}
  - {id: P-O3-4, expected: pass, note: "decayed-below-threshold filtering (Claim is above T_scenario)"}
  - {id: P-O3-5, expected: pass, note: "lazy rewrite triggered iff stale (stale present → rewrite fires; touches only the stale Claim)"}
  - {id: F-O3-1, expected: not_fire, note: "would fail if subject-granularity contamination"}
  - {id: F-O3-2, expected: not_fire, note: "would fail if alias miss"}
  - {id: F-O3-4, expected: not_fire, note: "would fail if lazy rewrite produces malformed claim_family_id"}
```

---

### 3.5 S5 — O1 `reinforces` (corroboration crosses threshold N, triggers upgrade)

**Stress purpose:** Exercises the corroboration-threshold-crossing branch of D-83/84-2 — `reinforces` action with corroboration count = N triggers upgrade. Single Claim consolidates multiple SUPPORTS sources (consensus path; no contradiction, no Claim-Claim edge).

```yaml
scenario_id: s5-buffett-long-term-holding-reinforces-threshold
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
      kind: person
    - slug: long-term-holding-strategy
      kind: concept

  links_to:
    # Two prior LINKS_TO from independent runs — candidate is the 3rd corroboration (= N)
    - from_slug: warren-buffett
      to_slug: long-term-holding-strategy
      run_id: run-2010-buffett-letter
      predicate_class_canonical: practices_strategy
      predicate_scope_slugs: ["global"]
      polarity: affirms
    - from_slug: warren-buffett
      to_slug: long-term-holding-strategy
      run_id: run-2015-buffett-letter
      predicate_class_canonical: practices_strategy
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    - source_id: KDB/raw/2010-buffett-letter.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/2015-buffett-letter.md
      entity_slug: warren-buffett
      role: subject

  claims: []
  edges: []
  about_edges: []
  alias_of_edges: []

  run_payloads:
    - run_id: run-2010-buffett-letter
      compile_result_path: KDB/runs/run-2010-buffett-letter/compile_result.json
      reconstructible_quote: "I prefer to hold investments indefinitely; my favorite holding period is forever."
    - run_id: run-2015-buffett-letter
      compile_result_path: KDB/runs/run-2015-buffett-letter/compile_result.json
      reconstructible_quote: "Time is the friend of the wonderful business."

input:
  candidate:
    candidate_id: cand-2020-buffett-long-term-holding-3
    subject_slug: warren-buffett
    predicate_class_raw: "practices_strategy"
    predicate_class_canonical: practices_strategy
    predicate_scope_slugs: ["global"]
    polarity: affirms
    modality: declarative
    # Dispatch derivation (per D-87.1-5): candidate_counterpart_found + null claim_id + non-null LINKS_TO ref → O2-eligible.
    # But relation_kind=reinforces + corroboration_count reaches N → upgrade triggered, routes through O1's upgrade-from-reinforces branch.
    counterpart_status: candidate_counterpart_found
    relation_kind: reinforces
    refines_truth_conditions: false
    counterpart_claim_id: null
    counterpart_links_to_ref:
      from_slug: warren-buffett
      to_slug: long-term-holding-strategy
    doxastic_fingerprint:
      state_hash: "sha256:reinforces_threshold..."
      classifier_input_scope:
        - "links_to_subject_mentions(warren-buffett, long-term-holding-strategy)"
        - "supports_cardinality_for_predicate(practices_strategy)"
    confidence:
      bucket: high
      score: 0.80
      score_source: config_map
      map_version: confidence_map_v1
    evidence:
      - source_id: KDB/raw/2020-buffett-letter.md
        quoted_text: "Our preferred holding period remains forever."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  entities: unchanged
  links_to: unchanged   # additive; not deleted on upgrade per D-83/84-7 Part A
  supports:
    add:
      - source_id: KDB/raw/2020-buffett-letter.md
        entity_slug: warren-buffett
        role: subject
  claims:
    add:
      # SINGLE Claim — consensus path consolidates all three corroborating sources
      - claim_id: "warren-buffett__practices_strategy__global__v1"
        claim_family_id: "warren-buffett__practices_strategy__global"
        subject_slug: warren-buffett
        predicate_class_canonical: practices_strategy
        predicate_scope_slugs: ["global"]
        version: 1
        state: active
        polarity: affirms
        modality: declarative
        provenance_type: analysis_emitted
        confidence: <placeholder-pending-OQ-26>
        confidence_spread: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
  edges: []   # no Claim-Claim edges — consensus, not contradiction
  about_edges:
    add:
      - claim_id: "warren-buffett__practices_strategy__global__v1"
        entity_slug: warren-buffett
        role: subject
  evidences:
    add:
      # 3 EVIDENCES — 2 reconstructed via Tier-1 + 1 analysis_emitted from current candidate
      - source_id: KDB/raw/2010-buffett-letter.md
        claim_id: "warren-buffett__practices_strategy__global__v1"
        quoted_text: "I prefer to hold investments indefinitely; my favorite holding period is forever."
        provenance_type: reconstructed_from_run_payload
        confidence: 0.80
      - source_id: KDB/raw/2015-buffett-letter.md
        claim_id: "warren-buffett__practices_strategy__global__v1"
        quoted_text: "Time is the friend of the wonderful business."
        provenance_type: reconstructed_from_run_payload
        confidence: 0.80
      - source_id: KDB/raw/2020-buffett-letter.md
        claim_id: "warren-buffett__practices_strategy__global__v1"
        quoted_text: "Our preferred holding period remains forever."
        provenance_type: analysis_emitted
        confidence: 0.80

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"
  upgrade_trigger: corroboration_threshold_crossed
  corroboration_count_at_upgrade: 3   # equals corroboration_threshold_n

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-2, expected: pass, note: "reinforces-above-threshold (Claim-creating consensus path)"}
  - {id: P-O1-5, expected: pass, note: "3 unique evidence sources → 3 EVIDENCES edges (mixed Tier-1 + analysis_emitted)"}
  - {id: P-O1-6, expected: pass, note: "aggregate confidence over 3 sources (placeholder; OQ-26-blocked)"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if reinforces with corroboration < N wrote a Claim"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (single Claim; no Claim-Claim edge)"}
```

---

### 3.6 S6 — O1 `qualifies_or_extends` with `refines_truth_conditions=true` (triggers upgrade)

**Stress purpose:** Refining truth conditions across predicate-scope variation. Creates NEW Claim family (different `predicate_scope_slugs`); OLD family Claim preserved; Claim-Claim `QUALIFIES` edge written.

```yaml
scenario_id: s6-buffett-apple-investment-qualified-by-valuation
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: apple-inc

  links_to:
    - from_slug: warren-buffett
      to_slug: apple-inc
      run_id: run-2020-buffett-apple-stake
      predicate_class_canonical: invests_in
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    - source_id: KDB/raw/2020-buffett-apple-stake.md
      entity_slug: warren-buffett
      role: subject

  claims:
    - claim_id: "warren-buffett__invests_in__global__v1"
      claim_family_id: "warren-buffett__invests_in__global"
      subject_slug: warren-buffett
      predicate_class_canonical: invests_in
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      object_slug: apple-inc
      provenance_type: analysis_emitted
      confidence: 0.80

  about_edges:
    - claim_id: "warren-buffett__invests_in__global__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2023-buffett-apple-valuation-qualifier
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in"
    predicate_class_canonical: invests_in
    predicate_scope_slugs: ["valuation_constrained"]   # DIFFERENT scope → different family
    polarity: affirms
    modality: declarative
    counterpart_status: candidate_counterpart_found
    relation_kind: qualifies_or_extends
    refines_truth_conditions: true   # KEY: refines → Claim-creating
    counterpart_claim_id: "warren-buffett__invests_in__global__v1"
    counterpart_links_to_ref: null
    doxastic_fingerprint:
      state_hash: "sha256:qualifies_truth..."
      classifier_input_scope:
        - "claim_family(warren-buffett__invests_in__global)"
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2023-buffett-valuation-discipline.md
        quoted_text: "We only invest in great businesses when the price is reasonable."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  entities: unchanged
  links_to: unchanged
  supports:
    add:
      - source_id: KDB/raw/2023-buffett-valuation-discipline.md
        entity_slug: warren-buffett
        role: subject
  claims:
    add:
      - claim_id: "warren-buffett__invests_in__valuation_constrained__v1"
        claim_family_id: "warren-buffett__invests_in__valuation_constrained"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in
        predicate_scope_slugs: ["valuation_constrained"]
        version: 1
        state: active
        polarity: affirms
        provenance_type: analysis_emitted
        confidence: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__invests_in__valuation_constrained__v1"
        to_claim_id: "warren-buffett__invests_in__global__v1"
        kind: QUALIFIES
  about_edges:
    add:
      - claim_id: "warren-buffett__invests_in__valuation_constrained__v1"
        entity_slug: warren-buffett
        role: subject
  evidences:
    add:
      - source_id: KDB/raw/2023-buffett-valuation-discipline.md
        claim_id: "warren-buffett__invests_in__valuation_constrained__v1"
        provenance_type: analysis_emitted

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-2, expected: pass, note: "qualifies-with-truth (Claim-creating + Claim-Claim QUALIFIES edge)"}
  - {id: P-O1-5, expected: pass, note: "single evidence entry → single EVIDENCES edge"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if no Claim created OR if QUALIFIES edge missing"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (OLD Claim untouched; two-Claim ABOUT integrity)"}
```

---

### 3.7 S7 — O1 `qualifies_or_extends` with `refines_truth_conditions=false` (topology-only)

**Stress purpose:** Exercises the qualifies-without-truth → topology-only branch. Zero Claim/EVIDENCES writes despite engaging an existing Claim counterpart. New topology (LINKS_TO + SUPPORTS) for a different object on same predicate.

```yaml
scenario_id: s7-buffett-amex-extends-without-refining
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-2020-buffett-apple-stake
      predicate_class_canonical: invests_in
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    - source_id: KDB/raw/2020-buffett-apple-stake.md
      entity_slug: warren-buffett
      role: subject

  claims:
    - claim_id: "warren-buffett__invests_in__global__v1"
      claim_family_id: "warren-buffett__invests_in__global"
      subject_slug: warren-buffett
      predicate_class_canonical: invests_in
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      object_slug: tech-industry
      provenance_type: analysis_emitted
      confidence: 0.80

  about_edges:
    - claim_id: "warren-buffett__invests_in__global__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2023-buffett-amex-investment
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in"
    predicate_class_canonical: invests_in
    predicate_scope_slugs: ["global"]   # SAME scope as existing Claim — not a refinement
    polarity: affirms
    counterpart_status: candidate_counterpart_found
    relation_kind: qualifies_or_extends
    refines_truth_conditions: false   # KEY: extends without refining → topology-only
    counterpart_claim_id: "warren-buffett__invests_in__global__v1"
    counterpart_links_to_ref:
      from_slug: warren-buffett
      to_slug: tech-industry
    doxastic_fingerprint:
      state_hash: "sha256:qualifies_no_truth..."
      classifier_input_scope:
        - "claim_family(warren-buffett__invests_in__global)"
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2023-buffett-amex-stake.md
        quoted_text: "Berkshire also continues to hold its American Express position."

expected_post_state:
  entities:
    add:
      - slug: american-express
        kind: organization
  links_to:
    add:
      - from_slug: warren-buffett
        to_slug: american-express
        run_id: <runtime-assigned>
        predicate_class_canonical: invests_in
        predicate_scope_slugs: ["global"]
        polarity: affirms
  supports:
    add:
      - source_id: KDB/raw/2023-buffett-amex-stake.md
        entity_slug: warren-buffett
        role: subject
  claims: unchanged       # NO Claim writes — topology-only path
  edges: unchanged        # no new Claim-Claim edges
  about_edges: unchanged
  alias_of_edges: unchanged
  evidences: unchanged    # no new EVIDENCES (no new Claim to attach to)

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-2, expected: pass, note: "qualifies-without-truth (topology-only — zero Claim writes)"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if a Claim were written for this cell"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation"}
  - {id: F-O1-5, expected: not_fire, note: "no unauthorized mutation — confirms topology-only is authorized for this disposition"}
```

---

### 3.8 S8 — O1 `supersedes` (mandatory upgrade + state transition + SUPERSEDES edge)

**Stress purpose:** Exercises the `supersedes` row — mandatory upgrade. Side effect: predecessor Claim transitions `active → superseded` per D-83/84-11 state machine. Claim-Claim `SUPERSEDES` edge written with temporal metadata.

```yaml
scenario_id: s8-buffett-apple-stake-supersedes-2023
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: apple-inc

  links_to:
    - from_slug: warren-buffett
      to_slug: apple-inc
      run_id: run-2020-buffett-apple-stake
      predicate_class_canonical: owns_stake_percentage
      predicate_scope_slugs: ["t=2020"]
      polarity: affirms

  supports:
    - source_id: KDB/raw/2020-buffett-apple-stake.md
      entity_slug: warren-buffett
      role: subject

  claims:
    - claim_id: "warren-buffett__owns_stake_percentage__t=2020__v1"
      claim_family_id: "warren-buffett__owns_stake_percentage__apple"
      subject_slug: warren-buffett
      predicate_class_canonical: owns_stake_percentage
      predicate_scope_slugs: ["t=2020"]
      version: 1
      state: active
      polarity: affirms
      object_slug: apple-inc
      object_qualifier: "5%"
      provenance_type: analysis_emitted
      confidence: 0.80

  about_edges:
    - claim_id: "warren-buffett__owns_stake_percentage__t=2020__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2023-buffett-apple-stake-update
    subject_slug: warren-buffett
    predicate_class_raw: "owns_stake_percentage"
    predicate_class_canonical: owns_stake_percentage
    predicate_scope_slugs: ["t=2023"]
    polarity: affirms
    counterpart_status: candidate_counterpart_found
    relation_kind: supersedes
    refines_truth_conditions: false
    counterpart_claim_id: "warren-buffett__owns_stake_percentage__t=2020__v1"
    counterpart_links_to_ref:
      from_slug: warren-buffett
      to_slug: apple-inc
    doxastic_fingerprint:
      state_hash: "sha256:supersedes..."
    object_slug: apple-inc
    object_qualifier: "8%"
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2023-buffett-apple-stake-update.md
        quoted_text: "Apple now represents 8% of the Berkshire portfolio."

expected_post_state:
  entities: unchanged
  links_to: unchanged
  supports:
    add:
      - source_id: KDB/raw/2023-buffett-apple-stake-update.md
        entity_slug: warren-buffett
        role: subject
  claims:
    update:
      # Predecessor transitions active → superseded per D-83/84-11
      - claim_id: "warren-buffett__owns_stake_percentage__t=2020__v1"
        state: superseded
        superseded_by: "warren-buffett__owns_stake_percentage__t=2023__v2"
    add:
      - claim_id: "warren-buffett__owns_stake_percentage__t=2023__v2"
        claim_family_id: "warren-buffett__owns_stake_percentage__apple"
        subject_slug: warren-buffett
        predicate_class_canonical: owns_stake_percentage
        predicate_scope_slugs: ["t=2023"]
        version: 2
        state: active
        polarity: affirms
        object_slug: apple-inc
        object_qualifier: "8%"
        provenance_type: analysis_emitted
        confidence: <placeholder-pending-OQ-26>
        supersedes: "warren-buffett__owns_stake_percentage__t=2020__v1"
        classified_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__owns_stake_percentage__t=2023__v2"
        to_claim_id: "warren-buffett__owns_stake_percentage__t=2020__v1"
        kind: SUPERSEDES
        temporal:
          superseded_at: "2026-06-01T00:00:00+09:00"
  about_edges:
    add:
      - claim_id: "warren-buffett__owns_stake_percentage__t=2023__v2"
        entity_slug: warren-buffett
        role: subject
  evidences:
    add:
      - source_id: KDB/raw/2023-buffett-apple-stake-update.md
        claim_id: "warren-buffett__owns_stake_percentage__t=2023__v2"
        provenance_type: analysis_emitted

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"
  state_transition:
    claim_id: "warren-buffett__owns_stake_percentage__t=2020__v1"
    from: active
    to: superseded
    via: supersedes_action

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-2, expected: pass, note: "supersedes (mandatory upgrade + predecessor state transition + SUPERSEDES edge)"}
  - {id: P-O1-5, expected: pass, note: "evidence cardinality"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if supersedes skipped Claim creation or skipped predecessor state transition"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (state machine + SUPERSEDES edge integrity)"}
```

---

### 3.9 S9 — O1 `orthogonal` (topology-only, no Claim engagement)

**Stress purpose:** Exercises the `orthogonal` row — candidate touches a subject with existing Claims but its predicate is unrelated. Topology-only writes; existing Claims untouched. Distinguishes from `no_counterpart` (S2) by the existence of subject-overlap without semantic engagement.

```yaml
scenario_id: s9-buffett-senate-meeting-orthogonal
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-2020-buffett-apple-stake
      predicate_class_canonical: invests_in
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    - source_id: KDB/raw/2020-buffett-apple-stake.md
      entity_slug: warren-buffett
      role: subject

  claims:
    # Existing contested-family Claim — unrelated to the candidate's predicate
    - claim_id: "warren-buffett__invests_in__global__v1"
      claim_family_id: "warren-buffett__invests_in__global"
      subject_slug: warren-buffett
      predicate_class_canonical: invests_in
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      object_slug: tech-industry
      provenance_type: analysis_emitted
      confidence: 0.80

  about_edges:
    - claim_id: "warren-buffett__invests_in__global__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2010-buffett-senate-meeting
    subject_slug: warren-buffett
    predicate_class_raw: "met_with"
    predicate_class_canonical: met_with   # entirely different predicate
    predicate_scope_slugs: ["global"]
    polarity: affirms
    counterpart_status: orthogonal
    relation_kind: null   # orthogonal → no relation_kind dispatch per D-83/84-2
    refines_truth_conditions: null
    counterpart_claim_id: null
    counterpart_links_to_ref: null
    doxastic_fingerprint:
      state_hash: "sha256:orthogonal..."
      classifier_input_scope:
        - "subject_mentions(warren-buffett)"
        - "predicate_class(met_with) — no overlap with existing predicates"
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2010-buffett-senate-testimony.md
        quoted_text: "Buffett testified before the Senate Banking Committee on financial regulation."

expected_post_state:
  entities:
    add:
      - slug: senate-banking-committee
        kind: organization
  links_to:
    add:
      - from_slug: warren-buffett
        to_slug: senate-banking-committee
        run_id: <runtime-assigned>
        predicate_class_canonical: met_with
        predicate_scope_slugs: ["global"]
        polarity: affirms
  supports:
    add:
      - source_id: KDB/raw/2010-buffett-senate-testimony.md
        entity_slug: warren-buffett
        role: subject
  claims: unchanged       # NO Claim writes — orthogonal path
  edges: unchanged
  about_edges: unchanged
  alias_of_edges: unchanged
  evidences: unchanged

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-2, expected: pass, note: "orthogonal (topology-only; existing Claims untouched)"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if a Claim were written for the orthogonal cell"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation"}
  - {id: F-O1-5, expected: not_fire, note: "no unauthorized mutation"}
```

---

### 3.10 S10 — O2 Tier-2 (SUPPORTS-overlap reconstruction; run-payload unavailable)

**Stress purpose:** Exercises Tier-2 provenance reconstruction per D-83/84-7 Part B — Tier-1 (run-payload) is unavailable; intersection of subject + object SUPPORTS gives candidate sources. OLD Claim's EVIDENCES carry `provenance_type=reconstructed_from_supports_overlap` with NULL `quoted_text` (per P-O2-3).

```yaml
scenario_id: s10-buffett-tech-upgrade-tier2
op_under_test: O2

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter   # run sidecar no longer available
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    # subject (warren-buffett) and object (tech-industry) share a SUPPORTS source — Tier-2 overlap candidate
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: tech-industry
      role: object
    # Non-overlapping SUPPORTS (only one entity each) — should NOT be selected by Tier-2 intersection
    - source_id: KDB/raw/1990s-buffett-bio.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/tech-industry-overview.md
      entity_slug: tech-industry
      role: object

  claims: []
  edges: []
  about_edges: []
  alias_of_edges: []

  # CRITICAL: run_payloads is empty — Tier-1 reconstruction will fail
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2020-buffett-apple-stake-tier2
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: invests_in_technology
    predicate_scope_slugs: ["global"]
    polarity: affirms
    counterpart_status: candidate_counterpart_found
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: null   # → O2 dispatch
    counterpart_links_to_ref:
      from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
    doxastic_fingerprint:
      state_hash: "sha256:tier2_dispatch..."
    confidence:
      bucket: high
      score: 0.80
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
      # OLD Claim — Tier-2 reconstructed from SUPPORTS overlap
      - claim_id: "warren-buffett__invests_in_technology__global__v1"
        claim_family_id: "warren-buffett__invests_in_technology__global"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in_technology
        predicate_scope_slugs: ["global"]
        version: 1
        state: active
        polarity: denies   # reconstructed counterpart asserts opposite stance (1995 avoid-tech)
        provenance_type: reconstructed_from_supports_overlap
        confidence: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
      # NEW Claim — analysis_emitted from current candidate
      - claim_id: "warren-buffett__invests_in_technology__global__v2"
        claim_family_id: "warren-buffett__invests_in_technology__global"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in_technology
        predicate_scope_slugs: ["global"]
        version: 2
        state: active
        polarity: affirms
        provenance_type: analysis_emitted
        confidence: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__invests_in_technology__global__v2"
        to_claim_id: "warren-buffett__invests_in_technology__global__v1"
        kind: CONTRADICTS
  about_edges:
    add:
      - claim_id: "warren-buffett__invests_in_technology__global__v1"
        entity_slug: warren-buffett
        role: subject
      - claim_id: "warren-buffett__invests_in_technology__global__v2"
        entity_slug: warren-buffett
        role: subject
  evidences:
    add:
      # OLD Claim EVIDENCES — Tier-2; the single intersected SUPPORTS source
      - source_id: KDB/raw/1995-buffett-letter.md
        claim_id: "warren-buffett__invests_in_technology__global__v1"
        quoted_text: null       # P-O2-3: NULL permitted for reconstructed_from_supports_overlap
        score: null
        provenance_type: reconstructed_from_supports_overlap
      # NEW Claim EVIDENCES — analysis_emitted, fully populated
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        claim_id: "warren-buffett__invests_in_technology__global__v2"
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        score: 0.80
        provenance_type: analysis_emitted

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"
  provenance_attempt_tier1: failed   # run-payload unavailable
  provenance_attempt_tier2: succeeded
  provenance_attempt_tier2_overlap_sources:
    - KDB/raw/1995-buffett-letter.md   # the intersection result

expected_invariants_hold: true
expected_op_to_invoke: O2
exercised_criteria:
  - {id: P-O2-1, expected: pass, note: "both Claims created"}
  - {id: P-O2-2, expected: pass, note: "OLD-Claim provenance_type=reconstructed_from_supports_overlap (Tier-2 path)"}
  - {id: P-O2-3, expected: pass, note: "NULL quoted_text / score permitted on Tier-2 EVIDENCES"}
  - {id: P-O2-4, expected: pass, note: "ABOUT edges on both Claims"}
  - {id: P-O2-5, expected: pass, note: "LINKS_TO unchanged (additive)"}
  - {id: P-O2-6, expected: pass, note: "idempotency"}
  - {id: F-O2-1, expected: not_fire, note: "would fail if LINKS_TO mutated"}
  - {id: F-O2-2, expected: not_fire, note: "would fail if Tier-3 reached when Tier-2 SUPPORTS-overlap was actually available"}
  - {id: F-O2-3, expected: not_fire, note: "would fail if OLD-Claim EVIDENCES were analysis_emitted"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation"}
```

---

### 3.11 S11 — O2 Tier-3 (synthesized marker; both Tier-1 and Tier-2 unavailable)

**Stress purpose:** Exercises the **positive** Tier-3 path per P-O2-7 — when no run-payload AND no SUPPORTS overlap exists, OLD Claim is created with **zero EVIDENCES edges** + synthesized-marker metadata in `promotion_audit`. F-O2-2 (premature Tier-3) and F-O2-4 (missing synthesized marker) are both expected to NOT fire.

```yaml
scenario_id: s11-buffett-tech-upgrade-tier3-synthesized
op_under_test: O2

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    # NO overlapping SUPPORTS — subject and object share no sources → Tier-2 fails
    - source_id: KDB/raw/1990s-buffett-bio.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/tech-industry-overview.md
      entity_slug: tech-industry
      role: object

  claims: []
  edges: []
  about_edges: []
  alias_of_edges: []

  # No run_payloads — Tier-1 fails as well
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2020-buffett-apple-stake-tier3
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: invests_in_technology
    predicate_scope_slugs: ["global"]
    polarity: affirms
    counterpart_status: candidate_counterpart_found
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: null
    counterpart_links_to_ref:
      from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
    doxastic_fingerprint:
      state_hash: "sha256:tier3_dispatch..."
    confidence:
      bucket: high
      score: 0.80
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
      # OLD Claim — Tier-3: zero EVIDENCES; provenance label reflects synthesized-marker case
      - claim_id: "warren-buffett__invests_in_technology__global__v1"
        claim_family_id: "warren-buffett__invests_in_technology__global"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in_technology
        predicate_scope_slugs: ["global"]
        version: 1
        state: active
        polarity: denies
        provenance_type: synthesized   # marker per D-83/84-7 Part B Tier-3
        confidence: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
      - claim_id: "warren-buffett__invests_in_technology__global__v2"
        claim_family_id: "warren-buffett__invests_in_technology__global"
        subject_slug: warren-buffett
        predicate_class_canonical: invests_in_technology
        predicate_scope_slugs: ["global"]
        version: 2
        state: active
        polarity: affirms
        provenance_type: analysis_emitted
        confidence: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__invests_in_technology__global__v2"
        to_claim_id: "warren-buffett__invests_in_technology__global__v1"
        kind: CONTRADICTS
  about_edges:
    add:
      - claim_id: "warren-buffett__invests_in_technology__global__v1"
        entity_slug: warren-buffett
        role: subject
      - claim_id: "warren-buffett__invests_in_technology__global__v2"
        entity_slug: warren-buffett
        role: subject
  evidences:
    add:
      # ONLY the NEW Claim has EVIDENCES — OLD Claim has zero per Tier-3 contract (P-O2-7)
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        claim_id: "warren-buffett__invests_in_technology__global__v2"
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        score: 0.80
        provenance_type: analysis_emitted

promotion_audit:
  disposition: auto_promote
  drift_signals: { fingerprint_drift: false, classification_drift: false }
  classified_at: "2026-06-01T00:00:00+09:00"
  provenance_attempt_tier1: failed       # run-payload unavailable
  provenance_attempt_tier2: failed       # no SUPPORTS overlap
  provenance_synthesized_marker: true    # P-O2-7: required Tier-3 metadata

expected_invariants_hold: true
expected_op_to_invoke: O2
exercised_criteria:
  - {id: P-O2-1, expected: pass, note: "both Claims created (OLD with zero EVIDENCES legitimately)"}
  - {id: P-O2-4, expected: pass, note: "ABOUT edges on both Claims"}
  - {id: P-O2-5, expected: pass, note: "LINKS_TO unchanged"}
  - {id: P-O2-6, expected: pass, note: "idempotency"}
  - {id: P-O2-7, expected: pass, note: "positive Tier-3: zero EVIDENCES + provenance_synthesized_marker=true"}
  - {id: F-O2-1, expected: not_fire, note: "LINKS_TO not mutated"}
  - {id: F-O2-2, expected: not_fire, note: "Tier-3 legitimately reached (Tier-1 + Tier-2 both unavailable in pre-state)"}
  - {id: F-O2-3, expected: not_fire, note: "no OLD-Claim EVIDENCES rows to mislabel"}
  - {id: F-O2-4, expected: not_fire, note: "synthesized-marker metadata is present per contract"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (zero-EVIDENCES OLD Claim is accepted per P-O2-7)"}
```

---

### 3.12 S12 — drift cell `(true, false)` — fingerprint drift, classification stable → `auto_promote_with_note`

**Stress purpose:** Exercises the D-83/84-8 Part D `(fingerprint_drift=true, classification_drift=false)` cell. Graph state changed in the candidate's fingerprint scope between analysis-time and promotion-time, but the change was orthogonal to the classification dispatch — disposition is `auto_promote_with_note`, graph mutates with drift note recorded.

```yaml
scenario_id: s12-drift-fingerprint-only-auto-promote-with-note
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      polarity: affirms

  # Promotion-time has an EXTRA SUPPORTS edge that didn't exist at analysis-time
  # → fingerprint hash drifts; classification (contradicts) is unaffected
  supports:
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/2018-buffett-interview.md   # NEW since analysis-time
      entity_slug: warren-buffett
      role: subject

  claims:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      claim_family_id: "warren-buffett__avoids_tech_investments__global"
      subject_slug: warren-buffett
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      provenance_type: analysis_emitted
      confidence: 0.80

  about_edges:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2020-buffett-apple-stake-drift-fp
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: invests_in_technology
    predicate_scope_slugs: ["global"]
    polarity: affirms
    modality: declarative
    counterpart_status: candidate_counterpart_found
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: "warren-buffett__avoids_tech_investments__global__v1"
    counterpart_links_to_ref: null
    # Analysis-time fingerprint snapshot — graph state at T1 (before the new SUPPORTS arrived)
    doxastic_fingerprint:
      state_hash: "sha256:fingerprint_at_analysis_time_T1"
      classifier_input_scope:
        - "claim(warren-buffett__avoids_tech_investments__global__v1).polarity"
        - "supports_cardinality_for_subject(warren-buffett)"
    # Analysis-time classification captured for drift comparison
    analysis_time_classification:
      counterpart_status: candidate_counterpart_found
      relation_kind: contradicts
      refines_truth_conditions: false
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  # auto_promote_with_note STILL mutates per D-83/84-8 Part D + P-O1-7
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
        predicate_class_canonical: invests_in_technology   # NEW Claim polarity flip
        predicate_scope_slugs: ["global"]
        version: 2
        state: active
        polarity: affirms
        provenance_type: analysis_emitted
        confidence: <placeholder-pending-OQ-26>
        classified_at: "2026-06-01T00:00:00+09:00"
  edges:
    add:
      - from_claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        to_claim_id: "warren-buffett__avoids_tech_investments__global__v1"
        kind: CONTRADICTS
  about_edges:
    add:
      - claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        entity_slug: warren-buffett
        role: subject
  evidences:
    add:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        claim_id: "warren-buffett__avoids_tech_investments__global__v2"
        provenance_type: analysis_emitted
        confidence: 0.80

promotion_audit:
  disposition: auto_promote_with_note
  drift_signals: { fingerprint_drift: true, classification_drift: false }
  drift_note: "fingerprint_drift due to new SUPPORTS edge (KDB/raw/2018-buffett-interview.md) — orthogonal to relation_kind dispatch; promoted with note"
  classified_at: "2026-06-01T00:00:00+09:00"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-2, expected: pass, note: "Claim-creating contradicts cell — mutation proceeds despite fingerprint drift"}
  - {id: P-O1-4, expected: pass, note: "drift signals: fingerprint_drift=true, classification_drift=false"}
  - {id: P-O1-7, expected: pass, note: "disposition auto_promote_with_note (mutates per P-O1-7)"}
  - {id: F-O1-2, expected: not_fire, note: "would fail if mutation skipped despite auto_promote_with_note disposition"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation"}
  - {id: F-O1-5, expected: not_fire, note: "auto_promote_with_note is an authorized mutation disposition"}
```

---

### 3.13 S13 — drift cell `(false, true)` — classification drift only → `investigate` (no mutation)

**Stress purpose:** Exercises the D-83/84-8 Part D `(fingerprint_drift=false, classification_drift=true)` cell. Same fingerprint should mean same classification; divergence signals classifier non-determinism, stale `classifier_version`, or coupling-as-invariant violation. Disposition `investigate` → **zero graph mutation** in default mode (per P-O1-7). F-O1-5 explicitly tests for unauthorized writes.

```yaml
scenario_id: s13-drift-classification-only-investigate
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      polarity: affirms

  supports:
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: warren-buffett
      role: subject

  claims:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      claim_family_id: "warren-buffett__avoids_tech_investments__global"
      subject_slug: warren-buffett
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      provenance_type: analysis_emitted
      confidence: 0.80

  about_edges:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2020-buffett-apple-stake-drift-cls
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: invests_in_technology
    predicate_scope_slugs: ["global"]
    polarity: affirms
    modality: declarative
    # PROMOTION-TIME re-classification will yield `contradicts`
    counterpart_status: candidate_counterpart_found
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: "warren-buffett__avoids_tech_investments__global__v1"
    counterpart_links_to_ref: null
    # Analysis-time fingerprint scope matches promotion-time → no drift
    doxastic_fingerprint:
      state_hash: "sha256:fingerprint_stable_across_T1_T2"
      classifier_input_scope:
        - "claim(warren-buffett__avoids_tech_investments__global__v1).polarity"
    # Analysis-time classification was DIFFERENT (e.g., qualifies_or_extends, refines=false)
    # but promotion-time re-classification yields contradicts → classification_drift=true
    analysis_time_classification:
      counterpart_status: candidate_counterpart_found
      relation_kind: qualifies_or_extends
      refines_truth_conditions: false
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  # investigate disposition → NO graph mutation per P-O1-7
  entities: unchanged
  links_to: unchanged
  supports: unchanged
  claims: unchanged
  edges: unchanged
  about_edges: unchanged
  alias_of_edges: unchanged
  evidences: unchanged

promotion_audit:
  disposition: investigate
  drift_signals: { fingerprint_drift: false, classification_drift: true }
  drift_note: "classification_drift without fingerprint_drift — suspect classifier non-determinism, stale classifier_version, or coupling-as-invariant violation; flagged for investigation"
  classified_at: "2026-06-01T00:00:00+09:00"
  investigation_record:
    analysis_time_classification: { counterpart_status: candidate_counterpart_found, relation_kind: qualifies_or_extends, refines_truth_conditions: false }
    promotion_time_classification: { counterpart_status: candidate_counterpart_found, relation_kind: contradicts, refines_truth_conditions: false }
    suspected_cause: classifier_non_determinism_or_coupling_violation

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-4, expected: pass, note: "drift signals: fingerprint_drift=false, classification_drift=true"}
  - {id: P-O1-7, expected: pass, note: "disposition investigate — no graph mutation per P-O1-7"}
  - {id: F-O1-5, expected: not_fire, note: "no unauthorized mutation — investigate disposition short-circuits before any Claim/EVIDENCES/LINKS_TO/SUPPORTS write"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (graph unchanged)"}
```

---

### 3.14 S14 — drift cell `(true, true)` — both drift → `human_review` (no mutation)

**Stress purpose:** Exercises the D-83/84-8 Part D `(fingerprint_drift=true, classification_drift=true)` cell. State change correlates with classification change — the new classification is based on more current state, but divergence is the signal worth human attention. Disposition `human_review` → **zero graph mutation** in default mode (per P-O1-7). F-O1-5 covers unauthorized-write detection.

```yaml
scenario_id: s14-drift-both-human-review
op_under_test: O1

eval_config:
  eval_clock: "2026-06-01T00:00:00+09:00"
  corroboration_threshold_n: 3
  confidence_decay_tau_days: 365
  default_read_confidence_threshold_t: 0.40
  confidence_map_version: confidence_map_v1

pre_state:
  entities:
    - slug: warren-buffett
    - slug: tech-industry

  links_to:
    - from_slug: warren-buffett
      to_slug: tech-industry
      run_id: run-1995-buffett-letter
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      polarity: affirms

  # Both the SUPPORTS edge (fingerprint scope) AND a new related Claim arrived since analysis-time
  supports:
    - source_id: KDB/raw/1995-buffett-letter.md
      entity_slug: warren-buffett
      role: subject
    - source_id: KDB/raw/2019-buffett-tech-pivot-context.md   # NEW since T1 — contributes to fingerprint drift
      entity_slug: warren-buffett
      role: subject

  claims:
    # Existing Claim
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      claim_family_id: "warren-buffett__avoids_tech_investments__global"
      subject_slug: warren-buffett
      predicate_class_canonical: avoids_tech_investments
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      provenance_type: analysis_emitted
      confidence: 0.80
    # NEW Claim arrived since analysis-time — affects classifier read surface AND outcome
    - claim_id: "warren-buffett__shifted_investment_thesis__global__v1"
      claim_family_id: "warren-buffett__shifted_investment_thesis__global"
      subject_slug: warren-buffett
      predicate_class_canonical: shifted_investment_thesis
      predicate_scope_slugs: ["global"]
      version: 1
      state: active
      polarity: affirms
      provenance_type: analysis_emitted
      confidence: 0.70

  about_edges:
    - claim_id: "warren-buffett__avoids_tech_investments__global__v1"
      entity_slug: warren-buffett
      role: subject
    - claim_id: "warren-buffett__shifted_investment_thesis__global__v1"
      entity_slug: warren-buffett
      role: subject

  edges: []
  alias_of_edges: []
  run_payloads: []

input:
  candidate:
    candidate_id: cand-2020-buffett-apple-stake-drift-both
    subject_slug: warren-buffett
    predicate_class_raw: "invests_in_technology"
    predicate_class_canonical: invests_in_technology
    predicate_scope_slugs: ["global"]
    polarity: affirms
    counterpart_status: candidate_counterpart_found
    relation_kind: contradicts
    refines_truth_conditions: false
    counterpart_claim_id: "warren-buffett__avoids_tech_investments__global__v1"
    counterpart_links_to_ref: null
    # Analysis-time fingerprint captured BEFORE the new SUPPORTS + new Claim arrived
    doxastic_fingerprint:
      state_hash: "sha256:fingerprint_at_T1_pre_drift"
      classifier_input_scope:
        - "claim(warren-buffett__avoids_tech_investments__global__v1).polarity"
        - "supports_cardinality_for_subject(warren-buffett)"
        - "related_claims_for_subject(warren-buffett)"
    # Analysis-time classification was different
    analysis_time_classification:
      counterpart_status: candidate_counterpart_found
      relation_kind: qualifies_or_extends
      refines_truth_conditions: true
    confidence:
      bucket: high
      score: 0.80
    evidence:
      - source_id: KDB/raw/2020-buffett-apple-stake.md
        quoted_text: "Berkshire's stake in Apple has grown to be one of its largest holdings."
        confidence:
          bucket: high
          score: 0.80

expected_post_state:
  # human_review disposition → NO graph mutation per P-O1-7
  entities: unchanged
  links_to: unchanged
  supports: unchanged
  claims: unchanged
  edges: unchanged
  about_edges: unchanged
  alias_of_edges: unchanged
  evidences: unchanged

promotion_audit:
  disposition: human_review
  drift_signals: { fingerprint_drift: true, classification_drift: true }
  drift_note: "both fingerprint_drift and classification_drift — state change correlates with classification change; flagged for human review"
  classified_at: "2026-06-01T00:00:00+09:00"
  human_review_record:
    analysis_time_classification: { counterpart_status: candidate_counterpart_found, relation_kind: qualifies_or_extends, refines_truth_conditions: true }
    promotion_time_classification: { counterpart_status: candidate_counterpart_found, relation_kind: contradicts, refines_truth_conditions: false }
    state_changes_in_fingerprint_scope:
      - "new SUPPORTS edge for warren-buffett"
      - "new Claim: shifted_investment_thesis"

expected_invariants_hold: true
expected_op_to_invoke: O1
exercised_criteria:
  - {id: P-O1-4, expected: pass, note: "drift signals: fingerprint_drift=true, classification_drift=true"}
  - {id: P-O1-7, expected: pass, note: "disposition human_review — no graph mutation per P-O1-7"}
  - {id: F-O1-5, expected: not_fire, note: "no unauthorized mutation under human_review disposition"}
  - {id: F-O1-4, expected: not_fire, note: "invariant preservation (graph unchanged)"}
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

**Progress (2026-05-23):** Batches 1–3 complete — 10 scenarios landed (S5–S14). Action-table-cell + upgrade-tier + drift-cell axes closed. Batch 4 remaining (5 cross-axis scenarios).

| Axis | Spike covers | Expansion adds | Status |
|---|---|---|---|
| Action-table cells (7) | `contradicts`, `no_counterpart` (S1, S2) | `reinforces` (S5), `qualifies-with-truth` (S6), `qualifies-without-truth` (S7), `supersedes` (S8), `orthogonal` (S9) | ✅ **Complete** |
| Upgrade tiers (3) | Tier 1 (S3) | Tier 2 (S10), Tier 3 (S11) | ✅ **Complete** |
| Drift cells (4) | `(false, false)` only — implicit in all spike + S5–S9 | `(true, false)` (S12), `(false, true)` (S13), `(true, true)` (S14) | ✅ **Complete** |
| State transitions (1 — `active → superseded`) | Implicit in S8 as side effect; dedicated scenario pending | 1 dedicated scenario (batch 4) | 🔄 Pending |
| Aliasing (1) | S4 (1) | Subject-canonicalized-between-runs variant (1 — batch 4) | 🔄 Pending |
| Retracted-counterpart (2) | Not covered | 2 (sibling-active and no-active-sibling — batch 4) | 🔄 Pending |
| Sequential-interaction (1) | Not covered | 1 dedicated scenario (batch 4) | 🔄 Pending |
| **Total expansion** | **4 spike + 5 batch 1** | **~10 remaining** = ~19 full coverage | |

Expansion ratification gate: §6 decisions ratified → all scenarios written → spot-check pass → #87.1 v1 ratified → unblocks #83/#84 implementation start.

---

## 8. Change log

- **2026-05-22** — v1 spike-phase draft. 4 scenarios (S1 O1 contradicts, S2 O1 no_counterpart, S3 O2 Tier-1 upgrade, S4 O3 aliased read). Template-stress observations + 6 OQs (OQ-S1..S6) + 10 decision gates (D-87.1-1..10) surfaced. Expansion to ~18 scenarios blocked on D-87.1-1..9 ratification.
- **2026-05-22** — §6 decisions D-87.1-1..10 **ratified**. D-87.1-5 ratified with vocabulary correction: `implied_by_links_to` is not a valid `counterpart_status` enum value per #83/#84 D-83/84-2; canonical enum is `no_counterpart` | `candidate_counterpart_found` | `orthogonal`. O2 dispatch is derived (not enum-named): `counterpart_status == candidate_counterpart_found` AND `counterpart_claim_id == null` AND `counterpart_links_to_ref != null`. S3 input field corrected accordingly. **OQ-S7 added** (should dispatch path be explicit or stay derived — current lean: stay derived). Expansion to 14 more scenarios now unblocked.
- **2026-05-23** — §3 renamed from "Spike scenarios" → "Probe scenarios" with origin note distinguishing spike (§§3.1–3.4) from expansion (§§3.5+). **Batch 1 expansion landed**: 5 action-table-cell scenarios — S5 reinforces (corroboration crosses N), S6 qualifies-with-truth (Claim-creating + QUALIFIES edge), S7 qualifies-without-truth (topology-only), S8 supersedes (mandatory upgrade + state transition + SUPERSEDES edge), S9 orthogonal (topology-only with subject-overlap). S1–S4 `exercised_criteria` retroactively patched to D-87.1-9 annotated form (`{id, expected: pass|not_fire, note}`). Action-table-cell axis now complete (7/7).
- **2026-05-23** — **Batch 2 expansion landed**: 2 upgrade-tier scenarios — S10 O2 Tier-2 (SUPPORTS-overlap reconstruction with NULL `quoted_text` per P-O2-3 + intersection narrowed to single shared source), S11 O2 Tier-3 (synthesized marker with zero EVIDENCES on OLD Claim + `provenance_synthesized_marker=true` in `promotion_audit` per P-O2-7). Upgrade-tier axis now complete (3/3). Tier-3 scenario exercises both F-O2-2 (premature-Tier-3 negative) and F-O2-4 (missing-marker negative) as expected_to_not_fire.
- **2026-05-23** — **Batch 3 expansion landed**: 3 drift-cell scenarios — S12 (true, false) auto_promote_with_note (mutation proceeds), S13 (false, true) investigate (no mutation — short-circuits before any write), S14 (true, true) human_review (no mutation). S13 and S14 carry `analysis_time_classification` + `investigation_record`/`human_review_record` blocks in `promotion_audit` to make the drift comparison auditable. F-O1-5 (unauthorized-mutation guard) fires as expected_to_not_fire across all three. Drift-cell axis now complete (4/4).
