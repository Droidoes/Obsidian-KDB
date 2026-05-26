# Task #89 NW-7 — Source Type Controlled Vocabulary v0.2

**Status:** v0.2 draft — folds 5-CLI panel review of v0.1 (Codex + Qwen CLI + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high; 5/5 guardrail-clean). Joseph-ratified at fork-resolution stage 2026-05-26 evening.
**Parent:** Task #89 (Component #1 Enrichment) v0.2.1 blueprint §9 (NW-7 placeholder)
**Predecessor:** `docs/task89-nw7-source-type-list-v0.1.md`
**Panel responses:** `docs/task89-nw7-v0.1-review-{codex,qwen,grok,deepseek,gemini}.md`
**Author:** Joseph + Claude (Coding Alter Ego)
**Date:** 2026-05-26

---

## 0. Changes from v0.1

### Framework correction (5/5 unanimous — F-1)

**D-NW7-4 rationale rewritten** to match the operational rule in §3.3 (which was already correct in v0.1). The contradiction caught by all 5 reviewers: v0.1's D-NW7-4 rationale said "recording medium wins," but §3.3 + scope texts said "rhetorical form wins regardless of medium." The operational rule is the correct one; v0.2 corrects the rationale.

**New principle**: **Rhetorical form wins over recording medium.** Q&A-dominated → `interview`; one-direction educational delivery → `transcript-lecture`. Medium-based (`transcript-podcast` vs `transcript-video`) is the residual tiebreaker only when neither rhetorical form dominates.

### Addition (3/5 — F-2)

**New entry: `chat-log`** (21st entry). Captures multi-party conversational exchanges in messaging or LLM interfaces (Slack/Discord exports, ChatGPT/Claude conversation exports). Closes a real gap — AI conversation exports are a growing ingestion surface for the `ai-ml` domain, and v0.1 had no clean home (`transcript-interview` was a semantic stretch; `other` lost signal).

### Rename (3/5 — F-4)

**`transcript-interview` → `interview`** — medium-neutral. The format is the load-bearing classifier; the `transcript-` prefix was semantically misleading for text-native Q&A (written interviews, AI conversation exports were forced into a `transcript-*` slot). `transcript-interview` preserved as alias for backward compatibility.

### Discipline (3/5 — F-3)

**New decision D-NW7-6: Scope texts are purely content-descriptive.** All "Distinguished from X" / "prefer Y over Z" clauses stripped from §2 scope texts (12 entries affected). Boundary disambiguation lives exclusively in §3. This eliminates the drift vector that produced F-1's contradiction (when boundary hints embedded in scopes drift from §3 rules, the LLM gets conflicting instructions). Mirrors NW-4 v0.4 precedent — `value-investing` scope is just "Investment philosophy, methods, mental models..." with NO sibling references.

### Tier 4 batch fold (panel refinements 1/5 each, non-controversial)

- §3.1 — venue-fallback rule for `blog` ↔ `post`: when venue cannot be inferred from content, classify by authorial stance (Deepseek F-2)
- §3.8 — `social-thread` refined to admit substantive single-post platform-native essays (LinkedIn article-posts, Substack Notes long-form), not only multi-post threads (Gemini F-3)
- §2.1 #9 — `documentation` scope tightened: "navigable, lookup-oriented, not narrative" qualifier (Qwen O-5)
- New §3.10 — `daily-note` ↔ `meeting-notes` boundary: omnibus dated log → `daily-note`; single-meeting artifact → `meeting-notes` (Codex O-4)
- New §3.11 — `documentation` ↔ `wiki` boundary: instruction/reference for action → `documentation`; descriptive entry about a topic → `wiki` (Gemini O-3)
- §3.4 — strengthened with explicit volume-based tiebreaker for annotated book excerpts (Gemini O-1)
- New §3.12 — `chat-log` ↔ `interview` boundary (induced by F-2 addition): both are multi-party conversational; `interview` is curated Q&A (interlocutor + subject); `chat-log` is informal exchange (often peer-to-peer or human↔AI)

### New OQs

- OQ-NW7-6 — Pass-1 prompt rendering format (cluster headers? boundary rules separate block?) — Component #1 implementation question
- OQ-NW7-7 — `other_reason` schema field (2/5 reviewer convergence; **NOT NW-7 vocab change** — flag for Task #89 v0.2.x schema)
- OQ-NW7-8 — `bookmarks` / `link-directory` candidate entry (Gemini OQ-1; defer to telemetry)
- OQ-NW7-9 — `article` ↔ `news` dominant-mode tiebreaker (Deepseek OQ-DS-NW7-3; defer to telemetry)
- OQ-NW7-10 — `transcript-lecture` symmetry to `interview` rename (should the transcript- prefix drop here too? Defer; monitor whether written-form lectures appear)

### Net count
**21 entries** (v0.1 had 20; +1 chat-log; 1 rename has same count effect).

### Pre-ratification vault alias scan (Qwen O-3)

Before NW-7 ratification and Pass-1 implementation, scan the user's vault for any existing `source_type` frontmatter values (any hand-tagged sources during NW-4's ratification period). For each found value not in v0.2's 21-entry list, decide: alias to a current ID, or force re-enrichment. **For `podcast` specifically: do NOT alias** — force re-enrichment so each source classifies correctly under the dropped-entry replacement (likely `transcript-podcast` if transcribed, `post`/`article` if show-notes-only). This is an operational note, not a vocab change.

