# Task #89 — Component #1 (Enrichment) Deep-Design: v0.2.2 Blueprint

**Status:** **v0.2.2 — amended 2026-05-26 night** (Pass-1↔Pass-2↔context-loader integration loop-close: D-89-18 retracted; D-89-19/D-89-20 ratified). Earlier same day: v0.2.1 (frontmatter sectionalization + compile-consumption-in-v1); v0.2 folded after round-2 architecture review panel (5/5 clean) + Joseph-led deliberation. Round-1 property additions deferred to **v0.3** (separate deliberation pass).

**v0.2.2 amendment sources:**
- 2026-05-26 night Pass-1 fields consumer-purpose deliberation (Joseph-led; triggered by Phase E checkpoint Bug #2)
- Two new locked decisions: D-89-19 (Source.summary = mechanical append of key_themes; persisted; replaces D-89-18) + D-89-20 (drop `key_entities`; add `entity_search_keys` ≤10; Task #90 input contract)
- One full retraction: D-89-18 (LLM merge — replaced by D-89-19's mechanical concat + D-89-20's structural-graph signal channel)
- One partial retraction: D-89-17 (the "TREAT key_entities as seed candidates" clause; rest stays in force)
- Task #90 (Context-loader T2-rewrite) input contract locked in `docs/TASKS.md`
- Session checkpoint: `docs/session-handoff-2026-05-26-task89-evening-v0.2.2-key_themes-loop-close.md`

**v0.2.1 amendment sources:**
- 2026-05-26 evening "what is frontmatter FOR" deliberation (Joseph-led)
- Three locked decisions: D-89-16 (frontmatter sectionalization), D-89-17 (compile consumes in v1), D-89-18 (key_themes merge via compile LLM — **note: D-89-18 retracted in v0.2.2**)
- Two new principle memories: [[feedback_integration_preconditions_are_architectural]], [[feedback_prompt_template_definition_plus_examples]]
- Sharpening of [[feedback_no_edge_predeclaration_no_hints]] (examples-for-shape OK; examples-for-edges NOT OK)
- See `docs/task89-deliberation-wikilinks-frontmatter.md` §12+ for the full lineage

**v0.2 fold sources:**
- 5 round-2 architecture review responses (`docs/task89-v0.1-review-{codex,qwen,grok,deepseek,gemini}.md`)
- A vs B vs C deliberation + frontmatter-mechanism deliberation (`docs/task89-deliberation-wikilinks-frontmatter.md`)
- Parent blueprint amendment of D-88-11 (commit `092b44f`)

**Reviewer panel for v0.1 review** (Joseph's evening shift 2026-05-25 — **all-CLI, all code-grounded**; first such arc in the project):
- **Codex** — CLI, code-grounded (panel incumbent)
- **Qwen CLI / qwen3.7-max** — CLI, code-grounded (**new** to panel)
- **Grok Build** — CLI, code-grounded (**new** to panel)
- **deepcode CLI / Deepseek** — CLI, code-grounded (Joseph migrated Deepseek from chat 2026-05-25; **new surface**)
- **agy / gemini-3.5-flash-high** — CLI, code-grounded (**re-trial** under explicit one-strike guardrail per [[feedback_gemini_review_only_guardrail]]; agy was previously dropped for overreach during #83/#84 era; gemini-3.5-flash-high is a newly available Flash variant)

**Panel-behavior outcome (v0.1 → v0.2):** 5/5 reviewers honored the no-repo-modification guardrail. agy completed 2-for-2 on its one-strike re-trial (round-1 property survey + round-2 architecture review).

**Lineage:**
- Parent: Task #88 — Ingestion System v0.2 blueprint (`docs/task88-ingestion-pipeline-blueprint.md`), Joseph-ratified 2026-05-25; D-88-11 amended 2026-05-26 (commit `092b44f`)
- Domain vocab: NW-4 v0.4 (`docs/task88-nw4-domain-list-v0.4.md`), ratified 2026-05-25
- Strategic frame: tunnel-from-both-ends pivot (2026-05-23) — end B is the design focus
- v0.1 brainstorm: 2026-05-25 evening
- v0.2 deliberation + fold: 2026-05-26

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
1. The Pass-1 LLM call: prompt construction, model invocation, structured-JSON response parsing, schema validation
2. The Pass-1 output schema: which properties are emitted and how they are typed
3. Deterministic post-processor that serializes the validated JSON envelope to YAML frontmatter and embeds it in the source markdown (D-89-13)
4. Post-Pass-1 deterministic override layer: `force_signal` / `force_noise` path-expression overrides
5. The replay archive sidecar (request + raw response + parsed JSON envelope, per [[project_milestone_validator_reconciler_live]] precedent)
6. NW-1 — Pass-1 substance criteria (the language used to instruct the LLM on signal-vs-noise judgment)
7. NW-7 — source_type controlled vocabulary (placeholder list in v0.1; full ratification deferred to sub-task)

**Out-of-#89 wikilink resolution (D-89-12 lockdown):** Pass-1 emits `key_entities` as a flat string list. All wikilink / entity-to-entity / `LINKS_TO`-edge resolution happens in compile against the live GraphDB. See `docs/task89-deliberation-wikilinks-frontmatter.md` for the full A vs B vs C deliberation lineage.

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
    LLM returns structured JSON envelope (D-89-13)
        ↓
[POST-PASS-1 PROCESSING]                ← Component #1 (this doc §5)
    • schema validation on the JSON envelope
    • apply force_signal / force_noise overrides to the envelope (§4)
    • serialize JSON → YAML frontmatter; embed in source (§3)
    • write replay-archive sidecar (envelope, request, raw response)
    • emit lifecycle event for Component #3 to consume
        ↓
[PASS-1 ROUTING by kdb_signal]          ← signal → compile; noise → stop
        ↓
[COMPILE + PASS-2]                      ← end A; Pass-2 worth-verdict per D-88-8
                                          must strip YAML frontmatter before
                                          its LLM call (§10.5 integration precondition)
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

## 2. Pass-1 output schema (locked, sectionalized in v0.2.1 per D-89-16)

Component #1 emits, per source, YAML frontmatter at the top of the source markdown, organized into **two sections** (D-89-16):

- **GraphDB-input section** — fields Pass-2 (compile) reads and uses for GraphDB construction
- **Audit section** — Pass-1's own audit/replay metadata; **Pass-2 ignores this section**

Both sections live in the same YAML frontmatter block on disk (single source of truth; user sees both in Obsidian; replay archive corresponds to both).

```yaml
---
# ============================================================
# GraphDB-input section — Pass-2 (compile) consumes (D-89-17)
# ============================================================

# --- Routing gate ---
kdb_signal: signal | noise           # binary; "uncertain" routes to signal per D-88-4 bias-to-inclusion
                                      # may be overridden post-Pass-1 by force_signal / force_noise (§4)
                                      # Routes Source into/out of compile via Component #3/#6 upstream

# --- Substantive classification (compile reads + writes to GraphDB) ---
domain: <one of 23 NW-4 v0.4 ids>     # required; → Source.domain (new column per D-89-17)
source_type: <one of NW-7 ids>        # required; → Source.source_type (existing column)
author: <string or null>              # required; → Source.author (new column per D-89-17)
summary: <1-3 sentences of prose>     # required; → Source.summary (new column per D-89-17)
                                      #   compile LLM merges with key_themes when writing (D-89-18)
key_entities: [<string>, ...]         # required; → seeds Entity nodes + SUPPORTS edges (existing)
key_themes: [<string>, ...]           # required; 2-5 finer-grain themes
                                      #   stays separate in frontmatter; compile LLM merges into
                                      #   Source.summary at write time (D-89-18); no Source.themes column

# ============================================================
# Audit section — Pass-1's own; Pass-2 IGNORES (D-89-16)
# ============================================================

confidence: 0.0-1.0                   # LLM-emitted confidence in the kdb_signal call
uncertainty_reason: <string or null>  # populated when confidence is low; "uncertain → pass" preserved
reject_reason: <string or null>       # populated when kdb_signal = noise; reason given by LLM
prompt_version: <semver>              # the prompt template version used
model: <model_id>                     # e.g., "deepseek-v4-flash:direct"
schema_version: <int>                 # this schema's version (starts at 1)

# Deterministic override audit (always emitted per Grok OQ-3 v0.2 fix) ---
override:
  applied: signal | noise | null      # the deterministic verdict (null if no override fired)
  rule: force_signal | force_noise | null
  match: <path expression> | null     # the specific glob that fired
  llm_original: signal | noise        # what the LLM had emitted before override
  reject_reason_cleared: <string> | null  # if force_signal cleared an LLM reject_reason
---

<original source body content unchanged>
```

**Note on the audit section staying in frontmatter (D-89-16 rationale):** The audit fields are Pass-1's own metadata about *how this source was enriched* — confidence in the call, model used, prompt version, override rationale. Per [[feedback_sources_stay_static_intrinsic_frontmatter_only]], these describe how Pass-1 processed the source (intrinsic to this enrichment instance), not derived relationships to other sources. They live in frontmatter for:
- User visibility (Obsidian renders them as Properties; user can spot low-confidence sources or overridden ones)
- Replay correspondence (sidecar JSON envelope and on-disk frontmatter mirror each other)
- Future audit telemetry (NW-5 benchmark, drift detection)

Pass-2 (compile) does NOT read this section. It is filtered out before the compile LLM call.

### 2.1 Property definitions

**GraphDB-input section** (Pass-2 reads + uses for GraphDB construction):

| Field | Type | Required | GraphDB destination | Description |
|---|---|---|---|---|
| `kdb_signal` | enum: `signal \| noise` | yes | Routes upstream — gates whether Source enters compile via Component #3/#6 | Bias-to-inclusion per D-88-4: "uncertain" → `signal`. LLM emits content-only judgment; deterministic post-Pass-1 layer may override (§4). |
| `domain` | enum (23 NW-4 v0.4 ids) | yes | **`Source.domain`** (new schema column) | Substantive classification. LLM picks one. `undecided` is allowed; `science-technology` is gated by the catch-all self-check per NW-4 §4.4. |
| `source_type` | enum (NW-7 placeholder list) | yes | `Source.source_type` (existing column) | Source form. LLM picks one (e.g., `post`, `transcript-podcast`, `letter`). v0.2 placeholder list in §9; NW-7 ratifies. |
| `author` | string \| null | yes | **`Source.author`** (new schema column) | Source attribution. LLM extracts from content + filename if available; `null` if not attributable. |
| `summary` | string (1-3 sentences) | yes | **`Source.summary`** (new schema column) | Prose distillation. Compile LLM merges with `key_themes` when writing Source.summary (D-89-18). |
| `key_entities` | list[string] | yes | Seeds Entity nodes + SUPPORTS edges (existing graph structure) | Raw mentions — people, companies, places, concepts surfaced by the LLM. Compile's entity extractor uses these as seeds; verifies, dedupes against existing GraphDB, supplements with entities discovered in body. |
| `key_themes` | list[string] | yes | Merged into `Source.summary` by compile LLM (D-89-18); no own column | 2-5 themes finer-grain than `domain`. Free-form. Stays separate in frontmatter for Pass-1 transparency; compile LLM weaves into Source.summary prose. NW-8 may add a Theme node type in v0.3+ if telemetry justifies. |

**Audit section** (Pass-2 IGNORES per D-89-16):

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence` | float 0.0-1.0 | yes | LLM-emitted confidence in the `kdb_signal` call. Pass-1 audit; no GraphDB consumer (Pass-2 ignores). User-visible in Obsidian. |
| `uncertainty_reason` | string \| null | yes | Populated when `confidence < 0.6` OR when `kdb_signal = signal` but the LLM had doubts. Preserves "uncertain → pass" audit trail. |
| `reject_reason` | string \| null | yes | Populated when `kdb_signal = noise`. The LLM's stated reason. Enables false-reject audit per D-88-3. |
| `prompt_version` | semver string | yes | The prompt template version. Bumped on prompt change. |
| `model` | string | yes | Model id (e.g., `deepseek-v4-flash:direct`). |
| `schema_version` | int | yes | Schema version, starts at 1; bumped on additive or breaking schema change. |
| `override` | object (always emitted) | yes | Override audit block. `applied: null` when no override fired (Grok OQ-3 fix). See §4.3-§4.6. |

### 2.1.1 Why the audit section stays in frontmatter (D-89-16)

The audit fields describe **how this source was enriched** — confidence in the call, model used, prompt version, override rationale. These are properties of the Pass-1 enrichment instance, not of relationships to other sources. They are intrinsic to this enrichment, consistent with [[feedback_sources_stay_static_intrinsic_frontmatter_only]].

Consumers (in v1):
- **User in Obsidian** — sees confidence, reject_reason, override block in side-panel Properties. Spots low-confidence sources at a glance.
- **Replay archive correspondence** — sidecar JSON envelope mirrors frontmatter audit fields one-to-one. Either is reconstructable from the other.
- **Future NW-5 benchmark** — reads confidence + override patterns for evaluation.
- **Future drift detection** — aggregates prompt_version / model across re-enrichments.

NOT a consumer in v1:
- **Compile (Pass-2)** — does not read this section; strips it (along with the rest of the frontmatter) before its LLM call. Audit metadata has no GraphDB graph-construction role.

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

The sibling artifact (`docs/task89-additional-properties-survey-prompt.md`) fired the round-1 multi-model survey on what ADDITIONAL properties would justify being added. Round-1 returned 5/5 with substantive proposals; v0.2 explicitly defers folding them (own deliberation pass required, see OQ-89-14). v0.3 opens the property-additions deliberation.

---

## 3. Source modification mechanism (D-89-13 — structured response, deterministic embed)

Component #1 modifies the source file **in-place**: it prepends a YAML frontmatter block at the top of the markdown. The LLM **does not return the enriched source**. The LLM returns a **structured JSON envelope** of the 13 fields; a deterministic post-processor serializes the JSON as YAML frontmatter and writes the source.

### 3.1 The flow

```
1. LLM call:
   - Input: source content + prompt template + structured-output JSON schema
   - Output: JSON envelope { kdb_signal, domain, source_type, author, summary,
             key_entities, key_themes, confidence, uncertainty_reason,
             reject_reason, prompt_version, model, schema_version }
   - LLM never sees the source body in its output; never re-emits the body

2. Validate JSON envelope against schema
   - Required fields present, types correct, enums valid
   - On failure: emit enrich_failed; archive raw response; NO source write

3. Apply post-LLM override (§4) — modifies the envelope IN MEMORY
   - force_noise / force_signal precedence (§4.3)
   - reject_reason survival rule (§4.6)

4. Read source from disk; capture mtime + content-hash
   - Parse existing frontmatter if present (re-enrichment case)
   - Apply user-frontmatter collision rule (§3.3)

5. Serialize envelope → YAML; merge with preserved user-added keys
   - Write atomically: write to temp file, rename to source path
   - Body content NEVER passes through the LLM and NEVER gets modified by Pass-1

6. Write replay-archive sidecar (§5.3) — JSON envelope + raw response + request
7. Emit lifecycle event for Component #3
```

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
  key_themes: [...]
  confidence: 0.92
  uncertainty_reason: null
  reject_reason: null
  prompt_version: 1.0.0
  model: deepseek-v4-flash:direct
  schema_version: 1
  ---
  # Berkshire 2020 Letter
  Dear shareholders,
  ...
```

Note: the source body remains byte-identical to the pre-enrichment version. Only the frontmatter block is added.

### 3.2 Why structured response + deterministic embed (D-89-13)

| Aspect | Returning enriched source | Returning structured JSON (D-89-13) |
|---|---|---|
| Token cost | LLM re-emits entire source body | LLM emits ~13 small property fields only |
| Source-body risk | LLM might trim whitespace, rewrap, alter formatting, drop content | Body is never present in LLM output; never modified |
| Validation surface | Parse YAML block + diff body for unintended edits | Validate flat JSON against schema; body untouched |
| Replay archive | Mixed envelope (body + frontmatter together) | Clean JSON envelope; body archived once at source |
| Failure mode | Bad LLM output can corrupt source on write | Bad LLM output → reject before any source modification |

This extends [[feedback_post_llm_deterministic_override]]: LLM does **judgment**; deterministic code does **writes**. The override-application mechanism (§4) and the frontmatter-embedding mechanism (here) follow the same discipline.

### 3.3 Re-enrichment merge behavior + user-frontmatter collision rule

On a re-enrichment (e.g., source content changed → Component #3 fires Pass-1 again):

1. Parse existing frontmatter from disk (if any)
2. Classify each existing key into one of three buckets:
   - **Pass-1 schema key, never modified by user** (the value still equals the value from the previous replay archive): Pass-1's new value replaces it
   - **Pass-1 schema key, modified by user since last enrichment** (current value ≠ previous replay archive value): user wins; new value goes into an `override` annotation block (see below); user's value is preserved
   - **Non-schema key (user-added)**: preserved verbatim
3. Run Pass-1; obtain new envelope
4. Apply override layer (§4) to the new envelope
5. Merge per the bucket rules above
6. Atomic write back to disk

**Collision-detection mechanism:** compare current frontmatter values against the most-recent replay-archive `parsed_envelope` for the same source. If a value diverges, it's a user override. (Per Gemini F-1.)

**Annotation when a user override is detected:** under the merged frontmatter, add (e.g.):

```yaml
user_overrides:
  - field: domain
    user_value: value-investing
    pass1_proposed_value: macro-and-monetary-policy
    detected_at: 2026-06-05T14:30:00-04:00
```

This gives the user visibility (they can spot what Pass-1 wanted to change) without clobbering their manual correction. (Per Deepseek F-4.)

**Schema-evolution collision** (separate sub-case): if v0.2+ adds a new required field that a user had already created manually with the same name, the user value wins and is annotated as above. The schema migration writes this annotation on the first re-enrichment after the migration. Tracked as **OQ-89-9**.

### 3.4 Pristine-source recovery (not in v0.1; design hook)

A future utility (post-v0.1) could strip the YAML frontmatter from a source to recover the pre-enrichment state. Not in v0.1 scope. Filed as **OQ-89-2**.

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

### 4.2 Defaults for v0.2

```yaml
force_signal: []                              # empty; user-populated
force_noise:
  - Daily Notes/**                            # diary-style content; not KDB ontology material (D-89-14)
  - Projects/**                               # work-tracking; not KDB ontology material
```

User can override either list per their vault. Future v0.3+ may add domain-specific defaults; v0.2 ships only the path lists Joseph called out 2026-05-25.

### 4.3 Override application logic (pseudocode order matches §4.4 precedence — Codex F-2 fix)

After the Pass-1 LLM call returns (with the LLM's own `kdb_signal` emission), the deterministic post-Pass-1 layer runs. **Blacklist is evaluated first** so that overlapping matches correctly resolve to noise per §4.4 precedence:

```
def apply_overrides(source_path, llm_envelope):
    if matches_any(source_path, force_noise):
        llm_envelope.kdb_signal = "noise"
        llm_envelope.override = {
            applied: "noise",
            rule: "force_noise",
            match: <which glob fired>,
            llm_original: llm_envelope_pre_override.kdb_signal
        }
        # reject_reason survival rule (§4.6): override → noise
        # — if LLM had emitted signal, populate reject_reason from override metadata

    elif matches_any(source_path, force_signal):
        llm_envelope.kdb_signal = "signal"
        llm_envelope.override = {
            applied: "signal",
            rule: "force_signal",
            match: <which glob fired>,
            llm_original: llm_envelope_pre_override.kdb_signal
        }
        # reject_reason survival rule (§4.6): override → signal
        # — if LLM had emitted noise + reject_reason, clear reject_reason
        #   to null; preserve original in override.reject_reason_cleared

    else:
        llm_envelope.override = {
            applied: null,           # always emitted, never omitted (Grok OQ-3)
            rule: null,
            match: null,
            llm_original: llm_envelope.kdb_signal
        }

    return llm_envelope
```

### 4.4 Precedence

**Blacklist wins ties** (defensive default for v0.2). If a file matches both `force_signal` and `force_noise`, `force_noise` applies. The reasoning: explicit user intent to exclude (in `force_noise`) should not be silently overridden by an upstream-defined `force_signal` pattern.

**Specificity-tiebreaker variant** (Gemini F-4, Deepseek's `Projects/special/**` + `Projects/**` example): some panel input argues for "most-specific glob wins" before defaulting to blacklist-wins. This is plausible but adds complexity (defining "specificity" robustly across globs is non-trivial). v0.2 ships blacklist-wins; OQ-89-3 carries the variant forward for telemetry-driven revisit.

### 4.5 LLM does not see the path lists

Per [[feedback_post_llm_deterministic_override]]: the LLM is not informed of the override lists; it judges content substance only. This keeps the LLM's job pure and the rules version-controllable in code, not prompt.

### 4.6 Override-block always emitted + reject_reason survival rule

Two related corrections from the v0.1 panel:

**Override block always emitted (Grok OQ-3):** v0.1 said the `override` block is omitted when no override fires. v0.2 always emits the block — when no override fires, `applied: null`, `rule: null`, `match: null`, `llm_original: <whatever LLM emitted>`. Rationale: stable frontmatter shape simplifies downstream consumers (compile, NW-5 probes, human inspection); makes "no override fired" explicit rather than inferred-from-absence.

**reject_reason survival rule (Deepseek F-6):**

When `force_signal` overrides an LLM-emitted `kdb_signal: noise` to `signal`, the LLM had populated `reject_reason` (e.g., "diary-shaped meta-commentary"). Leaving that reject_reason field next to `kdb_signal: signal` is contradictory and confusing.

Rule: when override applies and the LLM's pre-override `kdb_signal` differs from the override `applied` value:

- If override → `signal` AND LLM had emitted `noise` with a `reject_reason`: clear `reject_reason` to `null`; preserve original in `override.reject_reason_cleared: <original-reject-reason>`
- If override → `noise` AND LLM had emitted `signal` (no `reject_reason`): populate `reject_reason` with a synthetic value, e.g., `"deterministic override via force_noise: <matched-glob>"`

This keeps the user-readable frontmatter internally consistent while preserving the full audit trail in the `override` block.

### 4.7 Pre-LLM short-circuit explicitly NOT adopted (D-89-15)

Qwen F-9 and Grok OQ-4 raised the question of skipping the LLM call entirely for files matching `force_noise` (saving ~30% of LLM cost on a daily-notes-heavy vault). v0.2 explicitly **keeps the LLM call** on every in-scope source. Rationale:

- Audit signal preserved: we can see whether the LLM agreed with the path override (informs whether `force_noise` defaults are well-calibrated)
- Aligns with "LLM judges content; deterministic handles location" purity
- Single-user, infrequent workload — cost is the lesser concern at this scale ([[feedback_no_imaginary_risk]])

If post-deployment telemetry shows the LLM never disagrees with the path override (say, 99%+ alignment), v1.1+ can add the short-circuit as a cost optimization. Filed as **OQ-89-10**.

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
~/Obsidian/KDB/state/ingest_runs/<run_id>/<encoded_source_id>.json
```

**Path encoding rule** (Codex F-4, Gemini F-3): source IDs are vault-relative paths and may contain `/` characters. To keep replay-archive lookup flat and avoid creating nested empty directories per run, encode `/` as `__` in the sidecar filename:

| Source ID (vault-relative path) | Sidecar filename |
|---|---|
| `Investing/Buffett-letter-2020.md` | `Investing__Buffett-letter-2020.md.json` |
| `Notes/Quick-thoughts.md` | `Notes__Quick-thoughts.md.json` |
| `top-level-note.md` | `top-level-note.md.json` |

The original `source_id` (un-encoded) is preserved inside the JSON envelope. Replay code decodes filename → source_id by reversing the substitution. The encoding rule is one-to-one (`__` is not a valid pattern in Obsidian path segments per typical user habits; if it appears, fall back to URL-encoding `/` as `%2F`).

Schema:

```json
{
  "source_id": "Investing/Buffett-letter-2020.md",
  "source_path": "~/Obsidian/Investing/Buffett-letter-2020.md",
  "source_content_hash": "<sha256>",
  "request": { "prompt": "<full prompt>", "model": "...", "schema": "<JSON schema>" },
  "raw_response": { "status": "...", "body": "...", "usage": "..." },
  "parsed_envelope": {
    "kdb_signal": "signal", "domain": "value-investing", "source_type": "letter",
    "author": "Warren Buffett", "summary": "...", "key_entities": [...],
    "key_themes": [...], "confidence": 0.92, "uncertainty_reason": null,
    "reject_reason": null, "prompt_version": "1.0.0",
    "model": "deepseek-v4-flash:direct", "schema_version": 1
  },
  "override": {
    "applied": null | "signal" | "noise",
    "rule": null | "force_signal" | "force_noise",
    "match": null | "<glob>",
    "llm_original": "signal" | "noise",
    "reject_reason_cleared": null | "<original-reject-reason if force_signal cleared it>"
  },
  "user_overrides_detected": [],
  "timestamp": "2026-05-26T20:30:00-04:00",
  "outcome": "enriched" | "enriched_force_overridden" | "enrich_failed" | "enrich_skipped"
}
```

Notes:
- The `override` block is always present (per §4.6); `applied: null` indicates no override fired.
- `user_overrides_detected` is a list of any user-modified frontmatter values detected during re-enrichment (per §3.3).
- There is **no `corpus_snapshot` field** in v0.2 — Option B (D-89-12) eliminates corpus_index entirely.

The replay-archive lets us:
- Re-derive the frontmatter deterministically without re-firing the LLM (cheap regeneration after a schema migration)
- Audit Pass-1 behavior over time (false-rejects, drift, prompt-version comparisons, force-override calibration)
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

## 6. Wikilinks: out of Pass-1 scope (D-89-12 — Option B locked)

Pass-1 emits `key_entities` (flat string list of entity mentions; already in §2 schema). It does NOT emit wikilink suggestions. It does NOT load a corpus_index. It does NOT modify the source body. **All wikilink / entity-to-entity / `LINKS_TO`-edge resolution is compile's responsibility**, against the live GraphDB.

### 6.1 Lineage

v0.1 left three options open (A: body wikilinks; B: no wikilinks from Pass-1; C: frontmatter wikilinks + corpus_index). The 5-CLI panel converged 4-of-5 on Option C; Deepseek dissented to Option B on concrete-first grounds. Joseph-led mid-deliberation surfaced two structural concerns the panel under-weighted:

1. Body wikilinks (A) demand denormalization refresh on every corpus change → file-change cascade → compile re-trigger. A is fatal.
2. Corpus_index (in both A and C) is a stripped-down GraphDB built at Pass-1 time. GraphDB is already the authoritative comprehensive corpus index, built dynamically by compile. Duplicating this at Pass-1 re-creates every problem GraphDB was designed to solve.

These collapse both A and C; B is what remains. See `docs/task89-deliberation-wikilinks-frontmatter.md` for the full lineage including the 5-CLI panel convergence, the mid-deliberation reframe, and the two new principle memories ratified by this deliberation:

- [[feedback_obsidian_wikilinks_are_vanity]] — Obsidian's wikilink/graph-view feature is display-only with no programmatic utility
- [[feedback_sources_stay_static_intrinsic_frontmatter_only]] — sources stay as static as possible; frontmatter is permissible iff every property is intrinsic to the source itself; relational/dynamic properties belong in GraphDB

### 6.2 What this means concretely for Pass-1

- Pass-1 emits `key_entities` as a flat string list (raw mentions, unresolved); compile is responsible for matching against the live GraphDB
- No `wikilink_suggestions`, `grounded_in_corpus`, `occurrences_in_corpus`, or any wikilink-shaped frontmatter field
- No corpus_index loader; no corpus_snapshot in replay sidecar
- Pass-1 LLM prompt does NOT include other sources' frontmatter; each call is single-source

### 6.3 v1.1+ enhancement hook (Deepseek B' hook)

`key_entities` is the future anchor for v1.1+ corpus-aware wikilink suggestions IF compile's mechanical entity matching shows measurable gaps (filed as OQ-89-11). The v1.1+ mechanism would be: read `key_entities` from other enriched sources' frontmatter (already there — no new IO path); match current source's `key_entities` against the corpus; emit `wikilink_suggestions` as a new optional frontmatter field. This is an additive schema change, no migration, no breaking change.

Crucially: that v1.1+ enhancement would ONLY happen if we have measured evidence that compile's mechanical matching is insufficient. Concrete-first per [[feedback_concrete_first_extract_later]].

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
- Meta-commentary about doing work on the KDB itself (session reflections, retrospectives) — note that file-location-based handling (`force_noise` for `Projects/**`, `Daily Notes/**`) covers diary-shaped material directly via path override (D-89-14); the LLM still applies the substance test for any vault-meta-commentary that appears outside those paths.

**Note on Daily Notes (D-89-14):** v0.1 had implied an LLM-detection criterion specifically for Daily Notes ("reject diary-shaped meta-commentary"). v0.2 withdraws that criterion — Daily Notes are handled by the path-based override (`force_noise: [Daily Notes/**]` default). The LLM is NOT instructed to detect diary shapes. The LLM judges every source's content substance the same way; if a Daily Note happens to contain genuinely substantive content, the LLM emits `signal` (audit-preserved in the override block), but the deterministic override routes the file to noise. Users who want LLM judgment to win on Daily Notes can remove `Daily Notes/**` from `force_noise`.

### 8.3 Prompt construction notes

- The prompt does NOT use the word "shape" (per [[feedback_drop_the_word_shape]]). It refers to **content substance**.
- The prompt does NOT pre-declare cross-cut entity hints, edge expectations, or "for example" connections (per [[feedback_no_edge_predeclaration_no_hints]]).
- The prompt does NOT tell the LLM about `force_signal` / `force_noise` lists. The LLM judges content; deterministic layer handles location overrides.
- The prompt instructs the LLM that "uncertain → signal" (bias to inclusion per D-88-4).

### 8.4 Implementation surface for v0.2

The prompt template is `kdb_compiler/ingestion/pass1_prompt.j2` (Jinja2 template by precedent), versioned via `prompt_version` semver. v0.2 design specifies a concrete first cut; iteration is expected post-implementation under NW-5 telemetry.

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

### 10.3 v1.1+ — Pass-1 as a second producer (still deferred)

Once enrichment proves out, v1.1+ MAY introduce Pass-1 as a SECOND GraphDB producer that writes additional ingestion-side state directly to GraphDB (orphan tracking, cleanup retraction, etc.):
- New producer contract document: `docs/graphdb-kdb-enrichment-producer-contract.md` (sibling to the v1.0 producer contract)
- Same journal + sidecar + retraction patterns (matches #67 / #68 cleanup-event precedent)

This is **explicitly deferred from v1.** Compile remains the single producer for v1; Pass-1's contribution to GraphDB flows through compile reading + using the frontmatter (§10.4).

### 10.4 Compile consumes the frontmatter in v1 (D-89-17 — promoted from "v1.x amendment")

**v0.2.1 reframe:** v0.2's §10.4 said "compile MAY use frontmatter as a follow-up in v1.x." During the 2026-05-26 evening "what is frontmatter FOR" deliberation, this was promoted to **v1-required behavior** (D-89-17). Rationale: Pass-1 exists specifically to offload Pass-2 LLM work; if compile ignores the frontmatter and re-derives everything via its own LLM, Pass-1 delivers no value. The integration intent is consumption, not coexistence.

Per [[feedback_integration_preconditions_are_architectural]] — the right minimum fix is whatever closes the integration loop the two components were designed for, not "make compile not break."

**Compile-side v1 changes — summary list:**

| Frontmatter field | Compile action |
|---|---|
| (entire frontmatter block) | Parse YAML at the top of the source; separate from body before any LLM call (§10.5) |
| `kdb_signal` | Read; honor as routing input (Component #3/#6 may have already filtered, but compile re-checks defensively) |
| `domain` | Read; write to `Source.domain` (new schema column); do NOT re-classify via LLM |
| `source_type` | Read; write to `Source.source_type` (existing column); do NOT re-classify |
| `author` | Read; write to `Source.author` (new schema column); do NOT re-extract |
| `summary` | Read; pass into the compile LLM call alongside `key_themes`; LLM produces merged `Source.summary` (D-89-18) |
| `key_themes` | Read; pass into the compile LLM call alongside `summary`; merged into `Source.summary` (D-89-18) |
| `key_entities` | Read; pass as **seed candidates** for the compile entity-extraction step; LLM verifies, dedupes against GraphDB, supplements with body-discovered entities |
| Audit section (entire) | Ignore (per D-89-16) — strip out before LLM call along with the rest of the frontmatter |

**Required GraphDB schema additions (D-89-17 implies):**

- `Source.summary STRING`
- `Source.author STRING`
- `Source.domain STRING` (or new Source→Domain edge — design call during writing-plans)

Existing `Source.source_type` column gets populated for the first time (was previously inferred or null).

**Compile prompt template changes (per Joseph 2026-05-26 [2]):** The compile LLM prompt must include explicit instructions on what each frontmatter field means and how to use it. Specifically:

- For trusted fields (`domain`, `source_type`, `author`): instruct the LLM to USE the value, NOT re-derive
- For `summary` + `key_themes`: instruct the LLM to MERGE both into a final Source.summary that weaves themes into prose (D-89-18 — force the LLM to engage with both, not pass-through)
- For `key_entities`: instruct the LLM to TREAT as seed candidates for entity extraction, supplementing with body-found entities

The new compile prompt explicitly excludes the audit section (which has already been stripped by the source-reading layer per §10.5).

### 10.5 Frontmatter-handling implementation responsibility (was: "compile must strip" — Deepseek F-3, now expanded)

The source-reading layer in compile (`source_text_for()` in `kdb_compiler/compiler.py:104-107`) is responsible for:

1. **Read** the raw file
2. **Parse** the YAML frontmatter block at the top (if present)
3. **Split** into `(frontmatter_dict, body_text)` and return both
4. The Source-node writer uses the frontmatter dict to populate Source columns
5. The compile LLM call receives only the body text (audit section + GraphDB-input section both stripped from LLM input; GraphDB-input section is delivered via prompt-builder as structured metadata per the compile prompt template)

This expands what was v0.2's "OQ-89-12 ship-blocker precondition" (strip-and-discard) into a full integration enhancement (parse + use + write). The work is absorbed into the Pass-1 implementation arc.

**Acceptance test:** run compile on an enriched source; verify:
- `Source.domain`, `Source.author`, `Source.summary`, `Source.source_type` are populated from frontmatter values
- `key_entities` from frontmatter appear as seeded Entity nodes + SUPPORTS edges (compile may add more from body discovery)
- Compile LLM does NOT emit entities for metadata values (frontmatter is not pollution-leaking into entity extraction)
- The audit section does not influence Source node properties
- `Source.summary` is a merged prose that integrates both the Pass-1 summary AND the key_themes (not a verbatim copy of Pass-1's summary)

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

### D-89-11 — Wikilinks + corpus_index — OPEN for v0.1 review (2026-05-25) [CLOSED by D-89-12]

**Decision:** Not closed at v0.1. Three candidate options in §6 (A: corpus_index + body wikilinks; B: no corpus_index + no body wikilinks; C: corpus_index + frontmatter wikilinks). Synthesis lean = C (narrowly). Reviewer panel explicitly asked to recommend.

**Rationale:** Joseph (2026-05-25): present multiple options to the panel; let new CLI reviewers (Qwen 3.7-max, Grok Build) demonstrate design judgment, not just review accuracy. v0.2 closes this decision.

**Closure:** Closed by D-89-12 (Option B locked) after Joseph-led mid-deliberation surfaced two structural concerns the 4-of-5 panel convergence on C had under-weighted. See `task89-deliberation-wikilinks-frontmatter.md`.

### D-89-12 — Option B locked: no wikilinks + no corpus_index from Pass-1 (2026-05-26)

**Decision:** Pass-1 emits `key_entities` (flat string list) only. No `wikilink_suggestions`, no corpus_index, no corpus_snapshot in replay sidecar. Compile owns wikilink / entity-to-entity / `LINKS_TO`-edge resolution against the live GraphDB. v1.1+ may layer LLM-grounded suggestions on top IF compile's mechanical matching shows measurable gaps (Deepseek B' hook).

**Rationale:** During the v0.1 → v0.2 fork-resolution conversation 2026-05-26, two structural concerns about Option C surfaced that the 4-of-5 panel convergence did not address:

1. Body wikilinks (A) demand denormalization refresh on every corpus change → file-change → compile re-trigger cascade. A is fatal.
2. Corpus_index (in both A and C) is a stripped-down GraphDB at the wrong place and time. GraphDB is already the authoritative comprehensive corpus index; duplicating this at Pass-1 re-creates every problem GraphDB was designed to solve (dynamicity, iterative build, snapshot semantics, cold-start cascade).

These collapse A and C. B is what remains. The Deepseek-dissent concrete-first reasoning becomes the right answer once the dynamicity argument lands.

Two new principle memories captured by this deliberation:
- [[feedback_obsidian_wikilinks_are_vanity]] — Obsidian's wikilink/graph-view is display-only with no programmatic utility
- [[feedback_sources_stay_static_intrinsic_frontmatter_only]] — frontmatter is permissible iff every property is intrinsic; relational/dynamic properties belong in GraphDB

Lineage: `docs/task89-deliberation-wikilinks-frontmatter.md`.

### D-89-13 — LLM returns structured JSON; deterministic post-processor embeds YAML frontmatter (2026-05-26)

**Decision:** The Pass-1 LLM call returns a structured JSON envelope of the 13 fields. The LLM does NOT return the enriched source. A deterministic post-processor validates the JSON, applies overrides (§4), serializes as YAML frontmatter, and atomically writes the source (body unchanged).

**Rationale:** Cleaner architectural separation — LLM does judgment (emit property values), deterministic code does writes (serialize JSON as YAML, merge with existing frontmatter per §3.3). Cheaper (no body re-emission in LLM output). Safer (body never present in LLM output → never modified by LLM). Aligns with [[feedback_post_llm_deterministic_override]] extended from override-application to frontmatter-embedding.

Implication: providers that lack reliable structured-output support cannot be used for Pass-1 (filed as OQ-89-13). Same posture as [[project_deepseek_v4_flash_dropped]].

### D-89-14 — D-88-11 amended: Daily Notes default to force_noise via path-based override (2026-05-26)

**Decision:** Daily Notes remain in scope (Config B reads them; LLM runs on them per D-89-15), but default to `kdb_signal: noise` via `force_noise: [Daily Notes/**]` in scope-config. The LLM is NOT instructed to detect diary shapes; it judges content substance only. Users who want LLM substance judgment to win on Daily Notes can remove `Daily Notes/**` from their `force_noise` config. Parent blueprint D-88-11 amended to reflect this (commit `092b44f`).

**Rationale:** v0.1 D-89-4 (default force_noise list) had already chosen the path-based override mechanism per Joseph's 2026-05-25 evening framing: "we should not add additional prompt to LLM to tag no-pass; what we should do is tag it as no-pass after LLM pass-1 if the configuration indicates." That mechanism is more disciplined than D-88-11's LLM-prompt detection: LLM judges content; deterministic code applies location policy. The panel's Codex F-1 and Gemini F-2 argued for rollback (remove Daily Notes/** from default) on grounds that Daily Notes can contain source-worthy observations. Joseph's evening decision answered that concern via configurability (users can opt-in by removing the pattern). Parent blueprint catches up; NW-1 "reject vault-meta-commentary" criterion withdrawn for Daily Notes.

### D-89-15 — LLM runs on every in-scope source; pre-LLM short-circuit not adopted (2026-05-26)

**Decision:** Files matching `force_noise` still receive a full Pass-1 LLM call; the override applies after. No pre-filter that skips the LLM call.

**Rationale:** Audit signal preserved — the override block records both the LLM's pre-override emission and the deterministic result, letting us spot whether the default `force_noise` patterns are correctly calibrated (e.g., do Daily Notes consistently get LLM-emitted `noise`, or does the LLM frequently disagree?). At single-user-scale with infrequent workload ([[feedback_no_imaginary_risk]]), cost is the lesser concern. If post-deployment telemetry shows the LLM-pre-override emission consistently agrees with the deterministic outcome (~99%+), v1.1+ can add the short-circuit then. Filed as OQ-89-10.

### D-89-16 — Frontmatter sectionalized: GraphDB-input + Audit (2026-05-26 evening)

**Decision:** Pass-1 frontmatter has two explicit sections in the YAML output:
- **GraphDB-input section** — fields Pass-2 (compile) reads + uses for GraphDB construction (`kdb_signal`, `domain`, `source_type`, `author`, `summary`, `key_entities`, `key_themes`)
- **Audit section** — Pass-1's own audit/replay metadata (`confidence`, `uncertainty_reason`, `reject_reason`, `prompt_version`, `model`, `schema_version`, `override` block); **Pass-2 IGNORES this section**

Both sections stay in the same on-disk YAML frontmatter block (single source of truth; user-visible; replay-corresponding).

**Rationale:** During 2026-05-26 evening "what is frontmatter FOR" deliberation, Joseph applied a singular criterion to the schema: *"every component in the frontmatter need to be meaningful and useful to the compiler pipeline and to the construction of GraphDB."* The audit fields don't pass that test for compile's GraphDB-construction job — but they ARE intrinsic to the Pass-1 enrichment instance and serve real Pass-1 purposes (user visibility, replay correspondence, drift detection). Sectionalization preserves both: GraphDB-input fields feed compile; audit fields stay visible to user/replay/telemetry without polluting compile's LLM.

The earlier proposal to move audit fields to sidecar-only was overcorrection. Audit fields LIVE in frontmatter; Pass-2 just filters them out before its LLM call.

### D-89-17 — Compile consumes the frontmatter in v1 (NOT v1.x deferral) (2026-05-26 evening)

**Decision:** Compile reads the GraphDB-input section of the frontmatter in v1 and uses it for Source-node population (without LLM re-derivation). Required GraphDB schema additions:
- `Source.summary STRING` (new)
- `Source.author STRING` (new)
- `Source.domain STRING` (new) — or new Source→Domain edge (design call at writing-plans)

Existing `Source.source_type` column gets populated for the first time.

The OQ-89-12 "strip-and-discard" framing (v0.2) is **withdrawn**; compile-side work expands from a single-function frontmatter-strip into a full integration enhancement (parse + use + write). Absorbed into the Pass-1 implementation arc.

**Rationale:** During the 2026-05-26 evening deliberation, Joseph called out the strip-and-discard proposal as "an outrage" — Pass-1 was created specifically to offload domain (and other) extraction from compile (Pass-2); if compile ignores Pass-1's frontmatter and re-derives everything via its own LLM, the entire integration's purpose is defeated. The right minimum-viable fix is the one that closes the integration loop, not the one that prevents breakage with minimum change. Memory: [[feedback_integration_preconditions_are_architectural]].

This corrects the v0.2 §10.4 deferral of "compile MAY use frontmatter as v1.x amendment" — promoted to v1-required.

### D-89-18 — Compile LLM merges summary + key_themes (NOT deterministic Python) (2026-05-26 evening) — **RETRACTED 2026-05-26 night**

**Status:** RETRACTED. Superseded by D-89-19 (mechanical append, persisted) + D-89-20 (entity_search_keys carries the structural-graph signal for themes upstream of Pass-2). Original text retained below for the audit record.

**Decision (historical, retracted):** When compile writes `Source.summary`, it does NOT do a verbatim copy of `frontmatter.summary`. Instead, compile's LLM prompt receives both `frontmatter.summary` AND `frontmatter.key_themes`, and the LLM produces a merged Source.summary that weaves themes into the summary prose.

`key_themes` stays as a separate field in the frontmatter (visible to user, replay-archive-corresponding). It does NOT get its own GraphDB column (no `Source.themes`); the LLM merge integrates them into `Source.summary`.

**Rationale (historical):** Joseph 2026-05-26: *"compile LLM merge is a better idea because it forces the LLM to process both sections instead of treating it as a pass through."* A deterministic Python concatenation would be cheaper but mechanical; the LLM merge ensures both fields are processed and integrated meaningfully into a coherent Source.summary. The cost — one extra LLM step — is justified by the engagement guarantee.

**Why retracted:** D-89-20 moved key_themes' load-bearing structural role to `entity_search_keys` → context_loader T2-rewrite (Task #90), upstream of Pass-2. With themes participating in the graph through that channel, their appearance in Source.summary becomes purely descriptive — the "forces engagement" rationale no longer holds because engagement happens elsewhere. Mechanical concat (D-89-19) is honest and sufficient for the descriptive role.

### D-89-19 — Source.summary: mechanical append of key_themes (replaces D-89-18) (2026-05-26 night)

**Decision:** When `kdb_compiler/compiler.py` builds `source_meta.summary` for Pass-2, it deterministically appends `key_themes` to the Pass-1 verbatim summary:

```
source_meta["summary"] = pass1.summary.rstrip(". ") + ". Themes: " + ", ".join(pass1.key_themes) + "."
```

The appended string is what Pass-2 sees in its prompt **AND** what gets persisted as `Source.summary` in the GraphDB (single source of truth — Pass-2 view matches the persisted value). No LLM-merge step.

`key_themes` remains a separate field in the frontmatter (visible to user, replay-archive-corresponding). It does NOT get its own GraphDB column.

**Rationale:** D-89-18's "force LLM engagement" rationale was load-bearing only when key_themes had no other structural channel into the graph. D-89-20 moved that role to `entity_search_keys` → context_loader T2-rewrite (Task #90). With themes participating structurally upstream of Pass-2, Source.summary becomes a descriptive surface where mechanical concat is honest and sufficient.

Source.summary's contract becomes: *"a brief summary of the source followed by its key themes."* Persisting the appended version means a single source of truth (no Pass-2-view-vs-persisted desync), richer cross-source semantic linking material for future context-loading, and more searchable Source.summary content.

Per [[feedback_no_parallel_storage_to_authority]]: frontmatter remains the authority for `key_themes`; Source.summary's appended form is a derived view, regeneratable from frontmatter — not a parallel store.

**Cost saving:** removes the LLM merge step and dissolves Bug #2 from the 2026-05-26 implementation checkpoint (no field-landing-place needed for "merged summary"; there is no merged summary). Bug #1 (Source.source_type hardcoded at `graphdb_kdb/ingestor.py:144`) remains and is independent.

### D-89-20 — Drop `key_entities`; add `entity_search_keys` (2026-05-26 night)

**Decision:**

1. **Drop `key_entities` from the Pass-1 output schema entirely.**
2. **Add `entity_search_keys: list[string]`** (up to 10 kebab-case slugs) as a new Pass-1 field in the GraphDB-input section (per D-89-16).
3. Pass-1 generates `entity_search_keys` via prompt instruction with broad scope: include each item in `key_themes`, slug variants of themes, slugs for entity names mentioned in the source (people, organizations, named frameworks), and closely-related concepts that frequently co-occur with the source's themes. Cap at 10; lowercase kebab-case; prefer specificity ("value-investing" beats "investing").
4. `entity_search_keys` is **NOT** seen by Pass-2 (compile LLM). Its sole consumer is the context_loader's T2-rewrite (Task #90 input contract — `entity_search_keys` is the load-bearing structured signal that replaces the current whole-word regex in `graph_context_loader._t2_slug_in_text`).
5. **D-89-17 partial retract:** the "TREAT `key_entities` as seed candidates" clause of D-89-17 is RETRACTED. The rest of D-89-17 (USE `domain` / `source_type` / `author` directly; Source schema additions) remains in force.
6. **Pass-2 source_meta_dict shrinks to:** `{domain, source_type, author, summary (with themes appended per D-89-19)}`. `key_entities` and `key_themes` are no longer threaded into Pass-2's PASS-1 META block.

**Rationale:** `key_entities` was an unconscientious attempt to create `entity_search_keys` — a flat-list descriptive field without a clear consumer-purpose. Applying the consumer-purpose test:
- Pass-2 has the full body → can extract entities directly from primary source
- Pass-2's EXISTING CONTEXT snapshot strictly dominates a flat-string seed list (carries `{slug, title, page_type, outgoing_links}` per row — graph-structural detail, not just names)
- `key_entities`' "fresh-eyes pre-pick" value is marginal at best; Pass-2 won't miss what's literally in the body in front of it

`entity_search_keys` has a single sharp purpose: produce slug candidates designed to maximize hit rate against `Entity.slug` PK lookups at context_loader's T2 stage. Pass-1 does one well-defined job for this signal; the named consumer (T2-rewrite per Task #90) has a clean input contract.

The earlier sequencing-guardrail caution ("keep `key_entities` until #90 lands") was imaginary-risk hedging — `[[feedback_no_imaginary_risk]]`. Pass-2 loses nothing meaningful when `key_entities` goes away; it loses something meaningful when EXISTING CONTEXT is poor, which is exactly what Task #90 will fix.

**Architectural alignment:** matches `[[feedback_integration_preconditions_are_architectural]]` (each Pass-1 field has a named downstream consumer whose purpose shapes the field's content) and the consumer-purpose discipline that emerged from tonight's deliberation arc.

**Implementation footprint (pure deletions + additive; no schema migration):**

| File | Change |
|---|---|
| `kdb_compiler/ingestion/pass1_schema.py` | Remove `key_entities` from `Pass1Envelope` + JSON schema; add `entity_search_keys: list[str]` (max 10, kebab-case-string pattern) |
| `kdb_compiler/ingestion/pass1_prompt.j2` | Remove `key_entities` bullet (line ~60); add `entity_search_keys` section per the prompt draft in the session checkpoint |
| `kdb_compiler/ingestion/frontmatter_embedder.py` | Field list: drop `key_entities`, add `entity_search_keys` |
| `kdb_compiler/ingestion/enrich.py` | Default-empty dict: drop `key_entities`, add `entity_search_keys` |
| `kdb_compiler/compiler.py` (lines 115, 130, 299, 456) | Remove `key_entities` references; replace `summary` in source_meta_dict with `fm.summary.rstrip(". ") + ". Themes: " + ", ".join(fm.key_themes) + "."` per D-89-19 |
| `kdb_compiler/prompt_builder.py` (lines 130-145, 154-170, 186-191) | Remove `key_entities` from `_PASS1_META_BLOCK_TEMPLATE` + rendering helper; remove the "MERGE" + "TREAT key_entities as seed candidates" instructions; replace with simplified "USE three fields + summary is authoritative" guidance |
| `graphdb_kdb/ingestor.py:144` (Bug #1) | Independent fix — set `Source.source_type` from `source_meta.source_type` when present (small edit) |

Net code-line delta: roughly net-zero. Architecturally simpler, not larger.

---

## 13. Open questions

### Closed by v0.2

- **OQ-89-1 — corpus_index cold-start strategy.** Closed by D-89-12 — no corpus_index in v0.2.
- **OQ-89-6 — multi-source re-enrichment batching.** Closed by D-89-12 — no corpus_index → no batch-vs-sequential question.

### Carried forward (still open)

### OQ-89-2 — Pristine-source recovery utility (post-v0.1)

A future utility could strip Pass-1 frontmatter to recover the pre-Pass-1 source. Not in v0.2 scope; filed as a v1.1+ candidate.

### OQ-89-3 — Override precedence: specificity-tiebreaker variant (Gemini F-4)

v0.2 keeps blacklist-wins-ties as the default precedence. Gemini F-4 and Deepseek argued for a specificity-tiebreaker rule (most-specific glob wins before defaulting to blacklist) — useful for the `Projects/special/**` (whitelist) + `Projects/**` (blacklist) pattern. Tracked for telemetry-driven revisit. If user-edited scope-config telemetry shows specificity collisions are common, promote to D-89-x in v0.3+.

### OQ-89-4 — `key_themes` vs `property_tags` separation (carried from §2.3)

v0.1 merged `property_tags` (★ tier from brainstorm) into `key_themes` (★★ tier). v0.3 property-additions deliberation may revisit. Tie-break in v0.3.

### OQ-89-5 — Re-enrichment trigger surface vs Component #3

Component #1 exposes: `enrich(source_path, last_state) → enriched_source + new_state + lifecycle_event`. Component #3 owns when to call. Surface only is in v0.2; full Component #3 deep-design is its own arc.

### OQ-89-7 — Schema version vs prompt version bumping rules

§2.2 distinguishes additive schema change (no bump), required-field add/remove (schema bump), prompt-only change (prompt version bump). Reviewers may push for more nuanced rules during implementation.

### OQ-89-8 — `confidence` semantics + threshold for `uncertainty_reason` population

§2.1 says `uncertainty_reason` is populated when `confidence < 0.6` OR when LLM had doubts despite signal. The 0.6 threshold is arbitrary; could be empirically tuned via NW-5.

### New in v0.2

### OQ-89-9 — Schema-evolution + user-key collision resolution

When v0.2+ adds a new required field that a user has already created manually with the same name (e.g., user added `difficulty: hard` to their frontmatter; v0.3 adds `difficulty` as a Pass-1 schema field), what's the migration rule? Current §3.3 says user value wins + annotated in `user_overrides`. Edge case: if the user's value violates the schema enum (e.g., user wrote `difficulty: easyish` but schema requires `easy | medium | hard`), should the user value still win (with a `schema_invalid: true` flag) or should Pass-1 force-replace? v0.3 ratifies.

### OQ-89-10 — Pre-LLM short-circuit telemetry watch (post-deployment)

D-89-15 explicitly keeps the LLM call on force_noise matches for audit signal. Post-deployment: if telemetry shows the LLM-pre-override emission agrees with the deterministic outcome 99%+ of the time, v1.1+ may add a pre-LLM short-circuit as a cost optimization. Watch metric: `force_noise_llm_disagreement_rate` per run journal aggregation.

### OQ-89-11 — v1.1+ corpus-aware wikilink suggestion enhancement (telemetry-gated)

D-89-12 / Deepseek B' hook. Pass-1 emits `key_entities`; compile owns wikilink resolution. v1.1+ may layer LLM-grounded suggestions on top IF compile's mechanical entity matching shows measurable gaps. Watch metric: human-spot-check disagreement rate on compile's `LINKS_TO` edges; or a NW-5 wikilink-relevance probe (if NW-5 includes one). If compile's matching is sufficient, this OQ never activates.

### OQ-89-12 — Compile-side frontmatter integration (CLOSED + RESCOPED by D-89-17)

**Status:** v0.2 framed this as a "strip-and-discard ship-blocker." 2026-05-26 evening deliberation rescoped it: compile must not just strip — it must **consume** the GraphDB-input section of the frontmatter (use values to populate Source.domain/author/summary/source_type without LLM re-derivation; seed entity extraction with key_entities; merge summary+key_themes via LLM into Source.summary). Schema additions required (§10.4). Absorbed into the Pass-1 implementation arc rather than tracked as a separate "blocking precondition." See D-89-17 and §10.4/§10.5 for the rescoped work.

### OQ-89-15 — NW-8 Theme node design (new, deferred to v0.3+)

Should GraphDB have a first-class Theme node type (parallel to Domain), so themes can be queried via graph traversal (e.g., "all sources discussing intrinsic value", "themes co-occurring with entity X")? v1 covers themes via the merge-into-Source.summary mechanism (D-89-18); a Theme node type adds traversal power but requires its own NW-class deliberation (vocab, curation, aliases, canonicalization — analogous to NW-4 for Domain). File as separate sub-task if telemetry shows string-matching themes in Source.summary is insufficient for the queries Joseph cares about.

### OQ-89-13 — Provider parity on structured-output support

D-89-13 — Pass-1 LLM call uses structured-output mode (JSON envelope). The current panel reviewers (Qwen 3.7-max, Claude, Grok Build, Codex GPT-5, Deepseek) all advertise structured output, but parity isn't verified for the specific 13-field schema. Pre-implementation: test each candidate Pass-1 model against the schema. Drop any provider that lacks reliable structured-output support (same posture as [[project_deepseek_v4_flash_dropped]]).

### OQ-89-14 — Round-1 property-additions deliberation (deferred to v0.3)

The round-1 property-additions survey returned 5/5 with substantive proposals — e.g., `knowledge_intent`, `evidence_basis`, `temporal_frame`, `abstraction_level` (Codex); analogous candidates from Qwen, Grok, Deepseek, Gemini. v0.2 explicitly DOES NOT fold these into the schema. v0.3 opens a separate deliberation on which (if any) additions to ratify, with the same convergence + Joseph-led ratification flow used for D-89-12/13/14/15. v0.2 ships with the original 13-field schema unchanged.

---

## 14. Decision summary (v0.1 + v0.2 + v0.2.1)

| ID | Source | Status | Where in this doc |
|---|---|---|---|
| D-89-1 | Brainstorm 2026-05-25 | Locked (audit/schema split refined by D-89-16) | §2 + §12 |
| D-89-2 | Brainstorm 2026-05-25 (rename verdict→KDB-Signal) | Locked + propagated to parent blueprint | §2 + §12 |
| D-89-3 | Brainstorm 2026-05-25 (path-expression overrides) | Locked | §4 + §12 |
| D-89-4 | Brainstorm 2026-05-25 (Daily Notes/Projects defaults) | Locked (mechanism clarified by D-89-14) | §4.2 + §12 |
| D-89-5 | Brainstorm 2026-05-25 (in-place frontmatter) | Locked (mechanism refined by D-89-13) | §3 + §12 |
| D-89-6 | Brainstorm 2026-05-25 (no GraphDB writes from Pass-1 v1) | Locked | §10 + §12 |
| D-89-7 | Brainstorm 2026-05-25 (drop "shape" word) | Locked | §8 + §12 |
| D-89-8 | Brainstorm 2026-05-25 (build mode) | Locked | §0 header + §12 |
| D-89-9 | Brainstorm 2026-05-25 (NW-7 deferred) | Locked | §9 + §12 |
| D-89-10 | Carried from D-88-4 | Locked | §2.1 + §12 |
| D-89-11 | v0.1 (wikilinks + corpus_index OPEN) | **CLOSED by D-89-12** | §6.1 + §12 |
| D-89-12 | v0.2 deliberation 2026-05-26 (Option B locked) | Locked | §6 + §12 |
| D-89-13 | v0.2 deliberation 2026-05-26 (structured JSON + deterministic embed) | Locked | §3 + §12 |
| D-89-14 | v0.2 deliberation 2026-05-26 (D-88-11 amended; path-override mechanism) | Locked + propagated to parent blueprint commit `092b44f` | §8.2 + §12 |
| D-89-15 | v0.2 deliberation 2026-05-26 (no pre-LLM short-circuit) | Locked | §4.7 + §12 |
| D-89-16 | v0.2.1 deliberation 2026-05-26 evening (frontmatter sectionalized: GraphDB-input + Audit) | Locked | §2 + §12 |
| D-89-17 | v0.2.1 deliberation 2026-05-26 evening (compile consumes frontmatter in v1; schema additions; OQ-89-12 rescoped) | **Partial retract 2026-05-26 night** — "TREAT key_entities as seed candidates" clause retracted by D-89-20; rest stays in force | §10.4 + §12 |
| D-89-18 | v0.2.1 deliberation 2026-05-26 evening (compile LLM merges summary + key_themes) | **RETRACTED 2026-05-26 night** — superseded by D-89-19 + D-89-20 | §12 (historical record) |
| D-89-19 | v0.2.2 deliberation 2026-05-26 night (Source.summary: mechanical append of key_themes; persisted; replaces D-89-18) | Locked | §12 |
| D-89-20 | v0.2.2 deliberation 2026-05-26 night (drop `key_entities`; add `entity_search_keys` as T2-rewrite input contract; D-89-17 partial retract) | Locked | §12 |

### Round-2 panel non-controversial fixes folded into v0.2

| Source | Fix | Where in v0.2 |
|---|---|---|
| Codex F-2, Deepseek, Gemini, Grok (4/5 catch) | §4.3 pseudocode order swapped — force_noise checked before force_signal to match §4.4 precedence | §4.3 |
| Codex F-4, Gemini F-3 (3/5) | Sidecar path encoding rule — `/` → `__` for flat lookup; no nested empty directories | §5.3 |
| Deepseek F-4, Gemini F-1, Codex OQ-4 (3/5) | User-frontmatter collision rule — user values win + annotated in `user_overrides` block | §3.3 |
| Deepseek F-6 (1/5) | reject_reason survival rule — clear when force_signal flips noise→signal; populate when force_noise flips signal→noise | §4.6 |
| Grok OQ-3 (1/5) | Override block always emitted with `applied: null` when no override fired | §4.3, §4.6, §5.3 |
| Deepseek F-3 (1/5 — critical) | Compile must strip YAML frontmatter before its LLM call — ship-blocking integration precondition | §10.5, OQ-89-12 |
| Gemini F-4, Deepseek `Projects/special/**` example | Specificity-tiebreaker variant of override precedence carried forward as OQ for telemetry-driven revisit | §4.4, OQ-89-3 |

### Round-1 panel: deferred

Round-1 property-additions survey returned 5/5 with substantive proposals. v0.2 explicitly does NOT fold these — they require their own deliberation pass with the same convergence + Joseph-led ratification flow used for D-89-12/13/14/15. Tracked as OQ-89-14; v0.3 opens that deliberation.

### v0.2.1 amendments (2026-05-26 evening — Joseph-led "what is frontmatter FOR" deliberation)

| Decision / change | Origin | Where in v0.2.1 |
|---|---|---|
| D-89-16 — Frontmatter sectionalized: GraphDB-input + Audit | Joseph's [1] reframe: "every component in the frontmatter need to be meaningful and useful to the compiler pipeline and to the construction of GraphDB" | §2, §12 |
| D-89-17 — Compile consumes frontmatter in v1 (not v1.x); Source schema additions | Joseph's [2]: strip-and-discard called out as "outrage"; integration intent must close the loop | §10.4, §10.5, §12 |
| D-89-18 — Compile LLM merges summary + key_themes | Joseph's [3] (this conversation): force LLM to engage with both fields, not pass-through | §10.4, §12 |
| key_themes stays in frontmatter as separate field | Joseph's [3]: "keep summary and key_themes *separated* in the frontmatter in llm-pass-1" | §2.1 |
| Confidence stays in frontmatter audit section; compile ignores | Joseph's [3] / [6] correction: "confidence will stay with audit components in llm-pass-1" | §2.1.1 |
| Audit section stays in frontmatter (not sidecar-only) | Joseph's [1] reframe — earlier proposal to move audit to sidecar was overcorrection | §2, §2.1.1 |
| OQ-89-12 rescoped from "strip ship-blocker" → integration enhancement absorbed into Pass-1 implementation arc | D-89-17 | §10.5, §13 OQ-89-12 |
| OQ-89-15 — NW-8 Theme node design (new, deferred) | D-89-18 covers themes via summary-merge in v1; Theme node design is v0.3+ if telemetry justifies | §13 OQ-89-15 |
| Memory captures | New: [[feedback_integration_preconditions_are_architectural]]; [[feedback_prompt_template_definition_plus_examples]]. Sharpened: [[feedback_no_edge_predeclaration_no_hints]] (examples-for-shape OK; examples-for-edges NOT) | — |

### v0.2.2 amendments (2026-05-26 night — Joseph-led Pass-1↔Pass-2↔context-loader integration loop-close)

Discussion arc: Phase E checkpoint (Bug #1 + Bug #2 surfaced via E.1 static analysis) → forensic walk of how the existing context (graph snapshot) is built (`graph_context_loader` T1/T2/T3 algorithm) → recognition that T2's whole-word slug regex is a pre-Pass-1 heuristic that strictly dominates by Pass-1 structured signals → consumer-purpose test applied to `key_themes` (no Pass-2 use case after dominance shift) and then to `key_entities` (same conclusion) → ratification of `entity_search_keys` as the single purpose-built Pass-1 → context_loader signal channel.

| Decision / change | Origin | Where in v0.2.2 |
|---|---|---|
| D-89-19 — Source.summary: mechanical append of key_themes; persisted to GraphDB Source.summary | Joseph 2026-05-26 night: "key_themes is a form of summary" — concession on prompt-only-vs-persisted question; single source of truth | §12 |
| D-89-20 — Drop `key_entities`; add `entity_search_keys` (≤10 slugs); T2-rewrite input contract | Joseph 2026-05-26 night: "key_entities was an unconscientious attempt to create entity_search_keys" | §12 |
| D-89-18 retracted | D-89-19 replaces (mechanical append) + D-89-20 moves structural-graph signal upstream (entity_search_keys → context_loader) | §12 D-89-18 marker |
| D-89-17 partial retract | "TREAT key_entities as seed candidates" clause retracted; rest (USE domain/source_type/author + Source schema additions) stays | §14 table |
| Task #90 (Context-loader T2-rewrite) input contract locked | `entity_search_keys` is the sole structured input | `docs/TASKS.md` #90 |
| Bug #2 from 2026-05-26 implementation checkpoint dissolved | D-89-19 + D-89-20 eliminate the "where does merged_summary land" problem entirely | session-handoff doc |
| Memory captures | Sharpened: `[[feedback_no_imaginary_risk]]` (caught in transition-guardrail hedging during the discussion) | — |

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

## 16. Reviewer prompt header (used for v0.1 review — historical)

This was the prompt used to fire v0.1 at the reviewer panel. The repo-modification guardrail was **CRITICAL** — four of five reviewers were new to the panel, and `agy/gemini-3.5-flash-high` was on an explicit one-strike re-trial after previous overreach. **Panel outcome: 5/5 clean.** agy completed 2-for-2 on its one-strike trial (round-1 + round-2).

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

**END OF BLUEPRINT v0.2.1**
