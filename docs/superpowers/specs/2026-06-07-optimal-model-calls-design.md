# Design — Optimal per-model calls + clean-slate re-benchmark (#111)

- **Task:** #111 (optimal-calls engine sub-project)
- **Date:** 2026-06-07
- **Branch:** `feat/111-structured-output-upgrade`
- **Anchors:** `docs/reference/model-provider-api-calls.md` (per-provider call shapes, structured-output + reasoning matrix), #110 (the model pool this builds on), #109 (the benchmark this feeds).

## 1. Purpose

The #109 cohort scored every model through a **lowest-common-denominator** path — `response_format={"type":"json_object"}` (weak JSON mode), thinking-on for several models, the OpenAI-compat shim for Gemini. So "Gemini quarantines most / deepseek is best" are conclusions from a **handicapped comparison** — they reflect *our config*, not the models. We cannot tell which model builds the best graph until each is called the right way.

> **#111 goal:** call each cohort model through its **optimal configuration** (best structured-output mode + correct reasoning/thinking setting + right SDK/path), then re-run the #109 cohort from a **clean slate**, so the leaderboard reflects the models, not our handicaps. #111 is the prerequisite for a fair #109 re-run.

## 2. Scope

- **First batch (re-benchmark these 4):** `deepseek-v4-flash`, `qwen3.5-flash`, `gpt-5.4-mini`, `gemini-3.1-flash-lite`. (All models eventually; this is the first clean-slate cohort.)
- This spec covers the **optimal-calls engine** (and the pool-prep that supports it). The **clean-slate re-benchmark** itself runs on existing #109 machinery (`kdb-orchestrate --emit-kpis` → `kdb-benchmark score`), fired by Joseph.
- **Out of scope:** a full per-provider adapter-registry refactor (revisit *after* we have a 2nd native concrete — see §8); optimizing/benchmarking the later-batch models (`grok-4.20-0309-non-reasoning`, `gemma-4-12b-qat`) — they're added to the pool but not raced this round; Anthropic structured output (Claude uses tool-use, a different mechanism — out unless added to a batch).

## 3. The two-phase, tagged de-risk strategy

The load-bearing risk is the `json_schema` change (a too-strict schema *rejects valid output → more quarantines*, the opposite of the goal). So we **isolate the schema variable** with tagged baselines and a benchmark at each checkpoint — every step has a clean rollback, and `baseline-1 → baseline-2` is a pure measure of what `json_schema` bought.

| step | action | rollback / measure |
|---|---|---|
| **Phase 0** | Implement **run-provenance** ([1]: record `release_version` + save stdout per-run) + **leaderboard key** `(model, release_version)` ([2]); semver-tag `baseline-0`; benchmark | establishes the **measured baseline** (current behavior + provenance) |
| **Phase 1** | All non-schema API changes (pool-prep + per-model reasoning/thinking config) | `baseline-0 → baseline-1` = config-optimization effect |
| **Checkpoint A** | Semver-tag `baseline-1` + Joseph fires the clean-slate 4-model benchmark | the **"optimal minus schema"** reference |
| **Phase 2** | The `json_schema` structured-output change | revert to `baseline-1` if it regresses |
| **Checkpoint B** | Semver-tag `baseline-2` + benchmark | `baseline-1 → baseline-2` = `json_schema`'s isolated effect |

**Baselines are semver tags** per `RELEASES.md` — `v0.5.4` is the current pre-#111 release, so #111's baselines are **`v0.5.5`** (Phase 0 / baseline-0) → **`v0.5.6`** (baseline-1) → **`v0.5.7`** (baseline-2), and the recorded `release_version` reads as a real release number. Benchmarks are API-cost runs Joseph fires per `docs/reference/benchmark-cohort-procedure.md`. Net: the leaderboard accumulates each model at each release → the full optimization progression is visible per-model.

**Plans:** Phase 0, Phase 1, and Phase 2 each get their **own implementation plan** (separate `writing-plans` cycles), in order; each later phase begins only after the prior checkpoint's baseline is captured. This spec covers all three.

## 3a. Phase 0 — run provenance + leaderboard key (build FIRST)

