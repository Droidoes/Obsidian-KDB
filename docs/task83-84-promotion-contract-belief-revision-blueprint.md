# Task #83 + #84 — Hypothesis Promotion Contract + Belief Revision (Joint Blueprint)

**Status:** **v2** — v1 holistic review folded 2026-05-22 (D-83/84-1 through -8 + amendments + new D-83/84-9 through -12)
**Started:** 2026-05-22 (v1)
**v2 dated:** 2026-05-22 (same session, post-v1-review synthesis)
**Lineage:** Round 6 §9.4.2 mandate; (a+) decision via Joseph ratification 2026-05-22
**Parallel-design rationale:** `docs/what-is-the-ontology-for.md` §9.3.8 + [[feedback_concrete_first_extract_later]]
**Reviewer panel** (active post-2026-05-22, see `docs/external-review-panel.md`): Codex + Deepseek + Qwen. Antigravity (Gemini) deselected per one-strike rule.
**v1 review files:** `docs/task83-84-blueprint-v1-review-{codex,deepseek,qwen}.md`
**Anchors:**
- `docs/what-is-the-ontology-for.md` §9.4 (Round 6 closeout)
- `docs/TASKS.md` #83, #84
- Memory `project_round6_learn_operationalized`

---

## 1. Joint scope

This is **one blueprint covering both #83 and #84** because they share a single interlock surface — *what crosses the gate*. Splitting into two blueprints would specify that surface twice and invite drift.

**Task #83 — Hypothesis Promotion Contract.** The cross-cutting boundary operator that mediates every Analysis → Learn transition. Owns: input candidate shape, mutation typing, confidence/provenance requirements, conflict checks, auto-promote vs review thresholds, predeclared eval criteria.

**Task #84 — Belief Revision.** The first Learn slot (Round 6 §9.4.1 slot #1). Operates on belief state. Folds in forgetting + temporal validity + decay + contraction as sub-operations.

**Out of scope of this blueprint:** Tasks #85 (Identity Refinement) and #86 (Abstraction). Sketched informally here only insofar as needed to keep the #83 contract surface general enough to absorb them when their blueprints land.

---

## 2. Concrete scenario this blueprint specifies against

Per advisor input (design questions emerge from gaps in concrete traces, not from upfront enumeration):

> *I have `raw/articles/buffett-1995-letter.md` in the corpus. The compiler extracted: `Buffett —LINKS_TO→ circle-of-competence`, supported by that page. I now harvest `raw/articles/buffett-tech-pivot-2020.md` where Buffett discusses Apple investments as a deliberate departure from his historical anti-tech stance.*

**Today (schema v2.1):** New source compiles. New edges added (`Buffett —LINKS_TO→ Apple-Inc`, etc.) with `SUPPORTS` from the new page. Existing `circle-of-competence` edge untouched. Both claims coexist; no record of contradiction. **No belief revision.**

**Round 6 (a+) target behavior:**

1. **Analysis op** (link prediction / structural-hole detection / LLM contradiction detection — exact op TBD) emits a candidate: *"claim X (Buffett avoids tech, anchored 1995) is contradicted by claim Y (Buffett invests in tech, anchored 2020)."*
2. Candidate carries: confidence, provenance (both source paths + quoted text), supporting path (entity-level walk), mutation type.
3. Candidate hits **#83 Promotion Contract** gate. Auto-promote vs surface-for-review.
4. If promoted: **#84 Belief Revision** executes the mutation against current graph state.

This blueprint specifies steps 2–4. Step 1 (which Analysis op surfaces the candidate, when) is downstream of #83 and out of scope here.

---

## 3. Decision log

### D-83/84-1 — Schema placement: hybrid model (LINKS_TO default + Claim node on contention) — 2026-05-22

**Decision:** Adopt the **hybrid model** for representing belief state.

