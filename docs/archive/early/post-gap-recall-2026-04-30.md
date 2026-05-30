# Post-Gap Recall — KDB Architecture Self-Test (2026-04-30)

**Date:** 2026-04-30
**Gap covered:** 2026-04-22 → 2026-04-29 (9 days off-project for fixed-income portfolio rebalancing — see `~/Obsidian/Daily Notes/2026-04-29.md`)
**Last KDB working day:** 2026-04-21 (HEAD `88ee503`, 2 commits ahead of `origin/main`)

## Why this document exists

After 9 days off, I (project owner) walked through 8 architectural beats of KDB from memory before opening any code. The thought-partner verified each beat against ground truth (daily notes, commits, `docs/`, `MEMORY.md`). The exercise re-anchors the mental model before resuming work on **Task #19 (Define KPIs + gate thresholds)** — the natural next pick from the 04-21 handoff.

The dialectic format is deliberate: preserving both the recall *and* the verification makes this doc useful both as closure on this session's reorientation and as a template for the same exercise after future gaps.

**Headline finding:** strong recall on architecture, mechanics, and intent. **One real architectural inversion** (the summary ↔ article output taxonomy) and **two terminology drifts** (`eval` → `benchmark`; `resp-stats` is telemetry, not quality) to re-cement before any KPI design work.

---

## [1] KDB scope — Karpathy-inspired; embeds properties + wikilinks to existing vault categories/files

> **Recall:** "What [I] want to do — a KDB based on Karpathy proposal for new files, while creating embedded properties and wiki links to our existing categories/files in the Obsidian vault."

**Verdict:** ✅ correct.

**Verification:**
- KDB compiles markdown sources into structured wiki pages with `[[wikilink]]` connections.
- Output lives in `~/Obsidian/KDB/` as a parallel subtree alongside the user's existing vault content.
- Aspirational future phase: ingest existing vault content (`Equity Research/`, `History/`, etc.) into the compounding graph.

---

## [2] Build status — KDB pipeline working; existing-vault ingestion not started

> **Recall:** "So far we've been working on KDB and we have not started the embedding of existing files."

**Verdict:** ✅ correct.

**Verification:**
- The "raw → KDB" path is fully functional (proven 2026-04-21: 22 pages created, 40 updated on a real-vault wet run).
- Sources placed in `raw/` are the only input today. The user's pre-existing notes in `Equity Research/`, `History/`, etc. remain untouched by the compiler.
- The "existing-vault → KDB" backfill is unscoped future work.

---

## [3] State files — `manifest.json`, `last_scan.json`, `compile_result.json`

> **Recall:** "On the KDB side, we have a raw dir to dump files into for processing... we resolved [the issue of] tracking what files have been processed and what ones are new... the 'states' of all the files are ultimately stored in manifest. Although I forgot what `compile_result` and `last_scan` are for."

**Verdict:** ✅ correct on the bones; gap-fill below.

**Verification — the three-file mental model** (documented at `9f4610e`):

| File | Lifetime | Role |
|---|---|---|
| `manifest.json` | persistent | The **library catalog** — current state of what's in KDB (page slugs, hashes, page-types, link graph). Written at end-of-run. |
| `last_scan.json` | persistent | The **scanner's memory** — what files were in `raw/` last run + their hashes. Used to compute NEW / MODIFIED / UNCHANGED on the next run. |
| `compile_result.json` | per-run (ephemeral) | The **LLM's proposal for THIS run** — the JSON object Haiku returned. Lives only in the run's working state; gets validated, reconciled, applied, then folded into manifest. |

**Three different time horizons:** manifest = "what is", last_scan = "what we saw", compile_result = "what the LLM wants to change."

---

## [4] Run mechanics — scan, compile, telemetry

> **Recall:** "When we run the script, we scan the state of all the files in raw, pick the ones that are 'new' or 'modified', feed them into the LLM to 'compile'. The LLM response is recorded in `state/llm_resp` — one input file per entry. We also have another record per run (per script call, called `kdb-compile` or something)."

