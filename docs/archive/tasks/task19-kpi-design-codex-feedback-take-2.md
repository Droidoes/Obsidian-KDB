# Task #19 KPI Design — Codex Hostile Review Take 2

**Date:** 2026-05-06  
**Target:** [`task19-kpi-design.md`](task19-kpi-design.md) — Phase 3 Detailed Spec  
**Review posture:** hostile follow-up review of the code-ready scorer contract after Round 3 corrections.

## Must-Fix

### 1. Parse-failed records are contradicted for M6/M7

**Angles:** [B], [C]

Spec text:

> `docs/task19-kpi-design.md:492` — Source with `parse_ok=False` ... "Excluded from M6/M7 entirely" ... "M6/M7 still bill the cost / latency of failed calls naturally."

The table contradicts itself, and §6 contradicts the table by including every record where `source_words > 0`:

> `docs/task19-kpi-design.md:650` — `For each r ∈ R where r.source_words > 0:`
>  
> `docs/task19-kpi-design.md:666` — `For each r ∈ R where r.source_words > 0:`

Actual code writes tokens/latency/source_words for truncation, extract failure, parse failure, schema failure, and semantic failure after the model call (`kdb_compiler/compiler.py:203-231`, `kdb_compiler/compiler.py:306-322`). Those failed calls are economically real.

**Smallest fix:** state that M6/M7 include every matching record with `source_words > 0`, regardless of `parse_ok`; only true pre-call/source-read zero-word records are skipped.

### 2. Model-call failures can disappear from the requested model's denominator

**Angles:** [C], [G]

Spec text:

> `docs/task19-kpi-design.md:547` — `R` = list of all `RespStatsRecord` matching `(run_id, provider, model)`.
>  
> `docs/task19-kpi-design.md:788-798` — `score_run(... provider: str, model: str, ...)`

For pre-response failures, `build_resp_stats()` persists `provider=""` and `model=""` when `model_response is None` (`kdb_compiler/resp_stats_writer.py:138-150`). That means model-call failures will not match the scorer's requested `(provider, model)` and can vanish from S0/S1/M4 denominators, violating the "one file per attempted source" input contract (`docs/task19-kpi-design.md:470-476`).

**Smallest fix:** change telemetry so `RespStatsRecord.provider/model` are the requested provider/model even when no `ModelResponse` exists, or add `requested_provider` / `requested_model` fields and have the scorer filter on those.

### 3. Cost persistence claims are false

**Angles:** [B], [H]

Spec text:

> `docs/task19-kpi-design.md:207` — "Cost is computed at run time and persisted as `cost_usd` (no re-derivation)."
>  
> `docs/task19-kpi-design.md:240` — "`cost_usd` is persisted in `RespStatsRecord` (Task #29)."
>  
> `docs/task19-kpi-design.md:435` — "extend `RespStatsRecord` with `cost_usd`, `stop_reason`, `token_overrun`..."

Actual `RespStatsRecord` has no `cost_usd` field (`kdb_compiler/types.py:327-352`). The task ledger explicitly says the opposite:

> `docs/TASKS.md:57` — "`cost_usd` intentionally NOT persisted — scorer derives from `(input_tokens, output_tokens) × registry` at score time..."

**Smallest fix:** delete the persisted/frozen-cost claims and say M6 derives cost at scoring time from token counts plus the selected registry, or actually add `cost_usd`.

### 4. Schema-invalid parseable records can crash M1/M2/M3/S3

**Angles:** [A], [C], [D]

Spec text:

> `docs/task19-kpi-design.md:493` — Source with `parse_ok=True` but `schema_ok=False` is "Included in M1/M2/M3/M5 by raw `parsed_json` reads."
>  
> `docs/task19-kpi-design.md:593-598` — direct `r.parsed_json["pages"]`, `p["slug"]`, `p["outgoing_links"]`.
>  
> `docs/task19-kpi-design.md:611-612` — direct `set(r.parsed_json.get("concept_slugs", []))` and `r.parsed_json["pages"]`.

`parse_ok=True` only means `json.loads()` succeeded. The parsed value can still be an array/scalar, or a dict with wrong-typed fields, before schema validation. `check_compiled_source(parsed_json)` also calls `_check_source(parsed_json, ...)` without a top-level type guard (`kdb_compiler/validate_compile_result.py:280-296`).

**Smallest fix:** define tolerant coercion rules mirroring `build_parsed_summary()` / `body_link_check()`, or restrict M1/M2/M3/S3 to dict-shaped parsed payloads and count non-dicts as failures without crashing.

