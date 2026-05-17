# Task #73 — Manifest Ontology Removal (D50)

**Status:** pending
**Parent:** Manifest succession arc (§CODEBASE_OVERVIEW → manifest-succession-arc.md)
**Depends on:** D49 (GraphDB-only context — shipped `0b6f64e`)
**Decision:** D50

---

## Problem Statement

`manifest.json` currently dual-writes ontology data (pages, outgoing_links, source_refs, orphan status) alongside source-file metadata. Since D49, GraphDB is the only context authority — but manifest still carries a complete ontology copy that is:

1. **Redundant** — GraphDB's Entity/LINKS_TO/SUPPORTS already holds this.
2. **Architecturally confusing** — two "sources of truth" for the same data invites drift.
3. **A migration blocker** — manifest can't be slimmed to source-meta-only ledger while it still owns page/link state.

Piecemeal removal (e.g., stop writing outgoing_links only) creates a half-stale manifest, which is worse than either clean dual-write or clean removal.

---

## Decision D50

**`manifest.json` is no longer an ontology store.** GraphDB owns Entity, LINKS_TO, SUPPORTS, orphan status, and graph topology. `manifest.json` remains only as a **source-file metadata ledger** (file hashes, compile state, ingest timestamps) until renamed/replaced.

---

## Current Manifest Ontology Consumers

| # | Consumer | What it reads from manifest | Migration target |
|---|----------|-----------------------------|-----------------|
| 1 | `patch_applier.py` | `pages[path].{slug, title, page_type, outgoing_links}` for writing .md frontmatter | Derive from `compile_result` directly (entity metadata is already in the compile output before graph sync runs) — NOT from querying GraphDB, which hasn't been written yet at apply time |
| 2 | `manifest_update.py` | `pages` dict — adds/updates page entries, manages orphan_candidate status, supersession | Split into: (a) `source_state_update` for source-meta writes, (b) existing adapter-driven graph sync via `ObsidianRunsAdapter` (D-S0) — do NOT create a new `graph_update` module inside `kdb_compiler` |
| 3 | `kdb-clean orphans` | `pages` with `status: orphan_candidate`, archives markdown, computes slug-safe retractions | Query GraphDB `Entity WHERE status = 'orphan_candidate'`; reconstruct page path from `Entity.slug + Entity.page_type` (wiki/{page_type}s/{slug}.md convention); detect surviving same-slug pages via Entity status != orphan_candidate; cleanup journaling stays replayable via existing `retraction.json` sidecar format |
| 4 | `graphdb-kdb verify` | Compares manifest.pages against GraphDB entities for drift | Retire manifest-backed mode. Replace with **replay-to-temp-DB structural equality**: rebuild to a temp Kuzu dir from run journals, diff against live graph. CLI concept survives; implementation changes. |
| 5 | `context_loader.py` (legacy) | `pages` for context generation | Already dead (D49). Task #72 removes it. |

---

## New Compile Commit Order Under D50

### The Problem With Current Ordering

Current pipeline stages 7–9:
```
Stage 7: patch_applier  — writes .md files to vault
Stage 8: manifest_update — writes pages + source-meta to manifest.json
Stage 9: graph_sync     — archives sidecar + writes to GraphDB (D38: non-fatal)
```

If Stage 9 becomes fatal *after* Stages 7/8 have written, a graph_sync failure leaves:
- Markdown files updated (Stage 7 committed)
- Manifest updated with ontology data (Stage 8 committed)
- GraphDB stale (Stage 9 failed)
- Run journal records `success=false` → D39 rebuild excludes this payload

This is worse than the current state. The run produced valid compile output but it's not replayable.

### Required: Graph Sync Before Success Declaration

**Principle:** A run must be **replayable by rebuild** regardless of whether it's reported as success or failure. The sidecar archive is the source of truth for replayability — it must be written before anything can fail fatally.

**New commit order (post-D50):**

```
Stage 7:  patch_applier     — write .md files to vault (idempotent, re-runnable)
Stage 8a: archive_sidecar   — write compile_result + last_scan to state/runs/<run_id>/
Stage 8b: graph_sync        — write to GraphDB via ObsidianRunsAdapter (FATAL on failure)
Stage 9:  source_state_update — write source-meta to manifest.json (formerly manifest_update)
Stage 10: run_journal       — write run journal with success=true
```

Key properties:
- **Sidecar written before graph_sync.** If graph_sync fails fatally, the sidecar exists → `graphdb-kdb rebuild` can replay this run later.
- **Graph_sync failure = `success=false` in journal.** But the sidecar is present and payload_present=true → rebuild eligibility preserved (D39 eligibility: `success=true AND dry_run=false AND payload_present`).

**Wait — D39 eligibility requires `success=true`.** If graph_sync fails and we write `success=false`, rebuild won't replay it. Two options:

**Option 1 (recommended): Separate sidecar-present from run-success.**
Add a new eligibility rule: `payload_present=true` is sufficient for rebuild eligibility, regardless of success flag. The success flag tells the *operator* whether the live graph is current; the payload tells *rebuild* whether it can replay.

