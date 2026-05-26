# Task #89 v0.1 Blueprint Review — Qwen CLI (qwen3.7-max)

## Convergence

The v0.1 blueprint is architecturally sound in its core decisions. Specific points of agreement:

- **D-89-1 (7+6 property set):** The locked schema is well-scoped. The three-tier rationale (§2.3) is disciplined — ★★★ earns the LLM cost, ★★ adds provenance value, ★ is correctly deferred to the survey.
- **D-89-2 (kdb_signal naming):** `signal | noise` is a more accurate description of the judgment than `pass | not_pass`. Correct rename.
- **D-89-3 (post-LLM deterministic override):** Path-expression lists applied after the LLM call, with the LLM blind to the lists, is the right implementation of the `feedback_post_llm_deterministic_override` discipline.
- **D-89-5 (in-place frontmatter):** Filesystem-native, no parallel storage, Obsidian-renders-YAML — all correct. The body-preservation rule (§3.2) is well-defined.
- **D-89-6 (no GraphDB writes from Pass-1 in v1):** Correct deferral. The manifest.json → GraphDB-context-loader arc (JOURNEY.md §Iteration #3) demonstrates the cost of premature parallel-storage introduction. Pass-1's shape must be proven before it earns a producer contract.
- **D-89-10 (bias-to-inclusion):** "Uncertain → signal" with diagnostic fields preserved is the right default for a personal knowledge base where false-reject cost exceeds false-positive cost.
- **§5.3 replay archive:** Mirrors the `kdb-compile` sidecar pattern (Producer Contract §3.4) faithfully. The replay archive's inclusion of both `request` and `raw_response` enables deterministic re-derivation without re-firing the LLM — this is high-value.
- **§8 NW-1 substance criteria:** The explicit exclusion of file-location reasoning from the LLM's judgment (§8, §4.5) is consistent with the deterministic-override discipline. The `feedback_no_edge_predeclaration_no_hints` and `feedback_drop_the_word_shape` constraints are properly reflected.
- **§10.1 Pass-1 does NOT write GraphDB:** Correct. Compile remains the single GraphDB producer in v1. The v1.1+ second-producer path (§10.3) is the right sequencing — prove the enrichment shape first, then layer GraphDB writes.

## Findings

### F-1 — Parent blueprint §4.1 still uses `verdict: pass | not_pass` (§2, D-89-2)

**Section:** D-89-2, parent blueprint `docs/task88-ingestion-pipeline-blueprint.md` §4.1

D-89-2 states: *"Renamed from `verdict: pass | not_pass`. Renamed in parent blueprint §4.1 the same commit."* However, the parent blueprint v0.2 text at §4.1 still reads:

```
verdict: pass | not_pass,                # binary routing (D-88-4)
```

(line 206 of `docs/task88-ingestion-pipeline-blueprint.md`)

And §6.1 item 5 reads:

```
Pass-1 worth-verdict (binary `pass` / `not_pass`; "uncertain" → `pass`)
```

(line 341)

The rename was NOT propagated to the parent blueprint text. The v0.1 blueprint and the parent blueprint are now in drift: v0.1 says `kdb_signal: signal | noise`; parent says `verdict: pass | not_pass`.

**Recommendation:** Update parent blueprint §4.1 schema block and §6.1 item 5 to use `kdb_signal: signal | noise`. This should be done in the v0.2 commit of #89 to prevent the drift from compounding. A one-line amendment note in the parent blueprint's decision log (e.g., "D-88-4 amended: field renamed `kdb_signal`, values renamed `signal | noise` per D-89-2") would preserve audit trail.

### F-2 — `confidence` typed as `float 0.0-1.0` contradicts established project pattern (§2.1)

**Section:** §2.1 (field `confidence`), §2 schema

The v0.1 schema specifies `confidence: 0.0-1.0` (float) and the table confirms `float 0.0-1.0`. However, the project's established pattern for LLM-emitted confidence (D-83/84-8, `project_confidence_representation` memory) is:

> LLM emits confidence as bucketed enum (low | medium | high); system maps to configurable float at parse time (defaults: low→0.3, medium→0.5, high→0.8).

This pattern exists because LLMs are unreliable at producing calibrated floats but reliable at categorical judgments. The v0.1 schema contradicts this pattern by asking the LLM for a raw float.

**Recommendation:** Change `confidence` type to `enum: low | medium | high` with system-mapped float at parse time. The mapping table should be configurable (per the D-83/84-8 pattern). The `uncertainty_reason` trigger (§2.1: "populated when `confidence < 0.6`") should be rephrased as "populated when `confidence = low` OR when LLM had doubts despite `signal`." This aligns v0.1 with the established LLM-emits-enum → system-maps-float discipline.

### F-3 — `source_id` format in replay sidecar lacks identity-scheme specification (§5.3)

**Section:** §5.3

The replay sidecar schema shows `"source_id": "Investing/Buffett-letter-2020"` — a bare vault-relative path fragment. But the identity scheme differs by configuration:

- **Config A (raw-drop):** sources live at `~/Obsidian/KDB/raw/...`, so the source_id would be `KDB/raw/YT-transcriptions/some-video.md`
- **Config B (vault-in-place):** sources live at `~/Obsidian/...`, so the source_id would be `Investing/Buffett-letter-2020.md`

The parent blueprint §3.2.1 specifies identity = vault-relative path. The Producer Contract §3.5 specifies Obsidian's convention as `KDB/raw/<path>` (grandfathered namespace). Pass-1 operates across both configs, so the source_id convention needs to be explicit about what "vault-relative" means for each.

**Recommendation:** Specify in §5.3 that `source_id` follows the parent blueprint §3.2.1 identity scheme (vault-relative path from the Obsidian vault root). Add a note that for Config A sources, this includes the `KDB/raw/` prefix; for Config B, it is the path relative to `~/Obsidian/`. The example should show both: `"source_id": "KDB/raw/substack/some-post.md"` and `"source_id": "Investing/Buffett-letter-2020.md"`.

### F-4 — Override pseudocode (§4.3) does not specify composition with the full frontmatter emission

**Section:** §4.3

The override pseudocode returns a dict with `kdb_signal` and optionally `override`, but does not show how this composes with the rest of the Pass-1 frontmatter emission (domain, source_type, author, summary, key_entities, key_themes, audit fields). The pseudocode is correct in isolation but the integration point is unspecified:

```
def apply_overrides(source_path, llm_emission):
    if matches_any(source_path, force_signal):
        return {
            kdb_signal: "signal",
            override: { ... }
        }
```

Does this dict replace the entire frontmatter? Is it merged into the `llm_emission` dict? The answer is obviously "merge," but the blueprint should be explicit — especially because the `override` block is *absent* when no override fires (the LLM's original `kdb_signal` passes through), and present when an override fires. The merge semantics need to handle the conditional presence of the `override` key.

**Recommendation:** Rewrite the pseudocode to show the merge explicitly:

```
def apply_overrides(source_path, llm_emission):
    if matches_any(source_path, force_noise):    # blacklist-first per §4.4
        llm_emission.kdb_signal = "noise"
        llm_emission.override = {
            applied: "noise", rule: "force_noise",
            match: <glob>, llm_original: llm_emission.kdb_signal
        }
    elif matches_any(source_path, force_signal):
        llm_emission.kdb_signal = "signal"
        llm_emission.override = { ... }
    # else: no override key; llm_emission.kdb_signal passes through
    return llm_emission
```

This also fixes a subtle ordering issue: §4.4 says "blacklist wins ties" but the current pseudocode checks `force_signal` first. If both lists match, the `force_signal` branch fires and returns before `force_noise` is checked. The pseudocode ordering contradicts §4.4's stated precedence.

### F-5 — Pseudocode ordering contradicts §4.4 blacklist-wins-ties precedence (§4.3 vs §4.4)

**Section:** §4.3, §4.4

§4.4 states: *"Blacklist wins ties (defensive default). If a file matches both `force_signal` and `force_noise`, `force_noise` applies."*

But the §4.3 pseudocode checks `force_signal` first:

```
if matches_any(source_path, force_signal):
    return { kdb_signal: "signal", ... }
elif matches_any(source_path, force_noise):
    return { kdb_signal: "noise", ... }
```

This means a file matching both lists would get `signal` — the opposite of §4.4's stated intent.

**Recommendation:** Swap the order in the pseudocode: check `force_noise` first, then `force_signal`. The corrected version is shown in the F-4 recommendation above.

### F-6 — Lifecycle event taxonomy layer-mismatch with parent blueprint §3.5 (§5.2)

**Section:** §5.2

v0.1 §5.2 defines Pass-1 lifecycle events: `enriched`, `enrich_skipped`, `enrich_failed`, `enriched_force_overridden`.

Parent blueprint §3.5 defines Component #3 (Trigger) lifecycle events: `created`, `content_changed`, `path_changed`, `metadata_changed`, `deleted`, `revived`, `excluded`, `unchanged`.

These are two different taxonomies operating at different layers (Pass-1 outcome vs. source-change detection). The blueprint does not specify how Component #3 maps or composes these. When Component #3 detects a `content_changed` event and fires Pass-1, the Pass-1 outcome is `enriched` — but the downstream consumer (the compile router) needs to know both: *what changed* (content_changed) and *what Pass-1 decided* (enriched, signal).

**Recommendation:** Add a clarifying note to §5.2 that the Pass-1 lifecycle events are **outcome events** (what Pass-1 produced) distinct from Component #3's **detection events** (what changed in the source). The two compose as: detection event → fires Pass-1 → Pass-1 emits outcome event → routing by `kdb_signal`. Component #3 consumes both layers. The blueprint should name this explicitly to prevent implementers from conflating the two taxonomies.

### F-7 — Re-enrichment merge "user-added keys preserved" is underspecified (§3.3)

**Section:** §3.3

§3.3 states: *"Parse existing frontmatter (if any) — capture user-added keys that aren't in the Pass-1 schema (user may have added their own keys)"* and *"Pass-1 schema fields use new values; user-added keys preserved."*

Two edge cases are not addressed:

1. **Key collision:** If the user adds a key with the same name as a Pass-1 schema field (e.g., user writes `domain: my-personal-tag` in their frontmatter), the merge uses Pass-1's new value — silently overwriting the user's key. The user has no signal that their value was clobbered.

2. **Schema evolution:** If `schema_version` bumps and a previously user-defined key becomes a new Pass-1 schema field, the user's value is silently overwritten on next re-enrichment.

**Recommendation:** For case 1: Pass-1 should emit a warning in the run journal when a user-added key collides with a Pass-1 schema field name. The Pass-1 value wins (correct behavior — schema fields are authoritative), but the collision is surfaced for the user's awareness. For case 2: the `schema_version` field in the frontmatter already enables detection; the merge logic should check for version mismatches and log collisions. This is a low-cost addition to §3.3.

### F-8 — NW-1 substance criteria do not address multi-domain sources (§8.1)

**Section:** §8.1

NW-1 instructs the LLM to classify each source into exactly one domain (per D-NW4-1). But substantive sources often span two domains (e.g., an article on "how AI is transforming financial analysis" sits at `ai-ml` and `personal-finance`). The substance criteria do not instruct the LLM on how to handle this.

NW-4 v0.4 §4 (boundary rules) provides some guidance via axis-tagged disambiguation (vertical/horizontal/temporal). But boundaries are rules for edge cases, not a general instruction for multi-domain content.

**Recommendation:** Add a one-sentence instruction to §8.3 (prompt construction notes): *"When content genuinely spans two domains, classify by the domain that describes the source's primary contribution — what the source adds to the reader's understanding, not the background it assumes."* This gives the LLM a principled tiebreaker without introducing a `secondary_domain` field (which would violate D-NW4-1).

### F-9 — `source_type` placeholder includes types that are deterministically `noise` (§9.1 vs §4.2)

**Section:** §9.1, §4.2

The v0.1 `source_type` placeholder list includes `daily-note` and `meeting-notes` as valid enum values. But the `force_noise` defaults (§4.2) include `Daily Notes/**`. This creates a predictable pattern: the LLM fires Pass-1 on a daily note, classifies it as `source_type: daily-note` and `kdb_signal: <whatever>`, and then the deterministic override forces `noise` regardless.

This is not a contradiction — the LLM doesn't see the override lists (§4.5) — but it does mean the LLM is spending tokens on sources whose routing outcome is predetermined. At scale (a user with daily notes every day), this is a recurring waste.

**Recommendation:** This is acceptable for v0.1 — the LLM cost per source is low (deepseek-v4-flash:direct), and the audit trail value of having the LLM's actual judgment (even on force_noise sources) is preserved in the replay archive. However, flag for NW-5 telemetry: if `force_noise` sources constitute >30% of Pass-1 calls, consider a pre-Pass-1 short-circuit that skips the LLM call entirely for force_noise matches and emits a minimal frontmatter stub (`kdb_signal: noise`, `override: {...}`, `source_type: null`, all other fields null). File as **OQ-89-9**.

## Open Questions

### OQ-1 — Corpus index size bound for Options A and C (§6)

The blueprint estimates ~150K tokens for 1000 sources × 150 tokens per corpus_index entry. But this is additive to the source content + schema + NW-1 criteria already in the prompt. What is the total prompt budget, and at what corpus size does the prompt exceed the model's effective context window (not the theoretical limit, but the point where attention degradation measurably impacts property quality)?

NW-5 should include a prompt-budget test: measure property quality (especially `summary` coherence and `key_entities` recall) at corpus sizes 0, 100, 500, 1000, 2000 to find the degradation curve. If degradation begins before 1000 sources, Options A and C need a corpus-slicing strategy (domain-affinity, recency, sample) as a v1.1 work item.

### OQ-2 — `uncertainty_reason` population trigger (§2.1)

§2.1 says `uncertainty_reason` is populated "when `confidence < 0.6` OR when `kdb_signal = signal` but the LLM had doubts." If `confidence` moves to a bucketed enum (per F-2), the threshold becomes `confidence = low`. But the second clause ("LLM had doubts despite signal") is subjective — it requires the LLM to self-report doubt in a separate field. Is this a distinct LLM-emitted field, or is it derived from the confidence value?

**Recommendation:** Clarify that `uncertainty_reason` is an LLM-emitted free-text field (required when `confidence = low`, optional otherwise). The LLM populates it when it has specific reasons for uncertainty. This makes the trigger deterministic (`confidence = low` → required) rather than subjective ("had doubts").

### OQ-3 — Replay archive `source_content_hash` vs parent blueprint identity scheme (§5.3)

The replay sidecar schema includes `source_content_hash: <sha256>`. This is the content hash at Pass-1 time. But the parent blueprint §3.5 tracks SHA-256 as a change-detection signal. If a source is re-enriched (content changed → new Pass-1), the replay sidecar from the first enrichment has a different hash than the current content.

How does the replay system locate the correct sidecar for a given source? Is it keyed by `source_id` + `source_content_hash`? Or by `source_id` + `run_id`? The schema shows one sidecar per source per run, so `run_id` is the natural key — but this should be stated explicitly.

### OQ-4 — Frontmatter YAML serialization of list fields (§2)

`key_entities` and `key_themes` are `list[string]`. In YAML frontmatter, these can be serialized as either flow style (`[a, b, c]`) or block style (one item per line). Obsidian renders both, but they look different in the editor and have different merge-conflict profiles.

**Recommendation:** Specify flow style for short lists (`key_themes`, typically 2-5 items) and block style for longer lists (`key_entities`, which may grow). Or pick one style for all lists and stick with it. Consistency matters for Obsidian UX and for re-enrichment diff detection.

### OQ-5 — `author` extraction from sources with no explicit attribution (§2.1)

§2.1 says `author` is "LLM extracts from content + filename if available; `null` if not attributable." For Config B vault-in-place sources, the filename often carries author information (e.g., `Buffett-letter-2020.md`). But for Config A raw-drop sources, filenames are feeder-generated and may not carry author info (e.g., `substack/some-post.md`).

The instruction "filename if available" is vague — what filename patterns should the LLM look for? And should the prompt include the filename at all, or should the deterministic post-LLM layer extract author hints from the filename and pass them to the LLM as a hint?

**Recommendation:** The LLM should receive the source path as context (it already sees the content) and may extract author from filename patterns when obvious. But the deterministic post-LLM layer should NOT inject author hints — this would violate the content-only judgment principle. File as a prompt-construction note in §8.3.

### OQ-6 — Override match specificity in `override.match` field (§4.3)

The `override.match` field stores "the specific glob that fired." But path-expression matching may produce multiple matches (e.g., `Daily Notes/**` and `Daily Notes/2026/**` both match `Daily Notes/2026/05-25.md`). Which glob is stored — the first match? The most specific match? The one that determined the outcome?

Since the override logic uses `matches_any` (any-match triggers the override), the stored glob should be the one that was evaluated first in the list. But "first in list" depends on list ordering in the config file, which is fragile.

**Recommendation:** Store the most-specific matching glob (longest match), not the first match. This is more informative for debugging and more stable across config reorderings. Alternatively, store ALL matching globs as a list — but this adds frontmatter complexity for marginal value.

## Wikilink + Corpus_Index Decision (§6)

**Pick: Option C (filesystem corpus index + frontmatter wikilinks, no body modification)**

### Reasoning

The three options form a clean decision tree:

- **Option B** sacrifices one of Pass-1's highest-value contributions (LLM-grounded link discovery) for simplicity. The simplicity gain is real but not proportional to the value loss. Pass-1 without corpus awareness is a classification-and-summary pass — useful but not differentiated from what compile already does for entity extraction.
- **Option A** and **Option C** both provide corpus-grounded wikilink discovery. The difference is body modification. Option A's body-level wikilinks block creates three real failure modes:
  1. **Re-enrichment merge complexity** — the system must locate the wikilinks block delimiter, strip it, and regenerate without disturbing user edits above it. If the user edits text between the body and the wikilinks block (e.g., adds a paragraph), the delimiter detection becomes fragile.
  2. **OneDrive sync conflicts** — the vault is OneDrive-synced. A body modification by Pass-1 while the user has the file open in Obsidian creates a race condition that Option C avoids entirely.
  3. **Compile interaction** — compile reads source markdown and performs its own entity extraction on the body. A Pass-1-appended wikilinks block in the body introduces non-source content into compile's extraction scope. Compile would need to know to strip it, adding coupling.

**Option C** splits cleanly: Pass-1 owns LLM-grounded suggestion (in frontmatter); compile owns LINKS_TO edge creation (which it already does). The frontmatter is Pass-1's authoritative output; compile reads it as metadata input. No body modification means no merge complexity, no sync conflict, no compile coupling.

### Refinement (C' variation)

**Recommendation:** Add a `wikilink_suggestions` schema refinement. The v0.1 Option C schema in §6.4 shows:

```yaml
wikilink_suggestions:
  - target: Warren Buffett
    grounded_in_corpus: true
    occurrences_in_corpus: 7
```

The `occurrences_in_corpus` count is deterministic (countable from the corpus_index without LLM involvement). Move this to the deterministic post-LLM layer: the LLM emits `target` only; the post-LLM layer computes `grounded_in_corpus` and `occurrences_in_corpus` from the corpus_index it already constructed for the prompt. This keeps the LLM's job focused on semantic suggestion and the deterministic layer's job focused on counting.

Revised schema:

```yaml
# LLM emits:
wikilink_suggestions: [Warren Buffett, Berkshire Hathaway, See's Candies]

# Deterministic post-LLM layer enriches to:
wikilink_suggestions:
  - target: Warren Buffett
    grounded_in_corpus: true
    occurrences_in_corpus: 7
  - target: See's Candies
    grounded_in_corpus: false
    occurrences_in_corpus: 0
```

This also reduces the LLM's output token cost (just a list of strings, not structured objects) — a marginal but real attention-budget saving.

### Cold-start strategy (OQ-89-1)

For Option C, lean toward (a) from §13 OQ-89-1: run Pass-1 with empty corpus for early sources; re-enrich after corpus matures. This matches the #71 cold-start widening precedent. A v1.1 refinement could add a "corpus maturity trigger" that auto-queues re-enrichment when corpus reaches N sources (e.g., N=20) for the first time.

## Concerns on Post-LLM Override (§4)

### Alignment with `feedback_post_llm_deterministic_override`

The override mechanism is well-aligned with the established discipline: the LLM judges content only (§4.5); deterministic rules handle location/path-based decisions; audit fields preserve both the LLM's original judgment and the override details.

### Specific concerns

**1. F-4/F-5 above** — pseudocode ordering contradicts §4.4 precedence. This is a correctness bug in the pseudocode, not a design flaw, but it will propagate to implementation if not corrected.

**2. Override scope is narrow but may need expansion.** v0.1 overrides only `kdb_signal`. Future versions may want to override `domain` (e.g., force `daily-note` sources to `domain: undecided` without LLM involvement). The architecture supports this (add more override rules), but the v0.1 design does not explicitly note this extension point. A brief note in §4 that "override rules may expand beyond `kdb_signal` in v1.1+" would prevent implementers from hardcoding a signal-only override path.

**3. No override for `force_signal` audit.** The override block records the LLM's original `kdb_signal` when overridden. But it does not record whether the LLM's original judgment was correct or not — there is no feedback loop. For `force_noise` overrides, this means false-force-noise (overriding a genuine signal to noise) is invisible until a human audits the replay archive. NW-5 should include a "false-force-noise rate" measure: sample `force_noise` overrides where the LLM emitted `signal`, and have a human evaluate whether the LLM or the override was correct.

**4. Glob expressiveness.** The blueprint uses "path expression" / "glob" language but does not specify which glob dialect. Standard shell globs (`*`, `**`, `?`)? Extended globs (`!(pattern)`, `+(pattern)`)? Regex? The implementation choice affects what users can express in their config. Python's `pathlib.PurePath.match` supports basic globs; `fnmatch` is similar; `wcmatch` supports extended globs.

**Recommendation:** Specify the glob dialect in §4.1. Basic `**`/`*`/`?` globs (matching Python's `pathlib.PurePath.match` or `fnmatch`) are sufficient for v0.1. Extended globs can be added in v1.1+ if user demand emerges.

## Concerns on No-GraphDB-Writes Stance (§10)

### Alignment with `feedback_no_parallel_storage_to_authority`

The no-GraphDB-writes stance in v1 is correct and well-justified. The JOURNEY.md lesson (Iteration #3: manifest.json → GraphDB context loader arc) demonstrates that premature parallel storage creates drift risk that costs multiple iterations to unwind. Pass-1's enrichment shape is unproven; building a GraphDB producer contract on an unproven shape would repeat the manifest-as-connection-store error.

### Reach assessment: deferral to v1.1+ is correct

§10.3 defers Pass-1 as a second GraphDB producer to v1.1+. This is the right sequencing for three reasons:

1. **Shape-first, storage-second.** The enrichment shape (frontmatter schema) must be validated through at least one full ingestion cycle (Pass-1 → compile → Pass-2 → GraphDB) before the shape is stable enough for a second producer contract. If Pass-1's `key_entities` turns out to be unreliable, a GraphDB producer contract that writes `key_entities` to Source nodes would need immediate amendment.

2. **Compile remains the single producer.** The Producer Contract v1.0 was frozen for `kdb-compile`. Adding a second producer (Pass-1) requires either (a) a new producer contract document (§10.3's proposed `graphdb-kdb-enrichment-producer-contract.md`) or (b) extending the existing contract. Both are design work that should happen after the enrichment shape is proven.

3. **The adapter pattern absorbs it cleanly when the time comes.** The Producer Contract §2 shows the adapter interface is producer-agnostic. When Pass-1 becomes a second producer, it gets its own adapter (`graphdb_kdb/adapters/ingest_runs.py`) following the same B-lite pattern as `obsidian_runs.py`. No architectural change needed.

### One forward-looking note

When v1.1+ introduces Pass-1 as a second producer, the entity-ID namespacing question (Producer Contract §3.5) will resurface. Pass-1's `key_entities` are raw mentions (unresolved strings), not GraphDB entity IDs. The adapter will need to resolve these to existing Entity canonical_ids or create new Entity nodes — which is the same entity-resolution problem compile already solves. The v1.1 adapter design should reuse compile's entity-resolution logic rather than introducing a second resolution path. Flag this for the v1.1 producer contract design.

**END OF REVIEW**
