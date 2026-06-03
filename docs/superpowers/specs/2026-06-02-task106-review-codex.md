# Task #106 Design Review — Codex

## Verdict

`GO-WITH-CHANGES`

The design is close enough to turn into an implementation plan, but I would not proceed until the rung-1 mechanism and compiler-loop integration are tightened.

## (a) correctness/safety of the design

### [Severity: High] · spec §3 / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:44-48`; code `compiler/validate_source_response.py:58-97`

**Flaw:** Rung 1 should be targeted escaping, not broad `json-repair` as the primary production fix.

**Why it matters:** The spec correctly identifies the content-fidelity hole: schema/semantic gates do not validate body content. The live failure class is specifically invalid JSON string escapes like `\(`. A general-purpose repair library may insert/delete punctuation or alter string content in ways that still pass schema and semantic validation. The current semantic check only verifies `source_name`, `summary_slug` presence, and the single matching summary page; it does not validate body fidelity.

**Concrete suggested change:** Make targeted stray-backslash escaping the rung-1 production mechanism: escape `\` only when followed by a non-JSON-escape character inside JSON text, then re-parse. Optionally keep `json-repair` only as a probe/shadow tool or reject it for production until live evidence justifies broader repair.

### [Severity: High] · spec §2/§5 / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:38,83`; code `compiler/compiler.py:305-337`

**Flaw:** Repairs must be applied on a candidate copy, not directly to `state["parsed_json"]`.

**Why it matters:** If slug coercion mutates the parsed payload and then schema/semantic still fail, the failed repaired payload can leak into resp-stats and parsed summaries. That weakens forensic value and can make an unrecoverable emission look partially accepted.

**Concrete suggested change:** Parse raw emission into an attempt-local candidate. Repair a deep copy. Only assign `state["parsed_json"]` after the candidate passes the acceptance gates. If repair fails, keep the original failed candidate for error evidence or record both original/repaired summaries explicitly.

### [Severity: Medium] · spec §4a/§5 / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:57-59,83`; code `common/paths.py:63-71`, `compiler/validate_compile_result.py:232-255`

**Flaw:** Per-call validation does not enforce reserved slugs.

**Why it matters:** A collapse like `index--` to `index` can pass per-call schema/semantic, because reserved-slug checks currently live in aggregate compile-result validation. If the repaired candidate is accepted inside `compile_one`, it may skip the retry opportunity and then fail later at the aggregate validation stage.

**Concrete suggested change:** Either make `collapse_slug` return only slugs accepted by `paths.validate_slug()` for non-summary fields, or make the rung-2 acceptance gate run the same hard-zero single-source checks before accepting a repaired candidate.

## (b) scope & conservatism calls

### [Severity: Medium] · spec §4c / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:73-74`

**Flaw:** Collision policy needs to distinguish defining slugs from reference-only slugs.

**Why it matters:** Two page-defining slugs collapsing to one is a real conflict and must be refused. But a malformed reference-only slug collapsing into an already-defined emitted page may be a benign repair. The current text says "two distinct slugs map to the same new slug" without defining the universe precisely enough for implementation.

**Concrete suggested change:** Explicitly define collision scope. Refuse collisions among definitions: `summary_slug`, `pages[].slug`, and the page-derived concept/article definition set. For references (`outgoing_links`, body wikilinks, `log_entries[].related_slugs`), allow collapse only when the target resolves to exactly one emitted definition and no two emitted definitions collide.

### [Severity: Low] · spec §4b / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:69`; code `compiler/schemas/compiled_source_response.schema.json:29-31,99-113`

**Flaw:** The slug-bearing field list includes a stale/nonexistent field.

**Why it matters:** In the live per-call schema, `warnings[]` are strings, not objects with `related_slugs`. Including `warnings[].related_slugs[]` can send implementation work toward a nonexistent contract.

**Concrete suggested change:** Remove the parenthetical "and any `warnings[].related_slugs[]`" or mark it as future-only. The rest of the listed slug-bearing fields match the live per-call schema.

## (c) placement/integration with the real compiler flow

### [Severity: High] · spec §5 / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:80-83`; code `compiler/compiler.py:322-347`