---

## 1. Settled framework (v0.2 — 6 decisions)

### D-NW7-1 — Flat source_type list, no hierarchical sub-types
Pass-1 LLM classifies each source into exactly **one** entry from the flat list. No `sub_type` field. The `transcript-X` family looks hierarchical but is a naming convention only — Pass-1 sees a flat enum of 21 IDs.

**Rationale:** Same as D-NW4-1. Hierarchies smuggle structural decisions into the prompt that the GraphDB query layer can synthesize cheaper.

### D-NW7-2 — Cross-cutting relationships are not pre-declared
The config does NOT declare how source_types relate to one another. Cross-cuts emerge from query-layer aggregation if needed; they are not in the vocabulary config.

**Rationale:** [[feedback_no_edge_predeclaration_no_hints]]. Same discipline as D-NW4-5. Classification-disambiguation boundaries (§3) are rules, not edges.

### D-NW7-3 — Config schema (mirrors NW-4 v0.4 §7)
Per-entry: `id` + `display` + `scope` + `aliases`. Same 4-field shape as `domains.json`. File location: `kdb_compiler/config/source_types.json`.

### D-NW7-4 — Transcript family: rhetorical form wins (REVISED in v0.2)

When a transcript could classify by both rhetorical form and recording medium:

1. **Q&A structure dominates** (interlocutor asks; primary subject answers) → **`interview`** *regardless of recording medium*
2. **One-direction educational delivery** (single speaker teaching/presenting) → **`transcript-lecture`** *regardless of recording medium*
3. **Neither rhetorical form dominates AND recording medium identifiable** → medium-based: podcast → **`transcript-podcast`**; video → **`transcript-video`**
4. **Neither rhetorical form dominates AND medium ambiguous** → default to most-likely medium based on content cues

**Rationale (v0.2 correction):** Rhetorical form is more informative for query-time filtering than recording medium ("show me all interviews" should find interviews regardless of audio vs video origin). 5/5 reviewer convergence on this principle. The v0.1 rationale stated the opposite ("recording medium wins") but §3.3 + scope texts already encoded the correct rule — v0.2 aligns the rationale with the rule.

### D-NW7-5 — `other` is last-resort + telemetry-monitored
`other` is the residual catch-all. Use ONLY when no specific entry in #1-20 fits. Same usage discipline as NW-4 `undecided`: high `other` rate indicates the vocabulary needs expansion (post-deployment telemetry; OQ-NW7-1).

### D-NW7-6 — Scope texts are purely content-descriptive (NEW in v0.2)

Per-entry scope text in §2 (the text injected into the Pass-1 LLM prompt) describes ONLY **what content lives in this source_type**. Scope text does NOT:
- Reference other source_types ("Distinguished from X")
- Specify when to prefer one entry over another ("prefer Y if Z")
- Pre-declare cross-cuts or relationships (reinforces D-NW7-2)

**Boundary disambiguation lives exclusively in §3 of this document.** §3 boundary rules are rendered separately in the Pass-1 prompt template as a sibling block to the scope-descriptions block — NOT folded into scope text.

**Rationale (v0.2 from F-3):** Embedding boundary hints in scopes creates a drift vector. F-1's D-NW7-4 / §3.3 contradiction was exactly this class of drift — when scope hints and boundary rules can drift apart, the LLM gets conflicting instructions. Mirrors NW-4 v0.4 scope-text discipline (where `value-investing` scope is just "Investment philosophy, methods, mental models..." with no sibling references).

---

## 2. The list — 21 source_types

Cluster groupings below are **for human readability of this document only**. Pass-1 LLM sees a flat list of 21 IDs (per D-NW7-1).

Scope texts per D-NW7-6 are purely content-descriptive — no sibling references, no boundary hints. Boundary disambiguation lives in §3.

### 2.1 Written-prose cluster (10)

