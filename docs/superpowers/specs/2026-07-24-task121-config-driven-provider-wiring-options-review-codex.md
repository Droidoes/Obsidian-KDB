# Task #121 — Config-Driven Provider Wiring Options Review (Codex R1)

**Date:** 2026-07-24  
**Reviewer:** Codex  
**Review target:** `docs/superpowers/specs/2026-07-24-task121-config-driven-provider-wiring-options.md` (v1.0)  
**Review prompt:** `docs/superpowers/specs/2026-07-24-task121-codex-review-prompt.md`

## Verdict

**REVISE.**

The intent is sound, and `api_key_env` is the right public configuration
identifier. I would not ratify Option 1 as currently written, however, because
the document does not define how a route travels from `ModelSpec` to
`call_model`, conflates an absent endpoint with an explicit `null`, and leaves
the raw `--provider` escape hatch plus Ollama's no-key route underspecified.

The best shape is a small fourth option: **required per-model route data for
every active pool entry, layered over a provider-default registry used only
when no pool route exists**. In other words, use Option 1's per-model freedom
for normal operation and Option 3's provider registry strictly as the
compatibility boundary for raw/direct calls—not as a second authority for
active pool entries.

Suggested precedence:

1. A known `models.json` entry produces an explicit `ModelRoute`; its values are
   authoritative, including `endpoint: null`.
2. A raw `--provider` escape-hatch call or direct `ModelRequest` with no route
   uses the provider-default registry.
3. An unknown provider, malformed route, or missing required environment
   variable fails before SDK construction with a secret-safe
   `ModelConfigError`/`PoolError`.

This is still a small change, but it makes the ownership boundary unambiguous
and composes cleanly with Task #118's coming per-pass model selection.

## Findings

### 1. Important — the proposed route has no end-to-end carrier

**Evidence:** options doc lines 28–31; `common/model_pool.py:39-55,64-97`;
`common/call_model.py:41-62,82-125`;
`orchestrator/kdb_orchestrate.py:1082-1118`;
`ingestion/enrich/pass1_caller.py:104-109,169-176`;
`compiler/compiler.py:150-167,354-370`.

The document says `ModelSpec` gains `endpoint` and `api_key_env`, then describes
`call_model` using `spec.endpoint`. That object is not available there.
`resolve_models_json()` runs at the CLI boundary, after which the orchestrator
threads individual scalar fields through both passes. `call_model()` receives
only a `ModelRequest`; it must not silently re-resolve the pool by the provider's
model string because aliases need not equal API model IDs, multiple pool
entries can target the same model, and direct calls deliberately bypass the
pool.

**Concrete fix:** add the transport-neutral route to the actual request path.
A compact shape is:

```python
@dataclass(frozen=True)
class ModelRoute:
    endpoint: str | None
    api_key_env: str | None

@dataclass
class ModelRequest:
    ...
    route: ModelRoute | None = None
```

`ModelSpec` should carry a non-optional `route` for active entries. Thread that
single value through
`orchestrator.run → enrich_one/call_pass1 → ModelRequest` and
`orchestrator.run → compile_source/compile_one → ModelRequest`. A route object
also avoids adding another pair of loose scalars to signatures that Task #118
will soon split by pass.

Add explicit forwarding tests at both Pass-1 and Pass-2 boundaries, matching
the existing tests that prevent `use_completion_tokens` and `extra_body` from
being dropped.

### 2. Important — fallback, `null`, the escape hatch, and Ollama need one explicit contract

**Evidence:** options doc lines 26–37; `common/call_model.py:88-123,207-215`;
`common/config/__init__.py:39-47,53-70`;
`orchestrator/kdb_orchestrate.py:1098-1108`.

`spec.endpoint or PROVIDER_DEFAULT_ENDPOINT[provider]` is not a safe precedence
rule. It treats three different states as two:

- field absent — use a provider default;
- field present with `null` — intentionally pass `base_url=None`, required for
  the standard OpenAI SDK endpoint;
- field present with a URL — use the per-model override.

The same omission affects Option 2: deleting all provider defaults breaks the
documented unknown-model + `--provider` escape hatch, direct `ModelRequest`
callers, and the retained provider routes that currently have no active pool
entry. Ollama-local additionally has an environment-overridable endpoint
(`OLLAMA_BASE_URL`) but no API secret; the OpenAI SDK receives the literal
dummy key `"ollama"`. A required non-empty `api_key_env: str` cannot represent
that behavior.

**Concrete fix:** distinguish **route presence** from the route's endpoint
value:

- active pool entries must contain `endpoint` and `api_key_env`;
- `endpoint` may be JSON `null`, and that value must reach `OpenAI` unchanged;
- `api_key_env` may be `null` only for an explicitly no-auth provider such as
  ollama-local;
- `ModelRequest.route is None` alone invokes a provider-default registry for
  the raw/direct compatibility path;
- that registry owns special defaults such as `OLLAMA_BASE_URL` and the
  adapter-required dummy key.

Do not advertise missing fields as dropped-entry compatibility. The archive is
human-only and never loaded (`common/model_pool.py:57-61`); future active
entries should fail early when their route is incomplete instead of silently
falling back.

