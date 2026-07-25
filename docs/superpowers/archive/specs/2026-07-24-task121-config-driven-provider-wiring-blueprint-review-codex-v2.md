# Task #121 — Config-Driven Provider Wiring Blueprint Review (Codex R2)

**Date:** 2026-07-24  
**Reviewer:** Codex  
**Review target:** `docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-blueprint.md` (v0.2)  
**Architecture basis:** options v1.4 (D1–D6 ratified) plus blueprint decisions D7/D8  
**Prior review:** `2026-07-24-task121-config-driven-provider-wiring-blueprint-review-codex.md` (R1)

## Verdict

**REVISE.**

v0.2 absorbs almost all of R1 cleanly. The timeout knobs now have honest
phase meanings; the sample configuration, dependency mirrors, invalid-value
tests, provider validation, P0 documentation gate, and routing-versus-timeout
behavior statement are all materially improved. The routing architecture
itself remains sound.

One load-bearing retry claim is still incorrect: Pass-1's existing recovery
loop catches every model-call exception and calls `call_model()` again. Gemini
therefore has a Pass-1 retry, and OpenAI/Anthropic can compound their SDK
retries with two Pass-1 calls. D8 was ratified from an incomplete attempt
budget and should be re-confirmed against the corrected matrix.

The blueprint also treats a read-silence timeout as a total wall-clock bound,
which HTTPX does not provide, and leaves small but consequential ambiguities in
provider normalization and the full route carrier chain.

## Findings

### 1. Critical — D8's retry matrix omits Pass-1's broad exception retry

**Evidence:** blueprint lines 12, 164, 195, 216, and 225–226;
`ingestion/enrich/pass1_caller.py:169-170,241-246`;
`ingestion/tests/test_pass1_caller.py:154-166`;
`ingestion/tests/test_pass1_caller_robustness.py:231-253`;
`common/call_model_retry.py:27-37,57-81`;
`compiler/compiler.py:327-328,356-386`.

The blueprint says:

```text
Gemini: 1 attempt, no retry at any level.
Pass-1 ... retries schema failures, not transport.
```

The current Pass-1 loop does the opposite of the second sentence:

```python
for attempt in range(1, max_retries + 2):
    try:
        resp = call_model(req)
        ...
    except (json.JSONDecodeError, ValueError):
        continue
    except Exception:
        continue
```

With the default `max_retries=1`, any exception from `call_model`—transport,
authentication, config, or otherwise—is caught and the entire call is made
again. This behavior is explicitly pinned by the existing tests.

The current maximum call/HTTP-attempt shape is:

| Context | OpenAI / Anthropic | Gemini |
|---|---:|---:|
| Direct `call_model` invocation | up to 3 eligible SDK attempts | 1 |
| One Pass-1 source | up to 2 `call_model` invocations × 3 SDK attempts = **6** | up to **2** calls |
| One Pass-2 `call_model_with_retry` invocation | up to 3 wrapper calls × 3 SDK attempts = **9** | **1** on a transport exception |
| Full Pass-2 content-recovery loop | up to 2 model invocations × 9 = **18** in a mixed transport-recovery/content-rejection sequence | up to **2** only when a response returns but fails a retriable content gate; a transport exception is terminal |

The 18-attempt case is not eighteen consecutive terminal timeouts: a model
invocation must eventually return a response for the content-recovery loop to
advance. It is nevertheless the correct per-source upper attempt count under
the unchanged nested loops.

**Concrete fix:**

1. Replace D8's global provider-only statement with a **call-path × transport**
   matrix.
2. Re-record the known gap precisely: Gemini lacks SDK and
   `call_model_with_retry` transport retries, but Pass-1's broad recovery loop
   still repeats a Gemini transport failure once.
3. Add pins for:
   - Pass-1 repeating a model-call exception exactly once;
   - Pass-2 treating a Gemini transport exception as terminal;
   - the two content-attempt caps in Pass-1 and Pass-2;
   - the OpenAI and Anthropic SDK retry default actually being 2.
4. Ask Joseph to re-confirm D8 after seeing the corrected matrix. Preserving
   today's behavior remains a valid small-scope decision; the facts supporting
   that decision must be correct.

