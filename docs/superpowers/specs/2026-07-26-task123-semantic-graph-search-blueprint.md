# #123 — Semantic Graph Search: Blueprint v0.3 (for Joseph's ratification)

Date: 2026-07-26 · Task: **#123 Semantic graph search** · Status: **v0.3 — concurrence pass absorbed (codex CONCUR-WITH-ITEMS, items 1–5; opus5 CONCUR-WITH-ITEMS, G1–G8; all checkable claims verified against the repo); for Joseph's ratification**
Basis: **spec v0.4 RATIFIED + v0.5 amendments (D1–D4, Joseph 2026-07-26)** · vision v1.5 · fixture v1 (`3d271e2`) · truth probes draft-v1 (39 probes, `a3c832a`) · v0.1 reviews + synthesis · v0.2 concurrence responses (`…-blueprint-v0.2-concurrence-codex.md`, `…-blueprint-v0.2-concurrence-opus5.md`).

**Joseph's rulings (2026-07-26), binding:** **D1** — coding starts at blueprint sign-off; live experiments/tuning/ingestion and the destructive P3b wait for labels+gates/experiments. **D2** — State C runs the search (`expressions: []`, `query_kind: state_c`); D-90-8 retired. **D3** — no fat call on thin-empty with N>M; `completed` + `thin_attempted` + `thin_retained_zero` (R4 amendment; codex's dissent recorded). **D4** — screening cohort: gemini-3.6-flash (interim default) + gpt-5.4-mini + deepseek-v4-flash.

---

## 1. Package boundary (B1 — selected, pending blueprint ratification)

`kdb_search/` — new sibling package, imports **`{common}` only** (caller materializes the space; projection via `common/wiki_io.get_body`; selector via `common/call_model`; route via `common/model_pool.resolve_models_json`). Boundary test: `kdb_search` added to `INTERNAL`; `ALLOWED` rows `"kdb_search": {"common"}`, `"compiler": {…, "kdb_search"}`, `"tools": {…, "kdb_search"}` (P4 harness). The P5b MCP edge is added only when its materialization owner is named (not `kdb_graph`).

Packaging (P1): `packages.find` gains `kdb_search*`; package-data gains `kdb_search/prompts/*.txt`; `testpaths` gains `kdb_search/tests`; offline built-wheel prompt-loading smoke test.

## 2. Module design

```
kdb_search/
  __init__.py  types.py  projection.py  budget.py  prompts.py
  prompts/selector_thin_v1.txt  prompts/selector_fat_v1.txt
  response.py  search.py  artifact.py  replay.py  tests/
```

### 2.1 Core signature

```python
def graph_search(
    request: GraphSearchRequest,          # query, search_space (caller-materialized), max_results, opts
    *,
    selector: ModelSpec,                  # resolved via resolve_models_json(id) — fail hard at resolution:
                                          # unknown id / missing api_key_env / **ctx_window None** (G6) all
                                          # raise typed config errors before any search work
    call: Callable[[ModelRequest], ModelResponse],   # one API call per invocation; injectable
    body_reader: Callable[[str, PageType], str],     # default: get_body bound to the caller's vault_root
) -> GraphSearchResult:                    # hits, unresolved_expressions, status, execution,
                                           # evidence_status, body_coverage, telemetry, audit (always, §6)
```

### 2.2 Two-stage orchestration (R4 as amended by D3)

