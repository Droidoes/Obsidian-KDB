# #114 — Recovery-oriented Pass-2 parse stage (design)

Date: 2026-07-21 · Status: **v0.3.6 ratified** (Joseph, same day; v0.1–v0.3.5
revised after three Codex design rounds + five plan rounds — see §7) · Task: #114

## 1. The principle (the requirement, not background)

**The LLM response is a carrier; the JSON document is the payload. The parse
stage's job is to recover the payload with maximum tolerance for carrier
noise. It may only ever *select* (locate the complete document within
noise) — never *edit* (alter the document's bytes in ways that change the
decoded content). Failure is declared only when (a) no complete decodable
document exists in the response, or (b) the recovered document's *content*
fails the contract — the existing schema/semantic gates. A format
deviation, by itself, never fails a source.**

This is `[[feedback_coerce_dont_reject]]` (#104) restated as a *general
contract* instead of an *enumerated whitelist of tolerated defects*.

## 2. Problem statement

The pipeline polices the carrier at **two** stages, both violating the
principle:

1. **Extract** (`compiler/response_normalizer.py:28-73`) requires the
   response to end in `}` (or a single fenced block) — trailing non-brace
   junk fails the source before parse is even attempted.
2. **Parse** (`compiler/compiler.py:379`) is a binary `json.loads` verdict
   plus an enumerated list of per-class exceptions (backslash escape, slug
   coercion — each patched in after its failure class was discovered live).

Evidence (gemini-3.5-flash cohort runs 2026-07-21, `01-09-32` + `01-46-20`;
every case validated directly through the proposed decoding ladder):

- **19 recoverable failures** — a complete, valid JSON document present in
  the response: 15 with a lone duplicated `}` tail, 3 with a repeated
  closing-fragment tail, 1 that failed at the *extract* stage
  (`Callouts.md`; complete 3,223-char document + 19-char tail). Observed
  decoder-boundary tail lengths: 2/19/20/22 chars.
- **1 genuinely incomplete response** (`Negative cash-conversion cycle.md`)
  — stops mid-structure at `"warnings": []` with no closing `}`;
  `raw_decode` fails at end-of-input. Notably `stop_reason: STOP` — the
  model simply stopped. This is a true "no complete document" case:
  retry-class, not recoverable.

## 3. Design

### 3.1 Extract stage: loose unwrap; `extract_ok` demoted to telemetry

The extract stage's contract changes from "accept only these shapes" to
**"unwrap known wrappers, return the candidate"**:

- Strip a single fenced block if clearly present (existing fence logic,
  incl. the parse-based disambiguation for ``` inside string values).
- Anything else is returned as-is (stripped) — prose, trailing junk,
  multiple blocks are carrier noise for the *recovery* stage, not
  extract-stage failures.
- Selection rule: **the ROOT JSON value wins — root value first,
  prose-only first-`{` fallback, no scanning** (§3.2's root-preserving
  rule; a non-document or undecodable root is retry-class).

**`extract_ok` keeps its meaning — strict carrier-shape conformance (the
old `extract_json_text` verdict: bare object or single fenced block,
starts `{` ends `}`) — but becomes non-gating telemetry.** It stays on the
record as the per-source carrier-discipline signal. `failure_stage="extract"`
is retired from new records (the #25 stage literal remains for historical
records); existing compiler tests encoding strict-rejection behavior are
updated to the new contract.

### 3.2 Recovery path — one shared function, explicit composition order

**Shared API (pinned, Codex v0.3 F1):** the complete raw-response operation
lives in one function used by both `compile_one` AND `tools/replay.py`:

```python
recover_json_response(raw_text: str) -> RecoveryResult
```

It owns: loose unwrap (§3.1), strict-shape evaluation (`extract_ok`), and
the 5-step ladder below. `RecoveryResult` carries: the parsed object (or
None), `extract_ok`, `syntax_repaired`, `boundary_recovered`,
`prefix_discarded_chars`, `tail_discarded_chars`, and the terminal parse
error (for resp-stats). **Retries, `stop_reason`/truncation composition,
schema, and semantic handling stay with each caller.** Because unwrap and
strict-eval are inside the shared function, `compile_one` and replay
cannot derive different candidates or different `extract_ok` values for
the same captured response (parity test, §5).

The 5-step ladder, on the unwrapped candidate:

1. **Clean-decode the original candidate** — `json.loads`.
2. **Boundary-decode the original candidate** — root-preserving decode
   (the ROOT value at the first non-whitespace value-start; prose lead
   falls back to the first `{`); accept the complete root document.
   Sets `boundary_recovered` with prefix/tail counts.
3. **Escape-normalize** — `escape_stray_backslashes` (existing rung-1).
4. **Clean-decode the normalized candidate** — sets `syntax_repaired`.
5. **Boundary-decode the normalized candidate** — sets `syntax_repaired`
   AND `boundary_recovered` (the composed case).

Selection always precedes normalization: a document recoverable without
edits is never edited. Failure of all five → existing retry path
(`_MAX_COMPILE_ATTEMPTS = 2`) → quarantine.

**Recovery returns ANY complete JSON value** (v0.3.2, Codex plan round):
a decoded non-object (e.g. a top-level list) is a complete document and is
RETURNED, not rejected as "no complete document" — the top-level-object
contract is content, and content is judged by the schema gate. This keeps
existing telemetry honest (a fenced list fails schema, as today) instead of
reclassifying it as a parse failure.

**v0.3.3 hardening (Codex plan round 2):**

- **Explicit success signal.** JSON `null` decodes to Python `None`, which
  collides with a `parsed=None` failure sentinel. `RecoveryResult` carries
  `recovered: bool`; `parsed=None` WITH `recovered=True` means JSON null
  (schema then rejects it as content). Callers branch on `recovered`,
  never on `parsed is None`.
- **Root preservation.** Boundary-decode decodes the ROOT value: when the
  first non-whitespace character begins a JSON value (`[`, `"`, digit,
  `-`, `{`, or a letter-run matching a `true`/`false`/`null` literal in
  **either direction** — prefix-of-literal (`nul` = attempted root) or
  literal-led (`nulljunk` = root + adjacent-noise tail)), decode exactly
  there; if that fails, the answer is `None` — never scan into a nested
  `{` (no lifting an object out of a top-level array, no bypassing a
  failed root). Only a prose lead (the leading word is neither a literal
  prefix nor literal-led) falls back to the first `{`.
- **Coercion guarded to dicts.** After a schema failure,
  `coerce_slugs_and_propagate` is only invoked when `parsed_json` is a
  dict — list/scalar/`null` payloads go schema-retry → quarantine without
  `AttributeError`.

### 3.3 Truncation guard moves after recovery (behavior change, ratified)

`stop_reason in ("max_tokens", "length")` is carrier metadata, not proof
that no complete document exists. New order:

1. Run the full recovery path (§3.2) FIRST.
2. If a document is recovered → proceed to schema/semantic gates as
   normal. `stop_reason` is persisted on the record either way, so the
   truncation signal survives in telemetry.
3. If recovery fails AND stop_reason is `max_tokens`/`length` → terminal
   truncation, NO retry (a re-call still won't fit) — same disposition as
   today, reached after recovery instead of before.
4. If recovery fails and stop is normal → retry path as today.

**Behavior change, explicitly ratified:** a truncated-flagged response
containing a complete schema-clean document now succeeds instead of
quarantining.

### 3.4 Telemetry: boundary recovery, measured honestly (Codex v0.2 F3)

`RespStatsRecord` gains additive optional fields (#25 back-compat
pattern):

- `boundary_recovered: bool` — recovery step 2 or 5 fired.
- `prefix_discarded_chars: int` — carrier noise skipped before the
  selected root boundary (leading prose etc.).
- `tail_discarded_chars: int` — carrier noise after the document's
  decoder boundary (2/19/20/22 in the observed corpus).

(Naming settled *before* persisting: `boundary_recovered` covers both
prefix-only and tail-only recovery; `tail_discarded` alone would have
mislabeled the leading-prose case.)

- `final_status = "repaired"` whenever boundary recovery fired (consistent
  with the `syntax_repaired` mapping).
- `PassCallMeasurement` gains `boundary_recovered`; the KPI counters in
  `compiler/kpi/processing.py` count it: `recovery_rate` (survivors
  needing retry-or-repair) and `repair_rung_rate` both gain
  `… or c.boundary_recovered`. A first-attempt boundary recovery is
  visible on the board as a repair event — the model-quality signal is
  preserved, not masked.

**Defaults and status precedence (pinned, Codex v0.3 F2):**

- New records always serialize the new fields — `boundary_recovered:
  False`, counts `0` when recovery did not fire (`to_dict()` serializes
  defaults; they are never "absent" in new records).
- Historical Pass-2 records lack the keys; readers use
  `.get("boundary_recovered", False)` / `.get(..., 0)` (existing
  back-compat pattern).
- Pass-1 measurements: `boundary_recovered=False` (recovery is Pass-2
  only).
- `final_status` precedence (existing convention at
  `compiler/compiler.py:548-560`): schema/semantic/gate failure is
  `"quarantined"` regardless of whether recovery fired; attempt-1 success
  with any repair is `"repaired"`; attempt-2 success with any repair is
  `"retried-and-repaired"`; attempt-2 clean is `"retried"`; else
  `"clean"`.

### 3.5 Safety argument — split by path (Codex v0.2 F5)

- **Unmodified boundary selection** (steps 1, 2): the accepted value is a
  *complete* JSON document decoded without any byte change — nothing
  repaired, only recognized. A wrong-but-decodable prefix is rejected by
  the schema + semantic gates immediately downstream; selection can never
  smuggle content past the content gates.
- **Sanctioned escape-repair** (steps 3–5): `escape_stray_backslashes`
  edits bytes; the #106 invariant is *content-preserving through decode*
  (the parsed strings are identical), NOT byte-invertibility. This is the
  one byte-level normalization the ladder permits.

### 3.6 The hard line (unchanged)

Never *guess structure*: no bracket completion, no string trimming, no
fragment merging — the general json-repair-library behavior rejected at
#106 stays rejected. Selection is safe because the decoded document is
provably complete; guessing fabricates content. The incomplete
`Negative cash-conversion cycle.md` response is exactly this line in
action: nothing to select → retry → quarantine.

## 4. Out of scope

- Pass-1 parse path (100% clean on all five current-gen fires; no
  evidence). The util is reusable there if evidence appears.
- Retry counts, quarantine policy, schema/semantic gate contents.
- Multi-`{` scanning: within the prose fallback, recovery tries the first
  `{` only; a decodable non-document `{` before the real one is
  retry-class (no evidence). Root candidates are never scanned at all
  (a failed root decode is `None`, not a search).

## 5. Tests

- **Curated fixtures (tracked)**: the 20 real captured responses **copied**
  from the gitignored `benchmark/runs/` dirs into
  `compiler/tests/fixtures/` — the suite must not read benchmark artifacts.
- **Positive fixture tests (19)**: 15 lone-brace + 3 fragment + 1
  extract-stage (`Callouts.md`) — all recover to a schema-clean
  `parsed_json` with `boundary_recovered=True`, exact
  `tail_discarded_chars` (2/19/20/22). **All 19 also compile end-to-end
  through `compile_one`** (fake model returning the fixture text, source
  fabricated at the manifest `source_id` so `source_name` matches),
  asserting success and `final_status="repaired"` on the persisted record.
- **Incomplete negative (1)**: `Negative cash-conversion cycle.md` —
  recovery fails at all five steps → retry → quarantine (attempt count 2,
  `boundary_recovered=False`, counts 0).
- **Util unit tests** (`common/util/json_tail_fix.py` —
  `parse_document_prefix(text) -> tuple[object, int, int] | None`
  returning `(value, prefix_chars, tail_chars)` — ANY root JSON value):
  valid+tail → accepted with exact counts; leading prose → accepted with
  prefix count; no `{` → None; unterminated object → None; root
  preservation (array root + tail → whole array; truncated array → None,
  nested object never lifted); scalar roots (`null`, string); literal
  classification (`note:` is prose; `nul` is an attempted truncated root
  and never triggers prose fallback; `nulljunk` decodes root `null` with
  a noise tail); prose fallback tries the first `{` only (garbage `{`
  first → None, no scanning).
- **Negative fixture (schema-wrong prefix)**: complete small object
  followed by the real document → accepted by recovery, rejected by the
  schema gate → retry path. Proves selection does not bypass content gates.
- **Truncation composition**: complete-document + `stop_reason="length"`
  → accepted, `stop_reason` persisted; truncated-document + `"length"` →
  terminal truncation, no retry (attempt count stays 1).
- **Composition order**: response needing BOTH escape-fix and boundary
  recovery → recovered with `syntax_repaired AND boundary_recovered`;
  tail-only response is never byte-normalized (selection-first).
- **extract_ok telemetry**: a **non-brace** trailing-junk response records
  `extract_ok=False` (strict non-conformance) AND succeeds; brace-ending
  junk (lone `}`, fragment tails) is shape-conformant and records
  `extract_ok=True` yet still requires boundary recovery to parse. No new
  record carries `failure_stage="extract"`.
- **Replay parity**: `tools/replay.py` uses the shared recovery function;
  a captured trailing-junk response yields the same verdict via replay as
  via `compile_one`.
- **KPI counters**: `boundary_recovered` counted in `recovery_rate` and
  `repair_rung_rate`; measurement round-trip from RespStatsRecord.
- **Back-compat**: an old-format Pass-2 record (no new keys) reads via
  `.get(..., False/0)` and still measures; a Pass-1 projection reports
  `boundary_recovered=False`.
- **Regression**: existing escape-fix, slug-coercion, retry, quarantine
  tests unchanged and green (strict-rejection extractor tests updated per
  §3.1).

## 6. Validation gate

- Full non-live suite green (new + existing).
- No API fire required — the recovery path is exercised by fixtures; the
  next cohort fires validate it organically.

## 7. Change log

### v0.1 → v0.2 (Codex round 1: `REVISE` — 5 findings, all verified + accepted)

1. **[High] Extract-stage rejection** — strict shape check fails trailing
   non-`}` junk before parse. v0.2: loose-unwrap contract (§3.1).
2. **[High] Telemetry claim wrong** — repair KPIs didn't count tail
   recovery. v0.2: threaded into measurement + both counters (§3.4).
3. **[Medium] Truncation guard contradicts the principle** — terminal
   before parse. v0.2: recovery first (§3.3; behavior change ratified).
4. **[Medium] Composition order undefined** — and "provably invertible"
   was wrong. v0.2: explicit 5-step selection-first order (§3.2).
5. **[Medium] Fixture facts** — corrected counts; fixtures copied into a
   tracked dir (§5).

### v0.2 → v0.3 (Codex round 2: `REVISE` — 5 findings, all verified + accepted)

1. **[High] 20-fixture gate unpassable** — `Negative cash-conversion
   cycle.md` is genuinely incomplete (verified: `raw_decode` fails at
   end-of-input). v0.3: corpus corrected to **19 positives + 1 incomplete
   negative**; tail lengths 2/19/20/22 (§2, §5); same correction in
   `docs/TASKS.md`.
2. **[Medium] `extract_ok`/`failure_stage="extract"` undefined under
   loose unwrap** — v0.3: `extract_ok` = strict conformance, non-gating
   telemetry; `failure_stage="extract"` retired from new records (§3.1).
3. **[Medium] prefix recovery mislabeled as tail discard** — v0.3:
   `boundary_recovered` + explicit `prefix_discarded_chars` /
   `tail_discarded_chars` (§3.4).
4. **[Medium] replay tool would diverge** — v0.3: one shared recovery
   function for `compile_one` and `tools/replay.py` + parity test
   (§3.2, §5).
5. **[Low] safety argument covered only the selection path** — v0.3:
   split selection vs sanctioned escape-repair (§3.5).

### v0.3 → v0.3.1 (Codex round 3: `GO WITH CHANGES` — 4 findings, all accepted)

1. **[Medium] shared recovery boundary underspecified** — unwrap +
   strict-eval would still be duplicated between callers. v0.3.1: pinned
   `recover_json_response(raw_text) -> RecoveryResult` owning the complete
   raw-response operation; retries/`stop_reason`/schema/semantic stay with
   callers (§3.2).
2. **[Medium] defaults + status precedence implicit** — v0.3.1: new
   records always serialize `False`/`0`; historical records read via
   `.get`; Pass-1 reports `boundary_recovered=False`; `final_status`
   precedence pinned to the existing convention
   (`compiler/compiler.py:548-560`) (§3.4); back-compat tests added (§5).
3. **[Low] task ledger retained the disproven "20 complete documents"
   claim** — corrected in `docs/TASKS.md` (19 recoverable + 1 incomplete).
4. **[Low] selection wording vs first-brace rule** — v0.3.1: "the object
   beginning at the first `{` wins if it decodes completely; no
   subsequent brace scanning" (§3.1).

### v0.3.1 → v0.3.2 (Codex plan round: implementation-plan review, `REVISE` — 6 findings, all accepted)

Plan v1.1 (`docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md`)
folded in: winning-attempt reset semantics for `boundary_*` fields
(regression guard `test_compiler.py:1394-1465`); corrected `extract_ok`
truth values (shape-only check — lone-brace/fragment tails are
`extract_ok=True`); compiler-level fixture tests (schema + semantic over
all 19 positives, 3 e2e compile_one cases); pytest run directly (no
pipe-masked exit status); replay test file corrected. **One design-level
amendment (this section):** recovery returns ANY complete JSON value —
a decoded non-object is judged by the schema gate, not reclassified as a
parse failure (§3.2).

### v0.3.2 → v0.3.3 (Codex plan round 2: `REVISE` — 6 findings, all verified + accepted)

Integration defects from the v0.3.2 any-value amendment, fixed in plan
v1.2 and §3.2/§5 here:

1. **[High] JSON `null` ↔ failure-sentinel collision** — `recovered: bool`
   added to `RecoveryResult`; callers never branch on `parsed is None`
   (§3.2).
2. **[High] boundary recovery could lift an object out of a top-level
   array** — root-preserving decode rule: decode at the first
   non-whitespace value-start; a failed `[` root yields `None`, never a
   carved nested object (§3.2).
3. **[High] non-object payloads crash slug coercion** — coercion guarded
   to dicts; list/scalar/`null` go schema-retry → quarantine without
   `AttributeError` (§3.2).
4. **[Medium] architectural public-API assertion** —
   `test_no_semantic_functions_present` updated for `unwrap_response`.
5. **[Medium] acceptance criterion** — all 19 positive fixtures compile
   end-to-end through `compile_one` (not 3 representatives) (§5).
6. **[Low] `extract_ok` wording** — "non-brace trailing junk"; brace-ending
   junk records `extract_ok=True` yet still needs boundary recovery (§5).

### v0.3.3 → v0.3.4 (Codex plan round 3: `REVISE` — 6 findings, all verified + accepted)

1. **[High] value-start classification bug** — matching `t`/`f`/`n` by
   first character misclassified prose like `note:` as a root candidate
   (the v1.2 impl contradicted its own prose test). Fixed: lexical
   `true`/`false`/`null` prefix matching (plan Task 1).
2. **[Medium] superseded first-`{` passages** — §3.1 selection rule, §3.2
   ladder step 2, and the §5 util contract rewritten around "root value
   first, prose-only first-`{` fallback" (this section).
3. **[Medium] incomplete fixture not e2e-tested** — `compile_one` test for
   `Negative cash-conversion cycle.md`: 2 calls, quarantine,
   `parse_ok=False`, zero boundary telemetry (plan Task 6 test 9).
4. **[Medium] `parsed_json` annotations** — widened to `object | None` in
   `build_resp_stats` + `RespStatsRecord` (any-value recovery flows
   through on schema failure) + serialization test (plan Task 4).
5. **[Medium] dataclass field placement** — `boundary_recovered` appended
   after `semantic_ok` in `PassCallMeasurement` (plan Task 7).
6. **[Low] vacuous assertion** — `... is None or True` removed (plan Task 1).

### v0.3.4 → v0.3.5 (Codex plan round 4: `REVISE` — 5 findings, all verified + accepted)

1. **[High] truncated-literal roots bypassable** — `nul {"a": 1}` slipped
   past prefix matching into the prose fallback and returned the nested
   object. Strict root preservation adopted (Codex's option 1): a proper
   PREFIX of `true`/`false`/`null` counts as an attempted root → decode
   failure yields `None`, never a scan (§3.2; regression tests
   `nul`/`tru`/`fals` in plan Task 1).
2. **[Medium] wording pinned** — spec §3.2 + plan Task 1 interface now
   state the lexical-prefix classification explicitly.
3-5. **[Low] bookkeeping** — plan goal references this spec version;
   Task 1 expected count corrected (19); Task 6 test range 3-9.

### v0.3.5 → v0.3.6 (Codex plan round 5: `REVISE` — 4 findings, all verified + accepted)

1. **[High] complete literal + adjacent noise misclassified as prose** —
   `nulljunk {"a": 1}` fell through to the prose fallback and returned the
   later object, though `raw_decode` cleanly decodes root `null` at
   offset 0. Classification is now both-directional
   (`text.startswith(lit, i) or lit.startswith(tok)`): prefix-of-literal
   (`nul` = attempted root) OR literal-led (`nulljunk` = root + noise
   tail); `note:` stays prose (§3.2; regression tests in plan Task 1).
2. **[Medium] stale test comment** — the `'nul'`-alone test no longer
   claims the prose branch.
3. **[Low] spec §5 wording** — "`nul` is an attempted truncated root and
   never triggers prose fallback."
4. **[Low] prefix-telemetry wording** — "characters before the selected
   root boundary" (§3.4).

## 8. Docs on closure

`docs/TASKS.md` #114 row updated; `docs/CODEBASE_OVERVIEW.md` Milestone
Changelog entry per the closure rule.
