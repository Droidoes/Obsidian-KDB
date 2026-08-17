# Session handoff — 2026-08-16

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime. Supersedes `session-handoff-2026-08-15.md` — everything still open from there is carried forward below.

## TL;DR

**Task #145 (`kdb_fts` — the parallel extraction/ranking system over the gmail-substack corpus) went from problem statement to Phase 0 SHIPPED + Phase 1 PLANNED in one day.** Morning: problem statement + repo-placement briefs panel-reviewed (Grok/DeepSeek/Qwen/Codex/Claude); Joseph's calls: gate-then-extract coverage with per-topic decay, monorepo (new `kdb_fts/` package here, not 10x-Learning-Engine), naming consistency pass (compiler/orchestrator/search dirs renamed `kdb_graph_*`). **Phase 0 landed** (10 commits `3e4e3f8..e29eb73`, subagent-driven): deterministic intake + SQLite ledger + FTS5 over the 2,659-article raw corpus, no LLM; real-tree gate PASSED (`seen=2659 upserted=2659 deleted=0`, 131,961 paragraphs, 117 canonical authors, re-run idempotent, zero writes outside `KDB/fts/`; plan's "3 bleed" estimate unreproducible → amended to 0 with Joseph's sign-off). Blueprint v0.1 ratified (D1–D22; panel review skipped at Joseph's call). **Phase 1 plan written** (`58c9ad6`): LLM gate + `gate_verdicts` migration 2 + stdlib labeling web app + 150-article `calibration-p1` batch. Also today: **production vault-in-place run** confirmed the dir renames broke nothing; `graphdb-kdb verify` exit 0; **DeepSeek-V4 repricing** (peak cache-miss rates now in `models.json`, commit `7b5fc64` — flash 0.44/1.32, pro 1.32/3.96 per 1M) — everything pushed through `58c9ad6`.

**Next session pickup:** Joseph picks execution mode for the Phase 1 plan (subagent-driven recommended vs inline), then execute. Live gate at the end is Joseph-fired: `kdb-fts gate` over ~2,511 ok articles (~$2–3 at new prices), freeze `calibration-p1` (150), Joseph labels in the web app, `kdb-fts calibration` → confusion matrix → **Joseph sets the accept threshold**.

---

## 1. #145 Phase 0 — what exists now

- `kdb_fts/` package: `intake.py` (deterministic walk, D17 identity = gmail_message_id else sha256, paragraph IDs, cleanliness: ok/short/media/digest-stub/bleed), `ledger.py` (the only sqlite opener — write-guard R1), `schema.py` (migration 1), `author_map.py` (yaml over `<vault>/KDB/fts/author_map.yaml`), `state.py` (`$KDB_FTS_PATH` else `<vault>/KDB/fts/`), `cli.py` (`kdb-fts intake/search/status`).
- Write-boundary guard in `tools/tests/test_package_boundaries.py`: sqlite3.connect/mkdir/Path-write mutators allowed only in `ledger.py`; everything else via `common.atomic_io`.
- Suite 3288 green at close. Real corpus state: `~/Obsidian/KDB/fts/ledger.sqlite` (2,659 articles, FTS5 populated).

## 2. #145 Phase 1 plan — the shape (docs/superpowers/plans/2026-08-16-task145-kdb-fts-phase1-gate-review.md)

9 TDD tasks: (1) migration 2 `gate_verdicts` + txn-wrapped migrate + state subdirs; (2) canonical author in FTS; (3) gate prompt `prompts/gate_v1.md` + fail-closed parse (unknown topic → `other`+neither); (4) gate runner + `kdb-fts gate [--max][--dry-run][--model]` (resume by model+prompt_version, one retry, 5%-min-10 exploration marks on ineligible, journal per run); (5) `feedback.py` immutable `events.jsonl` (no update/delete by design) + `kdb-fts feedback`; (6) review batch freezer (deterministic topic-stratified, refuses overwrite — the frozen JSON IS the D13 exposure record); (7) stdlib `http.server` review app + one static page, exposure context stamped **server-side**; (8) `calibrate.py` precision/recall report (relevant = investment ∪ finance-econ; positive = strong/interesting); (9) final review + Joseph-fired live gate.

Plan-recorded deviations from blueprint §6: `gate_verdicts` gains `exploration`/`rationale`/token columns; feedback is jsonl-only in P1 (SQLite mirror waits for Phase 3's ranker); run journal written once at run end; author GC deferred post-v1 (the §6 "Phase-1 decision" — decided: no GC, orphans cosmetic).

## 3. Settled decisions (don't reopen)

- Monorepo; `kdb_fts` naming; state at `<vault>/KDB/fts/`; gmail-substack handled by this parallel system, graphDB compile optional later; harness combining both is a future option.
- D21 status labels (accepted/rejected/pending; helpful/not-so-much) override decay; D22 review surface = local stdlib web app; the 150-label calibration = batch `calibration-p1` in the app.
- bleed=0 ratified by Joseph (plan amended).
- Blueprint v0.1 approved; panel review deliberately skipped.
- DeepSeek pricing stored as peak-hours cache-miss (conservative; Joseph's runs land in the 01:00–04:00 UTC peak window); off-peak rates documented in `price_note`.

## 4. Open threads

- **#145 Phase 1 execution** — awaiting Joseph's mode pick (subagent-driven vs inline).
- **大风歌.md** quarantines every vault-in-place run (Chinese-only title can't slugify — `common/paths.py` PathError; ~3s/run wasted). Needs its own task if Chinese titles recur; Joseph hasn't decided.
- **#146** docs housekeeping (trim CODEBASE_OVERVIEW.md, archive old TASKS.md rows) — open.
- **#143 closure** — still parked on Joseph: compile decision for gmail-substack (now arguably superseded by kdb_fts existing — his call) + Milestone Changelog + TASKS #143 → Closed.
- **Phase-1 follow-ups already noted:** canonical author into FTS (in P1 plan Task 2), author GC (decided: defer), orchestrator argparse usage errors exit 0 through pipes (use `${PIPESTATUS[0]}`), plain `pytest` uses system Python — always `.venv/bin/python -m pytest`.
- PendingLink LLM-invented-slug finding from 2026-08-15 (434 targets exist nowhere; no code gate on prompt §5) — unfiled.

## 5. Environment gotchas (burned today, don't rediscover)

- `~/Obsidian` is a symlink to `/mnt/c/...` (WSL2) — `/mnt/c` paths in output are cosmetic.
- Kuzu allows ONE process on the graph — a concurrent `verify` crashed an orchestrate run; background-task TaskStop does NOT kill the python child (`kill -9` the pid).
- `kdb-orchestrate` requires `--vault-root` always.
