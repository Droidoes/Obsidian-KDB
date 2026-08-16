# #123 P3a — Pass-1.5 Integration: Blueprint v0.2 (post-review amendment fold)

Date: 2026-08-03 · Task: **#123 Semantic graph search, phase P3a** · Status: **v0.2 — review amendments folded, for ratification**

**Supersedes v0.1** (`2026-08-03-task123-p3a-blueprint-v0.1.md`) following the two panel
reviews of 2026-08-03 — Opus 5 (`2026-08-03-task123-p3a-blueprint-v0.1-review-opus5.md`)
and Codex round 1 (`2026-08-03-task123-p3a-blueprint-v0.1-review-round-1-codex.md`). Every
folded amendment is mapped, finding → disposition → sections changed, in §11.

Extends the ratified #123 blueprint (`2026-07-26-task123-semantic-graph-search-blueprint.md`, v0.17)
§3 / §11 / §12 into a full Phase-2 blueprint, amended by the **owner rulings of 2026-08-03**
(ledger: `docs/TASKS.md`, "Task #123 P3a session rulings"). Where this document and v0.17
disagree, this document wins; every such point is marked **[AMENDS v0.17]**. Mechanics that
changed between v0.1 and v0.2 are marked **[v0.2]** where a reader of v0.1 would otherwise
miss the change.

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
  → Pass-1.5 adapter: materialize domain space (T1 excluded) → QueryPayload → graph_search
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
  re-baseline only — the retiring fields, **seven series per §4.6 [v0.2]**, are not in
  `GRAPH_WEIGHTS`, verified `compiler/kpi/score.py:68-73`); `context_failed.search`
  preserved.
