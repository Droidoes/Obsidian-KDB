# Task #121 — Config-Driven Provider Wiring Options Review (Codex R2)

**Date:** 2026-07-24  
**Reviewer:** Codex  
**Review target:** `docs/superpowers/specs/2026-07-24-task121-config-driven-provider-wiring-options.md` (v1.1)  
**Review prompt:** `docs/superpowers/specs/2026-07-24-task121-codex-review-prompt-r2.md`

## Verdict

**REVISE.**

The R1 absorption is structurally faithful and materially better. The
`ModelRoute` carrier, explicit-route-versus-registry layering, corrected
routing evidence, environment-variable-name decision, uniform late secret
lookup, and expanded acceptance list all reflect the prior review.

Four contract issues still need resolution before this becomes a technical
spec. One is a concrete behavior regression (`XAI_API_KEY` is not this
repository's xAI variable); the others concern which boundary validates
caller-supplied routes, when the environment-backed Ollama endpoint resolves,
and whether a new provider of an existing `api_type` is actually JSON-only.

The selected architecture remains sound. This round does not reopen Joseph's
D1–D3 decisions.

## Findings

### 1. Important — the Class-B xAI registry entry names the wrong environment variable

**Evidence:** options v1.1 line 78; `common/config/__init__.py:56-57`;
`.env.example:14`; `docs/reference/model-provider-api-calls.md:175`;
`common/tests/test_call_model.py:278-289,447-450`.

The proposed registry uses `"XAI_API_KEY"`, while the repository's established
public configuration contract is `"XAI_GROK_API_KEY"`. Implementing the table
as written would break xAI direct calls and the retained-provider fallback
test despite a correctly configured environment.

**Concrete fix:** change the registry entry to:

```text
xai → (openai_compat, "https://api.x.ai/v1", "XAI_GROK_API_KEY")
```

In the spec, enumerate every registry row rather than leaving the middle as
`...`, and golden-pin each row against the current chain. That turns
"byte-identical fallback" into reviewable data and prevents another env-name
translation error.

### 2. Important — only pool routes have a stated validator; explicit routes from direct callers do not

**Evidence:** options v1.1 lines 47–66, 95–101, and 118–124;
`common/call_model.py:41-62,82-125`.

The document validates Class-A routes at pool resolution, but
`ModelRequest.route` is a public, caller-constructible value. A script or test
can supply an unknown `api_type`, an empty key name, a wrong endpoint type, or
a non-null native endpoint without passing through `resolve_models_json()`.
Python dataclass annotations do not enforce those constraints. Acceptance
mentions a "malformed route" error but does not assign that check to a runtime
boundary.

The Class-A/Class-B terminology also overstates what `call_model()` can know.
At that boundary the observable distinction is **explicit route present**
versus **route absent**; it cannot independently know whether the model ID was
once found in the pool. A future forwarding bug could drop an active route and
silently select the provider default. The proposed Pass-1/Pass-2 drop-guard
tests are the appropriate protection, but the text should not claim a stronger
runtime distinction than the request carries.

**Concrete fix:** define one final route-resolution function in the engine:

```text
effective_route =
    validate(req.route)                         if req.route is not None
    else validate(provider_default(req.provider))
```

Pool resolution should still validate early so malformed active data fails
before orchestration, but **every** effective route must pass the same
call-boundary validator before SDK construction. State the authority rules
explicitly:

- `api_type` alone selects the handler;
- `provider` remains the model/provider identity used by thinking translation,
  pricing context, responses, and telemetry;
- an explicit route is authoritative even if its `api_type` differs from the
  provider's Class-B default;
- the registry is consulted only when `route is None`;
- a route-less unknown provider fails before secret lookup or SDK creation.

No additional `route_origin` flag is necessary if the document adopts this
operational definition and retains the forwarding drop-guard tests.

### 3. Important — the registry shape cannot yet preserve late `OLLAMA_BASE_URL` resolution

**Evidence:** options v1.1 lines 71–93;
`common/config/__init__.py:32-34,45,64`;
`common/call_model.py:110-113`;
`common/tests/test_config.py:31-34`.

The table presents Ollama-local's endpoint as
`$OLLAMA_BASE_URL or default`, but `ModelRoute.endpoint` can hold only a
resolved string or `None`. If the provider registry is a module-level mapping
of concrete `ModelRoute` objects, the endpoint will be captured at import time.
Migrating tests from rebinding `settings` to `monkeypatch.setenv` will then not
change that cached route. It also creates different timing semantics from the
new API-key helper, which is explicitly late-bound.

There is no API-key timing problem if `common.config` performs `os.getenv` in a
function: importing the module loads `.env` first, and every later lookup sees
the current process environment. The unresolved hazard is specifically the
environment-backed **endpoint** in an otherwise static registry.

**Concrete fix:** make provider-default resolution a function/factory, or give
the internal default record a distinct `endpoint_env` field that is resolved
when `call_model()` chooses the route. Do not build Ollama's concrete endpoint
at module import. Pin a test that:

1. imports `common.call_model`;
2. then sets `OLLAMA_BASE_URL` with `monkeypatch.setenv`;
3. makes a route-less Ollama-local request; and
4. observes the new endpoint plus the literal dummy key `"ollama"`.

Keep active-pool `ModelRoute.endpoint` literal/authoritative; the dynamic
endpoint mechanism belongs only to the Class-B compatibility registry.

### 4. Important — “new provider of an existing type = pure JSON” conflicts with the closed `Provider` type

**Evidence:** options v1.1 lines 29–31, 42, 97, and 103–107;
`common/call_model.py:35-43`; `common/model_pool.py:39-43`.

D3 correctly decouples transport dispatch from provider identity, but the
current request contract still declares `provider` as a closed `Literal` of
the nine known values. Adding (for example) a new OpenAI-compatible provider
through `models.json` alone would violate that public type contract even
though its `api_type` needs no new handler. If implementation preserves the
Literal, the "pure JSON" extensibility claim is false and every new provider
still requires a code edit.

The remaining consumers do not require a closed provider enum:

- `_THINKING_DISABLE_EXTRA_BODY` is an optional mapping; an unmapped provider
  already means no injected parameter.
- pricing is carried by `ModelSpec`.
- response and telemetry provider fields are already strings.
- Class-B unknown-provider rejection comes from registry membership.

**Concrete fix:** choose and document one of these policies:

1. **Recommended:** make `provider` an opaque, validated non-empty `str` in
   `ModelRequest`/`ModelSpec`; keep only `ApiType` closed. An explicit valid
   route can then introduce a provider in JSON, while a route-less request
   still requires a known registry provider.
2. Retain `Provider = Literal[...]`, but retract "pure JSON" and list updating
   the Literal as part of adding a provider.

The first policy is the one consistent with Joseph's D3.

### 5. Minor — validation timing, exact field constraints, and shared-type ownership should be pinned before spec

**Evidence:** options v1.1 lines 35–49, 95–101, and 116–126;
`common/model_pool.py:57-71`.

Three implementation-shaping details remain implicit:

- "load-time validation" in acceptance and "pool-resolution time" in the
  design are not equivalent. Current `resolve_models_json()` inspects only the
  selected entry, so a malformed unselected active entry can remain latent.
- `endpoint` is said to be present/null, but its non-null constraints are not
  stated. At minimum it should be a non-empty string; authenticated remote
  routes should not silently accept an empty string.
- Both `ModelSpec` and `ModelRequest` need the same type, but its owning module
  is unnamed. Defining it in either engine or pool and importing in the other
  creates unnecessary semantic coupling.

**Concrete fix:** have the spec:

- validate the complete active pool once when `load_pool()` materializes it,
  while retaining final call-boundary validation from Finding 2;
- define `endpoint` as `null` or a non-empty string and `api_key_env` as a
  non-empty environment-variable name for authenticated routes;
- require non-empty `api_key_env` for all current active entries; keep
  `None` reserved for the Class-B Ollama-local no-auth default until an active
  no-auth model creates evidence for broadening the pool schema;
- place `ApiType` and `ModelRoute` in a small neutral module such as
  `common/model_route.py`, reused by the pool and engine;
- state whether the API-key fields made dead in `Settings` are removed in this
  task or intentionally retained as a compatibility surface.

## R1 absorption audit

| R1 finding | v1.1 status |
|---|---|
| F1 — missing carrier | **Absorbed:** `ModelRoute` is carried on `ModelSpec` and `ModelRequest`, with both-pass forwarding tests. |
| F2 — fallback/null/escape-hatch/Ollama | **Mostly absorbed:** authority layering and three-state endpoint semantics are correct; late Ollama endpoint resolution still needs Finding 3. |
| F3 — false Qwen precedent | **Absorbed:** evidence and rationale are now accurate. |
| F4 — split native secret resolution | **Absorbed:** all transports use the same late env-name lookup; final validation needs Finding 2. |
| F5 — narrow acceptance | **Absorbed:** the matrix is materially complete; exact registry rows and validation timing need Findings 1 and 5. |

## Direct answers to Kimi's R2 questions

1. **Carrier/layering:** the two authorities are conceptually clean. Define
   classes operationally by route presence and validate both explicit and
   default routes at the final boundary; otherwise fabricated direct routes
   bypass the stated contract.
2. **Dispatch on `api_type`:** sound and preferable. `api_type` should be the
   closed handler selector; `provider` should be an open identity string if
   "new provider = pure JSON" is a real requirement.
3. **Late `os.getenv`:** safe for secrets after `common.config` has loaded
   `.env`; it intentionally observes environment changes after import.
   `monkeypatch.setenv` is sufficient for key tests. Ollama's endpoint must use
   the same late-resolution discipline rather than a registry object frozen at
   import.
4. **Before spec:** fix the xAI env name, assign call-boundary validation,
   define late endpoint resolution, settle the open-provider type, and pin
   whole-pool validation/type ownership.

## Verification performed

- Re-traced the CLI pool/escape-hatch split, both `ModelRequest` construction
  sites, engine dispatch, native and OpenAI-compatible handlers, configuration
  loading behavior, retained-provider tests, and direct script caller.
- Reconciled all five R1 findings against v1.1 line by line.
- No production code or existing project artifact was modified by this review.
