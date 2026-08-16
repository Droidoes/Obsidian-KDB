# #123 P3a — Pass-1.5 Integration: Blueprint v0.1 (for panel review)

Date: 2026-08-03 · Task: **#123 Semantic graph search, phase P3a** · Status: **v0.1 — DRAFT, pre-ratification**

Extends the ratified #123 blueprint (`2026-07-26-task123-semantic-graph-search-blueprint.md`, v0.17)
§3 / §11 / §12 into a full Phase-2 blueprint, amended by the **owner rulings of 2026-08-03**
(ledger: `docs/TASKS.md`, "Task #123 P3a session rulings"). Where this document and v0.17
disagree, this document wins; every such point is marked **[AMENDS v0.17]**.

---

## 1. What P3a is

The wiring that makes Pass-1.5 real. `graph_search` is tested to 3,037 tests and has **no
caller anywhere outside `kdb_search/`** (verified by grep, 2026-08-03). Pass-2 is fed by
`compiler/context_loader.py:build_context_snapshot()`, whose T2 tier does a deterministic
PK/regex lookup on `entity_search_keys`. P3a replaces that lookup with the semantic selector
and retires the regex family outright.

After P3a, the per-source pipeline is:

```
Pass-1 enrich (frontmatter: domain, summary, key_themes, entity_search_keys, author)
  → Pass-1.5 adapter: materialize domain space → QueryPayload → graph_search
      → envelope sink (audit) + hit provenance read
  → context build: T1 (SUPPORTS) ∪ T2 (selector hits, selector order) ∪ T3 (1-hop)
  → Pass-2 compile_source (unchanged downstream of the snapshot)
```

## 2. Scope and non-goals

**In scope** (v0.17 §11 P3a row, carried): the pass-1.5 adapter (+ §3.1 plumbing);
`t2_selection` / `search_summary`; ContextRecordV2 + the dispatching loader (emit_kpis);
the envelope sink; KPI readers V1+V2; the measurement contract (§11); `query_kind: state_c`.

**[AMENDS v0.17] Now also in scope — the former P3b, folded into P3a** by the owner's
2026-08-03 REPLACE ruling: deletion of the T2Mode family (§7). v0.17 parked deletions
behind "experiments pass" (opus5 F3, B9); the owner has ruled the regex machinery does not
keep a seat at the table — *"not only does it not get a seat at the table, it doesn't get a
seat in the same continent of that table"* — founding evidence: PK/regex could not identify
search entries for `warren-buffett` / `charlie-munger`. The re-measurement-fallback
rationale for keeping it is withdrawn by the same ruling.

