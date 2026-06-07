# Model Provider API-Call Reference

How `common/call_model.py` calls each provider, the per-provider knobs, and a canonical
example per provider. **Grounded in the code** — every "what we send" row reflects
`_call_openai_compat` / `_call_anthropic` as written, not aspiration.

> Pool entries live in `common/models.json`; `common/model_pool.py` `resolve_models_json(id)`
> turns an entry into a `ModelRequest`'s provider/model/knobs (incl. translating the
> semantic `thinking` field into the provider's `extra_body` disable-param). The engine
> (`call_model.py`) takes an explicit `ModelRequest` and is provider-routing only.

## What we send on EVERY openai-compat call (`_call_openai_compat`)

```python
client = OpenAI(api_key=…, base_url=<provider>, timeout=LLM_TIMEOUT_SECONDS)
kwargs = {
    "model": model,                       # gemini: "models/"-prefixed
    "messages": [ {system?}, {user} ],
    "temperature": req.temperature,       # 0.0
    "max_tokens" | "max_completion_tokens": req.max_tokens,   # latter iff use_completion_tokens
}
if req.json_mode:  kwargs["response_format"] = {"type": "json_object"}
if req.extra_body: kwargs["extra_body"] = req.extra_body     # e.g. thinking-disable param
kwargs.update(req.extra)                                     # arbitrary per-call escape (unused today)
resp = client.chat.completions.create(**kwargs)
```

**Not set anywhere (important):**
- **`stream`** — unset → SDK default `False`. We are non-streaming by design (batch compile).
- **`reasoning_effort`** — unset. Reasoning models use the provider default. Only meaningful when
  thinking/reasoning is *enabled*; for our thinking-disabled entries it's moot. To control it
  would require adding it to `extra_body`/`extra` (no entry does today).
- `top_p`, `seed`, `stop`, `n`, etc. — unset (SDK defaults).

Anthropic uses a **different SDK** (`_call_anthropic`): `client.messages.create(model, max_tokens,
temperature, messages=[user], system?)` + `req.extra`. No `response_format`, no `extra_body`,
no streaming. (`json_mode` is a no-op on the anthropic path — it has no `response_format`.)

## Structured output — we use the WEAK mode everywhere

We send `response_format={"type": "json_object"}` (JSON **mode** — "be valid JSON"). The strong
form is **`json_schema`** (schema-constrained / "Structured Outputs" — the model is decoded
against our JSON schema, much higher JSON reliability):
```json
response_format={"type": "json_schema",
                 "json_schema": {"name": "...", "schema": <our schema>, "strict": true}}
```
| provider | strong structured output | how to reach it |
|---|---|---|
| openai (gpt-4o-mini / -2024-08-06 & later) | ✅ `json_schema` strict | **in-compat-path** — upgrade `response_format` (verified) |
| xai (grok-4.3, grok-4-1-fast-reasoning) | ✅ `json_schema` strict via OpenAI SDK @ api.x.ai/v1 | **in-compat-path** — upgrade `response_format` (verified) |
| deepseek | likely ✅ (OpenAI-compat) | in-compat-path — ⚠️ verify; already clean on json_object so low urgency |
| gemini | ✅ via **native SDK** `response_json_schema` | needs native handler — ⚠️ compat-endpoint json_schema support unverified |

