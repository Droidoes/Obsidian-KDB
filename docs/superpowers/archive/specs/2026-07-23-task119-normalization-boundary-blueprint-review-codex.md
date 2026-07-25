# Task #119 normalization-boundary blueprint — Codex R6 review

**Date:** 2026-07-23  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-23-task119-normalization-boundary-blueprint.md` v0.1

## Verdict

**REVISE BEFORE PROCEED.**

The ratified architecture remains sound, and the acceptance gate is strong. However, three high-severity blueprint contradictions could produce behavior contrary to D-119.

## Findings

### F1 — High: an unexpected summary slug becomes a failure again

The proposal schema forbids a summary `slug`, and BQ-6 classifies its presence as retriable structural insufficiency (`§3.1`, `BQ-6`).

That directly contradicts:

- “never rejects, never retries” in §1;
- the retry table's “never a failure cause”;
- D-119's ratified rule that the raw summary-slug value cannot cause rejection.

The prompt should omit the field, but the acceptance boundary must tolerate and ignore an unexpected summary slug—or Joseph must explicitly amend the ratified rule. The Phase-0 fixture should prove that an unexpected malformed or non-string slug does **not** retry or quarantine.

### F2 — High: the reused #106 function rewrites references without authority

Bridge rule 2 proposes applying `coerce_slugs_and_propagate` across page slugs and body targets before reference resolution (`§5`).

The existing function:

- collects body-only tokens as slug values;
- mechanically collapses and rewrites them even if they name no response page or registry entry;
- returns only `True`/`False`, conflating no-op, uncoercible input, and collision;
- mutates the proposal in place.

This behavior is visible in `compiler/repair.py:85-139`.

That violates “preserve without authority.” Refactor the machinery into a typed, pure plan:

1. normalize concept/article **page slugs**;
2. detect typed collision/uncoercible results;
3. create a raw-page-slug → canonical-page-slug map;
4. rewrite only body tokens that exactly match a uniquely mapped response page;
5. preserve body-only tokens verbatim.

### F3 — High: bridge-level alias resolution would bypass canonical provenance

Rule 4 makes the alias ledger a bridge authority while §7 promises `canonicalize` and the alias ledger remain untouched.

Today canonicalization owns ledger resolution and emits `canonical_meta.aliases_emitted`. That metadata is load-bearing for alias entities, `ALIAS_OF` edges, and live/replay equivalence:

- `orchestrator/kdb_orchestrate.py:157-176`
- `kdb_graph/intake.py:586-625`
- `compiler/canonicalize.py:570-623`

If the bridge rewrites the body first, canonicalization no longer sees the alias and cannot emit its provenance.

Recommended resolution: keep alias-ledger resolution exclusively in canonicalization. The bridge should handle response-local slug-form propagation only. If alias resolution genuinely moves into the bridge, `canonical_meta` ownership and failure-stage behavior must be redesigned explicitly.

### F4 — Medium: raw length validation can reject a coercible slug

The proposal schema enforces `maxLength: 120` before normalization. A raw slug containing a long repeated-hyphen run could exceed 120 but collapse to a valid short canonical slug. Current #106 can rescue that case; the proposed ordering cannot.

Use a distinct defensive raw-input cap, then enforce the canonical 120-character limit after `collapse_slug`.

### F5 — Medium: telemetry is not reconstructible as claimed

The blueprint §3.4 says raw proposal plus decisions reconstruct the canonical object.

But `parsed_json` is persisted only when `KDB_RESP_STATS_CAPTURE_FULL=1`:

- `common/types.py:368-372`
- `common/llm_telemetry.py:127,196`

`scripts/sandbox-run.sh` does not enable that setting. The proposed decision records also lack page or token locations.

Either:

- drop the reconstructibility claim and document the capture-full requirement; or
- persist enough location-aware evidence, a canonical object/hash, or both.

### F6 — Medium: replay version dispatch lacks a version source

The plan calls for prompt-version-aware replay, but `ReplayFixture` has no prompt or boundary version and `RespStatsRecord` has no prompt version (`tools/replay.py:32-41`).

Before Proceed, define:

- the fixture metadata field;
- the default for existing fixtures;
- the 3.x versus 4.x dispatch table;
- the new meaning of schema/semantic flags after the bridge;
- behavior for unknown future versions.

### F7 — Medium: the “typed” result does not enforce its invariant

`BridgeResult` permits both `canonical` and `reject` to be populated—or both absent—and has no typed representation for `CanonicalInvariantError`.

Use a discriminated union such as `BridgeSuccess | BridgeReject`; represent internal invariant failures as a distinct exception/result. Derive retryability from `RejectClass` rather than storing a second drift-prone boolean.

## Minor plan correction

The dependency statement says phases are both strictly sequential and that Phases 4–5 may run in parallel. More importantly, rewiring the pipeline before updating prompt 4.0.0 creates a transient contract mismatch. Combine the pipeline switch with the prompt/schema/version switch, or document a feature-gated seam that keeps every phase integrated and green.

## What is already strong

- D-119 is correctly ratified in the North Star.
- The proposal/canonical separation is the right architecture.
- Strict canonical and post-canonicalization invariants remain intact.
- The TDD corpus and live acceptance cohort are appropriately scoped.
- The inherited #115 KPI gate is preserved rather than weakened.

## Disposition

Once F1–F3 and the replay/telemetry contracts are resolved, the blueprint should be ready for another review and Joseph's explicit **Proceed** gate.

No code was changed and no tests were run; this was a documentation and code-path review.
