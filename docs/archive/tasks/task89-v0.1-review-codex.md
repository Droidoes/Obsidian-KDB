# Task #89 v0.1 Architecture Review — Codex

## Convergence

The blueprint's basic component boundary is sound: Pass-1 enriches source markdown and writes replayable filesystem artifacts; compile remains the graph producer in v1; GraphDB continues to be the live ontology authority rather than a second place for unproven Pass-1 semantics.

The strongest parts are §3's in-place frontmatter design, §5's replay sidecar posture, §8's content-only `kdb_signal` criteria, and §10's refusal to let Pass-1 write GraphDB Source-level data before the enrichment artifact has empirical proof. That stance aligns with the producer contract's producer/adapter/core boundary and with JOURNEY's D49-D51 lesson: avoid competing ontology authorities and keep recovery/replay explicit.

## Findings

F-1 — §4.2 / D-89-4 conflicts with parent blueprint D-88-11 on Daily Notes.

The parent blueprint says Daily Notes are in scope and processed by Pass-1, with the LLM rejecting diary/meta content by content substance. Task #89 changes the default to `force_noise: [Daily Notes/**, Projects/**]`, which means every Daily Note is deterministically routed to `noise` after the LLM call. That preserves "read and run Pass-1" mechanically but defeats the parent decision's intended value: Daily Notes can contain source-worthy observations that the user wanted enhanced.

**Recommendation:** Remove `Daily Notes/**` from the default `force_noise` list, or narrow it to a more explicit user-owned pattern if the intent is only to suppress known planning/log subtrees. Keep `Projects/**` separate; it has a different risk profile and was not the subject of D-88-11.

F-2 — §4.3 pseudocode contradicts §4.4 override precedence.

§4.4 says blacklist wins ties, but §4.3 checks `force_signal` before `force_noise`. A path matching both lists would return `signal`, not `noise`.

**Recommendation:** Swap the pseudocode order so `force_noise` is evaluated first, or change §4.4 if whitelist precedence is intended. The text and algorithm need to match before implementation.

F-3 — §5.1 empty-source handling does not satisfy the required schema in §2.

§5.1 says empty sources skip Pass-1 and emit `kdb_signal: noise` directly with `reject_reason: "empty source"`. §2 requires `domain`, `source_type`, `author`, `summary`, `key_entities`, `key_themes`, `confidence`, `uncertainty_reason`, `prompt_version`, `model`, and `schema_version`. The blueprint does not define deterministic placeholder values for these fields or a separate skip envelope.

**Recommendation:** Add an explicit deterministic "skipped-empty" envelope with all required schema fields populated, or define `enrich_skipped` as no frontmatter write plus journal-only audit. The latter is cleaner if empty files should not receive synthetic semantic metadata.

F-4 — §5.3 sidecar pathing is underspecified for vault-relative `source_id` values.

The sidecar path is `state/ingest_runs/<run_id>/<source_id>.json`, while examples use source IDs like `Investing/Buffett-letter-2020`. Vault-relative paths can contain slashes, duplicate basenames, spaces, extension differences, and characters that are inconvenient as JSON filenames. Without a canonical encoding rule, replay lookup and source movement audits can become ambiguous.

**Recommendation:** Define sidecar addressing as either a hash-addressed filename plus source metadata inside the JSON, or an escaped path convention with a documented bijection. This is contract-level because replay determinism depends on locating the exact archived envelope.

F-5 — §6 Options A/C require a corpus snapshot, but the snapshot contract is not specified.

Options A and C correctly say replay must archive the corpus snapshot used in the LLM call. The blueprint does not define snapshot granularity, ordering, truncation, filtering, or hash identity. If the corpus index is later regenerated from current frontmatter, replay will not reproduce the original LLM input.

**Recommendation:** If A or C is chosen, add a minimal corpus-index snapshot contract to §5.3: selected entries, ordering, selection rule, source content/frontmatter hashes, and prompt-budget truncation metadata. This can stay small, but it must be archived as input evidence.

F-6 — §6 Option C's `grounded_in_corpus: false` example weakens the stated grounding rule.

