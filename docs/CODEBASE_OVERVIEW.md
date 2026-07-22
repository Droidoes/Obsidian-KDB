# Obsidian-KDB — Codebase Overview (North Star)

**Status:** v1 architecture locked; M0 → M4 landed (compiler + validator + reconciler + benchmark engine + GraphDB-KDB layer + canonicalization all live). Post-`v0.5.7` (2026-07-17): #114 (recovery-oriented Pass-2 parse stage) shipped on `main` **untagged**. **#115 (Pass-2 contract revision) is ratified (spec v1.6 / blueprint v1.10, descoped) but not yet implemented** — per its pre-implementation gate, this doc describes the ratified post-#115 contract ahead of the code; until the Gate-2 contract commit lands, the running pipeline still matches the pre-#115 description.
**Last updated:** 2026-07-22
**Owners:** Joseph (human) + Claude Opus 4.7 (staff architect) + GPT 5.4 / Codex 5.3 (external review)

This is the **single source of truth** for the Obsidian-KDB project. All design rationale, decisions, and open questions live here. External AI consultation artifacts (Grok / Gemini Pro / GPT 5.4 / Codex 5.3) are referenced but not authoritative — they fed into the consensus captured below.

---

## Milestone Changelog

Dated architectural inflection points. Full retrospective and three-iteration history in [`docs/JOURNEY.md`](JOURNEY.md).

