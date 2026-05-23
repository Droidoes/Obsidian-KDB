# Task #87 Blueprint v1 — Holistic Review Prompt

**Purpose:** Fire blueprint v1 (`docs/task87-promotion-belief-revision-eval-criteria-blueprint.md`) at the post-Gemini external review panel for holistic structural review before code is written. Mirrors the v1-review pattern that produced Task #74 / #75 / #76 / #83/#84's v2 quality jump.

**Dispatched:** 2026-05-22 (to be fired by Joseph)
**Target panel:** Codex + Deepseek + Qwen (per `docs/external-review-panel.md`)
**Response files (one per reviewer):**
- `docs/task87-blueprint-v1-review-codex.md`
- `docs/task87-blueprint-v1-review-deepseek.md`
- `docs/task87-blueprint-v1-review-qwen.md`

---

## ─── Prompt body ───

You are reviewing **v1 of the predeclared eval criteria blueprint** for Task #87 in the Obsidian-KDB project. The blueprint is at `docs/task87-promotion-belief-revision-eval-criteria-blueprint.md`. It predeclares the criteria that will be used to evaluate the Task #83 (Hypothesis Promotion Contract) + Task #84 (Belief Revision) implementation before any code is written — mirroring the predeclared-eval pattern from Task #75.

This is the **holistic v1 review** — your chance to stress-test the criteria as a coherent whole. The blueprint isn't ratifying eval *thresholds* (those tune later); it's ratifying *what gets measured*, *what pre-state + input + post-state shape applies*, and *what invariants must hold*. Stress-test that shape.

### Project context (brief)

Task #87 is the eval-criteria counterpart to Task #83/#84, which is operationalized in `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (eight ratified decisions D-83/84-1 through D-83/84-8). Together they form one architectural unit: #83/#84 defines the **operations**; #87 defines **how we judge whether those operations work**.

**Critical framing adaptation.** Task #75 is *retrieval-eval* — "did the operation return the right answer to a query?" Task #87 is **mutation-eval** — "did the operation make the right state change to the graph?" The blueprint's §2 Glossary makes this explicit. The shape of a test case is:

> *Pre-state (graph fixture) + Input (candidate envelope / query) → Expected post-state (new/upgraded/unchanged Claim space) + Invariants preserved.*

This is integration-test-shaped, not unit-test-shaped. Reviewers from the #75 round should consciously re-frame.

### What to review

Read the full blueprint end-to-end. Then stress-test along these axes:

1. **Mutation-eval shape correctness.** Does the pre-state + input → post-state + invariants shape (§2, §4) actually capture what we need to measure for #83/#84? Is anything about graph-mutation eval still being retrieval-eval-shaped under the hood? (E.g., are any P-On-N or F-On-N criteria really "did the read return the right thing?" rather than "did the write produce the right state?")

