# Obsidian-KDB — Codebase Overview (North Star)

**Status:** v1 architecture locked; M0 → M2 landed (compiler + validator + reconciler + benchmark engine all live)
**Last updated:** 2026-05-08
**Owners:** Joseph (human) + Claude Opus 4.7 (staff architect) + GPT 5.4 / Codex 5.3 (external review)

This is the **single source of truth** for the Obsidian-KDB project. All design rationale, decisions, and open questions live here. External AI consultation artifacts (Grok / Gemini Pro / GPT 5.4 / Codex 5.3) are referenced but not authoritative — they fed into the consensus captured below.

---

## 1. Vision

A Karpathy-style LLM-compiled knowledge base (KDB) that lives inside Joseph's Obsidian vault without disturbing its existing human-curated structure.

**Core insight (Karpathy):** The LLM is the compiler. Raw sources (`raw/`) → compiled wiki (`wiki/`) via incremental LLM passes. Obsidian is the IDE/frontend; plain Markdown + wikilinks are the only storage format the end-user sees.

**What's novel in our build:** Most community implementations let the LLM directly write markdown files via agent tools (Claude Code / Cursor Write/Edit). That gives the LLM free authorial control and produces hallucinated paths, corrupt frontmatter, and inconsistent state. **Our architecture makes the LLM output structured JSON "page intents"; deterministic Python owns every file path, every byte of frontmatter, and every filesystem write.** This matches the discipline of a real compiler (LLM = parser/semantic analyzer; Python = codegen/linker).

**Design philosophy — no complexity for imaginary risk.** This system has one user, one process, and infrequent operation (minutes to hours between compiles, not milliseconds). We do not add locking/retry/transaction ceremony designed for multi-tenant or high-contention systems. Any individual file's corruption is recoverable by re-compiling — the value is in the collective body of `raw/` + `wiki/` + connections, not any single file. Cheap insurance only (atomic temp+fsync+replace, journal file, 2-retry max on transient I/O). No lock files, no two-phase commits, no cross-file transactions.

---

## 2. Two-Sided Vault Architecture

The vault has two distinct sides with different ownership:

| Side | Path | Owner | Purpose | Mutability |
|---|---|---|---|---|
| **Human Side** | `~/Obsidian/{AIML, Daily Notes, Projects, ...}` (22 existing folders) | Joseph, manually | Daily capture, thematic organization, long-form notes | Pristine — no LLM writes |
| **Machine Side** | `~/Obsidian/KDB/` | LLM compiler (via Python) | Raw sources + compiled wiki + state ledger | LLM owns `wiki/`; Python owns `state/`; Joseph owns `raw/` |

The two sides coexist as peers. Cross-linking between them is opt-in and asymmetric (see §8 Open Questions, Open-4).

---

## 3. Repo vs. Vault Separation

Two completely separate filesystems:

| Concern | Path | VCS / Backup |
|---|---|---|
| **Code** (this repo) | `~/Droidoes/Obsidian-KDB/` (WSL Linux) | git + GitHub |
| **Data** (vault) | `~/Obsidian/KDB/` (Windows local drive, OneDrive-synced) | OneDrive (30-day version history) |

The code reads from and writes to the vault via absolute paths. No nested git repos. No symlinks. OneDrive is the backup — we do **not** run a separate git repo inside the vault (earlier proposal dropped; OneDrive version history is sufficient for v1).

---

## 4. Two Tracks

### Track 1 — KDB Compiler (this project, v1 focus)
`raw/` → LLM → `wiki/{summaries, concepts, articles}`

Karpathy-pattern incremental compile. Described in detail below.

### Track 2 — `llm-linker` (deferred to v1.5 / v2)
In-place enhancer for the Human Side. Scans user-authored notes and injects `[[wikilinks]]` to KDB concepts. Renamed from "enhancer" at Joseph's request. Separate implementation; not part of this v1 scope.

---

## 5. Track 1 Pipeline (V1a)

```
┌────────────────┐   ┌───────────┐   ┌──────────────────┐   ┌────────────┐   ┌───────────────────┐   ┌──────────────────┐
│   kdb_scan.py  │──▶│ planner.py│──▶│ compiler.py      │──▶│ validate.py│──▶│ patch_applier.py  │──▶│ manifest_update  │
│ (deterministic │   │ (chunk    │   │ (per-source LLM, │   │ (schema)   │   │ (Python writes    │   │  .py (atomic     │
│  scan, hashes) │   │  batches) │   │  JSON output)    │   │            │   │  all .md files)   │   │  ledger update)  │
└────────────────┘   └───────────┘   └──────────────────┘   └────────────┘   └───────────────────┘   └──────────────────┘
       │                                                                                                       │
       ▼                                                                                                       ▼
 last_scan.json                                                                                         manifest.json
                                                                                                         runs/<run_id>.json
```

**Strict separation of concerns:**
- **LLM is stateless compute.** It receives prompt + source content + manifest snapshot; returns JSON with `slug`-keyed page intents (no paths, no timestamps, no frontmatter). Never writes files. Never reads filesystem state.
- **Python is deterministic state + I/O.** Scans, hashes, chunks, resolves paths, applies page intents (writes markdown), stamps frontmatter, updates ledger.
- **Markdown vault is persistent state.** Everything the system knows is reconstructible from `raw/` + `wiki/` + `state/`.

### Page ownership split

| Page | Authored by | Strategy |
|---|---|---|
| `wiki/summaries/*.md` | LLM | Full-body replacement; Python adds frontmatter |
| `wiki/concepts/*.md` | LLM | Full-body replacement; Python adds frontmatter |
| `wiki/articles/*.md` | LLM | Full-body replacement; Python adds frontmatter |

No `index.md` (D23) and no `log.md` (D24) are generated. Obsidian's file explorer + `manifest.json` serve as the TOC; `state/runs/<run_id>.json` is the authoritative per-run journal.

### Pipeline stages

