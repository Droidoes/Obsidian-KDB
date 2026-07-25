# Task #121 — Config-Driven Provider Wiring Blueprint Review (Codex R3)

**Date:** 2026-07-24  
**Reviewer:** Codex  
**Review target:** `docs/superpowers/archive/specs/2026-07-24-task121-config-driven-provider-wiring-blueprint.md` (v0.3)  
**Architecture basis:** options v1.4 (D1–D6) plus D7/D8  
**Prior review:** `2026-07-24-task121-config-driven-provider-wiring-blueprint-review-codex-v2.md` (R2)

## Verdict

**REVISE — narrow corrections only; no new architecture decision is needed.**

v0.3 absorbs every architectural issue from R2. The corrected retry matrix is
accurate, SDK retry counts are now explicitly pinned, provider identity is
canonical, every route-carrier hop is named and tested, read-silence semantics
are honest, the unseeded timeout change is disclosed, and phase ownership is
substantially clearer.

Two implementation-spec issues remain before P0/`Proceed`:

1. the risk section describes an impossible "18 silent wedges" path and then
   partially reintroduces a total-bound claim that D7 explicitly rejects;
2. the TDD matrix does not pin the malformed runtime **types** required by the
   ratified options acceptance contract, leaving room for raw
   `TypeError`/`AttributeError` instead of `ModelConfigError`.

Both are local blueprint edits. They do not reopen D1–D8.

## Findings

### 1. Important — the `18 × 900s` full-wedge scenario cannot occur

**Evidence:** blueprint lines 12, 18–27, 180, and 245–246;
`compiler/compiler.py:71,328-329,354-386`;
`common/call_model_retry.py:57-81`.

The corrected retry **attempt-count** matrix is right: a mixed Pass-2 source
can reach as many as 18 HTTP attempts across two content attempts.

The risk calculation is not:

```text
Pass-2 worst path ≈ 18 × 900s ≈ 4.5h if every attempt wedges silently
```

If every HTTP attempt wedges silently, the first
`call_model_with_retry()` exhausts its nine attempts and raises. `compile_one`
catches that model-call exception and returns immediately; it never reaches
the second content attempt. The all-silent terminal path is therefore:

```text
9 silent timeouts × 900s ≈ 2.25h, plus retry backoff/overhead
```

The 18-attempt path requires the first content attempt eventually to return a
response so a content gate can reject it and advance the loop. Its maximum
silent-timeout composition is:

```text
first content attempt: 8 silent failures + 1 returned response
second content attempt: 9 terminal silent failures
= 17 silent timeouts + one returned-response duration
```

That is a conditional `≈4.25h` of silence ceilings, plus generation and
backoff—not 18 silent wedges. If both content attempts return responses, the
maximum is 16 silent failures plus two response durations.

The final phrase "Bounded only by the attempt caps" also needs qualification.
Attempt caps bound the count of HTTP attempts, but D7 correctly states that a
byte-dripping peer can keep any one attempt alive indefinitely. They do not
create a wall-clock bound.

**Concrete fix:**

- use `≈2.25h` for the all-silent terminal Pass-2 path;
- optionally document the 17-silent-failure mixed path if that operational
  detail is useful;
- say attempt **counts** are bounded, while total wall time is not;
- keep all duration figures explicitly conditional.

### 2. Important — the runtime-type failure matrix promised by options v1.4 is missing

**Evidence:** options v1.4 lines 139–148 and 164–168;
blueprint lines 59–76, 110, 203, and 217;
the options document's statement that dataclass annotations enforce nothing.

The blueprint's rules imply that route fields have types, but the TDD matrix
only names:

- an unknown `api_call_type` string;
- endpoint empty/non-empty/`None`;
- key name empty/`None`.

It does not pin wrong runtime types, even though options v1.4 acceptance
explicitly requires "field presence, **types**" at Gate 1 and a "wrong endpoint
type" rejection at Gate 2.

This matters because a naïve implementation can leak the wrong exception:

```python
route.api_call_type not in API_CALL_TYPES  # list value → TypeError: unhashable
route.api_call_type                        # non-ModelRoute object → AttributeError
```

That violates `validate_route()`'s contract to raise `ModelConfigError` naming
the provider and violated rule before SDK construction.

**Concrete fix:** specify ordered runtime validation and tests:

