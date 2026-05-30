# Task #89 NW-7 v0.1 Source Type Controlled Vocabulary Review — Grok

**Reviewer:** Grok Build (CLI / code-grounded panel member)  
**Date:** 2026-05-26  
**Artifact reviewed:** `docs/task89-nw7-source-type-list-v0.1.md` (20-entry flat controlled vocabulary)  
**Context consulted:** Task #89 v0.2.1 enrichment blueprint (esp. §2.1, §9, §10.4), NW-4 v0.4 (sibling precedent), CODEBASE_OVERVIEW.md (Task #89 status), TASKS.md, existing GraphDB schema + ingestor usage of `source_type`, external-review-panel.md discipline.

---

## 1. Convergence

The v0.1 draft is structurally sound and correctly mirrors the ratified NW-4 v0.4 posture:

- Flat list (D-NW7-1 ≡ D-NW4-1).
- Explicit no pre-declaration of cross-cuts or edges in config scopes (D-NW7-2 ≡ D-NW4-5, reinforced by [[feedback_no_edge_predeclaration_no_hints]]).
- 4-field config schema (D-NW7-3) owned by Pass-1.
- Catch-all + telemetry discipline (D-NW7-5).
- Boundary rules correctly placed in §3 (disambiguation logic) rather than scope text.

Framework decisions (D-NW7-1..5) are well-articulated and justified against the project's "concrete-first, no imaginary risk" principles. The 20-entry count represents a clean refinement of the §9.1 placeholder (4 additions, 1 rename, 1 principled drop). No domain-axis coupling appears in any scope. The `transcript-X` family rule (D-NW7-4, recording medium wins) is explicit and testable.

This is production-ready vocabulary ratification material once the minor boundary stresses below are addressed.

## 2. Findings

**Finding F-1 (medium load-bearing): `blog` ↔ `post` venue axis is workable but the boundary description in §3.1 could be tightened for LLM consistency.**  
> "blog = own publication; post = community / forum / aggregator."

A Substack newsletter on the author's branded subdomain is correctly `blog`. A long-form post on the same author's personal site that is *not* framed as the "newsletter" is arguably still `blog`. The current wording leans on "own publication" vs "community," which is good, but the LLM may over-apply venue when a high-signal personal essay appears on a forum. This is the same class of judgment as NW-4's `value-investing` ↔ `personal-finance` (vertical) and will be stress-tested in Pass-1 prompt examples (correct place for examples).

**Finding F-2 (low-medium load-bearing): `transcript-written` case is not fully covered by the current four `transcript-*` entries or §3.3.**  
The prompt's axis 5 example (journalist's written Q&A submission) has no recording medium. Current rule ("format-driven... applies whether... written-Q&A") routes it to `transcript-interview`, which is probably the least-bad home. However, §3.3's decision tree does not explicitly call out the "no recording medium, pure text Q&A" case. This is a minor completeness gap rather than a flaw; adding a fifth `transcript-written` entry would increase granularity without clear empirical justification today (aligns with NW-4's "only when ≥2 sources organize it that way" spirit). Recommend explicit one-line addition to §3.3: "Pure text Q&A with no spoken origin or recording → `transcript-interview` (format dominates)."

**Observation O-1 (minor):** `social-thread` placement in the primary-document cluster (§2.3) is defensible on "platform-hosted original" grounds but sits awkwardly next to `speech` and `email`. Long-form threads are authored prose with threading mechanics. If the user's ingestion patterns later show many high-signal threads, query-layer clustering may treat them more like written-prose than primary documents. This is telemetry-watch territory (already covered by OQ-NW7-2 / OQ-NW7-4) and does not require a change now.

**Observation O-2 (minor, nice-to-have):** The `other` usage instruction ("Use ONLY when you can articulate in one sentence why none of #1-19 applies") is good. A slightly stronger phrasing ("must name the specific missing publication form/shape") would make it even harder for the LLM to lazily emit `other`. This is a prompt-refinement item, not a vocabulary change.

No findings rise to the level of requiring structural rework of D-NW7-1..5 or the 20-list itself. All 15 review axes in the prompt were stress-tested; the design holds.

## 3. Recommendations

**Recommendation R-1:** Add one clarifying sentence to §3.3 (after the current bullet on "If transcript provenance is ambiguous"):

> "Pure written Q&A (email interview, document-based submission, no audio/video origin) defaults to `transcript-interview` on rhetorical form."

This closes the written-interview gap without adding a new enum value.

**Proposal P-1 (non-blocking):** In the eventual Pass-1 prompt that consumes this vocabulary, include 2–3 concrete counter-examples for the `blog`/`post`/`article` cluster drawn from the user's actual vault (not generic "e.g." text). The vocab doc correctly avoids putting examples in scopes; the prompt is the right surface.

No other changes recommended to the list, framework decisions, or §5 config schema. The single alias (`transcript-youtube`) is correctly recorded. Scope text across all 20 entries respects the no-hints / no-cross-cut discipline.

## 4. Concrete classification probes

1. **Substack newsletter (author's own branded domain, 2,400 words, investment thesis with data tables)**  
   → `blog` (own publication, per §3.1 and §2.1 example).

2. **Long Twitter/X thread (12 tweets, detailed critique of a specific company's 10-K, substantive, no images)**  
   → `social-thread` (threaded structure on social platform with long-form content, §2.3 / §3.8).

3. **Auto-generated YouTube transcript of a 45-minute conference keynote (one speaker, slides visible in video, Q&A at end is minor)**  
   → `transcript-video` (recording medium wins per D-NW7-4; not primarily interview or lecture format).

4. **Scanned PDF of a 1997 shareholder letter (Warren Buffett style) with light user highlighting and one marginal note**  
   → `letter` (public, addressed, curated correspondence; the marginalia does not turn it into a summary or chapter).

5. **Email export of a 6-message back-and-forth with a domain expert on a narrow technical point (user forwarded the thread to self for archiving)**  
   → `email` (informal, individual, private distribution-list style, per §3.5 and §2.3).

6. **Wikipedia article on "Knowledge graph" with heavy citation section + one paragraph of user's own synthesis appended at the bottom**  
   → `wiki` (core content is encyclopedic register; the appended synthesis is small enough not to flip the classification to `article` or `book-summary`).

All six classify cleanly under v0.1. No probe landed in `other`.

## 5. Open questions

All five OQs already surfaced in the v0.1 document (OQ-NW7-1 through OQ-NW7-5) are appropriate and correctly scoped to post-deployment telemetry or deliberate deferral. No new OQs surfaced during this review.

The authority-axis idea (OQ-NW7-5) remains correctly deferred; introducing it now would violate the concrete-first + no-pre-declaration posture that has served the project well through NW-4.

---

**Verdict:** v0.1 is ready for Joseph's internal review + external panel dispatch (Codex + Qwen CLI + deepcode CLI + agy + this Grok review). Minor boundary clarifications (F-2 / R-1) are recommended but non-blocking. The design is consistent with every load-bearing precedent in the ingestion pipeline work.

**Word count:** ~1,180 (well under 2,500). All citations are to § anchors or decision IDs in the reviewed document or its direct parents.

**End of Grok review**