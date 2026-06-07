# `common/models.json` Model Pool + Cost/Ctx Diagnostics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reinstate the user-owned model pool (`common/models.json`) wired to the live path, and restore the two diagnostics it powers — per-call `cost_usd` and a proactive context-overrun guard.

**Architecture:** Three layers — `common/models.json` (data: pool + curation ledger) → `common/model_pool.py` (resolver: alias→`ModelSpec`, dropped-guard, token-estimate helpers) → `call_model.py` (engine, untouched). The `ModelSpec` is resolved once at the CLI and its fields are threaded **additively** into the existing decomposed `enrich_one`/`compile_one` params. Cost is pure arithmetic in each telemetry path from threaded prices × aggregated tokens. The ctx guard runs once per source after prompt assembly and routes overruns into existing per-source quarantine.

**Tech Stack:** Python 3, stdlib `json`/`dataclasses`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-06-models-json-pool-design.md` (#110).

**Conventions to honor:**
- Run the suite with `pytest -m "not live"` (`.env` auto-loads keys; plain `pytest` fires live calls — see [[feedback_user_fires_api_cost_runs]]).
- `common/config/__init__.py` is the plain-`os.getenv` settings pattern — follow it, no pydantic.
- Local-time ISO with offset for any datetimes ([[feedback_local_time_everywhere]]).

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `common/models.json` | Create | User-owned pool (active + dropped entries), seeded verbatim from the recovered file |
| `common/model_pool.py` | Create | `ModelSpec`, `load_pool()`, `resolve(id)`, `PoolError`/dropped-guard, `estimate_prompt_tokens()`, `fits_context()` |
| `common/tests/test_model_pool.py` | Create | Resolver + dropped-guard + estimate/fits tests |
| `orchestrator/kdb_orchestrate.py` | Modify | `--model` resolves via pool (default string `deepseek-v4-flash` unchanged, now resolves to the active entry); demote `--provider` to escape hatch; thread `ModelSpec` fields |
| `common/types.py` | Modify | Add `cost_usd: float = 0.0` to `RespStatsRecord` |
| `common/llm_telemetry.py` | Modify | `build_resp_stats`: `price_in`/`price_out` kwargs → compute `cost_usd` from aggregated tokens |
| `ingestion/enrich/replay_archive.py` | Modify | Add `cost_usd: float = 0.0` to `SidecarPayload` |
| `ingestion/enrich/enrich.py` | Modify | Compute Pass-1 `cost_usd` from threaded prices × aggregated tokens |
| `ingestion/enrich/pass1_caller.py` | Modify | ctx guard after prompt build, before retry loop |
| `compiler/compiler.py` | Modify | ctx guard after `state["prompt"]`, before model call; thread cost prices to `build_resp_stats` |
| `scripts/verify_structured_output_parity.py` | Modify | Repoint stale `tools/benchmark/models.json` ref → `common/models.json` |

---

# PHASE 1 — Pool + resolver (foundation; independently shippable)

### Task 1.1: Seed `common/models.json` + build the resolver

**Files:**
- Create: `common/models.json`
- Create: `common/model_pool.py`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Seed the data file, then apply the DeepSeek id renames.** Recover the pool, then rename three ids per the id scheme (direct route ⇒ bare slug; alternate routes ⇒ `:route` suffix):

```bash
git show 01a1d2d^:tools/benchmark/models.json > common/models.json
```

Apply these `id` edits (the `model`/`provider`/other fields stay untouched — only the alias `id` changes):
- `"deepseek-v4-flash:direct"` → `"deepseek-v4-flash"`   (active, provider `deepseek` — the default)
- `"deepseek-v4-pro:direct"` → `"deepseek-v4-pro"`        (dropped, provider `deepseek`)
- `"deepseek-v4-flash"` (the entry whose `provider` is `alibaba`) → `"deepseek-v4-flash:alibaba"`

Leave `"deepseek-v4-flash:cloud"` and all non-DeepSeek ids verbatim. Verify it's still the 14-entry array (4 dropped: `deepseek-v4-flash:alibaba`, `deepseek-v4-flash:cloud`, `deepseek-v4-pro`, plus `qwen-flash-us`, `gemini-3-flash-preview` — confirm count). Confirm there is now exactly one entry with `id == "deepseek-v4-flash"` and it is the active `provider: deepseek` one.

- [ ] **Step 2: Write the failing resolver test.**

```python
# common/tests/test_model_pool.py
import pytest
from common.model_pool import ModelSpec, resolve, PoolError, load_pool

