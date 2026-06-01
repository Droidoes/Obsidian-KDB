# Pass-1 Coercion + Pass-2 Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The 3 run-4 findings: (1) Pass-1 coerces >10 `entity_search_keys` to 10 instead of rejecting; (2) Pass-1 lets `source_type='other'` pass without `other_reason`; (3) Pass-2 retries on a recoverable bad-JSON emission instead of quarantining on the first.

**Architecture:** (1)+(2) live in Pass-1's deterministic layer — a new `normalize_llm_content()` coercion runs in `pass1_caller` *before* validation, and the OQ-NW7-7 cross-field rule is dropped from `pass1_schema`. (3) wraps the Pass-2 model-call→extract→parse→schema block in `compiler.compile_one` in a retry loop, mirroring Pass-1's `call_pass1` retry; truncation and hard model errors stay terminal.

**Tech Stack:** Python 3 stdlib, pytest. Files: `kdb_compiler/ingestion/pass1_schema.py`, `kdb_compiler/ingestion/pass1_caller.py`, `kdb_compiler/compiler.py`; tests in `kdb_compiler/tests/`.

**Spec:** `docs/run-4-findings.md` (Findings 1 + 3, with resolutions). Principle: [[feedback_coerce_dont_reject]].

**Note:** the audit's `confidence`-clamp and missing-nullable-default coercions are deliberately **out of scope** (never observed live; data-before-principle).

---

### Task 1: Pass-1 — coerce `entity_search_keys` to ≤10 (don't reject)

**Files:**
- Modify: `kdb_compiler/ingestion/pass1_schema.py` (add `normalize_llm_content`)
- Modify: `kdb_compiler/ingestion/pass1_caller.py` (call it before validation)
- Test: `kdb_compiler/tests/test_pass1_schema.py`, `kdb_compiler/tests/test_pass1_caller.py`

- [ ] **Step 1: Write the failing tests**

In `test_pass1_schema.py`, add:

```python
def test_normalize_truncates_entity_search_keys_to_10():
    from kdb_compiler.ingestion.pass1_schema import normalize_llm_content
    p = _content_only()
    p["entity_search_keys"] = [f"k{i}" for i in range(13)]
    normalize_llm_content(p)
    assert p["entity_search_keys"] == [f"k{i}" for i in range(10)]
    validate_llm_content(p)  # passes after normalize (no raise)


def test_normalize_leaves_short_keys_untouched():
    from kdb_compiler.ingestion.pass1_schema import normalize_llm_content
    p = _content_only()
    p["entity_search_keys"] = ["a", "b"]
    normalize_llm_content(p)
    assert p["entity_search_keys"] == ["a", "b"]
```

In `test_pass1_caller.py`, add:

```python
def test_caller_coerces_over_cap_keys_without_retry(monkeypatch):
    monkeypatch.setattr(
        caller_mod, "call_model",
        lambda req: _fake_response(_content_json(
            entity_search_keys=[f"k{i}" for i in range(13)])),
    )
    res = call_pass1(source_text="b", source_path="x.md",
                     provider="deepseek", model="deepseek-v4-flash")
    assert res.attempts == 1  # coerced, not rejected+retried
    assert res.parsed["entity_search_keys"] == [f"k{i}" for i in range(10)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest kdb_compiler/tests/test_pass1_schema.py kdb_compiler/tests/test_pass1_caller.py -m "not live" -q -W ignore -k "normalize or coerces"`
Expected: FAIL — `normalize_llm_content` does not exist / caller still retries.

- [ ] **Step 3: Add `normalize_llm_content` to `pass1_schema.py`**

Add immediately after `validate_envelope` (end of file):

```python
def normalize_llm_content(payload: dict[str, Any]) -> None:
    """Coerce benign shape deviations IN PLACE, before validation — don't reject
    + retry over a lossless, mechanical fix ([[feedback_coerce_dont_reject]]).

    Currently: truncate entity_search_keys to the first 10. The ≤10 cap is a
    retrieval budget, not a correctness bound — extra/imperfect slugs just miss
    the Entity.slug PK lookup harmlessly. The strict schema (maxItems:10) stays
    the gate; this runs ahead of it so an over-supply never trips validation."""
    keys = payload.get("entity_search_keys")
    if isinstance(keys, list) and len(keys) > 10:
        payload["entity_search_keys"] = keys[:10]
```

- [ ] **Step 4: Call it in `pass1_caller.py` before validation**