**Flaw:** The "schema + semantic" re-validation gate is not available at the proposed insertion point without reshaping the loop.

**Why it matters:** Today semantic validation runs only after the attempt loop breaks. If rung 2 fires inside the schema branch, the spec's promised schema+semantic re-validation requires factoring semantic validation into the attempt loop. Otherwise a slug-coerced candidate can be accepted after schema validation and fail semantic after the retry opportunity is gone.

**Concrete suggested change:** Introduce an attempt-local helper, for example `validate_candidate(candidate, source_name)`, that runs schema and, only if schema passes, semantic. Use that helper for clean emissions and repaired candidates inside the attempt loop before deciding retry vs accept.

### [Severity: High] · code `compiler/compiler.py:174-184,242,305-337,421-444`

**Flaw:** Existing per-attempt state can go stale across retries.

**Why it matters:** `parse_ok`, `parsed_json`, and schema fields live across attempts. A first attempt can parse but fail schema, then a final attempt can fail parse while `parse_ok`/`parsed_json` still reflect the previous attempt. #106 touches exactly this loop, so it should fix the stale-state class rather than layering repair on top of it.

**Concrete suggested change:** Reset attempt-local gate state each iteration. Copy final accepted state into `state` only on success, and copy final-failed state deliberately on terminal failure.

### [Severity: Medium] · spec §4b / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:68`; code `compiler/validate_source_response.py:100-124`, `compiler/repair.py:153-176`, `compiler/canonicalize.py:308-333`

**Flaw:** Body wikilink rewrite must use whole-token remapping that can see malformed slugs.

**Why it matters:** `body_wikilink_slugs()` only extracts valid kebab-case links, so it ignores links like `[[foo---bar]]`. Later, `reconcile_body_links()` rebuilds `outgoing_links` from body tokens. If body rewrite misses malformed links, the metadata can be repaired and then overwritten from the unrepaired body.

**Concrete suggested change:** Reuse or adapt the canonicalizer's whole-token rewrite pattern (`_remap_body_wikilinks`) but avoid its broader `_normalize_slug()` behavior. The slug-coercion rewrite should map exact whole `[[target]]` tokens through the conservative collapse map only.

## (d) homes/contract

### [Severity: Low] · spec §8 / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:105-112`; code `docs/CODEBASE_OVERVIEW.md`

**Flaw:** None load-bearing. Proposed homes are sound.

**Why it matters:** `common/paths.collapse_slug()` and compile-structural propagation in `compiler/repair` respect the package contract: `compiler -> common` is legal, and `common` remains a leaf.

**Concrete suggested change:** If the production rung-1 mechanism becomes targeted JSON-string escaping instead of `json-repair`, name the helper after the behavior rather than the package. `common/util/json_repair.py` is acceptable for a generic wrapper, but less honest for a targeted escape-only helper.

## (e) gaps/omissions

### [Severity: Medium] · spec §7 / `docs/superpowers/specs/2026-06-02-json-repair-slug-coercion-ladder-design.md:95-101`; code `common/types.py:406-428`, `common/llm_telemetry.py:146-176`

**Flaw:** Rung taxonomy is not representable in current telemetry and is not mutually exclusive.

**Why it matters:** Current `RespStatsRecord.attempts` is SDK-call retry count, not Pass-2 re-emission count. A source can also be both `repaired-syntax` and `coerced-slug`, or `retried` plus repaired on the second emission. A single enum will under-report multi-step recovery paths.

**Concrete suggested change:** Add explicit telemetry such as `compile_attempts`, `repair_events: list[str]`, and `resolution_path`. Keep `attempts` as SDK retry telemetry to avoid breaking benchmark semantics.

## Bottom line

This design is sound enough to become an implementation plan after the fixes above. The slug-coercion rung is appropriately conservative, but the compiler loop needs a cleaner attempt-local validation structure. My position on the rung-1 fork: do not make broad `json-repair` the primary production mechanism. Use targeted stray-backslash escaping for the known LaTeX failure class, preserve content through decode, and let everything else retry/quarantine unless more live evidence appears.