1. **Scan** (`kdb_scan.py`) — walks `raw/`, computes SHA-256, compares to `manifest.json`, emits `last_scan.json` with `to_compile` + `to_reconcile` lists. Handles symlinks (skip), binaries (flag metadata-only), two-pass rename detection. Atomic write.
2. **Plan** (`planner.py`) — reads `last_scan.json`, chunks `to_compile` into 10–20-source batches, builds per-source context snapshot from manifest.
3. **Compile** (`compiler.py`) — for each source: calls `call_model_with_retry` with source content + manifest snapshot + `KDB-Compiler-System-Prompt.md`; receives `compiled_sources[]` entry (slugs + page bodies, no paths/metadata); accumulates into `compile_result.json`.
4. **Validate** (`validate_compile_result.py`) — schema-gates `compile_result.json`; aborts run with no vault writes if malformed.
5. **Compute next manifest (pure)** (`manifest_update.build_manifest_update`) — in-memory only; no writes. Produces `next_manifest` + `journal`.
6. **Apply page intents** (`patch_applier.py`) — resolves slugs to paths (`paths.py`), stamps frontmatter from `next_manifest` (`run_context.py`), writes markdown files atomically (`atomic_io.py`). Never writes state files.
7. **Persist manifest** (`manifest_update.write_outputs`) — writes `runs/<run_id>.json` journal first, then `manifest.json` atomically (D15, journal-then-pointer). Runs **after** page writes so a failed vault write leaves state unchanged and the user re-runs cleanly.

---

## 6. State Model

Adopts **GPT 5.4's three-layer design**, hardened by Codex 5.3:

| Layer | Storage | Authority |
|---|---|---|
| **Per-page provenance** | Frontmatter in each `.md` file (`raw_path`, `raw_hash`, `raw_mtime`, `compiled_at`) | Human-readable, survives manifest loss |
| **Ledger** | `KDB/state/manifest.json` | Authoritative index of sources, pages, orphans, tombstones, runs |
| **Audit trail** | `KDB/state/runs/<run_id>.json` | Per-compile journal (JSON) — authoritative; no derived `log.md` mirror (D24) |

