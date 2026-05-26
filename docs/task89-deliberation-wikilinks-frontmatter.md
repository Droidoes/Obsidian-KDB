# Task #89 — Deliberation: Wikilinks (A vs B vs C) + Frontmatter Mechanism

**Date:** 2026-05-26
**Status:** Decisions locked; folds into v0.2 of `docs/task89-component1-enrichment-blueprint.md`
**Lineage:** v0.1 §6 OPEN → round-2 panel review (5/5 returned) → mid-deliberation reframe → this document

---

## 1. Scope of the deliberation

v0.1 §6 left two questions open as a single bundled decision:

1. **Wikilink emission strategy** — should Pass-1 produce wikilinks, and if so, where do they live in the source file (body vs frontmatter)?
2. **Corpus context provisioning** — does Pass-1 load a "corpus_index" (a view over other already-enriched sources' frontmatter) so the LLM can ground entity mentions against existing material?

The two were bundled because every wikilink strategy other than "none" requires corpus context to work.

A separate but adjacent question surfaced during the deliberation:

3. **Frontmatter writing mechanism** — does the LLM return an enriched source (body + frontmatter merged), or does the LLM return structured properties and deterministic code embed them as YAML?

---

## 2. The three options at the start

### Option A — body wikilinks

- LLM emits `wikilink_suggestions` based on corpus_index context
- Post-processing code appends a wikilink block to the source body (e.g., a `## Related` section at the bottom)
- Obsidian's native graph view picks up the body wikilinks; user sees rendered links

### Option C — frontmatter wikilinks + corpus_index

- LLM emits `wikilink_suggestions` based on corpus_index context
- Post-processing code writes the suggestions into frontmatter (`wikilink_suggestions: ["[[X]]", "[[Y]]"]`)
- Per Gemini's insight, YAML wikilink strings ARE indexed by Obsidian's graph view, so user-visible behavior is similar to A
- Source body remains untouched

### Option B — no corpus_index, no wikilinks from Pass-1

- Pass-1 emits `key_entities` only (flat list of entity mentions, no corpus grounding)
- Compile owns all entity-to-entity resolution and `LINKS_TO` edge construction at compile time, against the live GraphDB
- No corpus_index loader, no snapshot semantics, no cold-start mechanics

---

## 3. The round-2 panel position (5 CLI reviewers)

4-of-5 picked C with a C' refinement (frontmatter-only suggestions with `grounded_in_corpus` boolean + `occurrences_in_corpus` integer):

- **Codex** — C with C' refinement; corpus_snapshot must be archived in replay sidecar for determinism
- **Grok** — C with C' refinement; cold-start runs use "process anyway, accept weak suggestions, re-enrich later" strategy
- **Gemini** — C with C' refinement; surfaced the Obsidian-YAML-link-indexing observation that closes A's UX gap
- **Qwen** — C with explicit LLM/deterministic split (LLM emits string list; post-LLM enriches with grounding fields)

1-of-5 dissented to B:

- **Deepseek** — B with B' hook; concrete-first principle. Argued corpus_index adds cold-start complexity, prompt-budget pressure, replay-archival overhead for an LLM-grounded-discovery feature whose marginal value over compile's existing entity extraction is **unmeasured**. Designed `key_entities` to be the future anchor for v1.1+ corpus-aware enhancements (additive, no schema migration).

---

## 4. The mid-deliberation reframe

Two concerns surfaced that the panel under-weighted:

### 4.1 — Body wikilinks (A) demand denormalization refresh

Concern raised by user:

> "If we embed wiki links into the body of the sources, then we'll need to (theoretically) update the wiki links every time the corpus_index is changed... if we change the wiki links in a source, we trigger the compile pipeline."

This frames body wikilinks as a **denormalized view of corpus state**. The cascade:

1. New source added to corpus
2. Every existing source's body wikilinks are now potentially stale (might be missing a link to the new source, or have a link that needs reworking)
3. Refresh demands rewriting the body
4. File change is detected by Component #3 (Trigger)
5. Compile pipeline re-triggers for the modified source

In steady state, an add-heavy workload thrashes compile. **A is fatal.**

C contains the blast radius: stale frontmatter `wikilink_suggestions` are **inputs to compile**, not user-facing artifacts. Compile validates/filters them against the live GraphDB at compile time. Staleness is a noise floor for compile, not a cascade trigger. So C survives A's death.

### 4.2 — Corpus_index dynamicity also undermines C

Concern raised by user:

> "When the corpus changes, lets say we add a number of sources to it... how to keep corpus_index up-to-date... remember we plan to build corpus_index iteratively one source at a time... does that mean we'll need to rebuild the entire corpus_index from the start one source at a time?"

The iterative build problem:

| Enrichment order | corpus_index at LLM call time |
|---|---|
| Source 1 | `{}` (empty) |
| Source 2 | `{Source 1}` |
| Source N | `{Sources 1..N-1}` |

Each source's `wikilink_suggestions` is stale-by-construction. "Keep consistent" means re-enriching all earlier sources after each addition — O(N²) LLM calls. Infeasible.

This challenges C itself, not just A.

### 4.3 — The deeper realization

Concern raised by user:

> "Building corpus_index is in actuality building a stripped-down version of GraphDB of the corpus... which is what we are trying to do at the end of the workflow... GraphDB will be dynamic and authoritative."

This is the load-bearing insight. **corpus_index is a stripped-down GraphDB at the wrong place and time.** It re-creates every problem GraphDB was designed to solve:

- Dynamic state (corpus_index grows; needs update)
- Iterative build (one source at a time, like compile builds GraphDB)
- Snapshot semantics (replay needs a frozen view)
- Cold-start cascade (early sources are under-grounded)

GraphDB will already be the authoritative comprehensive corpus index. Compile writes to GraphDB. Compile knows about every source. Building corpus_index in Pass-1 duplicates GraphDB's purpose, in a different place, at a different time, with weaker semantics.

This collapses C. **B is the answer.**

---

## 5. Principles ratified by the deliberation

Two principles emerged that go beyond Task #89 and should constrain all future design:

### Principle A — Obsidian wikilinks are vanity

> "The wiki link feature for Obsidian is fundamentally useless because it's manual and static... its only utility is to help create an Obsidian graph whose sole purpose is to show off and impress... there is no other way to use that Obsidian graph... GraphDB on the other hand has a number of utilities... which includes constructing a graph using the connections."

The Obsidian wikilink/graph-view feature is display-only. It has no programmatic utility beyond visual rendering. Architectural decisions should NOT optimize for "looking nice in Obsidian's graph view." GraphDB is the actual graph with query, traversal, and structural utility. Captured as memory: [[feedback_obsidian_wikilinks_are_vanity]].

### Principle B — Sources stay as static as possible

> "We want to keep source as static as possible... frontmatter doesn't make source less static as long as the frontmatter is solely related to the source itself."

Frontmatter is permissible **iff every property is intrinsic to the source itself** — describing what the source IS, says, or mentions. Anything *relational* (links to other sources, derived corpus position, cross-document inferences) does NOT belong in source frontmatter — that is dynamic state and belongs in GraphDB. Captured as memory: [[feedback_sources_stay_static_intrinsic_frontmatter_only]].

Under this rule (cleanly satisfied by Option B):
- `domain`, `source_type`, `author`, `summary`, `kdb_signal`, `key_entities`, `key_themes` — all intrinsic ✓
- `wikilink_suggestions`, `grounded_in_corpus`, `occurrences_in_corpus` — all relational ✗

---

## 6. Decision: Option B with B' hook (concrete-first)

For v0.2:

- Pass-1 emits `key_entities` as a flat string list (already in the v0.1 schema)
- Pass-1 does NOT emit `wikilink_suggestions`, `grounded_in_corpus`, or `occurrences_in_corpus`
- No corpus_index loader; no corpus_snapshot field in replay sidecar
- Compile (with live GraphDB access) owns all wikilink resolution — `LINKS_TO` edges, entity-to-entity matching
- v1.1+ may add an additional optional frontmatter field (e.g., `wikilink_suggestions`) IF compile's mechanical matching shows measurable gaps; that addition would be purely additive (no schema migration)

This decision will land as **D-89-12** in the v0.2 blueprint, with this deliberation document as the lineage citation.

---

## 7. Frontmatter mechanism — LLM returns structured response; code embeds

A separate decision that emerged during the deliberation. The v0.1 blueprint left ambiguous whether the LLM would return the enriched source (body + frontmatter) or just the property components.

> "Instead of asking llm to embed frontmatter in the source and return the entirety of the enrichment, we should ask the llm to return the components of the frontmatter in structured response and post-processing and embedding the frontmatter contents into the source."

### Why this is the right architecture

| Aspect | Old (LLM returns enriched source) | New (LLM returns JSON props; code embeds) |
|---|---|---|
| Token cost | LLM re-emits entire source body in output | LLM emits ~13 small property fields only |
| Source-body risk | LLM might trim whitespace, rewrap, alter formatting, drop content | Body is never present in LLM output; never modified |
| Validation surface | Parse YAML block + diff body for unintended edits | Validate flat JSON against schema; body untouched |
| Replay archive | Mixed envelope (body + frontmatter together) | Clean JSON envelope; body archived once at source |
| Failure mode | Bad LLM output can corrupt source on write | Bad LLM output → reject before any source modification |

### Alignment with existing principles

This extends [[feedback_post_llm_deterministic_override]] from override-application to frontmatter-embedding: the LLM does **judgment** (emit property values); deterministic code does **writes** (serialize JSON as YAML, prepend to source, or merge per §3.3 re-enrichment rules).

### v0.2 implementation specification

- Pass-1 prompt requests a JSON object as response (structured-output mode where the provider supports it)
- LLM response shape: flat JSON with the 13 fields (7 substantive: `kdb_signal`, `domain`, `source_type`, `author`, `summary`, `key_entities`, `key_themes`; 6 audit: `confidence`, `uncertainty_reason`, `reject_reason`, `prompt_version`, `model`, `schema_version`)
- Provider with no structured-output support is dropped (per [[project_deepseek_v4_flash_dropped]])
- Post-processor:
  1. Validates JSON against schema
  2. On validation failure: emit `enrich_failed` envelope to replay archive; NO source write
  3. On validation success: serialize JSON as YAML frontmatter
  4. Read source file; merge frontmatter per §3.3 (preserve user-added keys, replace Pass-1 schema keys with new values)
  5. Write source atomically (write to temp + rename)
  6. Apply post-LLM deterministic overrides (`force_signal` / `force_noise`) per §4 — overrides modify the JSON in memory BEFORE the YAML serialization step, so the override block is part of the same atomic write

This decision will land as **D-89-13** in v0.2.

---

## 8. Implications for v0.2 blueprint

**Sections that change:**

- **§2 (Pass-1 output schema)** — unchanged structurally; gains explicit note that the LLM emits structured JSON, not embedded frontmatter
- **§3 (In-place YAML frontmatter mechanism)** — rewrite to describe the new flow: LLM → JSON → post-processor → YAML embed. §3.3 (re-enrichment merge) stays correct; the source-of-frontmatter-data changes but the merge logic is unchanged.
- **§5 (Post-Pass-1 deterministic flow + replay archive)** — sidecar envelope schema simplifies (no corpus_snapshot field, no wikilink_suggestions); add a note that the JSON envelope is the canonical archive form
- **§6 (Wikilinks + corpus_index)** — REMOVED. Replaced with a one-paragraph note: "Pass-1 emits `key_entities` only; wikilink resolution is compile's responsibility against the live GraphDB. See `task89-deliberation-wikilinks-frontmatter.md` for lineage. D-89-12."
- **§10 (Producer Contract alignment)** — add Deepseek F-3 as an integration precondition: compile's source-reading path must either (a) strip YAML frontmatter before feeding to the compile LLM, or (b) explicitly consume frontmatter as structured metadata. This is a v0.2 OQ that needs resolution before Pass-1 ships.
- **§12 (Decision log)** — add D-89-12 (Option B locked) and D-89-13 (structured-response → deterministic embed)

**Sections that stay the same:**

- §1 (Scope), §4 (Force-signal / force-noise overrides), §7 (Model selection), §8 (NW-1 substance criteria), §9 (NW-7 source_type vocabulary), §11 (NW-5 surfaces), §13 (Open questions — gets new entries but structure unchanged), §14-16

---

## 9. Open questions deferred to v0.2

The two principles above (Obsidian wikilinks vanity, sources stay static) are foundational and don't have open questions.

The B-locked decision creates one minor open question:

**OQ-D — Cold-start telemetry for the v1.1+ corpus-aware enhancement decision.** What measurement would tell us compile's mechanical entity matching is insufficient and we should layer LLM-grounded suggestions on top? This is a future-decision input; not blocking v0.2.

The frontmatter-mechanism decision creates one minor open question:

**OQ-E — Provider parity on structured-output support.** The current panel includes Qwen (qwen3.7-max), Claude (claude-opus-4-7), Grok Build, Codex (gpt-5), and Deepseek (via deepcode). Verify each can produce structured JSON output reliably for the 13-field schema before Pass-1 ships. Same posture as [[project_deepseek_v4_flash_dropped]] — if a provider lacks structured output, drop it.

---

## 10. Things this deliberation does NOT change

- D-89-1 through D-89-11 in v0.1 (except where superseded — see §8)
- Pass-1's role as a single-call content-substance judgment
- The post-LLM deterministic override mechanism (§4)
- The no-GraphDB-writes-from-Pass-1 stance (§10) — only the integration precondition is added
- The NW-4 domain vocabulary
- The 5-CLI reviewer panel methodology

---

## 11. References

- v0.1 / v0.2 / v0.2.1 blueprint — `task89-component1-enrichment-blueprint.md`
- Round-1 property survey — `task89-additional-properties-survey-prompt.md` + 5 reviewer responses
- Round-2 architecture review — `task89-v0.1-review-prompt.md` + 5 reviewer responses
- Parent blueprint — Task #88 ingestion-system blueprint (see TASKS.md)
- JOURNEY.md D49-D51 — GraphDB-as-ontology-authority lessons
- Producer Contract v1.0
- Memories: [[feedback_post_llm_deterministic_override]], [[feedback_no_parallel_storage_to_authority]], [[feedback_concrete_first_extract_later]], [[feedback_obsidian_wikilinks_are_vanity]], [[feedback_sources_stay_static_intrinsic_frontmatter_only]], [[feedback_integration_preconditions_are_architectural]] (v0.2.1), [[feedback_prompt_template_definition_plus_examples]] (v0.2.1)

---

## 12. v0.2.1 amendment — "What is frontmatter FOR?" reframe (2026-05-26 evening)

A second mid-day deliberation pivoted the design when OQ-89-12 (compile-side frontmatter handling) was being scoped for implementation. The assistant had proposed a "10-line standalone fix" — `source_text_for()` strips YAML frontmatter and discards it before compile's LLM call. Joseph rejected this:

> *"I kept asking the same question, is frontmatter meaningful? is frontmatter useful? you kept reassuring me yes it's meaningful, yes it's useful... NOW we are stripping it out and drop it on the floor... let me ask you again *how* is frontmatter meaningful? *how* is frontmatter useful?"*

> *"Completely dropping frontmatter on the floor at the compile stage is an outrage and totally unacceptable to me... I had expected a lot more from you."*

### 12.1 The reframe

The assistant's initial answer to "is frontmatter meaningful" had listed multiple consumers — compile-side LLM, Obsidian UX, audit, replay, NW-5, future enhancements. Joseph applied a singular criterion:

> *"One of the key questions you raised is meaningful to whom... there can be only one answer and that answer is 'to GraphDB'... we absolutely decided to create llm-pass-1 to offload llm-pass-2... every component in the frontmatter need to be meaningful and useful to the compiler pipeline and to the construction of GraphDB."*

This collapses the "multiple valid consumers" framing to a single one: **does this field feed GraphDB construction?**

### 12.2 Per-field audit through the GraphDB-utility lens

Applied to each v0.2 field:

| Field | GraphDB destination | Verdict |
|---|---|---|
| `kdb_signal` | Routes Source into/out of compile (Component #3/#6) | **GraphDB-essential — KEEP** |
| `domain` | New `Source.domain` column | **GraphDB-essential — KEEP** (the original Pass-1 purpose) |
| `source_type` | Existing `Source.source_type` column | **GraphDB-essential — KEEP** |
| `author` | New `Source.author` column | **GraphDB-essential — KEEP** |
| `summary` | New `Source.summary` column (compile LLM merges with key_themes) | **GraphDB-essential — KEEP** (source matter; Pass-2 doesn't regenerate) |
| `key_entities` | Existing Entity / SUPPORTS structure (seeds extraction) | **GraphDB-essential — KEEP** |
| `key_themes` | Merged into Source.summary by compile LLM; no own column in v1 | **KEEP separate in frontmatter; merge in compile LLM** (D-89-18) |
| `confidence` | None (Pass-2 ignores) | **KEEP in frontmatter (audit section); not consumed by Pass-2** |
| `uncertainty_reason`, `reject_reason`, `prompt_version`, `model`, `schema_version`, `override` block | None (Pass-2 ignores) | **KEEP in frontmatter (audit section); not consumed by Pass-2** |

### 12.3 The two-section frontmatter (D-89-16)

The audit fields fail the GraphDB-utility test directly — but they ARE intrinsic to the Pass-1 enrichment instance and serve real Pass-1-side purposes (user visibility, replay correspondence, drift detection). Sectionalizing the frontmatter resolves the tension:

- **GraphDB-input section** — Pass-2 consumes
- **Audit section** — Pass-1's own; Pass-2 ignores

Both live in the same on-disk YAML frontmatter block. An earlier proposal during this deliberation to move audit fields to sidecar-only was overcorrection (per Joseph's clarification "confidence will stay with audit components in llm-pass-1"). Frontmatter has dual structure, not single criterion.

### 12.4 Compile consumes frontmatter in v1 (D-89-17)

v0.2 §10.4 had deferred compile-side frontmatter consumption to "v1.x amendments." 2026-05-26 evening promoted this to v1-required. Rationale per [[feedback_integration_preconditions_are_architectural]]: Pass-1 was created specifically to offload compile-side LLM work; if compile ignores Pass-1's output, the integration's purpose is defeated. The right minimum-viable fix closes the integration loop, not just prevents breakage.

Compile-side v1 work expands from "10-line strip" to:
- Parse YAML frontmatter → return `(frontmatter_dict, body_text)`
- Use `domain`, `source_type`, `author` directly for Source-node columns (skip LLM re-derivation)
- Pass `summary` + `key_themes` into compile LLM (which merges them into Source.summary per D-89-18)
- Use `key_entities` as seed candidates for entity extraction
- Strip audit section before compile LLM input
- Update compile prompt template to explain frontmatter usage

GraphDB schema additions: `Source.summary`, `Source.author`, `Source.domain` (or new Source→Domain edge — design call at writing-plans).

### 12.5 Compile LLM merges summary + key_themes (D-89-18)

Earlier in the deliberation the assistant suggested deterministic Python concatenation for the merge. Joseph rejected:

> *"Compile LLM merge is a better idea because it forces the LLM to process both sections instead of treating it as a pass through."*

The LLM merge ensures both fields are engaged with and integrated meaningfully into a coherent Source.summary. Themes-as-prose-in-summary covers the v1 use case; a Theme node type (NW-8) is deferred to v0.3+ pending telemetry that string-matching themes in Source.summary is insufficient.

### 12.6 New principles ratified during v0.2.1

Two memories captured and one sharpened during this deliberation:

- **[[feedback_integration_preconditions_are_architectural]]** (new) — when wiring two components, ask what the integration is FOR; strip-and-discard signals you've forgotten the upstream's purpose. The 10-line-fix proposal is the cautionary example.
- **[[feedback_prompt_template_definition_plus_examples]]** (new) — Pass-1 prompts (and other LLM-emitted-field prompts) use a definition + examples template. Examples ground SHAPE, not relationships.
- **[[feedback_no_edge_predeclaration_no_hints]]** (sharpened) — the no-hints rule is about not hiding behind examples to make architectural decisions you can't justify; it does NOT prohibit examples-as-classification-clarification. Examples-for-field-shape OK; examples-for-edges NOT OK.

### 12.7 Sequencing impact

OQ-89-12 is **rescoped and closed** as a separate "ship-blocker." The compile-side integration work is absorbed into the Pass-1 implementation arc per D-89-17. Build order remains: Pass-1 ingestion implementation → compile-side integration → end-to-end. The "tunnel ends meet in the middle" moment is when compile is updated to consume Pass-1's frontmatter.
