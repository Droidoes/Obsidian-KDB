# Task #89 NW-7 v0.1 — External Review Fire-Prompt

**Purpose:** Fire the v0.1 source_type controlled vocabulary draft (`docs/task89-nw7-source-type-list-v0.1.md`) at the same 5-reviewer all-CLI panel that reviewed Task #89 v0.1 (5/5 clean). This is the precondition for Task #89 (Component #1 Enrichment) implementation plan-lock (Joseph 2026-05-26).

**Dispatched:** 2026-05-26 (to be fired by Joseph)
**Target panel (all-CLI, code-grounded):**
- **Codex** — CLI (panel incumbent)
- **Qwen CLI / qwen3.7-max** — CLI (panel incumbent; clean on Task #89 v0.1 review)
- **Grok Build** — CLI (panel incumbent; clean on Task #89 v0.1 review)
- **deepcode CLI / Deepseek** — CLI (panel incumbent; clean on Task #89 v0.1 review)
- **agy / gemini-3.5-flash-high** — CLI (2-for-2 successful re-trial during Task #89 v0.1 + round-2; per [[feedback_gemini_review_only_guardrail]])

**Response files (one per reviewer):**
- `docs/task89-nw7-v0.1-review-codex.md`
- `docs/task89-nw7-v0.1-review-qwen.md`
- `docs/task89-nw7-v0.1-review-grok.md`
- `docs/task89-nw7-v0.1-review-deepseek.md`
- `docs/task89-nw7-v0.1-review-gemini.md`

---

## ─── Prompt body ───

You are reviewing **NW-7 v0.1 — the source_type controlled vocabulary** for the Obsidian-KDB project (`docs/task89-nw7-source-type-list-v0.1.md`). It is a **20-entry flat controlled vocabulary** that the Pass-1 enrichment LLM in the project's ingestion pipeline will classify every ingested source against, sibling to NW-4 (`domain` vocabulary, ratified at v0.4 on 2026-05-25).

This is a **substantive-content review** (does the list capture the user's empirical source intake forms?) AND a **framework review** (are the upstream structural decisions defensible?). Both dimensions matter — please address each.

### 1. REPO-MODIFICATION GUARDRAIL (CRITICAL — read first)

Create EXACTLY ONE file in this CLI session. Your output file path depends on your reviewer identity:

- Codex:        `docs/task89-nw7-v0.1-review-codex.md`
- Qwen CLI:     `docs/task89-nw7-v0.1-review-qwen.md`
- Grok Build:   `docs/task89-nw7-v0.1-review-grok.md`
- deepcode CLI: `docs/task89-nw7-v0.1-review-deepseek.md`
- agy:          `docs/task89-nw7-v0.1-review-gemini.md`

Do NOT modify, create, or delete any other files in the repository.
Do NOT modify code, schemas, configuration, blueprints, or other docs.
Do NOT propose implementation patches or write code.

Your entire CLI session output must be confined to producing your single review file. Violating this guardrail (e.g., editing other files, committing changes, modifying code) results in de-selection from future review cycles per the one-strike rule (`docs/external-review-panel.md`).

All five reviewers completed the Task #89 v0.1 + round-2 review cycle clean (5/5, agy 2-for-2 on one-strike re-trial). This review is the natural continuation under the same discipline.

### 2. Project context (brief)

**The system.** Obsidian-KDB compiles Joseph's raw markdown sources into a knowledge graph (Kuzu GraphDB). The pipeline has two ends: end A = compile pipeline (mature); end B = ingestion pipeline (Task #88, in design). Pass-1 enrichment is Component #1 of end B; it emits structured frontmatter on each source.

**Where NW-7 fits.** Pass-1 emits `source_type` as one field of the GraphDB-input frontmatter section (Task #89 v0.2.1 §2.1). NW-7 is the controlled-vocabulary list of allowed values. The original Task #89 §9 shipped a 17-entry placeholder pending ratification. NW-7 ratifies that vocabulary so Pass-1 implementation references a stable enum. **This review is the precondition for Pass-1 implementation plan-lock** (Joseph 2026-05-26).

**What `source_type` is for.** It's a **filter axis at query time** (Task #89 §2.1, ★★ tier). Captures the publication-form shape of the raw source — written-prose vs transcript vs primary-document vs vault-meta — independent of substantive `domain`. Together `domain` (NW-4) and `source_type` (NW-7) give the user query-time filters: "show me all `transcript-podcast` content in `domain: value-investing`" or "all `paper` content tagged `ai-ml`".

**Sibling precedent.** NW-7 follows NW-4 v0.4's pattern exactly (`docs/task88-nw4-domain-list-v0.4.md`):
- Flat list, no sub-types (D-NW4-1 / D-NW7-1)
- 4-field config schema: id + display + scope + aliases (D-NW4-4 §7 / D-NW7-3 §5)
- No pre-declared cross-cuts (D-NW4-5 / D-NW7-2)
- Last-resort catch-all entry with telemetry KPI (NW-4 `undecided` / NW-7 `other`)

### 3. Framework decisions to validate (D-NW7-1..5)

The 20-list rests on five upstream design decisions. Reviewers should weigh in on each:

1. **D-NW7-1 — Flat list, no hierarchical sub-types.** Pass-1 picks one from 20. The `transcript-X` family looks hierarchical but is a naming convention only — LLM sees a flat enum. *(Alternative: 2-level form-then-subform hierarchy. Rejected for same reasons as D-NW4-1: hierarchies smuggle structural decisions into the prompt that query layer can synthesize.)*

2. **D-NW7-2 — Cross-cutting relationships not pre-declared.** Config does NOT declare how source_types relate (e.g., "transcripts are spoken-form-originated"). Cross-cuts emerge from query-layer aggregation. *(Sibling rule to D-NW4-5; reinforces [[feedback_no_edge_predeclaration_no_hints]].)*

3. **D-NW7-3 — Config schema = 4 fields.** id + display + scope + aliases. File location: `kdb_compiler/config/source_types.json`. Mirrors NW-4 `domains.json`.

4. **D-NW7-4 — `transcript-X` family: LLM picks most-specific.** Four transcript entries (`transcript-podcast`, `transcript-video`, `transcript-interview`, `transcript-lecture`). On ties between rhetorical mode and recording medium, **recording medium wins** (e.g., interview-format-content recorded on video → `transcript-video`, not `transcript-interview`).

5. **D-NW7-5 — `other` is last-resort + telemetry-monitored.** High `other` rate signals vocabulary needs expansion (OQ-NW7-1; analog to NW-4 `undecided`).

### 4. What to review

Read the full NW-7 v0.1 document end-to-end. Then stress-test along these axes:

1. **20 vs alternative count — is the granularity right?**
   - Too granular: should `blog` + `post` merge? Should the 4 `transcript-X` entries collapse to a single `transcript`?
   - Too coarse: missing entries that the placeholder dropped or this draft missed?
   - Probe: walk the v0.1 §0.1 additions/drops list. Defensible? Anything else add/drop?

2. **`podcast` drop (§0.1).** v0.1 dropped the placeholder's `podcast` entry on the reasoning that without a transcript, the .md file IS show notes (which classifies as `post` or `article`). Defensible? Counter-cases?

3. **`transcript-X` family boundary rule (D-NW7-4 + §3.3).** The "recording medium wins on ties" rule for transcripts may favor signal over intent. Counter-case: an interview format conducted via written-text (e.g., a journalist's written Q&A submission). Should there be a fifth `transcript-written` entry for that? Or is `transcript-interview` the right home regardless of medium?

4. **`blog` ↔ `post` venue-based distinction (§3.1).** Walking the boundary: a Substack newsletter is `blog`; a Reddit comment is `post`; an HN comment is `post`; a personal-domain WordPress = `blog`. Is venue-based the right axis, or is there a sharper one (length? authority? voice?)?

5. **`speech` ↔ `transcript-lecture` distinction (§3.6).** Text-form (prepared speech) vs transcribed-from-delivery. This is the subtlest boundary. Probe cases:
   - Lincoln's Gettysburg Address as text → `speech` ✓
   - Auto-generated YouTube transcript of Lincoln-impersonator delivery → `transcript-lecture` ✓
   - Modern policy address whose written text and delivered version diverge → which?

6. **`wiki` ↔ `article` distinction (§3.7).** Encyclopedic vs editorial. Edge case: a heavily-cited New York Review of Books essay reads encyclopedic in voice but is editorial in publication. Where does it land? Is the boundary stable enough for the LLM to apply consistently?

7. **`social-thread` cluster placement (§2.3).** v0.1 places `social-thread` in the primary-document cluster (closer to speeches than to magazine articles) on the platform-hosted-original reasoning. Defensible? Or is `social-thread` really a written-prose entry?

8. **`book-chapter` ↔ `book-summary` distinction (§3.4).** Verbatim vs distillation. The boundary is clear in concept. Pressure test: a heavily-annotated book-chapter with the user's own commentary woven in — chapter or summary?

9. **Vault-meta cluster (§2.4) `daily-note` + `meeting-notes`.** These default to `force_noise` per D-89-14. Are both warranted, or could one absorb the other? Is there a missing third (e.g., `journal-entry`, `scratchpad`)?

10. **Missing entries probe (analog to NW-4 OQ-NW4-6).** What's missing? Specific candidates to evaluate:
    - `presentation` / `slide-deck` (mentioned in §4 drops; reconsider?)
    - `legal-document` / `contract` (§4 drops; reconsider?)
    - `chat-log` (Slack export, Discord export, ChatGPT conversation export)
    - `bookmarks-page` (curated link collection)
    - `recipe` (§4 drops)
    - `code-snippet` / `gist` (§4 drops)
    - `journal-entry` (distinct from `daily-note`?)

11. **Authority-axis deferral (OQ-NW7-5).** v0.1 deliberately does NOT introduce authority-axis tagging (peer-reviewed > editorial > personal > primary-source > vault-meta) — left for telemetry-driven re-open. Defensible deferral, or should v0.2+ introduce it now (analog to NW-4 D-NW4-6 boundary-axis addition in v0.4)?

12. **`other` operational guardrail (D-NW7-5).** §2.5's `other` says "Use ONLY when you can articulate in one sentence why none of #1-19 applies." Sufficient guardrail, or does this need stronger enforcement (e.g., a hard threshold beyond which Pass-1 fails the call vs returning `other`)?

13. **Scope-text discipline (D-NW7-2 + [[feedback_no_edge_predeclaration_no_hints]]).** Walk each of the 20 scope descriptions in §2.1-2.5. Any that smuggle:
    - Cross-cut hints (e.g., "see also `transcript-podcast`")?
    - "For example" hints in scope (vs in §3 boundary rules where examples are permitted as classification illustration)?
    - Domain-axis coupling ("this source_type usually appears with `domain: X`")?

14. **Aliases completeness (§5).** v0.1 lists one alias: `transcript-video` ← `transcript-youtube`. Are there other renames/migrations needed? (Probe: the placeholder had `transcript-youtube` and entries with `book-chapter`-style hyphens — any that v0.1 should preserve as historical IDs for sources that may already have been hand-tagged?)

15. **NW-4 sibling consistency.** NW-7 should NOT contradict NW-4's structural posture. Cross-check:
    - Same flat-no-hierarchy posture? ✓ (D-NW4-1 / D-NW7-1)
    - Same no-edge-pre-declaration discipline? ✓ (D-NW4-5 / D-NW7-2)
    - Same 4-field config schema? ✓ (NW-4 §7 / NW-7 §5)
    - Same catch-all-with-telemetry pattern? ✓ (`undecided` / `other`)
    - Any structural divergence that's intentional? Should be called out.

### 5. Out of scope for this review

- **Pass-1 prompt wording** — Component #1 implementation; NW-7 only specifies vocabulary content.
- **Pass-1 output schema construction** — Component #1 implementation; NW-7 specifies the enum members.
- **`source_type` interaction with `kdb_signal` / `force_noise`** — Pass-1 design (Task #89 v0.2.1 §4); NW-7 doesn't change that.
- **Re-litigating D-NW4-* decisions** — NW-7 mirrors NW-4's structural posture deliberately; that posture is settled.
- **Re-litigating D-89-* decisions** in Task #89 v0.2.1 — NW-7 fits into Pass-1's existing schema; doesn't reshape it.
- **GraphDB schema changes** — `Source.source_type` exists already in the schema (Task #89 §10.4 reference); NW-7 doesn't propose adding/removing schema columns.
- **NW-4 (Domain) revisions** — separate vocabulary; only flagged if NW-7 surfaces a domain-side issue that has implications for source_type.

### 6. Output format

Standard review format. Suggested structure:

1. **Convergence** — what holds together cleanly across the framework + list (don't dwell; just note)
2. **Findings** — concrete issues, ambiguities, contradictions, missed considerations. Prefix substantive findings as `**Finding F-N:**` and minor / nice-to-have observations as `**Observation O-N:**`.
3. **Recommendations** — proposed amendments to specific decisions / scopes / boundary conventions / list entries. Prefix as `**Recommendation:**` or `**Proposal:**`.
4. **Concrete classification probes** — give 3–5 concrete source examples (titles or descriptions) and propose how each should classify under v0.1. Flag any that the list can't classify cleanly.
5. **Open questions** — additional questions raised but not resolvable in review.

**Length:** under 2500 words. Cite specific section anchors (e.g., "§2.1", "D-NW7-3", "OQ-NW7-2") where possible. Quote the v0.1 doc with `> …` blockquotes where raising an issue with specific wording.

### 7. The artifact to review

Attached: `docs/task89-nw7-source-type-list-v0.1.md` (full file).

For project context, reference as needed:
- `docs/task89-component1-enrichment-blueprint.md` v0.2.1 — the parent blueprint NW-7 plugs into (esp. §2.1 source_type field + §9 placeholder list NW-7 replaces)
- `docs/task88-nw4-domain-list-v0.4.md` — sibling controlled-vocabulary (Domain), ratified 2026-05-25; structural template for NW-7
- `docs/external-review-panel.md` — reviewer panel composition + flow context
- `docs/CODEBASE_OVERVIEW.md` — current architectural state + Milestone Changelog