§6.1 says grounded suggestions should not invent connections and should not suggest wikilinks for entities not seen in corpus. Option C then includes `grounded_in_corpus: false` as a useful candidate-new-entity signal. That is a different product: entity candidate extraction, not grounded wikilink suggestion.

**Recommendation:** For v1, keep `wikilink_suggestions` corpus-grounded only. Candidate new entities are already represented by `key_entities`; compile/Pass-2 can decide whether they become graph entities.

F-7 — §10.4 says compile can use frontmatter later, but #89 does not define the minimum compile-entry contract for `kdb_signal`.

The parent blueprint includes a Pass-1 gate at compile entry. Task #89 explains that signal flows to compile and noise stops, but it does not specify where that routing contract lives: source scanner, planner, compiler entrypoint, or orchestrator. This matters because v1 says no compile changes are required, while Pass-1 routing does require some consumer to respect `kdb_signal`.

**Recommendation:** Add a short contract statement: Component #3 or Component #6 filters compile candidates to `kdb_signal=signal`; compile itself may remain unchanged for v0.1. That preserves the "no compile changes required" claim without leaving the gate owner implicit.

## Open questions

OQ-1 — Should `force_noise` ever override a high-confidence LLM `signal`, or should such cases be routed to an audit queue?

OQ-2 — If a previously `noise` source becomes `signal` after content edits, does Component #3 requeue it for compile immediately, or only on the next orchestrator run?

OQ-3 — For Options A/C, what is the corpus-index selection rule once the full index exceeds prompt budget: same domain only, top-N lexical/entity overlap, recent sources, or deterministic hybrid?

OQ-4 — Does re-enrichment preserve user-authored frontmatter keys that collide semantically but not syntactically with Pass-1 fields, such as `tags`, `aliases`, or `summary`?

OQ-5 — Should `enrich_failed` write no source frontmatter, or write an audit-only frontmatter block? The latter risks polluting the source with transient operational failure state.

## Wikilink + corpus_index decision (§6)

Pick: Option C, with a narrower C' refinement.

Option C has the right separation of responsibilities: Pass-1 can make corpus-aware suggestions while source body content stays untouched, and compile remains responsible for graph entities/edges. Option A's body-appended wikilink block is not worth the merge/sync surface in a OneDrive-backed Obsidian vault. Option B is operationally clean, but it gives up one of the few enrichment tasks that benefits from the LLM seeing a corpus index.

**Proposal:** Use C' for v1:

- Frontmatter-only suggestions.
- Suggestions must be grounded in existing corpus entries.
- No `grounded_in_corpus: false` rows in `wikilink_suggestions`; use `key_entities` for raw candidate-new-entity mentions.
- Archive the exact corpus-index slice in the replay sidecar.
- Bootstrap with empty/sparse corpus rather than deferring Pass-1. Early runs can be re-enriched later if needed.

This keeps the design replayable and avoids drifting into either body mutation or GraphDB writes.

## Concerns on post-LLM override (§4)

The post-LLM override mechanism is directionally aligned with `feedback_post_llm_deterministic_override`: path/location policy belongs outside the LLM, and the LLM should judge content only.

The main concern is not the mechanism; it is the default policy. `Daily Notes/**` as default `force_noise` conflicts with D-88-11 and will hide precisely the class of daily-note insights the parent blueprint intended to let Pass-1 surface. A second concern is that override audit currently records the original binary value but not the LLM's confidence/reason at the override decision point. Those fields exist in the main envelope, but §4 should state that overrides preserve the full original parsed envelope in the replay sidecar, not just `llm_original`.

## Concerns on no-GraphDB-writes stance (§10)

The no-GraphDB-writes stance makes sense for v1. The producer contract expects graph mutation through producer artifacts and adapters, and JOURNEY's D49-D51 arc argues strongly against parallel ontology stores. Pass-1 frontmatter is not an ontology authority; it is enriched source state that compile may consume.

The deferral to a v1.1+ second producer is also reasonable, but it should stay behind a contract boundary. If Pass-1 later writes Source-level data to GraphDB, it needs its own producer contract, sidecar replay semantics, and adapter path. It should not directly mutate Kuzu from the enrichment component. The current §10.3 language points in that direction; one useful addition would be an explicit statement that any future Pass-1 graph writes must route through an adapter, matching the producer contract's core invariant.
