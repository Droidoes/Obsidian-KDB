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

### P2.1a — `prompts.py`: loader, assembly, D10 ordering → `test_prompts.py` — **DONE** 2026-07-27
- [x] `prompts/selector_thin_v1.txt`, `prompts/selector_fat_v1.txt` — drafted, not yet pinned.
      **One file per stage carrying BOTH halves**, split by a `<<<USER>>>` marker line: `PromptRef`
      holds one `version`, one `sha256` and one `repo_path`, so a two-file stage would need two
      refs — and the owner's prose review is over one rendered prompt per stage.
- [x] Loader: `Path(__file__).parent / "prompts" / …` (precedent: `compiler/prompt_builder.py:38`),
      cached; **no `__init__.py` in `prompts/`** — package-data is declared on `kdb_search`
      (`pyproject.toml:50`), so resource access goes through the parent package.
      **Asserted, because it is a real trap:** `prompts.py` and `prompts/` share a name, and the
      module only wins because a namespace-package directory is the import system's last resort —
      adding `prompts/__init__.py` would shadow the module. Mutation-checked.
- [x] `PromptRef` construction: `version` from the filename, `sha256` over the template bytes,
      `repo_path`, and `git_commit` — resolution decided here (see Decisions)
- [x] **D10 asserted on the rendered USER message, not the template source** — `EVIDENCE` before
      `QUERY`, both stages. A template can reorder at render time; the claim is about what the
      model receives, so the assertion belongs where the bytes are final. Asserted **twice**: once
      on slot order with content sentinels (immune to what the content contains) and once on the
      unindented section headers (the order the model reads), plus `endswith(query)` for D10's
      attention-position half.
- [x] **Offline prompt-loading smoke test** (blueprint §1) — deferred out of P1.0 by
      necessity (nothing existed to load); P2.1a is the first moment a `.txt` exists.
      **Divergence, deliberate and recorded: not a built wheel.** `.venv` has no `setuptools`,
      `build` or `wheel`, so building one needs a network install — offered to the owner rather
      than substituted silently. The property is covered in two halves instead: (i) the packaging
      **declaration** is parsed out of `pyproject.toml` and its globs expanded, so a new prompt
      file added without a packaging update fails; (ii) resolution is proved by a subprocess with
      `cwd` **outside the repo** and `PATH` emptied — which also pins `git_commit == "unknown"`,
      the installed-wheel case.
- [x] **The `SYSTEM_TEMPLATE_BUDGET_BYTES` obligation** (`constants.py:170-176`): assert the real
      rendered system block + user wrapper against 3,072 B, and raise the constant to the measured
      figure if exceeded. **MEASURED, and the constant still holds** — but the margin changed
      materially when codex's F1/F3 prose landed, so both figures are recorded:

      | | at first draft | after the codex absorption | headroom vs 3,072 |
      | --- | --- | --- | --- |
      | fat | 2,381 B (2,321 + 60) | **2,998 B** (2,938 system + 60 wrapper) | **74 B** |
      | thin | 2,146 B (2,085 + 61) | **2,507 B** (2,446 + 61) | 565 B |

      Measured in **bytes**, with the widest cap value the contract allows, so each figure is the
      stage's maximum rather than a sample. **The fat figure is the normative one** —
      `fat_worst_case_request_bytes()` is the constant's only consumer and it is fat's static
      guarantee that rests on it; thin is estimate-guarded with a typed `budget_estimation_miss`,
      so thin's assertion is a bonus.
      74 B is thin headroom for future prose — see "Open: raise
      `SYSTEM_TEMPLATE_BUDGET_BYTES`" below. It does **not** gate P2.1f: the pins freeze the
      *measured* bytes, which the constant does not move.
