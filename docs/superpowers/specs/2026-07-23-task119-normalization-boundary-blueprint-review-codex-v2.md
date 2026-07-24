# Task #119 normalization-boundary blueprint v0.2 — Codex R7 review

**Date:** 2026-07-23  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-23-task119-normalization-boundary-blueprint.md` v0.2

## Verdict

**REVISE BEFORE PROCEED — close, but two load-bearing contracts remain incomplete.**

The bridge and alias-provenance design are now sound. R6's three high-severity architecture findings were correctly absorbed.

## Findings

### F1 — High: 2.x and 3.x cannot share the same “legacy” replay stack

BQ-1 dispatches both `2.x` and `3.x` through today's validator (`§11`).

Code-history verification shows these are different contracts:

- At `e9ca323`, prompt 2.0.0 required the old shape: `source_name`, top-level `summary_slug`, seven-field pages, logs, and warnings.
- At `f8c9ad8`, prompt 3.0.0 uses the current wiki-native four-field page shape.

Therefore, a genuine 2.x response will be rejected by the 3.x validator rather than receiving an era-correct verdict.

Resolve with one explicit policy:

- retain a frozen 2.x schema/semantic validator and dispatch 2.x to it; or
- support only 3.x and 4.x, making 2.x explicitly unsupported and fail-closed.

Do not label 2.x replay “era-correct” while using the 3.x boundary.

### F2 — High: live telemetry and KPI semantics remain undefined

The blueprint says recovery/retry KPI definitions remain unchanged, but summary stamping now occurs on every successful response.

Current `final_status` becomes `repaired` whenever `slug_coerced` is true (`compiler/compiler.py:534-552`). If routine summary stamping or ignored stray fields feed that flag, virtually every successful 4.0 response becomes a recovery, invalidating the acceptance comparison.

The blueprint needs a live telemetry truth table:

- `schema_ok` = proposal-schema result;
- `semantic_ok` = bridge plus canonical self-check result;
- summary stamping and `summary_slug_ignored` do **not** set `slug_coerced` or change `final_status`;
- only concept/article form coercion sets `slug_coerced`;
- canonical invariant failures must trigger failed-response capture even if earlier flags passed.

This must be pinned by measurement and acceptance tests.

### F3 — Medium: the existing parity corpus cannot remain byte-exact

The plan says the wikilink parity corpus remains byte-exact (`§10`).

But current corpus cases deliberately expect body-only tokens such as `[[Foo--Bar]]` and `[[AAPL]]` to be coerced without a matching response page (`tests/fixtures/wikilink_parity/cases.json:41-119`). v0.2 correctly prohibits those rewrites.

Preserve the shared token-parsing cases, but add a new bridge-authority expectation surface. Do not require the obsolete coercion outputs to remain byte-identical.

### F4 — Medium: arbitrary stray values do not fit the decision type

The proposal accepts a summary `slug` containing any JSON value, including objects or arrays (`§3.1`). However, `NormalizationDecision.raw_value` accepts only `str | None` (`§3.3`).

Either accept a JSON-value type or record bounded telemetry such as:

- `raw_type`;
- truncated `raw_preview`;
- stable raw-value hash.

The latter keeps the always-on decision list small.

### F5 — Medium: information-loss protection is still not executable

D-119 requires rejection on information loss, but the bridge's canonical self-check verifies only schema shape and summary identity. A bridge bug could drop a concept page or `compilation_notes` and still pass both checks.

Add a conservation invariant:

- page count and page order preserved;
- `page_type`, `title`, prose, and notes preserved byte-for-byte;
- differences allowed only at declared slug fields and specifically located body-reference tokens;
- violations raise non-retriable `CanonicalInvariantError`.

### F6 — Low: blueprint questions still need decisions

BQ-2 through BQ-5 remain “leans,” even though later phases depend on them. Before requesting **Proceed**, convert them into explicit blueprint decisions—especially the CLI matrix for `--canonical` and `--source-id`.

Also assign CLI routing to either Phase 1 or Phase 4; it currently appears in both.

## R6 absorption status

- F1 unexpected-summary handling: resolved.
- F2 authority-safe body rewriting: resolved.
- F3 alias provenance ownership: resolved.
- F4 raw/canonical length separation: resolved.
- F5 telemetry persistence: mostly resolved; arbitrary-value typing remains.
- F6 replay versioning: partly resolved; 2.x dispatch is incorrect.
- F7 discriminated bridge result: resolved.
- Integrated pipeline/prompt phase: resolved.

## Disposition

Once F1–F5 above are corrected and the remaining leans are ratified as decisions, v0.3 should be ready for Joseph's **Proceed** gate.

No code was changed and no tests were run; this was a documentation and code-history review.
