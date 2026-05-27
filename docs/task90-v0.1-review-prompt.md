# Task #90 v0.1 — External Review Fire-Prompt

**Purpose:** Fire the v0.1 Context-loader T2-rewrite blueprint (`docs/task90-context-loader-t2-rewrite-blueprint.md`) at the standard 5-reviewer all-CLI panel. This is the precondition for Task #90 v0.2 ratification → algorithm-details task → implementation. Joseph ratified Option A as the v1 production default 2026-05-27 morning; this review stress-tests the algorithm, the alias-resolution helper, the Pass-1 `entity_search_keys` prompt section, and the benchmark plan.

**Dispatched:** 2026-05-27 (to be fired by Joseph)
**Target panel (all-CLI, code-grounded):**
- **Codex** — CLI (panel incumbent)
- **Qwen CLI / qwen3.7-max** — CLI (panel incumbent; clean on Task #89 NW-7 v0.1 review)
- **Grok Build** — CLI (panel incumbent; clean on Task #89 v0.1 review)
- **deepcode CLI / Deepseek** — CLI (panel incumbent; clean on Task #89 v0.1 review)
- **agy / gemini-3.5-flash-high** — CLI (3-for-3 successful re-trial: Task #89 v0.1 + round-2 + NW-7 v0.1; re-instated as full panel member per `[[feedback_gemini_review_only_guardrail]]`)

**Response files (one per reviewer):**
- `docs/task90-v0.1-review-codex.md`
- `docs/task90-v0.1-review-qwen.md`
- `docs/task90-v0.1-review-grok.md`
- `docs/task90-v0.1-review-deepseek.md`
- `docs/task90-v0.1-review-gemini.md`

---

## ─── Prompt body ───

You are reviewing **Task #90 v0.1 — the Context-loader T2-rewrite blueprint** for the Obsidian-KDB project (`docs/task90-context-loader-t2-rewrite-blueprint.md`). The blueprint specifies the algorithm by which `graph_context_loader` consumes the new `entity_search_keys` Pass-1 frontmatter field (locked 2026-05-26 via D-89-20) to build T2 of the tier-ranked context snapshot.

This is **both** an algorithm review (does the proposed code structure work?) and a Pass-1 prompt review (is the LLM prompt that produces `entity_search_keys` well-anchored to its consumer's actual lookup mechanism?). Both dimensions matter — please address each.

### 1. REPO-MODIFICATION GUARDRAIL (CRITICAL — read first)

Create EXACTLY ONE file in this CLI session. Your output file path depends on your reviewer identity:

- Codex:        `docs/task90-v0.1-review-codex.md`
- Qwen CLI:     `docs/task90-v0.1-review-qwen.md`
- Grok Build:   `docs/task90-v0.1-review-grok.md`
- deepcode CLI: `docs/task90-v0.1-review-deepseek.md`
- agy:          `docs/task90-v0.1-review-gemini.md`

Do NOT modify, create, or delete any other files in the repository.
Do NOT modify code, schemas, configuration, blueprints, or other docs.
Do NOT propose implementation patches or write code.

Your entire CLI session output must be confined to producing your single review file. Violating this guardrail (e.g., editing other files, committing changes, modifying code) results in de-selection from future review cycles per the one-strike rule (`docs/external-review-panel.md`).

All five reviewers completed Task #89 v0.1 + round-2 + NW-7 v0.1 clean (5/5; agy 3-for-3 on re-trial cycle). This review continues under the same discipline.

### 2. Project context (brief)

**The system.** Obsidian-KDB compiles Joseph's raw markdown sources into a knowledge graph (Kuzu GraphDB). The pipeline has two ends: end A = compile pipeline (mature, Pass-2 LLM that writes wiki pages); end B = ingestion pipeline (Task #88, in design). Task #89 (Component #1 Enrichment, CLOSED 2026-05-26) implements Pass-1: a structured-frontmatter classifier that runs upstream of compile.

**Where Task #90 fits.** The compile pipeline's `graph_context_loader` (`kdb_compiler/graph_context_loader.py`) builds a tier-ranked context snapshot of Entities for each source being compiled. T1 = SUPPORTS-based; T2 = slug-in-text whole-word regex (the pre-Pass-1 heuristic this rewrite replaces); T3 = 1/2-hop neighbors of T1∪T2. Task #89's D-89-20 added `entity_search_keys` to Pass-1's GraphDB-input frontmatter section as a structured "slugs to seed T2" signal. Task #90 is the consumer side of that contract.

**Why the rewrite.** The T2 whole-word regex is strictly dominated by Pass-1's `entity_search_keys` on enriched sources: the LLM has produced an explicit list designed for exactly this lookup. The regex misses surface-form variation, synonym mentions, and author/organization names that don't share the entity slug. Joseph selected Option A (clean replacement; structured-signal-only on Pass-1 path; legacy regex preserved as backward-compat for pre-Pass-1 sources) over Option B (layered structured ∪ regex) and Option C (strict replacement, no backward-compat). The blueprint bakes in a `T2Mode` enum so Option B can be re-selected as production default after the planned NW-9 benchmark, if benchmarking proves Option B better.

**Sibling precedent.** Task #90 v0.1 follows the Task #89 v0.1 + NW-7 v0.1 review pattern exactly. Blueprint structure mirrors `docs/task89-component1-enrichment-blueprint.md`.

### 3. What is LOCKED (do NOT reopen)

These items are ratified upstream and NOT subject to review:

- **§1.1–§1.3 — Input contract (D-89-20).** `entity_search_keys` field shape (list[str], ≤10 kebab-case), alias-aware lookup requirement (direct + canonical_id + ALIAS_OF per Task #74), T2 score = 2, Pass-2 view of ContextSnapshot unchanged.
- **§3.1 — Alias-reachability paths.** Direct PK → canonical_id → ALIAS_OF edge. Order ratified.
- **§4 — Pass-1 prompt section content** (the four "What to include" categories, format conventions, example). The wording is OPEN for review (§6 OQ-90-4 is explicitly your prompt-review hook); the existence of `entity_search_keys` as a Pass-1 field is LOCKED.
- **D-90-1** — Option A as v1 production default. **D-90-2** — `T2Mode` enum for A/B comparison. **D-90-3** — prompt inlined in §4. **D-90-4** — separate benchmark task (NW-9) gates production-default flip, not v1 ship.
- **D-89-20** itself, including the decision to drop `key_entities` and add `entity_search_keys` as the load-bearing Pass-1→T2 signal channel.

### 4. What is OPEN (primary review focus)

#### 4.1 The eight open questions in blueprint §9

These are the headline review items. The blueprint frames each as a fork; reviewers should pick a position and defend it.

- **OQ-90-1** — `entity_search_keys=[]` semantics: fall back to legacy regex (current proposal) vs. respect LLM's "no graph anchors" signal and emit empty T2. Which is more honest?
- **OQ-90-2** — Zero-hit fallback threshold (5% rate). Is 5% the right number? Should the threshold be raw-rate or precision-on-substantive-source?
- **OQ-90-3** — Kuzu Cypher compatibility for the proposed batch query (§3.3). Sane fallback to 1–2 simple queries OK? Any Kuzu-specific gotchas?
- **OQ-90-4** — Pass-1 prompt review (the headline OQ — see §5 below for the five framed sub-prompts).
- **OQ-90-5** — Frontmatter plumbing: option (i) planner double-parses vs option (ii) `CompileJob` schema change. Confirm preference for (i)?
- **OQ-90-6** — Mode selection mechanism: `KDB_T2_MODE` env var sufficient for v1, or config-file from the start?
- **OQ-90-7** — `T2Mode` enum location: `graph_context_loader` (current proposal) vs `kdb_compiler/types.py`.
- **OQ-90-8** — Legacy branch sunset trigger. Worth fixing now, or revisit post-NW-9?

#### 4.2 Open decisions D-90-5 / D-90-6 / D-90-7

These three are flagged as "Open for panel comment" in §11. Reviewer position requested:

- **D-90-5** — Cold-start title-phrase widening (Task #71) survives on legacy branch only; retired per-source as enrichment rolls out. Defensible, or should title-phrase widening also apply on the structured branch as a fallback?
- **D-90-6** — Zero-hit fallback: none in v1 per `[[feedback_no_imaginary_risk]]`. Counter-argue if you disagree.
- **D-90-7** — Frontmatter plumbing: planner double-parses (option (i)). Counter-argue if you prefer (ii).

### 5. Pass-1 prompt review — five framed sub-prompts (per blueprint §4)

The current `entity_search_keys` section of `kdb_compiler/ingestion/pass1_prompt.j2` is inlined verbatim in blueprint §4. The prompt's job is to maximize hit rate against `Entity.slug` PK lookups at T2 (after alias-aware resolution per §3). Reviewers should evaluate:

1. **Anchoring.** Does the prompt sufficiently anchor the LLM to the consumer's actual lookup mechanism (PK match + alias resolution)? Or does the LLM emit slugs blind to how they'll be resolved?
2. **Category boundaries.** Are the four "what to include" categories well-bounded? Category 4 ("Closely-related concepts that frequently co-occur with the source's themes, even if not named explicitly") — is this too much fanout? Not enough? Counter-productive (LLM emits speculative slugs that miss the active entity set)?
3. **Name disambiguation.** Is "surname-only AND full-name form" guidance the right pattern for proper-name disambiguation? Does it produce redundant slugs that pad the 10-cap with low-value entries?
4. **Cap of 10.** Is 10 the right cap? The top-50 context page cap suggests 10 is intentionally generous, but a sharper number may improve LLM precision. Probe: what's a realistic average hit rate (n alias-resolved / 10 emitted) that a well-tuned LLM should achieve?
5. **Example diversity.** The single in-prompt example is finance-domain (Buffett/Munger/value-investing). Should it be expanded to ≥3 domain-diverse examples to avoid anchoring LLM emissions to finance-domain phrasing patterns (especially for sources in `ai-ml`, `philosophy-ethics`, `arts-design`, etc.)?

### 6. What else to review

#### 6.1 Algorithm correctness

- **§2.5 `_t2_from_search_keys`.** Iterates raw keys → resolves each → intersects with candidate pool. Any edge cases this misses? (E.g., duplicate raw keys after resolution — already handled by `set` semantics, but worth a sanity check.)
- **§3 alias resolution.** Three reachability paths (direct PK → canonical_id → ALIAS_OF). Order correct? Any sources of ambiguity (e.g., entity has both `canonical_id NOT NULL` AND an outgoing `ALIAS_OF` edge — which path wins, and does the order in §3.1 produce the right answer)?
- **§3.3 batch query.** The proposed Cypher uses `OPTIONAL MATCH ... WITH ... OPTIONAL MATCH` + `CASE`. Kuzu Cypher subset compatibility unknown at design time. Specific Kuzu-version concerns?
- **§2.7 zero-hit semantics.** Source ships to Pass-2 with empty `context_snapshot.pages`. Is this OK for Pass-2 (compile prompt), or does it cause a downstream failure mode (Pass-2 hallucinates with no grounding)?

#### 6.2 Backward-compat semantics

- **§6.1 branch selector.** Treats both `frontmatter is None` and `frontmatter.entity_search_keys == []` as "fall back to legacy." Is this right? Or should empty-list be distinguished from absent-frontmatter? (Cross-links OQ-90-1.)
- **§6.2 plumbing.** Option (i) double-parse vs option (ii) `CompileJob` schema change. (Cross-links OQ-90-5 + D-90-7.)
- **§6.3 corpus state.** 0 hand-tagged sources across 1663 .md files means full legacy-branch fallback until `kdb-enrich` runs. Incremental migration story — gaps?

#### 6.3 Benchmark plan (§7 + NW-9 framing)

- **§7.1 architectural support.** `T2Mode` enum approach for A/B/baseline comparison. Mechanism sound? Any hidden coupling that makes mode-switching produce false-positive deltas (e.g., env-var-leakage across runs)?
- **§7.2 eval criteria.** Five criteria proposed (hit rate, precision via Pass-2 quality, recall vs gold T2, cold-start density, drift cost). Missing dimension? Over-specified?
- **§7.2 probe corpus.** "Enriched sources spanning ≥3 domains and ≥3 source_types." Is this the right axis? Or should the probe corpus stratify on a different dimension (size? domain alignment with active graph? source_type that historically scored low T1)?
- **§7.3 flip protocol.** One-line default-mode change. Acceptable risk model, or does flipping warrant more ceremony (e.g., a feature flag with canary period)?

#### 6.4 Test plan (§8)

- **§8.1 unit coverage.** Cases enumerated. Anything missing? E.g., what happens when `entity_search_keys` contains duplicates? Whitespace-only entries? Slugs that pass shape check but contain Unicode (current shape relaxation per `[[feedback_no_imaginary_risk]]` allows things like `"see's-candies"`)?
- **§8.2 live smoke.** Single end-to-end test sufficient, or does the new `T2Mode` machinery deserve mode-parameterized smoke coverage?
- **§8.3 regression.** Existing `test_graph_context_loader.py` parametrized with `T2Mode.LEGACY`. Sufficient regression discipline, or risk of false-pass (legacy mode no longer represents what production currently runs because production has shifted)?

#### 6.5 Code surface (§5)

- **Files touched** — `graph_context_loader.py` + `planner.py`. Is the `_build_t2` dispatcher (§2.1) the right abstraction boundary? Or should mode-dispatch live higher (e.g., in `build_context_snapshot` body)?
- **Signature changes** — `build_context_snapshot` adds two new params (`frontmatter`, `mode`). Acceptable signature evolution, or worth carrying both old + new for one cycle?

### 7. Out of scope for this review

- **Re-litigating D-89-20** (input contract). Locked 2026-05-26 night via Joseph deliberation; `entity_search_keys` field shape + alias-aware lookup + T2 score = 2 are settled.
- **Re-litigating D-90-1 through D-90-4.** Option A choice, `T2Mode` mechanism, prompt-inlining-for-review, NW-9 as separate sibling task — all ratified by Joseph 2026-05-27.
- **Pass-2 prompt or compile-pipeline behavior.** Task #90 changes only `graph_context_loader` production; Pass-2's view of `ContextSnapshot` is invariant.
- **GraphDB schema changes.** No schema changes proposed; Entity.canonical_id + ALIAS_OF edges already exist (Task #74).
- **Pass-1 schema changes.** `entity_search_keys` field shape is in `kdb_compiler/ingestion/pass1_schema.py`; the field exists, was empirically validated 2026-05-26 night via E.1. Schema changes not in scope.
- **NW-4 (Domain) or NW-7 (source_type) revisions.** Sibling vocabularies, separately ratified.
- **Implementation patches.** This is a design review. Implementation lands after v0.2 ratification via dedicated tasks. Do not propose code diffs.

### 8. Output format

Standard review format. Suggested structure:

1. **Convergence** — what holds together cleanly (algorithm shape, alias resolver design, T2Mode mechanism, prompt structure, etc.). Don't dwell; note briefly.
2. **Findings** — concrete issues, ambiguities, contradictions, missed considerations. Prefix substantive findings as `**Finding F-N:**` and minor / nice-to-have observations as `**Observation O-N:**`.
3. **Recommendations** — proposed amendments to specific decisions / sections / OQ positions. Prefix as `**Recommendation:**` or `**Proposal:**`. For OQ-90-1..8 and D-90-5/6/7, take an explicit position.
4. **Prompt-review block** — dedicated section on §4 Pass-1 prompt, addressing the five framed sub-prompts in §5 of this fire-prompt. Suggest specific wording edits if applicable (quoted).
5. **Edge-case probes** — give 3–5 concrete edge cases (specific `entity_search_keys` lists + graph states) and walk through how Option A's algorithm handles each. Flag any that produce surprising results.
6. **Open questions** — additional questions raised but not resolvable in review.

**Length:** under 3000 words. Cite specific section anchors (e.g., "§2.2", "§3.1", "OQ-90-3", "D-90-5") where possible. Quote the v0.1 doc with `> …` blockquotes when raising an issue with specific wording.

### 9. The artifact to review

Attached: `docs/task90-context-loader-t2-rewrite-blueprint.md` (full file).

For project context, reference as needed:
- `docs/task89-component1-enrichment-blueprint.md` v0.2.2 — parent blueprint; §12 D-89-20 is the input contract Task #90 consumes
- `docs/task88-ingestion-pipeline-blueprint.md` v0.2 — grandparent (ingestion-system framing)
- `kdb_compiler/graph_context_loader.py` — the file being rewritten
- `kdb_compiler/ingestion/pass1_prompt.j2` — the prompt §4 inlines (read for context, do not edit)
- `kdb_compiler/compiler.py:107` `SourceFrontmatter` — already plumbed
- `graphdb_kdb/schema.py` — Entity.canonical_id + ALIAS_OF edges (Task #74)
- `docs/external-review-panel.md` — panel composition + one-strike rule
- `docs/CODEBASE_OVERVIEW.md` — Milestone Changelog
