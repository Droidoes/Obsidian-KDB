# Task #89 v0.1 Blueprint — Architecture Review (Deepseek)

**Reviewer:** deepcode CLI (Deepseek)
**Date:** 2026-05-25
**Artifact reviewed:** `docs/task89-component1-enrichment-blueprint.md` v0.1
**Supporting docs:** Parent blueprint v0.2, NW-4 v0.4 domain list, Producer Contract v1.0, JOURNEY.md

---

## Convergence

The in-place YAML frontmatter approach (D-89-5, §3) is the right architectural primitive. Single source of truth, Obsidian-native rendering, no sidecar drift — each property of the decision is load-bearing. The `feedback_no_parallel_storage_to_authority` discipline is correctly applied: Pass-1 writes to the filesystem-native source file, not to GraphDB, not to a separate metadata store.

The post-LLM deterministic override mechanism (§4) correctly separates concerns: the LLM judges content substance; the deterministic layer handles location-based rules. The `override` audit block preserving `llm_original` alongside `applied` is the right observability pattern — the same audit-field discipline that Codex F4 established for Pass-1's `uncertainty_reason`.

The `kdb_signal: signal | noise` naming (D-89-2) is a genuine improvement over `verdict: pass | not_pass`. Signal/noise is descriptive of what the LLM is actually judging; verdict is courtroom-shaped and invites the LLM to posture as judge rather than classifier.

The no-GraphDB-writes-from-Pass-1 stance (§10, D-89-6) is correctly defended. The JOURNEY.md manifest.json → GraphDB transition arc is the project's cautionary tale about premature storage-layer commitments — proving the enrichment shape on filesystem-native frontmatter first, then considering a second producer contract for v1.1+, is the right sequence.

The replay-archive sidecar (§5.3) and run journal (§5.4) follow the established producer-contract pattern cleanly. The sidecar schema carrying `request` + `raw_response` + `parsed_envelope` + `override` provides full replay determinism.

---

## Findings

### Finding F-1: §4.4 blacklist-wins-ties precedence inverts the bias-to-inclusion principle

§4.4 states:

> **Blacklist wins ties** (defensive default). If a file matches both `force_signal` and `force_noise`, `force_noise` applies. The reasoning: explicit user intent to exclude (in `force_noise`) should not be silently overridden by an upstream-defined `force_signal` pattern.

The reasoning is asymmetric — it treats `force_signal` as "upstream-defined" and `force_noise` as "explicit user intent," but both lists are user-populated in the same config file. Consider the case where the user configures:

```yaml
force_signal: [Projects/special/**]
force_noise:  [Projects/**]
```

The user's intent is clear: most of `Projects/` is noise, but `Projects/special/` is signal. The `force_signal` glob is more specific, yet blacklist-wins-ties would force `Projects/special/memo.md` to `noise` — directly contradicting the user's explicit, more-granular intent.

This also violates D-88-4's bias-to-inclusion principle at the config layer. A false noise (suppressing real signal because of a coarse glob) is worse than a false signal (promoting noise that Pass-2 can reject) under the ratified inclusion bias.

**Recommendation:** Replace blacklist-wins-ties with **most-specific-glob-wins**. When a source matches both lists, the glob with the deeper path specificity takes precedence. If specificity is equal, bias to `force_signal` (consistent with D-88-4). This also resolves OQ-89-3.

### Finding F-2: §3.5 sync-conflict abort-and-re-fire creates an infinite retry hazard

§3.5 states:

> Pass-1 reads the source's mtime + content-hash before the LLM call; if either changed by the time we go to write, abort the write and re-fire Pass-1 on the new content

If the user is actively editing a source during an ingestion run, the content-hash could change again during the re-fire, triggering another abort-and-re-fire. No bound is specified.

**Recommendation:** Add a **max-retry cap** (2 re-fires) with an `enrich_skipped` outcome on the third attempt and a `reject_reason: "sync_conflict_retry_exhausted"` audit entry. The source is re-queued for the next Component #3 trigger cycle. This prevents a hot-loop while preserving the correctness guarantee (no stale LLM output written over fresh user edits).

### Finding F-3: §10.4 compile-integration assumption — frontmatter leakage into compile LLM prompt