- [x] Stage-2 bound assertion (blueprint §11's P2 row): with real templates,
      `fat_worst_case_request_bytes()` stops being part-declared and becomes measured —
      100 × 2,500 B + 4,096 B + the measured template = **257,094 B** ≤ ~257 kB,
      `tokens_lte_bytes` ⇒ tokens, + 26k reserved output = **283,094 < 320,000** (the declared-reserve
      figures are 257,168 / 283,168). Same assertion as the item above; stated once, tested once.

**Five things P2.1a carries beyond the bullets above.**

1. **Single-pass substitution is a P10 control, not a style choice.** Sequential
   `str.replace("{{EVIDENCE}}", …).replace("{{QUERY}}", …)` is an injection vector: an excerpt
   containing the literal `{{QUERY}}` gets the query block substituted *into it* on the second
   pass. `re.sub` never rescans replacement text, so a marker inside evidence or query content is
   inert — asserted directly, and mutation-checked by reintroducing the sequential form.
2. **Both silent-failure directions of substitution raise.** An unknown slot (`{{EVIDENC}}`) would
   ship a brace pair to the model; a value with **no** slot would drop silently — and the concrete
   case there is `{{MAX_RESULTS}}` disappearing from the fat prompt while the validator keeps
   counting `over_cap` violations against a rule the selector was never told.
3. **`max_results` is rendered into the fat prompt** (and the retention cap into thin), for exactly
   that reason. It sits in the per-request tail *after* evidence, since D10's invariant-first
   ordering applies to everything that varies per source, and before the query, since the query is
   last.
4. **The schema example inside each SYSTEM block is driven through the REAL validator** —
   `validate_response` / `validate_thin_retention`. This is the only in-repo oracle available for
   prompt prose: it pins that the example the model is told to copy is an example of a response the
   validator accepts, that the fat wire carries exactly `slug` + `matched` (no reinstated D8
   `evidence` field), and that expressions are addressed by **letter** (D11) — an integer example
   would re-open the base ambiguity. It also puts a floor under the owner's prose review: a
   wrongly-edited example fails a test instead of reaching a paid call.
5. **`artifact._sha256` → `artifact.sha256_digest` (public).** `prompts.py` stamps
   `PromptRef.sha256`, and the digest convention belongs to the artifact — sharing the function is
   what keeps the prompt hash and the artifact hashes from becoming two conventions. Pure rename,
   two call sites.

**Verification.** 62 new tests (`kdb_search/tests/test_prompts.py`) at first draft; **118 after both
codex rounds** (68 prompt + 50 H04 regression in `test_projection.py`, the growth almost all from R1/R2's
every-field × every-boundary parameterization); full suite **2,559 → 2,677 passed / 32 skipped**, green.
**Mutation-checked, 29 mutations, 29 caught** — the 20 below, plus 9 across the two absorption rounds: title escaping removed; slug escaping removed; the `splitlines()`
boundary set narrowed to `\n`; the escape dropping the character instead of collapsing it; the
escape expanded to a 2-char literal (which would break byte-count preservation); `_version_of` made
total again; `load_template` hardcoding the version instead of calling it; `page_type` escaping removed
(the type-hint exemption restored); and the H04 test oracle narrowed back to the characters round 1
covered. D10 reordered in each
template; sequential `.replace`; each of the unknown-slot / unused-value / repeated-slot guards
removed; `repo_path` computed absolute; `sha256` over the system half only; newline translation
disabled (CRLF leaking into the digest); `version` hardcoded instead of derived; the SYSTEM-half
slot check removed; overhead measured in characters instead of bytes; overhead measured with the
narrowest cap; the fat example switched to integer labels; the fat example re-growing an `evidence`
field; the result cap dropped from the wrapper; the thin example's slugs made non-copyable; the P10
precedence clause losing its query side; the word "JSON" removed; and `prompts/__init__.py` added
to shadow the module.

### P2.1a — codex review absorbed (verdict **REVISE**, 2026-07-27)

Review: `docs/superpowers/specs/2026-07-27-task123-p2.1a-review-codex.md`. Prompt:
`…-p2.1a-selector-prompts-review-prompt.md`. He reproduced the byte arithmetic independently and
confirmed the loader mechanics; four of five findings absorbed, the fifth filed.

- **F1 (HIGH) — the thin prompt was internally contradictory at a binding cap. ABSORBED.** Its
  claim that a false positive "costs almost nothing" is true only while the cap is slack; at
  ~490-against-100 every weak retention displaces a relevant identity, so the model was told not to
  be selective and then required to be, with no rule for resolving it — which invites truncation by
  *position* at exactly the transition. Replaced with two explicit steps: eligibility (read every
  identity before deciding; unsure-from-a-title is the case to keep; precision is stage 2's job),
  then the limit (fits ⇒ return all; exceeds ⇒ rank the whole eligible set and cut, and at a binding
  limit a weak identity is no longer free). Plus two prohibitions in both templates: **never stop
  reading once the list could be filled**, and **never treat EVIDENCE order as a relevance signal**
  — it is the graph's own ordering.
- **F3 (MEDIUM) — fat had no ordering criterion and a one-directional excerpt clause. ABSORBED.**
  Ordering now names directness and strength of positive support, centrally-about before
  supporting-coverage, breadth across QUERY keys/themes as the tiebreaker. And the excerpt clause
  gained its missing half: an excerpt's silence is weak evidence *against*, but **text you cannot
  see is not evidence for anything either** — never select on an unseen body, and judge a title-only
  entry solely on what its identity line positively shows. Without that, the honesty clause licensed
  speculative selection.
- **F2 (HIGH) — H04 fixed at the serializer, not left to a fixture. ABSORBED, owner-authorized.**
  See P2.7's H04 entry, which now records the fix rather than the filing.
- **F4 (LOW) — the version parser was unreachable on the real import path. ABSORBED.** The module
  constants called `_VERSION_RE.search(...).group(1)` at import, *before* `load_template`'s checked
  path and before `PromptTemplateError` was even defined — so a filename that lost its suffix raised
  `AttributeError`, and no test could reach the typed failure. Now one `_version_of()` parser,
  declared after the exception and used by both, with the parser itself tested directly over five
  malformed names (the import-time path cannot be monkeypatched after import).
- **F5 (LOW) — the wheel gap. FILED, not closed** (`docs/TASKS.md` #127). He confirms the packaging
  declaration is correct and module-relative loading is right, and agrees it blocks neither the pin
  nor calibration. Real build-wheel/install/import smoke lands when offline build tooling exists.
- **One correction to the review prompt, ours:** it called precision@5 "the project's only normative
  gate". Its **formula** is normative (spec §8.3 metric 3); the gate table has exactly one binding
  gate — escaped foreign-identity rate — and precision@5 is not in it. Codex is right; the ranking
  recommendation stands regardless.
- **Process note for the next reviewer prompt:** the output-file-only guardrail was strict enough
  that codex declined to run pytest at all (cache writes). Future prompts should explicitly permit
  `-p no:cacheprovider` runs.

### Open: raise `SYSTEM_TEMPLATE_BUDGET_BYTES` (owner call, **independent of P2.1f**)

Both absorption rounds together cost fat 617 B and left **74 B** of headroom. The suite is green — the
constant holds.

**Corrected sequencing (2026-07-27).** This was twice described as a P2.1f prerequisite. It is not.
The constant's only consumers are `budget.fat_worst_case_request_bytes()` (`budget.py:240`) and the
two headroom assertions (`test_prompts.py:472`, `test_budget.py:341`); P2.1f pins the **measured**
rendered bytes plus the version/SHA guard, and raising the reserve moves none of them. So the pins can
land now, and raising the constant later costs exactly what it costs today — a blueprint amendment and
a one-line change. What 74 B actually buys is *future prose* room: the next sentence anyone adds
breaks a ratified figure. That is a real cost, but it is not a blocker.

**The recommendation is to raise it to 4,096 B**, and the reason is that 3,072 was never a measured
bound: it is the "~3 kB system/template" line written into the M=100 guarantee before any prompt
existed. What the guarantee actually needs is slack against `SMALLEST_POOL_BUDGET_TOKENS`, and it has
**36,832 tokens** of it (283,168 against 320,000). Raising the reserve by 1,024 B moves the worst
case to 258,192 B and the guarantee to 284,192 — still ~35.8k under the pool, and 4,096 matches
`QUERY_BLOCK_CEILING_BYTES`, so the two per-request reserves read as one scheme. Trimming instructions
the review just added, to fit a figure invented before the instructions existed, is the wrong
optimization.

Cost: a **blueprint v0.15** amendment to §7.0/§7.0a (recompute the guarantee sum) plus the
`constants.py` docstring. No allowance, no ceiling, no wire figure moves. **Sequencing, per codex:
record v0.15 before changing the constant**, not after.

**Codex concurs (re-review Q3), with a better reason than ours.** Ours was "the prompt needs another
sentence", which is weak — a frozen v1 prompt arguably *should* be hard to extend. His is
**architectural capacity**: the golden pin is what forces version and review discipline on content
changes, so the reserve does not need to do that job too, and a 4,096 B reserve lets future
*reviewed* prompt versions evolve without a blueprint amendment for ordinary prose. That is the
argument to record, because it survives the objection ours does not.

### P2.1a — codex round 3 CLOSED (verdict **APPROVE-WITH-ITEMS**, 2026-07-27)

Response: `docs/superpowers/specs/2026-07-27-task123-p2.1a-round3-codex.md`, against `37be899`.
**R1–R4 all confirmed closed; P2.1f released; no further behavioral or prompt-prose change required.**

He re-derived rather than took our word for it: 3 fields × 11 boundaries = **33/33** one-line cases
by direct runtime probe, confirmed there is no fourth interpolation site in `render_thin_line` and
that `render_fat_block` inherits the protection by delegation, and confirmed the R2 oracle now fails
independently if `_LINE_BREAKS` is narrowed. On our disclosed mutation-harness defect: it "does not
change this conclusion" — because he inspected the source and tests directly and ran his own probe
rather than relying on our 29/29. That is the right response to the disclosure and vindicates making it.

**His one item, clerical, fixed in this commit.** The P2.7 narrative still said `_single_line` was
applied to "`slug` and `title`" — stale since R1 added `page_type`. Corrected at **both** sites (the
defect description and the implementation note), and while there we fixed a third staleness he did
not catch: the note claimed **12** regression tests where the count is now **50** (verified by
`--collect-only`, not by recollection — doc-vs-implementation drift being the exact defect he flagged).

Two slips in his response, recorded because neither changes the verdict and both could mislead later:
he cited the stale text as living in `…specs/2026-07-27-task123-p2.1a-plan.md`, which does not exist
(it is this file, `plans/…-p2-implementation-plan.md`); and his "32 expected skips" is the full-suite
number — `kdb_search/tests` alone is 31.

### P2.1a — codex re-review absorbed (round 2, verdict **REVISE**, 2026-07-27)

Review: `docs/superpowers/specs/2026-07-27-task123-p2.1a-rereview-codex.md`, against `568313c`. He
ran the suite this round (the guardrail was loosened to permit `-p no:cacheprovider`), reproduced
every figure, and confirmed F1/F3/F4 substantively resolved. Four new findings, all absorbed.

- **R1 (HIGH) — H04's "exactly one line for any input" was still false: `page_type` was not
  sanitized. ABSORBED, and this one is the real catch.** The first pass exempted the field because
  `SpaceEntity.page_type` carries the `PageType` `Literal` — which is a **type hint, not a runtime
  check**. Verified end to end: `SpaceEntity` validates nothing, `kdb_graph/schema.py:64` declares
  `page_type STRING`, `kdb_graph/intake.py:325` writes the producer value through unexamined, and
  `SpaceEntity(page_type="concept\nQUERY:")` rendered **two lines** with the second exactly `QUERY:`.
  The exemption was also inconsistent with our own reasoning one field over: the slug is sanitized
  precisely so the render path does not lean on a guarantee made elsewhere. Now applied to all three
  interpolated fields.
- **R2 (MEDIUM) — the H04 test oracle was derived from the production constant. ABSORBED.** The
  round-1 assertion read `not set(line) & set(_LINE_BREAKS)`, so narrowing `_LINE_BREAKS` in both
  production and the check would have stayed green — the test was asking whether the code agreed with
  itself. It also exercised only 8 of the 11 boundaries. Replaced with a **hardcoded `H04_BREAKS`**
  independent of production, anchored to the interpreter (each entry really splits; nothing in the
  ordinary ranges does; there are exactly ten single-character boundaries), asserted as a *subset* of
  the production set so a narrowed production set fails rather than narrowing the oracle with it, and
  parameterized **every field × every boundary**.
- **R3 (MEDIUM) — "byte-count preserving" was false. ABSORBED as a claim + test correction.**
  `" "` is 3 UTF-8 bytes and becomes 1, so the substitution is **character-count preserving and
  UTF-8 non-expanding**, not byte-preserving — and the round-1 test could not have caught the
  difference, because it compared two already-sanitized renders and so said nothing about input
  versus output. Non-expansion is the property the ceilings actually need (a sanitized render can
  only shrink), and it is now what is asserted, over every boundary. `_single_line`'s output
  behaviour is unchanged.
- **R4 (LOW) — "then the rest" and a record/template discrepancy. ABSORBED.** "then the rest" read as
  licence to include the remaining candidates, contradicting both positive-support-only and the
  anti-padding line. And this plan claimed *both* templates forbid stopping once the list could be
  filled while only thin said so. Fat's `HOW TO ORDER` now ends "rank the whole supported set before
  cutting to the limit: never stop once the list could be filled, and never treat the order of
  EVIDENCE as a signal of relevance." Cost +16 B, not the byte-neutral he predicted.
- **Q2, the question we could not answer ourselves:** he judges the fat block **not**
  over-instructed — `WHAT TO SELECT` defines membership, `HOW TO ORDER` defines order, and the
  separation helps rather than dilutes. The repeated positive-support wording he calls load-bearing
  enough to keep. Only "then the rest" needed removing.
- **One forward obligation filed, not absorbed** (`docs/TASKS.md` **#128**): the future
  graph→search-space materializer should validate `page_type` membership in the canonical vocabulary
  at that boundary, where it protects MCP, CLI and the viewer too instead of making each consumer
  rediscover the rule. Codex is explicit that this does **not** replace the local containment fix —
  two layers, and the outer one does not exist yet.
- **Harness defect found and fixed in our own tooling, recorded because it nearly produced a false
  clean sweep:** the mutation harness restored only the two modules, not the test files — so the one
  mutation that edits a test leaked into every mutation after it and "caught" them all by leaving the
  suite broken. Worse, refreshing the backup from that tree persisted the mutation into the backup.
  Restore now covers every file any mutation touches, and the backup is only ever taken from a
  verified-green tree.

### P2.1f — golden byte pins → `test_prompts_golden.py` — **DONE 2026-07-27**
- [x] Pinned exact bytes of both rendered templates + version/SHA guard. **18 tests.** Pins are
      hardcoded literals, never computed from the thing they check (the R2 oracle-independence
      lesson): digest, version, `repo_path`, both half-byte counts, and the overhead figure, per
      stage. The failure message on the digest pin states the D-115-13 obligation — rename the file
      to bump the version, update the pin, land both with the prose change in **one** commit —
      because a pin whose message does not say what to do gets re-blessed blindly.
- [x] **Two pins the "exact bytes" bullet did not imply, both load-bearing.**
      (i) **The two constants folded into the overhead are pinned separately.** The overhead is *not*
      a pure function of the template: `template_overhead_bytes` renders `{{RETENTION_CAP}}` /
      `{{MAX_RESULTS}}` from `M` / `MAX_RESULTS`, so widening `MAX_RESULTS` 50 → 100 adds a byte to
      fat's wrapper with every template byte identical — the digest pin stays green while the figure
      `fat_worst_case_request_bytes()` consumes moves. A second test proves that coupling is real
      (renders at the pinned cap and at 10×, asserts the byte counts differ) so the constants pin
      cannot later be "simplified" away as redundant to the digest.
      (ii) **D10 is re-asserted on the rendered bytes.** A content hash plus byte counts stays green
      under a length-preserving swap of the EVIDENCE and QUERY blocks, and these are the exact bytes
      calibration is fired against.
- [x] **`git_commit` deliberately excluded, as a recorded decision with its own test.** It moves with
      every commit; pinning it would fail this file on each one and train the team to re-bless pins
      without reading them, destroying the signal the other pins carry.
- [x] Mutation-checked (standing practice): **12 mutations, 10 caught by this file, 12 at package
      scope.** Both non-catches are recorded in the file's docstring as boundaries rather than holes —
      the hardcoded-`version` mutation is caught by `test_prompts.py`'s version-tracks-the-filename
      test (that file tests loader *behaviour*, this one pins *values*; duplicating would let one
      copy rot), and loosening this file's own `==` is a review concern no assertion can defend,
      verified non-fatal because the constants pin still catches the widening it was meant to catch.
- [x] **Lands after the prose review, before the D5 calibration gate.** Split from P2.1a
      deliberately: the pin is the only P2 artifact coupled to prose *content*; P2.2–P2.6 couple
      only to structure (a system string and a user string exist, in D10 order), so orchestration
      proceeds on the drafts while the prose is out for review.

### P2.2 — `search.py` spine: the zero-call terminals → `test_two_stage.py` — **DONE 2026-07-27**
**33 tests, mutation 18/18.** The spine ends at one explicit seam, `search.STAGE_CALL_SEAM`, which
raises `NotImplementedError`. That is the sub-phase boundary made executable: a zero-call terminal is
a claim about work *not* done, so it must be reachable without the machinery that does the work — and
if a zero-call path ever needed a scripted reply to be exercised, it would not be a zero-call path.
- [x] `graph_search` signature per §2.1; `call` injected; typed outcomes are `status` values and an
      unexpected exception **propagates** (no catch-all — §2.1's fail-hard posture). **`body_reader`
      is required, not defaulted**: `get_body` lives in `kdb_graph`, which this package must not
      import (B1), so §2.1's "default: `get_body` bound to the caller's `vault_root`" is the
      *adapter's* default, not the core's.
- [x] `abstain_empty_space` / `execution=not_executed` — empty or reason-stamped-empty space,
      `call` never invoked. **`domain_missing` is stamped narrowly and deliberately:** spec §3.4
      names two reasons (`domain_empty` | `domain_missing`) but `WatchedClass` is a *closed* literal
      carrying only the latter, so an empty cluster under a domain that exists emits **no** watched
      class rather than a string the type does not admit — the distinction stays recoverable from
      `domain` being `None` or set, and `EMPTY_SPACE.required_watched` is empty so nothing is owed.
      It also fires only for `domain_subtree`; a `whole_graph`/`explicit` space legitimately has no
      domain, and without that guard every empty whole-graph search would report one it never had.
- [x] thin-preflight `budget_exceeded` / `not_executed` — zero spend, never retried
- [x] `InvalidGraphSearchRequest(code="max_expressions_exceeded")` — raised before any rendering,
      body read, call or `StageRecord` (D9.2; P1 pinned the exception, P2 pins the *zero-work*).
      The zero-work half is pinned *structurally*: every test drives `call=NeverCalled()` and a
      `body_reader` that raises, so if either ran, that `AssertionError` — not
      `InvalidGraphSearchRequest` — is what would surface. The cap boundary is tested inclusive
      (10 valid, 11 not), without which an off-by-one rejecting every real pass-1 payload would pass.
- [x] Route resolution failures (`ctx_window` None, missing `tokens_lte_bytes`,
      visible + hidden > `max_output_tokens`) raise **before any rendering or calling** (§8 B10)
- [x] **Gate ORDER pinned, and recorded as a decision rather than read off the spec.** Ratified text
      makes request validation and route resolution both "before any work" and does not order them
      relative to each other. Chosen: **the request first**, because it is the caller's own input and
      is judgeable without any configuration — a caller sending 11 expressions is told about the 11
      expressions, not about a route they may not have chosen. Pinned by the one discriminating case,
      a request that violates **both** at once; each gate tested alone passes under either ordering.
- [x] `json_mode` **splits across two sub-phases, by necessity.** Requests are built in `stage_call`,
      so "`json_mode=True` on every `ModelRequest`" is **P2.3**'s assertion (moved there, not
      dropped). What lands here is the half that must fail before any work — see below.
- [x] Route cannot honour `json_mode` (anthropic) ⇒ typed config error at resolution, before any
      rendering. `common/call_model.py` implements `json_mode` for openai-compat (`:291`) and gemini
      (`:232`) and **not** for anthropic, so an anthropic selector would free-form its JSON
      *silently* — the exact Pass-2 failure `compiler/tests/test_compile_source.py:139` pins. Lives
      in `search._require_json_mode_capable`, **not** folded into `budget.resolve_selector_route`:
      that function's three checks are all window/output sizing, and adding a prompt-contract premise
      would stop its name matching its contents. Tested from both sides — anthropic rejected, gemini
      accepted — so a future "fix" cannot allow-list one provider and reject capable ones.
- [x] **The estimate provably includes the rendered evidence.** A small-window fixture alone could
      not show this: at a 20,000-token window the 29,000-token thin envelope busts the budget by
      itself, so those cases pin the terminal, not the estimate's inputs. A second fixture sizes the
      window so the envelope fits with ~11,000 tokens spare, where a 5-entity space passes and a
      2,000-entity space does not and the only difference is the evidence.
- [x] **The audit payload is built on every zero-call terminal** (§6 — the emptiness is the finding).
      Observed through `telemetry.search_snapshot_hash`. The discrimination tests compare **same
      size, same `graph_ref`, different slugs** — and separately, the same space reversed. The first
      draft compared empty-vs-100, which differs in size *and* manifest length and so would have
      passed on a hash tracking only `active_entity_count`: the same trap as the R2 oracle finding, an
      assertion that looks right and proves less than its name claims. Verified by mutation (manifest
      digest reduced to a count — both tests fail). **Open, deliberately not decided here:** how
      the *full* payload reaches the caller. Ratified §1.1 fixes `GraphSearchResult` at seven fields
      and `audit` is not among them, so blueprint §2.1's "audit (always, §6)" is an obligation, not a
      field. P2.2 discharges the build obligation and shapes nothing that presupposes the answer;
      delivery belongs with **P2.4**'s caller-persistence bullet.
- [x] The rendered prompt contains the literal word "JSON" (openai-compat 400s without it) —
      **done in P2.1a**, since the templates existed there and the assertion was cheaper to write
      once than to defer. Asserted over `system + user` for both stages; the word lives in the
      SYSTEM half, which counts.
- [x] `assert_result_contract` at every return site — **and proved WIRED, not merely present.** The
      one mutation the rest of the file could not catch was deleting the guard from a return site:
      while the spine produces conforming results, removing it changes nothing and every other test
      stays green, so the fail-closed guarantee silently becomes decorative. Closed by patching the
      shared field-pattern helper to emit a hit (which every zero-call terminal forbids,
      `hits_empty=True`) and requiring `ContractViolation` at each site. That took the sweep from
      17/18 to **18/18**.

### P2.3 — `stage_call`: attempts, records, output classification — **DONE** (`stage.py`, +62 tests)
Shipped as **`kdb_search/stage.py`**, a module of its own rather than more of `search.py`: `graph_search`
decides *which* stages run, `stage_call` owns what happens inside one. `search.py` is untouched — the
`STAGE_CALL_SEAM` still raises, and P2.2's zero-call terminals stay provable without the machinery that
spends. Wiring is P2.4's.

- [x] **`json_mode=True` on every selector `ModelRequest`, both stages** — asserted, mirroring
      `compiler/tests/test_compile_source.py:139`'s regression pin. **Moved here from P2.2**, which
      could not do it: requests are built in `stage_call`, so P2.2 owns only the half that must fail
      before any work (a route that cannot honour `json_mode` at all — done, `search.py`). Recorded so
      the split does not read as a dropped bullet.
- [x] Up to 2 logical attempts per executed stage; attempt 2 only after an allowed retry class
      (transport, timeout, `unparseable_response`, `structurally_unusable_response`,
      `all_entries_dropped` — `response.RETRY_CLASSES`)
- [x] One `StageRecord` per logical attempt **including failures**; `logical_call_count ==
      len(StageRecords)` (§6 invariant, already hashed by `artifact.py`)
- [x] Immediate retry, no backoff — pass-1's posture deliberately (§8 G5b, precedent
      `ingestion/enrich/pass1_caller.py:179`); the stage entry records the provider's *actual* SDK
      sub-retry policy (openai-family `max_retries=2`; **gemini none**), never counted as an attempt.
      Shipped as `StageRecord.sdk_sub_retries` + `stage._SDK_SUB_RETRIES`; the no-backoff posture is
      asserted by a test that fails the run if `time.sleep` is called, so a backoff layer has to break
      a test to arrive rather than sliding in as an improvement.
- [x] **Post-call output-budget classification at this one site, governing BOTH stages** (D9.3/D9.4):
      predicate is *normalized cap stop **AND** no complete usable document*; raw + normalized stop
      reason archived; unknown stop reason **never** guessed into the budget class; classified
      **before** the generic `unparseable_response` retry; never retried; terminal (F1 does not apply)
- [x] A complete usable document that merely carries a cap stop is validated **normally**, the stop
      recorded in telemetry (R1 salvage; `compiler.py:405-409`'s carrier-metadata ruling)
- [x] `budget_estimation_miss` — typed `budget_exceeded` / `detected: post_call` /
      `budget_side: input`, attempted once, never retried, excluded from the §8.4 gate series

**Three things the bullets did not say, decided here:**

- [x] **`response.validate_thin_response` — a thin-side document classifier that did not exist.**
      `validate_thin_retention` takes an already-parsed *list*; nothing did parse → structure → four-way
      classification for the thin wire, so `stage_call` had no way to classify a thin response at all.
      Added to `response.py` rather than inlined here, so `_parse` stays a single source. **Its
      classification reads the RETURNED entry count, never the validated one** — which is the whole
      reason it exists: `{"retained": []}` and an all-foreign document both validate to `retained == ()`,
      and they take opposite branches (D3's honest empty, never retried, vs `all_entries_dropped`, an
      allowed retry class). `fakes.retained_all_foreign_document` was already carrying that warning from
      the input side with no production counterpart to warn *about*.
- [x] **`StageRecord` gained `stop_reason_raw` / `stop_reason_normalized`.** §8 requires both archived
      per record and the dataclass had neither — only `BudgetRecord` carried a finish reason, which is
      the wrong home: a stop reason exists on every attempt, not only on the ones that end in a budget
      event. Folded into the integrity hash (what *happened*) and deliberately not the snapshot hash
      (what was *searched*).
- [x] **`StageOutcome.validated` is `None` on `exhausted`, on purpose**, though the last attempt may well
      have parsed. A retry-exhausted stage produced no usable answer by definition, and exposing its
      final document invites precisely the F1 bug the path exists to prevent — reading a thin retention
      off a stage whose failure is what makes the retention non-binding. The attempts stay fully
      archived in `records`; the field is what a *consumer* may act on.

**Mutation sweep: 28 designed, 28 caught** — including both behaviours P2.7 names as otherwise
uncovered (the stop-reason normalizer, the retry-class predicate). The sweep deliberately includes the
mutations that look harmless: `all_entries_dropped` dropped from the usable-document set, the D9.3
conjunction weakened to a bare cap-stop test, that same check moved *after* the generic retry, the
unrelated-400 `raise` swallowed, and the thin classifier branching on the validated list. Every one
changes a real outcome; none is caught by a status assertion alone.

### P2.4 — the two-stage flow → `test_two_stage.py` — **DONE** (+42 tests)
- [x] thin → fat order; thin **always** runs (R4 as amended — the masking-asymmetry rationale)
- [x] retain-all when N ≤ M (stage 2 = all eligible, manifest order); `thin.retained_validated`
      when N > M
- [x] **F1 path**: thin exhausted + N ≤ M ⇒ proceed to fat, concordance `null`,
      `thin_failed_nonbinding`, `execution=fat_after_thin_failure`
- [x] thin exhausted + N > M ⇒ `selector_failure` / `thin_attempted`, failure class recorded
- [x] **D3 terminal**: N > M and stage-2 empty ⇒ no fat call, `status=completed`, hits `[]`, ALL
      expressions unresolved, concordance `null`, `evidence_status=not_applicable`,
      `body_coverage=None`, `thin_retained_zero` (watched)
- [x] fat preflight `budget_exceeded` / `thin_attempted` — no fat `StageRecord`; the named F1
      interaction (`budget_exceeded` + `thin_failed_nonbinding`) covered
- [x] concordance = `len(fat_top10 ∩ thin_top20) / len(fat_top10)`; `None` when fat has no validated
      hits or no fat stage ran — **plus a third null case the bullet does not name**: thin produced
      no *validated retention at all* (the F1 path). A computed 0.0 there would report "the two
      stages agreed on nothing" about a comparison that never happened, and that value would enter
      the watched series as evidence. A thin stage that **ran** and honestly retained nothing is not
      that case — its ranked list exists and is empty, so 0.0 is a real measurement. The
      discriminator is `thin.validated is None` vs `retained == ()`, which is precisely the
      distinction `validate_thin_response` was added to preserve.
- [x] `artifact.build_audit_payload` on **every** path (§6 — one path, caller owns persistence).
      Enforced structurally: every post-thin terminal returns through one `finish` helper that
      builds the audit and calls `assert_result_contract`, so neither can be omitted from a return
      site — the mutation P2.2's sweep showed the rest of the suite cannot catch. **Audit DELIVERY
      remains the open owner question** (see below); this discharges the obligation to *build*.

**Two findings, one of them a gap in the ratified matrix:**

- [x] **`FAT_INPUT_ESTIMATION_MISS_ON_F1` — a missing contract row, added as a marked EXTENSION.**
      The ratified matrix gives the F1 treatment to the fat PRE-flight terminal and to the fat
      OUTPUT terminal, but not to the fat INPUT one: `FAT_INPUT_ESTIMATION_MISS` admits
      `two_stage_attempted` only. That reads as an ordering artifact — the D7 input rows predate
      D9.3's F1 treatment — rather than a decision, and the state **is** reachable (F1 runs fat after
      an exhausted thin; a sub-330k window can still draw the provider's over-window rejection).
      With no row, a legitimate search dies fail-closed on a `ContractViolation`. Every cell is
      **copied**, not inferred — the budget cells from `FAT_INPUT_ESTIMATION_MISS`, the execution and
      watched class from `FAT_OUTPUT_TRUNCATION_ON_F1` — the evidence side is left UNENUMERATED
      exactly as its parent leaves it, and the note says EXTENSION, NOT RATIFIED TEXT in its first
      words. **Flagged for owner ratification.**
- [x] **The contract guard's budget check was wrong for a two-stage producer.** It required *every*
      matching budget record to be a non-fit, which P1.5 could write safely because it had no
      producer: a fat pre-flight rejection carries two `pre_call`/`input` records — thin's, which
      passed, and fat's, which did not. That would have forbidden the passing thin record, and
      `BudgetRecord` exists to keep exactly those (a series of estimates that never bind is how the
      estimator's calibration gets judged). Narrowed to the **last** record of the class — records
      are appended in stage order, so the decision that ended the search is the last one.

**Mutation sweep: 27 designed, 27 caught — after one honest correction.** The
`request.max_results` → `MAX_RESULTS` mutation first reported as caught, and it was caught by a
`NameError` rather than by any test. Re-run with the literal `50`, the whole suite stayed green:
every test used the default cap, under which the two values coincide. That is a real gap —
`render_fat_messages` takes `max_results` with no default precisely so the prompt's cap and
`validate_response`'s cap cannot disagree — so two tests were added at a non-default cap, one per
end of the pairing.

### P2.5 — the §8 branch table as a parameterized oracle — **DONE** (`test_branch_table.py`)
*19 cases × 6 parameterized assertions + 5 table-coverage tests = **119 test IDs**; the two figures
below are the same thing counted at different granularity.*
- [x] One parameterized case per row of the branch-specific call-count table, each asserting
      (a) logical `call` invocations, (b) `logical_call_count == len(StageRecords)`,
      (c) `assert_result_contract` passes — **and three the bullet does not name**: (d) the script
      was fully *consumed*, since a range with slack hides a branch that stops early; (e) the run
      landed on the terminal the row NAMES, because several rows share a call count
      (`fat_preflight_budget` and `thin_retained_zero` are both one call) and a count-only oracle
      passes on a search that took the other branch entirely; (f) the archived per-stage attempt
      counts sit inside that terminal's *matrix* bounds — which is where §8's table and P1.5's matrix
      meet, two ratified statements about the same run that a single artifact cannot check alone.
- [x] This is P2's analog of P1.5's contract matrix: it is what proves the orchestration is
      **complete** rather than working on the happy path, and the table is already ratified, so the
      oracle is not being invented alongside the code it checks.

**The table prints 12 rows and names 11 distinct paths.** Row 9 —
`budget_estimation_miss, budget_side: input — 1 attempted at the missing stage, 0 after` — is a
*generic restatement* of rows 2 and 12, which give the same rule at thin and at fat specifically.
Inventing a case for it would mean inventing a path the controller does not have, so its claim is
asserted directly instead (one attempt at the stage that missed, nothing after, read off the
archived records). Recorded rather than padded to 12.

**19 cases across those 11 paths**, because a ranged row pinned at one end proves little: a row
covered only at its low end passes a controller that never retries, only at its high end one that
always does. The ranged rows are listed explicitly — the first attempt inferred them from a hyphen
in the label and matched `thin-preflight`, a row with no range at all — and that check found a real
hole: `fat exhausted` was covered only at 3 calls, so a controller burning a spurious thin retry
before every fat stage would have passed that row.

**Reaching the archive without presupposing the audit-delivery answer.** `graph_search` builds the
payload on every path and does not return it, delivery being the open owner question. The harness
wraps `build_audit_payload` and `assert_result_contract` in `search`'s namespace with pass-through
recorders, so nothing about the production signature is assumed and the tests survive whatever
delivery is ratified.

**Verified to be an independent oracle**, not a restatement of P2.4's: mutating `stage_call` to burn
one spurious retry per stage fails 42 cases in this file alone.

### P2.6 — `replay.py` → `test_replay.py` — **DONE** (+22 tests, mutation 14/14)
- [x] Record replay (default): integrity hash validated, **no calls, no body reads** — pinned
      structurally rather than by assertion: `replay_record(audit)` takes neither a `call` nor a
      `body_reader`, so a mode that *cannot be handed* a selector cannot invoke one.
- [x] Historical selector re-call (opt-in): **archived rendered bytes + manifest only**, stamped
      `historical_recall`. Documented at the call site: this path **bypasses the projector and the
      budget preflight by construction** — its bytes are historical. Wiring it through the normal
      path would produce different bytes and silently defeat the mode.
- [x] #119 byte-pinning survives: caller-supplied `context_snapshot=` writes no record (H8) —
      **the bullet is misfiled and its disposition is now recorded in code.** `context_snapshot` is
      `build_context_snapshot`'s, on the COMPILER side (blueprint §3.2); `kdb_search` has no such
      parameter anywhere and adding one to satisfy the bullet would invent exactly the
      consumer-specific coupling R2 forbids. Asserted as an absence across `graph_search`,
      `replay_record` and `recall_stage`, so a future reader finds the answer rather than the
      question.

**Two decisions the bullets left open, both settled by reading §5.2 rather than inferring:**

- [x] **Record replay returns `ReplayedSearch`, not a `GraphSearchResult`.** §5.2's words are "the
      persisted historical selection", and that is precisely what the archive holds:
      `SearchAuditPayload` carries a `SearchResultSummary` plus `execution`, so **six** of
      `GraphSearchResult`'s seven fields reconstruct exactly and `telemetry` does not reconstruct at
      all. Parts of it could be derived (space size from the manifest, title-only counts from the fat
      evidence, retry counts from the record count) but **`budget_records` genuinely cannot** — the
      pre-flight verdicts were never archived. A result carrying `budget_records=()` reads as "the
      estimates were taken and were zero", not as "this is a replay", and would enter the D5
      calibration series as a measurement. The narrower type says where the data isn't.
- [x] **Re-call passes an explicitly *archival* `BudgetVerdict`** (all figures zero, `fits=True`).
      `stage_call` requires a verdict, and synthesizing a realistic one would write invented
      `budget_estimate_tokens` into a fresh record. Note what is deliberately **not** zeroed:
      `selector_window` comes from the route being called *now*, which is the variable the A/B is
      changing — the one figure on such a record that means something.

**`stage_call` needed no re-call accommodation**, which is the P2.3 design paying off: it takes
`messages` as a parameter rather than rendering internally, so the archived `RenderedMessages` feed
straight through and "bypasses the projector by construction" is literally true rather than a bypass
hack. Re-call therefore inherits the whole attempt/retry/stop-reason contract instead of becoming a
second place for D9.3 to drift.

**Fat's re-call pool is the archived EVIDENCE, not the manifest.** Above M the two differ — the fat
stage only ever saw thin's retained pool — and validating a re-call against the full manifest would
accept a slug the selector was never shown, quietly widening the closed-world guarantee the original
run had. Thin's pool *is* the manifest; both directions are tested.

### P2.7 — adversarial fixtures + close-out → `test_adversarial.py`
- [x] H01 / H02 evidence-side injection (system-block precedence: evidence is subject matter,
      never directives) — 5 payloads × both sides, each a **different mechanism** rather than a
      variation: an imperative (the spec's own example), a forged section header, a forged block
      delimiter, a template slot, a forged system turn.
- [x] H03 query-side (P10) — the query-side indent guard fixture, over every unbounded field rather
      than `summary` alone, plus the end-to-end case showing an injected query reaches the QUERY slot
      and cannot appear in the evidence region.

**Each fixture asserts TWO things, and the second is the one that matters.** We cannot make a model
ignore an instruction; what is ours is (1) **structural containment** — injected text arrives as
content, at content indent, with the SYSTEM half byte-identical to the template and no slot
substituted — and (2) **output-side fail-closed**: every fixture *also* scripts a selector that
**obeys** the injection, and asserts nothing foreign leaves the function. Testing only (1) proves the
prompt is tidy while leaving a compromised selector unexercised; testing only (2) proves the
validator works while letting the prompt structure rot. Spec §1.1's guarantee is output-side for
exactly this reason.

**One assertion had to be rewritten after it failed for the right reason.** The first pass tested
"no `QUERY:` at column 0" — which fails on a *clean* render, because the template legitimately has
one there. The checkable claim is that an injection cannot **add** one, so every structural fixture
now compares against a benign control render. Same for the block delimiter: the block legitimately
closes with `  """` per entity, so the assertion is that the injected one is the only `"""` at
*content* indent.

**One recorded non-finding:** `Hit.title` carries the space's value verbatim, line breaks included.
Sanitization is a **render-side** containment measure (`_single_line`), deliberately not a mutation
of the data — a search result that silently rewrote a title would report something the vault does not
contain. Containment governs the prompt; the result reports the world.
- [x] **H04 — the identity-line indent asymmetry. FIXED in P2.1a (Joseph authorized 2026-07-27),
      not deferred to a fixture here.** Found while writing P2.1a, then made codex's F2.
      `projection._scalar_lines` splits a field value on `"\n"` and indents every continuation line,
      so an injected `"""` or section header renders as content and cannot terminate or forge a
      block. **`render_thin_line` did neither** — it interpolates `slug`, `title` and `page_type`
      into a single f-string, none of them sanitized — so a title containing `\nQUERY:` injected an **unindented** line into the evidence
      block, the one position P10's structural guard relies on, and every line-based claim about the
      block was false for that input (including `test_prompts.py`'s own).
      **Why fixed rather than fixtured, against the original filing:** (i) it is **byte-neutral on
      today's data** — 0 of the 163 fixture titles carry a line boundary, so no golden pin moves and
      no fixture regenerates, which was the whole reason for deferring; (ii) the escape collapses one
      character to one space, so it is **character-count preserving and UTF-8 non-expanding** even on
      pathological input and no ceiling or exact maximum can move because of it (round 1 claimed
      *byte-count preserving*, which codex R3 correctly refuted: `"\u2028"` is 3 UTF-8 bytes and becomes
      1, so the render can only shrink — which is the property the ceilings need); (iii) a fixture alone tests the defect without
      removing it, and a harder template delimiter does not help — an unescaped title forges that
      too. (iv) codex's stated rationale is wrong in one respect worth recording: *KDB-authored*
      titles were already safe (`compiler.page_writer.emit_frontmatter` raises on a newline in any
      frontmatter string, `compiler/tests/test_page_writer.py:116`). The open channel is
      **hand-authored ingested notes** — `yaml.safe_load` at `common/source_io.py:39` →
      `kdb_graph/intake.py:325`, no single-line check — which is precisely the 1,586-note vault
      queued next. Same conclusion, different path.
      Implemented as `projection._single_line`, applied to **all three** interpolated fields — `slug`,
      `title` and `page_type` (the round-1 pass exempted `page_type` on the strength of a `Literal`
      annotation, which codex R1 correctly called out as a type hint, not a runtime check) — over the
      **full `str.splitlines()` boundary set** (not just `\n\r`) so the invariant is stated in the terms
      every line-based test reasons in. 50 regression tests, every field × every boundary; the anomaly is deliberately **not**
      counted — no consumer, and unlike `delimiter_collision_guard` the anomaly is removed rather
      than left in place.
- [x] Full suite green; mutation-check the two behaviours with no other coverage (the D10 ordering
      assertion and the stop-reason normalization) per standing repo practice — **8/8 caught**, the
      two named behaviours plus four P10 containment mutations that the new fixtures are what catch
      (identity fields no longer single-lined; excerpt lines no longer indented; single-pass
      substitution replaced by sequential `str.replace`; query-block continuation lines unindented).
      Both D10 swaps are caught at both stages.
- [x] Update `docs/TASKS.md`, this plan's checkboxes, and blueprint §11's P2 row on closure

## P2 CLOSED — 2026-07-28

Repo suite **2,513 → 3,021**. Every sub-phase P2.0–P2.7 closed, every behaviour mutation-swept
(P2.1f 12, P2.2 18, P2.3 28, P2.4 27, P2.6 14, P2.7 8), and the §8 branch table verified as an
oracle independent of the flow tests that produced it.

**Two items carried OUT of P2 for the owner, neither blocking:**

1. **The audit-delivery surface.** `graph_search` builds `SearchAuditPayload` on every path and does
   not return it — ratified §1.1 fixes `GraphSearchResult` at seven fields and `audit` is not one, so
   blueprint §2.1's "audit (always, §6)" is an obligation, not a field. Only
   `telemetry.search_snapshot_hash` is surfaced. **The adapter (P3a) needs the whole payload to write
   its envelope**, so a surface has to be decided; it changes a public signature, which wants a
   ratification rather than an inference. Nothing built in P2 presupposes an answer — P2.5 and P2.6's
   tests reach the payload through pass-through recorders and survive any choice.
2. **`FAT_INPUT_ESTIMATION_MISS_ON_F1`** — the matrix extension added in P2.4 for a reachable state
   the ratified text has no row for. Marked EXTENSION, NOT RATIFIED TEXT in its own note.

**Also still open from P2.1a, off the critical path:** `SYSTEM_TEMPLATE_BUDGET_BYTES` 3,072 → 4,096
(74 B headroom; both reviewers recommend it, blueprint v0.15 first).

**Next gate: D5 calibration — Joseph fires it** (§7 usage-reported measurement, one non-comparative
call per candidate, 3-call ceiling; measurements to the sibling calibration artifact, fixture
manifest untouched). P2.1f's pins are frozen, which was its precondition.

### Gate — calibration (end of P2, **Joseph fires** — D5, ledger #11)
- [x] **Harness built and dry-run verified** — `tools/task123_calibrate_estimator.py`
      (+27 tests, mutation 16/16). Dry run is the default and `--fire` is required to spend;
      the 3-call ceiling is an object that raises rather than a loop that happens to run three
      times; the artifact is rewritten after every candidate so a late failure cannot lose an
      earlier paid measurement; the checksummed fixture is fingerprinted before and after and
      asserted unchanged.
- [x] **Prose review published for the owner** — `docs/superpowers/specs/2026-07-28-task123-selector-prompt-prose-review.md`,
      both fully-rendered templates plus the one input decision calibration needs (the query slot).
- [x] **Prose review LANDED 2026-08-02 (Joseph).** Three findings absorbed; both templates
      re-versioned `_v1` → `_v2`; `GOLDEN_DIGESTS` moved; blueprint **v0.15** raised
      `SYSTEM_TEMPLATE_BUDGET_BYTES` 3,072 → 4,096 (the fix did not fit in 74 B).
      **Correction, from the round-1 panel (codex F1 ≡ kimi F1, both independently):** the
      "invalidates three paid measurements" clause above was **wrong for FAT**. The calibrator
      renders **thin only** (`tools/task123_calibrate_estimator.py:199-201` — `render_thin_line`
      + `render_thin_messages`; there is no fat call site in the file), so a **fat-only** prose
      change costs a `_v3` bump and a re-pin but does **not** invalidate any paid measurement.
      Only a **thin** change does. This materially lowers the cost of the open fat-precision item.
- [x] §7 usage-reported measurement, one non-comparative call per candidate (3-call ceiling) —
      **FIRED 2026-08-02. GATE FULLY DISCHARGED — the ruling is no longer provisional.**
      gemini-3.6-flash 4,542 tok / **3.7127** B-per-token; deepseek-v4-flash 4,481 tok /
      **3.7632**; gpt-5.4-mini 4,402 tok / **3.8308** (first attempt 429 `insufficient_quota`;
      re-fired after credits, merged in by the D5 artifact merge guard, which preserved both
      already-paid rows through a run in which every call failed — its first real exercise).
      Worst measured under-estimate **1.077x** against the **1.25x** headroom; failure threshold
      is **3.20** B/token. **`ESTIMATOR_BYTES_PER_TOKEN = 4` STANDS.** Note the unmeasured
      candidate turned out to be the *least* dense of the three, so codex F4's
      cross-provider-extrapolation objection pointed at the safest route — the objection was
      right to raise and the answer was benign.
      **FOURTH FAMILY ADDED 2026-08-02 — `qwen3.7-flash` 4,448 tok / 3.7911.** Four
      *independent tokenizer families* (Google, DeepSeek, Qwen, OpenAI) now span just
      **3.7127–3.8308 — a 3.2% spread**, 16% clear of the 3.20 threshold. codex F4's
      objection was precisely that one family cannot predict another; four clustering this
      tightly is the strongest available answer to it. The call also confirmed
      `enable_thinking: false` empirically and closed the DashScope non-streaming watch-item.
      **`gpt-5.6-luna` rejected on the same run** (registered, fired, removed): a 400 —
      exhausted the entire 36,000-token thin envelope without finishing, D9's selector-admission
      signal. Recorded in `docs/reference/model-provider-api-calls.md`; not left in the pool.
- [x] Measurements persisted to the **sibling calibration artifact** — fixture manifest untouched
      (fingerprinted before and after, asserted unchanged): `benchmark/truth/task123_search_calibration_v1.json`
- [x] **#126 sequencing — RULED 2026-08-02 (Joseph): empty-slot calibration SATISFIES D5.**
      #126 is on record as "a prerequisite of the **D5 calibration gate** and **P5a**, which
      consume real keys". D5 was fired with the **empty query slot**, so it consumed **no** keys —
      the dependency is *sidestepped*, not violated, and the measured density is the slug-heavy
      (conservative) end since a real query block adds ≤ 4,096 B of prose, which tokenizes nearer
      4. Joseph's ruling: *"3.713 is as good as 4… the matter of fact is that we don't know… we
      need to keep the stats for the real ratio when we run the tests end-to-end."* **No re-fire.**
      The prerequisite is retained for **P5a**, where key *content* is load-bearing for selector
      quality; it was over-applied to D5, where only byte density matters and the keys are
      ≤ 1,280 B of a ~21 kB request, changed in content rather than volume.
      **Superseding follow-up:** the synthetic gate is replaced as the primary evidence by
      **live bytes-per-token telemetry** — a frozen fixture can only characterise the frozen
      input, whereas every real call measures the true evidence+query blend at production's own
      mix. Filed separately; `budget_estimate_tokens` is recorded today but the provider's
      *actual* input tokens are not, so the ratio is not yet derivable from a run.
- [x] Requires P2.1f frozen first (calibration is against the pinned prompts) — frozen

**Figures at the v2 pins** (empty query slot, 163 identities): rendered **16,863 B** = system
2,460 + user 14,403; ÷4 estimate **4,216 tokens**; all three D4 candidates pre-flight `fits`.
(The pre-v2 figures were 16,849 B / 4,213 tokens.)

**The prediction, and how it resolved.** Recorded before the run so it could not be rationalized
afterwards: slug-heavy identity text would tokenize nearer **3** B/token than 4, showing the
estimator to **underestimate** — an underestimated guardrail authorizes a request it was meant to
block. **Direction held; magnitude did not.** Measured ~**3.74** B/token, so the shortfall is
~**6-8%** (~1.07x), not the predicted 33% (1.333x) — and the 0.8 headroom absorbs 1.25x, so the
guard holds. Re-worked at each candidate's own pre-flight boundary both **fit** (901,529 vs
1,048,576; 848,515 vs 1,000,000). The "authorizes a request that does not fit" claim is
**withdrawn on evidence**; `ESTIMATOR_BYTES_PER_TOKEN = 4` stands, provisionally.

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

**`SELECTOR_PROMPT_VERSION` shipped as `SELECTOR_FAT_PROMPT_VERSION`** (spec §2.1 names the fat
constant without a stage word, and `SELECTOR_THIN_PROMPT_VERSION` with one). Recorded rather than
left silent, because it is a rename of a name in ratified text: the stage word makes the pair
symmetric, and both constants are **derived from their filenames** rather than declared, so neither
is a figure that can drift. A spec sync can adopt the stage word at the next amendment — no
behaviour depends on it.

**`render_fat_messages` takes `max_results` with no default.** The prompt states the cap and
`validate_response` counts `over_cap` against `request.max_results`; a default would let those two
disagree silently, charging the selector for a rule it was told differently. Thin's `retention_cap`
keeps its `M` default — that one genuinely is always `M`.

**The golden pin is split from the loader (P2.1a/P2.1f).** Recorded as a sequencing decision, not a
scope change: both items still land inside P2, and P2.1f still precedes the calibration gate.
