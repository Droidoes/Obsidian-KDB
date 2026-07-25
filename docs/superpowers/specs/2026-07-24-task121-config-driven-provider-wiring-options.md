# Task #121 — Config-Driven Provider Wiring (options v1.4)

**Date:** 2026-07-24 · **Status:** v1.4 — **D1–D6 all ratified by Joseph; Codex R1–R3 fully absorbed. SPEC-READY.**
**Filed by:** Joseph, 2026-07-24 — *"for each model we should add one field for openai endpoint and another one for api key name, just to use less hardcoding and improve commonality for the api calls."*
**Reviews:** Codex R1 → `…-options-review-codex.md` · R2 → `…-options-review-codex-v2.md` · R3 → `…-options-review-codex-v3.md` (R2 absorption audit: all 5 findings absorbed; no further options round needed for the closed R1/R2 architecture)

## Context

Provider wiring is currently a 7-branch `elif` chain in `common/call_model.py:86-122`:

```
anthropic → native SDK (settings.anthropic_api_key)          :140
openai    → openai SDK, base_url=None, settings.openai_api_key
gemini    → native google-genai SDK (settings.gemini_api_key) :164
xai       → openai SDK, https://api.x.ai/v1, settings.xai_api_key
alibaba   → openai SDK, https://dashscope-us.aliyuncs.com/compatible-mode/v1, settings.qwen_us_api_key
deepseek  → openai SDK, https://api.deepseek.com, settings.deepseek_api_key
ollama-local/cloud, zai → openai SDK, hardcoded URLs + settings keys
```

The pool (`common/model_pool.py::resolve_models_json` → `ModelSpec`) carries no routing fields today. Active pool (post-2026-07-24 pruning): `gpt-5.4-mini` (openai), `gemini-3.6-flash` (gemini-native), `deepseek-v4-flash` + `deepseek-v4-pro` (deepseek) — **three provider identities across two SDK transport families** (openai-compatible, gemini-native). Anthropic is retained but has no active entries (retired 2026-07-21). Dropped archive is human-only (code never reads it — `load_pool` docstring, `model_pool.py:57-61`).

**Goal (Joseph):** each models.json entry carries routing fields → less hardcoding, more commonality, per-model routing freedom.