**Rejected alternatives:** SQLite (too opaque, no diff, breaks OneDrive sync), vector DB (Karpathy explicitly rejects this), pure frontmatter-only (Grok's proposal — too lean at projected scale of thousands of files, no dependency graph).

**Manifest schema:** see `kdb_compiler/manifest.schema.md` (to be written in M1). Top-level sections: `schema_version`, `settings`, `stats`, `runs`, `sources`, `pages`, `orphans`, `tombstones`.

---

## 7. Benchmark Architecture (`kdb_benchmark/`)

The benchmark engine is the cross-model quality + cost + latency comparison layer that sits *next to* the compiler, not inside it. It consumes the per-call telemetry the compiler already emits (`RespStatsRecord` written by `compile_one`'s `finally` block) and produces a Borda-normalized scorecard ranking the participating models on a curated source corpus.

The full spec lives in [`docs/task19-kpi-design.md`](task19-kpi-design.md) (Phase 3 + Round 4 corrections, ~1000 lines). This section is the architectural summary — what someone needs to know to navigate the engine and modify it without re-reading the spec.

### 7.1 Package layout & boundary

```
kdb_benchmark/
├── runner.py     # invokes compile_one per source, isolated state_root
├── scorer.py     # per-measure functions, Borda, final_score
├── scorecard.py  # JSON + render_terminal artifact
├── registry.py   # models.json (provider, model, prices)
├── cli.py        # `kdb-benchmark --models a,b --sources <dir>`
└── tests/
benchmark/
├── sources/      # canonical 5-source corpus (CC-BY etc., tracked in git)
├── runs/         # per-model resp_stats records (gitignored)
├── inspect/      # ad-hoc inspection scratchpad (gitignored)
└── scores/       # JSON + .txt scorecards (tracked)
```

**One-way import boundary** (D25): `kdb_benchmark` imports from `kdb_compiler` (via `compile_one`, validators, types); `kdb_compiler` never imports from `kdb_benchmark`. The benchmark depends on the compiler's contract, not the reverse — keeps the production pipeline unaware of measurement concerns.

### 7.2 Input contract

The scorer reads dict-shaped `RespStatsRecord` JSONs the compiler writes during a benchmark run. **Capture-full mode (`KDB_RESP_STATS_CAPTURE_FULL=1`) is mandatory for scoring** (D26): without it, `parsed_json` is None on parse-pass records and measures M1/M2/M3/M4/M5/S3 cannot be computed. The runner sets the env var; the scorer raises `RuntimeError` if a benchmark record violates the contract.

`RespStatsRecord` is corpus-coverage authoritative — it has one record per attempted compile, including failed ones. `compile_result.compiled_sources[]` only contains successful compiles, so it is *not* the scorer's denominator authority for stage-success rates.

### 7.3 KPI structure (locked Round 3 + Round 4)

**Tier 1 — Stage Success Rates (S0 weighted; S1/S2/S3 diagnostic)**

| ID | Name | What it measures |
|---|---|---|
| **S0** | `pipeline_success_rate` | parse_ok ∧ schema_ok ∧ no hard-zero validator findings — the per-source binary "did this attempt produce a usable artifact" gate |
| S1 | `llm_resp_success_rate` | parse_ok rate (diagnostic only) |
| S2 | `validator_schema_pass_rate` | schema_ok rate over parse-pass set (diagnostic only) |
| S3 | `validator_hard_zero_pass_rate` | no-hard-zero rate over schema-pass set (diagnostic only) |

**Tier 2 — Measures (all weighted)**

| ID | Name | Formula | Domain |
|---|---|---|---|
| **M1** | `link_target_resolution` | (outgoing_links pointing to slugs in own emit-set) ÷ total | Graph integrity |
| **M2** | `concept_slugs_jaccard` | symmetric Jaccard of declared concept_slugs vs concept-typed pages | Slug-page pairing |
| **M3** | `article_slugs_jaccard` | same for article_slugs | Slug-page pairing |
| **M4** | `semantic_pass_rate` | post-schema semantic_check pass rate | Output integrity |
| **M5** | `body_emit_set_coverage` | fraction of declared `concept_slugs ∪ article_slugs` appearing as `[[slug]]` wikilinks in *other* pages' bodies (self-links excluded) | Output integrity |
| **M6** | `cost_per_1k_source_words` | (Σ input × price_in + Σ output × price_out) ÷ (source_words/1000) | Production cost |
| **M7** | `latency_per_1k_source_words` | Σ latency_ms ÷ (source_words/1000) | Production latency |

**Diagnostic-only telemetry (no weight, tracked for inspection):** `retry_load`, `token_overrun_rate`, `pages_per_1k_source_words`.

### 7.4 Locked weights (D30, supersedes D27 for M5/M6/M7)

| Bucket | Weight | Members |
|---|---|---|
| Pipeline gate | **20%** | S0 |
| Quality core | **50%** | M1 (20%) + M4 (15%) + M5 (15%) |
| Slug-page pairing | **10%** | M2 (5%) + M3 (5%) |
| Cost | **10%** | M6 |
| Latency | **10%** | M7 |
| **Total** | **100%** | (S0 20 + M1 20 + M2 5 + M3 5 + M4 15 + M5 15 + M6 10 + M7 10) |

D30 (2026-05-10) supersedes D27's M5/M6/M7 weights. M5 was 5% under D27 when it measured body_link_jaccard (tautological-by-construction post-#57 reconciler); after Task #59 swapped M5 to body_emit_set_coverage (a real body-content measure), the 5% weight was too low — qwen-flash-us topped the post-#60 regression scorecard despite M5=0.111. M5 now equals M4 in weight; M6/M7 each lose 5% to fund the bump. Quality core grows 30% → 50% of FINAL.

Source-words denominator on M6/M7 (vs. per-page or per-token): closes the page-spam exploit Codex review surfaced; corpus-controlled, model-independent, tokenizer-independent.

### 7.5 Cross-model normalization

Cost/latency raw rates differ in magnitude across models by 3× or more. Direct weighted summation would let cost dominate everything. Instead:

- **M6 / M7 are Borda-normalized within the candidate set** (D28). Average-rank algorithm: best raw rate → 1.0, worst → 0.0, ties get the average rank, all-equal candidates each get 0.5.
- **The other measures stay as raw rates** in [0,1]. They're already in a comparable scale (Jaccard, pass rates, etc.).
- **`final_score`** is the weighted sum, with pro-rata redistribution if any measure has rate=None (model-controlled zero-denom on M1/M2/M3/M5 scores 0.0 not None, per Round 4 MF6).
- **Outlier penalty** (D31, Task #62). After the weighted sum + pro-rata redistribution, an outlier penalty is applied: for each in-scope measure (S0 + M1–M5), models more than 10% below the candidate-set norm receive `−0.05` per 10%-band of deviation. Penalty units accumulate across measures; FINAL is floored at 0. Surfaces single-axis outliers that the weighted sum would otherwise average away. M6/M7 are excluded (already Borda-relative). See §7.6 below.

Borda is candidate-set-dependent — `final_score` is comparable **only within the same scorecard's candidate set**. The user's workflow is "rank latest, pick best" (D28); cross-version comparison is not a designed-for use case. Raw rates are exposed in the scorecard footer for cross-run magnitude inspection.

### 7.6 Outlier penalty (D31)

The weighted sum + pro-rata redistribution produces a "balanced average" FINAL that
treats each measure equally up to its weight. This dilutes single-axis outliers — a
model with one catastrophic measure but five healthy ones still ranks high. The
outlier penalty addresses this directly.

**Formula.** For each model and each in-scope measure (S0, M1, M2, M3, M4, M5):

  norm           = mean(measure.rate across active models, excluding rate=None)
  deviation_pct  = max(0, (norm − value) / norm × 100)
  penalty_units  = floor(deviation_pct / 10)

Per-model total: Σ penalty_units across in-scope measures × 0.05 → penalty deduction.
FINAL_with_penalty = max(0.0, FINAL_pre_penalty − total_penalty).

**Properties.**
- One-sided: only below-norm penalized.
- M6/M7 excluded: already Borda-normalized; penalizing them again would double-count.
- Cumulative, no cap: multi-axis underperformance compounds.
- Floor at 0: FINAL ∈ [0, 1] preserved.

**Visibility.** A `PENALTY` column in the rendered scorecard sits between M7_b and
FINAL, showing the deduction (e.g. `-0.40` or `-` for zero). The pre-penalty value
is preserved on `RunScore.final_score_pre_penalty` for audit.

See `docs/task62-outlier-penalty-design.md` for the worked example and full
locked-decision set (D31.1–D31.12).

### 7.7 Data flow

```
benchmark/sources/*.md
        │ (corpus, manifest gitignored)
        ▼
kdb_benchmark.runner.run_benchmark
        │  compile_one(source, isolated state_root, capture-full)
        ▼
benchmark/runs/<run_id>/state/llm_resp/*.json   (one RespStatsRecord per source)
        │
        ▼
kdb_benchmark.scorer.score_run → RunScore (raw rates per measure)
        │
        ▼  (collect across candidate models)
kdb_benchmark.scorer.score_runs → enriched RunScores with m6_borda, m7_borda, final_score
        │
        ▼
kdb_benchmark.scorecard.write_scorecard
        │  → benchmark/scores/<scorecard_id>.json   (machine)
        │  → benchmark/scores/<scorecard_id>.txt    (human, byte-equal to render_terminal)
        ▼
benchmark/runs/<run_id>/score_trace.txt  (always-on per-run + cross-run trace, --verbose mirrors to stdout)
```

CLI: `kdb-benchmark --models <a,b,...> --sources <dir> [--verbose]`.

### 7.8 Pointer to spec

For Phase 3 mechanics (per-measure pseudocode, edge-case policies, Borda algorithm details, Round 4 corrections), see [`docs/task19-kpi-design.md`](task19-kpi-design.md). That doc is the historical record of design rounds 1–4 and the locked spec; this section in the North Star doc is the durable summary.

---

## 8. GraphDB-KDB Layer (Kuzu-backed knowledge graph)

The reframe locked on 2026-05-10 (paradigm doc: `docs/New-GraphDB-Paradigm.md`): **KDB is a raw-text → knowledge-graph compiler**, not a wiki-page compiler with a graph as a byproduct. Wiki pages and `manifest.json` are *renderings* of the graph; the graph is the architectural primitive that downstream tooling (search, knowledge-hole detection, EXISTING CONTEXT seed selection, adaptive learning paths) consumes.

The bet is **explicit edges beat implicit similarity** — vector RAG flattens ontology into cosine distance; the graph preserves the explicit edges paid to construct. See memory note `feedback_graph_over_vector_for_kdb`.

### 8.1 Package layout & boundary

```
graphdb_kdb/                                ← producer-agnostic ontology layer
├── schema.py                               # Kuzu DDL (Entity / Source / LINKS_TO / SUPPORTS)
├── types.py                                # Entity, Source dataclasses; SyncResult, RebuildResult
├── graphdb.py                              # GraphDB connection manager + idempotent schema bootstrap
├── ingestor.py                             # apply_compile_result — atomic per-run mutations
├── queries.py                              # neighbors, paths, provenance reads
├── analytics.py                            # PageRank, Louvain, structural holes (hybrid via NetworkX)
├── verifier.py                             # verify_against_manifest — overlap audit
├── rebuilder.py                            # rebuild() — generic chronological replay (D-B1)
├── adapters/
│   ├── base.py                             # ProducerAdapter Protocol; RunDescriptor / EligibilityResult
│   └── obsidian_runs.py                    # Obsidian-KDB adapter (reference impl)
└── cli.py                                  # graphdb-kdb CLI dispatcher
```

**One-way import boundary** (D34 + D-B1, mirrors D25 for kdb_benchmark): `graphdb_kdb/` has **zero imports from `kdb_compiler`**. Producer-specific knowledge lives inside `adapters/obsidian_runs.py` and is expressed as JSON parsing of producer artifacts — never as Python imports of producer types. A grep invariant on `from kdb_compiler\|import kdb_compiler` inside `graphdb_kdb/` returns nothing.

**Physical separation** (D35): the Kuzu *data* directory lives at `~/Droidoes/GraphDB-KDB/` (sibling to `Obsidian-KDB/`, not OneDrive-synced — avoids binary-file corruption). The Python package code lives at `graphdb_kdb/` inside `Obsidian-KDB/` today; the extraction arc to a standalone repo `~/Droidoes/GraphDB-KDB-package/` is documented in `docs/graphdb-kdb-extraction-roadmap.md`.

### 8.2 Schema (Kuzu DDL)

```cypher
CREATE NODE TABLE Entity (
    slug          STRING PRIMARY KEY,    -- producer-emitted identifier; bare per D-S1 grandfather for Obsidian
    title         STRING,
    page_type     STRING,                -- summary | concept | article  (values still Obsidian-flavored, per D-A2 deferred)
    status        STRING,                -- active | stale | archived | orphan_candidate
    confidence    STRING,                -- low | medium | high
    created_at    STRING,                -- ISO with local offset (no UTC normalization per feedback_local_time_everywhere)
    updated_at    STRING,
    first_run_id  STRING,
    last_run_id   STRING
);

CREATE NODE TABLE Source (
    source_id          STRING PRIMARY KEY,
    source_type        STRING,           -- discriminator (multi-source-ready per D32-tempered); "obsidian-kdb-raw" for v1
    canonical_path     STRING,
    status             STRING,           -- active | moved | deleted | error
    file_type          STRING,
    hash               STRING,
    size_bytes         INT64,
    first_seen_at      STRING,
    last_seen_at       STRING,
    last_ingested_at   STRING,           -- renamed from last_compiled_at per D-A2 (graph-side ingestion concept)
    ingest_state       STRING,           -- renamed from compile_state per D-A2
    ingest_count       INT64,            -- renamed from compile_count per D-A2
    last_run_id        STRING,
    moved_to           STRING
);

CREATE REL TABLE LINKS_TO ( FROM Entity TO Entity, run_id STRING, created_at STRING );
CREATE REL TABLE SUPPORTS ( FROM Source TO Entity, role STRING, hash_at_time STRING, run_id STRING, created_at STRING );
```

**Naming history**: `Entity` was originally `Page` (renamed per D-A1 2026-05-14); `ingest_*` fields were originally `compile_*` (renamed per D-A2). Producer payloads (`compile_result.json`) retain the older names — the Obsidian adapter translates. The verifier's `_SOURCE_DIRECT_FIELDS` tuples are the alias bridge: `("compile_state", "ingest_state")` etc.

### 8.3 Pipeline integration — Stage 9 via adapter (D-S0)

`kdb-compile`'s 9-stage pipeline ends with **Stage 9 `graph_sync`**:

```
Stages 1–8 (existing): scan → validate scan → compile → validate compile_result →
                       reconcile → build manifest → apply pages → persist state

Stage 9 graph_sync (per D38 non-fatal):
  9a. Archive sidecar: atomic-copy state/{compile_result,last_scan}.json
      → state/runs/<run_id>/{compile_result,last_scan}.json
  9b. Live sync: graphdb_kdb.adapters.obsidian_runs.ObsidianRunsAdapter()
      .sync_current_run(cr, scan_dict, run_id)
```

Two architectural properties of the wiring:

1. **`kdb_compile.py` imports ONLY `ObsidianRunsAdapter`** (D-S0). Never `GraphDB`, never `apply_compile_result` directly. The adapter is the single producer→graph entry point — same code path as `graphdb-kdb rebuild` uses.
2. **Sidecar archival runs *before* the live sync.** If the sync fails (D38 non-fatal: warning + journal entry; overall run still success=true), the sidecar still exists — so `graphdb-kdb rebuild` is a real recovery path.

### 8.4 Replay / rebuild path (D39 — the independence proof)

`graphdb-kdb rebuild --vault-root <P>` drops all Kuzu tables and replays the eligible subset of `state/runs/*.json` chronologically:

- **Eligibility filter** (D39): `success=true AND dry_run=false AND payload_present`. Payload = per-run sidecar at `state/runs/<run_id>/{compile_result,last_scan}.json`. Adapters declare which producer journal `schema_version` they support (D-S3) — version mismatches return structured skip reasons (`'unsupported_version'`), not silent corruption.
- **B-lite split** (D-B1): `rebuilder.py` is producer-agnostic (drop-all + chronological iterate + per-run try/except); the adapter (`adapters/obsidian_runs.py`) supplies discover_runs / is_eligible / load_payload / apply. No producer-specific code in the core.
- **Blast radius v1** (D-S2, L8): whole-DB drop only; producer-scoped rebuild deferred until producer #2 ships. CLI prints a warning before the drop unless `--yes`.
- **Baton-backfill** (one-shot, opt-in via `--backfill-baton`): synthesizes a `RunDescriptor` pointing at `state/{compile_result,last_scan}.json` baton files using `manifest.runs.last_successful_run_id` as the synthetic run_id; sorts before all real runs (`sort_key="0000-pre-63-backfill"`); idempotent — silently skipped if a sidecar already exists at `state/runs/<run_id>/`. The one-time migration entry for the latest pre-#63 run, per #63.0 outcome (d) — the other 9 pre-#63 runs are unrecoverable.

Independence claim: **delete `manifest.json` → GraphDB still queryable; delete `~/Droidoes/GraphDB-KDB/` → manifest still works**. Both are derived from `compile_result`. `graphdb-kdb verify` audits overlap; `graphdb-kdb rebuild` regenerates either store from the post-#63 run history.

### 8.5 Pointers to companion docs

The blueprint + companion docs are the durable architecture record. This section is the navigation summary.

| Doc | Scope |
|---|---|
| [`docs/task-graphdb-kdb-blueprint.md`](task-graphdb-kdb-blueprint.md) | Locked decisions D32–D40 + D-A1/A2/B1/S0–S3; schema DDL; ingestion algorithm; rebuild semantics; #63.1–#63.9 sub-task ledger |
| [`docs/New-GraphDB-Paradigm.md`](New-GraphDB-Paradigm.md) | Conversational record of the 2026-05-10 reframe (graph-is-the-system); scope distinction GraphDB-KDB vs future `kdb-graph` |
| [`docs/graphdb-kdb-producer-contract.md`](graphdb-kdb-producer-contract.md) | Formal contract for what GraphDB-KDB expects from any producer (mutation payload + scan + run journal + sidecar archive); adapter interface |
| [`docs/graphdb-kdb-extraction-roadmap.md`](graphdb-kdb-extraction-roadmap.md) | 5-stage path from monorepo to standalone PyPI package; invariants PR1–PR10; anti-patterns |
| [`docs/manifest-succession-arc.md`](manifest-succession-arc.md) | M0–M4 transition arc: manifest.json from swiss-knife (source meta + ontology) to source-meta-only ledger; EXISTING CONTEXT switches to GraphDB at M1 |
| [`docs/task63-phase3-implementation-blueprint.md`](task63-phase3-implementation-blueprint.md) | Implementation plan for #63.5b + #63.6 + #63.7-pre (the three sub-tasks landed 2026-05-14) |

### 8.6 CLI surface (current)

```
graphdb-kdb init                                        # create Kuzu dir + schema
graphdb-kdb stats [--json]                              # node/edge counts by type
graphdb-kdb neighbors <slug> [--depth N] [--direction]  # BFS expansion
graphdb-kdb incoming <slug>                             # sugar for neighbors --direction in
graphdb-kdb path <from> <to> [--max-hops N]             # shortest directed path
graphdb-kdb cypher "<query>" [--params <json>]          # ad-hoc Cypher escape hatch
graphdb-kdb pagerank [--top N]                          # NetworkX-backed PageRank
graphdb-kdb communities                                 # Louvain community assignments
graphdb-kdb structural-holes                            # inter-community bridge counts
graphdb-kdb orphans                                     # list orphan-candidate entities
graphdb-kdb subgraph-by-source <source_id>              # source's induced subgraph
graphdb-kdb verify --vault-root <P>                     # diff Kuzu vs manifest.json
graphdb-kdb rebuild --vault-root <P> [--backfill-baton] # drop + replay (D-S2 whole-DB)
                  [--yes] [--json]
```

`--graph-dir <path>` overrides the Kuzu data directory (default: `$KDB_GRAPH_PATH` or `~/Droidoes/GraphDB-KDB/`).

---

## 9. Decisions Ledger

| # | Date | Decision | Rationale |
|---|---|---|---|
| D1 | 2026-04-18 | Two-Sided Vault (Human Side / Machine Side) with `KDB/` at vault top-level | Zero disruption to existing human-curated folders; clean ownership boundary |
| D2 | 2026-04-18 | Code repo separate from vault data | Git on code (WSL), OneDrive on data (Windows); no nested repos |
| D3 | 2026-04-18 | Track 2 renamed "enhancer" → `llm-linker` | User preference; shorter |
| D4 | 2026-04-18 | v1 target use case = pull `docs/` from `~/Droidoes/*` repos as seed raw sources | Known high-value content, low risk |
| D5 | 2026-04-18 | OneNote stays on Human Side | User decision |
| D6 | 2026-04-18 | No git inside vault; OneDrive version history is sufficient backup | Avoids `.git/index.lock` races with OneDrive sync |
| D7 | 2026-04-18 | Adopt GPT 5.4 state model (manifest.json + frontmatter + log.md + runs/) | Middle ground: richer than Grok's pure-markdown, lighter than Gemini's DAG+Git+Intent Architecture, matches working community patterns |
| D8 | 2026-04-18 | **LLM outputs "page intents" (slug + title + body + logical links); Python owns paths, frontmatter, timestamps, versions, backlink reconciliation.** Revised from original "patch-ops" wording after Codex M0 review. | Predictability, auditability, dry-run capability, no hallucinated paths / corrupt frontmatter. Boundary purity: LLM = semantic analyzer, Python = codegen/linker. |
| D9 | 2026-04-18 | Controller pipeline over mega-prompt (chunk 10–20 sources/batch) | Prevents prompt drift at 100+ files (Codex guidance) |
| D10 | 2026-04-18 | Reject SQLite for v1 (possibly v2 if scale demands) | JSON is LLM-inspectable, diff-friendly, OneDrive-compatible |
| D11 | 2026-04-18 | Content-hash (SHA-256) as source-of-truth; mtime is advisory only | Survives renames, OneDrive timestamp rewrites, cross-machine sync |
| D12 | 2026-04-18 | Flag-don't-nuke on delete: `orphan_candidate` + `tombstones`, never auto-delete wiki pages | User reviews orphans manually; no data loss |
| D13 | 2026-04-18 | Two-pass rename detection (hash-match before NEW/DELETED classification) | Prevents double-counting moved files (Codex fix) |
| D14 | 2026-04-18 | Minimal atomic write: temp + fsync + os.replace + ≤2-retry on transient I/O. **No lock files, no 6-retry ladder, no multi-phase commit.** | Single-user single-process workload; heavier machinery is imaginary-risk complexity. Revised from original Codex proposal after user philosophy note. |
| D15 | 2026-04-18 | Journal-then-pointer manifest writes (`runs/<run_id>.json` first, manifest.json last) | Crash-safe: failed runs don't corrupt ledger. Cheap; keep it. |
| D16 | 2026-04-18 | Provider abstraction ported from `~/Droidoes/Code-projects/youtube-comment-chat/src/llm.py` | Reuse: Anthropic / Gemini / OpenAI / Ollama already supported |
| D17 | 2026-04-18 | V1a: build full pipeline upfront (not evolve from mega-prompt) | Cleaner foundation, no rework later |
| D18 | 2026-04-18 | **Full-body replacement** over patch-ops for LLM-authored pages | Wiki pages are 100% LLM-owned; no human edits to preserve; no concurrent writers. Patch-op language, merge semantics, and per-op test surface = complexity for zero gain. Forward-compatible: the applier can accept `body` today and `ops[]` later without schema break. |
| D19 | 2026-04-18 (revised 2026-04-20) | Page-ownership split: LLM authors `summaries/`, `concepts/`, `articles/`. Originally included Python-authored `index.md` + `log.md`; both removed (D23, D24). | Python-authored files are pure functions of state; having the LLM emit them would waste tokens and risk drift. |
| D20 | 2026-04-18 | Shared seam modules: `paths.py`, `atomic_io.py`, `types.py`, `run_context.py` | Codex M0 review: three modules independently claim atomic-write discipline; centralize to prevent subtle divergence. |
| D21 | 2026-04-18 | Reserve `prompt_builder.py`, `context_loader.py`, `response_normalizer.py` as named stubs | Codex M0 review: `compiler.py` is trending toward god-module; reserve split points before M2 to avoid accretion. |
| D22 | 2026-04-18 | Design philosophy: **no complexity for imaginary risk** | Single-user, single-process, infrequent workload. Individual file corruption is recoverable by re-compile; the value is the collective body, not any single file. Drop machinery designed for multi-tenant/concurrent scenarios. See `~/.claude/projects/.../memory/feedback_no_imaginary_risk.md`. |
| D23 | 2026-04-20 | Drop `index.md`. Obsidian's file explorer + `manifest.json.pages{}` already serve as the TOC; the generated `index.md` was adding a misleading hub node to the graph view (every page had an inbound edge from it) without unique value. | Graph noise was real; the "single entry-point file" was redundant with Obsidian's native navigation and with `manifest.json` for programmatic consumers. Revises D19. |
| D24 | 2026-04-20 | Drop `log.md`. Same reasoning as D23: derived state, zero wikilinks = isolate node in graph view, and `state/runs/<run_id>.json` already holds the authoritative per-run journal with full detail. Warnings/info surfaced via stdout banners during the run; anyone needing post-hoc detail opens the JSON journal. | Eliminates a redundant human-facing mirror; no information is lost — just stops maintaining two views of the same data. Revises D19. |
| D25 | 2026-05-04 | Benchmark engine is a separate top-level package (`kdb_benchmark/`) with a strict one-way import boundary: `kdb_benchmark` may import from `kdb_compiler`; `kdb_compiler` never imports from `kdb_benchmark`. | Production pipeline stays unaware of measurement concerns. Forces clean dependency direction; Codex review confirmed this catches accidental coupling early. See §7.1. |
| D26 | 2026-05-04 | `RespStatsRecord` (capture-full mode) is the scorer's authoritative input — not `compile_result.compiled_sources[]`. | Resp-stats has one record per attempted compile (success or fail); compile_result only contains successful sources, so it can't ground stage-success rates. See §7.2. |
| D27 | 2026-05-04 | Locked benchmark weights: S0=20, M1=20, M2=5, M3=5, M4=15, M5=5, M6=15, M7=15 (sums to 100). Source-words denominator on M6/M7. | Round 3 closure after Codex hostile review surfaced page-spam exploit on per-page denominators. Per-1K-source-words is corpus-controlled, model-independent, tokenizer-independent — least-bad denominator without ground truth. See §7.3 / §7.4. |
| D28 | 2026-05-04 | Average-rank Borda for cross-model normalization on M6/M7 only; `final_score` comparable only within the same candidate set (rank-latest-pick-best workflow). | Cost/latency raw magnitudes differ 3× or more across models; direct summation would dominate. Other measures stay as raw rates (already on a [0,1] scale). User workflow does not need cross-version comparability — defuses Codex's biggest critique without adding scorecard_version ceremony. See §7.5. |
| D29 | 2026-05-10 | M5 retired body_link_jaccard (=1.000-by-construction post-#57) is replaced by `body_emit_set_coverage`: per-source `\|((⋃_p (body_wikilink_slugs(p.body) − {p.slug})) ∩ (concept_slugs ∪ article_slugs))\| / \|concept_slugs ∪ article_slugs\|`, micro-aggregated across the run. Computed in `kdb_benchmark/scorer.py` from captured `parsed_json` — no new RespStatsRecord fields (preserves one-way boundary D25). Self-links excluded to reward cross-page integration. Weight stays 5%. See `docs/task59-m5-replacement-design.md` for full design (D29.1–D29.9 sub-decisions). |
| D30 | 2026-05-10 | M5 weight bumped 5% → 15%; M6 and M7 each bumped 15% → 10%. Total still 100%. Quality core (S0 + M1 + M4 + M5) becomes 70% of FINAL (was 55%); cost+latency become 20% (was 30%). | Post-#59/#60 regression scorecard showed M5=0.111 outlier (qwen-flash-us) couldn't be discriminated at the 5% weight level — model still topped FINAL despite barely integrating concepts via body wikilinks. Reweight reflects the user's "if other models can do it, why can't you?" stance: quality should dominate FINAL more than cost/latency. Cross-generation FINAL comparison invalidated again per D29.9 (same doctrine). See `docs/TASKS.md` → Task #61. |
| D31 | 2026-05-10 | Outlier penalty added to FINAL composition. For each model and each in-scope measure (S0, M1, M2, M3, M4, M5), units = floor(((norm − value)/norm × 100) / 10) when value < norm; total = Σ units across measures; FINAL_post = max(0, FINAL_pre − 0.05 × total). M6/M7 excluded (Borda-relative). Surfaces single-axis outliers that the weighted sum would average away (e.g. qwen-flash-us with M5=0.111 dethroned). Cross-generation FINAL comparison invalidated again per D29.9 doctrine. See `docs/task62-outlier-penalty-design.md` (D31.1–D31.12 sub-decisions). |
| D32 | 2026-05-13 | **GraphDB-KDB is a multi-source raw-text → knowledge-graph compiler at the storage layer**; the schema admits `Source.source_type` as a discriminator and is source-agnostic. The ingestion API (`apply_compile_result`) is Obsidian-flavored for v1 (D32-tempered per Codex Round 1 v2 review). Graph is the architectural primitive; manifest.json + wiki markdown + future visualizations are *renderings*. | Differentiating bet: explicit edges beat implicit similarity. Vector RAG flattens ontology into cosine distance; the graph preserves what we paid to build. Storage-layer multi-source readiness is cheap to bake in; ingestion-layer abstraction without a second producer would be speculative. |
| D33 | 2026-05-13 | Storage = Kuzu 0.11.3 (embedded graph DB, Cypher dialect, multi-language bindings, MIT). | Purpose-built for embedded graph; file-based (no daemon), portable, industry-standard Cypher. NetworkX+JSONL is Python-only; SQLite-with-graph-schema forces consumers to reimplement traversal. |
| D34 | 2026-05-13 | Independence-by-shared-upstream: `manifest_update.py` and `graphdb_kdb.ingestor` each consume `compile_result + last_scan + run_id` independently. Neither reads or writes the other's store. | Ablation: delete `manifest.json` → GraphDB still queryable; delete `GraphDB-KDB/` → manifest still works. Both regenerable from `state/runs/<run_id>.json` history. Real independence by structural construction. |
| D35 | 2026-05-13 | Kuzu *data* directory location: `~/Droidoes/GraphDB-KDB/` (sibling to Obsidian-KDB; not OneDrive-synced). Override via `KDB_GRAPH_PATH` env var. | Physical separation mirrors logical separation. Avoids OneDrive corruption on Kuzu binary catalog files. Backup = recovery-via-rebuild (D39); belt-and-suspenders via `graphdb-kdb snapshot` (#63.9). |
| D36 | 2026-05-13 | Naming triad: Python module `graphdb_kdb`, Kuzu directory `GraphDB-KDB/`, CLI command `graphdb-kdb`. `kdb-graph` is **reserved** for a future Obsidian-graph-view utility — out of #63 scope. | Avoid conflating the multi-source ontology layer with a (future) Obsidian-specific rendering tool. Memory: `project_graphdb_kdb_vs_kdb_graph_distinction`. |
| D37 | 2026-05-13 (renamed D-A1 2026-05-14) | Schema: `Entity` and `Source` node tables; `LINKS_TO` (Entity→Entity), `SUPPORTS` (Source→Entity) rel tables. Originally `Page` node-table; renamed to `Entity` per D-A1 to remove the Obsidian-isms from the storage-layer vocabulary. | Provenance is first-class graph data, not a sidecar. `Entity` reads as abstract identity (vs `Page` which presumed wiki-page rendering) — better positioning for multi-source future. |
| D38 | 2026-05-13 | Pipeline integration: Stage 9 `graph_sync` runs AFTER Stage 8 (manifest write); failure is **non-fatal** — emits warning + journal entry, but overall compile run still returns success. | Honors D34 independence: a failed graph write must not roll back a successful manifest write. Recovery via `graphdb-kdb rebuild`. |
| D39 | 2026-05-13 | Rebuild path: `graphdb-kdb rebuild` drops all Kuzu tables and replays the **eligible** subset of `state/runs/*.json` chronologically. **Eligibility:** `success=true AND dry_run=false AND payload_present` (payload = sidecar archive at `state/runs/<run_id>/{compile_result,last_scan}.json` per #63.0 outcome). Independence proof: Kuzu regenerable without ever reading `manifest.json`, prospectively from #63 forward. | If GraphDB drifts from compile-history truth, regenerate from compile-history truth. Pre-#63 historical runs are unrecoverable except for the latest baton state — see §8.4 baton-backfill. |
| D40 | 2026-05-13 | Hybrid analytics: Kuzu Cypher fetches topology (edge lists, node attrs); NetworkX + python-louvain computes PageRank, Louvain communities, structural-holes. | Kuzu lacks native PageRank/Louvain; implementing iteratively in Cypher is awkward. At 10⁴-node ceiling the hybrid cost is sub-second per algorithm. |
| D-A1 | 2026-05-14 (Round 1 Codex) | Schema rename: `Page → Entity` node-table label. | `Node` would collide with Kuzu's NODE keyword + universal graph-theory term. `Entity` signals abstract identity. Free upgrade while schema is empty/small. |
| D-A2 | 2026-05-14 (Round 1 Codex) | Source field renames: `compile_state → ingest_state`, `compile_count → ingest_count`, `last_compiled_at → last_ingested_at`. Page enum values (page_type/status/confidence) retained — *values* are Obsidian-flavored; renaming names without revisiting values is cosmetic. | Pipeline-specific field NAMES become pipeline-neutral now. Pipeline-specific VALUES wait for producer #2 to inform the right abstraction. Verifier carries an alias map bridging the manifest side (still `compile_*`) and graph side. |
| D-B1 | 2026-05-14 (Round 1 Codex) | Rebuilder is **B-lite (adapter split)**: thin generic core in `graphdb_kdb/rebuilder.py` (drop+recreate, chronological iter, error reporting) + producer-specific logic in `graphdb_kdb/adapters/obsidian_runs.py`. Rule: `graphdb_kdb/` MUST NOT `import kdb_compiler.*`. Public function name `rebuild_from_obsidian_runs(...)`. | Pure-C (core imports producer types) would silently weaken D34 independence. B-lite preserves it by structure, not convention. Cost: ≤200 LOC adapter; verified by grep invariant. |
| D-S0 | 2026-05-14 (Round 2 Codex) | **Stage 9 routes through the Obsidian adapter**, not direct core call. `kdb_compile.py` Stage 9 calls `graphdb_kdb.adapters.obsidian_runs.sync_current_run(cr, scan, run_id)`. Single producer→graph entry point for both live sync and replay. | Makes Doc C's "producer never calls core directly" rule literal, not aspirational. Single code path = one place to debug/test/evolve. Closes OQ-E9 in extraction roadmap. |
| D-S1 | 2026-05-14 (Round 2 Codex) | **Multi-producer entity-id namespacing**: Obsidian grandfathered as bare slugs (implicit `obsidian:` namespace); all future producers MUST use explicit `<source_type>:<entity_id>` prefix. Adapter declares `entity_id_namespace: ClassVar[str \| None]`. | Retroactive migration of existing entities is destructive without operational benefit; grandfathering is cheaper. Cross-producer queries filter via `Source.source_type`, not slug prefix parsing. |
| D-S2 | 2026-05-14 (Round 2 Codex) | **Rebuild blast radius v1**: `graphdb-kdb rebuild` always drops the whole DB regardless of `--producer` flag. Producer-scoped rebuild deferred until producer #2 ships AND the team agrees the scoped semantics (tracked as L8 + blueprint TR-3). CLI prints warning before drop. | At v1 single-producer the simple correct semantics. Deferring lets the right scoped-rebuild rules be informed by real co-tenancy needs. |
| D-S3 | 2026-05-14 (Round 2 Codex) | Adapter declares `supported_journal_versions: ClassVar[list[str]]`. Mismatched versions return structured skip reason `'unsupported_version'` rather than silent corruption. | Producer journals evolve (Obsidian is at `2.0` today). Versioning discipline must be in place before Stage 1 of package extraction, not Stage 4. |

---

## 10. Open Questions

| # | Question | Status | Plan |
|---|---|---|---|
| Open-1 | Statefulness implementation | ✅ **Closed (D7–D15)** | GPT 5.4 approach + Codex hardening |
| Open-2 | Output format / schema | 🟡 Partial | Frontmatter keys locked (D7); patch-ops JSON schema pending M2 |
| Open-3 | Safety model for Human Side edits | 🔴 Deferred | Only relevant to Track 2 (`llm-linker`), not v1 |
| Open-4 | Link direction between Sides | 🔴 Deferred | Track 2 concern; recommended **Option C (asymmetric + opt-in bidirectional)** but not confirmed |
| Open-5 | Binary file handling (PDF, images) in `raw/` | 🟡 Partial | v1 marks as `compile_mode: metadata_only`; actual PDF/image parsers = v2 |
| Open-6 | Page-intents JSON schema design (shape, not mechanism) | 🟡 Skeleton in M0.1; full design in M2 | Skeleton committed at `kdb_compiler/schemas/compile_result.schema.json` |
| Open-7 | Chunk size tuning (10–20 default) | 🟡 Heuristic | Validate empirically during M2 first compile |
| Open-8 | Slug → path policy (how `[[slug]]` resolves to a file) | 🟡 Partial | `paths.py` stub declared; rules locked in M1 (see module docstring) |

---

## 11. Roadmap

### M0 — Scaffolding (commit `796848b`) ✅
- [x] Vault scaffold: `~/Obsidian/KDB/{raw, wiki/{summaries, concepts, articles}, state/runs, KDB-Compiler-System-Prompt.md}`
- [x] Repo scaffold: `~/Droidoes/Obsidian-KDB/{docs, kdb_compiler/tests/fixtures}`
- [x] `docs/CODEBASE_OVERVIEW.md` (this file)
- [x] `KDB/KDB-Compiler-System-Prompt.md` — compiler invariants for LLM
- [x] ~~`KDB/wiki/index.md`, `KDB/wiki/log.md` (empty)~~ — dropped by D23/D24
- [x] `KDB/state/manifest.json` (initial empty shape)
- [x] `kdb_compiler/__init__.py` + 8 module stubs
- [x] Initial commit

### M0.1 — Codex review remediation ✅
All M0.1 items landed; system prompt rewritten, shared seams added, schema skeleton + test fixtures committed.

### M1 — Deterministic layer (no LLM yet) ✅
Scanner, manifest updater, validators, call_model + retry, end-to-end dry run all landed. Fixture-based unit tests green throughout.

### M1.7 — Validator + reconciler on real vault ✅
`patch_applier`, `manifest_update.write_outputs`, `kdb_compile.py` orchestrator (8-stage pipeline), validate_compile_result with gate/measure split, reconciler for measure findings. Verified live on real vault 2026-04-21.

### M2 — LLM layer + benchmark ✅
- Live LLM compiler producing `compile_result.json` from real sources
- Per-call response capture (`RespStatsRecord` + `kdb-replay` fixture-driven replay)
- `kdb_benchmark/` engine: runner + scorer + scorecard + CLI (see §7)
- Canonical 5-source corpus + `models.json` registry
- Headline scorecard 2026-05-08 baseline established (haiku-4.5 vs sonnet-4.6)
- See `docs/TASKS.md` for the 30+ tasks closed across this milestone

### M3 — GraphDB-KDB Layer (#63) ✅ (sub-tasks #63.0 through #63.7-pre)
Task #63 — refoundation as raw-text → knowledge-graph compiler. Supersedes #26 + #27. See §8.
- **Architecture deliberation:** D32–D40 locked through 3 rounds of Codex review. D-A1/A2/B1/S0/S1/S2/S3 locked through 3 more rounds during Phase 3 implementation.
- **Companion docs:** blueprint, paradigm record, producer contract, extraction roadmap, manifest succession arc, Phase 3 implementation blueprint (see §8.5).
- **Sub-tasks shipped:** #63.0 replay-contract verification; #63.1 schema + skeleton; #63.2 ingestion; #63.3 read query API; #63.4 hybrid analytics; #63.5 verifier; #63.5b rename pass (Page→Entity, compile_*→ingest_*); #63.6 B-lite rebuilder + Obsidian adapter; #63.7-pre Stage 9 wiring via adapter + sidecar archival.
- **Test surface:** 96 graphdb_kdb tests + 6 Stage-9 integration tests in kdb_compiler/tests/.
- **Remaining in #63:** #63.7 (full Stage 9 integration with live runs on canonical corpus); #63.8 (this section); #63.9 (snapshot/export).

### M3+ (deferred)
- [ ] Track 2 (`llm-linker`) — separate sub-project
- [ ] News Clippings ingestion channel (from Google Sheet)
- [ ] Books sub-project (Track 3)
- [ ] Binary parsers (PDF, image OCR)
- [ ] Scale validation at 1,000+ sources
- [ ] Add 3rd model to benchmark to restore Borda gradient on M6/M7
- [ ] Ground truth dataset for benchmark (Task #20)

---

## 12. External References

Consulted AI artifacts (stored in `~/Obsidian/Projects/Obsidian-KDB/`):
- `Karpathy LLM Knowledge Base in Obsidian - Grok.md` — original design + lean v1 statefulness
- `Statefulness Implementation -Grok.md` — community impl survey
- `Karpathy's Obsidian LLM Knowledge Base -Gemini Pro.md` — academic treatise (not adopted)
- `Karpathy Obsidian LLM Complier Implementation - GPT 5.4.md` — state model baseline (adopted)
- `Codex 5.3 Reviews of GPT 5.4 Implementation of Kaparthy Obsidian LLM KDB.md` — hardening + working code (adopted)
- `docs/code-review-M0-codex.md` — Codex 5.3 review of M0 scaffold (drove M0.1 remediation; 5 findings all actioned)

Reference implementations surveyed:
- Reddit #1 (fabswill) — mtime-based scan, manual orphan handling
- Ustaad (Sohardh/ustaad) — SHA-256 in frontmatter, log.md flagging
- ussumant/llm-wiki-compiler — standalone engine + MCP server
- Ar9av/obsidian-wiki — manifest-based state (closest to our v1)

Karpathy source:
- X post: https://x.com/karpathy/status/2039805659525644595
