# Task #121 — Config-Driven Provider Wiring Options Review (Codex R3)

**Date:** 2026-07-24  
**Reviewer:** Codex  
**Review target:** `docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-options.md` (v1.2)  
**Review basis:** Codex R2 review and Kimi's R2 review prompt (no separate R3 prompt was present)

## Verdict

**REVISE.**

v1.2 faithfully absorbs the substantive R2 findings. The xAI environment name
is corrected, all nine defaults are explicit, Ollama's endpoint is late-bound,
every effective route has a final validator, provider identity is separated
from transport dispatch, the whole active pool is validated, the shared type
has a neutral owner, and Settings-orphan handling is now explicit.

No architectural rethink is needed. One Important runtime rule is still not
expressible by the proposed validator as written, and Joseph's D5/D6 choices
remain explicitly unconfirmed. Resolve those items before promoting this
options document into a technical spec.

## Findings

### 1. Important — the final validator lacks the context needed to enforce the no-auth rule

**Evidence:** options v1.2 lines 52–55, 95–102, 104–121, and 130–140.

The route type contains only:

```text
(api_type, endpoint, api_key_env)
```

The validation rule says `api_key_env=None` is permitted **only** for the
route-less Class-B Ollama-local default; every explicit route and every active
pool route must supply a non-empty environment-variable name. But the
pseudocode invokes `validate(route)`. A `ModelRoute` alone cannot tell whether
it came from:

- an active pool entry;
- an explicit caller-fabricated route; or
- the trusted Ollama-local registry factory.

It also does not contain `provider`, which is needed to identify Ollama-local.
Consequently, a single `validate(route)` implementation must either reject the
legitimate registry default or accept `None` on fabricated/incorrect
OpenAI-compatible routes. The later handler-level dummy-key rule has the same
missing context.

**Concrete fix:** keep `ModelRoute` small, but make the branch policy explicit
at the call boundary:

```text
if req.route is not None:
    route = validate_route(
        req.route,
        provider=req.provider,
        allow_no_auth=False,
    )
else:
    route = provider_default(req.provider)  # unknown provider fails here
    route = validate_route(
        route,
        provider=req.provider,
        allow_no_auth=(req.provider == "ollama-local"),
    )

api_key = (
    "ollama"
    if allow_no_auth
    else resolve_required_env(route.api_key_env, model=req.model, provider=req.provider)
)
```

The boolean is local resolution context, not a persisted `route_origin` field.
Gate 1 should always use `allow_no_auth=False`, matching the current decision
that no active entry may be no-auth. Add negative pins for:

- explicit Ollama-local route with `api_key_env=None`;
- explicit non-Ollama route with `api_key_env=None`;
- active-pool entry with `api_key_env=None`;

and retain the positive route-less Ollama-local default pin.

If Joseph instead wants caller-declared no-auth routes, add an explicit
`auth_mode` to `ModelRoute` and validate it. Do not infer authentication policy
merely from a missing key name.

### 2. Important — D5 and D6 are still unresolved architecture decisions

**Evidence:** options v1.2 lines 27–42, 155–171; AGENTS.md Architecture and
Blueprint gates.

The document labels D1–D4 as locked but correctly labels D5 and D6
"Joseph confirmation pending":

- D5 changes `provider` from a closed code-level value set to an open data
  identity.
- D6 removes nine fields from the repository's documented `Settings` surface.

Both choices are well-supported and I recommend accepting them. They are still
material contract decisions, not editorial details. Without confirmation, the
spec author cannot know which public types/config fields to implement, and the
acceptance list currently assumes both outcomes as if already selected.

**Concrete fix:** Joseph explicitly accepts or rejects D5 and D6. If accepted,
move them into "Decisions locked" and retain the current acceptance tests. If
either is rejected, revise D3/extensibility or the Settings cleanup scope
before drafting the spec. Do not silently treat this review as Joseph's
ratification.

### 3. Minor — two statements still conflict with the open-provider policy

**Evidence:** options v1.2 lines 31–35, 106–119, and 163–166.

D4 currently says unqualified `"unknown provider → ModelConfigError"`, while
D5 and the final authority rules deliberately allow a new provider when it
arrives with an explicit valid route. Only a **route-less** unknown provider is
an error. The acceptance list already expresses the intended distinction.

**Concrete fix:** change D4 to:

> route-less provider absent from the Class-B registry →
> `ModelConfigError`; an explicit valid route may use any non-empty provider
> identity.

Use the same qualification everywhere "unknown provider" appears.

### 4. Minor — the shared type sketch should use the closed `ApiType`, not `str`

**Evidence:** options v1.2 lines 50–60 and 134–139.

The design now establishes a shared closed `ApiType`, but the `ModelRoute`
sketch still declares `api_type: str`. Runtime validation would catch an
unknown value, yet the type contract fails to communicate D3's central
boundary: provider is open; transport type is closed.

**Concrete fix:** write:

```python
ApiType = Literal["openai_compat", "anthropic", "gemini"]

@dataclass(frozen=True)
class ModelRoute:
    api_type: ApiType
    endpoint: str | None
    api_key_env: str | None
```

Also rename the line-44 heading from "The v1.1 design" to "The v1.2 design."

## R2 absorption audit

| R2 finding | v1.2 status |
|---|---|
| F1 — wrong xAI env name | **Absorbed:** `XAI_GROK_API_KEY`; all nine registry rows are enumerated and pinned. |
| F2 — direct routes bypass validation | **Mostly absorbed:** two validation gates and operational route-presence semantics are correct; the no-auth exception still needs Finding 1's context. |
| F3 — Ollama endpoint import-time freeze | **Absorbed:** Class-B registry is a call-time factory, with an after-import env mutation pin. |
| F4 — closed Provider defeats JSON-only provider addition | **Technically absorbed:** provider becomes an open identity; awaits Joseph's D5 confirmation. |
| F5 — validation timing/type ownership | **Absorbed:** whole-pool Gate 1, call-boundary Gate 2, exact field constraints, neutral module, and Settings-orphan policy are stated; D6 awaits confirmation. |

## Direct technical assessment

- **Authority:** explicit route and route-less registry default are now
  unambiguous; the registry is not a rescue path.
- **Dispatch:** `api_type` as sole transport selector is sound. `provider`
  remains a stable identity for thinking translation, pricing context,
  response echo, and telemetry.
- **Environment timing:** late `os.getenv` after `common.config` imports and
  loads `.env` is sound. Neither secrets nor the Ollama endpoint should be
  cached in a module-level concrete route.
- **Failure behavior:** D4's fail-hard posture matches the existing engine.
  The no-auth exception must be explicitly authorized rather than inferred
  from `None`.
- **Spec readiness:** ready after Finding 1 is encoded and Joseph resolves
  D5/D6. No further options round is required for the already-closed R1/R2
  architecture.

## Verification performed

- Reconciled each R2 finding against v1.2 line by line.
- Rechecked the current provider type, Settings consumers, pool-loading
  behavior, environment names, route-less direct callers, and retained
  provider tests.
- No production code or existing project artifact was modified by this review.
