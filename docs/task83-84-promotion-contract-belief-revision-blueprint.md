# Task #83 + #84 — Hypothesis Promotion Contract + Belief Revision (Joint Blueprint)

**Status:** v1 in progress
**Started:** 2026-05-22
**Lineage:** Round 6 §9.4.2 mandate; (a+) decision via Joseph ratification 2026-05-22
**Parallel-design rationale:** `docs/what-is-the-ontology-for.md` §9.3.8 + [[feedback_concrete_first_extract_later]]
**Reviewers (planned, post-v1):** Codex + Antigravity (mirroring Task #74 / #75 / #76 pattern)
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
- `claim_id` = `<claim_family_id>__<polarity>__v<N>` — the *specific version of this claim* identity
- `scope-slug-set` is deterministically serialized: sort + join with `+`; empty set uses `<none>` sentinel
- **Delimiter guard:** `__` is the field separator; subjects / predicate_class / scope-slugs must be kebab-case with no `__` substring (enforced at canonicalization time per D-83/84-5)
- Example single-scope: `buffett__tech-investing-stance__tech-investing__rejects__v1`
- Example multi-scope: `buffett__tech-investing-stance__consumer-electronics+tech-investing__affirms__v1`

**F2 — State machine + Claim-to-Claim relation edges:**

States: `active | superseded | retracted`.

| Transition | Trigger |
|---|---|
| `active → superseded` | A newer claim is committed with a `Claim—SUPERSEDES→Claim` edge pointing at this claim |
| `active → retracted` | **Explicit retraction operation only** — operator marks claim withdrawn/invalid. **Not triggered by decay.** |
| `superseded → active` | Revival: only if the superseding claim is itself retracted; walk `SUPERSEDES` chain backward to find nearest non-retracted ancestor |
| `retracted → *` | Terminal — no path out. If the same claim needs to return, new instance with new version. |

**Decay ≠ retraction.** Decay reduces `confidence` over time (per a decay function operating on the field); state remains `active`. Retraction marks the claim invalid. Decayed claims are still part of the belief state, weighted lower; retracted claims are filtered from default retrieval.

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
| `confidence_score` | Analysis op's confidence in *this specific evidence* (distinct from Claim's aggregated confidence) |
| `run_id` | Which compile run created this evidence link |
| `created_at` | Timestamp |

Putting evidence metadata on the edge — not the Claim node — lets multiple sources support the same Claim with different quoted_texts and confidences, without a list-field on Claim.

**F4 — Meta-claims (`Claim—ABOUT→Claim`) deferred to v2.**

In v1: `Claim—ABOUT→Entity` only. Meta-claims (`Claim—ABOUT→Claim`) added in v2 if concrete demand surfaces.

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
  confidence_score DOUBLE,
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

**OQ-12 resolution (implicit):** the original `provenance.supporting_path` field on the candidate envelope is no longer needed. Persistent provenance lives on `Source—EVIDENCES→Claim` (quoted_text + confidence_score + run_id + created_at). The Analysis-op's graph-walk that surfaced the candidate is a transient artifact — operational info, not durable graph state. The candidate envelope's `supporting_path` field is dropped.

**Resolves:** OQ-3 (Claim attribute set), OQ-5 (meta-claims), OQ-12 (supporting_path).

**Opens:**

- **OQ-14** — How to aggregate multiple `EVIDENCES.confidence_score` values into the Claim's single `confidence` field (max, mean, Bayesian fusion, log-odds sum, etc.). Implementation-level question; deferred to the Belief Revision module work but flagged so it gets explicit attention.

### D-83/84-7 — Upgrade mechanism: additive on Claim layer; LINKS_TO untouched; three-tier provenance — 2026-05-22

**Decision:** Synthesis incorporating Codex's two tightenings (semantic-contract rewrite on D-83/84-1; α → α+ three-tier provenance hierarchy with explicit naming) on top of the (a)+(α) draft. Ratified by Joseph 2026-05-22. **Gemini was not consulted for this round** per the one-strike rule established 2026-05-22 after the hard-cap experiment partial failure (see `docs/gemini-review-hard-cap-prompt.md` + [[feedback_gemini_review_only_guardrail]]).