- `LINKS_TO` edges remain the default representation for **stable, uncontested, single-source claims** (the common case).
- A new `Claim` node type is instantiated **only when** a claim becomes contested, versioned, or has multi-source provenance worth explicit tracking.
- The Promotion Contract (#83) owns the "promote-to-Claim" trigger that performs the upgrade.

**Rejected alternatives:**

- **(i) Edge-attribute model** — extend `LINKS_TO` with `belief_weight` / `version` / `contradicts[]` / etc. Rejected because edges carrying contradiction arrays and temporal versioning *approximate* a separate object type without naming it; querying contested-claim patterns becomes ad-hoc; decay semantics on edge weight need their own contract anyway. Risk: gradually reinvents the Claim node model badly.
- **(ii) Full Claim-node model** — every belief gets reified as a Claim, all `LINKS_TO` edges replaced or co-derived. Rejected because it over-models the common case (most claims aren't contested at compile time); doubles the retrieval surface even for uncontested state; significant migration cost on existing schema v2.1 data.

**Rationale for (iii):**

- **YAGNI for the common case** — uncontested claims stay cheap on the LINKS_TO surface. No new node-type tax until contention demands it.
- **Architecturally clean for the cases that warrant it** — when contention arises, the Claim layer provides typed, queryable, versioned belief state.
- **Matches [[feedback_concrete_first_extract_later]]** — abstraction (Claim layer) is built when concrete demand (contention) arrives, not on speculation.
- **Matches [[feedback_no_imaginary_risk]]** — single-user single-machine workload; pay for complexity only when contention demands it.

**Cost being accepted:** one extra mechanism (the "upgrade" operation that takes an existing `LINKS_TO` edge and promotes the involved claim to a `Claim` node) that must be specified, tested, and documented. Two read paths at query time (`LINKS_TO` for stable beliefs, `Claim` for contested) — query layer must handle both deterministically.

**Amended by D-83/84-7 (2026-05-22):** the framing above (LINKS_TO = "uncontested" / Claim = "contested") oversimplifies. Post-#83/#84, `LINKS_TO` is the **corpus topology layer** (connection-presence); Claim space is the **belief layer**. Both coexist on contested pairs: `LINKS_TO` is untouched by the upgrade operation; Claim nodes are added on top. See D-83/84-7 Part A + Part D for the full semantic contract.

**Open questions filed against this decision:**

| OQ | Question | Owner | Status |
|---|---|---|---|
| **OQ-1** | What exactly triggers `upgrade-to-Claim`? Contradiction-only? Also corroboration-count thresholds? Also explicit user/system request? | #83 | **Resolved by D-83/84-2** |
| **OQ-2** | Post-upgrade, do the original `LINKS_TO` edges (a) stay as navigation shortcuts with consensus weight, (b) get removed entirely so retrieval routes through Claim space, or (c) get auto-derived from Claim state (LINKS_TO always reflects latest uncontested consensus; Claim space carries history)? Default lean: (c). | #84 | Open |
| **OQ-3** | Schema specifics — what attributes does the `Claim` node carry beyond `statement` / `confidence` / `version` / `created_at` / `last_revised_at`? | #84 | Open |
| **OQ-4** | How are existing `LINKS_TO` edges' belief weights and provenance derived at upgrade time? `LINKS_TO` today has minimal attributes (no weight, single SUPPORTS edge per source); the upgrade implies a richer provenance reconstruction. | #84 | Open |
| **OQ-5** | Does the Claim model support claims **about claims** (meta-belief — "I'm uncertain about X")? Or only claims **about entities**? Affects whether `Claim—ABOUT→Entity` is the only outbound edge, or if `Claim—ABOUT→Claim` is also valid. | #84 | Open |

### D-83/84-2 — Relation typology + upgrade-to-Claim triggers — 2026-05-22

**Decision:** Adopt a **two-step relation classification** for candidate claims relative to existing graph state, with a default-action table that determines `upgrade-to-Claim` triggers deterministically. Synthesis across Codex's 2-step decomposition + truth-condition discriminator, ratified by Joseph 2026-05-22.

**Step 1 — Counterpart status:**

- `no_counterpart` — no existing edge or Claim that the candidate engages
- `candidate_counterpart_found` — existing edge or Claim that the candidate engages
- `orthogonal` — candidate touches entities present in the graph but does not engage existing claims about them

**Step 2 — Relation kind** (only if `candidate_counterpart_found`):

- `reinforces` — same predicate, same polarity, additional evidence
- `contradicts` — same predicate, opposing polarity (claim X vs. not-X; narrative reframing also qualifies)
- `qualifies_or_extends` — adds nuance or condition to the prior claim
- `supersedes` — temporally replaces prior claim

**Step 3 — For `qualifies_or_extends` only, sub-flag:**

- `refines_truth_conditions: bool` — `true` iff the candidate alters the prior claim's truth conditions (e.g., *"Buffett invests in tech **iff** within circle-of-competence"*). `false` if it merely adds adjacent detail (e.g., *"Buffett also discusses insurance float in the 1995 letter"*).

**Default action table:**

| Counterpart status | Relation | Action |
|---|---|---|
| `no_counterpart` | — | Write `LINKS_TO` + `SUPPORTS`. No Claim. |
| `orthogonal` | — | Same as `no_counterpart` for the topology touched. No belief-revision action. |
| `candidate_counterpart_found` | `reinforces` | Add/aggregate support. **Upgrade to Claim only if** corroboration count crosses threshold N **or** explicit watch-flag fires. Default N=3 (configurable knob; see OQ-6). |
| `candidate_counterpart_found` | `contradicts` | **Upgrade to Claim.** Mandatory. |
| `candidate_counterpart_found` | `qualifies_or_extends` | **Upgrade to Claim iff** `refines_truth_conditions=true`. Else write topology only. |
| `candidate_counterpart_found` | `supersedes` | **Upgrade to Claim** with temporal/version metadata. Mandatory. Preserve prior version. |

**Rationale:**

- The two-step decomposition replaces a flat-6 enumeration (the original chat-side framing) because the flat list mixed three orthogonal axes — novelty (`asserts-new`), logical relation (`reinforces` / `contradicts` / `extends`), temporal relation (`supersedes`), disposition (`orthogonal`) — on one dimension. Real cases can be both `extends` AND `contradicts`; flat enumeration forces false-choice. Codex's 2-step decomposition (counterpart-status × relation-kind) makes the axes explicit.
- The `qualifies_or_extends` sub-flag is Codex's truth-condition discriminator — sharper than my original "depth-of-nuance threshold (open)" deferral. Adjacent-detail extensions don't warrant Claim-node overhead; truth-condition refinements do.
- Antigravity's Epistemic-Class grouping (Epistemically Independent / Directly Contentious / Epistemically Incremental) was considered. Adopted Codex's structural decomposition over Antigravity's categorical grouping because structural is composable (axes can be cross-tabulated) while categorical is not.

**Resolves:** OQ-1 (upgrade trigger).

**Opens:**

- **OQ-6** — Corroboration threshold N for `reinforces`. Default 3; needs empirical tuning on real corpus. Belongs in predeclared eval criteria (Task #75 pattern).
- **OQ-7** — *Resolved by D-83/84-4.* Same-predicate is canonical-form matching: `(subject_slug, predicate_class_canonical, predicate_scope_slugs as set)` triple equality, post predicate-class canonicalization (D-83/84-5).

### D-83/84-3 — Classifier role: (C) Mid + shared module + Doxastic Fingerprint as audit artifact — 2026-05-22

**Decision:** Adopt **(C) hints + confirmation** classifier role with five concrete commitments. Synthesis: Codex's shared-classifier + drift-bool framing + Antigravity's Doxastic-Fingerprint pattern — but fingerprint scoped as audit-only in v1, not as fast-path skip. Ratified by Joseph 2026-05-22.

1. **Shared classifier module** at `graphdb_kdb.core.belief_classifier` (exact path TBD per code conventions). Stateless function. Single implementation, called from both Analysis ops and the Promotion Contract. Mandatory single-source-of-truth — without it, Analysis-time and promotion-time classifiers would inevitably drift apart and the (C) Mid pattern would degrade silently.

2. **Promotion-time classification is authoritative.** Analysis-time output is a hint only. The contract never blindly accepts Analysis classification — the live graph state at promotion-time is what determines the action.

3. **Always re-classify at promotion-time in v1.** Predictable, simple, low overhead at our scale (single-user, infrequent compile). Predictability > latency optimization at v1.

4. **Doxastic Fingerprint as audit artifact, NOT as fast-path skip in v1.** Each candidate records: (a) the hash of the target's state at analysis-time, (b) the Analysis-time classification, (c) the promotion-time classification, (d) `classification_drift: bool` with reason if (b) and (c) differ. The fingerprint exists for audit + future eval — not to skip re-classification.

5. **Eval surface:** classifier-drift rate becomes a measurable signal (predeclared eval per Task #75 pattern). If drift stays low across a measurement window, **fingerprint-as-fast-path-skip becomes a v2 candidate** (Antigravity's full O(1) proposal). If drift is common, v2 retains the fingerprint as audit material but does not skip.

**Rationale:**

- (C) Mid preserves Analysis-op classifier work (which the op already does to surface the candidate) while keeping promotion-time honest against current state. (A) Lean candidate would waste Analysis-time graph-walking; (B) Rich candidate would freeze stale view as authoritative.
- The shared-classifier-module pattern is the load-bearing piece — both Codex and the (C) Mid logic require it. Without it, the pattern degrades.
- Always-re-classify in v1 follows [[feedback_no_imaginary_risk]]: predictable simplicity wins at our workload. The fast-path-skip optimization is real engineering value but not load-bearing yet.
- Fingerprint-as-audit captures Antigravity's structural insight (Analysis-time state matters for understanding why a classification was what it was) without committing to fingerprint-as-skip-mechanism prematurely. Audit data then *informs* the v2 decision empirically.

**Resolves:** classifier role question (from chat-side framing 2026-05-22).

**Opens:**

- **OQ-8** — Exact hash content for the Doxastic Fingerprint. Should hash include: target entity's full attribute set? Outgoing edges? Inbound edges? All Claims about the entity? Active version of any related Claim? Trade-off: too narrow → drift not detected; too broad → fingerprint constantly changes and audit signal is noise.
- **OQ-9** — Predeclared eval criteria for classifier drift. Mirroring Task #75 pattern. What thresholds count as "low drift" (fast-path-skip eligible) vs "high drift" (re-classification load-bearing)?

### D-83/84-4 — Predicate representation: structured form with polarity ⊥ modality split — 2026-05-22

**Decision:** Adopt **Option 2** (canonical predicate-class + structured form). Synthesis incorporates Codex's three refinements: polarity ⊥ modality split; `predicate_scope_slugs` separate from `object_slugs`; structured-form determinism over LLM-as-judge-at-classification. Ratified by Joseph 2026-05-22.

**`proposed_claim` data shape** (field within the candidate envelope — see §4):

| Field | Type | Purpose |
|---|---|---|
| `subject_slug` | canonical entity slug | Subject of the claim |
| `predicate_class_canonical` | string (post-canonicalization) | Same-predicate matching key |
| `predicate_class_raw` | string (LLM-emitted, pre-canonicalization) | Source-traceable form before normalization |
| `predicate_scope_slugs` | list of canonical entity slugs | Abstract scope for same-predicate matching (e.g., `[tech-investing]`). **Distinct from `object_slugs`** — see rationale. |
| `object_slugs` | list of canonical entity slugs | Concrete entities mentioned in this candidate (e.g., `[apple-inc]`) |
| `polarity` | enum `affirms \| rejects \| neutral` | Stance on the predicate |
| `modality` | enum `unconditional \| conditional` | Whether the claim is qualified |
| `condition_text` | optional string | Qualifying condition text if `modality=conditional` |
| `assertion_text` | LLM-emitted free-text | Natural-language form for audit + human review |

**Matching rules:**

- **Same-predicate:** `(subject_slug, predicate_class_canonical, predicate_scope_slugs as set)` triple equality.
- **Same-polarity:** `polarity` enum equality.
- **`contradicts`:** same-predicate + opposing polarity (`affirms` vs `rejects`).
- **`reinforces`:** same-predicate + same polarity.
- **Factual claims** (e.g., `predicate_class_canonical: founded-company`) use `polarity=affirms` (affirmative form) or `polarity=rejects` ("did NOT" claims). No special "factual" polarity needed — same-predicate matching still applies.

**Buffett scenario under this schema:**

```yaml
# Candidate emitted from the 2020 article
proposed_claim:
  subject_slug: buffett
  predicate_class_canonical: tech-investing-stance
  predicate_class_raw: "tech investment posture"
  predicate_scope_slugs: [tech-investing]
  object_slugs: [apple-inc]
  polarity: affirms
  modality: unconditional    # would be `conditional` if framed "iff circle-of-competence"
  condition_text: null
  assertion_text: "Buffett invests in Apple as a deliberate departure from his historical anti-tech stance."
```

Existing 1995 letter (promoted to Claim form):

```yaml
predicate_class_canonical: tech-investing-stance
predicate_scope_slugs: [tech-investing]
polarity: rejects
# subject_slug + predicate_class_canonical + predicate_scope_slugs MATCH → same predicate
# polarity OPPOSING → contradicts
```

Classifier verdict: `contradicts` → upgrade to Claim (mandatory per D-83/84-2). Deterministic.

**Rationale:**

- **Structured form is load-bearing.** D-83/84-2's action table cannot be deterministic if "same predicate" requires an LLM call per classification; D-83/84-3's Doxastic Fingerprint needs a structured key to hash. Option 1 (LLM-as-judge at classification time) was rejected for both reasons + API cost.
- **Polarity ⊥ modality split** (Codex's refinement): "conditional" is not a polarity. A conditional claim still has a polarity. Splitting axes makes both deterministic and orthogonally composable.
- **`predicate_scope_slugs` separate from `object_slugs`** (Codex's refinement): exact `object_slugs` equality is too brittle. The 2020 article mentions `apple-inc` concretely; the 1995 letter discussed `tech-investing` in general. Without the split, matching by literal `object_slugs` would miss the contradiction.
- **Factual claims collapse cleanly** under polarity=affirms/rejects + factual predicate class — no special "factual" polarity needed (rejects Joseph's earlier 4-value polarity draft).

**Rejected:**

- **Option 1** (LLM-as-judge at classification time) — kills determinism, breaks fingerprinting, costs API per classification.
- **Original 4-value polarity enum** (`affirms | rejects | conditional | factual`) — conflated polarity with modality (conditional ⊥ polarity) and with predicate-type (factual ⊥ stance). Codex's split is sharper.
- **Antigravity's Python dataclass concretization** — premature implementation-form lock-in; blueprint specifies field shape only.

**Resolves:** OQ-7 (predicate determination), OQ-11 (proposed_claim structured form).

**Opens:** none new at this layer. Canonicalization-infrastructure concern raised by Option 2 is addressed by D-83/84-5.

### D-83/84-5 — Predicate-class canonicalization: shared infrastructure pattern, separate registry — 2026-05-22

**Decision:** The `predicate_class_canonicalizer` reuses **Task #74's canonicalization infrastructure pattern + shared normalization utilities** (string normalization, embedding-similarity dedup, LLM-as-judge cache, provenance tracking, alias-ledger pattern). The **alias ledger/registry is separate** from the entity canonicalization ledger — entity identity and predicate identity are different domains. Implementation form (polymorphic base class vs shared utility module vs composition) is left to the implementation work. Ratified by Joseph 2026-05-22.

**Rationale:**

- D-83/84-4's structured form **requires** predicate-class canonicalization — same-predicate matching is canonical-form equality, not raw-string equality. Without canonicalization, the predicate taxonomy sprawls and matching becomes unreliable.
- Task #74's pattern is **proven discipline** — reusing it eliminates risk of greenfield design errors. The "shared utilities, separate registry" framing (Codex) is the right level of code reuse without entangling unrelated identity domains.
- **Implementation-form lock-in is premature** at blueprint time. Polymorphic base class (Antigravity), shared utility modules, mixins, composition, duck-typed convention — all viable; choice depends on Python conventions and refactoring constraints we don't have on the table here.

**Opens:**

- **OQ-13** — Exact implementation form for the shared canonicalization utilities (polymorphic base class? shared library module? mixin? composition?). Deferred to the canonicalizer-module implementation work but flagged so it gets explicit attention rather than drift. Whatever form is chosen must satisfy: (a) Task #74 entity canonicalization and the new predicate canonicalization share the normalization-utility code path; (b) their alias registries remain physically and logically separate.

### D-83/84-6 — Claim node schema design — 2026-05-22

**Decision:** Synthesis incorporating Codex's three corrections (claim_family_id / claim_id split; explicit Claim-Claim relation edges with decay separated from retraction; schema-correct `Source—EVIDENCES→Claim` anchor verified against `graphdb_kdb/schema.py`) + Antigravity's two substantive contributions (delimiter guard on slugs; edge-attribute enrichment on EVIDENCES). Ratified by Joseph 2026-05-22.

**F1 — `claim_id` format (family/instance split):**

- `claim_family_id` = `<subject_slug>__<predicate_class_canonical>__<scope-slug-set>` — the *what is this claim about* identity
- `claim_id` = `<claim_family_id>__v<N>` — the *specific version of this claim* identity. **Polarity is NOT part of `claim_id`** (amended per Codex v1 review Finding 1) — polarity remains a Claim node attribute that consumers query directly. Embedding polarity in `claim_id` was a v1 draft mistake that would have caused collisions for two `qualifies_or_extends` candidates sharing `(family, polarity)` but differing in `condition_text`.
- `scope-slug-set` is deterministically serialized: sort + join with `+`; empty set uses `<none>` sentinel
- **Version allocation:** `N` is monotonic **per `claim_family_id`** — all versioned Claims within a family share the version counter regardless of polarity, modality, or condition_text. Distinct claims within the same family are distinguished by Claim node attributes (polarity, modality, condition_text), not by `claim_id`. A contradictory claim (opposing polarity) in the same family gets the next sequential version (v2, v3, …) even though it semantically opposes prior versions; `CONTRADICTS` edges connect them as belief-level facts (D-83/84-6 F2).
- **Delimiter guard:** `__` is the field separator; subjects / predicate_class / scope-slugs must be kebab-case with no `__` substring (enforced at canonicalization time per D-83/84-5).
- **Parseability validation** (amended per Qwen v1 review F5): the Promotion Contract validates `claim_id` parseability before write — rejects candidates with malformed `claim_id`. Belt-and-suspenders check; canonicalization should prevent it, but the write path must not trust upstream.
- Example single-scope: `buffett__tech-investing-stance__tech-investing__v1`
- Example multi-scope: `buffett__tech-investing-stance__consumer-electronics+tech-investing__v1`

**F2 — State machine + Claim-to-Claim relation edges:**

States: `active | superseded | retracted`.

| Transition | Trigger |
|---|---|
| `active → superseded` | A newer claim is committed with a `Claim—SUPERSEDES→Claim` edge pointing at this claim |
| `active → retracted` | **Explicit retraction operation only** — operator marks claim withdrawn/invalid. **Not triggered by decay.** |
| `superseded → active` | Revival: only if the superseding claim is itself retracted; walk `SUPERSEDES` chain backward to find nearest non-retracted ancestor |
| `retracted → *` | Terminal — no path out. If the same claim needs to return, new instance with new version. |

**Decay ≠ retraction.** Decay reduces `confidence` over time (per a decay function operating on the field); state remains `active`. Retraction marks the claim invalid. Decayed claims are still part of the belief state, weighted lower; retracted claims are filtered from default retrieval.

**Decay threshold behavior** (amended per Qwen v1 review F3): when `confidence` decays below threshold T (configurable, analogous to OQ-6's corroboration threshold), the Claim remains `active` but is **excluded from default retrieval**. Audit/revision queries can still surface decayed-but-active Claims explicitly. Threshold T is OQ-level — see OQ-26 (confidence aggregation rule) which shares this surface.

**Retraction-edge propagation: see D-83/84-11.** This blueprint's v1 review (all three reviewers — Codex, Deepseek, Qwen) flagged that the state machine was silent on what happens to outgoing/incoming Claim-Claim edges when a Claim transitions to `retracted`. D-83/84-11 (filed below) specifies the default contract; OQ-21 captures the cascade/audit-filter variants.

New edge types (v1):

- `Claim—SUPERSEDES→Claim` — newer → older
- `Claim—CONTRADICTS→Claim` — new claim → existing claim being contradicted (semantically symmetric; queries traverse both directions)
- `Claim—QUALIFIES→Claim` — qualifier → qualified (for `qualifies_or_extends` with `refines_truth_conditions=true` per D-83/84-2)

**F3 — Provenance: `Source—EVIDENCES→Claim` with edge attributes:**

Anchor at `Source` (verified in `graphdb_kdb/schema.py` line 10 — existing pattern is `Source—SUPPORTS→Entity`; `Page` is not a node table in v2.1). Earlier "Page—..." references in chat-side framing were schema-drift mistakes; this decision is the corrected version.

Edge attributes on `EVIDENCES`:

| Attribute | Purpose |
|---|---|
| `quoted_text` | Source-text excerpt supporting the claim |
| `score` | Analysis op's confidence in *this specific evidence* (distinct from Claim's aggregated confidence). Renamed from `confidence_score` per D-83/84-8 Part C. |
| `run_id` | Which compile run created this evidence link |
| `created_at` | Timestamp |

Putting evidence metadata on the edge — not the Claim node — lets multiple sources support the same Claim with different quoted_texts and confidences, without a list-field on Claim.

**F4 — Meta-claims (`Claim—ABOUT→Claim`) deferred to v2.**

In v1: `Claim—ABOUT→Entity` only. Meta-claims (`Claim—ABOUT→Claim`) added in v2 if concrete demand surfaces.

**Claim domain membership** (amended per Codex v1 review OQ + Deepseek v1 review Finding 2): the Claim node has **no `domain` field**. Domain membership is reachable via the traversal `Claim—ABOUT→Entity—BELONGS_TO→Domain` (using the existing `BELONGS_TO` edge from Task #76). This is intentional — domain is an Entity property; Claims about an Entity share its domain by **association, not by duplication**. Belief-sensitive domain queries traverse two hops; this prevents `Claim.domain` denormalization drift if the entity's domain changes. Future Task #86 may need Claim-level domain tagging; defer until then.

**Resulting Kuzu schema (v1 — to ship as a future schema version, exact bump TBD in implementation):**

```cypher
CREATE NODE TABLE Claim (
  claim_id STRING PRIMARY KEY,
  claim_family_id STRING,
  subject_slug STRING,
  predicate_class_canonical STRING,
  predicate_class_raw STRING,
  predicate_scope_slugs STRING[],
  object_slugs STRING[],
  polarity STRING,
  modality STRING,
  condition_text STRING,
  assertion_text STRING,
  confidence DOUBLE,
  state STRING,
  version INT64,
  created_at TIMESTAMP,
  last_revised_at TIMESTAMP
);

CREATE REL TABLE EVIDENCES (
  FROM Source TO Claim,
  quoted_text STRING,
  score DOUBLE,                                -- renamed from confidence_score per D-83/84-8 Part C naming alignment
  provenance_type STRING,                    -- D-83/84-7: analysis_emitted | reconstructed_from_run_payload | reconstructed_from_supports_overlap
  run_id STRING,
  created_at TIMESTAMP
);

CREATE REL TABLE ABOUT (
  FROM Claim TO Entity,
  run_id STRING,
  created_at TIMESTAMP
);

CREATE REL TABLE SUPERSEDES (
  FROM Claim TO Claim,
  run_id STRING,
  created_at TIMESTAMP
);

CREATE REL TABLE CONTRADICTS (
  FROM Claim TO Claim,
  contradiction_kind STRING,
  run_id STRING,
  created_at TIMESTAMP
);

CREATE REL TABLE QUALIFIES (
  FROM Claim TO Claim,
  run_id STRING,
  created_at TIMESTAMP
);
```

**OQ-12 resolution (implicit):** the original `provenance.supporting_path` field on the candidate envelope is no longer needed. Persistent provenance lives on `Source—EVIDENCES→Claim` (quoted_text + score + run_id + created_at). The Analysis-op's graph-walk that surfaced the candidate is a transient artifact — operational info, not durable graph state. The candidate envelope's `supporting_path` field is dropped.

**Resolves:** OQ-3 (Claim attribute set), OQ-5 (meta-claims), OQ-12 (supporting_path).

**Opens:**

- **OQ-14** — How to aggregate multiple `EVIDENCES.score` values into the Claim's single `confidence` field (max, mean, Bayesian fusion, log-odds sum, etc.). **Promoted from implementation-deferred to structural per Codex/Qwen v1 review consensus — see OQ-26 below**; this OQ-14 placeholder kept for cross-reference, with resolution path being OQ-26.

### D-83/84-7 — Upgrade mechanism: additive on Claim layer; LINKS_TO untouched; three-tier provenance — 2026-05-22

**Decision:** Synthesis incorporating Codex's two tightenings (semantic-contract rewrite on D-83/84-1; α → α+ three-tier provenance hierarchy with explicit naming) on top of the (a)+(α) draft. Ratified by Joseph 2026-05-22. **Gemini was not consulted for this round** per the one-strike rule established 2026-05-22 after the hard-cap experiment partial failure (see `docs/gemini-review-hard-cap-prompt.md` + [[feedback_gemini_review_only_guardrail]]).

#### Part A — OQ-2 resolution: upgrade is additive on Claim layer; LINKS_TO untouched

- The Promotion Contract creates Claim nodes + Claim-Claim edges (`SUPERSEDES` / `CONTRADICTS` / `QUALIFIES`) + `EVIDENCES` edges.
- **The upgrade does not delete or derive `LINKS_TO`.** The upgrade operation is additive only.
- Normal compile ingestion (Stage 9/10 `graph_sync`) can still drop/recreate `LINKS_TO` via the existing current-state replacement path. That is not the upgrade's concern.
- **Semantic contract (post-#83/#84):**
  - `LINKS_TO` = corpus topology layer (which entities are associated in the corpus)
  - Claim space = belief layer (polarity, version, provenance, contradiction)
  - **Belief-sensitive reads must consult Claim space at tuple granularity** (amended per Codex v1 review Finding 6 + Qwen v1 review F1): for a queried `(subject_slug, predicate_class_canonical, predicate_scope_slugs)` tuple, if a `claim_family_id` exists in Claim space, read belief from Claim space; otherwise read from `LINKS_TO`. **Subject-presence is not sufficient** to trigger Claim-space consultation — only the specific tuple's family. This prevents forcing Claim-space reads on uncontested edges of a subject that has contested claims for *other* predicates.
  - Topology-only reads (`graph_context_loader`, V0 ops, PageRank, communities, structural-holes) consume `LINKS_TO` unchanged.

#### Part B — OQ-4 resolution: three-tier provenance reconstruction (α+)

When upgrading an existing belief into a Claim, populate `EVIDENCES` via this fallback chain:

- **Tier 1 (preferred): Run-payload candidate reconstruction** (renamed per Codex v1 review Finding 4). Use `LINKS_TO.run_id` to locate the run sidecar / `compile_result.json` that emitted the edge; extract the source page(s) + structured output. **Precision disclaimer:** this provides source attribution but **not** quote-level evidence — the run payload identifies *which page* emitted the link, not the specific *predicate-level assertion* now being reconstructed as a Claim. `provenance_type=reconstructed_from_run_payload` is weaker than `analysis_emitted` even when source IDs are recovered cleanly. `quoted_text` may remain NULL.
- **Tier 2 (fallback): SUPPORTS-overlap.** Walk `Source—SUPPORTS→Entity` for both subject and scope/object entities; intersection yields candidate sources. Honestly weaker — co-mention ≠ predicate-evidencing.
- **Tier 3 (escape hatch): synthesized marker.** If neither Tier 1 nor Tier 2 yields a source, create the OLD Claim with no `EVIDENCES` edges; record attempted-and-failed reconstruction in operational metadata.

#### Part C — `EVIDENCES.provenance_type` attribute (new)

| Value | Source | Required attributes |
|---|---|---|
| `analysis_emitted` | Analysis-op surfaced the candidate | `quoted_text` + `score` REQUIRED (unless candidate rejected or sent to human review) |
| `reconstructed_from_run_payload` | Tier 1 reconstruction | `quoted_text` + `score` MAY be NULL |
| `reconstructed_from_supports_overlap` | Tier 2 reconstruction | `quoted_text` + `score` MAY be NULL — weakest variant |

Schema update applied to D-83/84-6's `EVIDENCES` definition (provenance_type column added in-line above).

#### Part D — D-83/84-1 amendment (semantic-contract rewrite)

The original wording — *"LINKS_TO edges remain the default representation for stable, uncontested, single-source claims"* — is **superseded post-D-83/84-7** by:

> *"`LINKS_TO` is the corpus topology layer (connection-presence), not belief state. The Claim layer carries belief state. Before #83/#84 deployment, `LINKS_TO` topology and implicit belief coincided; after #83/#84 ships, they diverge — a contested entity pair has its `LINKS_TO` edge unchanged (topology) AND new Claim nodes (belief layer). Reading `LINKS_TO` as belief truth post-#83/#84 is a contract violation."*

Original D-83/84-1 entry preserved as-written for lineage; amendment note inline in D-83/84-1's body referencing this decision.

**Resolves:** OQ-2 (post-upgrade LINKS_TO behavior), OQ-4 (provenance reconstruction at upgrade).

**Opens:**

- **OQ-15** — Run-payload (Tier 1) eligibility constraints. Ties to D39 replayability and Task #69 `compile_count` audit findings (some early runs have ineligible sidecars). Implementation-level question.
- **OQ-16** — Tier-1 reconstruction timing: proactive (on every upgrade) vs. lazy (on demand from belief-sensitive queries). Performance vs. eagerness trade-off.
- **OQ-17** — Tier-2 (SUPPORTS-overlap) precision: `SUPPORTS` is per-Entity; `predicate_scope_slugs` may not always correspond directly to entities in `SUPPORTS`. Needs verification at implementation.

### D-83/84-8 — Candidate envelope details: targeted fingerprint + bucketed confidence with system-mapped score — 2026-05-22

**Decision:** Synthesis across three reviewers (Codex + Deepseek + Qwen — the post-Gemini panel; see `docs/external-review-panel.md`). All three picked (d)+(d). Codex contributed deterministic LINKS_TO keys + confidence auditability metadata + hash-scope/algorithm tags. Deepseek contributed the coupling-as-invariant contract, the explicit attribute spec for `canonical_form_hash`, and the LLM-emits-string-system-normalizes pattern. Qwen contributed the null-counterpart-collision flag + aggregation-distortion concern (deferred to OQ-14/OQ-18). Ratified by Joseph 2026-05-22.

#### Part A — Doxastic Fingerprint structure (resolves OQ-8)

Targeted fingerprint hashing **only the subject + counterpart** that the classifier actually consults. Audit artifact, not fast-path-skip (per D-83/84-3 #3, always re-classify at promotion-time in v1).

```yaml
doxastic_fingerprint:
  hash_scope: targeted-v1                # versioned scope/shape; future expansions bump this
  hash_algorithm: sha256                 # matches project's ledger_snapshot_sha256 pattern
  classifier_version: <version_string>   # classifier code+config snapshot identifier
                                         # (lightweight: a version-string, not a hash;
                                         # disambiguates same-fingerprint candidates with
                                         # different classifier rule/prompt configurations)

  subject:
    slug: <canonical_entity_slug>        # canonical slug post-#74
    state_hash: <sha256-hash>            # hashes ONLY {title, page_type, canonical_id}
                                         # procedural fields (created_at, updated_at,
                                         # last_run_id, first_run_id) EXCLUDED to prevent
                                         # false drift on re-compile

  counterpart:                           # ALWAYS an object; kind discriminates (amended per Qwen v1 review F4)
    kind: no_counterpart | orthogonal    # for no-comparison-target cases
    context_key:                         # disambiguates same-subject candidates with no counterpart
      predicate_class_canonical: <slug>  # avoids null-counterpart fingerprint collision
      scope_slugs: [<sorted_canonical_slugs>]
  # OR:
  counterpart:
    kind: LINKS_TO
    key:                                 # LINKS_TO has no stable edge ID today
      from_slug: <subject_slug>          # (verified `graphdb_kdb/schema.py:81`);
      to_slug: <target_slug>             # deterministic key required
    state_hash: <sha256-hash>            # NOTE: degenerate today — LINKS_TO carries only
                                         # `run_id`/`created_at` (both procedural).
                                         # state_hash effectively reduces to an
                                         # existence check. Acknowledged as expected.
  # OR:
  counterpart:
    kind: Claim
    id: <stable_claim_id>                # per D-83/84-6 F1 (claim_family_id + version)
    state_hash: <sha256-hash>            # hashes classifier-read fields ONLY:
                                         # {polarity, state, version, modality}
                                         # created_at, last_revised_at EXCLUDED
```

#### Part B — Coupling-as-invariant (Deepseek's structural contract)

> **The fingerprint hash content is defined as the union of all graph data the shared classifier reads during classification.** When the classifier's input surface expands (e.g., consults corroboration counts via OQ-6, domain membership via Task #76, or new Claim attributes), the fingerprint content **must** expand accordingly via a `hash_scope` version bump (e.g., `targeted-v1` → `targeted-v2`). **Fingerprint ≠ classifier-input-surface is a contract violation.**

This is a named architectural invariant, not a one-time spec. Future PRs that touch the classifier's input surface must update the fingerprint scope in the same PR.

#### Part C — Confidence representation (resolves OQ-10)

**LLM emission contract** (extends existing `kdb_compiler/schemas/compiled_source_response.schema.json` `#/$defs/confidence` pattern):

```json
{ "confidence": "high" }
// single string field, enum: "low" | "medium" | "high"
```

**Candidate envelope (post-parse, validated by upcoming JSON-Schema per OQ-19):**

```yaml
confidence:
  bucket: low | medium | high            # LLM-emitted, normalized to enum at parse
  score: 0.3 | 0.5 | 0.8                 # system-derived from bucket via configurable map
  score_source: config_map               # always 'config_map' in v1
  map_version: confidence_map_v1         # identifies which map was applied;
                                         # old decisions remain explainable after
                                         # config changes
```

**Naming alignment** (amended per Qwen v1 review F7): the EVIDENCES edge's `confidence_score` column is **renamed to `score`** to match the candidate's `confidence.score` field. Schema update applied to D-83/84-6's `EVIDENCES` definition. The mapping at promotion time is now `candidate.evidence[i].confidence.score → EVIDENCES.score` — consistent both directions.

**Config layer (off-candidate, versioned):**

```yaml
confidence_map_v1:
  low_to_float: 0.3
  medium_to_float: 0.5
  high_to_float: 0.8
# Default values; no empirical basis yet. Future eval surface per Task #75 pattern — see OQ-20.
```

#### Part D — Promotion-time audit fields (Codex's clarification)

These fields are added by the Promotion Contract at promotion-time — **NOT** emitted by the Analysis op:

```yaml
promotion_audit:
  fingerprint_drift: true | false        # subject.state_hash or counterpart.state_hash differs
  classification_drift: true | false     # promotion-time classification differs from analysis-time
  drift_explanation: <string>            # human-readable diff if either is true
```

The two are distinct signals: fingerprint can drift without classification changing (an irrelevant graph mutation in the subject's procedural fields, though our excluded-fields spec in Part A reduces this); classification can drift without fingerprint changing (caught by always-re-classify per D-83/84-3 #3 — e.g., a newly-relevant Claim that didn't exist at analysis-time). Recording both makes the audit explainable.

**Drift action matrix** (amended per Qwen v1 review F2): the Promotion Contract acts on the 4-cell combination of `fingerprint_drift` × `classification_drift` per the following defaults. Promotion-time classification is always authoritative (per D-83/84-3 #3) — the matrix governs *auto-promote vs human-review*, not which classification to apply.

| `fingerprint_drift` | `classification_drift` | Default action |
|---|---|---|
| `false` | `false` | **Auto-promote.** Both Analysis-time and promotion-time agree; expected case. |
| `true` | `false` | **Auto-promote with drift note.** Graph state changed but classification unaffected; drift was orthogonal to this candidate's classification surface. |
| `false` | `true` | **Investigate before promotion.** Same fingerprint should mean same input — different classification suggests either (a) classifier non-determinism, (b) `classifier_version` stale, or (c) **coupling-as-invariant violation** (fingerprint scope doesn't cover all classifier inputs). Flag for review. |
| `true` | `true` | **Human review.** Drift caused (or correlated with) the classification change. Exercise caution — the new classification is based on more current state, but the divergence is the signal worth a human look. |

Defaults are configurable knobs — see OQ-27. Audit data accumulates per-promotion, enabling empirical calibration over time.

**Resolves:** OQ-8 (Doxastic Fingerprint hash content), OQ-10 (confidence representation).

**Opens:**

- **OQ-18** — Aggregation distortion (Qwen's catch): when OQ-14 (confidence aggregation rule) lands, must handle bucketed/mapped aggregation edge cases — `low + high → mean(0.3, 0.8) = 0.55` rounds back to medium, losing the polarization signal. Flag `spread`/`variance` field, or `mode(bucket) + mean(score)` as a possible signal pair. **OQ-14 concern, not D-83/84-8.**
- **OQ-19** — Candidate envelope JSON-Schema (Deepseek's follow-up): create a JSON-Schema validating analysis-op emissions. Mirrors `compile_result.schema.json` pattern. Implementation-level follow-up.
- **OQ-20** — Confidence map empirical calibration: defaults `{0.3, 0.5, 0.8}` have no empirical basis. Belongs in Task #75 predeclared eval criteria territory (or its #83/#84 analog).
- **OQ-25** (filed v1 review per Deepseek F5) — Coupling-as-invariant enforcement mechanism. The "fingerprint = classifier-input-surface" contract (D-83/84-8 Part B) is currently manually-enforced — depends on a human PR author remembering to bump `hash_scope` when modifying the classifier's read surface. Options: (a) manual review checklist, (b) introspection test that walks the classifier read paths and verifies fingerprint coverage, (c) lint rule on the classifier module. Implementation-form question; not blueprint-level.
- **OQ-27** (filed v1 review per Part D matrix) — Default action thresholds for the 4-cell drift matrix are configurable; specific knob values + the per-cell behavior under heterogeneous confidence levels are empirical-tuning territory analogous to OQ-6/OQ-9 (predeclared eval criteria for #83/#84).

### D-83/84-9 — Claim identity under canonicalization: ABOUT-is-authoritative + denormalized lookup keys — 2026-05-22

**Decision:** Amends D-83/84-6 F1 and the D-83/84-7 Part D semantic contract. Per Codex v1 review Finding 2 + Deepseek v1 review Finding 3 — 2-reviewer convergence on a structural gap. Ratified by Joseph 2026-05-22.

**Authority binding:** `Claim—ABOUT→Entity` is the **authoritative subject binding**. The Claim's identity, for the purpose of "who is this claim about," is determined by the Entity node the ABOUT edge points at, **NOT** by the `subject_slug` field stored on the Claim.

**Denormalized lookup keys:** `Claim.subject_slug` and the `subject_slug` component of `claim_family_id` are **denormalized lookup keys** — derived from the authoritative ABOUT-target at claim-creation time. They are NOT the source of truth; they are cached identifiers used for fast lookup and human-readable IDs.

**Rewrite behavior under Task #74 entity canonicalization** (when aliases merge, e.g., `buffett` → `warren-buffett`):

- **Authoritative binding is unchanged.** `Claim—ABOUT→Entity` continues to point at the (now-canonical) Entity. The relation doesn't need rewriting — canonicalization updates the Entity node's `canonical_id`; the ABOUT edge still hits the right node by node identity.
- **Denormalized keys** (`Claim.subject_slug`, `claim_family_id`, `claim_id`) are **stale until rewritten**. Rewrite happens at two points:
  - **Rebuild path:** `graphdb-kdb rebuild` regenerates `claim_family_id` + `claim_id` from current canonical state. Authoritative.
  - **Incremental path:** the Promotion Contract performs **lazy rewrite** on Claims it touches during normal operation. When a Claim is read for matching, contradiction-check, or update, its `subject_slug` is reconciled to the canonical Entity via `ABOUT` traversal. Stale `claim_family_id` keys are accepted as input (for lookup) but corrected on write. Full incremental sweep is OQ-22's territory.
- **Alias-forwarding table is NOT introduced in v1.** Aliased lookups use the existing `ALIAS_OF` traversal pattern:
  ```cypher
  MATCH (c:Claim)-[:ABOUT]->(e:Entity)
  WHERE e.canonical_id = $slug OR exists((:Entity {slug: $slug})-[:ALIAS_OF]->(e))
  ```
  This is the v1 query pattern for "claims about X under any alias."

**Implication for OQ-22 (rebuild contract):** the rebuild path's role expands — rebuild must (a) replay compilations to restore LINKS_TO + SUPPORTS, (b) re-run Promotion Contract to restore Claims + Claim-Claim edges + EVIDENCES, **(c) regenerate all denormalized Claim keys from canonical state.** This is a load-bearing constraint on the OQ-22 resolution path.

**Resolves:** Codex v1 review Finding 2, Deepseek v1 review Finding 3.

**Opens:**

- **OQ-22** (filed v1 review per Deepseek F4) — Rebuild contract for Promotion-Contract-created data. `graphdb-kdb rebuild` currently replays `compile_result.json` payloads through the ingestor to reconstruct LINKS_TO + SUPPORTS. But Claim nodes, Claim-Claim edges, and EVIDENCES edges are **post-compilation artifacts** created by the Promotion Contract — they are NOT represented in `compile_result.json`. Resolution options: (a) store promotion decisions in the run payload as `promoted_candidates` so rebuild replays them, (b) re-run the Promotion Contract during rebuild after all compilations are replayed (default lean per D-83/84-9 above), (c) separate sidecar indexed by run_id. Affects snapshot contract too. Architectural question.

### D-83/84-10 — Promotion idempotency contract — 2026-05-22

**Decision:** Per Codex v1 review Finding 5 + Deepseek v1 review OQ-23/24 batch concerns. Ratified by Joseph 2026-05-22.

The Promotion Contract is a state-changing boundary. To support safe retry-after-partial-failure and avoid duplicate state from re-emission, every write the contract performs has an explicit uniqueness constraint.

**Uniqueness constraints:**

| Entity | Unique by | Behavior on collision |
|---|---|---|
| `Claim` node | `claim_id` (primary key) | Upsert — re-promoting the same candidate is a no-op |
| `Source—EVIDENCES→Claim` edge | `(source_id, claim_id, quoted_text_hash, provenance_type)` | Upsert — same source emitting the same evidence twice is a no-op; different quotes from the same source are separate evidences |
| `Claim—CONTRADICTS→Claim` edge | `(from_claim_id, to_claim_id)` | Upsert |
| `Claim—SUPERSEDES→Claim` edge | `(from_claim_id, to_claim_id)` | Upsert |
| `Claim—QUALIFIES→Claim` edge | `(from_claim_id, to_claim_id)` | Upsert |
| `Claim—ABOUT→Entity` edge | `(from_claim_id, to_entity_slug)` | Upsert |

`quoted_text_hash` is the SHA-256 of the normalized `quoted_text` string. Inclusion in the EVIDENCES uniqueness key lets the same source page evidence the same Claim with multiple distinct quotes (different paragraphs supporting different facets) while preventing exact-duplicate writes.

**Retry-after-partial-failure semantics:** the Promotion Contract is **safe to retry** at any point. If a partial write occurred (Claim created, EVIDENCES not yet written), retry will:

1. Find the existing Claim by `claim_id` (no-op on upsert).
2. Insert the missing EVIDENCES edges (no-op on already-present ones).
3. Complete the remaining Claim-Claim edges (no-op on already-present ones).

**Write ordering** (ensures partial state is queryable):

1. Create `Claim` nodes.
2. Create `Source—EVIDENCES→Claim` edges.
3. Create `Claim—ABOUT→Entity` edges.
4. Create `Claim—Claim` edges (`CONTRADICTS`, `SUPERSEDES`, `QUALIFIES`).
5. Update state attributes on existing Claims (e.g., `active → superseded` when a `SUPERSEDES` relation is established).

**Batch semantics** (resolves the immediate part of Deepseek v1 review OQ-23): the Promotion Contract processes candidates **sequentially** in v1. Each candidate runs through the full classify-promote pipeline before the next candidate begins. The promotion-time classification of candidate N sees the state after candidate N-1's promotion. Batch-parallel or batch-order-independence semantics are deferred — see OQ-23 (filed below).

**Resolves:** Codex v1 review Finding 5 (idempotency contract).
**Partially resolves:** Deepseek v1 review OQ-23 (sequential is the v1 default; parallel deferred).

**Opens:**

- **OQ-23** (filed v1 review per Deepseek) — Batch parallel / order-independence semantics. v1 is sequential per above. Future variants: parallel-with-deferred-classification (all candidates classified against pre-batch state, then committed) vs. pipeline-batched-with-conflict-detection. Implementation-level performance question.
- **OQ-28** (filed v1 review per Deepseek OQ-24) — Multi-candidate deduplication within a single Analysis-op emission. Can one Analysis op emit multiple candidates engaging the same counterpart? If so, is there a pre-gate dedup step? Or does each independently cross with the second seeing the first's result? Affects what "idempotency" means for batched analysis output.

### D-83/84-11 — Retraction edge-cleanup contract — 2026-05-22

**Decision:** Per 3-reviewer convergence (Codex v1 review OQ on retracted Claims as contradiction targets, Deepseek v1 review Finding 1, Qwen v1 review F6). Ratified by Joseph 2026-05-22.

When a Claim transitions to `state=retracted`:

**Default contract:**

- **Outgoing edges preserved.** The retracted Claim's `CONTRADICTS` / `SUPERSEDES` / `QUALIFIES` edges remain in the graph. They are **historical facts** — the Claim asserted this contradiction/supersession/qualification at one point, and that fact remains audit-valuable.
- **Incoming edges preserved.** Edges from other Claims pointing at the retracted Claim are preserved. Other Claims' state is **NOT** automatically changed by the target's retraction. Example: if Claim A `CONTRADICTS` Claim C and C is retracted, Claim A remains `active`. A's assertion (the contradiction) hasn't changed — only the target has been withdrawn.
- **No cascade.** Retracting Claim C does **NOT** auto-retract / auto-supersede / auto-revive any other Claim. Cascade effects are application-level decisions, not state-machine defaults.
- **Default-retrieval filter.** Retracted Claims are filtered out of default Claim-space retrieval (consistent with D-83/84-6 F2 retracted-filter rule). Audit / revision / contradiction-traversal queries can include retracted Claims explicitly via a query flag.

**SUPERSEDES revival cascade refinement** (per Deepseek v1 review Finding 1 sub-point + Qwen v1 review F6): the revival query (D-83/84-6 F2 `superseded → active` transition) walks `SUPERSEDES` chain backward to find the nearest non-retracted ancestor. **Coherence-check refinement:** the revived predecessor is checked for incoming `CONTRADICTS` edges from currently-`active` Claims. If any exist, revival is **gated for human review** rather than automatic. Prevents reviving a Claim whose belief is already contested by other live Claims.

**Resolves:** Deepseek v1 review Finding 1, Qwen v1 review F6, Codex v1 review OQ on retracted-as-contradiction-target.

**Opens:**

- **OQ-21** (filed v1 review) — Retraction cascade variants. Default is "no cascade." Specific cascade behaviors are opt-in operators that may be added in v2: (a) retracting a `QUALIFIES` source flags the qualifier for re-evaluation; (b) retracting a `SUPERSEDES`-source triggers auto-revival of the superseded predecessor (with coherence check); (c) batch retraction of a contradiction pair (both sides) when their `CONTRADICTS` evidence is itself retracted. None default in v1.

### D-83/84-12 — Confidence aggregation rule for Claim.confidence — 2026-05-22

**Decision:** Promotes OQ-14 + OQ-18 from "implementation-deferred" to structural per Codex v1 review OQ + Qwen v1 review OQ. Ratified by Joseph 2026-05-22.

**Why structural now:** the Claim node has a `confidence DOUBLE` field. The aggregation function that produces this from multiple `EVIDENCES.score` values **defines the field's semantics** at the contract level. Without specifying the function, the field is implementation-defined and can't be reasoned about by readers.

**v1 aggregation function:** **bounded mean of scores, weighted by source recency.**

```
confidence = Σ(evidence_i.score * w_i) / Σ(w_i)
  where w_i = decay(now() - evidence_i.created_at, tau)
        decay(t, tau) = exp(-t / tau)
```

- Bounded mean (vs unbounded sum) keeps `confidence ∈ [0, 1]` — matches `score`'s domain.
- Recency-weighted (vs uniform) so older evidence loses weight over time — implements decay-as-claim-property per D-83/84-6 F2 without modifying individual EVIDENCES rows.
- `tau` is a configurable knob (default: ~365 days; tuning is OQ-29).

**Aggregate spread/variance** (per Qwen v1 review F2 + OQ-18): an additional field `confidence_spread DOUBLE` is added to the Claim node, computed as the **standard deviation** of `evidence_i.score` (unweighted). Captures polarization signal — `low + high = mean 0.55` rounds back to medium, but spread=0.35 flags polarization. `confidence_spread` is informational, not used in the auto-promote action table.

**Schema update (applies to D-83/84-6):**

```cypher
-- Claim node table gains:
confidence_spread DOUBLE   -- stdev of EVIDENCES.score values; informational
```

**Resolves:** OQ-14 (confidence aggregation rule), OQ-18 (aggregation distortion / polarization signal).

**Opens:**

- **OQ-26** (filed v1 review, replaces OQ-14 placeholder) — Aggregation function tuning. The bounded-mean-with-recency-decay default is an architectural choice; the `tau` parameter and decay-function shape are empirical-tuning territory. Belongs in Task #75 predeclared eval analog for #83/#84.
- **OQ-29** — `tau` default value calibration. ~365 days is a guess; needs empirical work on the actual corpus.

---

## 4. Candidate envelope — fully specified (post-v1 review restructure)

Per Codex v1 review Finding 3, the candidate envelope's `provenance.*` parallel fields are restructured into an **`evidence[]` array of objects**, mirroring the cardinality of `Source—EVIDENCES→Claim` edges. Each evidence object carries its own `source_id`, `quoted_text`, and `confidence` — eliminating the ambiguity of multiple sources sharing parallel arrays of source_paths / quoted_texts / scores.

**Full envelope:**

```yaml
candidate:
  proposed_claim:                      # D-83/84-4 — structured predicate form
    subject_slug: <canonical>
    predicate_class_canonical: <slug>
    predicate_class_raw: <LLM-emitted>
    predicate_scope_slugs: [<sorted canonical slugs>]
    object_slugs: [<canonical slugs>]
    polarity: affirms | rejects | neutral
    modality: unconditional | conditional
    condition_text: <optional string>
    assertion_text: <LLM-emitted free-text>

  evidence:                            # D-83/84-8 + Codex v1 review F3 restructure
    - source_id: <KDB/raw/... source-page path>
      quoted_text: <source-text excerpt>
      confidence:                      # D-83/84-8
        bucket: low | medium | high
        score: 0.3 | 0.5 | 0.8         # system-derived from bucket
        score_source: config_map
        map_version: confidence_map_v1
    # ...one entry per source supporting the candidate;
    # each maps 1:1 to a Source—EVIDENCES→Claim edge on promotion

  analysis_classification:             # D-83/84-3 + D-83/84-2
    counterpart_status: no_counterpart | candidate_counterpart_found | orthogonal
    relation_kind: reinforces | contradicts | qualifies_or_extends | supersedes | null
    refines_truth_conditions: bool      # only when relation_kind=qualifies_or_extends

  counterpart_ref:                     # this blueprint — what counterpart was engaged
    kind: LINKS_TO | Claim | no_counterpart | orthogonal
    # for LINKS_TO:        { from_slug, to_slug }  (per D-83/84-8 Part A)
    # for Claim:           claim_id                (per D-83/84-6 F1 + D-83/84-9)
    # for no_counterpart / orthogonal: context_key (per D-83/84-8 Part A)

  doxastic_fingerprint:                # D-83/84-3 + D-83/84-8 (coupling-as-invariant)
    hash_scope: targeted-v1
    hash_algorithm: sha256
    classifier_version: <version-string>
    subject:
      slug: <canonical>
      state_hash: <sha256-hash>
    counterpart:                       # always an object; kind discriminates per D-83/84-8 Part A
      kind: LINKS_TO | Claim | no_counterpart | orthogonal
      # additional fields per kind (see D-83/84-8 Part A)
```

**At promotion-time** the contract:

1. Re-runs the shared classifier (D-83/84-3 #3) against current graph state, produces `promotion_classification`.
2. Recomputes fingerprint against current state; sets `fingerprint_drift = (analysis-time hash ≠ promotion-time hash)`.
3. Sets `classification_drift = (analysis-time classification ≠ promotion-time classification)`.
4. Applies the 4-cell action matrix (D-83/84-8 Part D) — auto-promote vs human-review.
5. If auto-promote: executes the D-83/84-2 action against current state, with idempotency constraints from D-83/84-10. Each `evidence[]` entry materializes as a `Source—EVIDENCES→Claim` edge.
6. Records `promotion_audit: {fingerprint_drift, classification_drift, drift_explanation}` for downstream observability.

**Evidence → EVIDENCES mapping** (one-to-one on promotion):

| Candidate field | EVIDENCES edge attribute |
|---|---|
| `evidence[i].source_id` | `(Source.source_id)` — the FROM-side node identity |
| `evidence[i].quoted_text` | `EVIDENCES.quoted_text` |
| `evidence[i].confidence.score` | `EVIDENCES.score` |
| `evidence[i].confidence.map_version` | preserved on edge or in run journal for audit |
| (constant) `'analysis_emitted'` | `EVIDENCES.provenance_type` |

**Reconstructed evidence** (Tier 1/2 of D-83/84-7 Part B) is added by the *upgrade* operation, not by the Analysis op — those EVIDENCES rows have `provenance_type` set to `reconstructed_from_run_payload` or `reconstructed_from_supports_overlap`, and `quoted_text`/`score` may be NULL.

---

## 5. Blueprint v2 status — v1 review folded; ready for predeclared-eval task + implementation

The v1 review (2026-05-22, Codex + Deepseek + Qwen — first round under the post-Gemini panel) surfaced 12 substantive findings convergent across 2–3 reviewers. All folded into this v2 blueprint:

| v1 review finding | Severity | Resolution |
|---|---|---|
| Claim retraction edge-cleanup (3-reviewer) | Structural | D-83/84-11 + OQ-21 |
| Canonicalization vs Claim identity (2-reviewer) | Structural | D-83/84-9 + OQ-22 |
| Tuple-granularity read-path (2-reviewer) | Structural | D-83/84-7 Part A amendment |
| Idempotency / batch / dedup (2-reviewer) | Structural | D-83/84-10 + OQ-23 + OQ-28 |
| Claim domain via traversal (2-reviewer) | Doc gap | D-83/84-6 amendment (after F4) |
| Confidence aggregation rule (2-reviewer) | Promoted to structural | D-83/84-12 + OQ-26 + OQ-29 |
| Claim version allocation under qualifiers | Structural | D-83/84-6 F1 amendment |
| Candidate envelope as evidence[] objects | Restructure | §4 fully rewritten |
| Tier-1 reconstruction overclaims precision | Cosmetic+ | D-83/84-7 Part B rename + disclaimer |
| Rebuild contract for Claims | Architectural Q | OQ-22 filed (inside D-83/84-9) |
| Coupling-as-invariant enforcement | Process Q | OQ-25 filed (inside D-83/84-8) |
| Fingerprint × classification drift matrix | Specificity | D-83/84-8 Part D amendment |
| Decay threshold behavior | Semantic gap | D-83/84-6 F2 amendment |
| `no_counterpart` fingerprint collision | Specificity | D-83/84-8 Part A `context_key` |
| `claim_id` parseability validation | Defense | D-83/84-6 F1 amendment |
| Naming collision (score vs confidence_score) | Polish | D-83/84-8 Part C alignment (EVIDENCES.score) |

**v2 structural decisions** (now 12, up from 8):

| Layer | Decisions | Status |
|---|---|---|
| Schema placement | D-83/84-1 (+ D-83/84-7 amendment) | ✅ |
| Relation typology + triggers | D-83/84-2 | ✅ |
| Classifier role + Doxastic Fingerprint pattern | D-83/84-3 | ✅ |
| Predicate representation | D-83/84-4 | ✅ |
| Predicate-class canonicalization | D-83/84-5 | ✅ |
| Claim node schema (+ amendments) | D-83/84-6 + v1 amendments | ✅ |
| Upgrade mechanism (+ amendments) | D-83/84-7 + v1 amendments | ✅ |
| Candidate envelope (+ amendments) | D-83/84-8 + v1 amendments | ✅ |
| **Claim identity under canonicalization** (NEW) | D-83/84-9 | ✅ |
| **Promotion idempotency contract** (NEW) | D-83/84-10 | ✅ |
| **Retraction edge-cleanup contract** (NEW) | D-83/84-11 | ✅ |
| **Confidence aggregation rule** (NEW) | D-83/84-12 | ✅ |

**Remaining OQs:** all either implementation-level (OQ-13 / OQ-15 / OQ-16 / OQ-17 / OQ-19) or predeclared-eval territory analogous to Task #75 (OQ-6 / OQ-9 / OQ-20 / OQ-26 / OQ-27 / OQ-29) or architectural-question-tracking (OQ-21 / OQ-22 / OQ-25 / OQ-28). None block implementation start.

**Recommended next steps** (post-v2):

1. **File the predeclared eval criteria task** for #83/#84 (analogous to Task #75 for step-3 ops). OQ-6, OQ-9, OQ-20, OQ-26, OQ-27, OQ-29 live there.
2. **Begin parallel implementation** on Task #83 (Promotion Contract) and Task #84 (Belief Revision) per the Round 6 §9.4.4 parallel-design sequencing.
3. Once #83 + #84 land, **unblock Tasks #85 (Identity Refinement) + #86 (Abstraction)** — they inherit the formalized contract from this blueprint.

---

## 6. GraphDB contract delta (Codex v1 review Finding 7)

The Claim layer introduces new persistence invariants. The GraphDB layer (`graphdb_kdb/`) treats verifier / rebuilder / snapshot as architectural safety rails (D35-D39). Claim space requires explicit updates to each:

**Schema migration:**

- New node type: `Claim` (with all D-83/84-6 + D-83/84-12 attributes + the post-rename `confidence_spread`)
- New rel types: `EVIDENCES`, `ABOUT`, `SUPERSEDES`, `CONTRADICTS`, `QUALIFIES`
- `EVIDENCES.score` rename (post D-83/84-8 Part C) — applies to the new edge, not a migration of existing edges (Claim space is new)
- Schema version bump (TBD — implementation chooses v2.2 / v2.3 / v3.0 per its existing migration discipline)

**Snapshot contract delta** (analogous to Task #80 for Domain/BELONGS_TO):

- Snapshot must export all Claim nodes + EVIDENCES / ABOUT / SUPERSEDES / CONTRADICTS / QUALIFIES edges in JSONL form
- Snapshot format version bumps when this lands (current v3 → v4 per snapshot.py convention)
- Per-edge attributes preserved (provenance_type, score, quoted_text, etc.)

**Rebuild contract delta** (the load-bearing one per OQ-22, scoped by D-83/84-9):

- Rebuild replays compilations to restore LINKS_TO + SUPPORTS (existing behavior)
- Rebuild re-runs the Promotion Contract against the restored compilation state to regenerate Claims + Claim-Claim edges + EVIDENCES
- Rebuild regenerates all denormalized Claim keys from canonical state (per D-83/84-9 — authoritative ABOUT-binding remains; subject_slug + claim_family_id + claim_id are re-derived)
- See OQ-22 for the implementation-form choice (re-run-Promotion vs replay-from-compile_result.json vs sidecar-by-run_id)

**Verifier contract delta** (analogous to Task #79 for Domain/BELONGS_TO):

New `graphdb-kdb verify` invariants for the Claim layer:

| Invariant | Description |
|---|---|
| Every `Claim` has an `ABOUT` edge | No orphan Claims; every Claim must be about an Entity |
| `Claim—ABOUT→Entity` targets exist | No dangling ABOUT references |
| `Source—EVIDENCES→Claim` sources exist | No EVIDENCES from nonexistent sources |
| Every `EVIDENCES` row has valid `provenance_type` | Enum constraint (per D-83/84-7) |
| `analysis_emitted` EVIDENCES rows have non-NULL `quoted_text` + `score` | Per D-83/84-7 Part C contract |
| Claim-Claim edges (CONTRADICTS / SUPERSEDES / QUALIFIES) target existing Claims | No dangling edges |
| State machine invariants | Terminal `retracted` Claims have no `retracted → active` history; `superseded` chains via SUPERSEDES are acyclic |
| `claim_id` parseability | Per D-83/84-6 F1 + Qwen v1 review F5 — Claim node's `claim_id` parses cleanly into `claim_family_id + v<N>` |
| Denormalized-key coherence | `Claim.subject_slug` matches `Claim—ABOUT→Entity.canonical_id` (or via ALIAS_OF) per D-83/84-9 |
| `claim_family_id` consistency | Two Claims with the same `claim_family_id` share `subject_slug`, `predicate_class_canonical`, and `predicate_scope_slugs` |

Verifier deviations may be flagged at severity tiers (`error` / `warning` / `info`) per existing verifier discipline.

---

## 7. References

To be populated. Primary sources: AGM (Alchourrón, Gärdenfors & Makinson 1985); continual-KGE literature (BAKE 2025); HippoRAG (Gutiérrez et al. 2024); Round 6 research returns (`docs/round6-research-*.md`). External reviewer files at `docs/task83-84-promotion-contract-belief-revision-blueprint-codex.md` (D-83/84-2/3 round) and `docs/task83-84-promotion-contract-belief-revision-blueprint-gemini.md` (D-83/84-2/3 round, overreach record). v1 holistic review files at `docs/task83-84-blueprint-v1-review-{codex,deepseek,qwen}.md`. Reviewer panel context at `docs/external-review-panel.md` + `docs/gemini-review-hard-cap-prompt.md`.