Prerequisite infrastructure for *every* baseline benchmark. Touches the #109 benchmark machinery (`kdb-orchestrate --emit-kpis` + `kdb-benchmark score`).

- **[1a] Record `release_version` per run.** At run time capture **`git describe --tags --dirty`** (yields the semver release tag, e.g. `v0.5.4`, or `v0.5.4-3-g<sha>` off-tag, or `…-dirty` with uncommitted changes — so a run is never silently mislabeled as a clean release). Persist it into the `measurements.json` header (`RunMeasurementHeader`, alongside provider/model) and the per-run dir `benchmark/runs/<id>/`.
- **[1b] Save the orchestrate stdout** (the Task-#102 live progress narrative) into `benchmark/runs/<id>/` (e.g. `console.log`), so each run's artifacts are self-contained.
- **[2] Leaderboard keyed on `(model, release_version)`.** `kdb-benchmark score` makes the unique line item **provider+model+release_version** (extends #109's existing `provider`+`model` row identity); it replaces an existing row only when **all three match**. A run on a new release_version is a **new row** — same model at different releases coexist (this is what makes the baseline-to-baseline deltas visible). Reset = delete the leaderboard file (unchanged).
- **Tests:** `release_version` is captured into the header + written to the per-run dir; stdout is teed to `console.log`; `score` keys on the triple — a re-run with the same triple replaces, a different `release_version` adds a row.
- Then **semver-tag `baseline-0`** and benchmark (current behavior, now properly recorded).

**Plans:** Phase 1 and Phase 2 each get their **own implementation plan** (separate `writing-plans` cycles) — Phase 2 only begins after Checkpoint A's baseline is captured. This spec covers both.

## 4. Phase 1 — everything except `json_schema`

### 4a. Pool-prep
- **File split:** `common/models.json` holds **active entries only**; new **`common/models_dropped.json`** holds the dropped curation ledger as a **pure human archive — the code never reads it** (Joseph's decision (b)).
- **`model_pool.py`:** `load_pool()` reads only `models.json`. Move all `dropped:true` entries to `models_dropped.json` — their `dropped`/`dropped_reason` keys stay there for the human record; active entries in `models.json` simply carry no `dropped` key. **Retire the now-unreachable dropped-guard:** with no `dropped` entries in the active pool, `DroppedModelError` and its branch in `resolve_models_json` are dead → remove them (a dropped id now yields `UnknownModelError` — "not in the pool"; the escape-hatch + conflict-check stay). Update/remove the #110 dropped-guard tests accordingly.
- **Roster:**
  - **Drop** `grok-4-1-fast-reasoning` (deprecated) → into `models_dropped.json` with reason "deprecated 2026-06; replaced by grok-4.20-0309-non-reasoning."
  - **Add** `grok-4.20-0309-non-reasoning` (provider `xai`, ctx_window 1_000_000, price_in 1.25, price_out 2.50). Non-reasoning ⇒ no thinking to disable. *Active, not in batch 1.*
  - **Add/replace** ollama-local model with `gemma-4-12b-qat` (provider `ollama-local`). *Active, not in batch 1; requires the model pulled on Joseph's machine.*
    - **UPDATE 2026-06-07:** shipped as `gemma4-12b-qat-128k` (128k ctx), then **ARCHIVED** after a live run — extremely slow, majority of sources quarantined, couldn't finish 36 sources (local 12B-QAT capability/hardware limit, not transient). **No active `ollama-local` model remains** → the Phase-2 "ollama-local native handler" candidate is **deprioritized** (nothing to serve it); Gemini is the sole Phase-2 native case. A local model's failure is capability/speed, not call-shape — `json_schema` would not rescue it.

### 4b. Per-model reasoning/thinking config (batch-1)

| model | provider | non-schema optimal config | status |
|---|---|---|---|
| `deepseek-v4-flash` | deepseek | thinking disabled (`{"thinking":{"type":"disabled"}}`) | ✅ **done in #110** |
| `qwen3.5-flash` | alibaba | `{"enable_thinking": false}` | ✅ **done in #110** |
| `gpt-5.4-mini` | openai | `reasoning_effort` — **`"none"` vs `"low"`** (OpenAI recommends `"low"` for extraction/classification — our task class) | ⚠️ **verify for gpt-5.4-mini** (docs cover gpt-5.5); Joseph fires a probe |
| `gemini-3.1-flash-lite` | gemini | thinking disable (`thinking_budget=0`) | ⚠️ **see Gemini wrinkle below** |

So Phase 1's *per-model* work is just **gpt-5.4-mini** + **gemini** (deepseek/qwen already optimal).

> **Binary `thinking` field vs graded reasoning.** #110's `thinking` field is **binary** (`disabled`/`enabled`) and the `_THINKING_DISABLE_EXTRA_BODY` table maps cleanly for deepseek/qwen (on↔off). But **openai/xai reasoning is graded** (`none`/`low`/`medium`/`high`/…), and we may want `gpt-5.4-mini` at **`"low"`** (OpenAI's recommended floor for extraction), *not* fully off — which the binary field can't express. Resolution: for graded providers, set the level via a **raw `extra_body`** entry on the model (e.g. `extra_body={"reasoning":{"effort":"low"}}`), leveraging #110's "keep `extra_body`, multi-option" decision. The binary `thinking` field stays for binary providers; graded reasoning rides raw `extra_body`. (Decide `none` vs `low` for gpt empirically — default to `"low"` unless a probe says otherwise.)

> **Gemini wrinkle (phasing):** Gemini's thinking-disable (`thinking_budget=0`) may or may not pass through the *compat* endpoint's `extra_body`. **If compat accepts it** → it's just another `thinking`-table entry, lands in Phase 1. **If not** → Gemini's full optimal config (thinking *and* schema) both wait on the native handler in Phase 2. Resolve via a quick verification (Joseph fires) or the gemini openai-compat docs. Until resolved, Gemini's Phase-1 config is "set if compat accepts, else defer to Phase 2."

### 4c. Tests (Phase 1)
- `load_pool()` reads only active entries; a dropped id (e.g. `deepseek-v4-flash:alibaba`) → `UnknownModelError`; `models_dropped.json` is valid JSON and is NOT loaded by code.
- Roster: new entries resolve to correct provider/ctx/price; deprecated grok id is gone from active.
- gpt-5.4-mini resolves with the chosen reasoning param in `extra_body`; gemini resolves with the thinking param iff compat-confirmed.
- Existing #110 tests updated for the dropped-guard retirement.

## 5. Checkpoint A
Tag `baseline-1`. Joseph fires the clean-slate batch-1 benchmark (reset sandbox → run each of the 4 `--emit-kpis` → `kdb-benchmark score`). This is the **"optimal config, json_object structured output"** reference leaderboard.

## 6. Phase 2 — `json_schema` structured output

> **⛔ SHELVED 2026-06-07 (data-mooted) — #111 closed at Phase 1.** baseline-1 showed the default model (deepseek) already at **0 quarantine** under `json_object` + the coerce ladder, so structured-output was solving a problem we don't have. The real #111 win was the **thinking/reasoning-disable latency cut (~30–70%)**, not schema-constrained decoding. Strict `json_schema` was judged a **poor fit for our generative use case**: (1) it would grammar-mask the rich free-form `body` field (quality risk); (2) our *hard* failures are **semantic** (slug-format, body↔`outgoing_links` invariant, slug-list consistency) which no `json_schema` can express — the reconciler+coerce+semantic layer owns them regardless; (3) its supported-keyword subset varies per provider and drops our value-constraints (`pattern`/`minLength`/`minItems`); (4) it contradicts the ratified coerce-don't-reject philosophy. Non-strict (schema-as-hint) was considered but deemed not worth the work given the default is already clean. **Un-shelve only if a future model genuinely needs schema-constrained decoding.** The design below is retained as the record of the not-taken path.

### 6a. Mechanism
- **`ModelRequest` gains `json_schema: dict | None = None`** (the engine's input contract; sits alongside `json_mode`).
- **Callers thread it:** `pass1_caller` → the Pass-1 content schema (from `pass1_schema.py`); `compile_one` → `compiler/schemas/compiled_source_response.schema.json` (the LLM-emitted Pass-2 shape).
- **`_call_openai_compat`:** when `json_schema` is present, send
  `response_format={"type":"json_schema","json_schema":{"name":<n>,"schema":<schema>,"strict":true}}`
  instead of `{"type":"json_object"}`. (json_mode stays the fallback when no schema is supplied.)

### 6b. Strict adaptation + the spike (the risk)
OpenAI/xai **strict** mode requires the schema be *strict-clean*: every object `additionalProperties:false` (the Pass-2 top level already has it — nested `pages[]` objects must too), **every property in `required`** (optionals expressed as `["type","null"]` unions), and only the supported keyword subset. Adapting `compiled_source_response.schema.json` (nested `pages[]`) is the real work, and **a too-strict schema rejects valid output**.

- **Spike first:** adapt the Pass-2 response schema to strict, then fire it at *one* batch-1 model on the real sandbox corpus (Joseph fires) → confirm it holds before building out. Pass-1's flat schema is trivially strict-clean; do it alongside.
- **Fallback:** if strict is too brittle for Pass-2, use **`strict:false`** for Pass-2 (schema-as-guidance, still better than `json_object`) and keep `strict:true` only where it's safe (Pass-1, and any provider/schema combo that validates clean).

### 6c. Per-provider dispatch
- **openai, xai** — `json_schema` strict via `response_format` in the **existing compat path** (verified). No new handler.
- **deepseek, qwen** — likely support `json_schema` via compat; **verify** (Joseph fires a probe) — fall back to `json_object` for that provider if not.
- **gemini** — its native SDK uses `response_json_schema`. **If the compat endpoint accepts `response_format: json_schema`**, gemini stays in the compat path (no new handler). **If not**, add a native **`_call_gemini`** handler (sibling to `_call_anthropic`, `google-genai` dependency) using `response_json_schema` + `thinking_config`. This is the one contingent, larger piece — gated on the compat-support verification.

### 6d. Tests (Phase 2)
- `ModelRequest.json_schema` threads from caller → `_call_openai_compat` → the constructed `response_format` (capture-assert, per the #110 pattern).
- A test asserting our adapted `compiled_source_response.schema.json` is **strict-clean** (additionalProperties:false on every object; every property required-or-null-union) — so a regression to the schema is caught in CI, not on a paid call.
- json_mode remains the path when no schema is supplied (back-compat).
- Gemini native handler (only if introduced): its own dispatch + `response_json_schema` construction test.

## 7. Checkpoint B
Tag `baseline-2`. Joseph fires the benchmark. **`baseline-1 → baseline-2`** isolates `json_schema`'s effect on the cohort (quarantines, graph quality). If it regresses, revert to `baseline-1`.

## 8. Architecture note (concrete-first)
Keep `_call_openai_compat` and **extend** it with the `json_schema` branch — do NOT refactor into a per-provider registry yet. If Gemini forces a native `_call_gemini`, we then have **two** native concretes (anthropic + gemini); only *then* consider extracting a clean per-provider adapter/registry (a future task, not this spec). This honors concrete-first — earn the abstraction from two real handlers, don't design it in the abstract.

## 9. Verifications Joseph fires (API cost)
1. `gpt-5.4-mini` `reasoning_effort` — accepts `"none"`? is `"low"` better for our extraction workload? (Phase 1)
2. Gemini compat endpoint — accepts thinking-disable `extra_body`? accepts `response_format: json_schema`? (decides the native-handler question) (Phase 1/2)
3. `deepseek`/`qwen` compat — accept `json_schema`? (Phase 2)
4. The Pass-2 strict-schema spike (Phase 2).
5. The three baseline benchmarks — `baseline-0` (Phase 0), `baseline-1` (Checkpoint A), `baseline-2` (Checkpoint B).

## 10. Open risks
- **Strict-schema feasibility for Pass-2** (the big one) — retired by the §6b spike + the `strict:false` fallback.
- **Gemini native-vs-compat** — decides whether Phase 2 includes a new SDK + handler; resolved by verification #2.
- **`none` vs `low` for gpt reasoning** — empirical; OpenAI's own guidance leans `"low"` for extraction.
