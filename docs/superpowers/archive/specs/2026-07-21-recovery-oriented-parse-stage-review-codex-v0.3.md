# Task #114 v0.3 Design Review - Codex

Date: 2026-07-21

## Verdict

`GO WITH CHANGES`

v0.3 resolves every substantive issue from the first two reviews. No
architectural redesign is needed; the remaining changes pin down the shared
API, compatibility defaults, and two documentation inconsistencies before
implementation planning.

## Findings

### [Severity: Medium] The shared recovery boundary remains underspecified

References: design spec lines 70-90.

The ladder is shared, but it accepts an already-unwrapped candidate. That
leaves strict-shape evaluation and loose unwrap duplicated between
`compile_one` and replay, so they could still derive different candidates or
`extract_ok` values.

Make the shared function own the complete raw-response operation:

```python
recover_json_response(raw_text: str) -> RecoveryResult
```

`RecoveryResult` should carry the parsed object, `extract_ok`, repair flags,
prefix/tail counts, and terminal parse error. Keep retries, `stop_reason`,
schema, and semantic handling with each caller.

### [Severity: Medium] Defaults and status precedence need to be explicit

References: design spec lines 110-132 and 172-174; `common/types.py:377-453`;
`common/measurement.py:17-159`.

The fields are described as additive `bool`/`int` telemetry, but the
incomplete test expects `boundary_recovered` to be "absent." New
`RespStatsRecord.to_dict()` records will normally serialize default fields.

Define the contract as:

- New/non-recovered records: `False`, `0`, `0`.
- Historical Pass-2 records: `.get(..., False/0)`.
- Pass-1 measurements: `boundary_recovered=False`.
- Schema/semantic failures remain `final_status="quarantined"` even if
  boundary recovery fired; successful attempt 1 is `repaired`, successful
  attempt 2 is `retried-and-repaired`.

Add backward-compatibility tests for an old Pass-2 record and a Pass-1
projection.

### [Severity: Low] The task ledger retains the disproven evidence claim

Reference: `docs/TASKS.md:45`.

The task row still says all 20 responses carried complete valid documents. It
should say 19 recoverable responses plus one genuinely incomplete response.

### [Severity: Low] The selection wording conflicts with the first-brace rule

References: design spec lines 58-60 and 160-161.

"The first complete decodable object wins" suggests scanning until something
decodes, while the out-of-scope contract tries only the first `{`.

Use: "The object beginning at the first `{` wins if it decodes completely; no
subsequent brace scanning."

## Validation Note

No files other than this review were changed and the test suite was not run.