§10.4 states:

> Compile's existing entity extraction operates on the body; the new frontmatter is available as metadata for compile to use

But compile currently reads source files as raw markdown. After Pass-1 enrichment, the source file contains a YAML frontmatter block at the top. If compile's content extraction does not strip YAML frontmatter before feeding content to the compile LLM, the frontmatter properties (`kdb_signal: signal`, `domain: value-investing`, `key_entities: [...]`) will appear as source text in the compile prompt. The compile LLM would then see metadata-as-content — confusing the entity extraction pass and potentially causing it to emit entities for metadata values.

This is not a Pass-1 bug — it's a compile-side integration concern. But the blueprint's §10.4 framing ("compile sees the new frontmatter... available as metadata") implies compile will handle it correctly, without verifying that compile's existing code does so. The compile pipeline was designed for raw markdown without frontmatter; adding frontmatter changes its input contract.

**Recommendation:** Add an **Integration precondition** section (or OQ) noting that before Pass-1 enrichment ships, compile's source-reading path must be verified to either (a) strip YAML frontmatter before LLM content extraction, or (b) pass frontmatter as a separate metadata block rather than raw text. Without this, enriched sources would silently degrade compile quality.

### Finding F-4: §3.3 user-added key collision with future schema additions

§3.3 specifies:

> Parse existing frontmatter (if any) — capture user-added keys that aren't in the Pass-1 schema (user may have added their own keys)

This is good defensive design. But when v0.2 adds a new official property (e.g., `difficulty`) that the user had previously added manually, the merge would overwrite the user's curated value with the LLM's — the user loses their editorial control silently.

**Recommendation:** Add a **collision rule** for re-enrichment: when a key exists in both the user-added set AND the new Pass-1 schema (because the schema added it after the user created it), preserve the user's value and add an `override`-style annotation: `difficulty_user_overridden: true` in the frontmatter. This gives the user visibility and control. File as an OQ for v0.2 resolution.

### Finding F-5: §5.1 schema-validation retry vs D-88-10 single-call discipline — distinction implicit but unstated

§5.1 says "Failure → retry once with structured-output retry pattern; second failure → mark Pass-1 as errored." D-88-10 from the parent blueprint says "Ship single-call enrichment for v1." These can be read as contradictory — retrying a failed call is a second call. But the intent is different: D-88-10 prohibits splitting the enrichment into multiple LLM calls (verdict+domain in one call, tags+wikilinks in another). A schema-validation retry is error-recovery on the same call, not a multi-call architecture. However, this distinction is not stated in the blueprint, and an implementer could reasonably read them as conflicting.

**Recommendation:** Add a sentence to §5.1: "Schema-validation retry is error-recovery on the same call type, not a multi-call architecture — it does not conflict with D-88-10's single-call discipline, which governs call splitting, not error retry."

### Finding F-6: §4.5 `reject_reason` survives `force_signal` override — misleading audit trail

When `force_signal` overrides an LLM-emitted `kdb_signal: noise`, the `override` block correctly preserves `llm_original: noise`. But the LLM also emitted `reject_reason: "diary-shaped meta-commentary"` — and this field remains in the frontmatter unchanged, directly above the `override` block that says the signal/noise verdict was reversed. A human reading the frontmatter sees a `reject_reason` explaining why the source was rejected, next to `kdb_signal: signal` — contradictory.

**Recommendation:** When `force_signal` overrides `kdb_signal: noise` to `signal`, either (a) clear `reject_reason` to `null` and annotate in the `override` block: `reject_reason_cleared: "<original>"` or (b) prefix the reject_reason with `[OVERRIDDEN]`. Option (a) is cleaner and preserves the audit trail without confusing frontmatter readers.

### Observation O-1: §8.2 noise definition overlaps with §4.2 `force_noise` defaults — belt-and-suspenders worth documenting

The `force_noise` defaults (`Daily Notes/**`, `Projects/**`) cover the same content §8.2 describes as noise (diary-shaped meta-commentary, workflow/task tracking). This is a belt-and-suspenders design: the LLM catches edge cases the path globs miss; the globs catch content the LLM might misclassify. But the blueprint doesn't articulate this layering explicitly. An implementer might wonder whether the LLM noise criteria and `force_noise` are competing authorities or complementary defenses.

