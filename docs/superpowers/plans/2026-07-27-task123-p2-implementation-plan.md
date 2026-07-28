# #123 P2 — selector orchestration: implementation plan

Task: **#123 Semantic graph search** · Phase: **P2** · Opened 2026-07-27
Basis: blueprint **v0.14** §2.1/§2.2/§5/§8/§9/§11/§12 + spec **v0.16** §2.1/§2.2/§2.3/§5.2 — D1–D11 all binding.
Branch: `feat/123-semantic-graph-search` · P1 closed at `d231331` (suite 2513)
Gate: **targeted tests + full suite green** (blueprint §11), then the **calibration gate (D5, Joseph fires)**.

## Scope

P2 is everything that turns P1's pieces into a selector that runs: the two prompt templates and
their loader, `graph_search`'s two-stage orchestration over an injected `call`, the 2-attempt loop
with per-attempt `StageRecord`s, the post-call output-budget classification, replay, and the
adversarial fixtures. No live calls — `call` is injected throughout (D1).

P1 left the composable pieces done and contract-tested: `projection` (grammar + both ceilings),
`budget` (preflight, route resolution, exact maxima), `response` (salvage + accounting),
`artifact` (payload + hashes), and `contracts.TERMINAL_CONTRACTS` — the 13-row terminal matrix that
P2 is the first phase to actually *produce* results against. P1.5 built that matrix as a
fail-closed return-site guard with no producer; **P2 is its producer**, so every terminal P2 reaches
must pass `assert_result_contract` at its return site.

**TDD order is oracle-first.** Two artifacts in P2 have real oracles on day one: the §8 branch-call
table (12 rows, ratified) and `TERMINAL_CONTRACTS` (**13** rows, ratified — this plan said 14 in its
first draft; `len(TERMINAL_CONTRACTS) == 13`, verified 2026-07-27, and no terminal is missing. The
figure is corrected rather than footnoted because P2.5 parameterizes the oracle over the table and a
wrong expected count is the one bug a table-driven test cannot catch). Everything else is prose or
plumbing. So the orchestration is built against those tables rather than against a happy path, and
the golden byte pins land **last** — see the P2.1a/P2.1f split below.

## Decided: `json_mode=True` on the selector call (Joseph, 2026-07-27)

**Confirmed: `json_mode=True`, on the ground of consistency with the two existing passes** —
*"if pass-1 and pass-2 both have json_mode=True, then we should have json_mode=True in Pass-1.5."*

Recorded with the distinction that settled it, because the same conflation will otherwise recur.
`ModelRequest.json_mode` is the **loose JSON-object mode** — `response_format: {"type":
"json_object"}` on openai-compat (`common/call_model.py:291`), `response_mime_type:
"application/json"` on gemini-native (`:232`). It constrains **syntax only**: a valid JSON object,
no prose preamble, no code fence. It does **not** constrain fields or shape. The restrictive
"always returns a fixed form" behaviour is a *different* parameter — `json_schema` / structured
outputs — which this codebase does not support at all (**zero** `json_schema` references in
`call_model.py`) and which #111 shelved.

Precedent, which is what the decision rests on: Pass-1 has always sent it
(`ingestion/enrich/pass1_caller.py:174`); Pass-2 did **not**, and that was a real failure —
2026-05-30 Run-2, `deepseek-v4-flash` emitted malformed JSON on a 95 kB source (`JSONDecodeError`,
not truncation) because the compile call free-formed JSON. Now pinned by
`compiler/tests/test_compile_source.py:139`. So the project already treats omitting the flag as a
defect with a regression test.

Consequences for P2:

- **The prose still carries the schema and a schema example** (Joseph's instruction, and openai-compat
  additionally 400s unless the literal word "JSON" appears in the prompt — asserted, not trusted).
  `json_mode` is not a substitute for the output contract; it removes prose *around* it.
- **The salvage ladder is unaffected and stays fully tested.** Truncation still yields
  `unparseable_response` (a cut-off object is invalid JSON — json_mode cannot help, and this is the
  whole basis of the D9 output terminal); a valid object with wrong keys still yields
  `structurally_unusable_response`; foreign slugs and out-of-vocabulary labels are still per-entry
  drops and coercions.
