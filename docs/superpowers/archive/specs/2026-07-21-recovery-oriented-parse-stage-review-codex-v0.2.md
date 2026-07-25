# Task #114 v0.2 Design Review - Codex

Date: 2026-07-21

## Verdict

`REVISE BEFORE IMPLEMENTATION`

The update successfully addresses all five findings from the first review,
including recovery-before-truncation, KPI threading, selection-first
composition, and tracked fixtures. It still needs a v0.3 correction before
implementation, chiefly because one required positive fixture is provably
unrecoverable. The remaining changes clarify contracts rather than alter the
core architecture.

## Findings

### [Severity: High] The 20-positive-fixture validation gate cannot pass

References: design spec lines 33-39, 140-153, and 196-198.

The spec says both extract-stage responses contain complete valid documents
and requires all 20 to recover. Direct validation shows:

- `Callouts.md`: complete, schema-clean object; 19-character tail.
- `Negative cash-conversion cycle.md`: incomplete object ending at
  `"warnings": []`; both original and escape-normalized `raw_decode` fail at
  EOF.

The correct corpus is **19 recoverable positives**: 15 lone-brace, 3 fragment,
and 1 extract-stage (`Callouts`). Make `Negative cash-conversion cycle.md` an
incomplete-document negative that retries and quarantines. Observed positive
tail lengths are `2/19/20/22`. The same correction is needed in
`docs/TASKS.md:45`.

### [Severity: Medium] `extract_ok` and `failure_stage="extract"` no longer have defined meanings

References: design spec lines 43-62; `common/types.py:393-400`;
`compiler/tests/test_compiler.py:580-613,1042-1067`.

Under loose unwrap, nearly every model response produces a candidate. The
spec must choose whether:

- `extract_ok` remains strict carrier-shape conformance but becomes
  non-gating, or
- `extract_ok` means loose unwrap completed, making it nearly always true and
  effectively retiring expected extract failures.

This affects response capture, the Task #25 failure taxonomy, and existing
compiler tests.

### [Severity: Medium] Prefix recovery is mislabeled as tail discard

References: design spec lines 43-55 and 107-120.

Loose unwrap permits leading prose, and `raw_decode` starts at the first `{`.
For `Here is JSON: {...}`, boundary recovery fires but discards no tail,
producing `tail_discarded=True` with `tail_discarded_chars=0` under the current
wording.

Prefer `boundary_recovered` plus explicit prefix/tail counts, or precisely
document that `tail_discarded` really means "boundary recovery fired." This
should be settled before the field becomes persisted API.

### [Severity: Medium] The replay tool would diverge from production parsing

References: design spec lines 57-62; `tools/replay.py:88-117`.

The spec allows strict extraction to remain for other callers, but
`tools/replay.py` explicitly claims to mirror `compile_one` and currently uses
strict extraction followed by plain `json.loads`.

Require replay to use the same shared recovery path, or explicitly redefine
replay as a strict-validator tool. Leaving this to implementation-time
call-site inspection risks two different verdicts for the same captured
response.

### [Severity: Low] The safety argument still describes only the selection path

References: design spec lines 72-87.

The argument says accepted content is "nothing repaired, only recognized,"
but steps 3-5 can accept escape-normalized content. Split the argument between
unmodified boundary selection and the existing sanctioned escape-repair path.

## Validation Note

No files other than this review were changed and no test suite was run. The
captured responses were validated directly through the proposed decoding
ladder.