The proposed constructor test—asserting that `max_retries` is omitted—does not
pin a two-retry budget. It only pins delegation to an upgradeable SDK default.
Either pass `max_retries=2` explicitly (same behavior with the installed SDKs)
or add a compatibility test that asserts each installed SDK's effective
default is 2 and deliberately fails on upstream drift.

### 2. Important — a read-silence ceiling is not a total-duration bound

**Evidence:** blueprint lines 11, 164, and 224–226;
installed HTTPX 0.28.1 / httpcore read path
`httpcore/_sync/http11.py:196-218`.

D7's selected configuration is internally coherent:

```python
httpx.Timeout(connect=120, write=120, pool=120, read=900)
```

However, `read=900` is applied to each transport read. It fails after 900
seconds with no bytes; it does not impose a 900-second total response deadline.
Non-streaming at the SDK surface does not change this—the transport may still
receive headers or body chunks internally. A peer that sends data before each
read deadline can keep the operation alive beyond 900 seconds.

Therefore these v0.2 claims are too strong:

- for a non-streaming call, the read-silence value "is the whole server-side
  generation wait";
- nine attempts are a worst-case `≈2.25h`;
- the path is "bounded, never forever";
- one source "can now occupy up to ~2.25h."

`2.25h` is a useful **conditional estimate** for nine attempts that each fail
after one uninterrupted 900-second silent read. It is not a wall-clock upper
bound.

**Concrete fix:** retain D7 if the accepted requirement is exactly a
read-silence watchdog, but:

- describe the estimate as conditional, not a maximum;
- state that no total wall-clock deadline is introduced;
- remove "bounded, never forever" and "up to" duration claims;
- if a hard per-call/per-source deadline is required, return that requirement
  to Architecture because it needs a separate total-deadline/watchdog design.

### 3. Important — provider validation currently normalizes routing but not identity

**Evidence:** blueprint lines 21, 45–48, 85, 95, 104–105, and 133–150;
current `common/call_model.py:127-135`.

`validate_provider_identity()` returns `provider.strip()`. `call_model()` uses
that local value for registry lookup and secret-resolution context, but the
handlers still receive the original `req`, and `ModelResponse` remains an echo
of `req.provider`. Gate 1 likewise says it calls the validator but does not say
that the returned normalized value is stored in `ModelSpec`.

Under the written algorithm, `" openai "` can route as `"openai"` while
telemetry/response identity remains `" openai "`. A padded pool provider can
also miss `_THINKING_DISABLE_EXTRA_BODY` because that lookup uses the stored
raw string. That violates the goal of one stable informational identity.

**Concrete fix:** choose one contract and pin it:

1. **Preferred:** provider identities must already be canonical; reject
   leading/trailing whitespace (`provider != provider.strip()`). Return the
   original valid string. This is simplest and preserves identity exactly.
2. Normalize end-to-end: store the normalized value in `ModelSpec`, construct
   or pass a normalized request to handlers, and echo the normalized value in
   responses and telemetry.

Add leading- and trailing-whitespace tests at both gates. Empty and
whitespace-only tests do not cover this split-identity case.

### 4. Important — name and test every hop in the route carrier chain

**Evidence:** blueprint lines 167–176 and 198–200;
`orchestrator/kdb_orchestrate.py:494-501,617-627,706-716,1083-1118`;
`ingestion/enrich/enrich.py:51-60,87-96`;
`ingestion/enrich/pass1_caller.py:104-110,169-174`;
`compiler/compiler.py:150-165,356-369,626-649,680-692`.

The actual route has two intermediate library boundaries that §6 does not
name:

```text
main → run → enrich_one → call_pass1 → ModelRequest
main → run → compile_source → compile_one → ModelRequest
```

Saying "`run()` threads route to both passes" and naming only `call_pass1` /
`compile_one` leaves room to miss `enrich_one` or `compile_source`. The test
plan also pins only the escape-hatch `route=None` at the orchestrator boundary;
that negative test cannot prove a known pool route survives the full chain.

**Concrete fix:**

- specify `route: ModelRoute | None = None` on `run`, `enrich_one`,
  `call_pass1`, `compile_source`, and `compile_one` so existing direct callers
  remain source-compatible;
