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
| 19 | in-progress   | Define KPIs + gate thresholds for KDB benchmark               | Phase 2 + Round 3 (Codex-driven) closed 2026-05-04; weights locked S0=20/M1=20/M2=5/M3=5/M4=15/M5=5/M6=15/M7=15. Phase 3 gated on **#28** (M5 impl); #29 closed at `26b345a`. See `docs/task19-kpi-design.md`, companion `task19-kpi-design-codex-feedback-take-1.md` |
| 20 | open          | Decide ground-truth source                                    | GT-A/B/C/D/E; recommendation is GT-D as v1 + GT-E as v2                                       |
| 21 | open          | Port/adapt `models.json` registry                             | Lift the 21-model shape from `youtube-comment-chat/src/eval/models.json`                      |
| 22 | open          | Design KDB scorecard format                                   | Mirror `benchmark/scores/in-out-list.txt`; depends on #19 + #20                               |
| 23 | open          | Document benchmark architecture in `CODEBASE_OVERVIEW.md`     | North Star first per CLAUDE.md; no implementation before docs land                            |
| 25 | open          | Capture exception type+message in resp-stats on pre-response failures | Small patch; makes failure records self-explanatory. From 2026-04-19                  |
| 26 | open          | Systematic review of EXISTING CONTEXT list design             | Surfaced from Task #19 Phase 2 dialogue (2026-04-30): rationale, manifest source data, step-by-step algorithm, objective, effectiveness measurement, industry-standard alignment. See `docs/task26-existing-context-design.md` |
| 27 | open          | Manifest scalability assessment + industry-standard review    | Surfaced from Task #19 Phase 2 dialogue (2026-04-30): is single-JSON `manifest.json` scalable to 10K+ pages? Are we following knowledge-graph / metadata-store best practices? |
| 28 | open          | M5 (`body_link_syntax_match`) implementation — symmetric Jaccard | Surfaced from Task #19 Round 3 (2026-05-04). Extend `validate_compiled_source_response` (~30 LOC) to scan body for `[[<slug>]]` tokens, build per-page body wikilink set, emit `\|declared ∩ body\|` and `\|declared ∪ body\|` counts. Symmetric Jaccard catches BOTH metadata-not-in-body AND body-wikilinks-not-declared. **Phase 3 gate** for Task #19. |
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
