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

### 7.4 Locked weights (D27, Round 3)

| Bucket | Weight | Members |
|---|---|---|
| Pipeline gate | **20%** | S0 |
| Quality core | **30%** | M1 (20%) + M5 (5%) + M4 (15% — split between Quality and Output Integrity but lives in Quality core for total) |
| Slug-page pairing | **10%** | M2 (5%) + M3 (5%) |
| Output integrity | (folded into Quality core via M4 + M5) | — |
| Cost | **15%** | M6 |
| Latency | **15%** | M7 |
| **Total** | **100%** | (S0 20 + M1 20 + M2 5 + M3 5 + M4 15 + M5 5 + M6 15 + M7 15) |

Source-words denominator on M6/M7 (vs. per-page or per-token): closes the page-spam exploit Codex review surfaced; corpus-controlled, model-independent, tokenizer-independent.

### 7.5 Cross-model normalization

Cost/latency raw rates differ in magnitude across models by 3× or more. Direct weighted summation would let cost dominate everything. Instead:

- **M6 / M7 are Borda-normalized within the candidate set** (D28). Average-rank algorithm: best raw rate → 1.0, worst → 0.0, ties get the average rank, all-equal candidates each get 0.5.
- **The other measures stay as raw rates** in [0,1]. They're already in a comparable scale (Jaccard, pass rates, etc.).
- **`final_score`** is the weighted sum, with pro-rata redistribution if any measure has rate=None (model-controlled zero-denom on M1/M2/M3/M5 scores 0.0 not None, per Round 4 MF6).

Borda is candidate-set-dependent — `final_score` is comparable **only within the same scorecard's candidate set**. The user's workflow is "rank latest, pick best" (D28); cross-version comparison is not a designed-for use case. Raw rates are exposed in the scorecard footer for cross-run magnitude inspection.

### 7.6 Data flow

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

### 7.7 Pointer to spec

For Phase 3 mechanics (per-measure pseudocode, edge-case policies, Borda algorithm details, Round 4 corrections), see [`docs/task19-kpi-design.md`](task19-kpi-design.md). That doc is the historical record of design rounds 1–4 and the locked spec; this section in the North Star doc is the durable summary.

---

## 8. Decisions Ledger

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

---

## 9. Open Questions

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

## 10. Roadmap

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

### M3+ (deferred)
- [ ] Track 2 (`llm-linker`) — separate sub-project
- [ ] News Clippings ingestion channel (from Google Sheet)
- [ ] Books sub-project (Track 3)
- [ ] Binary parsers (PDF, image OCR)
- [ ] Scale validation at 1,000+ sources
- [ ] Add 3rd model to benchmark to restore Borda gradient on M6/M7
- [ ] Ground truth dataset for benchmark (Task #20)

---

## 11. External References

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
