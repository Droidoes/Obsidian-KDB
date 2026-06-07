# Design — `common/models.json`: user-owned model pool + the diagnostics it powers

- **Task:** #110
- **Date:** 2026-06-06
- **Status:** Design — awaiting spec review → writing-plans
- **Supersedes context:** the model registry retired with the legacy #5 benchmark engine (`tools/benchmark/models.json`, deleted `01a1d2d`/merge `8469fb8`).

## 1. Problem & principle

`call_model.py` is the **engine** (developer-owned: provider SDKs, routing, retry, telemetry). The **pool of models** is user-owned configuration and must not require editing Python. Today it does:

- The set of valid providers is a hardcoded `Provider` union in `common/call_model.py`.
- Model selection is two raw flags — `kdb-orchestrate --provider <p> --model <m>` — passed opaquely to the SDK. There is no curated alias list, no per-model defaults, no guard against mismatched provider/model pairs.

The old `models.json` already drew the right line: it held **only user data** (alias→routing, per-model knobs, pricing, capability metadata, and a curation ledger), while provider dispatch (base_url, SDK family) stayed in code. It was deleted because its sole consumer — the #5 scoring engine — was retired. Two diagnostics it powered were lost or never wired:

- **Cost** was *derived downstream* by the deleted scorer from `price_in/price_out × tokens`. Nothing computes cost now (regression).
- **`ctx_window`** was intended as a pre-call overrun estimate; never wired.

This task reinstates the user-owned pool, **re-homed to `common/`** (it now feeds `call_model`, used by every pass — not benchmark-only) and **wired to the live path**, and restores the two diagnostics that depend on it.

### Naming (resolved from history)

The file was **always `models.json`** — `kdb_benchmark/models.json` (2026-05-08 → 05-23) then `tools/benchmark/models.json` (06-02 → deleted 06-06). There was never a `call_models.json`. Keep the basename `models.json`; only the directory moves → **`common/models.json`**. (Matches contents — it is a list of models — and honors "keep the same file name.")

## 2. Architecture

Three layers, clean boundaries:

```
common/models.json   (DATA — user-owned: pool + metadata + curation ledger)
        │
        ▼
common resolver      (LOOKUP — alias → ModelRequest fields; dropped-guard)
        │
        ▼
call_model.py        (ENGINE — unchanged dispatch; takes explicit provider+model)
```

`ModelRequest` already exposes every slot the JSON needs — `provider, model, max_tokens, use_completion_tokens, extra_body` — so each JSON entry maps **one-to-one** onto a `ModelRequest`. No new plumbing inside `call_model.py`'s dispatch.

## 3. `common/models.json` schema

A JSON array of entries. Fields (shaped exactly as the retired file):

| field | required | purpose |
|---|---|---|
| `id` | ✅ | alias the user types (`--model <id>`) |
| `provider` | ✅ | routing key — must be a valid `Provider` literal |
| `model` | ✅ | real model-id string passed to the SDK |
| `ctx_window` | ✅ | context-window size (tokens) — Phase 3 pre-flight guard |
| `max_output_tokens` | optional | model's output *ceiling* (capability). **Clamp metadata, NOT the per-call value** — see §4 note |
| `use_completion_tokens` | optional | GPT-5+ `max_completion_tokens` switch |
| `extra_body` | optional | provider kwargs (e.g. DeepSeek `{"thinking":{"type":"disabled"}}`) |
| `price_in` | ✅ | USD per 1M input tokens — Phase 2 cost |
| `price_out` | ✅ | USD per 1M output tokens — Phase 2 cost |
| `dropped` | optional | `true` ⇒ documented-rejected; selecting it errors |
| `dropped_reason` | optional | the curation-ledger audit text |

The `dropped`/`dropped_reason` curation ledger is **preserved** — institutional memory of which models were tried and rejected and why.

## 4. Phase 1 — Pool + resolver (foundation)

