# `manifest.json` — Role, Structure, and Semantics

**Companion to**: `docs/manifest.schema.md` (field-level reference) · `compile_result.md` · `last_scan.md` · `CODEBASE_OVERVIEW.md` §5

Consolidates the Q&A walkthrough from 2026-04-20: what `manifest.json` *is* (not just what's in it), why it's the most load-bearing file in `state/`, and how to read its four top-level blocks.

> **Field-level reference**: see `docs/manifest.schema.md`. This doc covers the role, mental model, and why the structure is what it is. For "what does field X hold," go to the schema doc.

---

## Mental Models at a Glance

Three framings carry most of the intuition. Read these first.

**📒 Ledger, not inventory (what `manifest.json` *is*):**

> `manifest.json` is the KDB system's **ledger of record** — the durable, authoritative state that persists across runs. An inventory is a *report* you generate and discard. A ledger is *authoritative* — the system's decisions depend on it, and it carries state forward. Delete it and the system is amnesiac: next run sees every file as NEW and rebuilds from scratch.

**↔️ Bidirectional (what it *tracks*):**

> The manifest tracks **both ends of the source→page relationship plus the reconciliation between them**. `sources{}` is the input side (raw files), `pages{}` is the output side (wiki pages), `orphans{}` + `tombstones{}` handle soft/hard deletion. The link graph is a derived index computed by walking everyone's `outgoing_links`.

**🔒 Python-only (who *writes* it):**

> Only `manifest_update.py` writes this file. The LLM never emits, touches, or sees the manifest. It is the canonical example of the **D8 boundary**: Python owns the bookkeeping; LLM owns the semantic intent.

---

## 1. Role — Why Manifest Matters Most

### The volatility hierarchy

```
Volatile batons      (overwritten each run):     last_scan.json, compile_result.json
Append-only journals (kept per run_id):          state/runs/<run_id>.json, state/llm_resp/<run_id>/
Durable ledger       (THE persistent state):     manifest.json    ◀── the one that matters
```

Among everything in `state/`, **only `manifest.json` is both mutable and kept across runs.** Everything else either gets overwritten (batons) or never changes after writing (journals).

### What depends on the manifest

Every stage downstream of the scanner reads the manifest:

| Reader | Uses manifest for |
|---|---|
| `kdb_scan.py` | Compare current file hashes to prior `sources{}.hash` — derive `action` enum per file |
| `planner.py` | Decide retry (UNCHANGED + prior error) by checking `sources{}.compile_state` |
| `context_loader.py` | Load prior `pages{}` so the LLM sees what already exists for this source |
| `compiler.py` | Pass prior page context to the LLM via `ContextSnapshot` |
| `patch_applier.py` | Know which pages to orphan, which to rekey (MOVED), which tombstone is active |
| `manifest_update.py` | Builds the *next* manifest from prior + scan + compile_result |

The only stages that don't read the manifest are ones that run purely on fresh inputs (the response normalizer, the validators, the resp-stats writer).

### The amnesia test

Rename or delete `manifest.json` and re-run the compiler. Every raw file classifies as `NEW`. Every page in `KDB/wiki/` becomes orphaned (no manifest record). The system performs a full rebuild as if it had never run before.

That's the quickest way to understand the manifest's role: **it is the system's memory.** Batons are messages passing through. Journals are a recording of what happened. The manifest is what the system actually *remembers* between runs.

---

## 2. Top-Level Structure

```json
{
  "schema_version": "1.0",
  "kb_id": "joseph-kdb",
  "created_at": "<ISO-local>",
  "updated_at": "<ISO-local>",
  "settings":    { ... },
  "stats":       { ... },
  "runs":        { "last_run_id": "...", "last_successful_run_id": "..." },
  "sources":     { "<source_id>": <SourceRecord>, ... },
  "pages":       { "<page_key>":   <PageRecord>,   ... },
  "orphans":     { "<page_key>":   <OrphanRecord>, ... },
  "tombstones":  { "<source_id>":  <TombstoneRecord>, ... }
}
```

Four **record blocks** (`sources`, `pages`, `orphans`, `tombstones`) plus three **metadata blocks** (`settings`, `stats`, `runs`).

### The four record blocks

| Block | Keyed by | Holds | Lifecycle |
|---|---|---|---|
| `sources{}` | `source_id` (e.g. `KDB/raw/transformer.md`) | One record per **active** raw file. Hash, mtime, compile history, which pages it produced. | Deleted sources move to `tombstones{}`. |
| `pages{}` | `page_key` (e.g. `KDB/wiki/concepts/self-attention.md`) | One record per **active** wiki page. Slug, type, source_refs, outgoing_links, incoming_links_known. | Orphaned pages move to `orphans{}`. |
| `orphans{}` | `page_key` | Pages whose `supports_page_existence` went empty (all supporting sources deleted). **Pages are NOT auto-deleted** (D12). | Manual review; can be archived or deleted. |
| `tombstones{}` | `source_id` | Deleted or moved source records. Provenance kept for undo/review. | Kept permanently (v1). |

### Why four blocks instead of one

Each block has different **status invariants** and different **downstream consumers**:

- `sources{}` is queried by the scanner and planner (compile-decision logic)
- `pages{}` is queried by the applier and context loader (vault-write logic + LLM context)
- `orphans{}` is a human-review queue (not a pipeline input)
- `tombstones{}` is a lineage archive (rarely read; kept for debugging and move-detection)

Splitting them lets readers ignore the blocks they don't care about, and keeps each block's records uniformly shaped.

---

## 3. Three Jobs the Manifest Actually Does

Beyond "listing what exists," the manifest performs three load-bearing computations that nothing else in the system does.

### 3.1 Computed graph reconciliation — `incoming_links_known`

Every `PageRecord` has an `incoming_links_known` field. It is **derived**, not authored.

`manifest_update.py` walks every page's `outgoing_links`, flips the edges, and writes the inverse index. The LLM never sees or edits this field — it is pure bookkeeping, computed from the union of everyone's outgoing edges.

**Why this belongs in the manifest** (not computed on-the-fly):

- Incremental updates: only recompute entries touched this run
- Applier writes frontmatter from the manifest — would need this index anyway
- The reverse-index is a "how many pages link to X?" answer that downstream tooling (Obsidian graph view, search) can consume directly

This is where the **D8 boundary** lands in the manifest: the LLM emits outgoing edges (semantic intent), Python computes incoming edges (bookkeeping).

### 3.2 Versioned history — `previous_versions[]`

Each `SourceRecord` carries a `previous_versions[]` array. Every hash change appends one entry. Capped at **20 entries** — old versions roll off.

Two rules enforced by `manifest_update.py`:
1. **Append-only** — never mutated in place.
2. **Cap strictly at 20** — the 21st entry evicts the oldest.

This is the manifest's answer to "what did this source look like three recompiles ago?" Not a full filesystem history (OneDrive handles that), but enough lineage to debug "this compile looks wrong — did the source change?"

### 3.3 Incremental enablement — `compile_state` + `last_run_id` + `last_compiled_at`

This trio is what makes the whole system incremental.

- `compile_state` ∈ `{compiled, recompiled, moved_source, error, metadata_only}` — what happened last time
- `last_run_id` — which run produced the current record state
- `last_compiled_at` — when (or `null` if never)

The scanner's **UNCHANGED + retry** logic (Bug 5 fix from 2026-04-19) consults `compile_state` — if a file is content-unchanged but `compile_state == "error"`, the path gets promoted into `to_compile[]` for retry instead of `to_skip[]`.

Without this trio the system could not be incremental. Every run would be a full rebuild because the scanner would have no way to ask "has this been successfully compiled recently?"

---

## 4. Lifecycle Invariants

From `manifest.schema.md` §"Lifecycle invariants" — worth re-stating because they govern every manifest mutation:

- Every `PageRecord` must reference ≥1 `source_id` that exists in `sources{}` OR `tombstones{}`. (No dangling pages.)
- Removing a source from `sources{}` must either cascade `source_refs` updates to every dependent page OR mark affected pages as orphans. (Explicit choice, never implicit.)
- `previous_versions[]` is append-only, capped at 20.
- Root-level `updated_at` bumps on every successful run.
- Path format is POSIX-style, relative to vault root. Never absolute.
- Content-hash (`sha256:<64-hex>`) is authoritative; `mtime` is advisory.

### What manifest v1 deliberately doesn't do (non-goals)

- **No cross-page transactions.** If a run fails mid-write, the journal (`runs/<run_id>.json`) exists but `manifest.json` is unchanged. User re-runs. D15: journal-then-pointer.
- **No rollback** beyond "restore from OneDrive version history."
- **No schema-migration tooling.** If we break the schema, a future `manifest.py migrate-to-1.1` is its own milestone.

---

## 5. How It All Composes

```
                  ┌──────────────── manifest.json (durable ledger) ───────────────┐
                  │                                                                │
KDB/raw/ ──▶ scan ──▶ last_scan.json ──▶ plan ──▶ compile ──▶ compile_result.json ──▶ apply ──▶ KDB/wiki/
                                                                                │
                                                                                └──▶ manifest_update ──▶ next manifest.json
                                                                                                  ├──▶ runs/<run_id>.json (journal)
                                                                                                  └──▶ llm_resp/<run_id>/ (telemetry)
```

Every run **reads** the prior manifest near the start and **writes** the next manifest near the end. The batons (`last_scan.json`, `compile_result.json`) are ephemeral; the manifest is what survives.

### Where to go for each question

| Question | File |
|---|---|
| "What's in `KDB/raw/` right now and what's changed?" | `last_scan.json` |
| "What did the LLM want written this run?" | `compile_result.json` |
| **"What's the canonical state of the KDB system right now?"** | **`manifest.json`** |
| "What did the pipeline actually change this run?" | `state/runs/<run_id>.json` |
| "Was the LLM call healthy?" | `state/llm_resp/<run_id>/*.json` |
| "What pages exist in the wiki?" | `manifest.json.pages{}` (or walk `wiki/**/*.md`) |
| "Which source produced which pages?" | `manifest.json.sources{}.outputs_created` |
| "What pages link to X?" | `manifest.json.pages[X].incoming_links_known` |
| "Was this source ever successfully compiled?" | `manifest.json.sources[id].last_compiled_at` (null if never) |
| "Has this page been orphaned?" | `manifest.json.orphans{}` |
| "Was this source deleted or moved?" | `manifest.json.tombstones{}` |

---

## 6. Quick-Reference — Design Rules (from manifest.schema.md)

- **Python owns this file.** LLM never writes it, never emits it.
- **JSON, pretty-printed, UTF-8.** `indent=2`, `ensure_ascii=False`, sorted top-level keys for stable diffs.
- **Schema-versioned.** `schema_version` at the root. Breaking change bumps the version; reader must check.
- **Path format.** POSIX-style, relative to vault root. Never absolute.
- **Content-hash authoritative.** `hash` fields are `sha256:<64-hex>`; `mtime` is advisory only.
- **Write discipline.** Only `manifest_update.py` writes. Journal-then-pointer (D15): `runs/<run_id>.json` atomic write **first**, then `manifest.json` atomic write. If the second write fails, the journal exists but the ledger is unchanged — user re-runs cleanly.