def test_resolve_active_entry_returns_modelspec():
    spec = resolve("deepseek-v4-flash")   # active, direct route, the default
    assert isinstance(spec, ModelSpec)
    assert spec.provider == "deepseek"
    assert spec.model == "deepseek-v4-flash"
    assert spec.ctx_window == 1000000
    assert spec.extra_body == {"thinking": {"type": "disabled"}}
    assert spec.price_in == 0.14 and spec.price_out == 0.28

def test_resolve_unknown_id_errors_with_id_list():
    with pytest.raises(PoolError) as e:
        resolve("no-such-model")
    assert "deepseek-v4-flash" in str(e.value)  # lists available ids

def test_resolve_dropped_entry_errors_with_reason():
    with pytest.raises(PoolError) as e:
        resolve("deepseek-v4-flash:alibaba")  # the dropped alibaba route
    msg = str(e.value)
    assert "dropped" in msg.lower()
    assert "dominated" in msg  # echoes dropped_reason

def test_load_pool_returns_all_entries_including_dropped():
    pool = load_pool()
    ids = {e["id"] for e in pool}
    assert "deepseek-v4-flash" in ids        # active default
    assert "deepseek-v4-flash:alibaba" in ids  # dropped ones still present (ledger)
```

- [ ] **Step 3: Run it — expect failure.**

Run: `pytest common/tests/test_model_pool.py -v`
Expected: FAIL — `ModuleNotFoundError: common.model_pool`.

- [ ] **Step 4: Implement `common/model_pool.py`.**

```python
# common/model_pool.py
"""model_pool — user-owned model registry loaded from common/models.json.

The JSON is DATA (pool + per-model knobs + curation ledger); this module is
the LOOKUP layer (alias -> ModelSpec, dropped-guard, token-estimate helpers).
call_model.py (the engine) is untouched and still takes explicit provider+model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

_POOL_PATH = Path(__file__).with_name("models.json")
WORDS_TO_TOKENS = 1.3  # deliberate over-estimate; no tokenizer dependency


class PoolError(ValueError):
    """Unknown id, or selection of a dropped (documented-rejected) model."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    model: str
    ctx_window: int | None = None
    max_output_tokens: int | None = None
    use_completion_tokens: bool = False
    extra_body: dict | None = None
    price_in: float = 0.0
    price_out: float = 0.0


@lru_cache(maxsize=1)
def load_pool() -> list[dict]:
    """Load the raw pool (all entries, including dropped)."""
    return json.loads(_POOL_PATH.read_text(encoding="utf-8"))


def resolve(model_id: str) -> ModelSpec:
    """alias id -> ModelSpec. Raises PoolError on unknown or dropped id."""
    by_id = {e["id"]: e for e in load_pool()}
    entry = by_id.get(model_id)
    if entry is None:
        avail = ", ".join(sorted(e["id"] for e in load_pool() if not e.get("dropped")))
        raise PoolError(f"Unknown model id {model_id!r}. Available: {avail}")
    if entry.get("dropped"):
        reason = entry.get("dropped_reason", "(no reason recorded)")
        raise PoolError(f"Model {model_id!r} is dropped: {reason}")
    return ModelSpec(
        id=entry["id"],
        provider=entry["provider"],
        model=entry["model"],
        ctx_window=entry.get("ctx_window"),
        max_output_tokens=entry.get("max_output_tokens"),
        use_completion_tokens=entry.get("use_completion_tokens", False),
        extra_body=entry.get("extra_body"),
        price_in=entry.get("price_in", 0.0),
        price_out=entry.get("price_out", 0.0),
    )
```

- [ ] **Step 5: Run tests — expect pass.**

Run: `pytest common/tests/test_model_pool.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit.**