- **`common/models.json`** seeded from the recovered content (active + dropped entries), re-homed.
- **Resolver** (new, in `common/` — e.g. `common/model_pool.py`): loads `common/models.json` once; `resolve(id) -> ModelSpec` (a frozen dataclass: `id, provider, model, ctx_window, max_output_tokens, use_completion_tokens, extra_body, price_in, price_out`). The `ModelSpec` object lives at the top of the call tree (CLI → `run()`); its **fields are threaded additively** into the existing decomposed `enrich_one`/`compile_one` params (which already take `provider, model, max_tokens, use_completion_tokens, extra_body`). No `ModelSpec`-object refactor of those signatures — additive optional kwargs only, zero churn across the 1175 tests, consistent with the existing decomposed pattern.

> **`max_output_tokens` is a ceiling, not the per-call value.** `ModelRequest.max_tokens` = *how much output to request this call* (deliberately 4096 Pass-1, 32768 Pass-2/CLI) — a workload decision owned by the pass/CLI. The pool's `max_output_tokens` is the model's *capability*. Use it only as a clamp: `effective_max_tokens = min(requested, max_output_tokens)` when the field is present. Never substitute it for the requested value.
  - Unknown `id` → `ModelConfigError` listing available ids.
  - `dropped: true` id → `ModelConfigError` echoing `dropped_reason` (the ledger actively protects against re-picking a rejected model).
- **CLI** (`kdb-orchestrate`): `--model <id>` resolves through the pool. `--provider` is **demoted to an escape hatch**, with one unambiguous rule:
  - `<id>` **is a known alias** → provider/knobs come from the pool; `--provider` is ignored. If `--provider` is passed *and conflicts* with the pool's provider, the run errors (catches the mistake rather than silently picking one). The way to run the same model on a different provider is a separate alias — the pool already does this (e.g. `deepseek-v4-flash` via `deepseek` vs `deepseek-v4-flash:alibaba` via `alibaba`).
  - `<id>` **is not a known alias** → `--provider` is **required**, and `<id>` is treated as a raw SDK model string (the one-off path; no pool metadata, so no cost/ctx guard for that call).
- **Default model + id scheme (resolved):** `:direct` is *our* benchmark-era route tag, **not** a real DeepSeek slug (verified against api-docs.deepseek.com — real slugs are `deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-chat`, `deepseek-reasoner`, no suffixes; and `:direct` only ever lived in our alias `id`, never in the `model` field sent to the API). Rule: **the direct DeepSeek route is canonical → bare slug (`:direct` is always redundant, dropped for both flash and pro); only genuinely-alternate routes (alibaba, cloud) keep a `:route` suffix for ledger provenance.** Id changes vs. the recovered file:
  - `deepseek-v4-flash:direct` (active, provider `deepseek`) → **`deepseek-v4-flash`** (the clean default)
  - `deepseek-v4-pro:direct` (dropped, provider `deepseek`) → **`deepseek-v4-pro`** (direct ⇒ bare, even though dropped)
  - `deepseek-v4-flash` (dropped, provider `alibaba`) → **`deepseek-v4-flash:alibaba`** (alternate route ⇒ suffixed; also vacates the bare name)
  - `deepseek-v4-flash:cloud` (dropped, ollama-cloud) — **unchanged** (alternate route, suffix kept)
  - all other ids seeded verbatim.

  The orchestrate default changes from `--model deepseek-v4-flash` (which had resolved to the **dropped** alibaba entry) to **`--model deepseek-v4-flash`** now resolving to the **active** direct entry. Without the rename the default + every #109 cohort run would hit the dropped-guard. The `--provider` default is dropped (provider now comes from the pool).
- **Thinking disabled (DeepSeek):** controlled by the request *parameter* `extra_body: {"thinking": {"type": "disabled"}}` (verified shape), not by model choice — already present on the entry; kept verbatim.
- **Orphan repoint:** `scripts/verify_structured_output_parity.py:18` references the deleted `tools/benchmark/models.json` → repoint to `common/models.json` (a second legitimate consumer of the pool).

## 5. Phase 2 — Cost diagnostic (pricing's job, restored)

`cost_usd = price_in/1e6 × **total**_input_tokens + price_out/1e6 × **total**_output_tokens`.

