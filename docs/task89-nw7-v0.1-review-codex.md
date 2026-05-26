# Codex Review — Task #89 NW-7 Source Type Vocabulary v0.1

## Findings

**Finding F-1:** D-NW7-4 is internally inconsistent across §1, §2.2, and §3.3.

The framework decision says recording medium wins when a transcript could be both medium-classified and rhetorical-mode-classified:

> format-of-recording wins (`transcript-video` over `transcript-interview`)

But the scope text for `transcript-podcast` / `transcript-video` and §3.3 say Q&A or lecture structure can override the recording medium. These are different classifier contracts. If Pass-1 receives both versions, it will oscillate on common cases like a YouTube interview, podcast interview, conference keynote video, or recorded classroom lecture.

This is the only issue I would treat as blocking before v0.2: choose one precedence rule and express it once. My recommendation is:

**Recommendation:** Make rhetorical form win when it is strong, and use recording medium only as fallback:

- Q&A-dominant transcript -> `transcript-interview`
- One-direction teaching / talk transcript -> `transcript-lecture`
- Otherwise, identifiable audio podcast -> `transcript-podcast`
- Otherwise, identifiable video -> `transcript-video`

That preserves the useful specific forms and avoids losing the most important query-time distinction: "show me interviews" should find interviews regardless of whether the recording was audio or video. If Joseph wants medium to win instead, then §2.2 and §3.3 should be rewritten to remove the Q&A / lecture overrides.

**Finding F-2:** The scope-text discipline in §5 is stricter than the actual §2 scopes.

§5 says config scopes have no inclusion/exclusion examples, boundary-pair declarations, or cross-cut hints. Several §2 scope strings would violate that if copied directly into `source_types.json`:

- `post` says it is distinguished from `blog` by venue.
- `article` says it is distinguished from `news`.
- `book-chapter`, `book-summary`, `letter`, `daily-note`, and `meeting-notes` all include neighboring-type disambiguators.
- `transcript-video` lists platform examples and points to interview / lecture overrides.

This is not fatal to the vocabulary, but it is a config-contract drift. Either §5 should explicitly allow short disambiguators in scope text, or the eventual JSON scopes should be stripped down to pure inclusion language and all tie-breakers should live only in §3.

**Recommendation:** Keep `source_types.json` scopes terse and non-relational; render §3 boundary rules separately in the Pass-1 prompt template. That matches the sharpened "examples-for-shape OK; examples-for-edges NOT" rule without making the config carry prompt logic.

**Finding F-3:** `blog` vs `post` has a concrete overlap: newsletters.

§2.1 classifies "Substack newsletter" under `blog`, while `post` includes "Newsletter post." §3.1 resolves Substack-on-own-publication to `blog`, but the list row still leaves an LLM-consumed ambiguity.

**Recommendation:** Remove "Newsletter post" from the `post` scope unless the intended meaning is "newsletter content saved as an email artifact." If that is intended, it belongs in the `email` boundary, not as a general `post` example. The stable axis should be venue/ownership:

- Own publication / branded author feed -> `blog`
- Community, forum, aggregator, or platform discussion item -> `post`
- Saved inbox artifact -> `email`

**Finding F-4:** `chat-log` is materially different enough to add now or make the primary telemetry watch.

The §6 watch list includes `chat-log`, but a Slack/Discord export or ChatGPT/Claude conversation export is not well-covered by `email`, `post`, `meeting-notes`, or `transcript-interview`. It is multi-turn, private or semi-private, often tool-mediated, and frequently contains mixed user/assistant authorship. This project is highly likely to accumulate AI conversation exports as source material.

**Proposal:** Add `chat-log` in v0.2 unless Joseph has empirical reason it is rare. Suggested scope: "Multi-turn chat conversation or messaging export, including Slack, Discord, Google Chat, or AI assistant conversation transcripts." This does not introduce hierarchy or authority; it captures a distinct source form.

**Finding F-5:** `other` has the right conceptual guardrail but no operational tripwire.

D-NW7-5 says high `other` rate signals expansion, and OQ-NW7-1 defers the threshold. Given NW-4 already has the `<5% per rolling 100-source window` precedent, leaving NW-7 threshold fully deferred weakens the implementation precondition.

