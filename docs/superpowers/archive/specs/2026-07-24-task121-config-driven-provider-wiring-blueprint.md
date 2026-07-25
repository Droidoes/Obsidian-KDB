# Task #121 — Config-Driven Provider Wiring (blueprint v0.4)

**Date:** 2026-07-24 · **Status:** v0.4 — absorbs Codex blueprint R3 (2 Important + 1 Minor, doc-level). Codex R3: "No further architecture round is necessary after those edits." **D1–D8 all ratified. Next: P0 → Joseph's Proceed**
**Architecture:** `2026-07-24-task121-config-driven-provider-wiring-options.md` v1.4 (D1–D6 ratified)
**Reviews:** blueprint R1 → `…-blueprint-review-codex.md` · R2 → `…-blueprint-review-codex-v2.md` · R3 → `…-blueprint-review-codex-v3.md`

## Decisions ratified (Joseph, 2026-07-24)

- **D7 — timeout contract:** two knobs, honest semantics.
  `LLM_TIMEOUT_SECONDS` = **connect/write/pool** phases; value reconciled to **120** everywhere (helper default + `.env.example` seed + docs).
  `LLM_INACTIVITY_TIMEOUT_SECONDS` = **read-silence watchdog** — max seconds of socket silence on any single read before failing hard. Default **900s**. Name kept (renaming would silently orphan the existing var in seeded `.env` files).
  **Contract caveat (Codex R2 F2):** a read-silence watchdog is **not a total wall-clock deadline** — httpx applies `read` per socket read; a peer dripping bytes before each deadline can hold a call open indefinitely. What it kills is the realistic wedge: a dead peer that goes silent. Attempt **counts** are bounded (D8); total wall time is not. A true total-deadline watchdog is a separate architecture item if ever required — not this task.
- **D8 — retry budgets preserved, documented, pinned (re-confirmed by Joseph 2026-07-24 against the corrected matrix).** No retry behavior changes. One behavior-identical hardening: constructors pass `max_retries=2` **explicitly** — the SDK-internal retry budget for ONE logical API call (one `.create()` may issue up to 3 HTTP requests on retryable failures: connection errors, timeouts, 429, 5xx) — same behavior as today's SDK default, pinned against upstream drift.
- **P0 documentation gate:** `TASKS.md` #121 row + a North Star (`CODEBASE_OVERVIEW.md`) architecture entry land **before implementation**; Proceed requested only after P0.

## The corrected retry matrix (Codex R2 F1)

Pass-1's recovery loop catches **every** model-call exception (`pass1_caller.py:243-246`, `except Exception: continue`) and re-calls — transport errors included. Pass-2's content-recovery loop (`compiler.py:328`, `_MAX_COMPILE_ATTEMPTS=2`) can invoke the model twice — but only advances when a content attempt **returns a response**; hard model-call errors are terminal (`compiler.py:327`). Attempt budgets per source:

| Context | OpenAI / Anthropic | Gemini |
|---|---:|---:|
| One `call_model` invocation | up to 3 SDK attempts (explicit `max_retries=2`) | 1 (SDK `retry_options=None`) |
| One Pass-1 source (broad loop, `max_retries=1`) | 2 invocations × 3 = **6** | **2** invocations |
| One Pass-2 `call_model_with_retry` | 3 wrapper × 3 SDK = **9** | **1** — transport exception is terminal (not in `_RETRYABLE`, `call_model_retry.py:28-37`) |
| Full Pass-2 per source (content loop × wrapper) | up to 2 × 9 = **18** in a mixed transport/content sequence | up to **2**, only when a response returns but fails a retriable content gate |

Known gap, precisely: Gemini has no SDK-internal or wrapper transport retry, but Pass-1's broad loop still repeats a Gemini transport failure once. All counts pinned by test (see §7).

## 1. What changes, at a glance

| Layer | Today | After |
|---|---|---|
| Routing knowledge | 7-branch elif chain, hardcoded URLs + `settings.*` keys (`call_model.py:86-125`) | Pool entries carry `ModelRoute`; 9-row Class-B registry factory covers route-less calls |
| Transport selection | inferred from `provider` | declared `api_call_type` (`openai_compat`/`anthropic`/`gemini`) — the only closed value set |
| `provider` | closed `Literal[9]` | free-form informational identity, validated **canonical** (D5 + §2 rule) |
| Secret resolution | `settings.<provider>_api_key` (import-time singleton) | `os.getenv(route.api_key_env)` late at the call boundary, all transports (D2/D6) |
| `Settings` | 10-field frozen dataclass + singleton | **deleted**; `common/config` keeps the `.env` loader + gains late-bound helpers (D6) |
| Timeouts | one scalar `LLM_TIMEOUT_SECONDS` (seeded 120, unseeded fallback 300) on all httpx phases; unread `LLM_INACTIVITY_TIMEOUT_SECONDS=60` placeholder in `.env.example` | `LLM_TIMEOUT_SECONDS` (120) → connect/write/pool; `LLM_INACTIVITY_TIMEOUT_SECONDS` (900) → read-silence watchdog. Gemini scalar → 900s |

