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
| 1 | `patch_applier.py` | `pages[path].{slug, title, page_type, outgoing_links}` for writing .md frontmatter | Query GraphDB for entity metadata at apply time |
| 2 | `manifest_update.py` | `pages` dict — adds/updates page entries, manages orphan_candidate status, supersession | Replace with GraphDB writes (entity upsert, status transitions) |
| 3 | `kdb-clean orphans` | `pages` with `status: orphan_candidate` | Query GraphDB `Entity WHERE status = 'orphan_candidate'` |
| 4 | `graphdb-kdb verify` | Compares manifest.pages against GraphDB entities for drift | Remove — no longer meaningful once manifest drops pages |
| 5 | `context_loader.py` (legacy) | `pages` for context generation | Already dead (D49). Task #72 removes it. |

---

## Critical Sequencing: Stage 9 Fatality

**Current:** Stage 9 `graph_sync` is non-fatal (D38). A sync failure logs a warning but the run still reports `success=true`.

**Why D38 made sense:** manifest carried a complete ontology copy. A failed graph_sync meant GraphDB was stale, but the system could still operate from manifest.

**Why D38 is wrong after D50:** once manifest stops carrying ontology, GraphDB is the sole ontology authority. A failed graph_sync after a successful compile means the system's ontology is stale with no fallback. Operator cannot trust graph queries until rebuild.

**Required change:** Before manifest ontology removal, Stage 9 must become **fatal for non-dry-run compiles**. A successful compile with a failed graph_sync should report `success=false` and surface the error clearly.

Alternative: compile auto-retries graph_sync once before declaring failure. But given this is a local Kuzu write (not a network call), transient failures are extremely unlikely — simpler to just make it fatal.

---

## Implementation Sequence

| Phase | Task | Dependency |
|-------|------|------------|
| A | **Blueprint approval** (this doc) | — |
| B | **Stage 9 fatality** — remove D38 non-fatal semantics for non-dry-run compiles | A |
| C | **Migrate `patch_applier`** — read entity metadata from GraphDB instead of manifest.pages | B |
| D | **Migrate `manifest_update` → `graph_update`** — supersession/orphan logic writes to GraphDB directly (entity status transitions, SUPPORTS edge management) | C |
| E | **Migrate `kdb-clean orphans`** — read orphan candidates from GraphDB | D |
| F | **Strip `pages` from manifest.json** — remove pages dict, outgoing_links, source_refs from manifest schema | C + D + E |
| G | **Remove `graphdb-kdb verify`** — no longer meaningful | F |
| H | **Remove legacy `context_loader.py`** (Task #72) | D49 (already done) |

Phases C/D/E can potentially be parallelized once B lands.

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
- **`graphdb-kdb rebuild`** — still regenerates from run journals (D39)
- **`kdb-compile` overall flow** — scan → compile → apply pages → persist state; the internal wiring changes but the operator-facing contract is unchanged
- **Page .md files in vault** — still written by patch_applier

---

## Acceptance Criteria

1. `manifest.json` contains only source-file metadata after a full compile run.
2. All ontology queries (entity lookup, link traversal, orphan detection) route through GraphDB.
3. Stage 9 graph_sync failure on a non-dry-run compile reports `success=false`.
4. `graphdb-kdb rebuild` remains the recovery path for corrupted/missing GraphDB.
5. All existing tests pass or are migrated.
6. `kdb-clean orphans --apply` still works, reading from GraphDB instead of manifest.

---

## Open Questions

- **Rename manifest.json?** Once it's source-meta-only, the name "manifest" is arguably misleading. Candidate: `source_state.json`. Defer to implementation time.
- **Schema version bump?** Removing `pages` is a breaking schema change. Version 3.0 with a one-time migration that drops pages? Or just drop them and let old tooling fail loud?
