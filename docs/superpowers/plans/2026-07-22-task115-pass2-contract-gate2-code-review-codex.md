# Task #115 — Pass-2 contract revision (Phases 1–2) — Gate-2 code review

**Reviewed:** 2026-07-22  
**Base:** `e9ca323` (`feat/115-pass2-contract`)  
**Scope:** uncommitted working-tree implementation of blueprint Tasks T1.1–T1.7 and T2.1–T2.5  
**Verdict:** **GO-WITH-CHANGES** — commit Gate 2 only after the High and Medium findings below are resolved and the deterministic suite is rerun.

The implementation follows the ratified architecture: the emitted contract is wiki-native, the removed aggregates are not reconstructed, summary identity is derived and checked on both sides of canonicalization, the #65 Repair stage is gone, historical aggregate fields remain readable, and graph intake derives new-shape edges from bodies while preserving the legacy-list path. The remaining issues are bounded implementation defects, not reasons to reopen the design.

## (a) Contract coherence (schema / prompt / builder)

### F1

**[Severity: Medium] · `compiler/prompts/KDB-Compiler-System-Prompt.md:74` · the model-facing summary-slug rule contradicts the executable rule.**

The prompt says the source stem is copied “verbatim” and that every character is preserved. The executable contract at `compiler/summary_slug.py:30` instead applies NFKD-to-ASCII `slugify`, collapses punctuation, lowercases, then truncates the normalized stem to 112 characters and strips a trailing hyphen. For example, `Café déjà vu.md` derives `summary-cafe-deja-vu`, and a 113-character stem is truncated; neither behavior is “verbatim.” Because the expected value is deliberately not injected into the prompt, the prose rule is the model’s only way to author the exact value. Long or punctuation-heavy names can therefore consume two calls and still be quarantined even when the model follows the written instruction.

**Suggested change:** state the production algorithm once and exactly: filename stem → NFKD/ASCII kebab-case → first 112 characters → strip a trailing hyphen → prepend `summary-`. Remove “copied verbatim / preserve every character,” retain the useful requirement to preserve meaningful numeric or identifier prefixes, and add prompt-contract tests for an accented/punctuated stem and a >112-character stem.

### F2

**[Severity: Low] · `compiler/validate_source_response.py:7` · public contract documentation still describes the deleted seven-field page shape and the retired `--source-name` CLI flag.**

The module docstring says all seven old page fields are required and documents `--source-name`, while the implementation correctly requires four fields and exposes `--source-id` at line 123. There are related stale descriptions at `compiler/validate_source_response.py:36`, `compiler/canonicalize.py:363`, and `compiler/schemas/compile_result.schema.json:237` that still speak about outgoing-link metadata rather than body-only remaps. These do not change runtime behavior, but they make the code-level contract disagree with the ratified design and can mislead the next maintainer.

**Suggested change:** update the docstrings/schema descriptions to the four-field contract, `--source-id`, and body-link-only canonical remaps. Where the aggregate schema retains historical properties, add the intended JSON-Schema annotations (`"deprecated": true`, `"readOnly": true`) in addition to prose descriptions.

## (b) Correctness of new gates (derive / semantic / canonicalize)

### F3

**[Severity: High] · `compiler/compiler.py:446` · a terminal post-call semantic rejection is not classified as validation on either telemetry or the outer result.**

On the final semantic failure, `compile_one` sets `state["error"]` and returns without calling `_set_failure`. The response record therefore persists `failure_stage=None`. `compile_source` then checks only `captured["record"].failure_stage` at `compiler/compiler.py:668` and maps the failure to generic outer stage `"compile"`. This violates the review packet’s explicit requirement that a semantic failure map inner `validate` → outer `validate`, and it causes event routing and last-failure diagnostics to describe a contract rejection as a compiler failure. Existing tests assert `semantic_ok=False` but never assert the two stage values, so the regression is green.

**Suggested change:** on the terminal semantic-failure branch, record a typed validation failure before returning (while retaining `semantic_errors` as the structured detail), and map that inner stage to outer `"validate"`. Add a `compile_source` test using a schema-valid, wrong derived summary slug that asserts both the persisted response record and `CompileSourceResult` carry `failure_stage="validate"`. Update the `FailureTelemetry` / `RespStatsRecord` documentation that currently says semantic failures are always outside the triplet.

### F4

**[Severity: High] · `compiler/canonicalize.py:222` · canonical body rewriting does not implement the wikilink forms accepted by the new body-authority contract.**

The canonicalizer explicitly treats `[[slug#heading]]` as out of scope and uses a regex that also rewrites escaped links and links inside inline/fenced code. The new system prompt permits headings at `compiler/prompts/KDB-Compiler-System-Prompt.md:118`, while both the compiler and graph extractors recognize headings and ignore escaped/code examples. Reproduction against the current code:

```text
_remap_body_wikilinks("See [[aapl#Revenue]].", {"aapl": "apple-inc"})
=> ("See [[aapl#Revenue]].", [])

_remap_body_wikilinks(r"Literal \[[aapl]] and `[[aapl]]`.", ...)
=> rewrites both non-link examples to apple-inc
```

This mismatch becomes load-bearing now that the metadata remap and `outgoing_links` fallback are removed from new payloads: an allowed alias-heading token can bypass canonical rewriting, while non-links can generate false `canonical_meta` aliases and mutate visible prose.

**Suggested change:** make canonical body rewriting use the same token semantics as the compiler/graph extraction contract: support plain, alias, and heading forms; preserve display text and heading suffixes; ignore escaped, fenced-code, and inline-code occurrences. Add the Phase-4 parity cases at this boundary now or at minimum add focused Gate-2 regression tests for the two reproduced cases before committing the body-authority cutover.

