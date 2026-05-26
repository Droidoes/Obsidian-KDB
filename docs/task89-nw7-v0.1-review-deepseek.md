# NW-7 v0.1 Source Type Controlled Vocabulary — Review (Deepseek)

**Reviewer:** deepcode CLI (Deepseek)
**Date:** 2026-05-26
**Artifact reviewed:** `docs/task89-nw7-source-type-list-v0.1.md`
**Supporting docs:** Task #89 v0.2.1 blueprint §9, NW-4 v0.4 (sibling precedent), external-review-panel.md

---

## Convergence

The structural mirroring of NW-4 v0.4 is well-executed. The same flat-no-hierarchy posture (D-NW7-1 mirrors D-NW4-1), the same no-edge-pre-declaration discipline (D-NW7-2 mirrors D-NW4-5), the same 4-field config schema (§5 mirrors NW-4 §7), and the same catch-all-with-telemetry pattern (`other` / `undecided`). This consistency across the two controlled vocabularies is architecturally clean — Pass-1 implementation handles `domain` and `source_type` identically at the schema level, which reduces prompt-design surface area.

The `podcast` drop (§0.1) is correctly reasoned. Without a transcript, the .md file's text IS show notes — classifying show-notes-as-podcast would train the LLM to ignore what the text actually contains. The drop tightens the vocabulary.

The `transcript-youtube` → `transcript-video` rename is the right generalization and the alias is preserved (§5). YouTube-specific naming was incidental to Joseph's current intake; medium-neutral naming is future-proof for Vimeo/Loom/local-video ingestion.

