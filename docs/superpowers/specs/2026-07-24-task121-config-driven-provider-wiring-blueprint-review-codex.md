# Task #121 — Config-Driven Provider Wiring Blueprint Review (Codex R1)

**Date:** 2026-07-24  
**Reviewer:** Codex  
**Review target:** `docs/superpowers/specs/2026-07-24-task121-config-driven-provider-wiring-blueprint.md` (v0.1)  
**Architecture basis:** options v1.4 (D1–D6 ratified; Codex options R1–R3 absorbed)

## Verdict

**REVISE.**

The routing half of the blueprint is nearly implementation-ready. It faithfully
translates the ratified architecture into a neutral `ModelRoute`, two
validation gates, a Class-B factory, uniform late secret resolution, native-key
injection, whole-pool validation, both-pass forwarding, and a strong TDD
matrix.

The new timeout scope is not yet blueprint-ready. The proposed `httpx.Timeout`
mapping cannot implement the documented first-byte-versus-mid-stream split on
the current non-streaming engine, the configured values conflict with the
repository's existing `.env.example`, and the retry-budget description is
incorrect for all three SDK families. Those are behavior and architecture
questions, not implementation details.

One routing-contract omission also remains: D5 says provider identity is a
validated non-empty string, but neither gate nor the tests validate it.

## Findings

### 1. Critical — the timeout mapping cannot implement the documented two-phase semantics

**Evidence:** blueprint lines 5, 15–18, 144–149, 177, 190, and 206;
`AGENTS.md:81`; `common/call_model.py:19,139-215`;
installed `httpcore/_sync/http11.py:196-218`;
installed `google/genai/types.py:2403-2405` and
`google/genai/_api_client.py:223-233,1310-1323,1373-1380`.

The repository documents:

```text
LLM_TIMEOUT_SECONDS            = first-byte patience
LLM_INACTIVITY_TIMEOUT_SECONDS = silence after the first chunk
```

The blueprint instead constructs:

```python
httpx.Timeout(connect=t, write=t, pool=t, read=inactivity)
```

An HTTPX `read` timeout is applied to **every** network read, including the
read that waits for the response headers/first response bytes. It is not a
"post-first-chunk only" timer. Because this engine deliberately uses
non-streaming SDK calls, `call_model()` has no first-chunk event at which it can
switch from one timeout to another.

Consequences:

- OpenAI-compatible and Anthropic calls would wait `inactivity`—not `t`—for
  the first response byte. `LLM_TIMEOUT_SECONDS` would govern connection
  acquisition/write/pool phases, not first-byte patience.
- Gemini's `HttpOptions.timeout` is documented by the installed SDK as a
  request timeout in milliseconds. The SDK converts it to a scalar HTTPX
  timeout and also sends `X-Server-Timeout`; it cannot express separate
  connect/read or first-byte/inactivity phases.
- The blueprint therefore does **not** make `AGENTS.md:81` true, and the
  timeout portion is not "zero behavior change."

**Concrete fix:** return this new scope to Architecture and choose one of three
honest contracts:

1. **Single read-silence ceiling (smallest change):**
   `LLM_INACTIVITY_TIMEOUT_SECONDS` controls HTTPX read timeout, explicitly
   including the initial response wait; `LLM_TIMEOUT_SECONDS` is renamed or
   redocumented as connect/write/pool timeout. Gemini uses the scalar
   request/server timeout. This meets the "never hang forever" goal but changes
   the current first-byte meaning.
2. **True first-byte + post-first-byte inactivity:** carve this into a separate
   transport/streaming design. It requires an observable response-start/chunk
   boundary (streaming or a custom transport/watchdog), not just an
   `httpx.Timeout` constructor.
3. **One request/read timeout:** retain a single documented ceiling and remove
   the unsupported two-phase claim.

Joseph must select and ratify the timeout contract. My lean is Option 1 if the
business requirement is simply a generous, bounded backstop; otherwise carve
Option 2 out so the small routing task stays small.

