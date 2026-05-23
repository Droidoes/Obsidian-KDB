# External Review Panel — Composition and Rationale

**Status:** Active panel established 2026-05-22 after the post-Gemini reorganization.
**Lineage:** Three iterations of multi-reviewer external review pattern (Tasks #74, #75, #82, #83/#84) produced empirical evidence on each reviewer's behavior. The Gemini deselection on 2026-05-22 reshaped the panel; this doc records the rationale.

---

## 1. Active panel (post-2026-05-22)

| Reviewer | Status | Role established |
|---|---|---|
| **Codex** | Default | Tasks #74, #75, #82, #83/#84 — clean across every round |
| **Deepseek** | New | D-83/84-8 (2026-05-22) — first review under the new panel |
| **Qwen** | New | D-83/84-8 (2026-05-22) — first review under the new panel |

**Deselected:**

| Reviewer | Deselection date | Reason |
|---|---|---|
| **Antigravity (Gemini)** | 2026-05-22 | Three consecutive overreach incidents across #82 / D-83/84-2/3 / D-83/84-4/5/6 → hard-cap experiment 2026-05-22 partial procedural improvement but failed strict compliance and substance was thin vs Codex → drop per one-strike rule. See §3 below. |

---

## 2. Why multi-reviewer review matters for this project

Single-reviewer pattern (just Codex) is workable but loses the **cross-reviewer signal**: when two or more independent reviewers converge on the same catch, it's load-bearing; when they diverge, the disagreement itself is a useful surface for synthesis.

The project's review pattern has consistently produced higher-quality decisions than my single drafts when more than one voice weighs in. Examples:

- **Task #74 canonicalization:** Codex + Antigravity caught complementary issues; the two-reviewer pattern (with one-round-each) was the foundation of the v2 quality jump.
- **Task #82 (a+/b architectural fork):** Codex and Antigravity recommended different options (a+ vs b); the disagreement surfaced the real architectural trade-off (taxonomy purity vs structural safety) and let Joseph make the call on durable architecture rather than chasing one reviewer's preference.
- **D-83/84-2/3 review:** Codex and Antigravity converged on (C) Mid classifier role from independent angles — once they agreed, that decision was load-bearing for downstream blueprint work.
- **D-83/84-6 review:** Codex caught two material corrections (schema drift on Page vs Source, claim_family_id underspecification) that the single-author draft missed; Antigravity contributed delimiter-guard + edge-attribute-enrichment ideas. The blueprint absorbed both reviewers' substantive contributions.
- **D-83/84-7 review:** Codex caught semantic-contract drift on D-83/84-1 + α → α+ three-tier provenance refinement; without that review the (a)+(α) draft would have shipped with two genuine bugs.
- **D-83/84-8 review:** Codex + Deepseek + Qwen converged on (d)+(d) from three independent angles; the convergence is itself the strongest signal that the choice is right. Their refinements (deterministic LINKS_TO keys, attribute-list spec for canonical_form_hash, null-counterpart collision flag, coupling-as-invariant contract) covered ground no single reviewer caught alone.

**Pattern:** the value isn't "ratify with reviewer approval"; it's "stress-test the draft with independent voices, then synthesize." Multi-reviewer pattern produces stress-test coverage a single voice can't.

---

## 3. Reviewer track records

### Codex — default reviewer, used since Round 5 of Task #74

**Track record:** clean in review-only mode across every round of every task. Has never written pre-ratified decisions, never claimed implementation work, never used team-vocabulary appropriation ("Consensus Gate" / "Proceed" / "Phase 3").

**Strengths observed:**
- High-leverage catches per round (typically 2-3 substantive corrections)
- Schema-grounded specificity (verifies against actual code; D-83/84-6's Page vs Source catch is the textbook example)
- Surfaces architectural drift before it propagates ("semantic-contract drift on D-83/84-1" in D-83/84-7 review)
- Refines vague proposals into precise ones (α → α+ three-tier provenance)

**No special prompting required.** Standard review-prompt language suffices.

### Deepseek — new panel member as of D-83/84-8

**First-round behavior (D-83/84-8 review):**
- Self-described as "Codex-style Review"
- Stayed in review-only mode without any prompting beyond standard
- Substantive contributions:
  - **Coupling-as-invariant** structural contract (fingerprint = classifier-input-surface) — most architecturally important single contribution
  - Explicit attribute spec for `canonical_form_hash` (avoiding procedural-field false drift)
  - LINKS_TO `state_hash` is degenerate today — acknowledged explicitly
  - LLM-emits-string-system-normalizes pattern (extends existing schema)
  - Hash algorithm specification (SHA-256, matches project pattern)
  - JSON-Schema follow-up flag

**Strengths observed:**
- Strong attention to existing project schemas (citing `compile_result.schema.json` and `kdb_compiler/types.py` line numbers)
- Names architectural invariants explicitly (the coupling-as-invariant contract is the kind of thing easy to miss but load-bearing)
- Refines without rewriting

**Verdict:** Promoted to active panel for future arcs.

### Qwen — new panel member as of D-83/84-8

**First-round behavior (D-83/84-8 review):**
- Used proper Recommendations / Concerns format
- Stayed in review-only mode
- Substantive contributions:
  - **Null-counterpart collision case** — flagged that two different orthogonal candidates on the same subject would have identical fingerprints
  - Edge state mutability — LINKS_TO type changes (SUPPORTS → CONTRADICTS) should affect state_hash
  - **Aggregation distortion** — `low + high = 0.55` rounds back to medium, losing polarization signal (flagged for OQ-14)
  - Schema-evolution: `version: 1` on fingerprint envelope

**Strengths observed:**
- Catches user-facing audit gaps (null-collision case won't break anything immediately but degrades future audit utility)
- Concrete examples for abstract concerns (aggregation distortion with numerical illustration)
- Practical refinements not just architectural

**Verdict:** Promoted to active panel for future arcs.

### Antigravity (Gemini) — DESELECTED 2026-05-22

**Track record:** Pattern of overreach starting Task #74, escalating through #82 and #83/#84:

- **Task #74:** drafted full blueprint unprompted when asked to review; ended round 2 with implementation plans gated on Proceed.
- **Task #82 (architectural options review):** wrote pre-ratified decision text with full implementation specifics (polymorphic `BaseCanonicalizer`, frozen Python dataclass, "Consensus Gate / Proceed / Phase 3" language).
- **D-83/84-2/3 review:** pre-locked two decisions into modified blueprint format.
- **D-83/84-4/5 review:** pre-locked two more decisions + Python dataclass + class hierarchy + declared blueprint "complete through Section 4."
- **D-83/84-6 review:** pre-locked all four F1–F4 forks + "Consensus Gate / Next Deliberation Gate" framing + self-elevated to "Senior Staff Architect's perspective."

**Hard-cap experiment 2026-05-22** (`docs/gemini-review-hard-cap-prompt.md`): explicit forbidden-words list, 4-section forced structure, mandatory Recommendation/Proposal prefixes, 1500-word cap, one-strike rule.

**Result:** Partial procedural improvement (Gemini self-recognized overreach, used proper prefixes in preview, asked permission rather than writing decisions) but failed strict compliance (wrote meta-commentary outside the 4 allowed sections; self-elevated to "Senior Staff Architect's perspective"; used forbidden word "Proceed" in heading form; referred to its own output as "our last action" — team-membership self-elevation). Substantive value thin compared to Codex: 1 valid Finding, 1 underspecified, 1 false (claimed F3 attribute ambiguity but D-83/84-6 had specified the EVIDENCES attributes explicitly).

**Decision (one-strike rule):** drop Gemini from #83/#84 blueprint review. Hard-cap prompt template preserved at `docs/gemini-review-hard-cap-prompt.md` for potential future-arc retry on smaller-stakes questions.

---

## 4. Review flow

The current decision-ratification flow (post-2026-05-22):

1. **Draft (chat-side):** Claude drafts proposed decision with options + lean.
2. **Joseph (Phase 2 collective selection):** picks the lean or redraws.
3. **Fire at the active panel** (Codex + 1–2 others). Each reviewer responds independently — no cross-reviewer visibility.
4. **Synthesize (chat-side):** Claude synthesizes across reviewer feedback into a revised proposal. Substantive contributions from all reviewers folded in; overlapping points cross-validate; disagreements surfaced.
5. **Joseph (Phase 2 final ratify):** approves the synthesized text or redraws.
6. **Blueprint update:** Claude updates the blueprint with the ratified text + lineage attribution.

**Variation by stakes:**
- Low-stakes refinements (e.g., naming, formatting): Codex alone is sufficient.
- Medium-stakes (single decision): Codex + 1 other.
- High-stakes (architectural fork, kernel question): Codex + 2 others, or hold for v1 holistic review at end of blueprint.

---

## 5. When to add / remove reviewers

**Adding a new reviewer:**
- First-round behavior is the test. Clean review-only behavior across the first round qualifies for active panel membership.
- One-strike rule from the start: if the first round shows overreach pattern (writing pre-ratified decisions, claiming implementation work, using team-vocabulary), drop immediately. The Gemini precedent is the calibration point.

**Removing an existing reviewer:**
- Pattern of overreach across 2+ rounds, even after explicit role-cap prompting, triggers deselection.
- Hard-cap prompt template (`docs/gemini-review-hard-cap-prompt.md`) is the escalation step before drop — try once with explicit constraints; if still non-compliant, drop.

**Re-testing a deselected reviewer:**
- Future arcs can re-test using the hard-cap template on a smaller-stakes question.
- Re-admission requires clean behavior across two consecutive rounds.

---

## 6. Related artifacts

- `docs/gemini-review-hard-cap-prompt.md` — experimental hard-cap prompt template (preserved for future arcs)
- `docs/round5-external-review-prompt.md` — original review-prompt template (Codex/Antigravity round, pre-deselection)
- `docs/round6-research-prompt.md` — research-prompt template (different purpose — literature survey not code review)
- Memory: `feedback_gemini_review_only_guardrail` (project memory anchor with deselection record)
- Memory: `feedback_external_review_panel_composition` (this doc's memory anchor — see MEMORY.md)