```bash
git add common/models.json common/model_pool.py common/tests/test_model_pool.py
git commit -m "feat(model_pool): seed common/models.json + resolver with dropped-guard (#110)"
```

---

### Task 1.2: Wire `kdb-orchestrate --model` through the pool

**Files:**
- Modify: `orchestrator/kdb_orchestrate.py:997-998` (defaults), `:1048` (run call), `_build_parser`, and `run()` model-threading
- Test: add to `orchestrator/tests/` (match the existing orchestrate test module)

- [ ] **Step 1: Write the failing CLI-resolution test.** Find the existing parser/dispatch test module (`grep -rl "_build_parser\|def test.*orchestrate" orchestrator/tests/`), add:

```python
def test_provider_default_is_none_escape_hatch():
    # --provider is demoted to an escape hatch; its default must be None so the
    # pool supplies the provider for known ids. (This is the fail-first driver:
    # the current default is "deepseek".) The --model default STRING is
    # unchanged ("deepseek-v4-flash") — Task 1.1's rename makes that same string
    # now resolve to the ACTIVE direct entry instead of the dropped alibaba one.
    parser = _build_parser()
    args = parser.parse_args(["--vault-root", "/tmp/x", "--pipeline", "p"])
    assert args.provider is None
    assert args.model == "deepseek-v4-flash"

def test_default_model_resolves_to_active_deepseek():
    # Guard: the default id resolves to the active direct entry, not a dropped id.
    from common.model_pool import resolve
    parser = _build_parser()
    args = parser.parse_args(["--vault-root", "/tmp/x", "--pipeline", "p"])
    spec = resolve(args.model)
    assert spec.provider == "deepseek"
    assert spec.model == "deepseek-v4-flash"

def test_unknown_model_id_rejected_when_no_provider_override():
    from common.model_pool import PoolError, resolve
    parser = _build_parser()
    args = parser.parse_args(["--vault-root", "/tmp/x", "--pipeline", "p",
                              "--model", "bogus-id"])
    assert args.provider is None
    with pytest.raises(PoolError):
        resolve(args.model)
```

- [ ] **Step 2: Run it — expect failure.**

Run: `pytest orchestrator/tests/ -k "provider_default or resolves_to_active or unknown_model_id" -v`
Expected: FAIL — `test_provider_default_is_none_escape_hatch` fails because `--provider` currently defaults to `"deepseek"`, not `None`.

