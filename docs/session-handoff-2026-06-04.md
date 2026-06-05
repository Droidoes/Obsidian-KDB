# Session handoff — 2026-06-04

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — Benchmark redesign: architecture CONVERGED, KPI list is next

Design-only session (no code). We resumed the benchmark-redesign brainstorm and **closed the architecture + locked the vocabulary**. The one remaining substantive thread — the **complete KPI list** — Joseph deliberately split into its **own next session**.

**THE resume artifact:** `docs/superpowers/specs/2026-06-03-benchmark-redesign-directions.md` — now carries an authoritative **`⭐ Convergence 2026-06-04`** block at the top. Read that block first; the old "inversion" section below it is struck-through/superseded.

### What converged today

1. **Vocabulary lock — measurement vs scoring.** (Joseph had been saying "score" but meant *measure* throughout.)
   - **Measurement** = per-run, per-model raw KPI values — GT-free, absolute, no peer. Emitted every run.
   - **Scoring** = the cross-model **Borda** step over a cohort of models' measurements. The only place "who's better" is decided.
   - ⇒ **the anchor problem never enters the benchmark** — anchors were only for a single-run *absolute self-score* (= the deferred telemetry layer). Borda needs weights, not anchors.

2. **Architecture (corrected — the prior doc mis-captured it).**
   ```
   kdb-orchestrate ──run per model over sandbox (Vault-in-place-test-run, 36 src)──┐
      ├─ emits per-run PROCESSING-KPI measurements (Pass-1 + Pass-2 records)        │
      └─ builds the final graphDB for that model                                    │
      └─[specific CLI option]→ POST-PROCESS: compute GRAPH-KPI measurements         │
                                                                                     ▼
   benchmark script (tools/benchmark/, SCORING only) — stitch per model → Borda → SCORES
   ```
   - `kdb-orchestrate` is the **run vehicle** and *emits measurements*; the **benchmark script only scores** — it never runs the passes. (Both my framings were wrong en route: not "drop the harness/use orchestrate as vehicle," and not "standalone harness re-runs the passes." This is the reconciled third thing.)
   - **Naming:** per-run file = `runs/<id>/measurements.json` (not `score.json`); `scores/` = benchmark output.
   - **Task #1 (architecture fork) CLOSED.**

3. **KPI triage — DIRECTION only** (complete list = next session):
   - **Keep, reframed:** S0 → per-token quarantine/failure rate (processing) · M4 → semantic-pass (processing) · M1 → dangling-edge/link-resolution over `LINKS_TO` (now **graph**).
   - **Kill (model-obsolete post 0.5.x ontology rebuild):** M2/M3 (declared-slug↔page pairing gone) · M5 (body wikilink coverage — wikilinks are display-only vanity).
   - **Drop from *scoring*** (diagnostic only if kept): M6 cost · M7 latency — model selection is settled on price; scoring them re-opens a closed axis.
   - **Promote to processing signals:** `retry_load` / `token_overrun_rate` (robustness; ties to #106/#108 ladders).
   - **The real new work:** graph-KPIs vs the current ontology graph (orphans, link density, `BELONGS_TO` coverage, entity fragmentation) — plausibly the most model-discriminating axis.

4. **"Minimum change" = the engine.** The ~20% salvage (Borda spine, run-recording, scorecard aggregator, `tools/benchmark/` layout) is re-pointed at the new KPI set + per-token normalization. KPI *content* change is TBD in its own session.

## OPEN — pick up here

- [ ] **HEADLINE / Joseph's open call:** make the **complete processing + graph KPI enumeration** the next session — OR slot **#108 (Pass-1 repair ladder)** / **#107 (Phase-B polish)** in front first. *(My lean: KPI enumeration is higher-leverage — it unblocks the whole framework; but #108 is a cleaner self-contained code win if he'd rather ship than design back-to-back.)*
- [ ] **KPI computation home** — deferred; decide once the list is known (it dictates which records each family reads). Likely measurement-compute production-side (orchestrator-adjacent, spans Pass-1+Pass-2), scoring in `tools/benchmark/`.
- [ ] **Parked nuance (framework spec):** processing-KPI emission *always-on every orchestrate run* (revises LOCKED #8) vs *gated behind benchmark mode* (preserves #8).
- [ ] **Smaller framework decisions** — settle *after* the KPI list (capture command shape · grouping key `model` vs `provider:model:prompt-version` · corpus fingerprint · prompt-version capture · TDD fixtures).
- [ ] **Formal `-design.md`** held until the KPI list lands.

## Housekeeping / open loops
- [ ] **COMMIT GATE OPEN.** Uncommitted: today's directions-doc edits, `session-handoff-2026-06-03.md`, `2026-06-03` + `2026-06-04` daily notes, this handoff. Joseph did not request commit today.
- [ ] **File a Task #N** in `docs/TASKS.md` for the benchmark redesign (still not assigned).
- [ ] Carry-over (untouched today): **#108**, **#107**, the 0.6→1.0 ingestion arc.

## Pointers
- Resume artifact: `docs/superpowers/specs/2026-06-03-benchmark-redesign-directions.md` (read the `⭐ Convergence 2026-06-04` block first).
- Old engine + KPI/Borda machinery: `tools/benchmark/` (`scorer.py` has S0/M1–M7 defs); North Star §7 (`docs/CODEBASE_OVERVIEW.md`).
- Test-run procedure: `docs/reference/test-run-procedure.md`. Sandbox: `~/Obsidian/Vault-in-place-test-run/` (36 sources).
- Task ledger: `docs/TASKS.md`. North Star: `docs/CODEBASE_OVERVIEW.md`. Journey: `docs/JOURNEY.md`.
- Memory: [[project_run3_next_sandbox_vault]] (benchmark-redesign direction + sandbox), [[feedback_obsidian_wikilinks_are_vanity]], [[feedback_apples_to_apples_within_session]], [[feedback_no_parallel_storage_to_authority]], [[feedback_user_fires_api_cost_runs]], [[feedback_devils_advocate_gate]].