```text
graph_search(request):
    space empty / reason-stamped-empty
        → abstain_empty_space, execution=not_executed           # one audit path; `call` never invoked
    estimate > floor(selector.ctx_window × 0.8)
        → budget_exceeded, execution=not_executed               # zero spend, never retried (R2)

    thin = stage_call("thin", …)                                # up to 2 logical attempts (§8); always runs
    if thin failed after its retry budget:
        if N ≤ M:   → proceed to fat with stage2 = all eligible; concordance: null;
                      telemetry thin_failed_nonbinding; execution=fat_after_thin_failure   # opus5 F1/G8.1
        else:       → selector_failure, execution=thin_attempted, failure_class recorded

    stage2_slugs = all_eligible if N ≤ M else thin.retained_validated     # manifest order (codex #3)
    if N > M and stage2_slugs empty:                             # D3 — no fat call; complete contract (codex c-1):
        → status=completed, execution=thin_attempted, hits=[],
          unresolved_expressions = ALL request expressions, concordance=null,
          evidence_status=not_applicable, body_coverage=None, fat-side yields null,
          telemetry thin_retained_zero (watched)

    fat = stage_call("fat", render fat over stage2_slugs with excerpts)  # up to 2 logical attempts (§8)
    if fat failed after its retry budget:
        → selector_failure, execution=two_stage_attempted, failure_class recorded

    result = response.validate_and_account(fat)                  # spec §2.3 salvage + expression accounting
    telemetry.concordance = len(fat_top10 ∩ thin_top20) / len(fat_top10)
                            #   None when fat has no validated hits or no fat stage ran (codex #12)
    audit = artifact.build(…)                                    # one StageRecord per logical attempt (§8)
```

**`execution` values:** `not_executed | thin_attempted | two_stage_attempted | fat_after_thin_failure` (the last names the opus5-F1 path: thin failed, N≤M, fat ran — G8.1).

### 2.3 Response handling (spec §2.3 — unchanged)

Four-way classification; per-entry drop+count; per-field coerce+count; never wholesale-discard a parseable response; controller-computed expression accounting with the ratified annotations; escaped foreign-identity rate = 0 by construction; thin validation = the same rule over `retained`.

## 3. The pass-1.5 adapter + context-build integration

### 3.1 Adapter (`compiler/search_adapter.py`, imports `{common, kdb_graph, kdb_search}`)

Invoked inside `compile_source` step 1, before `build_context_snapshot`, inside the same try. Explicit inputs:

```text
run_pass15(conn, *, frontmatter, selector: ModelSpec, vault_root: Path,
           state_root: Path, run_id: str, source_id: str, intra_run_order: int)
```

**P3a plumbing (opus5 G8.2 — named now, not discovered mid-phase):** `compile_source` today has no ordering param and the orchestrator loop passes no index; the selector reaches the compiler as provider/model/route scalars. P3a threads `intra_run_order` and a selector model id through `compile_source` (resolving to `ModelSpec` inside); **check whether the ordering is already recoverable from the manifest before persisting it a second time**; a CLI flag for selector-id switchability lands with P5b's live cohort.

Flow: (1) materialize the domain space slug-ascending + `GraphSnapshotRef`; (2) empty/missing domain ⇒ call `graph_search` with an empty reason-stamped space (abstention built by the core; `call` never invoked); (3) assemble QueryPayload (SD-1; **State C runs** with `expressions: []`, `query_kind: state_c` — D2; pre-pass-1 sources do not search); (4) one `graph_search` per source; (5) envelope → `state/runs/<run_id>/search/<safe_source_id>.json`, warn-only, `artifact_path` null on failure; (6) return ordered validated hits + V2 search summary. Two-vault-roots test proves the bound root supplies archived evidence.

### 3.2 `build_context_snapshot` changes

`t2_selection: list[str] | None` (selector order; `None` = no search ran) + `search_summary`. T1/T3/cap/ordering unchanged (SD-2 preserved; stage-1 pool recorded separately). `mode`/`resolver` params removed in P3b.

### 3.3 ContextRecordV2 (hit-level provenance — codex c-2 + opus5 G2, synthesized)

