# Manifest Schema — Reference

**Status:** v1 (`schema_version: "1.0"`). Authoritative Python shape lives in `kdb_compiler/types.py` (M1). This document is the human-readable reference; a formal `manifest.schema.json` may be added in v1.1 if we find drift between the Python dataclasses and what's on disk.

## File location

`~/Obsidian/KDB/state/manifest.json` — the ledger. Written by `manifest_update.py` only. Read by `kdb_scan.py`, `planner.py`, `context_loader.py`, `compiler.py`.

## Design rules

- **Python owns this file.** LLM never writes it, never emits it.
- **JSON, pretty-printed, UTF-8.** `indent=2`, `ensure_ascii=False`, sorted top-level keys for stable diffs.
- **Schema-versioned.** `schema_version` at the root. Any breaking change bumps the version; reader must check.
- **Path format:** all path strings are POSIX-style, relative to vault root (`KDB/raw/...`, `KDB/wiki/concepts/...`). Never absolute.
- **Content-hash authoritative:** `hash` fields are `sha256:<64-hex>`. `mtime` fields are advisory only.

## Top-level shape

```json
{
  "schema_version": "1.0",
  "kb_id": "joseph-kdb",
  "created_at": "<ISO-UTC>",
  "updated_at": "<ISO-UTC>",
  "settings":    { ... },
  "stats":       { ... },
  "runs":        { "last_run_id": "...", "last_successful_run_id": "..." },
  "sources":     { "<source_id>": <SourceRecord>, ... },
  "pages":       { "<page_key>":   <PageRecord>,   ... },
  "orphans":     { "<page_key>":   <OrphanRecord>, ... },
  "tombstones":  { "<source_id>":  <TombstoneRecord>, ... }
}
```

Where:
- `<source_id>` is a POSIX path like `KDB/raw/attention-paper.md`.
- `<page_key>` is a POSIX path like `KDB/wiki/concepts/attention-mechanism.md` (resolved from slug by `paths.py`).

## `settings`

```json
{
  "raw_root":           "KDB/raw",
  "wiki_root":          "KDB/wiki",
  "summaries_root":     "KDB/wiki/summaries",
  "concepts_root":      "KDB/wiki/concepts",
  "articles_root":      "KDB/wiki/articles",
  "log_file":           "KDB/wiki/log.md",
  "index_file":         "KDB/wiki/index.md",
  "hash_algorithm":     "sha256",
  "rename_detection":   true,
  "delete_policy":      "mark_orphan_candidate",
  "removed_link_policy":"soft_remove",
  "full_rebuild_supported": true
}
```

Settings rarely change. Stored in the manifest (not code) so that operators can audit what a given run used.

## `stats`

Derived counters; `manifest_update.py` recomputes on every run. Never hand-edit.

```json
{
  "total_raw_files": 0,
  "total_pages": 0,
  "total_summary_pages": 0,
  "total_concept_pages": 0,
  "total_article_pages": 0,
  "total_runs": 0
}
```

## `SourceRecord`

One per raw file currently active. Deleted files move to `tombstones`.

| Field | Type | Notes |
|---|---|---|
| `source_id` | string | same as key; redundant but aids debugging |
| `canonical_path` | string | POSIX relative; same as source_id for v1 |
| `status` | enum | `active` \| `moved` \| `deleted` \| `error` |
| `file_type` | string | `markdown` \| `binary` \| `unknown` |
| `hash` | string | `sha256:<64-hex>` |
| `mtime` | number | Unix seconds; advisory |
| `size_bytes` | number |  |
| `first_seen_at` | string | ISO UTC |
| `last_seen_at` | string | ISO UTC |
| `last_compiled_at` | string | ISO UTC; null if never compiled |
| `last_run_id` | string |  |
| `compile_state` | enum | `compiled` \| `recompiled` \| `moved_source` \| `error` \| `metadata_only` (binaries) |
| `compile_count` | number |  |
| `summary_page` | string | page_key of the summary page |
| `outputs_created` | array of page_key |  |
| `outputs_touched` | array of page_key |  |
| `concept_ids` | array of slug | concepts this source contributed to |
| `link_operations` | object | `{links_added, links_removed, backlink_edits}` — summary stats from the run |
| `provenance` | object | `{title, parser, compiler_version, schema_version_used}` |
| `previous_versions` | array | history entries (capped at 20); one per hash change |

## `PageRecord`

One per active wiki page (summary / concept / article). `index.md` and `log.md` are Python-authored and not tracked here.

| Field | Type | Notes |
|---|---|---|
| `page_id` | string | page_key path |
| `slug` | string | derived from path by `paths.py` |
| `page_type` | enum | `summary` \| `concept` \| `article` |
| `status` | enum | `active` \| `stale` \| `orphan_candidate` \| `archived` |
| `title` | string | human title (from frontmatter) |
| `created_at` | string | ISO UTC |
| `updated_at` | string | ISO UTC |
| `last_run_id` | string |  |
| `source_refs` | array | `[{source_id, hash, role}]` where role ∈ `primary` \| `supporting` \| `historical` |
| `supports_page_existence` | array of source_id | if empty → orphan candidate |
| `outgoing_links` | array of slug | what this page links to |
| `incoming_links_known` | array of slug | **derived** by `manifest_update.py` from everyone's `outgoing_links` — do not hand-edit |
| `last_link_reconciled_at` | string | ISO UTC |
| `confidence` | enum | `low` \| `medium` \| `high` |
| `orphan_candidate` | bool | convenience flag; mirrors status |

## `OrphanRecord`

Flagged when a page's `supports_page_existence` goes empty (all supporting sources deleted or all no longer supportive). The page itself is NOT deleted (D12).

| Field | Type |
|---|---|
| `page_id` | string |
| `flagged_at` | string (ISO UTC) |
| `reason` | string |
| `previous_supporting_sources` | array of source_id |
| `recommended_action` | enum | `review_manually` \| `archive` \| `delete` |
| `last_run_id` | string |

## `TombstoneRecord`

Records sources that are deleted or moved. Kept for provenance and to support undo/review.

| Field | Type |
|---|---|
| `source_id` | string |
| `status` | enum | `deleted` \| `moved` |
| `moved_to` | string | if status=moved |
| `hash` | string |
| `recorded_at` | string (ISO UTC) |
| `last_run_id` | string |

## Lifecycle invariants

- Every page must reference ≥1 `source_id` that exists in `sources` OR in `tombstones`.
- Removing a `source_id` from `sources` must either cascade `source_refs` updates across all pages OR mark affected pages as orphans.
- Never mutate `previous_versions[]` in place (append-only, cap at 20).
- `updated_at` at the root bumps on every successful run.

## Non-goals (v1)

- No cross-page transactions. If a run fails mid-write, the journal (`runs/<run_id>.json`) exists but `manifest.json` is unchanged. User re-runs.
- No rollback beyond "restore from OneDrive version history."
- No schema migration tooling. A future `manifest.py migrate-to-1.1` arrives only when we break the schema.
