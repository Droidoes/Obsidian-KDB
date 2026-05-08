# Project Task Ledger

Canonical, version-controlled index of every numbered project task. This is the
**source of truth** for task numbering and status — daily notes link into it,
memory notes reference it by number, session TODO trackers are ephemeral and
must not be used as the authoritative list.

## Conventions

- **Stable IDs.** Once assigned, a task's number never changes and is never reused.
- **Status values.** `open` (not started) · `in-progress` (actively being worked) · `closed` (landed).
- **Closure proof.** Every closed task links to the commit SHA, doc, or memory note that carries the resolution.
- **Assignment.** New tasks take the next free ID. Gaps in the numbering are preserved — don't backfill.
- **Decomposition.** When a task is split, the parent stays at `in-progress` and its sub-tasks get their own IDs.
- **Separate tracks.** Architectural open questions live in `docs/CODEBASE_OVERVIEW.md` as `Open-1..Open-8`; they are NOT task-numbered here.

---

## Open / In-Progress

| #  | Status        | Title                                                         | Notes                                                                                         |
|----|---------------|---------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| 2  | open          | Scalability discussion                                        | Thinking-work; defer until benchmark baseline establishes real cost/latency numbers           |
| 5  | in-progress   | LLM benchmarking                                              | Parent task; decomposed into #16–#23. Hook already scaffolded at stage-4 `response_score` slot |
| 16 | open          | Stand up durable task ledger (`docs/TASKS.md`)                | **This doc.** Root-cause fix for losing track of numbered tasks between sessions              |
| 19 | in-progress   | Define KPIs + gate thresholds for KDB benchmark               | **Phase 3 + Round 4 closed 2026-05-06** — code-ready scorer spec landed in `docs/task19-kpi-design.md` § *Phase 3 — Detailed Spec* + § *Round 4 Corrections* (Codex hostile review take 2: 8 must-fixes + 4 design-calls + 4 cheap-wins all addressed). Spec covers: function signatures (score_run takes `model_id`; M6/M7 raw rates plus separate `m6_borda`/`m7_borda` fields), dataclasses, per-measure formulas with isinstance guards, model-vs-corpus-controlled zero-denom split, average-rank tie handling with all-equal policy, retry_load clamp, S0 renamed `pipeline_success_rate`. Housekeeping: `MAX_RETRIES=2` exported; `check_compiled_source` + `HARD_ZERO_FINDING_TYPES` exposed; Round 4 telemetry fix — `build_resp_stats` persists requested provider/model on pre-response failures so scorer's filter contract holds. Phase 2 + Round 3 closed 2026-05-04 (weights locked S0=20/M1=20/M2=5/M3=5/M4=15/M5=5/M6=15/M7=15). #28 / #29 closed 2026-05-05 (`0bcc2b6` / `26b345a`). Tests at 462 passed / 1 skipped (+7 new from Round 4). **Only Phase 5 remains** — promote architecture into `docs/CODEBASE_OVERVIEW.md` once scorer-impl future task lands working code |
| 20 | open          | Decide ground-truth source                                    | GT-A/B/C/D/E; recommendation is GT-D as v1 + GT-E as v2                                       |
| 21 | open          | Port/adapt `models.json` registry                             | Lift the 21-model shape from `youtube-comment-chat/src/eval/models.json`                      |
| 23 | open          | Document benchmark architecture in `CODEBASE_OVERVIEW.md`     | North Star first per CLAUDE.md; no implementation before docs land                            |
| 25 | open          | Capture exception type+message in resp-stats on pre-response failures | Small patch; makes failure records self-explanatory. From 2026-04-19                  |
| 26 | open          | Systematic review of EXISTING CONTEXT list design             | Surfaced from Task #19 Phase 2 dialogue (2026-04-30): rationale, manifest source data, step-by-step algorithm, objective, effectiveness measurement, industry-standard alignment. See `docs/task26-existing-context-design.md` |
| 27 | open          | Manifest scalability assessment + industry-standard review    | Surfaced from Task #19 Phase 2 dialogue (2026-04-30): is single-JSON `manifest.json` scalable to 10K+ pages? Are we following knowledge-graph / metadata-store best practices? |
| 33 | open          | Benchmark orchestrator (future)                               | Surfaced 2026-05-06. v1: `kdb-benchmark` CLI accepts `--models a,b,c`, iterates sequentially, runs scorer + scorecard at end (single-process chain). Future v2: parallel execution across models, resume after partial failure, cross-run scorecard generation (e.g., score yesterday's runs + today's new run). Logged so we don't forget — not blocking v1 |
| 34 | in-progress   | Parameterize `source_id` prefix for benchmark schema validation | Surfaced 2026-05-07 by smoke-test fire. Smoke run failed S0/M4 + masked M1 because `compiled_source_response.schema.json` requires `source_id` to match `^KDB/raw/.+`, but benchmark sources don't live there. Fix: `validate_compiled_source_response.validate(payload, *, source_id_prefix="KDB/raw")` patches the schema's `$defs.sourceId.pattern` to `^<prefix>/.+`. `compile_one` accepts the same kwarg (default `KDB/raw` — production unchanged). Benchmark `runner.run_benchmark` derives the prefix from `sources_dir` (POSIX-normalized, leading/trailing `/` stripped) and constructs each source_id as `<prefix>/<filename>`. Tests cover override-accept, override-reject, regex-escape, and runner prefix-derivation. Re-fire smoke after merge to recover S0/M4/M1 signal |
| 35 | in-progress   | `kdb-benchmark --verbose` per-measure scoring trace            | Surfaced 2026-05-07 alongside #34. After #34 fixed the wiring, #35 makes the scoring derivation legible. **v1**: `score_run`/`score_runs` accept `verbose: bool`; lines print mid-flight. **v2 (2026-05-07)**: sink-based — internal API is `trace_sink: list[str] \| None`; CLI buffers all trace lines and prints them AFTER the scorecard table behind a `===` separator (so the table stays at top of screen). Per-source S0 breakdown always emitted (not just on failure), exposes full gate chain (parse_ok → schema_ok → parsed_json shape → hard-zero findings) plus rich finding `.detail` strings via new public helper `check_compiled_source_findings()` in `validate_compile_result.py`. Other measures retain inline evidence (M1 target_set size, M6/M7 derivation, Borda raw→ranked) |
| —  | open          | Resolve `Open-1..Open-8` in `docs/CODEBASE_OVERVIEW.md`       | Tracked there, not here. Target: close before end of M2                                       |

