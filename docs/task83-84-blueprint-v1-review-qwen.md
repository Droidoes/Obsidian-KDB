# Task #83 + #84 Blueprint v1 — Holistic Review (Qwen)

**Reviewer:** Qwen
**Date:** 2026-05-22
**Target:** `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (v1, 555 lines)
**Scope:** Holistic v1 review per `docs/task83-84-v1-review-prompt.md`.

---

## 1. Convergence

The blueprint hangs together cleanly. The spine is tight: hybrid schema (D-83/84-1) → relation typology triggers (D-83/84-2) → classifier discipline (D-83/84-3) → structured predicate (D-83/84-4) → canonicalization (D-83/84-5) → Claim schema (D-83/84-6) → upgrade mechanism (D-83/84-7) → candidate envelope (D-83/84-8). Each decision flows into the next without circular dependencies or orphaned assumptions. The Buffett scenario (§2) is threaded through multiple decisions and serves as a good concrete anchor.

The coupling-as-invariant contract (D-83/84-8 Part B) is the strongest architectural contribution — it makes the fingerprint a living contract rather than a one-time spec.

---

## 2. Findings

### F1 — D-83/84-7 Part A: two read paths, no declared conflict-resolution rule

> "Belief-sensitive reads must consult Claim space when a Claim family exists for the subject."

What happens when LINKS_TO says one thing and the Claim layer says another? The blueprint says "consult Claim space" but doesn't specify whether:

- (a) LINKS_TO is ignored entirely once a Claim exists for that pair
- (b) both are consulted with Claim taking precedence (weighted fusion)
- (c) the read path is configurable per consumer

This is an ambiguity, not a contradiction — but a consumer of the graph (e.g., `graph_context_loader`, V0 ops) needs a deterministic rule, not "consult." The D-83/84-7 semantic contract rewrite says "Reading LINKS_TO as belief truth post-#83/#84 is a contract violation" which leans toward (a), but the exact boundary is fuzzy: what about LINKS_TO edges that have no corresponding Claim for that pair but do have Claims for other predicates on the same subject? Does the mere existence of any Claim for the subject trigger Claim-space consultation for all edges, or only the contested pairs?

**Recommendation:** Add an explicit read-path rule to D-83/84-7: "For a given (subject, predicate, scope) tuple: if a Claim family exists, read from Claim space; otherwise read from LINKS_TO." Tuple-granularity, not subject-granularity. This keeps the rule local and avoids forcing Claim-space reads for uncontested edges on a contested subject.

### F2 — D-83/84-3 vs D-83/84-8 Part D: fingerprint drift vs. classification drift interaction under-specified

D-83/84-8 Part D defines two distinct signals:

- `fingerprint_drift` — state_hash changed
- `classification_drift` — classification changed

But the blueprint doesn't specify the expected correlation or the action matrix when they combine:

| `fingerprint_drift` | `classification_drift` | Action? |
|---|---|---|
| false | false | Auto-promote? |
| true | false | ? |
| false | true | ? |
| true | true | ? |

The blueprint says "record both" but doesn't say what the Promotion Contract does with each combination. In particular, `fingerprint=false, classification=true` is the case where "a newly-relevant Claim that didn't exist at analysis-time" appeared — the fingerprint couldn't detect it (by design, per targeted scope), but re-classification caught it. Should this case trigger human review? Auto-demote to lower confidence? The answer matters for the auto-promote vs review gate.

**Recommendation:** Add a decision matrix to §4 or D-83/84-8 Part D specifying the promotion behavior for each of the four combinations. Even "defer to implementation" with a note explaining the reasoning is better than silence.

### F3 — D-83/84-6 F2: state machine missing a decay-to-low-confidence action

> "Decay ≠ retraction. Decay reduces confidence over time; state remains active."

This is correct as a principle, but the state machine doesn't specify what happens when a claim's confidence decays below a meaningful threshold. At what point does a decayed claim get filtered from retrieval, archived, or flagged for review? "Active" at `confidence=0.01` and `confidence=0.8` are both "active" but semantically very different.

**Recommendation:** Add a confidence threshold note to F2: "When confidence decays below threshold T (configurable, analogous to OQ-6's corroboration threshold), the claim remains `active` but is excluded from default retrieval. The claim can still be surfaced for audit or re-evaluation." This gives the decay mechanism a concrete behavioral endpoint.

### F4 — D-83/84-2: `orthogonal` and `no_counterpart` have the same action but different semantics

The default action table gives both the same behavior: "Write LINKS_TO + SUPPORTS. No Claim." But `orthogonal` means "entities present, no claims engaged" while `no_counterpart` means "no existing edge or Claim." The difference matters for the Doxastic Fingerprint — `no_counterpart` → `counterpart: null` (per D-83/84-8 Part A) means the fingerprint is just the subject hash, creating the null-collision case Qwen flagged in the D-83/84-8 review. Two different `no_counterpart` candidates on the same subject will have identical fingerprints.

**Recommendation:** Add a `context_key` or `candidate_kind` field to the fingerprint for `no_counterpart` cases — something like the predicate class + scope that distinguishes "Buffett founded Berkshire" from "Buffett invests in Apple" even when neither has a counterpart. Minimal addition (one string), preserves the targeted-scope principle, avoids null-collision.

### F5 — D-83/84-6 F1: `claim_id` format assumes no `__` in component slugs but doesn't enforce at schema level

> "Delimiter guard: `__` is the field separator; subjects / predicate_class / scope-slugs must be kebab-case with no `__` substring (enforced at canonicalization time per D-83/84-5)"

The enforcement is deferred to canonicalization time (D-83/84-5), but the Claim node schema (Cypher DDL) has no constraint. A malformed slug from a legacy run or external source could create an unparseable claim_id.

**Recommendation:** Add a validation note to D-83/84-6 F1: "The Promotion Contract validates `claim_id` parseability before write — rejects candidates with malformed `claim_id`. This is a belt-and-suspenders check; canonicalization should prevent it, but the write path must not trust upstream."

### F6 — Missing: Claim retraction propagation

The blueprint specifies SUPERSEDES, CONTRADICTS, and QUALIFIES edges, but what happens when a Claim is retracted? Do its outbound edges get deleted? Do Claims that reference it (via QUALIFIES or CONTRADICTS) need to be re-evaluated? A retracted claim that was the basis for a QUALIFIES relationship leaves the qualifying claim dangling.

**Recommendation:** Add a note to D-83/84-6 F2 (or open a new OQ) specifying retraction propagation: "When a Claim is retracted, traverse its outbound Claim-Claim edges. For each dependent Claim: (a) CONTRADICTS edge → no action (contradiction remains historical fact); (b) SUPERSEDES edge → superseding claim loses its supersession basis; (c) QUALIFIES edge → qualifier becomes ungrounded, flag for re-evaluation."

### F7 — D-83/84-8 Part C: confidence `score` on the candidate vs. `confidence_score` on EVIDENCES — naming collision risk

The candidate envelope has `confidence.score` (system-derived from bucket). The EVIDENCES edge has `confidence_score`. On promotion, the blueprint says "Score becomes `EVIDENCES.confidence_score`" but the naming difference (`.score` vs `.confidence_score`) invites confusion.

**Recommendation:** Align naming. Either candidate uses `confidence.confidence_score` (matching the edge), or EVIDENCES uses `score` (matching the candidate). Consistency matters when tracing a promoted Claim's confidence back to its candidate origin.

---

## 3. Recommendations (summary)

| # | Decision | Recommendation | Priority |
|---|---|---|---|
| R1 | D-83/84-7 Part A | Declare tuple-granularity read-path rule (Claim-space iff Claim family exists for that specific tuple) | High |
| R2 | D-83/84-8 Part D | Add promotion action matrix for the 4 fingerprint/classification drift combinations | High |
| R3 | D-83/84-6 F2 | Add confidence decay threshold behavior (active but excluded from default retrieval below T) | Medium |
| R4 | D-83/84-8 Part A | Add `context_key` to fingerprint for `no_counterpart` cases to avoid null-collision | Medium |
| R5 | D-83/84-6 F1 | Add `claim_id` parseability validation at Promotion Contract write path | Low |
| R6 | D-83/84-6 F2 | Specify retraction propagation behavior for Claim-Claim edges | Medium |
| R7 | D-83/84-8 Part C | Align `confidence.score` naming with `EVIDENCES.confidence_score` | Low |

---

## 4. Open Questions

- **On OQ-6** (corroboration threshold): This is eval territory but has a structural dependency — D-83/84-2's `reinforces` action gates on "corroboration count crosses threshold N." The default N=3 is stated but the counting mechanism isn't: is it unique sources, unique runs, unique SUPPORTS edges? This affects whether OQ-6 is purely eval (tune the number) or structural (define what "count" means). Flag for the eval task to resolve the counting mechanism as well as the threshold value.

- **On OQ-14** (confidence aggregation): The blueprint defers this to implementation, but the aggregation function choice (max, mean, Bayesian) affects the Claim node's `confidence DOUBLE` field semantics. If the Claim node stores an aggregated confidence, the aggregation function should be specified at blueprint level even if the formula is tuned later. Otherwise the field's meaning is implementation-defined and can't be reasoned about at the contract level.
