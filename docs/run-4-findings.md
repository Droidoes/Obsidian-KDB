# Run-4 findings (live observations + follow-up changes)

Running notes from the run-4 attended run (2026-05-31). Each finding → a scoped
follow-up change (spec/plan after the run completes).

---

## Finding 1 — Pass-1: coerce benign shape deviations, don't reject

**Observed (source 5/36, `…/Graph RAG/GraphRAG for Adaptive KB - Gemini3.1.md`):**
```
Pass-1 attempt 1/2 failed: Pass-1 LLM content invalid at entity_search_keys:
[13 keys] is too long
```
The LLM emitted **13** `entity_search_keys`; the schema caps at **≤10** (`maxItems`),
so Stage-1 validation rejected the whole envelope and burned a retry (and risks a
quarantine if the retry also over-emits).

**Decision (Joseph, mid-run):** this is **not an invalid response** — it's a benign
over-supply. The runner should **take the first 10 and move on**, not declare invalid.

**Principle:** Pass-1 post-processing should **coerce** recoverable shape deviations and
reserve hard reject → retry → quarantine for **genuinely unrecoverable** content.

**Audit of every Stage-1 "invalid" case** (`kdb_compiler/ingestion/pass1_schema.py`,
`build_content_schema` / `validate_llm_content`):

| Case | Today | Proposed |
|---|---|---|
| `entity_search_keys` > 10 (`maxItems`) | reject | **coerce: truncate to first 10** |
| `confidence` outside [0.0, 1.0] | reject | **coerce: clamp to [0,1]** |
| missing nullable (`author`, `uncertainty_reason`, `reject_reason`, `other_reason`) | reject ("required") | **coerce: default null** |
| `kdb_signal` not `signal`/`noise` | reject | keep reject (core binary judgment) |
| `domain` off 23-ID vocab | reject | keep reject — *watch:* fuzzy-map/catch-all if frequent |
| `source_type` off 21-ID vocab | reject | keep reject — *watch* (as domain) |
| missing core field (`kdb_signal`/`domain`/`source_type`/`summary`) | reject | keep reject |
| gross type error (e.g. `summary` not string) | reject | keep reject |
| `source_type='other'` and `other_reason` null (OQ-NW7-7) | reject | **coerce: let pass (default null)** — Joseph 2026-05-31. `other_reason` is an audit field (Pass-2 ignores); a missing "why other" note isn't worth a reject/retry. Tradeoff: loses the OQ-NW7-7 vocab-evolution signal *when the LLM omits it* (still recorded when supplied). Drop the hard cross-field rule in `_validate_against`. **Observed live 29/36 (Berkshire Hathaway 2023 mtg): attempt 1 rejected, retry recovered → wasted one call; the coerce change would skip that retry.** |

**Mechanism:** add a `normalize(payload)` step in `pass1_caller` **before**
`validate_llm_content` — `entity_search_keys = entity_search_keys[:10]`, clamp
`confidence`, null-fill missing nullables. Genuinely-invalid cases still fail and retry.
The truncation is lossless to correctness (the schema's own comment notes extra /
imperfect slugs just miss the Entity.slug PK lookup harmlessly).

**Status:** captured; implement as a scoped change after run-4 (brainstorm → spec → plan).

---

## Finding 2 — Pass-2 quarantine (cause TBD)

**Observed (source ~10/36):**
```
pass-2 compile…
⚠ source_quarantine: AIML/Programing-Algorithm/Algorithm/Relative Ranking
Methods - Borda, Condorcet, and Aggregation.md — Pass-2 compile failed
```
Quarantine-and-continue worked (run advanced to 11/36, no abort). **Cause unknown
from the line** — diagnose post-run:
- `state/runs/<run_id>/orchestrator_events.jsonl` → the `source_quarantined` event's
  `failure_stage` / `exception_type` / `error`.
- `state/runs/<run_id>/pass2/…` → the preserved raw LLM response for that source.

**Candidates:** (1) malformed-JSON / schema failure on a dense doc (same *class* as
run-2's Canonical Ontology `JSONDecodeError`, fixed by json_mode `1d668bf` — check if
this is a different failure mode); (2) low-prior — #103 domain-scoping (but a smaller
context yields *fewer links*, not a compile *failure*). Confirm from the log, don't guess.

**RESOLVED — exact cause:** `JSONDecodeError: Invalid \escape: line 28 col 177`. The
Pass-2 LLM wrote **LaTeX inline-math `\(n-1\)` into the `body` JSON string** — `\(` is
**not a valid JSON escape** (valid: `\" \\ \/ \b \f \n \r \t \uXXXX`), so the parse died.
It should have emitted `\\(n-1\\)`. `stop_reason=stop`, `token_overrun=False`, 1 attempt
→ a clean JSON-**escaping** defect, not truncation. **Not a
#102/#103 regression** — a Pass-2 LLM JSON-output defect (same *class* as run-2's
`JSONDecodeError`, distinct cause: bad escape vs truncation).

**Key signal:** the *same source compiled cleanly in run-3* — same model, same input.
So this is **LLM JSON-emission non-determinism** on math-heavy content, not deterministic.
→ strongest case yet for a **Pass-2 parse-retry** (the run-3 memory deferred it at n=0;
we now have n≥1, and a re-call would very likely yield valid JSON — [[data-before-principle]]).

**Follow-up (Finding 3):** Pass-2 robustness to invalid-JSON emissions.

*Code facts (verified):*
- `compiler.py:376-381` — on `json.loads` `JSONDecodeError`, Pass-2 `_set_failure(parse)`
  and returns immediately. **No re-call.** (Pass-1 *does* retry its content validation —
  the `attempt 1/2` loop.)
- `call_model_retry.call_model_with_retry` retries **only `_RETRYABLE` SDK errors**
  (transient network/rate-limit), not parse/schema failures — those happen after the
  call returns and are terminal.
- `response_normalizer.py` is **extraction-only** ("strict JSON extraction. No semantic
  repair.") — strips fences + finds the JSON block (`extract_ok=True`) then plain
  `json.loads`. It does **not** repair malformed JSON. So there is **no** JSON-repair
  function today (the thing one might assume exists).

*Options for the change:*
1. **Parse/schema-failure retry** (re-call the model 1–2×, mirroring Pass-1; feed the
   error back — "invalid escape, escape backslashes") — Joseph's lean ([1]). Robust;
   the same source compiled in run-3, so a re-call would very likely succeed.
2. **Deterministic JSON-escape repair** (double any backslash not forming a valid JSON
   escape, before parse) — free, fixes *this* exact case, but reverses the normalizer's
   deliberate strict/no-repair stance; can mask deeper malformations.
3. **Prompt discipline** (instruct Pass-2 to escape backslashes / avoid raw LaTeX in
   JSON strings) — cheap complement.

Lean: **(1) parse-retry**, optionally + (3); (2) only if measured retries still fail.
Scoped change after the gate call (brainstorm → spec → plan).

**RESOLVED (Joseph 2026-05-31): option (1) — retry Pass-2.** On a parse/schema failure,
re-call the model (mirroring Pass-1's validation retry), optionally feeding the error
back; **no JSON-repair function**. The same source compiled in run-3, so a re-call would
very likely succeed.