**Key takeaway:** the json_object→json_schema upgrade is the real JSON-reliability lever (the
likely fix for Gemini's quarantines). For openai/xai/deepseek it's a `response_format` change
**inside the existing compat path** — NOT a per-provider split. The split is only forced where a
provider's *compat* endpoint can't do `json_schema` (possibly just Gemini → native SDK). Cost:
thread our schema into the call (`ModelRequest` gains an optional schema; callers supply
`compile_result.schema.json` / Pass-1 schema) + make our schemas strict-compatible + re-benchmark.

## Thinking / reasoning control — verified vs TODO

`resolve_models_json` injects a disable-param into `extra_body` ONLY for providers in the
verified table (`_THINKING_DISABLE_EXTRA_BODY`). Everything else is a no-op — **no guessed
param ever fires on a paid call**.

| provider | thinking default | disable param (in `extra_body`) | status |
|---|---|---|---|
| deepseek | ON | `{"thinking": {"type": "disabled"}}` | ✅ verified (api-docs.deepseek.com) |
| alibaba (qwen3.x) | ON | `{"enable_thinking": false}` | ✅ verified (DashScope deep-thinking docs) |
| anthropic | OFF (opt-in) | — (no param needed) | ✅ no-op |
| ollama-local/cloud | model-dependent (gemma4: none) | — | ✅ no-op |
| gemini (2.5+/3.x flash) | ON | `thinkingBudget: 0` — exact openai-compat shape unknown | ⚠️ **TODO verify** |
| openai (gpt-5.x) | reasoning models reason | `reasoning_effort` — may not fully disable | ⚠️ **TODO verify** |
| xai (grok reasoning) | ON | `reasoning_effort`? — may not be disableable | ⚠️ **TODO verify** |

---

## Per-provider detail

### deepseek — `https://api.deepseek.com` · `DEEPSEEK_API_KEY` · openai SDK
- **API docs:** https://api-docs.deepseek.com/
- Models: `deepseek-v4-flash` (active default), `deepseek-v4-pro` (active). No `:direct` suffix in real slugs.
- Thinking: param `extra_body={"thinking": {"type": "disabled"|"enabled"}}`. We disable. `reasoning_effort` only applies when enabled → moot for us.
- Provider's own example (thinking ENABLED — *not* our config):
  ```python
  client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
  client.chat.completions.create(
      model="deepseek-v4-pro",
      messages=[{"role":"system","content":"…"},{"role":"user","content":"…"}],
      stream=False,
      reasoning_effort="high",
      extra_body={"thinking": {"type": "enabled"}},
  )
  ```
- **Our call** sends the same minus `reasoning_effort`, with `extra_body={"thinking":{"type":"disabled"}}`, `response_format={"type":"json_object"}` (json_mode), `stream` unset (False).

### alibaba (Qwen) — `https://dashscope-us.aliyuncs.com/compatible-mode/v1` · `QWEN_US_API_KEY` · openai SDK
- **API docs:** https://www.alibabacloud.com/help/en/model-studio/ · thinking: https://www.alibabacloud.com/help/en/model-studio/deep-thinking
- **Model page (qwen3.5-flash):** https://modelstudio.console.alibabacloud.com/us-east-1?tab=doc#/doc/?type=model&url=2840914_2&modelId=group-qwen3.5-flash (Model Studio console — requires login)
- Models: `qwen3.5-flash`, `qwen3.6-flash` (active). Hybrid reasoning, **thinking ON by default**.
- Disable: `extra_body={"enable_thinking": false}` (now set via the `thinking` field). This is the fix for qwen's slowness.
- Provider's own example (thinking ENABLED + **streaming** — *not* our config):
  ```python
  client = OpenAI(api_key=os.getenv("DASHSCOPE_API_KEY"),
                  base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1")
  completion = client.chat.completions.create(
      model="qwen3.5-flash",
      messages=[{"role":"user","content":"…"}],
      extra_body={"enable_thinking": True},
      stream=True)               # thinking-on splits into reasoning_content + content deltas
  for chunk in completion:
      delta = chunk.choices[0].delta
      delta.reasoning_content   # the thinking trace
      delta.content             # the answer
  ```
- **Our call:** `extra_body={"enable_thinking": false}`, **non-streaming** — thinking-off yields no `reasoning_content`, just `content`, which `_call_openai_compat` reads in one shot (`resp.choices[0].message.content`). The slowness was the server generating the reasoning trace; disabling it removes that.
- ⚠️ **Streaming watch-item:** the official thinking-on example streams, and DashScope notes "most of these models support only streaming output." But "streaming is not strictly required when thinking is **disabled**," and the #109 cohort already ran `qwen3.5-flash` **non-streaming** successfully (with thinking *on*, the harder case) — so our thinking-off non-streaming path is empirically valid. If a future qwen call errors with a stream-required message, that's the trigger to add streaming support (a real refactor — `call_model` returns one response, not a stream).

### deepseek-via-alibaba / ollama-cloud — dropped routes
- `deepseek-v4-flash:alibaba` (alibaba compat layer) and `deepseek-v4-flash:cloud` (ollama-cloud) are **dropped** (audit ledger). The alibaba compat layer historically stripped/mis-routed `response_format` for non-Qwen models (`</think>` leakage) — see the entry's `dropped_reason`.

### anthropic — anthropic SDK · `ANTHROPIC_API_KEY`
- **API docs:** https://docs.anthropic.com/ (API reference: https://docs.anthropic.com/en/api/overview)
- Models: `haiku-4.5` (`claude-haiku-4-5-20251001`), `sonnet-4.6` (`claude-sonnet-4-6`).
- Extended thinking is **opt-in** (off by default) → no disable param needed.
- Separate code path (`_call_anthropic`): `messages.create(model, max_tokens, temperature, messages, system?)`. No `response_format` / `extra_body`.

### openai — default base_url (`api.openai.com`) · `OPENAI_API_KEY` · openai SDK
- **API docs:** https://platform.openai.com/docs/ · structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Model: `gpt-5.4-mini`. Uses `max_completion_tokens` (`use_completion_tokens: true`) — GPT-5 family requirement.
- **Structured outputs:** ✅ `response_format={"type":"json_schema","json_schema":{"name":…,"schema":…,"strict":true}}` ("evolution of JSON mode" — schema adherence; we use the weaker `json_object`). Supported gpt-4o-mini / gpt-4o-2024-08-06 & later (gpt-5.x family expected; not explicitly confirmed in the guide).
- Reasoning control — `reasoning_effort` (gpt-5.5): `"none"`, `"low"`, `"medium"` (default), `"high"`, `"xhigh"` (docs: https://developers.openai.com/api/docs/guides/deployment-checklist#set-up-reasoningeffort). `"none"` = fully disabled; `"low"` = lowest *active* reasoning (no `"minimal"`). Passed nested: `reasoning={"effort": …}` → via `extra_body={"reasoning": {"effort": "none"}}`.
  - **Design note for our workload:** OpenAI recommends **`"low"` for "extraction, routing, classification, or a simple rewrite"** — i.e. our compile/extract task class. So `"none"` (fully off) vs `"low"` (OpenAI's recommended floor for extraction) is a real tuning choice — A/B it if we ever run gpt in the #109 cohort, don't assume `"none"`.
  - ⚠️ **Still TODO / do NOT add yet:** values documented for `gpt-5.5`; our `gpt-5.4-mini` is unconfirmed. Verify before adding a pool knob.

### gemini — `https://generativelanguage.googleapis.com/v1beta/openai/` · `GEMINI_API_KEY` · openai SDK
- **API docs:** https://ai.google.dev/gemini-api/docs · openai-compat: https://ai.google.dev/gemini-api/docs/openai
- **Model page (gemini-3.1-flash-lite):** https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite
- Model: `gemini-3.1-flash-lite`. **Model id must be `models/`-prefixed** (handled in `_call_openai_compat`).
- Gemini 2.5+/3.x flash think by default; native disable is `thinking_config={"thinking_budget": 0}` — ⚠️ **TODO verify** for flash-lite.

> **⚠️ FINDING — we likely use a second-class Gemini path.** We route Gemini through the
> OpenAI-compat shim with `response_format={"type":"json_object"}` (plain "emit valid JSON").
> The **native `google-genai` SDK** supports `response_json_schema` — *schema-constrained*
> structured output (the model is decoded against our JSON schema, not just told to be JSON):
> ```python
> from google import genai
> client = genai.Client()
> resp = client.models.generate_content(
>     model="gemini-3.1-flash-lite",
>     contents=[prompt, input_text],
>     config={
>         "response_mime_type": "application/json",
>         "response_json_schema": <our JSON schema>,   # e.g. compile_result.schema.json
>         # "thinking_config": {"thinking_budget": 0}, # disable thinking
>     },
> )
> ```
> **Why this matters:** in the #109 cohort, `gemini-3.1-flash-lite` was the **worst** performer
> (−10 quarantine, "quarantines most"), and the dropped `gemini-3-flash-preview` was cut for
> "run-to-run variance + intermittent token-overrun." Schema-constrained decoding is exactly
> the lever that fixes JSON-malformation quarantines — so Gemini's poor showing may be partly
> **self-inflicted by the weak compat path**, not a model-quality gap. A native `_call_gemini`
> path (sibling to `_call_anthropic`) with `response_json_schema` + `thinking_config` is a
> candidate follow-up — it adds the `google-genai` dependency + schema plumbing, and would
> require re-benchmarking Gemini (#109). **Not in #110 scope; flagged for deliberate evaluation.**

### xai (Grok) — `https://api.x.ai/v1` · `XAI_GROK_API_KEY` · openai SDK
- **API docs:** https://docs.x.ai/ · structured outputs: https://docs.x.ai/developers/model-capabilities/text/structured-outputs
- Model: `grok-4-1-fast-reasoning` (a *reasoning* model).
- **Structured outputs:** ✅ `response_format={"type":"json_schema","json_schema":{"name":…,"schema":…,"strict":true}}` — works through the **OpenAI SDK** against `api.x.ai/v1` (our existing path), explicitly supported on `grok-4-1-fast-reasoning`. We use the weaker `json_object`.
- Reasoning control — `reasoning_effort`: `"none"` (disables reasoning entirely), `"low"` (default), `"medium"`, `"high"` (docs: https://docs.x.ai/developers/model-capabilities/text/reasoning#the-reasoning_effort-parameter). Disable via `extra_body={"reasoning_effort": "none"}` (merges into the request body) — IF added, the table maps `xai → {"reasoning_effort": "none"}`.
  - ⚠️ **Still TODO / do NOT add yet:** the doc covers `grok-4.3` / `grok-4.20-multi-agent`, **not** our `grok-4-1-fast-reasoning` — its support for `"none"` is unconfirmed (a "fast-reasoning" model may not allow disabling reasoning), and the exact shape (flat `reasoning_effort` vs nested `reasoning.effort`) is ambiguous. Verify against `grok-4-1-fast-reasoning` before adding a pool knob.
  - Note: unlike deepseek/qwen (whose disable param is a nested `extra_body` object/bool), xai's lever is `reasoning_effort` — a top-level request-body string. The `_THINKING_DISABLE_EXTRA_BODY` table handles it fine (`extra_body` merges into the body), so the `thinking` field abstraction still covers it once verified.

### ollama-local / ollama-cloud — `http://localhost:11434/v1` (or `OLLAMA_BASE_URL`) / `https://ollama.com/v1`
- **API docs:** https://docs.ollama.com/ (API reference: https://docs.ollama.com/api)
- `ollama-local` api_key is the literal `"ollama"`; `ollama-cloud` uses `OLLAMA_API_KEY`.
- Model: `gemma4-obsidian-bench` (local). No thinking mode → no-op.

---

## Open follow-ups
- ⚠️ Verify + add thinking/reasoning disable params for **gemini, openai, xai** (the three reasoning-capable entries currently running thinking-on). Until verified, they stay no-op per the "no guessed param on a paid call" rule.
- Decide whether `reasoning_effort` is ever a lever we want (only relevant for thinking-enabled configs).
- Re-confirm the qwen non-streaming path is robust given the DashScope streaming caveat.
