# Task #88 v0.1 Checkpoint — External Review Prompt

**Purpose:** Fire the v0.1 checkpoint blueprint (`docs/task88-ingestion-pipeline-blueprint.md`) at the post-Gemini external review panel for structural review of the **source-storage component + two-pass worth-judgment architecture** before deeper component design begins. This is a **checkpoint review, not v1 holistic** — only the architectural skeleton settled this round is in scope (see §10 of the blueprint for the explicit out-of-scope list).

**Dispatched:** 2026-05-24 (to be fired by Joseph)
**Target panel:** Codex + Deepseek + Qwen (per `docs/external-review-panel.md`)
**Response files (one per reviewer):**
- `docs/task88-v0.1-review-codex.md`
- `docs/task88-v0.1-review-deepseek.md`
- `docs/task88-v0.1-review-qwen.md`

---

## ─── Prompt body ───

You are reviewing **v0.1 checkpoint** of the Task #88 (Ingestion Pipeline) blueprint for the Obsidian-KDB project. The blueprint is at `docs/task88-ingestion-pipeline-blueprint.md`. It captures the architectural skeleton settled in the 2026-05-24 brainstorm following the 2026-05-23 strategic pivot ("tunnel from both ends" — pause end-A deepening; focus on end-B ingestion).

This is a **checkpoint review** — the architectural skeleton + source-storage component (#88's first deep-designed component) + the two-pass worth-judgment flow + the v1 scope sequencing. **It is NOT a v1 holistic review.** Multiple components remain outlined-only and are out of scope for this round (see §10 of the blueprint).

### Project context (brief)

End A (compile pipeline) is mature. Its input boundary was frozen 2026-05-23 as the **Producer Contract v1.0** at `docs/graphdb-kdb-producer-contract.md`. End B (ingestion) is being designed now.

The brainstorm decomposed end-B into 5 components plus 1 cross-cutting addition (Pass-2 worth-verdict in end A). The source-storage component (#2) was deep-designed this round; others remain outlined. A critical architectural insight emerged: the two source-storage configurations Joseph initially framed as separate platforms ("raw-drop" and "vault-in-place") are actually two **configurations of the same component** — 5 of 6 dimensions identical, only Location and Scope-config differ.

The other key architectural move was the two-pass worth-judgment flow: instead of gating sources at ingestion entry, the enrichment LLM (which fires per source anyway) piggybacks a binary `pass/not_pass` Pass-1 verdict; compile then does an ontology-aware Pass-2 verdict before adding to the ontology. This required ratifying an exception to the pivot rule ("no new architectural surface on end A"): Pass-2 is permitted as the single exception.

### What to review

Read the full blueprint end-to-end. Then stress-test along these axes:

1. **Component decomposition framework (§2).** Is the 5-component split clean (Enrichment / Source Storage / Trigger / Model selection / Move-from-compile)? Are any axes missing? Does any component cross-cut others in ways that suggest the cut is wrong? Pass-2 worth-verdict ended up living in end A, not as a 6th component — defensible, or a sign the decomposition needs rework?

2. **Source-storage 6-dimension decomposition (§3.2).** Are the dimensions (location / access pattern / identity / format / lifecycle / scope rules) the right cut? Anything missed, over-split, or under-split? Specifically:
   - Is "format" really a dimension or an attribute of location?
   - Is "lifecycle" actually multiple sub-dimensions (new-detection vs change-detection vs delete-detection vs move-detection have different costs and semantics)?
   - Is "identity" sufficient as "vault-relative path," or should it include content-hash for rename-stability?

3. **"One component, two configurations" abstraction (§3.1).** Does this hold up architecturally, or is there a hidden assumption that breaks once a third configuration (e.g., for non-Obsidian-vault sources) appears? Both v1 configs read Obsidian markdown — the abstraction is genuinely tested only when a non-vault, non-markdown source arrives.

4. **Dir-exclusion as the only pre-LLM gate (§4.2, D-88-3).** Is "ingest+enrich everything past dir-excludes" the right call? The piggyback-cost argument is the core rationale. Push specifically on:
   - The **silent-failure mode** (Pass-1 false-rejects are invisible — we don't know what we missed). Is sample-audit mitigation sufficient?
   - The hedge clause ("revisit if vault grows large AND LLM cost reverts") — is the watch-rule concrete enough to fire when it should?

5. **Two-pass worth-judgment (§4, D-88-4, D-88-5).** Does the Pass-1 / Pass-2 split hold up?
   - Is Pass-1 binary (`pass/not_pass`, "uncertain" → `pass`) the right shape, or is a third tier needed?
   - Is Pass-2 as new end-A architectural surface defensible, or should it live elsewhere (e.g., as a separate operator that compile consumes)?
   - Pass-2 mechanism is OQ-88-2 (explicit / implicit / hybrid) — weigh in.

6. **The architectural exception in D-88-5.** Pass-2 is the only permitted new surface on end A under the pivot rule. Is this defensible, or is the pivot rule being bent in a way that opens a slippery slope (other "necessary counterparts" might claim similar exceptions later)?

7. **Pass-1 attention dilution (OQ-88-4).** Pass-1 currently crams four outputs into one LLM call: verdict + domain/sub_domain + property_tags + wikilink_suggestions. Is this sound, or should it split? Specifically: is the worth-verdict (a single binary signal) at risk of being dominated by the larger generative outputs (tags + wikilinks)?

8. **Change-detection signal set (§3.5, D-88-7).** Is the signal set complete? Is the recompile-trigger logic correct? Specifically: should renames within the same dir trigger re-ingest, or only dir-path changes? Should content-hash be the only authoritative trigger, or are there cases where mtime-only change should also trigger?

9. **Consistency with Producer Contract v1.0** (`docs/graphdb-kdb-producer-contract.md`, frozen 2026-05-23). #88 produces artifacts that end A consumes per this contract. Specifically:
   - Does the #88 source-storage component align with the contract's §3 (four artifacts a producer must emit)?
   - Is there a missing intermediate layer between #88's enrichment output and the producer-contract's expected input shape?
   - Is the read-in-place / state-tracking-only model (D-88-2) compatible with the contract's run-shaped artifact emission pattern?
   - **Codex specifically: please cross-check** — your D-83/84-6 schema-grounded catches set the precedent.

10. **Vocabulary disambiguation (OQ-88-1).** Pick a recommendation. The ambiguity between Task #88's name ("Ingestion Pipeline") and the internal use of "pipeline" for source-producers is real.

11. **v1 scope (§6).** Are the IN/OUT items the right cut? Specifically:
    - Is deferring source-feeder framework design (Sub-C, §5.5) to post-v1 the right call, or does it create coupling debt?
    - Is deferring NW-4 (domain canonicalization list) to a parallel session the right cut, or does this v0.1 architectural skeleton implicitly depend on its content in ways not yet surfaced?

### Out of scope for this review

- **NW-4 — domain/sub_domain canonicalization list content.** Being designed in a parallel session. Reviewable separately.
- **NW-1 — Pass-1 criteria content** (the actual "is this signal?" prompt). Deferred to Component #1 deep design.
- **OQ-88-2 mechanism details** beyond which of the three options to prefer.
- **Source-feeder framework design** (Sub-C). Explicitly deferred from v1.
- **Component #4 model selection** (text vs graph LLM). Deferred to v2.
- **Re-litigating the strategic pivot** itself (compile-pause + ingestion-focus). Joseph-ratified 2026-05-23; not up for revision in this review.
- **Components #1 (Enrichment), #3 (Trigger), #5 (Move-from-compile) deep design** beyond their outlines in §5. They return in later checkpoints.
- **Pass-1 → Pass-2 routing of "uncertain"** — settled as "uncertain → pass" (binary).
- **Aliases.json operationalization** (#74 Path-0 finding) — out of #88 scope.

### Output format

Standard review-prompt format. Suggested structure:

1. **Convergence** — what holds together cleanly across the architectural skeleton (don't dwell; just note)
2. **Findings** — concrete issues, ambiguities, contradictions, missed considerations
3. **Recommendations** — proposed amendments to specific sections / decisions / OQs, prefixed `**Recommendation:**` or `**Proposal:**`
4. **Open questions** — additional questions raised but not resolvable in review

**Length:** under 2500 words. Cite specific section anchors (e.g., "§3.5", "D-88-4", "OQ-88-2") where possible. Quote the blueprint with `> …` blockquotes where raising an issue with specific wording.

### The blueprint to review

Attached: `docs/task88-ingestion-pipeline-blueprint.md` (full file).

For project context, also reference as needed:
- `docs/graphdb-kdb-producer-contract.md` v1.0 (frozen 2026-05-23) — the input boundary end A consumes
- `docs/CODEBASE_OVERVIEW.md` — current architectural state + Milestone Changelog
- `docs/JOURNEY.md` — three-iteration retrospective; why we got to this pivot
- `docs/session-handoff-2026-05-23-saturday-afternoon.md` §Strategic pivot — original pivot ratification context
- `docs/external-review-panel.md` — reviewer panel composition + flow