**Recommendation:** Add a sentence to §8.2: "The `force_noise` path-list (§4.2) covers known diary-shaped directories deterministically; the LLM's substance test is the safety net for noise content outside those directories and for diary-shaped content that happens to live elsewhere."

### Observation O-2: `source_type` v0.1 placeholder list (§9.1) — `daily-note` should not exist if Daily Notes are force_noise

The placeholder `source_type` enumeration includes `daily-note` (id: `daily-note`, display: "Daily Note / Log Entry"). But Daily Notes are in `force_noise` by default — they'll never reach Pass-1's `source_type` classification because they're deterministically noise-gated before the LLM even sees them (well, the LLM still sees them per §4.5 — the LLM judges content, then the override applies). Actually, the LLM DOES process Daily Notes (the override happens post-Pass-1), so the LLM would need to classify their `source_type`. But if the answer is always `daily-note`, it's wasted work.

However, the user might remove `Daily Notes/**` from `force_noise` (per D-88-11, Daily Notes are deliberately in scope), in which case `daily-note` as a source_type becomes valid again. This is internally consistent — just worth noting the dependency.

---

## Open Questions

**OQ-1 — Compile frontmatter stripping.** Does compile's source-reading path strip YAML frontmatter before feeding content to the compile LLM? If not, enriched sources will inject Pass-1 metadata into compile's entity extraction. Needs verification before Pass-1 ships. (See F-3.)

**OQ-2 — `kdb_signal` vs parent blueprint `verdict` field name.** D-89-2 says the rename was "propagated to parent blueprint the same commit." Has the parent blueprint §4.1 been updated from `verdict: pass | not_pass` to `kdb_signal: signal | noise`? Cross-check needed — if the parent still shows `verdict`, the two documents diverge on the field name of the routing gate.

**OQ-3 — User-added frontmatter key collision on schema migration.** When v0.2 adds a property the user had already added manually, what wins? (See F-4.) Needs a collision rule before schema additions land.

**OQ-4 — `reject_reason` semantics when `force_signal` overrides.** Should `reject_reason` be cleared, annotated, or preserved as-is when the verdict it explains is reversed? (See F-6.)

**OQ-5 — Config A (raw-drop) `force_noise` defaults.** The v0.1 defaults (`Daily Notes/**`, `Projects/**`) are vault-relative paths that won't match anything in `KDB/raw/`. The blueprint correctly notes "Config A (raw-drop) needs no default blacklist" (D-89-4 rationale) — but should this be stated in the config schema itself as a comment or convention, so future config authors don't cargo-cult the defaults into raw-drop contexts?

**OQ-6 — Wikilinks block delimiter (if Option A is chosen).** If the panel selects Option A, what delimiter separates the wikilinks block from the body? The delimiter must be (a) resistant to appearing in natural user content, (b) stable across re-enrichments, and (c) machine-parseable for regeneration. An HTML-comment delimiter (`<!-- KDB_WIKILINKS -->`) is the least-bad option but introduces non-markdown content into the body. Worth settling before implementation.

---

## Wikilink + corpus_index decision (§6)

**Recommendation: Option B for v0.1, with a B' design hook for v1.1.**

Option B (no corpus_index, no body wikilinks, frontmatter-only, compile owns all entity/LINKS_TO work) is the correct v0.1 choice. The reasoning turns on three principles the project has already ratified:

1. **Concrete-first** (`feedback_concrete_first_extract_later`). The corpus_index introduces cold-start bootstrap complexity, growing prompt-context cost (linear with corpus), replay-state archival overhead, and sequential-vs-batch ambiguity (OQ-89-6). These are real engineering costs for a feature — LLM-grounded wikilink discovery — whose marginal value over compile's existing entity extraction is unmeasured. Ship the minimum first; measure whether compile's link discovery is insufficient; THEN add corpus_index if the data demands it.