### 2. Important — the proposed 1800-second default is overridden by an existing 60-second sample config

**Evidence:** blueprint lines 5, 16, 62–66, 167, and 190;
`.env.example:18-22`; `setup.sh:40-49`.

The blueprint says the inactivity knob does not exist, defaults to 1800
seconds, and will be added to `.env.example`. In fact `.env.example` already
contains:

```text
LLM_TIMEOUT_SECONDS=120
LLM_INACTIVITY_TIMEOUT_SECONDS=60
```

`setup.sh` copies that file to `.env` for a new clone. The helper's 1800-second
default is therefore bypassed in the standard setup path, and existing users
with the seeded value will continue to get 60 seconds. A nominal default of
1800 does not produce the stated large ceiling.

This also makes blueprint line 18's unqualified "Zero behavior change for every
active run" false: routing is intended to be behavior-identical, but P3
deliberately changes timeout behavior.

**Concrete fix:** after Finding 1's contract is chosen:

- reconcile the helper default, `.env.example`, AGENTS.md, and provider
  reference to one value and one meaning;
- if 1800 is selected, change the existing sample from 60 to 1800 and document
  that existing `.env` files require a manual value change (`setup.sh` does not
  overwrite them);
- say **routing behavior is byte-identical** while timeout behavior is an
  intentional, separately accepted change;
- change P3 wording from "`.env.example` gains the knob" to "the existing
  placeholder is corrected/activated."

### 3. Important — timeout retry behavior is neither uniform nor described correctly

**Evidence:** blueprint lines 146–148, 177, 188–192;
`common/call_model_retry.py:27-37,57-81`;
installed `openai/_constants.py:8-10`;
installed `anthropic/_constants.py:8-10`;
installed `google/genai/_api_client.py:502-553,853-856,1386-1404`.

The statement "`call_model_retry` then applies its own ladder" is incomplete:

- OpenAI and Anthropic clients default to **two internal retries**. The outer
  `call_model_with_retry` also permits two retries, so a terminal timeout can
  consume up to 3 × 3 = **nine HTTP attempts**. At a 1800-second read ceiling,
  one source can occupy roughly 4.5 hours before backoff/overhead.
- The installed Google GenAI client performs no retry when
  `HttpOptions.retry_options` is `None`.
- The outer retry wrapper catches only Anthropic and OpenAI exception classes;
  it does not catch Google GenAI errors or a raw `httpx.TimeoutException`.
  A Gemini timeout therefore does not take the outer ladder.

All paths are bounded, but they have materially different budgets. The
blueprint currently implies common behavior that does not exist.

**Concrete fix:** explicitly choose and test one retry policy:

1. Preserve today's SDK-specific retry behavior and document the per-transport
   worst-case timeout budget; correct the Gemini statement.
2. Disable SDK-internal retries (`max_retries=0`) and make the shared outer
   wrapper authoritative, adding a verified Gemini timeout/error taxonomy.
3. Preserve OpenAI/Anthropic behavior but add a separately designed Gemini
   retry path.

Options 2 and 3 change retry telemetry and paid-call behavior, so they require
architecture approval. The smallest scope is Option 1 plus constructor and
exception-path tests that pin the actual budgets.

### 4. Important — D5's non-empty provider invariant is absent from both validation gates

**Evidence:** options v1.4 lines 31, 34, and 38;
blueprint lines 20–49, 68–83, 104–137, 163–180.

D5 ratifies `provider` as an open **validated non-empty string**. The blueprint
correctly removes the closed Literal, but `validate_route()` validates only
route fields. Gate 1 does not list provider validation, and Gate 2 would accept
an explicit valid route whose request provider is `""`, whitespace, or a
non-string runtime value. That creates blank/invalid response and telemetry
identity and weakens the new-provider contract.

**Concrete fix:**

- Add a shared `validate_provider_identity(provider)` check before either
  registry lookup or explicit-route validation.
- Gate 1 validates every pool entry's provider as a non-empty,
  non-whitespace string and wraps failure in `PoolError` naming the model ID.
