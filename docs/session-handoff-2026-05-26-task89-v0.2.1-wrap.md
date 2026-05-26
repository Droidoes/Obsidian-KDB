# Session Handoff — 2026-05-26 (Task #89 v0.1 → v0.2.1 wrap)

Two-day arc closed. Component #1 (Enrichment) deep-design moves from blank-page brainstorm to ratified v0.2.1 blueprint with Pass-1 ↔ Pass-2 contract locked. Implementation is the next session's work.

Branch state: **in sync with `origin/main` at `1664053`** (all session commits pushed at session end).

## Commits in this arc

| SHA | Subject | Day |
|---|---|---|
| `0548ca3` | docs(task89): v0.1 blueprint + properties survey — all-CLI panel composition | 2026-05-25 evening |
| `6eb793f` | docs(task89): round-1 panel — property survey responses (5 reviewers, all clean) | 2026-05-25 evening |
| `70b6647` | docs(task89): round-2 panel prompt — v0.1 architecture review | 2026-05-25 evening |
| `c3e93d9` | docs(task89): round-2 panel + Option B deliberation locked | 2026-05-26 mid-day |
| `092b44f` | docs(task88): D-88-11 amended by D-89-14 — Daily Notes path-override mechanism | 2026-05-26 mid-day |
| `651c8f3` | docs(task89): v0.2 fold — Option B + structured embed locked | 2026-05-26 mid-day |
| `1664053` | docs(task89): v0.2.1 — frontmatter sectionalized + compile consumes in v1 | 2026-05-26 evening |

(Plus this handoff commit.)

## State summary

**Task #89 — Component #1 (Enrichment) deep-design**

- Blueprint ratified at v0.2.1 at `docs/task89-component1-enrichment-blueprint.md`
- 18 decisions logged (D-89-1 through D-89-18); D-89-11 closed by D-89-12
- 15 open questions tracked (OQ-89-1 through OQ-89-15); OQ-89-1, -6, -12 closed during arc
- Three companion artifacts:
  - `docs/task89-deliberation-wikilinks-frontmatter.md` — full A vs B vs C + "what is frontmatter FOR" deliberation lineage
  - 5 round-1 property-survey responses (5/5 guardrail-clean)
  - 5 round-2 architecture-review responses (5/5 guardrail-clean)
- Parent blueprint Task #88 — D-88-11 amended (commit `092b44f`)
- 5 new principle memories captured / sharpened
- Implementation deferred to writing-plans (separate session)

## Session arc — two days, three iteration cycles

### Iteration 1: v0.1 brainstorm + round-1 panel (2026-05-25 evening)