- spell out both complete chains in §6;
- add a known-pool positive CLI pin (`spec.route` reaches `run`);
- add orchestrator/intermediate forwarding pins proving the same route object
  reaches both leaf `ModelRequest`s;
- retain the escape-hatch `None` test.

### 5. Minor — document the unseeded timeout-default change and clarify phase ownership

**Evidence:** blueprint lines 10, 24–26, 75–81, and 204–209;
`common/config/__init__.py:54-72`; `.env.example:18-22`.

The current `Settings.from_env()` fallback is 300 seconds, while the seeded
`.env.example` value is 120. The new helper fallback of 120 therefore changes
behavior for environments that run without a discovered `.env`; v0.2
documents seeded behavior but not this unseeded 300→120 change.

P1 also deletes `Settings`, while P3 says timeout helpers are wired and
validated there. P1 must still replace the three
`settings.llm_timeout_seconds` reads to stay suite-green, so the intermediate
timeout behavior and test ownership are ambiguous.

**Concrete fix:**

- include unseeded 300→120 in the D7 migration statement;
- state exactly what P1 passes to SDK constructors after `Settings` removal;
- assign each helper and its validation tests to one phase only. A clean split
  is: P1 introduces and uses the scalar `llm_timeout_seconds()` replacement;
  P3 introduces the inactivity helper and replaces scalar OpenAI/Anthropic
  timeouts with the component timeout.

## R1 absorption audit

| R1 finding | v0.2 status |
|---|---|
| F1 — unsupported first-byte/mid-stream semantics | **Absorbed:** D7 selects honest connect/write/pool versus read-silence semantics. Residual total-bound wording is R2 F2. |
| F2 — sample config conflicts with nominal default | **Absorbed:** 900 is reconciled into helper/sample/docs and existing `.env` migration is called out. Unseeded 300→120 is the minor remainder. |
| F3 — retry behavior incorrect | **Partially absorbed:** SDK and Pass-2 facts are improved, but Pass-1's broad exception retry was missed; R2 F1 is blocking. |
| F4 — provider invariant absent | **Mostly absorbed:** both gates and tests now validate provider identity. Canonicalization must be resolved per R2 F3. |
| F5 — North Star/task ledger stale | **Absorbed in plan:** P0 is now an explicit pre-Proceed gate. It is not yet executed. |
| F6 — dependency mirroring and invalid timeout values | **Absorbed:** both manifests and the full invalid-value test matrix are specified. |

## Positive assessment

These parts are ready and should remain unchanged:

- one closed `ApiCallType` and one open provider identity;
- neutral `ModelRoute` ownership;
- whole-pool Gate 1 plus universal call-boundary Gate 2;
- required active-pool routes with no rescue fallback;
- Class-B compatibility registry as factories;
- uniform late secret resolution and native-key injection;
- locally authorized Ollama no-auth;
- explicit routing-versus-timeout behavior-change statement;
- reconciled 900-second read-silence setting and existing `.env` migration;
- mirrored HTTPX dependency and fail-fast timeout-value validation;
- P0 North-Star/task-ledger gate;
- phased Class-B compatibility checkpoint before active-pool route threading.

## Required revision before `Proceed`

1. Correct D8 using the full call-path × transport matrix and re-confirm the
   preserve-current-behavior decision.
2. Correct read-silence duration claims; explicitly accept that it is not a
   total deadline.
3. Resolve provider canonicalization.
4. Enumerate and positively test every route-threading hop.
5. Complete P0 after the revised blueprint is accepted; only then request
   `Proceed`.

## Verification performed

- Reconciled blueprint v0.2 with options v1.4 and Codex blueprint R1.
- Traced current direct, Pass-1, and Pass-2 retry paths and their exception
  boundaries.
- Traced the complete CLI-to-`ModelRequest` carrier chain for both passes.
- Rechecked current config defaults, sample env, SDK retry defaults, timeout
  construction, dependency manifests, task ledger, and North Star.
- Ran:

  ```text
  .venv/bin/pytest -q \
    ingestion/tests/test_pass1_caller.py \
    ingestion/tests/test_pass1_caller_robustness.py \
    common/tests/test_call_model_retry.py

  43 passed
  ```

- No production code or existing project artifact was modified by this review.
