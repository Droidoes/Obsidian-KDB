# Task #74 — GraphDB-KDB Canonicalization Stage (Blueprint)

**Status:** Design — awaiting explicit Proceed on implementation (see §16).
**Date:** 2026-05-20 (drafted).
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #74 (to-be-opened).
**Anchor:** Round 5 §8.2 (canonicalization-first mandate) and §8.4 (5-layer
selection structure) in [`docs/what-is-the-ontology-for.md`](what-is-the-ontology-for.md).
Continuation of the #63 family architecturally; opened as a new top-level
task because #63 is closed in the ledger.
**Companion docs:**
- [`docs/task-graphdb-kdb-blueprint.md`](task-graphdb-kdb-blueprint.md) — the original #63 design (locks D32–D40 + D-A1/A2/B1/S0–S6; Codex 3-round reviewed)
- [`docs/task73-manifest-ontology-removal-blueprint.md`](task73-manifest-ontology-removal-blueprint.md) — D50/D51 split: GraphDB is live ontology authority; `source_state.json` is source lifecycle only
- [`docs/what-is-the-ontology-for.md`](what-is-the-ontology-for.md) §8 — Round 5 closeout (path = B; canonicalization-first; 5-layer vocabulary adopted)
- [`docs/CODEBASE_OVERVIEW.md`](CODEBASE_OVERVIEW.md) §5 (pipeline), §8 (GraphDB-KDB)
- [`docs/task74-canonicalization-blueprint-gemini-draft.md`](task74-canonicalization-blueprint-gemini-draft.md) — Gemini's premature draft (preserved as scratch; selected diagrams + DDL salvaged into this doc)

**Memory:** `project_ontology_purpose_kernel_question`, `feedback_no_imaginary_risk`, `feedback_concrete_first_extract_later`, `feedback_measurability_over_defensive_complexity`.

---

## 1. Why this exists

Round 5 of the kernel deliberation (`docs/what-is-the-ontology-for.md` §8)
closed at **Path B** — broad ingestion with no value/curation gate at the
door, on the bet that LLM extraction + graph operations (GraphRAG community
detection, HippoRAG Personalized PageRank) turn heterogeneous raw text into
useful structure.

That bet has a load-bearing engineering dependency: **canonicalization**.
In a schemaless extraction world (C1: LLM-extracted, not human-defined),
the same real-world entity routinely surfaces under multiple names — `Apple
Inc.`, `Apple, Inc.`, `AAPL`, `Apple`. If those become distinct graph
nodes, PageRank/PPR can't activate them together; community detection
splits the entity across clusters; the "emergent order" B promises
degrades to word soup (Antigravity Q5).

Round 5 §8.2 elevated this from "missed hedge" to **blueprint mandate**:
canonicalization must be designed as a **first-class compile-stage
component from day one**, not a post-hoc cleanup script. Retroactive
canonicalization on a graph already polluted with duplicates is
expensive — edges to merge, provenance to reconcile, communities to
re-cluster. Pay it up front.

Round 5 §8.4 separately adopted the **5-layer selection vocabulary**
(Codex Q8) as the organizing structure for the compile pipeline:
ingestion / extraction / canonicalization / query-time / human-
interpretation. Layers 2 and 3 are named, contracted compile stages. This
blueprint specifies **Layer 3**.

This task ships in a single coherent v1 across schema, algorithm,
pipeline integration, and validation. Algorithm complexity is phased
(string norm + alias-ledger first; embedding-similarity + LLM-as-judge
gated for v2) but schema and pipeline integration are full from day one.

---

## 2. Locked decisions