- Gate 2 applies the same rule to every `ModelRequest`, including explicit
  routes.
- Add pool and fabricated-request tests for missing, non-string, empty, and
  whitespace-only provider values, plus the positive `"acme"` open-provider
  pin.

### 5. Important — the North Star and task ledger do not reflect the claimed architecture state

**Evidence:** blueprint lines 3–5 and 186–190; `docs/TASKS.md:47`;
absence of Task #121/config-driven routing from `docs/CODEBASE_OVERVIEW.md`;
AGENTS.md Phase-1 North-Star gate.

The blueprint correctly cites options v1.4 as ratified, but the canonical
tracking artifacts still say:

- Task #121 is `proposed`;
- the ledger describes the superseded v1.0 recommendation and says Codex
  options review is pending;
- the North Star has no ratified Task #121 architecture entry.

The blueprint defers both documents to closure, but repository policy requires
the selected architecture in the North Star **before leaving Architecture**,
not only after implementation.

**Concrete fix:** add a P0 documentation gate before implementation:

- update `docs/TASKS.md` to the ratified v1.4 layered architecture and blueprint
  status;
- add a concise pre-implementation Task #121 architecture entry to
  `docs/CODEBASE_OVERVIEW.md`, including the final timeout decision if it stays
  in this task;
- reserve the closure edit for implementation outcome/test evidence.

Do not request `Proceed` until this gate and the timeout architecture decision
are complete.

### 6. Minor — dependency mirroring and timeout-value validation are missing from acceptance

**Evidence:** blueprint lines 62–66, 149, 167, 177, 190, and 204;
`pyproject.toml:8-20`; `requirements.txt:1-8`.

The blueprint adds HTTPX only to `pyproject.toml`, while `requirements.txt`
explicitly requires dependency changes to be mirrored. It also tests timeout
defaults and valid overrides but not malformed, zero, or negative values.
HTTPX accepts zero/negative values into its `Timeout` object; failure can then
surface later and less clearly at I/O time.

**Concrete fix:**

- add `httpx` to both `pyproject.toml` and `requirements.txt`;
- make both timeout helpers fail hard on non-integer and non-positive values
  with a config error naming the offending variable but not unrelated env
  values;
- add invalid-string, zero, and negative tests for both knobs;
- pin the direct dependency in the packaging/bootstrap verification.

## Positive assessment of the routing design

Subject to Finding 4, these parts are ready:

- `ApiCallType` is the only closed routing selector; provider remains an open
  identity.
- `ModelRoute` has a neutral, leaf-safe module and one validator.
- Explicit routes never fall back; route-less calls use the nine-row
  compatibility factory only.
- Ollama no-auth is locally authorized and cannot be caller-declared.
- Secrets resolve at the final boundary and never enter requests, telemetry,
  or errors.
- Native handlers receive injected keys without transport changes.
- Whole-pool and call-boundary validation compose correctly.
- Both-pass route threading and drop-guard tests are proportionate.
- P1 → P2 sequencing gives a clean Class-B compatibility checkpoint before
  active pool routes switch over.

## Recommended next blueprint revision

1. Keep §§2–7 routing design, adding provider-identity validation.
2. Add P0 North-Star/task-ledger synchronization.
3. Either:
   - carve the timeout scope into its own options task; or
   - add a short timeout-options decision section resolving Findings 1–3,
     then fold the selected contract into P3.
4. Reconcile `.env.example`, dependency mirrors, retry budgets, and failure
   tests with that decision.

## Verification performed

- Reconciled blueprint v0.1 with options v1.4 and all prior Codex findings.
- Traced both live request paths, route threading sites, retry wrapper,
  Settings consumers, task ledger, North Star, bootstrap config, and dependency
  manifests.
- Inspected installed runtime contracts:
  HTTPX 0.28.1, OpenAI 2.38.0, Anthropic 0.104.0, and Google GenAI 2.8.0.
- No production code or existing project artifact was modified by this review.
