# #123 — Semantic Graph Search: Blueprint v0.1 (for panel review)

Date: 2026-07-26 · Task: **#123 Semantic graph search** · Status: **v0.1 — for Joseph + panel (codex, opus5) review**
Basis: **spec v0.4 RATIFIED** (`2026-07-25-task123-semantic-graph-search-spec.md` — R1 per-entry salvage / R2 uniform budget / R3 narrower gate / R4 always-two-stage; SD-1..SD-6) · vision v1.5 · fixture v1 committed (`3d271e2`, `benchmark/truth/task123_search_snapshot_v1/`, 163 identities, suite 1963 green).

Scope: every open item the spec routed forward (§10): package boundary (P9), selector model route, the R2 pre-flight estimator, artifact-sink separability, excerpt serialization/escaping, T2Mode retirement mechanics, context-record schema evolution, exact serialized token counts (§7.1 blueprint duty), plus the integration shape, module design, phased implementation plan, and the TDD test plan. Fixture layout is **done** (R3 work item 1). Truth-set probe draft is a **separate artifact** (R3 step 2), tracked in its own document.

Decision points are **B1–B14**, each with a recommendation. Nothing here is ratified until Joseph rules after panel review.

---

## 1. Package boundary (P9) — B1

**The JOURNEY §6 lens (read before writing this section):** the GraphDB is a durable asset; the compiler is one producer; search consumers (pass-1.5, human CLI, MCP) are owned by none of them. "The second concrete consumer is the natural extract-the-shared-core trigger — catch it proactively." The anchored premise to interrogate: *"search belongs near the graph access code"* (same shape as the MCP-server mistake).

**Key structural fact from spec §1.1/§1.2:** `graph_search` never queries Kuzu. The **caller materializes the space** (identities only: slug/title/page_type/scope/graph_ref); the function owns text projection (reads wiki `.md` bodies via `common/wiki_io.get_body`), the selector calls (via `common/call_model`), and the artifact construction. Its entire import surface is therefore `common`.

**Options:**

| | Option A: new sibling `kdb_search/` | Option B: `kdb_graph/search.py` + injected selector | Option C: inside `compiler/` |
|---|---|---|---|
| Imports | `{common}` only | would need `common` (wiki_io, call_model) — **violates the AST-guarded invariant** `kdb_graph: ∅` | `{common, kdb_graph}` (allowed today) |
| Consumer-neutrality (vision P8) | yes — same shape as `kdb_mcp` (a sibling consumer of the durable asset) | yes, but only by injecting selector **and** body-reader, hollowing the module | no — human CLI/MCP would import the producer's internals |
| JOURNEY §6 lesson | extract the shared core at the second consumer, proactively | repeats the "sit with queries.py" anchoring | repeats the "keep it in the compiler repo" anchoring |
| Boundary-test change | add one row: `"kdb_search": {"common"}`; consumers add `kdb_search` to their allowed sets | none (but breaks the stricter `kdb_graph: ∅` rule — the doc contract would need loosening) | none |

**Recommendation (B1): Option A — `kdb_search/`, imports `{common}` only.** Callers (compiler adapter now; CLI/MCP later) materialize spaces via `kdb_graph` and pass them in. `kdb_search` never imports `kdb_graph` — the same decoupling that lets the truth-set harness run it against the frozen fixture with zero graph. Boundary test gains: `"kdb_search": {"common"}`, `"compiler": {"common", "kdb_graph", "kdb_search"}`.

## 2. Module design

```
kdb_search/
  __init__.py            # public surface: graph_search, request/result/payload types
  types.py               # GraphSearchRequest, QueryPayload, SearchSpaceRef, SpaceEntity, Hit,
                         # GraphSearchResult, GraphSnapshotRef, SearchTelemetry,
                         # SearchAuditPayload, SearchRunEnvelope, StageRecord, enums
  projection.py          # excerpt policy v1 projector + thin/fat evidence-block rendering (§2.1 layout)
  budget.py              # R2 pre-flight estimator (B3)
  prompts.py             # template load + SELECTOR_THIN_PROMPT_VERSION / SELECTOR_PROMPT_VERSION + sha256 (#115 pattern)
  prompts/selector_thin_v1.txt
  prompts/selector_fat_v1.txt
  response.py            # §2.3 four-way response classification + per-entry validation/salvage
                         # + controller-computed expression accounting
  search.py              # graph_search() — orchestration: budget → thin → retain-all → fat → result
  artifact.py            # payload/envelope construction, search_snapshot_hash, artifact_integrity_hash
  replay.py              # §5.2 record replay + historical selector re-call (opt-in)
  tests/                 # §7 test plan
```

