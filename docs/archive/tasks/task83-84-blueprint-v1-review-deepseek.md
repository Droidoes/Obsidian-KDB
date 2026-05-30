# Task #83 + #84 Blueprint v1 — Holistic Review (Deepseek)

**Reviewer:** Deepseek (panel member since D-83/84-8)
**Date:** 2026-05-22
**Target:** `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v1, 555 lines)
**Scope:** Holistic v1 review per `docs/task83-84-v1-review-prompt.md` — internal consistency, missed structural considerations, architectural risks, implementation risks, open-question coverage.

---

## 1. Convergence — what holds together cleanly

The eight decisions form a coherent chain where each layer depends cleanly on the one before:

- **D-83/84-1 → D-83/84-2 → D-83/84-3 → D-83/84-4**: The hybrid model (1) creates the entity basis for a counterpart check; the 2-step classifier (2) defines what "counterpart" means; the classifier role (3) says the check happens at both Analysis and promotion time with a shared module; the predicate representation (4) makes same-predicate matching deterministic so the classifier doesn't need an LLM call. Each depends on the previous; no circularities.

- **Candidate envelope cross-reference (§4, lines 508–522)**: The envelope table correctly cross-references every contributing decision. `proposed_claim` → D-83/84-4. `confidence` → D-83/84-8 with explicit score→EVIDENCES.confidence_score flow. `doxastic_fingerprint` → D-83/84-3 + D-83/84-8. The table's `analysis_classification` field references D-83/84-3 which specifies the 2-step shape (counterpart_status × relation_kind); the promotion-time fields are explicitly labeled "added by the Promotion Contract — NOT emitted by the Analysis op." This boundary is clean.

- **D-83/84-6 schema ↔ D-83/84-7 upgrade mechanism**: The Claim node carries exactly the fields the upgrade creates (polarity, modality, predicate_class_canonical, etc.). The `EVIDENCES` attributes (`quoted_text`, `confidence_score`, `provenance_type`, `run_id`) map 1:1 to what the upgrade provisions (D-83/84-7 Part C: `analysis_emitted | reconstructed_from_run_payload | reconstructed_from_supports_overlap`). The `SUPERSEDES` / `CONTRADICTS` / `QUALIFIES` edge types in D-83/84-6 §F2 match exactly what D-83/84-7 line 362 says the Promotion Contract creates.

- **D-83/84-8 Part B (Coupling-as-invariant)**: The `hash_scope: targeted-v1` tag + `classifier_version` field turn an implicit coupling into a versioned, auditable contract. This is the strongest architectural invariant in the blueprint — it prevents the silent bit-rot where the classifier starts reading new data but the fingerprint doesn't track it.

- **D-83/84-7 Part D amendment of D-83/84-1**: The semantic rewrite — LINKS_TO = topology, Claim = belief — is a genuine clarification, not a backtrack. The original D-83/84-1 framing ("uncontested = LINKS_TO, contested = Claim") was a v1 approximation; the amendment makes the contract precise without invalidating any downstream decision. The `BELONGS_TO` edge on entities already exists (Task #76); Claims don't need a domain field because `Claim—ABOUT→Entity—BELONGS_TO→Domain` provides domain via traversal. This pattern is implicitly correct but not stated — see Finding 2.

**Overall**: The inter-decision consistency is high. No contradictions between any two ratified decisions. The candidate envelope table (§4) is the load-bearing integration artifact and it's correct.

---

## 2. Findings — concrete issues, ambiguities, missed considerations

### Finding 1: Claim retraction edge-cleanup is unspecified

D-83/84-6 §F2 specifies the Claim state machine (`active → superseded → retracted`, with revival cascade) and the retraction semantics (decay ≠ retraction). But:

- **When Claim C is retracted, what happens to C's outgoing `CONTRADICTS`/`QUALIFIES` edges?** If Claim A `CONTRADICTS` Claim B, and Claim B is retracted, the contradiction doesn't become "resolved" — Claim A's assertion hasn't changed. But the graph now has a dangling edge pointing at a retracted node. Does Claim A's state remain `active`? Does it get a flag? The blueprint is silent.

- **When Claim C is retracted, what happens to incoming `CONTRADICTS`/`QUALIFIES` edges pointing at C?** Claim A `CONTRADICTS` Claim C. C gets retracted. Is A's edge preserved (for audit)? Pruned (to keep the graph clean)? Does A's state change?

- **`SUPERSEDES` cascade** (§F2 revival query) handles `active → retracted` correctly: walk backward, find nearest non-retracted ancestor. But the query walks `SUPERSEDES` only. What if the predecessor was also `CONTRADICTS`-targeted by something else? The revival doesn't check that the revived claim is still coherent in the belief state.

This is a real implementation ambiguity, not a deferred-implementation-detail. The state machine transitions are specified; the edge-behavior-under-retraction is not.

### Finding 2: Claim domain membership is available but implicit — should be stated

The Claim node schema (D-83/84-6, lines 293–311) has no `domain` field. Domain is an Entity attribute (Task #76, `BELONGS_TO`). Since `Claim—ABOUT→Entity`, a query can reach the domain via two hops. This works correctly for both retrieval and the predeclared-eval pipeline (Task #75 §4.2 community/domain-ratio gates). But the blueprint never states this traversal pattern explicitly. A reader could reasonably ask "do Claims get domain somehow?" and not find an answer.

**How it matters**: when the Task #75-style eval surface lands for #83/#84, someone will need to write "Claims per domain" queries. If the traversal isn't documented, the first implementation attempt will either (a) add redundant `domain` to the Claim node, or (b) discover the traversal and write it ad-hoc. Stating it now prevents (a).

### Finding 3: Entity canonicalization can invalidate existing Claim IDs on incremental compiles

D-83/84-6 §F1 defines `claim_id = <claim_family_id>__<polarity>__v<N>`, where `claim_family_id` includes `subject_slug`. Gemini's refinement (line 39: "The mutability concern is completely resolved by KDB's rebuild-first architecture") is correct for `graphdb-kdb rebuild`. But:

- **Incremental compiles** (`kdb-compile` without rebuild) won't re-derive all Claim IDs. If Task #74 discovers a new alias during an incremental compile (e.g., `buffett` → `warren-buffett`), existing Claims with `subject_slug: buffett` are now misindexed. The Claim's `subject_slug` column still says `buffett` but the canonical entity is `warren-buffett`.

- The Claim has a `subject_slug STRING` field (line 297). There's no join through `ALIAS_OF` for the subject — the slug is stored directly. So querying "all Claims about warren-buffett" won't find the old `buffett`-subjected Claims unless the query also traverses `ALIAS_OF` backward.

- This is not a rebuild problem (rebuild regenerates everything from scratch). But incremental compiles are the normal operating mode. The blueprint should acknowledge this as a known limitation — either (a) the Promotion Contract updates `subject_slug` on all affected Claims when a new alias is canonicalized, or (b) claim-subject queries must always resolve through `ALIAS_OF`, or (c) incremental operation accepts stale subject_slugs until the next rebuild.

### Finding 4: The rebuild contract for Promotion-Contract-created data is undefined

`graphdb-kdb rebuild` currently replays `compile_result.json` payloads through the ingestor to reconstruct the graph. But Claim nodes, Claim-Claim edges, and `EVIDENCES` edges are created by the Promotion Contract — they are **post-compilation artifacts**, not represented in `compile_result.json` payloads.

If rebuild only replays compilations, it produces no Claims. The graph would contain LINKS_TO topology but no belief layer. Two possible resolutions, neither stated:

- **(a) Store promotion decisions in the run payload** so rebuild can replay them (add a `promoted_candidates` section to `compile_result.json`).
- **(b) Re-run the Promotion Contract during rebuild** — the Promotion Contract reads the graph state and promotes candidates; rebuild replays compilations then re-runs promotion.

Either path has design implications. The blueprint should file this as an explicit architectural question rather than discover it at rebuild-implementation time.

### Finding 5: The coupling-as-invariant (D-83/84-8 Part B) has no enforcement mechanism

```
Fingerprint ≠ classifier-input-surface is a contract violation.
```

This is a named invariant but it's a **manual invariant** — it depends on a human reviewer or PR author remembering to update `hash_scope` when they modify the classifier's reads. Without an automated check (a test that introspects the classifier and verifies fingerprint scope covers all read paths), this invariant will drift the first time someone adds a classifier input and forgets the fingerprint update.

The `classifier_version` field in the fingerprint (line 416) mitigates this partially — if the classifier version changes but the hash_scope doesn't, it's a detectable inconsistency. But the version is a human-maintained string; it can also drift.

**Recommendation**: add OQ-22: "How to enforce coupling-as-invariant — manual review checklist? automated test that introspects classifier read surface? lint rule on classifier module?"

---

## 3. Recommendations — proposed amendments

### Recommendation 1: File retraction-edge-cleanup as architectural question (→ OQ-21)

Add to the OQ table:

```markdown
| **OQ-21** | When a Claim is retracted (state=retracted), what happens to its
outgoing and incoming CONTRADICTS / QUALIFIES edges? Options: (a) preserve all
edges for audit (dangling pointer acceptable for retracted nodes), (b) mark
edges as `retracted_source` without removing them, (c) cascade (retracting a
Claim may auto-resolve contradictions it anchored). Does retracting a Claim
that SUPERSEDES another trigger an automatic revival cascade per F2? | #84 |
Open |
```

This is a D-83/84-6 §F2 state-machine question, not an implementation detail. It affects the Claim-Claim edge semantics under the primary state transition (`active → retracted`).

### Recommendation 2: State domain traversal pattern explicitly

Add a note to D-83/84-6 or §4:

> Claims inherit domain membership via `Claim—ABOUT→Entity—BELONGS_TO→Domain`. No `domain` field is added to Claim; belief-sensitive domain queries traverse two hops. This pattern is intentional: domain is an Entity property; Claims about an Entity share its domain by association, not by duplication.

This prevents a future implementer from adding redundant `domain` to the Claim schema.

### Recommendation 3: Acknowledge incremental-compile subject_slug staleness as a known limitation

Add a note to D-83/84-6 §F1:

> **Incremental-compile limitation**: when Task #74 entity canonicalization discovers a new alias during an incremental compile, existing Claims with the old `subject_slug` are not automatically re-keyed. Claim-subject queries on incremental databases MUST resolve through `ALIAS_OF`: `MATCH (c:Claim)-[:ABOUT]->(e:Entity) WHERE e.canonical_id = $requested_slug OR exists((:Entity {slug: $requested_slug})-[:ALIAS_OF]->(e))`. This limitation is resolved on the next `graphdb-kdb rebuild`. Flagging for future incremental-compaction work.

### Recommendation 4: File rebuild contract for Claims as architectural question (→ OQ-22)

Add to the OQ table alongside my enforcement-mechanism note (Finding 5):

```markdown
| **OQ-22** | How does `graphdb-kdb rebuild` reproduce Claim nodes, Claim-Claim
edges, and EVIDENCES edges that are created by the Promotion Contract
downstream of compilation? Options: (a) store promotion decisions in
compile_result.json as `promoted_candidates` so rebuild replays them, (b) re-run
the Promotion Contract during rebuild after all compilations are replayed, (c)
store promotion decisions in a separate sidecar indexed by run_id. Affects
snapshot contract as well. | #84 / rebuild module | Open |
```

---

## 4. Open questions — additional concerns raised but not resolvable in review

| Tag | Question | Why it matters | Suggested owner |
|---|---|---|---|
| **OQ-23** | How does the Promotion Contract handle a batch of candidates that interact with each other? E.g., Candidate A contradicts existing Claim X; Candidate B also contradicts Claim X but supersedes Candidate A. If promoted sequentially, B's promotion happens before A's and A sees a Claim not an edge. If promoted in batch, the order doesn't matter because both see the pre-promotion state. Which is the contract? | Batch semantics affect determinism of promotion-time classification. The blueprint assumes per-candidate processing (§2: "Candidate hits #83 Promotion Contract gate") but doesn't specify batch ordering. | #83 |
| **OQ-24** | Can the same Analysis op emit multiple candidates that engage the same counterpart? If so, is there a deduplication step before the Promotion Contract? Or does each candidate independently go through the gate, with the second one seeing the first's promotion result? | OQ-23's sibling — same root question about batch semantics. The `null-counterpart collision` flag (Qwen's catch, implied by `hash_scope` + `classifier_version` metadata in D-83/84-8 Part A) avoids identical-fingerprint collision but doesn't address semantic deduplication. | #83 |

---

## 5. Verdict

**The blueprint is structurally sound for v1.** The eight decisions form a coherent chain; the candidate envelope integrates them cleanly; the LINKS_TO/Claim topology/belief separation (D-83/84-7 amendment) resolves the biggest potential semantic drift. The open questions (OQ-6, 9, 13–22) are correctly classified — most are implementation-level or eval-level, not structural blockers.

**Four areas need amendment before v1 declares done:**

1. **Claim retraction edge-cleanup** (Finding 1 → Recommendation 1): unspecified edge behavior under `active → retracted`. Needs an explicit contract or an OQ filed.
2. **Entity canonicalization vs incremental Claim IDs** (Finding 3 → Recommendation 3): subject_slug staleness on incremental compiles needs acknowledgment.
3. **Rebuild contract for Claims** (Finding 4 → Recommendation 4): how rebuild reproduces post-compilation Promotion Contract artifacts.
4. **Coupling-as-invariant enforcement** (Finding 5 → Recommendation 4 footnote): the strongest architectural invariant in the blueprint has only a manual enforcement story.

None of these block implementation start. All four can be resolved by filing OQs and acknowledging limitations — they don't require redesign.

**Recommendation**: Ratify v1 with the four amendments above folded in; move to v1→v2 with OQ-21/22/23/24 filed; begin implementation once blocking OQs (OQ-21: retraction edge-cleanup; OQ-22: rebuild contract) have a sketched resolution.
