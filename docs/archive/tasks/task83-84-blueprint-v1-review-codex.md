# Task #83 + #84 Blueprint v1 — Holistic Review (Codex)

**Reviewer:** Codex
**Date:** 2026-05-22
**Target:** `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v1, 555 lines)
**Scope:** Holistic v1 review per `docs/task83-84-v1-review-prompt.md`.

---

## Convergence

The blueprint is directionally coherent. D-83/84-7's amendment fixes the largest early risk: LINKS_TO is no longer overloaded as both topology and belief. The system now has a clean split:

- **LINKS_TO** = corpus association/topology
- **Claim** = belief state, contention, versioning, provenance
- **Promotion Contract** = only authorized Analysis → Learn mutation boundary

D-83/84-3 and D-83/84-8 also fit well: promotion-time classification is authoritative, and the fingerprint is audit material, not a skip mechanism. That is the right v1 simplicity trade.

---

## Findings

### 1. Claim identity is still under-specified for version allocation and qualifiers.

D-83/84-6 defines:

> `claim_id = <claim_family_id>__<polarity>__v<N>`

This is close, but not enough for the cases D-83/84-2 admits. If two distinct qualifying claims share subject, predicate, scope, polarity, and version counter space, they collide unless version allocation rules are global and deterministic. Example: two different `qualifies_or_extends` candidates both `affirms` the same family with different `condition_text`.

The blueprint needs to say whether `v<N>` is allocated per `claim_family_id`, per `(claim_family_id, polarity)`, or per supersession chain. My lean: version should be **family-global**, not polarity-local, because contradictory claims are part of one evolving belief family.

**Recommendation:** Amend D-83/84-6 F1: version is monotonic per `claim_family_id`; `claim_id = claim_family_id + "__v<N>"`; polarity remains a Claim attribute, not part of identity. If polarity must stay in the id for readability, it should not control version allocation.

### 2. Canonicalization migration is structural, not implementation-only.

The prompt's own review target asks what happens when Task #74 canonicalization merges aliases. The blueprint currently embeds `subject_slug` into both `Claim.subject_slug` and `claim_family_id`. If a subject slug is merged or canonical identity changes, Claim primary keys and Claim-family identity become stale.

This is not just migration plumbing. It affects the durable meaning of Claim identity.

**Recommendation:** Add a D-83/84-9 amendment: `Claim—ABOUT→Entity` is the authoritative subject binding; `subject_slug` and `claim_family_id` are denormalized lookup keys that must be rewritten during canonicalization repair/rebuild. Also specify whether Claim IDs are mutable on canonical rewrite or whether an alias-forwarding table is preserved.

### 3. The candidate envelope should use evidence objects, not parallel provenance fields.

§4 says:

- `provenance.source_paths`
- `provenance.quoted_text`
- `confidence.score` becomes `EVIDENCES.confidence_score`

But D-83/84-6 stores evidence on `Source—EVIDENCES→Claim`, where each source may have its own quote and confidence. The envelope should mirror that cardinality. Otherwise multiple sources/quotes/confidence scores become ambiguous.

**Recommendation:** Replace `provenance.source_paths` + `provenance.quoted_text` with:

```yaml
evidence:
  - source_id: KDB/raw/...
    quoted_text: ...
    confidence:
      bucket: high
      score: 0.8
      score_source: config_map
      map_version: confidence_map_v1
```

Then Claim confidence aggregation consumes `evidence[].confidence.score`; `EVIDENCES.confidence_score` is per evidence edge.

### 4. Tier-1 provenance reconstruction overclaims precision.

D-83/84-7 says:

> Use `LINKS_TO.run_id` to locate the run sidecar / `compile_result.json` that emitted the edge; extract the source page(s) + structured output.

Current `LINKS_TO` is entity topology, not predicate-level assertion. It has `run_id`, but not the predicate, quote, or claim structure. A run sidecar can tell what page emitted a link, but not necessarily the exact belief claim now being reconstructed. This is stronger than Tier 2, but still not exact.

**Recommendation:** Rename Tier 1 from "Run-payload reconstruction" to "run-payload candidate reconstruction" and explicitly state it may produce source attribution without quote-level evidence. `provenance_type=reconstructed_from_run_payload` should be treated as weaker than `analysis_emitted`, even when source IDs are recovered.

### 5. Promotion idempotency is missing.

Promotion is a mutating boundary. The blueprint specifies what to create, but not what happens when the same candidate is promoted twice, re-emitted by multiple Analysis ops, or partially applied before failure.

This is a v1 structural issue because it determines uniqueness constraints and merge behavior for Claim, EVIDENCES, and Claim-Claim edges.

**Recommendation:** Add a short "idempotency contract" to D-83/84-7:

- Claim upsert by `claim_id`
- EVIDENCES uniqueness by `(source_id, claim_id, quoted_text_hash, provenance_type)`
- CONTRADICTS/SUPERSEDES/QUALIFIES uniqueness by `(from_claim_id, to_claim_id)`
- promotion retry must be safe after partial completion

### 6. Belief-sensitive read contract needs one more level of specificity.

D-83/84-7 says:

> Belief-sensitive reads must consult Claim space when a Claim family exists for the subject.

Good, but incomplete. "For the subject" is too broad and could force every belief read about Buffett through all Buffett claims. The lookup key should be the **claim family**: subject + predicate class + scope.

**Recommendation:** Change to: belief-sensitive reads must consult Claim space when a `claim_family_id` exists for the queried `(subject_slug, predicate_class_canonical, predicate_scope_slugs)`.

### 7. Verifier/rebuild/snapshot obligations should be promoted from implied to explicit.

The GraphDB layer already treats verifier/rebuilder/snapshot as architectural safety rails. Claim space adds new invariants: Claim ABOUT targets exist, EVIDENCES sources exist, Claim-Claim edges target existing Claims, terminal retracted claims are not revived, superseded chains are acyclic.

**Recommendation:** Add a "GraphDB contract delta" section listing required updates to schema migration, snapshot, rebuild, and verify. This is not implementation form; it is the persistence contract.

---

## Open Questions

- Should `Claim.confidence` store only aggregate score, or also aggregate spread/variance from OQ-18? I think OQ-14 and OQ-18 are structural enough to resolve before implementation, because they affect the Claim schema.
- Should Claims inherit Domain from the subject entity, evidence sources, or neither? Lean: do not inherit as truth; derive at query time from ABOUT subject domain unless Task #86 later needs Claim-level domains.
- Should retracted Claims remain available as contradiction targets? Default retrieval filters them, but audit/revision queries probably need them traversable.