The four additions (§0.1) each fill genuine gaps in the placeholder: `book-summary` captures a real ingestion shape (the user's reading notes are a distinct content pattern from verbatim chapters); `documentation` is forward-looking for the `ai-ml` domain maturing; `social-thread` addresses the threaded-long-form pattern on social platforms; `wiki` captures the encyclopedic register that's neither blog nor article.

---

## Findings

### Finding F-1: D-NW7-4 contradicts §3.3 on interview-on-video classification precedence

D-NW7-4 states:

> If a transcript is ambiguous between two (e.g., a video that's an interview), the format-of-recording wins (`transcript-video` over `transcript-interview`) — the underlying medium is more durable signal than the rhetorical mode.

§3.3 states:

> If Q&A structure dominates (interlocutor asks; primary subject answers) → **`transcript-interview`** regardless of recording medium.

These two rules give opposite answers for the same case. An interview conducted on video with clear Q&A structure: D-NW7-4 says `transcript-video` (medium wins); §3.3 says `transcript-interview` (Q&A structure wins regardless of medium). The scope descriptions reinforce §3.3: `transcript-interview`'s scope says "Format-driven, not medium-driven — applies whether the interview was originally podcast, video, written-Q&A, or in-person"; `transcript-video`'s scope says "When a video is an interview format, prefer `transcript-interview` if Q&A structure dominates."

The scope descriptions and §3.3 are consistent with each other (rhetorical mode wins). D-NW7-4 is the outlier. The D-NW7-4 text uses "ambiguous between two" as a qualifier — suggesting the medium-wins rule applies only when Q&A structure does NOT clearly dominate. But the example given ("a video that's an interview") is the canonical case where Q&A DOES dominate, making the example actively misleading.

**Recommendation:** Revise D-NW7-4 to match §3.3 and the scope descriptions. The correct precedence is: (1) Q&A dominates → `transcript-interview`; (2) one-direction educational delivery → `transcript-lecture`; (3) neither dominates AND medium identifiable → medium-based (`transcript-podcast` or `transcript-video`). The D-NW7-4 text should state this explicitly and the example should be replaced with a genuine ambiguity case (e.g., "a conversational podcast with occasional Q&A segments, where neither interview nor monologue format dominates").

### Finding F-2: `blog` ↔ `post` venue-based distinction breaks on straddling platforms

§3.1 defines the boundary as venue-based: own publication → `blog`; community/forum/aggregator → `post`. This breaks on platforms that combine both:

- **Medium**: A writer publishes on their own Medium page (`blog` by the own-publication rule) but Medium is also an aggregator platform with editorial curation. Does the platform's aggregator nature override the own-publication framing?
- **Substack with community features**: Substack now has Notes (Twitter-like) and threaded comments. A Substack newsletter is `blog`, but a Substack Note is `post` or `social-thread`. The LLM needs to distinguish the publication surface, not just the platform domain.
- **GitHub Discussions**: Long-form, threaded, substantive — but it's a community forum, so `post`. Yet a GitHub Discussion can be as substantive as a blog post.

The venue axis is clear in principle but the LLM must infer venue from content + any available metadata. If the source file contains only the body text (no URL, no platform metadata), the venue signal may be absent entirely.

**Recommendation:** Add a fallback rule for §3.1: when venue cannot be determined from content alone, classify by **authorial stance**: single-author, framed as a self-contained piece → `blog`; response-to-community, framed as participation in a discussion → `post`. This gives the LLM a content-only fallback when venue metadata is unavailable.

### Finding F-3: Scope descriptions embed boundary-pair declarations that §5 anti-pattern list appears to forbid

§5's config schema anti-pattern list includes:

> ❌ Boundary-pair declarations (those live in §3 of this doc, not in the LLM-consumed config)

But the scope descriptions in §2 — which ARE LLM-consumed (injected into the classification prompt per §5 "Pass-1 LLM prompt rendering") — contain boundary-pair declarations:
- `book-chapter` scope: "Distinguished from `book-summary`: chapter = verbatim source content; summary = distillation."
- `speech` scope: "Distinguished from `transcript-lecture`: speech = the text-form of the address"
- `social-thread` scope: "distinguished from `post` by platform and threaded structure"
- `transcript-podcast` scope: "When a podcast is also an interview format, prefer `transcript-interview` if Q&A structure dominates"

These are classification-disambiguation hints embedded in scope descriptions. They are NOT cross-cut hints (they don't declare how types relate categorically) — they're boundary rules relocated from §3 into the LLM's view. The question is whether this violates D-NW7-2's "no pre-declared cross-cuts" or is permitted as classification disambiguation.

The NW-4 v0.4 precedent: NW-4's scope descriptions do NOT contain "prefer X over Y" or "distinguished from Y" language. NW-4 keeps boundary rules in §4 only; the scope descriptions describe what content lives in the domain without referencing other domains. Examples: `value-investing` scope is "Investment philosophy, methods, mental models in the Buffett / Munger / Li Lu / Pabrai tradition" — no mention of `personal-finance` or `economy-markets`.

**Recommendation:** Either (a) strip boundary-pair references from scope descriptions and rely on §3 for all disambiguation (consistent with NW-4 v0.4 precedent), or (b) revise the §5 anti-pattern text to clarify that classification-disambiguation references to sibling entries ARE permitted in scope descriptions (they're rules, not cross-cut declarations). Option (a) is cleaner and avoids the LLM over-weighting the boundary hints relative to its own content judgment.

### Finding F-4: Written-Q&A interview has no clear home

`transcript-interview` scope says: "Format-driven, not medium-driven — applies whether the interview was originally podcast, video, written-Q&A, or in-person." This explicitly includes written Q&A as an `transcript-interview`. But a written Q&A (e.g., a journalist's email Q&A with a subject, published as text) is not a transcript — it IS the original text. Calling it a `transcript-*` is misleading: nothing was transcribed.

The `transcript-interview` scope's "written-Q&A" inclusion stretches the `transcript-` prefix beyond its semantic range. The LLM may resist classifying a written Q&A as a `transcript-*` because the word "transcript" implies a conversion from spoken to written form.

**Recommendation:** Two paths: (a) add a new entry `interview-written` for text-native Q&A interviews, keeping `transcript-interview` for transcribed-from-spoken; or (b) broaden `transcript-interview`'s display name to "Interview (any medium)" and adjust the ID to `interview` (with `transcript-interview` as an alias). Path (b) is less disruptive to the 20-entry count and avoids fragmenting the interview family. Path (a) is semantically cleaner but adds an entry for a potentially rare type.

### Observation O-1: `social-thread` ↔ `post` boundary rests on threading — a structural feature the LLM may not perceive

§3.8 distinguishes by "threaded structure" and "substantive long-form content across the thread." But the LLM sees only the concatenated text of the source — it may not perceive whether the original was threaded. A long Reddit post and a Twitter thread, both presented as markdown in the vault, look identical to the LLM: a block of text. The LLM would need to infer threading from cues like "1/" numbering, "🧵" emoji, or platform metadata in the frontmatter. If those cues are absent, the distinction collapses.

**Observation O-2:** `daily-note` and `meeting-notes` in §2.4 reference `force_noise` / D-89-14 — coupling the vocabulary to a specific Task #89 decision that could change. If a future v0.3 removes `Daily Notes/**` from `force_noise`, the scope descriptions become stale. The coupling is descriptive ("Routes to noise by default"), not prescriptive, so it's low-risk — but worth flagging.

**Observation O-3:** The `presentation` / `slide-deck` drop (§4) defers to OQ-NW7-2 telemetry. But if Joseph starts ingesting slide decks (e.g., conference presentations from AI/ML or value-investing conferences), the nearest classification is `documentation` (structured technical reference) — which is a poor fit for a persuasive slide narrative. This is correctly deferred but the gap is real enough to mention.

---

## Recommendations

### Recommendation R-1: Fix the D-NW7-4 / §3.3 contradiction (addresses F-1)

Rewrite D-NW7-4 to state the actual precedence: rhetorical mode (interview > lecture) before recording medium (podcast > video). Replace the misleading example.

### Recommendation R-2: Strip boundary-pair references from scope descriptions (addresses F-3)

Remove "Distinguished from X" and "prefer Y over Z" language from scope descriptions in §2. Relocate all disambiguation to §3 boundary rules. This keeps scope descriptions as pure "what content lives here" descriptions, consistent with NW-4 v0.4 precedent and the §5 anti-pattern list.

### Recommendation R-3: Clarify the written-Q&A interview home (addresses F-4)

Either add `interview-written` as a new entry or broaden `transcript-interview` to a medium-neutral `interview` ID. Leaning toward the latter: the `transcript-` prefix is the implementation detail, not the classification concept.

### Recommendation R-4: Add venue-fallback rule for `blog` ↔ `post` (addresses F-2)

When venue metadata is absent from the source content, classify by authorial stance (self-contained piece → `blog`; community-participation → `post`).

---

## Concrete Classification Probes

**Probe 1:** *A YouTube auto-transcript of a 2-hour Joe Rogan interview with an AI researcher.* Content is Q&A-structured verbatim transcript. Q&A dominates → `transcript-interview` (per §3.3 / F-1 corrected rule). The recording medium (video) is overridden by the interview format. ✓ Clean.

**Probe 2:** *A journalist's published written Q&A with Li Lu, conducted via email, published as text on a financial blog.* Not a transcript — it IS the original text. Under current v0.1, `transcript-interview` is the nearest home (per its "written-Q&A" scope), but the `transcript-` prefix is misleading. Classification: `transcript-interview` by current rules, but semantically strained. This is F-4's pressure case. (If R-3 is adopted, classify as `interview` or `interview-written`.)

**Probe 3:** *A long-form Twitter thread by a semiconductor analyst, saved as a single .md file, analyzing TSMC's Q2 results.* Threaded structure, substantive content, social platform → `social-thread`. If the thread formatting cues (1/, 🧵) are preserved in the markdown, classification is clean. If the thread was concatenated without formatting cues, the LLM sees a long-form analysis and may classify as `article` or `post`. This is O-1's fragility.

**Probe 4:** *The prepared text of Buffett's 2023 shareholder letter, downloaded from Berkshire's website.* Written-prose form of a public address, curated and public-facing → `letter` (per §2.1 #8). Clean classification — the content IS the letter, verbatim.

**Probe 5:** *A heavily-annotated book chapter from Kahneman's "Thinking, Fast and Slow" — the user pasted the chapter text and interleaved their own commentary in blockquotes throughout.* The dominant nature is verbatim chapter text with user annotations woven in. If the original chapter text is the majority by volume → `book-chapter` (the annotations are marginalia on a verbatim excerpt). If the commentary dominates by volume and the chapter text serves as scaffolding for the user's analysis → `book-summary` (it's ABOUT the book). This is the §3.4 pressure test — the boundary works but the LLM must judge proportional dominance, which is a genuine cognitive task.

---

## Open Questions

**OQ-DS-NW7-1:** Does the `transcript-` prefix family carry semantic weight that constrains the LLM? If the LLM reads `transcript-interview` and the source is a written Q&A (never transcribed), will it resist the classification because "transcript" implies speech-to-text conversion? This is the same concern as F-4 but framed as a prompt-psychology question — worth testing in NW-5 benchmark scenarios.

**OQ-DS-NW7-2:** `chat-log` as a future entry — the OQ-NW7-2 watch list includes it. ChatGPT conversation exports are a growing ingestion surface for the `ai-ml` domain (prompt-engineering examples, model behavior logs). Should `chat-log` be added proactively in v0.2 rather than waiting for telemetry? The counterargument: no empirical evidence Joseph ingests chat logs today. The pro argument: the `ai-ml` domain is growing and chat logs are a natural ingestion candidate that `social-thread` (public) and `post` (community) don't cover well.

**OQ-DS-NW7-3:** The `article` ↔ `news` boundary (§3.2) uses "analysis vs reporting" as the discriminator. But some journalism blends both — a news analysis piece that reports facts AND interprets them. The boundary rule says article = "what to make of it," which includes news-with-analysis. Is this intentionally asymmetric (news-analysis hybrid → `article`), or should there be a "dominant mode" tiebreaker?