**Recommendation:** Copy the NW-4 provisional threshold into NW-7 as a non-fatal benchmark target: `other < 5% per rolling 100 enriched sources`, with clustered `other_reason` examples reviewed before vocabulary expansion. Do not fail individual Pass-1 calls just because they return `other`; that would turn a telemetry signal into a brittle ingest blocker.

## Convergence

The core framework holds. A flat, single-label `source_type` enum is the right level for Pass-1, and the 4-field config shape stays consistent with NW-4. The decision not to encode source-type relationships in config is also sound; query-layer aggregation can later synthesize "spoken-originated", "primary-document", or "vault-meta" views without making those relationships part of the controlled vocabulary.

The `podcast` drop is defensible. Pass-1 sees markdown text, not audio. If the file is a transcript, `transcript-podcast` applies; if it is show notes, the text shape is usually `blog`, `post`, `article`, or possibly `documentation` depending on structure. A bare `podcast` entry would invite the LLM to classify by source provenance rather than file content.

`book-summary`, `documentation`, `social-thread`, and `wiki` are good additions. They represent real source forms rather than domain leakage. `wiki` especially prevents encyclopedic reference material from being forced into `article`.

## Additional Observations

**Observation O-1:** The `social-thread` cluster placement is harmless because clusters are document-only, but I would move it mentally toward written-prose rather than primary-document. "Platform-hosted original" is a provenance fact, not the same kind of primary-document status as `speech`, `letter`, or `email`.

**Observation O-2:** `speech` vs `transcript-lecture` is stable if the classifier follows the source artifact, not the historical event. Prepared text -> `speech`; verbatim delivered transcript -> `transcript-lecture`; a combined source should classify by the dominant body or be split upstream.

**Observation O-3:** `wiki` vs `article` is stable enough if publication venue remains part of the judgment. A heavily cited New York Review of Books essay should still be `article`; encyclopedic tone alone should not override editorial publication form.

**Observation O-4:** `daily-note` and `meeting-notes` should stay separate. They reflect different user workflows and likely different false-positive patterns under `force_noise`. Add a boundary rule for daily notes that contain meeting sections: if the file is a date-stamped omnibus log, `daily-note`; if the file is a single meeting artifact, `meeting-notes`.

**Observation O-5:** Authority-axis deferral is correct. However, the docs should explicitly warn downstream consumers not to treat `paper > article > blog` as an evidence-quality ordering. `source_type` is a filter axis, not an authority score.

## Concrete Classification Probes

1. "Acquired Podcast: Costco episode transcript" -> `transcript-podcast` unless the content is dominated by host interviewing one primary subject, in which case under my recommended rule it becomes `transcript-interview`.

2. "YouTube transcript: Patrick Collison interviews Jensen Huang" -> ambiguous under v0.1 because D-NW7-4 and §3.3 conflict. Under my recommendation: `transcript-interview`.

3. "Federal Reserve Chair prepared remarks, official PDF" -> `speech`. If the file is the stenographic hearing transcript with Q&A, it should not be `speech`; it likely becomes `transcript-interview` or a future `hearing-transcript` if telemetry justifies it.

4. "Substack essay from an author's own publication" -> `blog`. A Substack email as saved from Gmail could still be `blog` if the body is the published essay; classify as `email` only when the email artifact itself is the source form.

5. "ChatGPT export: conversation analyzing GraphDB schema tradeoffs" -> no clean v0.1 home. `other` is honest, but repeated cases should promote `chat-log`.

## Open Questions

**OQ-Codex-1:** Should `chat-log` be added before implementation, given this project's likely AI-conversation intake, or deliberately forced through `other` for the first telemetry window?

**OQ-Codex-2:** Should Pass-1 prompt rendering include both config scopes and boundary rules, or only config scopes? If both, the implementation needs a clear source of truth so scope text and boundary text cannot drift.

**OQ-Codex-3:** Should `other` require a structured `other_reason` in the Pass-1 envelope? The current source schema does not include it, but without it the telemetry loop will be harder to diagnose.