## (c) Dual-mode and backward compatibility

### F5

**[Severity: Medium] · `compiler/validate_compile_result.py:195` · underivable source stems raise out of aggregate validation and replay instead of failing closed.**

NEW-mode aggregate validation calls `expected_summary_slug(source_id)` without catching `PathError`; `tools/replay.py:128` does the same. A validly shaped record or fixture with `source_id="KDB/raw/日本語.md"` raises `PathError` out of both APIs. `kdb-validate` consequently terminates with a traceback rather than returning a gate finding, and one such replay fixture aborts the whole replay run rather than producing a semantic-failure result. This is the same explicitly designed underivable-stem boundary that `compile_one` and `kdb-validate-response` already handle correctly.

**Suggested change:** catch `PathError` in both consumers. Aggregate validation should append a hard-zero gate finding (either a dedicated `summary_slug_underivable` type added to `HARD_ZERO_FINDING_TYPES`, or the ratified mismatch type with an explicit underivable detail); replay should return `semantic_ok=False` with a stable error detail and continue evaluating other fixtures. Add direct API and CLI tests for non-ASCII-only/empty-normalization source stems.

The ordinary dual-mode behavior is otherwise correct and per-source: a string `summary_slug` selects the ratified LEGACY referential checks, while absence selects NEW exact derivation. Adding `summary_slug` to an otherwise new-shaped record can select legacy semantics, but that is inherent in the explicitly ratified presence-based compatibility rule; safety therefore depends on the correctly tested invariant that new writers never emit the deprecated key. In NEW mode, `cs.get("summary_slug") or summary_page(cs)["slug"]` does not mask zero or multiple summary pages—the helper is reached and fails closed.

## (d) Layering and cross-package behavior

No additional finding.

Verified:

- `kdb_graph/` production modules do not import `compiler` or another sibling package.
- The graph-side body extractor is mirrored and drift-tested against the compiler extractor.
- New-shape body links create and survive replacement of `LINKS_TO`; an explicitly present legacy `outgoing_links` list remains authoritative, including an empty list.
- The compiler no longer calls the deleted repair dispatch or either removed reconciler. Repository-wide searches found no dangling production caller.
- `PageIntent`/writers use Python-owned `active` defaults, while graph confidence removal remains correctly deferred to Gate 3.

## (e) Scope and test coverage

### F6

**[Severity: Medium] · `kdb_graph/tests/test_rebuilder.py:883` · the “new-shape” half of the mixed-journal rebuild test is not a valid new contract record.**

The new journal contains only concept pages `c` and `d`; it has no summary page and could not pass NEW-mode aggregate validation. The test proves body-derived edge replay, but it does not prove that a representative valid NEW aggregate journal and a LEGACY journal coexist through the compatibility boundary. There is also no single aggregate-validator test containing one legacy source and one new source, so per-source mode selection is presently verified only by separate cases.

**Suggested change:** give the new journal its derived `summary-new` summary page, validate both journal payloads before rebuilding, and add one mixed aggregate validation test. Keep the existing edge assertions so the test covers both compatibility mode and graph behavior.

### F7

**[Severity: Low] · `compiler/tests/test_summary_slug.py:53` · guard/production equivalence is not pinned for the required non-ASCII failure case.**

The production helper has a direct non-ASCII rejection test, and the guard equivalence parametrization covers normalization and truncation successes, but it never asserts that both implementations reject a non-ASCII-only stem identically. The two functions are currently source-identical, so this is a test-seam omission rather than a current algorithm drift.

**Suggested change:** add a paired exception-equivalence case for a non-ASCII-only stem (and, ideally, an empty-normalization punctuation-only stem) so future guard/helper drift cannot pass by preserving only the success cases.

Scope discipline otherwise holds: no Phase-3 confidence removal leaked into this diff; no cross-source reservation/MOVED/WAL machinery from #116 appeared; `scripts/cohort_slug_collision_guard.py` and `common/measurement.py` are absent from the Gate-2 diff. The large test deletion is concentrated in the retired pairing/reconcile contract; the retained failure-path coverage remains elsewhere in `test_compiler.py` and `test_compiler_recovery.py`.

## Verification performed

- `git diff --check HEAD` — clean.
- Full default suite — one failure only: `ingestion/tests/test_pass1_enrich.py::test_enrich_one_smoke`; `DEEPSEEK_API_KEY` is present, so pytest attempted the live API call, which failed with `Connection error` in the network-restricted review environment. This test and failure are unrelated to the Gate-2 diff.
- Complete deterministic suite: `.venv/bin/python -m pytest -q -m 'not bench and not live'` — **green** (exit 0; one separately env-gated compiler live smoke skipped).
- Focused source/diff inspection covered all 56 tracked files plus `compiler/summary_slug.py` and `compiler/tests/test_summary_slug.py`; `docs/session-handoff-2026-07-22-evening.md` was excluded as instructed.

## Bottom line

The Gate-2 implementation translates the ratified derivation-first architecture faithfully in the common path and does not need architectural rework. It is **not safe to commit as-is**, because terminal semantic failures are observably routed to the wrong stage, aggregate/replay validation can crash on a required boundary case, and canonical body rewriting disagrees with the accepted wikilink grammar after body links become authoritative. Fix F3–F6, align the prompt rule in F1, rerun the deterministic suite, and then Gate 2 is suitable for commit approval; F2 and F7 are low-risk cleanup that should be folded into the same pre-commit pass if practical.
