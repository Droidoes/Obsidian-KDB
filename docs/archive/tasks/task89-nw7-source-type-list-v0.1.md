# Task #89 NW-7 — Source Type Controlled Vocabulary v0.1

**Status:** v0.1 draft (within-session; not yet externally reviewed). Mirrors NW-4 v0.4 pattern — Pass-1-owned controlled vocabulary for the `source_type` field, parallel to `domain`.
**Parent:** Task #89 (Component #1 Enrichment) v0.2.1 blueprint §9 (NW-7 placeholder)
**Lineage:** §9.1 placeholder list (17 entries) → this v0.1 refines + extends → v0.2 panel-fired → vN ratification
**Author:** Joseph + Claude (Coding Alter Ego)
**Date:** 2026-05-26
**Precondition for:** Task #89 implementation plan-lock (user call 2026-05-26)

---

## 0. Why NW-7

The `source_type` field of Pass-1's output schema is a **filter axis at query time** (per Task #89 v0.2.1 §2.1 + §2.3 tier ★★). It captures the publication-form shape of the raw source — written-prose vs transcript vs primary-document vs vault-meta — independent of substantive `domain`.

Like NW-4 (Domain), it is a Pass-1-owned controlled vocabulary: Pass-1 emits one ID per source; downstream (compile, GraphDB property indexing, query layer) reads the string value without semantic interpretation.

Until NW-7 ratifies, Pass-1 implementation is blocked on a placeholder. Joseph 2026-05-26: ratify NW-7 before Pass-1 implementation plan-lock so the Pass-1 prompt, output schema, and `kdb_compiler/config/source_types.json` reference a stable vocabulary that doesn't churn under implementation.

## 0.1 Changes from §9.1 placeholder

