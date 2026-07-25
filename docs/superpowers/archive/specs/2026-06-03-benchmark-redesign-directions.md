# Benchmark Redesign — Locked Directions (brainstorm in progress)

**Date:** 2026-06-03 · **Updated:** 2026-06-04 (architecture converged)
**Status:** 🟡 DRAFT — architecture converged & vocabulary locked (2026-06-04). The **complete KPI list is the remaining open work**, deliberately split into its **own separate session**. Formal `-design.md` is held until that list lands (writing it now would be one big TBD section).

---

## ⭐ Convergence 2026-06-04 (authoritative — supersedes any stale framing below)

**Vocabulary lock — measurement vs scoring:**
- **Measurement** = per-run, per-model raw KPI values (GT-free, absolute numbers, no peer needed). Emitted every run.
- **Scoring** = the cross-model **Borda** step that ranks a cohort of models' measurements per-KPI → weighted sum. The *only* place "who's better" is decided. Needs weights, **not** anchors → the anchor problem never enters the benchmark (it was only ever for a single-run absolute self-score = the deferred telemetry layer).

**Architecture (corrected — the "inversion" section below was a mis-capture):**
```
kdb-orchestrate ──run per model over sandbox (e.g. Vault-in-place-test-run, 36 src)──┐
   ├─ emits per-run PROCESSING-KPI measurements   (Pass-1 + Pass-2 records)          │
   └─ builds the final graphDB for that model                                        │
   └─[specific CLI option]→ POST-PROCESS: compute GRAPH-KPI measurements from graphDB│
                                                                                      ▼
benchmark script (tools/benchmark/, SCORING only) — stitch processing+graph per model,
                                                     cross-model Borda → SCORES
```
- `kdb-orchestrate` is the **run vehicle**; it *emits measurements*. The **benchmark script only scores** — it never runs the passes (my earlier "standalone harness that re-runs the passes" was wrong, and so was the "drop the harness, use orchestrate as the vehicle" framing — orchestrate *is* the vehicle, but the benchmark script is a separate scoring tool, not the runner).
- **Naming:** per-run file holds *measurements* → `runs/<id>/measurements.json` (not `score.json`); `scores/` is the benchmark script's output.
- **Home of KPI computation:** deferred until the KPI list is known (it determines which records each family reads). Likely production-side for the *measurement* compute (orchestrate emits it; processing spans Pass-1+Pass-2 → orchestrator-adjacent), with *scoring* in `tools/benchmark/`. Not finalized.
- **Parked nuance (for the framework spec, not blocking):** is processing-KPI emission *always-on every orchestrate run* (revises LOCKED #8) or *gated behind benchmark/sandbox mode* (preserves #8)?

**KPI triage — DIRECTION only (the complete list is the next separate session):**
- **Survive, reframed:** S0 → per-token quarantine/failure rate (processing) · M4 → semantic-pass rate (processing) · M1 → dangling-edge / link-resolution over `LINKS_TO` (now a *graph*-KPI).
- **Kill (model-obsolete after the 0.5.x ontology rebuild):** M2/M3 (declared-slug↔page pairing is gone) · M5 (body wikilink coverage — wikilinks are display-only vanity).
- **Drop from *scoring*** (keep as diagnostic if useful): M6 cost · M7 latency — model selection is *settled on price*; scoring them re-opens a closed axis.
- **Promote to processing signals:** old diagnostics `retry_load` / `token_overrun_rate` (real robustness signals; tie to the #106/#108 repair ladders).
- **The real new work:** graph-KPIs against the current ontology graph (orphans, link density, `BELONGS_TO` coverage, entity fragmentation) — plausibly the most model-discriminating axis.
- **"Minimum change" holds for the *engine*** (the ~20% salvage — Borda spine, run-recording, scorecard aggregator, `tools/benchmark/` layout — is re-pointed at the new KPI set + per-token normalization). KPI *content* change is TBD in its own session.

---

## Why (motivation)

Redesign of the benchmark — Joseph's framing: **~20% of the existing engine salvaged, ~80% new.** Model selection is already settled on **price** (~$0.05/run on deepseek); **quality is the only open axis**, and the old engine (`tools/benchmark/`, Task #5) can measure only **Pass-2** quality — blind to Pass-1 classification and to graph quality, which for a *graph compiler* is the axis that matters most.

The old engine: an **isolated harness** (`runner.py`) runs a curated corpus through one model, captures `RespStatsRecord` telemetry, and produces a **Borda-normalized** cross-model scorecard. 7 KPIs (S0/M1–M7), all Pass-2.

---

## The inversion (core idea) — ⚠️ SUPERSEDED by the Convergence 2026-06-04 block above

> ~~Stop driving benchmarks with a bespoke isolation harness. Use the **real `kdb-orchestrate` pipeline over the sandbox vault** as the benchmark vehicle, and score **both** processing quality and graph quality, apples-to-apples across models.~~
>
> **Correction (2026-06-04):** the "drop the harness / use orchestrate *as the vehicle*" phrasing mis-captured intent. `kdb-orchestrate` *is* the run vehicle and *emits measurements*; a **separate benchmark script scores only**. See the Convergence block for the authoritative data-flow.

Retained below for history: the *goals* (score both processing + graph quality, GT-free, apples-to-apples, per-token normalized) all stand — only the runner/vehicle framing changed.

---

## LOCKED decisions

1. **GT-free.** No ground-truth labels. KPIs are internal-consistency + graph-structure signals only. (Consistent with the old engine, which was GT-free by design — Task #20 closed won't-do.)

2. **Per-token normalization on every KPI** (per 1M / per 10K tokens), *including* failure rates (e.g. quarantines-per-1M-tokens, not per-source). Rationale (Joseph): a quarantine on a 95KB source ≠ a quarantine on a 2KB source; token-normalizing weights failures by volume processed. Absorbs both *how many* sources and *how big*.
   - ⚠️ Framework must still support **ratio pass-through** for KPIs that are already 0–1 (e.g. coverage), so the deferred KPI discussion isn't boxed in by a normalization primitive decided today.

3. **Borda by layer (refined 2026-06-03 — split on whether a peer set exists at scoring time):**
   - **Sandbox benchmark final / running score (cross-model) → Borda KEPT.** The cross-model step has a genuine candidate set (each model's latest sandbox run), so Borda ranks them per-KPI → weighted sum. This is what Borda is for. Needs per-KPI **weights**, *not* absolute anchors.
   - **Per-invocation processing-KPI self-score (deferred telemetry) → absolute, NO Borda.** A single production run has no peer set, so its "how healthy was this run" number must stand alone → absolute composite → **anchors needed.** That anchor-pinning burden lives entirely with the **deferred** layer, NOT today's build.
   - **Payoff:** because the benchmark uses Borda, **today's build sidesteps the anchor problem** — Borda ranks *relative* rates across candidates, so a Borda-ranked KPI needs only weights. The hard "what value = 0, what = 1" calibration defers along with the telemetry layer.
   - **Caveats (KPI-spec-level, not today):** (a) if any KPI is scored *absolutely within* the final score rather than Borda-ranked, that one still needs an anchor — the per-KPI Borda-vs-absolute split is a KPI-spec call; (b) the old **outlier penalty (D31)** was Borda-adjacent — decide back-or-not in the KPI spec.

4. **Two KPI families, kept SEPARATE (never blended into one number):**
   - **Processing-KPIs** — scoped to the sources *this run touched*; per-token normalized; meaningful on **every** run (incremental or full).
   - **Graph-KPIs** — computed over the *whole resulting graph*; meaningful **only on full-corpus runs**.
   - Why separate: on an incremental run (e.g. 3 changed sources against a 200-node graph), processing-KPIs describe 3 sources while graph-KPIs describe the cumulative graph — a blended composite would lie.

5. **Graph-KPIs matter — do NOT assume them away.** Joseph floated "unless we can prove graph-KPIs won't be a concern for any model" and then retracted it as wishful thinking. Two models can be processing-clean (valid JSON every source) yet produce very different graphs (good entities + dense links vs fragmented entities + orphans + under-emitted SUPPORTS → cratered BELONGS_TO). Graph quality is plausibly the **most** model-discriminating axis. (Joseph: *"keep doing the push-backs."*)

6. **Benchmark = full-corpus sandbox runs.** The vault-in-place test run (`~/Obsidian/Vault-in-place-test-run`, 36 sources) is the benchmark corpus → apples-to-apples on *both* families across models. Per-token fixes *size* differences; same-corpus fixes *content/difficulty* differences.

7. **"Running score"** (renamed from "final score"): uses each model's **latest full sandbox run** — **no historical averaging** of a model's performance over time. The aggregator takes a **list of specific runs**; updating = a model's newer run replaces its prior entry.

8. **SCOPE for the build (Joseph's sequencing):**
   - **Now / this spec:** the **sandbox benchmark** scoring processing + graph KPIs across models.
   - **Later (separate, deferred):** "shoo in" **always-on per-invocation processing-KPI telemetry** on *every* `kdb-orchestrate` run (production quality drift signal). Deferred deliberately.

---

## Architecture (the direction — my last response, captured)

### Code home (honors v0.5.2 D25 boundary; survives the later "shoo-in" with no relocation)
New `compiler/kpi/` concern — computation is **production-importable**, called from tools:
- `processing.py` — processing-KPIs from a completed run's per-source Pass-1/Pass-2 records (per-token normalized).
- `graph.py` — graph-KPIs via `kdb_graph.queries` (the single Kuzu door) over the run's resulting graph.
- `score.py` — the absolute composite. **Pluggable slot today**; anchors + weights filled by the KPI spec.

Lives in `compiler` because `compiler` already imports `common` + `kdb_graph`, and **both** `tools/benchmark` (today's caller) and a future `orchestrator` stage (the always-on path) may import `compiler` (D25: production never imports from `tools`; tools→compiler is allowed). So it never moves.

### Invocation today = tools-side POST-PROCESSOR (recommended; pending explicit confirm)
The benchmark reads a **completed** run's vault artifacts (`<vault>/KDB/state/runs/` + the graph) and computes the record *afterward*. **`kdb-orchestrate` is untouched today → zero production/regression risk.** Later, "shooing in" per-invocation telemetry = lift `processing.py` into an orchestrate stage calling the same module.
- **Fork (the one open architectural decision):** post-processor (rec) vs. orchestrate-stage-now. Post-processor matches "benchmark first, shoo-in later," zero pipeline risk; cost = benchmark is a *second* command after the run (nearly free since Joseph fires runs by hand).

### Storage (benchmark layer → repo; future telemetry layer → vault)
The sandbox vault is **wiped between model runs** (reset procedure nukes `state/runs/`), so per-run records can't live only in the vault — model A's record would be gone before model B runs. → write to the **repo** (reset-surviving), exactly where the old engine kept them:
- `benchmark/runs/<run_id>/score.json` — computed KPIs + run metadata only (model, prompt version, scope, token counts, corpus fingerprint). **NOT** raw LLM responses (resolves Joseph's [4]: responses stay ephemeral in the vault, consumed at capture time, never copied to git → lightweight records).
- `benchmark/scores/<scorecard_id>.json` — running-score output.
- (Advisor leaned "vault," but that was about the *future always-on telemetry* firing on every production run, where git churn is real. Curated benchmark records are low-volume + reset-fragile → repo is correct for *this* layer.)

### Workflow
1. Joseph (API cost — he fires): pause OneDrive sync → reset sandbox → `kdb-orchestrate --pipeline vault-test --model A`.
2. `kdb-benchmark capture <run>` → post-processes completed run → writes `benchmark/runs/<run_id>/score.json`.
3. Repeat for models B, C…
4. `kdb-benchmark score <run list>` → picks each model's latest full sandbox run → cross-model scorecard.

### Salvage map (the 20/80)
- **Salvaged (~20%):** run-recording + scorecard-aggregator spine, `benchmark/runs|scores/` layout, run-dir naming conventions, **the Borda-normalization + weighting machinery in `scorer.py`** (re-applied to the new two-family KPI set at the cross-model running-score step).
- **Replaced (~80%):** isolation runner → real orchestrator output; Pass-2-only KPIs → processing + graph families; per-token normalization. (Borda is *re-applied*, not replaced — see decision #3. Absolute composites are introduced only for the *deferred* per-invocation telemetry layer.)

---

## Decomposition (specs)
1. **This spec (in progress):** the benchmark **framework** — score-record schema, scope tagging, where the two families compute, persistence, the running-score aggregator. KPI computation is a pluggable slot.
2. **Next spec (the deferred deep-dive):** the **KPIs themselves** — processing + graph KPI definitions, per-KPI 0/1 **anchors**, weights, composite formula.
3. **Later:** always-on per-invocation processing-KPI telemetry (lift `processing.py` into an orchestrate stage).

---

## OPEN — pick up here

**NEXT SESSION (headline):** the **complete processing + graph KPI enumeration** — the full list, per-KPI definitions, per-token normalization specifics, then weights. The triage in the Convergence block is the *direction*, not the finalized list. Everything below depends on this landing.

- [x] ~~**Confirm the fork:** post-processor vs orchestrate-stage-now.~~ → RESOLVED 2026-06-04: orchestrate is the run vehicle & emits measurements; benchmark script scores only. See Convergence block.
- [ ] **The few smaller framework decisions** (settle *after* the KPI list — they're KPI-agnostic but cheaper to lock once the list exists):
  - Capture trigger/command shape (`kdb-benchmark capture <run>` vs auto-detect latest run).
  - **Record identity / grouping key** for "latest run per model" — is the key `model`, or `provider:model:prompt-version`? (Prompt iteration is a comparison axis too.)
  - **Corpus fingerprint** — how to assert "same 36 sources" (hash of source set) so the running-score only compares same-corpus cohorts.
  - **Prompt-version capture** — record Pass-1 + Pass-2 prompt versions (comparison axis).
  - TDD test plan + fixtures (existing `benchmark/runs/` data, or a captured sandbox run).
- [ ] Then write the ratified `-design.md`, spec self-review, user review gate → `writing-plans`.
- [ ] **KPI deep-dive** = its own session/spec (#2 above).

---

## Pointers
- Old engine: `tools/benchmark/` (`cli.py`, `runner.py`, `scorer.py`, `scorecard.py`, `registry.py`, `paths.py`, `models.json`); data in `benchmark/runs|sources|scores|truth/`. North Star §7 documents the old KPI/Borda machinery.
- Test-run procedure (reset + run, OneDrive pause): `docs/reference/test-run-procedure.md`.
- Sandbox vault: `~/Obsidian/Vault-in-place-test-run/` (36 sources; live runs fire here, not the repo).
- Memory: `project_run3_next_sandbox_vault` (benchmark-redesign direction + sandbox), `feedback_apples_to_apples_within_session`, `feedback_no_parallel_storage_to_authority`, `feedback_user_fires_api_cost_runs`, `feedback_devils_advocate_gate`.
- Task ledger: `docs/TASKS.md` (needs a new task # filed for this — TBD tomorrow).
