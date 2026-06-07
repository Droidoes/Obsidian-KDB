# #111 Phase 1 — Gemini Native API Handler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Call `gemini-3.1-flash-lite` through Google's **native `google-genai` SDK** (`from google import genai`) instead of the second-class OpenAI-compatibility shim — JSON mode + minimal thinking, reusing our existing prompt/output contract. No `response_json_schema` (that's Phase 2).

**Architecture:** Add a `_call_gemini` handler in `common/call_model.py`, a sibling to `_call_anthropic`, and reroute the `provider == "gemini"` dispatch to it (away from `_call_openai_compat`). It returns the same 5-tuple contract `(text, input_tokens, output_tokens, stop_reason, raw)` that `call_model` wraps into a `ModelResponse`, so nothing downstream (telemetry, cost, callers) changes. Gemini's native API uses a `GenerateContentConfig` with `response_mime_type="application/json"` (our current json-object guarantee) and `thinking_config={"thinking_level": "minimal"}` (the near-zero-reasoning floor for flash-lite — Gemini 3.x has no full thinking-off; `minimal` is the equivalent).

**Tech Stack:** Python 3, new dependency **`google-genai`**, pytest. The handler is sync (matches the existing engine); no streaming.

**Spec:** `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md` §6c (native Gemini handler), pulled forward into Phase 1 per the 2026-06-07 decision (native path is Gemini's real upgrade; `json_schema` stays isolated to Phase 2). Branch: continue on `feat/111-phase1`.

**Conventions:** run tests with `.venv/bin/pytest -m "not live"` (plain `pytest`/`python` aren't on PATH; `.env` auto-loads keys so always pass `-m "not live"`). **Baseline test count at start of this plan: 1228 passed, 1 skipped.**

---

## ⚠️ SDK field names to VERIFY against the installed package (no guessed param on a paid call)

The authoritative Gemini docs confirm: model id `"gemini-3.1-flash-lite"` (bare, **no** `models/` prefix natively), `thinking_config` uses **`thinking_level`** (values `minimal/low/medium/high`; `minimal` = floor for flash-lite, full-off unsupported), `response_mime_type="application/json"`, output cap 65,536, and `usage_metadata` exposes a `thoughts_token_count`. The docs did **not** pin: the exact `genai.Client(api_key=…, http_options=…)` signature, and the `usage_metadata` count field names. **The implementer MUST confirm these against the installed `google-genai` package** (`from google.genai import types; help(types.GenerateContentConfig)`, inspect `usage_metadata`) before the live smoke. The candidate names below (`prompt_token_count` / `candidates_token_count` / `total_token_count`) are the standard google-genai names — verify, don't assume. The **live smoke (Joseph fires)** is the final gate.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | add `google-genai` to dependencies |
| `common/call_model.py` | Modify | add `_call_gemini`; reroute `provider=="gemini"` dispatch; drop the gemini `models/`-prefix branch in `_call_openai_compat` (compat-only, now dead for gemini) |
| `common/tests/test_call_model.py` | Modify | TDD: `_call_gemini` builds the right config + maps usage→tuple, via a mocked `genai.Client` |
| `docs/reference/model-provider-api-calls.md` | Modify | correct the Gemini section (native handler shipped; `thinking_level` not `thinking_budget`) |

---

## Task 1: Add the `google-genai` dependency

**Files:** Modify `pyproject.toml`.

- [ ] **Step 1: Read the current `[project] dependencies` (or `[tool.poetry.dependencies]`) block** in `pyproject.toml` to match its exact style (PEP 621 list vs poetry table).

- [ ] **Step 2: Add `google-genai`** to the dependencies in the matching style (e.g. PEP 621: add `"google-genai>=1.0"` to the `dependencies` list — confirm the current published major; if unsure, pin loosely `"google-genai"`).

- [ ] **Step 3: Install into the venv.**

Run: `.venv/bin/pip install google-genai`
Expected: installs `google-genai` + its `google-*` deps.

- [ ] **Step 4: Verify the import + introspect the real API** (this is the "no guessed param" check).

Run:
```
.venv/bin/python -c "from google import genai; from google.genai import types; print(genai.__name__); print([a for a in dir(types.GenerateContentConfig) if not a.startswith('_')][:40])"
```
Expected: prints without error; the attribute list shows `system_instruction`, `temperature`, `max_output_tokens`, `response_mime_type`, `thinking_config`. **Record the real names** for Task 2. Also inspect the usage field: after Task 2's first mock you'll assert these, but note the canonical names here.

- [ ] **Step 5: Commit.**

```bash
git add pyproject.toml
git commit -m "build: add google-genai dependency for native Gemini handler (#111 Phase 1)"
```

---

## Task 2: Implement `_call_gemini` + reroute dispatch

**Files:** Modify `common/call_model.py`; Modify `common/tests/test_call_model.py`.

**Context:** `call_model()` dispatches by `req.provider`; `gemini` currently routes to `_call_openai_compat(...)` with the compat base_url + a `models/`-prefix hack. Replace that branch with `_call_gemini(req)`. The handler must return the SAME 5-tuple every other handler returns: `(text: str, input_tokens: int, output_tokens: int, stop_reason: str | None, raw)`. `call_model` already wraps it into `ModelResponse` and stamps latency — do NOT duplicate timing in the handler.

- [ ] **Step 1: Write the failing tests** in `common/tests/test_call_model.py`. Read the existing tests first to match the module's mocking idiom (how `_call_openai_compat`/`_call_anthropic` are tested — they likely monkeypatch the SDK client). Mock the genai client so NO network call fires:

```python
def test_call_gemini_builds_config_and_maps_usage(monkeypatch):
    import common.call_model as cm
    from common.call_model import ModelRequest

    captured = {}

    class _FakeResp:
        text = '{"ok": true}'
        # shape mirrors google-genai usage_metadata; VERIFY field names in Task 1
        class usage_metadata:
            prompt_token_count = 11
            candidates_token_count = 7
            total_token_count = 18
            thoughts_token_count = 0
        candidates = []  # finish-reason path tolerated as None

    class _FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp()

    class _FakeClient:
        def __init__(self, **kwargs): captured["client_kwargs"] = kwargs
        models = _FakeModels()

    # genai.Client(...) → fake; the handler calls cm.genai.Client(...)
    monkeypatch.setattr(cm.genai, "Client", _FakeClient)
    monkeypatch.setattr(cm.settings, "gemini_api_key", "test-key", raising=False)

    req = ModelRequest(provider="gemini", model="gemini-3.1-flash-lite",
                       prompt="hello", system="be terse", json_mode=True, max_tokens=2048)
    resp = cm.call_model(req)

    assert resp.text == '{"ok": true}'
    assert resp.input_tokens == 11 and resp.output_tokens == 7
    assert resp.provider == "gemini" and resp.model == "gemini-3.1-flash-lite"
    # model id passed BARE (no "models/" prefix) on the native path
    assert captured["model"] == "gemini-3.1-flash-lite"
    # config carried our knobs — assert via the GenerateContentConfig the handler built
    cfg = captured["config"]
    # cfg is a types.GenerateContentConfig (or dict) — assert response_mime_type + thinking_level minimal
    # (adapt the access to whatever the handler constructs; see Step 3)

def test_call_gemini_requires_api_key(monkeypatch):
    import common.call_model as cm
    from common.call_model import ModelRequest, ModelConfigError
    monkeypatch.setattr(cm.settings, "gemini_api_key", "", raising=False)
    with pytest.raises(ModelConfigError):
        cm.call_model(ModelRequest(provider="gemini", model="gemini-3.1-flash-lite", prompt="x"))
```

(Adjust the `cfg` assertion in Step 1 once Step 3 fixes whether the handler passes `config=` as a `types.GenerateContentConfig` or a plain dict. Prefer the typed `types.GenerateContentConfig` — then assert `cfg.response_mime_type == "application/json"` and `cfg.thinking_config.thinking_level == "minimal"`.)

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_call_model.py -k "gemini" -v -m "not live"`
Expected: FAIL — `_call_gemini` not defined / `cm.genai` not imported.

- [ ] **Step 3: Implement.** In `common/call_model.py`:

Add the import near the top (alongside `import anthropic`):
```python
from google import genai
from google.genai import types as genai_types
```

Replace the `elif req.provider == "gemini":` branch in `call_model()` with:
```python
    elif req.provider == "gemini":
        text, input_tokens, output_tokens, stop_reason, raw = _call_gemini(req)
```

Add the handler (sibling to `_call_anthropic`). VERIFY the `usage_metadata` field names + `Client` signature from Task 1 and adjust:
```python
def _call_gemini(req: ModelRequest) -> tuple[str, int, int, str | None, Any]:
    if not settings.gemini_api_key:
        raise ModelConfigError("GEMINI_API_KEY not set")
    # google-genai Client; timeout via http_options (ms). Verify exact kwarg in Task 1.
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai_types.HttpOptions(timeout=settings.llm_timeout_seconds * 1000),
    )
    # Gemini 3.x: thinking control is thinking_level (NOT thinking_budget); flash-lite
    # floor is "minimal" (full-off unsupported) — our extraction workload wants minimal.
    thinking_level = (req.extra_body or {}).get("thinking_level", "minimal")
    cfg_kwargs: dict[str, Any] = {
        "temperature": req.temperature,
        "max_output_tokens": req.max_tokens,
        "thinking_config": genai_types.ThinkingConfig(thinking_level=thinking_level),
    }
    if req.system is not None:
        cfg_kwargs["system_instruction"] = req.system
    if req.json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"
    config = genai_types.GenerateContentConfig(**cfg_kwargs)

    resp = client.models.generate_content(
        model=req.model,              # bare id; no "models/" prefix on the native path
        contents=req.prompt,
        config=config,
    )
    text = resp.text or ""
    usage = resp.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
    # finish reason: candidates[0].finish_reason if present, else None
    stop_reason = None
    cands = getattr(resp, "candidates", None) or []
    if cands:
        fr = getattr(cands[0], "finish_reason", None)
        stop_reason = str(fr) if fr is not None else None
    return text, input_tokens, output_tokens, stop_reason, resp
```

Then **remove the now-dead gemini `models/`-prefix branch** in `_call_openai_compat` (the `if req.provider == "gemini" and not req.model.startswith("models/")` lines) — gemini no longer routes there. Confirm no other provider relied on it (only gemini did).

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest common/tests/test_call_model.py -k "gemini" -v -m "not live"`

- [ ] **Step 5: Full suite.** `.venv/bin/pytest -m "not live" -q` → green (report count). Confirm the existing gemini-via-compat tests (if any) were updated/removed to reflect the native route — search: `grep -n "gemini" common/tests/test_call_model.py` and fix any test still asserting the `models/` prefix or compat base_url for gemini.

- [ ] **Step 6: Commit.**

```bash
git add common/call_model.py common/tests/test_call_model.py
git commit -m "feat(call_model): native google-genai handler for gemini (json-mode + minimal thinking) (#111 Phase 1)"
```

---

## Task 3: Correct the Gemini section in the provider reference

**Files:** Modify `docs/reference/model-provider-api-calls.md`.

- [ ] **Step 1: Read the current `### gemini` section** (around the openai-compat line + the "⚠️ FINDING / second-class path" block + the thinking-control table row).

- [ ] **Step 2: Update it** to reflect reality:
  - Gemini now uses the **native `google-genai` SDK** (`_call_gemini`), not the openai-compat shim.
  - Thinking control is **`thinking_level`** (values `minimal/low/medium/high`), NOT `thinking_budget`; flash-lite floor is `minimal` (full-off unsupported); `thinking_budget` + `thinking_level` together = 400 error.
  - JSON: `response_mime_type="application/json"` (json-mode, shipped Phase 1); `response_json_schema` is the Phase 2 enhancement.
  - Resolve the "⚠️ FINDING / TODO verify" markers for the now-shipped pieces (leave `response_json_schema` flagged as Phase 2).
  - Update the thinking-control matrix row for gemini from "⚠️ TODO verify" to the verified `thinking_level: minimal` native shape.

- [ ] **Step 3: Commit.**

```bash
git add docs/reference/model-provider-api-calls.md
git commit -m "docs(reference): gemini native handler + thinking_level (correct thinking_budget) (#111 Phase 1)"
```

---

## Final verification (before Checkpoint A / tagging `v0.5.6`)

- [ ] `.venv/bin/pytest -m "not live" -q` fully green (report count).
- [ ] `grep -n "models/" common/call_model.py` → the gemini compat-prefix branch is gone (no stale gemini compat logic).
- [ ] **Live smoke (Joseph fires — API cost):** one `kdb-orchestrate --model gemini-3.1-flash-lite --emit-kpis` run on the sandbox → confirm it (a) completes via the native path, (b) produces valid JSON output (no new quarantines vs the compat baseline), (c) `measurements.json` shows sane token counts (input/output non-zero, mapped from `usage_metadata`). This is the gate that the SDK field names + config are correct.
- [ ] Update `docs/TASKS.md` (#111 Phase 1 — Gemini native handler shipped).
- [ ] **Then Checkpoint A:** cut **`v0.5.6`** (RELEASES.md entry + annotated tag) and Joseph fires the clean-slate batch-1 benchmark (deepseek-v4-flash, qwen3.5-flash, gpt-5.4-mini, gemini-3.1-flash-lite each `--emit-kpis` → `kdb-benchmark score`). Leaderboard then shows gemini `@v0.5.4` (compat) → `@v0.5.6` (native), isolating the native-vs-shim effect; the `response_json_schema` effect lands at `@v0.5.7` (Phase 2).

---

## Self-Review

- **Spec coverage:** §6c native `_call_gemini` handler → Task 2; the json-mode-now / schema-Phase-2 split → handler omits `response_json_schema` (Task 2) and the reference doc records it (Task 3); dependency → Task 1. The thinking decision (`thinking_level: minimal`, no full-off) is encoded in the handler + corrected in the reference.
- **No guessed params on paid calls:** the SDK field names that the docs didn't pin (`Client` signature, `usage_metadata` counts) are explicitly flagged for Task-1 introspection + Task-2 mock assertion + the Joseph-fired live smoke as the final gate. The verified facts (model id, `thinking_level` values, `response_mime_type`, output cap) are baked in.
- **Integration seam:** `_call_gemini` returns the identical 5-tuple contract; `call_model` wraps it; ModelRequest gains NO new field in Phase 1 (json_mode suffices); telemetry/cost/callers unchanged. `response_json_schema` deferred → ModelRequest's optional schema field is a Phase-2 change, not here.
- **Placeholders:** the `cfg`/usage assertions in the Task-2 test are deliberately "adapt to the constructed config / verified field names" because the exact `types.GenerateContentConfig` accessors must be confirmed against the installed SDK in Task 1; the behavior pinned (bare model id, json-mode → application/json, thinking_level minimal, usage→tuple mapping, api-key guard) is unambiguous and the production handler code is complete.