Change the import line:

```python
from kdb_compiler.ingestion.pass1_schema import validate_llm_content, PASS1_SCHEMA_VERSION
```

to:

```python
from kdb_compiler.ingestion.pass1_schema import (
    normalize_llm_content, validate_llm_content, PASS1_SCHEMA_VERSION,
)
```

Then in `call_pass1`, find:

```python
            parsed = json.loads(raw_text)
            # STAGE 1 (Task #95): validate the LLM-owned content fields ONLY,
```

and insert the normalize call before the STAGE-1 comment:

```python
            parsed = json.loads(raw_text)
            # Coerce benign shape deviations (e.g. >10 entity_search_keys) BEFORE
            # validation — don't burn a retry over a lossless, mechanical fix.
            normalize_llm_content(parsed)
            # STAGE 1 (Task #95): validate the LLM-owned content fields ONLY,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest kdb_compiler/tests/test_pass1_schema.py kdb_compiler/tests/test_pass1_caller.py -m "not live" -q -W ignore`
Expected: PASS (the new tests + the existing `test_validate_llm_content_rejects_more_than_10_entity_search_keys`, which still holds — `validate_llm_content` alone stays strict).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/ingestion/pass1_schema.py kdb_compiler/ingestion/pass1_caller.py kdb_compiler/tests/test_pass1_schema.py kdb_compiler/tests/test_pass1_caller.py
git commit -m "feat(pass1): coerce >10 entity_search_keys to 10 before validation (Finding 1)"
```

---

### Task 2: Pass-1 — let `source_type='other'` pass without `other_reason`

**Files:**
- Modify: `kdb_compiler/ingestion/pass1_schema.py` (drop the OQ-NW7-7 cross-field rule)
- Test: `kdb_compiler/tests/test_pass1_schema.py` (rewrite the now-inverted test)

- [ ] **Step 1: Rewrite the existing test to assert it now passes**

In `test_pass1_schema.py`, replace:

```python
def test_validate_llm_content_keeps_other_reason_rule():
    payload = _content_only()
    payload["source_type"] = "other"
    payload["other_reason"] = None
    with pytest.raises(ValueError, match="other_reason"):
        validate_llm_content(payload)
```

with:

```python
def test_validate_llm_content_allows_null_other_reason():
    # Finding 1 (run-4): other_reason is an audit field (Pass-2 ignores it);
    # a missing "why other" note is not worth a reject + retry. Let it pass.
    payload = _content_only()
    payload["source_type"] = "other"
    payload["other_reason"] = None
    validate_llm_content(payload)  # no raise
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest kdb_compiler/tests/test_pass1_schema.py::test_validate_llm_content_allows_null_other_reason -m "not live" -q -W ignore`
Expected: FAIL — still raises `ValueError: … other_reason …`.

- [ ] **Step 3: Drop the cross-field rule in `_validate_against`**

In `pass1_schema.py`, find:

```python
        raise ValueError(f"Pass-1 {label} invalid at {path}: {e.message}") from e
    # OQ-NW7-7 cross-field rule: other_reason non-null when source_type='other'.
    if payload["source_type"] == "other" and not payload.get("other_reason"):
        raise ValueError(
            f"Pass-1 {label} invalid at other_reason: "
            "must be non-null string when source_type='other' (OQ-NW7-7)"
        )
```

and replace it with (drop the cross-field block; keep the schema-error raise):

```python
        raise ValueError(f"Pass-1 {label} invalid at {path}: {e.message}") from e
    # OQ-NW7-7's other_reason-required cross-field rule was dropped 2026-05-31
    # (run-4 Finding 1): other_reason is an audit field (Pass-2 ignores it), so a
    # missing "why other" note is coerced-through, not a reject. Trade-off: loses
    # the vocab-evolution signal when the LLM omits it (still recorded when given).
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest kdb_compiler/tests/test_pass1_schema.py -m "not live" -q -W ignore`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add kdb_compiler/ingestion/pass1_schema.py kdb_compiler/tests/test_pass1_schema.py
git commit -m "feat(pass1): let source_type=other pass without other_reason (Finding 1)"
```

---

### Task 3: Pass-2 — retry on a recoverable bad-JSON emission

**Files:**
- Modify: `kdb_compiler/compiler.py` (add a logger + `_MAX_COMPILE_ATTEMPTS`; wrap call→schema in a retry loop in `compile_one`)
- Test: `kdb_compiler/tests/test_compiler.py`