1. `route` must be a `ModelRoute`; otherwise `ModelConfigError`.
2. `api_call_type` must be a string before closed-set membership is tested.
3. `endpoint` must be `None` or a string; reject integer/list/object values.
4. `api_key_env` must be `None` or a string before auth-policy validation.
5. When `allow_no_auth=True`, only `None` or an otherwise valid key-name
   string is accepted; the flag must not disable type validation.
6. Gate 1 wraps each malformed JSON type in `PoolError` naming the model ID;
   Gate 2 returns `ModelConfigError` before any SDK constructor is called.

Add non-string/unhashable cases at both gates. Also reject whitespace-only
endpoint and key-name strings (and preferably padded values) so malformed
config does not survive to `os.getenv` or an SDK URL parser.

### 3. Minor — reconcile decision status, phase wording, and test ownership

**Evidence:** blueprint lines 3, 13, 96, 205, 207–215, and 223–228.

Three small editorial inconsistencies remain:

- The header says D8 was "re-presented to Joseph"; the decision section says
  it was "re-confirmed." Record one unambiguous state. If re-confirmed, say
  "re-presented and re-confirmed"; if still awaiting confirmation, D8 is not
  yet ratified.
- P1 says timeout behavior is unchanged, while line 40 correctly records the
  unseeded fallback change from 300 to 120. Say the **scalar constructor
  shape** and seeded value are unchanged; the unseeded fallback intentionally
  changes under D7.
- Pass-1 retry and Pass-2 content/transport pins are listed under
  `test_call_model.py`, but those boundaries belong in
  `ingestion/tests/test_pass1_caller*.py`,
  `common/tests/test_call_model_retry.py`, and
  `compiler/tests/test_compiler.py`. Assigning them to their owning layer will
  keep the implementation plan surgical.

## R2 absorption audit

| R2 finding | v0.3 status |
|---|---|
| F1 — incomplete retry matrix | **Absorbed:** the call-path × transport matrix is correct; Pass-1 and Gemini behavior are represented; `max_retries=2` is explicit. Only the derived risk example is wrong (R3 F1). |
| F2 — read-silence presented as total bound | **Absorbed in contract:** D7 now explicitly rejects a total deadline and documents byte-drip behavior. Risk wording needs the narrow correction in R3 F1. |
| F3 — split provider identity | **Absorbed:** padded identities are rejected; the original canonical string is used everywhere. |
| F4 — incomplete carrier chain | **Absorbed:** all five boundaries and both positive/negative forwarding paths are named. |
| F5 — unseeded default and phase ownership | **Absorbed:** 300→120 is disclosed and P1/P3 ownership is defined. One sentence needs wording alignment (R3 F3). |

## Positive assessment

The implementation architecture is ready:

- active-pool routes are required, early-validated, and authoritative;
- route-less calls retain a complete nine-provider compatibility registry;
- transport dispatch depends only on `api_call_type`;
- provider remains an open but canonical identity;
- secrets resolve late and uniformly for all handlers;
- Ollama no-auth remains locally authorized and caller-inexpressible;
- SDK retry behavior is explicitly stable against upstream default drift;
- timeout semantics and intentional behavior changes are disclosed;
- the complete route carrier supports Task #118 without adding loose scalars;
- P0 correctly precedes `Proceed`, and closure docs remain separate.

## Required edits before `Proceed`

1. Correct the silent-timeout risk arithmetic and wall-clock wording.
2. Add ordered runtime-type validation and its Gate-1/Gate-2 tests.
3. Reconcile the three minor status/phase/test-location statements.
4. Complete P0 (`TASKS.md` and the North Star) against the corrected blueprint.

No further architecture round is necessary after those edits unless D8 has not
actually been re-confirmed.

## Verification performed

- Reconciled v0.3 with options v1.4 and every R2 finding.
- Re-traced the nested SDK, wrapper, Pass-1, and Pass-2 attempt paths.
- Rechecked public dataclass/runtime validation boundaries and the ratified
  acceptance matrix.
- Rechecked route propagation, current config defaults, task ledger, and North
  Star state.
- Ran:

  ```text
  .venv/bin/pytest -q \
    common/tests/test_call_model.py \
    common/tests/test_model_pool.py \
    common/tests/test_config.py \
    ingestion/tests/test_pass1_caller.py \
    common/tests/test_call_model_retry.py

  92 passed
  ```

- No production code or existing project artifact was modified by this review.