2. **Operations roster (§3).** The blueprint compresses to 3 ops:
   - **O1** Promotion pipeline (candidate → Claim space mutation, the main #83 contract)
   - **O2** Upgrade-from-LINKS_TO (D-83/84-7, retroactive promotion of legacy edges)
   - **O3** Belief-sensitive read (the consumer-side observable behavior change)
   
   Is this the right cut? Specifically: should there be a 4th op for **demotion / retraction** (Claim → retracted state, dependent edges cleanup)? Or is that subsumed under O1 by treating retraction-candidates as a candidate envelope variant? Either answer is defensible — flag if you think the omission is structurally wrong.

3. **Per-op predeclared criteria (§4).** Each op has Pass / Fail / Gate criteria indexed P-O*N* / F-O*N* / G-O*N*. Stress-test:
   - **Coverage.** Are there observable behaviors the criteria don't cover? Anything that could pass all listed P-On-N criteria and still be wrong?
   - **Falsifiability.** Each F-On-N criterion should be falsifiable by a single failing test case. Are any F-On-N criteria vague enough that "fail" is judgment-dependent?
   - **Pre-state / post-state cleanliness.** The shape requires both states be machine-checkable. Are any criteria leaning on human inspection or LLM-judgment in disguise?

4. **Invariants reference (§5).** The blueprint references #83/#84 §6 invariants (Claim-Claim acyclicity, retracted-claim non-revival, EVIDENCES-source existence, etc.) instead of duplicating. Is the pointer sufficient? Should any invariants be *additionally* called out as eval-critical (i.e., "this is a non-negotiable invariant — fail the op if violated")?

5. **Hedge-watch rules (§6, HW-1..HW-7).** These are shaped-threshold criteria that turn into Pass/Fail later when #87.1 lands curated probe sets. Are HW-1..HW-7 covering the right hedges? In particular: are the **hedges from the Round 6 ontology-purpose discussion** (per `docs/what-is-the-ontology-for.md` §9.4.7) reflected? Reminder — the three Round 6 hedges were:
   - **HW-a:** Hypothesis Promotion gate becomes a productivity bottleneck (latency/throughput watch)
   - **HW-b:** Belief Revision audit-trail grows unwieldy (graph-size growth watch)
   - **HW-c:** Predicate-class taxonomy fragments under real corpus stress (canonicalization watch)
   
   Map them against HW-1..HW-7 and flag misses or mis-shapings.

6. **Probe-set framework (§7).** Curation is deferred to #87.1 (sub-task) — but the framework here predeclares coverage requirements. Are the coverage axes (per §7.1) sufficient? Is any axis missing that would let a probe set "look complete" while leaving a structural gap untested?

7. **Open questions (§8, OQ-1..OQ-5).** Same standard as #83/#84 v1 review: flag any OQ you think is actually *structural* and should resolve before v1 declares done (vs eval-tuning that can wait for implementation).

### Out of scope for this review

- **Specific threshold values.** "Latency target should be 200ms not 500ms" — tuning, not contract. The blueprint deliberately predeclares *what* to measure, not *what the cutoff is*.
- **Probe-set content.** #87.1 is filed as a separate sub-task for curating ~10–15 scenarios. This review is on the framework that probe-set will populate, not on specific scenarios.
- **Implementation form.** "Use pytest with parametrize" or "build a fixture factory" — that's Phase 3 work. The blueprint specifies contracts and shapes, not implementations.
- **Re-litigating ratified #83/#84 decisions.** D-83/84-1..-8 are settled. If you find a #83/#84 issue while reading #87, file it as a forward-pointer OQ rather than re-opening the decision.

### Output format

Standard review-prompt format. Suggested structure:

1. **Convergence** — what holds together cleanly across the eval framework (don't dwell; just note)
2. **Findings** — concrete issues, ambiguities, contradictions, missed considerations
3. **Recommendations** — proposed amendments to specific sections / per-op criteria / HW rules, prefixed `**Recommendation:**` or `**Proposal:**`
4. **Open questions** — additional questions raised but not resolvable in review

**Length:** under 2500 words. Cite specific section anchors (e.g., "§4 P-O1-3", "HW-5") where possible. Quote the blueprint with `> …` blockquotes where you're raising an issue with specific wording.

### The blueprint to review

Attached: `docs/task87-promotion-belief-revision-eval-criteria-blueprint.md` (full file).

For project context: see also
- `docs/task83-84-promotion-contract-belief-revision-blueprint.md` (the operations being evaluated; §6 holds the invariants this blueprint references)
- `docs/what-is-the-ontology-for.md` §9.4.7 (Round 6 hedges that informed HW rules)
- `docs/external-review-panel.md` (reviewer panel composition)
- `docs/CODEBASE_OVERVIEW.md` (architecture)
- Optional precedent: `docs/task75-predeclared-eval-criteria-blueprint.md` (the retrieval-eval pattern this one adapts — reading it side-by-side may help you see what's intentionally different here).
