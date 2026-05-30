# Session Handoff — 2026-05-23

A continuous session arc spanning 2026-05-22 evening → 2026-05-23 early morning.
**17 commits** since the prior handoff (`120496e`), all documentation, all in
service of one objective: **predeclared eval criteria for #83/#84 — ratified
end-to-end** (#83/#84 v2 → #87 v2 → #87.1 v1). Branch is **17 commits ahead
of `origin/main`**. Push gate held with Joseph.

## What happened

Three multi-iteration objectives closed back-to-back, all driven by the
external-review panel (Codex + Deepseek + Qwen — post-Gemini deselection
per `feedback_gemini_review_only_guardrail`):

### Phase A — #83/#84 v2 (Hypothesis Promotion + Belief Revision)

Started from the v1 hard-cap prompt experiment with Gemini (last attempt to
honor the review-only guardrail; failed strict compliance — formally
deselected). Codex + Deepseek + Qwen v1 reviews landed; v2 synthesized in
one pass (`01c6373`). D-83/84-8 (Doxastic Fingerprint) ratified mid-session
(`eddd01d`). 12 ratified decisions D-83/84-1..12.

### Phase B — #87 v1 → v2 (predeclared eval criteria)

Filed #87 to TASKS.md (`59b815d`); drafted v1 (`4d87ded`) mirroring Task #75's
spine but adapted to mutation-eval (vs Task #75's retrieval-eval). v1 fired
at the 3-reviewer panel; 16 findings landed. v2 synthesized (`0d68688`):
O3 reframed as hybrid op; HW-1..HW-11; `eval_config` block on probe template;
new P-O1-7/8 + F-O1-5 + F-O3-4; 13 new OQs registered (OQ-6..OQ-18). Joseph
ratified directly without v2 review fire ("im good with v2") — 5-reason
analysis recommended ratify-not-re-fire (pattern precedent, high-fidelity
reviewer application, small novel content, downstream forcing function,
v3-spiral risk).

### Phase C — #87.1 spike → expand → spot-check → v1 ratified

The largest single phase by volume. Used a **spike-then-expand workflow**:

1. **Spike** — 4 illustrative YAML scenarios stress-test the v2 §7.2 template
   (`8c514c7`). Surfaced 7 template gaps + 6 new OQs (OQ-S1..S6) + 10 decision
   gates (D-87.1-1..10) with leans baked in.

2. **§6 ratification** (`ea47740`) — Joseph ratified all 10 ("ratify all 10").
   **D-87.1-5's verify-hedge fired** — proposed `counterpart_status:
   implied_by_links_to` is **not** in #83/#84's canonical enum
   (`no_counterpart` | `candidate_counterpart_found` | `orthogonal`). O2
   dispatch is derived from three fields jointly. S3 input corrected;
   OQ-S7 registered (explicit vs derived dispatch). **Catch was load-bearing**
   — would have propagated across 5+ expansion scenarios.

3. **Expansion in 4 batches** — Batch 1 action-table cells `07974d7` (S5–S9);
   Batch 2 upgrade tiers `b843122` (S10 Tier-2, S11 Tier-3); Batch 3 drift
   cells `2b3d481` (S12–S14 with `auto_promote_with_note` / `investigate` /
   `human_review` dispositions); Batch 4 cross-axis `7cede1e` (S15
   supersedes-idempotency, S16 between-runs canonicalization, S17/S18
   retracted-counterpart × 2, S19 sequential multi-candidate with new
   YAML shape).

4. **Spot-check pass** (`34b06c5`) — surfaced **F-O3-3 (retracted-Claim leak)**
   unexercised in S4; added **S20** to close. Surfaced **F-O1-1
   (classification non-determinism)** as structurally non-scenario-exercisable;
   registered as **OQ-S8** (lean = defer to classifier-test suite). All 32
   other P/F criteria exercised. Slug delimiter guard verified across 20
   scenarios. S1–S4 retroactively patched to add `op_under_test:` field.

5. **v1 ratified** (`4f4335f`) — Joseph: "good with v1". Milestone Changelog
   entry added to `CODEBASE_OVERVIEW.md` per `feedback_milestone_closure_rule`.

## Commits landed this session

| Commit | Title | Phase |
|---|---|---|
| `aaab6ae` | `docs: #83/#84 blueprint v1 through D-83/84-6 + Gemini hard-cap prompt` | A |
| `eddd01d` | `docs: ratify D-83/84-8 + post-Gemini reviewer panel docs` | A |
| `01c6373` | `docs: #83/#84 blueprint v2 — v1 holistic review folded (Codex+Deepseek+Qwen)` | A |
| `59b815d` | `docs: TASKS — file #87 predeclared eval criteria for #83/#84` | B |
| `4d87ded` | `docs: #87 blueprint v1 + ledger update + #87.1 sub-task filing` | B |
| `0d68688` | `docs: #87 blueprint v2 — v1 holistic review folded (Codex+Deepseek+Qwen)` | B |
| `8c514c7` | `docs: #87.1 spike-phase blueprint — 4 scenarios + 10 decision gates` | C |
| `ea47740` | `docs: #87.1 §6 ratified — D-87.1-5 vocabulary corrected to canonical enum` | C |
| `07974d7` | `docs: #87.1 batch 1 — 5 action-table-cell scenarios (S5–S9)` | C |
| `b843122` | `docs: #87.1 batch 2 — Tier-2 + Tier-3 upgrade scenarios (S10, S11)` | C |
| `2b3d481` | `docs: #87.1 batch 3 — 3 drift-cell scenarios (S12, S13, S14)` | C |
| `7cede1e` | `docs: #87.1 batch 4 — 5 cross-axis scenarios (S15-S19); expansion complete` | C |
| `34b06c5` | `docs: #87.1 spot-check pass — S20 closes F-O3-3 gap; OQ-S8 + uniform shape` | C |
| `38c3a71` | `docs: TASKS — #87.1 spike + expansion + spot-check complete; v1 awaiting ratification` | C |
| `4f4335f` | `docs: #87 + #87.1 ratified — milestone changelog updated` | C |

(Plus 2 v1-review-response files landed externally from the reviewer panel and were referenced into the blueprint as `docs/task87-blueprint-v1-review-{codex,deepseek,qwen}.md`.)

## Documents created or substantively edited

| Doc | Purpose | State |
|---|---|---|
| `docs/task83-84-promotion-contract-belief-revision-blueprint.md` | #83/#84 architectural blueprint | v2 ratified; 12 ratified decisions D-83/84-1..12. |
| `docs/task87-promotion-belief-revision-eval-criteria-blueprint.md` | #87 predeclared eval criteria | v2 ratified; ~500 lines; 3 ops (O1/O2/O3), P-On-N / F-On-N criteria, HW-1..HW-11, 13 OQs OQ-6..OQ-18. |
| `docs/task87.1-probe-set-curation-blueprint.md` | #87.1 probe set | v1 ratified; ~3000 lines; **20 YAML scenarios** across 7 §7.1 coverage axes; 8 OQs OQ-S1..S8; 10 ratified decision gates D-87.1-1..10. |
| `docs/CODEBASE_OVERVIEW.md` | North Star architecture spec | Milestone Changelog entry added 2026-05-23 — predeclared eval criteria + probe set ratified for #83/#84. |
| `docs/TASKS.md` | Project task ledger | #87 marked `v1 ratified`; #87.1 sub-task marked complete with full implementation history. |

## New project patterns surfaced

1. **Mutation-eval discipline** (vs Task #75's retrieval-eval). #75 asks "did the
   op return the right thing?" — #87 asks "did the op make the right state
   change?" via `pre-state + input → expected post-state + invariants preserved`.
   Different shapes; complementary purposes. Both predeclared, both ship-before-
   implementation per Task #75 precedent. Now established as project pattern for
   any state-changing op.

2. **Spike-then-expand methodology for scenario corpora**. For probe-set or
   scenario-corpus curation work: draft 3–4 spike scenarios stress-testing the
   template shape, surface numbered decision gates with leans baked in, ratify
   shape before scaling, then expand mechanically. Spot-check audits per-criterion
   coverage. Saved as memory `feedback_spike_then_expand_methodology`. Validated
   on #87.1 — D-87.1-5's vocabulary catch alone would have propagated across
   5+ expansion scenarios without the gate.

3. **Per-criterion coverage audit** (`grep -oE "(P|F)-O[0-9]+-[0-9]+" | sort |
   uniq -c`) — the standard spot-check pattern. Reveals structural gaps:
   on #87.1 it surfaced F-O3-3 (added inline as S20) and F-O1-1 (declared
   non-scenario-exercisable; registered as OQ-S8).

## Task status

| # | State | Notes |
|---|---|---|
| 83 / 84 | ✅ v2 ratified | Hypothesis Promotion + Belief Revision; 12 ratified decisions. |
| 87 | ✅ v2 ratified | Predeclared eval criteria for #83/#84; 3 ops, P/F criteria, HW-1..HW-11. |
| **87.1** | **✅ v1 ratified** | **20 probe scenarios across 7 coverage axes; 8 OQs; 10 ratified gates.** |
| #83/#84 impl | 🟢 **unblocked** | All preconditions satisfied; next stack candidate. |

## Test surface

No tests added today — entire session was documentation. Existing test surface
unchanged from prior handoff (~996 passed total).

Probe scenarios in #87.1 are **specifications**, not executable tests yet. They
materialize as runnable YAML at `tests/eval/promotion/scenarios/o{1,2,3}/*.yaml`
at #83/#84 implementation start per OQ-S6 lean (one file per scenario).

## Architectural shifts worth surfacing for next session

1. **The predeclared-eval-criteria milestone is now visible.** Milestone
   Changelog entry 2026-05-23 captures "Predeclared eval criteria + probe set
   ratified for #83/#84" alongside the existing JOURNEY-era entries. Future
   sessions and contributors see one-line evidence that the eval contract
   exists and is ratified.

2. **#83/#84 implementation is unblocked.** The probe set is a mechanical eval
   the implementer can run as soon as O1/O2/O3 land. Eight scenarios carry
   `confidence: <placeholder-pending-OQ-26>` markers that resolve in-place
   when OQ-26 (confidence aggregation formula) closes; this doesn't block
   structural runs.

3. **OQ list grown but contained.** 8 new OQs (OQ-S1..S8) on #87.1 are
   implementation-detail follow-ups — pre-state inheritance shape (S1), runner
   matching mode (S2), runtime-field marker semantics (S3), O3 read-mode
   placement (S4), positive-vs-adversarial annotation (S5), scenario storage
   layout (S6), explicit-vs-derived dispatch (S7), classifier-determinism
   scoping (S8). None block #83/#84 implementation start; all have leans
   baked in.

4. **External review panel posture stable.** Codex + Deepseek + Qwen worked
   well on three back-to-back blueprint reviews. Gemini formally deselected
   for blueprint reviews (one-strike rule per `feedback_gemini_review_only_guardrail`).
   Hard-cap prompt preserved for future-arc retry if needed.

## What's queued (next session)

| Candidate | Type | Status |
|---|---|---|
| **#83/#84 implementation kickoff** | Code | All preconditions satisfied; probe set ready to run |
| OQ-26 (confidence aggregation formula) | Upstream decision | Soft-blocks 8 #87.1 scenarios on exact confidence values; resolvable in-place |
| OQ-S7 (explicit vs derived dispatch_path) | Implementation-shape | Mirrors dispatcher if #83/#84 introduces explicit field |
| OQ-S8 (F-O1-1 classifier-test suite) | Scoping | Defer to #83/#84 classifier-determinism layer |
| OQ-18 (retracted-counterpart upstream rule) | Cross-task | S17/S18 encode current lean; amend in-place if #83/#84 picks differently |
| Push to `origin/main` | Ops | 17 commits accumulated; push gate held |

Joseph's call on which thread to pick up first.