### 5. Borda tie handling is not the algorithm the spec names

**Angles:** [A], [B], [E]

Spec text:

> `docs/task19-kpi-design.md:725-731` — "DENSE RANKS WITH AVERAGING" and "Best gets 1.0; worst gets 0.0"
>  
> `docs/task19-kpi-design.md:742-745` — tied worst candidates get `0.125`

The worked example uses average ordinal ranks, not dense ranks. Also, tied-worst candidates do not get 0.0, contradicting the prose. All-candidates-tied is undefined for `N > 1`.

**Smallest fix:** rename this to average-rank normalization, remove "worst gets 0.0" for tied-worst cases, and add an all-equal policy.

### 6. Zero-denominator redistribution rewards abstention

**Angles:** [A], [E]

Spec text:

> `docs/task19-kpi-design.md:494` — zero-denominator measure rate is `None`; weight redistributed pro-rata.
>  
> `docs/task19-kpi-design.md:590-600` — M1 denominator is total outgoing links.
>  
> `docs/task19-kpi-design.md:634-640` — M5 denominator is body-link union.

A model that emits no outgoing links can remove M1 and M5 from the final score instead of scoring poorly. This reopens the prior review's link-abstinence issue (`docs/task19-kpi-design-codex-feedback-take-1.md:113-147`).

**Smallest fix:** for scored measures where the model controls the denominator, score denominator-zero as `0.0`, or add an explicit "not applicable because corpus has no opportunity" condition.

### 7. `score_runs()` destroys raw M6/M7 meaning

**Angles:** [A], [B]

Spec text:

> `docs/task19-kpi-design.md:809-817` — returned `RunScore` objects have M6/M7 rates "replaced by normalized [0, 1] values"; raw rates are preserved only on the original objects.

But `MeasureScore` has only one `rate` plus raw numerator/denominator (`docs/task19-kpi-design.md:509-516`). The returned object can therefore contain raw numerator/denominator with a normalized rate, which is an inconsistent shape.

**Smallest fix:** add `raw_rate` plus `score_rate`, or keep raw `MeasureScore` immutable and store Borda values separately in `final_score_components`.

### 8. `retry_load` can exceed 1.0

**Angles:** [A], [D], [E]

Spec text:

> `docs/task19-kpi-design.md:676-680` — `Σ max(0, r.attempts − 1) / (|R| × MAX_RETRIES)`
>  
> `docs/task19-kpi-design.md:683` — "Cap-normalized"

`call_model_with_retry()` defaults to `MAX_RETRIES + 1` attempts (`kdb_compiler/call_model_retry.py:20-25`, `kdb_compiler/call_model_retry.py:57-67`) but allows overrides. A record with `attempts > MAX_RETRIES + 1` makes the diagnostic exceed 1.0.

**Smallest fix:** define scorer behavior: raise on impossible attempts, or clamp per-record contribution to `MAX_RETRIES`.

## Design-Call

### 1. S0 name overclaims end-to-end success

**Angles:** [B], [J]

Spec text:

> `docs/task19-kpi-design.md:553-563` — S0 excludes `semantic_ok` and still uses `end_to_end_success_rate`.

Production success requires semantic pass before a `CompiledSource` is emitted (`kdb_compiler/compiler.py:264-280`). A source can pass S0 while failing production's per-source semantic contract.

**Smallest fix:** include `semantic_ok` in S0, or rename S0 to structural/gate success and stop calling it end-to-end.

### 2. Scoring by `(provider, model)` ignores registry IDs

**Angles:** [A], [C]

Spec text:

> `docs/task19-kpi-design.md:547` — records match `(run_id, provider, model)`.

`ModelEntry` has a stable `id` (`kdb_benchmark/registry.py:18-24`), but `load_registry()` only enforces unique IDs, not unique `(provider, model)` (`kdb_benchmark/registry.py:55-75`). Two registry entries can share provider/model with different future knobs.

**Smallest fix:** score by registry `id`, or require and validate unique `(provider, model)`.

### 3. JSON loader shape is underspecified

**Angles:** [A]

Spec text:

> `docs/task19-kpi-design.md:697-706` — uses `r.parsed_summary.page_count`.

On disk, `parsed_summary` is JSON/dict data emitted by `to_dict()` (`kdb_compiler/types.py:354-357`). The spec never defines whether scorer reconstructs dataclasses or uses dict access.