- [ ] **Step 3: Demote `--provider` to an escape hatch; keep the `--model` default string.** In `_build_parser` (`orchestrator/kdb_orchestrate.py:997-998`) — the `--model` default string stays `deepseek-v4-flash` (Task 1.1's rename changed what it *resolves to*, not the string); only `--provider` and the help text change:

```python
    p.add_argument("--model", default="deepseek-v4-flash",
                   help="model id from common/models.json (resolves provider + knobs)")
    p.add_argument("--provider", default=None,
                   help="escape hatch: required only when --model is NOT a pool id "
                        "(then --model is treated as a raw SDK model string)")
```

- [ ] **Step 4: Resolve once at the CLI entry, thread fields into `run()`.** In the CLI `main()`/dispatch (where `run(...)` is called near `:1048`), resolve before calling `run`:

```python
    from common.model_pool import resolve, ModelSpec, PoolError
    try:
        spec = resolve(args.model)
        provider, model = spec.provider, spec.model
        use_completion_tokens = spec.use_completion_tokens
        extra_body = spec.extra_body
        ctx_window = spec.ctx_window
        price_in, price_out = spec.price_in, spec.price_out
    except PoolError:
        if args.provider is None:
            raise  # unknown id + no override → surface the PoolError
        # one-off escape hatch: raw model string, no pool metadata
        provider, model = args.provider, args.model
        use_completion_tokens, extra_body, ctx_window = False, None, None
        price_in, price_out = 0.0, 0.0
```

Then extend `run()`'s signature with the new threaded params (defaults preserve current behavior):

```python
def run(
    *, pipeline_id, vault_root, state_root, graph_path,
    provider, model, max_tokens=32768, dry_run=False, limit=None,
    log_level="warning", quiet=False, emit_kpis=False,
    use_completion_tokens=False, extra_body=None, ctx_window=None,
    price_in=0.0, price_out=0.0,
) -> OrchestrateResult:
```

and pass `use_completion_tokens=use_completion_tokens, extra_body=extra_body, ctx_window=ctx_window, price_in=price_in, price_out=price_out` at the `enrich_one(...)` (`:614`) and `compile_one(...)` (`compiler.py:609`, reached via the orchestrate→compile path) call sites. (Tasks 2 and 3 consume these; Task 1.2 only threads them — unused-but-present is fine and keeps the threading change atomic.)

- [ ] **Step 5: Run tests — expect pass.**

Run: `pytest orchestrator/tests/ -k "provider_default or resolves_to_active or unknown_model_id" -v`
Expected: PASS.

- [ ] **Step 6: Full suite — no regressions.**

Run: `pytest -m "not live" -q`
Expected: PASS (1175 + new tests).

- [ ] **Step 7: Commit.**

```bash
git add orchestrator/kdb_orchestrate.py orchestrator/tests/
git commit -m "feat(orchestrate): --model resolves via pool; --provider demoted to escape hatch (#110)"
```

---

### Task 1.3: Repoint the orphan reference

**Files:**
- Modify: `scripts/verify_structured_output_parity.py:18`

- [ ] **Step 1: Repoint the path.** Change the comment/constant referencing `tools/benchmark/models.json` to `common/models.json`. Read the file first to match the exact form (comment vs. a `Path(...)` literal). If it actually *loads* the file, point it at `common.model_pool.load_pool()` instead of a raw path.

- [ ] **Step 2: Verify it imports/runs.**

Run: `python -c "import ast; ast.parse(open('scripts/verify_structured_output_parity.py').read())"`
Expected: no output (parses clean).

- [ ] **Step 3: Commit.**

```bash
git add scripts/verify_structured_output_parity.py
git commit -m "chore: repoint structured-output-parity script to common/models.json (#110)"
```

---

# PHASE 2 — Cost diagnostic (both telemetry paths)

### Task 2.1: Pass-2 `cost_usd` on `RespStatsRecord`

**Files:**
- Modify: `common/types.py` (`RespStatsRecord`, after `token_overrun` ~`:424`)
- Modify: `common/llm_telemetry.py` (`build_resp_stats` signature + body)
- Modify: `compiler/compiler.py:521` (pass `price_in`/`price_out`)
- Test: `common/tests/test_llm_telemetry.py` (existing module)

- [ ] **Step 1: Write the failing cost test.**

```python
def test_cost_usd_uses_aggregated_tokens(make_ctx):
    # price_in=0.14, price_out=0.28 per 1M; aggregated 1,000,000 in / 500,000 out
    rec = build_resp_stats(
        ctx=make_ctx, source_id="s1", provider="deepseek", model="deepseek-v4-flash",
        prompt=_FakePrompt("sys", "usr"), raw_response_text="{}",
        model_response=_resp(input_tokens=10, output_tokens=10),  # final-attempt (ignored for cost)
        extract_ok=True, parse_ok=True, parsed_json={}, schema_ok=True,
        schema_errors=[], semantic_ok=True, semantic_errors=[],
        total_input_tokens=1_000_000, total_output_tokens=500_000,
        price_in=0.14, price_out=0.28,
    )
    assert rec.cost_usd == pytest.approx(0.14 + 0.14)  # 0.14*1.0 + 0.28*0.5

def test_cost_usd_defaults_zero_when_unpriced(make_ctx):
    rec = build_resp_stats(
        ctx=make_ctx, source_id="s1", provider="ollama-local", model="gemma4",
        prompt=_FakePrompt("s", "u"), raw_response_text="{}",
        model_response=_resp(input_tokens=5, output_tokens=5),
        extract_ok=True, parse_ok=True, parsed_json={}, schema_ok=True,
        schema_errors=[], semantic_ok=True, semantic_errors=[],
    )  # no price kwargs
    assert rec.cost_usd == 0.0
```

(Reuse the module's existing `_FakePrompt`/`_resp`/`make_ctx` helpers; match their real names by reading the test file first.)

- [ ] **Step 2: Run it — expect failure.**

Run: `pytest common/tests/test_llm_telemetry.py -k cost_usd -v`
Expected: FAIL — `TypeError: unexpected keyword 'price_in'`.

- [ ] **Step 3a: Add the field to `RespStatsRecord`** (`common/types.py`, right after `token_overrun: bool = False`):

```python
    cost_usd: float = 0.0
```

- [ ] **Step 3b: Add price kwargs + compute in `build_resp_stats`** (`common/llm_telemetry.py`). Add to the signature:

```python
    price_in: float = 0.0,
    price_out: float = 0.0,
```

After the `agg_input_tokens`/`agg_output_tokens` block (~`:159-161`):

```python
    cost_usd = price_in / 1e6 * agg_input_tokens + price_out / 1e6 * agg_output_tokens
```

and pass `cost_usd=cost_usd` into the `RespStatsRecord(...)` constructor.

- [ ] **Step 3c: Thread prices at the Pass-2 call site** (`compiler/compiler.py:521` `build_resp_stats(...)` call). `compile_one` already receives the threaded `price_in`/`price_out` from Task 1.2 — add them to its signature (optional, default `0.0`) and forward into the `build_resp_stats` call.

- [ ] **Step 4: Run tests — expect pass.**

Run: `pytest common/tests/test_llm_telemetry.py -k cost_usd -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add common/types.py common/llm_telemetry.py compiler/compiler.py common/tests/test_llm_telemetry.py
git commit -m "feat(telemetry): Pass-2 cost_usd from aggregated tokens × pool pricing (#110)"
```

---

### Task 2.2: Pass-1 `cost_usd` on the sidecar

**Files:**
- Modify: `ingestion/enrich/replay_archive.py` (`SidecarPayload`)
- Modify: `ingestion/enrich/enrich.py` (compute + thread prices through `enrich_one`)
- Test: `ingestion/enrich/tests/` (sidecar test module)

- [ ] **Step 1: Write the failing test.** In the sidecar test module:

```python
def test_sidecar_carries_cost_usd():
    p = SidecarPayload(
        source_id="s", source_path="s.md", source_content_hash="h",
        request={}, raw_response={}, parsed_envelope={}, override={},
        user_overrides_detected=[], timestamp="2026-06-06T00:00:00-05:00",
        outcome="enriched", cost_usd=0.42,
    )
    from dataclasses import asdict
    assert asdict(p)["cost_usd"] == 0.42
```

- [ ] **Step 2: Run it — expect failure.**

Run: `pytest ingestion/enrich/tests/ -k cost_usd -v`
Expected: FAIL — `unexpected keyword 'cost_usd'`.

- [ ] **Step 3a: Add the field** (`replay_archive.py`, `SidecarPayload`, last field):

```python
    cost_usd: float = 0.0
```

- [ ] **Step 3b: Compute + thread in `enrich.py`.** `enrich_one` gains optional `price_in=0.0, price_out=0.0` kwargs (threaded from Task 1.2). At the success-path payload assembly (`enrich.py:138`), using the aggregated totals already on `call_result`:

```python
    cost_usd = (price_in / 1e6 * call_result.total_input_tokens
                + price_out / 1e6 * call_result.total_output_tokens)
```

and pass `cost_usd=cost_usd` into the `SidecarPayload(...)`. Failure/skipped payloads keep the `0.0` default.

- [ ] **Step 4: Run tests — expect pass.**

Run: `pytest ingestion/enrich/tests/ -k cost_usd -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add ingestion/enrich/replay_archive.py ingestion/enrich/enrich.py ingestion/enrich/tests/
git commit -m "feat(telemetry): Pass-1 sidecar cost_usd from aggregated tokens × pool pricing (#110)"
```

---

# PHASE 3 — Context-overrun pre-flight guard

### Task 3.1: Estimate helpers in `model_pool.py`

**Files:**
- Modify: `common/model_pool.py`
- Test: `common/tests/test_model_pool.py`

- [ ] **Step 1: Write the failing test.**

```python
from common.model_pool import estimate_prompt_tokens, fits_context

def test_estimate_prompt_tokens_words_x_1_3():
    # "a b c d e" system + "f g h i j" user = 10 words -> round(13.0) = 13
    assert estimate_prompt_tokens("a b c d e", "f g h i j") == 13

def test_fits_context_true_when_input_plus_output_within_window():
    assert fits_context(est_input=900, requested_output=90, ctx_window=1000) is True

def test_fits_context_false_when_over():
    assert fits_context(est_input=950, requested_output=90, ctx_window=1000) is False
```

- [ ] **Step 2: Run it — expect failure.**

Run: `pytest common/tests/test_model_pool.py -k "estimate or fits" -v`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement the helpers** (`common/model_pool.py`):

```python
def estimate_prompt_tokens(system: str | None, user: str) -> int:
    text = (system or "") + "\n\n" + user
    return round(len(text.split()) * WORDS_TO_TOKENS)

def fits_context(*, est_input: int, requested_output: int, ctx_window: int) -> bool:
    return est_input + requested_output <= ctx_window
```

- [ ] **Step 4: Run tests — expect pass.**

Run: `pytest common/tests/test_model_pool.py -k "estimate or fits" -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add common/model_pool.py common/tests/test_model_pool.py
git commit -m "feat(model_pool): words×1.3 prompt-token estimate + fits_context helpers (#110)"
```

---

### Task 3.2: Pass-1 guard before the retry loop

**Files:**
- Modify: `ingestion/enrich/pass1_caller.py` (after prompt build ~`:121`, before `for attempt` loop)
- Test: `ingestion/enrich/tests/` (pass1_caller test module)

- [ ] **Step 1: Write the failing test.** The guard must raise the synthetic-`TokenOverrun` failure WITHOUT calling the model when the estimate overruns. Use a monkeypatched `call_model` that fails the test if invoked:

```python
def test_pass1_overrun_quarantines_without_calling_model(monkeypatch):
    import ingestion.enrich.pass1_caller as pc
    monkeypatch.setattr(pc, "call_model",
                        lambda *a, **k: pytest.fail("model called despite overrun"))
    with pytest.raises(pc.TokenOverrunError):   # or the established quarantine signal
        pc.<entrypoint>(..., prompt=_huge_prompt(), ctx_window=100,
                        max_tokens=4096, provider="deepseek", model="m")
```

Match the real entrypoint name + how Pass-1 currently signals a quarantinable failure (read the module: it builds a `Pass1CallResult` / raises — mirror that, reusing the `"TokenOverrun"` exception-type vocab from `common/types.py`).

- [ ] **Step 2: Run it — expect failure.**

Run: `pytest ingestion/enrich/tests/ -k overrun -v`
Expected: FAIL — no guard yet (model gets called).

- [ ] **Step 3: Add the guard.** `pass1_caller` entry gains `ctx_window: int | None = None`. Immediately after `prompt` is assembled and before `for attempt in range(...)`:

```python
    from common.model_pool import estimate_prompt_tokens, fits_context
    if ctx_window is not None:
        est_in = estimate_prompt_tokens(getattr(prompt, "system", None),
                                        getattr(prompt, "user", prompt))
        if not fits_context(est_input=est_in, requested_output=max_tokens,
                            ctx_window=ctx_window):
            # skip-and-quarantine THIS source; no API spend. Use the same
            # failure surface Pass-1 already uses, exception_type "TokenOverrun".
            raise TokenOverrunError(
                f"prompt est {est_in} + out {max_tokens} > ctx_window {ctx_window}")
```

(If Pass-1 returns a result object rather than raising, construct the failed-result with `failure_stage`/exception_type `"TokenOverrun"` instead — match the existing pattern exactly.)

- [ ] **Step 4: Run tests — expect pass.**

Run: `pytest ingestion/enrich/tests/ -k overrun -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add ingestion/enrich/pass1_caller.py ingestion/enrich/tests/
git commit -m "feat(pass1): pre-flight ctx-overrun guard → quarantine, no API spend (#110)"
```

---

### Task 3.3: Pass-2 guard before the model call

**Files:**
- Modify: `compiler/compiler.py` (after `state["prompt"]` set ~`:265`, before `call_model_with_retry`)
- Test: `compiler/tests/` (compile_one test module)

- [ ] **Step 1: Write the failing test.** Mirror 3.2 for Pass-2: monkeypatch `call_model_with_retry` to fail if called; assert `compile_one` returns its quarantine result (`err` populated, one `RespStatsRecord` with `failure_stage`/exception_type `"TokenOverrun"`) when `ctx_window` is tiny.

```python
def test_compile_one_overrun_quarantines_without_model_call(monkeypatch, ...):
    import compiler.compiler as cc
    monkeypatch.setattr(cc, "call_model_with_retry",
                        lambda *a, **k: pytest.fail("model called despite overrun"))
    cs, logs, warns, err = cc.compile_one(job, ..., provider="deepseek",
                                          model="m", max_tokens=32768, ctx_window=50)
    assert cs is None and err is not None
    # and the written RespStatsRecord has failure_exception_type == "TokenOverrun"
```

- [ ] **Step 2: Run it — expect failure.**

Run: `pytest compiler/tests/ -k overrun -v`
Expected: FAIL — model gets called.

- [ ] **Step 3: Add the guard.** `compile_one` gains `ctx_window: int | None = None`. After `state["prompt"]` is set and before the `--- model call ---` block:

```python
    from common.model_pool import estimate_prompt_tokens, fits_context
    if ctx_window is not None:
        est_in = estimate_prompt_tokens(state["prompt"].system, state["prompt"].user)
        if not fits_context(est_input=est_in, requested_output=max_tokens,
                            ctx_window=ctx_window):
            # route into the existing per-source quarantine: set the failure the
            # finally-block build_resp_stats records, exception_type "TokenOverrun",
            # and skip the model call (no API spend). Match compile_one's existing
            # failure-staging mechanism (it always writes one RespStatsRecord).
            ...  # set failure state exactly as other pre-call failures do
```

Read `compile_one`'s existing failure handling (it "always writes exactly one RespStatsRecord in the finally block") and reuse that exact mechanism — do not invent a parallel path.

- [ ] **Step 4: Run tests — expect pass.**

Run: `pytest compiler/tests/ -k overrun -v`
Expected: PASS.

- [ ] **Step 5: Full suite green.**

Run: `pytest -m "not live" -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add compiler/compiler.py compiler/tests/
git commit -m "feat(pass2): pre-flight ctx-overrun guard → quarantine, no API spend (#110)"
```

---

## Final verification (before merge)

- [ ] `pytest -m "not live" -q` fully green.
- [ ] `kdb-orchestrate --help` shows `--model` defaulting to `deepseek-v4-flash` and the `--provider` escape-hatch help text.
- [ ] Live smoke (Joseph fires — API cost): one `kdb-orchestrate --model deepseek-v4-flash --emit-kpis` run on the sandbox vault (`~/Obsidian/Vault-in-place-test-run/`), confirm `cost_usd` is populated and non-zero in the Pass-1 sidecar + Pass-2 `measurements.json`.
- [ ] Update `docs/TASKS.md` (#110 → done narrative) and `docs/CODEBASE_OVERVIEW.md` Milestone Changelog on closure.

---

## Self-Review

- **Spec coverage:** §3 schema → Task 1.1; §4 resolver/CLI/default/orphan → Tasks 1.1–1.3; §5 cost (both paths, aggregated tokens, threaded prices) → Tasks 2.1–2.2; §6 ctx guard (helpers, per-pass placement, quarantine, est_input+output) → Tasks 3.1–3.3. No uncovered section.
- **Placeholders:** Tasks 3.2/3.3 deliberately defer to "match the existing failure-staging mechanism" rather than inventing code, because the exact quarantine surface must be read from the module at execution time — the test (model-not-called + `TokenOverrun` exception-type) pins the required behavior unambiguously. All other steps carry complete code.
- **Type consistency:** `ModelSpec` fields, `resolve`/`PoolError`/`load_pool`/`estimate_prompt_tokens`/`fits_context` names, and `cost_usd`/`price_in`/`price_out` are used identically across all tasks. `fits_context` is keyword-only everywhere it's called.
