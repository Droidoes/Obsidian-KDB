# Obsidian-KDB — Codebase Overview (North Star)

**Status:** v1 architecture locked; M0 → M2 landed (compiler + validator + reconciler + benchmark engine all live)
**Last updated:** 2026-05-23
**Owners:** Joseph (human) + Claude Opus 4.7 (staff architect) + GPT 5.4 / Codex 5.3 (external review)

This is the **single source of truth** for the Obsidian-KDB project. All design rationale, decisions, and open questions live here. External AI consultation artifacts (Grok / Gemini Pro / GPT 5.4 / Codex 5.3) are referenced but not authoritative — they fed into the consensus captured below.

---

## Milestone Changelog

Dated architectural inflection points. Full retrospective and three-iteration history in [`docs/JOURNEY.md`](JOURNEY.md).

- **2026-04-18** — **M0 scaffold.** KDB compiler architecture + schema-gated prompt/response contract (Task #4 family).
- **2026-04-21** — **Validator + reconciler live on real vault.** `pairing_omission` auto-heal proven on two back-to-back live runs (Task #65 / M1.7).
- **2026-05-10** — **Iteration #2 begins.** Kuzu reframed as architectural primitive; KDB becomes raw-text → knowledge-graph compiler (Task #63 family).
- **2026-05-14** — **GraphDB-KDB operational.** Schema v2 (`Entity` / `LINKS_TO` / `SUPPORTS`) + ingestor + verifier + snapshot + rebuilder + analytics (PageRank / Louvain / structural-holes) all green (Task #63 closure).
- **2026-05-16** — **Graph context loader lands.** `kdb_compiler.graph_context_loader` reads context from GraphDB (Task #70.1).
- **2026-05-17** — **LOOP CLOSED.** Manifest → graph substitution complete: D49 removes `manifest.json` as context authority; D50 strips ontology data from `manifest.json` (file-meta only); D51 establishes GraphDB as live ontology authority. Empirical proof via cold-start widening (graph 17–23 pages vs manifest 0–8) (Tasks #70, #71, #73).
- **2026-05-20** — **Canonicalization layer lands.** Stage 6 `canonicalize` inserted; `Entity.canonical_id` + `ALIAS_OF` edges shipped (Task #74).
- **2026-05-21** — **V0 step-3 ops regression suite locked.** Typed traversal + shortest-path direct-unit-guarded; `@pytest.mark.bench` opt-in pattern established (Task #81). **Schema v2.1 Domain field** shipped: `Domain` node + `BELONGS_TO` edge (Task #76).
- **2026-05-22** — **Three-iteration retrospective filed** ([`docs/JOURNEY.md`](JOURNEY.md)). This changelog itself is the mitigation for Lessons §5 (milestone-level signal was missing pre-this-doc).
- **2026-05-22** — **Round 6 closes — "Learn" operationalized.** Three Learn mechanisms ratified (Belief Revision / Identity Refinement / Abstraction & Principle Induction) + Hypothesis Promotion as first-class boundary contract per **(a+)** decision; M2 + M3 reclassified as Analysis-feeding-[C] Create; project's first articulated position on [C] Create recorded ([`docs/what-is-the-ontology-for.md`](what-is-the-ontology-for.md) §9.4; Task #82 closure; Tasks #83–#86 filed).
- **2026-05-23** — **Predeclared eval criteria + probe set ratified for #83/#84.** Task #87 v2 (eval criteria — 3 ops O1/O2/O3, P-On-N / F-On-N criteria, HW-1..HW-11 hedge-watch rules, `eval_config` block per Codex+Deepseek+Qwen panel review) + Task #87.1 v1 (20 probe scenarios across 7 §7.1 coverage axes, 8 OQs OQ-S1..S8 surfaced, D-87.1-1..10 decision gates ratified) both shipped. **Mutation-eval discipline adopted** (vs Task #75's retrieval-eval): pre-state + input → expected post-state + invariants preserved. **Unblocks #83/#84 implementation start.**
- **2026-05-23 (afternoon)** — **DeepSeek-V4-Flash returned to active pool via direct API.** The 2026-05-15 "capability gap" diagnosis was a routing artifact, not a model deficiency: Alibaba's OpenAI-compat layer was stripping/mis-handling `response_format` for non-Qwen models. Empirical fire on canonical corpus: S0=1.000, M1-M5=1.000, M7=3578ms (2.75× faster than Alibaba's best historical 9830ms). Ties #1 on cost-quality frontier with `gemini-3.1-flash-lite` at FINAL=0.956 (Gemini wins latency 4×; DeepSeek wins cost 50%). `deepseek-v4-pro:direct` dropped same-session (strictly dominated by Flash:direct — 3.2× cost, 2.7× latency, identical quality). **Meta-lesson:** control models must match the model-under-test's vendor/routing relationship, not just the routing layer.
- **2026-05-23 (Saturday afternoon)** — **#83/#84 O1 GREEN v1.4 — 14/15 probes (93%).** α-split closed three sub-arcs (S06 / S07 / S05) via *minimum-to-GREEN* changes once the harness-scope lens (disposition + drift signals only — no structural post-state assertions) was correctly applied. S06: sentinel hash was the only blocker. S07: classifier else-branch rule split per D-83/84-2 default action table (different object_slug + refines_truth=false → `qualifies_or_extends`, not `supersedes`); `object_slug` added to candidate envelope. S05: LINKS_TO-implicit-counterpart classifier fallback — when no Claim in family AND `counterpart_links_to_ref` points to a real LINKS_TO, treat as `candidate_counterpart_found` + `reinforces` (trust-the-hint on polarity/predicate — schema v2.2 LINKS_TO carries only run_id/created_at). **Tier-1 EVIDENCES reconstruction + object Entity/LINKS_TO writer in mutator + LINKS_TO predicate-field schema enrichment all stay deferred as latent debt** — observably untested at current verifier strictness (F3 shared-keys-only diff per morning ratification); will be addressed when verifier tightens after promotion-replay lands. Remaining 2 xfail (S12/S18) are a separate semantic-contradicts deferral class (LLM-classifier vs richer relation_kind authority).
- **2026-05-23 (Saturday morning)** — **#83/#84 O1 implementation — GREEN v1.2.** Schema v2.1 → v2.2 with the Claim layer (Claim node + EVIDENCES/ABOUT/SUPERSEDES/CONTRADICTS/QUALIFIES rel tables + `_migrate_2_1_to_2_2`); `_DROP_ORDER`, `snapshot.py` v3→v4, `verifier.py` (scope-limited diff), `stats()`, `cli.py` all updated to match (Tasks #12–#16). O1 Promotion Pipeline shipped as `graphdb_kdb/ops/op_1_promote.run` + `graphdb_kdb/core/belief_classifier.classify` — deterministic D-83/84-2 dispatch (3-way counterpart enum + relation_kind derivation), retracted-counterpart sibling walk per P-O1-8 OQ-18, D-83/84-8 Part D 4-cell disposition matrix, post-mutation invariant check ([G]). **11 of 15 ratified #87.1 probes pass** end-to-end with real disposition + fingerprint_drift + classification_drift assertions; 4 deferred in two clean classes: LINKS_TO-implicit-counterpart logic (S05/S06/S07 — D-83/84-7 Tier-2/Tier-3 reconstruction; option α) + semantic-contradicts without polarity flip (S12, S18). Probe corpus #87.1 v1.1 normalized (6 spike-vs-expansion variances accommodated, 3 promoted to first-class CandidateEnvelope fields, real classifier-computed fingerprint hashes). Session handoff at `docs/session-handoff-2026-05-23-saturday-morning.md`.

---

## 1. Vision

> **Architectural history — required warm-up reading.** For the *why we walked this way* across three iterations (compiler+wiki → GraphDB refoundation → loop closure + step-3 ops), see [`docs/JOURNEY.md`](JOURNEY.md). This Overview captures *what is true today*; JOURNEY captures *how we got here and what we learned*.

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

`kdb_compile.py` orchestrates a 10-stage pipeline (post-#74 — Task #74 inserted Stage [6] canonicalize between reconcile and build_source_state, renumbering downstream stages). Stage numbers below match the `# ----- [N] name -----` markers in `kdb_compile.py`.

1. **Scan** (`kdb_scan.py`) — walks `raw/`, computes SHA-256, compares to `manifest.json`, emits `last_scan.json` with `to_compile` + `to_reconcile` lists. Compile eligibility is the single honest comparison `current_hash != last_compiled_hash` (D46) — `compile_state` plays no part, and there is no force-recompile flag. Handles symlinks (skip), binaries (flag metadata-only), two-pass rename detection. Atomic write.
2. **Validate scan** — schema-gates `last_scan.json` shape before plan/compile consume it.
3. **Compile** (`compiler.py`) — for each source via `planner`-chunked 10–20-source batches: calls `call_model_with_retry` with source content + graph-derived context snapshot + `KDB-Compiler-System-Prompt.md`; receives `compiled_sources[]` entry (slugs + page bodies, no paths/metadata); accumulates into `compile_result.json`.
4. **Validate compile_result** (`validate_compile_result.py`) — schema-gates `compile_result.json`; aborts run with no vault writes if malformed.
5. **Reconcile compile_result** — unconditional `reconcile_slug_lists` + `reconcile_body_links` (D45 / Task #65 + Task #57): `concept_slugs`/`article_slugs` rebuilt from `pages[].page_type`; body wikilinks reconciled against `pages[]`. Pairing-class defects are made structurally impossible before downstream stages observe them.
6. **Canonicalize** (`kdb_compiler/canonicalize/`, Task #74, see `docs/task74-canonicalization-blueprint.md`) — loads `state/canonicalization/aliases.json` (missing ⇒ empty + warning, D-R5-8), resolves alias surface forms to canonical slugs (chain-flattened to root, D-R5-13), rewrites `pages[].outgoing_links`, `pages[].body` wikilinks, drops alias entries from `pages[]` (canonical-only, D-R5-12), emits `canonical_meta` (`aliases_emitted`, `outgoing_link_remaps`, `algorithm`), atomically overwrites `state/compile_result.json` (D-R5-10). Algorithmic failures (circular aliases, malformed ledger, ambiguous v2, sha mismatch) are **fatal** — failure journal written, pipeline halts before patch_applier (D-R5-9). Wiki ≡ graph at the naming layer.
7. **Build manifest update (pure)** (`manifest_update.build_manifest_update`) — in-memory only; no writes. Produces `next_manifest` + `journal`. Reads the canonicalized `compile_result.json`.
8. **Apply page intents** (`patch_applier.py`) — resolves slugs to paths (`paths.py`), stamps frontmatter from `next_manifest` (`run_context.py`), writes markdown files atomically (`atomic_io.py`). No canonicalization-awareness required (D-R5-12): `pages[]` is already canonical and body wikilinks already remapped. Never writes state files.
9. **Persist state** (`manifest_update.write_outputs`) — writes `runs/<run_id>.json` journal first (schema_version `2.2` post-#74), then `manifest.json` atomically (D15, journal-then-pointer). Runs **after** page writes so a failed vault write leaves state unchanged and the user re-runs cleanly.
10. **Graph sync** — see §8.3. Archives sidecar at `state/runs/<run_id>/{compile_result,last_scan}.json` (preserves `canonical_meta` for D39 replay), then routes the canonicalized compile_result through `ObsidianRunsAdapter().sync_current_run(...)` to update the live GraphDB ontology authority (D50/D51). Fatal for non-dry-run compiles (D50; revokes D38).

---

## 6. State Model

### Architectural layers (D51)

| Layer | Path | Role |
|---|---|---|
| **Source corpus** | `KDB/raw/` | Human-authored raw sources |
| **Live ontology authority** | `GraphDB-KDB/` (Kuzu) | Primary. Updated immediately on every compile (Stage 10 `graph_sync` post-#74). Owns Entity, LINKS_TO, SUPPORTS, ALIAS_OF, canonical_id, orphan status |
| **Reconstruction material** | `KDB/state/runs/<run_id>/` sidecars | Backup. Durable compile_result + scan snapshots. Enables `graphdb-kdb rebuild` if GraphDB is lost/corrupted |
| **Audit log** | `KDB/state/runs/<run_id>.json` journals | What happened, when, with which model, what failed |
| **Source-file lifecycle** | `KDB/state/source_state.json` | Source metadata ledger (hashes, compile state, timestamps). Not an ontology index (D50) |
| **Per-page provenance** | Frontmatter in each `.md` file | Human-readable (`raw_path`, `raw_hash`, `compiled_at`) |
| **Rendered view** | `KDB/wiki/` | Markdown output for Obsidian consumption |

**Primary data flow:** `raw/ → kdb-compile → Stage [6] canonicalize → Stage 10 immediate GraphDB update`. Runs are not in this hot path — they are written as audit records whose sidecars happen to also serve as reconstruction material.

**Rebuild/verify:** Proves the live authority matches what a clean reconstruction from sidecars would produce. Operational safety net, not the normal data flow.

**Rejected alternatives:** SQLite (too opaque, no diff, breaks OneDrive sync), vector DB (Karpathy explicitly rejects this), pure frontmatter-only (Grok's proposal — too lean at projected scale), `ontology_sources/*.json` per-source durable layer (redundant with sidecars, adds a third consistency surface — rejected in D51).

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
├── snapshot.py                             # snapshot() — JSONL+manifest+schema.cypher export (#63.9)
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
    page_type     STRING,                -- summary | concept | article | alias  (values still Obsidian-flavored, per D-A2 deferred)
    status        STRING,                -- active | stale | archived | orphan_candidate | alias
    confidence    STRING,                -- low | medium | high
    canonical_id  STRING,                -- Task #74: NULL ⇒ self is canonical; otherwise root canonical slug (chain-flattened, D-R5-13)
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
CREATE REL TABLE ALIAS_OF ( FROM Entity TO Entity, run_id STRING, created_at STRING, algorithm STRING );  -- Task #74
```

**Canonicalization invariants** (Task #74, enforced by `graphdb-kdb verify` Layer 3 / C1–C4):

- **C1** — every `Entity` with `canonical_id IS NOT NULL` has a matching `ALIAS_OF` edge to that canonical_id.
- **C2** — every `ALIAS_OF` edge's source `Entity` has `canonical_id` equal to the edge's destination.
- **C3** — `ALIAS_OF` is acyclic AND **flat** (D-R5-13): every `Entity.canonical_id` points at an `Entity` with `canonical_id IS NULL` — no chains, no cycles.
- **C4** — every `LINKS_TO` edge's destination has `canonical_id IS NULL`: LINKS_TO never points at an alias (D-R5-12; alias→canonical remap happens at Stage [6], before graph_sync).

Aliases are exempt from orphan detection (no `SUPPORTS` edges by OQ-E; canonical-only routing); `_detect_and_mark_orphans` is scoped to `canonical_id IS NULL`.

**Naming history**: `Entity` was originally `Page` (renamed per D-A1 2026-05-14); `ingest_*` fields were originally `compile_*` (renamed per D-A2). Producer payloads (`compile_result.json`) retain the older names — the Obsidian adapter translates. The verifier's `_SOURCE_DIRECT_FIELDS` tuples are the alias bridge: `("compile_state", "ingest_state")` etc.

### 8.3 Pipeline integration — Stage 10 via adapter (D-S0)

`kdb-compile`'s 10-stage pipeline ends with **Stage 10 `graph_sync`** (was Stage 9 pre-#74; canonicalize at Stage [6] renumbered downstream stages):

```
Stages 1–9 (post-#74): scan → validate scan → compile → validate compile_result →
                       reconcile → canonicalize → build source_state →
                       apply pages → persist state

Stage 10 graph_sync (D50: fatal for non-dry-run; revokes D38 non-fatal):
  10a. Archive sidecar: atomic-copy state/{compile_result,last_scan}.json
       → state/runs/<run_id>/{compile_result,last_scan}.json
       (compile_result is the CANONICALIZED version per D-R5-10, so the
        sidecar preserves canonical_meta for D39 replay)
  10b. Live sync: graphdb_kdb.adapters.obsidian_runs.ObsidianRunsAdapter()
       .sync_current_run(cr, scan_dict, run_id)
```

Two architectural properties of the wiring:

1. **`kdb_compile.py` imports ONLY `ObsidianRunsAdapter`** (D-S0). Never `GraphDB`, never `apply_compile_result` directly. The adapter is the single producer→graph entry point — same code path as `graphdb-kdb rebuild` uses.
2. **Sidecar archival runs *before* the live sync.** If the sync fails, the sidecar still exists — so `graphdb-kdb rebuild` is a real recovery path. (Per D50, graph_sync failure is now fatal for non-dry-run compiles since GraphDB is the live ontology authority; D38 non-fatal semantics were revoked for ontology writes.)

**Adapter's canonicalization responsibilities** (Task #74, Phase 3.5 in `graphdb_kdb/ingestor.py`): on top of canonical-entity upsert + LINKS_TO + SUPPORTS, the adapter reads `canonical_meta.aliases_emitted` from the canonicalized compile_result and writes one `Entity` row per alias (`canonical_id` = root canonical slug, `page_type` = `'alias'`) plus one `ALIAS_OF` edge alias→canonical with `algorithm` provenance. Promotion edge case: when a slug previously written as alias appears as canonical, `_upsert_entity` resets `canonical_id = NULL` and drops outgoing `ALIAS_OF` (preserves C1). Re-running the same `canonical_meta` is idempotent (drop-then-create on `ALIAS_OF` keeps the flat invariant — one edge per alias, run_id reflects most recent run; older provenance lives in the per-run sidecar).

### 8.4 Replay / rebuild path (D39 — the independence proof)

`graphdb-kdb rebuild --vault-root <P>` drops all Kuzu tables and replays the eligible subset of `state/runs/*.json` chronologically:

- **Eligibility filter** (D39): `success=true AND dry_run=false AND payload_present`. Payload = per-run sidecar at `state/runs/<run_id>/{compile_result,last_scan}.json`. Adapters declare which producer journal `schema_version` they support (D-S3) — version mismatches return structured skip reasons (`'unsupported_version'`), not silent corruption. The Obsidian adapter declares `supported_journal_versions = ["2.0", "2.1", "2.2"]`: `2.0` = compile runs (pre-cleanup, pre-#74), `2.1` = `kdb-clean` cleanup runs, `2.2` = post-#74 runs carrying `canonical_meta` in the sidecar `compile_result.json`.
- **B-lite split** (D-B1): `rebuilder.py` is producer-agnostic (drop-all + chronological iterate + per-run try/except); the adapter (`adapters/obsidian_runs.py`) supplies discover_runs / is_eligible / load_payload / apply. No producer-specific code in the core.
- **Blast radius v1** (D-S2, L8): whole-DB drop only; producer-scoped rebuild deferred until producer #2 ships. CLI prints a warning before the drop unless `--yes`.
- **Canonicalization replay** (Task #74): rebuild reads `canonical_meta.aliases_emitted` from each post-#74 sidecar and reproduces the exact `Entity.canonical_id` + `ALIAS_OF` edges the original compile produced. No re-execution of the canonicalization algorithm during rebuild — output is replayed from the journal, preserving D-R5-4 purity under replay. Pre-#74 journals (no `canonical_meta`) leave `canonical_id IS NULL` for all entities (matches their original state).
- **Baton-backfill** (one-shot, opt-in via `--backfill-baton`): synthesizes a `RunDescriptor` pointing at `state/{compile_result,last_scan}.json` baton files using `manifest.runs.last_successful_run_id` as the synthetic run_id; sorts before all real runs (`sort_key="0000-pre-63-backfill"`); idempotent — silently skipped if a sidecar already exists at `state/runs/<run_id>/`. The one-time migration entry for the latest pre-#63 run, per #63.0 outcome (d) — the other 9 pre-#63 runs are unrecoverable.

Independence claim: **delete `manifest.json` → GraphDB still queryable; delete `~/Droidoes/GraphDB-KDB/` → manifest still works**. Both are derived from `compile_result`. `graphdb-kdb verify` audits overlap (Layer 1 source-state preflight + Layer 2 replay structural diff + Layer 3 C1–C4 canonicalization invariants); `graphdb-kdb rebuild` regenerates either store from the post-#63 run history. `graphdb-kdb snapshot` (#63.9) writes a JSONL+manifest+schema export under `state/graph-snapshots/<run_id>/` — Task #74 bumped `snapshot_format_version` to `2` to include per-Entity `canonical_id` and an `alias_of.jsonl` file with full ALIAS_OF provenance, so Tier-2 OneDrive recovery preserves alias state.

**Maintenance — `kdb-clean orphans`:** `--apply` archives orphan pages, removes
them from `manifest.json`, and emits a replayable `cleanup` run journal +
`retraction.json` sidecar into `state/runs/`. `graphdb-kdb rebuild` replays the
cleanup event chronologically, so reaped pages stay retracted (Task #68).

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
| [`docs/task74-canonicalization-blueprint.md`](task74-canonicalization-blueprint.md) | Stage [6] canonicalize blueprint: locked decisions D-R5-1..D-R5-13; algorithm (string-norm → ledger → embedding v2 → llm-judge v2); schema delta (`Entity.canonical_id`, `ALIAS_OF`); C1–C4 verify invariants; rebuild semantics |
| [`docs/task75-predeclared-eval-criteria-blueprint.md`](task75-predeclared-eval-criteria-blueprint.md) | **Step-3 query-time eval contract (Task #75, blueprint v2 — Codex + Gemini review applied).** Predeclares the operations roster (PPR + community routing + subgraph extraction V1; typed traversal V0; shortest-path V0 / scored-multi-hop V2), per-op pass/fail/quantitative-gate criteria, hedge-watch rules HW-1..HW-7 (symptom → §8.3 hedge), step-3 preconditions (Task #76 `domain` field gates the community/domain-ratio acceptance only; Task #77 probe set), and OQ-1..OQ-9. Satisfies Round 5 §8.5/§8.6 path-forward precondition (Codex Q6 — avoid "implementation momentum disguised as empiricism"). Pattern mirrors Task #19 (compile-side KPI predeclaration → §7) extended to query-time. |

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

### 8.7 Graph context loader — retrieval tiers & cold-start widening

`graph_context_loader.py` builds a source-specific `ContextSnapshot` from the graph. It replaces `context_loader.py`'s manifest-based approach (selected via `KDB_CONTEXT_SOURCE=graphdb` in planner). The loader assigns entities to **retrieval tiers** — relevance-source categories, not graph-distance measures:

| Tier | Name | Score | Semantics |
|------|------|-------|-----------|
| T1 | Provenance tier | 3 | Entities directly supported by the current source via `(:Source)-[:SUPPORTS]->(:Entity)`. Strongest signal: "this source already owns/contributed to these entities." |
| T2 | Lexical-match tier | 2 | Active entities matched from source text. Slug-in-text (whole-word); on cold-start, widened to slug-or-title-in-text (#71). Seeds discovered from lexical evidence rather than provenance. |
| T3 | Neighborhood-expansion tier | 1 | Entities connected to the seed set (T1 ∪ T2) through `[:LINKS_TO]`. 1-hop by default; conditional 2-hop on cold-start when seed count is thin. |

Key distinction: **T1/T2 are seed-selection tiers** (what we search for). **T3 is graph-expansion** (how far we walk from seeds). Only T3 maps to "degree of separation"; T1 and T2 are relevance-source categories, not distances.

Tie-break within the same tier: PageRank descending, then slug ascending.

#### Cold-start detection & widening (D48, Task #71)

A source is cold-start when `len(t1_slugs) == 0` — it has no `SUPPORTS` edges (never compiled before). Without widening, T2 slug-in-text alone is too narrow for natural-language prose (hyphenated slugs rarely appear verbatim).

**Primary fix — title-in-text matching (T2 widening):**
When cold-start fires, T2 additionally matches entity titles as exact phrases in source text. Guardrail: a title is eligible iff `len(normalized) > 3` AND (has 2+ alphanumeric tokens OR is a single token with length >= 6). Filters short generics ("Risk", "Value", "Moat") while keeping useful concepts ("Margin of Safety", "Legalism", "Confucianism").

**Secondary amplifier — conditional 2-hop T3:**
When cold-start AND `|widened_T2| < 5` (the `_MIN_SEED_THRESHOLD`), T3 expands from 1-hop to 2-hop. Compensates for genuinely thin vocabulary overlap between source and graph.

**What does NOT change on cold-start:** tier scores (3/2/1), PageRank tie-break, `page_cap`, `ContextSnapshot` shape.

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
| D41 | 2026-05-15 (Task #64) | **Recompile supersession.** A source's recompile removes that source's support from prior pages the new run no longer emits. The graph ingestor already implements this; D41 binds the manifest path to parity. See `docs/task64-recompile-supersession-blueprint.md`. | Graph ingestor's `_replace_supports_for_source` is the reference design (Codex CRITICAL #2 fix in #63). Manifest-only union (`_ensure_page` always unions) diverges from graph truth after any recompile that emits fewer pages. D41 closes that gap without touching `graphdb_kdb`. |
| D42 | 2026-05-15 (Task #64) | **`source_refs` is current-state provenance, not an eternal log.** Stripped on supersession alongside `supports_page_existence`. History lives in run journals, `sources[].previous_versions`, and `orphans[].previous_supporting_sources`. See `docs/task64-recompile-supersession-blueprint.md`. | Keeping stale `source_refs` after supersession creates false provenance claims (a source "supports" a page it no longer emits). Run journals and `previous_supporting_sources` preserve history without polluting current-state. |
| D43 | 2026-05-15 (Task #64) | **Status-aware `source_refs` invariant.** `active` page → `source_refs` non-empty. `orphan_candidate` page → may be empty (provenance preserved in `orphans[].previous_supporting_sources`). Also fixes the pre-existing DELETED-path invariant crash. See `docs/task64-recompile-supersession-blueprint.md`. | Prior invariant rejected empty `source_refs` for all pages without a status filter — supersession legitimately empties them for orphan candidates. DELETED path had the same latent crash (never triggered because no source has been deleted in practice). Status-aware check makes the invariant correct for all reachable states. |
| D44 | 2026-05-15 (Task #64) | **D12 preserved.** Supersession flags pages `orphan_candidate`; never deletes page records or files. `delete_policy` stays `mark_orphan_candidate`. See `docs/task64-recompile-supersession-blueprint.md`. | D12 is the non-destructive safety invariant: orphan candidacy is a flag, not a deletion. #64 adds a new trigger (recompile supersession) but the outcome is identical to the existing orphan path — page stays in manifest and on disk, human reviews. |
| D45 | 2026-05-15 (Task #65) | **`pairing_type_mismatch` is reconcilable; `pages[].page_type` is authoritative.** A new unconditional `reconcile_slug_lists()` rebuilds `concept_slugs`/`article_slugs` from `pages[]` in `compile_one` (mirroring Task #57's body-wins `reconcile_body_links`). The validator demotes `pairing_type_mismatch` `gate`→`measure` and drops it from `HARD_ZERO_FINDING_TYPES`. See `docs/task65-pairing-reconcilable-blueprint.md`. | `concept_slugs`/`article_slugs` are denormalized indexes of `pages[].page_type`; the page object (title+body-bearing) is the deliberate classification. Hard-gating a slug-list mis-file discarded whole good compiles (EP1: 28 valid pages lost over 2 mis-filed slugs). Rebuilding from `pages[]` makes the pairing-inconsistency class structurally impossible. Removing `pairing_type_mismatch` from `HARD_ZERO_FINDING_TYPES` redefines the benchmark hard-zero pass-rate measure — a post-#65 re-fire sets the new baseline. |
| D46 | 2026-05-16 (Task #66) | **Compile eligibility is `current_hash != last_compiled_hash`.** A new source field `last_compiled_hash` records the hash last *successfully processed*; it advances **only on successful processing of the current content** — `apply_compile_result` for LLM-compiled text sources, `apply_scan_reconciliation` for metadata-only binaries (Q6) — never by the scan merely *seeing* a changed text source, never for an error-marked / missing source. The scan carries the prior value onto every `ScanEntry` as `compiled_hash` (required-but-nullable); `to_compile`/`to_skip` partition purely on the hash comparison, never on `action`. The `error_retry` side-channel is removed; `compile_state` stays informational but no longer affects eligibility. Force-recompile = a real source-content change; no manifest flag, no `--force`; content hash only, never mtime. See `docs/task66-compile-trigger-model-blueprint.md`. | `manifest.hash` advances during the *scan* (it means "last hash seen"), so reading it back as "last hash compiled" conflated two facts: a failed compile left `hash` already advanced, so the file read UNCHANGED next scan despite never compiling. `error_retry` was a patch over that conflation — and it made force-recompile possible by hand-editing `compile_state: "error"` into the manifest. Splitting the two hashes makes the trigger one honest comparison and removes the manifest-editable force path. |
| D47 | 2026-05-16 (Task #70) | **Superseded by D49.** Originally held manifest as default context source pending cold-start fix. Cold-start resolved (#71); D49 removed manifest-as-context entirely. | Historical: prevented premature default flip while graph context was weaker on cold-start. Now moot — graph is the only context authority. |
| D48 | 2026-05-17 (Task #71) | **Graph context loader must be self-sufficient — no manifest fallback path.** Cold-start is resolved by widening graph-native matching (title phrase + extended neighborhood hops), never by delegating to manifest. | Manifest is being phased out of the context-generation pipeline. Any fallback would be architectural regression. Rejected: (b) min-context fallback to manifest; (c) manifest-for-first-compile / graph-for-recompile split. |
| D49 | 2026-05-17 (Task #70 closure) | **GraphDB is the only supported EXISTING CONTEXT authority.** `manifest.json` must not be used for context generation. `KDB_CONTEXT_SOURCE` env var removed; planner always uses `graph_context_loader`. If GraphDB is missing/empty/corrupt, context planning fails loud → operator runs `graphdb-kdb rebuild`. `context_loader.py` retained as legacy reference only (not operator-facing). | Manifest is the wrong substrate for ontology/context — a flat index cannot encode graph relationships. Keeping it as rollback implies it is an acceptable competing source of truth; it is not. Graph outperforms manifest on both cold-start (17–23 vs 0–8 pages) and steady-state. Recovery path is rebuild from run journals (D39), not fallback to a weaker substrate. |
| D50 | 2026-05-17 (Task #73) | **`manifest.json` is no longer an ontology store.** GraphDB owns Entity, LINKS_TO, SUPPORTS, orphan status, graph topology. Manifest becomes source-file metadata ledger only (hashes, compile state, timestamps). Stage 9 `graph_sync` becomes fatal for non-dry-run compiles (revokes D38 non-fatal semantics for ontology writes). No piecemeal removal — pages, outgoing_links, source_refs, orphan status stripped together once consumers migrate. | Dual-write is architecturally confusing (two "sources of truth" invite drift) and blocks manifest slimming. Piecemeal removal (e.g., outgoing_links only) creates half-stale state — worse than either extreme. GraphDB is deterministically regenerable from run journals (D39); manifest cannot serve as fallback once it stops tracking ontology. See `docs/task73-manifest-ontology-removal-blueprint.md`. |
| D51 | 2026-05-17 (Task #73 closure) | **GraphDB is the live ontology authority; `state/runs/` sidecars are reconstruction material, not the primary data flow.** Layer model: `raw/` = source corpus; `GraphDB-KDB/` = live ontology authority (primary); `state/runs/` = audit log + reconstruction material (backup); `source_state.json` = source-file lifecycle metadata; `wiki/` = markdown rendering. Primary path: `kdb-compile → Stage 9 immediate GraphDB update` — runs are not in this hot path. Rebuild/verify use sidecars as backup to prove or restore consistency. `source_state` must not carry replay-selection pointers — replay eligibility belongs to the adapter/rebuilder, not the source metadata ledger. | Rejected: (a) event-sourcing framing where runs/ IS the ontology authority and GraphDB is "just a projection" — technically correct but cognitively misleading (implies the normal path goes through runs/; it doesn't). (b) `ontology_sources/*.json` per-source durable layer — redundant with sidecars, adds a third consistency surface, re-introduces coupling removed by D50. The current architecture already matches the compiler mental model (source → distill → update GraphDB); the naming just needed to make that explicit. |
| D52 | 2026-05-21 (Task #74 closure) | **Canonicalization is a top-level compile stage (new Stage [6]), not a side-effect of patch_applier or graph_sync.** Both downstream renderings — `patch_applier` (wiki .md files) and `graph_sync` (live GraphDB) — consume the canonicalized `compile_result`, so wiki and graph agree on entity names at the rendering layer. Algorithmic failure is fatal (D-R5-9; pipeline halts before patch_applier writes anything). Run journal `schema_version` bumps `2.1 → 2.2` to carry `canonical_meta` for D39 replay (D-R5-7). GraphDB gains `Entity.canonical_id` + `ALIAS_OF` rel table; alias entities are `canonical_id IS NOT NULL` + chain-flattened to root (D-R5-13). C1–C4 invariants are checkable from the live graph alone (no sidecar reads). Full locked-decision register (D-R5-1..D-R5-13) and algorithm details live in `docs/task74-canonicalization-blueprint.md`. | If canonicalization ran only inside `graph_sync`, the vault would show `[[AAPL.md]]` while the graph stored `apple-inc` — a divergence the human sees in Obsidian. Single source of canonical truth, consumed identically by both renderings, is the only way wiki ≡ graph at the naming layer. v1 implementation = string-norm + manual ledger (`state/canonicalization/aliases.json`); embedding-similarity + LLM-judge layers reserved for v2 (L9 in blueprint §14). |
| D-A1 | 2026-05-14 (Round 1 Codex) | Schema rename: `Page → Entity` node-table label. | `Node` would collide with Kuzu's NODE keyword + universal graph-theory term. `Entity` signals abstract identity. Free upgrade while schema is empty/small. |
| D-A2 | 2026-05-14 (Round 1 Codex) | Source field renames: `compile_state → ingest_state`, `compile_count → ingest_count`, `last_compiled_at → last_ingested_at`. Page enum values (page_type/status/confidence) retained — *values* are Obsidian-flavored; renaming names without revisiting values is cosmetic. | Pipeline-specific field NAMES become pipeline-neutral now. Pipeline-specific VALUES wait for producer #2 to inform the right abstraction. Verifier carries an alias map bridging the manifest side (still `compile_*`) and graph side. |
| D-B1 | 2026-05-14 (Round 1 Codex) | Rebuilder is **B-lite (adapter split)**: thin generic core in `graphdb_kdb/rebuilder.py` (drop+recreate, chronological iter, error reporting) + producer-specific logic in `graphdb_kdb/adapters/obsidian_runs.py`. Rule: `graphdb_kdb/` MUST NOT `import kdb_compiler.*`. Public function name `rebuild_from_obsidian_runs(...)`. | Pure-C (core imports producer types) would silently weaken D34 independence. B-lite preserves it by structure, not convention. Cost: ≤200 LOC adapter; verified by grep invariant. |
| D-S0 | 2026-05-14 (Round 2 Codex) | **Stage 9 routes through the Obsidian adapter**, not direct core call. `kdb_compile.py` Stage 9 calls `graphdb_kdb.adapters.obsidian_runs.sync_current_run(cr, scan, run_id)`. Single producer→graph entry point for both live sync and replay. | Makes Doc C's "producer never calls core directly" rule literal, not aspirational. Single code path = one place to debug/test/evolve. Closes OQ-E9 in extraction roadmap. |
| D-S1 | 2026-05-14 (Round 2 Codex) | **Multi-producer entity-id namespacing**: Obsidian grandfathered as bare slugs (implicit `obsidian:` namespace); all future producers MUST use explicit `<source_type>:<entity_id>` prefix. Adapter declares `entity_id_namespace: ClassVar[str \| None]`. | Retroactive migration of existing entities is destructive without operational benefit; grandfathering is cheaper. Cross-producer queries filter via `Source.source_type`, not slug prefix parsing. |
| D-S2 | 2026-05-14 (Round 2 Codex) | **Rebuild blast radius v1**: `graphdb-kdb rebuild` always drops the whole DB regardless of `--producer` flag. Producer-scoped rebuild deferred until producer #2 ships AND the team agrees the scoped semantics (tracked as L8 + blueprint TR-3). CLI prints warning before drop. | At v1 single-producer the simple correct semantics. Deferring lets the right scoped-rebuild rules be informed by real co-tenancy needs. |
| D-S3 | 2026-05-14 (Round 2 Codex) | Adapter declares `supported_journal_versions: ClassVar[list[str]]`. Mismatched versions return structured skip reason `'unsupported_version'` rather than silent corruption. | Producer journals evolve (Obsidian is at `2.0` today). Versioning discipline must be in place before Stage 1 of package extraction, not Stage 4. |
| D-S4 | 2026-05-14 (#63.7-A1 finding) | Phase 1 source-refresh in `graphdb_kdb/ingestor.py` does NOT bump `last_run_id` — `last_run_id` is bumped only by Phase 3 (`_update_source_ingest_state`) on actual ingest. `ON CREATE` seeds it as `''`. | Manifest's `last_run_id` is bumped only on compile events, never on bare scan. Graph must mirror this to produce zero `attribute_mismatch` divergence for sources that aren't touched in a given run. Without this, every scan-only run causes spurious drift. Discovered live during A1 inspection. |
| D-S5 | 2026-05-14 (#63.7-A2 finding) | Test isolation via autouse `conftest.py` fixture at `kdb_compiler/tests/conftest.py`: `monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))`. Every test in the package gets a per-test graph directory. | Stage 9 (added by #63.7-pre) routes through `ObsidianRunsAdapter().sync_current_run(...)` which resolves `KDB_GRAPH_PATH` to the live `~/Droidoes/GraphDB-KDB`. Without isolation, 33 tests in `test_kdb_compile.py` that exercise the full `compile(...)` pipeline silently write synthetic fixtures (`paper.md`, `mencius`, etc.) into the production graph. Discovered live during A2 inspection. |
| D-S6 | 2026-05-14 (Task B from #63.7) | `kdb-compile --model <id>` accepts an id from `kdb_benchmark/models.json` registry (default: `gemini-3.1-flash-lite`). Inline registry loader avoids `kdb_benchmark` import (would create a cycle: `kdb_benchmark.runner` already imports `kdb_compiler.compile_one`). Both tools read the same `models.json`. Fail-fast on unknown id (prints active-model list) or `dropped: true` entries (prints `dropped_reason`). `compiler.run_compile()` extended to accept `use_completion_tokens` + `extra_body` provider knobs (previously only `compile_one` accepted them; `kdb_benchmark.runner` bypassed `run_compile`). | Same registry = same fail-fast behavior across both tools. Provider-specific knobs (e.g., gpt-5+ `use_completion_tokens`) reach the live LLM call from the production CLI path, not just the benchmark path. Validated live across 3 providers (anthropic/haiku-4.5, gemini/gemini-3.1-flash-lite, alibaba/deepseek-v4-flash) plus a graceful-failure scenario. |

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

### M3 — GraphDB-KDB Layer (#63) ✅ DONE — sub-tasks #63.0 through #63.9
Task #63 — refoundation as raw-text → knowledge-graph compiler. Supersedes #26 + #27. See §8.
- **Architecture deliberation:** D32–D40 locked through 3 rounds of Codex review. D-A1/A2/B1/S0–S3 locked through 3 more rounds during Phase 3 implementation. D-S4/S5/S6 locked through #63.7 live validation (A1→A4 on real vault). Snapshot artifact design (#63.9) Codex-reviewed in 1 round; upgraded "JSONL dump" → "self-verifying JSONL + manifest + schema evidence" pre-implementation.
- **Companion docs:** blueprint, paradigm record, producer contract, extraction roadmap, manifest succession arc, Phase 3 implementation blueprint, snapshot Codex prompt (see §8.5).
- **Sub-tasks shipped:** #63.0 replay-contract verification; #63.1 schema + skeleton; #63.2 ingestion; #63.3 read query API; #63.4 hybrid analytics; #63.5 verifier; #63.5b rename pass (Page→Entity, compile_*→ingest_*); #63.6 B-lite rebuilder + Obsidian adapter; #63.7-pre Stage 9 wiring via adapter + sidecar archival; #63.7 live integration validation (4 scenarios × 3 providers); #63.8 docs (this section); #63.9 snapshot/export — JSONL+manifest+schema.cypher with per-file sha256 row counts; CLI subcommand `graphdb-kdb snapshot`; `latest.json` pointer sidecar.
- **#63.7 live validation arc (2026-05-14):** A1 no-op scan → Stage 9 archives sidecar, 0 entities upserted; A2 haiku-4.5 recompile of EP1 → 1 page (summary only); A3 gemini-3.1-flash-lite recompile of Howard-Marks → 7 pages + 10 edges (new default validated); A4 deepseek-v4-flash recompile of Buffett → JSON gate fail, D38 non-fatal contract held (graph not corrupted). Surfaced bugs fixed inline: D-S4 (`last_run_id` Phase 1 semantic), D-S5 (`KDB_GRAPH_PATH` test isolation). New feature: D-S6 (`--model` flag with shared registry). Deferred follow-ups: `raw_response_text=None` capture bug in alibaba extract-failure path (separate from #63.7 scope); deepseek-v4-flash single-trial regression observation parked for ~2026-05-18 retest.
- **3-tier recovery story now complete:** (1) Kuzu corrupted → `graphdb-kdb rebuild` from journals; (2) journals + Kuzu both lost → restore from snapshot (load-snapshot is a future v2 — write-only is the #63.9 scope cut); (3) all three lost → re-run `kdb-compile` on the live vault.
- **Test surface:** 106 graphdb_kdb tests (96 pre-#63.9 + 10 snapshot tests) + 6 Stage-9 integration tests in kdb_compiler/tests/ (550 total kdb-relevant tests).

### M4 — Canonicalization layer (#74) ✅ DONE — sub-tasks #74.1 through #74.8
Task #74 — Stage [6] canonicalize lands as a top-level compile stage between reconcile and build_source_state; wiki and graph see the same canonical names. Locked decisions D-R5-1..D-R5-13 + D52. See §5 (pipeline), §8.2 (schema delta), §8.3 (adapter alias-write pass), §8.4 (rebuild + snapshot v2), and the full blueprint at `docs/task74-canonicalization-blueprint.md`.
- **Sub-tasks shipped:** #74.1 schema delta (Entity.canonical_id + ALIAS_OF + migration); #74.2 `aliases.json` ledger loader; #74.3 `canonicalize.run()` algorithm; #74.4 `kdb_compile.py` Stage [6] wiring + journal `2.1 → 2.2` bump + `compile_result.schema.json` whitelist; #74.5 adapter Phase 3.5 — writes alias Entity + ALIAS_OF + `canonical_id`; #74.6 `graphdb-kdb verify` Layer 3 (C1–C4 invariants on the live graph); #74.7 snapshot format v2 + canonical_meta replay tests + back-compat tests; #74.8 docs (this section).
- **Round 5 external review:** Antigravity + Codex parallel reviews on the blueprint (see `docs/round5-external-review-{antigravity,codex,prompt}.md`); locked OQ-E (direct-to-canonical SUPPORTS), OQ-F (canonical-wins + longest + UNION merge), OQ-G (JSON ledger format) before implementation.
- **Test surface delta:** +14 alias-ingestion tests + 11 canonicalization-invariant tests + 3 snapshot-v2 tests + 3 rebuilder canonical_meta tests + 1 schema back-compat test.
- **Half-wire closure:** between #74.4 and #74.5, the adapter accepted v2.2 journals but ignored `canonical_meta`; #74.5 closed this. Wiki ≡ graph at the naming layer (verified by Layer 3 invariants).

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