- **Route coverage:** all three D4 candidates (`gemini-3.6-flash`, `gpt-5.4-mini`,
  `deepseek-v4-flash`) resolve to gemini-native or openai-compat, so all three honour it.
- **Latent-trap guard (P2.2):** the **anthropic path ignores `json_mode` silently** — `:195-207`
  builds kwargs without it. No D4 candidate is anthropic, so nothing today is affected, but a future
  anthropic selector would get a no-op with no complaint. Folded into the existing §8 B10 route
  assertions (which already fail hard on `ctx_window`, `tokens_lte_bytes` and `max_output_tokens`):
  a resolved selector whose route cannot honour json_mode raises a typed config error before any
  rendering. One predicate, same posture, no new machinery.

## One owner call before the phase closes

**The prompt prose needs one review, and it must land before the D5 calibration gate — not
merely before P3a.** The selector prose is the only P2 artifact with **no in-repo oracle**:
everything else checks against `contracts.py`, a byte ceiling, or the §8 table. Prose quality is
first measurable at P5a, where a bad prompt and a bad model are indistinguishable — which is
exactly the confound the D4 3-candidate A/B exists to remove. And **Joseph fires calibration
against these exact templates**, so prose that changes afterwards invalidates the calibration.
One compact review of both fully-rendered templates, not a question series.

## Sub-phases