- **2026-07-22** — **🏁 Task #117 CLOSED — per-pass leaderboards.** `kdb-benchmark score` now writes **three** boards per invocation: the combined board (unchanged — byte-identical output, golden-pinned) plus **`leaderboard-pass1.{json,md}` and `leaderboard-pass2.{json,md}`** (§7.7). Per-pass processing KPIs are **recomputed at score time** from each row's `run_state/` (new `load_run_measurements_with_stats` — the production loader stays strict; new `cost_usd` projection + 8 additive `compute_processing` diagnostics: per-pass recovery/retry/cost) and scored through the existing §6 `score_models` machinery (Pass-1: 3 processing axes, pro-rata 4:1:1 + penalty, graph inactive; Pass-2: 3 processing + 4 graph KPIs, 40/40/10/10). **Cost is a first-class selection column, never a Borda axis** (`≥$X (+N unknown)` — zero cost can mean unpriced/failed, not free); the Pass-2 board is honestly labeled a **downstream-outcome** board with eligibility/coverage/`p1_noise`/`p1_failed` columns; rows failing the per-board completeness contract (Pass-1 sidecar reconciliation, required-KPI gate incl. all four graph KPIs) render `unranked` with `missing_kpis` + `completeness_errors` — never pro-rated on missing evidence. Competition ranking (ties share ranks: 1, 1, 3); one shared `updated_at`; pre-serialized individually-atomic writes. Spec v0.3.1 + plan v1.4 (Codex 3+5 rounds, all findings code-verified): `docs/superpowers/{specs,plans}/2026-07-22-task117-per-pass-leaderboards*`. Live on the 2026-07-21 cohort: main board diff = stamps only; Pass-1 board surfaces the 6× cost spread (deepseek $0.050 vs gpt-5.4-mini $0.306) against GPT's reliability win — the #118 split-model evidence base. Commits `1ddbea9`→`86dba68` on `feat/117-per-pass-leaderboards`; 1436 non-live tests green.
- **2026-07-22** — **Task #115 DESIGN LOCKED — derivation-first Pass-2 contract revision; North Star updated pre-implementation (the ratified gate).** The Pass-2 LLM contract shrinks to **wiki-native data only** — `pages[]` (`slug`, `page_type`, `title`, `body`) + optional `compilation_notes` — with Python owning everything mechanical (D-115-1..15): six fields leave the contract (`concept_slugs`, `article_slugs`, top-level `summary_slug`, `outgoing_links`, `source_name`, `status`) with no aggregate reconstruction; **the contract speaks wiki, not graph** (pages, bodies, `[[wikilinks]]` — no edge-list projections); the summary page stays fully model-authored **including its slug**, gate-validated against the Python-derived `expected_summary_slug(source_id)` (exact-stem rule, pre-call underivable-stem rejection with zero API spend, post-canonicalization re-validation); **the system prompt moves into the repo** (`compiler/prompts/`) with `pass2_prompt_version` + loaded-text SHA-256 run stamps; `warnings` → `compilation_notes` (kept, optional), `log_entries` dropped; **`confidence` logically deprecated end-to-end** (Entity scope only; Claim tier untouched — D-A2 updated); **canonical links become body-authority** (canonicalization rewrites body wikilinks only) and **the graph owns wikilink→LINKS_TO derivation** with a legacy `outgoing_links` fallback inside the contract commit; the #65 **Repair stage is deleted whole** (pairing defects are structurally impossible under the shrunk contract) and the pipeline renumbers. Historical artifacts stay read-compatible: removed fields become optional-deprecated read-only with dual-mode aggregate validation (D-115-14). **Carve:** cross-source summary-slug reservation / MOVED lifecycle / durability → **#116** (paired with #94 as a WS3 pre-production gate); accepted temporary behavior = today's wiki last-writer-wins / graph co-ownership on normalized derived-slug collisions (existing behavior, not a regression). Spec v1.6 `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md`; blueprint v1.10 `docs/superpowers/plans/2026-07-21-task115-pass2-contract-revision-blueprint.md` (10 Codex rounds absorbed). §5/§6/§8/§9 updated to the ratified contract ahead of code — implementation proceeds Gates 0→4, each Joseph-approved, with baseline/comparison cohorts (gpt-5.4-mini + deepseek-v4-flash) bracketing the contract commit.
- **2026-07-21** — **🏁 Task #114 CLOSED — recovery-oriented Pass-2 parse stage.** The carrier/payload first principle made executable: the LLM response is a *carrier*, the JSON document is the *payload* — the parse stage recovers the payload with maximum tolerance for carrier noise; it may only **select** (locate the complete document), never **edit** decoded content, and declares failure only on (a) no complete decodable document or (b) recovered content failing the schema/semantic gates. A format deviation alone never fails a source. Shared `recover_json_response` owns the composition (loose `unwrap_response` → strict `json.loads` → 5-step selection-first ladder with root-preserving boundary-decode `parse_document_prefix`); `RecoveryResult.recovered` is the only success signal (JSON null ≠ failure); recovery runs **before** truncation (ratified behavior change). `boundary_recovered` + `prefix/tail_discarded_chars` telemetry threads into `recovery_rate` / `repair_rung_rate`; `tools/replay.py` consumes the same shared function (replay ≡ live parse). Motivated by the 20 gemini-3.5 carrier-noise failures (2026-07-21 cohort — 19 recoverable, 1 genuinely incomplete), curated into 20 tracked fixtures in `compiler/tests/fixtures/`. 9-commit chain `253af03`→`81e5690` on `feat/114-recovery-parse-stage`; 1379 non-live tests green. Spec `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md`.
- **2026-07-07** — **🧭 Strategic pivot — the LLM-operations tier is data-gated; #113 closes at Phase 3a (stress-test IDEA abandoned); next arc = build a comprehensive graph.** A precondition check on the live 248-entity sandbox graph showed the metacognitive analytics are **degenerate at personal scale**: grounding has no variance (214/218 canonical entities have exactly 1 source) and only 2 of 486 LINKS_TO edges cross a community boundary (4 bridge entities). This is the ratified **scale hedge** firing ([[project_ontology_purpose_kernel_question]]) and it generalizes — GraphRAG/HippoRAG would be equally degenerate at ~250 sparse nodes. **#113 Phase 3b (`stress_test`, the Named Gate) ABANDONED; #113 closes at Phase 3a.** The `kdb_graph` package + 7-tool read-only MCP server are a **retained asset** (the graph's query front door), parked to be re-prioritized after ingestion. **#83–#87 (Claim/Learn 2.0 tier) parked as data-gated.** Honest reframe: the graph's realistic present value is **canonicalization + retrieval**; the operations/metacognition tier is scale-gated; the **binding constraint has moved from code quality to corpus scale**. Next arc = **ingest the full vault-in-place** (1,586 notes, ~44× the 36-source sandbox) → comprehensive graph, then re-test the operations thesis. Review: `docs/2026-07-07-state-of-the-system.md`. Cleanup `c154595`. [[project_scale_hedge_pivot_ingest_vault]].
- **2026-06-11** — **#113 Phase 3a — read-only MCP stdio server shipped (`kdb_mcp/`).** New in-repo sibling package (NOT inside `kdb_graph` — it consumes both `kdb_graph` and `common`, so staying outside preserves the package's zero-`common` invariant; same-repo per F2, the panel consensus). A `FastMCP` server exposes **7 read tools** — `get_entity`, `graph_neighborhood`, `find_path`, `sources_for_entity`, `entities_for_source`, `resolve_search_keys`, `get_body` — each a thin wrapper over a pure adapter that opens `GraphDB(…, read_only=True)` **per call** (F5 reopen) and returns a stable **Pydantic** shape (never a raw `kdb_graph` dataclass); errors surface as the protocol `isError` envelope. SDK shapes were **verified against the installed `mcp` 1.27.2 before coding** (Context7), which caught that `from mcp import Client` doesn't exist in 1.27.2 — the in-memory test uses `create_connected_server_and_client_session(app._mcp_server)`. Two findings folded mid-build: **`resolve_search_keys` slugifies inputs** so human names ("Amortization") resolve, not slug-only (advisor catch, masked by a slug-only test); and **`config.default_graph_path()` derives from the vault root** (`<vault>/KDB/graph`) so graph + wiki content come from one KDB instance — the official dir is `~/Obsidian/KDB`, the sandbox `~/Obsidian/Vault-in-place-test-run`; the old `~/Droidoes/GraphDB-KDB` default was a stale 2.3 stray, now dead. Subagent-driven TDD (10 tasks + cleanups), final holistic review; 19 `kdb_mcp` tests, full suite **1290 green**, real-graph end-to-end smoke validated (and the live `~/Droidoes/GraphDB-KDB` correctly fail-fast on the 2.3≠2.4 schema — #112 working). Plan `docs/superpowers/plans/2026-06-11-phase3a-mcp-read-server.md`. **Next:** Phase 3b — the `stress_test` analytics composite (the Named Gate). [[project_113_graph_access_mcp]].
- **2026-06-11** — **#113 Phase 2 — `get_body` content tool shipped.** The slug→prose reader the MCP server and viewer need: `common/wiki_io.py::get_body(slug, page_type, *, root)` returns a wiki page's body (frontmatter stripped) from `KDB/wiki/<subdir>/<slug>.md`, composing the existing `paths.slug_to_abspath` + `source_io.parse_existing_frontmatter`; missing file → `ContentNotFoundError`. **Placement decision (A):** the reader lives in **`common/`** — next to the wiki path-logic it reuses — **not** in `kdb_graph`, preserving the package's verified zero-`common` dependency; the Phase-3 MCP tool and the viewer are thin *consumers* of it (the two stores stay separate, joined only at the MCP layer — F3). An hour of dialogue first untangled "what is `get_body`" (a tool, not a content-access subsystem) and surfaced a hard rigor critique → [[feedback_think_before_speaking_no_option_spray]]. Subagent-driven TDD, per-task spec+quality + final holistic review; 9 unit tests + live smoke on the real vault, full suite 1270 green. Spec `docs/superpowers/specs/2026-06-11-get-body-content-tool-design.md`. **Next:** Phase 3 (read-only MCP stdio server — gated on MCP-SDK doc verification). [[project_113_graph_access_mcp]].
- **2026-06-10** — **Graph-access package + read-only MCP server — design RATIFIED (v0.3); #112 + #113 Phase 1 landed.** Architectural reframe (the day's realization, reached only after repeated pushback — [[feedback_interrogate_anchored_premise]]): **the GraphDB is a durable asset; the compiler is one *producer*; the MCP server / viewer / KPI / O1-promotion are *consumers*; the access contract (`kdb_graph`) is owned by none of them** — so `kdb_graph` extracts into a standalone graph-access package and the compiler becomes a client. Design spec `docs/superpowers/specs/2026-06-10-graph-access-package-design.md` (**v0.3, 5/5 panel GO-WITH-FIXES** folded — Codex/Deepseek/Qwen/Gemini/Grok). A **6-model killer-app challenge** named the MCP's load-bearing consumer (its own "Gate"): the **Epistemic Load-Bearing Stress Test** — *"which of my most-relied-on ideas rest on the thinnest evidence?"* — a graph-native intersection of **PageRank × structural-hole bridge-position × SUPPORTS-degree** (metacognitive, not retrieval), with bridge-synthesis as the generative twin and **Worldview Reconciliation** (Claim layer) as the 2.0 North Star. **🏁 Task #112 CLOSED (`8d63019`)** — the unanimous panel blocker: `GraphDB._open()` ignored `read_only=True` (always opened read-write + ran DDL/migrations — a read-only open would *migrate* a mismatched DB); now passes `read_only` to Kuzu, verifies-don't-migrates, and blocks writes (`GraphDBReadOnlyError`). **Task #113 Phase 1 landed (merge `527d224`)** — package boundary formalization, subagent-driven TDD (4 tasks `2bb91fe`→`213d189`, each spec+quality reviewed): published shippable `kdb_graph.testing` (cross-package consumers stop importing `kdb_graph.tests.conftest`) + completed the public API surface (`GraphDBReadOnlyError`); 345 + 8 boundary tests green. **Next:** #113 Phase 2 (content-store accessor / `get_body`), Phase 3 (read-only MCP stdio server — gated on MCP-SDK doc verification). [[project_113_graph_access_mcp]].
- **2026-06-07** — **🏁 Task #109 CLOSED — benchmark calibration complete.** Baseline-1 (4-model cohort at `v0.5.6`) provided the cross-model spread needed for calibration. Existing rationale-based weights validated unchanged (`TOP_WEIGHTS`: quarantine 40 / graph 40 / recovery 10 / latency 10; `GRAPH_WEIGHTS`: connectivity 35 / link 30 / supports 20 / reuse 15). **τ=0.5 PINNED** (all three penalized models hit the max cap — threshold confirmed correctly calibrated); λ=0.10 remains PINNED. Promotion rule (`tools/benchmark/promotion.py`) available for the next multi-model cohort. §7 North Star doc rewritten to reflect the new orchestrate-emit → score-only architecture (the legacy `runner`/`scorer`/`scorecard`/`registry` + M0–M7 KPI system + D26–D31 weights were retired with Task #109's framework merge). [[project_benchmark_redesign_architecture]].
- **2026-06-07** — **🏁 Task #111 CLOSED — optimal per-model calls → clean-slate re-benchmark.** Two-phase tagged de-risk. **Phase 0 (`v0.5.5`):** run-provenance (`release_version` via `git describe` → header + `measurements.json`) + per-run `console.log` + leaderboard keyed on `(provider, model, release_version)`. **Phase 1 (`v0.5.6`):** pool restructure (`models.json` active / `models_dropped.json` human archive; dead dropped-guard retired → dropped id = `UnknownModelError`); **native `google-genai` Gemini handler** (`_call_gemini`, off the second-class openai-compat shim; `thinking_level:"minimal"`); `gpt-5.4-mini` `reasoning_effort:"low"` (flat, live-confirmed) + **`temperature` omitted** (GPT-5 reasoning rejects non-default temp; nullable per-model pool field); a **retry-telemetry fix** (re-prompt recoveries now counted in `recovery_rate`/`retry_load` — SDK transient retries excluded, matching Pass-1); and **per-source token in/out on the `pass-1 ✓`/`pass-2 ✓` console lines → `console.log`**. **baseline-1 (4-model cohort):** **gpt-5.4-mini #1 on graph quality** (84.67, 0 quarantine) once called correctly — overturning #109's handicapped "deepseek best" and validating the thesis (bad calls, not model quality, skewed #109) — **but `deepseek-v4-flash` stays the default on cost** (7.2× cheaper, also 0 quarantine, 2nd-best graph). `gemma4-12b-qat-128k` tried then **archived** (local 12B too slow / majority-quarantined / couldn't finish). **Phase 2 (`json_schema`, `v0.5.7`) SHELVED — data-mooted:** the default was already 0-quarantine under `json_object` + the coerce ladder; the real win was the **per-provider thinking/reasoning-disable latency cut (~30–70%)**, not structured output. Strict json_schema would grammar-mask our generative `body` (quality risk), can't express our semantic contracts (slug-format / body↔links — owned by the reconciler+coerce layer), and contradicts coerce-don't-reject ([[feedback_coerce_dont_reject]]). The `v0.5.6` tag was moved in-place 3× across Phase 1 to fold mid-cohort fixes (roadmap unchanged). Spec `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md`. [[project_111_optimal_model_calls]].
- **2026-06-07** — **Task #110 — user-owned model pool + cost/ctx diagnostics.** Merged to `main` via `feat/110-models-json-pool` (16 commits, subagent-driven TDD, per-task spec+quality reviews + a final holistic review; 1209 non-live tests; live-smoke clean on default `deepseek-v4-flash`). Reinstates the user-owned model pool retired with the #5 engine, re-homed to **`common/models.json`** (pool + curation ledger) + **`common/model_pool.py`** `resolve_models_json(id) → ModelSpec` (the lookup layer; `call_model.py` engine untouched): alias→provider+knobs, an **absolute dropped-guard** (`UnknownModelError`/`DroppedModelError` — dropped ids always error, even with `--provider`), and `words×1.3` ctx-estimate helpers. `kdb-orchestrate --model <id>` now resolves the pool; `--provider` demoted to an escape hatch with a conflict-check. **`cost_usd`** restored (pricing × **aggregated** tokens — the diagnostic lost with the #5 scorer) on BOTH telemetry paths (Pass-2 `RespStatsRecord` + Pass-1 sidecar `SidecarPayload`). A proactive **input-side ctx-overrun guard** (`est_input+requested_output ≤ ctx_window`) runs before the model call in both passes → skip-and-quarantine, **no API spend**, routed through the existing per-source quarantine (synthetic `TokenOverrun`, persisted structurally in the sidecar). The holistic review caught a **must-fix**: `use_completion_tokens`/`extra_body` were resolved but not threaded to the passes — now fixed, which makes thinking-disable actually apply and unbreaks `gpt-5.4-mini`. Plus a semantic **`thinking` field** (per-provider translation to the disable-param; verified alibaba `enable_thinking:false` + deepseek `thinking:disabled`, gemini/openai/xai no-op+TODO per "no guessed param on a paid call"), and **`deepseek-v4-pro` un-dropped** (permanent discount). New reference: **`docs/reference/model-provider-api-calls.md`** (per-provider call shapes, structured-output + reasoning-disable matrix). Follow-up #111 (structured-output `json_schema` upgrade + Gemini native handler). Deferred-and-documented: `max_output_tokens` clamp (untriggered), Pass-1 failed-source `cost_usd=0.0`. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-06-models-json-pool*`.
- **2026-06-06** — **Benchmark redesign framework landed + Pass-1 robustness closed (Tasks #109 + #108).** Merged to `main` `610e2c8` (subagent-driven, 13-task TDD plan, two-stage review per task; 1338 non-live tests). **#109 — benchmark redesign framework** (quality-only, GT-free, two families never blended): `common/measurement.py` projects existing telemetry into a unified `PassCallMeasurement` (P1+P2) + `RunMeasurementHeader` — a **logical view, not a new store** ([[feedback_no_parallel_storage_to_authority]]); `compiler/kpi/` computes the **processing** family (`quarantine_rate` · `intervention_burden` · `latency`, per-1M-token normalized) and the **graph** family (scored `dangling_link_rate` alias-aware + 4 watched diagnostics: entity-reuse · connectivity · orphan · search-key-resolution + 5 read-only diagnostics); `kdb-orchestrate --emit-kpis` writes repo `benchmark/runs/<id>/measurements.json` (reset-surviving — must emit *inside* the run since the sandbox graph is wiped before the next model); `kdb-benchmark score <run-id…>` Borda-ranks the latest run per `group_key` within a `corpus_fingerprint` cohort; watched→scored **promotion rule** (CoV>0.2 ∧ IQR-floor ∧ Spearman<0.7). **Weights, final scored-set selection, and promotion are PARKED to post-run-1 calibration** — the one step needing live cross-model spread (data-before-principle; setting them now would be the blind-anchoring the promote-on-data mechanism exists to avoid). **#108 — Pass-1 robustness** (NOT a port of #106's multi-rung ladder — that would be premature abstraction): Pass-1 `final_status` + aggregate token/latency telemetry persisted into the sidecar on every write path (feeds `PassCallMeasurement.from_pass1`, makes Pass-1 failures observable), and the shared `common/util/json_escape_fix` wired in before `json.loads` (one preventive, re-validation-gated rung); full ladder deferred until a real Pass-1 repairable class appears. **Validated by run-9** (`--emit-kpis`, `deepseek-v4-flash`): clean `measurements.json`, every header/scored/watched/diagnostic field populated. **Calibration watch surfaced by run-9:** `dangling_link_rate=0.0` looks perfect, but `entity_reuse 2.6%` / `graph_connectivity 14.5%` / `search-key-resolution 24.6%` expose a sparse, fragmented graph — confirming the design's caveat that dangling-rate must never stand alone (density/reuse are prime promotion candidates). **Open to close #109:** Joseph fires the ≥3-model cohort → `score` → set weights + run promotion. Specs: B1/B2/B3 under `docs/superpowers/specs/2026-06-05-*`; plan `docs/superpowers/plans/2026-06-05-benchmark-implementation.md`. [[project_benchmark_redesign_architecture]] · [[project_json_repair_coerce_ladder]]
- **2026-06-02** — **🏁 Release `v0.5.3` — Pass-2 robustness ladder (Task #106).** Deterministic, re-validation-gated repair ladder so Pass-2 recovers from the two confirmed recoverable LLM malformations instead of relying on a lucky retry. **Rung-1** targeted JSON backslash-escaping (`common/util/json_escape_fix`, content-preserving — the 5-model design panel replaced `json-repair` with this; **no new dependency**). **Rung-2** slug coercion (`common/paths.collapse_slug`: lowercase+collapse+strip, decision B) + propagation/collision-guard (`compiler/repair.coerce_slugs_and_propagate`). **`semantic_check` moved inside the attempt loop (LB2)**; compositional repair telemetry on `RespStatsRecord`. **run-8 clean** (`exit_reason=ok`; graph 172 Entity / 29 Source / 12 Domain / 173 `BELONGS_TO` / 177 `SUPPORTS` / 409 `LINKS_TO`; 1213 non-live tests). 5-panel design review (GO-WITH-CHANGES, all folded); subagent-driven (8-task TDD), two-stage review caught 2 real bugs. Viewer: zoom-gated captions + zoom readout. Merged `2fb5d0e`. Follow-up: Pass-1 ladder → Task #108. Plan: `docs/superpowers/plans/2026-06-02-task106-json-escape-slug-coercion.md`.
- **2026-06-02** — **🏁 Release `v0.5.2` — codebase realignment, Phase B (Task #105).** Split the `kdb_compiler` monolith (+ `graphdb_kdb`, `kdb_benchmark`) into **six peer packages** (`common` / `ingestion` / `compiler` / `kdb_graph` / `orchestrator` / `tools`), leaf-first, **move-don't-rewrite** (executed subagent-driven, 13 tasks). **B.3 dependency contract guard-tested** (actual import graph ≡ contract; one documented `orchestrator→tools.cleanup` exception). One real restructure — the `resp_stats_writer` split (`common/llm_telemetry` generic + `compiler/resp_summary`), lifted `parsed_summary` gate byte-identical. Deferred Phase-A cleanups landed (`failure_stage="repair"`, `JOURNEY` noun). **Zero behavior change**, proven by **run-7** (`exit_reason=ok`; graph 193 Entity / 29 Source / 10 Domain / 195 `BELONGS_TO` / 202 `SUPPORTS` / 468 `LINKS_TO` ≡ run-6 standard). 1191 non-live tests green. **5-panel code review GO-WITH-FIXES** (Codex/Deepseek/Qwen/Gemini/Grok); all must-fixes folded (F1–F6); 3 non-blocking follow-ups → Task #107. Merged `f28220e`. Plan: `docs/superpowers/plans/2026-06-02-phase-b-package-split.md`; review synthesis: `docs/superpowers/specs/2026-06-02-phase-b-review-synthesis.md`.

- **2026-06-02** — **🏁 Release `v0.5.1` — codebase realignment, Phase A (Task #105).** Architecture-level refactor so the implementation reflects the decided architecture (two pipelines — *ingestion* / *compiler* — over a *graph* substrate, conducted by an *orchestrator*, + *tools* and a *common* leaf). Thesis: **terminology debt IS the architecture problem.** 5-panel ratified (Codex/Deepseek/Qwen/Gemini/Grok-build); one refactor in two sequential phases — **A (fix-in-place) shipped, B (package split) next**, both before 0.6. Phase A retired the legacy `kdb_compile.py` batch driver + 427-ln `run_journal.py` + dead `planner`/`run_compile` + 5 CLI bindings; fixed 2 layering inversions (`common` is now a true leaf, guard-tested); renamed `reconcile→repair` · `patch_applier→page_writer` · `source_state_update→manifest_writer` · `validate_compiled_source_response→validate_source_response` · `ingestion/→enrich/` (+`run_journal→enrich_journal`); established the **single Kuzu door** (10-fn read API in `graphdb_kdb/queries.py`; `graph_context_loader→context_loader` authors zero Cypher, byte-identical port); rewrote §5 + swept stale refs. **Zero behavior change**, proven by **run-6** (`exit_reason=ok`: 29 compiled / 7 noise / 0 quarantined / 0 invariant; finalize 478 links, 0 orphans; graph 180 Entity / 29 Source / 10 Domain / **100% `BELONGS_TO`**) ≡ the run-5 standard. 1175 non-live tests green. Blueprint+plan: `docs/superpowers/{specs,plans}/2026-06-0{1,1}-codebase-realignment*`. See `docs/RELEASES.md`.
- **2026-05-31** — **🏁 Release `v0.5.0` — reliable orchestration.** Gated on a clean run-5 (`exit_reason=ok`: 36 scanned / 29 compiled / 7 noise / **0 quarantined / 0 invariant**; finalize 449 links, 0 orphans; graph v2.4: 181 Entity / 29 Source / 10 Domain). Bundles: #96 quarantine-and-continue, D1-A derived domains, #102 live stdout progress, #103 domain-scoped Pass-2 context, #97 GraphDB viewer, and the run-4-finding fixes (#104: Pass-1 coercion + Pass-2 parse/schema retry — which recovered run-4's lone quarantine in run-5). 1219 non-live tests green. Next arc: 0.6→1.0 ingestion pipelines. See `docs/RELEASES.md`.
- **2026-05-31** — **Task #104 — Pass-1 coercion + Pass-2 retry (run-4 findings).** Pass-1 coerces benign shape deviations instead of rejecting (truncate >10 `entity_search_keys` to 10; let `source_type='other'` pass without `other_reason`); Pass-2 retries on a recoverable bad-JSON emission (parse/schema), mirroring Pass-1's retry. Findings + resolutions in `docs/archive/tasks/run-4-findings.md`. Principle: coerce benign deviations, retry recoverable emissions, reject only the genuinely unrecoverable.

- **2026-05-31** — **Task #103 — T2/T3 domain-scoped retrieval (same-domain gate).** The Pass-2 context snapshot is now a positive pull from the source's Pass-1 domain only: `build_context_snapshot` scopes the T2/T3 candidate universe to entities `BELONGS_TO` the source's domain (`Domain.name`); T1 (the source's own SUPPORTS) unchanged; no padding (short/empty same-domain > off-domain noise); no-domain sources fall back to the full graph. **Overrides** the ratified D3 (C, coordinate-not-gate) → hard gate, on the rationale that context-scoping (anti-entropy) is distinct from link-creation (free) and Discover (future query-time); override recorded in `ontology-blueprint-V1.md` §7.

- **2026-05-31** — **Task #102 — orchestrator live progress on stdout.** Replaced #101's stderr/info-gated per-source snapshot with a default-on, blow-by-blow stdout narrative: per-source `[n/total]` header, `pass-1`/`pass-2` started→`✓ <elapsed>` lines, running counts, inline `⚠` alarms, reconcile/finalize timestamps. `EventRecorder`'s console renderer is now decoupled from the JSONL severity filter (renders every milestone regardless of `--log-level`); `--log-level` governs only file verbosity; `--quiet` silences the console. Two new `pass1_enrich_started`/`pass2_compile_started` events. Event JSONL + `last_orchestrate.json` unchanged.

- **2026-04-18** — **M0 scaffold.** KDB compiler architecture + schema-gated prompt/response contract (Task #4 family).
- **2026-04-21** — **Validator + reconciler live on real vault.** `pairing_omission` auto-heal proven on two back-to-back live runs (Task #65 / M1.7).
- **2026-05-10** — **Iteration #2 begins.** Kuzu reframed as architectural primitive; KDB becomes raw-text → knowledge-graph compiler (Task #63 family).
- **2026-05-14** — **GraphDB-KDB operational.** Schema v2 (`Entity` / `LINKS_TO` / `SUPPORTS`) + ingestor + verifier + snapshot + rebuilder + analytics (PageRank / Louvain / structural-holes) all green (Task #63 closure).
- **2026-05-16** — **Graph context loader lands.** `kdb_compiler.graph_context_loader` reads context from GraphDB (Task #70.1).
- **2026-05-17** — **LOOP CLOSED.** Manifest → graph substitution complete: D49 removes `manifest.json` as context authority; D50 strips ontology data from `manifest.json` (file-meta only); D51 establishes GraphDB as live ontology authority. Empirical proof via cold-start widening (graph 17–23 pages vs manifest 0–8) (Tasks #70, #71, #73).
- **2026-05-20** — **Canonicalization layer lands.** Stage 6 `canonicalize` inserted; `Entity.canonical_id` + `ALIAS_OF` edges shipped (Task #74).
- **2026-05-21** — **V0 step-3 ops regression suite locked.** Typed traversal + shortest-path direct-unit-guarded; `@pytest.mark.bench` opt-in pattern established (Task #81). **Schema v2.1 Domain field** shipped: `Domain` node + `BELONGS_TO` edge (Task #76).
- **2026-05-22** — **Three-iteration retrospective filed** ([`docs/JOURNEY.md`](JOURNEY.md)). This changelog itself is the mitigation for Lessons §5 (milestone-level signal was missing pre-this-doc).
- **2026-05-22** — **Round 6 closes — "Learn" operationalized.** Three Learn mechanisms ratified (Belief Revision / Identity Refinement / Abstraction & Principle Induction) + Hypothesis Promotion as first-class boundary contract per **(a+)** decision; M2 + M3 reclassified as Analysis-feeding-[C] Create; project's first articulated position on [C] Create recorded ([`docs/reference/what-is-ontology-for-V1.md`](reference/what-is-ontology-for-V1.md) §9.4; Task #82 closure; Tasks #83–#86 filed).
- **2026-05-23** — **Predeclared eval criteria + probe set ratified for #83/#84.** Task #87 v2 (eval criteria — 3 ops O1/O2/O3, P-On-N / F-On-N criteria, HW-1..HW-11 hedge-watch rules, `eval_config` block per Codex+Deepseek+Qwen panel review) + Task #87.1 v1 (20 probe scenarios across 7 §7.1 coverage axes, 8 OQs OQ-S1..S8 surfaced, D-87.1-1..10 decision gates ratified) both shipped. **Mutation-eval discipline adopted** (vs Task #75's retrieval-eval): pre-state + input → expected post-state + invariants preserved. **Unblocks #83/#84 implementation start.**
- **2026-05-23 (afternoon)** — **DeepSeek-V4-Flash returned to active pool via direct API.** The 2026-05-15 "capability gap" diagnosis was a routing artifact, not a model deficiency: Alibaba's OpenAI-compat layer was stripping/mis-handling `response_format` for non-Qwen models. Empirical fire on canonical corpus: S0=1.000, M1-M5=1.000, M7=3578ms (2.75× faster than Alibaba's best historical 9830ms). Ties #1 on cost-quality frontier with `gemini-3.1-flash-lite` at FINAL=0.956 (Gemini wins latency 4×; DeepSeek wins cost 50%). `deepseek-v4-pro:direct` dropped same-session (strictly dominated by Flash:direct — 3.2× cost, 2.7× latency, identical quality). **Meta-lesson:** control models must match the model-under-test's vendor/routing relationship, not just the routing layer.
- **2026-05-23 (Saturday afternoon, late)** — **#83/#84 O1 GREEN v1.5 — 15/15 probes (100%), zero xfail.** Closed S12 + S18 (the remaining semantic-contradicts deferral class) via: (a) **blueprint amendment narrowing D-83/84-2 `contradicts`** to polarity-flip-only — narrative reframing across different `predicate_class_canonical` is correctly captured by `classification_drift=true` → `human_review` per D-83/84-8 Part D, NOT by structural classifier detection (D-83/84-3 #1 forbids LLM-at-classifier). New **OQ-30 (predicate-class antonym registry)** filed for future load-bearing curation tied to HW-1 vanity-graph hedge. (b) **S12 rewritten** with a real polarity flip (`denies`↔`affirms`) preserving its `[fp_drift=true, classification_drift=false] → auto_promote_with_note` drift-cell role. (c) **S18 classifier patch** per OQ-18 branch B (retracted-no-sibling returns `no_counterpart`, does NOT engage retracted as counterpart) + LINKS_TO fallback gated off when `retracted_family_id` is set to preserve branch B precedence over LINKS_TO-implicit-counterpart. (d) S18 probe normalized so candidate envelope's `counterpart_status`/`relation_kind` reflect the shared-classifier output per D-83/84-3 #1 (Analysis-time and Promotion-time identical for identical input). Full suite: 999 pass / 1 skipped / 0 xfail / 0 fail (analytics excluded). The 4 latent debts surfaced in v1.4 remain explicitly tracked (mutator object-Entity/LINKS_TO writers, threshold-N gate for reinforces, Tier-1 EVIDENCES reconstruction, LINKS_TO schema enrichment) — to be addressed when verifier tightens after promotion-replay lands.
- **2026-05-23 (Saturday afternoon)** — **#83/#84 O1 GREEN v1.4 — 14/15 probes (93%).** α-split closed three sub-arcs (S06 / S07 / S05) via *minimum-to-GREEN* changes once the harness-scope lens (disposition + drift signals only — no structural post-state assertions) was correctly applied. S06: sentinel hash was the only blocker. S07: classifier else-branch rule split per D-83/84-2 default action table (different object_slug + refines_truth=false → `qualifies_or_extends`, not `supersedes`); `object_slug` added to candidate envelope. S05: LINKS_TO-implicit-counterpart classifier fallback — when no Claim in family AND `counterpart_links_to_ref` points to a real LINKS_TO, treat as `candidate_counterpart_found` + `reinforces` (trust-the-hint on polarity/predicate — schema v2.2 LINKS_TO carries only run_id/created_at). **Tier-1 EVIDENCES reconstruction + object Entity/LINKS_TO writer in mutator + LINKS_TO predicate-field schema enrichment all stay deferred as latent debt** — observably untested at current verifier strictness (F3 shared-keys-only diff per morning ratification); will be addressed when verifier tightens after promotion-replay lands. Remaining 2 xfail (S12/S18) are a separate semantic-contradicts deferral class (LLM-classifier vs richer relation_kind authority).
- **2026-05-26** — **NW-7 v0.2 ratified — 21-entry source_type controlled vocabulary.** Single-session arc closed: v0.1 (20 entries — refined §9.1 placeholder with 4 new entries + 1 rename + 1 drop) → 5-CLI panel review (Codex + Qwen CLI/qwen3.7-max + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high; **5/5 guardrail-clean; agy 3-for-3 on post-strike re-trial across Task #89 v0.1 + round-2 + NW-7 v0.1**) → v0.2 fold (5/5 unanimous **F-1** fixed — D-NW7-4 rationale rewritten to match operational §3.3 rule: **rhetorical form wins over recording medium**; 3/5-convergent fixes locked — **F-2** `chat-log` added as 21st entry (new Conversational / interactive cluster), **F-3** new **D-NW7-6** scope-text discipline (12 "Distinguished from X" clauses stripped from §2; §3 sole boundary authority), **F-4** `transcript-interview` → `interview` rename with alias; Tier-4 batch fold of 7 1/5 refinements). Final: 21 source_types in 6 readability clusters (written-prose 10 / spoken-transcribed 3 / conversational-interactive 2 NEW / primary-document 3 / vault-meta 2 / residual 1); minimal 4-field config schema (`id` / `display` / `scope` / `aliases`) Pass-1-owned at `kdb_compiler/config/source_types.json`; 2 aliases enable rename migration without backfill (`transcript-video` ← `transcript-youtube`, `interview` ← `transcript-interview`). 5 new OQs (OQ-NW7-6..10) — telemetry-driven or Component #1 implementation. `other_reason` schema field flagged for Task #89 v0.2.x (NOT NW-7 vocab change). **NW-7 ratification CLEARS the precondition for Pass-1 implementation plan-lock** (Joseph 2026-05-26). Memory candidate: [[feedback_gemini_review_only_guardrail]] update with agy 3-for-3 successful re-trial — empirical evidence to re-instate agy as full panel member without one-strike conditional. Unblocks `superpowers:writing-plans` for Pass-1 ingestion implementation arc. Artifacts: `docs/archive/tasks/task89-nw7-source-type-list-v0.2.md` (production-ready vocab) + `docs/archive/tasks/task89-nw7-source-type-list-v0.1.md` (v0.1 lineage) + 5 reviewer responses + dispatch prompt (audit trail).
- **2026-05-27** — **Task #90 v1 ship — context-loader T2-rewrite live-verified.** Closes the Pass-1↔context-loader tunnel-meeting-in-the-middle locked by D-89-20. `graph_context_loader._build_t2` now dispatches via `T2Mode` enum (STRUCTURED v1 default / LAYERED A+B benchmark / LEGACY backward-compat). STRUCTURED branch consumes Pass-1's `entity_search_keys` from frontmatter via shared `kdb_compiler/source_io.py` helper (D-90-10 — fixes B-1 planner→compiler circular import + Gemini F-4 double-disk-read); three-state handling per D-90-8 (A: legacy fallback for pre-Pass-1 sources / B: structured emit / C: empty-list honored as no-anchors signal, no fallback). Alias-aware `Entity.slug` resolver — simple 1-query default with Python-decided path precedence (**drift-from-plan disclosure:** 1-query chosen over plan's 2-query for Path 3 dead-target disambiguation correctness; parity-test enforces simple ≡ batch functional identity across 12 probe cases); Codex-tested batched resolver as `KDB_T2_RESOLVER=batch` escape hatch. Pass-1 prompt v1.0.0 → v1.1.0 amendments deployed (anchoring sentence with exact-PK comparison + Cat 2/3/4 tightening + ≥3 domain-diverse examples + conjunctions-in-slugs clarification); `PASS1_PROMPT_VERSION` constant migrated to enable §10 watch-for #7 hit-rate correlation. **E.1 live smoke GREEN 2026-05-27 (11.33s, ~$0.01):** synthetic value-investing source → Pass-1 emitted 6 `entity_search_keys` → ContextSnapshot pages=4 with seed entities resolved 4/4 against test GraphDB (`['intrinsic-value', 'margin-of-safety', 'value-investing', 'warren-buffett']`). E.2 ship gate satisfied at prompt-builder layer (non-live plumbing test; Deepseek F-5 unverified-assumption closed without API spend per advisor reframe). **Legacy sunset gated on D-90-12 3-part AND-gate** (corpus 100% enriched + NW-9 cold-start density ≥ + NW-9 precision ≥). Single-day blueprint→ship cadence mirroring Task #89 marathon: v0.1 morning (Joseph ratified Option A + T2Mode mechanism + Pass-1 prompt inlined for panel) → 5-CLI panel afternoon (Codex + Deepseek + agy/gemini-3.5-flash-high + Grok + Qwen; **5/5 guardrail-clean; agy 4-for-4** on post-strike re-trial cycle — re-instatement holds without conditional) → v0.2 fold (3 bugs caught: B-1 circular import + B-2 dead canonical_id targets + B-3 §2.5↔§3.3 N+1 contradiction; 5 new decisions D-90-8..D-90-12; all 10 unique panel catches + 6 Pass-1 prompt amendments folded; zero Joseph vetoes) → Phase A-E shipped (`71f8ef9`→`68ee371`) → E.1 live-fire close. Test footprint: 1115 → 1116 pass. **Task #90 status flipped to closed; Pass-1↔Pass-2 tunnel architecturally complete.** NW-9 benchmark (gated on ~50–200 enriched sources) filed as separate sibling task to time legacy sunset. Artifacts: `docs/archive/tasks/task90-context-loader-t2-rewrite-blueprint.md` v0.2 (§13 amendments + §14 reviewer-convergence); `docs/superpowers/plans/2026-05-27-task90-context-loader-t2-rewrite-implementation.md` (5-phase impl plan); 5 reviewer responses; `docs/archive/handoffs/session-handoff-2026-05-27-task90-impl-done-e1-pending.md`.
- **2026-05-30** — **🎯 First complete end-to-end `kdb-orchestrate` run (run-3) — clean, real corpus.** After run-1 (Pass-1 null-`override.llm_original` fail-fast → fixed by #95) and run-2 (Pass-2 fail-fast: deepseek emitted malformed JSON on a 95KB source — `JSONDecodeError`, not truncation; `stop_reason=stop`), run-3 completed with `exit_code=0` / `exit_reason="ok"` over the sandbox vault (`~/Obsidian/Vault-in-place-test-run`): **36 scanned · 36 enriched · 29 compiled · 7 noise · 0 failed · 0 quarantined**. The run-2 Pass-2 failure was root-caused to a **missing `json_mode`** on the compile call (Pass-1, same `deepseek-v4-flash:direct` model, already requested it) and fixed in **`1d668bf`** (`json_mode=True` on the Pass-2 `ModelRequest` → provider-constrained valid JSON); parse-retry deliberately **not** added (every source was `attempts=1`; the one observed retry never recovered — no evidence warranted, [[data-before-principle]]). **Finalize ran over the full committed set** (`links_wired=451`), dissolving #94's stranded-`LINKS_TO` class end-to-end. **Graph verified coherent**: 178 entities · 29 sources · 439 LINKS_TO · 185 SUPPORTS · 4 domains · 29 BELONGS_TO · **0 orphans** (7 noise correctly stay out of the graph). This single run validates the full arc: **#95 Pass-1 contract + json_mode Pass-2 + #96 observability/quarantine + #94 dissolution** — all green on real corpus. **Cost: ~$0.14 for all three runs** combined on `deepseek-v4-flash:direct` (~$0.05/full run) — model selection is settled on price; quality is the only open axis (→ benchmark-redesign arc). Run summary: `<vault>/KDB/state/last_orchestrate.json` (run `2026-05-30T15-53-39_EDT`). Memory: [[project_run3_next_sandbox_vault]].
- **2026-05-30** — **Task #96 path ratified — orchestrator observability before quarantine.** Real-run-1 proved the `kdb-orchestrate` tunnel works but exposed a missing operational substrate: no structured event log, no severity taxonomy, weak failure evidence, and no production-grade invariant checks. Joseph ratified **B then C**: first add a structured observability/error foundation (`OrchestratorEvent` JSONL under `state/runs/<run_id>/`, severity taxonomy `debug` / `info` / `warning` / `source_quarantine` / `run_fatal` / `invariant_violation`, explicit invariant checks instead of bare Python `assert`, richer `last_orchestrate.json`, raw-response persistence on model failures, and source-state lifecycle naming cleanup from deprecated `compile_state` to `run_state` schema v3.1); then revise D-91-8 fail-fast into quarantine-and-continue so source-local failures do not kill the batch and finalize always runs over committed sources, dissolving #94's stranded deferred `LINKS_TO` class. C1 now persists source-local failures as `run_state=error_ingest|error_compile|error_commit` plus structured `last_failure`, preserves retry eligibility by not advancing `last_compiled_hash`, and exits completed quarantine runs with `completed_with_quarantines`. C2 proves finalization runs over the committed set after later quarantines, wiring deferred `LINKS_TO` and writing `compile_result.json`; all-quarantined runs skip finalization with visible `finalize_skipped` evidence. **C3 (severity-driven circuit breaker) DEFERRED 2026-05-30** — attended runs + `--limit N` (#99) cap blast radius and C1/C2 surface all-quarantined runs without masking, so thresholds wait on a measured baseline; revisit on first real multi-source run or unattended scheduling. **D-96-1** narrows D-91-8 fail-fast to run-fatal scope (source-local `source_quarantine` continues; `run_fatal`/`invariant_violation` still abort). **Task #96 CLOSED** — full non-live `kdb_compiler/` + `graphdb_kdb/` suite green (1 live smoke skip). Blueprint: `docs/archive/tasks/task96-orchestrator-error-handling-blueprint.md`.
- **2026-05-26 (late night)** — **Task #89 v0.2.2 closure — Pass-1 ↔ Pass-2 ↔ GraphDB tunnel ends meet (live-verified).** Phase E closed in single late-night session: code shipped + live integration test green. **Architectural amendments (decided earlier this evening, ratified in v0.2.2 blueprint)**: **D-89-18 RETRACTED** — the "compile LLM merges summary + key_themes" rationale was load-bearing only when key_themes had no other structural channel into the graph. Replaced by **D-89-19** (mechanical append: `Source.summary = Pass-1.summary + ". Themes: ..."`; persisted to GraphDB — single source of truth, Pass-2 view matches persisted state) + **D-89-20** (drop `key_entities` entirely; add `entity_search_keys` ≤10 kebab-case slugs as a purpose-built Pass-1 field whose sole consumer is the future T2-rewrite — Task #90 input contract). **D-89-17 partial retract** — "TREAT key_entities as seed candidates" clause removed; rest stays. Pass-2's source_meta_dict shrinks to `{domain, source_type, author, summary (with themes appended)}` — cleaner contract, less ceremony. **Bug #1 fix** — `Source.source_type` no longer hardcoded to `obsidian-kdb-raw`; Pass-1's classification now flows through `_write_source_meta()` to the GraphDB Source node (small, independent fix). **Bug #2 DISSOLVED** — there is no merged_summary to land anywhere; mechanical append goes directly to `Source.summary`. **E.1 live acceptance test green** (39.19s; 1 Pass-1 enrich + 1 compile call against `deepseek-v4-flash:direct`): all 5 §10.5 contract checks pass — C1 domain populated; C2 author populated; C3 source_type matches Pass-1 (Bug #1 fix verified); C4 Source.summary contains Pass-1 verbatim + "Themes: ..." append (D-89-19 verified end-to-end); C5 frontmatter has `entity_search_keys` and no `key_entities` (D-89-20 verified). Architectural lesson — **consumer-purpose test for Pass-1 fields**: ask "does Pass-2 derive load-bearing value from this field?" — if not, the field's real consumer lives elsewhere (e.g., context_loader) and the producer's job should be shaped accordingly. Both `key_themes` (kept for upstream T2 + mechanical-append summary tag) and `key_entities` (dropped — subsumed by purpose-built `entity_search_keys`) were re-evaluated under this lens. Memory: `[[feedback_no_imaginary_risk]]` reinforced (caught in transition-guardrail hedging during deliberation); `[[feedback_gemini_review_only_guardrail]]` candidate update (agy 3-for-3 on post-strike re-trial). Artifacts: `docs/archive/tasks/task89-component1-enrichment-blueprint.md` v0.2.2 (D-89-19/D-89-20 in §12; v0.2.2 amendments table in §14); `docs/archive/handoffs/session-handoff-2026-05-26-task89-evening-v0.2.2-key_themes-loop-close.md` (architectural arc); E.1 acceptance test at `kdb_compiler/tests/test_pass1_end_to_end.py` (the 5-contract collect-all-failures harness). Implementation footprint: ~12 files edited (Pass-1 schema/prompt/embedder/enrich + compiler.py + prompt_builder.py + 5 test files + ingestor.py for Bug #1); net code-line delta near zero (architecturally simpler, not larger). Task #89 status flipped to closed; Task #90 (Context-loader T2-rewrite) input contract locked.
- **2026-05-26** — **Task #89 Component #1 (Enrichment) blueprint v0.2.1 — Pass-1 ↔ Pass-2 contract locked.** Two-day deliberation arc closed. **Day 1 (2026-05-25)** — v0.1 drafted via brainstorm; all-CLI 5-reviewer panel (Codex + Qwen CLI/qwen3.7-max + Grok Build + deepcode CLI + agy/gemini-3.5-flash-high — project's first all-CLI panel; **agy completed 2-for-2 on one-strike re-trial**); round-1 property survey + round-2 architecture review both clean (5/5 guardrail-honored). **Day 2 (2026-05-26)** — Joseph-led mid-deliberation reframe locked four substantive decisions beyond panel convergence: **D-89-12** Option B (no wikilinks/corpus_index from Pass-1 — corpus_index recognized as stripped-down GraphDB at wrong place/time; compile owns LINKS_TO resolution against live GraphDB; v1.1+ enhancement deferred via Deepseek B' hook). **D-89-13** structured-JSON-then-deterministic-embed (LLM returns JSON envelope; deterministic post-processor serializes to YAML and atomically writes; body never present in LLM output). **D-89-14** D-88-11 amended in parent blueprint (commit `092b44f`) — Daily Notes default to `force_noise` via post-LLM path-based override; LLM judges content substance only, never instructed to detect diary shapes. **D-89-15** LLM runs on every in-scope source; no pre-LLM short-circuit (audit signal preserved). **Evening session** added three more decisions after Joseph's "what is frontmatter FOR" reframe collapsed multi-consumer thinking to a singular criterion: *every component in the frontmatter must be meaningful and useful to compile + GraphDB construction*. **D-89-16** frontmatter sectionalized — GraphDB-input section (consumed by Pass-2) + Audit section (Pass-2 ignores; user-visible + replay-corresponding). **D-89-17** compile consumes frontmatter in v1 (NOT v1.x amendment as v0.2 had deferred) — rescopes OQ-89-12 from 10-line strip-and-discard into full integration enhancement; required Source schema additions: `Source.summary`, `Source.author`, `Source.domain`. **D-89-18** compile LLM merges summary + key_themes when writing Source.summary (forces LLM to engage both, not pass-through). Five new principle memories captured / sharpened: [[feedback_obsidian_wikilinks_are_vanity]], [[feedback_sources_stay_static_intrinsic_frontmatter_only]], [[feedback_integration_preconditions_are_architectural]] (cautionary: assistant proposed strip-and-discard for OQ-89-12 — Joseph called out the architectural failure), [[feedback_prompt_template_definition_plus_examples]], and sharpening of [[feedback_no_edge_predeclaration_no_hints]] (examples-for-shape OK; examples-for-edges NOT). Artifacts: `docs/archive/tasks/task89-component1-enrichment-blueprint.md` v0.2.1, `docs/archive/tasks/task89-deliberation-wikilinks-frontmatter.md` (full A vs B vs C + "what is frontmatter FOR" lineage), 5 round-2 review files, parent blueprint D-88-11 amendment. **Next:** writing-plans for Pass-1 ingestion implementation; compile-side integration follows after Pass-1 ships ("tunnel ends meet in the middle"). Commits: `0548ca3` (v0.1 + properties survey), `6eb793f` (round-1 panel), `70b6647` (round-2 prompt extraction), `c3e93d9` (round-2 panel + deliberation locked Option B), `092b44f` (parent blueprint D-88-11 amendment), `651c8f3` (v0.2 fold).
- **2026-05-25** — **NW-4 v0.4 ratified — 23-domain canonical Pass-1 vocabulary.** Three-iteration arc closed in one session: v0.2 (24 domains, panel-reviewable) → 5-reviewer external panel (Codex + Deepseek + Qwen + Gemini Pro Deep Research + Grok) → v0.3 fold (panel feedback + new **D-NW4-5** no-pre-declaration philosophy: "don't pre-declare edges, cross-cut hints, or 'for example' connections in scopes; LLM decides edges via GraphDB architecture" + parent blueprint `sub_domain` bug fix per Codex F-1 + Deepseek F-1) → v0.4 fold (Joseph review + new **D-NW4-6** boundary-axis framework: vertical (↑) abstraction-stack / horizontal (↔) lens-or-form / temporal (⇄); §4 restructured by axis + `arts` → `arts-design` (scope broadened to include graphic/industrial/interaction/residential design); `equity-research` → `personal-finance` (scope absorbs retirement financial planning + tax strategies + portfolio construction); `retirement-lifestyle` + `food-drinks` → `lifestyle` merger (broader: travel, collections, home design, retirement activities); `ai-ml` scope adds GraphDB + ontology as AI harness; `economy-markets` scope adds economic data + statistics). Final: 23 domains in 6 readability clusters; minimal 4-field config schema (`id` / `display` / `scope` / `aliases`) Pass-1-owned; aliases enable rename migration without backfill. Memory: [[feedback_no_edge_predeclaration_no_hints]] generalizes D-NW4-5 for all KDB ontology design going forward; [[feedback_gemini_review_only_guardrail]] updated to distinguish `agy` / `gemini-3.5-flash` (dropped) vs Gemini Pro Deep Research / `gemini-3.1-pro` in chat (acceptable; verbose but substantive — re-evaluate `agy` when `gemini-3.5-pro` lands). Unblocks #89 Component #1 (Enrichment) deep-design (next blocker). Artifacts: `docs/archive/tasks/task88-nw4-domain-list-v0.4.md` (production-ready vocab) + `docs/archive/tasks/task88-nw4-domain-list-v0.3.md` (intermediate checkpoint) + 5 reviewer responses (audit trail). Commits: `097b54e` (v0.2 + 5-panel dispatch) + `9de41f7` (v0.3 + v0.4 + blueprint bug fix).
- **2026-05-23 (Saturday morning)** — **#83/#84 O1 implementation — GREEN v1.2.** Schema v2.1 → v2.2 with the Claim layer (Claim node + EVIDENCES/ABOUT/SUPERSEDES/CONTRADICTS/QUALIFIES rel tables + `_migrate_2_1_to_2_2`); `_DROP_ORDER`, `snapshot.py` v3→v4, `verifier.py` (scope-limited diff), `stats()`, `cli.py` all updated to match (Tasks #12–#16). O1 Promotion Pipeline shipped as `graphdb_kdb/ops/op_1_promote.run` + `graphdb_kdb/core/belief_classifier.classify` — deterministic D-83/84-2 dispatch (3-way counterpart enum + relation_kind derivation), retracted-counterpart sibling walk per P-O1-8 OQ-18, D-83/84-8 Part D 4-cell disposition matrix, post-mutation invariant check ([G]). **11 of 15 ratified #87.1 probes pass** end-to-end with real disposition + fingerprint_drift + classification_drift assertions; 4 deferred in two clean classes: LINKS_TO-implicit-counterpart logic (S05/S06/S07 — D-83/84-7 Tier-2/Tier-3 reconstruction; option α) + semantic-contradicts without polarity flip (S12, S18). Probe corpus #87.1 v1.1 normalized (6 spike-vs-expansion variances accommodated, 3 promoted to first-class CandidateEnvelope fields, real classifier-computed fingerprint hashes). Session handoff at `docs/archive/handoffs/session-handoff-2026-05-23-saturday-morning.md`.
- **2026-05-31** — **Task #97 — GraphDB viewer bake-off → official D3 viewer.** Six-model render-only bake-off; Gemini's D3 force-directed viewer won and was promoted to the official single-command builder `tools/viewer/kdb_graph_viewer.py` + `tools/viewer/kdb_graph_viewer_template.html` (reads Kuzu → neutral JSON → self-contained HTML). The Cytoscape `kdb_graph_viewer-opus.py` was retired. Refined on the Gemini base: 2/3-scale nodes, Entity=blue/Source=green, Elastic-only layout (Clusters removed), self-loops dropped, solid BELONGS_TO / dashed SUPPORTS, smaller arrowheads that dim with ego-focus, hover-triggered ego-focus, and a combined right panel (search + node/edge filters + reset + node detail) with a header show/hide toggle. Original Gemini submission + 2-stage `build_gemini.py` pipeline preserved under `tools/viewer/bakeoff/` as fallback.

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

### Package structure (Phase B — six peer packages)

```
common/          ← leaf: shared types, atomic I/O, call_model, paths, source_io
ingestion/       ← Pass-1 pipeline: kdb_scan, enrich/ (signal/noise + entity_search_keys)
compiler/        ← Pass-2 pipeline: compiler, canonicalize, page_writer, context_loader, prompts/
kdb_graph/       ← producer-agnostic graph layer: schema, intake, queries, adapters
orchestrator/    ← conductor: kdb_orchestrate, manifest_writer, event recorder
tools/           ← operational tools: replay, cleanup, benchmark, viewer, diagnostics
```

**Dependency contract (B.3):**
- `common` → nothing (true leaf; guard-tested)
- `kdb_graph` → `common`
- `ingestion` → `common`
- `compiler` → `common` + `kdb_graph`
- `orchestrator` → all packages (the conductor)
- `tools` → `common` / `kdb_graph` / `ingestion` / `compiler`

Nothing depends on `tools` EXCEPT one documented exception: `orchestrator` calls `tools.cleanup` for orphan cleanup inline (deferred decoupling, out of Phase B's move-only scope).

---

The live conductor is `orchestrator/kdb_orchestrate.py`. Per-source flow:

```
┌────────────────┐   ┌──────────────────────────┐   ┌──────────────────┐
│   kdb_scan.py  │──▶│  enrich/ (Pass-1)         │──▶│  compiler.py     │
│ (deterministic │   │  (LLM: signal/noise,       │   │  (Pass-2 LLM:    │
│  scan, hashes) │   │   domain, entity_search_   │   │   wiki-native    │
└────────────────┘   │   keys; writes frontmatter)│   │   pages[] with   │
       │             └──────────────────────────┘   │  [[wikilinks]]   │
       ▼                                            │   in bodies)     │
 last_scan.json                                     └──────────────────┘
                                                              │
                                                              ▼
                                                   ┌──────────────────┐   ┌────────────────┐   ┌──────────────────┐
                                                   │ canonicalize.py  │──▶│  page_writer.py│──▶│ manifest_writer  │
                                                   │ (alias remap of  │   │ (Python writes │   │ (atomic ledger   │
                                                   │  body wikilinks) │   │  all .md files)│   │  update)         │
                                                   └──────────────────┘   └────────────────┘   └──────────────────┘
                                                                                                                │
                                                                                                                ▼
                                                                                                          manifest.json
                                                                                                          runs/<run_id>/
```

**Finalize pass** (after all sources committed): merge the per-source compile_results → batch `wire_links` → single deferred `detect_orphans` pass → `kdb-clean` orphan reaping → write the combined `compile_result.json` replay payload. (Graph intake itself runs **per source**, inside the commit sequence — see stages below and §8.3.)

**Strict separation of concerns:**
- **LLM is stateless compute.** It receives prompt + source content + graph-derived context snapshot; returns structured JSON (no paths, no timestamps, no frontmatter). Never writes files. Never reads filesystem state.
- **Python is deterministic state + I/O.** Scans, hashes, resolves paths, applies page intents (writes markdown), stamps frontmatter, updates ledger.
- **GraphDB (`kdb_graph`/Kuzu) is the substrate.** `context_loader.py` reads it via the graph query API. `manifest.json` is the source-state metadata ledger (hashes, run_state, timestamps — not an ontology index per D50).
- **Markdown vault is persistent state.** Everything the system knows is reconstructible from `raw/` + `wiki/` + `state/`.

### Page ownership split

| Page | Authored by | Strategy |
|---|---|---|
| `wiki/summaries/*.md` | LLM | Full-body replacement; Python adds frontmatter |
| `wiki/concepts/*.md` | LLM | Full-body replacement; Python adds frontmatter |
| `wiki/articles/*.md` | LLM | Full-body replacement; Python adds frontmatter |

No `index.md` (D23) and no `log.md` (D24) are generated. Obsidian's file explorer + `manifest.json` serve as the TOC; `state/runs/<run_id>/` is the authoritative per-run journal.

### Pipeline stages

`kdb_orchestrate.py` is the live conductor. Per-source flow (post-#115: the #65 Repair stage is deleted whole — its pairing-reconciliation classes are structurally impossible under the shrunk contract — and the stages renumber; Task #74's canonicalize sits between validate and page_writer):

1. **Scan** (`kdb_scan.py`) — walks `raw/`, computes SHA-256, compares to `manifest.json`, emits `last_scan.json` with `to_compile` + `to_reconcile` lists. Compile eligibility is the single honest comparison `current_hash != last_compiled_hash` (D46) — `run_state` plays no part, and there is no force-recompile flag. Handles symlinks (skip), binaries (flag `no_graph_db`), two-pass rename detection. Atomic write.
2. **Enrich** (`enrich/` — Pass-1 LLM) — for each source: LLM judges content (signal/noise), classifies domain and source_type, emits `entity_search_keys` (≤10 kebab-case slugs); writes enrichment frontmatter atomically to the source file. Signal sources advance to Pass-2; noise sources are recorded and skipped.
3. **Compile** (`compiler.py` — Pass-2 LLM) — for each signal source: builds a graph-derived context snapshot via `context_loader.build_context_snapshot`, calls `call_model_with_retry` with source content + context + the repo-packaged `compiler/prompts/KDB-Compiler-System-Prompt.md` (repo-owned post-#115, D-115-13; every run header stamps `pass2_prompt_version` + the loaded prompt's SHA-256); receives a `compiled_sources[]` entry of **wiki-native data only** — `pages[]` (`slug`, `page_type`, `title`, `body`) + optional `compilation_notes`. The contract speaks wiki, not graph: no `source_name`, `summary_slug`, `concept_slugs`/`article_slugs`, `outgoing_links`, `status`, `confidence`, or `log_entries` — Python owns everything mechanical. The semantic gate requires exactly one `page_type == "summary"` page whose slug equals `expected_summary_slug(source_id)` (Python derives the stem deterministically — slugify + length budget — but never injects it into the prompt; the model authors, Python validates). An underivable stem fails before the model call (`failure_stage="validate"`, zero API spend). Accumulates into `compile_result.json`.
4. **Validate compile_result** (`validate_compile_result.py`) — schema-gates `compile_result.json`; aborts per-source with quarantine if malformed (source-local failure does not kill the batch — D-96-1). Post-#115 **dual-mode** (D-115-14): new-shape payloads validate against the derived expected summary slug; historical payloads carrying the six removed fields still validate — those fields are optional, deprecated, read-only, and never copied forward.
5. **Canonicalize** (`canonicalize.py`, Task #74, see `docs/archive/tasks/task74-canonicalization-blueprint.md`) — loads `state/canonicalization/aliases.json` (missing ⇒ empty + warning, D-R5-8), resolves alias surface forms to canonical slugs (chain-flattened to root, D-R5-13), rewrites `pages[].body` wikilinks only (post-#115 body-authority, D-115-9: `outgoing_links` no longer exists in the contract — the old outgoing-links union and slug-list remap are deleted; links that exist only in a dropped body die with it), drops alias entries from `pages[]` (canonical-only, D-R5-12), emits `canonical_meta` (`aliases_emitted`, `outgoing_link_remaps` — historical field name retained for read-compat, now describing body-link remaps —, `algorithm`), atomically overwrites `state/compile_result.json` (D-R5-10). Algorithmic failures (circular aliases, malformed ledger, ambiguous v2, sha mismatch) are **fatal** — failure journal written, pipeline halts before page_writer (D-R5-9). **Post-canonicalization invariant (D-115-11):** for every source, exactly one `page_type == "summary"` page AND its slug still equals `expected_summary_slug(source_id)` — re-checked immediately after `canonicalize.run()`, before any write; summary/non-summary cross-type merges are hard-rejected via typed `CanonicalizationError` (quarantine, no writes). Wiki ≡ graph at the naming layer.
6. **Apply page intents** (`page_writer.py`) — resolves slugs to paths (`paths.py`), stamps frontmatter (`run_context.py`), writes markdown files atomically (`atomic_io.py`). `status` is a **Python-owned stamp** post-#115 — the model no longer emits it; a page without one defaults to `active`. No canonicalization-awareness required (D-R5-12): `pages[]` is already canonical and body wikilinks already remapped. Never writes state files. A throw here leaves the graph untouched (β case-a, clean).
7. **Graph intake** (`kdb_graph/intake.py::apply_compile_result`) — per-source Kuzu transaction on the run's single shared GraphDB connection (Task #91 shared-connection design; see §8.3), updating the live GraphDB ontology authority (D50/D51). **LINKS_TO derivation is graph-owned** (post-#115): the intake derives a page's edge target-set from its body wikilinks (mirrored extractor); historical payloads carrying `outgoing_links` prefer the stored list — the delete-then-recreate contract is unchanged, so recompiles under the new shape do not erase edges. Orphan-marking and link-wiring are deferred to the finalize pass. A throw rolls the Kuzu txn back clean and the manifest is never written, so the source self-heals on re-run (β case-a). Fatal for non-dry-run compiles (D50; revokes D38).
8. **Persist state** (`manifest_writer`) — the **commit boundary** of the β ordering (D-91-15, graph-sync-first): the advanced manifest is computed pure (no I/O) up front, then `manifest.json` is written atomically **LAST** — only after the wiki pages and the graph txn both succeed. A throw here is the distinct, surfaced `manifest_post_graph` residual (graph committed, manifest absent), which self-heals via idempotency on re-run.

---

## 6. State Model

### Architectural layers (D51)

| Layer | Path | Role |
|---|---|---|
| **Source corpus** | `KDB/raw/` | Human-authored raw sources |
| **Live ontology authority** | `GraphDB-KDB/` (Kuzu) | Primary. Updated immediately on every compile (Stage 7 `graph_sync` post-#115 renumbering). Owns Entity, LINKS_TO (derived from body wikilinks post-#115), SUPPORTS, ALIAS_OF, canonical_id, orphan status |
| **Reconstruction material** | `KDB/state/runs/<run_id>/` sidecars | Backup. Durable compile_result + scan snapshots. Enables `graphdb-kdb rebuild` if GraphDB is lost/corrupted |
| **Audit log** | `KDB/state/runs/<run_id>.json` journals | What happened, when, with which model, what failed |
| **Source-file lifecycle** | `KDB/state/manifest.json` | Source-state metadata ledger (hashes, run_state, timestamps). Not an ontology index (D50) |
| **Per-page provenance** | Frontmatter in each `.md` file | Human-readable (`raw_path`, `raw_hash`, `compiled_at`) |
| **Rendered view** | `KDB/wiki/` | Markdown output for Obsidian consumption |

**Primary data flow:** `raw/ → kdb-orchestrate → Stage 5 canonicalize → graph-sync (immediate GraphDB update)`. Runs are not in this hot path — they are written as audit records whose sidecars happen to also serve as reconstruction material.

**Rebuild/verify:** Proves the live authority matches what a clean reconstruction from sidecars would produce. Operational safety net, not the normal data flow.

**Rejected alternatives:** SQLite (too opaque, no diff, breaks OneDrive sync), vector DB (Karpathy explicitly rejects this), pure frontmatter-only (Grok's proposal — too lean at projected scale), `ontology_sources/*.json` per-source durable layer (redundant with sidecars, adds a third consistency surface — rejected in D51).

---

## 7. Benchmark Architecture

The benchmark is a **two-step** quality measurement layer: `kdb-orchestrate --emit-kpis` (the run vehicle) **emits** per-run measurement data from real pipeline runs; `kdb-benchmark score` (the scoring tool) **ranks** models via hierarchical weighted Borda. The two roles are permanently separated — the scorer never re-runs the passes, and the production pipeline never imports from `tools/benchmark`.

### 7.1 Package layout & boundary

```
tools/benchmark/
├── cli.py          # `kdb-benchmark score <run-id…>`
├── promotion.py    # watched-KPI promotion evaluator
├── paths.py        # benchmark dir conventions
└── tests/

compiler/kpi/
├── processing.py   # processing-family KPI computation
├── graph.py        # graph-family KPI computation (reads via kdb_graph.queries)
├── score.py        # Borda engine + hierarchical composite scorer + penalty
└── report.py       # per-run report.md renderer

common/
└── measurement.py  # PassCallMeasurement + RunMeasurementHeader (logical view over telemetry — not a new store)

benchmark/
├── sources/        # canonical 36-source sandbox corpus (tracked in git)
├── runs/           # per-model measurements.json + report.md (gitignored)
└── scores/         # leaderboard.json + leaderboard.md (tracked)
```

**One-way import boundary** (D25, preserved): `tools/benchmark` and `compiler/kpi` import from `compiler` and `common`; production pipeline packages never import from `tools`. `compiler/kpi` is used by both the orchestrator (emit path) and the scorer (load-and-rank path).

### 7.2 How to run a cohort

1. **Reset the sandbox** (`~/Obsidian/Vault-in-place-test-run`) and run `kdb-orchestrate --emit-kpis --model <model-id>` once per candidate model. Each run writes `benchmark/runs/<run-id>/measurements.json` (reset-surviving — the sandbox graph is wiped before the next model; measurements must be emitted inside the run). See the cohort runbook: `docs/reference/benchmark-cohort-procedure.md`.
2. **Score** with `kdb-benchmark score <run-id> [<run-id>…]` (one run-id per model). Writes/updates `benchmark/scores/leaderboard.json` + `leaderboard.md`.

### 7.3 KPI families

Two families, kept structurally separate — never blended at scoring time.

**Processing family** (from per-run telemetry, per-1M-token normalized):

| KPI | Direction | What it measures |
|---|---|---|
| `quarantine_rate` | ↓ | fraction of sources that failed to produce a usable compile result |
| `recovery_rate` | ↓ | fraction of sources requiring compile re-prompts (SDK transient retries excluded) |
| `latency` | ↓ | median end-to-end latency per source (ms) |

**Graph family** (from the Kuzu knowledge graph after the run, combined into one `graph_score`):

| KPI | Direction | What it measures |
|---|---|---|
| `graph_connectivity` | ↑ | largest-connected-component fraction of canonical entities |
| `link_density` | ↑ | LINKS_TO edges per entity |
| `supports_density` | ↑ | SUPPORTS edges per entity |
| `entity_reuse` | ↑ | fraction of entities referenced by ≥2 sources |

**Watched diagnostics** (emitted each run, not scored; evaluated for promotion after each cohort via `tools/benchmark/promotion.py`):
`entity_search_key_resolution` · `orphan_rate` · `semantic_pass_rate` · `signal_noise_ratio` · `retry_load` · `token_overrun_rate` · `repair_rung_rate` · `domain_breadth` · `domain_null_rate` · `belongs_to_coverage` · per-pass breakdowns (`quarantine_rate_pass1/2`, `latency_pass1/2`; #117 adds `recovery_rate_pass1/2`, `retry_load_pass1/2`, `cost_usd_pass1/2`, `cost_unknown_calls_pass1/2`)

### 7.4 Weights & penalty (all PINNED)

**Top-level composite** (`compiler.kpi.score.TOP_WEIGHTS`):

| Axis | Weight |
|---|---|
| `quarantine_rate` | 40% |
| `graph_score` (combined) | 40% |
| `recovery_rate` | 10% |
| `latency` | 10% |

**Within-graph** (`compiler.kpi.score.GRAPH_WEIGHTS`):

| KPI | Weight |
|---|---|
| `graph_connectivity` | 35% |
| `link_density` | 30% |
| `supports_density` | 20% |
| `entity_reuse` | 15% |

Weighting is hierarchical: the four graph KPIs first combine into one `graph_score`, then `graph_score` enters the composite as the single 40% term. This preserves the 40/40/10/10 split exactly even when a model is missing a graph KPI (pro-rata renormalization happens within each family, not across the flat composite).

**Weak-spot penalty** (leaderboard-only): **τ=0.5 PINNED**, **λ=0.10 PINNED**. Operates on the four composite axes (`quarantine_rate` / `recovery_rate` / `latency` / `graph_score` Borda values — equal treatment). A model with a glaring weak composite axis (weakest < τ) loses up to 10 pts on the 0–100 headline score: `penalty = λ · max(0, (τ − weakest) / τ)`. Baseline-1 validated the parameters: deepseek penalized on latency, gemini on quarantine, qwen on recovery — each hitting the cap.

### 7.5 Data flow

```
~/Obsidian/Vault-in-place-test-run   (36-source sandbox)
        │
        ▼
kdb-orchestrate --emit-kpis --model <id>   (one per candidate; reset sandbox between runs)
        │  Pass-1 + Pass-2 + graph build + graph-KPI computation
        ▼
benchmark/runs/<run-id>/measurements.json   (header + processing.scored/watched + graph.scored/watched/diagnostic)
benchmark/runs/<run-id>/report.md           (per-run human summary)
        │
        ▼ (collect one run-id per candidate model)
kdb-benchmark score <run-id…>
        │  Borda rank → hierarchical composite → penalty → leaderboards (§7.7)
        ▼
benchmark/scores/leaderboard.json            (+ .md)
benchmark/scores/leaderboard-pass1.json      (+ .md)   # #117
benchmark/scores/leaderboard-pass2.json      (+ .md)   # #117
```

### 7.6 Promotion rule

`tools/benchmark/promotion.py` evaluates watched diagnostics for promotion to the scored set after each multi-model cohort. A watched KPI promotes when **all three** hold:

1. **CoV > 0.2** — varies meaningfully across models
2. **Q1 > ε** — the bulk of values are non-trivially non-zero
3. **max |Spearman| vs scored < 0.7** — not redundant with any already-scored KPI

Promotion is advisory (human decision, not automatic). Prime candidates from baseline-1: `entity_search_key_resolution`, `orphan_rate`.

### 7.7 Per-pass leaderboards (#117, spec v0.3.1)

`kdb-benchmark score` writes **three** boards per invocation: the combined board (§7.4 scoring, unchanged) plus `leaderboard-pass1.{json,md}` and `leaderboard-pass2.{json,md}` (filenames derive from the `--leaderboard` stem). Rationale: model performance is pass-specific (own prompt/contract/failure modes); the split boards are the evidence base for a later cheap-Pass-1 / quality-Pass-2 model split (#118).

- **Recompute, don't re-run.** Per-pass processing KPIs are recomputed at score time from each row's `run_state/` (`load_run_measurements` → `compute_processing`); graph KPIs come from `measurements.json` (emit-time graph state, not reproducible at score time). No pipeline change, no re-runs.
- **Same machinery, pass-scoped inputs.** Pass KPIs map onto the canonical processing names and go through the §6 `score_models` path: Pass-1 = 3 processing KPIs (pro-rata 4:1:1 + weak-spot penalty, graph term inactive); Pass-2 = 3 processing + 4 graph KPIs (identical 40/40/10/10 shape). The Pass-2 board is explicitly a **downstream-outcome** board (Pass-1 gating/failures decide Pass-2 coverage — e.g. Qwen's 28 vs 29) — isolated per-pass attribution waits on #118. It carries `pass2_eligibility_rate` (`signal/p1_attempted`), `pass2_measurement_coverage` (`loaded/p2_attempted`), and `p1_noise`/`p1_failed` disposition columns.
- **Cost is a selection column, never a Borda axis.** `cost_usd_pass1/2` render prominently; `cost_unknown_calls > 0` ⇒ `≥$X (+N unknown)` (zero cost can mean unpriced/failed, not free — cf. #110 deferred item).
- **Fail closed.** A row is ranked on a pass board only if its `run_state/` passes the per-board completeness contract (header parses; Pass-1 sidecar count reconciles with `p1_attempted` incl. skipped; Pass-2 records == `p2_attempted`; required KPI inputs present). Incomplete rows render `unranked` with `measurement_source` + `missing_kpis` — never pro-rata on missing evidence.
- **Honest metadata.** Pass boards persist `board_scope`, full-precision `effective_top_weights` (Pass-1: 2/3, 1/6, 1/6, graph 0.0), `unranked[]`, and per-row `raw_values` (one contract for ranked + unranked rows). Competition ranking: tied composites share a rank (1, 1, 3); the main board keeps sequential ranks.
- **Write boundary.** All three boards are computed/validated/rendered before any write; each file is replaced individually-atomically under one shared `updated_at` (mixed-generation detection is best-effort under the single-user model; rerun heals).

Main-board contract: scored KPIs, ranking, composite, and scored columns unchanged; its data-driven raw-values table may additionally surface the #117 diagnostics on newly emitted runs. Spec: `docs/superpowers/specs/2026-07-22-task117-per-pass-leaderboards-design.md` (v0.3.1, Codex 3 rounds).

---

## 8. GraphDB-KDB Layer (Kuzu-backed knowledge graph)

The reframe locked on 2026-05-10 (paradigm doc: `docs/reference/New-GraphDB-Paradigm.md`): **KDB is a raw-text → knowledge-graph compiler**, not a wiki-page compiler with a graph as a byproduct. Wiki pages and `manifest.json` are *renderings* of the graph; the graph is the architectural primitive that downstream tooling (search, knowledge-hole detection, EXISTING CONTEXT seed selection, adaptive learning paths) consumes.

The bet is **explicit edges beat implicit similarity** — vector RAG flattens ontology into cosine distance; the graph preserves the explicit edges paid to construct. See memory note `feedback_graph_over_vector_for_kdb`.

### 8.1 Package layout & boundary

```
kdb_graph/                                  ← producer-agnostic ontology layer
├── schema.py                               # Kuzu DDL (Entity / Source / LINKS_TO / SUPPORTS)
├── types.py                                # Entity, Source dataclasses; SyncResult, RebuildResult
├── graphdb.py                              # GraphDB connection manager + idempotent schema bootstrap
├── intake.py                               # apply_compile_result — atomic per-run mutations
├── queries.py                              # neighbors, paths, provenance reads (single Kuzu door)
├── analytics.py                            # PageRank, Louvain, structural holes (hybrid via NetworkX)
├── verifier.py                             # verify_against_manifest — overlap audit
├── rebuilder.py                            # rebuild() — generic chronological replay (D-B1)
├── snapshot.py                             # snapshot() — JSONL+manifest+schema.cypher export (#63.9)
├── adapters/
│   ├── base.py                             # ProducerAdapter Protocol; RunDescriptor / EligibilityResult
│   └── obsidian_runs.py                    # Obsidian-KDB adapter (reference impl)
└── cli.py                                  # graphdb-kdb CLI dispatcher
```

**One-way import boundary** (D34 + D-B1, mirrors D25 for kdb_benchmark): `kdb_graph/` has **zero imports from the production compiler packages**. Producer-specific knowledge lives inside `adapters/obsidian_runs.py` and is expressed as JSON parsing of producer artifacts — never as Python imports of producer types. A grep invariant on `from compiler\|from ingestion\|from orchestrator` inside `kdb_graph/` returns nothing.

**Physical separation** (D35): the Kuzu *data* directory lives at `~/Droidoes/GraphDB-KDB/` (sibling to `Obsidian-KDB/`, not OneDrive-synced — avoids binary-file corruption). (Superseded 2026-06-11, #113: the default now derives `<vault>/KDB/graph` from `OBSIDIAN_VAULT_PATH`; `KDB_GRAPH_PATH` overrides. The old `~/Droidoes/GraphDB-KDB/` dir is a retired stray.) The Python package code lives at `kdb_graph/` inside `Obsidian-KDB/`; the extraction arc to a standalone repo `~/Droidoes/GraphDB-KDB-package/` is documented in `docs/reference/graphdb-kdb-extraction-roadmap.md`.

### 8.2 Schema (Kuzu DDL)

```cypher
CREATE NODE TABLE Entity (
    slug          STRING PRIMARY KEY,    -- producer-emitted identifier; bare per D-S1 grandfather for Obsidian
    title         STRING,
    page_type     STRING,                -- summary | concept | article | alias  (values still Obsidian-flavored, per D-A2 deferred)
    status        STRING,                -- active | stale | archived | orphan_candidate | alias
    confidence    STRING,                -- low | medium | high — LOGICALLY DEPRECATED (D-115-12, post-#115): no writes/reads/queries/snapshots; dead column stays until the next destructive schema change
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
    ingest_state       STRING,           -- graph-side name for producer run_state
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
- **C4** — every `LINKS_TO` edge's destination has `canonical_id IS NULL`: LINKS_TO never points at an alias (D-R5-12; alias→canonical remap happens at the canonicalize stage — Stage 5 post-#115 — before graph_sync).

Aliases are exempt from orphan detection (no `SUPPORTS` edges by OQ-E; canonical-only routing); `_detect_and_mark_orphans` is scoped to `canonical_id IS NULL`.

**Naming history**: `Entity` was originally `Page` (renamed per D-A1 2026-05-14); graph-side `ingest_*` fields were originally `compile_*` (renamed per D-A2). The producer source-state ledger now uses `run_state` for source lifecycle status (Task #96 C1 prep, schema v3.1); deprecated `compile_state` is accepted only as a migration/replay fallback. The verifier's `_SOURCE_DIRECT_FIELDS` tuples are the alias bridge: `("run_state", "ingest_state")` etc.

### 8.3 Pipeline integration — per-source graph intake (β commit model, D-91-15)

`kdb-orchestrate` runs graph intake **per source**, inside the commit sequence (post-#74 + Task #91; canonicalize precedes intake — Stage 5 after the post-#115 renumbering):

```
Per-source commit (β order):  scan → enrich (Pass-1) → compile (Pass-2) →
                               canonicalize → page_writer →
                               graph intake → manifest write (LAST = commit boundary)
  (post-#115: the Repair stage is deleted whole; stages renumber.)

  Graph intake (D50: fatal for non-dry-run; revokes D38 non-fatal):
    kdb_graph.intake.apply_compile_result(cr, single_scan, run_id, conn=conn,
                                          detect_orphans=False, wire_links=False)
    — one Kuzu transaction per source over the run's shared read-write
      GraphDB connection; a throw rolls back clean and the manifest is never
      written (β case-a self-heal). Post-#115 the LINKS_TO target-set is
      graph-owned: derived from body wikilinks via a mirrored extractor
      (`body_wikilink_slugs`); legacy payloads carrying `outgoing_links`
      prefer the stored list. Delete-then-recreate per source unchanged.

Finalize passes (once, over the final graph): merge per-source compile_results
  → batch wire_links → single detect_orphans pass → kdb-clean orphan reaping
  → write the combined compile_result.json replay payload.
```

Two architectural properties of the wiring:

1. **The orchestrator holds a shared `GraphDB` connection and calls `kdb_graph.intake` entry points directly** (Task #91 shared-connection design — `kdb_orchestrate.py` imports `GraphDB` + `apply_compile_result` / `wire_links` / `detect_orphans` / `apply_cleanup`). This supersedes the original D-S0 adapter-only wiring for the live path; the `ObsidianRunsAdapter` remains the single producer→graph entry point for **rebuild/replay** (`graphdb-kdb rebuild`, D39). (The D-S0 ledger row below is kept as the historical record.)
2. **Replay material survives a sync failure.** Per-source Kuzu failures roll back before the manifest commit boundary (β case-a), and the combined `compile_result.json` replay payload is written at finalize — so `graphdb-kdb rebuild` remains a real recovery path. (Per D50, graph intake failure is fatal for non-dry-run compiles since GraphDB is the live ontology authority; D38 non-fatal semantics were revoked for ontology writes.)

**Adapter's canonicalization responsibilities** (Task #74, Phase 3.5 in `kdb_graph/intake.py`): on top of canonical-entity upsert + LINKS_TO + SUPPORTS, the adapter reads `canonical_meta.aliases_emitted` from the canonicalized compile_result and writes one `Entity` row per alias (`canonical_id` = root canonical slug, `page_type` = `'alias'`) plus one `ALIAS_OF` edge alias→canonical with `algorithm` provenance. Promotion edge case: when a slug previously written as alias appears as canonical, `_upsert_entity` resets `canonical_id = NULL` and drops outgoing `ALIAS_OF` (preserves C1). Re-running the same `canonical_meta` is idempotent (drop-then-create on `ALIAS_OF` keeps the flat invariant — one edge per alias, run_id reflects most recent run; older provenance lives in the per-run sidecar).

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
| [`docs/reference/task-graphdb-kdb-blueprint.md`](reference/task-graphdb-kdb-blueprint.md) | Locked decisions D32–D40 + D-A1/A2/B1/S0–S3; schema DDL; ingestion algorithm; rebuild semantics; #63.1–#63.9 sub-task ledger |
| [`docs/reference/New-GraphDB-Paradigm.md`](reference/New-GraphDB-Paradigm.md) | Conversational record of the 2026-05-10 reframe (graph-is-the-system); scope distinction GraphDB-KDB vs future `kdb-graph` |
| [`docs/reference/graphdb-kdb-producer-contract.md`](reference/graphdb-kdb-producer-contract.md) | Formal contract for what GraphDB-KDB expects from any producer (mutation payload + scan + run journal + sidecar archive); adapter interface |
| [`docs/reference/graphdb-kdb-extraction-roadmap.md`](reference/graphdb-kdb-extraction-roadmap.md) | 5-stage path from monorepo to standalone PyPI package; invariants PR1–PR10; anti-patterns |
| [`docs/reference/manifest-succession-arc.md`](reference/manifest-succession-arc.md) | M0–M4 transition arc: manifest.json from swiss-knife (source meta + ontology) to source-meta-only ledger; EXISTING CONTEXT switches to GraphDB at M1 |
| [`docs/archive/tasks/task63-phase3-implementation-blueprint.md`](archive/tasks/task63-phase3-implementation-blueprint.md) | Implementation plan for #63.5b + #63.6 + #63.7-pre (the three sub-tasks landed 2026-05-14) |
| [`docs/archive/tasks/task74-canonicalization-blueprint.md`](archive/tasks/task74-canonicalization-blueprint.md) | Canonicalize-stage blueprint (Stage [6] in pre-#115 numbering; Stage 5 today): locked decisions D-R5-1..D-R5-13; algorithm (string-norm → ledger → embedding v2 → llm-judge v2); schema delta (`Entity.canonical_id`, `ALIAS_OF`); C1–C4 verify invariants; rebuild semantics |
| [`docs/archive/tasks/task75-predeclared-eval-criteria-blueprint.md`](archive/tasks/task75-predeclared-eval-criteria-blueprint.md) | **Step-3 query-time eval contract (Task #75, blueprint v2 — Codex + Gemini review applied).** Predeclares the operations roster (PPR + community routing + subgraph extraction V1; typed traversal V0; shortest-path V0 / scored-multi-hop V2), per-op pass/fail/quantitative-gate criteria, hedge-watch rules HW-1..HW-7 (symptom → §8.3 hedge), step-3 preconditions (Task #76 `domain` field gates the community/domain-ratio acceptance only; Task #77 probe set), and OQ-1..OQ-9. Satisfies Round 5 §8.5/§8.6 path-forward precondition (Codex Q6 — avoid "implementation momentum disguised as empiricism"). Pattern mirrors Task #19 (compile-side KPI predeclaration → §7) extended to query-time. |

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
graphdb-kdb domains [--json]                            # Domain nodes sorted by entity count
graphdb-kdb snapshot [--vault-root <P>] [--out <dir>]   # JSONL+manifest+schema export (#63.9)
```

`--graph-dir <path>` overrides the Kuzu data directory (default: `$KDB_GRAPH_PATH`, else `<vault>/KDB/graph` derived from `OBSIDIAN_VAULT_PATH`).

### 8.7 Graph context loader — retrieval tiers & cold-start widening

`context_loader.py` builds a source-specific `ContextSnapshot` from the graph. It reads the graph via the `kdb_graph.queries` API (no raw Kuzu), replacing the legacy manifest-based approach. The loader assigns entities to **retrieval tiers** — relevance-source categories, not graph-distance measures:

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
| D29 | 2026-05-10 | M5 retired body_link_jaccard (=1.000-by-construction post-#57) is replaced by `body_emit_set_coverage`: per-source `\|((⋃_p (body_wikilink_slugs(p.body) − {p.slug})) ∩ (concept_slugs ∪ article_slugs))\| / \|concept_slugs ∪ article_slugs\|`, micro-aggregated across the run. Computed in `kdb_benchmark/scorer.py` from captured `parsed_json` — no new RespStatsRecord fields (preserves one-way boundary D25). Self-links excluded to reward cross-page integration. Weight stays 5%. See `docs/archive/tasks/task59-m5-replacement-design.md` for full design (D29.1–D29.9 sub-decisions). |
| D30 | 2026-05-10 | M5 weight bumped 5% → 15%; M6 and M7 each bumped 15% → 10%. Total still 100%. Quality core (S0 + M1 + M4 + M5) becomes 70% of FINAL (was 55%); cost+latency become 20% (was 30%). | Post-#59/#60 regression scorecard showed M5=0.111 outlier (qwen-flash-us) couldn't be discriminated at the 5% weight level — model still topped FINAL despite barely integrating concepts via body wikilinks. Reweight reflects the user's "if other models can do it, why can't you?" stance: quality should dominate FINAL more than cost/latency. Cross-generation FINAL comparison invalidated again per D29.9 (same doctrine). See `docs/TASKS.md` → Task #61. |
| D31 | 2026-05-10 | Outlier penalty added to FINAL composition. For each model and each in-scope measure (S0, M1, M2, M3, M4, M5), units = floor(((norm − value)/norm × 100) / 10) when value < norm; total = Σ units across measures; FINAL_post = max(0, FINAL_pre − 0.05 × total). M6/M7 excluded (Borda-relative). Surfaces single-axis outliers that the weighted sum would average away (e.g. qwen-flash-us with M5=0.111 dethroned). Cross-generation FINAL comparison invalidated again per D29.9 doctrine. See `docs/archive/tasks/task62-outlier-penalty-design.md` (D31.1–D31.12 sub-decisions). |
| D32 | 2026-05-13 | **GraphDB-KDB is a multi-source raw-text → knowledge-graph compiler at the storage layer**; the schema admits `Source.source_type` as a discriminator and is source-agnostic. The ingestion API (`apply_compile_result`) is Obsidian-flavored for v1 (D32-tempered per Codex Round 1 v2 review). Graph is the architectural primitive; manifest.json + wiki markdown + future visualizations are *renderings*. | Differentiating bet: explicit edges beat implicit similarity. Vector RAG flattens ontology into cosine distance; the graph preserves what we paid to build. Storage-layer multi-source readiness is cheap to bake in; ingestion-layer abstraction without a second producer would be speculative. |
| D33 | 2026-05-13 | Storage = Kuzu 0.11.3 (embedded graph DB, Cypher dialect, multi-language bindings, MIT). | Purpose-built for embedded graph; file-based (no daemon), portable, industry-standard Cypher. NetworkX+JSONL is Python-only; SQLite-with-graph-schema forces consumers to reimplement traversal. |
| D34 | 2026-05-13 | Independence-by-shared-upstream: `manifest_writer` and `graphdb_kdb.ingestor` each consume `compile_result + last_scan + run_id` independently. Neither reads or writes the other's store. | Ablation: delete `manifest.json` → GraphDB still queryable; delete `GraphDB-KDB/` → manifest still works. Both regenerable from `state/runs/<run_id>.json` history. Real independence by structural construction. |
| D35 | 2026-05-13 | Kuzu *data* directory location: `~/Droidoes/GraphDB-KDB/` (sibling to Obsidian-KDB; not OneDrive-synced). Override via `KDB_GRAPH_PATH` env var. (Superseded 2026-06-11, #113: default derives `<vault>/KDB/graph` from `OBSIDIAN_VAULT_PATH`; `KDB_GRAPH_PATH` overrides.) | Physical separation mirrors logical separation. Avoids OneDrive corruption on Kuzu binary catalog files. Backup = recovery-via-rebuild (D39); belt-and-suspenders via `graphdb-kdb snapshot` (#63.9). |
| D36 | 2026-05-13 | Naming triad: Python module `graphdb_kdb`, Kuzu directory `GraphDB-KDB/`, CLI command `graphdb-kdb`. `kdb-graph` is **reserved** for a future Obsidian-graph-view utility — out of #63 scope. | Avoid conflating the multi-source ontology layer with a (future) Obsidian-specific rendering tool. Memory: `project_graphdb_kdb_vs_kdb_graph_distinction`. |
| D37 | 2026-05-13 (renamed D-A1 2026-05-14) | Schema: `Entity` and `Source` node tables; `LINKS_TO` (Entity→Entity), `SUPPORTS` (Source→Entity) rel tables. Originally `Page` node-table; renamed to `Entity` per D-A1 to remove the Obsidian-isms from the storage-layer vocabulary. | Provenance is first-class graph data, not a sidecar. `Entity` reads as abstract identity (vs `Page` which presumed wiki-page rendering) — better positioning for multi-source future. |
| D38 | 2026-05-13 | Pipeline integration: Stage 9 `graph_sync` runs AFTER Stage 8 (manifest write); failure is **non-fatal** — emits warning + journal entry, but overall compile run still returns success. | Honors D34 independence: a failed graph write must not roll back a successful manifest write. Recovery via `graphdb-kdb rebuild`. |
| D39 | 2026-05-13 | Rebuild path: `graphdb-kdb rebuild` drops all Kuzu tables and replays the **eligible** subset of `state/runs/*.json` chronologically. **Eligibility:** `success=true AND dry_run=false AND payload_present` (payload = sidecar archive at `state/runs/<run_id>/{compile_result,last_scan}.json` per #63.0 outcome). Independence proof: Kuzu regenerable without ever reading `manifest.json`, prospectively from #63 forward. | If GraphDB drifts from compile-history truth, regenerate from compile-history truth. Pre-#63 historical runs are unrecoverable except for the latest baton state — see §8.4 baton-backfill. |
| D40 | 2026-05-13 | Hybrid analytics: Kuzu Cypher fetches topology (edge lists, node attrs); NetworkX + python-louvain computes PageRank, Louvain communities, structural-holes. | Kuzu lacks native PageRank/Louvain; implementing iteratively in Cypher is awkward. At 10⁴-node ceiling the hybrid cost is sub-second per algorithm. |
| D41 | 2026-05-15 (Task #64) | **Recompile supersession.** A source's recompile removes that source's support from prior pages the new run no longer emits. The graph ingestor already implements this; D41 binds the manifest path to parity. See `docs/archive/tasks/task64-recompile-supersession-blueprint.md`. | Graph ingestor's `_replace_supports_for_source` is the reference design (Codex CRITICAL #2 fix in #63). Manifest-only union (`_ensure_page` always unions) diverges from graph truth after any recompile that emits fewer pages. D41 closes that gap without touching `graphdb_kdb`. |
| D42 | 2026-05-15 (Task #64) | **`source_refs` is current-state provenance, not an eternal log.** Stripped on supersession alongside `supports_page_existence`. History lives in run journals, `sources[].previous_versions`, and `orphans[].previous_supporting_sources`. See `docs/archive/tasks/task64-recompile-supersession-blueprint.md`. | Keeping stale `source_refs` after supersession creates false provenance claims (a source "supports" a page it no longer emits). Run journals and `previous_supporting_sources` preserve history without polluting current-state. |
| D43 | 2026-05-15 (Task #64) | **Status-aware `source_refs` invariant.** `active` page → `source_refs` non-empty. `orphan_candidate` page → may be empty (provenance preserved in `orphans[].previous_supporting_sources`). Also fixes the pre-existing DELETED-path invariant crash. See `docs/archive/tasks/task64-recompile-supersession-blueprint.md`. | Prior invariant rejected empty `source_refs` for all pages without a status filter — supersession legitimately empties them for orphan candidates. DELETED path had the same latent crash (never triggered because no source has been deleted in practice). Status-aware check makes the invariant correct for all reachable states. |
| D44 | 2026-05-15 (Task #64) | **D12 preserved.** Supersession flags pages `orphan_candidate`; never deletes page records or files. `delete_policy` stays `mark_orphan_candidate`. See `docs/archive/tasks/task64-recompile-supersession-blueprint.md`. | D12 is the non-destructive safety invariant: orphan candidacy is a flag, not a deletion. #64 adds a new trigger (recompile supersession) but the outcome is identical to the existing orphan path — page stays in manifest and on disk, human reviews. |
| D45 | 2026-05-15 (Task #65) | **`pairing_type_mismatch` is reconcilable; `pages[].page_type` is authoritative.** A new unconditional `reconcile_slug_lists()` rebuilds `concept_slugs`/`article_slugs` from `pages[]` in `compile_one` (mirroring Task #57's body-wins `reconcile_body_links`). The validator demotes `pairing_type_mismatch` `gate`→`measure` and drops it from `HARD_ZERO_FINDING_TYPES`. See `docs/archive/tasks/task65-pairing-reconcilable-blueprint.md`. | `concept_slugs`/`article_slugs` are denormalized indexes of `pages[].page_type`; the page object (title+body-bearing) is the deliberate classification. Hard-gating a slug-list mis-file discarded whole good compiles (EP1: 28 valid pages lost over 2 mis-filed slugs). Rebuilding from `pages[]` makes the pairing-inconsistency class structurally impossible. Removing `pairing_type_mismatch` from `HARD_ZERO_FINDING_TYPES` redefines the benchmark hard-zero pass-rate measure — a post-#65 re-fire sets the new baseline. |
| D46 | 2026-05-16 (Task #66) | **Compile eligibility is `current_hash != last_compiled_hash`.** A new source field `last_compiled_hash` records the hash last *successfully processed*; it advances **only on successful processing of the current content** — `apply_compile_result` for LLM-compiled text sources, `apply_scan_reconciliation` for metadata-only binaries (Q6) — never by the scan merely *seeing* a changed text source, never for an error-marked / missing source. The scan carries the prior value onto every `ScanEntry` as `compiled_hash` (required-but-nullable); `to_compile`/`to_skip` partition purely on the hash comparison, never on `action`. The `error_retry` side-channel is removed; lifecycle state is informational but no longer affects eligibility (`compile_state` historically, `run_state` after Task #96 schema v3.1). Force-recompile = a real source-content change; no manifest flag, no `--force`; content hash only, never mtime. See `docs/archive/tasks/task66-compile-trigger-model-blueprint.md`. | `manifest.hash` advances during the *scan* (it means "last hash seen"), so reading it back as "last hash compiled" conflated two facts: a failed compile left `hash` already advanced, so the file read UNCHANGED next scan despite never compiling. `error_retry` was a patch over that conflation — and it made force-recompile possible by hand-editing `compile_state: "error"` into the manifest. Splitting the two hashes makes the trigger one honest comparison and removes the manifest-editable force path; Task #96 later deprecated `compile_state` in favor of `run_state` without changing the trigger. |
| D47 | 2026-05-16 (Task #70) | **Superseded by D49.** Originally held manifest as default context source pending cold-start fix. Cold-start resolved (#71); D49 removed manifest-as-context entirely. | Historical: prevented premature default flip while graph context was weaker on cold-start. Now moot — graph is the only context authority. |
| D48 | 2026-05-17 (Task #71) | **Graph context loader must be self-sufficient — no manifest fallback path.** Cold-start is resolved by widening graph-native matching (title phrase + extended neighborhood hops), never by delegating to manifest. | Manifest is being phased out of the context-generation pipeline. Any fallback would be architectural regression. Rejected: (b) min-context fallback to manifest; (c) manifest-for-first-compile / graph-for-recompile split. |
| D49 | 2026-05-17 (Task #70 closure) | **GraphDB is the only supported EXISTING CONTEXT authority.** `manifest.json` must not be used for context generation. The `KDB_CONTEXT_SOURCE` env var has no effect; the orchestrator calls `context_loader` directly. If GraphDB is missing/empty/corrupt, context snapshot build fails loud → operator runs `graphdb-kdb rebuild`. | Manifest is the wrong substrate for ontology/context — a flat index cannot encode graph relationships. Keeping it as rollback implies it is an acceptable competing source of truth; it is not. Graph outperforms manifest on both cold-start (17–23 vs 0–8 pages) and steady-state. Recovery path is rebuild from run journals (D39), not fallback to a weaker substrate. |
| D50 | 2026-05-17 (Task #73) | **`manifest.json` is no longer an ontology store.** GraphDB owns Entity, LINKS_TO, SUPPORTS, orphan status, graph topology. Manifest becomes source-file metadata ledger only (hashes, compile state, timestamps). Stage 9 `graph_sync` becomes fatal for non-dry-run compiles (revokes D38 non-fatal semantics for ontology writes). No piecemeal removal — pages, outgoing_links, source_refs, orphan status stripped together once consumers migrate. | Dual-write is architecturally confusing (two "sources of truth" invite drift) and blocks manifest slimming. Piecemeal removal (e.g., outgoing_links only) creates half-stale state — worse than either extreme. GraphDB is deterministically regenerable from run journals (D39); manifest cannot serve as fallback once it stops tracking ontology. See `docs/archive/tasks/task73-manifest-ontology-removal-blueprint.md`. |
| D51 | 2026-05-17 (Task #73 closure) | **GraphDB is the live ontology authority; `state/runs/` sidecars are reconstruction material, not the primary data flow.** Layer model: `raw/` = source corpus; `GraphDB-KDB/` = live ontology authority (primary); `state/runs/` = audit log + reconstruction material (backup); `manifest.json` = source-state metadata ledger (hashes, run_state, timestamps — not ontology); `wiki/` = markdown rendering. Primary path: `kdb-orchestrate → graph-sync (immediate GraphDB update)` — runs are not in this hot path. Rebuild/verify use sidecars as backup to prove or restore consistency. The source-state ledger must not carry replay-selection pointers — replay eligibility belongs to the adapter/rebuilder, not the source metadata ledger. | Rejected: (a) event-sourcing framing where runs/ IS the ontology authority and GraphDB is "just a projection" — technically correct but cognitively misleading (implies the normal path goes through runs/; it doesn't). (b) `ontology_sources/*.json` per-source durable layer — redundant with sidecars, adds a third consistency surface, re-introduces coupling removed by D50. The current architecture already matches the compiler mental model (source → distill → update GraphDB); the naming just needed to make that explicit. |
| D52 | 2026-05-21 (Task #74 closure) | **Canonicalization is a top-level compile stage (new Stage [6]), not a side-effect of page_writer or graph_sync.** Both downstream renderings — `page_writer` (wiki .md files) and `graph_sync` (live GraphDB) — consume the canonicalized `compile_result`, so wiki and graph agree on entity names at the rendering layer. Algorithmic failure is fatal (D-R5-9; pipeline halts before page_writer writes anything). Run journal `schema_version` bumps `2.1 → 2.2` to carry `canonical_meta` for D39 replay (D-R5-7). GraphDB gains `Entity.canonical_id` + `ALIAS_OF` rel table; alias entities are `canonical_id IS NOT NULL` + chain-flattened to root (D-R5-13). C1–C4 invariants are checkable from the live graph alone (no sidecar reads). Full locked-decision register (D-R5-1..D-R5-13) and algorithm details live in `docs/archive/tasks/task74-canonicalization-blueprint.md`. | If canonicalization ran only inside `graph_sync`, the vault would show `[[AAPL.md]]` while the graph stored `apple-inc` — a divergence the human sees in Obsidian. Single source of canonical truth, consumed identically by both renderings, is the only way wiki ≡ graph at the naming layer. v1 implementation = string-norm + manual ledger (`state/canonicalization/aliases.json`); embedding-similarity + LLM-judge layers reserved for v2 (L9 in blueprint §14). |
| D-A1 | 2026-05-14 (Round 1 Codex) | Schema rename: `Page → Entity` node-table label. | `Node` would collide with Kuzu's NODE keyword + universal graph-theory term. `Entity` signals abstract identity. Free upgrade while schema is empty/small. |
| D-A2 | 2026-05-14 (Round 1 Codex; updated by Task #96 on 2026-05-30) | Graph-side source field renames: `compile_state → ingest_state`, `compile_count → ingest_count`, `last_compiled_at → last_ingested_at`. Producer source-state later moved active lifecycle status from deprecated `compile_state` to `run_state` (schema v3.1) while GraphDB retained `ingest_state` as its neutral projection name. Page enum values (page_type/status) retained — *values* are Obsidian-flavored; renaming names without revisiting values is cosmetic. **`confidence` value dropped 2026-07-21 (D-115-12):** logically deprecated end-to-end — Entity-scope writes/reads/queries/snapshots stop; the dead Kuzu column stays until the next destructive schema change. Claim-tier computed confidence is untouched. | Pipeline-specific graph field NAMES become pipeline-neutral now. Pipeline-specific VALUES wait for producer #2 to inform the right abstraction. Verifier carries an alias map bridging producer `run_state` to graph `ingest_state`; legacy `compile_state` is migration/replay fallback only. |
| D-B1 | 2026-05-14 (Round 1 Codex) | Rebuilder is **B-lite (adapter split)**: thin generic core in `graphdb_kdb/rebuilder.py` (drop+recreate, chronological iter, error reporting) + producer-specific logic in `graphdb_kdb/adapters/obsidian_runs.py`. Rule: `graphdb_kdb/` MUST NOT `import kdb_compiler.*`. Public function name `rebuild_from_obsidian_runs(...)`. | Pure-C (core imports producer types) would silently weaken D34 independence. B-lite preserves it by structure, not convention. Cost: ≤200 LOC adapter; verified by grep invariant. |
| D-S0 | 2026-05-14 (Round 2 Codex) | **Graph-sync routes through the Obsidian adapter**, not direct core call. `kdb_orchestrate.py` calls `graphdb_kdb.adapters.obsidian_runs.sync_current_run(cr, scan, run_id)`. Single producer→graph entry point for both live sync and replay. | Makes Doc C's "producer never calls core directly" rule literal, not aspirational. Single code path = one place to debug/test/evolve. Closes OQ-E9 in extraction roadmap. |
| D-S1 | 2026-05-14 (Round 2 Codex) | **Multi-producer entity-id namespacing**: Obsidian grandfathered as bare slugs (implicit `obsidian:` namespace); all future producers MUST use explicit `<source_type>:<entity_id>` prefix. Adapter declares `entity_id_namespace: ClassVar[str \| None]`. | Retroactive migration of existing entities is destructive without operational benefit; grandfathering is cheaper. Cross-producer queries filter via `Source.source_type`, not slug prefix parsing. |
| D-S2 | 2026-05-14 (Round 2 Codex) | **Rebuild blast radius v1**: `graphdb-kdb rebuild` always drops the whole DB regardless of `--producer` flag. Producer-scoped rebuild deferred until producer #2 ships AND the team agrees the scoped semantics (tracked as L8 + blueprint TR-3). CLI prints warning before drop. | At v1 single-producer the simple correct semantics. Deferring lets the right scoped-rebuild rules be informed by real co-tenancy needs. |
| D-S3 | 2026-05-14 (Round 2 Codex) | Adapter declares `supported_journal_versions: ClassVar[list[str]]`. Mismatched versions return structured skip reason `'unsupported_version'` rather than silent corruption. | Producer journals evolve (Obsidian is at `2.0` today). Versioning discipline must be in place before Stage 1 of package extraction, not Stage 4. |
| D-S4 | 2026-05-14 (#63.7-A1 finding) | Phase 1 source-refresh in `graphdb_kdb/ingestor.py` does NOT bump `last_run_id` — `last_run_id` is bumped only by Phase 3 (`_update_source_ingest_state`) on actual ingest. `ON CREATE` seeds it as `''`. | Manifest's `last_run_id` is bumped only on compile events, never on bare scan. Graph must mirror this to produce zero `attribute_mismatch` divergence for sources that aren't touched in a given run. Without this, every scan-only run causes spurious drift. Discovered live during A1 inspection. |
| D-S5 | 2026-05-14 (#63.7-A2 finding) | Test isolation via autouse `conftest.py` fixture at `kdb_compiler/tests/conftest.py`: `monkeypatch.setenv("KDB_GRAPH_PATH", str(tmp_path / "graph_isolated"))`. Every test in the package gets a per-test graph directory. | Graph-sync routes through `ObsidianRunsAdapter().sync_current_run(...)` which resolves `KDB_GRAPH_PATH` to the live `~/Droidoes/GraphDB-KDB`. Without isolation, tests that exercise the full `compile(...)` pipeline silently write synthetic fixtures into the production graph. Discovered live during A2 inspection. |
| D-S6 | 2026-05-14 (Task B from #63.7) | `kdb-orchestrate --model <id>` accepts an id from `kdb_benchmark/models.json` registry (default: `gemini-3.1-flash-lite`). Inline registry loader avoids `kdb_benchmark` import (would create a cycle: `kdb_benchmark.runner` already imports `kdb_compiler.compile_one`). Both tools read the same `models.json`. Fail-fast on unknown id (prints active-model list) or `dropped: true` entries (prints `dropped_reason`). `compiler.run_compile()` extended to accept `use_completion_tokens` + `extra_body` provider knobs (previously only `compile_one` accepted them; `kdb_benchmark.runner` bypassed `run_compile`). | Same registry = same fail-fast behavior across both tools. Provider-specific knobs (e.g., gpt-5+ `use_completion_tokens`) reach the live LLM call from the production CLI path, not just the benchmark path. Validated live across 3 providers (anthropic/haiku-4.5, gemini/gemini-3.1-flash-lite, alibaba/deepseek-v4-flash) plus a graceful-failure scenario. |
| D-115 | 2026-07-21 (Task #115 ratification, spec v1.6) | **The Pass-2 contract is derivation-first: the LLM emits wiki-native data only** — `pages[]` (`slug`, `page_type`, `title`, `body`) + optional `compilation_notes`. Python owns identity (deterministic `expected_summary_slug(source_id)` + exact-stem semantic gate, model-authored slug), `status` stamping, and summary identification; the graph owns wikilink→LINKS_TO derivation (body-authority; legacy `outgoing_links` fallback). Six fields leave the contract (`concept_slugs`/`article_slugs`/top-level `summary_slug`/`outgoing_links`/`source_name`/`status`) with no aggregate reconstruction; `warnings` → `compilation_notes`; `log_entries` dropped; `confidence` logically deprecated (Entity scope — D-A2 updated); the system prompt moves to the repo (`compiler/prompts/`) with `pass2_prompt_version` + loaded-text SHA-256 stamps; the #65 Repair stage is deleted whole. Historical artifacts read-compatible via optional-deprecated fields + dual-mode validation. Full register D-115-1..15: `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md`. Cross-source slug reservation / MOVED lifecycle / durability carved to #116 (paired with #94). | Model-emitted mechanical aggregates were unearned classifications — Python derives them deterministically, so the model's surface shrinks to what only it can author (titles, bodies, wikilinks, page_type). Rejected: prompt-injected summary slug (model authorship preserved — gate-validated instead); Python reconstruction of removed aggregates (fictitious precision); keeping Repair-stage reconcilers (their defect classes are structurally impossible under the shrunk contract). |

---

## 10. Open Questions

| # | Question | Status | Plan |
|---|---|---|---|
| Open-1 | Statefulness implementation | ✅ **Closed (D7–D15)** | GPT 5.4 approach + Codex hardening |
| Open-2 | Output format / schema | 🟡 Partial | Frontmatter keys locked (D7); patch-ops JSON schema pending M2 |
| Open-3 | Safety model for Human Side edits | 🔴 Deferred | Only relevant to Track 2 (`llm-linker`), not v1 |
| Open-4 | Link direction between Sides | 🔴 Deferred | Track 2 concern; recommended **Option C (asymmetric + opt-in bidirectional)** but not confirmed |
| Open-5 | Binary file handling (PDF, images) in `raw/` | 🟡 Partial | v1 marks as `compile_mode: metadata_only`; actual PDF/image parsers = v2 |
| Open-6 | Page-intents JSON schema design (shape, not mechanism) | 🟡 Skeleton in M0.1; full design in M2 | Skeleton committed at `compiler/schemas/compile_result.schema.json` |
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
`page_writer`, `manifest_writer`, `kdb_compile.py` orchestrator (8-stage pipeline — since superseded by `kdb_orchestrate.py`), validate_compile_result with gate/measure split, reconciler for measure findings. Verified live on real vault 2026-04-21.

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
Task #74 — Stage [6] canonicalize lands as a top-level compile stage between reconcile and build_source_state; wiki and graph see the same canonical names. Locked decisions D-R5-1..D-R5-13 + D52. See §5 (pipeline), §8.2 (schema delta), §8.3 (adapter alias-write pass), §8.4 (rebuild + snapshot v2), and the full blueprint at `docs/archive/tasks/task74-canonicalization-blueprint.md`.
- **Sub-tasks shipped:** #74.1 schema delta (Entity.canonical_id + ALIAS_OF + migration); #74.2 `aliases.json` ledger loader; #74.3 `canonicalize.run()` algorithm; #74.4 Stage [6] wiring + journal `2.1 → 2.2` bump + `compile_result.schema.json` whitelist; #74.5 adapter Phase 3.5 — writes alias Entity + ALIAS_OF + `canonical_id`; #74.6 `graphdb-kdb verify` Layer 3 (C1–C4 invariants on the live graph); #74.7 snapshot format v2 + canonical_meta replay tests + back-compat tests; #74.8 docs (this section).
- **Round 5 external review:** Antigravity + Codex parallel reviews on the blueprint (see `docs/archive/rounds/round5-external-review-{antigravity,codex,prompt}.md`); locked OQ-E (direct-to-canonical SUPPORTS), OQ-F (canonical-wins + longest + UNION merge), OQ-G (JSON ledger format) before implementation.
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
- `docs/archive/early/code-review-M0-codex.md` — Codex 5.3 review of M0 scaffold (drove M0.1 remediation; 5 findings all actioned)

Reference implementations surveyed:
- Reddit #1 (fabswill) — mtime-based scan, manual orphan handling
- Ustaad (Sohardh/ustaad) — SHA-256 in frontmatter, log.md flagging
- ussumant/llm-wiki-compiler — standalone engine + MCP server
- Ar9av/obsidian-wiki — manifest-based state (closest to our v1)

Karpathy source:
- X post: https://x.com/karpathy/status/2039805659525644595