**Smallest fix:** specify a loader that reconstructs `RespStatsRecord` / `ParsedSummary`, or use dict access in scorer pseudocode.

### 4. Industry-standard comparability gaps are knowingly accepted but should be named in output

**Angles:** [I]

The previous review flagged scorer/corpus/registry versioning and candidate-set identity as standard benchmark hygiene (`docs/task19-kpi-design-codex-feedback-take-1.md:602-644`). The current spec rejects scorecard/pricing versioning as "NOT planned" (`docs/task19-kpi-design.md:853`).

That is defensible only if the scorecards explicitly reject historical comparability. Otherwise the Borda candidate-set dependency will be misread later.

**Smallest fix:** add scorecard text/metadata saying final scores are only comparable within the same emitted candidate set; raw rates remain the cross-run inspection surface.

## Cheap-Win

### 1. Export claims are true, but uncovered

**Angles:** [H]

Verified:

- `MAX_RETRIES = 2` exists (`kdb_compiler/call_model_retry.py:20`).
- `HARD_ZERO_FINDING_TYPES` exists (`kdb_compiler/validate_compile_result.py:104-110`).
- `check_compiled_source()` exists (`kdb_compiler/validate_compile_result.py:280-296`).

An `rg` check found no dedicated tests for the new exports.

**Smallest fix:** add tiny tests for wrapper filtering and constant import.

### 2. M2/M3 slug-list coercion must be explicit

**Angles:** [A], [D]

Spec text:

> `docs/task19-kpi-design.md:610-612` — `D = set(r.parsed_json.get("concept_slugs", []))`

If `concept_slugs` is a string, `set("abc")` produces character slugs. Schema failure catches the bad type elsewhere, but the measure formula still needs deterministic behavior.

**Smallest fix:** say non-`list[str]` slug fields are treated as empty for M2/M3.

### 3. M1 duplicate outgoing-link semantics are undefined

**Angles:** [A]

Spec text:

> `docs/task19-kpi-design.md:595-598` — M1 counts `p["outgoing_links"]` directly.

M5 explicitly uses set semantics in code (`kdb_compiler/validate_compiled_source_response.py:153-161`), but M1 does not say whether duplicate outgoing links count once or multiple times.

**Smallest fix:** choose list-count or set-count and state it.

### 4. Historical Phase 2 text remains easy to misread

**Angles:** [B]

Spec text:

> `docs/task19-kpi-design.md:411-424` — Phase 2 rows still show old pre-Round-3 weights and per-page metric names.

This is labeled historical, but it is close enough to live status text that a future implementer may skim the wrong section.

**Smallest fix:** mark the whole subsection "superseded by Round 3 / Phase 3 below."

## Defensible

### 1. M2/M3 Jaccard repair worked

**Angles:** [D], [E]

The Phase 3 M2/M3 formulas are bounded and micro-aggregated (`docs/task19-kpi-design.md:607-623`). Declared-nonempty/pages-empty and pages-nonempty/declared-empty both score 0 through a nonempty union.

### 2. Within-source duplicates and cross-source duplicates are separable

**Angles:** [D]

Within-source duplicate slugs are caught by S3 via `duplicate_slug` (`kdb_compiler/validate_compile_result.py:154-174`). Cross-source duplicate slugs collapse naturally in M1's target set. That is defensible for "does this link resolve to any page?"

### 3. Partial capture-full runs fail loud

**Angles:** [G]

Spec text:

> `docs/task19-kpi-design.md:482-485` — parse-passing records with `parsed_json is None` raise `RuntimeError`.
>  
> `docs/task19-kpi-design.md:801-805` — `score_run()` documents that `RuntimeError`.

That is the right failure mode for mixed capture-full runs. Caveat: the provider/model empty-record bug above can still hide some pre-response failures before this assertion sees them.

## Prior Review Continuity

Resolved from take 1:

- Per-page cost/latency denominator was replaced by source words.
- M2/M3 were changed to bounded Jaccard.
- M5 rollover ambiguity was removed by landing Task #28 first.
- Token overrun telemetry now exists on `RespStatsRecord`.
- Semantic-correctness blind spot is now acknowledged.

Still unresolved or reintroduced:

- Link-abstinence via M1/M5 zero-denominator redistribution.
- Version/candidate-set comparability remains intentionally rejected; this is defensible only if scorecards say final scores are within-candidate-set only.
- Cost persistence/versioning wording is currently false and internally inconsistent.