**Behavior-change statement:** *routing* behavior is byte-identical for every active run (pinned); *retry* behavior is byte-identical (D8 — explicit `max_retries=2` equals today's SDK default); *timeout* behavior intentionally changes (D7): read-silence ceiling 120s→900s on openai/anthropic transports, gemini scalar 120s→900s, the unread inactivity placeholder becomes live at 900, **and the unseeded-environment connect/pool/write fallback moves 300→120** (`Settings.from_env` defaulted 300 where no `.env` is found; the new helper default is 120 everywhere, matching the seeded value).

## 2. New module — `common/model_route.py`

Neutral home; `common` is the LEAF package — imports nothing internal.

```python
ApiCallType = Literal["openai_compat", "anthropic", "gemini"]  # CLOSED — new type = one handler + one value
API_CALL_TYPES: frozenset[str] = frozenset(get_args(ApiCallType))

class ModelConfigError(ValueError):
    """Missing/incorrect provider config (moved from call_model; re-exported there for compat)."""

@dataclass(frozen=True)
class ModelRoute:
    api_call_type: ApiCallType
    endpoint: str | None      # None = SDK-built-in URL (meaningful for openai_compat)
    api_key_env: str | None   # env-var NAME; None only via the trusted ollama-local registry default

def validate_provider_identity(provider: object) -> str:
    """Provider must be a str, non-empty, AND ALREADY CANONICAL — leading/trailing
    whitespace is REJECTED (provider != provider.strip()), never silently normalized:
    routing, thinking-translation lookup, response echo, and telemetry must see ONE
    identical string. Returns the original valid string. Runs FIRST at both gates."""

def validate_route(route: ModelRoute, *, provider: str, allow_no_auth: bool) -> ModelRoute:
    """The single route validator (Gate 2 core; Gate 1 wraps it — see §4).
    Raises ModelConfigError naming provider + the violated rule (never secrets)."""
```

`validate_route` checks, **in order** (Codex R3 F2 — wrong runtime types must surface as `ModelConfigError`, never leak a raw `TypeError`/`AttributeError`):

1. `route` is a `ModelRoute` instance — anything else rejects.
2. `api_call_type` is a **str** (before closed-set membership — an unhashable value like a list would otherwise raise `TypeError`), then ∈ `API_CALL_TYPES`.
3. `endpoint` is `None` or a **str** (int/list/object rejects); a string must be **non-empty and non-whitespace** (padded values reject — malformed config must not survive to an SDK URL parser).
4. `api_key_env` is `None` or a **str** (before auth policy); a string must be **non-empty and non-whitespace** (padded rejects — it feeds `os.getenv`).
5. Auth policy: `allow_no_auth=False` → `api_key_env` must be a valid string; `allow_no_auth=True` (only the ollama-local registry row) → `None` or a valid string. **The flag never disables type validation.**
6. Native types (`anthropic`, `gemini`): `endpoint` **must be None**.

Gate 1 wraps each malformed JSON type in `PoolError` naming the model id; Gate 2 raises `ModelConfigError` before any SDK constructor runs.

`ModelConfigError` moves here so `common/config` can raise it without an import cycle; `common/call_model.py` re-exports it — existing imports keep working.

## 3. `common/config/__init__.py` — rewritten, smaller

Keeps: `_find_dotenv()` + `load_dotenv(...)` at import (untouched semantics).
Deletes: `Settings` dataclass, `settings` singleton, `Settings.from_env()`.
Gains (late-bound `os.getenv` function calls — `monkeypatch.setenv`-friendly):

```python
def resolve_required_env(name: str, *, model: str, provider: str) -> str:
    """Missing/empty → ModelConfigError naming the env var + model + provider — NEVER the value."""

def llm_timeout_seconds() -> int:            # LLM_TIMEOUT_SECONDS, default 120 — introduced in P1
def llm_inactivity_timeout_seconds() -> int: # LLM_INACTIVITY_TIMEOUT_SECONDS, default 900 — introduced in P3
```

**Value validation:** both timeout getters fail hard on non-integer and non-positive values, naming the offending variable.

**Phase ownership (Codex R2 F5):** P1 introduces `llm_timeout_seconds()` and uses it as a like-for-like scalar replacement for the three `settings.llm_timeout_seconds` reads (`call_model.py:144,168,215`) — the **scalar constructor shape and the seeded 120 value are unchanged** in P1; the unseeded fallback intentionally moves 300→120 under D7 (§1 statement). P3 introduces `llm_inactivity_timeout_seconds()`, value validation, and the `httpx.Timeout` composition.

## 4. `common/model_pool.py` — pool carries the route

- `ModelSpec` gains `route: ModelRoute` (**non-optional**). `provider` stays `str` — stored **canonical** (Gate 1 rejects non-canonical via `validate_provider_identity`, so the stored value is the valid original).
- models.json entries gain three fields: `api_call_type`, `endpoint` (key present; `null` or URL string), `api_key_env`. The 4 active entries:

| id | api_call_type | endpoint | api_key_env |
|---|---|---|---|
| gpt-5.4-mini | openai_compat | `null` | `OPENAI_API_KEY` |
| gemini-3.6-flash | gemini | `null` | `GEMINI_API_KEY` |
| deepseek-v4-flash | openai_compat | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| deepseek-v4-pro | openai_compat | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |

- **Gate 1:** `load_pool()` validates the **whole pool** once at materialization. Each entry: `validate_provider_identity` → required route fields present → build `ModelRoute` → `validate_route(..., allow_no_auth=False)`; failure → `PoolError` naming the model id + cause. (`lru_cache`: exceptions not cached; tests `cache_clear` on swap.)
- `resolve_models_json` reads the pre-validated route.
- Three-state endpoint: **absent key** → Gate-1 `PoolError`; **explicit `null`** → `endpoint=None`; **string** → override. No `or DEFAULT` (D4).
- `_THINKING_DISABLE_EXTRA_BODY` untouched — its lookup uses the stored (canonical) provider.

## 5. `common/call_model.py` — engine rewrite

### 5.1 Request/response contract

- `ModelRequest` gains `route: ModelRoute | None = None`. `provider: str` (`Provider` Literal deleted — D5).
- `ModelResponse` unchanged.

### 5.2 Class-B registry — factory, not static data

```python
_PROVIDER_DEFAULTS: dict[str, Callable[[], ModelRoute]] = {
    "anthropic":    lambda: ModelRoute("anthropic", None, "ANTHROPIC_API_KEY"),
    "openai":       lambda: ModelRoute("openai_compat", None, "OPENAI_API_KEY"),
    "gemini":       lambda: ModelRoute("gemini", None, "GEMINI_API_KEY"),
    "xai":          lambda: ModelRoute("openai_compat", "https://api.x.ai/v1", "XAI_GROK_API_KEY"),
    "alibaba":      lambda: ModelRoute("openai_compat", "https://dashscope-us.aliyuncs.com/compatible-mode/v1", "QWEN_US_API_KEY"),
    "deepseek":     lambda: ModelRoute("openai_compat", "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "ollama-local": lambda: ModelRoute("openai_compat",
                                       os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                                       None),   # no-auth; dummy key below
    "ollama-cloud": lambda: ModelRoute("openai_compat", "https://ollama.com/v1", "OLLAMA_API_KEY"),
    "zai":          lambda: ModelRoute("openai_compat", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY"),
}

def provider_default(provider: str) -> ModelRoute:
    """Unknown provider → ModelConfigError (before secret lookup or SDK construction)."""
```

Per-request invocation → `OLLAMA_BASE_URL` resolves late. All 9 rows golden-pinned.

### 5.3 Final resolution + dispatch

```python
def call_model(req: ModelRequest) -> ModelResponse:
    provider = validate_provider_identity(req.provider)          # first, always
    if req.route is not None:
        route = validate_route(req.route, provider=provider, allow_no_auth=False)
        allow_no_auth = False
    else:
        route = validate_route(provider_default(provider), provider=provider,
                               allow_no_auth=(provider == "ollama-local"))
        allow_no_auth = provider == "ollama-local"
    api_key = "ollama" if allow_no_auth else resolve_required_env(
        route.api_key_env, model=req.model, provider=provider)

    if route.api_call_type == "openai_compat":
        ... _call_openai_compat(req, base_url=route.endpoint, api_key=api_key)
    elif route.api_call_type == "gemini":
        ... _call_gemini(req, api_key=api_key)
    elif route.api_call_type == "anthropic":
        ... _call_anthropic(req, api_key=api_key)
```

Authority rules: `api_call_type` alone selects the handler; explicit route authoritative even if its type differs from the provider's registry row; registry consulted only when `route is None`; no-auth never caller-declared.

### 5.4 Handlers

- `_call_openai_compat(req, *, base_url, api_key)` — signature unchanged.
- `_call_gemini(req, *, api_key)` / `_call_anthropic(req, *, api_key)` — key injected; bodies otherwise unchanged.

### 5.5 Timeouts (D7) and retry budgets (D8)

- openai_compat + anthropic clients (P3): `timeout=httpx.Timeout(connect=t, write=t, pool=t, read=inactivity)` — `t=120`, `inactivity=900`. P1 keeps passing the scalar `t` exactly as today.
- gemini `HttpOptions` (P3): `timeout=inactivity * 1000` (scalar-only API; also drives `X-Server-Timeout`). P1 keeps `t * 1000`.
- **Retry budgets (D8 — preserved + pinned):** constructors pass **`max_retries=2` explicitly** (behavior-identical to the SDK default; immune to upstream drift). The full call-path × transport matrix lives at the top of this document; the pins are in §7.
- **No total deadline (D7 caveat):** the read-silence watchdog kills silent peers; attempt **counts** are bounded, total wall time is not. Duration figures are **conditional estimates**, never bounds.
- **Dependency:** httpx direct import → added to **both** `pyproject.toml` and `requirements.txt` (P3).

## 6. Threading the route — every hop named

```
main (kdb_orchestrate.py:1083, spec.route | escape-hatch None)
  → run (kdb_orchestrate.py, route kwarg)
  → enrich_one (enrich.py:51) → call_pass1 (pass1_caller.py:104) → ModelRequest (:170)
main
  → run
  → compile_source (compiler.py:626) → compile_one (compiler.py:150) → ModelRequest (:357)
```

- `route: ModelRoute | None = None` keyword on **all five** — `run`, `enrich_one`, `call_pass1`, `compile_source`, `compile_one` — every existing direct caller stays source-compatible.
- `common/call_model_retry.py`: transparent (forwards the `ModelRequest` as-is).
- Pins: **positive CLI pin** (known pool id → `spec.route` reaches `run`); **orchestrator/intermediate forwarding pins** (the same route object reaches the leaf `ModelRequest` in *both* passes); **escape-hatch pin** (`route=None` survives to both leaves → registry path).
- #118 alignment: per-pass models will thread one route per pass through exactly these kwargs.

## 7. Test plan (TDD)

**New `common/tests/test_model_route.py`:** provider identity — non-string/empty/whitespace-only rejected; **leading/trailing-whitespace rejected (canonical rule)**; normal accepted. **Ordered runtime-type matrix (R3 F2):** non-`ModelRoute` object; non-str `api_call_type` (incl. unhashable list — no `TypeError` leak); unknown `api_call_type`; non-str `endpoint` (int/list/object); endpoint empty/whitespace-only/padded rejected; non-str `api_key_env`; empty/whitespace/padded key names rejected; `api_key_env=None` at `allow_no_auth=False` rejected / at `True` accepted (type validation still active under the flag); non-null native endpoint rejected; messages name provider + rule.

**`test_config.py` (rewrite):** dotenv loading; resolver success/missing/empty (message contains var+model+provider, not a sentinel secret); `llm_timeout_seconds` — default 120 + valid override (P1), invalid-string/zero/negative (P3); `llm_inactivity_timeout_seconds` — default 900 + full matrix (P3).

**`test_call_model.py` (migrate + extend):**
- `_use_settings` → `monkeypatch.setenv` throughout.
- **9 registry-row golden pins**; ollama late-endpoint pin (import → setenv → new endpoint + dummy key).
- Route-less unknown provider → `ModelConfigError` pre-SDK; empty/whitespace/padded `provider` → `ModelConfigError` (explicit route or not).
- Explicit-route authority: fabricated `"acme"` route dispatches (D5 zero-code-edits pin); differing-`api_call_type` honored; no-auth negatives (explicit `api_key_env=None` rejected, both provider classes).
- Runtime-type pins at Gate 2: non-`ModelRoute` route, wrong-typed fields → `ModelConfigError` before any SDK constructor.
- Missing key names var/model/provider, never the value.
- Timeout pins (P3): `httpx.Timeout(read=900, connect/write/pool=120)` default + override; gemini `900_000`.
- **Retry pins:** constructors pass `max_retries=2` (constructor kwargs observed).
- Unknown `api_call_type` on fabricated route → `ModelConfigError`.

**`common/tests/test_call_model_retry.py`:** `_RETRYABLE` membership unchanged; wrapper attempt cap (3) unchanged.

**`ingestion/tests/test_pass1_caller*.py`:** **Pass-1 repeats a model-call exception exactly once** (existing broad-loop behavior, explicitly pinned); content-attempt cap (`max_retries=1` → 2 invocations).

**`compiler/tests/test_compiler.py`:** **a Gemini transport exception is terminal in Pass-2** (no wrapper retry); `_MAX_COMPILE_ATTEMPTS=2` content cap.

**`test_model_pool.py`:** 4 active entries → `spec.route` byte-identical pins; Gate-1 rejection per rule incl. padded/blank provider and the malformed-JSON-type matrix (wrapped in `PoolError` naming the model id); `_THINKING_DISABLE_EXTRA_BODY` unchanged.

**Forwarding (per §6):** positive CLI pin, both-pass leaf forwarding pins, escape-hatch None pin.

**Parity script:** unchanged source; runs against any provider.

## 8. Implementation plan (P0 + 3 phases, each suite-green; commit gate = Joseph's approval per phase)

- **P0 — tracking docs.** `docs/TASKS.md` #121 row → ratified architecture + blueprint v0.4; `CODEBASE_OVERVIEW.md` gains the #121 entry (D1–D8). *No code.* Proceed requested only after P0 lands.
- **P1 — engine internals, routing behavior byte-identical.** `model_route.py`; `config` rewrite (incl. `llm_timeout_seconds()` as like-for-like scalar replacement — **scalar constructor shape and seeded 120 unchanged; unseeded fallback intentionally 300→120 under D7**); `call_model` rewrite (registry factory, provider identity, resolver, dispatch, injected native keys, **explicit `max_retries=2`**); test migrations + new engine/config/route tests. All callers exercise Class B → routing identical by construction. *Verification:* full suite green.
- **P2 — config-driven pool.** models.json fields on the 4 active entries; `model_pool` (`ModelSpec.route`, Gate 1); threading per §6 (all five hops); forwarding pins. *Verification:* full suite green; byte-identical-route pins.
- **P3 — timeout activation + docs.** `llm_inactivity_timeout_seconds()` + value validation + `httpx.Timeout` composition (openai/anthropic) and gemini scalar switch + tests; httpx in both manifests; `.env.example` placeholder **corrected/activated** (60→900, comments rewritten; existing `.env` files need a manual edit — called out in the changelog); `AGENTS.md:81` rewritten to the true semantics; `docs/reference/model-provider-api-calls.md` updated (incl. the D8 retry matrix); North Star milestone + `TASKS.md` closure. *Verification:* full suite green.

**Live smoke (optional, Joseph-gated):** one sandbox `kdb-orchestrate` run per active model post-P3 — requires Drive-sync pause.

## 9. Out of scope

- Total wall-clock per-call deadline / activity-proof watchdog — separate architecture item (D7 caveat).
- True first-byte / mid-stream split — needs streaming transport (D7).
- Retry-policy changes (wrapper-authoritative, Gemini retry ladder) — paid-call behavior (D8).
- Gemini via Google's OpenAI-compat shim — separate task with live parity verification.
- `auth_mode` / caller-declared no-auth — YAGNI.
- `_THINKING_DISABLE_EXTRA_BODY`, pricing, ctx-window guard, telemetry — pinned unchanged.
- Anthropic pool entries — provider retained, no active models.

## 10. Risks

- **Settings removal ripples:** grep-verified consumers are `call_model.py` + 2 test files only; a missed importer fails loudly at import.
- **Read-silence is not a total bound (accepted, D7):** a byte-dripping peer can hold a call open past any read ceiling; attempt **counts** are bounded, total wall time is not. A hard deadline returns to Architecture if ever required.
- **Longer silent-tolerance (conditional estimates, Codex R3 F1):** a wedged attempt now waits 900s (was 120s) before failing. All-silent terminal Pass-2 path ≈ 9 × 900s ≈ **2.25h** + backoff (the content loop cannot advance — `compiler.py:327`). The 18-attempt path requires a returned response: max silent composition = 8 silent + 1 response (first content attempt) + 9 silent (second) = **17 silent ≈ 4.25h** conditional, plus generation/backoff. Figures are estimates for attempts that each hit one uninterrupted silent read — never bounds.
- **Gate-1 strictness:** a malformed future entry fails the whole pool at first touch — intended (D4).
- **httpx direct-import:** mirrored in both manifests; `httpx.Timeout` API is ancient — no version floor.
