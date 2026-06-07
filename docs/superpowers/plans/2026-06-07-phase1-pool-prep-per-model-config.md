# #111 Phase 1 — Pool-prep + Per-model Reasoning/Thinking Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every batch-1 model call *optimal short of `json_schema`* — split the model pool into an active file + a human-only dropped archive, retire the now-dead dropped-guard, swap the roster, and apply per-model reasoning/thinking config — so the `@v0.5.4 → baseline-1` (`v0.5.6`) delta measures the config-optimization effect in isolation.

**Architecture:** All changes sit in the #110 model-pool layer (`common/models.json` data + `common/model_pool.py` lookup) and its two consumers' error-handling. The pool already threads `extra_body` end-to-end (`resolve_models_json → ModelSpec.extra_body → ModelRequest.extra_body → openai-compat SDK`), so per-model reasoning config is **pure data** (a JSON `extra_body` entry) riding the existing path — no engine change. Splitting `dropped` entries out of the active file makes the dropped-guard branch unreachable, so it is deleted (a dropped id now resolves to `UnknownModelError`, "not in the pool").

**Tech Stack:** Python 3, stdlib `json`/`dataclasses`/`functools.lru_cache`, pytest. No new dependencies (Gemini's native SDK is a Phase-2 contingency, not this phase).

**Spec:** `docs/superpowers/specs/2026-06-07-optimal-model-calls-design.md` §4 (Phase 1) + §5 (Checkpoint A). Branch: continue on `feat/111-structured-output-upgrade` (currently merged to `main` at `v0.5.5`/`f82ca4c`) — cut a fresh `feat/111-phase1` off `main` if you prefer isolation.

**Conventions:** run tests with `.venv/bin/pytest -m "not live"` (plain `pytest`/`python` aren't on PATH; `.env` auto-loads keys so always pass `-m "not live"`). **Baseline test count at branch start: 1221 passed, 1 skipped.**

**RESOLVED (2026-06-07, Joseph's verifications):**
- **Task 6 (gpt-5.4-mini reasoning):** ✅ **`reasoning_effort: "low"`** for structured output (Joseph confirmed). Landed.
- **Task 7 (gemini thinking):** ❌ **DROPPED FROM PHASE 1 → deferred to Phase 2.** Decision settled: Gemini goes through the **native `google-genai` SDK** handler (`_call_gemini`), where `thinking_config={"thinking_budget":0}` and `response_json_schema` are delivered together (see `docs/reference/model-provider-api-calls.md` "⚠️ FINDING" + spec §6c). No compat probe; building the native handler for thinking-only in Phase 1 would be premature — it lands with the schema work in Phase 2.

Tasks 1–6 done. Task 7 carried to Phase 2.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `common/models_dropped.json` | Create | Pure human archive of dropped entries (`dropped`/`dropped_reason` kept). **Code never reads it.** |
| `common/models.json` | Modify | Active entries only — no entry carries a `dropped` key. Roster swaps applied here. |
| `common/model_pool.py` | Modify | Delete `DroppedModelError` + the dropped-guard branch; simplify the avail-id list; update `load_pool` docstring. |
| `common/tests/test_model_pool.py` | Modify | Repoint the 3 dropped-guard tests to the new "moved-out → UnknownModelError" + "load_pool active-only" behavior. |
| `orchestrator/kdb_orchestrate.py` | Modify | Drop the `DroppedModelError` import (`:48`); rewrite the obsolete except-block comment (`:1074-1077`). |
| `orchestrator/tests/test_kdb_orchestrate.py` | Modify | Repoint `test_main_dropped_model_errors_despite_provider_override` (`:879`) — a moved-out id is now an escape-hatch passthrough with `--provider`, `UnknownModelError` without. |

**Final active roster** (after Tasks 1+5): `haiku-4.5`, `sonnet-4.6`, `gpt-5.4-mini`, `gemma-4-12b-qat`, `qwen3.5-flash`, `gemini-3.1-flash-lite`, `qwen3.6-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`, `grok-4.20-0309-non-reasoning`.
**Archive** (`models_dropped.json`): `gemini-3-flash-preview`, `deepseek-v4-flash:cloud`, `qwen-flash-us`, `deepseek-v4-flash:alibaba`, `grok-4-1-fast-reasoning`.

> **OPEN MICRO-DECISION (confirm with Joseph before Task 5):** spec §4a says "Add/replace ollama-local model with `gemma-4-12b-qat`." This plan **replaces** the existing `gemma4-obsidian-bench` alias (a benchmark-specific name) with `gemma-4-12b-qat`. If Joseph wants both kept, make it an *add* instead.

---

## Task 1: Split the pool — `models.json` active-only + `models_dropped.json` archive

**Files:**
- Create: `common/models_dropped.json`
- Modify: `common/models.json`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Write the failing tests for the split.** Append to `common/tests/test_model_pool.py`:

```python
import json as _json
from pathlib import Path as _Path

def test_active_pool_has_no_dropped_entries():
    # After the split, models.json holds ACTIVE entries only.
    active = _json.loads((_Path("common/models.json")).read_text(encoding="utf-8"))
    assert all("dropped" not in e for e in active), \
        "models.json must not contain dropped entries after the split"

def test_dropped_archive_is_valid_json_and_holds_the_moved_entries():
    arch = _json.loads((_Path("common/models_dropped.json")).read_text(encoding="utf-8"))
    ids = {e["id"] for e in arch}
    assert {"gemini-3-flash-preview", "deepseek-v4-flash:cloud",
            "qwen-flash-us", "deepseek-v4-flash:alibaba"} <= ids
    assert all(e.get("dropped") is True and e.get("dropped_reason") for e in arch), \
        "archive entries keep their dropped/dropped_reason record"
```

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_model_pool.py -k "active_pool_has_no_dropped or dropped_archive" -v -m "not live"`
Expected: FAIL — `models_dropped.json` does not exist / `models.json` still has dropped entries.

- [ ] **Step 3: Create `common/models_dropped.json`** with the four currently-dropped entries moved verbatim (copy their exact objects from `models.json` — `gemini-3-flash-preview`, `deepseek-v4-flash:cloud`, `qwen-flash-us`, `deepseek-v4-flash:alibaba`, each keeping its `dropped`/`dropped_reason`). Wrap as a JSON array. Add a leading sentinel comment is not possible in JSON; instead the file is documented by its filename + this plan.

- [ ] **Step 4: Edit `common/models.json`** — delete those four entries from the array. The remaining entries must carry **no** `dropped` key (the four removed were the only ones). Active entries after this step: `haiku-4.5`, `sonnet-4.6`, `gpt-5.4-mini`, `grok-4-1-fast-reasoning` (dropped in Task 5), `gemma4-obsidian-bench` (renamed in Task 5), `qwen3.5-flash`, `gemini-3.1-flash-lite`, `qwen3.6-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`.

- [ ] **Step 5: Run — expect pass.** `.venv/bin/pytest common/tests/test_model_pool.py -k "active_pool_has_no_dropped or dropped_archive" -v -m "not live"`

- [ ] **Step 6: Commit.**

```bash
git add common/models.json common/models_dropped.json common/tests/test_model_pool.py
git commit -m "feat(pool): split models.json (active) / models_dropped.json (human archive) (#111 Phase 1)"
```

---

## Task 2: Retire the dropped-guard in `model_pool.py`

**Files:**
- Modify: `common/model_pool.py`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Rewrite the three existing dropped-guard tests** in `common/tests/test_model_pool.py` to the new behavior. (a) Remove `DroppedModelError` from the top import block (lines 2–9 → keep `ModelSpec, resolve_models_json, PoolError, UnknownModelError, load_pool`). (b) Replace the bodies:

```python
def test_dropped_id_now_raises_unknown_model_error():
    # Post-split: a formerly-dropped id is simply not in the active pool.
    with pytest.raises(UnknownModelError):
        resolve_models_json("qwen-flash-us")  # moved to models_dropped.json

def test_moved_out_route_raises_unknown_model_error():
    with pytest.raises(UnknownModelError):
        resolve_models_json("deepseek-v4-flash:alibaba")  # archived route

def test_load_pool_returns_active_entries_only():
    ids = {e["id"] for e in load_pool()}
    assert "deepseek-v4-flash" in ids              # active default
    assert "deepseek-v4-flash:alibaba" not in ids  # archived, NOT loaded by code
```

(Delete the old `test_dropped_id_raises_dropped_model_error`, `test_resolve_dropped_entry_errors_with_reason`, and `test_load_pool_returns_all_entries_including_dropped`.)

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_model_pool.py -v -m "not live"`
Expected: FAIL — `DroppedModelError` still imported elsewhere / `resolve_models_json("qwen-flash-us")` raises `DroppedModelError` not `UnknownModelError` (until the file split from Task 1 is in — if Task 1 committed, it now raises UnknownModelError already and these pass; the import line is the remaining failure once Step 3 lands).

- [ ] **Step 3: Edit `common/model_pool.py`.** Delete the `DroppedModelError` class (lines 36–37) and rewrite `resolve_models_json` to drop the dropped-guard branch and simplify the avail list:

```python
@lru_cache(maxsize=1)
def load_pool() -> list[dict]:
    """Load the active pool from models.json. Dropped entries live in
    models_dropped.json (a human archive the code never reads)."""
    return json.loads(_POOL_PATH.read_text(encoding="utf-8"))


def resolve_models_json(model_id: str) -> ModelSpec:
    """alias id -> ModelSpec. Raises UnknownModelError for an id not in the
    active pool (dropped ids were archived out of models.json)."""
    by_id = {e["id"]: e for e in load_pool()}
    entry = by_id.get(model_id)
    if entry is None:
        avail = ", ".join(sorted(e["id"] for e in load_pool()))
        raise UnknownModelError(f"Unknown model id {model_id!r}. Available: {avail}")
```

(Keep everything from the `thinking` translation block onward unchanged — lines 70–92 in the original.) Also update the module docstring line 4: `the LOOKUP layer (alias -> ModelSpec) plus token-estimate helpers` (drop "dropped-guard"), and the `PoolError` docstring line 29 to `"""Base: unknown id or invalid pool entry."""`.

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest common/tests/test_model_pool.py -v -m "not live"`

- [ ] **Step 5: Commit.**

```bash
git add common/model_pool.py common/tests/test_model_pool.py
git commit -m "feat(pool): retire dead dropped-guard; dropped id -> UnknownModelError (#111 Phase 1)"
```

---

## Task 3: Update the orchestrator for the retired guard

**Files:**
- Modify: `orchestrator/kdb_orchestrate.py`
- Test: `orchestrator/tests/test_kdb_orchestrate.py`

- [ ] **Step 1: Rewrite the orchestrate test** at `orchestrator/tests/test_kdb_orchestrate.py:879`. The old `test_main_dropped_model_errors_despite_provider_override` asserted a dropped id errors *even with* `--provider`. Post-retirement, an archived id is unknown → with `--provider` it takes the escape hatch (raw passthrough, no error); without `--provider` it raises `UnknownModelError`. Replace it (and drop the `common.model_pool.DroppedModelError` reference at `:884`):

```python
def test_main_archived_model_without_provider_raises_unknown(tmp_path, <existing main fixtures>):
    # An archived (formerly-dropped) id is no longer in the active pool: with no
    # --provider override it surfaces UnknownModelError.
    import common.model_pool
    with pytest.raises(common.model_pool.UnknownModelError):
        main([... "--model", "qwen-flash-us"])  # archived; no --provider

def test_main_archived_model_with_provider_uses_escape_hatch(tmp_path, monkeypatch, <existing main fixtures>):
    # With --provider the escape hatch activates (raw passthrough) — match how the
    # other escape-hatch test drives main() and asserts run(...) is reached.
    ...  # assert run is invoked with provider=<override>, model="qwen-flash-us"
```

(Read the existing escape-hatch test in this module — there is one for an unknown id + `--provider` — and mirror its fixture/mocking exactly; reuse its `run` stub so no real run fires.)

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest orchestrator/tests/test_kdb_orchestrate.py -k "archived_model" -v -m "not live"`
Expected: FAIL — `DroppedModelError` import gone / behavior mismatch.

- [ ] **Step 3: Edit `orchestrator/kdb_orchestrate.py`.** Line 48 — remove `DroppedModelError` from the import:

```python
from common.model_pool import resolve_models_json, UnknownModelError, PoolError
```

Lines 1074–1077 — rewrite the now-obsolete comment in the `except UnknownModelError:` block (the logic is unchanged):

```python
    except UnknownModelError:
        # A dropped id is now simply not in the active pool (archived to
        # models_dropped.json), so it arrives here as UnknownModelError. The
        # escape hatch is only for ids not in the pool at all.
        if args.provider is None:
            raise  # unknown id + no override → surface the UnknownModelError
```

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest orchestrator/tests/test_kdb_orchestrate.py -k "archived_model or escape" -v -m "not live"`

- [ ] **Step 5: Commit.**

```bash
git add orchestrator/kdb_orchestrate.py orchestrator/tests/test_kdb_orchestrate.py
git commit -m "refactor(orchestrate): drop DroppedModelError handling after guard retirement (#111 Phase 1)"
```

---

## Task 4: Roster — drop `grok-4-1-fast-reasoning`, add `grok-4.20-0309-non-reasoning`

**Files:**
- Modify: `common/models.json`, `common/models_dropped.json`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Write the failing tests.** Append to `common/tests/test_model_pool.py`:

```python
def test_deprecated_grok_is_archived():
    with pytest.raises(UnknownModelError):
        resolve_models_json("grok-4-1-fast-reasoning")  # deprecated → archived

def test_new_grok_resolves_with_correct_provider_and_pricing():
    spec = resolve_models_json("grok-4.20-0309-non-reasoning")
    assert spec.provider == "xai"
    assert spec.ctx_window == 1_000_000
    assert spec.price_in == 1.25 and spec.price_out == 2.50
    assert spec.extra_body is None  # non-reasoning ⇒ no thinking to disable
```

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_model_pool.py -k "grok" -v -m "not live"`

- [ ] **Step 3: Move `grok-4-1-fast-reasoning` to the archive.** Cut its object from `common/models.json` and append to `common/models_dropped.json` with the drop record:

```json
  {
    "id": "grok-4-1-fast-reasoning",
    "provider": "xai",
    "model": "grok-4-1-fast-reasoning",
    "ctx_window": 2000000,
    "price_in": 0.2,
    "price_out": 0.5,
    "dropped": true,
    "dropped_reason": "deprecated 2026-06; replaced by grok-4.20-0309-non-reasoning."
  }
```

- [ ] **Step 4: Add `grok-4.20-0309-non-reasoning` to `common/models.json`** (active):

```json
  {
    "id": "grok-4.20-0309-non-reasoning",
    "provider": "xai",
    "model": "grok-4.20-0309-non-reasoning",
    "ctx_window": 1000000,
    "price_in": 1.25,
    "price_out": 2.50
  }
```

- [ ] **Step 5: Run — expect pass.** `.venv/bin/pytest common/tests/test_model_pool.py -k "grok" -v -m "not live"`

- [ ] **Step 6: Commit.**

```bash
git add common/models.json common/models_dropped.json common/tests/test_model_pool.py
git commit -m "feat(pool): drop deprecated grok-4-1; add grok-4.20-0309-non-reasoning (#111 Phase 1)"
```

---

## Task 5: Roster — replace the ollama-local model with `gemma-4-12b-qat`

> **Confirm the OPEN MICRO-DECISION above (replace vs add) before this task.** This plan replaces `gemma4-obsidian-bench`.

**Files:**
- Modify: `common/models.json`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Write the failing test.** Append to `common/tests/test_model_pool.py`:

```python
def test_gemma_4_12b_qat_resolves_as_local_zero_price():
    spec = resolve_models_json("gemma-4-12b-qat")
    assert spec.provider == "ollama-local"
    assert spec.price_in == 0.0 and spec.price_out == 0.0
    assert spec.extra_body is None

def test_old_gemma_bench_alias_gone():
    with pytest.raises(UnknownModelError):
        resolve_models_json("gemma4-obsidian-bench")
```

(Also update `test_resolve_local_model_has_zero_price_and_default_knobs` at the top of the file — it resolves `"gemma4-obsidian-bench"`; repoint it to `"gemma-4-12b-qat"` or delete it as redundant with the new test.)

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_model_pool.py -k "gemma" -v -m "not live"`

- [ ] **Step 3: Edit `common/models.json`** — replace the `gemma4-obsidian-bench` entry with:

```json
  {
    "id": "gemma-4-12b-qat",
    "provider": "ollama-local",
    "model": "gemma-4-12b-qat",
    "ctx_window": 65536,
    "price_in": 0.0,
    "price_out": 0.0
  }
```

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest common/tests/test_model_pool.py -k "gemma" -v -m "not live"`

- [ ] **Step 5: Commit.**

```bash
git add common/models.json common/tests/test_model_pool.py
git commit -m "feat(pool): replace gemma4-obsidian-bench with gemma-4-12b-qat (#111 Phase 1)"
```

---

## Task 6: `gpt-5.4-mini` reasoning config — VERIFICATION-GATED (spec Verification #1)

> **BLOCKED until Joseph's probe.** Question: does `gpt-5.4-mini` accept `reasoning_effort:"none"`, and is `"low"` better for our extraction task? Default to `"low"` (OpenAI's recommended extraction floor) unless the probe says `"none"` wins. **Confirm the exact key shape** the openai-compat SDK forwards — `reasoning_effort` (top-level chat-completions param) vs a nested `reasoning.effort`. The probe pins both before this lands; no guessed param on a paid call.

**Files:**
- Modify: `common/models.json`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Write the failing test** (using the verified key — shown with `reasoning_effort:"low"` as the default; substitute the probe's result):

```python
def test_gpt_5_4_mini_carries_reasoning_config():
    spec = resolve_models_json("gpt-5.4-mini")
    assert spec.provider == "openai"
    # Verified shape from Joseph's probe (default: reasoning_effort low).
    assert spec.extra_body == {"reasoning_effort": "low"}
```

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_model_pool.py -k "gpt_5_4_mini_carries" -v -m "not live"`

- [ ] **Step 3: Edit the `gpt-5.4-mini` entry in `common/models.json`** — add the `extra_body` (this rides the existing `resolve → ModelSpec.extra_body → ModelRequest.extra_body → SDK` path; no code change). It merges with any thinking-disable param, but openai has no thinking mapping so `extra_body` is exactly this:

```json
    "extra_body": { "reasoning_effort": "low" }
```

(Insert as a key in the existing `gpt-5.4-mini` object, e.g. after `"use_completion_tokens": true`.)

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest common/tests/test_model_pool.py -k "gpt_5_4_mini_carries" -v -m "not live"`

- [ ] **Step 5: Commit.**

```bash
git add common/models.json common/tests/test_model_pool.py
git commit -m "feat(pool): gpt-5.4-mini reasoning_effort=low (verified) (#111 Phase 1)"
```

---

## Task 7: `gemini-3.1-flash-lite` thinking config — ❌ DEFERRED TO PHASE 2 (not done in Phase 1)

> **RESOLVED 2026-06-07: deferred to Phase 2.** Gemini is settled to use the native `google-genai` SDK handler (`_call_gemini`), where `thinking_config={"thinking_budget":0}` + `response_json_schema` are built together (`docs/reference/model-provider-api-calls.md` "⚠️ FINDING"; spec §6c). The Phase-1 compat-`extra_body` approach below is therefore **not pursued** — kept here only as the record of the path not taken. Do NOT implement this in Phase 1.

<details><summary>Original (not-pursued) Phase-1 compat approach</summary>

**Files:**
- Modify: `common/model_pool.py` (`_THINKING_DISABLE_EXTRA_BODY`), `common/models.json`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Write the failing test** (shown with `thinking_config.thinking_budget=0` as the candidate; substitute the probe's verified shape):

```python
def test_gemini_thinking_disable_generated_from_field():
    spec = resolve_models_json("gemini-3.1-flash-lite")
    assert spec.provider == "gemini"
    assert spec.extra_body == {"thinking_config": {"thinking_budget": 0}}
```

- [ ] **Step 2: Run — expect failure.** `.venv/bin/pytest common/tests/test_model_pool.py -k "gemini_thinking" -v -m "not live"`

- [ ] **Step 3: Edit `common/model_pool.py`** — add the verified mapping to `_THINKING_DISABLE_EXTRA_BODY` (and update the comment so gemini is no longer listed as TODO/no-op):

```python
_THINKING_DISABLE_EXTRA_BODY = {
    "alibaba": {"enable_thinking": False},
    "deepseek": {"thinking": {"type": "disabled"}},
    "gemini": {"thinking_config": {"thinking_budget": 0}},  # verified via compat (#111 V2)
}
```

Then add `"thinking": "disabled"` to the `gemini-3.1-flash-lite` entry in `common/models.json`.

- [ ] **Step 4: Run — expect pass.** `.venv/bin/pytest common/tests/test_model_pool.py -k "gemini_thinking" -v -m "not live"`

- [ ] **Step 5: Commit.**

```bash
git add common/model_pool.py common/models.json common/tests/test_model_pool.py
git commit -m "feat(pool): gemini thinking-disable via compat (verified) (#111 Phase 1)"
```

</details>

---

## Final verification (before Checkpoint A / tagging `v0.5.6`)

- [ ] `.venv/bin/pytest -m "not live" -q` fully green (report count; baseline 1221 + new pool tests, minus the 3 retired/rewritten).
- [ ] `grep -rn "DroppedModelError" --include="*.py" .` returns **nothing** (guard fully retired).
- [ ] `python3 -c "import json; json.load(open('common/models.json')); json.load(open('common/models_dropped.json'))"` — both valid JSON.
- [ ] Update `docs/TASKS.md` (#111 Phase 1 progress).
- [ ] **Then Checkpoint A:** cut **`v0.5.6`** (RELEASES.md entry + annotated tag), and **Joseph fires the clean-slate batch-1 benchmark** — reset sandbox (`docs/reference/test-run-procedure.md`) → run **deepseek-v4-flash, qwen3.5-flash, gpt-5.4-mini, gemini-3.1-flash-lite** each `--emit-kpis` → `kdb-benchmark score` → the leaderboard now shows each model `@v0.5.4` (baseline-0) **and** `@v0.5.6` (baseline-1), the config-optimization delta visible per-model. (API cost — Joseph fires, [[feedback_user_fires_api_cost_runs]].)

---

## Self-Review

- **Spec coverage:** §4a pool-prep — file split (Task 1), dropped-guard retirement (Tasks 2–3), roster drop/add grok (Task 4) + gemma (Task 5); §4b per-model config — gpt-5.4-mini graded reasoning via raw `extra_body` (Task 6), gemini thinking-disable iff compat-confirmed (Task 7); §4c tests — covered per task (active-only load, archived→UnknownModelError, roster resolution, dropped-guard tests updated); §5 Checkpoint A — Final-verification section. deepseek/qwen need no Phase-1 change (already optimal in #110) — correctly omitted.
- **Placeholder scan:** the only deliberate `<...>` placeholders are the orchestrate-test fixtures in Task 3 (the exact `main()` harness + escape-hatch stub must be read from the module at execution time; the *behavior* each test pins is spelled out). All JSON entries and `model_pool.py` edits carry complete content. Tasks 6–7 show the default param shape explicitly and flag that Joseph's probe confirms it before the commit.
- **Type consistency:** `resolve_models_json`/`load_pool`/`UnknownModelError`/`PoolError` names match the source; `ModelSpec.extra_body` is the single field every config task writes through; the deleted `DroppedModelError` is removed from all three referencing sites (model_pool, kdb_orchestrate import + comment, both test modules). Roster ids match between the active/archive files and the tests.
- **Sequencing:** Tasks 1–5 deterministic and ordered (split → retire guard → orchestrator → roster); Tasks 6–7 gated on Joseph's verifications and can land last (or Task 7 be dropped to Phase 2). Each task is independently committable and leaves the suite green.