### P2.0 — the shared fake `call` (`kdb_search/tests/fakes.py`) — **DONE** 2026-07-27
- [x] `FakeSelector` implementing `Callable[[ModelRequest], ModelResponse]`: scripted per-attempt
      responses, recorded requests, invocation count (the §8 table's assertion target)
- [x] Must produce **all three stop-reason spellings** — `"length"` (openai-compat `:299`),
      `"max_tokens"` (anthropic `:207`), `"MAX_TOKENS"` (gemini enum `:250-254`) — **plus an unknown
      one**. D9.4's normalization is only testable through this fake, and the gemini spelling is the
      interim default selector's, so a fake that omits it would leave the live path uncovered.
- [x] Transport failure and timeout injection (the allowed retry classes that are not response-shaped)
- [x] Canned wire documents: usable, 6-of-10 salvage, unparseable, structurally unusable,
      all-entries-dropped, thin `retained` lists incl. empty (D3)

**Six things P2.0 carries beyond the bullets above, each because a bullet would otherwise have been
untestable at P2.5:**

- **The thin side has its own `all_entries_dropped` producer** (`retained_all_foreign_document`), and
  this is the most load-bearing addition. The bullets listed "thin `retained` lists incl. empty (D3)"
  and stopped there — but `{"retained": []}` and a non-empty all-foreign list **validate to the
  identical `retained == ()`** while taking *opposite* control-flow branches: the first is D3's
  `thin_retained_zero` (`completed`, no fat call, **never retried**), the second is an **allowed retry
  class** (§8 B11). A controller that branches on the validated list rather than the response class
  collapses them, and a malfunctioning selector then reads as an honest empty — exactly what D3's
  watched class exists to prevent. Pinned as a measurement in
  `test_thin_empty_and_thin_all_foreign_validate_IDENTICALLY`, so the indistinguishability is on
  record before P2.3 rather than discovered as a bug inside it. Also added for stage-correctness:
  `thin_structurally_unusable_document` (thin's failure is a missing `retained`, not a missing
  `selections`) and `thin_truncated_text` (`THIN_OUTPUT_TRUNCATION`'s producer — a severed list, not
  prose).
- **`stop_reason` defaults to the *route's* ordinary completion, not a fixed spelling.** A fixed
  default hands an openai-compat request gemini's `"STOP"` — a finish reason that route never emits —
  so a normalizer keyed to the wrong provider family would pass. `ROUTE_DEFAULT_STOP` is a sentinel
  rather than `None`, because `None` is itself a legitimate value a route may report.

- **`ScriptedReply.input_tokens` is settable.** The bullets covered the output side (stop reasons) and
  skipped the input side entirely, which leaves `THIN_INPUT_ESTIMATION_MISS` /
  `FAT_INPUT_ESTIMATION_MISS` — both `detected="post_call"`, `budget_side="input"` — with no producer.
- **Failure injection uses the real SDK exception types, and the context-length rejection is one of
  them.** Verified this session: `common/call_model.py` catches nothing (retry/backoff lives in
  `common/call_model_retry.py:28`, and §8 adopts pass-1's bare-`call_model` posture), so transport,
  timeout and D7's provider rejection all reach the selector loop as raw `openai.*` /
  `google.genai.errors.*`. All constructible in-process. Both spellings of the rejection are provided
  (`openai.BadRequestError` with `code="context_length_exceeded"`, `genai_errors.ClientError` 400) for
  the same reason all three stop-reason spellings are — plus `unrelated_bad_request()`, so P2.3's
  predicate must *distinguish* a context-length 400 from any other 400 rather than typing every
  malformed request as a budget event.
- **Documents are built FROM a space, never beside one.** `response.py:184` makes space membership the
  sole identity authority, so a canned "usable" document whose slugs are not in the test's space
  classifies as `all_entries_dropped` — and the test still passes, for the wrong reason. Every builder
  takes the space as its first argument; `test_fakes.py` pins the failure mode directly (same
  document, disjoint space, class flips).
- **Wire labels are hardcoded `"A"`, `"B"`, … — not imported from `expression_labels()`.** These are
  bytes arriving from a model: an input, not an expectation. Deriving them would give D11 a fourth
  synchronized source and hide a mutation to `WIRE_LABEL_ALPHABET` from every P2 test at once. Only
  `len(LABELS) == MAX_EXPRESSIONS` is pinned.

Also `NeverCalled` (a `call` that fails loudly, for the zero-call terminals — the failure then names
the violation instead of surfacing as an index error) and `FakeScriptExhausted`, an `AssertionError`.

**One claim deliberately weakened rather than left standing.** The first draft of that class said an
unscripted call "must not be catchable by an `except Exception`" — false: `AssertionError` *is* an
`Exception`. What actually makes an unscripted call propagate is **§2.1's no-catch-all posture** (the
retry loop catches allowed classes by concrete SDK type), so the class *relies on* that posture rather
than being immune to its violation, and the docstring now says so with the trigger for revisiting
(`BaseException` if a broad catch is ever introduced). The test was rewritten too: the original
`not isinstance(…, openai.APIError)` was true by construction and could never fail; it now asserts the
exhaustion type is outside every injectable failure class **and** that each injectable failure *is*
inside one — the half that would catch a fixture drifting out of the retry family.

**Verification:** `test_fakes.py`, 46 tests, each canned document driven through the *real*
`validate_response` / `validate_thin_retention` rather than asserted by inspection. **13 mutations
applied, all 13 caught** — salvage 6→5; `usable_document` ignoring the space; `FakeSelector` replaying
entry 0; both truncation builders returning the full document; the over-call guard removed; the gemini
spelling lowercased; `assert_consumed` neutered; the all-foreign fixture collapsed to empty *and*
re-pointed at real slugs (the two mutations that would erase the D3 distinction); route-default stop
resolution removed; `ok_stop_for` flattened to one spelling; `None` swallowed by the sentinel path.
`kdb_search` suite 589 passed / 31 skipped; full suite **2,559 passed** / 32 skipped (was 2,513 at P1
close, `d231331`).

### P2.1a — `prompts.py`: loader, assembly, D10 ordering → `test_prompts.py`
- [ ] `prompts/selector_thin_v1.txt`, `prompts/selector_fat_v1.txt` — drafted, not yet pinned
- [ ] Loader: `Path(__file__).parent / "prompts" / …` (precedent: `compiler/prompt_builder.py:38`),
      cached; **no `__init__.py` in `prompts/`** — package-data is declared on `kdb_search`
      (`pyproject.toml:50`), so resource access goes through the parent package
- [ ] `PromptRef` construction: `version` from the filename, `sha256` over the template bytes,
      `repo_path`, and `git_commit` — resolution decided here (see Decisions)
- [ ] **D10 asserted on the rendered USER message, not the template source** — `EVIDENCE` before
      `QUERY`, both stages. A template can reorder at render time; the claim is about what the
      model receives, so the assertion belongs where the bytes are final.
- [ ] **Offline built-wheel prompt-loading smoke test** (blueprint §1) — deferred out of P1.0 by
      necessity (nothing existed to load); P2.1a is the first moment a `.txt` exists. This is also
      what proves the `Path(__file__).parent` access survives a wheel install.
- [ ] **The `SYSTEM_TEMPLATE_BUDGET_BYTES` obligation** (`constants.py:170-176`): assert the real
      rendered system block + user wrapper against 3,072 B, and raise the constant to the measured
      figure if exceeded. **Low risk, stated so it does not read as a mid-phase failure:** the
      static guarantee has **36,832 tokens of slack** (283,168 against 320,000), so a realistic
      1–3 kB system block cannot break it. But raising the constant edits a ratified §7.0a figure
      and therefore costs a **blueprint v0.15** bump — expected, not a regression.
- [ ] Stage-2 bound assertion (blueprint §11's P2 row): with real templates,
      `fat_worst_case_request_bytes()` stops being part-declared and becomes measured —
      100 × 2,500 B + 4,096 B + the measured template ≤ ~257 kB, `tokens_lte_bytes` ⇒ tokens,
      + 26k reserved output < 320k. Same assertion as the item above; stated once, tested once.

### P2.1f — golden byte pins → `test_prompts_golden.py`
- [ ] Pinned exact bytes of both rendered templates + version/SHA guard
- [ ] **Lands after the prose review, before the D5 calibration gate.** Split from P2.1a
      deliberately: the pin is the only P2 artifact coupled to prose *content*; P2.2–P2.6 couple
      only to structure (a system string and a user string exist, in D10 order), so orchestration
      proceeds on the drafts while the prose is out for review.

### P2.2 — `search.py` spine: the zero-call terminals → `test_two_stage.py`
- [ ] `graph_search` signature per §2.1; `call` injected; typed outcomes are `status` values and an
      unexpected exception **propagates** (no catch-all — §2.1's fail-hard posture)
- [ ] `abstain_empty_space` / `execution=not_executed` — empty or reason-stamped-empty space,
      `call` never invoked
- [ ] thin-preflight `budget_exceeded` / `not_executed` — zero spend, never retried
- [ ] `InvalidGraphSearchRequest(code="max_expressions_exceeded")` — raised before any rendering,
      body read, call or `StageRecord` (D9.2; P1 pinned the exception, P2 pins the *zero-work*)
- [ ] Route resolution failures (`ctx_window` None, missing `tokens_lte_bytes`,
      visible + hidden > `max_output_tokens`) raise **before any rendering or calling** (§8 B10)
- [ ] `json_mode=True` on every selector `ModelRequest`, both stages — asserted, mirroring
      `compiler/tests/test_compile_source.py:139`'s regression pin
- [ ] Route cannot honour `json_mode` (anthropic) ⇒ typed config error at resolution, before any
      rendering — folded into the B10 assertions above
- [ ] The rendered prompt contains the literal word "JSON" (openai-compat 400s without it)
- [ ] `assert_result_contract` at every return site

### P2.3 — `stage_call`: attempts, records, output classification
- [ ] Up to 2 logical attempts per executed stage; attempt 2 only after an allowed retry class
      (transport, timeout, `unparseable_response`, `structurally_unusable_response`,
      `all_entries_dropped` — `response.RETRY_CLASSES`)
- [ ] One `StageRecord` per logical attempt **including failures**; `logical_call_count ==
      len(StageRecords)` (§6 invariant, already hashed by `artifact.py`)
- [ ] Immediate retry, no backoff — pass-1's posture deliberately (§8 G5b, precedent
      `ingestion/enrich/pass1_caller.py:179`); the stage entry records the provider's *actual* SDK
      sub-retry policy (openai-family `max_retries=2`; **gemini none**), never counted as an attempt
- [ ] **Post-call output-budget classification at this one site, governing BOTH stages** (D9.3/D9.4):
      predicate is *normalized cap stop **AND** no complete usable document*; raw + normalized stop
      reason archived; unknown stop reason **never** guessed into the budget class; classified
      **before** the generic `unparseable_response` retry; never retried; terminal (F1 does not apply)
- [ ] A complete usable document that merely carries a cap stop is validated **normally**, the stop
      recorded in telemetry (R1 salvage; `compiler.py:405-409`'s carrier-metadata ruling)
- [ ] `budget_estimation_miss` — typed `budget_exceeded` / `detected: post_call` /
      `budget_side: input`, attempted once, never retried, excluded from the §8.4 gate series

### P2.4 — the two-stage flow → `test_two_stage.py`
- [ ] thin → fat order; thin **always** runs (R4 as amended — the masking-asymmetry rationale)
- [ ] retain-all when N ≤ M (stage 2 = all eligible, manifest order); `thin.retained_validated`
      when N > M
- [ ] **F1 path**: thin exhausted + N ≤ M ⇒ proceed to fat, concordance `null`,
      `thin_failed_nonbinding`, `execution=fat_after_thin_failure`
- [ ] thin exhausted + N > M ⇒ `selector_failure` / `thin_attempted`, failure class recorded
- [ ] **D3 terminal**: N > M and stage-2 empty ⇒ no fat call, `status=completed`, hits `[]`, ALL
      expressions unresolved, concordance `null`, `evidence_status=not_applicable`,
      `body_coverage=None`, `thin_retained_zero` (watched)
- [ ] fat preflight `budget_exceeded` / `thin_attempted` — no fat `StageRecord`; the named F1
      interaction (`budget_exceeded` + `thin_failed_nonbinding`) covered
- [ ] concordance = `len(fat_top10 ∩ thin_top20) / len(fat_top10)`; `None` when fat has no validated
      hits or no fat stage ran
- [ ] `artifact.build_audit_payload` on **every** path (§6 — one path, caller owns persistence)

### P2.5 — the §8 branch table as a parameterized oracle
- [ ] One parameterized case per row of the 12-row branch-specific call-count table, each asserting
      (a) logical `call` invocations, (b) `logical_call_count == len(StageRecords)`,
      (c) `assert_result_contract` passes
- [ ] This is P2's analog of P1.5's contract matrix: it is what proves the orchestration is
      **complete** rather than working on the happy path, and the table is already ratified, so the
      oracle is not being invented alongside the code it checks.

### P2.6 — `replay.py` → `test_replay.py`
- [ ] Record replay (default): integrity hash validated, **no calls, no body reads**
- [ ] Historical selector re-call (opt-in): **archived rendered bytes + manifest only**, stamped
      `historical_recall`. Documented at the call site: this path **bypasses the projector and the
      budget preflight by construction** — its bytes are historical. Wiring it through the normal
      path would produce different bytes and silently defeat the mode.
- [ ] #119 byte-pinning survives: caller-supplied `context_snapshot=` writes no record (H8)

### P2.7 — adversarial fixtures + close-out → `test_adversarial.py`
- [ ] H01 / H02 evidence-side injection (system-block precedence: evidence is subject matter,
      never directives)
- [ ] H03 query-side (P10) — the query-side indent guard fixture
- [ ] Full suite green; mutation-check the two behaviours with no other coverage (the D10 ordering
      assertion and the stop-reason normalization) per standing repo practice
- [ ] Update `docs/TASKS.md`, this plan's checkboxes, and blueprint §11's P2 row on closure

### Gate — calibration (end of P2, **Joseph fires** — D5, ledger #11)
- [ ] §7 usage-reported measurement, one non-comparative call per candidate (3-call ceiling)
- [ ] Measurements persisted to the **sibling calibration artifact** — fixture manifest untouched
- [ ] Requires P2.1f frozen first (calibration is against the pinned prompts)

## Decisions taken here

**`PromptRef.git_commit` resolution — best-effort `git rev-parse --short HEAD`, cached, `"unknown"`
on failure.** Precedent exists: `common/version.py:release_version()` is the same posture
(subprocess, 5 s timeout, `"unknown"` when git is unavailable). Not reused directly, because
`release_version()` returns a `git describe` string (`v0.5.6-12-gd231331-dirty`) and the field is
named `git_commit` — putting a describe string in it would break the name-matches-contents rule.
Cached at module level so it is not a subprocess in the hot path, and it returns `"unknown"` rather
than raising in a built wheel with no `.git`. **Not load-bearing:** a dirty tree means the commit
does not fully describe the template, which is exactly why `PromptRef` also carries `sha256` over
the template bytes — content fidelity rests on the hash, and `git_commit` is provenance colour.

**The golden pin is split from the loader (P2.1a/P2.1f).** Recorded as a sequencing decision, not a
scope change: both items still land inside P2, and P2.1f still precedes the calibration gate.