- **Loader dispatch:** version-dispatching `parse_context_record` (V1|V2); `ContextLoadResult`/`ContextEvidence`/`orchestrator/emit_kpis.py`/record tests updated for V1, V2, mixed histories. `context_failed.search` non-null when search completed before the builder raised.
- **Provenance lives on the HIT (opus5 G2's carrier; codex c-2's cardinality resolved all-match at hit level):** the V2 `search` section carries per-hit `{slug, first_run_id, match_recency: pre_run|cohort|age_unknown}` — from **one batched direct read over the validated hit slugs post-validation** (new `kdb_graph.queries.entity_first_run_ids(conn, slugs)`; `active_entities()` does not carry it; **no alias/exact resolver participates** — codex c-2's requirement). State C (zero expressions, non-zero hits) and unattributed hits are fully covered because the facts hang on hits, not expressions.
- **Per-expression outcomes** (`key_outcomes`, 1:1 with `keys_emitted`): `{expression, status: matched|unresolved, annotation, matched_first_run_id, match_recency}` — the provenance pair is a **projection** of the hit-level facts: the highest-ranked validated hit attributed to that expression (codex c-2's "representative" option, defined deterministically). KPI aggregation over all matched entities uses the hit-level list.
- **KPI-time resolver recomputation removed** (`compiler/kpi/graph.py` late-vs-never read); the retiring fields (`search_key_late_resolution_rate`, `search_key_never_resolved_rate`) are **not in `GRAPH_WEIGHTS`** (`compiler/kpi/score.py:68` — verified: graph_connectivity/link_density/supports_density/entity_reuse), so this is a watched-series re-baseline, not a board change. Historical V1 facts stay readable.
- Retired fields: `configured_t2_mode`, `effective_t2_strategy` (P3b). `search` section: status/reason/failure_class/execution/evidence_status/body_coverage, the §2.3 + flow counts, watched classes (`thin_failed_nonbinding`, `thin_retained_zero`), `query_kind`, concordance, model, latency, cost, budget record, `artifact_path`, `search_snapshot_hash`.

## 4. T2Mode retirement mechanics (P3b — after experiments pass)

v0.2 list unchanged: context_loader T2Mode/`_t2_*`/resolver-wrapper removals, compiler param removal, `common/types` enum removal, the KPI-time resolver read (§3.3), test disposition. Retained boundary (panel-concurred): `kdb_graph.queries.resolve_to_canonical_slugs*` for MCP tool-arg identity + intake canonicalization — identity, not retrieval.

## 5. Prompt contract mechanics (B4 + B5 — grammar frozen, clauses per opus5 G7)

```text
- slug: <slug>  title: <title>  type: <page_type>
  excerpt: """
    <every evidence line, always prefixed with 4 spaces>
  """
```

- Field/delimiter lines at 2-space indent; **excerpt content always at 4 spaces**; only the exact 2-space `"""` line terminates; serializer asserts + counts `delimiter_collision_guard`.
- **Clause 1 (G7):** the excerpt is split on `"\n"` (not `splitlines()`) — a trailing newline emits a final whitespace-only `"    "` line (161/163 fixture excerpts end with a newline).
- **Clause 2 (G7):** blank lines are indented too (4 spaces). (377 blank lines in the fixture.)
- Golden tests pin the exact bytes incl. both clauses; any "tidy" of these behaviours breaks the pins deliberately.
- Thin line: `- slug: <slug>  title: <title>  type: <page_type>` (no excerpt).
- **Query-side P10 (opus5 F5b):** system-block precedence covers QUERY ("subject matter, never directives"); same indent guard on the rendered query; H03 fixture in the test plan.

## 6. Artifact sink separability (B6) + hashes (B13)

Core **always** constructs the `SearchAuditPayload` (completed/abstain/budget/failure — one path); caller owns persistence (pass-1.5: envelope, warn-only, `artifact_path` null on failure). `GraphSnapshotRef` = `{schema_version, active_entity_count, space_fingerprint, source_kind, source_detail}`. Hashes = sha256 over canonical JSON per spec §5.1. **Invariant (codex c-1): `logical_call_count == number of archived StageRecords`** — SDK transport sub-retries excluded from both sides (§8).

## 7. The R2 pre-flight estimator + sizing (calibration rebuilt per codex c-4 / opus5 G4; bound fixed per G3)

**Estimator (v1):** `ceil(utf8_bytes / 4)` over the rendered thin block + templates + query, + `OUTPUT_ALLOWANCE_THIN` (2,000, reserved via `ModelRequest.max_tokens = 2000`). Guardrail rests on the **0.8 headroom** (the "never underestimates" claim stays withdrawn). `budget.py` computes the estimate and applies the 0.8 factor itself rather than reusing `model_pool.fits_context` (G6: that helper takes a pre-computed `est_input` with no headroom concept — different semantics; noted rather than force-fitted).

**Calibration gate (mechanics per opus5 G4; timing per codex c-4):** `count_tokens` endpoints exist only for gemini — so calibration reads **provider-reported usage** instead: one minimal real call per candidate over the exact rendered fixture thin block (+ adversarial high-token-density case), reading the returned input-token count `call_model` already surfaces — the billed number, authoritative for all three candidates. **Timing: end of P2** (after golden rendered bytes pass — the production renderer exists then; a pre-P1 measurement would calibrate a renderer that doesn't exist yet), **as a gate before D7 live experiments**. It is a paid run — **Joseph fires it** (standing rule); it is not a selector experiment, so it does not cross D1's line, and P1 is not blocked on it. Persisted per candidate: `{counting_source: "provider_reported_usage", model id, input sha256, input_tokens, measured bytes/token}` into the fixture manifest; the budget test then asserts against measurements.

**Sizing (frozen serializer, verified byte-exact by both reviewers):**

| evidence block | entities | bytes | bytes÷4 | per-entity |
|---|---|---|---|---|
| thin, whole graph | 163 | 14,343 | ~3.6k | 88 B |
| thin, value-investing | 51 | 4,404 | ~1.1k | 86 B |
| fat, whole graph | 163 | 112,673 | ~28.2k | 691 B |
| fat, value-investing | 51 | 38,512 | ~9.6k | 755 B |
| fat, largest-150 subset | 150 | 107,885 | ~27.0k | 719 B |

- **Stage-2 bound (opus5 G3 — the v0.2 figure was falsified by the fixture):** the per-entity figure is derived from the **policy maximum** (250w + 25w extension ≈ 275w at the corpus's ~8.8 B/word + indent + field overhead ≈ **2,500 B**) and verified against the **fixture maximum 2,209 B** (`value-investing-as-owner-mindset…`, 251w) — `150 × 2,500 B = 375 kB ≈ 94k tokens < 102.4k` (80% × 128k): an **8% margin**, asserted in the §9 test against the policy-max formula and the fixture max. No architecture consequence (pool is 400k/1M/1M).
- **Why only stage 1 is guarded (the named asymmetry, G3's optional item — declined for v1):** thin is unbounded in N (the whole point of the guard); fat is statically bounded by M=150 × policy-max ≈ 94k, which holds for any window ≥128k. A fat-stage estimator would be a spec amendment (R2 is a stage-1 rule); recorded, not adopted.
- Vault-scale projections (measured): thin whole-graph ~9,600 × 88 B ≈ 845 kB ≈ **~211k tokens**; largest-domain ~3,000 ≈ 264 kB ≈ **~66k**; fat ≤ 150 ≈ ≤27k expected / ~94k policy-bound. All pass the configured pool's 80% budgets.
- Cost upper bound per source (largest domain): ~10.7k conservative input tokens → ~$0.01–0.02 today; 1,706-source re-ingest ≈ **$25 deepseek / $115 gpt-5.4-mini / $230 gemini**.

## 8. Selector route (B10) + retry composition (B11 — contract frozen per codex c-1; policy label per opus5 G5)

**B10:** `ModelSpec` via `resolve_models_json` (fail-hard incl. `ctx_window` present — §2.1); `DEFAULT_SELECTOR_MODEL_ID = "gemini-3.6-flash"` (interim); cohort per D4; production default post-D7.

**B11 — the stage/attempt contract:**

- **Up to two logical attempts per executed stage; attempt 2 only after an allowed retry class** (transport, timeout, `unparseable_response`, `structurally_unusable_response`, `all_entries_dropped`). Each logical attempt = one `call(ModelRequest)` (production: single `call_model` — not the 3-attempt wrapper).
- One `StageRecord` per logical attempt incl. failures; `logical_call_count == archived StageRecords` (§6).
- **The stage entry records the provider's *actual* SDK sub-retry policy** (G5 — verified: openai-family `max_retries=2`, `common/call_model.py:192/:273`; **gemini has none** — `call_model.py:212`: no such constructor kwarg, `HttpOptions.retry_options` default None). Never counted as selector attempts.
- **Backoff posture: deliberately pass-1's** (G5's option b — bare `call_model`, no wrapper; precedent `ingestion/enrich/pass1_caller.py:179`): the kdb_search loop retries immediately on the allowed classes. Recorded as a posture adoption, not an oversight; a Retry-After/exponential layer is a later refinement if telemetry shows transport flakes dominate.
- Branch-specific call counts (replaces "two calls per executed search" everywhere — §3.1, phases, tests):

| terminal path | logical selector calls |
|---|---:|
| empty space / budget_exceeded | 0 |
| D3 thin-retained-zero (N>M) | 1–2 thin, 0 fat |
| normal completed | 1–2 thin + 1–2 fat = 2–4 |
| thin exhausted, N>M | 2 thin, 0 fat |
| thin exhausted, N≤M → fat (F1) | 2 thin + 1–2 fat = 3–4 |
| fat exhausted | 1–2 thin + 2 fat = 3–4 |

## 9. Replay modes (spec §5.2 — unchanged)

Record replay (default; integrity hash validated; no calls/reads) and historical selector re-call (opt-in; archived bytes + manifest only; stamped `historical_recall`).

## 10. Truth-set harness shape (P4)

`tools/benchmark/` harness over fixture v1 (checksum-verified; body_reader serves frozen bytes), 39 probes (incl. H03), spec §8.3 metrics 1–7 + failure/retry rates + concordance + cost; reduced-M protocol parameterized (M=10/20 over the 51; M=20/40 over the 163). **Live runs wait for Joseph's labels + gates (D1).**

## 11. Measurement/board contract (codex c-3 + opus5 G1 — decided) + phased plan

**The pass-1.5 measurement decision (codex c-3's option 2 + opus5 G1's "kept separate" fix):**

- **pass-1.5 stays OUT of the scored union.** Scored axes (`quarantine_rate`, `recovery_rate`, `latency` per-1M-token over pass1+pass2) are unchanged in population; **a test asserts that adding a pass-1.5 record does not move them** — every 2026-07-25 baseline row stays comparable, no silent re-baseline (G1's blocking reading closed).
- **Cost-centre diagnostics, no third ranked board:** the measurement loader gains a `pass1_5` projection (glob `search/*.json`); aggregate evidence + rendered raw columns gain `cost_usd_pass1_5`, `cost_unknown_calls_pass1_5`, call/retry counts, tokens, latency. `effective_top_weights` gets an explicit `pass1_5` case (no accidental fall-through — G1.4).
- **One measurement per search** (not per stage): avoids the pass-1 `duplicate_source_id` completeness collision; per-stage cost/prompt attribution survives as fields inside the search measurement — `prompt_versions: {thin, fat}` (G1.3; `PassCallMeasurement`'s single `prompt_version` doesn't fit two prompts).
- **Header analog (G1.2):** `RunMeasurementHeader` gains `searches_attempted` so the D-117-5 completeness contract can mark the pass-1.5 column complete.
- **Reconciliation invariant (codex c-3):** total run cost and call count == pass1 + pass1.5 + pass2 (integration test).

**Phases (calibration re-timed per codex c-4; plumbing per G8.2):**

| Phase | Content | Gate |
|---|---|---|
| **P1 — core, no LLM** | packaging (§1), types, projection (§5 grammar + clauses), budget estimator, response salvage/accounting, artifact builder + hashes, boundary rows | targeted tests + full suite green |
| **P2 — selector orchestration** | prompt templates + guards, two-stage `graph_search` (canned `call`), retain-all, F1 path, D3 terminal, concordance, 2-attempt loop + per-attempt StageRecords, replay, P10 fixtures (evidence + query-side), golden bytes, stage-2 bound assertion (policy-max + fixture-max) | targeted tests + full suite green |
| **Calibration (end of P2)** | §7 usage-reported measurement, all three candidates, Joseph fires | measurements persisted in fixture manifest |
| **P3a — additive integration** | adapter (+ §3.1 plumbing), `t2_selection`/`search_summary`, ContextRecordV2 + dispatching loader (emit_kpis), envelope sink, KPI readers V1+V2, **measurement contract (§11)**, `query_kind: state_c`. T2Mode parked (`# retired, pending D7`) | targeted + integration tests (§12) + full suite |
| **P4 — truth-set harness** | §10 harness, self-tested on canned outputs | harness self-tests green |
| **D7 gate** | Joseph's labels + numerical gates (his schedule) | — |
| **P5a — experiments** | 3-candidate A/B (D4), reduced-M stage-1 recall gate, §8.5 cross-domain A/B | truth-set gates pass |
| **P3b — destructive retirement** | §4 deletions + test disposition + #122 eval-doc re-baseline note (watched-series only — §3.3) | experiments pass (opus5 F3) |
| **P5b — ship + second consumer** | live cohort (Joseph-gated, Drive paused, selector-id CLI flag), CLI/MCP surface (materialization owner named), FTS track | Joseph-gated |

## 12. Test plan (TDD-first; concurrence items folded)

**P1 (`kdb_search/tests/`):** `test_contract.py` (status × execution × evidence_status matrix incl. the D3 terminal's complete contract: all expressions unresolved, concordance null, evidence_status `not_applicable`, body_coverage None; `fat_after_thin_failure` naming); `test_response.py` (four-way, 6-of-10, coercion, accounting); `test_zero_escape.py` (property); `test_budget.py` (zero-invocation `budget_exceeded`; never retried; estimator asserted against **recorded calibration measurements**; **stage-2 bound = policy-max formula verified against fixture max 2,209 B**; `max_tokens=2000`; **`ctx_window=None` route ⇒ typed config error at resolution, before any work**); `test_projection.py` (policy v1 + **§5 grammar incl. both G7 clauses — trailing-newline whitespace line, indented blank lines**); `test_artifact.py` (payload on all paths; `logical_call_count == StageRecords`; hashes); packaging smoke tests.

**P2 (`kdb_search/tests/`):** `test_prompts_golden.py` (pinned bytes; version/SHA guard); `test_two_stage.py` (thin→fat order; retain-all variants; **branch-specific call counts per the §8 table**; F1 path (proceed + `thin_failed_nonbinding` + concordance null + `fat_after_thin_failure`); D3 terminal (no fat call + `thin_retained_zero`); concordance formula + null cases; retry classes ⇒ attempt 2 archived; exhausted ⇒ typed `selector_failure`; stage entry records the provider's actual sub-retry policy); `test_adversarial.py` (H01/H02 evidence-side, H03 query-side); `test_replay.py`.

**P3a (`compiler/tests/`, `orchestrator/tests/`, `tools/tests/`):** `test_search_adapter.py` (SD-1 payload incl. author; materialization; missing domain ⇒ core abstention, zero calls; State C ⇒ search runs, `query_kind: state_c`; pre-pass-1 ⇒ no search; warn-only envelope, `artifact_path` null on failure; `intra_run_order` threaded; two-vault-roots evidence binding; **hit-level `first_run_id`/`match_recency` via the batched read — resolver never invoked**); `test_context_loader.py` (selector order into EXISTING CONTEXT; cap interaction; cold-start widening); `test_context_record_v2.py` (factory invariants; strict parser; version dispatch; V1/V2/mixed; `context_failed.search` preserved; hit-level + representative-projection provenance shapes); `test_compile_source.py` (one search/source; **branch-specific call assertions**; selector_failure ⇒ honest empty T2 + compile continues; adapter defect ⇒ `context_failed`); `test_kpi_graph.py` (V1+V2; **no resolver call in the KPI path**; expression-accounting series); `orchestrator/tests/test_context_records.py` (emit_kpis V1/V2/mixed); **measurement tests: pass-1.5 record does NOT move scored axes; diagnostic columns present; `searches_attempted` completeness; cost/call reconciliation invariant**.

**P4:** harness self-tests (probe loading incl. H03, metrics, reduced-M, gates).

**Live cohort (P5b, Joseph-gated, Drive paused):** 3-model baseline re-run; before/after on T2 delivered, `matched`, `match_recency`.

## 13. Decision record (B1–B14 — final dispositions)

| # | Question | Disposition |
|---|---|---|
| **B1** | Package boundary | **Selected, pending blueprint ratification** (label corrected per codex c-5): `kdb_search/`, `{common}`; packaging per §1 |
| **B3** | Estimator | `ceil(utf8_bytes/4)` + 2k reserved output vs 80% window; calibration = provider-reported usage at end of P2, Joseph fires (§7) |
| **B4** | Prompt storage | `kdb_search/prompts/*.txt`, version + SHA guard, package-data + wheel smoke test |
| **B5** | Escaping | Frozen grammar (§5) incl. G7 clauses; JSON-array amendment rejected |
| **B6** | Artifact sink | Core always constructs; caller persists; `artifact_path` null on failure; `logical_call_count == StageRecords` |
| **B7** | Adapter placement | `compiler/search_adapter.py` in `compile_source` step 1; explicit `vault_root`/`intra_run_order`/`ModelSpec`; §3.1 plumbing named |
| **B8** | Record evolution | V2 + sibling envelope; dispatching loader; `context_failed.search` preserved; **hit-level provenance + representative per-expression projection**; KPI resolver read removed (no scored axis touched) |
| **B9** | T2Mode retirement | P3a parks (`# retired, pending D7`); P3b deletes after experiments pass; kdb_graph resolvers retained (identity) |
| **B10** | Selector route | `ModelSpec` via `resolve_models_json` (ctx_window asserted); cohort = gemini (interim) + gpt + deepseek (D4) |
| **B11** | Retry composition | Up-to-2 logical attempts/executed stage; per-attempt StageRecords; actual sub-retry policy recorded; pass-1 no-backoff posture adopted (§8) |
| **B12** | FTS track | P5b, independent CLI/MCP-surface track |
| **B13** | Refs + hashes | Caller-computed `GraphSnapshotRef`; canonical-JSON sha256s |
| **B14** | Gate + edges | D1–D4 per Joseph (binding); plus F1 (`fat_after_thin_failure`), F4/c-3 (§11 measurement contract), F5b (query-side P10), codex #12 (concordance) |

## Changelog

- **v0.3 (2026-07-26)** — concurrence pass absorbed (codex items 1–5, opus5 G1–G8; every checkable claim verified against the repo first: fixture max fat block 2,209 B; gemini has no `max_retries` (`call_model.py:212`); `ModelSpec.ctx_window` is `int|None`; retiring KPI fields absent from `GRAPH_WEIGHTS`). codex c-1: stage/attempt contract frozen ("up to two logical attempts per executed stage"), branch-specific call-count table, `logical_call_count == StageRecords`, D3 terminal's complete result contract. c-2 ≡ opus5 G2: provenance moved to hit level (batched direct read, no resolver) with the per-expression representative projection; State C/unattributed hits covered. c-3 ≡ G1: measurement contract decided — pass-1.5 out of the scored union (non-movement test), cost-centre diagnostics, per-search measurement with `prompt_versions {thin,fat}`, `searches_attempted` header, reconciliation invariant, explicit weights case. c-4 ≡ G4: calibration = provider-reported usage at end of P2, Joseph fires; no `count_tokens` dependency. c-5: spec v0.5 amendments published (D1–D4), ledger + North Star synced, B1 label corrected. opus5 G3: stage-2 bound re-derived from policy-max (2,500 B/entity ⇒ 94k < 102.4k, 8% margin) verified against fixture max; fat-stage estimator declined with the unbounded-vs-static asymmetry recorded. G5: actual sub-retry policy recorded per provider (gemini none); pass-1 no-backoff posture adopted. G6: `ctx_window` asserted at resolution; `fits_context` non-reuse noted. G7: two serializer clauses (trailing-newline whitespace line; indented blank lines). G8: `fat_after_thin_failure` execution value; P3a plumbing named.
- **v0.2 (2026-07-26)** — v0.1 panel review absorbed (codex REVISE 9+2; opus5 F1–F8) + **Joseph's rulings D1–D4** (coding at sign-off; State C runs; no fat call on thin-empty N>M + `thin_retained_zero`; deepseek joins the cohort). 12 convergent absorptions: packaging; serializer grammar frozen + sizing recomputed; emit_kpis dispatch; KPI resolver removal; 2-attempt loop; adapter wiring; single empty-space audit path; estimator honesty + calibration gate; concordance denominator; thin-failure-nonbinding; P3a/P3b split; measurement reader + query-side P10 (H03).
- **v0.1 (2026-07-26)** — initial blueprint for panel review.