---

## Closed

| #  | Title                                                       | Resolution                                                                                                                          |
|----|-------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| 1  | CLI progress banners (7-stage → 8-stage)                    | `b377bfc` original 7-stage; `88ee8fc` promoted to 8-stage with reconcile banner                                                     |
| 3  | Wiki type & graph case study                                | `docs/wiki.md` — three-type ontology rationale, concept lifecycle, graph topology intuition                                         |
| 4  | Prompt & JSON output structure                              | Direction A via Task #11 synthesis + 2026-04-21 Option A refinements; Direction B's goal met by validator+reconciler (auto-heal). See memory `project_task4_prompt_schema_directions.md` |
| 6  | `patch_applier` empty-plan crash                            | `92aa778` code fix (both cases closed by single Option-1 change); `7e28297` ticket closure. See `docs/bug-patch-applier-empty-plan.md` |
| 7  | Drop `index.md` (D23)                                       | `b708d63`. Obsidian file explorer is the TOC; `manifest.json` is the machine index                                                  |
| 8  | Drop `log.md` (D24)                                         | `48f1666`. `state/runs/<run_id>.json` is the authoritative per-run journal                                                          |
| 9  | 1-sentence ask for compiler prompt                          | Locked in `docs/session-handoff-2026-04-20.md`                                                                                      |
| 10 | 5-bullet high-level spec (v3)                               | Locked in `docs/session-handoff-2026-04-20.md`                                                                                      |
| 11 | Expand 5-bullet spec into detailed behavioral sections      | Completed as part of the Task #12–#15 multi-model synthesis workflow                                                                |
| 12 | Claude draft of compiler system prompt                      | Part of the parallel drafting pool → synthesis                                                                                      |
| 13 | Grok draft of compiler system prompt                        | Part of the parallel drafting pool → synthesis                                                                                      |
| 14 | Gemini draft of compiler system prompt                      | Part of the parallel drafting pool → synthesis                                                                                      |
| 15 | QWEN + GPT5.4 drafts + synthesis + install + rename         | Synthesized prompt installed to `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` (renamed from `CLAUDE.md`, commit `1312757`). See memory `project_task11_completed.md` |
| 17 | Terminology sweep: aspirational "eval" → mechanical names   | `b7ea53a`. Code/tests/fixtures/CLI/blueprint/memory all renamed: `eval_replay → response_replay`, `kdb-eval → kdb-replay`, `KDB_EVAL_CAPTURE_FULL → KDB_RESP_CAPTURE_FULL`, `llm_eval/ → llm_resp/`, `EvalRecord → RespStatsRecord`. Reserves "benchmark" for Task #5 cross-model work |
| 18 | Decide benchmark directory structure (D2)                   | `5825d0f`. D2 picked: top-level `kdb_benchmark/` engine package + top-level `benchmark/` data dir (sources/truth/scores tracked; runs/inspect gitignored). One-way import boundary. 9 unit tests green |
| 29 | `RespStatsRecord` telemetry plumbing for benchmark scorer   | `26b345a`. `RespStatsRecord` gained `stop_reason`/`token_overrun`/`source_words`. `ModelEntry` gained `price_in`/`price_out` (USD per 1M tokens; `0.0` for local). `cost_usd` intentionally NOT persisted — scorer derives from `(input_tokens, output_tokens) × registry` at score time, respecting the `kdb_compiler -/-> kdb_benchmark` one-way import boundary from #18. +10 tests. Phase 3 gate for #19 |
| 28 | M5 (`body_link_syntax_match`) implementation — symmetric Jaccard | `0bcc2b6`. Added `body_link_check(payload) -> (intersection, union)` to `validate_compiled_source_response` (~58 LOC w/ docstrings). Per-page set semantics: `declared = set(outgoing_links)`, `body = slugs in [[…]] tokens` after stripping fenced/inline code spans (negative-lookbehind handles `\`-escapes). Returns `Σ\|D_p ∩ B_p\|`, `Σ\|D_p ∪ B_p\|` summed across pages. Wired into `build_resp_stats` → persisted on `RespStatsRecord.body_link_intersection` / `body_link_union`; both default to 0 on parse failure. Scorer derives Jaccard ratio at score time. +16 tests. Last Phase 3 gate for #19 |
| 32 | Benchmark corpus v1 (`benchmark/sources/`)                  | `d31d054`. Curated 5 license-clean public sources (~28.6K words, ~250 KB total): (1) Attention Is All You Need (arXiv 1706.03762v7) — license caveat in meta.yaml for personal-use repo; (2) Distill "Why Momentum Really Works" (CC-BY-4.0); (3) The Twelve-Factor App (CC-BY-4.0); (4) Distill "Research Debt" (CC-BY-4.0); (5) Rust Book Ch. 4 — Understanding Ownership (MIT/Apache-2.0). Each source paired with `.meta.yaml` carrying source URL, version, license, attribution, conversion command, sha256 checksum, fetched_at, word/char counts. HTML→MD via `html2text` (pandoc not installed); math notation doubles cosmetically in Attention + Momentum but doesn't affect Borda-ranked KPIs. Estimated cost ~$1.50 per scorecard for haiku-4.5 + sonnet-4.6 |
| 22 | Design KDB scorecard format                                 | `2780f63`. `kdb_benchmark/scorecard.py` — `build_scorecard(runs)` orders post-Borda RunScores by final_score desc, stamps a scorecard_id (local-ISO-timestamp + candidate set), embeds the Round 4 DC4 disclaimer. `render_terminal()` outputs rank \| model_id \| S0 \| M1..M5 \| M6_b \| M7_b \| FINAL \| RAN_AT plus raw-rates inspection footer plus diagnostics plus disclaimer. `write_scorecard()` writes JSON to `benchmark/scores/<scorecard_id>.json`. 8 unit tests |
| 30 | Benchmark runner (`kdb_benchmark/runner.py`)                | `2780f63`. Isolation-contract orchestrator. Invokes `compile_one` directly (NOT the production `kdb-compile` pipeline — structurally cannot touch the user's vault); empty `ContextSnapshot` per source for cold-compilation determinism; sets `KDB_RESP_STATS_CAPTURE_FULL=1` (§3 mandate); writes `RespStatsRecord` JSONs under `<runs_root>/<run_id>/state/llm_resp/`. run_id format `<model_id>-<local-ISO-timestamp_TZ>`. Snapshots system prompt into `<run_id>/vault/KDB/` for re-runnability. 9 unit tests covering registry lookup, .meta.yaml skipping, capture-full env, system-prompt copy, isolated state_root |
| 31 | Benchmark scorer (`kdb_benchmark/scorer.py`)                | `b16525d`. Implements `docs/task19-kpi-design.md` § Phase 3 § 5–§ 9: `MeasureScore` + `RunScore` dataclasses; per-measure functions (S0 `pipeline_success_rate`, S1/S2/S3 diagnostics, M1 link_target_resolution, M2/M3 concept/article Jaccard, M4 semantic_pass_rate, M5 body-link Jaccard, M6/M7 cost/latency per 1K source-words, 3 diagnostics); `borda_normalize` (average-rank with all-equal policy + drop-None-rate); `final_score` (weighted sum + pro-rata redistribution); `score_run(state_root, run_id, model_id)` + `score_runs(runs)`. Edge cases per § 4 (parse-fail M6/M7 inclusion via source_words>0; non-dict parsed_json guards; non-list slug coercion; model-vs-corpus zero-denom split; retry_load clamp; M1 list semantics). 57 unit tests via TDD |

---

## Unused IDs

`#24` — historical gap (originally reserved on 2026-04-21 but was bypassed when #25 was assigned next). Per the no-backfill rule, this gap stays. Do not assign #24 to any new task.

---

## How to update this file

- **Add a task**: append to the `Open / In-Progress` table with the next free ID.
- **Close a task**: move the row to the `Closed` table, replace the `Status` column with the `Resolution` column content (commit SHA / doc path / memory note name).
- **Decompose a task**: flip parent to `in-progress`, add sub-tasks with new IDs, update parent's "Notes" column to list them.
- **Never** renumber or reuse IDs.
- **Always** commit changes to this file alongside the work that caused them, so git history shows the ledger evolving in lockstep with the project.