| # | ID | Display | Scope |
|---|---|---|---|
| 1 | `blog` | Blog Post | Personal blog post, technical blog, Substack newsletter, Medium piece, individual-authored writing on a personal or branded publication. Typically short to medium length (500-3000 words). |
| 2 | `post` | Online Post | Newsletter post, forum post, community-platform post (Reddit-style threaded discussion, HN-style comment), or generic online text published on a community / forum / aggregator venue. |
| 3 | `article` | Magazine / Long-form Article | Editorially-published magazine article, longform journalism piece, think-piece, or essay published through an editorial intermediary (The Atlantic, New Yorker, trade publication). Analytical, argumentative, or interpretive in voice. |
| 4 | `news` | News Report | Event-reporting journalism: news article reporting facts of a current event, press release, market report. Reports what happened. |
| 5 | `paper` | Academic / Research Paper | Peer-reviewed paper, preprint (arXiv, SSRN), working paper, conference paper, thesis, dissertation. Academic publication form regardless of subject. |
| 6 | `book-chapter` | Book Chapter / Excerpt | Verbatim chapter, section, or excerpt extracted from a longer book-length work. The content IS the book's text. |
| 7 | `book-summary` | Book Summary | Full-book distillation, chapter-by-chapter notes, or third-party summary of a book-length work (Blinkist-style abstracts, user's reading notes, executive summaries). The content is ABOUT a book, not FROM the book. |
| 8 | `letter` | Public Letter | Shareholder letter, public open letter, addressed correspondence intended for a defined audience and published as such (Buffett's letters, Bezos's letters, public open letters in trade publications). Curated, public-facing, addressed. |
| 9 | `documentation` | Technical Documentation | Software API documentation, product documentation, technical reference, tutorial, runbook, README. Content structured as a technical reference — navigable, lookup-oriented, not narrative. |
| 10 | `wiki` | Wiki / Encyclopedic Entry | Wikipedia article, encyclopedia entry, knowledge-base reference article, fandom wiki page. Content authored in encyclopedic register — third-person, multi-source, citation-heavy, neutral tone. |

### 2.2 Spoken-medium-transcribed cluster (3)

| # | ID | Display | Scope |
|---|---|---|---|
| 11 | `transcript-podcast` | Podcast Transcript | Verbatim transcript of an audio podcast episode — host monologue, host + guest conversation, or panel discussion. |
| 12 | `transcript-video` | Video Transcript | Verbatim transcript of video content — YouTube video, recorded talk, Vimeo, Loom, local video file. Medium-neutral within the video umbrella. |
| 13 | `transcript-lecture` | Lecture / Talk Transcript | Verbatim transcript of one-direction educational or informational delivery — academic lecture, conference talk, keynote, TED-style talk, public address. |

### 2.3 Conversational / interactive cluster (2)

| # | ID | Display | Scope |
|---|---|---|---|
| 14 | `interview` | Interview | Q&A-structured exchange where one or more interlocutors question a primary subject. Curated and intentional — the interviewer prepares questions and the subject is the focus. Format-driven and medium-neutral: applies to spoken interviews (transcribed), written interviews (email Q&A, document-based submission), and any other Q&A-structured exchange that is the source's primary form. |
| 15 | `chat-log` | Chat Log / Conversation | Verbatim log of a conversational exchange between two or more parties in a messaging or LLM interface — Slack export, Discord channel archive, Google Chat export, saved ChatGPT / Claude / Gemini conversation transcript. Informal register, rapid alternating multi-speaker conversational blocks, often tool-mediated. |

### 2.4 Primary-document cluster (3)

| # | ID | Display | Scope |
|---|---|---|---|
| 16 | `speech` | Speech / Address | Written-prose form of an address — prepared text of a speech, written speech, written address. Often the speaker's prepared text, regardless of whether the speech was actually delivered. |
| 17 | `social-thread` | Social Media Thread | Long-form thread, carousel, or substantive standalone post on a social platform (Twitter/X thread, LinkedIn long-form post, Threads multi-post, substantive single-post platform-native essay). Authored on the platform; the platform IS the publication venue. |
| 18 | `email` | Email | Forwarded or saved email correspondence, individual or distribution-list email content. Informal register, individual or small-group distribution. |

### 2.5 Vault-meta cluster (2)

These entries describe vault-internal source types that typically route to `noise` via `force_noise` path overrides (per Task #89 D-89-14). Source_type is still emitted by Pass-1 for completeness + audit + future use.

| # | ID | Display | Scope |
|---|---|---|---|
| 19 | `daily-note` | Daily Note / Log Entry | Obsidian Daily Note format — date-stamped vault page logging activities, reflections, todos. Typically diary-shaped omnibus of the day's events. Routes to `noise` by default via `force_noise: [Daily Notes/**]` (D-89-14). |
| 20 | `meeting-notes` | Meeting Notes | User-generated meeting notes — attendee-recorded notes from a meeting, call, or working session. Single-meeting artifact (one source = one meeting). User-summarized, paraphrased, action-item-shaped. |

### 2.6 Residual (1)

| # | ID | Display | Scope |
|---|---|---|---|
| 21 | `other` | Other source form | Residual catch-all for source forms not covered by #1-20. Use ONLY when you can articulate in one sentence why none of #1-20 applies — the articulation MUST name the specific missing publication form or shape (not just "doesn't fit"). If you cannot articulate that reason, re-examine #1-20 first. High `other` rate indicates the vocabulary needs expansion (OQ-NW7-1). |

---

## 3. Classification boundaries

Boundaries are classification disambiguation rules. They tell Pass-1 which `source_type` wins when content sits at an edge. They are NOT graph edges (per D-NW7-2). Per D-NW7-6, boundary rules live exclusively here — NOT embedded in scope texts.

### 3.1 `blog` ↔ `post` — venue + authorial stance
- **`blog`** when the content is on a personal blog, branded blog, or single-author publication (own publication; Substack/Ghost/WordPress/Medium with author's own subdomain).
- **`post`** when the content is on a community / forum / aggregator (Reddit, HN, generic web forum) — multi-author venue, not own publication.
- **Venue-fallback rule (NEW v0.2):** when venue cannot be inferred from content alone (source markdown contains only body text, no URL, no platform metadata), classify by **authorial stance**: single-author, framed as a self-contained piece → `blog`; response-to-community, framed as participation in a discussion → `post`.

### 3.2 `article` ↔ `news` — analysis vs reporting
- **`article`** when the piece is analytical, argumentative, or extended take (think-piece, opinion column, longform feature). Reports what to make of events.
- **`news`** when the piece reports facts of an event (who/what/when/where coverage, market report, press release). Reports what happened.
- Hybrid news-analysis: classify by dominant mode. If analysis fraction > reporting fraction by volume → `article`; otherwise → `news`. Persistent hybrid patterns are a watch metric (OQ-NW7-9).

### 3.3 Transcript family — rhetorical form wins (REVISED in v0.2 per D-NW7-4)
- If Q&A structure dominates → **`interview`** regardless of recording medium.
- If one-direction educational delivery dominates → **`transcript-lecture`** regardless of recording medium.
- If neither rhetorical form dominates AND recording medium identifiable: **podcast** → `transcript-podcast`; **video** → `transcript-video`.
- If neither rhetorical form dominates AND medium ambiguous → default to most-likely medium from content cues.

### 3.4 `book-chapter` ↔ `book-summary` — verbatim vs distillation, volume-tested
- **`book-chapter`** when the content IS the book's text (extracted chapter or section, verbatim).
- **`book-summary`** when the content is ABOUT the book (third-party summary, user's notes, distillation, abstract).
- **Volume-based tiebreaker for annotated excerpts (NEW v0.2):** for files mixing verbatim book text with user commentary, classify by proportional dominance. If the original chapter text is the majority by volume (commentary is marginalia on a verbatim excerpt) → `book-chapter`. If the user-authored summary, analysis, or restructuring dominates by volume (chapter text serves as scaffolding for the user's analysis) → `book-summary`.

### 3.5 `letter` ↔ `email` — public-curated vs private-informal
- **`letter`** for shareholder letters, public open letters, formally-addressed published correspondence (Buffett's annual letter). Defined audience + intentional publication.
- **`email`** for forwarded individual emails, saved newsletters in email format, list correspondence not framed as a "letter." Informal individual or small-group distribution.

### 3.6 `speech` ↔ `transcript-lecture` — text-form vs transcribed-from-delivery
- **`speech`** when the source is the prepared written text of an address (the speaker's notes or published prepared text — regardless of whether the speech was actually delivered).
- **`transcript-lecture`** when the source is a verbatim transcription of the delivered talk.
- A published "Speech to Congress, March 1933" (text-form) → `speech`. The auto-generated YouTube transcript of a TED talk (delivered) → `transcript-lecture`.

### 3.7 `wiki` ↔ `article` — encyclopedic vs editorial
- **`wiki`** when authored in encyclopedic register — third-person, multi-source citations, neutral tone (Wikipedia, fandom wikis, internal knowledge-base entries). Often collaboratively authored or no individual authorial signature.
- **`article`** when authored editorially — author voice, argument, analysis (magazine longform, think-piece). Even citation-heavy editorial essays with single-author signatures classify as `article`.

### 3.8 `social-thread` ↔ `post` — platform-native authored vs community comment (REFINED v0.2)
- **`social-thread`** when the content is platform-native substantive authored content — a multi-tweet thread, LinkedIn long-form post (with or without thread structure), Threads multi-post, substantive single-post platform-native essay. The platform IS the publication venue and the content is authored as a standalone piece for that platform.
- **`post`** when the content is a community/forum comment or short casual social sharing — Reddit comment, HN response, single-tweet without thread structure, short social media share without standalone-piece framing.
- **Key axis (v0.2 refinement):** substantive standalone authorship (`social-thread`) vs community-conversational participation (`post`). Single-post LinkedIn essays are `social-thread` despite being non-threaded.

### 3.9 `interview` ↔ `meeting-notes` — verbatim vs user-summarized
- **`interview`** when the source is a verbatim Q&A exchange (transcript of spoken interview, or text-native written interview).
- **`meeting-notes`** when the source is user-summarized notes from a meeting / call (paraphrased, abbreviated, action-item-shaped).
- Test: would the source be reconstructable verbatim from the file? Yes → `interview`; No (compressed by note-taker) → `meeting-notes`.

### 3.10 `daily-note` ↔ `meeting-notes` — omnibus log vs single artifact (NEW v0.2)
- **`daily-note`** when the file is a date-stamped omnibus log of the day's activities, reflections, todos (Obsidian Daily Note format). Even if a meeting section exists within a daily note, the file's overall form is daily-log → `daily-note`.
- **`meeting-notes`** when the file is a single dedicated artifact for one meeting / call / working session, not a date-stamped omnibus.

### 3.11 `documentation` ↔ `wiki` — instructional reference vs descriptive entry (NEW v0.2)
- **`documentation`** when the content is product-focused, instructional, action-oriented — API references, README files, runbooks, tutorials, how-to guides. The reader is expected to USE this to do something.
- **`wiki`** when the content is descriptive — encyclopedic entry about a product, entity, concept, or topic. The reader is expected to LEARN ABOUT something.

### 3.12 `chat-log` ↔ `interview` — informal multi-party vs curated Q&A (NEW v0.2)
- **`chat-log`** when the exchange is informal, peer-to-peer or human↔AI conversation, with rapid alternating turns and no clear interlocutor-vs-subject role. Slack/Discord chats, ChatGPT/Claude conversation exports, Google Chat threads.
- **`interview`** when the exchange has clear curated structure — designated interlocutor(s) asking prepared questions, designated subject(s) answering. The interviewer is the questioner; the subject is the focus.
- Test: if both parties are equally substantive contributors with no clear questioner/answerer role → `chat-log`. If one party is clearly the questioner and another is the answered subject → `interview`.

---

## 4. Explicit drops (carried from v0.1 + v0.2 additions)

| Candidate | Why dropped |
|---|---|
| **`podcast` (audio-only, no transcript)** | Without transcript, source content IS show notes (classifies as `post` or `article`). Audio-only podcast as a source-type entry describes the AUDIO not the text; redundant. (Carried from v0.1 §0.1.) |
| **`pdf`** | PDF is a container format, not a source type — a PDF can be a paper, book-chapter, letter, etc. Source-type captures content shape, not file format. |
| **`audio` / `video`** (no-transcript variants) | Container/medium not content shape — Pass-1 sees text content. |
| **`presentation` / `slide-deck`** | Plausible but rare for user's current intake; defer to telemetry (OQ-NW7-2). If slide narratives become common, consider as v0.3+. |
| **`legal-document` / `contract`** | Specialized; not in user's typical patterns; defer. |
| **`code-snippet` / `gist`** | Pass-1 doesn't typically ingest code; if needed, `documentation` covers structured technical content. |
| **`thread-twitter` / `thread-linkedin` / per-platform variants** | Consolidated to single `social-thread`; platform is incidental to the content shape. v0.2 §3.8 refinement: single-post LinkedIn essays also classify as `social-thread`. |
| **`book` (full book)** | If a full book is ingested as a single file, treat as `book-chapter` (a long one) or split via Component #2 before ingestion. v1 doesn't ship `book` because it conflates source-unit with content-shape. |
| **Quote-collection variant** | NW-4's `domain: quotes` covers the substantive axis; source_type-side a quote-collection .md → whatever its publication form is. |
| **`recipe`** | Not in user's vault patterns; if it appears, `post` or `wiki` covers. |
| **`research-note` / `equity-research-report`** | Describes `domain: personal-finance` content; source-form is typically `paper` (long) or `post` (short). |
| **`interview-written` as separate entry (v0.2)** | Resolved by F-4 rename `transcript-interview` → `interview` (medium-neutral). Written-Q&A interviews now classify cleanly under `interview` without semantic stretch. |
| **`bookmarks` / `link-directory` (v0.2 Gemini OQ-1)** | Plausible but defer to telemetry (OQ-NW7-8). Currently routes to `wiki` if curated with descriptive entries, or `other` if pure link-dump. Promote if cluster density emerges. |

---

## 5. Config schema (D-NW7-3 — mirrors NW-4 v0.4 §7)

### Ownership clarification
The config is the **Pass-1 source of truth** for the controlled vocabulary. Everything downstream reads the resulting `source_type` string value — only Pass-1 needs scope descriptions for prompt-context rendering.

### Per-entry — 4 fields

```json
{
  "id": "interview",
  "display": "Interview",
  "scope": "Q&A-structured exchange where one or more interlocutors question a primary subject. Curated and intentional — the interviewer prepares questions and the subject is the focus. Format-driven and medium-neutral: applies to spoken interviews (transcribed), written interviews (email Q&A, document-based submission), and any other Q&A-structured exchange that is the source's primary form.",
  "aliases": ["transcript-interview"]
}
```

| Field | Type | Purpose |
|---|---|---|
| `id` | string, kebab-case, unique | Canonical identifier used in Pass-1 output schema, GraphDB property values, query layer |
| `display` | string, Title Case | Human-facing name for UI / docs / display contexts |
| `scope` | string, prose paragraph | Content-only description of what classifies here. **No "for example" hints. No edge declarations. No sibling references** (per D-NW7-6). |
| `aliases` | array of strings, optional | Historical IDs that resolve to this current ID at query time. Enables rename migration without backfill. |

### What the config does NOT hold (anti-pattern per D-NW7-2 + D-NW7-6)
- ❌ Inclusion / exclusion examples
- ❌ Boundary-pair declarations (those live in §3 of this doc, not in the LLM-consumed config)
- ❌ Sibling-entry references ("Distinguished from X", "prefer Y over Z" — per D-NW7-6)
- ❌ Expected-rollup-cluster (smuggles hierarchy)
- ❌ Prompt-rendering text (the prompt template is its own artifact; the config feeds it raw scopes)
- ❌ Cross-cut hints

### Consumed by (Pass-1 owns; downstream reads values)
- **Pass-1 LLM prompt rendering** — scope descriptions injected into the classification prompt; **§3 boundary rules rendered as a separate sibling block** (per D-NW7-6; OQ-NW7-6 covers exact format)
- **Pass-1 output schema** — `source_type` field validated as enum over current IDs (aliases NOT accepted on write; only on read)
- **GraphDB property indexing** — `Source.source_type` (existing column per Task #89 §10.4) indexed for query
- **Query layer** — alias resolution at read time so historical sources resolve to current IDs
- **Pass-2 (compile)** — reads `source_type` as a string property per Task #89 D-89-17

### Aliases needed for v0.2 renames

```json
[
  { "id": "transcript-video", "aliases": ["transcript-youtube"] },
  { "id": "interview", "aliases": ["transcript-interview"] }
]
```

### File location (v1)
`kdb_compiler/config/source_types.json` — single source of truth; all consumers read from it. Mirrors `kdb_compiler/config/domains.json` (NW-4).

---

## 6. Open questions

### Carried from v0.1

#### OQ-NW7-1 — `other` rate KPI threshold (post-deployment)
Telemetry-driven. Threshold analog to NW-4's OQ-NW4-13 (`undecided` < 5% per rolling 100-source window). Specific threshold deferred to NW-5 (Pass-1 benchmark). v0.2 provisional target: `other` < 5% per rolling 100 enriched sources (per Codex F-5 recommendation).

#### OQ-NW7-2 — Specialized source-type telemetry watch
Monitor `other` classifications post-deployment for clustering patterns. Watch list: `presentation`, `legal-document`, `chat-log` (closed in v0.2 — added), `bookmarks-page` (covered by OQ-NW7-8), `recipe`. Re-open vocabulary deliberation if cluster density > N sources / month.

#### OQ-NW7-3 — Cross-source-type ↔ domain interactions
v0.2 explicitly does NOT couple source_type to domain (per D-NW7-2). Empirical correlations may emerge (e.g., `transcript-lecture` strongly correlates with `domain: ai-ml`). These should remain query-layer aggregations, not config declarations.

#### OQ-NW7-4 — `social-thread` durability
Social-media-platform content is link-rot-prone. Should source_type carry a flag for "platform-hosted-original-may-disappear"? Provisional: NO — Pass-1 is for source enrichment; durability is a Component #2 concern.

#### OQ-NW7-5 — Authority-axis tagging (deferred v0.3+)
Authority axis (peer-reviewed > editorial > personal > primary-source > vault-meta) could parallel NW-4 v0.4's D-NW4-6 boundary axes. v0.1 + v0.2 deliberately DON'T introduce — would smuggle ranking decisions. Telemetry-driven re-open if needed.

### New in v0.2

#### OQ-NW7-6 — Pass-1 prompt rendering format (Component #1 implementation)
Per D-NW7-6, scope texts and §3 boundary rules render as separate blocks in the Pass-1 prompt. Open implementation questions:
- Cluster headers exposed to LLM (e.g., "Written-prose cluster:" before the 10 entries) or flat numbered list only? Qwen OQ-NW7-7 flagged hierarchy-leakage risk if cluster headers are exposed. Lean: flat numbered list only.
- §3 boundary rules block — rendered as a separate "Classification boundaries" section after the scope-descriptions block? Or interleaved per-cluster?
- Source-of-truth — config scopes AND §3 boundary rules are both authoritative inputs to the prompt. Need clear separation in the prompt-rendering code so they cannot drift.

Resolves at Pass-1 implementation; not in NW-7 scope but flagged here.

#### OQ-NW7-7 — `other_reason` schema field (Task #89, NOT NW-7)
2/5 reviewer convergence (Codex F-5/OQ-3 + Qwen O-1/R-3). Add a structured `other_reason: string | null` to Pass-1 output schema — required when `source_type = other`, null otherwise. Feeds OQ-NW7-1 telemetry directly. **This is a schema-level addition to Task #89 v0.2.x, NOT a NW-7 vocabulary change.** Flag for absorption into the Pass-1 implementation plan.

#### OQ-NW7-8 — `bookmarks` / `link-directory` candidate entry (telemetry-deferred)
Gemini OQ-1. Curated bookmark / link collections in Obsidian (e.g., `Reading/Investing-Bookmarks.md` containing 50 links with brief descriptions). Currently routes to `wiki` (if descriptive) or `other` (if pure link-dump). Promote to first-class entry if cluster density emerges in telemetry.

#### OQ-NW7-9 — `article` ↔ `news` dominant-mode tiebreaker (telemetry-deferred)
Deepseek OQ-DS-NW7-3. v0.2 §3.2 provisional tiebreaker: classify by dominant mode (volume of analysis vs reporting). Monitor classification consistency on hybrid news-analysis pieces (e.g., NYT explanatory news). Re-open §3.2 rule if telemetry shows >10% classifier oscillation on this boundary.

#### OQ-NW7-10 — `transcript-lecture` symmetry to `interview` rename (telemetry-deferred)
v0.2 renamed `transcript-interview` → `interview` (medium-neutral). The symmetric question: should `transcript-lecture` similarly become `lecture` to admit text-form lectures without forcing them into `speech`? Currently §3.6 distinguishes `speech` (prepared text) from `transcript-lecture` (transcribed delivery). A medium-neutral `lecture` would blur that boundary. Deferred — monitor for written-form lectures appearing in `other` or being mis-classified as `speech`.

---

## 7. Versioning

- **v0.1** — initial 20-entry draft (within-session; not externally reviewed). Refined the §9.1 placeholder. Joseph internally ratified 2026-05-26 ("v0.1 is good").
- **v0.2** — this document. Folds 5-CLI panel review of v0.1 (Codex + Qwen CLI + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high; 5/5 guardrail-clean). 5/5 unanimous F-1 (D-NW7-4 contradiction) fixed; 3/5-convergence additions (chat-log) + renames (interview) + discipline (D-NW7-6) folded; Tier-4 batch fold of 7 1/5 refinements. 5 new OQs.
- **v0.3** — pending. If Joseph review of v0.2 surfaces redirects, fold. If clean, v0.2 promotes to ratified.
- **Post-ratification iteration** — operational telemetry-driven (OQ-NW7-1 through 10) once Component #1 ships and live ingestion produces real distribution data. No external panel re-review planned post-ratification; ratified version is production-ready vocabulary.

---

## 8. Disposition of v0.1 panel findings

Convergence labels: **U** = 5/5 unanimous, **S** = 3/5+ strong, **M** = 2/5 majority, **B** = 1/5 unique.

### Load-bearing findings

| Finding | Convergence | v0.2 disposition |
|---|---|---|
| **F-1: D-NW7-4 / §3.3 contradiction** | **U (5/5)** | ✓ Locked — D-NW7-4 rationale rewritten to match §3.3 (rhetorical form wins; medium residual). |
| **F-2: chat-log missing entry** | **S (3/5 — Codex F-4 + Gemini F-2 + Deepseek OQ-DS-NW7-2)** | ✓ Added as 21st entry in new Conversational / interactive cluster (§2.3). |
| **F-3: Scope-text discipline drift** | **S (3/5 — Codex F-2 + Qwen F-2 + Deepseek F-3)** | ✓ New D-NW7-6 — scope texts purely content-descriptive; §3 sole boundary authority. All 12 "Distinguished from X" clauses stripped from §2 scopes. |
| **F-4: Written-Q&A `transcript-interview` stretch** | **S (3/5 — Qwen F-3 + Deepseek F-4 + Gemini OQ-2; Grok F-2 minor)** | ✓ Renamed `transcript-interview` → `interview` (medium-neutral); alias preserved. Cluster restructured (3 transcript entries + new Conversational cluster). |

### Schema-level (flagged for Task #89, NOT NW-7 vocab change)

| Finding | Convergence | v0.2 disposition |
|---|---|---|
| `other_reason` structured field | M (2/5 — Codex F-5/OQ-3 + Qwen O-1/R-3) | ✓ Flagged as OQ-NW7-7 for Task #89 v0.2.x schema absorption. NOT NW-7 vocab. |

### Tier 4 — Refinements folded into v0.2

| Source | Fix | Where folded |
|---|---|---|
| Deepseek F-2 | Venue-fallback rule for `blog` ↔ `post` when content lacks venue metadata (authorial stance fallback) | §3.1 |
| Gemini F-3 | `social-thread` refined to admit substantive single-post platform-native essays | §3.8 |
| Qwen O-5 | `documentation` scope tightened: "navigable, lookup-oriented, not narrative" | §2.1 #9 |
| Codex O-4 | `daily-note` ↔ `meeting-notes` boundary: omnibus dated log vs single-meeting artifact | New §3.10 |
| Gemini O-3 | `documentation` ↔ `wiki` boundary: instructional reference vs descriptive entry | New §3.11 |
| Gemini O-1 | Volume-based tiebreaker for annotated book excerpts | §3.4 |
| (induced by F-2 add) | `chat-log` ↔ `interview` boundary | New §3.12 |
| Qwen O-3 | Pre-ratification vault alias scan | §0 operational note (not vocab change) |
| Codex F-5 | `other` rate KPI provisional target (< 5% per rolling 100 sources) | OQ-NW7-1 update |

### Tier 5 — New OQs for v0.2

| Source | OQ |
|---|---|
| Qwen OQ-NW7-7 + Codex OQ-2 + Qwen OQ-NW7-8 | OQ-NW7-6 — Pass-1 prompt rendering format (Component #1) |
| Codex OQ-3 + Qwen R-3 | OQ-NW7-7 — `other_reason` schema field (Task #89, not NW-7) |
| Gemini OQ-1 | OQ-NW7-8 — `bookmarks` / `link-directory` candidate (defer to telemetry) |
| Deepseek OQ-DS-NW7-3 | OQ-NW7-9 — `article` ↔ `news` dominant-mode tiebreaker |
| (induced by F-4 rename) | OQ-NW7-10 — `transcript-lecture` symmetry to `interview` rename |

### Tier 6 — Observations carried as context (no v0.2 change)

| Observation | Disposition |
|---|---|
| Codex O-1 — `social-thread` cluster placement | v0.2 moved to Primary-document cluster; rationale documented |
| Codex O-2 — `speech` ↔ `transcript-lecture` stable | ✓ Confirmed; §3.6 unchanged |
| Codex O-3 — `wiki` ↔ `article` stable | ✓ Confirmed; §3.7 unchanged |
| Codex O-5 — Authority-axis warning to downstream consumers | Noted; OQ-NW7-5 carries forward |
| Qwen O-2 — Podcast show-notes-plus-transcript compound case | Acceptable; Pass-1 prompt-engineering concern, not vocab gap |
| Qwen O-4 — `social-thread` cluster rationale | Documented in §2.4 cluster header note (new in v0.2) |
| Deepseek O-1 — `social-thread` threading-cue fragility | Acknowledged; F-3 refinement (§3.8 admits substantive single-post) mitigates partially |
| Deepseek O-2 — D-89-14 coupling in vault-meta scopes | Acknowledged; descriptive language preserved |
| Deepseek O-3 — `presentation` / `slide-deck` gap | OQ-NW7-2 telemetry watch |
| Gemini O-2 — Wiki = collaborative; article = single-author | Folded into §3.7 |

### Panel behavior

**5/5 guardrail-clean.** All 5 reviewers honored the no-repo-modification guardrail in the dispatch prompt; no other files modified. **agy on 3-for-3** clean track record (Task #89 v0.1 review + Task #89 round-2 review + NW-7 v0.1 review); one-strike re-trial conclusively passed.

---

## 9. Anchors

- Task #89 v0.2.1 blueprint §9 — original placeholder + NW-7 framing
- Task #88 NW-4 v0.4 (`docs/task88-nw4-domain-list-v0.4.md`) — sibling controlled-vocabulary precedent
- v0.1 (`docs/task89-nw7-source-type-list-v0.1.md`) — predecessor; v0.2 is the panel-fold version
- v0.1 panel responses (`docs/task89-nw7-v0.1-review-{codex,qwen,grok,deepseek,gemini}.md`) — panel inputs
- v0.1 dispatch prompt (`docs/task89-nw7-v0.1-review-prompt.md`) — context for reviewers
- `docs/external-review-panel.md` — 5-reviewer panel composition + flow + one-strike rule
- [[feedback_no_edge_predeclaration_no_hints]] — drives D-NW7-2 + D-NW7-6 scope-text discipline
- [[feedback_concrete_first_extract_later]] — drives concrete-first vocabulary (vs axes upfront)
- [[feedback_post_llm_deterministic_override]] — `source_type` is content-only judgment; no path-based override (unlike `kdb_signal`)
- [[feedback_gemini_review_only_guardrail]] — agy 3-for-3 successful re-trial confirms post-strike-rehab status

---

**END OF NW-7 v0.2 DRAFT**