| ID | Decision | Rationale |
|---|---|---|
| **D-R5-1** | The compile pipeline is structured as a 5-layer selection cascade (ingestion / extraction / canonicalization / query-time / human-interpretation). Layers 2 and 3 are named, contracted compile stages; layer 1 is the harvester/X6 boundary; layer 4 is the query architecture; layer 5 is out of compile scope. | `docs/what-is-the-ontology-for.md` §8.4. B does not abolish selection — it relocates selection from layer 1 to layers 2-4, where the LLM + graph operations carry the load. Naming the layers makes future deliberation precise ("at which layer?") and prevents ad-hoc "selection" arguments from re-litigating B. |
| **D-R5-2** | Canonicalization is a first-class compile-stage component owning: (a) string normalization, (b) deterministic alias ledger, (c) provenance, with extension points for (d) embedding-similarity dedup and (e) LLM-as-judge for ambiguous cases. v1 ships (a)+(b)+(c); (d) and (e) ship in v2 behind config gates. | §8.2 mandate. Phased v1 honors `feedback_no_imaginary_risk` + `feedback_concrete_first_extract_later`: at current corpus scale (~70 entities) embedding+judge ROI is low; baseline string norm + curated alias ledger handles ~80% of duplication. Full toolkit schema is provisioned from day one (so v2 enable is no-migration). |
| **D-R5-3** | Canonicalization is a **new top-level compile stage** inserted between current Stage [5] reconcile and current Stage [6] build_source_state. Both downstream consumers — `patch_applier` (writes wiki pages) and `graph_sync` (writes the live GraphDB ontology authority per D50/D51) — consume the **canonicalized** compile_result. | Wiki pages and graph entities must agree on names. If canonicalization runs only inside graph_sync, the vault shows `[[AAPL.md]]` while the graph stores `apple-inc` — a divergence the human sees in Obsidian and that breaks the wiki↔graph correspondence. Single source of canonical truth, consumed identically by both renderings. Requires journal schema bump (canonical_meta in compile_result, see D-R5-7). |
| **D-R5-4** | The canonicalization contract is **idempotent and pure**: output is a deterministic function of (extraction output, alias-ledger-snapshot). No hidden in-memory state; full canonicalization output is written into the compile_result payload archived per-run at `state/runs/<run_id>/compile_result.json`. | Preserves #63 D34 independence-by-shared-upstream and D39 replay semantics. `graphdb-kdb rebuild` reconstructs the graph including all aliases by replaying the canonicalized compile_results from sidecar archives — no separate alias state needs to survive. |
| **D-R5-5** | Entity identity model: keep `Entity.slug` as the Kuzu **primary key** (no migration of existing #63 entities). Add a nullable `canonical_id` property on `Entity`. Aliases are themselves `Entity` rows whose `canonical_id` points at the canonical entity's slug. Canonical entities have `canonical_id IS NULL` (or self-pointing — see §13 Open Questions OQ-A). | #63 D37 + D-A1 + D-S1 keep `Entity.slug` PK with `<source_type>:` namespacing rules; reusing that PK shape preserves all shipped #63 implementation (62+ live grandfathered entities) and avoids a destructive schema migration. Aliases as `Entity` rows (not a separate `Alias` node table) keeps Cypher patterns uniform: `MATCH (e:Entity)` returns both canonicals and aliases; `WHERE e.canonical_id IS NULL` filters to canonicals. |
| **D-R5-6** | Alias relationship: new directed Kuzu REL table `ALIAS_OF` (Entity→Entity) with `run_id`, `created_at`, and `algorithm` properties (algorithm ∈ `{string_norm, ledger, embedding, llm_judge}` to record which v1/v2 mechanism produced the alias). | "Explicit edges beat implicit similarity" (#63 D37 principle, applied to aliases). Provenance attaches to the relationship — we can ask "which sources mention which surface forms of canonical entity X?" naturally: `MATCH (s:Source)-[:SUPPORTS]->(a:Entity)-[:ALIAS_OF]->(c:Entity {slug:'apple-inc'})`. Future v2 algorithms (embedding/judge) record themselves via the `algorithm` property without schema changes. |
| **D-R5-7** | Two independent version bumps: (1) `compile_result.schema.json` gains `canonical_id` (page-level) and `canonical_meta` (top-level) as **optional** properties, both whitelisted under `additionalProperties: false`; no separate canonicalized schema. (2) Run-journal `schema_version` bumps `2.1` → `2.2`. Adapter `supported_journal_versions = ["2.0", "2.1", "2.2"]` — pre-#74 journals replay cleanly (canonical_meta absent → all entities treated as canonical). | Journal versioning is separate from source-state versioning (which is at `3.0` after #73 Phase F) — they bumps independently per #63 D-S3. Single-schema-with-optional-fields avoids double validation (Stage 4 raw vs Stage 6 canonicalized): the same schema is valid both before and after Stage 6, with Stage 6 just *filling in* optional fields. `additionalProperties: false` is preserved because the new fields are declared. |
| **D-R5-8** | The deterministic alias ledger lives at `KDB/state/canonicalization/aliases.json` (single hand-curated JSON file). Format: `{"aliases": [{"surface": STRING, "canonical": STRING, "note"?: STRING}]}`. The optional `note` field carries the human comment / rationale that comments would in YAML. v1 has no UI for ledger editing — user edits the file directly. **Missing file is non-fatal**: Stage 6 logs a warning ("no aliases file at <path>; running with empty ledger — string normalization only") and proceeds with an empty ledger. Malformed JSON or sha-mismatch-on-replay remain fatal (see D-R5-9). | JSON over YAML resolved per OQ-G — matches `KDB/state/` convention (last_scan.json, source_state.json, compile_result.json, run journals are all JSON); avoids a new `pyyaml` dependency; stdlib-only ledger loader; schema/validation tooling stays straightforward. Human-edit ergonomics adequate for a short hand-edited file with a `note` field. Missing-file-fatal would brick first run before any aliases exist; empty-ledger-fallback honors `feedback_no_imaginary_risk`. |
| **D-R5-9** | Stage failure semantics: canonicalization stage *algorithmic* failure (circular aliases, malformed ledger JSON, ambiguous v2 results, sha-mismatch on replay) is **fatal** — failure journal written, pipeline halts before Stage [7] patch_applier (matches D50 Phase B for graph_sync). Missing ledger file is **not** an algorithmic failure; see D-R5-8. | Wiki and graph must agree on names. Mid-pipeline canonicalization failure must leave both renderings on the previous state. Recovery: fix the ledger / input, re-run `kdb-compile`. |
| **D-R5-10** | Stage [6] **overwrites** `state/compile_result.json` with the canonicalized compile_result atomically before returning. All subsequent stages — Stage [7] build_source_state, Stage [8] patch_applier, Stage [10] graph_sync — read the canonicalized file. The sidecar archived under `state/runs/<run_id>/compile_result.json` (per #63.0 outcome) is therefore the canonical version, preserving `canonical_meta` for D39 replay. | Without this, Stage 6 produces canonicalized_cr in memory only, the on-disk `state/compile_result.json` retains the raw extraction, and the post-graph_sync archival writes the raw version into the sidecar — `canonical_meta` is silently lost from the journal, and `graphdb-kdb rebuild` cannot reconstruct alias state. Atomic write-back closes that gap. |
| **D-R5-11** | Stage [6] rewrites alias references in **three** places, not just one: (a) `compile_result.pages[i].outgoing_links` slugs (metadata); (b) `[[wikilink]]` tokens embedded in `compile_result.pages[i].body` markdown (rendered to vault); (c) `compile_result.canonical_meta.outgoing_link_remaps` provenance record. Body rewriting is a regex pass over the page body markdown, replacing each `[[alias-surface]]` with `[[canonical-slug]]` (preserving Obsidian display-text syntax `[[canonical|alias-surface]]` when configured). | `patch_applier.py:234` writes `intent["body"]` unchanged. Without body-token rewriting, the metadata `outgoing_links` would point at canonicals but the vault `.md` body would still render `[[AAPL]]` — Obsidian would create a separate orphan page for AAPL because the file `apple-inc.md` exists. Wiki ≡ graph requires rewriting BOTH metadata and body. |
| **D-R5-12** | Alias `Entity` rows exist **only in the graph**, never as wiki pages. Concretely: (a) `compile_result.pages[]` contains only **canonical** page intents — Stage 6's merge logic ensures aliases that arrived as page intents are folded into their canonical's body per the merging policy in OQ-F; (b) `patch_applier` is unchanged — it iterates `pages[]` and writes one `.md` file per entry, all canonical; (c) `graph_sync` reads `canonical_meta.aliases_emitted` and creates `Entity` rows for aliases plus `ALIAS_OF` edges, but no SUPPORTS/LINKS_TO writes from `pages[]` reach them as primary entities. | Aliases are graph-level provenance, not rendering artifacts. The vault stays clean (one file per canonical entity). `patch_applier` requires no canonicalization-awareness — Stage 6 has already filtered `pages[]` to canonicals-only. |
| **D-R5-13** | Stage [6] **flattens alias chains at compile time** so every `Entity.canonical_id` points directly at the ultimate root canonical (never at an intermediate alias). If the ledger contains `A→B` and `B→C`, Stage 6 emits canonical_id `C` for *both* `A` and `B`. Cycle detection (D-R5-9 fatal) covers chains that loop back. | At query time, a simple `MATCH (a:Entity {slug:'aapl'})` reading `a.canonical_id` returns the root canonical in O(1), without variable-length traversal `[:ALIAS_OF*]->`. PPR/community queries that assume "one canonical per concept" stay correct. |

---

## 3. Architecture at a glance

```
                        compile_result.json
                              (per run, schema v2.x with canonical_meta)
                                 │
                                 │  produced by Stage [3] compile (LLM)
                                 ▼
                       ┌──────────────────────┐
                       │ Stage [4] validate    │
                       │ Stage [5] reconcile   │
                       └──────────┬───────────┘
                                  │  validated + reconciled compile_result
                                  ▼
                       ┌──────────────────────────┐
                       │ Stage [6] canonicalize   │  ← NEW (this blueprint)
                       │  - string norm           │
                       │  - alias ledger lookup   │
                       │  - resolve outgoing      │
                       │  - emit canonical_meta   │
                       │  (v2: embed sim + judge) │
                       └──────────┬───────────────┘
                                  │ canonicalized compile_result
                                  │ (slugs resolved, canonical_meta filled)
                  ┌───────────────┴────────────────┐
                  │   (two downstream consumers,   │
                  │    both see canonical names)   │
                  ▼                                ▼
        Stage [7] patch_applier          Stage [10] graph_sync
        - writes wiki .md pages          - writes Entity nodes
        - frontmatter from cr            - writes LINKS_TO edges
        - canonical names ≡ graph        - writes SUPPORTS edges
                                         - writes ALIAS_OF edges (NEW)
                                         - sets canonical_id (NEW)
```

**Stage renumbering.** Current pipeline `[1]–[9]` becomes `[1]–[10]`:

| Before | After | Stage |
|---|---|---|
| [1] | [1] | scan |
| [2] | [2] | validate scan |
| [3] | [3] | compile |
| [4] | [4] | validate compile_result |
| [5] | [5] | reconcile compile_result |
| — | **[6]** | **canonicalize** (NEW) |
| [6] | [7] | build source_state update |
| [7] | [8] | apply pages (patch_applier) |
| [8] | [9] | persist state |
| [9] | [10] | graph_sync |

Run-journal `schema_version` bump `2.1` → `2.2` (D-R5-7). `compile_result.schema.json` gains `canonical_id` and `canonical_meta` as optional whitelisted properties (no schema-version field on compile_result currently — additionalProperties: false enforced at 5 levels, so this is a property-list extension, not a version bump).

---

## 4. The 5-layer compile pipeline (framing)

KDB compile is a sequence of selection stages with explicit contracts —
not a monolithic "compile" step. Each layer relocates selection one step
deeper from the ingestion door:

| # | Layer | Selects | Implementation in KDB |
|---|---|---|---|
| 1 | **Ingestion** | Which files enter the corpus | Harvester / X6 mechanical-role exclusion (`.venv`, `node_modules`, generated artifacts). Settled: B + X6, no value/taste curation. |
| 2 | **Extraction** | Which entities/relations the LLM emits per source | Stage [3] compile — LLM produces `compile_result`. Quality depends on prompt + model + extraction contract. |
| 3 | **Canonicalization** | Which surface forms unify into one canonical entity | **This blueprint** — Stage [6] canonicalize. |
| 4 | **Query-time** | Which subgraph activates for a given query | Runtime — PPR / community routing (HippoRAG / GraphRAG). Out of scope for this blueprint. |
| 5 | **Human interpretation** | Which surfaced output the human believes | Outside the compile boundary — Obsidian UI, downstream readers. |

The mental model: B doesn't abolish selection. It relocates selection
from layer 1 (the ingestion gate Philosophy A would impose) down to
layers 2–4, where the LLM and graph operations carry the load. Each
layer is engineered separately.

---

## 5. Schema delta (Kuzu DDL)

Lives in `graphdb_kdb/schema.py`. Applied at first connection in
`GraphDB._ensure_schema()`. **First-connection initialization on a fresh
DB**; existing #63 DB requires migration (see §8).

```cypher
-- 1. Entity gains canonical_id (nullable property)
CREATE NODE TABLE Entity (
    slug          STRING PRIMARY KEY,        -- unchanged from #63 D37/D-A1
    title         STRING,
    page_type     STRING,                    -- summary | concept | article
    status        STRING,                    -- active | stale | archived | orphan_candidate
    confidence    STRING,                    -- low | medium | high
    canonical_id  STRING,                    -- NEW: points to canonical Entity.slug; NULL if self is canonical
    created_at    STRING,
    updated_at    STRING,
    first_run_id  STRING,
    last_run_id   STRING
);

-- 2. New ALIAS_OF relationship (Entity → Entity)
CREATE REL TABLE ALIAS_OF (
    FROM Entity TO Entity,
    run_id      STRING,                      -- which run introduced this alias
    created_at  STRING,
    algorithm   STRING                       -- string_norm | ledger | embedding | llm_judge
);
```

**Invariants enforced by Stage [6]:**

1. If `Entity.canonical_id IS NOT NULL`, there must exist an `ALIAS_OF`
   edge from this entity to the entity at `canonical_id`. (Co-write.)
2. `ALIAS_OF` edges are acyclic AND **flat** (D-R5-13): `Entity.canonical_id`
   always points at the *root* canonical (the entity with `canonical_id IS
   NULL`), not at an intermediate alias. Chain detection during Stage 6
   resolves multi-hop ledger entries; cycle detection raises
   `CircularAliasError` (D-R5-9 fatal).
3. The `canonical_id` of a canonical entity is NULL (not self-pointing —
   see §13 OQ-A). The "canonical" predicate is `canonical_id IS NULL`.
4. `compile_result.pages[]` contains **only canonical** page intents
   (D-R5-12). Alias surface forms that arrived as page intents are folded
   into the canonical per OQ-F merging policy; alias entities reach the
   graph only via `canonical_meta.aliases_emitted`.
5. Both `outgoing_links` metadata AND inline `[[wikilink]]` body tokens
   are remapped to canonical slugs **before** Stage [8] patch_applier
   sees them (D-R5-11), so wiki bodies and link metadata agree.
6. `LINKS_TO` edges in the live graph always target canonical entities
   (no `LINKS_TO` → alias). This is enforced by §9.1 verify C4.

---

## 6. Canonicalization stage contract

### 6.1 Inputs

```python
def canonicalize(
    cr: CompileResult,           # produced by Stage [3] compile, validated [4], reconciled [5]
    ledger: AliasLedger,         # loaded from KDB/state/canonicalization/aliases.json
    run_id: str,                 # current run identifier
) -> CanonicalizedCompileResult:
    ...
```

### 6.2 Outputs

The stage writes back to `state/compile_result.json` (D-R5-10) with the
in-memory `CanonicalizedCompileResult`. The on-disk artifact is a
`compile_result` matching `compile_result.schema.json` (with canonical
extensions added as optional whitelisted properties per D-R5-7) with:

- **`pages[]` containing only canonical page intents** (D-R5-12). Alias
  surface forms that arrived as separate page intents are folded into
  their canonical's body per OQ-F. Each page carries `canonical_id`
  (`NULL` if the page itself is canonical, which is the case for every
  page in `pages[]` post-Stage 6 — see OQ-A for why we keep the field
  on the page level anyway).
- **Both `outgoing_links` metadata AND inline `[[wikilink]]` body
  tokens** remapped to canonical slugs (D-R5-11). Body remapping uses
  regex over markdown — see §7 step (d).
- **A `canonical_meta` block** at the top level of compile_result:

```json
{
  "canonical_meta": {
    "algorithm_version": "1.0",
    "ledger_snapshot_sha256": "<sha256 of aliases.json at compile time>",
    "aliases_emitted": [
      {"alias_slug": "aapl", "canonical_slug": "apple-inc", "algorithm": "ledger"}
    ],
    "outgoing_link_remaps": [
      {"from": "aapl", "to": "apple-inc"}
    ],
    "merged_pages": [
      {"alias_page_slug": "aapl", "merged_into_canonical": "apple-inc", "merge_strategy": "<per OQ-F>"}
    ]
  }
}
```

`merged_pages` records each fold-in event for D39 replay and audit. If
no fold-in happened in a run, the array is empty.

### 6.3 Error semantics

Most failure modes are fatal per D-R5-9; missing ledger file is the one
exception (warning + empty ledger per D-R5-8).

| Error | Cause | Behavior |
|---|---|---|
| (none) | `aliases.json` does not exist | Log warning; run with empty ledger; emit `canonical_meta.ledger_snapshot_sha256 = "empty"`; **proceed** (D-R5-8). |
| `CircularAliasError` | Ledger or algorithm produces A→B and B→A (or longer cycle) | Fatal — write failure journal, halt pipeline. User edits ledger; re-runs. |
| `LedgerLoadError` | `aliases.json` present but malformed JSON, or schema-mismatch (e.g., entry missing `surface` or `canonical`) | Fatal — write failure journal, halt pipeline. |
| `LedgerShaMismatchError` | On `graphdb-kdb rebuild`: archived `canonical_meta.ledger_snapshot_sha256` does not match current `aliases.json` sha (replay would diverge from history) | Fatal — refuse rebuild; user reverts ledger to the archived version, or accepts loss-of-replay by force-rebuild flag (not in v1). |
| `AmbiguousAliasError` | (v2 only — same alias surface maps to multiple competing canonicals via embedding/judge) | Fatal — write failure journal showing competing candidates; user disambiguates via ledger entry. |

---

## 7. Algorithm pipeline (v1)

Stage 6 processes the full `compile_result` in five passes:

```
   ────────────────────────────────────────────────────────────────
   PASS 1 — Per-slug canonical resolution (chain-flattening)
   ────────────────────────────────────────────────────────────────

   For each entity slug appearing anywhere in cr (pages[] keys,
   outgoing_links targets, body wikilink tokens):

   [a] String normalization
      - lowercase, strip whitespace, collapse internal whitespace
      - normalize unicode (NFKC), strip diacritics if configured
      - remove punctuation except '-'
      → "AAPL" becomes "aapl"

   [b] Ledger lookup with chain-flattening (D-R5-13)
      - exact match on normalized surface form against aliases.json
      - if not found: this slug IS its own canonical (canonical_id = NULL)
      - if found: ledger gives "aapl" → "apple-inc"
        - recursively look up "apple-inc" in ledger
        - if "apple-inc" also has a canonical: continue traversal
        - cycle detection on visited set: raise CircularAliasError if seen
        - terminate when an entry has no further ledger mapping
        - that terminal entry is the ROOT canonical
        - all intermediate aliases also map to the root canonical
        → canonical_slug = "apple-inc" (root); algorithm = "ledger"

   Build the resolution map:
     resolve: dict[surface_slug, RootCanonical] = {
       "aapl":        "apple-inc",
       "apple-inc":   None,            # canonical itself
       "apple, inc.": "apple-inc",     # chain-flattened
     }

   ────────────────────────────────────────────────────────────────
   PASS 2 — Page intent canonicalization + merging (D-R5-12 + OQ-F)
   ────────────────────────────────────────────────────────────────

   Walk cr.pages[]:
   - For each page intent with slug S:
     - canonical_slug = resolve.get(S, S)
     - If canonical_slug == S: keep page as-is (and union into below if
       it gains contributors from aliases mapping to it)
     - If canonical_slug != S: this is an alias page intent
       - find/create the page intent for canonical_slug in pages[]
       - apply OQ-F merging policy:
         * BODY: canonical-slug page-intent body wins if present;
           otherwise longest body among the alias contenders wins.
         * outgoing_links: UNION of all contenders' outgoing_links,
           remapped through resolve, deduped (D-R5-13 root-only).
         * source_refs / provenance: UNION across contenders so the
           canonical page records every source that emitted any
           surface form mapped to it.
         * alias provenance: every alias-side contender slug is added
           to canonical_meta.aliases_emitted (algorithm = "ledger").
       - DROP the alias page intent from pages[]
       - record in canonical_meta.merged_pages with the chosen body
         strategy ("canonical-wins" or "longest-wins")

   Result: cr.pages[] contains only canonical page intents whose
   outgoing_links and source_refs are the UNION of contributions from
   every alias surface form folded into them.

   ────────────────────────────────────────────────────────────────
   PASS 3 — Outgoing-links remap (metadata)
   ────────────────────────────────────────────────────────────────

   Walk every page.outgoing_links[]:
   - For each link target T: T' = resolve.get(T, T)
   - Replace T with T' in outgoing_links
   - Record (T, T') in canonical_meta.outgoing_link_remaps (dedup)

   ────────────────────────────────────────────────────────────────
   PASS 4 — Body wikilink remap (markdown bodies) — D-R5-11
   ────────────────────────────────────────────────────────────────

   For each remaining (canonical) page.body:
   - Regex pass: find all [[wikilink]] tokens (incl. [[link|display]] form)
   - For each token's target slug T: T' = resolve.get(T, T)
   - Replace [[T]] with [[T']]
   - For [[T|display]] form: replace with [[T'|display]] (preserve display)
   - Re-record any new remaps in canonical_meta.outgoing_link_remaps

   ────────────────────────────────────────────────────────────────
   PASS 5 — Emit canonical_meta + write back
   ────────────────────────────────────────────────────────────────

   - Populate canonical_meta:
     - algorithm_version: "1.0"
     - ledger_snapshot_sha256: sha256(aliases.json content) or "empty"
     - aliases_emitted: list of {alias_slug, canonical_slug, algorithm}
     - outgoing_link_remaps: deduped (from, to) pairs
     - merged_pages: per Pass 2

   - Atomic write-back of cr to state/compile_result.json (D-R5-10)

   - Return canonicalized_cr for in-process passes (Stages [7], [8], [10])
```

**v2 extensions (gated behind config flag, schema designed in but algorithms off in v1):**

- `[b'] Embedding similarity` — inserted between (a) and (b). Compute
  embedding for normalized slug; query embedding store for near-matches
  above configurable threshold; if hit, treat the match as if it were
  in the ledger (subject to chain-flattening in (b)). Emit alias with
  `algorithm = "embedding"`.
- `[b''] LLM-as-judge` — for ambiguous embedding near-matches (cosine
  in a configurable mid-band), call an LLM with context "are these the
  same entity?" Emit alias with `algorithm = "llm_judge"`.

v2 work is out of scope for #74; tracked as L9 in §14.

---

## 8. Pipeline integration

### 8.1 New Stage [6] in `kdb_compile.py`

Insert after Stage [5] reconcile, before current Stage [6] build_source_state
(which becomes Stage [7]):

```python
# ----- [6] canonicalize -----
ledger_path = state_dir / "canonicalization" / "aliases.json"
try:
    ledger = AliasLedger.load_or_empty(ledger_path)   # D-R5-8: missing → empty + warning
    canonicalized_cr = canonicalize.run(
        cr=reconciled_cr,
        ledger=ledger,
        run_id=run_id,
    )
    # D-R5-10: atomic write-back so subsequent stages and archival see canonical
    atomic_io.write_json(state_dir / "compile_result.json", canonicalized_cr.to_dict())
except (CircularAliasError, LedgerLoadError, AmbiguousAliasError, LedgerShaMismatchError) as e:
    # D-R5-9: fatal; write failure journal and exit
    write_failure_journal(run_id, stage=6, error=e)
    return ApplyResult.failure(...)
# all subsequent stages read state/compile_result.json which is now canonical
```

### 8.2 Subsequent stage updates

- **Stage [7] build source_state** — reads `state/compile_result.json`
  (now canonicalized). No behavioral change; source_state is
  source-meta only per D50, doesn't deal with entity names beyond
  per-source ingest_count tracking.
- **Stage [8] patch_applier** — reads canonicalized `state/compile_result.json`.
  **No canonicalization-awareness required** (D-R5-12): `pages[]` already
  contains only canonical page intents; `body` already has `[[wikilinks]]`
  remapped to canonical (D-R5-11); the existing `intent["body"]` write
  path at `patch_applier.py:234` works unchanged. One file per canonical
  entity; aliases never get rendered.
- **Stage [10] graph_sync** (was [9]) — reads canonicalized
  `state/compile_result.json`. New responsibilities:
  - **For pages (canonical entities):** unchanged from #63 behavior —
    upsert `Entity` row with `canonical_id = NULL`; write `SUPPORTS` and
    `LINKS_TO` edges as today.
  - **For aliases in `canonical_meta.aliases_emitted`:** upsert `Entity`
    row for the alias slug with `canonical_id = <root canonical>`; write
    `ALIAS_OF` edge alias→canonical with `algorithm` from canonical_meta.
    SUPPORTS/LINKS_TO routing for aliases is governed by **OQ-E** —
    see §13.

### 8.3 Migration on existing #63 DB

The current GraphDB has 62+ Obsidian-grandfathered entities with no
`canonical_id` and no `ALIAS_OF` edges. Migration is **non-destructive**:

1. `ALTER NODE TABLE Entity ADD canonical_id STRING` (Kuzu DDL).
2. Existing entities default to `canonical_id IS NULL` — they are all
   already canonical by construction (no aliases existed yet).
3. `CREATE REL TABLE ALIAS_OF (...)` — empty at migration time.
4. First post-#74 compile populates aliases on entities the LLM emits
   under multiple surface forms thereafter.

No retroactive sweep of existing entities. Existing duplicates (if any)
are accepted as pre-canonicalization legacy; they can be resolved later
by editing the ledger and forcing recompile of affected sources. This is
the pragmatic posture — retroactive cleanup is exactly what Round 5 §8.2
warns against ("expensive after"), but the existing #63 corpus is small
(~70 entities) and was hand-curated, so duplication rate is low.

### 8.4 Rebuild path (D39 compatibility)

`graphdb-kdb rebuild` replays journals in chronological order. Each
post-#74 journal carries `canonical_meta` in its compile_result sidecar.
Rebuild reads `canonical_meta.aliases_emitted` and writes the exact
`Entity.canonical_id` + `ALIAS_OF` edges that the original compile
produced. No re-execution of the canonicalization algorithm during
rebuild — output is replayed from the journal, preserving D-R5-4 purity
under replay.

Pre-#74 journals (no `canonical_meta`): adapter treats as
`canonical_id IS NULL` for all entities (matches their original state).
Adapter declares `supported_journal_versions = ["2.0", "2.1", "2.2"]`
per #63 D-S3 — `"2.0"` covers compile run journals, `"2.1"` covers
`kdb-clean` cleanup journals, `"2.2"` is the new post-#74 run journal
version (D-R5-7).

---

## 9. Validation + rebuild paths

### 9.1 `graphdb-kdb verify` extension

`verify` adds canonicalization-aware checks on the **live graph** (no
sidecar reads required — all four invariants are observable from the
graph alone):

- **C1** — every `Entity` with `canonical_id IS NOT NULL` has a matching
  `ALIAS_OF` edge to that canonical_id.
- **C2** — every `ALIAS_OF` edge's source `Entity` has `canonical_id`
  equal to the edge's destination.
- **C3** — `ALIAS_OF` is acyclic AND flat: every `Entity.canonical_id`
  points at an `Entity` with `canonical_id IS NULL` (i.e., no chains,
  no cycles — D-R5-13 invariant).
- **C4** — every `LINKS_TO` edge's destination has `canonical_id IS NULL`
  (LINKS_TO targets are always canonical entities — D-R5-12 invariant).
  Phrased as a live graph property: no `LINKS_TO` ever points at an alias.

### 9.2 `graphdb-kdb rebuild` (no API change)

Existing `rebuild` semantics apply (#63 D39 + D-B1 + D-S0). New behavior
is internal to the adapter, which now writes `canonical_id` and
`ALIAS_OF` from `canonical_meta` during replay.

---

## 10. Test surface (target counts)

| Test | Count | Notes |
|---|---|---|
| String normalization unit tests | ~10 | unicode, punctuation, casing, whitespace edge cases |
| Ledger load — happy path + missing-file warning + malformed + sha snapshot | ~6 | including missing → empty-ledger warning behavior (D-R5-8) |
| Chain flattening (D-R5-13) | 4 | A→B→C resolves to C for both A and B; cycle A→B→A → fatal; mixed chain + leaf entries; ledger-only entry |
| Canonicalization stage integration | ~10 | end-to-end with mock compile_result; ledger hit/miss; metadata + body wikilink remap (D-R5-11); pages[] merging (OQ-F) |
| Body wikilink regex pass | 4 | `[[alias]]` → `[[canonical]]`; `[[alias\|display]]` → `[[canonical\|display]]`; mixed bodies; idempotent on already-canonical |
| Stage 6 write-back (D-R5-10) | 2 | state/compile_result.json contains canonical_meta after Stage 6; subsequent stages read canonicalized version |
| Page intent merging (OQ-F) | 3 | per the selected merging policy — see §13 |
| Circular alias detection | 3 | A→B→A; A→B→C→A; A→A (self) |
| Schema migration (existing DB) | 2 | ALTER TABLE adds canonical_id column; ALIAS_OF created; pre-existing entities default to canonical_id NULL |
| compile_result.schema.json validation | 3 | canonical_meta absent (pre-#74 cr); canonical_meta present (post-#74); additionalProperties: false still rejects unknown fields |
| Rebuild replay | 4 | post-#74 journal replays with same aliases (sha matches); pre-#74 journal replays as all-canonical; sha-mismatch on replay → fatal |
| `graphdb-kdb verify` C1–C4 | 4 | each invariant violation detected (LINKS_TO → alias rejected; chain detected; missing ALIAS_OF edge; mismatched canonical_id) |
| Stage [6] failure → fatal halt | 3 | CircularAliasError + LedgerLoadError + AmbiguousAliasError(v2) all prevent patch_applier from running; missing ledger does NOT fail |
| patch_applier integration | 2 | aliases never reach pages[]; all wiki files are canonical-named; body links resolve to canonical .md filenames |

**Target: 60 new tests minimum.**

---

## 11. Sequencing — sub-task breakdown

| Sub-task | Scope | Estimated complexity |
|---|---|---|
| **#74.1** | Schema delta — `Entity.canonical_id` + `ALIAS_OF` table in `graphdb_kdb/schema.py`; first-connection initialization + ALTER migration for existing DB | small |
| **#74.2** | `aliases.json` ledger format (stdlib `json` only, no new deps per OQ-G resolution) + `AliasLedger.load_or_empty()` loader (missing → empty + warning per D-R5-8) + sha256 snapshotter | small |
| **#74.3** | `canonicalize.run()` algorithm — Pass 1 string-norm + ledger lookup + chain flattening (D-R5-13); Pass 2 page-intent canonicalization + merging per OQ-F; Pass 3 outgoing-links remap; Pass 4 body `[[wikilink]]` regex remap (D-R5-11); Pass 5 canonical_meta emission + atomic write-back (D-R5-10); error classes | medium-large |
| **#74.4** | `kdb_compile.py` Stage [6] wiring + stage renumbering [6]→[7]/[7]→[8]/[8]→[9]/[9]→[10]; journal `schema_version` bump `2.1` → `2.2`; `compile_result.schema.json` update to whitelist `canonical_id` + `canonical_meta` as optional properties at the right levels | medium |
| **#74.5** | `graphdb_kdb/adapters/obsidian_runs.py` reads `canonical_meta`, writes alias `Entity` rows + `canonical_id` + `ALIAS_OF` (with `algorithm` property); SUPPORTS routing per OQ-E lean; `supported_journal_versions = ["2.0", "2.1", "2.2"]` | small-medium |
| **#74.6** | `graphdb-kdb verify` C1–C4 invariants on the live graph (no sidecar reads required) | small |
| **#74.7** | Test suite — full coverage per §10 (60+ tests) | medium |
| **#74.8** | Documentation — `CODEBASE_OVERVIEW.md` §5 (pipeline stage list) + §8 (GraphDB schema delta) updates; `graphdb-kdb verify` man text; D50/D51 references stay accurate | small |

Sequencing rule: ship #74.1 → #74.2 → #74.3 → #74.4 → #74.5 in dependency
order; #74.6, #74.7, #74.8 can be interleaved.

---

## 12. Dependencies + setup

- **Kuzu** ≥ 0.11.3 (unchanged; ALTER TABLE ADD supported)
- **No new Python dependencies.** OQ-G resolved JSON (D-R5-8), so the
  ledger is parsed with the stdlib `json` module. PyYAML was the only
  candidate new dep; not needed.
- **No new external services** for v1. Embedding model + LLM judge in v2
  will require config (embedding API + judge model selection) — out of
  scope for #74.

---

## 13. Open questions

All v1 OQs resolved as of 2026-05-20 after second consultation round
with Codex + Antigravity. OQ-A through OQ-D were "settled-but-flagged"
(my leans agreed with both reviewers); OQ-E, OQ-F, OQ-G were genuine
forks, all closed below. Section retained as the audit trail of how
each call was settled.

### 13.1 Settled v1 OQs

- **OQ-A — Self-pointing canonical_id vs NULL.** D-R5-5 picks NULL ("self
  is canonical means canonical_id is null"). Alternative: canonical
  entities point at themselves (`canonical_id = self.slug`). NULL is
  simpler for queries (`WHERE canonical_id IS NULL` ≡ canonical); self-
  pointing makes the alias-traversal pattern uniform at the cost of a
  redundant string on every canonical row. **Lean: NULL** (locked in
  D-R5-5; flagging in case of objection).

- **OQ-B — `ALIAS_OF` direction.** D-R5-6 picks alias → canonical.
  Alternative: canonical → alias. **Lean: alias → canonical** (locked in
  D-R5-6 — matches the convention "the child points at the parent" and
  enables `MATCH (a)-[:ALIAS_OF]->(c)` to read naturally as "give me the
  canonical of a").

- **OQ-C — JSON Schema update mechanics.** D-R5-7 specifies that
  `canonical_id` and `canonical_meta` become optional whitelisted
  properties in `compile_result.schema.json`. #74.4 includes the schema
  edit. Format-only; not a decision fork (the open question is just
  "remember to land the schema edit alongside the stage").

- **OQ-D — Schema validation strategy.** D-R5-7 picks single schema with
  optional fields (Stage 4 validates raw; Stage 6 fills in optional
  fields; same schema valid both pre- and post-Stage-6). Alternative is
  two distinct schemas validated at separate stages. **Lean: single
  schema** (locked in D-R5-7). Flagging because Codex called the
  contract underspecified.

- **OQ-E — SUPPORTS-edge routing when an alias is mentioned. RESOLVED:
  direct-to-canonical.** Source `-[:SUPPORTS]->` always lands on the
  *canonical* entity, never on an alias. Codex and Antigravity both
  picked (a) directly; rationale convergence: (1) `pages[]` already
  contains only canonical page intents per D-R5-12, so the existing
  SUPPORTS write path in `graph_sync` naturally produces canonical
  edges; (2) PPR / community detection / GraphRAG queries are exactly
  the operations §8 says justify the project — they need clean
  canonical activations, not alias noise that double-counts or
  re-routes activation energy; (3) surface-form provenance is preserved
  in `canonical_meta.aliases_emitted` archived per-run (D-R5-10) and is
  queryable by run_id from the sidecar — the right home for an audit
  question. Dual-write (c) was explicitly rejected because it distorts
  SUPPORTS counts and orphan-detection logic (Codex). Locked into D-R5-12
  and the §8.2 Stage [10] graph_sync responsibilities. Alternatives kept
  in `docs/task74-canonicalization-blueprint-gemini-draft.md` for
  reference.

- **OQ-F — Page-intent merging policy. RESOLVED: canonical-name-wins
  with longest-body fallback + UNION of outgoing_links and source_refs.**
  Body selection rule: if any colliding page intent was emitted under
  the canonical slug itself, that body wins; otherwise the longest body
  among the alias contenders wins. Both reviewers picked (a) with (b)
  as fallback. **Codex added an important refinement:** the merge is
  NOT just body selection — `outgoing_links` and `source_refs` (and any
  per-page provenance) must be **unioned/deduped** across ALL
  contenders (not just the body-winner), so the canonical page
  records every source that emitted any surface form mapped to it.
  Without the union, source-attribution silently drops contributors
  whose body didn't win. Locked into §7 Pass 2 algorithm.
  `canonical_meta.merged_pages` records which strategy fired
  (`canonical-wins` or `longest-wins`) per merge.

- **OQ-G — Ledger file format. RESOLVED: JSON.** Codex argued JSON,
  Antigravity argued YAML; tie broken by repo convention. The case for
  JSON: (1) `KDB/state/` is JSON-by-convention — `last_scan.json`,
  `source_state.json`, `compile_result.json`, run journals all JSON;
  making `aliases.json` the one YAML file in `state/` is an
  inconsistency; (2) no new dependency — `pyyaml` would have been the
  only new dep for #74, removable; (3) schema/validation tooling stays
  uniform with the existing JSON Schema patterns. Gemini's ergonomics
  concern is addressed by the optional `note` field in each ledger
  entry — the comments-equivalent for a hand-curated file. Locked into
  D-R5-8.

### 13.2 Deferred to v2 (tracked as L9 in §14)

- **Embedding model + threshold band.** Which embedding model
  (local vs API)? Where does the embedding store live (Kuzu vector
  index? sidecar)? What cosine threshold band triggers LLM-judge?
- **LLM-judge model selection.** Same model as compile, or a
  different one? Cost budget per ambiguous alias?
- **Editor UX for the alias ledger.** v1 is hand-edited file.
  v2 may want `graphdb-kdb canonicalize add-alias <surface> <canonical>`
  CLI helper. Out of #74.

---

## 14. Known limitations (v1)

| Tag | Limitation | Mitigation |
|---|---|---|
| **L9** | Embedding-similarity and LLM-as-judge gated off in v1. Aliases not present in the ledger remain duplicated until the user adds them. | Schema designed for v2 enablement (zero migration). Watch corpus growth for duplication patterns; promote to v2 when warranted. |
| **L10** | No retroactive sweep of pre-#74 entities. Existing duplicates (if any) persist until the user adds them to the ledger and forces recompile of affected sources. | Pragmatic posture — corpus is small (~70 entities); retroactive sweep risks the cost §8.2 warned against. |
| **L11** | Ledger is a single global file (no per-source or per-domain scoping). | Acceptable at current scale; revisit if corpus grows past O(10³) entities or if domain-specific aliases conflict. |

---

## 15. Verification criteria for closure

Task #74 ships when, on the canonical corpus:

1. `aliases.json` has at least one curated entry the user confirms is
   correct (e.g., a real `[[AAPL]]` ↔ `Apple Inc.` if such surfaces in
   the corpus; otherwise a synthetic test entry the user signs off on).
2. A `kdb-compile` run with that alias entry in scope produces:
   - Wiki: only the canonical page is written; `[[wikilinks]]` that
     referred to the alias surface form now render to the canonical page.
   - Graph: alias `Entity` row exists with `canonical_id` filled;
     `ALIAS_OF` edge exists; canonical `Entity` row has `canonical_id IS NULL`.
3. `graphdb-kdb verify` returns clean (no C1–C4 violations).
4. `graphdb-kdb rebuild` from journals reproduces the exact alias state
   (same nodes, edges, canonical_id values).
5. All 38+ tests green.
6. `CODEBASE_OVERVIEW.md` updated to reflect the 10-stage pipeline and
   GraphDB schema additions.

---

## 16. What "Proceed" looks like

User says **"Proceed with #74"** → I:

1. Add Task #74 to `docs/TASKS.md` open section with the sub-task list.
2. Start #74.1 (schema delta) and walk through implementation per
   Phase 4 of the standard workflow.
3. Each sub-task gets explicit Proceed gate before commit per CLAUDE.md.

User says **"Refine X"** → we re-open the relevant Locked Decision or
Open Question in this doc and iterate.