- v0.1 blueprint drafted via brainstorm session on top of NW-4 v0.4 closure (same day morning)
- All-CLI 5-reviewer panel composed (project's first all-CLI arc): Codex + Qwen CLI/qwen3.7-max + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high
- `agy` on explicit one-strike re-trial per [[feedback_gemini_review_only_guardrail]]; CLI reviewer no-repo-mod guardrail captured as new memory [[feedback_cli_reviewer_no_repo_mod_guardrail]] and embedded in every reviewer prompt
- Round-1 (additional-properties survey): 5/5 responses returned, all guardrail-clean. Substantive proposals from each (Codex: `knowledge_intent`, `evidence_basis`, `temporal_frame`, `abstraction_level`; analogous from others). Folding deferred to v0.3 deliberation (OQ-89-14).
- v0.1 left §6 OPEN as a 3-option deliberation (A: body wikilinks; B: no wikilinks; C: frontmatter wikilinks + corpus_index)

### Iteration 2: v0.2 fold (2026-05-26 mid-day)

- Round-2 (architecture review) returned 5/5 clean. `agy` completed 2-for-2 on its one-strike re-trial.
- Panel converged 4-of-5 on Option C with C' refinements; Deepseek dissented to Option B (concrete-first).
- **Joseph-led mid-deliberation reframe** surfaced two structural concerns the panel under-weighted:
  - Body wikilinks (A) demand denormalization refresh on every corpus change → file-change → compile re-trigger cascade. A fatal.
  - corpus_index (in both A and C) is a stripped-down GraphDB at the wrong place and time. GraphDB is already the authoritative comprehensive corpus index.
- These collapse A and C; B is what remains. **D-89-12 locked Option B.**
- Three additional v0.2 decisions: **D-89-13** structured-JSON-then-deterministic-embed (LLM returns JSON envelope; deterministic post-processor serializes to YAML and atomically writes); **D-89-14** D-88-11 amended (parent blueprint catches up to path-based override mechanism for Daily Notes; LLM no longer instructed to detect diary shapes); **D-89-15** LLM runs on every in-scope source (no pre-LLM short-circuit; audit signal preserved).
- 6 round-2 panel non-controversial fixes folded: pseudocode precedence swap, sidecar path encoding, user-frontmatter collision rule, reject_reason survival, override-block-always-emitted, compile YAML-strip integration precondition (OQ-89-12).
- Two new principle memories from this iteration: [[feedback_obsidian_wikilinks_are_vanity]], [[feedback_sources_stay_static_intrinsic_frontmatter_only]].

### Iteration 3: v0.2.1 — "What is frontmatter FOR?" reframe (2026-05-26 evening)

Triggered when the assistant proposed a "10-line standalone fix" for OQ-89-12 (`source_text_for()` strips YAML frontmatter and **discards** it before compile's LLM call). Joseph's rejection:

> *"completely dropping frontmatter on the floor at the compile stage is an outrage and totally unacceptable to me... I had expected a lot more from you... a lot more!!!"*

The strip-and-discard proposal had implicitly retracted the integration's purpose. Pass-1 was created specifically to offload domain (and other source-level metadata) extraction from compile (Pass-2). If compile ignores Pass-1's frontmatter and re-derives via its own LLM, the entire integration's purpose is defeated.

Joseph applied a singular criterion to the schema audit: **every component in the frontmatter must be meaningful and useful to compile + GraphDB construction.** This collapsed the multi-consumer framing the assistant had implicitly drifted toward (frontmatter useful for compile, Obsidian UX, audit, replay, NW-5...) to one consumer-of-record: GraphDB.

Per-field GraphDB-utility audit produced three new decisions:

- **D-89-16** — Frontmatter sectionalized into GraphDB-input section + Audit section. Both live in the same on-disk YAML block. Pass-2 ignores the audit section. Confidence + uncertainty_reason + reject_reason + prompt_version + model + schema_version + override block all sit in the audit section (stay in frontmatter for user visibility + replay correspondence; not consumed by compile).
- **D-89-17** — Compile consumes frontmatter in v1 (not v1.x deferral as v0.2 had said). OQ-89-12 rescoped from "10-line strip" into full integration enhancement (parse + use + write + LLM prompt update). Required GraphDB schema additions: `Source.summary`, `Source.author`, `Source.domain`. Absorbed into Pass-1 implementation arc.
- **D-89-18** — Compile LLM merges summary + key_themes (NOT deterministic Python concat). Forces LLM to engage with both fields, not pass-through. `key_themes` stays as separate field in frontmatter; merged into `Source.summary` via LLM at compile time. NW-8 Theme node design deferred to v0.3+ (OQ-89-15).

The session also surfaced the [[feedback_no_edge_predeclaration_no_hints]] memory needed sharpening — that rule was about not hiding behind examples to make architectural decisions you can't justify; it does NOT prohibit examples-as-classification-clarification. New prompt-template pattern memory: [[feedback_prompt_template_definition_plus_examples]] (definition + illustrative-only examples).

## Memory updates this arc

- **NEW** [[feedback_obsidian_wikilinks_are_vanity]] — Obsidian's wikilink/graph-view feature is display-only with no programmatic utility. Don't design architecture to feed it. GraphDB is the real graph.
- **NEW** [[feedback_sources_stay_static_intrinsic_frontmatter_only]] — Frontmatter is permissible iff every property is intrinsic to the source itself; relational/dynamic properties belong in GraphDB.
- **NEW** [[feedback_integration_preconditions_are_architectural]] — When wiring two components, ask what the integration is FOR; strip-and-discard signals you've forgotten the upstream's purpose. **CAUTIONARY ENTRY**: the OQ-89-12 strip-and-discard proposal that triggered Joseph's "outrage" callout IS the cautionary example.
- **NEW** [[feedback_prompt_template_definition_plus_examples]] — For free-form Pass-1 fields, prompt uses two-part template (definition + illustrative-only examples). Examples ground SHAPE, not relationships.
- **NEW** [[feedback_cli_reviewer_no_repo_mod_guardrail]] — Every CLI reviewer prompt MUST include explicit output-file-only guardrail; CLI reviewers have filesystem access and overreach without it. (Captured during round-1 dispatch; v0.1 commit `0548ca3`.)
- **SHARPENED** [[feedback_no_edge_predeclaration_no_hints]] — Original rule was about not hiding behind examples to make architectural decisions; clarified now that examples-for-shape (classification illustration) are OK; examples-for-edges (relationship pre-declaration) are NOT.

## Architectural rules to consult on resumption

- **D-89-12 (Option B locked)** — Pass-1 emits `key_entities` only; compile owns wikilink/`LINKS_TO` resolution against live GraphDB. Don't propose corpus_index or wikilink_suggestions fields in v1. v1.1+ may layer LLM-grounded suggestions on top IF compile's mechanical matching shows measurable gaps (Deepseek B' hook).
- **D-89-13 (structured JSON + deterministic embed)** — Pass-1 LLM returns a JSON envelope of the 13 fields. Deterministic post-processor validates, applies overrides, serializes to YAML, atomically writes the source. Body never present in LLM output. Providers without reliable structured-output support cannot be used (OQ-89-13).
- **D-89-14 (Daily Notes path-override mechanism)** — Daily Notes default to `force_noise: [Daily Notes/**]` post-LLM path override. LLM judges content substance only; never instructed to detect diary shapes. Configurable: user can remove `Daily Notes/**` from `force_noise` to get LLM substance judgment.
- **D-89-15 (no pre-LLM short-circuit)** — LLM runs on every in-scope source including force_noise matches. Audit signal preserved (we can see whether LLM agreed with path override). v1.1+ may add cost-optimization short-circuit IF telemetry shows ≥99% agreement (OQ-89-10).
- **D-89-16 (frontmatter sectionalized)** — Two-section frontmatter; GraphDB-input section consumed by Pass-2; audit section ignored by Pass-2 but kept on disk for user + replay + telemetry visibility.
- **D-89-17 (compile consumes in v1)** — Compile parses YAML frontmatter, uses GraphDB-input section directly to populate Source node columns, seeds Entity extraction with `key_entities`, strips audit + GraphDB-input both from body before its LLM call (LLM only sees body content). Required schema additions: `Source.summary STRING`, `Source.author STRING`, `Source.domain STRING` (or new Source→Domain edge — design call at writing-plans).
- **D-89-18 (compile LLM merges summary + themes)** — Compile's prompt template receives both `frontmatter.summary` and `frontmatter.key_themes`; LLM produces a merged Source.summary that weaves themes into the prose. NW-8 Theme node design deferred to v0.3+.

## Open path for next session

**Primary: writing-plans for Pass-1 ingestion implementation.** This is the brainstorming-skill's terminal step. The Pass-1 implementation arc is the heart of #89 (#89 is named "Component #1 (Enrichment) deep-design" — the design is now done; implementation follows).

**Pass-1 ingestion implementation scope** (from v0.2.1 blueprint):

- New module structure (`kdb_compiler/ingestion/` or similar — doesn't exist yet)
- Pass-1 LLM call mechanism with structured-output JSON envelope (D-89-13)
- `force_signal` / `force_noise` deterministic override layer (§4)
- YAML frontmatter embedder (deterministic Python — serialize validated JSON → YAML; merge per §3.3 user-frontmatter collision rule)
- Replay archive sidecar (§5.3 — JSON envelope + raw response + request, with sidecar path encoding `/` → `__`)
- Run journal (§5.4)
- Tests (unit + integration; provider-parity smoke for structured-output per OQ-89-13)

**Pass-1 ingestion is the "end B" of the tunnel-from-both-ends pivot.** Compile-side integration (the Pass-2 amendments per D-89-17/D-89-18) follows AFTER Pass-1 ships — that's the moment the tunnel ends meet.

**Pass-1 implementation prerequisites to verify before writing-plans:**

- Provider structured-output parity (OQ-89-13) — verify each candidate Pass-1 model can reliably produce the JSON envelope schema. Drop providers that can't (same posture as [[project_deepseek_v4_flash_dropped]]).
- Pass-1 prompt template design — uses the Definition + Examples template per [[feedback_prompt_template_definition_plus_examples]] for free-form fields (`author`, `summary`, `key_entities`, `key_themes`). Controlled-vocab fields (`domain`, `source_type`) use the vocab itself as the input.

**Compile-side integration scope (D-89-17/D-89-18 — comes AFTER Pass-1 ships):**

- Schema additions: `Source.summary`, `Source.author`, `Source.domain` (or Source→Domain edge); SCHEMA_VERSION bump 2.2 → 2.3 per existing migration pattern (precedent #74, #76)
- `kdb_compiler/compiler.py:104-107` (`source_text_for()`) — rewrite to parse YAML frontmatter and return `(frontmatter_dict, body_text)`; ripple through callers
- Compile Source-node writer — populate new columns from frontmatter
- Compile entity extraction — seed with `frontmatter.key_entities`; LLM verifies, dedupes against existing GraphDB, supplements
- Compile prompt template (`prompt_builder.py` + Jinja) — explain frontmatter usage; instruct LLM to USE provided values (skip re-derivation of `domain`/`source_type`/`author`); instruct LLM to MERGE `summary` + `key_themes` into Source.summary; instruct LLM to TREAT `key_entities` as seed candidates
- Integration acceptance test: run compile on an enriched source; verify Source columns populated from frontmatter; verify entity extraction seeded; verify no frontmatter pollution in body LLM input

## Things to consult on resumption

- **Memory** [[feedback_integration_preconditions_are_architectural]] — READ THIS FIRST when starting compile-side work. The cautionary lesson is fresh.
- **Memory** [[feedback_obsidian_wikilinks_are_vanity]], [[feedback_sources_stay_static_intrinsic_frontmatter_only]] — the principles that drove the v0.2.1 reframe
- **Memory** [[feedback_prompt_template_definition_plus_examples]] — when designing Pass-1 prompt
- **Memory** [[feedback_no_edge_predeclaration_no_hints]] (sharpened) — when writing prompt instructions; examples-for-shape OK, examples-for-edges NOT
- **Blueprint v0.2.1** at `docs/task89-component1-enrichment-blueprint.md` — the spec to implement
- **Deliberation doc** at `docs/task89-deliberation-wikilinks-frontmatter.md` — the full lineage including v0.2.1 reframe (§12)
- **Parent blueprint** at `docs/task88-ingestion-pipeline-blueprint.md` — D-88-11 amended (commit `092b44f`)
- **Existing schema** at `graphdb_kdb/schema.py` v2.2 — for the migration target
- **Existing compile code** at `kdb_compiler/compiler.py:104-107` (`source_text_for()`) and `prompt_builder.py:118-143` (`build_prompt()`) — the specific touchpoints for compile-side integration

## Methodology lessons reinforced

1. **Integration preconditions are architectural, not mechanical.** The OQ-89-12 strip-and-discard proposal would have shipped a "10-line fix" that defeated Pass-1's entire reason for being. Captured as memory; the cautionary example IS the proposal itself. The minimum-viable fix is whatever closes the integration loop the two components were designed for — not the smallest code change.

2. **"Meaningful to whom?" is a load-bearing question.** When defending a design claim, name the consumer. Multi-consumer framings ("it's useful for compile + UX + audit + replay + ...") drift away from the design's actual purpose. Joseph's collapse to a singular criterion ("meaningful to GraphDB construction") was the right architectural discipline.

3. **Devil's-advocate gate worked again.** Per [[feedback_devils_advocate_gate]], the assistant output a 3-point structured callout (original position / concessions / failure modes) BEFORE retracting the multi-consumer framing under Joseph's pressure. That made the retraction explicit and gave Joseph the surface to push further (which he did, on the audit-fields placement). Without the gate, the retraction could have been silent capitulation.

4. **The panel is right *enough* of the time to be valuable; not right *every* time.** Round-2 panel converged 4-of-5 on Option C; Joseph-led mid-deliberation collapsed both A and C to B via two structural concerns the panel under-weighted (denormalization refresh; corpus_index-as-stripped-down-GraphDB). Panel convergence is signal, not proof. The Joseph veto path was load-bearing.

5. **CLI reviewer guardrails work when explicit.** All 5 panel reviewers honored the no-repo-modification guardrail across both rounds (10-for-10). `agy` specifically completed 2-for-2 on its one-strike re-trial. The lesson: per-reviewer output file paths + explicit "do not modify anything else" + one-strike consequence statement in the prompt header is sufficient discipline.

6. **Milestone closure → changelog rule sustained.** Per [[feedback_milestone_closure_rule]], the v0.2.1 closure earned its `CODEBASE_OVERVIEW.md` Milestone Changelog entry in the same commit (`1664053`) — covers the full two-day arc.

## Mental state for resumption

The design phase of #89 is **done**. v0.2.1 is ratified by Joseph; all forks have been collectively settled. The Pass-1 ↔ Pass-2 contract is locked end-to-end on paper; nothing is implementation-blocked by a design ambiguity.

The next session has a clean entry point: **invoke the writing-plans skill** to draft the Pass-1 ingestion implementation plan. Once the plan is approved, code follows.

**Sequencing reminder for the implementation arc:**

1. Pass-1 ingestion side first (producer)
2. Compile-side integration second (consumer)
3. End-to-end acceptance test (the "tunnel ends meet" moment)

**Do not collapse this sequence.** Producer-before-consumer is the natural build order; compile-side changes test better against real Pass-1 output than hand-crafted fixtures. Pass-1 surfaces uncertainties earlier; compile-side waits gracefully (Pass-1 isn't running on any production source today, so the integration-gap window has zero blast radius).

**Round-1 property additions remain deferred to v0.3 (OQ-89-14).** They are NOT part of this implementation arc. The 13-field schema in v0.2.1 is what implementation targets. If post-implementation telemetry shows additional properties would earn their LLM cost, v0.3 opens that deliberation separately.