- **Aggregated tokens, not final-attempt.** You pay for every retry. Both telemetry paths already accumulate `total_input_tokens`/`total_output_tokens` (#108) — cost MUST use those, never the single-attempt `input_tokens`/`output_tokens`.
- **`price_in`/`price_out` are threaded in explicitly** as new optional kwargs (default `0.0`) — pure arithmetic on threaded inputs. Do **not** re-look-up the pool by `(provider, model)` inside the telemetry builders: the model string is not pool-unique (same `model` under different providers/prices), and a hidden pool dependency hurts testability.
- **Two telemetry paths** (Pass-1 ≠ Pass-2):
  - **Pass-2** — add `cost_usd: float` to `RespStatsRecord` (`common/types.py`); compute in `build_resp_stats` (`common/llm_telemetry.py`).
  - **Pass-1** — add `cost_usd` to the sidecar payload (`ingestion/enrich/replay_archive.py` `SidecarPayload`); compute where the sidecar is assembled.
- Stored **raw** (atomic fact); per-1k-source-words normalization stays a downstream projection (`source_words` already on the record). **Always-on**, not capture-gated.
- Pre-response failure / unknown / unpriced model → `cost_usd = 0.0` (best-effort; never crashes telemetry). Local/free models (`0`/`0`) → `0.0` naturally.

## 6. Phase 3 — Context-overrun pre-flight guard (ctx_window's job, new)

- Named constant `WORDS_TO_TOKENS = 1.3` (no tokenizer dependency — deliberate over-estimate, errs toward catching early; no existing helper to reuse).
- Shared helper (e.g. `common/model_pool.py` `estimate_prompt_tokens(system, user) -> int` + `fits_context(est_input, requested_output, ctx_window) -> bool`): `est_input = round(word_count × WORDS_TO_TOKENS)`, `word_count` = whitespace-split length of `system + "\n\n" + user` (matches how `prompt_hash` is built). The budget check is **`est_input + requested_output ≤ ctx_window`** (the call must fit input *and* the room reserved for output), not input alone.
- **Placement: right after prompt assembly in EACH pass, before the retry loop** — `pass1_caller` (after `prompt` is built, before the `for attempt` loop) and `compile_one` (after `state["prompt"]` is set, before the model call). **Not** inside `call_model` (Pass-1 loops `call_model` on retries → the guard would re-run per attempt) and **not** a field on `ModelRequest` (`ctx_window` is never sent to the API — it's a guard-only concern, keep the engine's input contract clean).
- **On overrun: skip-and-quarantine this source, do NOT abort the run.** "Fail fast" = no API spend for this source + route into the **existing per-source quarantine** via `failure_stage` (reuse the synthetic `"TokenOverrun"` exception-type vocab already in `types.py`), so the run continues over the other sources — consistent with how source-local failures are handled today.
- When the resolved entry has **no `ctx_window`** (e.g. an ad-hoc `--provider` one-off with no pool metadata), the guard is **skipped** (can't check what we don't know).
- Complements — does not replace — the existing **reactive, output-side** `token_overrun` flag (`stop_reason in {max_tokens, length}`). This new guard is **proactive, input-side**.

## 7. Testing (TDD per phase)

- **P1:** resolver returns correct `ModelRequest` fields for a known id; unknown id errors with id list; `dropped` id errors with reason; `--provider` override path; `extra_body`/`use_completion_tokens` carried through.
- **P2:** cost arithmetic for a priced model (known token counts → exact USD); zero-price local model → 0.0; unknown/absent-price model → 0.0; pre-response failure → 0.0.
- **P3:** estimate just under `ctx_window` passes; at boundary; just over → raises with no `call_model` invocation (assert the engine is not called).
- Full suite (1175 non-live) stays green. Live model calls remain `@pytest.mark.live`, fired by the user.

## 8. Boundaries / non-goals

- **No change to `call_model.py` dispatch** — it keeps taking explicit `provider`+`model`. Adding a genuinely new *provider* (new base_url/SDK branch) is still a code edit + env key; out of scope here.
- **Secrets stay in env** — API keys are never in `models.json` (`common/config`).
- **No pricing-promo tracking** — `price_*` are current static numbers; promo-expiry logic is out of scope.
- **No model-quality scoring** — this is telemetry/diagnostics, not quality (M2 E3 remains deferred).

## 9. Open follow-ups (not in this task)

- A cost-aware KPI / leaderboard column could later consume `cost_usd` (the #109 cohort). Enabled by, but not built in, this task.