**Non-goals:** selector experiments / cohort A/B (P5a); the truth-set harness (P4);
CLI/MCP search surfaces and FTS (P5b); live vault ingestion (post-P3a, owner-gated);
split-model passes (#118 — single model across all three passes initially, owner ruling).

## 3. Binding rulings

### 3.1 Carried from v0.17 / spec v0.16 (not re-opened)

- **B7 placement:** adapter = `compiler/search_adapter.py`, imports `{common, kdb_graph,
  kdb_search}`; invoked inside `compile_source` step 1, before `build_context_snapshot`,
  inside the same try (adapter defect ⇒ existing `context_failed` channel).
- **§3.1 flow:** materialize slug-ascending space + `GraphSnapshotRef`; empty/missing
  domain ⇒ call `graph_search` with an empty reason-stamped space (core abstains, `call`
  never invoked); State C **runs** with `expressions: []`; pre-Pass-1 sources do not
  search; one search per source; envelope warn-only, `artifact_path` null on failure;
  one batched `entity_first_run_ids` read over validated hit slugs, adapter-side.
- **Request-bound violation:** `len(expressions) > MAX_EXPRESSIONS` raises
  `InvalidGraphSearchRequest(code="max_expressions_exceeded")` — exception, not a status;
  lands in `context_failed`; counter in adapter telemetry.
- **§3.3 / B8:** ContextRecordV2 + dispatching loader; hit-level provenance
  (`first_run_id`, `match_recency: pre_run|cohort|age_unknown`) with per-expression
  representative projection; KPI-time resolver recomputation removed (watched-series
  re-baseline only — the retiring fields are not in `GRAPH_WEIGHTS`, verified
  `compiler/kpi/score.py:68`); `context_failed.search` preserved.
- **§11 / F4+c-3:** the full measurement contract (§8 below).
- **D-123-H:** audit delivered on the result (8th field); the adapter owns persistence;
  search does no I/O. **Logging policy:** one-line summary per document, full bytes
  retained only on failure (~80 kB/receipt ⇒ ~125 MB per 1,586-note ingest if kept whole;
  a successful search's evidence is reconstructable from graph + snapshot hash).
- **Live bytes-per-token series (2026-08-02, #10):** the envelope persists
  `StageRecord.provider_input_tokens`; a KPI reader aggregates `measured_bytes_per_token`
  **per stage and per model — never blended**. D5 baseline (four tokenizer families):
  gemini-3.6-flash 3.7127 · deepseek-v4-flash 3.7632 · qwen3.7-flash 3.7911 ·
  gpt-5.4-mini 3.8308 B/token; failure threshold 3.20; `ESTIMATOR_BYTES_PER_TOKEN = 4` stands.

### 3.2 New owner rulings (2026-08-03)

- **R-P3a-1 — Strategic fork settled:** continue #123 through P3a; the 1,586-note vault
  ingestion waits, then runs instrumented (full chain).
- **R-P3a-2 — REPLACE, not supplement:** semantic selection is the sole T2 seeding path.
  Deletion scope (§7): STRUCTURED / LEGACY / LAYERED T2 modes, the regex machinery, the
  cold-start 2-hop widening. T1 (SUPPORTS edges) stays. Supersedes spec D1's P3b timing.
- **R-P3a-3 — T2 and T3 are either Pass-1.5-generated or empty.** Empty T1/T2/T3 is
  valid; Pass-2 compiles cold (proven daily by benchmark cold-compilation on an empty
  `ContextSnapshot`). T3 remains a deterministic 1-hop graph expansion of T1∪T2 seeds —
  empty seeds ⇒ empty T3, and that is a valid answer, not a defect.
- **R-P3a-4 — First sandbox run is full-chain only:** the first Vault-in-place-test-run
  E2E from now on is Pass-1 + Pass-1.5 + Pass-2. No interim current-pipeline run. That
  run doubles as the prompt-1.3.0 first live fire and the pre-vault smoke.
- **R-P3a-5 — Single model across all three passes initially** (deepseek-v4-flash /
  qwen3.7-flash the named candidates); the selector seat is the run's model. Split-model
  stays parked in #118. No new CLI flag: `sandbox-run.sh --model` already drives all passes.
- **R-P3a-6 — Output envelope: 1M ctx in / 64K out-token.** Pool entries currently
  register 384K (deepseek-v4-flash) / 128K (qwen3.7-flash) `max_output_tokens` — adjusted
  to 65,536 in P3a.0. Both pass the selector preconditions with headroom (thin reserve
  36,000; fat 26,000 — v0.17 §7.0).

## 4. Components

### 4.1 `compiler/search_adapter.py` (new)

Signature (v0.17 §3.1, carried verbatim):

```text
run_pass15(conn, *, frontmatter, selector: ModelSpec, vault_root: Path,
           state_root: Path, run_id: str, source_id: str, intra_run_order: int)
           -> Pass15Outcome
```

`Pass15Outcome` (new frozen dataclass, adapter-internal contract):
`search_ran: bool` · `t2_selection: list[str] | None` (validated hit slugs, selector
order; `None` = no search ran) · `search_summary: SearchSummary | None` (§5.2) ·
`envelope_written: bool`.

Flow (numbered per v0.17 §3.1, with the settled mechanics named):

1. **Gate:** `frontmatter is None` ⇒ return `Pass15Outcome(search_ran=False, …)` —
   pre-Pass-1 sources do not search (R-P3a-3: T2 stays empty; T1/T3 proceed).
2. **Materialize the space** (the adapter is *the* graph→search-space materializer —
   this discharges **#128**: `page_type` vocabulary validated HERE, at the boundary,
   exactly as `projection.py:125-128` assigns). Read `queries.domain_entity_slugs(conn,
   domain)` ∩ `queries.active_entities(conn)`, drop non-vocabulary `page_type` (counted,
   watched), sort slug-ascending (the dataclass does not sort — ordering is the
   materializer's obligation). Build `GraphSnapshotRef{schema_version,
   active_entity_count, space_fingerprint, source_kind: "domain_subtree",
   source_detail: domain}` — `space_fingerprint` = sha256 over canonical JSON of the
   ordered manifest (spec §5.1 convention).
3. **Empty/missing domain** ⇒ call `graph_search` with the empty reason-stamped space
   (`domain: None` ⇒ `domain_missing` watched class); core builds the abstention, `call`
   never invoked, zero spend.
4. **Assemble QueryPayload** via `projection.render_query_block(summary=…, domain=…,
   author=…, key_themes=…, expressions=entity_search_keys)` (SD-1 incl. `author`;
   State C ⇒ `expressions: []`, valid by construction). `query_kind` ("state_b" |
   "state_c") is adapter-side telemetry — the core is consumer-neutral by design (R2);
   it is recorded in the V2 record's search section, never sent to the core.
5. **One `graph_search(request, selector=selector, call=call_model_fn,
   body_reader=…)` per source.** `body_reader` binds `common/wiki_io.get_body(slug,
   page_type, root=vault_root)`; `ContentNotFoundError` degrades to title-only inside
   projection. (Fix in P3a.0: `search.py:200-201`'s docstring says `get_body` lives in
   `kdb_graph` — stale; it lives in `common/wiki_io`.)
6. **Envelope sink:** wrap `result.audit` in `SearchRunEnvelope{audit, run_id,
   source_id, intra_run_order, artifact_path}` (shape already declared,
   `kdb_search/artifact.py:368-379`, unused today) →
   `state/runs/<run_id>/search/<safe_source_id>.json`, atomic write, **warn-only** —
   `artifact_path` null on failure, the source outcome never affected.
7. **Provenance read:** one batched `queries.entity_first_run_ids(conn, hit_slugs)`
   (NEW — §4.2) over the validated hits (≤ `max_results`); per-hit
   `{slug, first_run_id, match_recency}` where `match_recency` = `cohort` if
   `first_run_id == run_id`, `pre_run` if a different known id, `age_unknown` if None.
   No alias/exact resolver participates (codex c-2).
8. **Return** ordered validated hits + the V2 search summary.

**Failure channels (fail-hard posture, carried):** typed outcomes
(`abstain_empty_space`, `budget_exceeded`, `selector_failure` with class) are
`result.status` values — the adapter converts them to an **honest empty T2 and compile
continues**. `InvalidGraphSearchRequest`, `SearchConfigError`, `ContractViolation`, and
any unexpected exception **propagate** — inside `compile_source`'s step-1 try they land
in the existing `context_failed` channel (`compiler.py:706-728`), with
`context_failed.search` non-null when the search completed before the raise (B8).

### 4.2 `kdb_graph` additions (minimal, boundary-respecting)

- **`queries.entity_first_run_ids(conn, slugs: list[str]) -> dict[str, str | None]`** —
  one batched read: `{slug: first_run_id}` for active entities. New function; the only
  new graph surface P3a needs. `kdb_graph` keeps its no-sibling-imports invariant.
- **Retained boundary (B9, unchanged):** `queries.resolve_to_canonical_slugs*` stay for
  MCP tool-arg identity + intake canonicalization — their output is **never** surfaced as
  search results, fallback, annotation, comparator, or telemetry (R1's enforcement
  clause). Their *retrieval* consumer (`context_loader`) is deleted (§7).

### 4.3 `compiler/context_loader.py` rewiring

`build_context_snapshot` signature changes:

- **NEW** `t2_selection: list[str] | None = None` — validated selector hits in selector
  order; `None` = no search ran (pre-Pass-1 / replay path). T2 = `t2_selection or []`
  intersected with the active same-domain pool minus T1, **order preserved** (selector
  rank feeds the within-tier ordering ahead of the PageRank tie-break; SD-2's strict
  tier ordering and the page cap are unchanged).
- **NEW** `search_summary: SearchSummary | None = None` — adapter's V2 summary for the
  telemetry product; never serialized into the prompt.
- **[AMENDS v0.17] DELETED at the same time** (was P3b): `mode` / `resolver` params,
  `T2Mode`, `_build_t2` / `_t2_structured` / `_t2_layered` / `_t2_legacy` /
  `_t2_from_search_keys`, `_t2_slug_in_text`, `_t2_title_in_text`, `_title_eligible`,
  `_whole_word_alternation`, the resolver wrappers (`_resolve_to_canonical_slugs*` —
  four thin wrappers), `_MIN_SEED_THRESHOLD` and the 2-hop widening (`max_hops` is
  always 1). See §7 for the full disposition.
- `ContextTelemetry` (common/types) loses `configured_t2_mode` /
  `effective_t2_strategy`; gains `search: SearchSummary | None`. `EffectiveT2Strategy`
  / `ConfiguredT2Mode` enums deleted. `keys_emitted` now carries the original
  (pre-truncation) expressions from the adapter; `key_outcomes` becomes the
  per-expression matched/unresolved projection (§5.2) — **the #122 dispositions
  (`resolved_t2_seed` / `already_t1` / …) retire with the resolver**: the V2 record's
  outcome vocabulary is `matched | unresolved`, annotation-carried.
- Unchanged: T1 (`source_supported_slugs`), the same-domain gate (D3), T3 1-hop
  mechanics, PageRank tie-break, page cap + projection, the two-product split
  (snapshot byte-facing / telemetry persistence-facing).

### 4.4 `compiler/compiler.py` + `orchestrator/kdb_orchestrate.py` plumbing

- `compile_source` gains `selector: ModelSpec | None = None` and
  `intra_run_order: int = 0`; **loses** `mode` / `resolver`. Step 1 becomes: adapter
  (when `context_snapshot is None` — the replay/tooling path never searches, writes no
  record, unchanged) → builder with `t2_selection` / `search_summary`.
- The orchestrator resolves the **selector `ModelSpec` once per run** from
  `common/models.json` (`resolve_models_json`, ctx_window asserted — B10) by the run's
  model id (R-P3a-5: selector seat = run model) and threads it with the per-source
  loop index as `intra_run_order`. v0.17's "check whether the ordering is recoverable
  from the manifest" is settled: **the loop index is authoritative** — the manifest
  records set membership, not compile order; recovering order post-hoc would derive
  the fact from a non-authoritative source. One param, persisted once in the envelope.
- `selector=None` + `context_snapshot=None` is a configuration defect ⇒
  `SearchConfigError` ⇒ `context_failed` (fail-hard; replay callers always pass a
  snapshot).

### 4.5 ContextRecordV2 + dispatching loader

**V2 schema** (`schema_version: 2`), written by `compile_source` to the same
`runs/<run_id>/context/<safe_source_id>.json` path:

- **Carried from V1 (H7):** `run_id`, `source_id`, `status`, `t1`/`t2`/`t3`
  TierRecords, `candidate_universe_size`, `domain_scope`, `cold_start`, `page_cap`.
- **Dropped:** `configured_t2_mode`, `effective_t2_strategy` (machinery deleted), and
  `max_hops` (constant 1 with widening gone — a field that cannot vary carries no
  information).
- **`keys_emitted`** = the original pre-truncation expressions (opus5 M4; rendered
  forms live in the envelope; truncation-flagged indices noted in the search section).
- **`key_outcomes`** (1:1 with `keys_emitted`): `{expression, status:
  matched|unresolved, annotation, matched_first_run_id, match_recency}` — the
  provenance pair is a deterministic projection of the hit-level facts: the
  highest-ranked validated hit attributed to that expression.
- **`search` section** (`null` only when no search ran): `status`, failure class,
  `execution`, `evidence_status`, `body_coverage`, `query_kind`, the §2.3/flow counts
  (eligible space size — SD-5's tracked trend series, no threshold — stage1_retained,
  stage2_pool_size, returned_entries, valid_entry_yield, unattributed_hit_count,
  retry_attempts), watched classes, concordance, selector `{provider, model, route}`,
  `latency_ms`, `cost_usd`, budget records, per-stage `{thin, fat}` token/cost/
  `provider_input_tokens` splits, `artifact_path`, `search_snapshot_hash`, and the
  **per-hit provenance list** `{slug, first_run_id, match_recency}`.
- **`context_failed` V2:** same null-observable invariants as V1, plus
  `context_failed.search` non-null when the search completed before the builder raised.

**Dispatching loader:** `parse_context_record(raw)` pre-reads `schema_version` and
routes to the V1 or V2 strict parser (today a V2 file degrades to a `malformed`
integrity issue — `parse_context_record_v1` hard-rejects `!= 1`). `ContextLoadResult.
records` widens to `list[ContextRecordV1 | ContextRecordV2]`; emit_kpis integrity
counting and reconciliation are unchanged; V1/V2/mixed histories all load.

### 4.6 KPI readers V1+V2 (`compiler/kpi/graph.py`)

- V1 path unchanged (historical records stay readable; the V1-only aggregates gate on
  V1 fields as today).
- V2 path: `context_build_success_rate`, `context_explicit_empty_count` (State C
  count), `context_t{1,2,3}_{candidates,delivered}_mean` read from the same fields —
  plus the new watched series: `search_status_counts`, `search_expression_
  {matched,unresolved}_rate`, `search_hit_recency_{pre_run,cohort,age_unknown}_rate`,
  `search_space_entity_count_mean` (SD-5 trend), `search_cost_usd_total`,
  `search_latency_ms_mean`, and the **bytes-per-token series:
  `search_bytes_per_token{stage: thin|fat, model}` — aggregated per stage × per model,
  never blended** (R: handoff §2(b)). Thin sends slug-heavy identity lines, fat sends
  whole prose bodies; one figure hides the spread the series exists to show.
- **Removed:** the KPI-time resolver recomputation (`search_key_late_resolution_rate`,
  `search_key_never_resolved_rate`) — watched-series re-baseline, not a board change
  (not in `GRAPH_WEIGHTS`, verified). **No resolver call in the KPI path** — pinned by
  test (§9).
- `emit_kpis.py:296`'s `copytree(run_dir, …/run_state)` auto-packages the new
  `search/` envelope dir into benchmark run dirs with zero changes.

### 4.7 Measurement contract (v0.17 §11, carried; mechanics named)

- **pass-1.5 stays OUT of the scored union** — scored axes unchanged in population; a
  test asserts adding a pass-1.5 record does not move them (G1).
- **New `SearchPassMeasurement`** (frozen dataclass, `common/measurement.py`) — one
  measurement **per search**, not per stage (avoids the pass-1 `duplicate_source_id`
  completeness collision): `run_id`, `source_id`, `pass_="pass1_5"`,
  `provider`/`model`, `prompt_versions: {thin, fat}` (G1.3 — `PassCallMeasurement`'s
  single `prompt_version` doesn't fit two prompts), `status`, `execution`, `calls`,
  `attempts`, `total_input_tokens` / `total_output_tokens` (summed over StageRecords),
  per-stage `{thin, fat}` token/cost splits, `total_latency_ms`, `cost_usd`,
  `search_snapshot_hash`. Projection `from_pass1_5(envelope: dict)` reads the envelope
  on disk; identification predicate: has `audit` + `run_id` + `source_id`.
- **Loader:** third glob block `<run_dir>/search/*.json` in `_load_run_measurements`;
  stats keys `pass1_5_dir_exists`, `pass1_5_identified`, `pass1_5_malformed`. Existing
  diagnostic series (`retry_load`, `token_overrun_rate`, `repair_rung_rate`) keep their
  pass1+pass2 population (H4).
- **Header:** `RunMeasurementHeader` gains `searches_attempted` (G1.2) — the D-117-5
  completeness contract marks the pass-1.5 column complete.
- **Reconciliation invariant (H5):** total run cost/calls == pass1 + pass1_5 + pass2;
  the independent side is the envelopes on disk: `len(glob("search/*.json")) ==
  searches_attempted` — a successful-write completeness condition; envelope write
  failure (warn-only) surfaces as an incomplete measurement state + a derived
  artifact-write-failure count, never a silent violation. (Note: the
  `search_artifact_write_failures` *core constant* stayed deleted per D-123-H; this
  count is derived at read time from null `artifact_path`s.)
- **Boards:** diagnostic `cost_usd_pass1_5`, `cost_unknown_calls_pass1_5`, call/retry
  counts, tokens, latency columns; `effective_top_weights` gains an explicit
  `pass1_5` case — no accidental fall-through (G1.4). No third ranked board.

### 4.8 Registry edit (P3a.0, R-P3a-6)

`common/models.json`: `deepseek-v4-flash.max_output_tokens` 384,000 → **65,536**;
`qwen3.7-flash.max_output_tokens` 128,000 → **65,536**. Registry test asserts the cap;
both entries keep `ctx_window: 1,000,000` and `tokens_lte_bytes: true` (selector route
preconditions, `budget.resolve_selector_route`).

## 5. Data schemas

### 5.1 Envelope on disk — `state/runs/<run_id>/search/<safe_source_id>.json`

`SearchRunEnvelope` (`kdb_search/artifact.py:368-379`, shape already declared):
`{schema_version, audit: SearchAuditPayload, run_id, source_id, intra_run_order,
artifact_path}`. The audit carries the full `StageRecord` bytes incl.
`provider_input_tokens` — one-line summary per document logged at write time; the file
itself is the failure-retained full evidence (D-123-H logging policy: the running log
keeps one line per doc; full bytes live only in this per-source envelope, and
downstream consumers reconstruct success evidence from graph + snapshot hash rather
than re-reading 80 kB receipts).

### 5.2 `SearchSummary` (adapter → context_loader → V2 record)

Frozen dataclass in `common/types.py` (persistence-facing; never prompt-serialized):
`search_ran`, `query_kind`, `status`, `failure_class`, `execution`, `evidence_status`,
`body_coverage`, `query_truncated_indices: tuple[int, ...]`, counts (§4.5 list),
`watched`, `concordance`, `selector: {provider, model, route}`, `latency_ms`,
`cost_usd`, `budget_records`, `stage_splits: {thin, fat}`, `artifact_path`,
`search_snapshot_hash`, `space_entity_count`, `hits: tuple[{slug, first_run_id,
match_recency, matched_expressions}, ...]`.

## 6. Integration boundaries

| Producer → Consumer | Contract |
|---|---|
| adapter → `kdb_search` | `GraphSearchRequest` / `GraphSearchResult`; core stays I/O-free, consumer-neutral, `{common}`-only imports |
| adapter → `kdb_graph` | `domain_entity_slugs`, `active_entities`, **new** `entity_first_run_ids`; adapter imports `kdb_graph`, core never does (B1) |
| adapter → `common/wiki_io` | `get_body(slug, page_type, root=vault_root)` — the two-vault-roots evidence binding test pins the bound root |
| adapter → disk | envelope, warn-only, atomic write |
| `compile_source` → `context_loader` | `t2_selection` / `search_summary`; telemetry never enters the prompt |
| `compile_source` → disk | one ContextRecord (V2) per source per run, both builder outcomes |
| `emit_kpis` / KPI | dispatching loader V1/V2/mixed; no resolver in the KPI path |
| measurement / boards | `search/*.json` glob; scored union untouched; reconciliation vs. header |

## 7. Deletion plan (former P3b — folded in per R-P3a-2)

| Delete | Where |
|---|---|
| `T2Mode`, `_build_t2`, `_t2_structured`, `_t2_layered`, `_t2_legacy`, `_t2_from_search_keys`, `_t2_slug_in_text`, `_t2_title_in_text`, `_title_eligible`, `_whole_word_alternation`, `_MIN_SEED_THRESHOLD`, 2-hop widening | `compiler/context_loader.py` |
| `_resolve_to_canonical_slugs{,_batch,_with_provenance,_with_provenance_batch}` wrappers | `compiler/context_loader.py` (the `kdb_graph.queries` originals stay — identity boundary, §4.2) |
| `mode` / `resolver` params | `build_context_snapshot`, `compile_source`, orchestrator call site |
| `ConfiguredT2Mode`, `EffectiveT2Strategy`, `KeyOutcome` (V1 vocabulary), #122 disposition enum | `common/types.py` — V1 parser keeps its own literal sets for historical reads |
| KPI-time resolver read + `search_key_{late,never}_*` series | `compiler/kpi/graph.py` |
| Tests: T2-mode dispatch, resolver parity, legacy/layered suites | `compiler/tests/` — disposition per file: delete mode-specific cases; port tier/cap/ordering cases to the `t2_selection` contract |
| Doc sweep | `CODEBASE_OVERVIEW.md` (T2Mode/STRUCTURED references), `AGENTS.md` architecture paragraph, #122 eval-doc re-baseline note (watched-series only) |

Sunset gates that no longer apply: D-90-12's three-part AND-gate and the NW-9
preconditions are superseded by R-P3a-2 (recorded, not silently dropped).

## 8. Phased implementation plan

| Phase | Content | Gate |
|---|---|---|
| **P3a.0 — foundations** | §4.8 registry edit (+test); `kdb_graph.queries.entity_first_run_ids` (+tests); stale `search.py` docstring fix | targeted + full suite green |
| **P3a.1 — adapter** | `compiler/search_adapter.py` + `SearchSummary`; space materialization incl. **#128 vocabulary check**; envelope sink; provenance read. Unwired | `test_search_adapter.py` green + full suite |
| **P3a.2 — wiring + deletions** | compile_source/orchestrator plumbing (`selector`, `intra_run_order`); context_loader rewiring; §7 deletions + test disposition + enum cleanup | `test_context_loader.py` / `test_compile_source.py` rewritten green; suite green; grep proves no `T2Mode`/`_t2_` references outside history |
| **P3a.3 — V2 records + KPI** | ContextRecordV2 factory/parser; dispatching loader; emit_kpis V1/V2/mixed; KPI readers V1+V2 + bytes-per-token series; KPI resolver-read removal | `test_context_record_v2.py`, `test_kpi_graph.py`, `orchestrator/tests/test_context_records.py` green; suite green |
| **P3a.4 — measurement** | `SearchPassMeasurement` + loader glob + stats; header `searches_attempted`; reconciliation invariant; board diagnostic columns | measurement tests (§9) green; suite green |
| **P3a.5 — docs + close** | North Star milestone changelog; AGENTS.md sweep; TASKS.md #123 row; session handoff | owner review |
| **Sandbox gate (Joseph fires)** | full-chain `scripts/sandbox-run.sh` — doubles as prompt-1.3.0 first fire + pre-vault smoke (R-P3a-4) | run completes; KPI/board/envelope inspection; THEN vault ingestion becomes schedulable |

## 9. Test plan (TDD-first; v0.17 §12 P3a list carried + amendments)

**P3a.1 (`compiler/tests/test_search_adapter.py`):** SD-1 payload incl. `author`;
materialization (slug-ascending; **non-vocabulary `page_type` dropped + counted —
#128**; fingerprint deterministic); missing domain ⇒ core abstention, zero calls;
State C ⇒ search runs, `query_kind: state_c`; pre-Pass-1 ⇒ no search; warn-only
envelope, `artifact_path` null on failure; `intra_run_order` threaded; two-vault-roots
evidence binding; hit-level `first_run_id`/`match_recency` via the batched read —
**resolver never invoked**; `InvalidGraphSearchRequest` propagates with zero calls,
zero StageRecords.

**P3a.2 (`compiler/tests/test_context_loader.py`, `test_compile_source.py`):** selector
order into EXISTING CONTEXT within tier; cap interaction; T3 expands from T1∪T2 seeds
only, always 1-hop; empty T1/T2/T3 ⇒ valid cold snapshot; one search per source;
**branch-specific call assertions** (typed status ⇒ zero or thin-only calls per the §8
table); `selector_failure` ⇒ honest empty T2 + compile continues; adapter defect ⇒
`context_failed`; replay path (`context_snapshot=`) never searches, writes no record;
deletion grep-guards (no `T2Mode`, no `_t2_` symbols, no mode/resolver params).

**P3a.3 (`compiler/tests/test_context_record_v2.py`, `test_kpi_graph.py`,
`orchestrator/tests/test_context_records.py`):** factory invariants; strict parser
(both directions of the status invariant); version dispatch; V1/V2/mixed histories;
`context_failed.search` preserved; hit-level + representative-projection shapes; V1+V2
KPI reads; **no resolver call in the KPI path**; expression-accounting series;
bytes-per-token aggregation asserted **per stage × per model** (a blended figure is a
test failure).

**P3a.4 (measurement):** a pass-1.5 record **does NOT move scored axes**; diagnostic
columns present; `searches_attempted` completeness; cost/call reconciliation
invariant; envelope-write-failure ⇒ incomplete measurement state, never silent.

## 10. Watch-fors for the first full-chain run (carried from the handoff, updated)

- **Prompt 1.3.0 has never fired live** (#126 re-specified `entity_search_keys` as
  query terms). The sandbox run is its first fire — inspect the emitted keys before
  trusting the search results built on them.
- **`thin fails ⇒ no fat` (D-123-G) is now visible** — no F1 masking; at sandbox scale
  every space is small, so thin failures surface directly.
- **Zero-key sources make §8.3 metric 6 degenerate** (unresolved-expressions metric
  reads empty); the V2 `query_kind` field exists precisely so this is readable.
- **DashScope content-filter false positives** (`data_inspection_failed`) — the
  durable provider-level risk; flagged twice on the Li Lu lecture.
- **Drive sync paused** during the run (sandbox script prompts; Kuzu corruption risk).

## 11. Open questions for the panel / owner

1. **OQ-P3a-1 — V2 drops `max_hops`** (constant-1 field deleted with the widening
   mechanism) rather than keeping it pinned at 1 for series continuity. Panel: any
   consumer we missed that reads it?
2. **OQ-P3a-2 — `SearchPassMeasurement` as a new dataclass** vs. widening
   `PassCallMeasurement` (single `prompt_version` doesn't fit two prompts; a third
   type keeps the pass1/pass2 projections untouched). Confirm the new-type reading.
3. **OQ-P3a-3 — T3 pool stays same-domain-gated** (D3 gate applies to T3 exactly as
   today; the selector's T2 hits are already domain-scoped by space construction).
   Carried silently in v0.17; stated here for confirmation.
4. **OQ-P3a-4 — deleted-series tombstones:** the retiring watched series
   (`search_key_late_resolution_rate` etc.) vanish from KPI output post-P3a.3. Keep a
   one-release tombstone note in the KPI payload, or a clean cut with the re-baseline
   note in docs only?

## 12. Changelog

- **v0.1 (2026-08-03)** — initial draft. Extends v0.17 §3/§11/§12 with settled
  mechanics (model seat, intra_run_order authority, envelope path, V2 field list,
  deletion disposition); folds former P3b into P3a per R-P3a-2; closes #128 by
  assigning vocabulary validation to the adapter-materializer.
