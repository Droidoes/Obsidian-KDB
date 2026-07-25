# #108 — Pass-1 robustness: outcome telemetry + shared `json_escape_fix` (B2)

**Date:** 2026-06-05 · **Status:** 🟢 ratified design (Joseph approved 2026-06-05)
**Depends on:** B1 `2026-06-05-passcallmeasurement-design.md` (this *is* B1 producer-delta #2 + the json_escape_fix rung).
**Ledger:** #108. **Principle:** [[feedback_coerce_dont_reject]] · [[feedback_name_must_match_contents]] · [[feedback_no_imaginary_risk]].

---

## 1. Scope (settled 2026-06-05)

Not a repair-ladder port — instrumentation + one proven shared rung. Run-8's two Pass-1 failures (empty response, `summary=None`) are **retry-only** and the #104-era retry already rescues them. The json-escape class is real and recurring but has only hit **Pass-2** (run-4/run-5); wiring its shared fix into Pass-1 is cheap preventive parity for a proven, pass-agnostic class. Everything heavier (null-fill, temp-bump, summary coercion) is **deferred until a Pass-1 repairable class actually appears**.

## 2. Change 1 — wire `json_escape_fix` into `call_pass1`

In the attempt loop (`ingestion/enrich/pass1_caller.py:84-87`), between `raw_text = resp.text` and `json.loads(raw_text)`:

```
parsed = try json.loads(raw_text)
  on JSONDecodeError:
      escaped = json_escape_fix(raw_text)          # common/util/json_escape_fix — shared, content-preserving
      parsed = try json.loads(escaped)
        success → syntax_repaired = True; proceed
        JSONDecodeError → re-raise → existing retry branch (fresh emission)
```

- **Re-validation-gated:** the escaped text still runs `normalize_llm_content` + `validate_llm_content`. A bad escape can't slip through — it falls to the retry, exactly #106's guarantee.
- **Import:** `common.util.json_escape_fix` (already a leaf; ingestion→common is legal).
- This rung fires only on the *repairable* JSON-syntax class. The empty-response class (`Expecting value: line 1 col 1`) has nothing to escape → falls straight to retry, unchanged.

## 3. Change 2 — Pass-1 `final_status` + flags (B1 delta #2)

Extend `Pass1CallResult` (`pass1_caller.py:23-33`) + the sidecar `raw_response` block:

| field | derivation |
|---|---|
| `final_status` | `clean` (parsed+validated attempt 1, no repair) · `repaired` (json_escape_fix fixed it on attempt 1) · `retried-and-repaired` (succeeded only on attempt 2) · `quarantined` (all attempts exhausted → `Pass1CallError`) |
| `syntax_repaired` | True iff json_escape_fix fired on the winning attempt |
| `total_input_tokens` / `total_output_tokens` / `total_latency_ms` / `call_count` | summed across all attempts (B1 delta #1, P1 half — today only the last attempt is kept) |
| `final_attempt_index` | the attempt that succeeded (or the last, on quarantine) |

Persisted into the sidecar by `enrich.py` (extends the existing `raw_response` dict). `enrich.py` already emits the `source_quarantined` lifecycle event on `Pass1CallError` — `final_status='quarantined'` is the record-level mirror of that event.

`slug_coerced` is always `False` for Pass-1 (no slug rung exists); `semantic_ok` is `None` (no Pass-1 semantic gate) — both per the B1 shape.

## 4. Test plan (TDD)
- **json_escape_fix wired:** a Pass-1 response with a stray-backslash (e.g. LaTeX in `summary`) → parses after escape → `final_status='repaired'`, `syntax_repaired=True`, NOT quarantined.
- **bad escape falls through:** an irreparable-JSON response → escape fails to parse → routes to retry → (if 2nd attempt clean) `retried-and-repaired`.
- **final_status paths:** clean / repaired / retried-and-repaired / quarantined each asserted.
- **retry-only classes unchanged:** empty-response + `summary=None` fixtures still route retry→quarantine — now *labeled* with the right `final_status`, behavior otherwise identical.
- **aggregation:** 2-attempt fixture → `total_*` summed, `call_count=2`, `final_attempt_index=2`.
- **projection:** `from_pass1` (B1 adapter) over the new sidecar → correct `PassCallMeasurement`.

## 5. Explicitly out of scope (deferred until data)
- nullable null-fill (no sighting anywhere)
- temp-bump on retry (every retry has succeeded without it — no deterministic-failure evidence)
- `summary=None` / empty-response coercion (retry-only — not repairable)
