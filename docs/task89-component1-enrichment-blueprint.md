# Task #89 — Component #1 (Enrichment) Deep-Design: v0.1 Blueprint

**Status:** **v0.1 — drafted 2026-05-25** (evening session, on top of #88 NW-4 v0.4 closure earlier the same day). Pending 5-reviewer panel fire.

**Reviewer panel for v0.1 review** (Joseph's evening shift 2026-05-25 — **now all-CLI, all code-grounded**; first such arc in the project):
- **Codex** — CLI, code-grounded (panel incumbent)
- **Qwen CLI / qwen3.7-max** — CLI, code-grounded (**new** to panel)
- **Grok Build** — CLI, code-grounded (**new** to panel)
- **deepcode CLI / Deepseek** — CLI, code-grounded (Joseph migrated Deepseek from chat 2026-05-25; **new surface**)
- **agy / gemini-3.5-flash-high** — CLI, code-grounded (**re-trial** under explicit one-strike guardrail per [[feedback_gemini_review_only_guardrail]]; agy was previously dropped for overreach during #83/#84 era; gemini-3.5-flash-high is a newly available Flash variant)

The all-CLI panel is itself a methodology experiment for #89: chat reviewers with many reference docs were operationally heavy for Joseph; CLI reviewers read the repo natively. v0.1 review evaluates both content quality AND CLI behavior under explicit review-only guardrails.

**Lineage:**
- Parent: Task #88 — Ingestion System v0.2 blueprint (`docs/task88-ingestion-pipeline-blueprint.md`), Joseph-ratified 2026-05-25
- Domain vocab: NW-4 v0.4 (`docs/task88-nw4-domain-list-v0.4.md`), ratified 2026-05-25
- Strategic frame: tunnel-from-both-ends pivot (2026-05-23) — end B is the design focus
- Brainstorm session: 2026-05-25 evening (this document is the brainstorm output)

**Anchors:**
- `docs/task88-ingestion-pipeline-blueprint.md` v0.2 — parent blueprint (§5.1 outlines Component #1)
- `docs/task88-nw4-domain-list-v0.4.md` — controlled `domain` vocabulary (23 entries)
- `docs/graphdb-kdb-producer-contract.md` v1.0 — existing producer contract Pass-1 should align with (per Codex F3 from #88 v0.1 review)
- `docs/external-review-panel.md` — reviewer panel composition + flow
- `docs/JOURNEY.md` — three-iteration retrospective; manifest.json → GraphDB context loader arc
- Memory anchors: [[feedback_post_llm_deterministic_override]], [[feedback_no_parallel_storage_to_authority]], [[feedback_kdb_signal_naming]], [[feedback_drop_the_word_shape]], [[feedback_no_edge_predeclaration_no_hints]], [[feedback_concrete_first_extract_later]], [[feedback_no_imaginary_risk]]

**Sibling artifact (fires in parallel with this blueprint):**
- `docs/task89-additional-properties-survey-prompt.md` — multi-model survey asking *"what additional properties would justify being added to the same single Pass-1 call?"* (Joseph 2026-05-25). Results feed v0.2 synthesis.

---

## 1. Scope and frame

Component #1 (Enrichment) is the LLM pass that converts a raw source file into an enriched source: YAML frontmatter at the top carrying structured properties, plus the post-Pass-1 deterministic overrides applied to its `kdb_signal` field. It is the **first LLM call** of the ingestion pipeline, fired per source by Component #3 (Trigger).

**Component #1 owns:**
1. The Pass-1 LLM call: prompt construction, model invocation, response parsing, schema validation
2. The Pass-1 output schema: which properties are emitted and how they are typed
3. In-place YAML frontmatter writing to the source markdown
4. Post-Pass-1 deterministic layer: `force_signal` / `force_noise` path-expression overrides
5. The replay archive sidecar (request + raw response + parsed envelope, per [[project_milestone_validator_reconciler_live]] precedent)
6. NW-1 — Pass-1 substance criteria (the language used to instruct the LLM on signal-vs-noise judgment)
7. NW-7 — source_type controlled vocabulary (placeholder list in v0.1; full ratification deferred to sub-task)
8. The optional `corpus_index` function and its use in the LLM prompt (Section 6 — open decision)

**Out of scope for #89 (lives in other components / sub-tasks):**
- **When** to fire enrichment (lifecycle event taxonomy, change-detection signals, orphan-cascade depth) — Component #3 (Trigger), separate deep-design
- **Pass-2 worth-verdict** in compile (D-88-5, D-88-8) — end-A side of the tunnel; separate deep-design
- **Pass-1 benchmark / predeclared eval criteria** — NW-5, separate work item (per blueprint v0.2 §5.1; follows Task #75 / #87 pattern)
- **Orchestrator** — Component #6, separate deep-design (§5.6 of parent blueprint)
- **Move-from-compile capabilities** — Component #5, separate deep-design (domain canonicalization is the first concrete; NW-4 v0.4 ratified)
- **Source feeders** — out of v1 architecture per parent blueprint §5.5

**Where Pass-1 sits in the pipeline (refined from blueprint v0.2 §4.1):**

```
[source files in scope per Component #2 path-config]
        ↓
[PASS-1 LLM CALL]                       ← Component #1 (this doc §2)
        ↓
[POST-PASS-1 PROCESSING]                ← Component #1 (this doc §5)
    • schema validation
    • apply force_signal / force_noise overrides (§4)
    • resolve wikilink suggestions (option-dependent per §6)
    • write frontmatter in-place + replay-archive sidecar
    • emit lifecycle event for Component #3 to consume
        ↓
[PASS-1 ROUTING by kdb_signal]          ← signal → compile; noise → stop
        ↓
[COMPILE + PASS-2]                      ← end A; Pass-2 worth-verdict per D-88-8
        ↓
   KDB ontology
```

**Note on "gate" vocabulary** (Joseph correction 2026-05-25): the original parent blueprint v0.2 §4.1 used "DIR-EXCLUDE GATE" pre-Pass-1. That language is **retired here**. Pre-Pass-1 has **no gate**; it's config-driven path filtering. The same blacklist/whitelist pattern threads through all path-based decisions across components:

| Layer | Config list | Behavior |
|---|---|---|
| Component #2 (Source Storage) | `exclude_paths` | Never read (circularity guards: `KDB/wiki/*`, `KDB/state/*`, `.obsidian/*`, etc.) |
| Component #1 (this doc §4) | `force_noise` | Read, run Pass-1, deterministically override to `noise` (default: `Daily Notes/**`, `Projects/**`) |
| Component #1 (this doc §4) | `force_signal` | Read, run Pass-1, deterministically override to `signal` (default: empty) |
| Component #1 (this doc §4) | (neither matches) | Read, run Pass-1, LLM judges from content |

All four are config-driven path-expression decisions; none is a "gate" in the routing sense. The first actual gate is **post-Pass-1 routing by `kdb_signal`**: signal flows on to compile; noise stops here.

---

## 2. Pass-1 output schema (locked)

Component #1 emits, per source, the following YAML frontmatter at the top of the source markdown:

```yaml
---
# === KDB-Signal (the gate) ===
kdb_signal: signal | noise           # binary; "uncertain" routes to signal per D-88-4 bias-to-inclusion
                                      # may be overridden post-Pass-1 by force_signal / force_noise (§4)

# === Substantive classification ===
domain: <one of 23 NW-4 v0.4 ids>     # required; LLM picks one from canonical vocab
source_type: <one of NW-7 ids>        # required; LLM picks one (v0.1 placeholder list; NW-7 ratifies)
author: <string or null>              # source attribution; null if not attributable
summary: <1-3 sentences of prose>     # cheap-read distillation for humans + Pass-2 + queries
key_entities: [<string>, ...]         # raw mentions (people, companies, places, concepts) — unresolved
key_themes: [<string>, ...]           # 2-5 finer-grain than domain; free-form

# === Audit fields (Codex F4 from #88 v0.1 review) ===
confidence: 0.0-1.0                   # LLM-emitted confidence in the kdb_signal call
uncertainty_reason: <string or null>  # populated when confidence is low; "uncertain → pass" preserved
reject_reason: <string or null>       # populated when kdb_signal = noise; reason given by LLM
prompt_version: <semver>              # the prompt template version used
model: <model_id>                     # e.g., "deepseek-v4-flash:direct"
schema_version: <int>                 # this schema's version (starts at 1)

# === Deterministic override audit (only present if overridden) ===
override:                              # optional block; absent if no override applied
  applied: signal | noise              # the deterministic verdict
  rule: force_signal | force_noise     # which list matched
  match: <path expression>             # the specific glob that fired
  llm_original: signal | noise         # what the LLM had emitted before override
---

<original source body content unchanged>

<wikilinks block at end — see §6, open architectural decision>
```

### 2.1 Property definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `kdb_signal` | enum: `signal \| noise` | yes | The gate. Bias-to-inclusion per D-88-4: "uncertain" → `signal`. LLM emits content-only judgment; deterministic post-Pass-1 layer may override (§4). |
| `domain` | enum (23 NW-4 v0.4 ids) | yes | Substantive classification. LLM picks one. `undecided` is allowed; `science-technology` is gated by the catch-all self-check per NW-4 §4.4. |
| `source_type` | enum (NW-7 placeholder list) | yes | Source form. LLM picks one (e.g., `post`, `transcript-podcast`, `letter`). v0.1 placeholder list in §9; NW-7 ratifies. |
| `author` | string \| null | yes | Source attribution. LLM extracts from content + filename if available; `null` if not attributable. |
| `summary` | string (1-3 sentences) | yes | Prose distillation. Cheap-read downstream payoff: humans / Pass-2 / future queries scan without re-reading the source. |
| `key_entities` | list[string] | yes | Raw mentions — people, companies, places, concepts surfaced by the LLM. Unresolved (no GraphDB matching at Pass-1 time). Feeds wikilink layer in §6 (depending on chosen path). |
| `key_themes` | list[string] | yes | 2-5 themes finer-grain than `domain`. Free-form (per D-NW4-3 curation rule — no controlled vocab yet; promotion may come later via OQ-NW4-15 telemetry). |
| `confidence` | float 0.0-1.0 | yes | LLM-emitted confidence in the `kdb_signal` call. |
| `uncertainty_reason` | string \| null | yes | Populated when `confidence < 0.6` OR when `kdb_signal = signal` but the LLM had doubts. Preserves "uncertain → pass" audit trail. |
| `reject_reason` | string \| null | yes | Populated when `kdb_signal = noise`. The LLM's stated reason. Enables false-reject audit per D-88-3. |
| `prompt_version` | semver string | yes | The prompt template version. Bumped on prompt change. |
| `model` | string | yes | Model id (e.g., `deepseek-v4-flash:direct`). |
| `schema_version` | int | yes | Schema version, starts at 1; bumped on additive or breaking schema change. |
| `override` | object \| absent | no | Present only if deterministic post-Pass-1 layer overrode the LLM. See §4.3. |

### 2.2 Schema versioning + migration

- `schema_version` starts at `1` in v0.1.
- **Additive change** (new optional field): no version bump.
- **Required-field addition or removal**: bump `schema_version`. Replay-time migration follows the existing `kdb_compile` schema-migration pattern (precedent: #74, #76 chained migrations).
- **Prompt-only change** (re-wording, scope tightening): bump `prompt_version` semver. `schema_version` unchanged.
- The replay archive (§5.4) stores both versions per call; replay knows which migration path to apply.

### 2.3 Property tier rationale

The 7 substantive properties + 6 audit fields = the locked v0.1 set. Tier reasoning from the brainstorm:

- **★★★ tier** (must-have): `kdb_signal` (the gate), `domain` (routes into classification), `summary` (massive cheap-read payoff), `key_entities` (feeds wikilink layer).
- **★★ tier** (strong value): `author` (provenance metadata compile currently re-derives), `source_type` (filter axis at query time), `key_themes` (finer-grain than domain; accumulates evidence for OQ-NW4-15).
- **★ tier dropped**: `time_period` (handy but not load-bearing for v1; revisit if reviewers push back), `language` (English-only for v1), `property_tags` (overlaps `key_themes`; merged into `key_themes` for v0.1).

The sibling artifact (`docs/task89-additional-properties-survey-prompt.md`) fires the multi-model survey on what ADDITIONAL properties would justify being added — results feed v0.2 synthesis. Reviewers may propose additions in their v0.1 response as well; both inputs converge in v0.2.

---

## 3. Source modification mechanism

Component #1 modifies the source file **in-place**: it prepends a YAML frontmatter block at the top of the markdown.

```
BEFORE Pass-1 enrichment:
~/Obsidian/Investing/Buffett-letter-2020.md:
  # Berkshire 2020 Letter
  Dear shareholders,
  ...

AFTER Pass-1 enrichment:
~/Obsidian/Investing/Buffett-letter-2020.md:
  ---
  kdb_signal: signal
  domain: value-investing
  source_type: letter
  author: Warren Buffett
  summary: "..."
  key_entities: [Warren Buffett, Berkshire Hathaway, See's Candies, ...]
  ...
  ---
  # Berkshire 2020 Letter
  Dear shareholders,
  ...
  <wikilinks block at end — depending on §6 path>
```

### 3.1 Why in-place

Per Joseph's morning framing (2026-05-25): *"the LLM preprocessing pass that embeds frontmatter at top of source markdown + suggests wiki links at end."* Direct in-place embedding has these properties:

1. **Single source of truth.** The source file IS the enriched representation. No sidecar drift.
2. **Filesystem-native corpus.** A subsequent Pass-1 call can read the frontmatter from any other enriched source by scanning the filesystem — no separate store needed (see §6 Options A and C).
3. **Obsidian-native.** Frontmatter is rendered by Obsidian as YAML properties; immediately useful to the user when browsing the vault.
4. **Pass-2 / compile can read frontmatter directly.** No new IO path; compile's existing source reading just sees frontmatter.

### 3.2 Body content discipline

Pass-1 **does not modify the body content** beyond optionally appending a wikilinks block at the bottom (subject to §6's open decision). Specifically:

- Existing user-edited content (text, markdown structure, existing frontmatter from the user) is preserved
- Re-enrichment merges: the YAML frontmatter is updated (full re-write of the frontmatter block); the body remains intact
- If a wikilinks block was previously appended (Option A path), re-enrichment regenerates it; everything before the wikilinks block delimiter is preserved

### 3.3 Re-enrichment merge behavior

On a re-enrichment (e.g., source content changed → Component #3 fires Pass-1 again):

1. Parse existing frontmatter (if any) — capture user-added keys that aren't in the Pass-1 schema (user may have added their own keys)
2. Run Pass-1; obtain new frontmatter values
3. Merge: Pass-1 schema fields use new values; user-added keys preserved
4. Write merged frontmatter back in-place
5. Body content untouched (modulo §6 path A's wikilinks block regeneration)

### 3.4 Pristine-source recovery (not in v0.1; design hook)

For users who want to revert a source to pre-Pass-1 state, a future utility (post-v0.1) could strip the YAML frontmatter and the wikilinks block. Not in v0.1 scope. Filed as **OQ-89-2**.

### 3.5 Sync conflict considerations

The user's Obsidian vault is on OneDrive (synced from Windows). Pass-1 writes to vault files. Sync conflicts are possible if the user edits a source while Pass-1 is enriching it.

Mitigations for v0.1:
- Pass-1 reads the source's mtime + content-hash before the LLM call; if either changed by the time we go to write, abort the write and re-fire Pass-1 on the new content
- Sync-conflict files (OneDrive creates `<file>-conflict-<machine>.md`) are reported via the run journal but otherwise ignored by Component #3 (they are not first-class sources)

---

## 4. Configuration: force_signal / force_noise + post-Pass-1 overrides

### 4.1 Mechanism

Scope-config holds two path-expression lists (lives alongside existing dir-excludes from parent blueprint §3.3):

```yaml
# scope-config.yaml
force_signal:               # whitelist — always emit kdb_signal=signal post-Pass-1
  - <path expression>
force_noise:                # blacklist — always emit kdb_signal=noise post-Pass-1
  - Daily Notes/**          # v0.1 default
  - Projects/**             # v0.1 default
```

### 4.2 Defaults for v0.1

```yaml
force_signal: []                              # empty; user-populated
force_noise:
  - Daily Notes/**                            # diary-style content; not KDB ontology material
  - Projects/**                               # work-tracking; not KDB ontology material
```

User can override either list per their vault. Future v0.2+ may add domain-specific defaults; v0.1 ships only the path lists Joseph called out 2026-05-25.

### 4.3 Override application logic

After the Pass-1 LLM call returns (with the LLM's own `kdb_signal` emission), the deterministic post-Pass-1 layer runs:

```
def apply_overrides(source_path, llm_emission):
    if matches_any(source_path, force_signal):
        return {
            kdb_signal: "signal",
            override: {
                applied: "signal",
                rule: "force_signal",
                match: <which glob fired>,
                llm_original: llm_emission.kdb_signal
            }
        }
    elif matches_any(source_path, force_noise):
        return {
            kdb_signal: "noise",
            override: {
                applied: "noise",
                rule: "force_noise",
                match: <which glob fired>,
                llm_original: llm_emission.kdb_signal
            }
        }
    else:
        return {
            kdb_signal: llm_emission.kdb_signal,
            # no `override` key in frontmatter
        }
```

### 4.4 Precedence

**Blacklist wins ties** (defensive default). If a file matches both `force_signal` and `force_noise`, `force_noise` applies. The reasoning: explicit user intent to exclude (in `force_noise`) should not be silently overridden by an upstream-defined `force_signal` pattern.

This is filed as a watch-rule (OQ-89-3) — if reviewers push for an inverted precedence with rationale, revisit in v0.2.

### 4.5 LLM does not see the path lists

Per [[feedback_post_llm_deterministic_override]]: the LLM is not informed of the override lists; it judges content substance only. This keeps the LLM's job pure and the rules version-controllable in code, not prompt.

---

## 5. Post-LLM deterministic flow

After the LLM call returns, Component #1 runs:

1. **Schema validation.** The LLM response is parsed against the v0.1 schema. Required fields present, types correct, enums valid. Failure → retry once with structured-output retry pattern; second failure → mark Pass-1 as errored (audit trail) and abort.
2. **Apply override** (§4.3).
3. **Resolve wikilink suggestions** (§6 — depends on chosen architectural option).
4. **Write frontmatter in-place** to source markdown (§3).
5. **Write replay archive** to sidecar (§5.4).
6. **Emit lifecycle event** for Component #3 to consume (per parent blueprint §3.5 taxonomy — `enriched`, `enrich_failed`, `enrich_skipped`).

### 5.1 Failure modes + retries

| Failure | Handling |
|---|---|
| LLM connection error | Retry up to 2 times with backoff; if still failing, mark `enrich_failed` and abort |
| Schema validation failure | Retry once; if still failing, mark `enrich_failed` and abort |
| Sync-conflict file detected (post-LLM) | Abort write; mark `enrich_skipped`; re-queue for next Component #3 trigger |
| Write permission denied | Mark `enrich_failed`; surface in run journal |
| Empty / zero-length source | Skip Pass-1; emit `kdb_signal: noise` directly with `reject_reason: "empty source"`; no LLM call fired |

### 5.2 Lifecycle event emission

Pass-1 emits one of the following events per source (Component #3 consumes):

- `enriched` — successful Pass-1; frontmatter written
- `enrich_skipped` — pre-conditions not met (e.g., excluded by dir-config, sync-conflict file)
- `enrich_failed` — Pass-1 attempted but errored
- `enriched_force_overridden` — successful Pass-1, but post-Pass-1 override applied (subtype of `enriched`)

### 5.3 Replay archive sidecar

For every Pass-1 call (success or fail), Component #1 writes a replay-archive sidecar to:

```
~/Obsidian/KDB/state/ingest_runs/<run_id>/<source_id>.json
```

Schema:

```json
{
  "source_id": "Investing/Buffett-letter-2020",
  "source_path": "~/Obsidian/Investing/Buffett-letter-2020.md",
  "source_content_hash": "<sha256>",
  "request": { "prompt": "<full prompt>", "model": "...", "schema": "..." },
  "raw_response": { "status": "...", "body": "...", "usage": "..." },
  "parsed_envelope": { "kdb_signal": "signal", "domain": "...", "..." },
  "override": null | { "applied": "...", "rule": "...", "match": "...", "llm_original": "..." },
  "prompt_version": "1.0.0",
  "schema_version": 1,
  "timestamp": "2026-05-25T20:30:00-04:00",
  "outcome": "enriched" | "enriched_force_overridden" | "enrich_failed" | "enrich_skipped"
}
```

The replay-archive lets us:
- Re-derive the frontmatter deterministically without re-firing the LLM (cheap regeneration after a schema migration)
- Audit Pass-1 behavior over time (false-rejects, drift, prompt-version comparisons)
- Feed NW-5 benchmark scenarios (predeclared eval criteria, parallel work item)

### 5.4 Run journal

Each ingestion run produces a journal at:

```
~/Obsidian/KDB/state/ingest_runs/<run_id>/journal.json
```

Schema (mirrors `kdb-compile` journal pattern):

```json
{
  "run_id": "ingest-2026-05-25T20-30-00",
  "schema_version": "1.0",
  "event_type": "ingest",
  "sources_processed": 47,
  "by_outcome": { "enriched": 32, "enriched_force_overridden": 4, "enrich_skipped": 8, "enrich_failed": 3 },
  "prompt_version": "1.0.0",
  "model": "deepseek-v4-flash:direct",
  "force_signal_globs": [],
  "force_noise_globs": ["Daily Notes/**", "Projects/**"],
  "timestamp": "2026-05-25T20:30:00-04:00",
  "duration_seconds": 213
}
```

The journal is the unit Component #3 (Trigger) and the Orchestrator (Component #6) consume.

---

## 6. Open architectural decision: wikilinks + corpus index

**This is the load-bearing open decision for v0.1.** Three candidate paths are presented below for panel input. Each is internally consistent; each makes a different bet about where wikilinks live and whether Pass-1 reads other sources' frontmatter as context.

### 6.1 The underlying tension

Wikilinks are pointers to *other* content. A LLM running on a single source has no native way to know what exists in the rest of the corpus, and therefore can only guess at which entity mentions deserve wikilinks. Three responses are coherent:

- **Make Pass-1 corpus-aware** — give it semantic context from other sources' frontmatter so its wikilink suggestions are grounded (Options A and C).
- **Give up on Pass-1 wikilinks entirely** — keep Pass-1 single-source and let compile (which already does entity extraction and LINKS_TO edge creation) own all link work (Option B).
- **Recursive GraphDB dipping (agentic)** — explicitly considered and rejected as v1 scope (over-engineered; introduces multi-round LLM calls; replay complexity).

### 6.2 Option A — filesystem corpus index + body wikilinks

**Pass-1 reads other enriched sources' frontmatter; emits grounded wikilink suggestions; modifies source body to append a wikilinks block at the bottom.**

```
Pass-1 INPUT:
  - current source content
  - corpus_index(scope) → dict reading frontmatter from all other enriched sources in scope
    keyed by source_path; values: {kdb_signal, domain, summary, key_entities, key_themes, source_type, author}

Pass-1 LLM CALL:
  Prompt includes:
  - Current source content
  - Corpus index entries (or a curated slice if too large)
  - Instruction: "Suggest wikilinks for entities you see in the current source that
    appear in other sources' key_entities (grounded suggestions); do NOT invent
    connections; do NOT suggest wikilinks for entities not seen in corpus."

Pass-1 OUTPUT (frontmatter as in §2 + wikilinks block at bottom of body):
  ---
  <frontmatter>
  ---
  <original body>

  ## Suggested wikilinks
  - [[Warren Buffett]]      <!-- matched corpus entity -->
  - [[Berkshire Hathaway]]  <!-- matched corpus entity -->
  - See's Candies            <!-- LLM suggested but no corpus match; left as plain text -->
```

**Pros:**
- Wikilinks visible in Obsidian's graph view from the source page itself (UX win for vault navigation)
- LLM-grounded by construction (sees what's actually in the pipeline)
- Compile reads enriched source as today; wikilinks-in-body participate in compile's existing entity extraction

**Cons:**
- Modifies source body (re-enrichment must regenerate the wikilinks block cleanly without disturbing user-added content above it)
- Corpus index size grows linearly with corpus; at ~1000 sources × ~150 tokens per entry = ~150K tokens of prompt context (fits modern LLMs but starts to bite)
- Cold-start: first N sources have empty / sparse corpus; their wikilinks are weak until re-enrichment after corpus matures
- Re-enrichment merge complexity around the wikilinks block boundary (must use a stable delimiter to avoid clobbering user edits below it)

**Replay implications:** corpus snapshot used must be archived in the replay sidecar; replay reconstructs the LLM call from the snapshot.

**Scale implications:** corpus-index size is bounded by prompt budget. v2+ filtering strategies (domain-affinity slice, recency, sample) become work items if corpus outgrows budget.

### 6.3 Option B — no corpus index, no body wikilinks (Joseph's [1])

**Pass-1 is single-source. No corpus_index function. Frontmatter only; no wikilinks block appended. Compile handles all entity / LINKS_TO work as today.**

```
Pass-1 INPUT:
  - current source content (only)

Pass-1 LLM CALL:
  Prompt: source content + schema + NW-1 substance criteria

Pass-1 OUTPUT (frontmatter only; body untouched):
  ---
  kdb_signal: signal
  ...
  key_entities: [Warren Buffett, Berkshire Hathaway, See's Candies]   <-- raw mentions
  ...
  ---
  <original body, unchanged>
```

**Pros:**
- **Simplest possible.** No corpus_index complexity. No body modification. No cold-start. No corpus-snapshot replay overhead.
- Concrete-first: ship the minimum that emits useful frontmatter; add corpus-aware behavior in v1.1+ only if compile's existing entity work proves insufficient.
- Pass-1 cost is bounded (no growing prompt context).
- No "circles" risk — there's no architecture to drift into manifest.json territory.

**Cons:**
- No LLM-grounded wikilink discovery. Whatever discovery compile already does (NER + alias resolution via #74) is all we get.
- The frontmatter `key_entities` list is the only Pass-1 contribution to link discovery; compile must extract its own links from the body.
- Loses the "one of the payoffs that justifies the LLM cost" from the §2.3 brainstorm.

**Replay implications:** trivially replayable; no corpus state.

**Scale implications:** none (per-source cost; no corpus growth dependency).

### 6.4 Option C — filesystem corpus index + frontmatter wikilinks (no body modification)

**Pass-1 reads corpus index (like A); emits grounded wikilink suggestions in frontmatter as a property, not appended to body; compile reads frontmatter wikilink suggestions and uses them as input to its existing entity / LINKS_TO work.**

```
Pass-1 INPUT:
  - current source content
  - corpus_index(scope) → same as Option A

Pass-1 LLM CALL:
  Prompt: same as Option A (with corpus index context)

Pass-1 OUTPUT (frontmatter ONLY; body untouched):
  ---
  ...
  key_entities: [Warren Buffett, Berkshire Hathaway, See's Candies]
  wikilink_suggestions:                          # NEW frontmatter field for Option C
    - target: Warren Buffett
      grounded_in_corpus: true                   # entity found in other sources' key_entities
      occurrences_in_corpus: 7
    - target: Berkshire Hathaway
      grounded_in_corpus: true
      occurrences_in_corpus: 12
    - target: See's Candies
      grounded_in_corpus: false                  # candidate new entity
      occurrences_in_corpus: 0
  ...
  ---
  <original body, unchanged>
```

**Pros:**
- Corpus-grounded wikilink suggestions (LLM has empirical reason to suggest each one)
- Source body untouched (no merge / sync / Obsidian-overwrite risk on existing edits)
- Compile gets a high-quality input to its entity/LINKS_TO work (suggestions PASSES; compile DISPOSES)
- Frontmatter `grounded_in_corpus: false` cases surface candidate-new-entities — useful signal in their own right
- Re-enrichment merges are simple (just update frontmatter; body never touched)

**Cons:**
- Obsidian graph view doesn't directly benefit from Pass-1 (wikilinks aren't materialized in the body; only compile's separate wiki output creates body-level `[[...]]`)
- Corpus_index complexity remains (cold-start, growing context)
- Adds a new frontmatter field (`wikilink_suggestions`) — schema cost
- Two layers (Pass-1 suggests + compile renders) — slightly more moving parts than Option A

**Replay implications:** same as Option A (corpus snapshot archived).

**Scale implications:** same as Option A (corpus_index size bound by prompt budget).

### 6.5 Synthesis lean

**My current lean: Option C, narrowly.**

Reasoning:
- Option B sacrifices the LLM-grounded wikilink discovery, which is one of the brainstorm-identified payoffs that justifies the Pass-1 cost. Without it, Pass-1's value-add over what compile already provides is thinner.
- Option A's body modification has real failure modes (re-enrichment merge complexity, sync conflicts on user-edited bodies, Obsidian sync overwriting Pass-1's appended block). The Obsidian-graph-view UX benefit is real but not load-bearing — Joseph navigates primarily via compile's wiki output already (which has its own `[[wikilinks]]` between wiki pages).
- Option C splits cleanly: Pass-1 owns LLM-grounded suggestion; compile owns the LINKS_TO edge creation it already does. Concrete separation of concerns. Frontmatter-only is replay-safe + merge-safe + sync-safe.

That said, this is a close call between A and C; the panel may surface considerations I'm missing.

### 6.6 Explicit ask to reviewers

> **Which of Options A, B, C do you recommend for v0.1, and why?**
>
> Specifically:
> - Is Option C's frontmatter-only approach sufficient, or does Option A's body-wikilink-block UX justify the merge complexity?
> - Is Option B's simplicity worth giving up Pass-1 grounded wikilink discovery entirely?
> - Are there options A', B', C' (variations) we should consider?
> - For Option A or C: what's the cleanest cold-start strategy when the corpus is empty / sparse?

---

## 7. Model selection + cost

### 7.1 Default model

**`deepseek-v4-flash:direct`** — matches `kdb_compiler/kdb_compile.py:51` (the current compile-side default; cost-quality frontier winner per 2026-05-23 DeepSeek-direct experiment; ties `gemini-3.1-flash-lite` on FINAL=0.956). Configurable per `models.json`.

### 7.2 Cost guardrails

Per [[feedback_no_imaginary_risk]]: no automated cost-tracking / circuit-breakers in v0.1. Cost is user-managed externally (model selection, batch sizing, manual oversight).

### 7.3 Cost watch (for telemetry, not gating)

The run journal (§5.4) reports per-run sources processed + model + duration. Future telemetry may aggregate token usage if needed; v0.1 does not implement.

### 7.4 Multi-model evaluation

NW-5 (Pass-1 benchmark, separate work item) will evaluate multiple models on the same corpus. v0.1 default is `deepseek-v4-flash:direct`; benchmark may recommend a change.

---

## 8. NW-1 — Pass-1 substance criteria

The LLM's `kdb_signal` judgment is **content substance only** (per [[feedback_post_llm_deterministic_override]]). It is not asked about file location, file name, provenance, or any non-content metadata.

### 8.1 What counts as `signal`

The source contains substantive knowledge content that contributes to the KDB ontology: an idea, observation, explanation, framework, theory, case study, argument, analysis, or report of novel information.

Examples (illustrative; the LLM is given the framing, not the examples per [[feedback_no_edge_predeclaration_no_hints]]):
- An essay arguing for a particular investment approach
- A transcript explaining how the Federal Reserve manages monetary policy
- A book chapter analyzing Pabrai's portfolio decisions
- A news article reporting on a substantive economic shift
- A research note evaluating a company's quarterly performance

### 8.2 What counts as `noise`

The source does not contain substantive knowledge content. Most often:
- Workflow / task tracking (today I worked on X, tomorrow I will do Y, bullet list of TODOs)
- Conversational fragments / chatter / unstructured social messages
- Logs / system output / audit trails / data dumps without analysis
- Empty or near-empty files
- Pure references / pointers without their own substantive content (e.g., "see this PDF" with no other text)
- Meta-commentary about doing work on the KDB itself (session reflections, retrospectives) — note that file-location-based handling (`force_noise` for `Projects/**`, `Daily Notes/**`) covers most of this already; the LLM still applies the substance test as a safety net

### 8.3 Prompt construction notes

- The prompt does NOT use the word "shape" (per [[feedback_drop_the_word_shape]]). It refers to **content substance**.
- The prompt does NOT pre-declare cross-cut entity hints, edge expectations, or "for example" connections (per [[feedback_no_edge_predeclaration_no_hints]]).
- The prompt does NOT tell the LLM about `force_signal` / `force_noise` lists. The LLM judges content; deterministic layer handles location overrides.
- The prompt instructs the LLM that "uncertain → signal" (bias to inclusion per D-88-4).

### 8.4 Implementation surface for v0.1

The prompt template is `kdb_compiler/ingestion/pass1_prompt.j2` (Jinja2 template by precedent), versioned via `prompt_version` semver. v0.1 ships a concrete first cut; iteration is expected post-panel-review.

---

## 9. NW-7 — source_type controlled vocabulary placeholder

A parallel to NW-4 v0.4 (domain) — full ratification is a separate sub-task (NW-7). v0.1 ships with a placeholder list to unblock Pass-1; NW-7 ratifies the production set before v0.2.

### 9.1 v0.1 placeholder enumeration

| id | display |
|---|---|
| `blog` | Blog Post |
| `post` | Online Post (newsletter, forum, generic) |
| `article` | News / Magazine Article |
| `paper` | Academic / Research Paper |
| `book-chapter` | Book Chapter / Excerpt |
| `podcast` | Podcast (audio + show notes; no transcript) |
| `transcript-podcast` | Podcast Transcript |
| `transcript-youtube` | YouTube / Video Transcript |
| `transcript-interview` | Interview Transcript |
| `transcript-lecture` | Lecture / Talk Transcript |
| `letter` | Shareholder / Public Letter |
| `news` | News Report |
| `speech` | Speech / Address |
| `email` | Email |
| `daily-note` | Daily Note / Log Entry |
| `meeting-notes` | Meeting Notes |
| `other` | Source form not in this list |

**Overlap note** (Joseph 2026-05-25): some entries overlap (`blog` vs `post`; `podcast` vs `transcript-podcast`) — intentional. User-natural categories are kept even when they shade into one another; the LLM picks the most-specific fit per source. NW-7 ratifies the consolidated production set.

### 9.2 Config schema (mirrors NW-4 v0.4 §7)

```json
{
  "id": "transcript-podcast",
  "display": "Podcast Transcript",
  "scope": "Verbatim transcript of an audio podcast episode. Use when the source is the transcribed spoken content from a podcast format (host + guest, or solo monologue). For interviews specifically, prefer `transcript-interview`.",
  "aliases": []
}
```

### 9.3 NW-7 ratification scope

NW-7 (separate sub-task) ratifies:
- Final set of source_type entries (additions or removals from §9.1)
- Scope descriptions for each
- Aliases for renaming migration
- Same 5-reviewer panel pattern (Codex + Qwen CLI + Grok Build + Deepseek + Gemini Pro DR)

---

## 10. Producer contract alignment (Codex F3)

Codex's F3 from the #88 v0.1 review flagged that the design needed to map ingestion artifacts to the Producer Contract v1.0. This section addresses that for Pass-1 / Component #1 specifically.

### 10.1 Pass-1 does NOT write to GraphDB in v1

Per [[feedback_no_parallel_storage_to_authority]] and the architectural decision in this brainstorm, v0.1 keeps Pass-1 purely **filesystem-native**:

- Pass-1's output: in-place frontmatter on the source markdown + sidecar replay archive + run journal
- Compile remains the only GraphDB producer (writing Source / Entity / Page / Domain / Claim nodes + edges)
- The frontmatter Pass-1 emits is consumed by compile (which reads enriched source files anyway)

### 10.2 Pass-1 artifact taxonomy (mirroring Producer Contract §3)

| Producer Contract role | Pass-1 v0.1 artifact |
|---|---|
| Mutation payload | (none — Pass-1 doesn't mutate GraphDB) |
| Scan / state payload | The enriched source markdown itself (in-place frontmatter is the per-source state) |
| Run journal | `state/ingest_runs/<run_id>/journal.json` (§5.4) |
| Sidecar archive | `state/ingest_runs/<run_id>/<source_id>.json` per source (§5.3) |

### 10.3 v1.1+ — Pass-1 as a second producer (deferred)

Once enrichment proves out, v1.1+ MAY introduce Pass-1 as a SECOND GraphDB producer:
- New producer contract document: `docs/graphdb-kdb-enrichment-producer-contract.md` (sibling to the v1.0 producer contract)
- Pass-1 writes Source-level enrichment properties (summary, key_entities, etc.) to GraphDB Source nodes
- Same journal + sidecar + retraction patterns (matches #67 / #68 cleanup-event precedent)

This is **explicitly deferred from v0.1.** Reason: v0.1 must prove the per-source enrichment shape first; layering GraphDB writes on top of an unproven shape risks designing for a model that turns out to be wrong. Per [[feedback_concrete_first_extract_later]].

### 10.4 Compile reads enriched source

Compile (existing behavior) reads source markdown. With v0.1 in place, compile sees the new frontmatter at top + body underneath. Compile's existing entity extraction operates on the body; the new frontmatter is **available as metadata** for compile to use (e.g., compile could pre-populate Source.domain from frontmatter.domain rather than re-extracting). v0.1 does NOT require compile changes; v1.x compile-side amendments can leverage frontmatter as a follow-up.

---

## 11. NW-5 (Pass-1 predeclared eval criteria) — out of #89 scope

Per parent blueprint v0.2 §5.1, NW-5 is a separate work item that defines Pass-1's predeclared eval criteria following the Task #75 / #87 pattern. v0.1 of #89 lists the **surfaces** NW-5 will measure but does not define NW-5's criteria.

### 11.1 Surfaces NW-5 will measure

- **`kdb_signal` accuracy**: false-positive rate (noise marked as signal), false-negative rate (signal marked as noise), human-spot-check disagreement rate
- **`domain` accuracy**: classification accuracy against curated test corpus with known domains; `undecided` rate (target: <5% per OQ-NW4-13); `science-technology` catch-all rate (per OQ-NW4-14)
- **`summary` quality**: human-spot-check coherence, accuracy, succinctness; length compliance (1-3 sentences)
- **`key_entities` precision + recall**: against ground-truth entity lists
- **`source_type` accuracy**: against known types in test corpus
- **`author` accuracy**: against known authorship
- **`confidence` calibration**: low-confidence predictions ≠ high false rates
- **Wikilink quality (depending on §6 path)**: precision (grounded suggestions actually map to relevant entities), recall (entities mentioned that should have been suggested)
- **Latency + cost per source**: model selection input

### 11.2 NW-5 sequencing

NW-5 should land **before** Pass-1 implementation (per Task #75 precedent: eval criteria precede implementation). However, it does not block v0.1 of #89 (this blueprint) — #89 is the design; NW-5 + implementation can proceed in parallel after v0.2 ratification.

---

## 12. Decision log

### D-89-1 — Pass-1 schema is 7 substantive + 6 audit fields (2026-05-25)

**Decision:** Pass-1 output is the YAML frontmatter in §2.1 — `kdb_signal` + `domain` + `source_type` + `author` + `summary` + `key_entities` + `key_themes` + 6 audit fields. ★ tier (`time_period`, `language`, `property_tags`) dropped from v0.1.

**Rationale:** ★★★ + ★★ tier earn the LLM cost per the brainstorm. ★ tier is "stretching" per Joseph 2026-05-25. Multi-model survey (sibling artifact) fires in parallel to discover ADDITIONAL properties for v0.2.

### D-89-2 — `kdb_signal: signal | noise` naming (2026-05-25)

**Decision:** Pass-1 binary content judgment is `kdb_signal` field, values `signal | noise`. Renamed from `verdict: pass | not_pass`.

**Rationale:** Per [[feedback_kdb_signal_naming]] — verdict is courtroom-shaped; the actual question is signal-vs-noise. Renamed in parent blueprint §4.1 the same commit.

### D-89-3 — Post-LLM deterministic override via path-expression lists (2026-05-25)

**Decision:** Two scope-config lists `force_signal` + `force_noise`, path expressions. Applied post-Pass-1. Blacklist wins ties. Audit fields preserve LLM emission + override rule.

**Rationale:** Per [[feedback_post_llm_deterministic_override]] — provenance / location / path decisions live outside the LLM. Joseph confirmed the symmetric whitelist + blacklist shape 2026-05-25.

### D-89-4 — Default `force_noise: [Daily Notes/**, Projects/**]` (2026-05-25)

**Decision:** v0.1 ships with these two globs in `force_noise`. `force_signal: []` empty.

**Rationale:** Joseph 2026-05-25: "Daily Notes/** goes to the black list… maybe Projects/** as well." Covers the vault-side Config B meta-commentary cases. Config A (raw-drop) needs no default blacklist (users explicitly drop into `raw/`).

### D-89-5 — In-place YAML frontmatter modification (2026-05-25)

**Decision:** Pass-1 writes a YAML frontmatter block at the top of the source markdown, in-place. Body content preserved (modulo §6 path A's wikilinks block).

**Rationale:** Joseph's morning framing: "embeds frontmatter at top of source markdown." Filesystem-native; no parallel storage; Obsidian-renders YAML properties natively.

### D-89-6 — Pass-1 does NOT write GraphDB in v1 (2026-05-25)

**Decision:** Component #1 remains purely filesystem-native. Compile is the only GraphDB producer in v1. v1.1+ may introduce Pass-1 as a second producer (separate contract); deferred.

**Rationale:** Per [[feedback_no_parallel_storage_to_authority]] — adding GraphDB writes to Pass-1 risks parallel-storage drift before the enrichment shape has been proven. Concrete-first.

### D-89-7 — Drop "shape" from Pass-1 prompt + criteria language (2026-05-25)

**Decision:** Pass-1 substance criteria (§8) do not use the word "shape" to describe what is or isn't signal. Substance-focused language only.

**Rationale:** Per [[feedback_drop_the_word_shape]] — Joseph 2026-05-25 corrected the project-wide use of "shape" as a vague descriptor. Applies here to NW-1 criteria language and the prompt template.

### D-89-8 — Build mode: Claude solo draft → 5-CLI-reviewer panel (2026-05-25)

**Decision:** v0.1 drafted by Claude (this document). Fires at expanded **all-CLI** 5-reviewer panel (Codex + Qwen CLI/qwen3.7-max + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high). v0.2 folds reviewer feedback.

**Rationale:** Matches NW-4 v0.2 pattern (most recent sub-component precedent) — but with a substantive shift: all five reviewers are now code-grounded CLIs (vs. NW-4's 3 CLI + 2 chat). Four reviewers are new to the panel — Qwen CLI (qwen3.7-max), Grok Build, deepcode CLI (Deepseek migrated from chat surface), and agy/gemini-3.5-flash-high. The last is re-trialed under an explicit one-strike guardrail per [[feedback_gemini_review_only_guardrail]] — agy was previously dropped for overreach during #83/#84. Joseph's reasoning for the all-CLI shift (2026-05-25): chat reviewers with many reference docs were operationally heavy; CLI reviewers read the repo natively. The §16 reviewer prompt header enforces a strict no-repo-modification guardrail to enable fair evaluation across all four new-to-panel reviewers.

### D-89-9 — source_type controlled vocabulary deferred to NW-7 (2026-05-25)

**Decision:** v0.1 ships with a 15-entry placeholder list (§9.1). NW-7 (separate sub-task) ratifies the production set before v0.2.

**Rationale:** Same pattern as NW-4 v0.4 ratified the `domain` vocabulary. Avoids drift (per [[feedback_name_must_match_contents]]).

### D-89-10 — Bias-to-inclusion preserved (uncertain → signal) (2026-05-25)

**Decision:** Pass-1 routes uncertainty to `signal` (consistent with D-88-4 from parent blueprint). Diagnostic preserved via `uncertainty_reason` and `confidence` audit fields (per Codex F4).

**Rationale:** D-88-4 from parent blueprint; not re-litigated here. Audit preserves false-positive vs false-negative trade-off observability.

### D-89-11 — Wikilinks + corpus_index — OPEN for v0.1 review (2026-05-25)

**Decision:** Not closed at v0.1. Three candidate options in §6 (A: corpus_index + body wikilinks; B: no corpus_index + no body wikilinks; C: corpus_index + frontmatter wikilinks). Synthesis lean = C (narrowly). Reviewer panel explicitly asked to recommend.

**Rationale:** Joseph (2026-05-25): present multiple options to the panel; let new CLI reviewers (Qwen 3.7-max, Grok Build) demonstrate design judgment, not just review accuracy. v0.2 closes this decision.

---

## 13. Open questions

### OQ-89-1 — corpus_index cold-start strategy (gated on §6 outcome)

If Option A or C is chosen, how should Pass-1 behave when the corpus is empty or sparse (first N sources)?

Candidates:
- (a) Run Pass-1 with empty corpus; wikilinks weak for early sources; re-enrich after corpus matures
- (b) Defer Pass-1 until corpus reaches threshold N; awkward (no way to bootstrap)
- (c) Bootstrap mode: first batch processes without corpus_index; subsequent batches use it

Lean: (a) — same pattern as #71 cold-start widening for compile-side context. Reviewers may have better.

### OQ-89-2 — Pristine-source recovery utility (post-v0.1)

A future utility could strip Pass-1 frontmatter + wikilinks block to recover the pre-Pass-1 source. Not in v0.1 scope; filed as a v1.1+ candidate.

### OQ-89-3 — Override precedence (blacklist vs whitelist)

v0.1 default: blacklist wins ties (defensive). Reviewers may push for whitelist-wins or most-specific-glob-wins. Decision lockable in v0.2.

### OQ-89-4 — `key_themes` vs `property_tags` merge (carried from §2.3)

v0.1 merges `property_tags` (★ tier from brainstorm) into `key_themes` (★★ tier). Reviewers may push to separate them. Tie-break in v0.2.

### OQ-89-5 — Re-enrichment trigger surface vs Component #3

Component #1 exposes: `enrich(source_path, last_state) → enriched_source + new_state + lifecycle_event`. Component #3 owns when to call. Surface only is in v0.1; full Component #3 deep-design is its own arc. Reviewers may flag misalignment.

### OQ-89-6 — Multi-source re-enrichment batching

When Component #3 fires re-enrichment on N sources in one run, should Pass-1 process them sequentially (each one re-reads corpus_index including its own freshly-updated frontmatter), or batch-then-write (all read same corpus snapshot)?

Sequential lean (each sees freshest corpus) per concrete-first. Decision lockable in v0.2.

### OQ-89-7 — Schema version vs prompt version bumping rules

Currently §2.2 distinguishes additive schema change (no bump), required-field add/remove (schema bump), prompt-only change (prompt version bump). Reviewers may push for more nuanced rules.

### OQ-89-8 — `confidence` semantics + threshold for `uncertainty_reason` population

§2.1 says `uncertainty_reason` is populated when `confidence < 0.6` OR when LLM had doubts despite signal. The 0.6 threshold is arbitrary; could be empirically tuned via NW-5.

---

## 14. v0.1 amendment summary (carried into v0.2)

| ID | Source | Status | Where in v0.1 |
|---|---|---|---|
| D-89-1 | Brainstorm 2026-05-25 | Locked | §2 + §12 |
| D-89-2 | Brainstorm 2026-05-25 (rename verdict→KDB-Signal) | Locked + propagated to parent blueprint | §2 + §12 |
| D-89-3 | Brainstorm 2026-05-25 (path-expression overrides) | Locked | §4 + §12 |
| D-89-4 | Brainstorm 2026-05-25 (Daily Notes/Projects defaults) | Locked | §4.2 + §12 |
| D-89-5 | Brainstorm 2026-05-25 (in-place frontmatter) | Locked | §3 + §12 |
| D-89-6 | Brainstorm 2026-05-25 (no GraphDB writes from Pass-1 v1) | Locked | §10 + §12 |
| D-89-7 | Brainstorm 2026-05-25 (drop "shape" word) | Locked | §8 + §12 |
| D-89-8 | Brainstorm 2026-05-25 (build mode) | Locked | §0 header + §12 |
| D-89-9 | Brainstorm 2026-05-25 (NW-7 deferred) | Locked | §9 + §12 |
| D-89-10 | Carried from D-88-4 | Locked | §2.1 + §12 |
| D-89-11 | Brainstorm 2026-05-25 (wikilinks + corpus_index) | **OPEN — reviewers asked** | §6 + §12 |

---

## 15. Things to consult during review

- `docs/task88-ingestion-pipeline-blueprint.md` v0.2 — parent blueprint (Component #1 outlined in §5.1)
- `docs/task88-nw4-domain-list-v0.4.md` — `domain` controlled vocab (23 entries Pass-1 picks from)
- `docs/graphdb-kdb-producer-contract.md` v1.0 — existing producer contract pattern
- `docs/JOURNEY.md` — manifest.json → GraphDB context loader retrospective (relevant to §10's no-GraphDB-writes decision; reviewers should validate the no-parallel-storage rule applies)
- `docs/external-review-panel.md` — panel composition + flow + one-strike rule for overreach
- `kdb_compiler/kdb_compile.py` — existing CLI entry point + model default to align with
- `kdb_compiler/schema.py` — existing GraphDB schema + migration pattern (relevant to §10.3 v1.1+ second-producer deferral)
- Memory: [[feedback_no_parallel_storage_to_authority]] (the architectural discipline that drove §3 + §6 + §10 to filesystem-native)
- Memory: [[feedback_post_llm_deterministic_override]] (drove §4 + §8.3 — LLM judges content only)
- Memory: [[feedback_kdb_signal_naming]] (drove §2 naming)
- Memory: [[feedback_drop_the_word_shape]] (drove §8 language discipline)
- Memory: [[feedback_no_edge_predeclaration_no_hints]] (drove §8.3 + §6 — no edge hints, no "for example" pre-declarations)

---

## 16. Reviewer prompt header (for panel fire)

When firing this v0.1 at the reviewer panel, the prompt should include the following text. The repo-modification guardrail is **CRITICAL** — four of five reviewers are new to the panel, and `agy/gemini-3.5-flash-high` is on an explicit one-strike re-trial after previous overreach.

```
You are reviewing Task #89 — Component #1 (Enrichment) v0.1 blueprint for the
KDB Ingestion System. Anchor docs are listed in §15 of the blueprint.

1. REPO-MODIFICATION GUARDRAIL (CRITICAL — read first)

   Create EXACTLY ONE file in this CLI session. Your output file path depends
   on your reviewer identity:

     - Codex:        docs/task89-v0.1-review-codex.md
     - Qwen CLI:     docs/task89-v0.1-review-qwen.md
     - Grok Build:   docs/task89-v0.1-review-grok.md
     - deepcode CLI: docs/task89-v0.1-review-deepseek.md
     - agy:          docs/task89-v0.1-review-gemini.md

   Do NOT modify, create, or delete any other files in the repository.
   Do NOT modify code, schemas, configuration, blueprints, or other docs.
   Do NOT propose implementation patches or write code.

   Your entire CLI session output must be confined to producing your single
   review file. Violating this guardrail (e.g., editing other files,
   committing changes, modifying code) results in de-selection from future
   review cycles per the one-strike rule (docs/external-review-panel.md).

   Three of five reviewers are new to the panel: Qwen CLI (qwen3.7-max),
   Grok Build, deepcode CLI. agy/gemini-3.5-flash-high is an explicit re-trial
   after previously being dropped for overreach. This review evaluates both
   content quality AND CLI behavior under the guardrail above.

2. REVIEWER ROLE

   - Identify factual errors, contradictions, scope gaps, missing OQs
   - Recommend a path for the OPEN decision in §6 (Options A / B / C),
     with reasoning
   - Flag concerns about the post-LLM override mechanism (§4)
   - Flag concerns about the no-GraphDB-writes-from-Pass-1 stance (§10)
   - Cross-check the blueprint against parent blueprint and producer
     contract (anchors in §15)
   - Cite specific section / decision IDs (e.g., "D-89-3", "§4.4") when
     raising findings

3. OUTPUT FORMAT (mirrors NW-4 v0.2 panel pattern)

   In your single review file, include:
   - Convergence section (where you agree with the blueprint as-is)
   - Findings list (F-1, F-2, ... each with section reference + recommendation)
   - Open questions (OQ list — gaps you'd want closed before implementation)
   - Wikilink decision recommendation (your pick of A / B / C, with reasoning)
```

The additional-properties survey is a separate artifact at
`docs/task89-additional-properties-survey-prompt.md`; it has its own per-reviewer
output file (`docs/task89-additional-properties-survey-<model>.md`) and can fire
in the same panel cycle without conflict.

---

**END OF BLUEPRINT v0.1**