**Verdict:** ✅ correct.

**Verification + nuance worth re-cementing:**
- CLI: `kdb-compile` (entry point of the `kdb_compiler` package).
- Per-input file: `state/llm_resp/<run_id>/<source_slug>.json` — one **resp-stats record** per source.
- Per-run journal: `state/runs/<run_id>.json` — every stage's payload, timing, errors, warnings.

**Terminology drift caught (Task #17, 2026-04-21):** the records under `llm_resp/` are **call telemetry** — tokens, latency, attempts, well-formedness gates — *not* quality evaluations. The user themselves swept the codebase to enforce this:

| Old (aspirational) | New (mechanical) |
|---|---|
| `eval_writer.py` | `resp_stats_writer.py` |
| `EvalRecord` | `RespStatsRecord` |
| `KDB_EVAL_CAPTURE_FULL` | `KDB_RESP_CAPTURE_FULL` |
| `state/llm_eval/` | `state/llm_resp/` |
| `eval_replay.py` (CLI: `kdb-eval`) | `response_replay.py` (CLI: `kdb-replay`) |

The discipline: **name must match contents.** "Benchmark" is reserved for cross-model comparison.

---

## [5] UI — stage banners, run journal carries errors/warnings

> **Recall:** "We worked on a very detailed UI display of different steps in the workflow. UI details and errors/warnings are also recorded in the runs."

**Verdict:** ✅ correct.

**Verification — the current 8-stage pipeline** (was 7 until 2026-04-21; reconcile was promoted to its own `[5/8]` banner on `88ee8fc`):

```
[1/8] scan
[2/8] validate_last_scan
[3/8] plan
[4/8] compile  ← LLM call (Haiku 4.5 default)
[5/8] reconcile  ← NEW 2026-04-21 — auto-heals pairing drift
[6/8] validate_compile_result
[7/8] patch_apply
[8/8] manifest_update
```

The reconcile stage was the marquee 2026-04-21 milestone. It auto-fixes pairing drift between `pages[]` and the flat `concept_slugs`/`article_slugs` lists when the LLM forgets one side. Two consecutive real-vault compiles (different slugs each time — `corruption`, `mencius`) confirmed the defect is probabilistic and recurring, not a one-shot fluke. Auto-healing is cheaper than loud-failing.

The run journal at `state/runs/<run_id>.json` captures per-stage timings, payloads, and any findings (validator gate/measure findings, reconciler actions taken).

---

## [6] System prompt — multi-model synthesis for structured output

> **Recall:** "We then worked on the prompt for the LLM for generating the responses, to make the output very structured and formatted."

**Verdict:** ✅ correct.

**Verification:**
- Workflow: parallel drafts from Claude / Grok / Gemini / QWEN / GPT-5.4 → synthesis → installed at `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` (renamed from `CLAUDE.md`, commit `1312757`).
- Closed as Tasks #11–#15 in `docs/TASKS.md`.
- 2026-04-21 surgical refinements (Option A): three edits to the *already-installed* prompt — pairing callout after §2 JSON example, §6 field reference rewritten procedurally, self-check rewritten as count-based.
- **Important reframe captured in `MEMORY.md`:** prompt hardening ≠ enforcement. The system-prompt pairing rule is a *probability reduction*. The reconciler stage is the *guarantee*. The two layers cooperate; neither alone suffices.

---

## [7] Output taxonomy — ⚠️ INVERTED (the one real correction)

> **Recall:** "We want the LLM to generate articles (one per doc), concepts (multiple per doc), and summaries (to connect articles with concepts). Article is a little bit like TL;DR, concept is almost like semantic embedding in human-readable text using VectorDB terminology, and summary is the connection between article and concepts — a little bit like the ontology of concepts. So summary is a little bit like the GraphDB."

**Verdict:** ⚠️ **inverted on summary ↔ article.** Concept analogy is right.

**Verification — the locked spec** (Task #10 v3, in `docs/wiki.md` and the system prompt):

| Type | Cardinality | Role | Recall mapping |
|---|---|---|---|
| **summary** | exactly **1 per source** | The source's gloss / TL;DR | this is what was called "article" |
| **concept** | many per source | Atomic idea — closest to a semantic-embedded unit | ✅ correct |
| **article** | **rare**, cross-source | Multi-concept synthesis — the GraphDB-like layer that compounds knowledge across sources | this is what was called "summary" |

**Easy mnemonic:** **article is the rarest and highest-effort output**, not the cheapest. It's the synthesis tier — emitted only when the LLM sees a real cross-concept pattern worth condensing. Summaries are routine (one per doc, always); articles are the alpha.

**Why this matters for Task #19:** the KPI candidate `concept_slugs_coverage` and the pairing-invariant rules `pairing_commission` / `pairing_omission` operate on concept and article slugs separately. Getting the type semantics straight in working memory is a prerequisite for designing scoring rules that distinguish "the LLM under-produced concepts" (a routine signal) from "the LLM failed to synthesize an article" (a rare-event signal). Different metrics, different thresholds.

---

## [8] Where we left off — eval/benchmark framework

> **Recall:** "Right before the 9-day break, we wanted to establish an evaluation system to score the LLM output / compile_results. Once we can reliably score and value the quality of the LLM response, we can then run tests with a host of LLM APIs and ollama local models to identify the best list of models we can use to generate KDB in earnest."

**Verdict:** ✅ direction right; precision worth restoring.

**Verification:**

**Terminology** (Task #17, 2026-04-21 — the user's own discipline call):
- "Benchmark" = cross-model comparison (the work that's about to begin)
- "Resp-stats" = per-call telemetry (what's already captured every run)
- "Eval" was retired as too aspirational/conflated. The codebase, CLI, env vars, blueprint, and memory notes were all swept.

**Decomposition** (2026-04-21):
- Parent **Task #5 (LLM benchmarking)** is `in-progress`.
- Sub-tasks: **#19** KPIs + gate thresholds (next pick) · **#20** ground-truth source · **#21** `models.json` registry expansion · **#22** scorecard format · **#23** architecture docs in `CODEBASE_OVERVIEW.md`.

**Scaffold landed** (Task #18 closed at `5825d0f`, 2026-04-21):
- Top-level `kdb_benchmark/` engine package — `paths.py`, `registry.py`, `models.json` (2 entries seeded), 9 unit tests.
- Top-level `benchmark/` data dir — `sources/`, `truth/`, `scores/` tracked via `.gitkeep`; `runs/`, `inspect/` gitignored.
- One-way import boundary: `kdb_benchmark` → `kdb_compiler` only, never the reverse.
- **Banked locally, not yet pushed** (C3 chosen on 04-21 for fresh-eye review — now stale-eye review nine days later).

**Hook point already in place:**
- `kdb_compiler/validate_compile_result.py` carries a `score_response` stub returning `None`.
- The stage-4 journal payload has a `response_score` slot ready to receive benchmark-scored results.
- The benchmark engine plugs into this slot — no additional plumbing needed in the compiler.

**KPI candidate set** (subject to Task #19 design):
- `pairing_integrity` — `pages[]` ⟷ slug-lists match rate (`pairing_commission + pairing_omission == 0`)
- `concept_slugs_coverage` — declared slugs that produced a page / declared slugs
- `link_target_resolution` — `outgoing_links` that resolve in `pages[]`
- `body_link_syntax_match` — declared `outgoing_links` present as `[[slug]]` in body
- `schema_pass_rate` — `schema_ok` flags per N runs
- `semantic_pass_rate` — `semantic_ok` flags per N runs
- Cost / latency: `p50_latency`, `p95_latency`, `cost_per_page`

The Task #19 deliverable is the **gate vs. measure split** across this set — which metrics fail a model out of contention (gate), which are scored and reported (measure). Mirrors the validator's existing severity model from 2026-04-21 (`pairing_*` mismatches were promoted to *measure* severity once the reconciler made them auto-fixable).

---

## Net summary

**Recall scorecard:** 7 ✅, 1 ⚠️ inversion, 2 terminology drifts noted.

**The inversion (summary ↔ article)** is the only beat where the code-side ground truth and recall disagreed. Refresh the mnemonic:
- **summary** = 1 per source, the TL;DR (routine)
- **concept** = many per source, atomic idea (the building block)
- **article** = rare, cross-source synthesis (the alpha)

**The terminology discipline** the user established on 2026-04-21 is worth re-internalizing because Task #19 (KPIs) depends on it: **what we measure** is exactly where vague vocabulary causes design errors.
- `benchmark` = cross-model comparison
- `resp-stats` = per-call telemetry (NOT quality)
- `eval` = retired

**Mental model to carry into Task #19:**

```
sources (raw/)
   │
   ▼
[1/8] scan ──── last_scan.json (memory of what we saw)
[2/8] validate_last_scan
[3/8] plan
[4/8] compile (LLM) ──── compile_result.json (proposal) + state/llm_resp/<run_id>/ (telemetry)
[5/8] reconcile (auto-heal pairing drift)
[6/8] validate_compile_result ──── score_response() stub ← Task #19 hook lives here
[7/8] patch_apply ──── ~/Obsidian/KDB/ (vault output)
[8/8] manifest_update ──── manifest.json (library catalog)
                                    ▲
                                    │
                  state/runs/<run_id>.json (per-run journal)
```

**Output types produced by stage 4:**
- 1 × **summary** per source (always)
- N × **concepts** per source (always, ≥1)
- 0..1 × **article** per source (rare, cross-concept synthesis)

---

## Next pick

**Task #19 — Define KPIs + gate thresholds for the KDB benchmark.**

Phase 1 (Strategize per CLAUDE.md): propose 2-3 architectural option-shapes for the gate-vs-measure split across the candidate KPIs above.

**Pre-Task #19 housekeeping** (one-time, do first):
1. `source .venv/bin/activate && python -m pytest -q` — verify 421 pass + 1 skip still holds after the gap.
2. Stale-eye review of `kdb_benchmark/paths.py`, `kdb_benchmark/registry.py`, `benchmark/README.md` — push the 2 banked commits if clean.
3. Decide whether to commit `docs/session-handoff-2026-04-21.md` (currently untracked) and this file (`docs/post-gap-recall-2026-04-30.md`).

---

## Reference — files relevant to Task #19

| File | Why |
|---|---|
| `docs/TASKS.md` | Canonical task ledger — source of truth |
| `docs/wiki.md` | Locked taxonomy (summary/concept/article) — the type semantics KPIs operate on |
| `kdb_compiler/validate_compile_result.py` | `score_response` stub slot — the Task #19 hook point |
| `kdb_compiler/resp_stats_writer.py` | Record shape (per-call telemetry) the benchmark engine reuses |
| `kdb_benchmark/paths.py` + `registry.py` | D2 skeleton — ready for runner / scorer / scorecard to land on |
| `kdb_benchmark/models.json` | 2-entry stub; Task #21 expands this to the full 21-model shape |
| Memory `project_task5_benchmark_scoring_directions.md` | Direction A (validator-derived metrics) + Direction B (LLM-as-a-judge) |
| Memory `project_benchmark_framework_deferred.md` | E1/E2 shipping in M2; E3 deferred |
| Memory `feedback_no_imaginary_risk.md` | Single-user workload — no defensive complexity |
| `~/Droidoes/Code-projects/youtube-comment-chat/src/eval/models.json` | Reference 21-model registry shape |
| `~/Droidoes/Code-projects/youtube-comment-chat/benchmark/scores/in-out-list.txt` | Reference scorecard format |