- [ ] **Step 1: Write the failing test**

In `test_compiler.py`, add (uses the existing `_fake_call`, `_good_model_response`, `_write_vault`, `_write_raw`, `_job`, `_ctx`, `SOURCE_A`, `_resp_stats_files`):

```python
def test_compile_one_retries_on_bad_json_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    calls = {"n": 0}

    def bad_then_good(req):
        calls["n"] += 1
        if calls["n"] == 1:
            # invalid JSON: unescaped backslash (the run-4 LaTeX `\(` defect)
            return ModelResponse(
                text=r'{"summary_slug": "s", "body": "gets \(n-1\) points"}',
                input_tokens=10, output_tokens=5, latency_ms=1,
                model="claude-opus-4-7", provider="anthropic", attempts=1,
            )
        return _good_model_response(SOURCE_A)

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: bad_then_good}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    assert calls["n"] == 2          # re-called once after the bad emission
    assert err is None              # retry recovered
    assert cs is not None
    assert cs.source_id == SOURCE_A


def test_compile_one_quarantines_after_all_attempts_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _write_vault(tmp_path)
    _write_raw(vault, SOURCE_A, "alpha body")
    state_root = vault / "KDB" / "state"
    ctx = _ctx(vault)

    def always_bad(req):
        return ModelResponse(
            text=r'{"body": "gets \(n-1\) points"}',
            input_tokens=10, output_tokens=5, latency_ms=1,
            model="claude-opus-4-7", provider="anthropic", attempts=1,
        )

    monkeypatch.setattr(
        "kdb_compiler.compiler.call_model_with_retry",
        _fake_call({SOURCE_A: always_bad}),
    )

    cs, logs, warns, err = compiler.compile_one(
        _job(vault, SOURCE_A),
        vault_root=vault, state_root=state_root, ctx=ctx,
        provider="anthropic", model="claude-opus-4-7", max_tokens=4096,
    )

    assert cs is None
    assert err is not None  # still fails after exhausting attempts
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest kdb_compiler/tests/test_compiler.py -m "not live" -q -W ignore -k "retries_on_bad_json or quarantines_after_all"`
Expected: `test_compile_one_retries_on_bad_json_then_succeeds` FAILS (`calls["n"] == 1`, no retry → `err` set). The `quarantines_after_all` test likely already passes (single attempt fails).

- [ ] **Step 3: Add a logger + retry-count constant to `compiler.py`**

At the top of `kdb_compiler/compiler.py`, add (after the existing `from __future__ import annotations` / imports block — place with the other module-level constants):

```python
import logging

log = logging.getLogger(__name__)

# Pass-2 re-calls the model on a recoverable bad-JSON emission (extract/parse/
# schema), mirroring Pass-1's call_pass1 retry. initial + 1 retry.
_MAX_COMPILE_ATTEMPTS = 2
```

(If an `import logging` already exists, don't duplicate it — add only `log` and `_MAX_COMPILE_ATTEMPTS`.)

- [ ] **Step 4: Wrap model-call→extract→parse→schema in the retry loop**

In `compile_one`, replace the entire block from `# --- model call ---` through the end of the `# --- schema ---` block (the `return` after `schema validation failed`) with:

```python
        # --- model call + extract + parse + schema, with a retry on a
        # recoverable bad-JSON emission. Mirrors Pass-1's call_pass1 retry: the
        # model sometimes emits invalid JSON (e.g. unescaped LaTeX backslashes on
        # math-heavy sources, run-4 Finding 3); a re-call usually returns valid
        # JSON. Truncation and hard model-call errors are terminal (a re-call
        # won't help). The SDK-transient retry already lives in call_model_with_retry.
        for attempt in range(1, _MAX_COMPILE_ATTEMPTS + 1):
            last_attempt = attempt == _MAX_COMPILE_ATTEMPTS

            # --- model call ---
            try:
                state["model_response"] = call_model_with_retry(
                    ModelRequest(
                        provider=provider,
                        model=model,
                        system=state["prompt"].system,
                        prompt=state["prompt"].user,
                        temperature=0.0,
                        max_tokens=max_tokens,
                        use_completion_tokens=use_completion_tokens,
                        extra_body=extra_body,
                        json_mode=True,
                    )
                )
                state["raw_response_text"] = state["model_response"].text
            except Exception as e:
                _set_failure(state, "model_call", type(e).__name__, str(e))
                state["error"] = (
                    f"{source_id}: model call failed: {type(e).__name__}: {e}"
                )
                return (None, [], [], state["error"])

            # --- truncation guard (terminal — a re-call won't fit a bigger output) ---
            sr = state["model_response"].stop_reason
            if sr in ("max_tokens", "length"):
                _set_failure(
                    state, "truncation", "TokenOverrun",
                    f"stop_reason={sr!r}; max_tokens={max_tokens}",
                )
                state["error"] = (
                    f"{source_id}: truncated at max_tokens={max_tokens} "
                    f"(stop_reason={sr!r}); raise --max-tokens or shorten source"
                )
                return (None, [], [], state["error"])

            # --- extract ---
            try:
                json_text = response_normalizer.extract_json_text(
                    state["raw_response_text"]
                )
                state["extract_ok"] = True
            except ValueError as e:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} extract failed, retrying: {e}"
                    )
                    continue
                _set_failure(state, "extract", type(e).__name__, str(e))
                state["error"] = f"{source_id}: extract failed: {e}"
                return (None, [], [], state["error"])

            # --- parse ---
            try:
                state["parsed_json"] = json.loads(json_text)
                state["parse_ok"] = True
            except json.JSONDecodeError as e:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} invalid JSON, retrying: "
                        f"{e.msg} at line {e.lineno}"
                    )
                    continue
                _set_failure(state, "parse", type(e).__name__, str(e))
                state["error"] = (
                    f"{source_id}: invalid JSON: {e.msg} at line {e.lineno}"
                )
                return (None, [], [], state["error"])

            # --- schema ---
            state["schema_errors"] = validate_compiled_source_response.validate(
                state["parsed_json"]
            )
            state["schema_ok"] = state["schema_errors"] == []
            if not state["schema_ok"]:
                if not last_attempt:
                    log.warning(
                        f"{source_id}: Pass-2 attempt {attempt}/"
                        f"{_MAX_COMPILE_ATTEMPTS} schema invalid, retrying: "
                        f"{state['schema_errors'][0]}"
                    )
                    continue
                state["error"] = (
                    f"{source_id}: schema validation failed: {state['schema_errors'][0]}"
                )
                return (None, [], [], state["error"])

            break  # extract_ok + parse_ok + schema_ok → proceed to semantic
```

(The `# --- semantic ---` block and everything after it is unchanged — semantic failures stay terminal, matching the parse/schema retry scope.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest kdb_compiler/tests/test_compiler.py -m "not live" -q -W ignore`
Expected: PASS (the two new tests + all existing compiler tests — the happy path now runs one loop iteration and `break`s, behavior unchanged).

- [ ] **Step 6: Commit**

```bash
git add kdb_compiler/compiler.py kdb_compiler/tests/test_compiler.py
git commit -m "feat(pass2): retry on recoverable bad-JSON emission (Finding 3)"
```

---

### Task 4: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full non-live suite**

Run: `python3 -m pytest -m "not live" -W ignore --no-header`
Expected: PASS at the standing baseline (1214 passed + the new tests; 1 live skip).

- [ ] **Step 2: Commit any incidental touch-up**

```bash
git add -A && git commit -m "test: full non-live suite green for pass1-coerce + pass2-retry"
```

---

## Self-Review

**Spec coverage:**
- Finding 1a (truncate entity_search_keys) → Task 1 (`normalize_llm_content` + caller call) ✓
- Finding 1b (other_reason let-pass) → Task 2 (drop cross-field rule + rewrite test) ✓
- Finding 3 (Pass-2 retry on parse/schema/extract) → Task 3 (retry loop, mirrors Pass-1; truncation/model-error/semantic terminal) ✓
- Out-of-scope (confidence-clamp, nullable-default) → intentionally omitted, noted ✓

**Placeholder scan:** none — every code step is complete. The one conditional ("if `import logging` already exists, don't duplicate") is concrete and verifiable (grep confirmed it does NOT exist today, so it will be added).

**Type consistency:** `normalize_llm_content(payload: dict) -> None` defined in Task 1 Step 3, imported + called in Step 4, used in tests Step 1. `_MAX_COMPILE_ATTEMPTS` defined Task 3 Step 3, used in the loop Step 4. The loop reuses the exact `ModelRequest(...)` args, `_set_failure`, `state[...]`, and return tuple shape `(None, [], [], state["error"])` from the original block. `log` defined Step 3, used Step 4.