- **§11 / F4+c-3:** the full measurement contract (§8 below).
- **D-123-H:** audit delivered on the result (8th field); the adapter owns persistence;
  search does no I/O. **Logging policy:** one-line summary per document, full bytes
  retained only on failure (~80 kB/receipt ⇒ ~125 MB per 1,586-note ingest if kept whole;
  a successful search's evidence is reconstructable from graph + snapshot hash). **[v0.2]**
  §5.1 now conforms to this policy: success persists a compact per-stage projection, the
  full `SearchAuditPayload` only on failure.
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
- **[v0.2] Ratified behavior change (opus R-4):** under a binding `page_cap`, **selector
  rank now decides which T2 pages survive** where PageRank decided before (§4.3). That is
  the intended improvement — stated here as a ruling, not inherited as a clause in a
  parameter list.

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
`envelope_written: bool` · **[v0.2]** `t1_slugs: frozenset[str] | None` (the adapter's
single T1 read, passed through to the context builder — step 2).

Flow (numbered per v0.17 §3.1, with the settled mechanics named):

1. **Gate:** `frontmatter is None` ⇒ return `Pass15Outcome(search_ran=False, …)` —
   pre-Pass-1 sources do not search (R-P3a-3: T2 stays empty; T1/T3 proceed).
2. **Materialize the space** (the adapter is *the* graph→search-space materializer —
   this discharges **#128**: `page_type` vocabulary validated HERE, at the boundary,
   exactly as `projection.py:125-128` assigns). **[v0.2]** The space excludes T1
   **before the selector runs**, matching today's semantics (`context_loader.py:202`
   passes `candidate_slugs=pool − t1_slugs`):
   `space = queries.domain_entity_slugs(conn, domain) ∩ queries.active_entities(conn)
   − queries.source_supported_slugs(conn, source_id)`.
   The T1 read is **shared with the context builder** — a single read, passed through
   on `Pass15Outcome.t1_slugs`, not duplicated. Drop non-vocabulary `page_type`
   (counted, watched), sort slug-ascending (the dataclass does not sort — ordering is
   the materializer's obligation). Build `GraphSnapshotRef{schema_version,
   active_entity_count, space_fingerprint, source_kind: "domain_subtree",
   source_detail: domain}` — `space_fingerprint` = sha256 over canonical JSON of the
   ordered manifest (spec §5.1 convention). **Consequence:** hits on already-supported
   entities cannot occur, so the retired #122 vocabulary needs no `already_t1`
   successor — `matched | unresolved` stays sufficient and no `hit_already_t1` watched
   class is introduced; `eligible_space_size` keeps today's post-T1-exclusion meaning.
3. **Empty/missing domain** ⇒ call `graph_search` with the empty reason-stamped space
   (`domain: None` ⇒ `domain_missing` watched class); core builds the abstention, `call`
   never invoked, zero spend. **[v0.2]** `abstain_empty_space` is a real outcome
   producing a record: the V2 search section is **populated, not null** — the adapter
   searched the empty space and the core abstained, and the record shows the abstention
   (`matched | unresolved` vocabulary, no `max_hops`).
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
6. **[v0.2] Search summary first:** the V2 `SearchSummary` is built **immediately after
   `graph_search` returns**, from the in-memory `GraphSearchResult`/audit, before any
   failure-sensitive post-processing — so `context_failed.search` always carries the
   completed search summary when a search ran.
7. **Envelope sink:** wrap the per-search persistence product (§5.1) in
   `SearchRunEnvelope{…, run_id, source_id, intra_run_order, artifact_path}` (shape
   already declared, `kdb_search/artifact.py:368-379`, unused today) →
   `state/runs/<run_id>/search/<safe_source_id>.json`, atomic write, **warn-only** —
   `artifact_path` null on failure, the source outcome never affected. **[v0.2]** A
   write failure is a **warning, counted** (`searches_attempted − searches_written`,
   §4.7) — not an exception; the source continues compiling.
8. **Provenance read:** one batched `queries.entity_first_run_ids(conn, hit_slugs)`
   (NEW — §4.2) over the validated hits (≤ `max_results`); per-hit
   `{slug, first_run_id, match_recency}` where `match_recency` = `cohort` if
   `first_run_id == run_id`, `pre_run` if a different known id, `age_unknown` if None.
   No alias/exact resolver participates (codex c-2). **[v0.2]** A provenance-read
   failure (`entity_first_run_ids` raises) is **warn-and-continue**: warning logged,
   `provenance=None`, the hits land in the existing `age_unknown` recency bucket, and
   the source continues compiling.
9. **Return** ordered validated hits + the V2 search summary.

**[v0.2] Failure channels:** typed outcomes (`abstain_empty_space`, `budget_exceeded`,
`selector_failure` with class) are `result.status` values — the adapter converts them to
an **honest empty T2 and compile continues** (unchanged). Post-search adapter steps
(envelope write, provenance read) are **warn-and-continue** per steps 7–8 — no typed
exception carrier. **Only pre-search validation errors** (`InvalidGraphSearchRequest`,
`SearchConfigError`) **propagate** — inside `compile_source`'s step-1 try they land in
the existing `context_failed` channel (`compiler.py:706-728`), with
`context_failed.search` non-null when the search completed before the raise (B8; the
summary exists by step 6 whenever a search ran).

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
  intersected with the active same-domain pool minus T1, **order preserved** — the
  minus-T1 is a no-op safeguard under §4.1's pre-selector T1 exclusion **[v0.2]**.
- **NEW** `t1_slugs: frozenset[str] | None = None` **[v0.2]** — the adapter's single
  T1 read (`source_supported_slugs`), passed through so the exclusion is computed once;
  `None` (replay/tooling path) ⇒ the builder reads it itself, as today.
- **[v0.2] T2 ordering rule, explicit:** the within-tier sort key is
  `(-tier, rank_index, -pagerank, slug)`, where `rank_index` is the hit's **fat-stage
  rank position** for T2 members (`Hit` order is fat's ranked order; thin is
  membership-only) and a constant for T1/T3 members. SD-2's strict tier ordering stands;
  the **page cap applies after the sort, unchanged**. Behavior change ratified in §3.2:
  under a binding cap, selector rank — not PageRank — decides which T2 pages survive.
- **NEW** `search_summary: SearchSummary | None = None` — adapter's V2 summary for the
  telemetry product; never serialized into the prompt.
- **[AMENDS v0.17] DELETED at the same time** (was P3b): `mode` / `resolver` /
  **`source_text` [v0.2]** params, `T2Mode`, `_build_t2` / `_t2_structured` /
  `_t2_layered` / `_t2_legacy` / `_t2_from_search_keys`, `_t2_slug_in_text`,
  `_t2_title_in_text`, `_title_eligible`, `_whole_word_alternation`, the resolver
  wrappers (`_resolve_to_canonical_slugs*` — four thin wrappers), `_MIN_SEED_THRESHOLD`
  and the 2-hop widening (`max_hops` is always 1). **`source_text` joins the deletion
  list [v0.2]:** after the regex family is deleted it is consumed by nothing
  (`context_loader.py:318,345,468,495,522,545` are exactly the deleted family);
  `compile_source` stops passing `source_text=body` (`compiler.py:703`); the `re`
  import goes with it. `active_entities` **stays** — the projection still reads
  `title` / `page_type`. See §7 for the full disposition.
- `ContextTelemetry` (common/types) loses `configured_t2_mode` /
  `effective_t2_strategy`; gains `search: SearchSummary | None`. `EffectiveT2Strategy`
  / `ConfiguredT2Mode` enums deleted. `keys_emitted` now carries the original
  (pre-truncation) expressions from the adapter; `key_outcomes` becomes the
  per-expression matched/unresolved projection (§5.2) — **the #122 dispositions
  (`resolved_t2_seed` / `already_t1` / …) retire with the resolver**: the V2 record's
  outcome vocabulary is `matched | unresolved`, annotation-carried.
- **[v0.2] Empty-graph / empty-space early return under V2:** the search section is
  **populated, not null** — the adapter searched the empty space and the core abstained
  (`abstain_empty_space` is a real outcome producing a record, §4.1 step 3); the record
  shows the abstention, in the `matched | unresolved` vocabulary, with no `max_hops`.
- Unchanged: T1 (`source_supported_slugs`), the same-domain gate (D3), T3 1-hop
  mechanics, PageRank tie-break (within T1/T3), page cap + projection, the two-product
  split (snapshot byte-facing / telemetry persistence-facing). **[v0.2] Absent-domain
  rule, stated rather than hidden:** when a source has no domain, today's behavior is
  the **whole active graph** as the tiering pool (`context_loader.py:193`) — preserved
  as-is (OQ-P3a-3 resolution, §12).

### 4.4 `compiler/compiler.py` + `orchestrator/kdb_orchestrate.py` plumbing

- `compile_source` gains `selector: ModelSpec | None = None` and
  `intra_run_order: int = 0`; **loses** `mode` / `resolver`. Step 1 becomes: adapter
  (when `context_snapshot is None` — the replay/tooling path never searches, writes no
  record, unchanged) → builder with `t2_selection` / `t1_slugs` / `search_summary`.
- **[v0.2] Run boundary:** the run gains an explicit **run-level selector `ModelSpec`
  parameter**, resolved once from `common/models.json` (`resolve_models_json`,
  ctx_window asserted — B10) by the run's model id (R-P3a-5: selector seat = run model)
  and **threaded to every source** — not re-resolved per source from the raw SDK model
  name (unstable identity, conflicts with the ad-hoc provider escape hatch). The
  orchestrator **fails before entering the source loop** when no valid selector seat
  exists. The per-source loop index is threaded as `intra_run_order`: v0.17's "check
  whether the ordering is recoverable from the manifest" is settled — **the loop index
  is authoritative** (the manifest records set membership, not compile order; recovering
  order post-hoc would derive the fact from a non-authoritative source). One param,
  persisted once in the envelope.
- **[v0.2] Run-start output-cap validation:** lowering `common/models.json`
  `max_output_tokens` does not itself constrain Pass-2, which uses `--max-tokens`
  directly — so the run validates **`--max-tokens ≤ selector.max_output_tokens`**
  (65,536 after the R-P3a-6 edit) before entering the source loop. Pass-1 is fixed at
  4,096; selector calls are internally bounded below 65,536.
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
  information; OQ-P3a-1 resolution, §12).
- **`keys_emitted`** = the original pre-truncation expressions (opus5 M4; rendered
  forms live in the envelope; truncation-flagged indices noted in the search section).
  **[v0.2] Fallback:** on the adapter-error path (`InvalidGraphSearchRequest` /
  `SearchConfigError` propagate before adapter output exists), `keys_emitted` falls
  back to `frontmatter.entity_search_keys` — the same guarantee V1 made
  (`compiler.py:717-719`).
- **`key_outcomes`** (1:1 with `keys_emitted`): `{expression, status:
  matched|unresolved, annotation, matched_first_run_id, match_recency}` — the
  provenance pair is a deterministic projection of the hit-level facts: the
  highest-ranked validated hit attributed to that expression. **[v0.2] Expression
  accounting authority:** `GraphSearchResult.unresolved_expressions` (`result.py:136`)
  is **the authority for the unresolved set**; `Hit.matched_expressions`
  (`types.py:133`) is **the attribution source**. Unresolved is never derived a second
  time from absence of hits — an expression appearing in neither would be silently
  lost. P3a.1 tests assert the invariant: `unresolved_expressions ∪ (union of
  hit.matched_expressions)` partitions `query.expressions`.
- **`search` section** (`null` only when no search ran): `status`, failure class,
  `execution`, `evidence_status`, `body_coverage`, `query_kind`, the §2.3/flow counts
  (eligible space size — SD-5's tracked trend series, no threshold — stage1_retained,
  stage2_pool_size, returned_entries, valid_entry_yield, unattributed_hit_count,
  retry_attempts), watched classes, concordance, selector `{provider, model, route}`,
  `latency_ms`, `cost_usd`, budget records, **`stage2_budget_bound` [v0.2]** (the 0/N
  evidence required to ever delete the fail-safe on evidence rather than argument),
  per-stage `{thin, fat}` token/cost/`provider_input_tokens` splits, `artifact_path`,
  `search_snapshot_hash`, and the **per-hit provenance list** `{slug, first_run_id,
  match_recency}`. **[v0.2]** The rest of the telemetry sweep
  (`all_entries_dropped_occurrences`, `query_truncated_occurrences`,
  `attempted_violations`, `stage2_hydrated` / `stage2_title_only`) stays in the
  envelope only — deliberate disposition **"retained, not aggregated"**
  (`body_coverage` partly covers the last two). **No new KPI series.**
- **`context_failed` V2:** same null-observable invariants as V1, plus
  `context_failed.search` non-null when the search completed before the builder raised —
  **[v0.2]** guaranteed structurally: the summary is built immediately after
  `graph_search` returns, before failure-sensitive post-processing (§4.1 step 6).

**Dispatching loader:** `parse_context_record(raw)` pre-reads `schema_version` and
routes to the V1 or V2 strict parser (today a V2 file degrades to a `malformed`
integrity issue — `parse_context_record_v1` hard-rejects `!= 1`). `ContextLoadResult.
records` widens to `list[ContextRecordV1 | ContextRecordV2]`; emit_kpis integrity
counting and reconciliation are unchanged; V1/V2/mixed histories all load.
**[v0.2]** `common.types.KeyOutcome` is deleted per plan, so the V1 parser gets a
**persistence-local `KeyOutcomeV1` inside `compiler/context_record.py`** for V1
parsing/factory-retirement purposes; the V2 outcome type is distinct, so historical
and current vocabularies cannot mix.

### 4.6 KPI readers V1+V2 (`compiler/kpi/graph.py`)

- V1 path unchanged (historical records stay readable; the V1-only aggregates gate on
  V1 fields as today).
- V2 path: `context_build_success_rate` and `context_t{1,2,3}_{candidates,delivered}_mean`
  read from the same fields; **`context_explicit_empty_count` is re-sourced [v0.2]:**
  V1 derives it from `effective_t2_strategy == "explicit_empty"`
  (`compiler/kpi/graph.py:181-183`), a field V2 drops — the V2 count is records whose
  search section has `query_kind == "state_c"`, **over records where a search ran**
  (search section non-null). Population change, stated: on V1 every complete record
  could answer; on V2 a pre-Pass-1 source cannot.
- New watched series: `search_status_counts`, `search_expression_
  {matched,unresolved}_rate`, `search_hit_recency_{pre_run,cohort,age_unknown}_rate`,
  `search_space_entity_count_mean` (SD-5 trend), `search_cost_usd_total`,
  `search_latency_ms_mean`, and the **bytes-per-token series:
  `search_bytes_per_token{stage: thin|fat, model}` — aggregated per stage × per model,
  never blended** (R: handoff §2(b)). Thin sends slug-heavy identity lines, fat sends
  whole prose bodies; one figure hides the spread the series exists to show.
- **[v0.2] Removed — the full retiring family is SEVEN series** (all at
  `compiler/kpi/graph.py:171-178`), not two:
  `search_key_resolved_at_load_rate`, `search_key_late_resolution_rate`,
  `search_key_never_resolved_rate`, `search_key_resolved_pre_run_rate`,
  `search_key_resolved_cohort_rate`, `search_key_resolved_age_unknown_rate`,
  `search_key_t2_seed_rate`. Dispositions:
  - `search_key_resolved_at_load_rate` → **renamed** to the new
    `search_expression_matched_rate` (same population).
  - The three recency series (`pre_run` / `cohort` / `age_unknown`) are **per-KEY**;
    the new `search_hit_recency_*` series are **per-HIT** — an explicit **re-baseline
    (denominator change), not a rename**, so the series is not read as continuous
    across P3a.
  - `search_key_late_resolution_rate`, `search_key_never_resolved_rate`,
    `search_key_t2_seed_rate` → **clean cut, no successor** (the KPI-time resolver
    recomputation dies with them).
  Verified: **none of the seven is in `GRAPH_WEIGHTS`** (`compiler/kpi/score.py:68-73`)
  — watched-series re-baseline, board unchanged. **No resolver call in the KPI path** —
  pinned by test (§9). The re-baseline is recorded in `docs/TASKS.md` and here —
  **clean cut, no payload tombstones** (OQ-P3a-4 resolution, §12).
- `emit_kpis.py:296`'s `copytree(run_dir, …/run_state)` auto-packages the new
  `search/` envelope dir into benchmark run dirs with zero changes.

### 4.7 Measurement contract (v0.17 §11, carried; mechanics named)

- **pass-1.5 stays OUT of the scored union** — scored axes unchanged in population; a
  test asserts adding a pass-1.5 record does not move them (G1).
- **[v0.2] New `SearchPassMeasurement`** (frozen dataclass, `common/measurement.py`) —
  one measurement **per search**, not per stage (avoids the pass-1
  `duplicate_source_id` completeness collision): `run_id`, `source_id`,
  `pass_="pass1_5"`, `provider`/`model`, `prompt_versions: {thin, fat}` (G1.3 —
  `PassCallMeasurement`'s single `prompt_version` doesn't fit two prompts; widening the
  shared type would endanger every existing measurement — OQ-P3a-2 resolution, §12),
  `status`, `execution`, `calls`, `attempts`, `total_input_tokens` (summed over the
  audit's StageRecords), per-stage `{thin, fat}` token/cost splits, `total_latency_ms`,
  `cost_usd`, `search_snapshot_hash`. **The measurement is computed by the adapter
  from the in-memory `GraphSearchResult`/audit at run time — it never re-parses
  envelope bytes**, so nothing measurement needs is lost by the compact success form
  (§5.1). The run-time-computed measurement is what gets persisted per search — the
  compact receipt carries exactly the fields it needs. (codex 1's ask for output-side
  token retention is rejected — §11/A21.)
- **[v0.2] Separate loader channel:** the measurement loader bundle
  (`common/measurement.py`, `RunMeasurements` with pass1/pass2 lists at `:315`/`:353`,
  loaders at `:380`/`:394`) gains a **separate `search: list[SearchPassMeasurement]`**
  list, fed by a third glob block `<run_dir>/search/*.json` over the persisted
  run-time-computed records; stats keys
  `pass1_5_dir_exists`, `pass1_5_identified`, `pass1_5_malformed`. `compute_processing`
  continues to receive **only pass1/pass2** — Pass-1.5 stays out of the scored union
  and the D-117-5 completeness contract keeps its meaning on the existing columns.
  Search measurements feed their dedicated diagnostic aggregation only. Existing
  diagnostic series (`retry_load`, `token_overrun_rate`, `repair_rung_rate`) keep their
  pass1+pass2 population (H4).
- **[v0.2] Header:** `RunMeasurementHeader` gains **both `searches_attempted` and
  `searches_written`** (G1.2) — the D-117-5 completeness contract marks the pass-1.5
  column complete. Envelope write failures = `searches_attempted − searches_written`
  (a null `artifact_path` cannot be counted at read time — a failed write leaves no
  envelope). The V2 summary may still carry `artifact_path: null` for source-level
  evidence.
- **[v0.2] Reconciliation invariant (H5):** total run cost/calls == pass1 + pass1_5 +
  pass2; the independent side is the envelopes on disk: `len(glob("search/*.json")) ==
  searches_written` — a successful-write completeness condition; envelope write
  failure (warn-only) surfaces as `searches_attempted − searches_written > 0`, an
  incomplete measurement state, never a silent violation. (Note: the
  `search_artifact_write_failures` *core constant* stayed deleted per D-123-H; the
  count is derived from the two header counters.)
- **Boards:** diagnostic `cost_usd_pass1_5`, `cost_unknown_calls_pass1_5`, call/retry
  counts, tokens, latency columns; `effective_top_weights` gains an explicit
  `pass1_5` case — no accidental fall-through (G1.4). No third ranked board.
- **[v0.2] Pre-run cost projection (P3a.0, opus R-11):** REPLACE puts two additional
  LLM calls on every source, and R-P3a-5 leaves the seat open between two candidates
  ~4× apart on price — so the seat choice is preceded by a measured projection,
  produced in P3a.0 **before** the seat is chosen (§8). No paid calls required; the
  numbers come from the corpus.

### 4.8 Registry edit (P3a.0, R-P3a-6)

`common/models.json`: `deepseek-v4-flash.max_output_tokens` 384,000 → **65,536**;
`qwen3.7-flash.max_output_tokens` 128,000 → **65,536**. Registry test asserts the cap;
both entries keep `ctx_window: 1,000,000` and `tokens_lte_bytes: true` (selector route
preconditions, `budget.resolve_selector_route`). The edit is capability metadata only —
the behavioral run cap is enforced by the `--max-tokens ≤ selector.max_output_tokens`
run-start validation (§4.4) **[v0.2]**.

## 5. Data schemas

### 5.1 Envelope on disk — `state/runs/<run_id>/search/<safe_source_id>.json`

**[v0.2] Success vs. failure, per the ratified logging policy** (v0.17 §3.1: full bytes
retained only on failure):

- **SUCCESS:** the envelope persists a **compact per-stage projection** — per stage:
  stage/attempt, prompt ref, model stamp, token usage, cost, stop reason, validation
  counts, `retained_identities`. **No** `rendered_messages`, `raw_response_text`,
  `parsed_output`, or evidence bodies.
- **FAILURE:** the full `SearchAuditPayload` is persisted, as today.

`SearchRunEnvelope` (`kdb_search/artifact.py:368-379`, shape already declared, unused
today) **stays as the wrapper**; the compact projection is a **small new receipt type
alongside it**, not a modification of `StageRecord`. `SearchPassMeasurement` is
computed by the adapter from the in-memory result/audit at run time (§4.7), so the
compact success form loses nothing measurement needs. **Rejected alternative:** amending
the logging policy to retain full bytes on success (~80 KB/source ⇒ ~127 MB/run at
1,586 sources) was rejected on storage cost.

### 5.2 `SearchSummary` (adapter → context_loader → V2 record)

Frozen dataclass in `common/types.py` (persistence-facing; never prompt-serialized):
`search_ran`, `query_kind`, `status`, `failure_class`, `execution`, `evidence_status`,
`body_coverage`, `query_truncated_indices: tuple[int, ...]`, counts (§4.5 list),
`watched`, `concordance`, `selector: {provider, model, route}`, `latency_ms`,
`cost_usd`, `budget_records`, **`stage2_budget_bound` [v0.2]**, `stage_splits:
{thin, fat}`, `artifact_path`, `search_snapshot_hash`, `space_entity_count`, `hits:
tuple[{slug, first_run_id, match_recency, matched_expressions}, ...]`.

## 6. Integration boundaries

| Producer → Consumer | Contract |
|---|---|
| adapter → `kdb_search` | `GraphSearchRequest` / `GraphSearchResult`; core stays I/O-free, consumer-neutral, `{common}`-only imports |
| adapter → `kdb_graph` | `domain_entity_slugs`, `active_entities`, `source_supported_slugs` (shared T1 read) **[v0.2]**, **new** `entity_first_run_ids`; adapter imports `kdb_graph`, core never does (B1) |
| adapter → `common/wiki_io` | `get_body(slug, page_type, root=vault_root)` — the two-vault-roots evidence binding test pins the bound root |
| adapter → disk | envelope: compact success projection / full audit on failure **[v0.2]**; warn-only, atomic write, counted (`searches_written`) |
| adapter → measurement | `SearchPassMeasurement` computed at run time from the in-memory result/audit; never re-parsed from envelope bytes **[v0.2]** |
| `compile_source` → `context_loader` | `t2_selection` / `t1_slugs` **[v0.2]** / `search_summary`; telemetry never enters the prompt |
| `compile_source` → disk | one ContextRecord (V2) per source per run, both builder outcomes |
| `emit_kpis` / KPI | dispatching loader V1/V2/mixed; no resolver in the KPI path |
| measurement / boards | `search/*.json` glob into a **separate search channel** **[v0.2]**; scored union untouched; reconciliation vs. header `searches_written` **[v0.2]** |

## 7. Deletion plan (former P3b — folded in per R-P3a-2)

| Delete | Where |
|---|---|
| `T2Mode`, `_build_t2`, `_t2_structured`, `_t2_layered`, `_t2_legacy`, `_t2_from_search_keys`, `_t2_slug_in_text`, `_t2_title_in_text`, `_title_eligible`, `_whole_word_alternation`, `_MIN_SEED_THRESHOLD`, 2-hop widening, the `re` import **[v0.2]** | `compiler/context_loader.py` |
| `_resolve_to_canonical_slugs{,_batch,_with_provenance,_with_provenance_batch}` wrappers | `compiler/context_loader.py` (the `kdb_graph.queries` originals stay — identity boundary, §4.2) |
| `mode` / `resolver` / **`source_text` [v0.2]** params | `build_context_snapshot`, `compile_source` (stops passing `source_text=body`, `compiler.py:703`), orchestrator call site |
| `ConfiguredT2Mode`, `EffectiveT2Strategy`, `KeyOutcome` (V1 vocabulary), #122 disposition enum | `common/types.py` — the V1 parser gets a **persistence-local `KeyOutcomeV1`** in `compiler/context_record.py` **[v0.2]**; the V2 outcome type is distinct so historical and current vocabularies cannot mix |
| **`build_context_record_v1` (the V1 factory) [v0.2]** — V1 goes READ-ONLY | `compiler/context_record.py:160` (it reads the retiring `telemetry.max_hops`); its only non-test callers (`compiler.py:709,732`) switch to V2; the **V1 parser is retained** for historical reads |
| KPI-time resolver read + **all seven `search_key_*` series** (`resolved_at_load`, `late_resolution`, `never_resolved`, `resolved_pre_run`, `resolved_cohort`, `resolved_age_unknown`, `t2_seed`) **[v0.2]** | `compiler/kpi/graph.py:171-178` — dispositions in §4.6 (one rename, one re-baselined family, three clean cuts) |
| Tests: T2-mode dispatch, resolver parity, legacy/layered suites | `compiler/tests/` — disposition per file: delete mode-specific cases; port tier/cap/ordering cases to the `t2_selection` contract |
| Doc sweep | `CODEBASE_OVERVIEW.md` (T2Mode/STRUCTURED references), `AGENTS.md` architecture paragraph, #122 eval-doc re-baseline note (watched-series only; re-baseline recorded in `docs/TASKS.md` **[v0.2]**) |

Sunset gates that no longer apply: D-90-12's three-part AND-gate and the NW-9
preconditions are superseded by R-P3a-2 (recorded, not silently dropped).

## 8. Phased implementation plan

**[v0.2] Phase order amended (codex 2):** the V2 record types + factory + parser +
writer land **before or within** the wiring phase, so no gate exists where the rewired
builder lacks a valid serialization path; the following phase narrows to dispatching
loaders + KPI consumers. **No temporary V1 compatibility shim.**

| Phase | Content | Gate |
|---|---|---|
| **P3a.0 — foundations** | §4.8 registry edit (+test); `kdb_graph.queries.entity_first_run_ids` (+tests); stale `search.py` docstring fix; **[v0.2] pre-run cost projection** (opus R-11): one table — thin input bytes (bounded by M × `MAX_SLUG_LEN`), fat input bytes (stage-2 pool × mean body size, measured over the vault's active entities via `common/wiki_io.get_body` — the same read `body_reader` will do), output allowance, × per-M pricing from `common/models.json` for **both** seat candidates (deepseek-v4-flash, qwen3.7-flash), × 1,586 sources; bytes→tokens via D5's measured families. No paid calls; numbers from the corpus. Produced **before the selector seat is chosen** (R-P3a-5) | targeted + full suite green; projection table delivered |
| **P3a.1 — adapter** | `compiler/search_adapter.py` + `SearchSummary`; space materialization incl. **#128 vocabulary check** and **pre-selector T1 exclusion [v0.2]**; envelope sink (compact success / full failure); provenance read. Unwired | `test_search_adapter.py` green + full suite |
| **P3a.2 — V2 records + wiring + deletions [v0.2]** | **ContextRecordV2 types + factory + parser + writer land FIRST** (before or within the wiring); `KeyOutcomeV1` persistence-local type; compile_source/orchestrator plumbing (`selector`, `intra_run_order`, run-level selector seat + `--max-tokens` validation); context_loader rewiring; §7 deletions + test disposition + enum cleanup. **No V1 compatibility shim** | V2 factory/parser/writer tests green before the wiring lands; `test_context_loader.py` / `test_compile_source.py` rewritten green; suite green; grep proves no `T2Mode`/`_t2_` references outside history |
| **P3a.3 — loaders + KPI consumers [v0.2]** | dispatching loader; emit_kpis V1/V2/mixed; KPI readers V1+V2 + bytes-per-token series; KPI resolver-read removal (seven series) | `orchestrator/tests/test_context_records.py`, `test_kpi_graph.py` green; suite green |
| **P3a.4 — measurement** | `SearchPassMeasurement` + separate loader channel + stats; header `searches_attempted` + `searches_written`; reconciliation invariant; board diagnostic columns | measurement tests (§9) green; suite green |
| **P3a.5 — docs + close** | North Star milestone changelog; AGENTS.md sweep; TASKS.md #123 row (+ the search_key_* re-baseline note); session handoff | owner review |
| **Sandbox gate (Joseph fires)** | full-chain `scripts/sandbox-run.sh` — doubles as prompt-1.3.0 first fire + pre-vault smoke (R-P3a-4). **[v0.2] Sequential sub-checkpoints (opus R-12):** **(A)** Pass-1 under prompt 1.3.0 — first live fire — output inspected and accepted (`entity_search_keys` sane) **before (B)** Pass-1.5 results are read. If 1.3.0's keys are wrong, downstream selector judgments are read through a broken query | (A) accepted → (B) read; run completes; KPI/board/envelope inspection; THEN vault ingestion becomes schedulable |

## 9. Test plan (TDD-first; v0.17 §12 P3a list carried + amendments)

**P3a.1 (`compiler/tests/test_search_adapter.py`):** SD-1 payload incl. `author`;
materialization (slug-ascending; **non-vocabulary `page_type` dropped + counted —
#128**; fingerprint deterministic); **[v0.2] T1 excluded from the space before the
selector runs** (`source_supported_slugs` subtraction; single T1 read shared with the
builder); missing domain ⇒ core abstention, zero calls, **search section populated**
(abstain_empty_space is a record, not a null) **[v0.2]**; State C ⇒ search runs,
`query_kind: state_c`; pre-Pass-1 ⇒ no search; warn-only envelope, `artifact_path`
null on failure **and the write failure counted** (`searches_attempted −
searches_written`) **[v0.2]**; **[v0.2] warn-and-continue:** provenance-read failure ⇒
warning + `provenance=None` ⇒ hits in `age_unknown`, compile continues;
`intra_run_order` threaded; two-vault-roots evidence binding; hit-level
`first_run_id`/`match_recency` via the batched read — **resolver never invoked**;
`InvalidGraphSearchRequest` propagates with zero calls, zero StageRecords;
**[v0.2] expression-accounting partition invariant:**
`unresolved_expressions ∪ (union of hit.matched_expressions)` partitions
`query.expressions`.

**P3a.2 (`compiler/tests/test_context_loader.py`, `test_compile_source.py`,
`compiler/tests/test_context_record_v2.py` [v0.2]):** selector order into EXISTING
CONTEXT within tier — **explicit sort key `(-tier, rank_index, -pagerank, slug)`,
`rank_index` = fat-stage rank for T2, constant for T1/T3 [v0.2]**; cap interaction
(selector rank decides which T2 pages survive a binding cap); T3 expands from T1∪T2
seeds only, always 1-hop; empty T1/T2/T3 ⇒ valid cold snapshot; one search per source;
**branch-specific call assertions** (typed status ⇒ zero or thin-only calls per the §8
table); `selector_failure` ⇒ honest empty T2 + compile continues; adapter defect ⇒
`context_failed`; **`keys_emitted` falls back to `frontmatter.entity_search_keys` on
the adapter-error path [v0.2]**; replay path (`context_snapshot=`) never searches,
writes no record; deletion grep-guards (no `T2Mode`, no `_t2_` symbols, no
mode/resolver/`source_text` params **[v0.2]**); **V2 record factory invariants; strict
parser (both directions of the status invariant); V2 writer round-trip; `KeyOutcomeV1`
parses historical records and cannot mix with the V2 vocabulary [v0.2]**;
**run-boundary tests [v0.2]:** selector `ModelSpec` resolved once and threaded; run
fails before the source loop with no valid selector seat; `--max-tokens >
selector.max_output_tokens` rejected at run start.

**P3a.3 (`test_kpi_graph.py`, `orchestrator/tests/test_context_records.py`):** version
dispatch; V1/V2/mixed histories; `context_failed.search` preserved (incl. the
summary-built-before-post-processing guarantee **[v0.2]**); hit-level +
representative-projection shapes; V1+V2 KPI reads; **`context_explicit_empty_count`
re-sourced to `query_kind == "state_c"` over records where a search ran [v0.2]**;
**all seven `search_key_*` series gone; recency re-baseline (per-key → per-hit)
asserted as a denominator change [v0.2]**; **no resolver call in the KPI path**;
expression-accounting series; bytes-per-token aggregation asserted **per stage × per
model** (a blended figure is a test failure).

**P3a.4 (measurement):** a pass-1.5 record **does NOT move scored axes**;
`compute_processing` receives only pass1/pass2 **[v0.2]**; diagnostic columns present;
`searches_attempted` **and `searches_written`** completeness **[v0.2]**; cost/call
reconciliation invariant; envelope-write-failure ⇒ `attempted − written > 0`,
incomplete measurement state, never silent; **measurement computed from the adapter's
run-time product, never re-parsed from envelope bytes [v0.2]**.

## 10. Watch-fors for the first full-chain run (carried from the handoff, updated)

- **Prompt 1.3.0 has never fired live** (#126 re-specified `entity_search_keys` as
  query terms). **[v0.2]** This is now a **gate sub-checkpoint**, not a watch-for: §8's
  sandbox gate (A) requires the Pass-1 output inspected and accepted
  (`entity_search_keys` sane) **before** (B) Pass-1.5 results are read — if 1.3.0's
  keys are wrong, every downstream selector judgment is read through a broken query.
- **`thin fails ⇒ no fat` (D-123-G) is now visible** — no F1 masking; at sandbox scale
  every space is small, so thin failures surface directly.
- **Zero-key sources make §8.3 metric 6 degenerate** (unresolved-expressions metric
  reads empty); the V2 `query_kind` field exists precisely so this is readable.
- **DashScope content-filter false positives** (`data_inspection_failed`) — the
  durable provider-level risk; flagged twice on the Li Lu lecture.
- **Drive sync paused** during the run (sandbox script prompts; Kuzu corruption risk).

## 11. v0.2 amendment changelog

Every panel finding and its decided disposition, folded into the sections named. v0.1
content not contradicted by an amendment is preserved verbatim or near-verbatim.

| Amend | Finding | Disposition | Sections changed |
|---|---|---|---|
| A1 | opus R-1 | Accepted — space excludes T1 **before** the selector (`− source_supported_slugs`); T1 read shared with the builder, single read; no `hit_already_t1` class; `eligible_space_size` keeps post-exclusion meaning | §1 pipeline diagram, §4.1 (Pass15Outcome, step 2), §4.3 (T2 def, new `t1_slugs` param), §6, §9 P3a.1 |
| A2 | opus R-2 | Accepted — retiring family is **seven** series; `resolved_at_load` renamed to `search_expression_matched_rate`; recency family re-baselined per-key → per-hit (explicit denominator change); `late_resolution` / `never_resolved` / `t2_seed` clean cut; all seven verified outside `GRAPH_WEIGHTS` | §3.1 B8 bullet, §4.6, §7 row 6, §9 P3a.3 |
| A3 | opus R-3 | Accepted — `context_explicit_empty_count` re-sourced to `query_kind == "state_c"` over records where a search ran; population change stated | §4.6, §9 P3a.3 |
| A4 | opus R-4 | Accepted — explicit sort key `(-tier, rank_index, -pagerank, slug)`, `rank_index` = fat-stage rank for T2, constant for T1/T3; cap after sort; behavior change ratified in §3.2 | §3.2, §4.3, §9 P3a.2 |
| A5 | opus R-5 | Accepted — `source_text` param deleted with the regex family (consumed by nothing after); `compile_source` stops passing it; `re` import goes; `active_entities` stays | §4.3, §7 row 1 + row 3, §9 P3a.2 |
| A6 | opus R-6 | Accepted — `unresolved_expressions` is the unresolved-set authority, `Hit.matched_expressions` the attribution source; no second derivation; partition invariant asserted in P3a.1 tests | §4.5, §9 P3a.1 |
| A7 | opus R-7 (partial) | Partially accepted — `stage2_budget_bound` persisted in the V2 search section (the 0/N fail-safe evidence); remainder of the sweep retained-not-aggregated, no new KPI series | §4.5, §4.6 (via "no new series"), §5.2 |
| A8 | opus R-8 | Accepted — V1 context record goes **read-only**: `build_context_record_v1` retired (reads `telemetry.max_hops`), callers switch to V2, V1 parser retained | §7 new row 5 |
| A9 | opus R-9 | Accepted — `keys_emitted` falls back to `frontmatter.entity_search_keys` on the adapter-error path | §4.5, §9 P3a.2 |
| A10 | opus R-10 | Accepted — empty-graph/empty-space early return under V2: search section **populated** (abstain_empty_space is a record), `matched\|unresolved` vocabulary, no `max_hops` | §4.1 step 3, §4.3, §9 P3a.1 |
| A11 | opus R-11 | Accepted — pre-run cost projection becomes explicit P3a.0 work, before the seat is chosen; corpus-measured, no paid calls | §4.7, §8 P3a.0 row |
| A12 | opus R-12 | Accepted — sandbox gate split into sequential sub-checkpoints: (A) prompt-1.3.0 Pass-1 output accepted before (B) Pass-1.5 results read; the §10 watch-for becomes the gate sub-checkpoint | §8 sandbox gate row, §10 |
| A13 | codex 2 | Accepted — V2 record types + factory + parser + writer land before/within the wiring phase; next phase narrows to loaders + KPI consumers; no V1 compatibility shim; phases, gates, and test-plan references renumbered | §8 (whole table), §9 (P3a.2/P3a.3 split) |
| A14 | codex 3 | Accepted — success persists a compact per-stage projection (no rendered messages / raw responses / parsed output / evidence bodies); failure keeps the full `SearchAuditPayload`; `SearchRunEnvelope` stays the wrapper, compact projection is a new receipt type; measurement computed by the adapter at run time, never re-parsed from envelope bytes; full-bytes-on-success alternative rejected on storage cost | §3.1 D-123-H bullet, §4.7, §5.1, §6, §9 P3a.4 |
| A15 | codex 4 | Accepted — `RunMeasurements` gains a separate `search: list[SearchPassMeasurement]`; `compute_processing` receives only pass1/pass2; D-117-5 keeps its meaning on existing columns | §4.7, §6, §9 P3a.4 |
| A16 | codex 5 | Accepted — post-search adapter steps are warn-and-continue (no typed exception carrier); envelope-write failure counted; provenance failure ⇒ `age_unknown`, compile continues; only pre-search validation errors propagate; summary built immediately after `graph_search` returns | §4.1 steps 6–8 + failure channels, §4.5 context_failed bullet, §9 P3a.1/P3a.3 |
| A17 | codex 6 | Accepted — header gains **both** `searches_attempted` and `searches_written`; write failures = attempted − written; envelope glob reconciled against `searches_written`; `artifact_path: null` remains source-level evidence | §4.1 step 7, §4.7 header + reconciliation, §6, §9 P3a.1/P3a.4 |
| A18 | codex 7 | Accepted — explicit run-level selector `ModelSpec`, resolved once, threaded to every source; fail before the source loop with no valid seat; run-start validation `--max-tokens ≤ selector.max_output_tokens` | §4.4, §4.8, §8 P3a.2, §9 P3a.2 |
| A19 | codex 8 | Accepted — persistence-local `KeyOutcomeV1` in `compiler/context_record.py`; V2 outcome type distinct | §4.5 loader paragraph, §7 row 4, §8 P3a.2, §9 P3a.2 |
| A20 | OQ-P3a-1..4 | Resolved — see §12: drop `max_hops`; new `SearchPassMeasurement` with separate channel; keep T3 same-domain gate + state the absent-domain whole-graph rule; clean cut + documented re-baseline | §4.3 absent-domain rule, §4.5, §4.6, §4.7, §7, §12 |
| A21 | rejections | **codex 1** (retain `provider_output_tokens` + schema bump): **rejected** for P3a scope — its only consumer was v0.1's `total_output_tokens` field, which is **dropped from `SearchPassMeasurement`** instead; `cost_usd` is already computed and retained per call; the bytes-per-token series is input-side; deferred until an output-side KPI is actually proposed (YAGNI). **opus R-7 full sweep:** partially accepted (A7); remainder retained-not-aggregated by deliberate disposition. **opus OQ-4 tombstones:** superseded by clean cut (A20) | §4.7 (field list), this table |

## 12. Open questions — resolved (2026-08-03)

All four v0.1 open questions are settled by the panel + owner (A20); recorded here as
resolutions, no longer open.

1. **OQ-P3a-1 → DROP `max_hops`** (2/2 panel convergence). No consumer missed — full
   grep: the context-tiering `max_hops` is read by the V1 schema/factory/parser and
   `context_loader` only; **no KPI series reads it**. V1 goes read-only per A8, so the
   field survives in historical records through the retained V1 parser.
2. **OQ-P3a-2 → NEW `SearchPassMeasurement` dataclass, separate loader channel**
   (2/2). `prompt_versions: {thin, fat}` doesn't fit `PassCallMeasurement`'s single
   `prompt_version`, one-measurement-per-search is the right grain, and widening the
   shared type would endanger every existing measurement. `compute_processing` keeps
   receiving only pass1/pass2 (A15).
3. **OQ-P3a-3 → KEEP the T3 same-domain gate** (2/2) — already true today:
   `_t3_neighbors` receives `pool − seeds` where `pool` is the domain pool
   (`context_loader.py:193,214`). **Plus the explicit absent-domain rule:** when a
   source has no domain, today's behavior is the **whole active graph**
   (`context_loader.py:193`) — preserved, now stated rather than hidden (§4.3).
4. **OQ-P3a-4 → CLEAN CUT + documented re-baseline** (codex over opus's tombstone
   lean; owner decision on simplicity grounds). The denominator change (A2) is recorded
   in `docs/TASKS.md` and this blueprint — **not** in payload tombstone fields, which
   have no runtime consumer and become schema debris.

## 13. Changelog

- **v0.1 (2026-08-03)** — initial draft. Extends v0.17 §3/§11/§12 with settled
  mechanics (model seat, intra_run_order authority, envelope path, V2 field list,
  deletion disposition); folds former P3b into P3a per R-P3a-2; closes #128 by
  assigning vocabulary validation to the adapter-materializer.
- **v0.2 (2026-08-03)** — post-review amendment fold. Applies the Opus 5 (R-1..R-12)
  and Codex round-1 (1–8) findings per the owner/lead-engineer dispositions (§11):
  pre-selector T1 exclusion; seven-series KPI retirement with rename / re-baseline /
  clean-cut dispositions; `context_explicit_empty_count` re-source; explicit T2 sort
  key; `source_text` deletion; expression-accounting authority + partition invariant;
  `stage2_budget_bound` persisted; V1 record read-only; `keys_emitted` fallback;
  populated abstention records; P3a.0 cost projection; split sandbox gate; phase
  reorder (V2 serialization before/within wiring); compact success envelope per the
  logging policy; separate measurement channel; warn-and-continue post-search failure
  model; `searches_written` header counter; run-level selector seat + `--max-tokens`
  validation; `KeyOutcomeV1`; all four OQs resolved. codex 1 rejected (§11/A21).
