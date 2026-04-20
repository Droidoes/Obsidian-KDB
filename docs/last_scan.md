# `last_scan.json` — Role, Schema, and Semantics

**Companion to**: `kdb_compiler/schemas/last_scan.schema.json` · `compile_result.md` · `manifest.schema.md` · `CODEBASE_OVERVIEW.md` §5

Consolidates the Q&A walkthrough from 2026-04-20: what `last_scan.json` contains, what role it plays in the pipeline, and how its three decision fields answer the "does this file need compiling?" question.

---

## Mental Models at a Glance

Two framings carry most of the intuition. Read these first, then the sections below fill in the mechanics.

**🏃 The baton (what `last_scan.json` *is*):**

> `last_scan.json` is **the scanner's baton** passed to the planner — same pattern as `compile_result.json` at the next seam. It captures one scan; the next scan overwrites it. The only `last_scan.json` that exists is the latest one.

**🔍 Evidence vs. verdict (how to read `last_scan.json`):**

> The scanner reports **evidence** in `files[]` (what's on disk, hashes, sizes, mtimes, change-action) and a **verdict** in `to_compile[]` / `to_reconcile[]` / `to_skip[]` (what the planner should do next). The verdict is the scanner's actionable output; `files[]` is the raw data it's derived from.

---

## 1. What `last_scan.json` Does

### Role — the handoff at the scan → plan seam

`last_scan.json` is produced by `kdb_scan.py` and consumed by `kdb_compile.py` / the planner. It answers two distinct questions in one file:

1. **"What's in `KDB/raw/` right now, and what changed since the last scan?"** → `files[]` + `summary`
2. **"What should the pipeline do about it?"** → `to_compile[]` · `to_reconcile[]` · `to_skip[]`

The planner and compiler downstream read the three decision lists directly. They do not re-derive decisions from `files[]` — that work is already done by the scanner.

### Volatility — one file, overwritten each run

Same retention pattern as `compile_result.json`:

- **One `last_scan.json` on disk at a time.** The latest scan overwrites the previous.
- **No scan history kept.** If you want "what did the scan say three runs ago," it's gone.
- Historical run-level records live in `state/runs/<run_id>.json` (journal of what *changed in the vault*) — not in scan outputs.

### Growth profile

- **`files[]` scales linearly with `KDB/raw/`.** 1000 raw files → 1000 `scanEntry` entries.
- **The file itself does not accumulate history.** It's a snapshot, not a log.

---

## 2. Schema Walkthrough

### 2.1 Evidence — `files[]`

One `scanEntry` per file in `KDB/raw/`. Required fields:

| Field | Meaning |
|---|---|
| `path` | Canonical relative path (e.g. `KDB/raw/transformer.md`) |
| `action` | Change-action enum: `NEW` · `CHANGED` · `UNCHANGED` · `MOVED` |
| `current_hash` | `sha256:…` of current file content |
| `current_mtime` | Current filesystem mtime |
| `size_bytes` | Current file size |
| `file_type` | `markdown` · `binary` · `unknown` |
| `is_binary` | Boolean |

Conditional fields (required depending on `action`):

| When `action` is… | Also required |
|---|---|
| `CHANGED` | `previous_hash`, `previous_mtime` |
| `UNCHANGED` | `previous_hash`, `previous_mtime` |
| `MOVED` | `previous_hash`, `previous_mtime`, `previous_path` |
| `NEW` | *(none — no prior state exists)* |

**`DELETED` is deliberately NOT in `files[]`.** Deleted files are surfaced only in `to_reconcile[]` — if they're gone from disk, they cannot appear in a list of "files on disk."

### 2.2 Verdict — the three decision fields

These are what the planner actually acts on.

**`to_compile[]`** — paths the planner sends to the LLM.
- Every `NEW` and `CHANGED` file appears here.
- `UNCHANGED` files can *also* appear here — for retry cases (see §2.5).

**`to_reconcile[]`** — manifest-only ops, no LLM call needed.
- `MOVED` — rename detection matched a prior-hash at a new path. Journal records the rekey; pages get rekeyed.
- `DELETED` — prior-known file no longer on disk. Tombstone written to manifest; downstream applier marks the page stale.

**`to_skip[]`** — paths that need nothing. Content unchanged *and* prior compile was clean.

**Schema invariants enforced by `validate_last_scan.py`:**

- `to_compile` and `to_skip` are **disjoint** — a path cannot be in both.
- `to_compile` paths have `action ∈ {NEW, CHANGED, UNCHANGED}`.
- `to_skip` paths have `action == UNCHANGED`.
- Every `NEW` / `CHANGED` path in `files[]` appears in `to_compile`.
- Every `UNCHANGED` path in `files[]` appears in exactly one of `to_compile` (retry) or `to_skip`.
- No duplicate paths in `files[]`, `to_compile`, or `to_skip`.

### 2.3 Summary counts

`summary` has one integer per action class (`new`, `changed`, `unchanged`, `moved`, `deleted`, `error`, `skipped_symlink`) so the CLI can print a one-line digest without walking `files[]` itself.

### 2.4 Provenance — `settings_snapshot`

Captures which scanner settings produced this scan (`rename_detection`, `symlink_policy`, `scan_binary_files`, `binary_compile_mode`). Useful for debugging "why did this scan classify X differently?" — the snapshot tells you whether a setting changed between runs.

### 2.5 The "UNCHANGED + retry" nuance

This is where the scanner quietly consults **more than just the hash** to decide verdicts.

An `UNCHANGED` file means "content hash didn't change since the last scan." Normally that routes to `to_skip[]`. But if the prior compile for that path **errored** (provider failure, validation rejection, etc.), the scanner promotes the file back into `to_compile[]` so the next run retries it.

This is Bug 5 from the 2026-04-19 session: before the fix, errored sources with unchanged content never retried because they classified as `UNCHANGED` and went straight to `to_skip[]`. The fix was in the planner side — the scanner correctly emits the evidence (`UNCHANGED` with prior error), and the routing logic promotes it into `to_compile[]`. The `validate_last_scan` invariant was loosened accordingly to permit `UNCHANGED` in `to_compile[]`.

**Takeaway**: the three decision fields are not a pure function of `files[]` alone — they also reflect manifest-known error state. That's why they live in the scan output (pre-computed verdict), not derived later by the planner.

---

## 3. How It All Composes

```
KDB/raw/ ──▶ scanner ──▶ last_scan.json ──▶ planner ──▶ compiler ──▶ compile_result.json ──▶ applier ──▶ KDB/wiki/
                                │                                           │
                                └── "what changed on disk + verdict"        └── "what the LLM wants written"
                                          volatile, overwritten                      volatile, overwritten
```

Two baton artifacts, two seams, same retention pattern:

| Baton | Seam | Writer | Reader | Overwritten? |
|---|---|---|---|---|
| `last_scan.json` | scan → plan | `kdb_scan.py` | `kdb_compile.py`, planner | ✅ each scan |
| `compile_result.json` | compile → apply | `compiler.py` (live) or operator (fixture) | `kdb_compile.py`, applier | ✅ each compile |

Neither file is the audit trail. History lives in:

| Question | File |
|---|---|
| "What's on disk right now?" | `last_scan.json` |
| "What did the LLM want written this run?" | `compile_result.json` |
| "What did the pipeline actually change this run?" | `state/runs/<run_id>.json` |
| "Was the LLM call healthy?" | `state/llm_resp/<run_id>/*.json` |
| "What's in the wiki right now?" | `state/manifest.json` + `wiki/**/*.md` |

---

## 4. Quick-Reference — Where Things Live

| Question | Field / file |
|---|---|
| "What files are in `KDB/raw/`?" | `last_scan.files[]` |
| "Did this specific file change?" | `files[i].action` + compare `current_hash` vs `previous_hash` |
| "Does this file need compiling?" | Path in `to_compile[]` vs `to_skip[]` vs `to_reconcile[]` |
| "Was this file renamed or deleted?" | `to_reconcile[]` with `type: MOVED` or `type: DELETED` |
| "How many changed this run?" | `summary.changed` |
| "Which scanner settings produced this scan?" | `settings_snapshot` |