**Option 2: Graph_sync failure = success=true with a `graph_sync_failed` flag.**
Run still counts as successful for rebuild purposes (compile was valid), but carries a warning flag. Operator sees the flag and runs `graphdb-kdb rebuild` manually. Simpler but semantically dishonest — the live graph IS stale.

**Recommendation: Option 1.** Amend D39 eligibility to `(success=true OR payload_present=true) AND dry_run=false`. This means rebuild always has maximum replay coverage. The success flag accurately reports live-graph health.

### Why patch_applier Does NOT Need GraphDB

`patch_applier` runs at Stage 7, before graph_sync. It renders frontmatter (slug, title, page_type, outgoing_links) from data that's already available in `compile_result.compiled_sources[].pages[]`. It does not need to query GraphDB — the compile output is the authoritative source at render time. GraphDB is just the persistence target for the same data.

Migration path: change `patch_applier` to read from `compile_result` payload directly instead of `next_manifest.pages`. This is a source-of-data change, not a pipeline-ordering change.

---

## Implementation Sequence (Revised)

| Phase | Task | Dependency |
|-------|------|------------|
| A | **Blueprint approval** (this doc) | — |
| B | **Reorder stages: sidecar before graph_sync** — separate sidecar archival from graph_sync; make graph_sync fatal; amend D39 eligibility | A |
| C | **Migrate `patch_applier`** — derive frontmatter from `compile_result` directly, not from manifest.pages | A (independent of B) |
| D | **Split `manifest_update`** — extract `source_state_update` (source-meta only) from page/ontology writes; page/ontology writes already handled by existing graph_sync adapter (D-S0) | B + C |
| E | **Migrate `kdb-clean orphans`** — read orphan candidates from GraphDB; reconstruct page paths from Entity.slug + page_type; maintain replayable cleanup journaling | D |
| F | **Strip `pages` from manifest.json** — remove pages dict, outgoing_links, source_refs from schema; version bump | C + D + E |
| G | **Evolve `graphdb-kdb verify`** — retire manifest-backed diff; implement replay-to-temp-DB structural equality check | F |
| H | **Remove legacy `context_loader.py`** (Task #72) | D49 (already done, independent) |

Phases B and C are independent — can be parallelized.

---

## What Remains in manifest.json After D50

```json
{
  "schema_version": "3.0",
  "sources": {
    "KDB/raw/foo.md": {
      "hash": "sha256:...",
      "size_bytes": 12345,
      "file_type": "markdown",
      "last_compiled_at": "2026-05-17T...",
      "compile_count": 3,
      "last_run_id": "2026-05-17T..."
    }
  },
  "runs": {
    "last_successful_run_id": "2026-05-17T..."
  }
}
```

No `pages`, no `outgoing_links`, no `source_refs`, no `orphan_candidate` status.

---

## What Does NOT Change

- **Run journals / sidecar archives** — still written to `state/runs/`
- **`graphdb-kdb rebuild`** — still regenerates from run journals (D39, with amended eligibility)
- **`kdb-compile` operator-facing contract** — scan → compile → pages in vault; internal wiring changes but operator experience unchanged
- **Page .md files in vault** — still written by patch_applier
- **Adapter boundary (D-S0)** — `kdb_compiler` routes through `ObsidianRunsAdapter`, never calls GraphDB core directly

---

## §8.3 / §8.4 Documentation Update Required

Post-D50, the following CODEBASE_OVERVIEW claims become historical:

- §8.3: "Stage 9 graph_sync is D38 non-fatal" → becomes fatal
- §8.4: "delete manifest → GraphDB still queryable; delete GraphDB → manifest still works" → only the first half remains true for ontology; manifest no longer carries ontology data

These should be updated when Phase B lands (not before, to avoid docs/code divergence).

---

## Acceptance Criteria

1. `manifest.json` contains only source-file metadata after a full compile run.
2. All ontology queries (entity lookup, link traversal, orphan detection) route through GraphDB.
3. Stage 9 graph_sync failure on a non-dry-run compile reports `success=false` in run journal.
4. Sidecar archive is written *before* graph_sync — a failed graph_sync run remains replayable by rebuild.
5. D39 rebuild eligibility amended: `(success=true OR payload_present=true) AND dry_run=false`.
6. `graphdb-kdb rebuild` remains the recovery path for corrupted/missing GraphDB.
7. All existing tests pass or are migrated.
8. `kdb-clean orphans --apply` still works, reading from GraphDB; cleanup journals remain replayable.
9. `graphdb-kdb verify` replaced with replay-to-temp-DB structural equality (CLI survives, implementation changes).

---

## Open Questions

- **Rename manifest.json?** Once it's source-meta-only, "manifest" is misleading. Candidate: `source_state.json`. Defer to implementation time.
- **Schema version bump?** Removing `pages` is a breaking change. Version 3.0 with a one-time migration that drops pages on first write? Or just drop them and let old tooling fail loud?
- **D39 eligibility amendment timing:** Should this land with Phase B (recommended) or as a standalone pre-Phase-B change?
