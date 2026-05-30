# Task #83 + #84 Blueprint v1 — Holistic Review Prompt

**Purpose:** Fire blueprint v1 (`docs/task83-84-promotion-contract-belief-revision-blueprint.md`) at the post-Gemini external review panel for holistic structural review before any code is written. Mirrors the v1-review pattern that produced Task #74 / #75 / #76's v2 quality jump.

**Dispatched:** 2026-05-22 (to be fired by Joseph)
**Target panel:** Codex + Deepseek + Qwen (per `docs/external-review-panel.md`)
**Response files (one per reviewer):**
- `docs/task83-84-blueprint-v1-review-codex.md`
- `docs/task83-84-blueprint-v1-review-deepseek.md`
- `docs/task83-84-blueprint-v1-review-qwen.md`

---

## ─── Prompt body ───

You are reviewing **v1 of a joint blueprint** for Tasks #83 (Hypothesis Promotion Contract) and #84 (Belief Revision) in the Obsidian-KDB project. The blueprint is at `docs/task83-84-promotion-contract-belief-revision-blueprint.md`. It contains eight ratified decisions (D-83/84-1 through D-83/84-8) developed across multiple per-decision review rounds with you (and other reviewers).

This is the **holistic v1 review** — your chance to stress-test the blueprint as a coherent whole before implementation begins. Each prior round focused on individual decisions; this round looks at the system.

### Project context (brief)

The blueprint operationalizes the "Learn" arm of the project's [B]/[C]/[A] second-brain goal (per `docs/what-is-the-ontology-for.md` §9.4). Round 6 ratified three Learn mechanisms + Hypothesis Promotion as a first-class boundary contract (the **(a+)** decision):

1. Belief Revision (Task #84)
2. Identity Refinement (Task #85, deferred)
3. Abstraction / Principle Induction (Task #86, deferred)

Plus Hypothesis Promotion Contract (Task #83), the cross-cutting boundary mediating every Analysis → Learn transition.

The current blueprint covers **only #83 + #84**, parallel-designed per §9.4.4. #85 and #86 inherit the contract.

### What to review

Read the full blueprint end-to-end. Then stress-test along these axes:

1. **Internal consistency.** Do D-83/84-1 through -8 hang together without contradictions? The candidate envelope shape (assembled across D-83/84-3, -4, -6, -7, -8) — is it consistent at every decision boundary? Does the upgrade mechanism (D-83/84-7) correctly use the Claim node schema (D-83/84-6)?

2. **Missed structural considerations.** What architecturally-load-bearing concerns aren't addressed? Some candidate areas to probe (you may find others):
   - Claim retraction propagation — when a Claim is retracted, what happens to its `CONTRADICTS` / `SUPERSEDES` / `QUALIFIES` edges and to other Claims that referenced it?
   - Interaction with Task #76 Domain field — Claims about an entity, does the Claim inherit the entity's domain? Does that affect community/domain-ratio gates (Task #75 §4.2)?
   - Canonicalization-of-canonicalization — when Task #74 entity canonicalization merges aliases, what happens to existing Claims using the now-merged `subject_slug`?
   - Schema migration story — going from v2.1 to a future v2.x with Claim + 5 new edge types. Migration risk?
   - Rebuild / snapshot — `graphdb-kdb rebuild` and `graphdb-kdb snapshot` need to handle the new schema. What's the contract?

3. **Architectural risks per decision.** Each ratified decision has a stated rationale; flag any rationale you find weak under whole-blueprint reading. (E.g., does the hybrid model in D-83/84-1 hold up under the upgrade mechanism in D-83/84-7? Does D-83/84-3's "always re-classify at promotion-time" still make sense given D-83/84-8's targeted fingerprint?)

4. **Implementation risks.** What's likely to be expensive or fragile when this hits code? Items the blueprint doesn't yet address but should (or should explicitly defer with a note).

5. **Open-question coverage.** The blueprint has open OQs (OQ-6, OQ-9, OQ-13, OQ-14, OQ-15, OQ-16, OQ-17, OQ-18, OQ-19, OQ-20). Are any of them actually structural and should be resolved before v1 declares done?

### Out of scope for this review

- **Implementation form.** Polymorphic class hierarchies, specific Python type signatures, Cypher query patterns — these are Phase 3 work. The blueprint specifies contracts, not implementations.
- **Re-litigating ratified decisions** unless you have new evidence (a missed consideration, a structural inconsistency you noticed in this holistic read). Decisions are versioned; if a real problem surfaces, propose a D-83/84-9 amendment.
- **Predeclared eval criteria** (OQ-6, OQ-9, OQ-18, OQ-20) — these are filed for a separate task analogous to Task #75. They live outside this blueprint.

### Output format

Standard review-prompt format. Suggested structure:

1. **Convergence** — what holds together cleanly across the blueprint (don't dwell; just note)
2. **Findings** — concrete issues, ambiguities, contradictions, missed considerations
3. **Recommendations** — proposed amendments to specific decisions, prefixed `**Recommendation:**` or `**Proposal:**`
4. **Open questions** — additional questions raised but not resolvable in review

**Length:** under 2500 words. Cite specific decision numbers and section anchors (e.g., "D-83/84-7 Part C") where possible. Quote the blueprint with `> …` blockquotes where you're raising an issue with specific wording.

### The blueprint to review

Attached: `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (full file).

For project context: see also `docs/what-is-the-ontology-for.md` §9.4 (Round 6 closure that mandated this blueprint), `docs/external-review-panel.md` (reviewer panel composition), and `docs/CODEBASE_OVERVIEW.md` (architecture).
