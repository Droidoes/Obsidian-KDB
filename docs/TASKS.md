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
| 19 | open          | Define KPIs + gate thresholds for KDB benchmark               | Parallel to yt-comment-chat `signal ≥75 \| parse ≥95 \| merge_err <2`                          |
| 20 | open          | Decide ground-truth source                                    | GT-A/B/C/D/E; recommendation is GT-D as v1 + GT-E as v2                                       |
| 21 | open          | Port/adapt `models.json` registry                             | Lift the 21-model shape from `youtube-comment-chat/src/eval/models.json`                      |
| 22 | open          | Design KDB scorecard format                                   | Mirror `benchmark/scores/in-out-list.txt`; depends on #19 + #20                               |
| 23 | open          | Document benchmark architecture in `CODEBASE_OVERVIEW.md`     | North Star first per CLAUDE.md; no implementation before docs land                            |
| 25 | open          | Capture exception type+message in resp-stats on pre-response failures | Small patch; makes failure records self-explanatory. From 2026-04-19                  |
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

---

## Unused IDs

`#24` — reserved for the next new task after #23. Gap is intentional — do not backfill.

---

## How to update this file

- **Add a task**: append to the `Open / In-Progress` table with the next free ID.
- **Close a task**: move the row to the `Closed` table, replace the `Status` column with the `Resolution` column content (commit SHA / doc path / memory note name).
- **Decompose a task**: flip parent to `in-progress`, add sub-tasks with new IDs, update parent's "Notes" column to list them.
- **Never** renumber or reuse IDs.
- **Always** commit changes to this file alongside the work that caused them, so git history shows the ledger evolving in lockstep with the project.