Pin at least these cases: OpenAI explicit `endpoint=None`; DeepSeek explicit
URL; raw `--provider` fallback; Ollama-local environment endpoint + dummy key;
and malformed/missing route data.

### 3. Important — the cited Qwen precedent does not establish per-model endpoint variance

**Evidence:** options doc lines 20–22, 39–42, and 49–51;
`common/models_dropped.json:89-121`.

Both `qwen3.6-flash-us` and `qwen3.6-flash` are recorded with
`provider: "alibaba"` and therefore use the same current DashScope endpoint and
key source. They differ in API model/deployment ID, not in the route fields
under review. The stronger historical routing evidence is
`deepseek-v4-flash` via DeepSeek direct, Alibaba, and Ollama Cloud—but those
routes already have distinct provider identities, so a provider registry can
represent them.

This does not make per-model fields a bad choice: Joseph explicitly requested
them, and they preserve a useful future override seam. It does mean the
architecture should not be selected on a precedent the repository does not
contain.

**Concrete fix:** correct the evidence statement. Justify required per-model
routes as the chosen ownership/flexibility policy, and describe the historical
multi-provider DeepSeek entries as evidence that routing affects behavior—not
as proof of same-provider endpoint variance. State that there are currently
three active provider identities (`openai`, `gemini`, `deepseek`) across two
SDK transport families.

### 4. Important — `api_key_env` should be uniform across transports, not inert on native models

**Evidence:** options doc lines 28–31 and 44–47;
`common/call_model.py:86-93,139-168`.

Option 1 gives all four active entries routing fields but leaves native
handlers unchanged. That makes Gemini's `api_key_env` inert while
OpenAI-compatible calls use `os.getenv`; configuration and tests then have two
secret-resolution paths (`settings.gemini_api_key` versus a dynamic env lookup).
It also weakens the claim that each active entry's effective route is
config-driven.

**Concrete fix:** choose **environment-variable names**, not Settings attribute
names, but resolve them once at the final call boundary for every transport.
Pass the resolved key into `_call_anthropic`, `_call_gemini`, or
`_call_openai_compat`; never place the secret itself in `ModelSpec`,
`ModelRequest`, telemetry, or error context. Keeping the public env name in
JSON means a new key does not require a new `Settings` dataclass field, which
is the actual commonality benefit of this task.

Put the lookup helper in `common.config` (where `.env` loading already lives),
validate a non-empty env-var name at pool resolution, and make missing-key
errors identify the variable/model/provider without including the value.
Native endpoints may remain `null`; reject a non-null native endpoint until a
native handler explicitly supports overriding it.

### 5. Minor — the acceptance sketch covers only the happy-path active pool

**Evidence:** options doc lines 53–57;
`common/tests/test_call_model.py:252-320,433-467`;
`scripts/verify_structured_output_parity.py:51-70`.

The existing engine intentionally tests retained routes with no active pool
entry and supports direct `ModelRequest` callers. Those are exactly where a
config-driven rewrite is most likely to regress.

**Concrete fix:** expand acceptance to cover:

- load-time validation for field presence, types, empty strings, and the
  native-endpoint rule;
- both Pass-1 and Pass-2 forwarding of the resolved route;
- active OpenAI, Gemini, and DeepSeek effective routes;
- retained xAI, Alibaba, Z.AI, Anthropic, Ollama Cloud, and Ollama-local
  fallback routes;
- unknown provider and missing-key errors;
- raw `--provider` escape-hatch behavior;
- no secret values in exceptions or telemetry;
- unchanged `_THINKING_DISABLE_EXTRA_BODY` behavior and unchanged pricing
  resolution (both are orthogonal consumers of `provider`/`ModelSpec`);
- updates to the call-model/module contract, `.env.example`, provider reference,
  and North Star milestone entry at closure.

## Direct answers to Kimi's review questions

1. **Option choice:** Option 3 is not strictly better. Choose the layered fourth
   shape above: required per-model `ModelRoute` for active entries, with a
   provider registry only for route-less raw/direct compatibility calls.
2. **Key identifier:** choose `api_key_env`, resolved late and uniformly for all
   transports. Do not store Settings attribute names in user-owned JSON.
3. **Other mappings:** pricing remains per-model and is unaffected.
   `_THINKING_DISABLE_EXTRA_BODY` remains a verified provider-to-request-shape
   translation, not endpoint/auth routing, and should stay separate.
   `base_url=None`, the raw escape hatch, native-handler key resolution,
   `OLLAMA_BASE_URL`, and Ollama's dummy key all need explicit regression tests.

## Verification performed

- Read-only trace of the pool resolution, CLI escape hatch, both pass call
  chains, native handlers, OpenAI-compatible handler, provider settings,
  retained model archive, and current provider tests.
- Focused baseline:
  `.venv/bin/pytest -q common/tests/test_model_pool.py common/tests/test_call_model.py`
  → **61 passed**.
- The first run with system `pytest` could not collect because that interpreter
  lacks `google-genai`; the repository virtual environment passed cleanly.
- No production code or existing project artifact was modified by this review.