### 2.1 Core signature

```python
def graph_search(
    request: GraphSearchRequest,          # query, search_space (caller-materialized), max_results, opts
    *,
    selector: SelectorRoute,              # resolved from models.json (B10): id, provider, model,
                                          # ctx_window, price_in/out, api_call_type, ...
    call: Callable[..., ModelResponse] = call_model_with_retry,   # injectable (tests, replay)
    body_reader: Callable[[str, PageType], str] = wiki_io.get_body,  # injectable (fixture/harness)
) -> GraphSearchResult:                    # .hits, .unresolved_expressions, .status, .execution,
                                           # .evidence_status, .body_coverage, .telemetry,
                                           # .audit (SearchAuditPayload — always constructed)
```

- **Consumer-neutral core:** no `run_id`/`source_id`/paths anywhere in `kdb_search`. The pass-1.5 adapter (§3) wraps `result.audit` in a `SearchRunEnvelope` and persists it (B6).
- **`SelectorRoute`** is the models.json entry resolved by `common/model_pool.resolve_models_json` — the #121 config-driven wiring; missing/invalid config fails hard at resolution, before any search work.
- **Fail-hard, no catch-all (Joseph, #121 posture):** typed, deliberate outcomes (`budget_exceeded`, `selector_failure` with class, `abstain_empty_space`) are values in `result.status`. An *unexpected* exception inside `graph_search` is a defect and **propagates** — for pass-1.5 it lands in the existing `context_failed` channel (§3.2), never silently converted into an empty result.

### 2.2 Two-stage orchestration (R4, codex #3 retain-all)

```text
graph_search(request):
    space = request.search_space                      # ordered, slug-ascending (§1.2)
    if space empty / domain missing:
        → status=abstain_empty_space, execution=not_executed   (zero spend, typed reason)
    estimate = budget.estimate_thin_tokens(request)   # B3
    if estimate > floor(selector.ctx_window × 0.8):
        → status=budget_exceeded, execution=not_executed       (zero spend, NEVER retried, R2)

    # stage 1 — thin, recall-oriented, ALWAYS runs (R4)
    thin = call_stage("thin", render thin over ALL eligible identities)   # ≤2 attempts (B11)
    if thin failed after retry budget:
        → status=selector_failure, execution=thin_attempted, failure_class recorded

    # stage-2 input (codex #3): N ≤ M=150 ⇒ EVERY eligible identity, regardless of thin's list;
    #                           N > M   ⇒ thin's validated retained list (dedup, foreign-dropped, ≤M)
    stage2_slugs = all_eligible if N ≤ M else thin.retained_validated
    presented in MANIFEST order (slug-ascending), never thin's ranked order (fat stays unanchored)
    if N > M and stage2_slugs empty:                  # thin honestly retained nothing (B14)
        → status=completed, hits=[], execution=thin_attempted

    # stage 2 — fat, projection of excerpts INSIDE the function (§4), ≤2 attempts
    fat = call_stage("fat", render fat over stage2_slugs with excerpts)
    if fat failed after retry budget:
        → status=selector_failure, execution=two_stage_attempted, failure_class recorded

    result = response.validate_and_account(fat)       # §2.3 salvage + expression accounting
    telemetry.concordance = |fat.top10 ∩ thin.ranked_top20| / 10    # §8.3 watched series
    audit = artifact.build(...)                       # §5.1 payload, per-attempt stage entries
```

### 2.3 Response handling (R1, §2.3 — restated as mechanics)

`response.py` implements exactly the ratified rules:

- **Four-way classification** of each raw stage response: `unparseable_response` / `structurally_unusable_response` (valid JSON, no `selections` array / no `retained` array for thin) / `all_entries_dropped` / valid (incl. **empty `selections` = honest empty, never a failure**). Classes 1–3 → stage retry (B11); exhausted → `selector_failure` with the class.
- **Per-entry drop+count:** foreign slug (∉ space), malformed entry. **Per-field coerce+count:** unknown `matched_expression` removed (hit may stand unattributed), duplicate slug keep-first, over-cap truncate.
- **Never wholesale-discard a parseable response** (Joseph's 6-of-10 rule).
- **Expression accounting (controller-computed):** every request expression → `matched` / `unresolved`; selector's `unresolved_expressions` advisory only (`selector_accounting_delta` counted); `cap_exhausted_possible` when `len(hits)==max_results`; `unattributed_hit_count` + `unattributed_possible` annotations (excluded from abstention scoring).
- **Escaped foreign-identity rate = 0 by construction** — emitted hits are membership-checked post-validation.
- Thin validation is the **same rule** applied to `retained` (foreign/malformed dropped, duplicates deduped, over-M truncated).

## 3. The pass-1.5 adapter + context-build integration — B7, B8

### 3.1 Where the adapter runs (B7)

Spec §3.2 says "orchestrator loop, per source, after pass-1 enrichment commits and before `compile_source`'s context build." The code reality: the context build happens **inside** `compile_source` step 1 (`compiler/compiler.py:700–735`), which already holds everything the adapter needs (`conn`, `frontmatter`, `state_root`, `ctx.run_id`) and already owns the warn-only audit-write precedent (`_write_context_record`, `compiler.py:640`).

**Recommendation (B7): the adapter is `compiler/search_adapter.py`, invoked inside `compile_source` step 1, immediately before `build_context_snapshot`, inside the same try — so an unexpected adapter/search defect lands in the existing `context_failed` path (typed search failures never raise; they are `result.status` values).**

```text
compile_source step 1 (new flow):
    if context_snapshot is None:                       # production path (not replay/tooling)
        search_outcome = None
        if frontmatter is not None and frontmatter.entity_search_keys:     # State B
            search_outcome = search_adapter.run_pass15(
                conn, frontmatter=frontmatter, selector_route=…,
                state_root=state_root, run_id=ctx.run_id, source_id=source_id)
        # frontmatter None (pre-pass-1) or explicit empty keys (State C) → no selector call,
        # T2 empty — D-90-8's "honor the LLM's no-anchors judgment" preserved (B14)
        build = build_context_snapshot(conn, source_id=…, source_text=body,
                                       frontmatter=frontmatter,
                                       t2_selection=search_outcome.hit_slugs if search_outcome else None,
                                       search_summary=search_outcome.summary if search_outcome else None)
        persist ContextRecordV2 (complete)             # §3.3
```

`search_adapter.run_pass15` (compiler-side, imports `{common, kdb_graph, kdb_search}`):

1. **Materialize the space** (§1.2): `queries.domain_entity_slugs(conn, domain)` ∩ `queries.active_entities(conn)` → `SpaceEntity` list, slug-ascending; missing domain → `None` space → adapter short-circuits to `abstain_empty_space`/`domain_missing` **without calling graph_search** (spec §3.3 — zero spend), T2 empty, T3 cold-start widening unchanged.
2. **Assemble QueryPayload** (SD-1): `expressions = entity_search_keys`; `text` = fixed template rendering `domain`, `summary`, `key_themes`, `entity_search_keys`, `author` from pass-1 frontmatter.
3. **Compute `GraphSnapshotRef`** (B13) adapter-side.
4. Call `kdb_search.graph_search(request, selector=route)` — **once per source** (two selector calls per executed search, R4).
5. Wrap `result.audit` in `SearchRunEnvelope` (run_id, source_id, created_at, intra_run_order) and write `state/runs/<run_id>/search/<safe_source_id>.json` via `common.atomic_io.atomic_write_json` — **warn-only**, mirroring `_write_context_record` (audit evidence must never affect the source outcome).
6. Return `(ordered validated hit slugs, search summary)` to the caller.

### 3.2 `build_context_snapshot` changes

- New params: `t2_selection: list[str] | None` (ordered selector hits; `None` = no search ran → T2 empty) and `search_summary` (the V2 record's search section; `None` on the caller-supplied-snapshot path).
- T2 tier = `t2_selection` **in selector order** (P2 — tier ranking inside T2 is the selector's, not PageRank); T1/T3 unchanged (T3 expands from T1∪T2 seeds, cold-start 2-hop widening stays); merged `page_cap=50` applies as today; EXISTING CONTEXT reflects T2 in selector order (D2).
- **Removed params:** `mode`, `resolver` (B9).
- Telemetry: `ContextTelemetry` gains the search-summary object; `t2` TierRecord = selector hits pre/post merged cap (SD-2 preserved — candidates/delivered meanings unchanged); the stage-1 pool is recorded **separately**, never overloaded into T2 candidates (codex's SD-2 condition).

### 3.3 Context-record schema evolution (B8)

Spec §5.1: "the #122 context record gains a search section — blueprint decides v2 field vs sibling record."

**Recommendation (B8): BOTH, layered — the byte-fidelity artifact is the sibling envelope (§3.1 step 5, spec §5.1 verbatim); the per-source context record bumps to `ContextRecordV2` carrying a search *summary* + artifact reference.** Rationale: `compiler/kpi/graph.py` already reads context records as the per-source audit unit (coverage + #122 decomposition); splitting the summary away from the record would force every KPI reader to join two trees. The envelope remains the only byte-exact artifact.

`ContextRecordV2` (strict factory/parser mirroring V1's reject-never-coerce posture; `schema_version: 2`; reader dispatches on version so V1 history stays readable):

- **Kept unchanged:** `run_id`, `source_id`, `status` (`complete`/`context_failed`), `t1/t2/t3` TierRecords, `candidate_universe_size`, `domain_scope`, `cold_start`, `max_hops`, `page_cap`, `keys_emitted` (= the selector's `expressions`).
- **Re-shaped:** `key_outcomes` → per-expression accounting — `{expression, status: matched|unresolved, annotation: none|cap_exhausted_possible|unattributed_possible}`, 1:1 positional alignment with `keys_emitted` preserved (V2 parser invariant, same as V1). The five resolution-era dispositions and `target_first_run_id` provenance die with the resolver (B9).
- **Retired fields:** `configured_t2_mode`, `effective_t2_strategy` (T2Mode gone).
- **New `search` section (nullable — null on `context_failed` and on pre-pass-1/State-C no-search paths):** `status` (completed|abstain_empty_space|budget_exceeded|selector_failure), `abstain_reason` (domain_empty|domain_missing|null), `failure_class` (transport|timeout|unparseable_response|structurally_unusable_response|all_entries_dropped|null), `execution`, `evidence_status`, `body_coverage`, counts (`eligible_space_size`, `stage1_retained`, `stage2_hydrated`, `stage2_title_only`, `returned_entries`, `valid_entries`, `valid_entry_yield` (null on zero-returned), per-class `attempted_violations`, `all_entries_dropped`, `unattributed_hit_count`, `retry_attempts`), `concordance` (null when thin produced no ranking), `model` (id/provider/model), `latency_ms`, `cost`, `budget` (`estimate_tokens`, `selector_window`, `headroom_factor`, `outcome`), `artifact_path`, `search_snapshot_hash`.
- **KPI continuity:** `compiler/kpi/graph.py` reads V1+V2 (coverage counts both); the #122 decomposition's T2-source changes from resolver outcomes to expression accounting — the `warren-buffett never_resolved` series' successor is V2's per-expression `matched|unresolved`. The #122 eval doc is amended at implementation time to declare the series re-baseline (flagged as a P3 work item, not silent).

## 4. T2Mode retirement mechanics — B9

All three modes retire with #123's ship (spec §3.4 — the selector is the only production T2 path; the deterministic resolver has **no role anywhere in the search path**).

**Removed (compiler):** from `context_loader.py` — `T2Mode`, `_effective_strategy`, `_build_t2`, `_t2_structured`, `_t2_layered`, `_t2_legacy`, `_t2_from_search_keys`, `_t2_slug_in_text`, `_t2_title_in_text`, `_title_eligible`, `_whole_word_alternation`, and the four resolver wrappers (`_resolve_to_canonical_slugs{,_batch,_with_provenance,_with_provenance_batch}`); from `compiler.py` — `mode`/`resolver` params and their threading; from `common/types.py` — `ConfiguredT2Mode`, `EffectiveT2Strategy` (V2 record drops them); from `context_record.py` — the V1-only enums move into the V1 parser (kept for history).

**Explicitly retained (boundary Joseph flagged "not a valid *search* method" — these are not search):** `kdb_graph.queries.resolve_to_canonical_slugs*` stay — `kdb_mcp/adapters.py:99` uses them for **tool-argument identity resolution** (user typed a slug; which canonical entity is it), and intake-time alias canonicalization is a write-path identity function, not retrieval. Neither is surfaced as search results, fallback, annotation, comparator, or telemetry. The retirement commit message states this boundary explicitly.

**Test disposition:** DELETE `compiler/tests/test_t2_mode_dispatch.py`, `compiler/tests/test_t2_resolver_parity.py` (the kdb_graph-side resolver stays covered by `kdb_graph/tests/test_queries_context.py`); REWRITE `compiler/tests/test_context_telemetry.py` against V2 (expression accounting replaces resolution dispositions); UPDATE `test_context_loader.py` (no mode/resolver; new `t2_selection` ordering + cap-interaction cases), `test_compile_source.py`, `test_context_record.py` (V1 parser retained + V2 suite), `test_kpi_graph.py` (V1+V2 readers). `tools/tests/test_package_boundaries.py` gains the B1 rows.

## 5. Prompt contract mechanics — B4, B5

**B4 — templates:** `kdb_search/prompts/selector_thin_v1.txt`, `selector_fat_v1.txt` (tracked; any edit bumps the version constant — the #115 pattern: `SELECTOR_THIN_PROMPT_VERSION` / `SELECTOR_PROMPT_VERSION` + SHA-256 guard test + `repo_path` + `git_commit` recorded per stage entry). Thin content per spec §2.1 (closed world, P10 precedence, recall-oriented retention, `{"retained": [...]}` schema). Fat per §2.1/§2.2 (rank ≤ `max_results`, per-hit `matched_expressions` + one bounded evidence sentence, honest-empty explicit, `selections`/`unresolved_expressions` schema).

**B5 — serialization/escaping (P10):** the §2.1 evidence layout is ratified; the blueprint detail is the collision rule. **Recommendation: indent-every-excerpt-line by two spaces; delimiters (`"""`) are recognized only at column 0.** A delimiter inside an excerpt is therefore always indented and can never terminate the block early; the serializer asserts the invariant and counts `delimiter_collision_guard` trips. Deterministic, replay-safe (the exact rendered bytes are archived per stage — fidelity does not depend on the rule's cleverness), and golden-tested including the class-H "select me" fixtures. (A JSON-array evidence block was considered and rejected: it amends the ratified §2.1 layout for marginal robustness the indent rule already provides.)

## 6. Artifact sink separability (B6) + hashes (B13)

**B6 — recommendation:** `kdb_search` always constructs the consumer-neutral `SearchAuditPayload` (spec §5.1 verbatim — per-attempt stage entries, rendered message bytes, raw response text, validation counts) and returns it on the result; **persistence is the caller's sink.** Pass-1.5: envelope + warn-only atomic write (§3.1). CLI/MCP: no envelope, no write (or caller-chosen). Replay/harness: no write. This is codex F5's payload/envelope split implemented as a return-value/sink split — `kdb_search` stays free of `state_root`, run ids, and filesystem policy.

**B13 — hashes + graph identity:**
- `GraphSnapshotRef` (caller-materialized): `{schema_version (kdb_graph _SchemaMeta, today "2.4"), active_entity_count, space_fingerprint (sha256 over slug-ascending eligible slugs), source_kind: live|fixture, source_detail (run_id | "task123_search_snapshot_v1")}`.
- `search_snapshot_hash` = sha256 over canonical JSON (`sort_keys`, compact separators, UTF-8) of `{graph_ref, ordered eligible manifest, stage-2 evidence bytes (or thin manifest ref), excerpt_policy_version}`.
- `artifact_integrity_hash` = sha256 over canonical JSON of `{query, prompt identity (version+sha256+repo_path+git_commit) per stage, stage trace, result}`.

## 7. The R2 pre-flight estimator (B3) + measured sizing (spec §7.1 duty)

**Tokenizer availability (verified this session):** `.venv` has **no local tokenizer** (no tiktoken/sentencepiece/tokenizers; `google-genai` and `anthropic` offer only network `count_tokens` — a spend, wrong for a zero-spend guardrail). Spec §7.2's ratified rule: exact per-model tokenizer **where available**, otherwise UTF-8 bytes ÷ 4 (conservative; `words × 1.3` underestimates slug-heavy text ~1.7×).

**Recommendation (B3): ship `ceil(utf8_bytes / 4)` as the v1 estimator — dependency-free, model-agnostic, never underestimates on the measured corpus (below). No new dependency.** (tiktoken would cover only gpt among the candidates; gemini has no local tokenizer at all. Revisit only if a future selector's window is small enough that estimator slack routes real traffic to `budget_exceeded`.)

```text
estimate_thin_tokens = ceil(bytes(rendered_thin_block + system_template + user_wrapper + query_block) / 4)
                     + OUTPUT_ALLOWANCE_THIN (constant 2,000 — thin output ≤ 150 slugs ≈ 1.5k tokens)
budget             = floor(selector.ctx_window × 0.8)         # Joseph's headroom factor (R2)
estimate > budget  ⇒ budget_exceeded, zero spend, typed telemetry, never retried
```

**Measured sizing (spec §7.1's required recompute — executed against fixture v1 this session; bytes authoritative, tokens = bytes÷4 conservative / words×1.3 optimistic):**

| evidence block (spec §2.1 rendering) | entities | bytes | bytes÷4 | words×1.3 | per-entity |
|---|---|---|---|---|---|
| thin, whole graph | 163 | 14,343 | ~3.6k | ~2.2k | 87 B |
| thin, value-investing (largest domain) | 51 | 4,404 | ~1.1k | ~0.7k | 86 B |
| fat, whole graph | 163 | 110,121 | ~27.5k | ~18.3k | 675 B |
| fat, value-investing | 51 | 37,664 | ~9.4k | ~6.4k | 738 B |
| fat, M=150 cap (production worst case) | 150 | 101,102 | ~25.3k | ~16.8k | 674 B |

- Matches spec §7.1's ranges (thin ~13–23 tok/entity; fat ~97 tok/entity expected-case words-based ≈ 169 conservative).
- **Stage-2 fit premise (opus5 §2.6a), restated with the conservative estimator:** 150 × ~1,820 B (250w cap +10% extension + field overhead) ≈ 68k tokens < 80% of a 128k window — both candidates (gpt-5.4-mini 400k, gemini-3.6-flash 1M) pass with wide margin; §9's bound test asserts this formula.
- **Vault-scale projection (measured per-entity bytes):** thin whole-graph ~9,600 entities ≈ 835k B ≈ **~209k tokens**; thin largest-domain ~3,000 ≈ 261k B ≈ **~65k**; fat ≤ 150 ≈ **≤25k expected / ~68k safety-bound**. Against 80% budgets: gpt-5.4-mini (320k) admits everything except nothing here; gemini (800k) admits all. The guardrail stays non-binding for the configured pool — it exists for smaller-window future models (R2's point).
- **Cost (upper bound, pass-1.5 per source in the largest domain):** thin ~1.1k + fat ~9.4k conservative ≈ 10.5k input tokens (~7k realistic) → today ~$0.01–0.02/source at flash pricing; a full 1,706-source re-ingest upper bound ≈ **$25 (deepseek-v4-flash) / $115 (gpt-5.4-mini) / $230 (gemini-3.6-flash)** — most domains are far smaller; the number is the worst-domain × all-sources bound.
- **SD-5's survivor:** space entity count per search is recorded in telemetry as the tracked trend series (spec §7.2); no threshold is tuned.

## 8. Selector model route (B10) + retry composition (B11)

**B10 — recommendation:** the selector route is a models.json id resolved via `common/model_pool.resolve_models_json` (fail-hard #121 semantics), pinned by a module constant `DEFAULT_SELECTOR_MODEL_ID` in `kdb_search`, overridable per-call (the truth-set harness and experiments pass it explicitly). **Default decided by the truth-set A/B (D7) between the two in-pool candidates: `gemini-3.6-flash` (1M window) and `gpt-5.4-mini` (400k window).** Interim default for implementation: `gemini-3.6-flash` (ran the fixture cohort; larger budget headroom). Deepseek is not a v1 candidate (its pass-2 link-emission collapse is the #120 investigation).

**B11 — retry composition:** transport/timeout classes reuse `common/call_model_retry.call_model_with_retry` (SDK retryable errors, exponential backoff — the D-119 machinery) **inside** one stage attempt; the §2.3 response-level classes (`unparseable`, `structurally_unusable`, `all_entries_dropped`) retry at the **stage** level — **2 attempts total per stage** (the #104/#106 precedent), each attempt archived as its own stage entry (opus5 §2.6b). `budget_exceeded` is never retried (deterministic). Retry counters live in telemetry (`retry_attempts`, per-stage `attempt: 1..2`).

## 9. Replay modes (spec §5.2 — mechanics)

- **Record replay** (default replay path): `replay.py` loads a persisted envelope and returns the historical `GraphSearchResult` — no LLM call, no body reads; validates `artifact_integrity_hash` on load. The #119 byte-pinning pattern survives: replayed compiles use caller-supplied `context_snapshot=` (which writes no record — existing behavior, unchanged).
- **Historical selector re-call** (opt-in, selector-version A/B): re-runs the selector against the **archived** stage-2 evidence bytes + archived rendered messages; validates hits against the archived manifest; result is stamped `historical_recall` and never presented as current search; never reads live wiki.

## 10. Truth-set harness shape (P4 preview — full design after Joseph's labels)

`tools/benchmark/` gains a harness that loads fixture v1 (checksums verified by the committed smoke test), builds `SearchSpaceRef` from `identities.json` (body_reader serves frozen excerpt bytes — never the live vault), runs the probe artifact (R3 step 2, separate document), and emits §8.3 metrics 1–7 + selector-failure/retry rates + concordance + cost. The reduced-M protocol (metric 2) is implemented by parameterizing M per run (M=10/20 over value-investing's 51; M=20/40 over the 163). **No live selector run crosses the D7 gate until Joseph ratifies labels + gates (B14).**

## 11. Phased implementation plan

| Phase | Content | Verification gate |
|---|---|---|
| **P1 — core, no LLM** | `kdb_search` types, projection (policy v1 + parity unit tests on synthetic bodies vs the fixture's pinned caps), budget estimator, response classification/salvage/accounting, artifact builder + hashes, boundary-test rows | targeted tests + full suite green |
| **P2 — selector orchestration** | prompt templates + version/SHA guards, two-stage `graph_search` with injectable `call` (canned responses), retain-all enforcement, concordance, stage retry, replay modes, P10 adversarial fixtures, golden rendered-bytes tests, stage-2 fit-bound assertion | targeted tests + full suite green |
| **P3 — pass-1.5 integration** | `compiler/search_adapter.py`, `build_context_snapshot` `t2_selection`/`search_summary`, ContextRecordV2 (+V1 reader retained), envelope sink, KPI readers V1+V2, **T2Mode retirement + test disposition (B9)**, #122 eval-doc series re-baseline note | targeted + integration tests (orchestrator loop, one search per source, two calls per executed search; missing-domain; State A/C; cap interaction; context_failed on defect) + full suite |
| **P4 — truth-set harness** | §10 harness + reduced-M protocol; probe artifact finalized (R3 step 2) → **D7 gate: Joseph's labels + numerical gates** | harness self-tests against canned selector outputs |
| **P5 — experiments + second consumer** (post-D7 only) | selector A/B (B10 default), §8.5 cross-domain A/B, live cohort re-run (Joseph-gated, Drive paused); CLI/MCP whole-graph surface; **FTS infra track (B12)** | Joseph-gated per experiment |

**Sequencing constraint (B14):** codex's adopted closing line reads "no implementation, selector tuning, or vault ingestion crosses the D7 gate until steps 1–3 are complete." **Recommended reading:** P1–P3 build machinery testable entirely with canned/mocked selector outputs — no live selector spend, no tuning, no ingestion — and may proceed once this blueprint is ratified; P4's harness is likewise self-testable. Everything involving a **live selector call** (truth-set experiments, cohort re-runs, vault ingestion) waits for Joseph's labels + gates. The probe-artifact draft (R3 step 2) proceeds in parallel with P1–P3 so labeling is never the bottleneck. Panel/Joseph to confirm or tighten this reading.

## 12. Test plan (TDD-first; spec §9 expanded)

Tests are written **before** the implementation in each phase, with these pass criteria:

**P1 (`kdb_search/tests/`):**
- `test_contract.py` — request/result shapes; `status` × `execution` × `evidence_status` matrix (incl. `abstain_empty_space`/`not_executed`/`not_applicable`/`None`; `budget_exceeded`; `thin_attempted`/`two_stage_attempted` failure paths); empty-`selections` = honest empty; `valid_entry_yield = None` on zero-returned.
- `test_response.py` — §2.3 four-way classification; Joseph's 6-of-10 (1 duplicate + 3 malformed/foreign ⇒ 6 survive in order, per-class counts); unknown-expression coercion (unattributed hit stands); over-cap truncation; never wholesale-discard; thin-list validation = same rule; expression accounting (`matched`/`unresolved`, `selector_accounting_delta`, `cap_exhausted_possible`, `unattributed_possible`).
- `test_zero_escape.py` — arbitrary hostile raw output ⇒ emitted hits ⊆ space, always.
- `test_budget.py` — estimate over/under 80% of a fake window ⇒ `budget_exceeded` with **zero invocations** (mock asserts never called) / proceeds; never retried; identical routing for every caller shape; no small-space skip; **estimator conservatism: bytes÷4 estimate ≥ measured fixture thin block's words×1.3 figure** (the codex #2 anti-underestimate assertion, pinned to fixture v1 numbers); stage-2 payload bound formula asserted (§7).
- `test_projection.py` — policy v1 on synthetic bodies: ≤250w verbatim; cap at 250 + sentence extension ≤ +10%; hard cut; determinism; missing body ⇒ title-only + `body_coverage`; delimiter-guard counting (B5).
- `test_artifact.py` — payload/envelope shapes; per-attempt stage entries; `graph_ref`; both hashes well-formed + stable under canonical serialization.

**P2 (`kdb_search/tests/`):**
- `test_prompts_golden.py` — fixed space + query ⇒ pinned rendered bytes per stage; version/SHA/repo_path/git_commit guard (#115 pattern).
- `test_two_stage.py` — thin→fat call order; N≤M retain-all (thin returns 0/3/M ⇒ stage-2 input = all eligible, manifest order); N>M honored-retention; thin-empty with N>M ⇒ honest empty at `thin_attempted`; concordance computation; retry classes ⇒ attempt 2 recorded; exhausted ⇒ `selector_failure` + typed class; **no deterministic substitution anywhere** (resolver never imported — asserted by the boundary test, not a mock).
- `test_adversarial.py` — class-H "select me" evidence fixtures: not selected unless relevant, zero foreign slugs out.
- `test_replay.py` — persist → mutate a candidate body → record-replay reproduces with no call; re-call replays archived bytes, validates against archived manifest, stamped, never live.

**P3 (`compiler/tests/`, `tools/tests/`):**
- `test_search_adapter.py` — QueryPayload assembly (SD-1 fields incl. `author`); domain materialization (slug-ascending, active-only); missing domain ⇒ abstain, zero calls, typed reason; envelope write warn-only (write failure doesn't fail the source); `intra_run_order`.
- `test_context_loader.py` (updated) — `t2_selection` order preserved into EXISTING CONTEXT; cap interaction with T1/T3 (SD-2 candidates/delivered); T3 cold-start widening with selector-empty T2; `t2_selection=None` ⇒ empty T2.
- `test_context_record_v2.py` — factory invariants (search section required on complete-with-search, null on the no-search paths), strict parser (rejects V1 enums in V2, null rules), V1 reader retained, version dispatch.
- `test_compile_source.py` (updated) — one search per source, two calls per executed search; selector_failure ⇒ honest empty T2 + compile continues; adapter defect ⇒ `context_failed`; State A/C ⇒ no selector call.
- `test_kpi_graph.py` (updated) — V1+V2 coverage; expression-accounting series.
- Retirement sweep: `test_t2_mode_dispatch.py` / `test_t2_resolver_parity.py` deleted; grep-guard that `T2Mode`/`_t2_legacy` symbols are gone (covered by import failures + boundary test).
- `tools/tests/test_package_boundaries.py` — B1 rows.

**P4:** harness self-tests with canned selector outputs (probe loading, metric computation incl. reduced-M, gate evaluation against predeclared thresholds).

**Live cohort (post-P4, Joseph-gated, Drive paused):** the §9 live read — 3-model baseline re-run with the #122 decomposition re-baselined on V2 expression accounting.

## 13. Decision points (for Joseph, after panel review)

| # | Question | Recommendation |
|---|---|---|
| **B1** | Package boundary | New sibling `kdb_search/`, imports `{common}` (§1) |
| **B3** | Pre-flight estimator | `ceil(utf8_bytes/4)` + 2k output allowance vs 80% window; no tokenizer dependency (§7) |
| **B4** | Prompt storage | `kdb_search/prompts/*.txt`, version constants + SHA guard (#115 pattern) (§5) |
| **B5** | Excerpt escaping | 2-space indent rule, column-0 delimiters, guard counter (§5) |
| **B6** | Artifact sink | Core returns payload; caller owns persistence (pass-1.5: envelope, warn-only) (§6) |
| **B7** | Adapter placement | `compiler/search_adapter.py` inside `compile_source` step 1, same try as the context build (§3.1) |
| **B8** | Record evolution | `ContextRecordV2` search summary + sibling byte-fidelity envelope; V1 reader retained; KPI reads both (§3.3) |
| **B9** | T2Mode retirement | Remove compiler-side machinery + tests as listed; kdb_graph resolvers retained (identity, not search) (§4) |
| **B10** | Selector route | models.json id via `resolve_models_json`; interim default `gemini-3.6-flash`; truth-set A/B decides vs `gpt-5.4-mini` (§8) |
| **B11** | Retry composition | transport retry inside an attempt (call_model_retry); stage-level 2 attempts total; budget never retried (§8) |
| **B12** | FTS infra track | Defer to P5 as an independent CLI/MCP-surface track (Kuzu FTS over slug/title); never wired into pass-1.5 (§11) |
| **B13** | GraphSnapshotRef + hashes | Caller-computed ref (schema_version + count + space fingerprint + source kind/detail); canonical-JSON sha256s (§6) |
| **B14** | D7-gate reading + edge cases | P1–P4-self-test proceed pre-labels (no live selector spend); live calls post-gate only. Edge rulings: empty `expressions` (State C) ⇒ no selector call, empty T2; thin-empty with N>M ⇒ honest empty at `thin_attempted` (§2.2, §3.1, §11) |

## Changelog

- **v0.1 (2026-07-26)** — initial blueprint for panel review: B1–B14 decisions + recommendations; module design; adapter/context-build integration; T2Mode retirement mechanics; ContextRecordV2; estimator + fixture-measured sizing (spec §7.1 duty discharged: thin 87 B/entity, fat 675–738 B/entity, M=150 fat 101k B ≈ 25.3k conservative tokens; vault-scale thin whole-graph ~209k); phased plan P1–P5; TDD test plan.