### Additions (4 new)
| ID | Why added |
|---|---|
| `book-summary` | Distinct from `book-chapter` — full-book distillation / chapter-by-chapter notes are a real ingestion shape (e.g., Blinkist-style summaries, user's own book-reading notes). Was missing from §9.1. |
| `documentation` | Software / product / API technical documentation — common ingestion candidate as the `ai-ml` domain matures and the KDB absorbs technical references. |
| `social-thread` | Substantive long-form social-media threads (Twitter/X, LinkedIn, Threads) — distinct from short posts; some of the user's investing / ai-ml ingestion candidates live here. |
| `wiki` | Encyclopedic / Wikipedia entries — distinct reference shape from blogs/articles; warrants its own filter. |

### Renames (1)
| Old ID | New ID | Reason |
|---|---|---|
| `transcript-youtube` | `transcript-video` | Medium-neutral. Transcripts can come from YouTube, Vimeo, Loom, or local video; the placeholder's YouTube specificity is incidental to the user's current intake. Alias preserved. |

### Drops (1)
| Candidate | Why dropped |
|---|---|
| `podcast` (audio + show notes, no transcript) | Without a transcript, the .md file's content IS show notes — which classifies as `post` or `article`. A "podcast without transcript" entry doesn't describe a distinct content shape; it describes the AUDIO source. Pass-1 sees text content; if a podcast was ingested without transcription, its text is show-notes-shaped. Drop the entry to avoid LLM mis-classification of show-notes-as-podcast. |

### Net count
v0.1 has **20 entries** (placeholder had 17; +4 new, -1 dropped = 20).

---

## 1. Settled framework (v0.1 — 5 decisions, mirroring NW-4 v0.4 D-NW4-1..5)

### D-NW7-1 — Flat source_type list, no hierarchical sub-types
Pass-1 LLM classifies each source into exactly **one** entry from the flat list. No `sub_type` field. The `transcript-X` family looks hierarchical but is a naming convention only — Pass-1 sees a flat enum of 20 IDs.

**Rationale:** Same as D-NW4-1. Hierarchies smuggle structural decisions into the prompt that the GraphDB query layer can synthesize cheaper.

### D-NW7-2 — Cross-cutting relationships are not pre-declared
The config does NOT declare how source_types relate to one another (e.g., "transcripts are spoken-form-originated, opposed to written-prose"). Cross-cuts emerge from query-layer aggregation if needed; they are not in the vocabulary config.

**Rationale:** [[feedback_no_edge_predeclaration_no_hints]]. Same discipline as D-NW4-5. Classification-disambiguation boundaries (§4) are rules, not edges.

### D-NW7-3 — Config schema (mirrors NW-4 v0.4 §7)
Per-entry: `id` + `display` + `scope` + `aliases`. Same 4-field shape as `domains.json`. File location: `kdb_compiler/config/source_types.json`.

### D-NW7-4 — `transcript-X` family: LLM picks most-specific
The 4 transcript entries (`transcript-podcast`, `transcript-video`, `transcript-interview`, `transcript-lecture`) form a naming family. LLM picks the most-specific fit. If a transcript is ambiguous between two (e.g., a video that's an interview), the format-of-recording wins (`transcript-video` over `transcript-interview`) — the underlying medium is more durable signal than the rhetorical mode.

**Boundary rule** in §4 makes this explicit.

### D-NW7-5 — `other` is last-resort + telemetry-monitored
`other` is the residual catch-all. Use ONLY when no specific entry in #1-19 fits. Same usage discipline as NW-4 `undecided`: high `other` rate indicates the vocabulary needs expansion (post-deployment telemetry; OQ-NW7-1).

---

## 2. The list — 20 source_types

Cluster groupings below are **for human readability of this document only**. Pass-1 LLM sees a flat list of 20 IDs (per D-NW7-1).

### 2.1 Written-prose cluster (10)

| # | ID | Display | Scope |
|---|---|---|---|
| 1 | `blog` | Blog Post | Personal blog post, technical blog, Substack newsletter, Medium piece, individual-authored writing on a personal or branded publication. Typically short to medium length (500-3000 words). |
| 2 | `post` | Online Post | Newsletter post, forum post, community-platform post (Reddit-style threaded discussion, HN-style comment), or generic online text not framed as a "blog post." Distinguished from `blog` by venue: blog = own publication; post = community / forum / aggregator. |
| 3 | `article` | Magazine / Long-form Article | Editorially-published magazine article, longform journalism piece, think-piece, or essay published through an editorial intermediary (The Atlantic, New Yorker, trade publication). Distinguished from `news`: article = analysis / argument / extended take; news = event reporting. |
| 4 | `news` | News Report | Event-reporting journalism: news article reporting facts of a current event, press release, market report. Distinguished from `article`: news = what happened; article = what to make of it. |
| 5 | `paper` | Academic / Research Paper | Peer-reviewed paper, preprint (arXiv, SSRN), working paper, conference paper, thesis, dissertation. Academic publication form regardless of subject. |
| 6 | `book-chapter` | Book Chapter / Excerpt | Verbatim chapter, section, or excerpt extracted from a longer book-length work. Distinguished from `book-summary`: chapter = verbatim source content; summary = distillation. |
| 7 | `book-summary` | Book Summary | Full-book distillation, chapter-by-chapter notes, or third-party summary of a book-length work (e.g., Blinkist-style abstracts, user's reading notes, executive summaries). The content is ABOUT a book, not FROM the book. |
| 8 | `letter` | Public Letter | Shareholder letter, public open letter, addressed correspondence intended for a defined audience and published as such (Buffett's letters, Bezos's letters, public open letters in trade publications). Distinguished from `email`: letter = curated, public-facing, addressed; email = informal, individual, private. |
| 9 | `documentation` | Technical Documentation | Software API documentation, product documentation, technical reference, tutorial, runbook, README. Structured technical reference content. |
| 10 | `wiki` | Wiki / Encyclopedic Entry | Wikipedia article, encyclopedia entry, knowledge-base reference article, fandom wiki page. Content authored in encyclopedic register (third-person, multi-source, citation-heavy). |

### 2.2 Spoken-medium-transcribed cluster (4)

| # | ID | Display | Scope |
|---|---|---|---|
| 11 | `transcript-podcast` | Podcast Transcript | Verbatim transcript of an audio podcast episode (host monologue, host + guest, or panel). When a podcast is also an interview format, prefer `transcript-interview` if Q&A structure dominates. |
| 12 | `transcript-video` | Video Transcript | Verbatim transcript of video content — YouTube video, recorded talk, Vimeo, Loom, local video. Medium-neutral. When a video is an interview format, prefer `transcript-interview` if Q&A structure dominates; when it's a lecture, prefer `transcript-lecture`. |
| 13 | `transcript-interview` | Interview Transcript | Q&A-structured transcript where one or more interlocutors question a primary subject. Format-driven, not medium-driven — applies whether the interview was originally podcast, video, written-Q&A, or in-person. |
| 14 | `transcript-lecture` | Lecture / Talk Transcript | One-direction educational delivery — academic lecture, conference talk, keynote, TED-style talk, public address. Distinguished from `speech`: lecture = transcribed-from-recording; speech = written-prose form of an address (often the prepared text, regardless of delivery). |

### 2.3 Primary-document cluster (3)

| # | ID | Display | Scope |
|---|---|---|---|
| 15 | `speech` | Speech / Address | Written-prose form of an address — prepared text of a speech, written speech, written address. Distinguished from `transcript-lecture`: speech = the text-form of the address (often the prepared text); transcript-lecture = transcribed-from-recording of delivered talk. |
| 16 | `social-thread` | Social Media Thread | Long-form thread or carousel on a social platform (Twitter/X long thread, LinkedIn post-with-thread, Threads multi-post). Substantive content authored in thread form; distinguished from `post` by platform and threaded structure. |
| 17 | `email` | Email | Forwarded or saved email correspondence, individual or distribution-list email content. Distinguished from `letter`: email = informal / individual / often private; letter = curated / public-facing. |

### 2.4 Vault-meta cluster (2)

These entries describe vault-internal source types that typically route to `noise` via `force_noise` path overrides (per Task #89 D-89-14). Source_type is still emitted by Pass-1 for completeness + audit + future use.

| # | ID | Display | Scope |
|---|---|---|---|
| 18 | `daily-note` | Daily Note / Log Entry | Obsidian Daily Note format — date-stamped vault page logging activities, reflections, todos. Typically diary-shaped. Routes to `noise` by default via `force_noise: [Daily Notes/**]` (D-89-14). |
| 19 | `meeting-notes` | Meeting Notes | User-generated meeting notes — attendee-recorded notes from a meeting, call, or working session. Distinguished from `transcript-interview`: meeting notes = user-summarized; transcript = verbatim. |

### 2.5 Residual (1)

| # | ID | Display | Scope |
|---|---|---|---|
| 20 | `other` | Other source form | Residual catch-all for source forms not covered by #1-19. Use ONLY when you can articulate in one sentence why none of #1-19 applies. If you cannot articulate that reason, re-examine #1-19 first. High `other` rate indicates the vocabulary needs expansion (OQ-NW7-1). |

---

## 3. Classification boundaries

Boundaries are classification disambiguation rules. They tell Pass-1 which `source_type` wins when content sits at an edge. They are NOT graph edges (per D-NW7-2).

### 3.1 `blog` ↔ `post` — venue type
- **`blog`** when the content is on a personal blog, branded blog, or single-author publication (own publication; Substack/Ghost/WordPress/Medium).
- **`post`** when the content is on a community / forum / aggregator (Reddit, HN, Twitter thread NOT in thread-form, generic web forum) — multi-author venue, not own publication.
- Substack newsletter on the author's own subdomain → `blog`. HN comment thread → `post`. Twitter long-thread → `social-thread` (more specific).

### 3.2 `article` ↔ `news` — analysis vs reporting
- **`article`** when the piece is analytical, argumentative, or extended take (think-piece, opinion column, longform feature).
- **`news`** when the piece reports facts of an event (who/what/when/where coverage, market report, press release).
- A "deep-dive analysis" feature article in WSJ → `article`. A WSJ news story about today's Fed announcement → `news`.

### 3.3 `transcript-podcast` ↔ `transcript-video` ↔ `transcript-interview` ↔ `transcript-lecture` — most-specific wins (per D-NW7-4)
- If Q&A structure dominates (interlocutor asks; primary subject answers) → **`transcript-interview`** regardless of recording medium.
- If one-direction educational delivery (single speaker teaching/presenting) → **`transcript-lecture`**.
- If neither Q&A nor lecture dominates AND the recording medium is identifiable: **podcast** = `transcript-podcast`; **video** = `transcript-video`.
- If transcript provenance is ambiguous → default to the recording medium (podcast vs video), not the rhetorical mode.

### 3.4 `book-chapter` ↔ `book-summary` — verbatim vs distillation
- **`book-chapter`** when the content IS the book's text (extracted chapter or section, verbatim).
- **`book-summary`** when the content is ABOUT the book (third-party summary, user's notes, distillation, abstract).
- A scanned-and-OCR'd PDF of a Munger essay → `book-chapter` (or `letter` depending on framing).
- "Poor Charlie's Almanack — Chapter 1 Summary" → `book-summary`.

### 3.5 `letter` ↔ `email` — public-curated vs private-informal
- **`letter`** for shareholder letters, public open letters, formally-addressed published correspondence (Buffett's annual letter).
- **`email`** for forwarded individual emails, saved newsletters in email format, list correspondence not framed as a "letter."
- The boundary lives at audience + curation: defined audience + intentional publication → `letter`; otherwise → `email`.

### 3.6 `speech` ↔ `transcript-lecture` — text-form vs transcribed-from-delivery
- **`speech`** when the source is the prepared written text of an address (often the speaker's notes or published prepared text — regardless of whether the speech was actually delivered).
- **`transcript-lecture`** when the source is a verbatim transcription of the delivered talk.
- A published "Speech to Congress, March 1933" → `speech`. The auto-generated YouTube transcript of a TED talk → `transcript-lecture`.

### 3.7 `wiki` ↔ `article` — encyclopedic vs editorial
- **`wiki`** when authored in encyclopedic register — third-person, multi-source citations, neutral tone (Wikipedia, fandom wikis, internal knowledge-base entries).
- **`article`** when authored editorially — author voice, argument, analysis (magazine longform, think-piece).
- Wikipedia article on Buffett → `wiki`. New Yorker profile of Buffett → `article`.

### 3.8 `social-thread` ↔ `post` — threaded substance vs single-post
- **`social-thread`** when the content is a multi-tweet thread, LinkedIn post-plus-thread, or Threads multi-post, with substantive long-form content across the thread.
- **`post`** when the content is a single forum / community post (Reddit comment, HN response, single-tweet).

### 3.9 `transcript-interview` ↔ `meeting-notes` — verbatim vs user-summarized
- **`transcript-interview`** when the source is a verbatim transcription of a Q&A interview.
- **`meeting-notes`** when the source is user-summarized notes from a meeting / call (paraphrased, abbreviated, action-item-shaped).
- Test: would the source be reconstructable verbatim from the file? Yes → `transcript-*`; No (compressed by note-taker) → `meeting-notes`.

---

## 4. Explicit drops (candidates considered, not in v0.1)

| Candidate | Why dropped |
|---|---|
| **`podcast` (audio-only, no transcript)** | Without transcript, source content IS show notes (classifies as `post` or `article`). Audio-only podcast as a source-type entry describes the AUDIO not the text; redundant. Per §0.1 drop rationale. |
| **`pdf`** | PDF is a container format, not a source type — a PDF can be a paper, book-chapter, letter, etc. Source-type captures content shape, not file format. |
| **`audio` / `video`** (no-transcript variants) | Same as `podcast` — Pass-1 sees text content; if a video/audio was ingested without transcription, the text content is whatever-the-text-is. The MEDIA format isn't a source_type. |
| **`presentation` / `slide-deck`** | Plausible but rare for user's vault ingestion patterns; defer to telemetry-driven add (OQ-NW7-2). |
| **`legal-document` / `contract`** | Specialized; not in user's typical ingestion patterns; defer. |
| **`code-snippet` / `gist`** | Pass-1 doesn't typically ingest code; if needed, `documentation` covers structured technical content. |
| **`thread-twitter` / `thread-linkedin` / per-platform variants** | Consolidated to single `social-thread`; platform is incidental to the content shape. |
| **`book` (full book)** | If a full book is ingested as a single file, treat as `book-chapter` (a long one) or split via Component #2 (Source Storage) before ingestion. v1 doesn't ship `book` because it conflates "the source unit" question with "the content shape" question. |
| **Quote-collection variant** | NW-4's `domain: quotes` covers this on the substantive-classification axis; source_type-side a quote-collection .md file → whatever its publication form is (typically `post` or `wiki`-ish curation). |
| **`recipe`** | Not in user's vault patterns; if it appears, `post` or `wiki` covers. |
| **`research-note` / `equity-research-report`** | These describe `domain: personal-finance` content; the source-form is typically `paper` (long) or `post` (short). source_type captures shape; analysis-type lives elsewhere. |

---

## 5. Config schema (D-NW7-3 — mirrors NW-4 v0.4 §7)

### Ownership clarification
The config is the **Pass-1 source of truth** for the controlled vocabulary. Everything downstream (Pass-2, GraphDB property indexing, query layer) reads the resulting `source_type` string value — only Pass-1 needs scope descriptions for prompt-context rendering.

### Per-entry — 4 fields

```json
{
  "id": "transcript-video",
  "display": "Video Transcript",
  "scope": "Verbatim transcript of video content — YouTube video, recorded talk, Vimeo, Loom, local video. Medium-neutral. When a video is an interview format, prefer `transcript-interview` if Q&A structure dominates; when it's a lecture, prefer `transcript-lecture`.",
  "aliases": ["transcript-youtube"]
}
```

| Field | Type | Purpose |
|---|---|---|
| `id` | string, kebab-case, unique | Canonical identifier used in Pass-1 output schema, GraphDB property values, query layer |
| `display` | string, Title Case | Human-facing name for UI / docs / display contexts |
| `scope` | string, prose paragraph | Content-only description of what classifies here. **No "for example" hints. No edge declarations.** (Enforces D-NW7-2.) |
| `aliases` | array of strings, optional | Historical IDs that resolve to this current ID at query time. Enables rename migration without backfill. |

### What the config does NOT hold (anti-pattern per D-NW7-2)
- ❌ Inclusion / exclusion examples
- ❌ Boundary-pair declarations (those live in §3 of this doc, not in the LLM-consumed config)
- ❌ Expected-rollup-cluster (smuggles hierarchy)
- ❌ Prompt-rendering text (the prompt template is its own artifact; the config feeds it raw scopes)
- ❌ Cross-cut hints

### Consumed by (Pass-1 owns; downstream reads values)
- **Pass-1 LLM prompt rendering** — scope descriptions injected into the classification prompt
- **Pass-1 output schema** — `source_type` field validated as enum over current IDs (aliases NOT accepted on write; only on read)
- **GraphDB property indexing** — `Source.source_type` (existing column per Task #89 §10.4) indexed for query (no semantic interpretation — just string property)
- **Query layer** — alias resolution at read time so historical sources resolve to current IDs
- **Pass-2 (compile)** — reads `source_type` as a string property per Task #89 D-89-17; does not require config scope descriptions for its ontology operations

### Aliases needed for v0.1 renames

```json
[
  { "id": "transcript-video", "aliases": ["transcript-youtube"] }
]
```

### File location (v1)
`kdb_compiler/config/source_types.json` — single source of truth; all consumers read from it. Mirrors `kdb_compiler/config/domains.json` (NW-4).

---

## 6. Open questions

### OQ-NW7-1 — `other` rate KPI threshold (post-deployment)
Telemetry-driven. Threshold analog to NW-4's OQ-NW4-13 (`undecided` < 5% per rolling 100-source window). Specific threshold deferred to NW-5 (Pass-1 benchmark).

### OQ-NW7-2 — Specialized source-type telemetry watch
Monitor `other` classifications post-deployment for clustering patterns (e.g., if many sources end up classified `other` because they are presentations, surface `presentation` for ratification). Watch list: `presentation`, `legal-document`, `chat-log`, `bookmarks-page`. Re-open vocabulary deliberation if cluster density > N sources / month.

### OQ-NW7-3 — Cross-source-type ↔ domain interactions
v0.1 explicitly does NOT couple source_type to domain (per D-NW7-2 no pre-declaration). But empirical correlations may emerge (e.g., `transcript-lecture` strongly correlates with `domain: ai-ml` or `domain: value-investing`). These should remain query-layer aggregations, not config declarations. Watch for whether Pass-1 LLM tries to use one to inform the other inappropriately (e.g., classifying everything from a finance podcast as `value-investing` regardless of actual content).

### OQ-NW7-4 — `social-thread` durability
Social-media-platform content is link-rot-prone (deleted threads, account suspensions). When a `social-thread` is ingested, the source markdown is the only durable copy. Should source_type carry a flag for "platform-hosted-original-may-disappear"? Provisional: NO — Pass-1 is for source enrichment; durability is a Component #2 (Source Storage) concern. Re-open if loss patterns surface.

### OQ-NW7-5 — Authority-axis tagging (deferred v0.2+)
NW-4 v0.4 added boundary axes (D-NW4-6: vertical/horizontal/temporal). The analog for NW-7 could be an authority axis (peer-reviewed > editorial > personal > primary-source > vault-meta) which the query layer could use to weight evidence. v0.1 explicitly DOES NOT introduce this — would smuggle ranking decisions into the controlled vocabulary. Leave for telemetry-driven re-open if needed.

---

## 7. Versioning

- **v0.1** — this document. Initial 20-entry list (within-session; not externally reviewed). Refines + extends the §9.1 placeholder. 4 new entries (`book-summary`, `documentation`, `social-thread`, `wiki`); 1 rename (`transcript-youtube` → `transcript-video`); 1 drop (`podcast`).
- **v0.2** — pending. Joseph's internal review of v0.1; folds his redirects / catches before external panel dispatch.
- **v0.3** — pending. Folds 5-reviewer external panel feedback (Codex + Qwen CLI + Grok Build + Deepseek + Gemini Pro DR — per `docs/external-review-panel.md` post-2026-05-22 composition).
- **v0.4** — pending (if needed). Joseph's review of v0.3 → final ratification. v0.4 is production-ready vocabulary.
- **Post-ratification iteration** — operational telemetry-driven (OQ-NW7-1 through 5) once Component #1 ships and live ingestion produces real distribution data.

---

## 8. Anchors

- Task #89 v0.2.1 blueprint §9 — original placeholder + NW-7 framing
- Task #88 NW-4 v0.4 (`docs/task88-nw4-domain-list-v0.4.md`) — sibling controlled-vocabulary precedent
- `docs/external-review-panel.md` — 5-reviewer panel composition + flow
- [[feedback_no_edge_predeclaration_no_hints]] — drives D-NW7-2 + scope-text discipline
- [[feedback_concrete_first_extract_later]] — drives 20-entry concrete-first vocabulary (vs designing axes upfront per OQ-NW7-5)
- [[feedback_post_llm_deterministic_override]] — `source_type` is content-only judgment; no path-based override (unlike `kdb_signal`)

---

**END OF NW-7 v0.1 DRAFT**