**Evidence statement (corrected per Codex R1 F3):** there is **no** same-provider endpoint variance in repo history — `qwen3.6-flash` and `qwen3.6-flash-us` are both `provider: "alibaba"` (same endpoint, same key, different deployment IDs). The historical deepseek triple-route (`deepseek-v4-flash` direct / `:alibaba` / `:cloud` via ollama-cloud) shows the *same API model* reached through **distinct provider identities** — proof that routing affects behavior, not proof of same-provider variance. Per-model route fields are justified as the chosen ownership/flexibility policy (Joseph's explicit request + a future override seam), not by precedent.

## Decisions locked (Joseph, 2026-07-24)

- **D1 — layered fourth shape** (supersedes v1.0 Options 1–3; see "Options considered" below).
- **D2 — `api_key_env` holds an environment-variable NAME** (e.g. `"DEEPSEEK_API_KEY"`), resolved late; never a Settings attribute name, never the secret.
- **D3 — explicit `api_call_type` field** (Joseph's naming) declaring the call type: `"openai_compat"`, `"anthropic"`, `"gemini"`. The sole dispatch selector. Extensible: a new provider of an existing type is pure JSON; a new type is one handler + one enum value.
- **D4 — fail-hard config contract (Joseph's standing principle).** Missing or incorrect config fails the call loudly — no catch-all, no silent default, no rescue path. Concretely, at every layer:
  - pool resolution (Class A): absent/malformed route fields, unknown `api_call_type`, non-null native endpoint → `PoolError` before any SDK construction;
  - call boundary: missing/empty env var → `ModelConfigError` naming variable + model + provider (never the value); a **route-less** provider absent from the Class-B registry → `ModelConfigError` (an explicit valid route may use any non-empty provider identity — D5);
  - **no `or DEFAULT` fallbacks on route fields anywhere** — the Class-B registry is consulted only when `ModelRequest.route is None` (a deliberate caller choice: escape hatch / direct call), never as a rescue for a broken pool entry;
  - no try/except around config resolution that degrades to a default; SDK errors propagate (`call_model` docstring contract, unchanged).
  This matches today's engine behavior (missing key → `ModelConfigError` at `call_model.py:210-211`, `:140-141`, `:164-165`; unknown provider → `:124-125`) — D4 writes it down so the rewrite preserves it by construction.
- **D5 — `provider` is a free-form informational identity (Joseph, ratified 2026-07-24).** Open, validated non-empty `str` on `ModelRequest`/`ModelSpec`; routing authority lives entirely in `api_call_type`. Remaining functional roles (not routing): thinking-disable translation lookup (unmapped = safe no-op), pricing context, response echo, telemetry — **and the registry lookup key for route-less Class-B calls**: a call carrying its own valid route may use any provider name; a route-less call must name one of the 9 registry rows or fail hard (D4). (Codex R2 F4 — the closed `Provider = Literal[…]` would have falsified D3's "pure JSON" claim.)
- **D6 — `Settings` class removed entirely (Joseph, ratified 2026-07-24 — extended past Codex's orphan-removal proposal).** After env-name resolution, the class would hold one field (`llm_timeout_seconds`) — so the whole dataclass + singleton goes. What survives in `common/config`: (a) the **`.env` loader** (`_find_dotenv` + `load_dotenv`) — the bootstrap everything depends on, untouched; (b) late-bound env helpers — `resolve_required_env(name, *, model, provider)` (the secret resolver, Codex R1 F4) and `llm_timeout_seconds()` (replaces the three `settings.llm_timeout_seconds` reads at `call_model.py:144,168,215`; late-bound so `monkeypatch.setenv` works). `test_config.py` is rewritten around the helpers; the `_use_settings` mechanics in `test_call_model.py` migrate to `monkeypatch.setenv`. Grep-verified consumers of the class today: `call_model.py` + the two test files only. `.env` itself is unchanged — same variable names, same secrets.

## The v1.3 design

### ModelRoute — the end-to-end carrier (Codex F1)

`ModelSpec` fields die at the CLI boundary today: `kdb_orchestrate.py:1092-1097` unpacks the spec into loose scalars that flow through `run()` → `call_pass1` (`pass1_caller.py:170` builds the `ModelRequest`) and `compile_one` (`compiler.py:357` builds it). `call_model` only ever sees `ModelRequest`. Re-resolving the pool inside `call_model` by model string is unsound: aliases need not equal API model IDs, and multiple pool entries can share one API model string (`deepseek-v4-flash` active + `deepseek-v4-flash:alibaba` archived — same string, different routes). So the route must travel **on the request**:

```python
ApiCallType = Literal["openai_compat", "anthropic", "gemini"]  # CLOSED — new type = one handler + one value

@dataclass(frozen=True)
class ModelRoute:
    api_call_type: ApiCallType      # closed transport selector (provider stays an OPEN identity string — D5)
    endpoint: str | None   # None = SDK-built-in URL (meaningful for openai_compat)
    api_key_env: str | None  # env-var NAME; None only for the trusted ollama-local registry default
```

- `ModelSpec.route: ModelRoute` — **non-optional** for active pool entries.
- `ModelRequest.route: ModelRoute | None = None` — default None keeps direct callers (scripts, tests, escape hatch) source-compatible.
- **Module ownership (Codex R2 F5):** `ApiCallType` (the closed value set) + `ModelRoute` live in a small neutral module, `common/model_route.py`, reused by pool and engine — defining it in either of those and importing across would create needless semantic coupling. (`common` is the LEAF package; nothing new imports inward.)
- Threaded: CLI boundary (`resolve_models_json`) → `run()` → `call_pass1` / `compile_one` → `ModelRequest`. One object instead of another pair of loose scalars in signatures Task #118 will soon split per-pass.
- Forwarding tests at both Pass-1 and Pass-2 boundaries, matching the existing drop-guard tests for `use_completion_tokens` / `extra_body`.

### Two call classes, one authority each (the "layering")

```
Class A — model id IS in the active pool:
  the entry's route is REQUIRED and authoritative. Validated at pool-resolution
  time; incomplete/malformed route → PoolError before any SDK construction.
  The provider registry is NEVER consulted for Class A.

Class B — no pool entry (raw --provider escape hatch, direct ModelRequest):
  a provider-default registry in code answers: provider → {api_call_type, endpoint,
  api_key_env}. This is its ONLY job — compatibility boundary, not a second
  authority. Preserves today's behavior for verify_structured_output_parity.py,
  ad-hoc scripts, and the retained providers with no active entries.

Neither resolves → ModelConfigError naming model/provider/env-var — never the secret.
```

Why not v1.0 Option 1's fallback: `spec.endpoint or DEFAULT` collapses three states into two. The contract distinguishes **absent** (load error — incomplete route), **`null`** (explicit: use the SDK's built-in URL — OpenAI needs exactly `base_url=None`), and **URL** (explicit override).

### Provider registry shape (Class B only)

Lives in `common/call_model.py` (it *is* the engine's routing knowledge — the elif chain's content, formalized as data). **All nine rows enumerated** (Codex R2 F1 — no `...`; each row golden-pinned by test against today's chain):

```
provider     → (api_call_type, endpoint, api_key_env)
anthropic    → (anthropic, None, "ANTHROPIC_API_KEY")
openai       → (openai_compat, None, "OPENAI_API_KEY")
gemini       → (gemini, None, "GEMINI_API_KEY")
xai          → (openai_compat, "https://api.x.ai/v1", "XAI_GROK_API_KEY")   # vendor+product name — config/__init__.py:56-57, .env.example:14
alibaba      → (openai_compat, "https://dashscope-us.aliyuncs.com/compatible-mode/v1", "QWEN_US_API_KEY")
deepseek     → (openai_compat, "https://api.deepseek.com", "DEEPSEEK_API_KEY")
ollama-local → (openai_compat, <resolved LATE from $OLLAMA_BASE_URL, default http://localhost:11434/v1>, None)  # no-auth: dummy key "ollama"
ollama-cloud → (openai_compat, "https://ollama.com/v1", "OLLAMA_API_KEY")
zai          → (openai_compat, "https://api.z.ai/api/paas/v4", "ZAI_API_KEY")
```

Special cases the registry owns: `OLLAMA_BASE_URL` env-overridable endpoint (`common/config/__init__.py:64`) and the adapter-required literal dummy key `"ollama"` (`call_model.py:112`). A required non-empty `api_key_env` cannot express no-auth — hence `api_key_env: None` + handler-level dummy.

**Late endpoint resolution (Codex R2 F3):** the registry is **not** a module-level mapping of concrete routes — `settings = Settings.from_env()` is a frozen import-time singleton (`config/__init__.py:74`), so a static registry would freeze `OLLAMA_BASE_URL` at import and defeat `monkeypatch.setenv`. Registry access is a **factory function** resolved when `call_model` chooses the route (same late-binding discipline as the key helper). Active-pool `ModelRoute.endpoint` stays literal/authoritative; the dynamic mechanism belongs only to the Class-B registry. Pinned test: import `common.call_model` → `monkeypatch.setenv("OLLAMA_BASE_URL", …)` → route-less ollama-local request → observes the new endpoint + dummy key `"ollama"`.

### Final call-boundary resolution + validation (Codex R2 F2)

`ModelRequest.route` is public and caller-constructible — dataclass annotations enforce nothing, and `call_model` cannot know whether a model id was ever in the pool. The operational distinction at the engine boundary is **route present vs route absent**, nothing stronger. One final resolution function in the engine, validating **every** effective route before SDK construction (Codex R3 F1: the validator needs resolution **context** — a bare `validate(route)` cannot tell the trusted ollama-local registry default, where `api_key_env=None` is legitimate, from a fabricated/incorrect explicit route, where it is not):

```python
if req.route is not None:
    # Explicit routes are ALWAYS authenticated — no-auth is never caller-declared.
    route = validate_route(req.route, provider=req.provider, allow_no_auth=False)
else:
    # Unknown provider fails inside provider_default (before secret lookup/SDK).
    route = validate_route(provider_default(req.provider), provider=req.provider,
                           allow_no_auth=(req.provider == "ollama-local"))

api_key = ("ollama" if allow_no_auth
           else resolve_required_env(route.api_key_env, model=req.model, provider=req.provider))
```

`allow_no_auth` is **local resolution context, not a persisted `route_origin` field** — `ModelRoute` stays small and origin-free. No-auth is authorized only for the trusted ollama-local registry default; Gate 1 (pool validation) always uses `allow_no_auth=False` — no active entry may be no-auth. *Considered and rejected:* an `auth_mode` field on `ModelRoute` for caller-declared no-auth — speculative (no active no-auth model exists); if that need ever materializes, add it explicitly rather than inferring auth policy from a missing key name.

Authority rules:

- `api_call_type` alone selects the handler;
- `provider` remains the model/provider **identity** for thinking-param translation, pricing context, responses, telemetry — never a routing authority;
- an explicit route is authoritative **even if its `api_call_type` differs** from the provider's registry default;
- the registry is consulted only when `route is None` — never as a rescue for a broken pool entry (D4);
- a route-less unknown provider fails before secret lookup or SDK creation.

Pool resolution still validates early (malformed active data fails before orchestration), but that is a *second, earlier* gate — not a substitute for the call-boundary validator. No `route_origin` flag: the operational definition + the Pass-1/Pass-2 forwarding drop-guard tests carry the protection.

### Uniform late key resolution (Codex F4)

- The env-var **name** is resolved to a key **once, at the final call boundary, for every transport** — the resolved value is passed into `_call_openai_compat` / `_call_gemini` / `_call_anthropic`. Today the native handlers read `settings.*` directly (`call_model.py:164`, `:140`); leaving that in place would make Gemini's `api_key_env` inert and split secret resolution into two paths.
- Lookup helper lives in `common.config` (where `.env` loading already lives). Missing/empty var → `ModelConfigError` identifying variable + model + provider, **never the value**.
- The secret never appears in `ModelSpec`, `ModelRequest`, telemetry, or error context.
- Test mechanics note: existing call-model tests monkeypatch Settings attributes (`_use_settings`); they migrate to `monkeypatch.setenv` on the env-var names. Behavior pinned, mechanics updated.

### Validation contract (two gates — Codex R2 F2/F5)

**Gate 1 — whole-pool validation at `load_pool()`:** `resolve_models_json()` inspects only the *selected* entry, so validating there leaves malformed unselected entries latent. The complete active pool is validated once when `load_pool()` materializes it (fail-fast at first touch, `PoolError` naming the entry), plus the final call-boundary validator above on every effective route.

Rules (both gates):

- `api_call_type` present and one of the closed `ApiCallType` values; unknown → error.
- `endpoint` key **present**; value is JSON `null` **or a non-empty string** (empty string is malformed, not "default").
- `api_key_env` present, **non-empty** env-var name for every authenticated route. `None` is reserved for the Class-B ollama-local no-auth default — no active entry may use it until a real no-auth model creates evidence for broadening the pool schema.
- **Native types (`anthropic`, `gemini`): `endpoint` must be `null`** — reject a non-null native endpoint until that handler explicitly supports overriding it.
- The 4 active entries get routes byte-identical in effect to today's hardcoded wiring (zero behavior change, pinned by test).

### Out of scope (unchanged consumers of provider/ModelSpec)

- `_THINKING_DISABLE_EXTRA_BODY` (`model_pool.py:22-28`) — a verified provider→request-shape translation, not routing.
- Pricing resolution, ctx-window guard, telemetry identity.
- Gemini via Google's OpenAI-compat shim (would make the single-path unification total) — a transport change on the best-performing model; needs live parity verification; separate future task.

## Options considered (record)

- **v1.0 Option 1** (per-entry fields + provider-default fallback) — superseded: fallback conflates absent vs explicit null; route had no carrier to `call_model`.
- **v1.0 Option 2** (required fields, defaults deleted) — rejected: breaks the `--provider` escape hatch, direct `ModelRequest` callers, and retained no-active-entry providers.
- **v1.0 Option 3** (provider registry only) — rejected as the *sole* mechanism (loses per-model seam), **retained as the Class-B compatibility boundary** in the layered shape.
- **Codex R1's fourth shape** — **adopted**: required per-model `ModelRoute` for active entries; registry strictly for route-less raw/direct calls.

## Acceptance (v1.2 — expanded per Codex F5 + R2)

- **Gate 1:** whole-pool validation at `load_pool()` — a malformed *unselected* entry fails at first pool touch; per-rule pins (field presence, types, empty strings, unknown `api_call_type`, native-endpoint rule).
- **Gate 2:** call-boundary validator runs on **every** effective route, including fabricated caller-supplied routes (unknown `api_call_type`, empty key name, wrong endpoint type, non-null native endpoint → error before SDK construction).
- Forwarding: route survives to `ModelRequest` at **both** Pass-1 and Pass-2 boundaries (drop-guard tests).
- Effective routes byte-identical to today for all 4 active entries (pinning test per entry: api_call_type + endpoint + resolved key source).
- **All 9 registry rows golden-pinned** against today's chain (Codex R2 F1 — the `XAI_GROK_API_KEY` class of error becomes unrepresentable).
- Ollama-local late-endpoint pin: import → `monkeypatch.setenv("OLLAMA_BASE_URL", …)` → route-less request observes the new endpoint + dummy key `"ollama"`.
- No-auth authorization pins (R3 F1): explicit ollama-local route with `api_key_env=None` → rejected; explicit non-ollama route with `api_key_env=None` → rejected; active-pool entry with `api_key_env=None` → rejected at Gate 1; route-less ollama-local default → positive pin (dummy key `"ollama"`).
- Open-provider pin (D5): a new openai_compat provider introduced via JSON only — no code edit — resolves and dispatches; route-less unknown provider fails.
- Error paths: unknown provider, missing key (names var, not value), malformed route.
- Fail-hard by construction (D4): no `or DEFAULT` on route fields (grep-check in spec), no try/except around config resolution, registry consulted only when `route is None`.
- Escape hatch (`--provider` + unknown model id) behaves exactly as today.
- No secret values in exceptions or telemetry.
- `_THINKING_DISABLE_EXTRA_BODY` behavior and pricing resolution unchanged (orthogonal consumers pinned).
- Settings removal (D6): `Settings` class + singleton deleted; `common/config` keeps the `.env` loader and gains late-bound helpers (`resolve_required_env`, `llm_timeout_seconds()`); `test_config.py` rewritten; `_use_settings` mechanics migrated to `monkeypatch.setenv`.
- Docs at closure: call-model/module contract, `.env.example`, provider reference, AGENTS.md env section, North Star milestone entry.
- Full suite green; no behavior change to any active run.