2. **No complexity for imaginary risk** (`feedback_no_imaginary_risk`). The risk that "compile's entity extraction won't find enough links" is hypothetical until proven. The compile pipeline already does NER + alias resolution (#74) + LINKS_TO edge creation from body wikilinks. Adding a second link-discovery layer before measuring whether the first layer is insufficient adds complexity for an unproven gap.

3. **D-88-10 single-call quality monitor.** The corpus_index adds prompt context that grows with corpus size. At some scale, the prompt budget forces either truncation (degrading link quality for large vaults) or a second call (violating D-88-10). Option B avoids this entirely — per-source cost is bounded.

**The B' hook:** Design `key_entities` to be the future anchor for corpus-aware wikilink suggestions. When v1.1 adds corpus_index, the mechanism is: (1) read `key_entities` from other enriched sources (they're already in frontmatter, no new IO path needed); (2) match current source's `key_entities` against the corpus; (3) emit `wikilink_suggestions` as a new optional frontmatter field. This preserves Option B for v0.1 while making the v1.1 upgrade a pure schema addition (additive, no migration, no breaking change).

Options A and C both introduce corpus_index at v0.1. Option A additionally modifies the source body, creating re-enrichment merge risk, sync-conflict surface area, and delimiter fragility. Option C avoids body modification but still carries the corpus_index complexity. Neither is justified until compile's link discovery is proven insufficient.

---

## Concerns on post-LLM override (§4)

The §4 mechanism is well-structured. Three concerns:

1. **Precedence** (F-1 above). Blacklist-wins-ties should be most-specific-glob-wins, consistent with D-88-4's bias-to-inclusion.

2. **`reject_reason` survival** (F-6 above). `force_signal` overriding `noise` to `signal` leaves a misleading `reject_reason` in the frontmatter.

3. **Config file format.** The blueprint shows YAML for scope-config (§4.1) but the NW-4 v0.4 §7 config uses JSON (`domains.json`). The project should standardize on one config format. The parent blueprint's existing dir-exclusion config is not specified in either format in the blueprint — but the NW-4 domain config is explicitly JSON. If the scope-config format is YAML while `domains.json` is JSON, that's a consistency irritant, not a bug. Worth flagging for v0.2 config unification.

**Overall assessment of §4:** The mechanism is correct. The LLM judges content substance; the deterministic layer handles location-based rules. The override audit trail preserves what the LLM emitted vs. what was applied. The open question (OQ-89-3) on precedence is the only structural gap, and it's resolvable in v0.2.

---

## Concerns on no-GraphDB-writes stance (§10)

The §10 stance is **correct and well-defended**. Three observations:

1. **The JOURNEY.md precedent is directly applicable.** The manifest.json → GraphDB transition arc was a lesson in premature storage-layer commitment — manifest.json carried ontology data it was never designed to carry, and the extraction was painful. Pass-1 writing to GraphDB before the enrichment shape is proven would repeat that mistake. The blueprint's deferral to v1.1+ ("prove the shape first, add the producer later") is the right application of that lesson.

2. **The producer contract mapping (§10.2) is honest.** Pass-1 doesn't pretend to be a full producer — it has no mutation payload and explicitly notes this. The "v1.1+ as a second producer" path (§10.3) correctly frames the separation: a new producer contract document, a new adapter, same journal + sidecar + retraction patterns. This is the right architectural placeholder — concrete enough to guide future work, abstract enough not to constrain v0.1.

3. **The compile-side pre-population note (§10.4) is a double-edged sword.** "Compile could pre-populate Source.domain from frontmatter.domain rather than re-extracting" — this is correct in principle (don't re-derive what Pass-1 already computed) but introduces a subtle coupling: if the domain vocabulary evolves between Pass-1 enrichment and compile time (e.g., a domain rename via aliases), the compile-side Source.domain would carry the old domain ID unless the compile pipeline also reads the aliases config. This is not a v0.1 concern (compile doesn't change), but it's a coupling point to flag for v1.x when compile starts consuming frontmatter.

**Recommendation:** Keep the §10 stance as-is. Add a note to §10.4: "When compile starts consuming Pass-1 frontmatter in v1.x, it must also consume the NW-4 aliases config to resolve historical domain IDs to current canonical IDs — otherwise domain renames cause Source.domain divergence." This is a future-integration guardrail, not a v0.1 change.
