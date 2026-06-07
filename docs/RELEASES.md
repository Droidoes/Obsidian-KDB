# KDB Release Notes

Backward-looking, **version-keyed** release log. Major releases (`X.0.0`) carry a
running narrative; every point release gets at least one documented entry. Forward
plan: `docs/ROADMAP.md`. Fine-grained date-keyed dev log: `docs/CODEBASE_OVERVIEW.md`
Milestone Changelog.

Versioning + tag policy: see `docs/ROADMAP.md` § Versioning policy. Tags are cut
(and point-release wrapping is evaluated) at each session handoff.

---

## 0.5.6 — #111 Phase 1: model-pool restructure + native Gemini handler + gpt reasoning (tagged `v0.5.6`, 2026-06-07)

**Theme:** baseline-1 marker — optimal per-model config *short of* `json_schema`. The
`json_schema` variable stays isolated to Phase 2 (`v0.5.7`) for every provider.

**What landed (#111 Phase 1, merged from `feat/111-phase1`):**
- **Model-pool restructure** — `common/models.json` split into active-only + new
  `common/models_dropped.json` (a pure human archive the code never reads). The now-dead
  dropped-guard retired: a dropped/archived id resolves to `UnknownModelError` (the
  `DroppedModelError` branch is gone). Roster: dropped `grok-4-1-fast-reasoning` (deprecated)
  → archive; added `grok-4.20-0309-non-reasoning` + `gemma4-12b-qat-128k` (ollama-local, 128k ctx).
- **`gpt-5.4-mini` reasoning + temperature** — `extra_body={"reasoning_effort": "low"}` for
  structured output (`"low"` is OpenAI's extraction floor). **Temperature is now a nullable
  per-model pool override** — gpt-5.4-mini sets it `null` so we omit the `temperature` kwarg
  entirely (GPT-5 reasoning models reject any non-default `temperature`; ours hardcoded `0.0`
  and 400'd). Every other model still sends `temperature=0.0` (deterministic extraction).
- **Gemini → native `google-genai` SDK** — new `_call_gemini` handler (sibling to
  `_call_anthropic`) moves Gemini **off the second-class openai-compat shim**: JSON mode
  (`response_mime_type="application/json"`) + `thinking_config.thinking_level="minimal"`
  (Gemini 3.x uses `thinking_level`, not the 2.5-era `thinking_budget`; flash-lite's floor is
  `minimal`, full thinking-off unsupported). Telemetry maps `usage_metadata`
  (output = `candidates_token_count` + `thoughts_token_count`). New `google-genai` dependency.
  **`response_json_schema` deferred to Phase 2.**
- **Retry-telemetry fix** — a Pass-2 compile that recovers via **re-prompt** (schema/semantic
  re-validation loop) with no in-place repair was invisible to `recovery_rate`/`retry_load`
  (they keyed off `model_response.attempts` = SDK transient retries, not the compile re-prompt
  count). Now `recovery_rate`/`retry_load` count `final_attempt_index > 1` (content re-prompts
  only; SDK 429/5xx retries deliberately excluded, matching Pass-1); a re-prompt-only recovery
  records `final_status="retried"`; `compile_meta.attempts` carries the re-prompt count; and the
  per-source `pass-2 ✓ (N attempts)` line + `console.log` now surface retries. Makes the
  baseline-1 `recovery_rate` axis trustworthy.
- **Per-source token telemetry** — the `pass-1 ✓` / `pass-2 ✓` console lines now show
  `· in <n> / out <n>` (per-source token in/out, alongside latency), captured in each run's
  `console.log` via the `EventRecorder`. Display-only — no `measurements.json`/KPI change.

deepseek + qwen were already optimal (#110), so they're unchanged. 1247 non-live tests green;
Gemini native path live-smoke validated (exit 0, 0 quarantined, native `usage_metadata` tokens).
Sets up **baseline-1** (batch-1 four models at `v0.5.6`) against the `@v0.5.4` baseline-0; for
Gemini the `@v0.5.4 → @v0.5.6` delta isolates the native-vs-shim effect. Plans:
`docs/superpowers/plans/2026-06-07-phase1-pool-prep-per-model-config.md` +
`docs/superpowers/plans/2026-06-07-phase1-gemini-native-handler.md`.

---

## 0.5.5 — #111 Phase 0: run provenance + release-keyed leaderboard (tagged `v0.5.5`, 2026-06-07)

**Theme:** the baseline-0 marker for the #111 two-phase de-risk — make every benchmark
run version-attributable *before* re-benchmarking, so the optimal-call upgrades in
Phase 1/2 land as isolated, per-model-comparable deltas. Pure provenance/scoring
plumbing; **no model-call-path change** (Phase 1 begins that).

**What landed (#111 Phase 0, merged from `feat/111-structured-output-upgrade`):**
- **Run provenance** — `common/version.py` `release_version()` (`git describe --tags
  --dirty --always`, best-effort → `"unknown"`) stamped into
  `RunMeasurementHeader.release_version` and the emitted `measurements.json` (back-compat
  default `""` for pre-#111 headers).
- **Saved run narrative** — orchestrate stdout accumulated by the `EventRecorder` and
  written to per-run `benchmark/runs/<id>/console.log`.
- **Release-keyed leaderboard** — `kdb-benchmark score` now keys rows on
  **`(provider, model, release_version)`** (`provider/model@version`), so the same model
  at different releases accumulates as distinct, comparable rows; the same triple re-run
  replaces. *Migration: a pre-#111 bare-model leaderboard is incompatible — delete
  `benchmark/scores/leaderboard.{json,md}` once.*

1221 non-live tests green. Sets up the clean-slate **baseline-0** cohort
(deepseek-v4-flash / qwen3.5-flash / gpt-5.4-mini / gemini-3.1-flash-lite) to be fired
at this tag. The prior 3-model cohort has been preserved as the `@v0.5.4` baseline.
Plan: `docs/superpowers/plans/2026-06-07-phase0-run-provenance-leaderboard-key.md`.
Spec: `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md`.

---

## 0.5.4 — Benchmark framework + user-owned model pool (tagged `v0.5.4`, 2026-06-07)

**Theme:** the infrastructure that sets up a *fair* model evaluation — the GT-free benchmark
framework (#109), Pass-1 robustness telemetry (#108), and a user-owned model pool with cost/ctx
diagnostics (#110). Bundles the work merged to `main` since `v0.5.3` (this release closes the
untagged-`main` gap). On the 0.5.x line; precursor to the #111 optimal-calls + clean-slate
re-benchmark arc.

**What landed:**
- **#110 — user-owned model pool + cost/ctx diagnostics** (merge `5d99900`; 1209 non-live tests;
  live-smoke clean). `common/models.json` (pool + curation ledger) + `common/model_pool.py`
  `resolve_models_json(id) → ModelSpec` (alias→provider+knobs, absolute dropped-guard, `words×1.3`
  ctx-estimate helpers); `kdb-orchestrate --model <id>` resolves the pool (`--provider` demoted to
  an escape hatch + conflict-check). **`cost_usd`** restored (pricing × aggregated tokens) on both
  telemetry paths; proactive **input-side ctx-overrun guard** in both passes (skip-and-quarantine,
  no API spend). Semantic **`thinking` field** (per-provider disable translation: verified alibaba
  `enable_thinking:false` + deepseek `thinking:disabled`); `deepseek-v4-pro` un-dropped. New
  reference `docs/reference/model-provider-api-calls.md` (per-provider call shapes + structured-output
  / reasoning matrix). Follow-ups: #111 (`json_schema` upgrade + Gemini native handler).
- **#109 — benchmark redesign framework** (merge `610e2c8`; **calibration parked**). Quality-only,
  GT-free, two families never blended: `common/measurement.py` (`PassCallMeasurement` P1+P2 logical
  projection), `compiler/kpi/` (processing + graph families), `kdb-orchestrate --emit-kpis` →
  `benchmark/runs/<id>/measurements.json`, `kdb-benchmark score` Borda leaderboard + weak-spot
  penalty. Weights/final-set/promotion **parked to post-cohort calibration** (needs live cross-model
  spread — data-before-principle). `§7` doc-debt + weight calibration close out at #109-final.
- **#108 — Pass-1 robustness** (with #109). `final_status` + aggregate token/latency telemetry on the
  Pass-1 sidecar (feeds `PassCallMeasurement.from_pass1`, makes Pass-1 failures observable); shared
  `common/util/json_escape_fix` wired before `json.loads`. Full ladder deferred (Pass-1 has zero
  repairable failures — data-before-principle).

**Process:** all subagent-driven TDD with per-task spec+quality reviews; #110 also had a final
holistic review that caught a live-path threading must-fix. Note: `common/__init__.py` `__version__`
is stale (`0.5.2`) — git-describe is the authoritative version; #111 Phase 0 wires release provenance.

**Next:** **#111** — call each model optimally (`json_schema` structured output + per-model
reasoning/thinking config) → clean-slate cohort re-benchmark, then close #109 weight calibration.

---

## 0.5.3 — Pass-2 robustness ladder (tagged `v0.5.3`, 2026-06-02)

**Theme:** make Pass-2 deterministically recover from the two confirmed recoverable
LLM-emission malformations instead of relying on a lucky retry — a re-validation-gated
repair ladder (Task #106). 0.6-robustness precursor, on the 0.5.x line.

**Gate — run-8 clean E2E:** `exit_reason=ok`; graph **172 Entity · 29 Source · 12 Domain ·
173 `BELONGS_TO` · 177 `SUPPORTS` · 409 `LINKS_TO`** (≡ run-6/7 standard; 0 quarantined).
**1213 non-live tests green.** The new compositional repair telemetry plumbed through end-to-end
(all 29 Pass-2 compiles recorded `final_status='clean'` — the malformations didn't recur this run,
so the rungs correctly stayed dormant; the repair paths are covered by 15+ unit/integration tests).

**What landed (Task #106 — deterministic ladder: `emit → repair → retry → repair → quarantine`,
every repair re-validation-gated):**
- **Rung 1 — targeted JSON backslash-escaping** (`common/util/json_escape_fix`): doubles only the
  stray `\` that JSON rejects (e.g. unescaped LaTeX `\(n-1\)`) so the bytes parse **and the backslash
  survives** — content-preserving by construction. The 5-model design panel chose this over the
  `json-repair` package (which can silently strip content); **no new pip dependency**.
- **Rung 2 — slug coercion** (`common/paths.collapse_slug`): lowercase + collapse `-{2,}`→`-` +
  edge-strip (the deterministic non-semantic subset of `slugify`), with full reference-propagation
  across all 7 slug-bearing fields (regex wikilink rewrite preserving `|display`/`#anchor`) + an
  all-values collision guard, in `compiler/repair.coerce_slugs_and_propagate`.
- **LB2 — `semantic_check` moved inside the attempt loop** so a post-repair semantic failure retries
  rather than quarantining with no budget left; per-attempt state reset fixes a latent stale-state class.
- **Compositional telemetry** on `RespStatsRecord` (`compile_attempts`/`syntax_repaired`/`slug_coerced`/
  `final_status`) — observable deterministic-recovery rate, so over-reach is detectable.

**Also:** **viewer** — node captions now appear only past a zoom threshold (`LABEL_ZOOM_THRESHOLD`)
with a live zoom readout in the header.

**Process:** spec **5-panel design review** (Codex/Deepseek/Qwen/Gemini/Grok → unanimous
GO-WITH-CHANGES; all folded, incl. the rung-1 escaping decision and Joseph's decision-B lowercase).
Implemented **subagent-driven** (8-task TDD plan); per-task two-stage review caught two real bugs
(a telemetry sticky-flag mis-report; the original semantic-gate gap). Merged `2fb5d0e`. Plan:
`docs/superpowers/plans/2026-06-02-task106-json-escape-slug-coercion.md`; synthesis:
`docs/superpowers/specs/2026-06-02-task106-review-synthesis.md`.

**Next:** run-8 surfaced recoverable failures clustering in **Pass-1** (empty-response, null-summary;
all retry-rescued) → **Task #108** (extend the ladder into Pass-1; rung-1 already reusable in
`common/util`). Then the **0.6→1.0 ingestion-pipelines** arc.

---

## 0.5.2 — Codebase realignment, Phase B (tagged `v0.5.2`, 2026-06-02)

**Theme:** finish the realignment — split the monolithic `kdb_compiler` package into the
peer-package structure the architecture has described since `v0.5.0`, **before** the 0.6
ingestion arc builds on top of it. Internal refactor, **zero behavior change**. (Task #105, Phase B.)

**Gate — run-7 clean E2E** (post-split): `exit_reason=ok`; finalize wired **468 links, 0 orphans**;
graph **193 Entity · 29 Source · 10 Domain · 195 `BELONGS_TO` · 202 `SUPPORTS`** — structurally ≡
run-6 (the delta is normal LLM run-to-run variance) → behavior preserved end-to-end. **1191 non-live
tests green** (1175 → 1191: +16 guard/split/render/gate tests, none lost).

**What landed (Phase B — package split; leaf-first, move-don't-rewrite):**
- **Six peer packages** replace the flat `kdb_compiler/` (+ `graphdb_kdb`, `kdb_benchmark`):
  `common` (leaf) · `ingestion` · `compiler` · `kdb_graph` (was `graphdb_kdb`; `graphdb-kdb` CLI name kept) ·
  `orchestrator` · `tools`. Extracted in dependency order so every step stayed green.
- **B.3 dependency contract is guard-tested** — `tools/tests/test_package_boundaries.py` AST-asserts the
  actual import graph equals the contract (`common`→∅ · `kdb_graph`→`common` · `ingestion`→`common` ·
  `compiler`→`common`+`kdb_graph` · `orchestrator`→all · `tools`→{`common`,`kdb_graph`,`ingestion`,`compiler`}),
  with one documented `orchestrator→tools.cleanup` inline-cleanup exception.
- **One real restructure** — `resp_stats_writer` split into `common/llm_telemetry` (generic call telemetry)
  + `compiler/resp_summary` (`build_parsed_summary`); the internal `parsed_summary` gate was **lifted** to the
  compiler call site (byte-identical condition) to keep `common` a true leaf.
- **Deferred Phase-A cleanups landed**: `failure_stage="reconcile"→"repair"`, `JOURNEY` `source_state.json→manifest.json`.
- Tests redistributed into per-package `tests/` dirs behind a shared root `conftest.py`; `pyproject` discovery,
  package-data, and `testpaths` updated; all 9 CLI entry points resolve.

**Execution + review:** implemented **subagent-driven** (13-task plan, fresh agent per task, two-stage review on
the logic-bearing ones). **5-panel code review** (Codex · Deepseek · Qwen · Gemini · Grok) → **GO-WITH-FIXES**, all
must-fixes folded (F1–F6: guard retired migration scripts, `__version__`→`0.5.2`, `setup.sh`/boundary-set/wheel-exclude/
stale-text). 3 non-blocking follow-ups (viewer packaging · `compiler.compiler` rename · cleanup decoupling) → **Task #107**.
Synthesis: `docs/superpowers/specs/2026-06-02-phase-b-review-synthesis.md`. Merged `f28220e`.

**Next:** the **0.6 robustness ladder** — **Task #106** (JSON-repair + slug-coercion), now landing in the real
`common/util` + `compiler/repair` homes; panel-review its spec → writing-plans → run-8.

---

## 0.5.1 — Codebase realignment, Phase A (tagged `v0.5.1`, 2026-06-02)

**Theme:** make the implementation reflect the decided architecture — pay down the
monolithic-`kdb_compile`-era terminology + structure debt **before** the 0.6 ingestion
arc. Internal refactor, **zero behavior change**. (Task #105.)

**Gate — run-6 clean E2E** (post-refactor): `exit_reason=ok` — 36 scanned / 36 enriched /
**29 compiled / 7 noise / 0 quarantined / 0 invariant**; finalize wired 478 links, 0 orphans.
Graph: 180 Entity · 29 Source · **10 Domain** · 100% `BELONGS_TO`. Structurally ≡ run-5 (the
delta is normal LLM run-to-run variance) → behavior preserved end-to-end. 1175 non-live tests green.

**What landed (Phase A — fix-in-place; one refactor, two sequential phases, A then B):**
- **Retired the legacy batch path**: `kdb_compile.py` (the superseded "second orchestrator"),
  its 427-ln `run_journal.py`, dead `planner.py`/`compiler.run_compile`, and 5 dead CLI bindings.
- **Fixed two layering inversions** so `common`-level leaves (`types`, `source_io`) depend on
  nothing above them (`SourceFrontmatter`→`types`, frontmatter parser→`source_io`); guard-tested.
- **Honest renames**: `reconcile→repair` · `patch_applier→page_writer` ·
  `source_state_update→manifest_writer` · `validate_compiled_source_response→validate_source_response` ·
  `ingestion/→enrich/` (+`run_journal→enrich_journal`). (`manifest.json` file kept — its name is honest.)
- **Single Kuzu door**: a 10-function context read-API in `graphdb_kdb/queries.py`;
  `graph_context_loader→context_loader` now authors **zero Cypher** (byte-identical query port).
- **North Star §5 rewritten** to the orchestrator architecture + stale-reference sweep.

**Ratification:** 5-model panel (Codex · Deepseek · Qwen · Gemini · Grok-build), unanimous GO;
blueprint v2 + reviews + synthesis under `docs/superpowers/specs/2026-06-01-codebase-realignment-*`.

**Next:** **Phase B** — split the `kdb_compiler` monolith into peer packages
(`common`/`ingestion`/`compiler`/`graph`=`kdb_graph`/`orchestrator`/`tools`), still before 0.6.

---

## 0.5.0 — Reliable orchestration (tagged `v0.5.0`, 2026-05-31)

**Theme:** the end-to-end `kdb-orchestrate` pipeline runs reliably, observably, and
gracefully — the 0.5.0 gate.

**Gate — run-5 clean E2E** (`2026-05-31T21-05-23`): `exit_code=0`, `exit_reason="ok"` —
36 scanned / 36 enriched / **29 compiled / 7 noise / 0 failed / 0 quarantined / 0
invariant / 0 warnings**; finalize wired 449 links, 0 orphans. Graph (schema **v2.4**):
181 Entity · 29 Source · **10 Domain** · 444 LINKS_TO · 183 SUPPORTS · 181 BELONGS_TO.

**What landed since 0.4.1:**
- **#96 — quarantine-and-continue** error-handling: severity taxonomy + structured
  `orchestrator_events.jsonl`, production invariant checks, source-local quarantine
  (run continues; `run_fatal`/`invariant` still abort), finalize-always-over-committed-set.
- **#102 — live stdout progress**: default-on, blow-by-blow per-stage narrative
  (`[n/total] ▸ source`, `pass-1`/`pass-2` with elapsed, running counts, inline `⚠`),
  `--quiet` opt-out, console decoupled from JSONL verbosity (supersedes #101's stderr tee).
- **#103 — domain-scoped Pass-2 context** (D3 → hard same-domain gate): the context
  snapshot is pulled only from the source's Pass-1 domain (anti-entropy).
- **D1-A derived domains** (from 0.4.1): `BELONGS_TO` derived from `Source.domain`+`SUPPORTS`;
  10 domains live in run-5 (vs 4 pre-backfill).
- **Pass-1 coercion + Pass-2 retry** (run-4 findings, `docs/run-4-findings.md`): Pass-1
  coerces >10 `entity_search_keys` to 10 and lets `source_type='other'` pass without
  `other_reason` (don't reject benign deviations); Pass-2 retries on a recoverable bad-JSON
  emission (parse/schema), mirroring Pass-1 — which recovered run-4's lone quarantine
  (a LaTeX `\(…\)` JSON-escape slip) in run-5.
- **#97 — GraphDB viewer**: multi-model bake-off → official single-command D3 viewer
  (`tools/viewer/kdb_graph_viewer.py`).

**Run history:** run-4 surfaced the findings (1 quarantine from a stochastic LLM
JSON-escape defect, handled gracefully); the fixes landed; **run-5 came back clean** → gate
met. 1219 non-live tests green. Next: **0.6 → 1.0** (ingestion pipelines). See `docs/ROADMAP.md`.

---

## 0.4.1 — Domain derivation, D1-A producer slice (tagged `v0.4.1`, 2026-05-31)

**Theme:** first slice toward 0.5.0 — fixes the domain meaning layer.

`Entity BELONGS_TO Domain` is now a **derived projection** from `Source.domain` +
`SUPPORTS` (an entity belongs to the domains of the sources that support it),
replacing the broken per-page LLM `domain`. Edges carry `support_count` (distinct
supporting sources); `sub_domain` retired. Pass-2 no longer emits page
`domain`/`sub_domain`. Schema → **v2.4** (destructive REL change; rebuild-only).
Snapshot → **v6**.

**Validated on run-3 data (zero LLM cost):** domains 4 → **11**; `value-investing`
0 → **66 entities** (now the top domain); canonical-entity domain coverage
16% → **100%**.

Implements ratified decision **D1-A** (`docs/ontology-blueprint-V1.md` v0.2). Plan:
`docs/superpowers/plans/2026-05-31-task-0.5.0-producer-domain-rebuild.md`. 1010
non-live tests green; final code review (opus) cleared it to ship.

**Still pending for 0.5.0:** D3 domain-scoped T2/T3 retrieval · stdout/progress
messaging · **run-4** (the orchestration-reliability gate).

---

## 0.4.0 — baseline (tagged `v0.4.0`, 2026-05-31)

**State:** the end-to-end pipeline runs (`feeder → ingestion/Pass-1 → compiler/Pass-2
→ GraphDB`). Run-3 (2026-05-30) was the first clean E2E run — 36 scanned / 29 compiled
/ 7 noise / 0 quarantined; graph: 178 Entity · 29 Source · 4 Domain · 0 Claim.

**Known limitation (the 0.5 target):** the domain meaning layer is broken —
`BELONGS_TO` is built from a leftover Pass-2 per-page LLM `domain` that under-emits
(24/147 concept pages, 4 values; `value-investing` never emitted). Orchestration is
not yet reliable.

**Planning landed this line:** Ontology Blueprint V1 ratified after a 5-model panel
review — D1→A (derive domain), D2→deferred to 2.0 (Claim/Learn layer), D3→C
(domain as retrieval coordinate). Release versioning + roadmap adopted.

→ Next: **0.5.0** (reliable orchestration). See `docs/ROADMAP.md`.
