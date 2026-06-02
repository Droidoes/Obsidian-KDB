# Task #95 — Two-Stage Validation Sketch

The contract fix splits Pass-1 validation into two stages with code-stamping
between them. Goal: the LLM is asked for **content only**; code owns provenance
and audit; both halves are validated.

## The problem today (one-stage, wrong place)

```
LLM → json.loads → stamp prompt_version+model → validate_envelope(FULL) → apply_overrides
                                                  ▲
                                  validates override/schema_version the LLM
                                  wrongly owns; the FINAL envelope is never validated
```

`pass1_caller.py:62-67` parses, stamps only `prompt_version`+`model`, then runs
the full schema (which requires `override`, `schema_version`, `llm_original`).
`apply_overrides` runs AFTER in `enrich.py` and rebuilds `override` from scratch
— so the LLM's override is validated then discarded. The assembled envelope that
`apply_overrides` produces is never re-validated.

## The target (two-stage)

```
LLM → json.loads
     → validate_llm_content(parsed)          # STAGE 1: the 11 model-owned fields ONLY
     → code stamps: model, prompt_version, schema_version
     → apply_overrides(...) builds `override` block (sole producer)
     → validate_envelope(full)               # STAGE 2: the complete assembled envelope
     → return
```

### Stage 1 — `validate_llm_content(parsed)` (NEW)

The 11 fields the LLM is contractually responsible for:
`kdb_signal, domain, source_type, author, summary, key_themes,
entity_search_keys, confidence, uncertainty_reason, reject_reason, other_reason`

- Same enum/type/`maxItems` rules as today for those fields.
- Keeps the `other_reason` cross-field rule (non-null when source_type=other).
- Does NOT require `override`, `model`, `prompt_version`, `schema_version` —
  the LLM is no longer asked for them, so their absence is correct.
- This is the validation whose failure (if any) triggers the caller's retry.

### Code-stamp step (between stages)

`pass1_caller` (or a small helper) injects the caller-owned fields onto the
parsed dict — same values stamped today, just now ALL of them:
`model`, `prompt_version`, `schema_version`.

### `apply_overrides` — sole producer of `override` (UNCHANGED logic)

Already builds the full `override` block from `kdb_signal` (overrides.py:36+).
After the contract change it is the ONLY place `override` is constructed — the
LLM no longer supplies a copy to discard. **One in-scope cleanup:** the empty-
source and failed paths in `enrich.py` (:140, :171) hand-build `override` dicts
with hardcoded `llm_original`; route them through the same constructor so there's
a single source of truth. (Add an `apply_overrides`-style helper that takes a
`kdb_signal` + path and returns the block, callable from all three paths.)

### Stage 2 — `validate_envelope(full)` (EXISTING, repurposed)

The current full-schema validator, now run on the COMPLETE assembled envelope
(post-stamp, post-override) instead of on raw LLM output. This is the gap-closer:
today nothing validates the final object. Belt-and-suspenders — if a stamping or
override-construction bug ships a malformed block, Stage 2 catches it.

## Where each piece lives

| Concern | File | Change |
|---|---|---|
| Stage-1 schema (11 content fields) | `pass1_schema.py` | NEW `build_content_schema()` + `validate_llm_content()` |
| Stage-2 schema (full) | `pass1_schema.py` | keep `build_json_schema()` + `validate_envelope()`; both stay |
| call flow (parse→S1→stamp→override→S2) | `pass1_caller.py` | reorder; S1 is the retry-gated validation |
| override single-producer | `overrides.py` + `enrich.py` | extract one constructor; 3 call sites use it |
| prompt (stop asking for code-owned) | `pass1_prompt.j2` | DONE (this session) |

## Validation-placement decision (Joseph [4] earlier — now resolved)

We considered a dedicated pre-post-processing `pass1_validation` module vs.
keeping validation inside the caller/post-processing. **Sketch lean: keep it in
`pass1_schema.py` as two functions** (`validate_llm_content` + `validate_envelope`),
called from `pass1_caller`. Rationale: no new module needed; the split is two
small functions, not a new boundary; matches existing structure. The "explicit
rules of what's invalid" Joseph wanted live as Stage-1's content schema + the
cross-field rule — explicit and one place. (Revisit if the invalid-HANDLING
policy from #98 benchmark adds per-field repair — that may justifying a richer
module later, but not now.)

## What this sketch deliberately does NOT decide

- **Invalid-result HANDLING** (coerce vs drop vs fail per field) — still
  data-gated on the #98 benchmark. This sketch only fixes WHAT is validated and
  WHERE; it keeps today's behavior on failure (retry then raise → quarantine via
  #94). Handling policy is a later, separate change.

## TDD test list (write first)

1. `validate_llm_content` accepts an envelope with NO override/model/version fields.
2. `validate_llm_content` rejects bad `kdb_signal` / off-enum `domain` / >10 keys.
3. `validate_llm_content` keeps the `other_reason`-when-other rule.
4. Full flow: parsed content-only dict → stamped + override-built → passes Stage 2.
5. `override` constructor produces identical blocks from success/empty/failed paths.
6. Regression: a real captured response (content-only) round-trips to a valid
   stored envelope identical in the downstream-consumed fields.
