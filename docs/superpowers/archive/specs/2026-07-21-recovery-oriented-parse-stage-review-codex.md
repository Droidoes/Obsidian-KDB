# Task #114 Design Review - Codex

Date: 2026-07-21

## Verdict

`REVISE BEFORE IMPLEMENTATION`

The boundary-selection idea is strong, but the current blueprint does not
fully implement its own recovery principle.

## Findings

### [Severity: High] Strict extraction prevents the new recovery rung from running

References: design spec lines 38-52; `compiler/response_normalizer.py:28-73`.

The proposed `raw_decode` occurs after `extract_json_text`, but the extractor
rejects any response that does not end in `}`. In the two cited runs, there is
an additional extraction failure whose first JSON object is complete and
schema-clean. The proposed implementation would still quarantine it.

Recovery should operate on a loosely unwrapped candidate before strict shape
rejection. This likely requires changing the extractor contract and its
prose/trailing-content tests.

### [Severity: High] The claimed benchmark telemetry is not actually preserved

References: design spec lines 72-80 and 100-102;
`common/measurement.py:17-40`; `compiler/kpi/processing.py:60-69,93-94`.

The spec says `recovery_rate` and `repair_rung_rate` retain the model-quality
signal. They currently count only retries, `syntax_repaired`, or
`slug_coerced`; `PassCallMeasurement` has no tail-recovery field.

A first-attempt tail recovery would therefore appear clean to the board.
Either thread `tail_discarded` into measurement and KPI calculations now, or
state clearly that only raw telemetry is retained and board visibility is
deferred. The intended `final_status` also needs definition.

### [Severity: Medium] The terminal truncation guard contradicts the general principle

References: design spec lines 7-14 and 53-54; `compiler/compiler.py:344-358`.

A `max_tokens` or `length` response is rejected before extraction or parsing.
Such a response can contain a complete JSON document followed by truncated
junk. Under the stated rule, that document should be accepted.

Either parse before declaring truncation, or narrow the principle so
`stop_reason` remains independently terminal.

### [Severity: Medium] Byte selection and escape normalization are not composed precisely

References: design spec lines 43-50; `common/util/json_escape_fix.py:18-25`.

The spec says the parse stage never edits bytes, then exempts
`escape_stray_backslashes` as "provably invertible." That helper does edit
bytes and is not generally invertible. More importantly, the blueprint does
not say whether `raw_decode` receives the original candidate or the escaped
candidate.

Use an explicit order:

1. Clean-decode the original candidate.
2. Boundary-decode the original candidate.
3. Apply escape normalization.
4. Clean-decode the normalized candidate.
5. Boundary-decode the normalized candidate.

This preserves selection-first semantics and defines combined
`syntax_repaired + tail_discarded` behavior.

### [Severity: Medium] The evidence and fixture contract need correction

References: design spec lines 26-32 and 104-121; `.gitignore:42`.

The captured records contain 18 `Extra data` failures, but their final-response
tails are 15 lone duplicated braces and 3 repeated fragments, not 17 and 1.
Tail lengths from the decoder boundary are 2, 20, or 22 characters, so the
proposed "exact 21-char" test is not presently reproducible. There is also the
schema-clean extraction failure noted above.

Both cited run directories are excluded by `.gitignore` and contain zero
tracked files. The spec should require copying curated responses into a
tracked `compiler/tests/fixtures/` artifact rather than reading benchmark runs
directly.

## Recommendation

Reopen the ratification gate for a v0.2 that resolves the extraction-boundary
and telemetry findings, then fold the remaining clarifications into the test
matrix.
