# Task #143 Blueprint v0.1 — Gmail/Substack ingestion pipeline (feeder) + pipelines.d registry

Filed 2026-08-09 from Joseph's directive: build the first **ingestion pipeline**
(feeder: external info → KDB sources) for the Substack financial-subscription
emails in `joseph.ft.public@gmail.com`, as the repeatable pattern for future
feeders (model-prompt archive next). Vocabulary on record: *ingestion pipeline*
= feeder (external → source); *compile pipeline* = scan → pass-1/1.5/2 → commit
(the existing orchestration).

Downstream intent (recorded, **out of scope**): a separate equity-research repo
will consume the extracted sources to identify/track investment ideas (idea
extraction, ledgers, follow-up). This task's contract ends at clean sources in
a known vault dir.

## 1. Problem

- The compile pipeline's input contract is "markdown files in the vault";
  nothing converts external content into such files. `ingestion/feeder/` is an
  empty placeholder; `Pipeline.feeder` exists as unused metadata (#91); the
  `"raw"` pipeline type has never had a member.
- The single hand-edited `<state_root>/pipelines.json` forces every feeder to
  edit a shared config file. Joseph's ruling: one config file per pipeline —
  pipelines become plugins (a new feeder ships its own file; nothing else
  changes).
- Gmail state: label `Substack_raw` holds the backlog (~3,931 messages per the
  Gmail UI; the API's `resultSizeEstimate` is unreliable). Label
  `Substack_ai_processed` (6 msgs) is the old workflow's processed marker and
  becomes the authoritative processed-state (D3).

## 2. Decisions (ratified 2026-08-09, Joseph)

- **D1.** The feeder is a deterministic **code module** —
  `ingestion/feeder/gmail.py` + `kdb-gmail-fetch` entry point. No LLM in the
  feeder; no ad-hoc agent conversion ("the latter is the former without the
  logics and rules written down").
- **D2.** Metadata-only frontmatter. The feeder fills only what it knows:
  `title`, `author`, `published_date`, `source_url` (canonical Substack link),
  `gmail_message_id`, `content_kind`, `feeder`, `ingested_at`. **No `domain` /
  `source_type`** — pass-1 enrich remains the single classification authority
  (prompt-versioned, schema-gated, benchmarked); a classifying feeder would be
  a second authority with its own prompt drift.
- **D3.** Gmail processed-state = **label move**: on successful conversion,
  remove `Substack_raw`, add `Substack_ai_processed`. `Substack_raw` becomes a
  self-draining work queue; failed conversions stay in `raw`. This is the only
  Gmail write; all other access is read-only.
- **D4.** No local ingestion *ledger*. One append-only conversion **journal**
  `KDB/state/feeders/gmail.jsonl` (`message_id`, `source_url`, `filename`,
  `ingested_at`, `outcome`) for audit + dedup-by-canonical-URL. The idea ledger
  belongs to the future equity-research repo.
- **D5.** Sources land in `KDB/raw/joseph-ft-public-gmail/` — the first
  `"raw"`-type pipeline root. (The 8 stray files formerly in `KDB/raw/` were
  removed 2026-08-09: 7 duplicates of in-scope vault sources, 1 stray project
  doc.)
- **D6.** Registry migration: `pipelines.json` → `pipelines.d/<id>.json`, one
  pipeline per file; loader globs + aggregates + validates cross-file id
  uniqueness; filename stem must equal the entry's `id`. The `vault-in-place`
  **id string is unchanged** — it is stamped in manifest/journal records (#91),
  so the file rename must not touch it.
- **D7.** Non-text content (video/podcast link pages): graceful degradation —
  convert with `content_kind: video|podcast` (best-effort), body = email text +
  canonical URL; the compile pipeline's noise path classifies. No transcript
  scraping in v1.
- **D8.** Backlog strategy: slice-first validation (`--max 5` → eyeball →
  `--max 25` → review gate), then chunked backlog at Joseph's go. Fetch via the
  `gws gmail` CLI (auth verified 2026-08-09: `users getProfile` →
  `joseph.ft.public@gmail.com`) — the feeder shells out; no new OAuth client.
- **D9.** One task (#143) covers workstream A (registry migration) + B (gmail
  feeder).

## 3. Design

### 3.1 Workstream A — `pipelines.d/` registry migration

- `ingestion/config/pipeline_registry.py::load_pipelines(state_root)` — replace
  single-file read with a glob of `<state_root>/pipelines.d/*.json`; each file
  holds exactly one pipeline object (the existing entry schema: `id`, `type`,
  `root`, `excludes`, `force_noise`, `force_signal`, `file_types`, `feeder`).
- Validation: per-entry rules unchanged; **plus** cross-file id uniqueness and
  filename-stem == `id`. If neither `pipelines.d/` nor legacy `pipelines.json`
  exists → `PipelineRegistryError` as today. If **only** legacy
  `pipelines.json` exists → error with an explicit migration instruction (the
  file lives in the vault, not the repo — migration is a one-time operator
  step, performed in this task for the prod vault: write
  `pipelines.d/vault-in-place.json` + `pipelines.d/gmail-substack.json`,
  delete `pipelines.json`). If **both** exist → fail-closed error directing the
  operator to remove the legacy file (never silently pick one).
- Orchestrator/menu/loader API signatures unchanged — consumers see the same
  `list[Pipeline]`.
- New prod entry `gmail-substack.json`: `type: "raw"`, root
  `<vault>/KDB/raw/joseph-ft-public-gmail`, `file_types: [".md"]`, empty
  excludes/force lists, `feeder: {"command": "kdb-gmail-fetch"}` (descriptive,
  per #91 v1). `vault-in-place`'s `"KDB/"` exclusion already keeps raw sources
  out of the in-place scan — unchanged and correct.

### 3.2 Workstream B — gmail feeder

Flow (`kdb-gmail-fetch [--max N] [--dry-run] [--label Substack_raw]`):

1. **List**: `gws gmail users messages list` with
   `q: "label:<label>"`, `--page-all`, capped at `--max`.
2. **Journal skip**: message-ids already journaled as `converted`/`dedup` are
   skipped (belt; the label is the primary state).
3. **Get**: `gws gmail users messages get` `format=full` per message → headers
   (`Subject`, `From`, `Date`, `Message-ID`) + best body part (prefer
   `text/html`; base64url decode).
4. **Extract**: HTML → markdown with boilerplate stripping (unsubscribe footer,
   tracking images, button chrome); canonical Substack URL = first
   `substack.com/p/` (or `/s/` post) link, else the view-in-browser link;
   best-effort `content_kind` (`video` if the page is a video-embed/player
   link, `podcast` for audio embeds, else `article`). `author` from `From:`;
   `published_date` from `Date:` (ISO).
5. **Dedup**: if `source_url` already appears in the journal → outcome `dedup`,
   no file written, **labels still moved** (a duplicate left in `raw` would
   re-poll the queue forever), journal records `dedup_of`.
6. **Write**: `<slug>.md` into the raw dir; slug from title, short message-id
   suffix on collision; atomic write via `common/atomic_io`.
7. **Label move**: `users messages modify` —
   `addLabelIds=[<processed>]`, `removeLabelIds=[<raw>]`; label IDs resolved at
   runtime by name via `users labels list` (never hardcoded).
8. **Journal**: append one JSONL line per message (atomic append).

Failure handling: per-message try/except — failures are logged to stderr and
left in `Substack_raw`; the run ends with summary counts
(`converted/skipped/dedup/failed`); non-zero exit only on fatal errors
(auth failure, missing label, raw dir unwritable). `--dry-run` prints the
planned conversions (id, title, url, content_kind) with no file writes, no
label moves, no journal appends.

Frontmatter template (the full D2 contract — also the input contract for the
future ideas repo):

```yaml
---
title: <Subject, stripped of Re:/Fwd:>
author: <From display name or address>
published_date: <ISO date from Date: header>
source_url: <canonical Substack URL>
gmail_message_id: <Gmail API message id (the id list/get/modify operate on)>
content_kind: article | video | podcast
feeder: gmail-substack
ingested_at: <ISO timestamp>
---
```

Layering: `ingestion/feeder/` imports `common` only (atomic_io, paths); it must
NOT import compiler/kdb_graph/orchestrator — `gws` access lives behind a small
subprocess seam (`feeder/gmail_client.py`) so tests inject fixtures (the
`tools/replay.py` capture pattern). Boundary guard
(`tools/tests/test_package_boundaries.py`) must stay green.

### 3.3 Compile-pipeline integration (no code)

Next `kdb-orchestrate --pipeline gmail-substack` run scans the raw dir and
compiles like any other source (pass-1 classifies noise — including
`content_kind: video` sources — per the existing path).

## 4. Implementation plan

- **Phase A** (registry): loader glob/aggregate + validations + error paths;
  tests; prod vault config migration; docs line.
- **Phase B** (feeder): `gmail_client` seam → extraction → dedup/journal →
  writer → label move → CLI + entry point.
- **Phase C** (live gate): `--max 5 --dry-run` preview → real `--max 5` →
  Joseph eyeballs sources + Gmail labels → `--max 25` → review → chunked
  backlog only at Joseph's go.

## 5. TDD test plan

- A: glob aggregation across ≥2 files; id-uniqueness violation; filename≠id;
  legacy-only error message; `vault-in-place` id preserved; orchestrator menu
  unchanged (existing tests re-pointed).
- B: extraction fixtures (captured `gws` JSON): boilerplate stripped; canonical
  URL variants (`/p/`, view-in-browser); `content_kind` article vs video vs
  podcast; slug collision suffix; dedup-by-URL (`dedup_of`, no file, labels
  moved); journal append format; label-id resolution by name; `--dry-run`
  zero-side-effects; per-message failure isolation (one bad message doesn't
  stop the batch; stays unlabeled).
- Boundary guard green; full non-live suite green.

## 6. Verification gates

1. Phase A: unit tests green + prod `pipelines.d/` loads (`graphdb-kdb`/
   orchestrate startup unaffected).
2. Phase B: unit tests green.
3. Phase C: live slice of 5 — sources well-formed (frontmatter D2-complete,
   bodies readable), labels moved in Gmail UI, journal appended, re-run no-ops.

## 7. Blast radius

- Repo: `ingestion/config/pipeline_registry.py` + its tests; new
  `ingestion/feeder/gmail.py` + `gmail_client.py` + tests; `pyproject.toml`
  (entry point; possibly one small HTML→markdown dep — check existing deps
  first); `docs/CODEBASE_OVERVIEW.md` + `AGENTS.md` structure lines at closure.
- Vault (one-time, operator): `KDB/state/pipelines.json` → `pipelines.d/`;
  `KDB/raw/joseph-ft-public-gmail/` created; `KDB/state/feeders/` created.
- External: Gmail label writes on the two labels only.

## 8. Success criteria

- `kdb-gmail-fetch --max 5` converts 5 real emails into D2-conformant sources
  in `KDB/raw/joseph-ft-public-gmail/`; Gmail labels moved; journal appended;
  immediate re-run is a no-op.
- `kdb-orchestrate --pipeline gmail-substack` scans and compiles the converted
  sources end-to-end.
- `pipelines.d/` registry loads both pipelines; legacy `pipelines.json` gone;
  full non-live suite green.
