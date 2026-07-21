# Task #114 Pre-Merge Review

**Branch:** `feat/114-recovery-parse-stage` against `main`  
**Reviewed:** 2026-07-21  
**Verdict:** **GO WITH CHANGES**

## Findings

### 1. [Important] Multiple fenced blocks are incorrectly unwrapped as one block

**Location:** `compiler/response_normalizer.py:112`

`unwrap_response` removes the first opener and final closer without checking
for additional fenced blocks. For example, a `null` block followed by a valid
object block becomes `null ... {object}`; boundary recovery selects `null`,
causing schema retry and eventual quarantine.

Per the ratified specification, multiple blocks should remain unchanged as
carrier noise. Keeping the original carrier allows the first-`{` fallback to
select the object payload.

**Concrete fix:** Mirror `extract_json_text`'s parse-based disambiguation. If
the prospective body contains another fence, strip the outer fence only when
the entire body decodes as one JSON document; otherwise return the original
stripped response. Add a regression test with a scalar first block and a valid
object second block.

### 2. [Important] Successful recovery can bypass the raw-response capture setting

**Location:** `common/llm_telemetry.py:156`

`failed_after_response` still treats `extract_ok=False` as failure. Since Task
#114 makes `extract_ok` non-gating, a successfully recovered, schema-clean
response with leading prose persists its full raw response even when
`KDB_RESP_STATS_CAPTURE_FULL` is unset. This violates the documented capture
boundary and may retain source-derived content unexpectedly.

**Concrete fix:** Determine failure from the gating verdicts instead:

```python
failed_after_response = bool(raw_response_text) and not (
    parse_ok and schema_ok and semantic_ok
)
```

Add tests proving that successful `extract_ok=False` recovery suppresses raw
text while actual parse, schema, and semantic failures still retain it.

## Verdict

**GO WITH CHANGES.** No Critical findings were identified, but the two
Important issues above should be fixed before merge.

The remaining requested contracts are correctly implemented: root
preservation and literal classification, the explicit `recovered` sentinel,
the shared five-step recovery ladder, compiler/replay parity,
recovery-before-truncation, dict-guarded coercion, winning-attempt flags,
telemetry defaults and KPI threading, and package layering.

The supplied full-suite result was `1379 passed`; the review used targeted
read-only reproductions for the two findings and did not rerun the full suite.