#### Part A — OQ-2 resolution: upgrade is additive on Claim layer; LINKS_TO untouched

- The Promotion Contract creates Claim nodes + Claim-Claim edges (`SUPERSEDES` / `CONTRADICTS` / `QUALIFIES`) + `EVIDENCES` edges.
- **The upgrade does not delete or derive `LINKS_TO`.** The upgrade operation is additive only.
- Normal compile ingestion (Stage 9/10 `graph_sync`) can still drop/recreate `LINKS_TO` via the existing current-state replacement path. That is not the upgrade's concern.
- **Semantic contract (post-#83/#84):**
  - `LINKS_TO` = corpus topology layer (which entities are associated in the corpus)
  - Claim space = belief layer (polarity, version, provenance, contradiction)
  - **Belief-sensitive reads must consult Claim space when a Claim family exists for the subject.** Topology-only reads (`graph_context_loader`, V0 ops, PageRank, communities, structural-holes) consume `LINKS_TO` unchanged.

#### Part B — OQ-4 resolution: three-tier provenance reconstruction (α+)

When upgrading an existing belief into a Claim, populate `EVIDENCES` via this fallback chain:

- **Tier 1 (preferred): Run-payload reconstruction.** Use `LINKS_TO.run_id` to locate the run sidecar / `compile_result.json` that emitted the edge; extract the source page(s) + structured output. Provides specific source attribution.
- **Tier 2 (fallback): SUPPORTS-overlap.** Walk `Source—SUPPORTS→Entity` for both subject and scope/object entities; intersection yields candidate sources. Honestly weaker — co-mention ≠ predicate-evidencing.
- **Tier 3 (escape hatch): synthesized marker.** If neither Tier 1 nor Tier 2 yields a source, create the OLD Claim with no `EVIDENCES` edges; record attempted-and-failed reconstruction in operational metadata.

#### Part C — `EVIDENCES.provenance_type` attribute (new)

| Value | Source | Required attributes |
|---|---|---|
| `analysis_emitted` | Analysis-op surfaced the candidate | `quoted_text` + `confidence_score` REQUIRED (unless candidate rejected or sent to human review) |
| `reconstructed_from_run_payload` | Tier 1 reconstruction | `quoted_text` + `confidence_score` MAY be NULL |
| `reconstructed_from_supports_overlap` | Tier 2 reconstruction | `quoted_text` + `confidence_score` MAY be NULL — weakest variant |

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

  counterpart: null                      # for no_counterpart / orthogonal cases
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

**Resolves:** OQ-8 (Doxastic Fingerprint hash content), OQ-10 (confidence representation).

**Opens:**

- **OQ-18** — Aggregation distortion (Qwen's catch): when OQ-14 (confidence aggregation rule) lands, must handle bucketed/mapped aggregation edge cases — `low + high → mean(0.3, 0.8) = 0.55` rounds back to medium, losing the polarization signal. Flag `spread`/`variance` field, or `mode(bucket) + mean(score)` as a possible signal pair. **OQ-14 concern, not D-83/84-8.**
- **OQ-19** — Candidate envelope JSON-Schema (Deepseek's follow-up): create a JSON-Schema validating analysis-op emissions. Mirrors `compile_result.schema.json` pattern. Implementation-level follow-up.
- **OQ-20** — Confidence map empirical calibration: defaults `{0.3, 0.5, 0.8}` have no empirical basis. Belongs in Task #75 predeclared eval criteria territory (or its #83/#84 analog).

---

## 4. Candidate envelope — settled and open fields

D-83/84-4 settled `proposed_claim`'s structured form. D-83/84-6 settled the persistent provenance representation (`Source—EVIDENCES→Claim` edge with attributes), which made the previously-open `supporting_path` field on the candidate envelope unnecessary (OQ-12 resolved by dropping the field). The full envelope crossing the #83 gate:

| Field | Source | Specified by | Status |
|---|---|---|---|
| `proposed_claim` | Analysis op + shared classifier (predicate-canon) | **D-83/84-4** | Settled. |
| `provenance.source_paths` | Analysis op | This blueprint | Settled — list of `raw/...` source paths supporting the claim. |
| `provenance.quoted_text` | Analysis op | This blueprint | Settled — source-text excerpts (become `EVIDENCES.quoted_text` on promotion per D-83/84-6). |
| `confidence` | Analysis op | **D-83/84-8** | Bucketed enum (`low`/`medium`/`high`) + system-derived `score` + `score_source` + `map_version`. Score becomes `EVIDENCES.confidence_score` on promotion per D-83/84-6. |
| `analysis_classification` | Analysis op + shared classifier | D-83/84-3 | Settled — 2-step result per D-83/84-2. |
| `counterpart_ref` | Analysis op | This blueprint | Settled — existing edge or Claim ID being engaged (null if `no_counterpart` / `orthogonal`). |
| `doxastic_fingerprint` | Analysis op | D-83/84-3, **D-83/84-8** | Targeted: hashes subject (canonical-form attributes only) + specific counterpart state. Coupling-as-invariant: scope expands with classifier-input-surface. |

**At promotion-time** the contract re-runs the shared classifier (D-83/84-3 #3), produces `promotion_classification` (same shape as `analysis_classification`), compares fingerprint freshness, sets `classification_drift: bool` with reason. These fields are added to the candidate envelope (or to a per-candidate audit record) by the Promotion Contract — not emitted by the Analysis op.

---

## 5. Blueprint v1 status — structurally complete pending external v1 review

With D-83/84-8 ratified, the **structural** decisions for #83 (Promotion Contract) and #84 (Belief Revision) are complete:

| Layer | Decision | Status |
|---|---|---|
| Schema placement | D-83/84-1 (+ D-83/84-7 amendment) | ✅ |
| Relation typology + triggers | D-83/84-2 | ✅ |
| Classifier role + Doxastic Fingerprint pattern | D-83/84-3 | ✅ |
| Predicate representation | D-83/84-4 | ✅ |
| Predicate-class canonicalization | D-83/84-5 | ✅ |
| Claim node schema | D-83/84-6 | ✅ |
| Upgrade mechanism | D-83/84-7 | ✅ |
| Candidate envelope details | D-83/84-8 | ✅ |

**Remaining open questions** are all either implementation-level (OQ-13 canonicalization form; OQ-14 confidence aggregation; OQ-15/16/17 upgrade-mechanism details; OQ-19 candidate-envelope JSON-Schema) or predeclared-eval territory analogous to Task #75 (OQ-6 corroboration threshold; OQ-9 drift eval thresholds; OQ-18 aggregation-distortion signal; OQ-20 confidence map calibration). None block structural v1.

**Recommended next steps** (decision for Joseph):

1. **Fire blueprint v1 holistically at the post-Gemini reviewer panel** (Codex + Deepseek + Qwen — see `docs/external-review-panel.md`) for v1 review. Mirrors Tasks #74 / #75 / #76 pattern (per-decision review during draft → holistic v1 review → v2 → implementation).
2. **File a separate task for predeclared eval criteria for #83/#84** (analogous to Task #75 for step-3 ops). OQ-6 / OQ-9 / OQ-18 / OQ-20 live there, not in this blueprint.
3. **Begin implementation** on Task #83 (Promotion Contract) and Task #84 (Belief Revision) in parallel per the §9.4.4 parallel-design sequencing.

Once v1 is reviewed and any blocking feedback addressed (→ v2), Tasks #85 (Identity Refinement) and #86 (Abstraction) can be unblocked since they inherit the formalized contract.

---

## 6. References

To be populated. Primary sources: AGM (Alchourrón, Gärdenfors & Makinson 1985); continual-KGE literature (BAKE 2025); HippoRAG (Gutiérrez et al. 2024); Round 6 research returns (`docs/round6-research-*.md`). External reviewer files at `docs/task83-84-promotion-contract-belief-revision-blueprint-{codex,gemini}.md`.
