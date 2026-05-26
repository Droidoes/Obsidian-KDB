# NW-7 v0.1 Review — Qwen CLI (qwen3.7-max)

## Convergence

The 20-entry list is a sound refinement of the §9.1 placeholder. Additions (`book-summary`, `documentation`, `social-thread`, `wiki`) each capture a distinct publication form; the rename corrects platform-specific naming; the `podcast` drop correctly identifies a content-form / media-form confusion. The five framework decisions mirror NW-4 v0.4's structural posture: flat list, no pre-declared cross-cuts, 4-field config schema, catch-all with telemetry KPI. NW-4 sibling consistency holds across all five structural checkpoints.

Granularity is right — no merge candidates are compelling (`blog` ↔ `post` are venue-distinguishable; the four `transcript-X` entries serve real query-time filter needs). The explicit-drops list (§4) is well-reasoned — `pdf`, `audio`, `video` correctly identified as container/media formats; `presentation`, `legal-document`, `code-snippet` correctly deferred to telemetry.

## Findings

### Finding F-1: D-NW7-4 principle statement contradicts its own operational rule (§1 / §3.3)

**Section:** D-NW7-4 (rationale clause), §2.2 scope texts, §3.3 boundary rule

D-NW7-4's rationale clause states:

> If a transcript is ambiguous between two (e.g., a video that's an interview), the format-of-recording wins (`transcript-video` over `transcript-interview`) — the underlying medium is more durable signal than the rhetorical mode.

But the operational rule in §3.3 says the **opposite**:

> If Q&A structure dominates (interlocutor asks; primary subject answers) → `transcript-interview` **regardless of recording medium**.
> If one-direction educational delivery → `transcript-lecture`.
> If **neither** Q&A nor lecture dominates AND the recording medium is identifiable: podcast = `transcript-podcast`; video = `transcript-video`.

The operational rule is **rhetorical-form-first** — Q&A structure → `transcript-interview` regardless of medium; lecture structure → `transcript-lecture`. Recording medium is the **residual** tiebreaker when neither rhetorical form dominates. This is the correct rule — rhetorical form is more informative for query-time filtering than recording medium, and the "regardless of recording medium" language in §3.3 is unambiguous.

The contradiction is in D-NW7-4's rationale clause, not in §3.3. The rationale says "recording medium wins" as a blanket principle; the rule says "recording medium wins *only as a residual*."

The `transcript-interview` scope text further undermines D-NW7-4's stated principle:

> Format-driven, **not medium-driven** — applies whether the interview was originally podcast, video, written-Q&A, or in-person.

"Format-driven, not medium-driven" directly contradicts "recording medium is more durable signal than the rhetorical mode."

**Recommendation:** Amend D-NW7-4's rationale clause to match the actual operational rule:

> If a transcript is ambiguous between two, **rhetorical form wins** (`transcript-interview` for Q&A-dominated content regardless of recording medium; `transcript-lecture` for one-direction educational delivery). Recording medium is the residual tiebreaker when neither rhetorical form dominates (`transcript-podcast` vs `transcript-video`).

This corrects the principle without changing the rule — §3.3 is already correct.

### Finding F-2: Scope text discipline divergence from NW-4 — transcript scopes contain boundary hints (§2.2)

**Section:** §2.2 scope texts (entries 11-14), D-NW7-2, NW-4 v0.4 D-NW4-5

NW-7 §5 config schema states: *"No 'for example' hints. No edge declarations."* But the `transcript-X` scope texts embed boundary-rule fragments:

- `transcript-podcast`: *"When a podcast is also an interview format, prefer `transcript-interview` if Q&A structure dominates."*
- `transcript-video`: *"When a video is an interview format, prefer `transcript-interview` if Q&A structure dominates; when it's a lecture, prefer `transcript-lecture`."*

Compare NW-4's purely content-descriptive scopes (e.g., `value-investing`: *"Investment philosophy, methods, mental models in the Buffett / Munger / Li Lu / Pabrai tradition."*). No "prefer X if Y" routing instructions.

The divergence has a practical motivation (the four-way transcript disambiguation is complex), but it creates drift risk — F-1 already demonstrates scope text contradicting D-NW7-4's stated principle.

**Recommendation:** Strip boundary hints from transcript scope texts; make scopes purely content-descriptive. Rely on §3.3 (injected into the Pass-1 prompt as a separate block) for boundary disambiguation. This matches NW-4's discipline and eliminates the drift vector between scope hints and §3.3 rules. If the pragmatic case for local routing context is compelling, document the transcript family as an explicit exception in D-NW7-2 — but don't let the exception go undocumented.

### Finding F-3: `transcript-interview` scope includes "written-Q&A" — naming stretch (§2.2)

**Section:** §2.2, `transcript-interview` scope

The scope states: *"Format-driven, not medium-driven — applies whether the interview was originally podcast, video, written-Q&A, or in-person."*

The "written-Q&A" inclusion is a naming stretch — a text-native Q&A exchange (email interview, document-based Q&A) was never recorded, so calling it a `transcript-*` is misleading. The `transcript-` prefix implies speech-to-text derivation. Pragmatically, `transcript-interview` is the only interview-shaped entry and the classification is correct. But the naming tension should be flagged for post-ratification telemetry (see OQ-NW7-6).

### Observation O-1: `other` guardrail is strong but could specify where the one-sentence reason goes (§2.5)

§2.5 says: *"Use ONLY when you can articulate in one sentence why none of #1-19 applies."*

This is a good LLM-prompt guardrail — forcing articulation before fallback reduces lazy `other` classification. But the schema doesn't specify where the one-sentence reason lives. Is it emitted as a structured field (e.g., `other_reason: <string>`)? Or is it internal LLM reasoning that doesn't appear in the output?

For telemetry (OQ-NW7-1), the `other_reason` text is the primary signal for clustering patterns and identifying vocabulary gaps. Without a structured field, the reason exists only in the LLM's internal chain-of-thought (if prompted for it) and is lost.

**Recommendation:** Add an `other_reason` field to the Pass-1 output schema — required when `source_type = other`, null otherwise. This is a schema-level addition (Task #89 v0.2.1 territory, not NW-7 vocabulary territory), but NW-7 should flag the need. The field feeds OQ-NW7-1 telemetry directly.

### Observation O-2: `podcast` drop — compound show-notes-plus-transcript files (§0.1)

The drop reasoning is sound. But an intermediate case exists: a podcast ingested with auto-generated transcript appended to show notes (common with Whisper-based tools). The .md file contains both show notes AND a verbatim transcript. Under v0.1, this classifies as `transcript-podcast` — correct, but the show-notes portion introduces extraction noise. Accept for v0.1; this is a Pass-1 prompt-engineering concern (multi-shape source handling), not a vocabulary gap.

### Observation O-3: Single alias may be insufficient for historical frontmatter migration (§5)

§5 lists only one alias: `transcript-video` ← `transcript-youtube`. But if any sources were hand-tagged with the §9.1 placeholder IDs before NW-7 ratification, those IDs need aliases too. Specifically:

- The placeholder had `podcast` — now dropped. Sources tagged `podcast` need to resolve to something (likely `transcript-podcast` if they had transcripts, `post` if they were show-notes-only). A blanket alias `podcast` → `transcript-podcast` would be wrong for show-notes-only cases.
- The placeholder had `transcript-youtube` — renamed. This alias IS listed. ✓

**Recommendation:** Before ratification, scan the vault for any existing `source_type` frontmatter values (if any sources were hand-tagged during NW-4's ratification period). For each found value not in the v0.1 list, decide: alias to a current ID, or re-classify via Pass-1 re-enrichment. For `podcast` specifically: do NOT alias — force re-enrichment so each source classifies correctly under the new vocabulary.

### Observation O-4: `social-thread` cluster placement rationale could be stated more precisely (§2.3)

§2.3 places `social-thread` in the primary-document cluster (between `speech` and `email`). The implicit reasoning is that social threads are platform-hosted-original content — the platform IS the publication venue, and the thread is the primary document. This distinguishes it from `post` (community/aggregator venue) and `blog` (own-publication venue).

The placement is defensible, but the rationale isn't stated. A reader might expect `social-thread` in the written-prose cluster (it IS written prose) or question why it's closer to `speech` than to `article`.

**Recommendation:** Add a one-line cluster-placement note to §2.3 header: *"Primary-document cluster: content whose publication form is native to its platform — the platform IS the publication venue, not a distribution channel for content created elsewhere."*

### Observation O-5: `documentation` scope may be too broad for the user's current intake (§2.1)

`documentation` scope: *"Software API documentation, product documentation, technical reference, tutorial, runbook, README. Structured technical reference content."*

This covers a very wide range — from a single README.md to a 500-page API reference. The user's vault currently has limited technical documentation ingestion (the `ai-ml` domain is maturing but not yet a heavy documentation consumer). The broad scope is correct for future-proofing, but the LLM may over-classify: any technical-looking blog post could be pulled toward `documentation` if the scope is read broadly.

**Recommendation:** Tighten the scope slightly to emphasize the *reference* nature: *"Software API documentation, product documentation, technical reference, tutorial, runbook, README — content structured as a technical reference (navigable, lookup-oriented, not narrative). Distinguished from `blog`/`article`: documentation = reference form; blog/article = narrative or argumentative form."* The "navigable, lookup-oriented, not narrative" qualifier gives the LLM a sharper discriminator.

## Recommendations

### R-1: Amend D-NW7-4 rationale to match §3.3 operational rule (addresses F-1)

Replace the rationale clause in D-NW7-4:

> **Before:** "If a transcript is ambiguous between two (e.g., a video that's an interview), the format-of-recording wins (`transcript-video` over `transcript-interview`) — the underlying medium is more durable signal than the rhetorical mode."
>
> **After:** "If a transcript is ambiguous between two, rhetorical form wins: Q&A-dominated content → `transcript-interview` regardless of recording medium; one-direction educational delivery → `transcript-lecture`. Recording medium is the residual tiebreaker when neither rhetorical form dominates (`transcript-podcast` vs `transcript-video`)."

### R-2: Strip boundary hints from transcript scope texts (addresses F-2, option 1)

Rewrite §2.2 scope texts to be purely content-descriptive:

| ID | Revised Scope |
|---|---|
| `transcript-podcast` | Verbatim transcript of an audio podcast episode — host monologue, host + guest conversation, or panel discussion. |
| `transcript-video` | Verbatim transcript of video content — YouTube, Vimeo, Loom, recorded talk, or local video file. |
| `transcript-interview` | Verbatim transcript of a Q&A-structured conversation where one or more interlocutors question a primary subject. Applies regardless of original medium (audio, video, written, in-person). |
| `transcript-lecture` | Verbatim transcript of one-direction educational or informational delivery — academic lecture, conference talk, keynote, public address. |

Boundary disambiguation rules for the transcript family live exclusively in §3.3 (which is injected into the Pass-1 prompt as a separate block per the boundary-conventions design).

### R-3: Add `other_reason` schema field flag (addresses O-1)

Flag for Task #89 v0.2.1: add `other_reason: <string or null>` to the Pass-1 output schema audit section — required when `source_type = other`, null otherwise. This feeds OQ-NW7-1 telemetry. NW-7 itself doesn't change; the schema addition is in the parent blueprint.

### R-4: Tighten `documentation` scope to emphasize reference form (addresses O-5)

Per O-5 above — add "structured as a technical reference (navigable, lookup-oriented, not narrative)" to the `documentation` scope and add a `blog`/`article` distinction clause.

## Concrete classification probes

Five real-world source examples to stress-test the vocabulary:

### Probe 1: Lex Fridman Podcast #400 — Sam Altman interview (YouTube, auto-transcribed)

**Expected:** `transcript-interview` — Q&A structure dominates (Fridman asks; Altman answers). Recording medium is video, but per §3.3 rhetorical form wins.
**Result:** ✓ Clean classification. The §3.3 rule handles this unambiguously.

### Probe 2: Buffett 2024 Shareholder Letter (PDF, OCR'd to markdown)

**Expected:** `letter` — shareholder letter, public-facing, addressed correspondence.
**Result:** ✓ Clean. §3.5 `letter` ↔ `email` boundary applies (public-curated vs private-informal). Not `book-chapter` despite being from Berkshire's annual report — the letter is a standalone addressed document, not a chapter extracted from a longer work.

### Probe 3: ChatGPT conversation export — "Explain quantum computing" (markdown)

**Expected:** Unclear. The content is a Q&A exchange between user and AI. Under §3.3, Q&A structure dominates → `transcript-interview`? But "interview" implies human interlocutors, and the `transcript-` prefix implies speech-to-text derivation. The source was never spoken — it's a text-native AI conversation.
**Result:** ⚠ Edge case. `transcript-interview` is the closest fit under v0.1 rules, but the classification feels forced. Options: (a) accept `transcript-interview` with the scope-text stretch noted in F-3; (b) classify as `other` with `other_reason: "AI conversation export — no human interlocutor, no recording medium"`; (c) classify as `documentation` if the content is structured as a technical reference. **Recommendation for v0.2:** This is an OQ-NW7-2 watch-list candidate. If AI conversation exports become a recurring intake form, add `conversation-export` or broaden `transcript-interview` scope to include AI interlocutors. For v0.1, (a) is acceptable.

### Probe 4: "The Psychology of Human Misjudgment" — Munger speech (published text with editorial footnotes)

**Expected:** `speech` — the prepared text of an address, with editorial apparatus.
**Result:** ✓ Clean. §3.6 `speech` ↔ `transcript-lecture` boundary: text-form of the address → `speech`. The editorial footnotes don't change the content shape — the primary content is the address text. Not `transcript-lecture` because this is the published written text, not a transcription of the delivery.

### Probe 5: New York Review of Books — 8000-word essay on the history of central banking

**Expected:** `article` — editorially published longform, author voice, analytical.
**Result:** ✓ Clean, but worth walking the `wiki` ↔ `article` boundary (§3.7). The essay is encyclopedic in scope and citation-heavy (wiki-like), but it's editorially published with author voice and argument (article-like). §3.7's rule: encyclopedic *register* (third-person, neutral tone) → `wiki`; editorial *publication* (author voice, argument) → `article`. This essay has author voice and argument → `article`. The encyclopedic breadth is a content characteristic, not a register characteristic. The boundary holds.

## Open questions

### OQ-NW7-6: `transcript-` prefix naming for text-native interviews (new)

Raised by F-3. The `transcript-` prefix implies speech-to-text derivation. If text-native Q&A content (written interviews, AI conversation exports, email-Q&A exchanges) becomes a recurring intake form, the `transcript-interview` name becomes misleading. Should the family be renamed from `transcript-X` to a prefix that doesn't imply speech-to-text? (e.g., `spoken-X` for the speech-derived entries + `interview` for format-driven entries regardless of medium.) Deferred to post-ratification telemetry.

### OQ-NW7-7: Scope text rendering in Pass-1 prompt (new)

How are the 20 scope texts injected into the Pass-1 prompt? As a flat numbered list? Grouped by cluster (with cluster labels visible to the LLM)? The fire-prompt says cluster groupings are "for human readability only" and the LLM "sees a flat list." But if the prompt template renders clusters with headers (e.g., "Written-prose cluster:"), the LLM will see cluster structure and may use it for classification — which reintroduces the hierarchy that D-NW7-1 explicitly rejects.

**Recommendation:** Confirm in the Pass-1 prompt template that the 20 entries are rendered as a flat numbered list without cluster headers. This is a Component #1 implementation detail, but NW-7 should flag it to prevent accidental hierarchy leakage.

### OQ-NW7-8: Boundary rules (§3) prompt injection format (new)

§3.3's transcript boundary rules are the operational authority for the four-way transcript disambiguation (especially after R-2 strips boundary hints from scope texts). How are these rules injected into the Pass-1 prompt? As a separate "boundary conventions" block after the source_type list? Inline with the list? The injection format affects how well the LLM applies the rules. NW-4's boundary rules (§4 in the domain list) are presumably injected as a separate block; NW-7 should follow the same pattern for consistency.

**END OF REVIEW**
